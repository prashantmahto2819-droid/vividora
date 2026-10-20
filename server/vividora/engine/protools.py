"""Pro tools for the MAIN video (effects.pro) — all off by default, zero cost when off.

effects.pro = {
  "stabilize":   {"enabled": false, "strength": 0.5, "zoom": 0},          two-pass vidstab (deshake fallback)
  "denoise":     {"enabled": false, "method": "hqdn3d|nlmeans", "strength": 0.4},
  "sharpen":     {"enabled": false, "method": "cas|unsharp", "amount": 0.4},
  "face_refine": {"enabled": false, "strength": 0.5, "brighten": 0.3, "eyes": 0.3},
  "speed_warp":  "off|fast|balanced|best"     smooth slow motion for edl.speed ranges < 0.75×
  "color":       colorpro spec (wheels / curves / HSL / match)
  "morph_cut":   {"enabled": false, "all": false, "frames": 8, "mode": "flow|blend"}   (+ edl cut.morph)
  "mask":        masks spec + "bg": "black|blur|#rrggbb"
}
effects.transform.kf = {x, y, scale, rotation, opacity}  keyframes on the OUTPUT timeline
  (x/y = offset as a fraction of the frame like transform.x/y, scale = 1 full frame).

Render-time cost (CPU, 1080p, relative to a plain render ≈ 1×):
  stabilize  +1 decode pass (detect, ~0.3–0.6× realtime of the source) + ~10 % in the render
  denoise    hqdn3d +5 %; nlmeans +150–300 % (use on short clips)
  sharpen    cas/unsharp +3–5 %
  face_refine one sampled face-detect pass (2 fps) + a tiny mask video + ~15 % in the render
  speed_warp fast +5 %; balanced (½-res optical flow) ≈ 1–2 fps of slowed footage; best ≈ 0.3–1 fps
  color      one lut3d +3 %
  morph_cut  per cut: 2-frame optical-flow morph, < 0.2 s each
  mask       static PNG +2 %; animated: numpy mask video (~3 ms/frame) + 2 %
  transform.kf  one overlay + per-frame scale +5–10 %
"""

from __future__ import annotations

import math
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import colorpro, masks
from . import keyframes as K
from .ffmpeg import escape_filter_path

TOOLS = {
    "stabilize": {"label": "स्टेबलाइज़ · Stabilise", "params": [
        {"name": "strength", "label": "ताक़त · Strength", "min": 0.1, "max": 1, "default": 0.5, "step": 0.05},
        {"name": "zoom", "label": "zoom % (0 = auto)", "min": 0, "max": 20, "default": 0, "step": 1}],
        "cost": "1 extra decode pass + ~10 %"},
    "denoise": {"label": "नॉइज़ हटाएँ · Denoise", "methods": ["hqdn3d", "nlmeans"], "params": [
        {"name": "strength", "label": "ताक़त · Strength", "min": 0.05, "max": 1, "default": 0.4, "step": 0.05}],
        "cost": "hqdn3d +5 %, nlmeans +150–300 %"},
    "sharpen": {"label": "शार्प · Sharpen", "methods": ["cas", "unsharp"], "params": [
        {"name": "amount", "label": "मात्रा · Amount", "min": 0.05, "max": 1, "default": 0.4, "step": 0.05}],
        "cost": "+3–5 %"},
    "face_refine": {"label": "चेहरा निखारें · Face refine", "params": [
        {"name": "strength", "label": "स्किन स्मूद · Skin smooth", "min": 0, "max": 1, "default": 0.5, "step": 0.05},
        {"name": "brighten", "label": "चमक · Brighten", "min": 0, "max": 1, "default": 0.3, "step": 0.05},
        {"name": "eyes", "label": "आँखें · Eye pop", "min": 0, "max": 1, "default": 0.3, "step": 0.05}],
        "cost": "face detect (2 fps sample) + ~15 %"},
    "speed_warp": {"label": "स्पीड वार्प · Speed Warp (smooth slow-mo)", "choices": ["off", "fast", "balanced", "best"],
                   "cost": "fast +5 %, balanced ~1–2 fps, best ~0.3–1 fps of slowed footage"},
    "morph_cut": {"label": "मॉर्फ कट · Morph cut (smooth jump cut)", "modes": ["flow", "blend"], "params": [
        {"name": "frames", "label": "frames", "min": 4, "max": 16, "default": 8, "step": 2}],
        "cost": "< 0.2 s per cut"},
    "color": {"label": "कलर · Colour wheels / curves / HSL / match", "cost": "one lut3d +3 %"},
    "mask": {"label": "मास्क · Mask (main video)", "bg": ["black", "blur", "#rrggbb"], "cost": "+2 %"},
}


