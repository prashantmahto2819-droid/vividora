"""Render-time effects: zoom, looks, transitions, music ducking, overlays.

Every function returns ffmpeg filter fragments; render.py composes them.
Times are on the OUTPUT timeline (after cuts), in seconds.
"""

from __future__ import annotations

import math

from pathlib import Path

from .ffmpeg import escape_filter_path

# Colour "looks" — pick by name; a LUT file (.cube) from the library can be used instead.
LOOKS: dict[str, dict] = {
    "none": {"label": "जैसा है", "filter": ""},
    "warm": {"label": "गर्म", "filter": "colorbalance=rs=.06:gs=.01:bs=-.06,eq=saturation=1.08:contrast=1.03"},
    "cinematic": {"label": "सिनेमैटिक", "filter": "eq=contrast=1.1:saturation=0.9:brightness=-0.02,colorbalance=rs=-.03:bs=.07:rm=-.02:bm=.04"},
    "vivid": {"label": "चटख", "filter": "eq=saturation=1.3:contrast=1.06,unsharp=5:5:0.5:5:5:0"},
    "soft": {"label": "सॉफ़्ट", "filter": "eq=contrast=0.95:saturation=0.95,gblur=sigma=0.6"},
    "bw": {"label": "ब्लैक & व्हाइट", "filter": "hue=s=0,eq=contrast=1.12"},
    "cool": {"label": "ठंडा", "filter": "colorbalance=rs=-.05:bs=.06,eq=saturation=1.02"},
    "vintage": {"label": "विंटेज", "filter": "curves=vintage,eq=saturation=0.85,vignette=PI/5"},
    "teal_orange": {"label": "Teal-Orange", "filter": "colorbalance=rs=.08:gs=-.02:bs=-.10:rh=-.06:bh=.10,eq=saturation=1.12:contrast=1.06"},
    "matte": {"label": "Matte", "filter": "curves=m='0/0.06 0.25/0.26 0.75/0.74 1/0.94',eq=saturation=0.92"},
    "moody": {"label": "Moody", "filter": "eq=brightness=-0.06:contrast=1.15:saturation=0.8,colorbalance=bs=.06:bm=.03,vignette=PI/4.5"},
    "golden": {"label": "Golden hour", "filter": "colorbalance=rs=.1:gs=.04:bs=-.08:rm=.05:gm=.02,eq=saturation=1.1:brightness=0.02"},
    "bright": {"label": "Bright & clean", "filter": "eq=brightness=0.05:contrast=1.04:saturation=1.08,unsharp=3:3:0.4"},
    "retro": {"label": "Retro VHS", "filter": "eq=saturation=1.2:contrast=0.95,noise=alls=10:allf=t,colorbalance=rs=.05:bs=.05"},
    "noir": {"label": "Noir", "filter": "hue=s=0,eq=contrast=1.3:brightness=-0.05,vignette=PI/4"},
}

# Global extras stacked after the look (ids → ffmpeg filter)
EXTRAS: dict[str, dict] = {
    "vignette": {"label": "Vignette", "filter": "vignette=PI/4.5"},
    "grain": {"label": "Film grain", "filter": "noise=alls=9:allf=t+u"},
    "sharpen": {"label": "Sharpen", "filter": "unsharp=5:5:0.8:5:5:0"},
    "mirror": {"label": "Mirror (flip)", "filter": "hflip"},
    "letterbox": {"label": "Cinematic bars", "filter": "drawbox=x=0:y=0:w=iw:h=ih*0.07:color=black:t=fill,drawbox=x=0:y=ih*0.93:w=iw:h=ih*0.07:color=black:t=fill"},
    "shake": {"label": "Handheld shake", "filter": "crop=iw-24:ih-24:'12+7*sin(t*37)':'12+7*cos(t*29)',scale=iw+24:ih+24:flags=bicubic"},
    "soft_glow": {"label": "Soft glow", "filter": "split[gl1][gl2];[gl2]gblur=sigma=14[glb];[gl1][glb]blend=all_mode=screen:all_opacity=0.25"},
    "fade_in": {"label": "Fade in", "filter": "fade=t=in:d=0.6"},
}

TRANSITIONS = {
    "none": "कोई नहीं", "flash": "Flash", "dip": "Dip to black", "punch": "Zoom punch", "whip": "Whip blur",
    "glitch": "Glitch", "flashpunch": "Flash + punch",
    # real two-clip transitions (ffmpeg xfade) — these overlap the clips by XFADE_SECONDS
    "x_dissolve": "Dissolve", "x_fade": "Cross fade", "x_fadeblack": "Fade black", "x_fadewhite": "Fade white",
    "x_wipeleft": "Wipe ←", "x_wiperight": "Wipe →", "x_wipeup": "Wipe ↑", "x_wipedown": "Wipe ↓",
    "x_slideleft": "Slide ←", "x_slideright": "Slide →", "x_slideup": "Slide ↑", "x_slidedown": "Slide ↓",
    "x_smoothleft": "Smooth ←", "x_smoothright": "Smooth →", "x_circleopen": "Circle open", "x_circleclose": "Circle close",
    "x_circlecrop": "Circle crop", "x_radial": "Radial", "x_pixelize": "Pixelize", "x_hblur": "Blur",
    "x_zoomin": "Zoom in", "x_squeezeh": "Squeeze", "x_diagtl": "Diagonal", "x_hlslice": "Slices", "x_coverleft": "Cover ←", "x_revealright": "Reveal →",
    "x_fadegrays": "Fade grays", "x_hlwind": "Wind",
}
XFADE_SECONDS = 0.4


def is_xfade(kind: str | None) -> bool:
    return bool(kind) and kind.startswith("x_")


def extras_filter(ids: list[str]) -> str:
    return ",".join(EXTRAS[i]["filter"] for i in ids if i in EXTRAS)


