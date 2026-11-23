#!/usr/bin/env python3
"""One montage that uses EVERY beat effect (video cuts and photo cuts) must join to its full length — a cut whose
effect changed the frame properties would make ffmpeg >= 7 stop early or hang in the join.
    cd server && python3 tests/test_montage_allfx.py"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vividora.engine import beatcut  # noqa: E402
from vividora.engine.presets import platform  # noqa: E402


def sh(*a: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *a], check=True)


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="vivi_allfx_"))
    try:
        sh("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=40", "-vf", "format=yuv420p10le,setparams=range=tv:color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc",
           "-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "log-level=error", "-tag:v", "hvc1", str(tmp / "hdr.mov"))
        sh("-f", "lavfi", "-i", "testsrc=s=960x540:r=25:d=40", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(tmp / "sdr.mp4"))
        sh("-f", "lavfi", "-i", "testsrc2=s=2016x1512", "-frames:v", "1", "-q:v", "3", str(tmp / "a.jpg"))
        sh("-f", "lavfi", "-i", "sine=f=220:d=60", str(tmp / "song.mp3"))
        clips = {"hdr": {"path": tmp / "hdr.mov", "kind": "video", "w": 1280, "h": 720}, "sdr": {"path": tmp / "sdr.mp4", "kind": "video", "w": 960, "h": 540},
                 "pic": {"path": tmp / "a.jpg", "kind": "image", "w": 2016, "h": 1512}}
        order = ["hdr", "sdr", "pic"]
        segs = []
        for k, fx in enumerate(beatcut.FX_ALL * 2):          # every effect twice, on rotating sources → each meets video and photo
            cid = order[(k + k // len(beatcut.FX_ALL)) % 3]
            segs.append({"i": k, "clip": cid, "src_in": float(k % 20), "dur": 0.7, "speed": 1.0, "fx": fx, "pulse": [0.35] if k % 4 == 0 else [],
                         "focus": [0.5, 0.5], "face": False, "score": 1, "energy": 0.5, "keep": True, "kind": clips[cid]["kind"], "beat": k})
        total = round(sum(s["dur"] for s in segs), 3)
        pl = {"segments": segs, "total": total, "music_start": 0.0, "bpm": 100, "look": "none"}
        t = time.time()
        out = beatcut.render(pl=pl, clips=clips, music_path=tmp / "song.mp3", out_dir=tmp / "out", name="ig-reel",
                             preset={**platform("ig-reel"), "width": 540, "height": 960})
        f = Path(out["files"][0]["path"])
        st = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration,nb_frames", "-of", "json", str(f)],
                                       capture_output=True, text=True).stdout)["streams"]
        v = next(s for s in st if s["codec_type"] == "video")
        assert abs(float(v["duration"]) - total) < 0.3, f"video {v['duration']}s but the plan is {total}s — the join stopped early"
        print(f"OK — {len(segs)} cuts, {len(beatcut.FX_ALL)} effects, {total}s joined in {time.time() - t:.0f}s on ffmpeg {subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True).stdout.split()[2][:14]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
