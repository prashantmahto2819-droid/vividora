"""Pro colour correction, baked into ONE 3D LUT (.cube) per clip → a single lut3d pass.

JSON ("color" on the main video `effects.pro.color` or on an overlay clip):
  {"wheels": {"lift":   {"r":0,"g":0,"b":0,"y":0},     -1..1   shadows
              "gamma":  {"r":0,"g":0,"b":0,"y":0},     -1..1   mid-tones (+ = brighter)
              "gain":   {"r":0,"g":0,"b":0,"y":0},     -1..1   highlights
              "offset": {"r":0,"g":0,"b":0,"y":0}},    -1..1   whole range
   "curves": {"master": [[0,0],[0.5,0.55],[1,1]], "r": [...], "g": [...], "b": [...]},   points x,y in 0..1
   "hsl": [{"hue": 30, "range": 40, "softness": 20, "sat": 0.2, "lum": 0.0, "hue_shift": 0}],  secondaries
   "match": {"src": {"mean":[L,a,b], "std":[L,a,b]}, "ref": {...}, "amount": 1.0},   from POST …/color/match
   "amount": 1.0}
Order: match → wheels → curves → HSL → amount mix. Everything neutral = no filter at all.
Cost: one lut3d (tetrahedral) ≈ 2–4 ms per 1080p frame on one core.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

LUT_SIZE = 33
WHEELS = ("lift", "gamma", "gain", "offset")
CH = ("r", "g", "b")


# ----------------------------------------------------------------- validation
def clean(c) -> dict | None:
    if not isinstance(c, dict) or c.get("enabled") is False:
        return None
    out: dict = {}
    wh = {}
    for k in WHEELS:
        src = (c.get("wheels") or {}).get(k) or {}
        if isinstance(src, (list, tuple)):
            src = dict(zip(("r", "g", "b", "y"), src))
        vals = {ch: max(-1.0, min(1.0, _f(src.get(ch), 0.0))) for ch in ("r", "g", "b", "y")}
        if any(abs(v) > 1e-4 for v in vals.values()):
            wh[k] = vals
    if wh:
        out["wheels"] = wh
    cv = {}
    for k in ("master", *CH):
        pts = (c.get("curves") or {}).get(k)
        if isinstance(pts, list):
            pp = sorted((max(0.0, min(1.0, _f(p[0], 0))), max(0.0, min(1.0, _f(p[1], 0))))
                        for p in pts if isinstance(p, (list, tuple)) and len(p) >= 2)
            if len(pp) >= 2 and any(abs(x - y) > 1e-4 for x, y in pp):
                cv[k] = pp[:16]
    if cv:
        out["curves"] = cv
    hsl = []
    for s in (c.get("hsl") or [])[:8]:
        if not isinstance(s, dict):
            continue
        item = {"hue": _f(s.get("hue"), 0.0) % 360, "range": max(1.0, min(360.0, _f(s.get("range"), 40.0))),
                "softness": max(0.0, min(180.0, _f(s.get("softness"), 20.0))),
                "sat": max(-1.0, min(1.0, _f(s.get("sat"), 0.0))), "lum": max(-1.0, min(1.0, _f(s.get("lum"), 0.0))),
                "hue_shift": max(-180.0, min(180.0, _f(s.get("hue_shift"), 0.0)))}
        if abs(item["sat"]) > 1e-4 or abs(item["lum"]) > 1e-4 or abs(item["hue_shift"]) > 1e-3:
            hsl.append(item)
    if hsl:
        out["hsl"] = hsl
    m = c.get("match")
    if isinstance(m, dict) and isinstance(m.get("src"), dict) and isinstance(m.get("ref"), dict):
        try:
            mm = {k: {"mean": [float(x) for x in m[k]["mean"]][:3], "std": [max(1e-3, float(x)) for x in m[k]["std"]][:3]}
                  for k in ("src", "ref")}
            mm["amount"] = max(0.0, min(1.0, _f(m.get("amount"), 1.0)))
            if mm["amount"] > 0:
                out["match"] = mm
        except (KeyError, TypeError, ValueError, IndexError):
            pass
    if not out:
        return None
    out["amount"] = max(0.0, min(1.0, _f(c.get("amount"), 1.0)))
    return out if out["amount"] > 0 else None


def _f(v, d: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


# ----------------------------------------------------------------- colour maths
def _srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _lin_to_srgb(c):
    c = np.clip(c, 0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


_M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
_MI = np.linalg.inv(_M)
_WP = np.array([0.95047, 1.0, 1.08883])


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    xyz = _srgb_to_lin(rgb) @ _M.T / _WP
    d = 6 / 29
    f = np.where(xyz > d ** 3, np.cbrt(xyz), xyz / (3 * d * d) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    fy = (lab[..., 0] + 16) / 116
    fx, fz = fy + lab[..., 1] / 500, fy - lab[..., 2] / 200
    d = 6 / 29

    def inv(f):
        return np.where(f > d, f ** 3, 3 * d * d * (f - 4 / 29))
    xyz = np.stack([inv(fx), inv(fy), inv(fz)], -1) * _WP
    return _lin_to_srgb(xyz @ _MI.T)


def _rgb_to_hsl(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    l = (mx + mn) / 2
    d = mx - mn
    s = np.where(d < 1e-6, 0, d / np.maximum(1e-6, 1 - np.abs(2 * l - 1)))
    h = np.zeros_like(l)
    dd = np.maximum(d, 1e-6)
    h = np.where(mx == r, ((g - b) / dd) % 6, h)
    h = np.where(mx == g, (b - r) / dd + 2, h)
    h = np.where(mx == b, (r - g) / dd + 4, h)
    h = np.where(d < 1e-6, 0, h) * 60
    return h % 360, np.clip(s, 0, 1), l


def _hsl_to_rgb(h, s, l):
    c = (1 - np.abs(2 * l - 1)) * s
    hp = (h % 360) / 60
    x = c * (1 - np.abs(hp % 2 - 1))
    z = np.zeros_like(h)
    conds = [(hp < 1), (hp < 2), (hp < 3), (hp < 4), (hp < 5), (hp >= 5)]
    rgbs = [(c, x, z), (x, c, z), (z, c, x), (z, x, c), (x, z, c), (c, z, x)]
    r = np.select(conds, [v[0] for v in rgbs]); g = np.select(conds, [v[1] for v in rgbs]); b = np.select(conds, [v[2] for v in rgbs])
    m = l - c / 2
    return np.stack([r + m, g + m, b + m], -1)


def _pchip(xs, ys, x):
    """Monotone cubic (Fritsch–Carlson) through the curve points."""
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    if xs[0] > 0:
        xs, ys = np.r_[0.0, xs], np.r_[ys[0], ys]
    if xs[-1] < 1:
        xs, ys = np.r_[xs, 1.0], np.r_[ys, ys[-1]]
    h = np.diff(xs); h[h == 0] = 1e-6
    dlt = np.diff(ys) / h
    m = np.zeros_like(ys)
    m[1:-1] = np.where(dlt[:-1] * dlt[1:] > 0, 2 / (1 / np.where(dlt[:-1] == 0, 1e-9, dlt[:-1]) + 1 / np.where(dlt[1:] == 0, 1e-9, dlt[1:])), 0)
    m[0], m[-1] = dlt[0], dlt[-1]
    i = np.clip(np.searchsorted(xs, x) - 1, 0, len(xs) - 2)
    t = (x - xs[i]) / h[i]
    h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
    return h00 * ys[i] + h10 * h[i] * m[i] + h01 * ys[i + 1] + h11 * h[i] * m[i + 1]


def transform(rgb: np.ndarray, c: dict) -> np.ndarray:
    """Apply a cleaned colour spec to RGB values in 0..1 (any shape …×3)."""
    src = rgb.astype(np.float64)
    out = src.copy()
    m = c.get("match")
    if m:
        lab = rgb_to_lab(out)
        sm, ss = np.array(m["src"]["mean"]), np.array(m["src"]["std"])
        rm, rs = np.array(m["ref"]["mean"]), np.array(m["ref"]["std"])
        lab2 = (lab - sm) / ss * rs + rm
        out = out + (np.clip(lab_to_rgb(lab2), 0, 1) - out) * m["amount"]
    wh = c.get("wheels")
    if wh:
        def val(k, i):
            w = wh.get(k) or {}
            return w.get(CH[i], 0.0) + w.get("y", 0.0)
        for i in range(3):
            x = out[..., i]
            lift, gain = val("lift", i) * 0.25, 1 + val("gain", i) * 0.5
            gamma = max(0.2, 1 + val("gamma", i) * 0.6)
            x = gain * (x + lift * (1 - x))
            x = np.power(np.clip(x, 0, None), 1 / gamma)
            out[..., i] = x + val("offset", i) * 0.25
    cv = c.get("curves")
    if cv:
        if cv.get("master"):
            xs, ys = zip(*cv["master"])
            out = _pchip(xs, ys, np.clip(out, 0, 1))
        for i, ch in enumerate(CH):
            if cv.get(ch):
                xs, ys = zip(*cv[ch])
                out[..., i] = _pchip(xs, ys, np.clip(out[..., i], 0, 1))
    for s in c.get("hsl") or []:
        out = np.clip(out, 0, 1)
        h, sat, lum = _rgb_to_hsl(out)
        dh = np.abs((h - s["hue"] + 180) % 360 - 180)
        half, soft = s["range"] / 2, max(1e-3, s["softness"])
        w = np.clip(1 - (dh - half) / soft, 0, 1)
        w = w * w * (3 - 2 * w)
        w = w * np.clip((sat - 0.04) / 0.16, 0, 1)  # greys / near-neutral skin of other hues stay untouched
        h2 = h + s["hue_shift"] * w
        sat2 = np.clip(sat * (1 + s["sat"] * w), 0, 1)
        lum2 = np.clip(lum + s["lum"] * 0.35 * w * (1 - np.abs(2 * lum - 1)), 0, 1)
        out = _hsl_to_rgb(h2, sat2, lum2)
    out = src + (out - src) * c.get("amount", 1.0)
    return np.clip(out, 0, 1)


def write_cube(c: dict, path: Path, size: int = LUT_SIZE) -> Path:
    g = np.linspace(0, 1, size)
    b, gg, r = np.meshgrid(g, g, g, indexing="ij")          # red varies fastest in .cube order
    rgb = np.stack([r, gg, b], -1).reshape(-1, 3)
    out = transform(rgb, c)
    lines = ["TITLE \"vividora\"", f"LUT_3D_SIZE {size}", "DOMAIN_MIN 0 0 0", "DOMAIN_MAX 1 1 1"]
    lines += [f"{x:.6f} {y:.6f} {z:.6f}" for x, y, z in out]
    path.write_text("\n".join(lines) + "\n")
    return path


def lut_filter(c, work: Path, name: str = "color") -> str:
    """ffmpeg filter for a colour spec ("" when neutral / missing). The LUT is cached by content."""
    from .ffmpeg import escape_filter_path
    cc = clean(c)
    if not cc:
        return ""
    work.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(json.dumps(cc, sort_keys=True).encode()).hexdigest()[:12]
    p = work / f"{name}_{key}.cube"
    if not p.exists():
        write_cube(cc, p)
    return f"lut3d=file='{escape_filter_path(p)}':interp=tetrahedral"


# ----------------------------------------------------------------- colour match
def frame_rgb(path: Path, t: float = 0.0, width: int = 256) -> np.ndarray:
    """One frame (or an image) as float RGB 0..1, width px wide."""
    info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                           "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip().split(",")
    sw, sh = int(info[0]), int(info[1])
    h = max(2, int(round(sh * width / sw / 2)) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(path), "-frames:v", "1",
                          "-vf", f"scale={width}:{h}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    if len(raw) < width * h * 3:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1", "-vf", f"scale={width}:{h}",
                              "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True).stdout
    return np.frombuffer(raw[:width * h * 3], np.uint8).reshape(h, width, 3) / 255.0


def lab_stats(rgb: np.ndarray) -> dict:
    lab = rgb_to_lab(rgb.reshape(-1, 3))
    # ignore only fully blown highlights (they carry no colour); real blacks are part of the look
    keep = lab[:, 0] < 99.5
    if keep.sum() > 64:
        lab = lab[keep]
    return {"mean": [round(float(x), 3) for x in lab.mean(0)], "std": [round(float(max(x, 0.5)), 3) for x in lab.std(0)]}


def match(src_rgb: np.ndarray, ref_rgb: np.ndarray, amount: float = 1.0, keep_luma: bool = False) -> dict:
    """Reinhard-style transfer params (Lab mean/std per channel) that make src look like ref."""
    s, r = lab_stats(src_rgb), lab_stats(ref_rgb)
    # damp extreme contrast changes — a dark reference must not crush a bright clip
    for i in range(3):
        k = r["std"][i] / s["std"][i]
        r["std"][i] = round(s["std"][i] * max(0.5, min(2.0, k)), 3)
    if keep_luma:
        r["mean"][0], r["std"][0] = s["mean"][0], s["std"][0]
    return {"match": {"src": s, "ref": r, "amount": max(0.0, min(1.0, amount))}}