@lru_cache(maxsize=1)
def ffmpeg_filters() -> frozenset[str]:
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and len(parts[0]) == 3:
            names.add(parts[1])
    return frozenset(names)


def has_vidstab() -> bool:
    f = ffmpeg_filters()
    return "vidstabdetect" in f and "vidstabtransform" in f


def _on(d) -> dict | None:
    return d if isinstance(d, dict) and d.get("enabled") else None


def _f(v, d: float, lo: float = -1e9, hi: float = 1e9) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return d


# ------------------------------------------------------------------ source-level (before cuts)
class SourceTap:
    """Filters that must see the uncut source in frame order (stabilisation, face refine).
    render.py takes its video source label(s) from here instead of the literal [0:v]."""

    def __init__(self) -> None:
        self.chain = ""            # comma chain / subgraph applied to [0:v]
        self.inputs: list[list[str]] = []
        self.labels: list[str] = []
        self.notes: list[str] = []

    def attach(self, inputs: list[str], chains: list[str], next_in: int, uses: int) -> int:
        if not self.chain:
            self.labels = ["[0:v]"] * uses
            return next_in
        chain = self.chain
        for i, a in enumerate(self.inputs):
            inputs += a
            chain = chain.replace(f"{{IN{i}}}", str(next_in + i))
        next_in += len(self.inputs)
        self.labels = [f"[srcv{i}]" for i in range(uses)]
        chains.insert(0, f"[0:v]{chain}" + (f",split={uses}" if uses > 1 else ",null") + "".join(self.labels))
        return next_in

    def label(self, i: int = 0) -> str:
        return self.labels[i] if i < len(self.labels) else "[0:v]"


def source_tap(e: dict, video: Path, meta: dict, work: Path, need_until: float, preview: bool = False,
               need_from: float = 0.0) -> SourceTap:
    tap = SourceTap()
    pro = e.get("pro") or {}
    parts: list[str] = []
    st = _on(pro.get("stabilize"))
    if st and not preview:
        f = stabilize_filter(st, video, work, need_until)
        if f:
            parts.append(f)
            tap.notes.append("stabilize:" + ("vidstab" if "vidstab" in f else "deshake"))
    fr = _on(pro.get("face_refine"))
    if fr:
        sub = face_refine_graph(fr, video, meta, work, need_until, n_inputs=len(tap.inputs), start=need_from)
        if sub:
            graph, inp = sub
            tap.inputs.append(inp)
            parts.append(graph)
            tap.notes.append("face_refine")
        else:
            tap.notes.append("face_refine:no-face")
    tap.chain = ",".join(parts)
    return tap


def stabilize_filter(st: dict, video: Path, work: Path, need_until: float) -> str:
    strength = _f(st.get("strength"), 0.5, 0.05, 1.0)
    zoom = _f(st.get("zoom"), 0.0, 0.0, 30.0)
    if has_vidstab():
        trf = work / "stab.trf"
        shak = int(round(3 + 7 * strength))
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-t", f"{need_until + 0.5:.3f}", "-an",
               "-vf", f"vidstabdetect=shakiness={shak}:accuracy=12:stepsize=6:result='{escape_filter_path(trf)}'", "-f", "null", "-"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and trf.exists():
            smooth = int(round(6 + 44 * strength))
            zz = f"optzoom=0:zoom={zoom:.1f}" if zoom > 0 else "optzoom=1"
            return (f"vidstabtransform=input='{escape_filter_path(trf)}':smoothing={smooth}:{zz}:interpol=bicubic:crop=black,"
                    f"unsharp=5:5:0.5:3:3:0.3")
    r = int(round(8 + 40 * strength))
    k = 1 + max(zoom, 4.0) / 100
    return (f"deshake=rx={min(64, r // 16 * 16 or 16)}:ry={min(64, r // 16 * 16 or 16)}:edge=mirror,"
            f"scale=trunc(iw*{k:.3f}/2)*2:trunc(ih*{k:.3f}/2)*2,crop=trunc(iw/{k:.3f}/2)*2:trunc(ih/{k:.3f}/2)*2")


