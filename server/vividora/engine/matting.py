"""Person cutout for moving video: Robust Video Matting (mobilenetv3, ONNX) → a
grayscale alpha video, cached per project (job "matte", the main video's 720p
proxy) or per library item (job "matte_lib", B-roll / overlay clips). Every body
effect (background swap, stroke, glow, blink, drop-in…) and every "सिर्फ़ इंसान"
overlay reuses it; the editor plays it live next to the picture (WebGL).

LICENCE — the RVM weights (rvm_mobilenetv3_fp32.onnx, ~15 MB) are GPL-3.0
(github.com/PeterL1n/RobustVideoMatting). They are NOT part of this repository:
model_path() downloads them once at runtime into MODELS_DIR. Keep it that way —
do not vendor the .onnx file into the repo or the Docker image.

How a frame is processed (CPU only):
  decode (ffmpeg, scaled to the MATTE size) → RVM with the recurrent state of the
  previous frame → alpha at matte size → (guided upsample to the OUTPUT size when the
  matte was computed smaller) → light temporal stabilising → encode.

Quality knobs (plan()):
  quality "fast" | "balanced" (default) | "hair"
    matte short side   512 | 720 | 1080 (never more than the source)
    RVM inner size     long side ≈ 256 | 320 | 448 px  → downsample_ratio = that / long side
  RVM's own refiner (deep guided filter) brings the coarse result back to the matte
  size, so hair detail comes from a bigger *matte* size; the inner size decides how well
  the body shape is understood — and almost all of the CPU time (measured: inner 320 ≈
  half the cost of inner 448 at the same 720p matte size). The RVM authors recommend an
  inner size of 256–512 px.

Temporal stability: the four recurrent states are carried frame to frame and reset
to zero at hard scene changes (thumbnail difference) and at the joins of merged
clips (`resets`), so the previous shot's person never "ghosts" into the next one.
Static stretches (identical frames) reuse the last alpha instead of running RVM.

Alpha storage — H.264 yuv420p, CRF 16, short GOP (fast seeking for the live preview):
  * plays in every browser (the editor composites it live) and decodes fast in ffmpeg;
  * masks are mostly flat → ~0.5–2 MB per minute at 720p; max error ≈ ±2/255 on edges;
  * ffv1 / PNG would be lossless but 10–40× larger and not playable by <video>, so
    the editor could not preview with it; gray-only H.264 (High 4:0:0) is rejected by
    several browser decoders. Stored as limited range: Y = 16 + 219·alpha, chroma 128 — the
    render reads the Y plane as is (extractplanes=y, no swscale range guessing) and stretches it
    back (effects.ALPHA_RANGE); browsers expand limited range by themselves.

Speed (see docs in the final report): ~60–120 ms per 720p frame on one modern
core-pair with "balanced"; "fast" roughly halves that. ETA is reported in the job
progress message.
"""

from __future__ import annotations

import os
import subprocess
import time
import urllib.request
from pathlib import Path

import numpy as np

from . import ffmpeg

MODEL_URL = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx"
MODEL_NAME = "rvm_mobilenetv3_fp32.onnx"  # GPL-3.0 weights, downloaded at runtime (never vendored)

QUALITY = {
    # matte short side cap, RVM inner long side
    "fast": (512, 256),
    "balanced": (720, 320),
    "hair": (1080, 448),
}
SCENE_CUT = 28.0      # mean abs diff (0..255) of 64×36 gray thumbnails → hard cut → reset states
STATIC = 0.35         # below this the frame is treated as identical → reuse the last alpha
MAX_STATIC_RUN = 30   # …but run RVM at least once a second anyway


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
    if os.getenv("VIVIDORA_MATTE_MOCK"):
        return True
    try:
        import onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


def _even(v: float) -> int:
    return max(2, int(round(v / 2)) * 2)


def plan(width: int, height: int, quality: str = "balanced", out_short: int | None = None) -> dict:
    """Sizes for one clip. out = size of the stored alpha (main video: the proxy size;
    library clip: ≤ 720 short side); matte = size RVM runs at (≤ out)."""
    cap, inner = QUALITY.get(quality or "balanced", QUALITY["balanced"])
    w, h = max(2, int(width)), max(2, int(height))
    short = min(w, h)
    k_out = min(1.0, (out_short or short) / short)
    ow, oh = _even(w * k_out), _even(h * k_out)
    k_m = min(1.0, cap / min(ow, oh))
    mw, mh = _even(ow * k_m), _even(oh * k_m)
    dsr = max(0.1, min(1.0, inner / max(mw, mh)))
    return {"out": (ow, oh), "matte": (mw, mh), "downsample": round(dsr, 4), "quality": quality or "balanced"}


