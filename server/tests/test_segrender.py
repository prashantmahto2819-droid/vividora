#!/usr/bin/env python3
"""Segment-cached render tests (engine/segrender.py).

    cd server && python3 tests/test_segrender.py [--out DIR]

1. same picture: a 75 s synthetic recording (cuts, zoom, flash transitions, captions, a title, a B-roll
   overlay, music, watermark) rendered in one pass and in cached pieces → same frame count / duration,
   the pieces' frames match the single pass (sampled, incl. around every boundary), sound present.
2. cache hit: a second render with one cut moved re-renders only the pieces that changed; a render with
   nothing changed reuses every piece.
3. join continuity: no duplicated / missing frames at boundaries (frame timestamps strictly +1/fps).
Exit code 1 when a check fails.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vividora.engine import render, segrender  # noqa: E402
from vividora.engine.presets import caption_style  # noqa: E402

FPS = 30
FAILS: list[str] = []


def check(cond: bool, label: str, val=None) -> None:
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"  → {str(val)[:300]}"))
    if not cond:
        FAILS.append(label)


def ff(*args: str) -> None:
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg: " + r.stderr[-800:])


def probe(p: Path) -> dict:
    from vividora.engine.ffmpeg import probe as pr
    return pr(p)


def frames_gray(path: Path, scale_w: int = 160) -> np.ndarray:
    info = probe(path)
    w, h = scale_w, int(round(info["height"] * scale_w / info["width"] / 2)) * 2
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True).stdout
    n = len(raw) // (w * h)
    return np.frombuffer(raw[:n * w * h], np.uint8).reshape(n, h, w).astype(np.float32)


def pts_list(path: Path) -> list[float]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=pts_time",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return [float(x.strip(",")) for x in out.split() if x.strip(",").strip()]


def make_media(d: Path) -> dict:
    d.mkdir(parents=True, exist_ok=True)
    src = d / "rec.mp4"
    if not src.exists():
        # a moving pattern + a big frame counter, so a frame off shows up as a large pixel difference
        ff("-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate={FPS}:duration=75",
           "-f", "lavfi", "-i", "sine=frequency=440:duration=75",
           "-vf", "drawtext=text='%{n}':fontsize=160:fontcolor=white:x=(w-tw)/2:y=(h-th)/2:box=1:boxcolor=black@0.6",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", str(src))
    music = d / "music.m4a"
    if not music.exists():
        ff("-f", "lavfi", "-i", "sine=frequency=220:duration=90", "-af", "volume=0.5", "-c:a", "aac", str(music))
    img = d / "broll.png"
    if not img.exists():
        ff("-f", "lavfi", "-i", "color=c=orange:size=640x360:duration=1", "-frames:v", "1", str(img))
    wm = d / "wm.png"
    if not wm.exists():
        ff("-f", "lavfi", "-i", "color=c=white@0.8:size=200x80:duration=1", "-frames:v", "1", str(wm))
    return {"src": src, "music": music, "img": img, "wm": wm}


def edl_with(cuts: list[tuple[float, float]], dur: float) -> dict:
    return {"duration": dur, "cuts": [{"start": a, "end": b, "enabled": True, "kind": "filler"} for a, b in cuts],
            "stats": {"cuts": len(cuts)}}


def transcript_for(dur: float) -> dict:
    words, t, i = [], 0.5, 0
    while t < dur - 1:
        words.append({"start": round(t, 2), "end": round(t + 0.4, 2), "text": f"शब्द{i}", "w": f"शब्द{i}"})
        t += 0.6
        i += 1
    segs = [{"start": words[k]["start"], "end": words[min(len(words) - 1, k + 9)]["end"], "text": " ".join(w["text"] for w in words[k:k + 10]),
             "words": words[k:k + 10]} for k in range(0, len(words), 10)]
    return {"segments": segs, "language": "hi"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.getenv("VIVIDORA_TEST_OUT", "/tmp/vividora_seg_tests"))
    a = ap.parse_args()
    out = Path(a.out)
    media = make_media(out / "media")
    cache = out / "cache"
    shutil.rmtree(cache, ignore_errors=True)
    os.environ["SEG_CACHE_DIR"] = str(cache)
    src = media["src"]
    info = probe(src)
    meta = {"width": info["width"], "height": info["height"], "fps": FPS, "duration": info["duration"], "has_audio": True}
    cuts = [(10.0, 11.5), (24.3, 26.0), (33.0, 33.8), (47.2, 49.0), (60.0, 61.1)]
    edl = edl_with(cuts, info["duration"])
    tr = transcript_for(info["duration"])
    style = caption_style("karaoke")
    preset = {"id": "yt-long", "label": "YouTube", "width": 1280, "height": 720, "fit": "crop", "burn_captions": True,
              "video": {"crf": 18, "preset": "ultrafast", "fps_max": 60}, "audio": {"loudness": -14, "true_peak": -1.5},
              "caption_margin_v": 0.12, "caption_scale": 1.0}
    effects = {"zoom": {"enabled": True, "strength": 1.0, "mode": "punch"}, "transition": "flash", "look": "none",
               "music": {"path": str(media["music"]), "volume": 0.2, "duck": True},
               "broll": [{"path": str(media["img"]), "type": "image", "start": 40.0, "end": 45.0, "fit": "pip", "pos": "tr"}],
               "titles": [{"start": 20.0, "end": 25.0, "text": "नमस्ते", "pos": "top", "size": 0.08, "color": "#FFFFFF"}],
               "watermark": {"path": str(media["wm"]), "opacity": 0.7, "size": 0.14, "pos": "tr"}}
    common = dict(video=src, audio=None, meta=meta, edl=edl, transcript=tr, preset=preset, style=style,
                  burn_captions=True, effects=effects, encoder_preset="ultrafast")

    # ---- 1. one pass vs pieces
    t0 = time.time()
    single = render.render(out_dir=out / "single", name="yt-long", **common)
    t_single = time.time() - t0
    sp = Path(single["files"][0]["path"])
    t0 = time.time()
    seg = segrender.render_segmented(project_id="p1", source_sig="src1", out_dir=out / "seg1", name="yt-long", **common)
    t_seg = time.time() - t0
    gp = Path(seg["files"][0]["path"])
    print(f"single {t_single:.1f}s · pieces {t_seg:.1f}s · {seg['segmented']}")
    ps, pg = probe(sp), probe(gp)
    check(abs(ps["duration"] - pg["duration"]) < 0.08, "same duration", (ps["duration"], pg["duration"]))
    check(pg["has_audio"], "joined file has sound")
    fs, fg = frames_gray(sp), frames_gray(gp)
    check(fs.shape[0] == fg.shape[0], "same frame count", (fs.shape[0], fg.shape[0]))
    n = min(fs.shape[0], fg.shape[0])
    diff = np.abs(fs[:n] - fg[:n]).mean(axis=(1, 2))
    bad = int((diff > 6.0).sum())
    print(f"  frame mean-abs-diff: max {diff.max():.2f}, mean {diff.mean():.2f}, frames > 6: {bad}")
    check(bad <= max(2, n // 200), "pieces match the single pass (≤0.5% frames differ)", (bad, n))
    check(diff.max() < 25, "no frame off by a whole frame (counter would differ a lot)", diff.max())
    pts = pts_list(gp)
    steps = np.diff(np.array(pts))
    check(len(pts) == n and np.all(np.abs(steps - 1 / FPS) < 1e-3), "timestamps strictly continuous", (len(pts), float(steps.min()), float(steps.max())))
    # loudness: both files similar
    def lufs(p: Path) -> float:
        r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(p), "-af", "ebur128=peak=none", "-f", "null", "-"], capture_output=True, text=True).stderr
        import re as _re
        m = _re.findall(r"I:\s+(-?[\d.]+) LUFS", r)
        return float(m[-1]) if m else -99.0
    ls, lg = lufs(sp), lufs(gp)
    check(abs(ls - lg) < 1.5, "loudness matches", (ls, lg))

    # ---- 2. cache: unchanged → all reused; one cut moved → only its pieces re-render
    seg2 = segrender.render_segmented(project_id="p1", source_sig="src1", out_dir=out / "seg2", name="yt-long", **common)
    check(seg2["segmented"]["reused"] == seg2["segmented"]["pieces"], "unchanged render reuses every piece", seg2["segmented"])
    cuts2 = list(cuts)
    cuts2[2] = (33.0, 34.4)  # the third cut grows by 0.6 s
    common2 = {**common, "edl": edl_with(cuts2, info["duration"]), "effects": {**effects, "zoom": {"enabled": False}}}
    base2 = segrender.render_segmented(project_id="p2", source_sig="src1", out_dir=out / "seg3", name="yt-long", **common2)
    cuts3 = list(cuts2)
    cuts3[3] = (47.2, 48.6)
    common3 = {**common2, "edl": edl_with(cuts3, info["duration"])}
    seg3 = segrender.render_segmented(project_id="p2", source_sig="src1", out_dir=out / "seg4", name="yt-long", **common3)
    s3 = seg3["segmented"]
    print(f"  after one cut edit: {s3}")
    check(s3["reused"] >= s3["pieces"] - 3, "one cut edit re-renders only a few pieces", s3)
    check(s3["reused"] >= 1, "some pieces reused after an edit", s3)
    gp3 = Path(seg3["files"][0]["path"])
    exp_dur = info["duration"] - sum(b - a for a, b in cuts3)
    check(abs(probe(gp3)["duration"] - exp_dur) < 0.08, "edited render has the right length", (probe(gp3)["duration"], exp_dur))

    # ---- 3. eligibility: xfade / short video fall back
    r = segrender.why_not({"transition": "x_fade"}, edl, meta, None, preset)
    check(r is not None, "cross-dissolve is not pieced", r)
    r = segrender.why_not({}, edl, {**meta, "duration": 20}, None, preset)
    check(r is not None, "short video is not pieced", r)
    # prune keeps recent files
    pr = segrender.prune(days=7, max_gb=100)
    check(pr["removed"] == 0, "prune keeps fresh pieces", pr)
    pr = segrender.prune(days=7, max_gb=0.0)
    check(pr["total"] == 0 or pr["removed"] > 0, "prune trims to the size cap", pr)
    (out / "results.json").write_text(json.dumps({"fails": FAILS, "single_s": t_single, "seg_s": t_seg, "seg": seg["segmented"]}, indent=1))
    print(f"\n{'ALL PASSED' if not FAILS else str(len(FAILS)) + ' FAILED: ' + ', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