# ------------------------------------------------------------------ face refinement
def _haar():
    try:
        import cv2
        if not hasattr(cv2, "CascadeClassifier"):
            return None, None
        p = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        return (cv2, cv2.CascadeClassifier(str(p))) if p.exists() else (None, None)
    except Exception:  # noqa: BLE001
        return None, None


def _skin_box(rgb: np.ndarray) -> tuple[float, float, float, float] | None:
    """Fallback face finder: biggest skin-coloured blob in the upper ¾ (YCbCr thresholds)."""
    h, w, _ = rgb.shape
    r, g, b = [rgb[..., i].astype(np.float32) for i in range(3)]
    cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
    y = 0.299 * r + 0.587 * g + 0.114 * b
    m = (cb > 77) & (cb < 127) & (cr > 136) & (cr < 173) & (y > 50)
    m[int(h * 0.8):] = False
    if m.sum() < h * w * 0.004:
        return None
    try:
        import cv2
        n, lab, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
        if n <= 1:
            return None
        i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        x0, y0, bw, bh = stats[i, 0], stats[i, 1], stats[i, 2], stats[i, 3]
    except Exception:  # noqa: BLE001
        ys, xs = np.nonzero(m)
        x0, y0, bw, bh = xs.min(), ys.min(), xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
    # a face is roughly 3:4; the blob may include the neck → trim its height
    bh = min(bh, int(bw * 1.35))
    return (x0 + bw / 2) / w, (y0 + bh / 2) / h, bw / w, bh / h


def detect_faces(video: Path, until: float, step: float = 0.5, width: int = 320,
                 start: float = 0.0) -> list[tuple[float, float, float, float, float]]:
    """[(t, cx, cy, w, h)] normalised, sampled every `step` s (Haar cascade, else skin blob)."""
    from .ffmpeg import probe
    info = probe(video)
    sw, sh = int(info["width"]), int(info["height"])
    h = max(2, int(round(sh * width / sw / 2)) * 2)
    cv2, det = _haar()
    start = max(0.0, min(start, until))
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", str(video), "-t", f"{until - start + step:.3f}", "-an",
                             "-vf", f"fps={1 / step:.4f},scale={width}:{h}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    out, n, fb = [], 0, width * h * 3
    assert proc.stdout is not None
    while True:
        buf = proc.stdout.read(fb)
        if len(buf) < fb:
            break
        rgb = np.frombuffer(buf, np.uint8).reshape(h, width, 3)
        box = None
        if det is not None:
            faces = det.detectMultiScale(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), scaleFactor=1.15, minNeighbors=4, minSize=(20, 20))
            if len(faces):
                x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                box = ((x + fw / 2) / width, (y + fh / 2) / h, fw / width, fh / h)
        if box is None:
            box = _skin_box(rgb)
        if box:
            out.append((start + n * step, *box))
        n += 1
    proc.wait()
    return out


def _smooth_boxes(boxes, alpha: float = 0.5):
    out, prev = [], None
    for b in boxes:
        if prev is None:
            prev = list(b)
        else:
            prev = [b[0]] + [p + (x - p) * alpha for p, x in zip(prev[1:], b[1:])]
        out.append(tuple(prev))
    return out


