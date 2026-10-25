"""Hardware acceleration detection and FFmpeg tuning for low-end PCs.

Detects VAAPI (AMD/Intel), sets thread limits, and picks encoder presets
based on available system resources.  Tuned for the HP Z440 (12 cores,
64 GB, AMD RX 580 — VAAPI, no CUDA).

Usage:
    from . import hwaccel
    extra = hwaccel.ffmpeg_resource_args(is_heavy=True)
    # → ['-threads', '6', '-thread_queue_size', '512']
    vaapi = hwaccel.vaapi_encode_args("h264")
    # → ['-vaapi_device', '/dev/dri/renderD128', '-c:v', 'h264_vaapi', ...]
"""

from __future__ import annotations

import functools
import logging
import os
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("vividora.hwaccel")

# ---- VAAPI detection --------------------------------------------------------

_VAAPI_DEVICES = ("/dev/dri/renderD128", "/dev/dri/renderD129")

VAAPI_ENCODERS = {
    "h264": "h264_vaapi",
    "h265": "hevc_vaapi",
    "vp9":  "vp9_vaapi",
    "av1":  "av1_vaapi",
}


@functools.lru_cache(maxsize=1)
def vaapi_device() -> str | None:
    """Return the first usable VAAPI render node, or None."""
    for dev in _VAAPI_DEVICES:
        if Path(dev).exists():
            # Verify it actually works with vainfo or ffmpeg
            try:
                r = subprocess.run(
                    ["ffmpeg", "-hide_banner", "-init_hw_device", f"vaapi=va:{dev}",
                     "-f", "lavfi", "-i", "color=black:s=64x64:d=0.1",
                     "-vf", "format=nv12,hwupload",
                     "-c:v", "h264_vaapi", "-frames:v", "1",
                     "-f", "null", "-"],
                    capture_output=True, text=True, timeout=15,
                )
                if r.returncode == 0:
                    log.info("VAAPI available: %s", dev)
                    return dev
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
    log.info("VAAPI not available")
    return None


@functools.lru_cache(maxsize=1)
def vaapi_supported_codecs() -> set[str]:
    """Which of our codecs have working VAAPI encoders."""
    dev = vaapi_device()
    if not dev:
        return set()
    supported = set()
    for codec_id, vaapi_enc in VAAPI_ENCODERS.items():
        try:
            out = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True, text=True, timeout=10,
            ).stdout
            if f" {vaapi_enc} " in out:
                supported.add(codec_id)
        except Exception:  # noqa: BLE001
            pass
    log.info("VAAPI encoders: %s", supported or "none")
    return supported


def vaapi_encode_args(codec_id: str) -> list[str]:
    """Return FFmpeg args to use VAAPI encoding, or empty list if not available.

    The caller still needs to add the hwupload filter to the filter chain.
    For segment rendering where filter chains are complex, we skip VAAPI
    and use software encoding with tuned thread counts instead.
    """
    dev = vaapi_device()
    if not dev or codec_id not in vaapi_supported_codecs():
        return []
    vaapi_enc = VAAPI_ENCODERS[codec_id]
    return ["-vaapi_device", dev, "-c:v", vaapi_enc]


# ---- Thread and memory limits -----------------------------------------------

