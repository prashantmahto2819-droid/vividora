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


def on_bg(tmp: Path, tf: dict, name: str, preset_fit: str = "crop", src: str = "white"):
    """One frame of a 1080x1920 source over the user's own background → grey levels on a 5x5 grid of points."""
    kind = render._custom_bg(tf)
    assert kind, tf
    pre, sw, sh = fx.transform_pre(tf, W, H)
    ins = ["-f", "lavfi", "-i", f"color={src}:s={W}x{H}:d=1:r=30"]
    if kind == "image":
        ins += ["-loop", "1", "-i", tf["bg_image_path"]]
    elif kind == "video":
        ins += ["-stream_loop", "-1", "-i", tf["bg_video_path"]]
    graph = (render._bg_chain(tf, kind, 1 if kind != "gradient" else None, W, H, 30) + ";[0:v]" + (pre + "," if pre else "")
             + render._frame_on_bg(tf, sw, sh, W, H, preset_fit, 0.5, 0.5, place=True) + ",format=gray[v]")
    out = tmp / f"{name}.gray"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *ins, "-filter_complex", graph, "-map", "[v]", "-frames:v", "1",
                    "-f", "rawvideo", str(out)], check=True, timeout=120)
    px = out.read_bytes()
    assert len(px) == W * H, (len(px), name)
    return lambda x, y: px[int(y * (H - 1)) * W + int(x * (W - 1))]


def own_background(tmp: Path) -> None:
    mk = lambda *a: subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *a], check=True)  # noqa: E731
    mk("-f", "lavfi", "-i", "color=0x404040:s=640x360", "-frames:v", "1", str(tmp / "bg.png"))            # dark grey photo (landscape)
    mk("-f", "lavfi", "-i", "color=0x404040:s=640x360:d=1:r=25", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(tmp / "bg.mp4"))
    half = {"x": 0, "y": 0, "w": 1, "h": 0.5}
    img = {"bg": "image", "bg_image_path": str(tmp / "bg.png")}
    assert render._custom_bg({"bg": "image"}) is None and render._custom_bg({"bg": "blur"}) is None      # no file → normal fill
    at = on_bg(tmp, {**img, "crop": half, "crop_fit": "fit"}, "img_fit")
    assert at(.5, .5) > 200 and 40 < at(.5, .03) < 90 and 40 < at(.5, .97) < 90, (at(.5, .5), at(.5, .03))   # band on the photo
    at = on_bg(tmp, {**img, "crop": half, "crop_fit": "fit", "scale": 0.5, "x": 0.2, "y": -0.3}, "img_place")
    # half-size band (540x480) moved right by 20% of the width and up by 30% of the height → centre at (0.7, 0.2)
    assert at(.7, .2) > 200 and at(.2, .2) < 90 and at(.7, .5) < 90 and at(.5, .5) < 90, (at(.7, .2), at(.2, .2), at(.7, .5))
    at = on_bg(tmp, {**img, "scale": 0.5}, "img_small")                                                   # no crop: shrunk video on the photo
    assert at(.5, .5) > 200 and at(.1, .1) < 90 and at(.9, .9) < 90
    at = on_bg(tmp, dict(img), "img_full")                                                                 # nothing to show behind → all video
    assert at(.02, .02) > 200 and at(.98, .98) > 200
    at = on_bg(tmp, {"bg": "video", "bg_video_path": str(tmp / "bg.mp4"), "crop": half, "crop_fit": "fit"}, "vid_fit")
    assert at(.5, .5) > 200 and 40 < at(.5, .03) < 90, (at(.5, .5), at(.5, .03))
    at = on_bg(tmp, {"bg": "gradient", "bg_color": "#000000", "bg_color2": "#000000", "crop": half, "crop_fit": "fit"}, "grad")
    assert at(.5, .5) > 200 and at(.5, .03) < 30
    at = on_bg(tmp, {**img, "crop": half, "crop_fit": "fill"}, "img_fill")                                 # "fill": zoomed to the whole frame
    assert at(.5, .03) > 200 and at(.5, .97) > 200


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
        own_background(tmp)
        print("OK")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
