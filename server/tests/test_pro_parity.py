"""A clip that goes through the pro compositor (trim / mask / crop / keyframes …) keeps its sticker animation, photo frame
and Ken Burns move — it must look like the same clip on the simple path. Run: python3 tests/test_pro_parity.py"""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vividora.engine import compose, render  # noqa: E402

T = Path(tempfile.mkdtemp(prefix="vividora-parity-"))
W, H = 640, 360


def ff(*a):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *a], check=True)


def frames(effects: dict, name: str, times) -> list[np.ndarray]:
    meta = {"width": W, "height": H, "fps": 25, "duration": 4.0, "has_audio": True}
    pre = {"id": "t", "label": "t", "width": W, "height": H, "fit": "crop", "burn_captions": False,
           "video": {"crf": 18, "preset": "ultrafast", "fps_max": 60}, "audio": {"loudness": -14, "true_peak": -1.5}}
    r = render.render(video=T / "main.mp4", audio=None, meta=meta, edl={"duration": 4.0, "cuts": []}, transcript=None, preset=pre, style=None,
                      out_dir=T / name, name=name, effects=effects, face_track="off", encoder_preset="ultrafast", burn_captions=False)
    f = r["files"][0]["path"]
    out = []
    for t in times:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(f), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        out.append(np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(np.float32))
    return out


def box(im):
    """Centre and width of the red sticker (fractions of the frame), None when it is not there."""
    m = (im[..., 0] > 150) & (im[..., 1] < 90) & (im[..., 2] < 90)
    if m.sum() < 30:
        return None
    ys, xs = np.where(m)
    return round(float(xs.mean()) / W, 3), round(float(ys.mean()) / H, 3), round(float(xs.max() - xs.min()) / W, 3)


def main():
    ff("-f", "lavfi", "-i", f"color=c=0x303030:s={W}x{H}:d=4:r=25", "-f", "lavfi", "-i", "sine=f=300:d=4", "-c:v", "libx264", "-preset", "ultrafast",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(T / "main.mp4"))
    ff("-f", "lavfi", "-i", "color=c=red:s=200x120", "-frames:v", "1", str(T / "s.png"))
    ff("-f", "lavfi", "-i", "testsrc2=s=800x450", "-frames:v", "1", str(T / "photo.png"))
    base = {"type": "image", "path": str(T / "s.png"), "start": 0.4, "end": 3.6, "fit": "free", "x": 0.5, "y": 0.5, "scale": 0.3, "_id": "a"}
    full = {"x": 0, "y": 0, "w": 1, "h": 1}            # "crop" is a pro key: the same clip, now on the compositor
    assert not compose.is_pro(base) and compose.is_pro({**base, "crop": full})
    times = [0.5, 0.62, 0.8, 1.5, 2.6, 3.5]
    worst = {}
    for anim in ("drop", "pop", "slide_left", "zoom", "spin", "float", "wiggle", "bounce", "elastic", "shake", "rotate_in", "slide_up"):
        a = frames({"broll": [{**base, "anim": anim}]}, "l_" + anim, times)
        b = frames({"broll": [{**base, "anim": anim, "crop": full}]}, "p_" + anim, times)
        d = 0.0
        for t, x, y in zip(times, a, b):
            bx, by = box(x), box(y)
            if bx is None or by is None:
                assert bx is None and by is None or t in (0.5, 3.5), (anim, t, bx, by)     # only the faint first / last frames may differ
                continue
            d = max(d, abs(bx[0] - by[0]), abs(bx[1] - by[1]), abs(bx[2] - by[2]))
        worst[anim] = round(d, 3)
        assert d < 0.05, f"{anim}: the pro clip is up to {d:.3f} of the frame away from the simple one"
    moved = frames({"broll": [{**base, "anim": "drop", "crop": full}]}, "p_drop2", [0.5, 2.0])
    assert box(moved[0]) is None or box(moved[0])[1] < 0.3, "drop must start above the frame on the pro path too"
    print("animations on the pro path match the simple path (largest gap, fraction of the frame):", worst)

    # photo frame: border + rounded corners + shadow
    st = {"border": 0.05, "border_color": "#FFFFFF", "radius": 0.2, "shadow": 0.8}
    a = frames({"broll": [{**base, **st}]}, "l_frame", [2.0])[0]
    b = frames({"broll": [{**base, **st, "crop": full}]}, "p_frame", [2.0])[0]
    white = lambda im: int(((im.min(axis=2) > 200)).sum())                       # noqa: E731  the border
    dark = lambda im: int((im.max(axis=2) < 30).sum())                           # noqa: E731  the shadow on the grey wall
    assert white(a) > 500 and abs(white(a) - white(b)) < 0.25 * white(a), (white(a), white(b))
    assert dark(a) > 100 and abs(dark(a) - dark(b)) < 0.5 * dark(a) + 60, (dark(a), dark(b))
    assert box(b) and abs(box(a)[2] - box(b)[2]) < 0.02, (box(a), box(b))          # the picture keeps its size with a shadow
    assert np.abs(a - b).mean() < 4, float(np.abs(a - b).mean())
    print(f"photo frame on the pro path: border {white(b)} px (simple {white(a)}), shadow {dark(b)} px (simple {dark(a)}), same size ✓")

    # Ken Burns: a photo that fills the frame keeps moving on the pro path
    ph = {"type": "image", "path": str(T / "photo.png"), "start": 0.4, "end": 3.6, "fit": "cover", "kb": "zoom_in", "kb_amount": 0.4, "fade": False, "_id": "k"}
    a = frames({"broll": [ph]}, "l_kb", [0.6, 3.4])
    b = frames({"broll": [{**ph, "crop": full}]}, "p_kb", [0.6, 3.4])
    assert np.abs(b[0] - b[1]).mean() > 8, "the photo does not move on the pro path"
    assert np.abs(a[0] - b[0]).mean() < 12 and np.abs(a[1] - b[1]).mean() < 12, (float(np.abs(a[0] - b[0]).mean()), float(np.abs(a[1] - b[1]).mean()))
    print("Ken Burns on the pro path: moves, and matches the simple path ✓")
    print("ALL PASS")


if __name__ == "__main__":
    main()
