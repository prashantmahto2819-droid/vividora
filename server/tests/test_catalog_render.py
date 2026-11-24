"""Every effect and every look the editor lists builds a filter graph that this ffmpeg really accepts, and an effect
that only works on the whole video (Color Pop) does not break the export when it sits on the timeline as a clip.

    python3 tests/test_catalog_render.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vividora.engine import catalog, effects as fx, render  # noqa: E402

W, H, FPS = 160, 90, 20


def accepts(chain: str) -> str:
    """'' when ffmpeg runs the chain on a short test picture, else the end of its error."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s={W}x{H}:r={FPS}:d=0.5", "-filter_complex",
                        f"[0:v]{chain},format=yuv420p[v]", "-map", "[v]", "-f", "null", "-"], capture_output=True, text=True)
    return "" if r.returncode == 0 else r.stderr.strip()[-300:]


def main() -> None:
    jobs: list[tuple[str, str]] = []
    skipped = []
    for e in catalog.EFFECTS:
        chain = catalog.stack_filter([{"id": e["id"], "params": {}}], W, H, FPS, 0.5)
        if not chain or "__" in chain:          # placeholders (Color Pop) are wired by the renderer itself
            skipped.append(e["id"])
            continue
        jobs.append((f"effect {e['id']}", chain))
    for gid, g in catalog.GRADE_PRESETS.items():
        chain = catalog.grade_filter({k: v for k, v in g.items() if k not in ("label", "cat")})
        if chain:
            jobs.append((f"look {gid}", chain))
    for lid in fx.LOOKS:
        chain = fx.look_filter(lid)
        if chain:
            jobs.append((f"quick look {lid}", chain))
    for x in fx.EXTRAS:
        jobs.append((f"extra {x}", fx.extras_filter([x])))
    with ThreadPoolExecutor(4) as ex:
        bad = [(n, err) for (n, _), err in zip(jobs, ex.map(lambda j: accepts(j[1]), jobs)) if err]
    assert not bad, "ffmpeg refuses:\n" + "\n".join(f"  {n}: {e}" for n, e in bad[:12])
    assert skipped == ["color_pop"], skipped
    print(f"PASS {len(jobs)} effects / looks build a graph ffmpeg accepts (placeholder effects: {skipped})")

    # Color Pop as a timed effect clip: skipped with a warning — the export still comes out, with the other clip applied
    t = Path(tempfile.mkdtemp(prefix="vividora-cat-"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=2", "-f", "lavfi", "-i", "sine=f=300:d=2",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(t / "v.mp4")], check=True)
    pre = {"id": "t", "label": "t", "width": 320, "height": 180, "fit": "crop", "burn_captions": False,
           "video": {"crf": 26, "preset": "ultrafast", "fps_max": 30}, "audio": {"loudness": -14, "true_peak": -1.5}}
    res = render.render(video=t / "v.mp4", audio=None, meta={"width": 320, "height": 180, "fps": 30, "duration": 2.0, "has_audio": True},
                        edl={"duration": 2.0, "cuts": []}, transcript=None, preset=pre, style=None, out_dir=t / "o", name="cp",
                        effects={"fxclips": [{"id": "color_pop", "start": 0.2, "end": 1.6, "params": {}}, {"id": "vhs", "start": 0.2, "end": 1.6, "params": {}}]},
                        face_track="off", encoder_preset="ultrafast", burn_captions=False)
    assert Path(res["files"][0]["path"]).stat().st_size > 2000
    print("PASS Color Pop as a timeline clip no longer fails the export")


if __name__ == "__main__":
    main()
    print("ALL PASS")
