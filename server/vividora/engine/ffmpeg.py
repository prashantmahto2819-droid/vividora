from __future__ import annotations

import json
import re
import shutil
import os
import subprocess
import time
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


def still(path: str | Path) -> Path:
    """A photo that is safe to feed to `-loop 1`.

    Phone photos (iPhone HDR / portrait, Samsung, Pixel "Ultra HDR") are JPEGs with a SECOND picture inside (gain map,
    depth map — MPF). ffmpeg reads that as a 2-frame stream and `-loop 1 -t …` then never ends. For such files the first
    picture is written once next to the original and that copy is used; ordinary images are returned unchanged."""
    path = Path(path)
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0",
                              "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)],
                             capture_output=True, text=True, timeout=60).stdout.strip().split(",")[0]
        if int(out or 1) <= 1:
            return path
    except (ValueError, OSError, subprocess.SubprocessError):
        return path
    fixed = path.with_name(path.name + ".still.jpg")
    if fixed.exists() and fixed.stat().st_size > 0:
        return fixed
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-frames:v", "1", "-update", "1",
                        "-q:v", "2", str(fixed)], capture_output=True, text=True, timeout=120)
    return fixed if r.returncode == 0 and fixed.exists() and fixed.stat().st_size > 0 else path


# ---- pieces that will be joined with the concat demuxer must look identical to ffmpeg --------------------------------
# A photo piece (JPEG: full range, centre chroma, bt601) next to a phone-video piece (limited range, left chroma, often
# HLG/bt2020) makes ffmpeg ≥ 7 "reconfigure the filter graph" in the middle of the join: the audio restarts, timestamps
# jump, and the encode either stops early or dead-locks for ever. So every piece ends with UNIFORM_VF and is encoded
# with UNIFORM_ENC — same pixel format, range, colour tags and chroma position — and HDR sources are really converted
# to SDR (hdr_to_sdr) instead of only being re-labelled.
UNIFORM_VF = ("scale=in_range=auto:out_range=tv,format=yuv420p,"
              "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709")
UNIFORM_ENC = ["-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
               "-chroma_sample_location", "left"]
_TONEMAP = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
            "zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def hdr_to_sdr(path: str | Path) -> str:
    """Filter chain that turns an HDR video (iPhone HLG / Dolby Vision, HDR10 PQ) into SDR bt709 — "" for SDR sources.
    Put it after the resize (it works in float, so fewer pixels = much faster)."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=color_transfer",
                              "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=60).stdout.strip().lower()
    except (OSError, subprocess.SubprocessError):
        return ""
    if out.split(",")[0].strip() not in ("arib-std-b67", "smpte2084"):
        return ""
    mode = (os.getenv("HDR_TONEMAP") or "hable").lower()   # hable = best highlights · fast = direct conversion · off = only re-label
    return "" if mode == "off" else ("zscale=t=bt709:m=bt709:p=bt709:r=tv,format=yuv420p" if mode == "fast" else _TONEMAP)


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


_SCRIPT_OPT: list[str] = []


def _script_opt(cmd: list[str]) -> list[str]:
    """`-filter_complex_script FILE` was deprecated in ffmpeg 7 and removed in 8 (new spelling: `-/filter_complex FILE`).
    Callers keep the old spelling; it is translated here when the installed ffmpeg no longer knows it."""
    if "-filter_complex_script" not in cmd:
        return cmd
    if not _SCRIPT_OPT:
        try:
            helptxt = subprocess.run(["ffmpeg", "-hide_banner", "-h", "full"], capture_output=True, text=True, timeout=30).stdout
        except (OSError, subprocess.SubprocessError):
            helptxt = "filter_complex_script"
        _SCRIPT_OPT.append("-filter_complex_script" if "filter_complex_script" in helptxt else "-/filter_complex")
    return [_SCRIPT_OPT[0] if x == "-filter_complex_script" else x for x in cmd]


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
    full = ["ffmpeg", "-hide_banner", "-y", "-nostats", *resource_args, "-progress", "pipe:1", *_script_opt(cmd)]
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
    # watchdog: a stuck ffmpeg (e.g. an endless image loop) prints no progress at all, so a reader loop alone would
    # wait for ever. A side thread kills it when the output position has not moved for FFMPEG_STALL_SECONDS.
    stall_s = float(os.getenv("FFMPEG_STALL_SECONDS", "900") or 0)
    moved = [time.monotonic(), ""]
    stalled = threading.Event()

    def _watch() -> None:
        while proc.poll() is None:
            if stall_s and time.monotonic() - moved[0] > stall_s:
                stalled.set()
                try:
                    proc.kill()
                except OSError:
                    pass
                return
            time.sleep(1.0)
    threading.Thread(target=_watch, daemon=True).start()
    try:
        for line in proc.stdout:
            if line.startswith("out_time_ms=") and line != moved[1]:
                moved[0], moved[1] = time.monotonic(), line
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
    if stalled.is_set():
        raise FFmpegError(f"{label}: {int(stall_s)}s तक कोई progress नहीं — ffmpeg अटक गया था, रोक दिया")
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
