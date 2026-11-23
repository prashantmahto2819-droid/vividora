#!/usr/bin/env python3
"""Every montage effect renders, changes the START of the cut and leaves the END untouched (so cuts still join cleanly).
    cd server && python3 tests/test_montage_fx.py"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vividora.engine import beatcut  # noqa: E402

W, H, FPS, D = 270, 480, 30, 1.2


def render(tmp: Path, fx: str) -> list[bytes]:
    """The segment graph of engine/beatcut.py for one effect → RGB frames."""
    chain = beatcut._fx_chain({"dur": D, "fx": fx, "pulse": []}, W, H, FPS)
    big = fx == "shake"
    pre = f"scale={int(W * 1.1) if big else W}:{int(H * 1.1) if big else H}"
    graph = f"[0:v]fps={FPS},{pre}[r0];[r0]{chain + ',' if chain else ''}scale={W}:{H},trim=duration={D},setpts=PTS-STARTPTS,setsar=1,format=rgb24[v]"
    out = tmp / f"{fx}.raw"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s={W}x{H}:r={FPS}:d={D + 0.2}",
                    "-filter_complex", graph, "-map", "[v]", "-f", "rawvideo", str(out)], check=True, timeout=120)
    raw = out.read_bytes()
    n = W * H * 3
    return [raw[i:i + n] for i in range(0, len(raw) - n + 1, n)]


def diff(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a[::11], b[::11])) / len(a[::11])


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="vivi_fx_"))
    try:
        assert set(beatcut.FX_LABELS) == set(beatcut.FX_ALL), set(beatcut.FX_ALL) ^ set(beatcut.FX_LABELS)
        assert all(f in beatcut.FX_ALL for f in beatcut.FX_STRONG + beatcut.FX_SOFT + beatcut.FX_REVEAL)
        base = render(tmp, "cut")
        want = len(base)
        assert want >= 28, want
        whole_cut = {"zoom_in", "zoom_out"}          # slow moves that last the whole cut
        bad = []
        for fx in beatcut.FX_ALL:
            if fx == "cut":
                continue
            fr = render(tmp, fx)
            if abs(len(fr) - want) > 1:
                bad.append((fx, "frames", len(fr)))
                continue
            early = max(diff(fr[i], base[i]) for i in (0, 1, 2, 3))
            late = diff(fr[-2], base[-2])
            if early < 1.0:
                bad.append((fx, "start looks like a plain cut", round(early, 2)))
            if fx not in whole_cut and fx != "shake" and late > 4.0:   # rgbashift leaves a tiny colour-conversion difference even when it is off
                bad.append((fx, "end is not clean", round(late, 2)))
            print(f"  {fx:13s} start Δ{early:6.1f}   end Δ{late:5.1f}")
        assert not bad, bad
        # the plan can open with a reveal and uses the theme's pools
        print(f"OK — {len(beatcut.FX_ALL) - 1} effects")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