def threads() -> int:
    env = os.getenv("MATTE_THREADS")
    if env:
        return max(1, int(env))
    n = os.cpu_count() or 4
    # ffmpeg decode/encode are light next to RVM; leave one core free on big machines
    return max(1, min(8, n - 1 if n > 4 else n))


class _MockSession:
    """Stand-in for RVM in tests (VIVIDORA_MATTE_MOCK=1): 'person' = pixels that differ from
    the frame's median colour (works for a subject on a plain / moving background)."""

    def run(self, _names, feeds):
        src = feeds["src"][0]                      # 3×h×w float
        med = np.median(src.reshape(3, -1), axis=1)[:, None, None]
        d = np.abs(src - med).sum(axis=0)
        pha = np.clip((d - 0.25) * 4, 0, 1)[None, None].astype(np.float32)
        z = np.zeros([1, 1, 1, 1], np.float32)
        return [None, pha, z, z, z, z]


def session(n_threads: int | None = None):
    if os.getenv("VIVIDORA_MATTE_MOCK"):
        return _MockSession()
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = n_threads or threads()
    so.inter_op_num_threads = 1
    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(model_path()), so, providers=["CPUExecutionProvider"])


def _box(x: np.ndarray, r: int) -> np.ndarray:
    import cv2
    return cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1), borderType=cv2.BORDER_REFLECT)


