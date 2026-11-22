#!/usr/bin/env python3
"""Crop → "fit": the selected part is shown whole (not zoomed to fill the frame); old projects keep filling.
    cd server && python3 tests/test_crop_fit.py"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vividora.engine import effects as fx  # noqa: E402
from vividora.engine import render  # noqa: E402

W, H = 1080, 1920


def frame(tmp: Path, tf: dict, name: str):
    """Render one frame of a white 1080x1920 source through crop → frame step; return grey levels at a few points."""
    pre, sw, sh = fx.transform_pre(tf, W, H)
    fit, col = render._crop_fit(tf, "crop")
    vf = (pre + "," if pre else "") + render._frame_filter(sw, sh, W, H, fit, 0.5, 0.5, None, col)
    out = tmp / f"{name}.gray"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=white:s={W}x{H}:d=1", "-filter_complex",
                    f"[0:v]{vf},format=gray[v]", "-map", "[v]", "-frames:v", "1", "-f", "rawvideo", str(out)], check=True)
    px = out.read_bytes()
    assert len(px) == W * H, (len(px), fit)
    at = lambda x, y: px[int(y * (H - 1)) * W + int(x * (W - 1))]  # noqa: E731
    return fit, at(0.5, 0.02), at(0.5, 0.5), at(0.5, 0.98)


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="vivi_cropfit_"))
    try:
        half = {"x": 0, "y": 0, "w": 1, "h": 0.5}                 # the top half of a vertical video
        fit, top, mid, bot = frame(tmp, {"crop": half, "crop_fit": "fit", "bg": "black"}, "fit_black")
        assert fit == "pad" and top < 30 and bot < 30 and mid > 200, (fit, top, mid, bot)   # half-height band, black above/below
        fit, top, mid, bot = frame(tmp, {"crop": half, "crop_fit": "fit", "bg": "color", "bg_color": "#808080"}, "fit_col")
        assert fit == "pad" and 100 < top < 160 and mid > 200, (fit, top, mid)
        fit, top, mid, bot = frame(tmp, {"crop": half, "crop_fit": "fit"}, "fit_blur")
        assert fit == "fitblur" and mid > 200 and top < mid, (fit, top, mid)                # blurred, darkened copy behind
        fit, top, mid, bot = frame(tmp, {"crop": half}, "legacy")                            # old project: zoom to fill
        assert fit == "crop" and top > 200 and mid > 200 and bot > 200, (fit, top, mid, bot)
        fit, top, mid, bot = frame(tmp, {"crop": half, "crop_fit": "fill"}, "fill")
        assert fit == "crop" and top > 200, (fit, top)
        assert render._crop_fit({"crop_fit": "fit"}, "blur") == ("blur", "black")           # no crop → the preset decides
        assert render._crop_fit({"crop": {"x": 0, "y": 0, "w": 1, "h": 1}, "crop_fit": "fit"}, "crop")[0] == "crop"
        print("OK")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
