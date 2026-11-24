"""An overlay clip played backwards (`reverse: true`): the picture really runs last-frame-first in the export.

    python3 tests/test_reverse.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vividora.engine import compose, render  # noqa: E402

T = Path(tempfile.mkdtemp(prefix="vividora-rev-"))
PRE = {"id": "t", "label": "t", "width": 320, "height": 180, "fit": "crop", "burn_captions": False,
       "video": {"crf": 20, "preset": "ultrafast", "fps_max": 30}, "audio": {"loudness": -14, "true_peak": -1.5}}


def ff(*a: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)


def lum(name: str, **kw) -> list[int]:
    r = render.render(video=T / "main.mp4", audio=None, meta={"width": 320, "height": 180, "fps": 30, "duration": 5.0, "has_audio": True},
                      edl={"duration": 5.0, "cuts": []}, transcript=None, preset=PRE, style=None, out_dir=T / name, name=name,
                      effects={"broll": [{"path": str(T / "ramp.mp4"), "type": "video", "start": 1.0, "end": 4.0, "fit": "cover", "fade": False, **kw}]},
                      face_track="off", encoder_preset="ultrafast", burn_captions=False)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", r["files"][0]["path"], "-vf", "fps=2,scale=32:18", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True, check=True).stdout
    return [int(x) for x in np.frombuffer(raw, np.uint8).reshape(-1, 18 * 32).mean(axis=1)]


def main() -> None:
    # a clip that gets brighter with time, over a dark main video
    ff("-f", "lavfi", "-i", "color=c=black:s=320x180:r=30:d=4,geq=lum='60*T':cb=128:cr=128", "-f", "lavfi", "-i", "sine=f=300:d=4",
       "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(T / "ramp.mp4"))
    ff("-f", "lavfi", "-i", "color=c=0x202020:s=320x180:r=30:d=5", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
       "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(T / "main.mp4"))
    assert compose.is_pro({"reverse": True}) and not compose.is_pro({"reverse": False})
    fwd, rev = lum("f"), lum("r", reverse=True)
    a, b = fwd[3:8], rev[3:8]                                     # samples inside the clip (1.5 s … 3.5 s)
    assert all(y > x for x, y in zip(a, a[1:])), fwd             # forwards: rising
    assert all(y < x for x, y in zip(b, b[1:])), rev             # reversed: falling
    assert abs(rev[2] - fwd[7]) < 25, (fwd, rev)                  # it starts where the forward one ended
    assert fwd[0] == rev[0] and fwd[-1] == rev[-1]                # outside the clip nothing changed
    print("PASS reversed clip runs backwards:", fwd, "→", rev)
    # with its own sound and a trim it still renders
    assert len(lum("rs", reverse=True, volume=0.8, trim_in=0.5)) >= 9
    print("PASS reversed with sound + trim renders")


if __name__ == "__main__":
    main()
    print("ALL PASS")
