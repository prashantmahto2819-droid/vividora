#!/usr/bin/env python3
"""Phone photos with a second picture inside (iPhone HDR / portrait — MPF) must not hang `-loop 1`; and a stuck
ffmpeg is killed by the watchdog instead of blocking the worker.     cd server && python3 tests/test_still.py"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vividora.engine import ffmpeg  # noqa: E402

GRAPH = ("[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[r0];"
         "[r0]zoompan=z='1+0.10*in_time/0.790':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
         "scale=1080:1920,trim=duration=0.790,setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v]")


def seg(src: Path, out: Path) -> list[str]:   # the montage segment command (engine/beatcut.py)
    return ["-loop", "1", "-framerate", "30", "-t", "0.890", "-i", str(src), "-filter_complex", GRAPH, "-map", "[v]", "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-t", "0.790", str(out)]


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="vivi_still_"))
    try:
        mk = lambda size, name: subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",  # noqa: E731
                                                f"testsrc2=s={size}", "-frames:v", "1", str(tmp / name)], check=True)
        mk("4032x3024", "big.jpg"); mk("1008x756", "small.jpg")
        phone = tmp / "phone_photo"   # library files have no extension; two JPEGs in one file = main picture + gain map
        phone.write_bytes((tmp / "big.jpg").read_bytes() + (tmp / "small.jpg").read_bytes())
        assert ffmpeg.still(tmp / "big.jpg") == tmp / "big.jpg", "an ordinary photo is used as it is"
        fixed = ffmpeg.still(phone)
        assert fixed != phone and fixed.exists(), fixed
        pr = ffmpeg.probe(fixed)
        assert (pr.get("width"), pr.get("height")) == (4032, 3024), pr   # the main picture, not the small one
        assert ffmpeg.still(phone) == fixed, "second call reuses the copy"
        assert ffmpeg.still(tmp / "missing.jpg") == tmp / "missing.jpg", "never raises"
        t = time.time()
        ffmpeg.run(seg(fixed, tmp / "ok.mp4"), label="segment")
        assert (tmp / "ok.mp4").stat().st_size > 1000 and time.time() - t < 60
        # watchdog: the raw 2-picture file loops for ever on this graph → killed, error raised, no process left behind
        os.environ["FFMPEG_STALL_SECONDS"] = "5"
        t = time.time()
        try:
            ffmpeg.run(seg(phone, tmp / "bad.mp4"), label="stuck")
            print("note: this ffmpeg build does not hang on the raw file")
        except ffmpeg.FFmpegError as e:
            assert "progress" in str(e) and time.time() - t < 40, e
        print("OK")
    finally:
        os.environ.pop("FFMPEG_STALL_SECONDS", None)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
