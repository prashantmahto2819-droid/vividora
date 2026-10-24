"""Shape masks for overlay clips and the main video.

Mask JSON (all optional except shape):
  {"shape": "circle|ellipse|rect|heart|star|linear|mirror",
   "x": 0.5, "y": 0.5,          centre, fraction of the layer (0..1)
   "w": 0.6, "h": 0.6,          size, fraction of layer width / height (circle uses w)
   "rotation": 0,               degrees (linear: direction of the wipe edge; mirror: band angle)
   "roundness": 0,              rect corner radius 0..1 (1 = pill)
   "points": 5,                 star points (3..12); "inner": 0.45 inner radius ratio
   "feather": 0.02,             soft edge, fraction of the layer's shorter side (0..0.5)
   "invert": false,
   "kf": {"x": [...], "y": [...], "w": [...], "h": [...], "rotation": [...], "feather": [...], "roundness": [...]}}

The mask is drawn with numpy (signed-distance shapes, 1-px anti-aliasing) so a still mask is one
PNG and an animated mask is a small lossless grey video (≤ 640 px, scaled up in the graph).
That is far cheaper than a per-pixel geq expression and looks identical on every frame.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import numpy as np

from . import keyframes as K

SHAPES = {
    "circle": "Circle (गोला)", "ellipse": "Ellipse", "rect": "Rectangle (rounded)", "heart": "Heart ❤",
    "star": "Star ⭐", "linear": "Linear / split (wipe)", "mirror": "Mirror band (पट्टी)",
    "polygon": "Polygon / freehand ✎",
}
MAX_VERTS = 400
DEFAULTS = {"x": 0.5, "y": 0.5, "w": 0.6, "h": 0.6, "rotation": 0.0, "roundness": 0.0, "feather": 0.02,
            "points": 5, "inner": 0.4}
ANIM_KEYS = ("x", "y", "w", "h", "rotation", "feather", "roundness")
PARAMS = [
    {"name": "x", "label": "X (centre)", "min": -0.5, "max": 1.5, "default": 0.5, "step": 0.005},
    {"name": "y", "label": "Y (centre)", "min": -0.5, "max": 1.5, "default": 0.5, "step": 0.005},
    {"name": "w", "label": "चौड़ाई", "min": 0.01, "max": 3, "default": 0.6, "step": 0.005},
    {"name": "h", "label": "ऊँचाई", "min": 0.01, "max": 3, "default": 0.6, "step": 0.005},
    {"name": "rotation", "label": "घुमाव °", "min": -360, "max": 360, "default": 0, "step": 1},
    {"name": "roundness", "label": "गोल कोने", "min": 0, "max": 1, "default": 0, "step": 0.01},
    {"name": "feather", "label": "Feather (नरम किनारा)", "min": 0, "max": 0.5, "default": 0.02, "step": 0.005},
    {"name": "points", "label": "Star points", "min": 3, "max": 12, "default": 5, "step": 1},
    {"name": "inner", "label": "Star inner", "min": 0.1, "max": 0.9, "default": 0.4, "step": 0.01},
]
MAX_ANIM_SIDE = 640


def clean(spec) -> dict | None:
    """Validated mask spec, or None (= no mask)."""
    if not isinstance(spec, dict) or spec.get("enabled") is False:
        return None
    shape = spec.get("shape")
    if shape not in SHAPES:
        return None
    out = {"shape": shape, "invert": bool(spec.get("invert"))}
    for p in PARAMS:
        try:
            v = float(spec.get(p["name"], DEFAULTS[p["name"]]))
        except (TypeError, ValueError):
            v = float(DEFAULTS[p["name"]])
        out[p["name"]] = max(p["min"], min(p["max"], v))
    if shape == "polygon":
        # vertices as [x, y] fractions of the layer (0..1), at least 3; drawn around (x, y) with w/h = 1 unscaled
        pts = []
        for q in (spec.get("pts") or [])[:MAX_VERTS]:
            try:
                pts.append((max(-1.0, min(2.0, float(q[0]))), max(-1.0, min(2.0, float(q[1])))))
            except (TypeError, ValueError, IndexError):
                continue
        if len(pts) < 3:
            return None
        out["pts"] = pts
    out["kf"] = {k: K.normalize(v, lo=next(p["min"] for p in PARAMS if p["name"] == k),
                                hi=next(p["max"] for p in PARAMS if p["name"] == k))
                 for k, v in (spec.get("kf") or {}).items() if k in ANIM_KEYS}
    out["kf"] = {k: v for k, v in out["kf"].items() if K.animated(v)}
    return out


def is_animated(spec: dict | None) -> bool:
    return bool(spec and spec.get("kf"))


def _at(spec: dict, t: float) -> dict:
    v = dict(spec)
    for k, pts in (spec.get("kf") or {}).items():
        v[k] = K.sample(pts, t)
    return v


def draw(spec: dict, W: int, H: int, t: float = 0.0) -> np.ndarray:
    """Float mask (H, W) in 0..1 at time t."""
    p = _at(spec, t)
    s = float(min(W, H))
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    u = (xs + 0.5 - p["x"] * W) / s
    v = (ys + 0.5 - p["y"] * H) / s
    r = math.radians(p["rotation"])
    c, sn = math.cos(r), math.sin(r)
    ur, vr = u * c + v * sn, -u * sn + v * c
    a = max(1e-4, p["w"] * W / (2 * s))
    b = max(1e-4, p["h"] * H / (2 * s))
    shape = p["shape"]
    if shape == "circle":
        sd = np.hypot(ur, vr) - a
    elif shape == "ellipse":
        sd = (np.hypot(ur / a, vr / b) - 1.0) * min(a, b)
    elif shape == "rect":
        rr = max(0.0, min(1.0, p["roundness"])) * min(a, b)
        qx, qy = np.abs(ur) - a + rr, np.abs(vr) - b + rr
        sd = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - rr
    elif shape == "heart":
        # exact heart distance (Inigo Quilez's sdHeart): tip at (0,0), ~1.21 wide, ~1.10 tall
        kx, ky = 0.6036 / a, 0.5518 / b
        hx = np.abs(ur * kx)
        hy = -vr * ky + 0.5518
        d_top = np.hypot(hx - 0.25, hy - 0.75) - math.sqrt(2) / 4
        m = np.maximum(hx + hy, 0.0) * 0.5
        d_low = np.sqrt(np.minimum((hx - 0.0) ** 2 + (hy - 1.0) ** 2, (hx - m) ** 2 + (hy - m) ** 2)) * np.sign(hx - hy)
        sd = np.where(hx + hy > 1.0, d_top, d_low) / max(kx, ky)
    elif shape == "star":
        k = int(round(p["points"]))
        q = p["inner"]
        verts = [((a if i % 2 == 0 else a * q) * math.sin(math.pi * i / k), -(b if i % 2 == 0 else b * q) * math.cos(math.pi * i / k))
                 for i in range(2 * k)]
        sd = _poly_sd(ur, vr, verts)
    elif shape == "polygon":
        # vertices are layer fractions; x/y translate the whole shape (0.5 = as drawn), w/h scale it about its centre
        pts = p["pts"]
        mx = sum(q[0] for q in pts) / len(pts)
        my = sum(q[1] for q in pts) / len(pts)
        sw, sh = p["w"] / 0.6, p["h"] / 0.6  # DEFAULT w/h 0.6 = drawn size
        verts = [((((q[0] - mx) * sw + mx + (p["x"] - 0.5)) * W - p["x"] * W) / s, (((q[1] - my) * sh + my + (p["y"] - 0.5)) * H - p["y"] * H) / s) for q in pts]
        sd = _poly_sd(ur, vr, verts)
    elif shape == "linear":
        sd = ur
    else:  # mirror band
        sd = np.abs(vr) - b
    f = max(p["feather"], 1.0 / s)
    alpha = np.clip(0.5 - sd / f, 0.0, 1.0)
    if spec.get("invert"):
        alpha = 1.0 - alpha
    return alpha


def _poly_sd(x: np.ndarray, y: np.ndarray, verts: list[tuple[float, float]]) -> np.ndarray:
    """Signed distance to a closed polygon (negative inside), straight edges."""
    d = np.full(x.shape, np.inf, dtype=np.float32)
    inside = np.zeros(x.shape, dtype=bool)
    n = len(verts)
    for i in range(n):
        (x0, y0), (x1, y1) = verts[i], verts[(i + 1) % n]
        ex, ey = x1 - x0, y1 - y0
        wx, wy = x - x0, y - y0
        t = np.clip((wx * ex + wy * ey) / (ex * ex + ey * ey + 1e-12), 0, 1)
        d = np.minimum(d, np.hypot(wx - ex * t, wy - ey * t))
        cond = (y0 > y) != (y1 > y)
        xi = x0 + (y - y0) * ex / (ey if abs(ey) > 1e-12 else 1e-12)
        inside ^= cond & (x < xi)
    return np.where(inside, -d, d)


def multiply(*masks: np.ndarray | None) -> np.ndarray | None:
    out = None
    for m in masks:
        if m is None:
            continue
        out = m if out is None else out * m
    return out


def write_png(arr: np.ndarray, path: Path) -> Path:
    from PIL import Image
    Image.fromarray(np.clip(arr * 255 + 0.5, 0, 255).astype(np.uint8), "L").save(path)
    return path


def anim_size(W: int, H: int) -> tuple[int, int]:
    k = min(1.0, MAX_ANIM_SIDE / max(W, H))
    return max(2, int(W * k) // 2 * 2), max(2, int(H * k) // 2 * 2)


def write_video(frame_fn, W: int, H: int, dur: float, fps: float, path: Path) -> Path:
    """frame_fn(t) → (h, w) float mask at the reduced size; encoded losslessly (ffv1 grey)."""
    w, h = anim_size(W, H)
    n = max(1, int(math.ceil(dur * fps)) + 1)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}",
                            "-r", f"{fps:.4f}", "-i", "-", "-c:v", "ffv1", "-pix_fmt", "gray", str(path)],
                           stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert enc.stdin is not None
    from . import ffmpeg as _ff
    _ff.track(enc)
    try:
        for i in range(n):
            _ff.check_cancel()
            enc.stdin.write(np.clip(frame_fn(i / fps) * 255 + 0.5, 0, 255).astype(np.uint8).tobytes())
    finally:
        enc.stdin.close()
        _ff.untrack(enc)
    if enc.wait() != 0:
        raise RuntimeError("mask video failed: " + (enc.stderr.read().decode(errors="ignore")[-300:] if enc.stderr else ""))
    return path


def crop_spec(crop) -> dict | None:
    """Overlay-clip crop {x, y, w, h} (fractions of the clip, top-left based, keyframeable via kf)
    as a hard rectangle mask."""
    if not isinstance(crop, dict):
        return None
    try:
        x, y = float(crop.get("x", 0)), float(crop.get("y", 0))
        w, h = float(crop.get("w", 1)), float(crop.get("h", 1))
    except (TypeError, ValueError):
        return None
    kf = {k: K.normalize(v) for k, v in (crop.get("kf") or {}).items() if k in ("x", "y", "w", "h")}
    kf = {k: v for k, v in kf.items() if K.animated(v)}
    if not kf and w >= 0.999 and h >= 0.999 and x <= 0.001 and y <= 0.001:
        return None
    # top-left based crop → centre based rect mask
    ck = {}
    if kf:
        times = sorted({p["t"] for pts in kf.values() for p in pts})
        cx = [{"t": t, "v": K.sample(kf.get("x", []), t, x) + K.sample(kf.get("w", []), t, w) / 2, "ease": "linear"} for t in times]
        cy = [{"t": t, "v": K.sample(kf.get("y", []), t, y) + K.sample(kf.get("h", []), t, h) / 2, "ease": "linear"} for t in times]
        ck = {"x": cx, "y": cy, "w": kf.get("w") or [], "h": kf.get("h") or []}
        ck = {k: v for k, v in ck.items() if v}
    return {"shape": "rect", "x": x + w / 2, "y": y + h / 2, "w": w, "h": h, "rotation": 0.0, "roundness": 0.0,
            "feather": 0.0, "points": 5, "inner": 0.4, "invert": False, "kf": ck}


def build(specs: list[dict | None], W: int, H: int, dur: float, fps: float, work: Path, name: str) -> tuple[list[str], str] | None:
    """Render the product of the given masks for a W×H layer.
    → (ffmpeg input args, filter that turns that input into a W×H gray stream starting at 0) or None."""
    specs = [s for s in specs if s]
    if not specs:
        return None
    work.mkdir(parents=True, exist_ok=True)
    if not any(is_animated(s) for s in specs):
        p = write_png(multiply(*[draw(s, W, H) for s in specs]), work / f"{name}.png")
        return (["-loop", "1", "-framerate", f"{fps:.4f}", "-t", f"{dur + 0.5:.3f}", "-i", str(p)],
                "format=gray,setpts=PTS-STARTPTS")
    w, h = anim_size(W, H)
    p = write_video(lambda t: multiply(*[draw(s, w, h, t) for s in specs]), W, H, dur, fps, work / f"{name}.mkv")
    return (["-i", str(p)], f"scale={W}:{H}:flags=bilinear,format=gray,setpts=PTS-STARTPTS")
