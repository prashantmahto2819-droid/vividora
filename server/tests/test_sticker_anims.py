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


if __name__ == "__main__":
    main()
    print("ALL PASS")