def transition_filters(cuts: list[tuple[float, str]], duration: float) -> tuple[str, str]:
    """Per-cut transitions on the output timeline. Returns (pre_zoom_bump_expr, filters).
    cuts: [(time, kind)]. The zoom bump is added to the zoom expression (punch)."""
    pre, parts = [], []
    flash_t = [t for t, k in cuts if k in ("flash", "flashpunch")]
    if flash_t:
        parts.append(flash_filter(flash_t))
    punch_t = [t for t, k in cuts if k in ("punch", "flashpunch")]
    for t in punch_t[:80]:
        pre.append(f"0.11*exp(-max(0\\,t-{t:.3f})*9)*gte(t\\,{t:.3f})")
    dip_t = [t for t, k in cuts if k == "dip"]
    if dip_t:
        # brightness dips to black and back over ±0.14 s (fade= would blacken everything before st)
        terms = "+".join(f"max(0\\,1-abs(t-{t:.3f})/0.14)" for t in dip_t[:120])
        parts.append(f"eq=brightness='-min(1\\,{terms})':eval=frame")
    whip_t = [t for t, k in cuts if k == "whip"]
    if whip_t:
        en = "+".join(f"between(t\\,{t - 0.09:.3f}\\,{t + 0.09:.3f})" for t in whip_t[:150])
        parts.append(f"gblur=sigma=16:enable='{en}'")
    gl_t = [t for t, k in cuts if k == "glitch"]
    if gl_t:
        en = "+".join(f"between(t\\,{t - 0.06:.3f}\\,{t + 0.1:.3f})" for t in gl_t[:150])
        parts.append(f"rgbashift=rh=14:bh=-14:enable='{en}',noise=alls=40:allf=t:enable='{en}'")
    return "+".join(pre), ",".join(p for p in parts if p)

ZOOM_LEVELS = [1.0, 1.14, 1.0, 1.08, 1.2, 1.0, 1.12]


ZOOM_MODES = {"punch": "Punch-in हर कट पर", "push": "धीरे-धीरे zoom in (Ken Burns)", "inout": "In-Out बारी-बारी",
              "beat": "हर 2 सेकंड punch", "emphasis": "ज़ोर वाले शब्दों पर"}


def zoom_plan(boundaries: list[float], duration: float, strength: float = 1.0,
              min_gap: float = 1.6, max_points: int = 80, mode: str = "punch",
              emphasis: list[float] | None = None) -> list[tuple[float, float]]:
    """Zoom targets: [(time, zoom)]. punch = alternate levels at cuts; push = slow
    continuous push per segment; inout = in on one cut, out on the next; beat = every 2 s;
    emphasis = punch on given times (loud/keyword words)."""
    k = max(0.0, min(2.0, strength))
    if mode == "push":
        pts = []
        marks = sorted(set([0.0, *[b for b in boundaries if b < duration]]))
        for i, b in enumerate(marks[:max_points]):
            end = marks[i + 1] if i + 1 < len(marks) else duration
            pts.append((round(b, 3), 1.0))
            pts.append((round(max(b + 0.05, end - 0.05), 3), round(1.0 + 0.12 * k, 4)))
        return pts or [(0.0, 1.0)]
    if mode == "beat":
        boundaries = [i * 2.0 for i in range(int(duration / 2.0) + 1)]
        min_gap = 1.9
    if mode == "emphasis" and emphasis:
        boundaries = emphasis
        min_gap = 1.2
    if mode == "inout":
        pts, last, i = [], -10.0, 0
        for b in sorted(set([0.0, *boundaries])):
            if b - last < min_gap or b >= duration:
                continue
            pts.append((round(b, 3), round(1.0 + (0.16 * k if i % 2 else 0.0), 4)))
            last, i = b, i + 1
        return pts[:max_points] or [(0.0, 1.0)]
    pts: list[tuple[float, float]] = []
    last = -10.0
    i = 0
    for b in sorted(set([0.0, *boundaries])):
        if b - last < min_gap or b >= duration:
            continue
        z = 1.0 + (ZOOM_LEVELS[i % len(ZOOM_LEVELS)] - 1.0) * k
        pts.append((round(b, 3), round(z, 4)))
        last = b
        i += 1
        if len(pts) >= max_points:
            break
    return pts or [(0.0, 1.0)]


def zoom_expr(points: list[tuple[float, float]], ease: float = 0.3) -> str:
    """Piecewise expression z(t) for ffmpeg: eases to each target over `ease` seconds."""
    if len(points) == 1:
        return f"{points[0][1]:.4f}"
    expr = f"{points[-1][1]:.4f}"
    prev_z = 1.0
    segs = []
    for i, (t0, z) in enumerate(points):
        t1 = points[i + 1][0] if i + 1 < len(points) else 1e9
        segs.append((t0, t1, prev_z, z))
        prev_z = z
    # build from the last segment backwards so nesting stays shallow at the front
    for t0, t1, z0, z1 in reversed(segs):
        ramp = f"({z0:.4f}+({z1:.4f}-{z0:.4f})*min(1\\,(t-{t0:.3f})/{ease}))"
        expr = f"if(between(t\\,{t0:.3f}\\,{t1:.3f})\\,{ramp}\\,{expr})"
    return expr


def zoom_filter(points: list[tuple[float, float]], w: int, h: int, fx: float = 0.5, fy: float = 0.4,
                bump: str = "") -> str:
    """Scale per frame by z(t), then crop back to w×h around the focus point."""
    z = zoom_expr(points)
    if bump:
        z = f"({z})+({bump})"
    return (f"scale=w='trunc(iw*({z})/2)*2':h='trunc(ih*({z})/2)*2':eval=frame:flags=bicubic,"
            f"crop={w}:{h}:x='(iw-{w})*{fx:.3f}':y='(ih-{h})*{fy:.3f}'")


def look_filter(look: str | None, lut_path: Path | None = None) -> str:
    if lut_path is not None:
        return f"lut3d=file='{escape_filter_path(lut_path)}'"
    return LOOKS.get(look or "none", LOOKS["none"])["filter"]


def flash_filter(cut_times: list[float], color: str = "white", alpha: float = 0.55, frames: float = 0.045) -> str:
    """A brief flash at each cut point (whip-style transition without re-encoding segments)."""
    times = [t for t in cut_times if t > 0.1]
    if not times:
        return ""
    enable = "+".join(f"between(t\\,{t - frames:.3f}\\,{t + frames:.3f})" for t in times[:200])
    return f"drawbox=color={color}@{alpha}:t=fill:enable='{enable}'"


