"""Generic keyframes → ffmpeg expressions, sendcmd scripts and stepped filter chains.

Model (JSON):  {param: [{"t": seconds, "v": number, "ease": "linear|in|out|inout|hold"}, ...]}
  * t is relative to the start of the thing that owns the keyframes (an overlay clip's own
    start, an effect clip's start; the main video uses the output timeline).
  * `ease` describes the curve FROM this keyframe TO the next one.
  * Before the first keyframe the first value holds, after the last the last value holds.
  * A plain number instead of a list = constant (no animation, zero cost).

Three ways to animate, cheapest first:
  expr()        piecewise eased expression for filters that evaluate per frame
                (overlay x/y, scale w/h with eval=frame, rotate a, crop x/y, geq, setpts …).
                Built as a flat SUM of clipped ramps (no nested if()) so long lists stay fast.
  sendcmd()     a command script for filters that support runtime commands but not
                expressions (colorchannelmixer aa = opacity, …).
  stepped()     any filter chain: the clip is cut into short chunks (default 1/8 s), each chunk
                rendered with the value at its middle, concatenated again. Works for every
                catalog effect / grade parameter. Cost ≈ the filter itself (+ a few labels).
"""

from __future__ import annotations

import math
from typing import Any, Callable

EASES = {
    "linear": "Linear",
    "in": "Ease in (धीरे शुरू)",
    "out": "Ease out (धीरे रुके)",
    "inout": "Ease in-out (smooth)",
    "hold": "Hold (एक दम बदले)",
}
MAX_POINTS = 120


def normalize(points: Any, default: float | None = None, lo: float | None = None, hi: float | None = None) -> list[dict]:
    """Accept [{t,v,ease}] / [[t,v(,ease)]] / a number → sorted clean list (may be empty)."""
    if points is None or points == "":
        return [] if default is None else [{"t": 0.0, "v": float(default), "ease": "linear"}]
    if isinstance(points, (int, float)):
        return [{"t": 0.0, "v": _clamp(float(points), lo, hi), "ease": "linear"}]
    out: list[dict] = []
    for p in points if isinstance(points, list) else []:
        try:
            if isinstance(p, dict):
                t, v, ease = float(p.get("t", 0)), float(p.get("v")), str(p.get("ease") or "linear")
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                t, v, ease = float(p[0]), float(p[1]), str(p[2]) if len(p) > 2 else "linear"
            else:
                continue
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(t) and math.isfinite(v)):
            continue
        out.append({"t": max(0.0, round(t, 4)), "v": _clamp(v, lo, hi), "ease": ease if ease in EASES else "linear"})
    out.sort(key=lambda p: p["t"])
    dedup: list[dict] = []
    for p in out:
        if dedup and abs(dedup[-1]["t"] - p["t"]) < 1e-4:
            dedup[-1] = p
        else:
            dedup.append(p)
    return dedup[:MAX_POINTS]


def _clamp(v: float, lo: float | None, hi: float | None) -> float:
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def animated(points: list[dict]) -> bool:
    return len(points) >= 2 and any(abs(p["v"] - points[0]["v"]) > 1e-9 for p in points)


def _ease_expr(u: str, ease: str) -> str:
    if ease == "in":
        return f"pow({u},3)"
    if ease == "out":
        return f"(1-pow(1-{u},3))"
    if ease == "inout":
        return f"({u}*{u}*(3-2*{u}))"
    if ease == "hold":
        return f"gte({u},1)"
    return u


def _ease_py(u: float, ease: str) -> float:
    if ease == "in":
        return u ** 3
    if ease == "out":
        return 1 - (1 - u) ** 3
    if ease == "inout":
        return u * u * (3 - 2 * u)
    if ease == "hold":
        return 1.0 if u >= 1 else 0.0
    return u


