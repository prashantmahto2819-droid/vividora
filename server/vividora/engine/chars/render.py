"""SVG frames → pictures, through ffmpeg's librsvg decoder (present in the Docker ffmpeg; no
cairo / browser needed). Results are cached by a hash of everything that shaped them.

  preview_png(params, pose, w, h)          one frame (library tiles, customiser)
  clip_webm(params, spec, w, h)            an animated, transparent VP9 webm the editor plays and the
                                           render composites (overlay_input_args adds -c:v libvpx-vp9)
  spec = {"dur", "base", "gesture"?, "expr"?, "lip": {"words": [...], "wav": path}?, "fps", "seed", "flip"}
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from . import anim, lipsync, rig

FPS = 25


def cache_dir() -> Path:
    d = Path(os.getenv("DATA_ROOT", "./data")).resolve() / "cache" / "chars"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _key(*parts) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:20]


def _ff(args: list[str]) -> None:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg (svg): " + (r.stderr or "").strip()[-600:])


def svg_to_png(svg: str, out: Path, w: int, h: int) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vsvg_") as td:
        f = Path(td) / "f_00001.svg"
        f.write_text(svg, encoding="utf-8")
        _ff(["-framerate", "1", "-i", str(Path(td) / "f_%05d.svg"), "-frames:v", "1", "-vf", f"scale={w}:{h}:flags=bicubic",
             "-pix_fmt", "rgba", str(out)])
    return out


def preview_png(params: dict, pose: dict | None = None, w: int = 300, h: int = 600) -> Path:
    p = rig.validate(params)
    out = cache_dir() / "png" / f"{_key(p, pose or {}, w, h, 'v2')}.png"
    if out.exists():
        return out
    return svg_to_png(rig.svg(p, pose, width=w, height=h), out, w, h)


def frame_pose(spec: dict, t: float, sched=None, env=None) -> dict:
    pose = anim.compose(t, spec.get("base") or "idle", spec.get("gesture"), int(spec.get("seed") or 0), float(spec.get("phase") or 0))
    if spec.get("expr"):
        pose["expr"] = spec["expr"]
    if sched is not None:
        v, j = lipsync.mouth_at(sched, env, t)
        pose["viseme"], pose["mouth_open"] = v, j
    if spec.get("flip"):
        pose["flip"] = 1
    # per-segment overrides: [{t0, t1, gesture?, expr?}]
    for seg in spec.get("segments") or []:
        if float(seg.get("t0", 0)) <= t < float(seg.get("t1", 0)):
            if seg.get("gesture"):
                pose.update(anim.pose_at(seg["gesture"], t - float(seg["t0"])))
            if seg.get("expr"):
                pose["expr"] = seg["expr"]
            if seg.get("talking") is False:
                pose["viseme"], pose["mouth_open"] = "rest", 0.0
    return pose


def clip_webm(params: dict, spec: dict, w: int = 480, h: int = 960, on_progress=None) -> Path:
    """Transparent VP9 webm of the character acting `spec` for spec['dur'] seconds."""
    p = rig.validate(params)
    fps = int(spec.get("fps") or FPS)
    dur = max(0.2, float(spec.get("dur") or 2.0))
    lip = spec.get("lip") or {}
    key = _key(p, {k: v for k, v in spec.items() if k != "lip"}, {"words": lip.get("words"), "wav": lip.get("wav_sig")}, w, h, "v2")
    out = cache_dir() / "webm" / f"{key}.webm"
    if out.exists():
        return out
    sched = env = None
    if lip.get("words"):
        sched = lipsync.schedule(lip["words"])
        if lip.get("wav") and Path(lip["wav"]).exists():
            env = lipsync.loudness(Path(lip["wav"]))
    n = int(round(dur * fps))
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vchar_") as td:
        td = Path(td)
        for i in range(n):
            t = i / fps
            pose = frame_pose(spec, t, sched, env)
            (td / f"f_{i + 1:05d}.svg").write_text(rig.svg(p, pose, width=w, height=h), encoding="utf-8")
            if on_progress and i % 25 == 0:
                on_progress(i / max(1, n), f"character frames {i}/{n}")
        tmp = td / "out.webm"
        _ff(["-framerate", str(fps), "-i", str(td / "f_%05d.svg"), "-vf", f"scale={w}:{h}:flags=bicubic,format=yuva420p",
             # flat vector art compresses well even at the fastest VP9 setting (5× faster than "good")
             "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", "-b:v", "0", "-crf", "30", "-deadline", "realtime", "-cpu-used", "8",
             "-row-mt", "1", "-threads", "4", "-r", str(fps), str(tmp)])
        tmp.replace(out)
    return out


def sheet_png(params: dict, clip: str, w: int = 160, h: int = 320, frames: int = 6) -> Path:
    """A strip of frames from one pose clip (the animation picker)."""
    p = rig.validate(params)
    out = cache_dir() / "png" / f"{_key(p, clip, w, h, frames, 'sheet')}.png"
    if out.exists():
        return out
    c = anim.CLIPS.get(clip, anim.CLIPS["idle"])
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vsheet_") as td:
        td = Path(td)
        for i in range(frames):
            t = c["len"] * i / frames
            (td / f"f_{i + 1:05d}.svg").write_text(rig.svg(p, anim.compose(t, clip), width=w, height=h), encoding="utf-8")
        _ff(["-framerate", "1", "-i", str(td / "f_%05d.svg"), "-frames:v", "1", "-vf", f"scale={w}:{h},tile={frames}x1", "-pix_fmt", "rgba", str(out)])
    return out