def guided_upsample(alpha_lr: np.ndarray, guide_hr: np.ndarray, r: int = 2, eps: float = 1e-3) -> np.ndarray:
    """Fast guided filter (He & Sun 2015): fit alpha ≈ a·I + b on the small picture, upsample a, b
    and apply them to the full-size gray picture → edges follow the real image, not the blur of a
    plain resize. alpha_lr float32 0..1 (h×w); guide_hr float32 0..1 gray (H×W)."""
    import cv2
    H, W = guide_hr.shape
    # the linear model is fitted at half the matte size (the "fast" in fast guided filter):
    # ~4× fewer box-filter pixels, edges still come from the full-size guide
    h, w = max(8, alpha_lr.shape[0] // 2), max(8, alpha_lr.shape[1] // 2)
    p = cv2.resize(alpha_lr, (w, h), interpolation=cv2.INTER_AREA)
    I = cv2.resize(guide_hr, (w, h), interpolation=cv2.INTER_AREA)
    mI, mp = _box(I, r), _box(p, r)
    cov = _box(cv2.multiply(I, p), r) - cv2.multiply(mI, mp)
    var = _box(cv2.multiply(I, I), r) - cv2.multiply(mI, mI)
    a = cv2.divide(cov, var + eps)
    b = mp - cv2.multiply(a, mI)
    A = cv2.resize(_box(a, r), (W, H), interpolation=cv2.INTER_LINEAR)
    B = cv2.resize(_box(b, r), (W, H), interpolation=cv2.INTER_LINEAR)
    q = cv2.add(cv2.multiply(A, guide_hr), B)
    return cv2.min(cv2.max(q, 0.0), 1.0)


def _thumb(rgb: np.ndarray) -> np.ndarray:
    import cv2
    g = rgb[..., 1] if rgb.ndim == 3 else rgb
    return cv2.resize(g, (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32)


def _fmt_eta(s: float) -> str:
    s = max(0, int(s))
    return f"{s // 60}:{s % 60:02d}"


def matte(video: Path, out: Path, *, width: int, height: int, fps: float, duration: float,
          quality: str = "balanced", out_size: tuple[int, int] | None = None, downsample: float | None = None,
          resets: list[float] | None = None, stabilize: bool = True, n_threads: int | None = None,
          on_progress=None, crf: int = 16) -> dict:
    """Write a gray alpha video of `video` to `out` (same fps; size = out_size or the source size)."""
    ow, oh = out_size or (_even(width), _even(height))
    pl = plan(ow, oh, quality)
    mw, mh = pl["matte"]
    dsr = np.array([float(downsample or pl["downsample"])], np.float32)
    sess = session(n_threads)
    upsample = (mw, mh) != (ow, oh)
    fps = float(fps or 30.0)
    dec_w, dec_h = (ow, oh) if upsample else (mw, mh)   # decode at the output size; RVM input is resized
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-an", "-vf",
                            f"fps={fps:.4f},scale={dec_w}:{dec_h}:flags=bicubic", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10 ** 7)
    gop = max(6, int(round(fps / 2)))
    # frames go in as yuv420p with Y = 16 + 219·alpha and neutral chroma: no colour conversion anywhere,
    # so the stored range is exactly "limited" (browsers expand it; the render reads Y with extractplanes)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-color_range", "tv",
                            "-s", f"{ow}x{oh}", "-r", f"{fps:.4f}", "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
                            "-crf", str(crf), "-g", str(gop), "-bf", "0", "-pix_fmt", "yuv420p", "-color_range", "tv",
                            "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    chroma = bytes([128]) * ((ow // 2) * (oh // 2) * 2)
    import cv2
    zero = np.zeros([1, 1, 1, 1], np.float32)
    rec = [zero] * 4
    reset_frames = sorted({int(round(t * fps)) for t in (resets or []) if t > 0})
    frame_bytes = dec_w * dec_h * 3
    total = max(1, int(round(duration * fps)))
    n = skipped = n_resets = 0
    run_ms: list[float] = []
    cpu0, t0, last_report = time.process_time(), time.time(), 0.0
    prev_thumb = prev_a = None
    static_run = 0
    assert dec.stdout is not None and enc.stdin is not None
    try:
        while True:
            buf = dec.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            rgb = np.frombuffer(buf, np.uint8).reshape(dec_h, dec_w, 3)
            th = _thumb(rgb)
            diff = float(np.abs(th - prev_thumb).mean()) if prev_thumb is not None else 255.0
            prev_thumb = th
            cut = (n in reset_frames) or (n > 0 and diff > SCENE_CUT)
            if cut:
                rec = [zero] * 4
                n_resets += 1
            if prev_a is not None and not cut and diff < STATIC and static_run < MAX_STATIC_RUN:
                a = prev_a
                skipped += 1
                static_run += 1
            else:
                static_run = 0
                small = cv2.resize(rgb, (mw, mh), interpolation=cv2.INTER_AREA) if upsample else rgb
                src = small.transpose(2, 0, 1)[None].astype(np.float32) * (1.0 / 255.0)
                t1 = time.time()
                _fgr, pha, *rec = sess.run(None, {"src": src, "r1i": rec[0], "r2i": rec[1], "r3i": rec[2], "r4i": rec[3],
                                                  "downsample_ratio": dsr})
                run_ms.append((time.time() - t1) * 1000)
                a = np.clip(pha[0, 0], 0, 1).astype(np.float32)
                if upsample:
                    guide = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) * (1.0 / 255.0)
                    a = guided_upsample(a, guide)
                if stabilize and prev_a is not None and not cut:
                    # damp edge flicker where the matte barely changed; real motion (big change) passes through
                    d = np.abs(a - prev_a)
                    a = np.where(d < 0.12, 0.6 * a + 0.4 * prev_a, a)
            prev_a = a
            enc.stdin.write((a * 219.0 + 16.5).astype(np.uint8).tobytes())
            enc.stdin.write(chroma)
            n += 1
            now = time.time()
            if on_progress and (now - last_report > 1.0 or n == total):
                last_report = now
                per = (now - t0) / n
                left = max(0, total - n) * per
                on_progress(min(0.99, n / total),
                            f"cutout {n}/{total} · {per * 1000:.0f} ms/frame · ~{_fmt_eta(left)} बाकी")
    finally:
        enc.stdin.close()
        dec.stdout.close()
        dec.wait()
        err = enc.stderr.read().decode(errors="ignore") if enc.stderr else ""
        enc.wait()
    if enc.returncode != 0 or not out.exists() or n == 0:
        raise ffmpeg.FFmpegError(f"alpha encode failed: {err[-300:]}")
    wall = time.time() - t0
    return {"frames": n, "width": ow, "height": oh, "fps": fps, "matte_w": mw, "matte_h": mh,
            "downsample": float(dsr[0]), "quality": pl["quality"], "skipped": skipped, "resets": n_resets,
            "ms_per_frame": round(wall * 1000 / n, 1),
            "rvm_ms": round(sum(run_ms) / max(1, len(run_ms)), 1),
            "cpu_ms_per_frame": round((time.process_time() - cpu0) * 1000 / n, 1),
            "threads": n_threads or threads(), "seconds": round(wall, 1),
            "codec": f"h264 yuv420p crf{crf}", "bytes": out.stat().st_size}
