"""Render-time effects: zoom, looks, transitions, music ducking, overlays.

Every function returns ffmpeg filter fragments; render.py composes them.
Times are on the OUTPUT timeline (after cuts), in seconds.
"""

from __future__ import annotations

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
}

ZOOM_LEVELS = [1.0, 1.14, 1.0, 1.08, 1.2, 1.0, 1.12]


def zoom_plan(boundaries: list[float], duration: float, strength: float = 1.0,
              min_gap: float = 1.6, max_points: int = 80) -> list[tuple[float, float]]:
    """Zoom targets at segment starts: [(time, zoom)]. Alternates levels so
    jump cuts read as deliberate punch-ins."""
    pts: list[tuple[float, float]] = []
    last = -10.0
    i = 0
    for b in sorted(set([0.0, *boundaries])):
        if b - last < min_gap or b >= duration:
            continue
        z = 1.0 + (ZOOM_LEVELS[i % len(ZOOM_LEVELS)] - 1.0) * max(0.0, min(2.0, strength))
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


def zoom_filter(points: list[tuple[float, float]], w: int, h: int, fx: float = 0.5, fy: float = 0.4) -> str:
    """Scale per frame by z(t), then crop back to w×h around the focus point."""
    z = zoom_expr(points)
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
                duration: float, fade: float = 1.5) -> tuple[str, str]:
    """Mix background music under the voice. Returns (filter_text, output_label)."""
    m = (f"[{music_index}:a]aformat=sample_rates=48000:channel_layouts=mono,"
         f"atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,volume={volume:.3f},"
         f"afade=t=in:d={fade},afade=t=out:st={max(0.0, duration - fade):.3f}:d={fade}[mus]")
    if duck:
        chain = (f"{m};{voice_label}asplit[vmain][vside];"
                 f"[mus][vside]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=450:makeup=1[mduck];"
                 f"[vmain][mduck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[amixed]")
    else:
        chain = f"{m};{voice_label}[mus]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[amixed]"
    return chain, "[amixed]"


def overlay_input_args(item: dict, path: Path) -> list[str]:
    """ffmpeg input args for a B-roll clip or image overlay item."""
    dur = max(0.2, float(item["end"]) - float(item["start"]))
    if item.get("type") == "image":
        return ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(path)]
    return ["-t", f"{dur + 0.5:.3f}", "-i", str(path)]


def overlay_filter(item: dict, input_index: int, w: int, h: int, in_label: str, out_label: str, idx: int) -> str:
    """Full-frame B-roll (fit: cover) or a picture-in-picture box, shown between start and end."""
    s, e = float(item["start"]), float(item["end"])
    pip = item.get("fit") == "pip"
    if pip:
        bw, bh = int(w * 0.42), int(h * 0.42 * (9 / 16) if w < h else h * 0.42)
        prep = (f"[{input_index}:v]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
                f"setpts=PTS-STARTPTS+{s:.3f}/TB[ov{idx}]")
        pos = {"tl": "24:24", "tr": f"W-w-24:24", "bl": f"24:H-h-{int(h*0.28)}", "br": f"W-w-24:H-h-{int(h*0.28)}"}.get(item.get("pos", "tr"), "W-w-24:24")
    else:
        prep = (f"[{input_index}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                f"setpts=PTS-STARTPTS+{s:.3f}/TB[ov{idx}]")
        pos = "0:0"
    fade = ""
    if item.get("fade", True) and not pip:
        fade = f",fade=t=in:st={s:.3f}:d=0.25:alpha=1,fade=t=out:st={max(s, e - 0.25):.3f}:d=0.25:alpha=1"
        prep = prep.replace(f"[ov{idx}]", f",format=yuva420p{fade}[ov{idx}]")
    return (f"{prep};{in_label}[ov{idx}]overlay={pos}:enable='between(t\\,{s:.3f}\\,{e:.3f})'"
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
    """ASS style + events for title/text overlays: [{start,end,text,pos: top|center|bottom, size, color, bg}]."""
    base = min(width, height)
    style = (f"Style: Title,{font},{round(0.075 * base)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
             f"-1,0,0,0,100,100,0,0,1,{round(0.006 * base, 1)},{round(0.003 * base, 1)},8,"
             f"{round(0.06 * width)},{round(0.06 * width)},{round(0.1 * height)},1")
    out = []
    from .captions import _esc, _t, ass_color
    for t in titles:
        txt = _esc(str(t.get("text", ""))).replace("|", "\\N")
        if not txt.strip():
            continue
        an = {"top": 8, "center": 5, "bottom": 2}.get(t.get("pos", "top"), 8)
        size = round(float(t.get("size", 0.075)) * base)
        tags = f"\\an{an}\\fs{size}\\fad(150,150)"
        if t.get("color"):
            tags += f"\\c{ass_color(t['color'])}"
        if t.get("bg"):
            tags += f"\\bord{round(0.02 * base, 1)}\\3c{ass_color(t['bg'])}"
        out.append(f"Dialogue: 2,{_t(float(t['start']))},{_t(float(t['end']))},Title,,0,0,0,,{{{tags}}}{txt}")
    return style, out