def music_chain(voice_label: str, music_index: int, *, volume: float = 0.18, duck: bool = True,
                duration: float, fade: float = 1.5, duck_amount: float = 0.6) -> tuple[str, str]:
    """Mix background music under the voice. Returns (filter_text, output_label).
    duck_amount 0..1 — how much the music drops while someone speaks."""
    fade = max(0.0, min(float(fade), duration / 3))
    m = (f"[{music_index}:a]aformat=sample_rates=48000:channel_layouts=mono,"
         f"atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,volume={volume:.3f}"
         + (f",afade=t=in:d={fade:.2f},afade=t=out:st={max(0.0, duration - fade):.3f}:d={fade:.2f}" if fade > 0 else "")
         + "[mus]")
    if duck:
        da = max(0.05, min(1.0, float(duck_amount)))
        ratio = round(2 + 18 * da, 1)
        chain = (f"{m};{voice_label}asplit[vmain][vside];"
                 f"[mus][vside]sidechaincompress=threshold=0.02:ratio={ratio}:attack=15:release=450:makeup=1[mduck];"
                 f"[vmain][mduck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[amixed]")
    else:
        chain = f"{m};{voice_label}[mus]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[amixed]"
    return chain, "[amixed]"


# ---- voice enhancement ---------------------------------------------------
# Every preset is just a starting point for the sliders in the editor's Audio
# panel; any value the creator sets overrides the preset's.
VOICE_PARAMS = {
    "volume":   {"label": "आवाज़ volume", "min": 0, "max": 2.5, "step": 0.05, "default": 1.0},
    "denoise":  {"label": "noise हटाना", "choices": ["strong", "light", "off"], "default": "strong"},
    "highpass": {"label": "rumble cut (Hz)", "min": 0, "max": 200, "step": 5, "default": 80},
    "bass":     {"label": "bass / गर्माहट (dB)", "min": -12, "max": 12, "step": 0.5, "default": 0},
    "mud":      {"label": "भारीपन कम (300Hz dB)", "min": -12, "max": 6, "step": 0.5, "default": 0},
    "presence": {"label": "साफ़पन / presence (dB)", "min": -12, "max": 12, "step": 0.5, "default": 0},
    "treble":   {"label": "treble / चमक (dB)", "min": -12, "max": 12, "step": 0.5, "default": 0},
    "deess":    {"label": "स-स कम (de-ess)", "min": 0, "max": 1, "step": 0.05, "default": 0},
    "compress": {"label": "आवाज़ बराबर (compress)", "min": 0, "max": 1, "step": 0.05, "default": 0},
    "gate":     {"label": "बीच की साँस/शोर दबाएँ", "min": 0, "max": 1, "step": 0.05, "default": 0},
    "fade_in":  {"label": "fade in (s)", "min": 0, "max": 5, "step": 0.1, "default": 0},
    "fade_out": {"label": "fade out (s)", "min": 0, "max": 5, "step": 0.1, "default": 0},
    "loudness": {"label": "कुल loudness (LUFS)", "min": -24, "max": -9, "step": 0.5, "default": -14},
}
VOICE_PRESETS = {
    "off":     {"label": "कुछ नहीं (original)", "denoise": "off", "highpass": 0},
    "clean":   {"label": "साफ़ (हल्का)", "highpass": 80, "compress": 0.3},
    "studio":  {"label": "Studio (recommended)", "highpass": 80, "bass": 1, "mud": -2, "presence": 3, "treble": 2, "deess": 0.4, "compress": 0.5, "gate": 0.2},
    "soft":    {"label": "Soft / warm (मुलायम)", "highpass": 70, "bass": 3, "mud": -1, "presence": 0.5, "treble": -2, "deess": 0.6, "compress": 0.4, "gate": 0.15},
    "podcast": {"label": "Podcast / radio (भरी हुई)", "highpass": 90, "bass": 2.5, "mud": -3, "presence": 4, "treble": 1, "deess": 0.5, "compress": 0.75, "gate": 0.3},
    "bright":  {"label": "Clear / bright (तेज़ साफ़)", "highpass": 100, "mud": -3, "presence": 5, "treble": 3, "deess": 0.5, "compress": 0.5, "gate": 0.2},
    "phone":   {"label": "Phone mic fix", "highpass": 120, "bass": 2, "mud": -4, "presence": 3, "treble": 1.5, "deess": 0.6, "compress": 0.6, "gate": 0.35},
}


def voice_settings(cfg: dict | None) -> dict:
    """Merge preset defaults with the creator's overrides → final numbers."""
    cfg = dict(cfg or {})
    preset = cfg.get("preset") or "studio"
    out = {k: v["default"] for k, v in VOICE_PARAMS.items()}
    out.update({k: v for k, v in VOICE_PRESETS.get(preset, {}).items() if k != "label"})
    for k, spec in VOICE_PARAMS.items():
        v = cfg.get(k)
        if v is None or v == "":
            continue
        if "choices" in spec:
            if v in spec["choices"]:
                out[k] = v
        else:
            try:
                out[k] = max(spec["min"], min(spec["max"], float(v)))
            except (TypeError, ValueError):
                pass
    out["preset"] = preset
    return out


