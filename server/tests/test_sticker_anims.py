"""Every sticker / picture animation in the menu really animates in the export (none is a silent plain fade),
and a turned sticker keeps its size when it also animates.

    python3 tests/test_sticker_anims.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vividora.engine import effects as fx  # noqa: E402

T = Path(tempfile.mkdtemp(prefix="vividora-stk-"))
W, H = 320, 180


def ff(*a: str) -> bytes:
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *a], capture_output=True)
    if r.returncode:
        raise RuntimeError(r.stderr.decode()[-500:])
    return r.stdout


def render(item: dict) -> np.ndarray:
    """→ frames [n, H, W, 3] of a 2 s clip: grey background + the sticker."""
    chain = fx.overlay_filter(item, 1, W, H, "[0:v]", "[v]", 0)
    raw = ff("-f", "lavfi", "-i", f"color=c=0x404040:s={W}x{H}:r=20:d=2", *fx.overlay_input_args(item, T / "s.png"),
             "-filter_complex", chain, "-map", "[v]", "-f", "rawvideo", "-pix_fmt", "rgb24", "-")
    n = len(raw) // (W * H * 3)
    return np.frombuffer(raw[:n * W * H * 3], np.uint8).reshape(n, H, W, 3).astype(np.float32)


def main() -> None:
    # a sticker that is not symmetric: a turn / flip must be visible
    ff("-f", "lavfi", "-i", "color=c=red:s=120x60,format=rgba,geq=r='255*lt(X,60)':g='255*gt(Y,30)':b=40:a=255", "-frames:v", "1", str(T / "s.png"))
    base = {"type": "image", "path": str(T / "s.png"), "start": 0.2, "end": 1.9, "fit": "free", "x": 0.5, "y": 0.5, "scale": 0.35}
    plain = render({**base, "anim": "none"})
    fade = render({**base, "anim": "fade"})
    assert len(plain) == 40, len(plain)
    seen = {}
    for a in fx.STICKER_ANIMS:
        if a in ("none", "fade"):
            continue
        f = render({**base, "anim": a})
        assert len(f) == len(plain), (a, len(f))
        d = np.abs(f - fade).mean(axis=(1, 2, 3))          # per frame: how far from a plain fade-in
        seen[a] = float(d.max())
        assert d.max() > 0.3, f"{a}: looks the same as a plain fade (max diff {d.max():.2f}) — not animated in the export"
        if a not in ("float", "wiggle"):                    # the looping ones keep moving; the rest settle on the plain picture
            assert np.abs(f[30] - plain[30]).mean() < 1.5, (a, float(np.abs(f[30] - plain[30]).mean()))
    print("PASS all", len(seen), "animations move:", {k: round(v, 1) for k, v in seen.items()})

    # turned 30° + animated: once settled it is the same picture as turned 30° without animation
    r0 = render({**base, "anim": "none", "rotate": 30})
    for a in ("pop", "spin", "flip", "elastic"):
        r1 = render({**base, "anim": a, "rotate": 30})
        d = float(np.abs(r1[32] - r0[32]).mean())
        assert d < 1.5, f"{a}: a turned sticker changes size when animated (diff {d:.2f})"
    print("PASS a turned sticker keeps its size with an animation")


def test_frame_style_and_ken_burns() -> None:
    """Photo frame (border, rounded corners, shadow) and Ken Burns on a full-screen photo — measured on the pixels."""
    ff("-f", "lavfi", "-i", "color=c=0x00C000:s=200x120", "-frames:v", "1", str(T / "p.png"))          # a plain green photo
    base = {"type": "image", "path": str(T / "p.png"), "start": 0.0, "end": 1.9, "fit": "free", "x": 0.5, "y": 0.5, "scale": 0.5}

    def at(item, x, y):
        f = render2(item)[20]
        return tuple(int(v) for v in f[y, x])
    plain = render2(base)[20]
    assert plain[90, 160, 1] > 150 and plain[90, 160, 0] < 60                                              # green in the middle
    cx0, cy0 = 80, 42                                                                                       # the picture: x 80–240, y 42–138
    assert plain[cy0 + 2, cx0 + 2, 1] > 150 and plain[cy0 - 6, cx0 - 6, 1] < 90                             # square corner, grey outside
    # rounded: the corner pixel is background again, the middle is untouched
    r = render2({**base, "radius": 0.5})[20]
    assert r[cy0 + 2, cx0 + 2, 1] < 90 and r[90, 160, 1] > 150, (r[cy0 + 2, cx0 + 2], r[90, 160])
    # border: red edge, green inside
    b = render2({**base, "border": 0.05, "border_color": "#FF0000"})[20]
    assert b[90, cx0 + 3, 0] > 150 and b[90, cx0 + 3, 1] < 80 and b[90, 160, 1] > 150, (b[90, cx0 + 3], b[90, 160])
    # shadow: darker than the background just outside the bottom-right, the picture itself where it was
    sh = render2({**base, "shadow": 1})[20]
    assert sh[138 + 2, 160].mean() < plain[138 + 2, 160].mean() - 12 and sh[90, 240 + 2].mean() < plain[90, 240 + 2].mean() - 12, (sh[140, 160], sh[90, 242])
    assert abs(sh[90, 160, 1] - plain[90, 160, 1]) < 12 and abs(sh[132, 160, 1] - plain[132, 160, 1]) < 12   # the picture itself did not move or darken (the last 2 px are chroma-soft)
    assert sh[cy0 - 4, 160].mean() > sh[138 + 2, 160].mean() + 8                                             # far weaker above than below
    # all three + an animation still render
    assert len(render2({**base, "radius": 0.2, "border": 0.03, "shadow": 0.6, "anim": "pop", "rotate": 15})) == 40
    assert fx.frame_style({"type": "image"}, 100, 0) == ""
    print("PASS photo frame: rounded corners, border, shadow (alone, together, with an animation)")

    # Ken Burns: a photo with a white square in its centre, filling the frame
    ff("-f", "lavfi", "-i", f"color=c=0x202060:s={W * 2}x{H * 2},drawbox=x={W - 40}:y={H - 40}:w=80:h=80:color=white:t=fill", "-frames:v", "1", str(T / "k.png"))
    kb = {"type": "image", "path": str(T / "k.png"), "start": 0.0, "end": 2.0, "fit": "cover", "fade": False}

    def white(item, n):
        f = render2(item, "k.png")[n]
        m = f.min(axis=2) > 200
        ys, xs = np.nonzero(m)
        return int(m.sum()), (float(xs.mean()) if len(xs) else -1), (float(ys.mean()) if len(ys) else -1)
    still0, still1 = white(kb, 2), white(kb, 36)
    assert abs(still0[0] - still1[0]) < 60 and abs(still0[1] - still1[1]) < 1.5                              # no kb: does not move
    zi0, zi1 = white({**kb, "kb": "zoom_in"}, 2), white({**kb, "kb": "zoom_in"}, 36)
    assert zi1[0] > zi0[0] * 1.15 and abs(zi1[1] - W / 2) < 4, (zi0, zi1)                                    # grows, stays centred
    zo0, zo1 = white({**kb, "kb": "zoom_out"}, 2), white({**kb, "kb": "zoom_out"}, 36)
    assert zo0[0] > zo1[0] * 1.15, (zo0, zo1)
    pl0, pl1 = white({**kb, "kb": "pan_left"}, 2), white({**kb, "kb": "pan_left"}, 36)
    assert pl1[1] - pl0[1] > 20 and abs(pl1[2] - pl0[2]) < 3, (pl0, pl1)                                     # the view goes left → the square moves right
    pd0, pd1 = white({**kb, "kb": "pan_down"}, 2), white({**kb, "kb": "pan_down"}, 36)
    assert pd0[2] - pd1[2] > 10 and abs(pd1[1] - pd0[1]) < 3, (pd0, pd1)
    assert fx.ken_burns({"type": "video", "kb": "zoom_in", "start": 0, "end": 2}, W, H) == "" and fx.ken_burns({**kb, "kb": "nope"}, W, H) == ""
    print("PASS Ken Burns: zoom in / out, pan — a photo without it stays still, a video is never touched")


def render2(item: dict, name: str = "p.png") -> np.ndarray:
    chain = fx.overlay_filter(item, 1, W, H, "[0:v]", "[v]", 0)
    raw = ff("-f", "lavfi", "-i", f"color=c=0x404040:s={W}x{H}:r=20:d=2", *fx.overlay_input_args(item, T / name),
             "-filter_complex", chain, "-map", "[v]", "-f", "rawvideo", "-pix_fmt", "rgb24", "-")
    n = len(raw) // (W * H * 3)
    return np.frombuffer(raw[:n * W * H * 3], np.uint8).reshape(n, H, W, 3).astype(np.float32)


if __name__ == "__main__":
    test_frame_style_and_ken_burns()
    main()
    print("ALL PASS")
