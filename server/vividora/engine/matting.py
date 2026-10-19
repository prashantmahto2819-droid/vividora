"""Person cutout for the whole video: Robust Video Matting (mobilenetv3, ONNX)
on the 720p proxy → a grayscale alpha video cached per project. Every
"body effect" (background swap, stroke, glow, blink, drop-in…) reuses it.

Model (GPL-3.0, ~15 MB) is downloaded once into MODELS_DIR. CPU only;
~60–80 ms per 720p frame on a modern core → a 10-minute video ≈ 20 min.
"""

from __future__ import annotations

import os
import subprocess
import urllib.request
from pathlib import Path

import numpy as np

from . import ffmpeg

MODEL_URL = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx"
MODEL_NAME = "rvm_mobilenetv3_fp32.onnx"


def models_dir() -> Path:
    d = Path(os.getenv("MODELS_DIR") or os.getenv("WHISPER_CACHE") or "./models")
    d.mkdir(parents=True, exist_ok=True)
    return d


def model_path() -> Path:
    p = models_dir() / MODEL_NAME
    if not p.exists():
        tmp = p.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.replace(p)
    return p


def available() -> bool:
    try:
        import onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


def matte(video: Path, out: Path, *, width: int, height: int, fps: float, duration: float,
          downsample: float = 0.375, threads: int | None = None, on_progress=None) -> dict:
    """Write a gray alpha video (same size/fps as `video`) to `out`."""
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = threads or max(1, (os.cpu_count() or 4) - 2)
    sess = ort.InferenceSession(str(model_path()), so, providers=["CPUExecutionProvider"])
    w, h = int(width) // 2 * 2, int(height) // 2 * 2
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"scale={w}:{h}", "-pix_fmt", "rgb24",
                            "-f", "rawvideo", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10 ** 7)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}",
                            "-r", f"{fps:.3f}", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
                            "-pix_fmt", "gray", "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE,
                           stderr=subprocess.DEVNULL)
    rec = [np.zeros([1, 1, 1, 1], np.float32)] * 4
    dsr = np.array([downsample], np.float32)
    frame_bytes = w * h * 3
    n, total = 0, max(1, int(duration * fps))
    assert dec.stdout is not None and enc.stdin is not None
    try:
        while True:
            buf = dec.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            src = np.frombuffer(buf, np.uint8).reshape(1, h, w, 3).transpose(0, 3, 1, 2).astype(np.float32) / 255.0
            fgr, pha, *rec = sess.run(None, {"src": src, "r1i": rec[0], "r2i": rec[1], "r3i": rec[2], "r4i": rec[3],
                                             "downsample_ratio": dsr})
            enc.stdin.write((np.clip(pha[0, 0], 0, 1) * 255).astype(np.uint8).tobytes())
            n += 1
            if on_progress and n % 15 == 0:
                on_progress(min(0.99, n / total), f"cutout {n}/{total}")
    finally:
        enc.stdin.close()
        dec.wait()
        enc.wait()
    if enc.returncode != 0 or not out.exists():
        raise ffmpeg.FFmpegError("alpha encode failed")
    return {"frames": n, "width": w, "height": h, "fps": fps}