def voice_chain(cfg: dict | None, duration: float) -> str:
    """ffmpeg filters (comma-joined, no labels) that polish a spoken voice track."""
    v = voice_settings(cfg)
    f: list[str] = []
    if v["highpass"] > 0:
        f.append(f"highpass=f={v['highpass']:.0f}:p=2")
    if v["denoise"] == "light":
        f.append("afftdn=nf=-24:tn=1")
    if v["gate"] > 0:
        # gentle expander: quiet breaths/room noise between words go down, never to silence
        f.append(f"agate=threshold={0.004 + 0.02 * v['gate']:.4f}:ratio={1.5 + 3 * v['gate']:.2f}:range={10 ** (-(4 + 14 * v['gate']) / 20):.3f}:attack=5:release=180")
    if v["bass"]:
        f.append(f"bass=g={v['bass']:.1f}:f=120:w=0.7")
    if v["mud"]:
        f.append(f"equalizer=f=300:t=q:w=1.1:g={v['mud']:.1f}")
    if v["presence"]:
        f.append(f"equalizer=f=3500:t=q:w=1.2:g={v['presence']:.1f}")
    if v["treble"]:
        f.append(f"treble=g={v['treble']:.1f}:f=9000:w=0.6")
    if v["deess"] > 0:
        f.append(f"deesser=i={0.15 + 0.6 * v['deess']:.2f}:m=0.5:f=0.5:s=o")
    if v["compress"] > 0:
        c = v["compress"]
        f.append(f"acompressor=threshold={-14 - 12 * c:.1f}dB:ratio={1.5 + 4.5 * c:.2f}:attack=6:release=140:makeup={1 + 3 * c:.2f}:knee=4")
    if abs(v["volume"] - 1.0) > 1e-3:
        f.append(f"volume={v['volume']:.3f}")
    if v["fade_in"] > 0:
        f.append(f"afade=t=in:d={min(v['fade_in'], duration / 2):.2f}")
    if v["fade_out"] > 0:
        d = min(v["fade_out"], duration / 2)
        f.append(f"afade=t=out:st={max(0.0, duration - d):.3f}:d={d:.2f}")
    return ",".join(f)


def overlay_input_args(item: dict, path: Path) -> list[str]:
    """ffmpeg input args for a B-roll clip or image overlay item."""
    dur = max(0.2, float(item["end"]) - float(item["start"]))
    if item.get("type") == "image":
        return ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(path)]
    return ["-t", f"{dur + 0.5:.3f}", "-i", str(path)]


BLENDS = {"normal": "Normal", "screen": "Screen (काला हटे — light leak, particles)", "black": "काला background हटाएँ",
          "white": "सफ़ेद background हटाएँ", "green": "Green screen हटाएँ", "blue": "Blue screen हटाएँ"}


def _key(item: dict) -> str:
    """Make part of an overlay transparent (green screen, black/white background, screen-like glow)."""
    b = item.get("blend") or "normal"
    sim = float(item.get("key_sim", .25) or .25)
    if b == "green":
        return f",format=rgba,colorkey=0x00FF00:{sim:.2f}:0.15"
    if b == "blue":
        return f",format=rgba,colorkey=0x0000FF:{sim:.2f}:0.15"
    if b == "black":
        return f",format=rgba,colorkey=0x000000:{min(sim, .2):.2f}:0.1"
    if b == "white":
        return f",format=rgba,colorkey=0xFFFFFF:{min(sim, .2):.2f}:0.1"
    if b == "screen":
        return ",format=rgba,lumakey=threshold=0:tolerance=0.08:softness=0.35"
    return ""


ALPHA_RANGE = "lut=y='if(lt(val\\,22)\\,0\\,clip((val-16)*255/219\\,0\\,255))'"


def edge_filter(shrink: float, feather: float, short_side: int) -> str:
    """Edge refinement of a gray alpha: shrink (erode) the matte by `shrink` px and soften it by
    `feather` px. Values are in pixels of a 720p picture and scale with the real size."""
    k = max(0.5, short_side / 720)
    f = []
    n = int(round(max(0.0, min(8.0, float(shrink or 0))) * k))
    f += ["erosion"] * n
    fe = max(0.0, min(8.0, float(feather or 0))) * k
    if fe >= 0.3:
        f.append(f"gblur=sigma={fe:.2f}")
    return ",".join(f)


def _cut_src(item: dict, input_index: int, alpha_index: int | None, idx: int, h: int) -> tuple[str, str, str]:
    """Source picture of an overlay: the clip itself, or — for a "सिर्फ़ इंसान" (cutout) clip — the
    clip with its cached person matte as alpha. → (pre-chain;, source label, key filter)."""
    if alpha_index is None:
        return "", f"[{input_index}:v]", _key(item)
    edge = edge_filter(item.get("edge_shrink", 0), item.get("edge_feather", 0), h)
    pre = (f"[{alpha_index}:v]extractplanes=y,{ALPHA_RANGE}{',' + edge if edge else ''}[oa{idx}];"
           f"[oa{idx}][{input_index}:v]scale2ref=flags=bicubic[oas{idx}][ovs{idx}];"
           f"[ovs{idx}]format=rgba[ovr{idx}];[ovr{idx}][oas{idx}]alphamerge[ocut{idx}];")
    return pre, f"[ocut{idx}]", ""  # the person matte replaces colour keying


def overlay_filter(item: dict, input_index: int, w: int, h: int, in_label: str, out_label: str, idx: int,
                   alpha_index: int | None = None) -> str:
    """Full-frame B-roll (fit: cover), a picture-in-picture box, or a free transform
    (fit: free → x, y, scale, opacity, rotate, optional keyframe `to` for a move/zoom).
    alpha_index: input with the clip's person matte → only the person is laid over the video."""
    s, e = float(item["start"]), float(item["end"])
    pip = item.get("fit") == "pip"
    if item.get("fit") == "free":
        return _free_overlay(item, input_index, w, h, in_label, out_label, idx, alpha_index)
    pre, src, key = _cut_src(item, input_index, alpha_index, idx, h)
    if pip:
        bw, bh = int(w * 0.42), int(h * 0.42 * (9 / 16) if w < h else h * 0.42)
        prep = (f"{pre}{src}scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh}{key},"
                f"setpts=PTS-STARTPTS+{s:.3f}/TB[ov{idx}]")
        pos = {"tl": "24:24", "tr": f"W-w-24:24", "bl": f"24:H-h-{int(h*0.28)}", "br": f"W-w-24:H-h-{int(h*0.28)}"}.get(item.get("pos", "tr"), "W-w-24:24")
    else:
        prep = (f"{pre}{src}scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}{key},"
                f"setpts=PTS-STARTPTS+{s:.3f}/TB[ov{idx}]")
        pos = "0:0"
    fade = ""
    if item.get("fade", True) and not pip:
        fade = f",fade=t=in:st={s:.3f}:d=0.25:alpha=1,fade=t=out:st={max(s, e - 0.25):.3f}:d=0.25:alpha=1"
        prep = prep.replace(f"[ov{idx}]", f",format=yuva420p{fade}[ov{idx}]")
    return (f"{prep};{in_label}[ov{idx}]overlay={pos}:enable='between(t\\,{s:.3f}\\,{e:.3f})'"
            f":eof_action=pass{out_label}")