def _cpu_count() -> int:
    """Usable CPU count, capped by cgroup if in a container."""
    try:
        # cgroup v2
        quota = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if quota[0] != "max":
            period = int(quota[1]) if len(quota) > 1 else 100_000
            return max(1, int(int(quota[0]) / period))
    except (OSError, ValueError, IndexError):
        pass
    try:
        # cgroup v1
        quota = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text().strip())
        period = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text().strip())
        if quota > 0:
            return max(1, quota // period)
    except (OSError, ValueError):
        pass
    return os.cpu_count() or 4


@functools.lru_cache(maxsize=1)
def cpu_count() -> int:
    return _cpu_count()


def ffmpeg_resource_args(is_heavy: bool = False) -> list[str]:
    """Thread and buffer limits to prevent FFmpeg from consuming all RAM.

    Heavy jobs (render, montage) get fewer threads so quick pipeline jobs
    (transcribe, autocut) aren't starved.  Memory-constrained systems also
    get smaller thread queue sizes to prevent input buffer bloat.

    HP Z440 with 12 cores:
    - Heavy: 6 threads (leaves 6 for other work + the Python process)
    - Light: 4 threads (short jobs, no need for all cores)
    """
    cpus = cpu_count()
    env_threads = os.getenv("FFMPEG_THREADS")
    if env_threads:
        threads = max(1, int(env_threads))
    elif is_heavy:
        # Use half the cores for heavy jobs
        threads = max(2, cpus // 2)
    else:
        # Light jobs: fewer threads, finish fast with low footprint
        threads = max(2, min(4, cpus // 3))

    # Thread queue size: limits how many packets FFmpeg buffers per input.
    # Default is 8 packets per thread — we cap it to prevent RAM spikes
    # on multi-input filter chains (music + sfx + broll + main video).
    queue_size = int(os.getenv("FFMPEG_THREAD_QUEUE_SIZE", "512"))

    args = ["-threads", str(threads), "-thread_queue_size", str(queue_size)]

    return args


def x264_thread_args(threads: int | None = None) -> str:
    """x264-params string to limit encoder-internal threads.

    x264 allocates ~8 MB per frame thread; on a 12-core machine the default
    (1.5× cores = 18 threads) uses ~144 MB just for frame buffers.
    Capping at 6 keeps it under 50 MB.
    """
    if threads is None:
        threads = max(2, cpu_count() // 2)
    return f"threads={threads}:lookahead-threads={max(1, threads // 2)}"


def x265_pool_args(threads: int | None = None) -> str:
    """x265-params addition to limit encoder threads."""
    if threads is None:
        threads = max(2, cpu_count() // 2)
    return f"pools={threads}:frame-threads={max(1, threads // 3)}"


# ---- Memory-aware preset selection ------------------------------------------

def smart_preset(requested: str | None, codec: str = "h264") -> str:
    """Pick an encoder preset considering available RAM.

    When memory is tight (sysguard reports < WARN_FREE_GB), use a faster
    preset to reduce peak RAM — faster presets use less memory because they
    skip expensive analysis passes.

    Preset ladder (slowest → fastest, for x264):
    veryslow → slower → slow → medium → fast → faster → veryfast → superfast → ultrafast
    """
    if requested:
        return requested
    # Check memory via sysguard
    try:
        from . import sysguard  # type: ignore[attr-defined]
        mem = sysguard._mem_info()
    except Exception:  # noqa: BLE001
        # sysguard is in the parent package
        try:
            from .. import sysguard
            mem = sysguard._mem_info()
        except Exception:  # noqa: BLE001
            return "medium"

    avail = mem.get("available_gb", 99)

    if avail < 4:
        # Critical: use fastest preset that still looks decent
        log.warning("RAM low (%.1f GB free) — using 'faster' preset", avail)
        return "faster"
    if avail < 8:
        # Tight: use fast preset
        log.info("RAM moderate (%.1f GB free) — using 'fast' preset", avail)
        return "fast"

    # Normal: use medium (the default)
    return "medium"


# ---- Segment size tuning ----------------------------------------------------

def smart_segment_seconds(default: float = 15.0) -> float:
    """Reduce segment duration when RAM is low, so each piece peaks lower.

    A 15s 1080p segment decoded + encoded uses ~800 MB peak.
    A 10s segment uses ~550 MB.
    An 8s segment uses ~450 MB.
    """
    try:
        from .. import sysguard
        mem = sysguard._mem_info()
    except Exception:  # noqa: BLE001
        return default

    avail = mem.get("available_gb", 99)
    env_override = os.getenv("SEG_TARGET_SECONDS")
    if env_override:
        return max(5.0, float(env_override))

    if avail < 4:
        return 8.0
    if avail < 8:
        return 10.0
    return default
