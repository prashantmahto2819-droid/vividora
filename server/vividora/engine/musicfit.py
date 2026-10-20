"""Music remix: fit a song to a target length so it ENDS like the song ends (on a bar / phrase),
instead of being cut off and faded.

How: beats + bar starts from beatcut.music(); the song is cut and re-joined only at bar starts
(phrase = 4 bars preferred), with short equal-power crossfades:
  * longer song   → intro … [jump] … the song's own ending
  * shorter song  → a middle phrase is looped k times
The remaining error (≤ a bar) is absorbed by a tiny tempo change (≤ ±4 %, pitch kept) or, if
that is not enough, by ending on the nearest bar with a short fade.

  plan(path, target)          → {"pieces": [[start, end], …], "crossfade", "tempo", "length", "bpm", …}
  render(path, plan, out)     → audio file
  fit_file(path, target, work) (cached) — what render.py uses when effects.music.fit is true
Cost: one decode for beat analysis (~1–2 s per song minute) + one ffmpeg audio pass.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

CROSSFADE = 0.12
MAX_TEMPO = 0.04


def _bars(mu: dict) -> list[float]:
    beats = mu["beats"]
    b0 = int(mu.get("bar0", 0))
    bars = [float(beats[i]) for i in range(b0, len(beats), 4)]
    if not bars or bars[0] > 0.05:
        bars = [0.0, *bars]
    return bars


def plan(path: Path, target: float, mu: dict | None = None) -> dict:
    from .beatcut import music
    mu = mu or music(Path(path), max_seconds=max(30.0, target))
    D = float(mu["duration"])
    bars = _bars(mu)
    bars = [b for b in bars if b < D - 0.5]
    period = float(mu["period"])
    cf = min(CROSSFADE, period / 2)
    res = {"bpm": mu["bpm"], "duration": round(D, 3), "target": round(target, 3), "crossfade": cf}
    if target <= 0:
        raise ValueError("target must be > 0")
    if abs(D - target) / target <= MAX_TEMPO:
        pieces = [(0.0, D)]
    elif D > target:
        # intro [0, X) + ending [Y, D): X + (D - Y) - cf ≈ target; X, Y on bar starts, prefer whole phrases
        best = None
        for i, x in enumerate(bars):
            if x < min(target * 0.25, 4 * period * 4):
                continue
            if x > target:
                break
            for j, y in enumerate(bars):
                if y <= x + period:
                    continue
                L = x + (D - y) - cf
                err = abs(L - target)
                score = err + (0 if (j - i) % 4 == 0 else period * 0.75) + (0 if i % 4 == 0 else period * 0.4)
                if best is None or score < best[0]:
                    best = (score, x, y)
        pieces = [(0.0, best[1]), (best[2], D)] if best else [(0.0, D)]
    else:
        # loop a middle phrase (4 bars, else 2, else 1) k times
        n = len(bars)
        best = None
        for bl in (16, 8, 4):  # beats per loop section
            nb = bl // 4
            for i in range(max(1, n // 4), max(2, min(n - nb, int(n * 0.75) + 1))):  # a middle phrase, not the outro
                if i + nb >= n:
                    break
                a, b = bars[i], bars[i + nb]
                sec = b - a - cf
                if sec <= period:
                    continue
                k = max(1, round((target - D) / sec))
                L = D + k * sec - cf * 0
                err = abs(L - target)
                score = err + (0 if i % 4 == 0 else period * 0.5)
                if best is None or score < best[0]:
                    best = (score, a, b, k)
            if best and best[0] < period:
                break
        if best:
            _, a, b, k = best
            pieces = [(0.0, b)] + [(a, b)] * (k - 1) + [(a, D)]
        else:
            pieces = [(0.0, D)] * max(1, round(target / D))
    length = sum(e - s for s, e in pieces) - cf * (len(pieces) - 1)
    tempo = length / target
    end_trim = None
    if abs(tempo - 1) > MAX_TEMPO:
        # still off: speed what we can, then end on the last bar start before the target (+ fade)
        tempo = max(1 - MAX_TEMPO, min(1 + MAX_TEMPO, tempo))
        end_trim = target
    res.update(pieces=[[round(s, 3), round(e, 3)] for s, e in pieces], length=round(length, 3),
               tempo=round(tempo, 5), end_trim=end_trim, output_length=round(min(target, length / tempo), 3))
    return res


def render(path: Path, pl: dict, out: Path) -> Path:
    pieces, cf = pl["pieces"], float(pl["crossfade"])
    n = len(pieces)
    # one input per piece (an asplit feeding a chain of acrossfades stalls and drops the tail)
    args: list[str] = []
    fc = []
    for i, (s, e) in enumerate(pieces):
        args += ["-ss", f"{s:.4f}", "-t", f"{e - s:.4f}", "-i", str(path)]
        fc.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS[q{i}]")
    cur = "[q0]"
    for i in range(1, n):
        fc.append(f"{cur}[q{i}]acrossfade=d={cf:.4f}:c1=qsin:c2=qsin[x{i}]")
        cur = f"[x{i}]"
    tail = ""
    t = float(pl.get("tempo", 1))
    if abs(t - 1) > 1e-4:
        tail += f"atempo={t:.5f},"
    if pl.get("end_trim"):
        T = float(pl["end_trim"])
        tail += f"atrim=0:{T:.3f},afade=t=out:st={max(0.0, T - 1.2):.3f}:d=1.2,"
    fc.append(f"{cur}{tail}anull[a]")
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args, "-filter_complex", ";".join(fc), "-map", "[a]",
                        "-c:a", "pcm_s16le", str(out)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("music fit failed: " + r.stderr[-400:])
    return out


def fit_file(path: Path, target: float, work: Path) -> Path:
    key = hashlib.sha1(f"{path}:{path.stat().st_size}:{target:.2f}".encode()).hexdigest()[:12]
    out = work / f"music_fit_{key}.wav"
    if out.exists():
        return out
    try:
        return render(path, plan(path, target), out)
    except Exception:  # noqa: BLE001 — a failed remix must never stop the render: the plain song is used
        return path