def _lerp(a: float, b: float, s: float, e: float) -> str:
    d = max(0.05, e - s)
    return f"({a:.4f}+({b:.4f}-{a:.4f})*min(1\\,max(0\\,(t-{s:.3f})/{d:.3f})))"


def _free_overlay(item: dict, idx_in: int, w: int, h: int, in_label: str, out_label: str, idx: int,
                  alpha_index: int | None = None) -> str:
    s, e = float(item["start"]), float(item["end"])
    pre, src, key = _cut_src(item, idx_in, alpha_index, idx, h)
    x0, y0 = float(item.get("x", 0.5)), float(item.get("y", 0.5))          # centre, fraction of frame
    sc0 = float(item.get("scale", 0.4))                                       # width as fraction of frame width
    op = max(0.0, min(1.0, float(item.get("opacity", 1.0))))
    rot = float(item.get("rotate", 0))
    to = item.get("to") or {}
    x1, y1, sc1 = float(to.get("x", x0)), float(to.get("y", y0)), float(to.get("scale", sc0))
    ow = max(8, int(w * max(sc0, sc1)))
    prep = (f"{pre}{src}scale={ow}:-2:flags=bicubic,format=rgba{key},setpts=PTS-STARTPTS+{s:.3f}/TB")
    if rot:
        prep += f",rotate={rot}*PI/180:c=black@0:ow='hypot(iw,ih)':oh=ow"
    if op < 1:
        prep += f",colorchannelmixer=aa={op:.3f}"
    anim = item.get("anim") or "none"
    if anim != "none":
        prep += f",fade=t=in:st={s:.3f}:d=0.15:alpha=1,fade=t=out:st={max(s, e - 0.2):.3f}:d=0.2:alpha=1"
    prep += f"[ovf{idx}]"
    zexpr = None
    if abs(sc1 - sc0) > 0.001:
        zexpr = _lerp(sc0, sc1, s, e)
    if anim in ("pop", "bounce", "zoom"):
        # overshoot ease on the first 0.35 s: 0 → 1.15 → 1.0 (pop); bounce has a second, smaller kick
        u = f"min(1\\,max(0\\,(t-{s:.3f})/0.35))"
        if anim == "zoom":
            k = f"(1.6-0.6*{u})"
        elif anim == "bounce":
            k = f"(if(lt({u}\\,0.6)\\,{u}/0.6*1.18\\,1.18-0.18*({u}-0.6)/0.4)+0.04*sin(10*max(0\\,t-{s:.3f}))*exp(-4*max(0\\,t-{s:.3f})))"
        else:
            k = f"if(lt({u}\\,0.7)\\,0.2+{u}/0.7*0.95\\,1.15-0.15*({u}-0.7)/0.3)"
        base = zexpr or f"{max(sc0, sc1):.4f}"
        zexpr = f"({base})*({k})"
    if zexpr:
        zw = f"'max(8\\,trunc({w}*{zexpr}/2)*2)'"
        prep = prep.replace(f"[ovf{idx}]", f",scale=w={zw}:h=-2:eval=frame[ovf{idx}]")
    px = f"'{w}*{_lerp(x0, x1, s, e)}-w/2'" if (x1 != x0) else f"'{w * x0:.1f}-w/2'"
    py = f"'{h}*{_lerp(y0, y1, s, e)}-h/2'" if (y1 != y0) else f"'{h * y0:.1f}-h/2'"
    if anim == "slide_up":
        py = f"'{h * y0:.1f}-h/2+{h * 0.35:.0f}*pow(max(0\\,1-(t-{s:.3f})/0.35)\\,2)'"
    elif anim == "slide_left":
        px = f"'{w * x0:.1f}-w/2+{w * 0.6:.0f}*pow(max(0\\,1-(t-{s:.3f})/0.35)\\,2)'"
    elif anim == "drop":
        py = f"'{h * y0:.1f}-h/2-{h:.0f}*pow(max(0\\,1-(t-{s:.3f})/0.45)\\,2)'"
    elif anim == "shake":
        px = f"'{w * x0:.1f}-w/2+{w * 0.012:.1f}*sin(60*t)*exp(-3*max(0\\,t-{s:.3f}))'"
    elif anim == "float":
        py = f"'{h * y0:.1f}-h/2+{h * 0.01:.1f}*sin(4*t)'"
    return (f"{prep};{in_label}[ovf{idx}]overlay=x={px}:y={py}:eval=frame:enable='between(t\\,{s:.3f}\\,{e:.3f})'"
            f":eof_action=pass{out_label}")


def watermark_filter(input_index: int, w: int, h: int, in_label: str, out_label: str,
                     opacity: float = 0.75, size: float = 0.14, pos: str = "tr") -> str:
    lw = int(w * size)
    margin = int(min(w, h) * 0.035)
    place = {"tl": f"{margin}:{margin}", "tr": f"W-w-{margin}:{margin}",
             "bl": f"{margin}:H-h-{margin}", "br": f"W-w-{margin}:H-h-{margin}"}.get(pos, f"W-w-{margin}:{margin}")
    return (f"[{input_index}:v]scale={lw}:-1,format=rgba,colorchannelmixer=aa={opacity:.2f}[wm];"
            f"{in_label}[wm]overlay={place}{out_label}")


def title_events(titles: list[dict], width: int, height: int, font: str = "Poppins") -> tuple[str, list[str]]:
    """Text items → ASS (templates, in/out/loop animations): see engine/textfx.py."""
    from .textfx import title_events as _te
    return _te(titles, width, height, font)


