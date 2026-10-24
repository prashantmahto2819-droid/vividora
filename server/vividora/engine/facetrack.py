"""Where is the face? Sampled face detection → smooth horizontal pan for 9:16 crops.

Runs during `prepare` on the 720p proxy. Uses OpenCV's Haar cascade (ships with
opencv-python-headless, no model download). If OpenCV is missing the result is
empty and renders fall back to a fixed focus point.

Output: [[t, cx], ...] with cx in 0..1 (centre of the subject, source time),
already smoothed with a dead zone so the crop window only moves when the
person really moves — a reframing that drifts every frame looks seasick.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

SAMPLE_W = 320


def _detector():
    try:
        import cv2  # noqa: WPS433
    except ImportError:
        return None, None
    path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    if not path.exists():
        return None, None
    return cv2, cv2.CascadeClassifier(str(path))


def track(video: Path, duration: float, width: int, height: int, *, step: float = 0.33,
          dead_zone: float = 0.06, max_seconds: float = 3600) -> list[list[float]]:
    cv2, det = _detector()
    if det is None or duration <= 0:
        return []
    import numpy as np
    sw = SAMPLE_W
    sh = max(2, int(round(height * sw / width / 2)) * 2)
    fps = 1.0 / step
    cmd = ["ffmpeg", "-v", "error", "-i", str(video), "-t", f"{min(duration, max_seconds):.2f}",
           "-vf", f"fps={fps:.4f},scale={sw}:{sh}", "-pix_fmt", "gray", "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    from . import ffmpeg as _ff
    _ff.track(proc)
    raw: list[tuple[float, float | None]] = []
    n = 0
    frame_bytes = sw * sh
    assert proc.stdout is not None
    while True:
        _ff.check_cancel()
        buf = proc.stdout.read(frame_bytes)
        if len(buf) < frame_bytes:
            break
        frame = np.frombuffer(buf, dtype=np.uint8).reshape(sh, sw)
        faces = det.detectMultiScale(frame, scaleFactor=1.15, minNeighbors=4, minSize=(24, 24))
        t = n * step
        if len(faces):
            # biggest face wins (the speaker); ignore tiny background faces
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            raw.append((t, (x + w / 2) / sw))
        else:
            raw.append((t, None))
        n += 1
    proc.wait()
    return _smooth(raw, dead_zone)


def _smooth(raw: list[tuple[float, float | None]], dead_zone: float) -> list[list[float]]:
    """Hold the last known centre through misses; move only past the dead zone,
    then ease. Returns keyframes (dropping repeats to keep the JSON small)."""
    if not raw or all(c is None for _, c in raw):
        return []
    # fill gaps with the nearest detection
    cs = [c for _, c in raw]
    last = next(c for c in cs if c is not None)
    filled = []
    for c in cs:
        if c is not None:
            last = c
        filled.append(last)
    # median over a short window kills single-frame jitter
    win = 3
    med = [sorted(filled[max(0, i - win):i + win + 1])[len(filled[max(0, i - win):i + win + 1]) // 2]
           for i in range(len(filled))]
    out: list[list[float]] = []
    target = med[0]
    cur = target
    for i, (t, _) in enumerate(raw):
        if abs(med[i] - target) > dead_zone:
            target = med[i]
        cur += (target - cur) * 0.35  # ease toward the target
        cur = max(0.0, min(1.0, cur))
        if not out or abs(out[-1][1] - cur) > 0.004:
            out.append([round(t, 2), round(cur, 4)])
    return out


def crop_commands(keyframes: list[list[float]], scaled_w: int, crop_w: int, to_out_time=None,
                  fallback_x: float = 0.5) -> str:
    """ffmpeg sendcmd script moving crop@face along the smoothed path.
    `to_out_time(src_t)` maps source time to output time (None = dropped)."""
    span = max(0, scaled_w - crop_w)
    lines = [f"0.0 crop@face x {int(span * fallback_x)};"]
    last_x = None
    for t, cx in keyframes:
        ot = to_out_time(t) if to_out_time else t
        if ot is None:
            continue
        x = int(max(0, min(span, cx * scaled_w - crop_w / 2)))
        if x == last_x:
            continue
        lines.append(f"{ot:.3f} crop@face x {x};")
        last_x = x
    return "\n".join(lines) + "\n"