def face_refine_graph(fr: dict, video: Path, meta: dict, work: Path, until: float, n_inputs: int = 0, start: float = 0.0):
    """→ (subgraph on the source stream, mask-video input args) or None when no face is found."""
    boxes = detect_faces(video, until, start=start)
    if not boxes:
        return None
    boxes = _smooth_boxes(boxes)
    fps = min(15.0, float(meta.get("fps") or 30))  # the face moves slowly; framesync holds each mask frame
    sw, sh = int(meta.get("width") or 1280), int(meta.get("height") or 720)
    mw, mh = masks.anim_size(sw, sh)
    ts = np.array([b[0] for b in boxes])
    arr = np.array([b[1:] for b in boxes])
    ys, xs = np.mgrid[0:mh, 0:mw].astype(np.float32)

    empty = np.zeros((mh, mw), np.float32)

    def frame(t: float) -> np.ndarray:
        if t < start - 0.5:  # before the part that is used: nothing to draw (cheap)
            return empty
        cx, cy, bw, bh = [float(np.interp(t, ts, arr[:, i])) for i in range(4)]
        # a generous ellipse around the face box (forehead → chin), soft edge
        rx, ry = bw * 0.62 * mw, bh * 0.75 * mh
        d = np.hypot((xs - cx * mw) / max(1, rx), (ys - (cy - bh * 0.04) * mh) / max(1, ry))
        return np.clip((1.0 - d) / 0.25, 0, 1)
    mv = masks.write_video(frame, mw, mh, until + 0.5, fps, work / "face_mask.mkv")
    s = _f(fr.get("strength"), 0.5, 0, 1)
    br = _f(fr.get("brighten"), 0.3, 0, 1)
    ey = _f(fr.get("eyes"), 0.3, 0, 1)
    gw = max(64, sw // 4 // 2 * 2)
    gh = max(36, int(round(sh * gw / sw / 2)) * 2)
    # skin probability from chroma (soft YCbCr box), computed at ¼ size
    skin = ("255*clip(min(cb(X\\,Y)-77\\,127-cb(X\\,Y))/6\\,0\\,1)*clip(min(cr(X\\,Y)-136\\,172-cr(X\\,Y))/6\\,0\\,1)")
    i = n_inputs
    g = (f"split=3[fr0][fr1][fr2];"
         f"[fr2]scale={gw}:{gh},format=yuv444p,geq=lum='{skin}':cb=128:cr=128,format=gray,gblur=sigma=1.5,scale={sw}:{sh}[frsk];"
         f"[{{IN{i}}}:v]scale={sw}:{sh}:flags=bilinear,format=gray,setpts=PTS-STARTPTS,split[frfa][frfb];"
         f"[frsk]split[frs1][frs2];[frs1][frfa]blend=all_mode=multiply,lut=y='val*{0.8 * s:.3f}'[frm];"
         f"[fr1]bilateral=sigmaS={3 + 5 * s:.1f}:sigmaR={0.025 + 0.045 * s:.3f}:planes=1,"
         f"eq=brightness={0.025 * br:.4f}:gamma={1 + 0.06 * br:.4f},format=yuva420p[frsm];[frsm][frm]alphamerge[frsa];"
         f"[fr0][frsa]overlay=format=auto[frb]")
    if ey > 0.01:
        # eyes / brows / lips = the NON-skin parts inside the face ellipse → a little local contrast
        g += (f";[frb]split[frc0][frc1];[frs2]negate[frns];[frns][frfb]blend=all_mode=multiply,lut=y='val*{0.8 * ey:.3f}'[frem];"
              f"[frc1]unsharp=5:5:{0.6 + 1.2 * ey:.2f}:5:5:0,eq=contrast={1 + 0.06 * ey:.3f},format=yuva420p[frsh];"
              f"[frsh][frem]alphamerge[frea];[frc0][frea]overlay=format=auto")
    else:
        g += ";[frb]null"
    g += ",format=yuv420p"
    return g, ["-i", str(mv)]


# ------------------------------------------------------------------ output chain pieces
def denoise_filter(pro: dict) -> str:
    d = _on(pro.get("denoise"))
    if not d:
        return ""
    s = _f(d.get("strength"), 0.4, 0.01, 1.0)
    if d.get("method") == "nlmeans":
        return f"nlmeans=s={1 + 5 * s:.2f}:p=3:r=7"
    return f"hqdn3d={1 + 7 * s:.2f}:{1 + 5 * s:.2f}:{2 + 10 * s:.2f}:{2 + 8 * s:.2f}"


def sharpen_filter(pro: dict) -> str:
    d = _on(pro.get("sharpen"))
    if not d:
        return ""
    a = _f(d.get("amount"), 0.4, 0.0, 1.0)
    if d.get("method") == "unsharp":
        return f"unsharp=5:5:{0.3 + 1.2 * a:.2f}:5:5:0"
    return f"cas=strength={0.1 + 0.6 * a:.3f}"  # cas 1.0 is far too harsh for faces


def pre_grade(e: dict, work: Path) -> str:
    """Denoise + colour correction LUT, right after the picture is framed (before zoom/look/grade)."""
    pro = e.get("pro") or {}
    parts = [denoise_filter(pro), colorpro.lut_filter(pro.get("color"), work, "main")]
    return ",".join(p for p in parts if p)


def post_grade(e: dict) -> str:
    return sharpen_filter(e.get("pro") or {})


def warp_main(e: dict, rate: float, fps: float) -> str:
    from .compose import warp_filter
    mode = (e.get("pro") or {}).get("speed_warp")
    return warp_filter(mode if isinstance(mode, str) else ((mode or {}).get("mode") if isinstance(mode, dict) and mode.get("enabled") else None),
                       rate, fps)


def transform_kf(tf: dict | None, w: int, h: int, fps: float, dur: float, work: Path) -> str:
    """Main video position / size / rotation / opacity keyframes (output timeline). "" = not animated."""
    t = tf or {}
    raw = t.get("kf") or {}
    kf = {k: K.normalize(raw.get(k)) for k in ("x", "y", "scale", "rotation", "opacity") if raw.get(k)}
    if not any(K.animated(v) or (k == "rotation" and v and abs(v[0]["v"]) > 1e-3) for k, v in kf.items()):
        return ""
    s0, x0, y0 = float(t.get("scale", 1) or 1), float(t.get("x", 0) or 0), float(t.get("y", 0) or 0)
    bg = t.get("bg", "blur")
    if bg == "blur":
        back = "[tka]gblur=sigma=30,eq=brightness=-0.08[tkbg]"
    else:
        col = "black" if bg in ("black", "", None) else "0x" + str(t.get("bg_color", "#000000")).lstrip("#")[:6]
        back = f"[tka]drawbox=x=0:y=0:w=iw:h=ih:color={col}:t=fill[tkbg]"
    fg = "[tkb]format=rgba"
    op = kf.get("opacity")
    if op and K.animated(op):
        cmd = work / "main_op.cmd"
        cmd.write_text(K.sendcmd("colorchannelmixer@mop", "aa", op, dur, fps))
        fg += f",sendcmd=f='{escape_filter_path(cmd)}',colorchannelmixer@mop=aa={K.sample(op, 0):.4f}"
    elif op and op[0]["v"] < 0.999:
        fg += f",colorchannelmixer=aa={op[0]['v']:.4f}"
    cw = w
    rot = kf.get("rotation")
    if rot and (K.animated(rot) or abs(rot[0]["v"]) > 1e-3):
        fg += f",rotate=a={K.q(K.expr(rot, 't', scale=math.pi / 180))}:ow='hypot(iw,ih)':oh=ow:c=black@0"
        cw = int(math.hypot(w, h) / 2 + 1) * 2
    sc = kf.get("scale") or [{"t": 0, "v": s0, "ease": "linear"}]
    fg += f",format=yuva420p,scale=w={K.q('max(2,trunc(' + str(cw) + '*' + K.expr(sc, 't') + '/2)*2)')}:h=-2:eval=frame"
    xs = kf.get("x") or [{"t": 0, "v": x0, "ease": "linear"}]
    ys = kf.get("y") or [{"t": 0, "v": y0, "ease": "linear"}]
    px = K.q(f"(W-w)/2+W*{K.expr(xs, 't')}")
    py = K.q(f"(H-h)/2+H*{K.expr(ys, 't')}")
    return f"split[tka][tkb];{back};{fg}[tkfg];[tkbg][tkfg]overlay=x={px}:y={py}:eval=frame:format=auto,format=yuv420p"


def main_mask(e: dict, w: int, h: int, fps: float, dur: float, work: Path):
    """→ (input args, filter subgraph template with {IN0}) or None."""
    m = (e.get("pro") or {}).get("mask")
    spec = masks.clean(m)
    if not spec:
        return None
    res = masks.build([spec], w, h, dur, fps, work, "main_mask")
    if not res:
        return None
    args, prep = res
    bg = (m or {}).get("bg") or "black"
    if bg == "blur":
        back = "[mma]gblur=sigma=30,eq=brightness=-0.1[mmbg]"
    else:
        col = "black" if bg in ("black", "") else "0x" + str(bg).lstrip("#")[:6]
        back = f"[mma]drawbox=x=0:y=0:w=iw:h=ih:color={col}:t=fill[mmbg]"
    g = (f"split[mma][mmb];{back};[{{IN0}}:v]{prep},trim=duration={dur + 0.1:.3f}[mmk];"
         f"[mmb]format=yuva420p[mmc];[mmc][mmk]alphamerge[mmf];[mmbg][mmf]overlay=format=auto:eof_action=pass,format=yuv420p")
    return args, g


# ------------------------------------------------------------------ morph cut
def morph_points(e: dict, edl: dict, keep, segs, use_segments: bool, cuts: list[float]) -> list[float]:
    """Output times of the jump cuts that get a morph (global switch or per-cut `morph: true`)."""
    mc = (e.get("pro") or {}).get("morph_cut") or {}
    glob = bool(mc.get("enabled")) and bool(mc.get("all"))
    flags = {}
    for c in edl.get("cuts") or []:
        if c.get("enabled", True) and c.get("morph") is not None:
            flags[round(float(c.get("end", -1)), 2)] = bool(c["morph"])
    if not (glob or any(flags.values())) or (not mc.get("enabled") and not any(flags.values())):
        return []
    pts = []
    if use_segments:
        starts = {round(a, 2) for a, _ in keep[1:]}
        for sg in segs[1:]:
            if round(sg["a"], 2) in starts and not str(sg.get("tr", "")).startswith("x_"):
                if flags.get(round(sg["a"], 2), glob):
                    pts.append(sg["out_start"])
    else:
        for t, (a, _) in zip(cuts, keep[1:]):
            on = glob
            for k, v in flags.items():
                if abs(k - a) < 0.08:
                    on = v
            if on:
                pts.append(t)
    return pts


def morph_graph(points: list[float], e: dict, fps: float, dur: float, cur: str, chains: list[str],
                seg_bounds: list[float] | None = None) -> str:
    """Replace ±k frames around each cut with frames morphed (optical flow) from the last good frame
    before to the first good frame after. Audio is untouched; duration unchanged."""
    if not points:
        return cur
    mc = (e.get("pro") or {}).get("morph_cut") or {}
    frames = int(_f(mc.get("frames"), 8, 4, 16)) // 2 * 2
    mode = "mci" if mc.get("mode", "flow") != "blend" else "blend"
    bounds = sorted(set([0.0, *(seg_bounds or points), dur]))
    use = []
    for tc in points:
        prev_b = max([b for b in bounds if b < tc - 1e-6], default=0.0)
        next_b = min([b for b in bounds if b > tc + 1e-6], default=dur)
        k = min(frames // 2, int((tc - prev_b) * fps) - 2, int((next_b - tc) * fps) - 2)
        if k >= 2:
            use.append((tc, k))
    if not use:
        return cur
    n = len(use)
    outs = "".join(f"[mcA{i}][mcB{i}]" for i in range(n))
    chains.append(f"{cur}split={2 * n + 1}[mcm]{outs}")
    base = "[mcm]"
    for i, (tc, k) in enumerate(use):
        ta = tc - (k + 1) / fps
        tb = tc + k / fps
        w0 = tc - k / fps
        gap = (2 * k + 1) / fps
        mi = (f"minterpolate=fps={fps:.3f}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1:scd=none" if mode == "mci"
              else f"minterpolate=fps={fps:.3f}:mi_mode=blend:scd=none")
        chains.append(f"[mcA{i}]trim=start={ta - 0.25 / fps:.4f}:duration={0.9 / fps:.4f},setpts=PTS-STARTPTS[mca{i}];"
                      f"[mcB{i}]trim=start={tb - 0.25 / fps:.4f}:duration={0.9 / fps:.4f},setpts=PTS-STARTPTS[mcb{i}];"
                      f"[mca{i}][mcb{i}]concat=n=2:v=1:a=0,setpts=N*{gap:.5f}/TB,tpad=stop=4:stop_mode=clone,{mi},"
                      f"trim=start_frame=1:end_frame={2 * k + 1},setpts=PTS-STARTPTS+{w0:.4f}/TB[mcx{i}];"
                      f"{base}[mcx{i}]overlay=enable='between(t\\,{w0 - 0.1 / fps:.4f}\\,{w0 + (2 * k - 0.5) / fps:.4f})':eof_action=pass[mco{i}]")
        base = f"[mco{i}]"
    return base


def can_stabilize() -> str:
    return "vidstab" if has_vidstab() else ("deshake" if "deshake" in ffmpeg_filters() else "none")


def which(binary: str) -> bool:
    return shutil.which(binary) is not None