STICKER_ANIMS = {"none": "कोई नहीं", "fade": "Fade", "pop": "Pop (bounce in)", "bounce": "Bounce", "zoom": "Zoom in",
                 "slide_up": "नीचे से", "slide_left": "दाएँ से", "drop": "ऊपर से गिरे", "shake": "Shake", "float": "Float"}


TEXT_ANIMS = {"none": "कोई नहीं", "fade": "Fade", "pop": "Pop", "slide_up": "Slide up", "slide_left": "Slide in (बाएँ से)",
              "zoom_out": "Zoom out", "typewriter": "Typewriter", "bounce": "Bounce", "glow": "Glow pulse", "shake": "Shake"}


def text_anim_tags(anim: str, an: int, w: int, h: int, dur_ms: int) -> str:
    """ASS override tags for in/out animation of a title."""
    cx = w / 2
    cy = {8: h * 0.12, 5: h / 2, 2: h * 0.88}.get(an, h / 2)
    o = min(400, dur_ms // 3)
    if anim == "none":
        return ""
    if anim == "fade":
        return f"\\fad(200,200)"
    if anim == "pop":
        return f"\\fad(80,150)\\fscx60\\fscy60\\t(0,160,\\fscx112\\fscy112)\\t(160,260,\\fscx100\\fscy100)"
    if anim == "slide_up":
        return f"\\fad(120,150)\\move({cx:.0f},{cy + h * 0.06:.0f},{cx:.0f},{cy:.0f},0,{o})"
    if anim == "slide_left":
        return f"\\fad(100,150)\\move({cx - w * 0.25:.0f},{cy:.0f},{cx:.0f},{cy:.0f},0,{o})"
    if anim == "zoom_out":
        return f"\\fad(80,150)\\fscx160\\fscy160\\t(0,{o},\\fscx100\\fscy100)"
    if anim == "bounce":
        return (f"\\fad(60,150)\\move({cx:.0f},{cy - h * 0.08:.0f},{cx:.0f},{cy:.0f},0,{o // 2})"
                f"\\fscy80\\t({o // 2},{o // 2 + 90},\\fscy115)\\t({o // 2 + 90},{o // 2 + 200},\\fscy100)")
    if anim == "glow":
        return f"\\fad(150,150)\\blur2\\t(0,{dur_ms // 2},\\blur10)\\t({dur_ms // 2},{dur_ms},\\blur2)"
    if anim == "shake":
        return (f"\\fad(80,120)\\t(0,60,\\frz2)\\t(60,120,\\frz-2)\\t(120,180,\\frz1.5)\\t(180,240,\\frz-1)\\t(240,300,\\frz0)")
    if anim == "typewriter":
        return ""
    return "\\fad(150,150)"


# ---------------------------------------------------------------------------
# Body effects (need the cached alpha video from engine/matting.py)
BODY_BG = {"none": "जैसा है", "blur": "Blur", "dim": "Dark", "flat": "Solid colour", "image": "Image (library)",
           "video": "Video (library)", "gradient": "Gradient"}
BODY_ANIMS = {"none": "कोई नहीं", "drop": "आसमान से गिरे (drop-in)", "pop": "Pop out", "slide": "Slide in", "blink": "Blink / strobe",
              "rise": "नीचे से उठे"}


def body_chain(body: dict, w: int, h: int, v_in: str, a_in: str, out_label: str, *, extra_inputs: dict,
               ass_behind: str | None = None, fonts_dir: str | None = None, fps: float = 30.0,
               duration: float = 60.0) -> list[str]:
    """Compose: background → glow → stroke → text-behind → subject (animated) → clones.
    v_in: cut video label; a_in: cut alpha (gray, same size). extra_inputs: {'bg_image': idx, 'bg_video': idx}."""
    ch: list[str] = []
    bg_mode = body.get("bg", "blur")
    fr = f"{fps:.3f}".rstrip("0").rstrip(".")
    # --- person transform (size / position / mirror) — applied to picture and mask together
    s_ = max(0.3, min(2.0, float(body.get("subj_scale", 1.0) or 1.0)))
    dx, dy = float(body.get("subj_x", 0) or 0), float(body.get("subj_y", 0) or 0)
    flip = bool(body.get("flip"))
    moved = abs(s_ - 1) > 1e-3 or abs(dx) > 1e-3 or abs(dy) > 1e-3 or flip

    def _xf(src: str, dst: str, gray: bool) -> str:
        sw, sh = max(2, int(w * s_ / 2) * 2), max(2, int(h * s_ / 2) * 2)
        f = f"{src}" + ("format=gray," if gray else "") + ("hflip," if flip else "") + f"scale={sw}:{sh}"
        if s_ <= 1:
            ox = int(max(0, min(w - sw, (w - sw) / 2 + dx * w)))
            oy = int(max(0, min(h - sh, (h - sh) / 2 + dy * h)))
            f += f",pad={w}:{h}:{ox}:{oy}:black"
        else:
            cx = int(max(0, min(sw - w, (sw - w) / 2 - dx * w)))
            cy = int(max(0, min(sh - h, (sh - h) / 2 - dy * h)))
            f += f",crop={w}:{h}:{cx}:{cy}"
        return f + dst
    # --- background
    if bg_mode == "blur":
        ch.append(f"{v_in}split[bsrc][bsub];[bsrc]gblur=sigma={float(body.get('bg_blur', 18)):.1f},eq=brightness=-0.04[bg0]")
        v_sub = "[bsub]"
    elif bg_mode == "dim":
        ch.append(f"{v_in}split[bsrc][bsub];[bsrc]eq=brightness=-0.35:saturation=0.6[bg0]")
        v_sub = "[bsub]"
    elif bg_mode == "flat":
        ch.append(f"color=c={_c(body.get('bg_color', '#111111'))}:s={w}x{h}:r={fr},format=yuv420p[bg0]")
        ch.append(f"{v_in}copy[bsub]")
        v_sub = "[bsub]"
    elif bg_mode == "gradient":
        c1, c2 = _c(body.get("bg_color", "#1b1f3a")), _c(body.get("bg_color2", "#f2b33d"))
        ch.append(f"gradients=s={w}x{h}:c0={c1}:c1={c2}:x0=0:y0=0:x1={w}:y1={h}:speed=0.02:r={fr},format=yuv420p[bg0]")
        ch.append(f"{v_in}copy[bsub]")
        v_sub = "[bsub]"
    elif bg_mode in ("image", "video") and extra_inputs.get("bg_" + bg_mode) is not None:
        idx = extra_inputs["bg_" + bg_mode]
        sp = max(0.25, min(4.0, float(body.get("bg_speed", 1.0) or 1.0)))
        pre = f"[{idx}:v]" + (f"setpts=PTS/{sp:.3f}," if bg_mode == "video" and abs(sp - 1) > 1e-3 else "") + f"fps={fr},"
        if body.get("bg_fit") == "contain":
            ch.append(f"{pre}split[bgA][bgB];[bgA]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},gblur=sigma=30[bgAb];"
                      f"[bgB]scale={w}:{h}:force_original_aspect_ratio=decrease[bgBf];[bgAb][bgBf]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[bg0]")
        else:
            ch.append(f"{pre}scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,format=yuv420p[bg0]")
        ch.append(f"{v_in}copy[bsub]")
        v_sub = "[bsub]"
    else:
        ch.append(f"{v_in}split[bg0][bsub]")
        v_sub = "[bsub]"
    # --- background adjustments: slow zoom, extra blur, darken, colour tint
    adj = []
    z = max(0.0, min(0.5, float(body.get("bg_zoom", 0) or 0)))
    if z > 0:
        n = max(1, int(duration * fps))
        adj.append(f"scale={w * 2}:{h * 2},zoompan=z='1+{z:.3f}*min(on/{n}\\,1)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fr}")
    bb = float(body.get("bg_blur2", 0) or 0)
    if bb > 0 and bg_mode not in ("blur",):
        adj.append(f"gblur=sigma={bb:.1f}")
    dim = max(0.0, min(0.9, float(body.get("bg_dim", 0) or 0)))
    if dim > 0:
        adj.append(f"eq=brightness={-0.5 * dim:.3f}:saturation={1 - 0.4 * dim:.3f}")
    if adj:
        ch.append(f"[bg0]{','.join(adj)},format=yuv420p[bg0a]")
        bg_label = "[bg0a]"
    else:
        bg_label = "[bg0]"
    ta = max(0.0, min(0.9, float(body.get("bg_tint_amt", 0) or 0)))
    if ta > 0:
        ch.append(f"color=c={_c(body.get('bg_tint', '#F2B33D'))}@{ta:.2f}:s={w}x{h}:r={fr},format=rgba[tintc];"
                  f"{bg_label}[tintc]overlay=0:0:shortest=1:format=auto[bg0t]")
        bg_label = "[bg0t]"
    if moved:
        ch.append(_xf(v_sub, "[bsubT]", False))
        v_sub = "[bsubT]"
        ch.append(_xf(a_in, "[aT]", True))
        a_in = "[aT]"
    # alpha copies
    shadow = bool(body.get("shadow"))
    n_alpha = 1 + (1 if body.get("glow") else 0) + (1 if body.get("stroke") else 0) + (1 if shadow else 0)
    labels = "".join(f"[al{i}]" for i in range(n_alpha))
    # matte videos are limited-range (black = 16): stretch to 0…255 so "empty" is really transparent
    rng = ALPHA_RANGE
    # "किनारा": shrink / soften the matte edge (halo of the old background, hard pixel edges)
    edge = edge_filter(body.get("edge_shrink", 0), body.get("edge_feather", 0), min(w, h))
    if edge:
        rng += "," + edge
    ch.append(f"{a_in}format=gray,{rng},split={n_alpha}{labels}" if n_alpha > 1 else f"{a_in}format=gray,{rng}[al0]")
    ai = 1
    base = bg_label
    # --- text behind person goes on the background
    if ass_behind:
        sub = f"ass=filename='{ass_behind}':shaping=complex" + (f":fontsdir='{fonts_dir}'" if fonts_dir else "")
        ch.append(f"{base}{sub}[bgt]")
        base = "[bgt]"
    anim = body.get("anim", "none") or "none"
    T = float(body.get("anim_seconds", 0.9))
    # an animated person moves as one layer: shadow + glow + outline + body together
    layered = anim != "none"
    of = "rgb" if layered else "auto"
    if layered:
        ch.append(f"color=c=black@0.0:s={w}x{h}:r={fr},format=rgba[lay0]")
        cur = "[lay0]"
    else:
        cur = base
    # --- drop shadow under the person
    if shadow:
        so = max(0.0, min(1.0, float(body.get("shadow_opacity", 0.55))))
        sb = max(1, int(body.get("shadow_blur", 18)))
        off = int(float(body.get("shadow_offset", 0.012)) * w)
        ch.append(f"[al{ai}]boxblur={sb}:1,lutyuv=y='val*{so:.2f}'[shda];color=c=black:s={w}x{h}:r={fr},format=rgba[shdc];"
                  f"[shdc][shda]alphamerge[shd];{cur}[shd]overlay={off}:{off}:format={of}[bgsh]")
        cur = "[bgsh]"
        ai += 1
    # --- glow (blurred, coloured alpha)
    if body.get("glow"):
        gc = _c(body.get("glow_color", "#F2B33D")); gs = float(body.get("glow_size", 24))
        ch.append(f"[al{ai}]boxblur={gs:.0f}:1,lutyuv=y='min(255\\,val*{float(body.get('glow_strength', 1.6)):.2f})'[glowa]")
        ch.append(f"color=c={gc}:s={w}x{h}:r={fr},format=rgba[glowc];[glowc][glowa]alphamerge[glow]")
        ch.append(f"{cur}[glow]overlay=0:0:format={of}[bgg]")
        cur = "[bgg]"
        ai += 1
    # --- stroke (ring = dilate(alpha) − alpha)
    if body.get("stroke"):
        sc = _c(body.get("stroke_color", "#FFFFFF")); sw = max(1, int(body.get("stroke_width", 8)))
        ch.append(f"[al{ai}]split[sa1][sa2];[sa1]boxblur={sw}:1,lutyuv=y='if(gt(val\\,24)\\,255\\,0)'[dil];"
                  f"[dil][sa2]blend=all_mode=subtract[ring]")
        ch.append(f"color=c={sc}:s={w}x{h}:r={fr},format=rgba[strc];[strc][ring]alphamerge[stroke]")
        ch.append(f"{cur}[stroke]overlay=0:0:format={of}[bgs]")
        cur = "[bgs]"
        ai += 1
    # --- subject
    ch.append(f"{v_sub}format=rgba[vsub];[vsub][al0]alphamerge[subj0]")
    subj = "[subj0]"
    if body.get("afterimage"):
        ch.append(f"{subj}split[sa][sb];[sa]lagfun=decay={float(body.get('after_decay', 0.9)):.2f},colorchannelmixer=aa=0.6[trail];"
                  f"{cur}[trail]overlay=0:0:format={of}[bga]")
        cur = "[bga]"
        subj = "[sb]"
    clones = int(body.get("clones", 0) or 0)
    if clones:
        ch.append(f"{subj}split={clones + 1}" + "".join(f"[cl{i}]" for i in range(clones + 1)))
        for i in range(clones):
            off = int(w * 0.22 * (i + 1)) * (-1 if i % 2 else 1)
            ch.append(f"[cl{i + 1}]colorchannelmixer=aa=0.45[clo{i}];{cur}[clo{i}]overlay={off}:0:format={of}[bgc{i}]")
            cur = f"[bgc{i}]"
        subj = "[cl0]"
    if not layered:
        ch.append(f"{cur}{subj}overlay=0:0:format=auto{out_label}")
        return ch
    ch.append(f"{cur}{subj}overlay=0:0:format=rgb,format=rgba[layer]")
    lay = "[layer]"
    enable = ""
    x, y = "0", "0"
    if anim == "drop":
        y = f"'if(lt(t\\,{T})\\,-{h}*(1-pow(t/{T}\\,2))\\,0)'"
    elif anim == "rise":
        y = f"'if(lt(t\\,{T})\\,{h}*(1-pow(t/{T}\\,2))\\,0)'"
    elif anim == "slide":
        x = f"'if(lt(t\\,{T})\\,-{w}*(1-pow(t/{T}\\,2))\\,0)'"
    elif anim == "blink":
        P = float(body.get("blink_period", 0.4))
        enable = f":enable='lt(mod(t\\,{P})\\,{P * 0.55:.3f})'"
    elif anim == "pop":
        ch.append(f"{lay}scale=w='trunc(iw*if(lt(t\\,{T})\\,0.6+0.5*min(1\\,t/{T})\\,1.0)/2)*2':h=-2:eval=frame[layp]")
        lay = "[layp]"
        x, y = "'(W-w)/2'", "'(H-h)/2'"
    ch.append(f"{base}{lay}overlay=x={x}:y={y}:format=auto:eval=frame{enable}{out_label}")
    return ch


def _c(hex_color: str) -> str:
    return "0x" + str(hex_color or "#000000").lstrip("#")[:6]


# ---------------------------------------------------------------------------
# Main video transform: crop / rotate / mirror (before framing) and
# position & size inside the frame (after framing)

def transform_pre(t: dict | None, src_w: int, src_h: int) -> tuple[str, int, int]:
    t = t or {}
    f: list[str] = []
    w, h = src_w, src_h
    c = t.get("crop") or None
    if c and (float(c.get("w", 1)) < .999 or float(c.get("h", 1)) < .999):
        cw = max(16, int(w * float(c.get("w", 1)) / 2) * 2)
        ch = max(16, int(h * float(c.get("h", 1)) / 2) * 2)
        cx = int(max(0, min(w - cw, w * float(c.get("x", 0)))))
        cy = int(max(0, min(h - ch, h * float(c.get("y", 0)))))
        f.append(f"crop={cw}:{ch}:{cx}:{cy}")
        w, h = cw, ch
    rot = int(t.get("rotate", 0) or 0) % 360
    if rot == 90:
        f.append("transpose=1"); w, h = h, w
    elif rot == 180:
        f.append("hflip,vflip")
    elif rot == 270:
        f.append("transpose=2"); w, h = h, w
    if t.get("flip_h"):
        f.append("hflip")
    if t.get("flip_v"):
        f.append("vflip")
    ang = float(t.get("angle", 0) or 0)
    if abs(ang) > .05:
        a = math.radians(ang)
        # rotate and zoom just enough that no empty corners show
        k = abs(math.cos(a)) + abs(math.sin(a)) * max(w / h, h / w)
        f.append(f"rotate={a:.5f}:ow=iw:oh=ih:c=black,scale=iw*{k:.4f}:ih*{k:.4f},crop={w}:{h}")
    return ",".join(f), w, h


def transform_post(t: dict | None, w: int, h: int) -> str:
    t = t or {}
    s = float(t.get("scale", 1) or 1)
    dx, dy = float(t.get("x", 0) or 0), float(t.get("y", 0) or 0)
    if abs(s - 1) < 1e-3 and abs(dx) < 1e-3 and abs(dy) < 1e-3:
        return ""
    sw, sh = max(16, int(w * s / 2) * 2), max(16, int(h * s / 2) * 2)
    bg = t.get("bg", "blur")
    if bg == "blur":
        back = f"[tpa]gblur=sigma=30,eq=brightness=-0.08[tpbg]"
    else:
        col = "black" if bg in ("black", "", None) else "0x" + str(t.get("bg_color", "#000000")).lstrip("#")[:6]
        back = f"[tpa]drawbox=x=0:y=0:w=iw:h=ih:color={col}:t=fill[tpbg]"
    x = f"(W-w)/2+{dx * w:.1f}"
    y = f"(H-h)/2+{dy * h:.1f}"
    return f"split[tpa][tpb];{back};[tpb]scale={sw}:{sh}[tpfg];[tpbg][tpfg]overlay=x='{x}':y='{y}'"
