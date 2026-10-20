"""Scene-change detection (ffmpeg's scene score) → times usable as markers or split points.

detect(path, threshold=0.3, start=0, end=None, min_gap=0.6) → [{"t": seconds, "score": 0..1}]
Runs on a 320-px wide decode (use the 720p proxy): ~20–60× realtime on one core.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_PTS = re.compile(r"pts_time:([\d.]+)")
_SCORE = re.compile(r"lavfi\.scene_score=([\d.]+)")


def detect(path: Path, threshold: float = 0.3, start: float = 0.0, end: float | None = None,
           min_gap: float = 0.6, max_scenes: int = 500) -> list[dict]:
    threshold = max(0.02, min(0.95, float(threshold)))
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-v", "info"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path)]
    if end is not None and end > start:
        cmd += ["-t", f"{end - start:.3f}"]
    cmd += ["-an", "-vf", f"scale=320:-2,select='gt(scene\\,{threshold:.3f})',metadata=print:file=-", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    out: list[dict] = []
    t = None
    for line in r.stdout.splitlines():
        m = _PTS.search(line)
        if m:
            t = float(m.group(1)) + start
            continue
        m = _SCORE.search(line)
        if m and t is not None:
            sc = float(m.group(1))
            if out and t - out[-1]["t"] < min_gap:
                if sc > out[-1]["score"]:
                    out[-1] = {"t": round(t, 3), "score": round(sc, 3)}
            else:
                out.append({"t": round(t, 3), "score": round(sc, 3)})
            t = None
    return out[:max_scenes]