def expr(points: list[dict], var: str = "t", offset: float = 0.0, scale: float = 1.0, add: float = 0.0) -> str:
    """value(var) as an ffmpeg expression (commas NOT escaped; see q()). The keyframe times are
    shifted by `offset` (e.g. clip start when the filter sees the output timeline); the value is
    mapped as v*scale+add."""
    if not points:
        return f"{add:.6g}"
    v0 = points[0]["v"] * scale + add
    terms = [f"{v0:.6g}"]
    for a, b in zip(points, points[1:]):
        dv = (b["v"] - a["v"]) * scale
        if abs(dv) < 1e-12:
            continue
        t0, d = a["t"] + offset, max(1e-4, b["t"] - a["t"])
        u = f"clip(({var}-{t0:.4f})/{d:.4f},0,1)"
        terms.append(f"{dv:+.6g}*{_ease_expr(u, a['ease'])}")
    return "(" + "".join(terms) + ")"


def q(e: str) -> str:
    """Quote an expression for a filtergraph option: commas escaped + single quotes."""
    return "'" + e.replace(",", "\\,") + "'"


def sample(points: list[dict], t: float, default: float = 0.0) -> float:
    if not points:
        return default
    v = points[0]["v"]
    for a, b in zip(points, points[1:]):
        d = max(1e-4, b["t"] - a["t"])
        u = min(1.0, max(0.0, (t - a["t"]) / d))
        v += (b["v"] - a["v"]) * _ease_py(u, a.get("ease", "linear"))
    return v


def sendcmd(target: str, option: str, points: list[dict], dur: float, fps: float,
            fmt: Callable[[float], str] | None = None, every: int = 1) -> str:
    """Command script: one line per `every` frames while the value changes (static parts skipped)."""
    fmt = fmt or (lambda x: f"{x:.4f}")
    lines, last = [], None
    n = max(1, int(math.ceil(dur * fps)))
    for i in range(0, n + 1, max(1, every)):
        t = i / fps
        val = fmt(sample(points, t))
        if val != last:
            lines.append(f"{t:.4f} {target} {option} {val};")
            last = val
    return "\n".join(lines) + "\n"


def stepped(in_label: str, out_label: str, dur: float, fps: float, build: Callable[[float], str], *,
            uid: str, step: float = 0.125, max_chunks: int = 64) -> str:
    """Run `build(t_mid)` (a comma chain WITHOUT labels, or a subgraph whose labels are made unique
    here) on consecutive chunks of the stream → concat. Times inside each chunk stay on the
    stream's own clock, so time-based effects do not restart per chunk."""
    import re
    dur = max(1.0 / fps, dur)
    step = max(2.0 / fps, step, dur / max_chunks)
    n = max(1, int(math.ceil(dur / step - 1e-6)))
    if n == 1:
        return f"{in_label}{build(dur / 2)}{out_label}"
    outs = "".join(f"[{uid}k{i}]" for i in range(n))
    parts = [f"{in_label}split={n}{outs}"]
    for i in range(n):
        a, b = i * step, min(dur, (i + 1) * step) if i < n - 1 else dur + 10
        chain = re.sub(r"\[([A-Za-z]\w*)\]", lambda m: f"[{m.group(1)}_{uid}{i}]", build(min(dur, (a + min(b, dur)) / 2)))
        parts.append(f"[{uid}k{i}]trim=start={a:.4f}:end={b:.4f},{chain},setpts=PTS-STARTPTS[{uid}c{i}]")
    parts.append("".join(f"[{uid}c{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,setpts=PTS-STARTPTS{out_label}")
    return ";".join(parts)


def params_at(base: dict, kf: dict[str, list[dict]] | None, t: float) -> dict:
    """Numeric params with keyframes evaluated at time t."""
    out = dict(base or {})
    for k, pts in (kf or {}).items():
        if pts:
            out[k] = sample(pts, t)
    return out


def norm_map(kf: Any) -> dict[str, list[dict]]:
    """{param: points} → normalized; drops empties."""
    if not isinstance(kf, dict):
        return {}
    out = {}
    for k, v in kf.items():
        pts = normalize(v)
        if pts:
            out[str(k)] = pts
    return out
