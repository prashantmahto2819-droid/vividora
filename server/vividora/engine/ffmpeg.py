from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

ProgressFn = Callable[[float, str], None]


class FFmpegError(RuntimeError):
    pass


class Cancelled(RuntimeError):
    """The job was cancelled while a child process ran; the worker reports nothing for it."""
    no_retry = True


# ---- cancel support: every long child process the worker starts is tracked here, so a cancel from the
# editor (seen on the next heartbeat) kills the running ffmpeg/decoder at once instead of after the render.
import threading as _threading  # noqa: E402

_PROCS: set = set()
_LOCK = _threading.Lock()
CANCEL = _threading.Event()


def track(proc) -> None:
    with _LOCK:
        _PROCS.add(proc)


def untrack(proc) -> None:
    with _LOCK:
        _PROCS.discard(proc)


def cancel_all() -> int:
    """Set the cancel flag and terminate every tracked child. Returns how many were killed."""
    CANCEL.set()
    with _LOCK:
        procs = list(_PROCS)
    n = 0
    for pr in procs:
        try:
            if pr.poll() is None:
                pr.kill()
                n += 1
        except Exception:  # noqa: BLE001
            pass
    return n


def reset_cancel() -> None:
    CANCEL.clear()
    with _LOCK:
        _PROCS.clear()


def check_cancel() -> None:
    if CANCEL.is_set():
        raise Cancelled("रद्द किया")


def have(binary: str) -> bool:
    return shutil.which(binary) is not None


def probe(path: str | Path) -> dict:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise FFmpegError(f"ffprobe failed: {out.stderr.strip()[:500]}")
    data = json.loads(out.stdout)
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    duration = float(data.get("format", {}).get("duration") or 0)
    info: dict = {"duration": duration, "has_audio": a is not None, "has_video": v is not None}
    if v:
        w, h = int(v.get("width", 0)), int(v.get("height", 0))
        rotation = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rotation = int(sd["rotation"])
        rotation = int(v.get("tags", {}).get("rotate", rotation) or rotation)
        if abs(rotation) % 180 == 90:
            w, h = h, w  # phones store portrait video as rotated landscape
        num, _, den = (v.get("avg_frame_rate") or "30/1").partition("/")
        try:
            fps = float(num) / float(den or 1)
        except (ValueError, ZeroDivisionError):
            fps = 30.0
        info.update(
            width=w, height=h, fps=round(fps or 30.0, 3), vcodec=v.get("codec_name"),
            orientation="vertical" if h > w else ("square" if h == w else "horizontal"),
        )
    if a:
        info.update(acodec=a.get("codec_name"), sample_rate=int(a.get("sample_rate", 0) or 0))
    return info


def run(cmd: list[str], *, duration: float | None = None, on_progress: ProgressFn | None = None,
        label: str = "ffmpeg", is_heavy: bool = False) -> None:
    """Run ffmpeg, reporting progress (0..1) from its -progress output.

    is_heavy: when True, injects thread/buffer limits from hwaccel so heavy
    renders don't consume all cores and RAM on low-end PCs.
    """
    check_cancel()
    # Inject resource limits for heavy jobs (render, montage, matte)
    resource_args: list[str] = []
    if is_heavy:
        try:
            from . import hwaccel
            resource_args = hwaccel.ffmpeg_resource_args(is_heavy=True)
        except Exception:  # noqa: BLE001
            pass
    full = ["ffmpeg", "-hide_banner", "-y", "-nostats", *resource_args, "-progress", "pipe:1", *cmd]
    proc = subprocess.Popen(full, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    track(proc)
    last = -1.0
    assert proc.stdout is not None
    # stderr is drained on its own thread: a chatty run (timestamp warnings on a concatenated file) would
    # otherwise fill the 64 KB pipe while we read progress from stdout and ffmpeg would block forever
    import threading
    err_buf: list[str] = []

    def _drain() -> None:
        try:
            for ln in proc.stderr:  # type: ignore[union-attr]
                err_buf.append(ln)
                if len(err_buf) > 400:
                    del err_buf[:200]
        except (ValueError, OSError):
            pass
    th = threading.Thread(target=_drain, daemon=True)
    th.start()
    try:
        for line in proc.stdout:
            if on_progress and duration and line.startswith("out_time_ms="):
                try:
                    t = int(line.split("=", 1)[1]) / 1_000_000
                except ValueError:
                    continue
                frac = max(0.0, min(1.0, t / duration))
                if frac - last >= 0.02:
                    last = frac
                    on_progress(frac, label)
        rc = proc.wait()
        th.join(timeout=5)
    except BaseException:
        # a cancel raised from the progress callback (or anything else): never leave ffmpeg running on its own
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        untrack(proc)
    if CANCEL.is_set():
        raise Cancelled("रद्द किया")
    if rc != 0:
        tail = "\n".join("".join(err_buf).strip().splitlines()[-15:])
        raise FFmpegError(f"{label} failed:\n{tail}")


_SIL_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SIL_END = re.compile(r"silence_end:\s*([\d.]+)")


def silences(path: str | Path, noise_db: float = -35, min_dur: float = 0.45) -> list[tuple[float, float]]:
    """Return (start, end) of silent stretches in an audio/video file."""
    out = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn",
            "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    result: list[tuple[float, float]] = []
    start: float | None = None
    for line in out.stderr.splitlines():
        m = _SIL_START.search(line)
        if m:
            start = max(0.0, float(m.group(1)))
            continue
        m = _SIL_END.search(line)
        if m and start is not None:
            result.append((start, float(m.group(1))))
            start = None
    return result


def escape_filter_path(p: str | Path) -> str:
    """Escape a path for use inside an ffmpeg filter argument (subtitles=…)."""
    s = str(Path(p).as_posix())
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")
