"""Pro compositing for overlay clips (effects.broll items): speed + ramps, trim, per-clip colour /
grade / effect stack, masks, crop, blend modes, opacity and keyframed transform — plus the clip's
own sound (pitch-preserved atempo) when it is given a volume.

An overlay item only goes through here when it uses one of the new fields (see is_pro); every
older project renders exactly as before through effects.overlay_filter.

Item fields (all optional; times in seconds):
  trim_in, trim_out        part of the SOURCE clip to use
  speed                    0.25…4 constant speed
  speed_ramp               keyframes {t: source seconds after trim_in, v: speed} (curve speed)
  speed_warp               "off" | "fast" | "balanced" | "best" — smooth slow motion (< 0.75×)
  volume                   0 (muted, default) … 2 — the clip's own audio, mixed under the main sound
  color                    engine/colorpro.py spec (wheels / curves / HSL / match)
  grade, grade_preset      catalog grade sliders / preset id
  stack                    catalog effect stack [{id, params, kf}]
  mask                     engine/masks.py spec;  crop {x,y,w,h,kf} (fractions of the clip)
  blend_mode               normal | screen | multiply | overlay | softlight | hardlight | add | subtract |
                           lighten | darken | difference | exclusion | colordodge | colorburn
  opacity                  0…1
  kf                       {x, y, scale, rotation, opacity} keyframes, t relative to the clip start.
                           x/y = centre (fraction of frame), scale = multiplier of the base size,
                           rotation = degrees, opacity 0…1.
  cutout + alpha_path      "सिर्फ़ इंसान": the clip's cached person matte (worker-resolved) becomes its
                           alpha — trimmed / sped / framed exactly like the picture, then edge_shrink /
                           edge_feather, multiplied with the mask / crop.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from . import catalog, colorpro, masks
from . import keyframes as K
from .ffmpeg import escape_filter_path

BLEND_MODES = {
    "normal": "Normal", "screen": "Screen", "multiply": "Multiply", "overlay": "Overlay", "softlight": "Soft light",
    "hardlight": "Hard light", "add": "Add (linear dodge)", "subtract": "Subtract", "lighten": "Lighten",
    "darken": "Darken", "difference": "Difference", "exclusion": "Exclusion", "colordodge": "Color dodge",
    "colorburn": "Color burn",
}
# ffmpeg's blend uses the FIRST input as the top layer; its "overlay"/"hardlight" condition on the
# other layer than Photoshop's, so the names are swapped here
_FF_MODE = {"overlay": "hardlight", "hardlight": "overlay", "add": "addition", "colordodge": "dodge", "colorburn": "burn"}
SPEED_WARP = {"off": "बंद · Off", "fast": "Fast (frame blend)", "balanced": "Balanced (optical flow, ½ res)",
              "best": "Best (optical flow, full res — slow)"}
KF_PARAMS = {"x": (-1.0, 2.0), "y": (-1.0, 2.0), "scale": (0.01, 10.0), "rotation": (-3600.0, 3600.0), "opacity": (0.0, 1.0)}
PRO_KEYS = ("trim_in", "trim_out", "speed", "speed_ramp", "speed_warp", "volume", "color", "grade", "grade_preset",
            "stack", "mask", "crop", "blend_mode", "kf", "lut", "lut_path", "tr")


def is_pro(item: dict) -> bool:
    for k in PRO_KEYS:
        v = item.get(k)
        if v in (None, "", [], {}, False):
            continue
        if k == "speed" and abs(float(v or 1) - 1) < 1e-3:
            continue
        if k in ("trim_in", "volume") and float(v or 0) <= 0:
            continue
        if k == "blend_mode" and v == "normal":
            continue
        if k == "speed_warp" and v == "off":
            continue
        return True
    return False


# ------------------------------------------------------------------ speed
def ramp_pieces(item: dict, need_out: float, src_avail: float | None, step: float = 0.1, max_pieces: int = 100):
    """Source pieces [(a, len, speed)] covering enough source for `need_out` seconds of output."""
    pts = K.normalize(item.get("speed_ramp"), lo=0.25, hi=4.0)
    const = max(0.25, min(4.0, float(item.get("speed", 1) or 1)))
    if not K.animated(pts):
        v = pts[0]["v"] if pts else const
        span = need_out * v
        if src_avail is not None:
            span = min(span, src_avail)
        return [(0.0, max(0.04, span), v)]
    # long ramps: coarser steps so the expression stays small
    est = need_out * max(p["v"] for p in pts)
    step = max(step, est / max_pieces)
    pieces, a, out = [], 0.0, 0.0
    while out < need_out - 1e-6 and len(pieces) < max_pieces * 2:
        v = max(0.25, min(4.0, K.sample(pts, a + step / 2)))
        ln = step
        if out + ln / v > need_out:
            ln = (need_out - out) * v
        if src_avail is not None and a + ln > src_avail:
            ln = max(0.0, src_avail - a)
        if ln <= 1e-4:
            break
        pieces.append((a, ln, v))
        a += ln
        out += ln / v
    return pieces or [(0.0, 0.04, 1.0)]


def out_duration(item: dict, src_avail: float) -> float:
    """How long the clip plays on the timeline when all of src_avail seconds are used."""
    ps = ramp_pieces(item, 1e6, src_avail)
    return sum(ln / v for _, ln, v in ps)


def setpts_for(pieces) -> str:
    if len(pieces) == 1:
        v = pieces[0][2]
        return "setpts=PTS-STARTPTS" + (f",setpts=PTS/{v:.5f}" if abs(v - 1) > 1e-4 else "")
    terms = "+".join(f"min(max(T-{a:.4f},0),{ln:.4f})/{v:.5f}" for a, ln, v in pieces)
    return "setpts=PTS-STARTPTS,setpts=" + K.q(f"({terms})/TB")


def atempo(rate: float) -> str:
    parts, r = [], rate
    while r > 2.0:
        parts.append("atempo=2.0"); r /= 2.0
    while r < 0.5:
        parts.append("atempo=0.5"); r /= 0.5
    if abs(r - 1) > 1e-4 or not parts:
        parts.append(f"atempo={r:.5f}")
    return ",".join(parts)


def audio_pieces(pieces, max_n: int = 24):
    """Merge video ramp pieces into ≤ max_n audio pieces (atempo per piece keeps the pitch)."""
    if len(pieces) <= max_n:
        return pieces
    k = math.ceil(len(pieces) / max_n)
    out = []
    for i in range(0, len(pieces), k):
        grp = pieces[i:i + k]
        a, ln = grp[0][0], sum(g[1] for g in grp)
        o = sum(g[1] / g[2] for g in grp)
        out.append((a, ln, ln / o))
    return out


def warp_filter(mode: str | None, min_speed: float, fps: float) -> str:
    """Speed Warp: synthesize in-between frames for slow motion (< 0.75×)."""
    if not mode or mode == "off" or min_speed >= 0.75:
        return ""
    if mode == "fast":
        return f"minterpolate=fps={fps:.3f}:mi_mode=blend,"
    if mode == "best":
        return f"minterpolate=fps={fps:.3f}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1:scd=none,"
    return (f"scale=trunc(iw/4)*2:trunc(ih/4)*2,minterpolate=fps={fps:.3f}:mi_mode=mci:mc_mode=obmc:me_mode=bidir:scd=none,"
            f"scale=trunc(iw)*2:trunc(ih)*2,")


# ------------------------------------------------------------------ geometry
def _ev(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def base_box(item: dict, W: int, H: int, src_w: int, src_h: int) -> tuple[int, int, float, float, str]:
    """→ (box_w, box_h, centre_x, centre_y, fit filter)."""
    fit = item.get("fit") or "cover"
    ar = src_w / max(1, src_h)
    if fit == "pip":
        bw, bh = _ev(W * 0.42), _ev(H * 0.42 * (9 / 16) if W < H else H * 0.42)
        pos = item.get("pos", "tr")
        cx = (24 + bw / 2) / W if pos in ("tl", "bl") else (W - 24 - bw / 2) / W
        cy = (24 + bh / 2) / H if pos in ("tl", "tr") else (H - H * 0.28 - bh / 2) / H
        return bw, bh, cx, cy, f"scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh}"
    if fit == "free":
        bw = _ev(W * max(0.02, float(item.get("scale", 0.4) or 0.4)))
        bh = _ev(bw / ar)
        return bw, bh, float(item.get("x", 0.5)), float(item.get("y", 0.5)), f"scale={bw}:{bh}:flags=bicubic"
    if fit == "contain":
        k = min(W / src_w, H / src_h)
        bw, bh = _ev(src_w * k), _ev(src_h * k)
        return bw, bh, 0.5, 0.5, f"scale={bw}:{bh}:flags=bicubic"
    return W, H, 0.5, 0.5, f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"


def _kf(item: dict, dur: float, x0: float, y0: float) -> dict[str, list[dict]]:
    out = {k: K.normalize(v, lo=KF_PARAMS[k][0], hi=KF_PARAMS[k][1]) for k, v in (item.get("kf") or {}).items() if k in KF_PARAMS}
    out = {k: v for k, v in out.items() if v}
    to = item.get("to") or {}
    if to and item.get("fit") == "free":  # legacy one-step move → keyframes
        if "x" not in out and "x" in to:
            out["x"] = [{"t": 0.0, "v": x0, "ease": "linear"}, {"t": dur, "v": float(to["x"]), "ease": "linear"}]
        if "y" not in out and "y" in to:
            out["y"] = [{"t": 0.0, "v": y0, "ease": "linear"}, {"t": dur, "v": float(to["y"]), "ease": "linear"}]
        if "scale" not in out and "scale" in to:
            s0 = float(item.get("scale", 0.4) or 0.4)
            out["scale"] = [{"t": 0.0, "v": 1.0, "ease": "linear"}, {"t": dur, "v": float(to["scale"]) / s0, "ease": "linear"}]
    return out


# ------------------------------------------------------------------ transitions between overlay clips
TRANSITIONS = {"crossfade": "Crossfade", "dip": "Dip (काला)", "slide_left": "Slide ←", "slide_right": "Slide →",
               "slide_up": "Slide ↑", "slide_down": "Slide ↓", "zoom": "Zoom in", "wipe": "Wipe →"}


def _tr_prev(items: list[dict], it: dict) -> dict | None:
    """The clip this one takes over from: the latest-ending clip on the same track that starts earlier."""
    best = None
    for o in items:
        if o is it or (o.get("track") or 0) != (it.get("track") or 0):
            continue
        if float(o.get("start", 0)) < float(it.get("start", 0)):
            if best is None or float(o.get("end", 0)) > float(best.get("end", 0)):
                best = o
    return best


def transition_window(items: list[dict], it: dict) -> tuple[dict | None, float, float]:
    """(previous clip, overlap seconds, transition seconds actually possible)."""
    tr = it.get("tr") or {}
    if not isinstance(tr, dict) or not tr.get("kind") or tr.get("kind") == "none":
        return None, 0.0, 0.0
    prev = _tr_prev(items, it)
    if prev is None:
        return None, 0.0, 0.0
    overlap = max(0.0, float(prev.get("end", 0)) - float(it.get("start", 0)))
    want = max(0.1, min(5.0, float(tr.get("dur", 0.5) or 0.5)))
    return prev, overlap, min(want, overlap)


def _kf_point(lst: list[dict], t: float, v: float) -> None:
    lst.append({"t": round(t, 4), "v": round(v, 4), "ease": "linear"})


def apply_transitions(items: list[dict]) -> tuple[list[dict], list[str]]:
    """Materialise `tr` on a clip as keyframes on COPIES of it and of the clip before it on the same
    track. Returns (new items, notes). A transition longer than the overlap is shortened; no overlap → note."""
    out = [dict(x) for x in items]
    notes: list[str] = []
    for it in out:
        prev, overlap, wd = transition_window(out, it)
        if prev is None:
            if it.get("tr", {}).get("kind") not in (None, "", "none") if isinstance(it.get("tr"), dict) else False:
                notes.append("transition: पिछली clip नहीं मिली (उसी track पर, छूती या overlap करती हुई)")
            continue
        if wd < 0.08:
            notes.append("transition: clips overlap नहीं करतीं — handles कम हैं, transition छोड़ी")
            continue
        kind = it["tr"]["kind"]
        s_it, s_pv = float(it["start"]), float(prev["start"])
        op_it = float(it.get("opacity", 1.0) if it.get("opacity") is not None else 1.0)
        op_pv = float(prev.get("opacity", 1.0) if prev.get("opacity") is not None else 1.0)
        kf_it = {k: [dict(p) for p in v] for k, v in (it.get("kf") or {}).items()}
        kf_pv = {k: [dict(p) for p in v] for k, v in (prev.get("kf") or {}).items()}
        # the previous clip always fades out over the window (dip: in the first half)
        pv_a, pv_b = s_it - s_pv, s_it - s_pv + (wd / 2 if kind == "dip" else wd)
        kf_pv.setdefault("opacity", [])
        if not any(abs(float(p.get("t", 0))) < 1e-6 for p in kf_pv["opacity"]):
            _kf_point(kf_pv["opacity"], 0.0, op_pv)
        _kf_point(kf_pv["opacity"], pv_a, op_pv)
        _kf_point(kf_pv["opacity"], pv_b, 0.0)
        kf_pv["opacity"].sort(key=lambda p: p["t"])
        # the new clip comes in
        it_a, it_b = (wd / 2, wd) if kind == "dip" else (0.0, wd)
        kf_it.setdefault("opacity", [])
        if kind in ("crossfade", "dip", "zoom"):
            _kf_point(kf_it["opacity"], it_a, 0.0)
            _kf_point(kf_it["opacity"], it_b, op_it)
        if kind == "zoom":
            sc = float(it.get("scale", 1.0) or 1.0)
            kf_it.setdefault("scale", [])
            _kf_point(kf_it["scale"], 0.0, sc * 0.6)
            _kf_point(kf_it["scale"], wd, sc)
        if kind.startswith("slide_"):
            x0, y0 = float(it.get("x", 0.5) or 0.5), float(it.get("y", 0.5) or 0.5)
            d = {"slide_left": ("x", x0 + 1.0), "slide_right": ("x", x0 - 1.0), "slide_up": ("y", y0 + 1.0), "slide_down": ("y", y0 - 1.0)}[kind]
            kf_it.setdefault(d[0], [])
            _kf_point(kf_it[d[0]], 0.0, d[1])
            _kf_point(kf_it[d[0]], wd, x0 if d[0] == "x" else y0)
            if it.get("fit") != "free":
                it["fit"] = "free"
                it.setdefault("x", x0)
                it.setdefault("y", y0)
                it.setdefault("scale", it.get("scale") or 1.0)
        if kind == "wipe":
            if it.get("mask"):
                notes.append("wipe: clip पर पहले से mask है — crossfade लगाया")
                _kf_point(kf_it["opacity"], 0.0, 0.0)
                _kf_point(kf_it["opacity"], wd, op_it)
            else:
                it["mask"] = {"shape": "rect", "x": 0.5, "y": 0.5, "w": 1.0, "h": 1.0, "rotation": 0, "roundness": 0, "feather": 0.02, "enabled": True,
                              "kf": {"x": [{"t": 0.0, "v": -0.5, "ease": "linear"}, {"t": round(wd, 4), "v": 0.5, "ease": "linear"}]}}
        for k in list(kf_it):
            kf_it[k].sort(key=lambda p: p["t"])
        it["kf"] = {k: v for k, v in kf_it.items() if v}
        prev["kf"] = {k: v for k, v in kf_pv.items() if v}
    return out, notes


# ------------------------------------------------------------------ main builder
def build(item: dict, idx: int, W: int, H: int, fps: float, cur: str, work: Path) -> dict:
    """Filter graph for one pro overlay clip.
    → {"inputs": [[args…] per input], "chains": [...], "out": label, "audio": (chains, label) | None}
    Input indexes inside the returned chains are placeholders {IN0}, {IN1}… — render.py fills them."""
    from .effects import ALPHA_RANGE, _key, edge_filter
    from .ffmpeg import probe
    s, e = float(item["start"]), float(item["end"])
    dur = max(1.0 / fps, e - s)
    path = Path(item["path"])
    is_img = item.get("type") == "image"
    try:
        info = probe(path)
    except Exception:  # noqa: BLE001
        info = {"width": W, "height": H, "has_audio": False, "duration": 0}
    src_w, src_h = int(info.get("width") or W), int(info.get("height") or H)
    trim_in = max(0.0, float(item.get("trim_in", 0) or 0))
    src_total = float(info.get("duration") or 0) or None
    avail = None
    if not is_img:
        if item.get("trim_out") not in (None, ""):
            avail = max(0.05, float(item["trim_out"]) - trim_in)
        elif src_total:
            avail = max(0.05, src_total - trim_in)
    pieces = [(0.0, dur, 1.0)] if is_img else ramp_pieces(item, dur, avail)
    span = sum(p[1] for p in pieces)
    min_speed = min(p[2] for p in pieces)
    inputs: list[list[str]] = []
    if is_img:
        inputs.append(["-loop", "1", "-framerate", f"{fps:.3f}", "-t", f"{dur + 0.2:.3f}", "-i", str(path)])
    else:
        # fast seek to ~1 s before trim_in, then a frame-exact trim in the graph
        seek = max(0.0, trim_in - 1.0)
        from .effects import alpha_decoder
        inputs.append([*alpha_decoder(path), "-ss", f"{seek:.3f}", "-t", f"{trim_in - seek + span + 0.3:.3f}", "-i", str(path)])
        pre_v = f"trim=start={trim_in - seek:.4f},"
        pre_a = f"atrim=start={trim_in - seek:.4f},"
    bw, bh, cx0, cy0, fit_f = base_box(item, W, H, src_w, src_h)
    kf = _kf(item, dur, cx0, cy0)
    ch: list[str] = []
    L = f"pc{idx}"
    # --- time: speed / ramp → geometry → speed warp → constant fps, clip-local clock 0…dur
    v = "[{IN0}:v]" + ("setpts=PTS-STARTPTS," if is_img else pre_v + setpts_for(pieces) + ",")
    v += f"{fit_f},setsar=1,"
    if not is_img:
        v += warp_filter(item.get("speed_warp"), min_speed, fps)
    v += f"fps={fps:.3f},trim=duration={dur:.3f},setpts=PTS-STARTPTS"
    ap = item.get("alpha_path")
    cut = bool(item.get("cutout") and ap and not is_img and Path(ap).exists())
    if not cut:
        v += _key(item)  # the person matte replaces colour keying (as on the legacy path)
    # --- look: colour LUT, grade, effects (on the colour planes; alpha kept aside)
    looks = []
    lp = item.get("lut_path")
    if lp and Path(lp).exists():  # a library .cube on this clip only, with its own intensity
        from . import effects as _fx
        looks.append(_fx.lut_mix(f"lut3d=file='{escape_filter_path(Path(lp))}':interp=tetrahedral", item.get("lut_amount")))
    lut = colorpro.lut_filter(item.get("color"), work, f"clip{idx}")
    if lut:
        looks.append(lut)
    g = item.get("grade") or ({k: x for k, x in catalog.GRADE_PRESETS.get(item.get("grade_preset") or "", {}).items()
                               if k not in ("label", "cat")} if item.get("grade_preset") else None)
    gf = catalog.grade_filter(g)
    if gf:
        looks.append(gf)
    st = catalog.stack_filter(item.get("stack"), bw, bh, fps, dur)
    if st:
        looks.append(re.sub(r"\[([A-Za-z]\w*)\]", lambda m: f"[{m.group(1)}_{L}]", st) + f",scale={bw}:{bh},setsar=1")
    mspec = masks.build([masks.clean(item.get("mask")), masks.crop_spec(item.get("crop"))], bw, bh, dur, fps, work, f"mask{idx}")
    if mspec:
        inputs.append(mspec[0])
    if cut:
        # same source window as the picture (seek / trim / speed / fit / warp) → frame-exact person alpha
        ai = len(inputs)
        inputs.append(["-ss", f"{seek:.3f}", "-t", f"{trim_in - seek + span + 0.3:.3f}", "-i", str(ap)])
        edge = edge_filter(item.get("edge_shrink", 0), item.get("edge_feather", 0), H)
        ch.append(f"[{{IN{ai}}}:v]{pre_v}{setpts_for(pieces)},scale={src_w}:{src_h},{fit_f},setsar=1,"
                  f"{warp_filter(item.get('speed_warp'), min_speed, fps)}fps={fps:.3f},trim=duration={dur:.3f},"
                  f"setpts=PTS-STARTPTS,format=yuv420p,extractplanes=y,{ALPHA_RANGE}{',' + edge if edge else ''}[{L}ct]")
    if looks or mspec or cut:
        if cut:
            ch.append(v + f",format=rgba[{L}c]")
            alpha = f"[{L}ct]"
        else:
            ch.append(v + f",format=rgba,split[{L}c][{L}a]")
            ch.append(f"[{L}a]alphaextract[{L}al0]")
            alpha = f"[{L}al0]"
        if mspec:
            ch.append(f"[{{IN1}}:v]{mspec[1]},trim=duration={dur:.3f}[{L}mk];{alpha}[{L}mk]blend=all_mode=multiply:shortest=1[{L}al1]")
            alpha = f"[{L}al1]"
        col = f"[{L}c]format=yuv420p" + ("," + ",".join(looks) if looks else "")
        ch.append(f"{col},format=rgba[{L}cl];[{L}cl]{alpha}alphamerge")
    else:
        ch.append(v + ",format=rgba")
    # --- opacity (static or keyframed via sendcmd), fades
    tail = []
    op = max(0.0, min(1.0, float(item.get("opacity", 1.0) if item.get("opacity") is not None else 1.0)))
    if "opacity" in kf and K.animated(kf["opacity"]):
        cmd = work / f"op{idx}.cmd"
        cmd.write_text(K.sendcmd(f"colorchannelmixer@op{idx}", "aa", kf["opacity"], dur, fps, every=1))
        tail.append(f"sendcmd=f='{escape_filter_path(cmd)}',colorchannelmixer@op{idx}=aa={K.sample(kf['opacity'], 0):.4f}")
    else:
        if "opacity" in kf:
            op = kf["opacity"][0]["v"]
        if op < 0.999:
            tail.append(f"colorchannelmixer=aa={op:.4f}")
    if item.get("fade", True) and (item.get("fit") or "cover") == "cover":
        fd = min(0.25, dur / 4)
        tail.append(f"fade=t=in:st=0:d={fd:.3f}:alpha=1,fade=t=out:st={max(0.0, dur - fd):.3f}:d={fd:.3f}:alpha=1")
    # --- rotation (fixed hypot canvas) then per-frame scale
    rot_pts = kf.get("rotation") or ([{"t": 0.0, "v": float(item.get("rotate", 0) or 0), "ease": "linear"}] if float(item.get("rotate", 0) or 0) else [])
    cw = bw
    if rot_pts and (K.animated(rot_pts) or abs(rot_pts[0]["v"]) > 1e-3):
        r = K.expr(rot_pts, "t", scale=math.pi / 180)
        tail.append(f"rotate=a={K.q(r)}:ow='hypot(iw,ih)':oh=ow:c=black@0")
        cw = _ev(math.hypot(bw, bh) + 1)
    sc = kf.get("scale")
    if sc and K.animated(sc):
        tail.append(f"format=yuva420p,scale=w={K.q(f'max(2,trunc({cw}*' + K.expr(sc, 't') + '/2)*2)')}:h=-2:eval=frame")
    elif sc and abs(sc[0]["v"] - 1) > 1e-3:
        tail.append(f"scale={_ev(cw * sc[0]['v'])}:-2")
    ch[-1] += ("," + ",".join(tail) if tail else "") + f"[{L}]"
    # --- composite
    mode = item.get("blend_mode") or "normal"
    mode = mode if mode in BLEND_MODES else "normal"
    xs, ys = kf.get("x") or [{"t": 0, "v": cx0, "ease": "linear"}], kf.get("y") or [{"t": 0, "v": cy0, "ease": "linear"}]
    out = f"[vo{idx}]"
    if mode == "normal":
        px = K.q(f"{W}*{K.expr(xs, 't', offset=s)}-w/2")
        py = K.q(f"{H}*{K.expr(ys, 't', offset=s)}-h/2")
        ch.append(f"[{L}]setpts=PTS+{s:.4f}/TB[{L}t];{cur}[{L}t]overlay=x={px}:y={py}:eval=frame:format=auto:"
                  f"enable='between(t\\,{s:.4f}\\,{e:.4f})':eof_action=pass{out}")
    else:
        px = K.q(f"{W}*{K.expr(xs, 't')}-w/2")
        py = K.q(f"{H}*{K.expr(ys, 't')}-h/2")
        ffm = _FF_MODE.get(mode, mode)
        top, bot = (f"[{L}lg]", f"[{L}bg]") if mode != "subtract" else (f"[{L}bg]", f"[{L}lg]")
        ch.append(f"{cur}split[{L}m][{L}s];[{L}s]trim=start={s:.4f}:end={e:.4f},setpts=PTS-STARTPTS,split[{L}b1][{L}b2]")
        ch.append(f"color=black@0:s={W}x{H}:r={fps:.3f}:d={dur + 0.1:.3f},format=rgba[{L}cv];"
                  f"[{L}cv][{L}]overlay=x={px}:y={py}:eval=frame:format=rgb:eof_action=pass,format=rgba,split[{L}ly][{L}la]")
        ch.append(f"[{L}la]alphaextract[{L}lal];[{L}ly]format=gbrp[{L}lg];[{L}b1]format=gbrp[{L}bg];"
                  f"{top}{bot}blend=all_mode={ffm}:shortest=1,format=rgba[{L}bl];[{L}bl][{L}lal]alphamerge[{L}ba];"
                  f"[{L}b2][{L}ba]overlay=format=auto:shortest=1,format=yuv420p,setpts=PTS+{s:.4f}/TB[{L}e];"
                  f"[{L}m][{L}e]overlay=enable='between(t\\,{s:.4f}\\,{e:.4f})':eof_action=pass{out}")
    # --- the clip's own sound
    audio = None
    vol = max(0.0, min(2.0, float(item.get("volume", 0) or 0)))
    if vol > 0 and not is_img and info.get("has_audio"):
        ap = audio_pieces(pieces)
        if len(ap) == 1:
            a = f"[{{IN0}}:a]{pre_a}asetpts=PTS-STARTPTS,{atempo(ap[0][2])}"
        else:
            labs = "".join(f"[{L}ap{j}]" for j in range(len(ap)))
            parts = [f"[{{IN0}}:a]{pre_a}asetpts=PTS-STARTPTS,asplit={len(ap)}{labs}"]
            for j, (a0, ln, sp) in enumerate(ap):
                parts.append(f"[{L}ap{j}]atrim=start={a0:.4f}:end={a0 + ln:.4f},asetpts=PTS-STARTPTS,{atempo(sp)}[{L}aq{j}]")
            a = ";".join(parts) + ";" + "".join(f"[{L}aq{j}]" for j in range(len(ap))) + f"concat=n={len(ap)}:v=0:a=1"
        ms = int(round(s * 1000))
        fd = min(0.05, dur / 4)
        a += (f",atrim=0:{dur:.4f},aformat=sample_rates=48000:channel_layouts=mono,volume={vol:.3f},"
              f"afade=t=in:d={fd:.3f},afade=t=out:st={max(0.0, dur - fd):.3f}:d={fd:.3f},adelay={ms}|{ms}[{L}aud]")
        audio = (a, f"[{L}aud]")
    return {"inputs": inputs, "chains": ch, "out": out, "audio": audio}



def _shift_pts(pts: list[dict], d: float) -> list[dict]:
    """Keyframes moved d seconds earlier; the value at d becomes the first keyframe at 0."""
    if not pts:
        return pts
    rest = [{**p, "t": round(p["t"] - d, 4)} for p in pts if p["t"] - d > 1e-4]
    return [{"t": 0.0, "v": K.sample(pts, d), "ease": "linear"}] + rest


def advance(item: dict, d: float) -> dict:
    """The first `d` seconds of a clip are dropped (a Short / preview starts inside it): move the
    source in-point and the clip-relative keyframes so what remains looks the same."""
    if d <= 1e-4:
        return item
    out = dict(item)
    if item.get("type") != "image":
        pts = K.normalize(item.get("speed_ramp"), lo=0.25, hi=4.0)
        if K.animated(pts):
            src = sum(ln for _, ln, _ in ramp_pieces(item, d, None))
            out["speed_ramp"] = _shift_pts(pts, src)
        else:
            src = d * max(0.25, min(4.0, float(item.get("speed", 1) or 1)))
        out["trim_in"] = round(float(item.get("trim_in", 0) or 0) + src, 4)
    if isinstance(item.get("kf"), dict):
        out["kf"] = {k: _shift_pts(K.normalize(v), d) for k, v in item["kf"].items()}
    for key in ("mask", "crop"):
        m = item.get(key)
        if isinstance(m, dict) and isinstance(m.get("kf"), dict):
            out[key] = {**m, "kf": {k: _shift_pts(K.normalize(v), d) for k, v in m["kf"].items()}}
    if isinstance(item.get("stack"), list):
        out["stack"] = [{**st, "kf": {k: _shift_pts(K.normalize(v), d) for k, v in st["kf"].items()}}
                        if isinstance(st, dict) and isinstance(st.get("kf"), dict) else st for st in item["stack"]]
    return out


def wire(res: dict, next_in: int) -> tuple[list[str], list[str], int, tuple | None]:
    """Fill input placeholders → (ffmpeg input args, chains, next free input index, audio)."""
    args: list[str] = []
    mapping = {}
    for i, a in enumerate(res["inputs"]):
        args += a
        mapping[f"{{IN{i}}}"] = str(next_in + i)

    def fill(s: str) -> str:
        for k, v in mapping.items():
            s = s.replace(k, v)
        return s
    chains = [fill(c) for c in res["chains"]]
    audio = (fill(res["audio"][0]), res["audio"][1]) if res.get("audio") else None
    return args, chains, next_in + len(res["inputs"]), audio
