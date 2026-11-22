#!/usr/bin/env python3
"""Auto beat-edit montage of mixed sources — an HDR phone video (10-bit HEVC, HLG), an ordinary SDR video and a phone
photo with two pictures inside — must render to the full length. On ffmpeg ≥ 7 the photo piece used to make the join
reconfigure its filter graph and stop early / dead-lock.        cd server && python3 tests/test_montage_mixed.py"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vividora.engine import beatcut, ffmpeg  # noqa: E402
from vividora.engine.presets import platform  # noqa: E402


def sh(*a: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *a], check=True)


def props(p: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=pix_fmt,color_range,color_space,color_transfer,color_primaries,chroma_location,duration", "-of", "json", str(p)],
                         capture_output=True, text=True).stdout
    return json.loads(out)["streams"][0]


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="vivi_mixed_"))
    try:
        sh("-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=8", "-vf",
           "format=yuv420p10le,setparams=range=tv:color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc",
           "-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "log-level=error", "-tag:v", "hvc1", str(tmp / "hdr.mov"))
        sh("-f", "lavfi", "-i", "testsrc=s=1280x720:r=30:d=8", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(tmp / "sdr.mp4"))
        sh("-f", "lavfi", "-i", "testsrc2=s=4032x3024", "-frames:v", "1", "-q:v", "3", str(tmp / "a.jpg"))
        sh("-f", "lavfi", "-i", "testsrc2=s=1008x756", "-frames:v", "1", str(tmp / "b.jpg"))
        (tmp / "photo").write_bytes((tmp / "a.jpg").read_bytes() + (tmp / "b.jpg").read_bytes())   # main picture + gain map
        # a song with a clear beat (120 bpm clicks over a tone)
        sh("-f", "lavfi", "-i", "sine=f=220:d=20", "-f", "lavfi", "-i", "sine=f=1200:d=20", "-filter_complex",
           "[1:a]volume='if(lt(mod(t,0.5),0.05),1,0)':eval=frame[c];[0:a][c]amix=inputs=2[a]", "-map", "[a]", str(tmp / "song.mp3"))
        assert ffmpeg.hdr_to_sdr(tmp / "hdr.mov") and not ffmpeg.hdr_to_sdr(tmp / "sdr.mp4")
        files = {"hdr": ("hdr.mov", "video"), "sdr": ("sdr.mp4", "video"), "photo": ("photo", "image")}
        infos = [{"id": cid, **beatcut.clip(tmp / f, kind)} for cid, (f, kind) in files.items()]
        mu = beatcut.music(tmp / "song.mp3", 12)
        pl = beatcut.plan(mu, infos, max_seconds=12, pins=list(files))
        used = {s["clip"] for s in pl["segments"]}
        assert used == set(files), f"plan must use all three sources, used {used}"
        clips = {i["id"]: {"path": tmp / files[i["id"]][0], "kind": i["kind"], "w": i["w"], "h": i["h"]} for i in infos}
        t = time.time()
        out = beatcut.render(pl=pl, clips=clips, music_path=tmp / "song.mp3", out_dir=tmp / "out", name="ig-reel", preset=platform("ig-reel"))
        f = Path(out["files"][0]["path"])
        pr = props(f)
        want = sum(float(s["dur"]) for s in pl["segments"])
        assert abs(float(pr["duration"]) - want) < 0.25, f"video is {pr['duration']}s, plan is {want:.2f}s (stopped early?)"
        assert pr["pix_fmt"] == "yuv420p" and pr.get("color_range") == "tv" and pr.get("color_transfer") == "bt709", pr
        a = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=duration", "-of", "csv=p=0", str(f)],
                           capture_output=True, text=True).stdout.strip()
        assert abs(float(a) - want) < 0.3, f"audio {a}s vs {want:.2f}s"
        print(f"OK — {len(pl['segments'])} pieces, {want:.1f}s, rendered in {time.time() - t:.0f}s on {subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True).stdout.split()[2]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
