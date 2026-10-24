"""Segment-cached render: the video is made in ~15 s pieces that are cached by what went into them.

After a small edit only the pieces whose inputs changed are rendered again; the sound is made once
for the whole video (ducking / loudness must see all of it) and the pieces are joined without
re-encoding. Cancel stops between pieces; a later render picks the finished pieces up from the cache.

Pieces are cut on jump cuts (where the picture restarts anyway) and, inside long uncut stretches, at
quiet points at least 0.35 s away from a zoom move. The full video's zoom plan is sliced per piece so a
punch-in that straddles a boundary is identical on both sides; the transition of the cut a piece starts
on is drawn at its first frames, the leading half of the next cut's transition at its last ones.

Not every project can be pieced (see `why_not`): cross-dissolve transitions, speed ramps, morph cuts,
stabilise / face refine, keyframed main-video transform or mask, the global effect stack, and cutout
animations all depend on the whole timeline — those render in one go as before.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

from . import effects as fx
from . import ffmpeg, protools
from .autocut import keep_segments, remap_words, words_of
from .encode import RENDER_VERSION
from .render import _cut_points, _snap, out_timeline, render

log = logging.getLogger("vividora.segrender")

TARGET_SECONDS = 15.0     # wanted piece length
MAX_SECONDS = 26.0        # a piece never gets longer than this (split inside a long take)
MIN_TOTAL = 40.0          # shorter videos: one plain render is faster than pieces + join
CACHE_DAYS = 7
CACHE_GB = float(os.getenv("SEG_CACHE_GB", "20"))


def cache_root() -> Path:
    return Path(os.getenv("SEG_CACHE_DIR") or (Path(os.getenv("TMPDIR", "/tmp")) / "vividora-segcache"))


# ---------------------------------------------------------------- eligibility
def why_not(effects: dict | None, edl: dict, meta: dict, clip: dict | None, preset: dict) -> str | None:
    """None when the segment path reproduces the single-pass render exactly; otherwise the reason."""
    e = effects or {}
    if clip:
        return "Short / preview"
    if os.getenv("SEGMENT_RENDER", "1") == "0":
        return "SEGMENT_RENDER=0"
    dur = float(meta.get("duration") or 0)
    if dur < MIN_TOTAL:
        return "छोटा video"
    tr = e.get("transition") or "none"
    if fx.is_xfade(tr):
        return "cross-dissolve transition"
    for c in edl.get("cuts") or []:
        if c.get("enabled", True) and fx.is_xfade(c.get("transition") or "none"):
            return "cross-dissolve transition"
        if c.get("enabled", True) and c.get("morph"):
            return "morph cut"
    if e.get("speed") or edl.get("speed"):
        return "speed ramp"
    if e.get("stack"):
        return "effect stack (पूरे video पर)"
    pro = e.get("pro") or {}
    for k in ("stabilize", "face_refine", "morph_cut", "mask"):
        v = pro.get(k)
        if isinstance(v, dict) and v.get("enabled"):
            return k
    tf = e.get("transform") or {}
    if tf.get("kf"):
        return "keyframed transform"
    body = e.get("body") or {}
    if body.get("enabled") and (float(body.get("bg_zoom", 0) or 0) > 0 or (body.get("anim") or "none") != "none"):
        return "cutout animation"
    return None


# ---------------------------------------------------------------- planning
def _keep(edl: dict, fps: float) -> list[tuple[float, float]]:
    keep = [(_snap(a, fps), _snap(b, fps)) for a, b in keep_segments(edl)]
    return [(a, b) for a, b in keep if b - a >= 1 / fps]


def plan_pieces(keep: list[tuple[float, float]], zoom_points: list[float], fps: float,
                target: float = TARGET_SECONDS, longest: float = MAX_SECONDS) -> list[dict]:
    """Pieces on the source timeline: [{keep: [(a,b)…], src_start, src_end, out_start, out_dur, on_cut}].
    `zoom_points` are output times where the zoom eases (a split must not land inside an ease)."""
    pieces: list[dict] = []
    cur: list[tuple[float, float]] = []
    cur_dur = 0.0
    out_t = 0.0
    zp = sorted(zoom_points)

    def ok_split(t_out: float) -> bool:
        return all(not (p - 0.05 <= t_out < p + 0.4) for p in zp)

    def flush() -> None:
        nonlocal cur, cur_dur, out_t
        if not cur:
            return
        pieces.append({"keep": cur, "src_start": cur[0][0], "src_end": cur[-1][1], "out_start": round(out_t, 4),
                       "out_dur": round(cur_dur, 4)})
        out_t += cur_dur
        cur, cur_dur = [], 0.0

    for a, b in keep:
        d = b - a
        while d > longest:  # a long take: split it at frame boundaries, away from zoom eases
            x = _snap(a + int(round(target * fps)) / fps, fps)
            tries = 0
            while not ok_split(out_t + cur_dur + (x - a)) and tries < 40:
                x = _snap(x + 0.25, fps)
                tries += 1
            if x >= b - 1.0:
                break
            cur.append((a, x))
            cur_dur += x - a
            flush()
            a, d = x, b - x
        if cur and cur_dur + d > target * 1.35:
            flush()
        cur.append((a, b))
        cur_dur += d
        if cur_dur >= target:
            flush()
    flush()
    cut_starts = {keep[i][0] for i in range(1, len(keep))}
    for p in pieces:
        p["on_cut"] = p["src_start"] in cut_starts  # starts on a jump cut (not the start, not a split inside a take)
    return pieces


def piece_key(core: dict, piece: dict, e: dict, words: list[dict], edl: dict) -> str:
    """Everything that decides this piece's pixels: its source range, the items that fall inside it
    (on the piece's own clock), the cuts it contains, the words it shows."""
    o0, o1 = piece["out_start"], piece["out_start"] + piece["out_dur"]
    items = {}
    for key in ("titles", "broll", "fxclips"):
        got = []
        for it in e.get(key) or []:
            if not isinstance(it, dict):
                continue
            s, en = float(it.get("start", 0)), float(it.get("end", 0))
            if en > o0 and s < o1:
                got.append({**it, "start": round(s - o0, 3), "end": round(en - o0, 3)})
        items[key] = got
    cuts_in = [c for c in (edl.get("cuts") or []) if c.get("enabled", True)
               and piece["src_start"] - 0.1 <= float(c.get("end", -1)) <= piece["src_end"] + 0.1]
    ws = [(round(float(w["start"]) - o0, 2), round(float(w["end"]) - o0, 2), w.get("w") or w.get("text"))
          for w in words if float(w["end"]) > o0 and float(w["start"]) < o1]
    core2 = {**core, "keep": piece["keep"], "items": items, "cuts": cuts_in, "words": ws, "on_cut": piece["on_cut"],
             "tr": [piece.get("tr_in"), piece.get("tr_out")], "zoom": piece.get("zoom"), "hook": piece.get("hook")}
    return hashlib.sha1(json.dumps(core2, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:20]


def _zoom_slice(points: list[tuple[float, float]], t0: float, t1: float) -> list[tuple[float, float]]:
    """The full plan restricted to [t0, t1), on the piece's own clock, opening at the level reached before t0."""
    level = 1.0
    for t, z in points:
        if t < t0:
            level = z
    return [(-0.3, level)] + [(round(t - t0, 3), z) for t, z in points if t0 <= t < t1]


def _probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                          "-show_entries", "stream=nb_read_frames,r_frame_rate:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True).stdout
    try:
        j = json.loads(out)
        st = (j.get("streams") or [{}])[0]
        return {"frames": int(st.get("nb_read_frames") or 0), "duration": float((j.get("format") or {}).get("duration") or 0)}
    except (ValueError, IndexError):
        return {"frames": 0, "duration": 0.0}


# ---------------------------------------------------------------- the render
def render_segmented(*, project_id: str, source_sig: str, on_progress=None, **kw) -> dict:
    """Same arguments and result as render.render (minus clip). `source_sig` identifies the source files
    (asset ids + sizes). Raises ValueError with a reason when this project cannot be pieced."""
    effects = dict(kw.get("effects") or {})
    edl, meta, preset = kw["edl"], kw["meta"], kw["preset"]
    reason = why_not(effects, edl, meta, kw.get("clip"), preset)
    if reason:
        raise ValueError(reason)
    from . import encode
    src_fps = float(meta.get("fps") or 30.0)
    fps_max = float(preset.get("video", {}).get("fps_max", 60))
    fps0 = round(src_fps if src_fps <= fps_max + 0.5 else fps_max, 3) or 30.0
    enc = encode.plan(kw.get("export"), preset, meta, fps0)
    fps = enc["fps"]
    keep = _keep(edl, fps)
    if not keep:
        raise ValueError("कट के बाद कुछ नहीं बचा")
    full_dur = sum(b - a for a, b in keep)
    if full_dur < MIN_TOTAL:
        raise ValueError("छोटा output")
    cuts = _cut_points(keep)
    transcript = kw.get("transcript")
    words = remap_words(words_of(transcript), keep) if transcript else []
    zoom = effects.get("zoom") or {}
    emph = None
    if zoom.get("enabled") and zoom.get("mode") == "emphasis" and words:
        import re as _re
        from .shorts import HOOK_WORDS
        emph = [wd["start"] for wd in words if _re.sub(r"[^\w]", "", wd["w"].lower()) in HOOK_WORDS or wd["w"].rstrip().endswith("!")]
    plan = (fx.zoom_plan(cuts, full_dur, float(zoom.get("strength", 1.0)), mode=zoom.get("mode") or "punch", emphasis=emph)
            if zoom.get("enabled") else [(0.0, 1.0)])
    pieces = plan_pieces(keep, [t for t, _ in plan], fps)
    if len(pieces) < 2:
        raise ValueError("एक ही टुकड़ा")
    # transition kind at each cut (source time of the cut's end → kind)
    default_tr = effects.get("transition") or ("flash" if effects.get("flash") else "none")
    cut_kind: dict[float, str] = {}
    for c in edl.get("cuts") or []:
        if c.get("enabled", True):
            cut_kind[round(float(c.get("end", -1)), 2)] = c.get("transition") or default_tr
    for i, p in enumerate(pieces):
        p["tr_in"] = (cut_kind.get(round(p["src_start"], 2), default_tr) if p["on_cut"] else None)
        nxt = pieces[i + 1] if i + 1 < len(pieces) else None
        p["tr_out"] = (cut_kind.get(round(nxt["src_start"], 2), default_tr) if nxt and nxt["on_cut"] else None)
        p["zoom"] = _zoom_slice(plan, p["out_start"], p["out_start"] + p["out_dur"]) if zoom.get("enabled") else None
        p["hook"] = kw.get("hook") if i == 0 else None

    # what every piece shares
    e_vid = {k: v for k, v in effects.items() if k not in ("music", "sfx", "voice", "voice_track", "voice_track_path",
                                                             "voice_track_words", "voice_track_mode", "voice_track_under",
                                                             "voice_track_sig", "track_audio", "titles", "broll", "fxclips", "font_paths")}
    core = {"v": RENDER_VERSION, "preset": preset.get("id"), "src": source_sig, "export": enc["export"],
            "style": kw.get("style"), "cap_over": kw.get("caption_overrides"), "burn": kw.get("burn_captions"),
            "focus": [kw.get("focus_x", 0.5), kw.get("focus_y", 0.5)], "face_track": kw.get("face_track", "auto"),
            "effects": e_vid, "fonts": sorted(Path(x).name for x in (effects.get("font_paths") or [])),
            "fps": fps, "x264": kw.get("encoder_preset") or preset.get("video", {}).get("preset", "medium")}
    cdir = cache_root() / project_id
    cdir.mkdir(parents=True, exist_ok=True)
    out_dir: Path = kw["out_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    name = kw["name"]
    work = out_dir / f".{name}.pieces"
    work.mkdir(exist_ok=True)

    keys = [piece_key(core, p, effects, words, edl) for p in pieces]
    have = [(cdir / f"{k}.{enc['container']}").exists() for k in keys]
    reused = sum(have)
    total_steps = len(pieces) - reused + 1  # + the sound
    step = [0]
    label = preset.get("label", name)

    def prog(frac_inner: float, msg: str) -> None:
        if on_progress:
            on_progress(min(0.97, (step[0] + frac_inner) / max(1, total_steps) * 0.97),
                        f"{label}: {msg} · टुकड़ा {min(step[0] + 1, len(pieces))}/{len(pieces)} ({reused} cache से)")

    t_start = time.time()
    akey = hashlib.sha1(json.dumps({"v": RENDER_VERSION, "src": source_sig, "edl": edl, "preset": preset.get("id"),
                                    "aud": {k: effects.get(k) for k in ("music", "sfx", "voice", "voice_track", "voice_track_mode",
                                                                         "voice_track_under", "track_audio", "broll", "hidden_tracks")},
                                    "export": {k: enc["export"].get(k) for k in ("audio_codec", "audio_kbps", "sample_rate", "mono")}},
                                   sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:20]
    aext = "webm" if enc["export"]["audio_codec"] == "opus" else "m4a"
    adst = cdir / f"{akey}.{aext}"
    audio_box: dict = {"path": adst if adst.exists() else None, "none": False}
    if adst.exists():
        os.utime(adst, None)
        total_steps -= 1

    def do_piece(i: int) -> None:
        p, k = pieces[i], keys[i]
        dst = cdir / f"{k}.{enc['container']}"
        if dst.exists():
            os.utime(dst, None)
            return
        ffmpeg.check_cancel()
        pe = dict(effects)
        for key in ("titles", "broll", "fxclips"):
            pe[key] = effects.get(key) or []
        sub = dict(kw)
        sub.update(effects=pe, out_dir=work, name=f"p{i:03d}",
                   clip={"start": p["src_start"], "end": p["src_end"]},
                   hook=kw.get("hook") if i == 0 else None,
                   seek=max(0.0, p["src_start"] - 0.5), video_only=True,
                   boundary_cut=p["tr_in"], trailing_cut=p["tr_out"],
                   zoom_plan_override=p["zoom"],
                   on_progress=prog)
        res = render(**sub)
        f = Path(res["files"][0]["path"])
        want = int(round(p["out_dur"] * fps))
        got = res.get("frames")
        if got != want:
            raise RuntimeError(f"piece {i}: {got} frames, expected {want}")
        shutil.move(str(f), str(dst))
        step[0] += 1

    def do_audio() -> None:
        # the sound, once, for the whole video (a small picture is still computed — overlays may carry sound)
        if audio_box["path"] is not None:
            return
        ffmpeg.check_cancel()
        small = {**preset, "width": 320, "height": 180}
        sub = dict(kw)
        sub.update(preset=small, out_dir=work, name="audio", audio_only=True, on_progress=prog,
                   export={**(kw.get("export") or {}), "resolution": "source", "width": 0, "height": 0, "quality": "final"})
        res = render(**sub)
        ap = res.get("audio")
        if ap:
            shutil.move(str(ap), str(adst))
            audio_box["path"] = adst
        else:
            audio_box["none"] = True
        step[0] += 1

    # pieces a few at a time (each ffmpeg filter graph is single-threaded; the encoder is not), the sound beside them
    import concurrent.futures as _cf
    workers = max(1, min(3, (os.cpu_count() or 4) // 6))
    todo = [i for i in range(len(pieces)) if not have[i]]
    with _cf.ThreadPoolExecutor(max_workers=workers + 1) as ex:
        futs = [ex.submit(do_audio)] + [ex.submit(do_piece, i) for i in todo]
        for f_ in futs:
            f_.result()  # re-raises the first failure (and Cancelled)
    audio_path = audio_box["path"]
    # join
    lst = work / "pieces.txt"
    lst.write_text("".join(f"file '{(cdir / f'{k}.{enc['container']}').as_posix()}'\n" for k in keys), encoding="utf-8")
    out = out_dir / f"{name}.{enc['container']}"
    cmd = ["-f", "concat", "-safe", "0", "-i", str(lst)]
    if audio_path:
        cmd += ["-i", str(audio_path)]
    cmd += ["-map", "0:v:0"] + (["-map", "1:a:0"] if audio_path else []) + ["-c", "copy", *enc["extra"], "-t", f"{full_dur:.3f}", str(out)]
    ffmpeg.run(cmd, duration=full_dur, on_progress=lambda f, m: on_progress and on_progress(0.97 + 0.03 * f, "जोड़ रहे हैं"), label="join")
    # validation: every frame accounted for, no drift, sound present when expected
    info = _probe(out)
    want_frames = sum(int(round(p["out_dur"] * fps)) for p in pieces)
    if abs(info["frames"] - want_frames) > 2:
        raise RuntimeError(f"join: {info['frames']} frames, expected {want_frames}")
    if abs(info["duration"] - full_dur) > 0.25:
        raise RuntimeError(f"join: duration {info['duration']:.2f}s, expected {full_dur:.2f}s")
    if audio_path:
        a = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(out)],
                           capture_output=True, text=True).stdout.strip()
        if not a:
            raise RuntimeError("join: no audio stream")
    shutil.rmtree(work, ignore_errors=True)
    style = kw.get("style")
    burn = preset.get("burn_captions", True) if kw.get("burn_captions") is None else kw.get("burn_captions")
    files = [{"kind": "render", "path": out, "mime": enc["mime"], "label": preset["id"],
              "meta": {"preset": preset["id"], "width": enc["width"], "height": enc["height"], "duration": round(full_dur, 2),
                       "fps": fps, "codec": enc["codec"], "container": enc["container"],
                       "export": enc["export"] if kw.get("export") else None,
                       "captions": (style or {}).get("id") if (burn and style) else None,
                       "segmented": {"pieces": len(pieces), "reused": reused, "seconds": round(time.time() - t_start, 1)},
                       "effects": {"zoom": bool(zoom.get("enabled")), "look": effects.get("look") or None,
                                   "music": bool((effects.get("music") or {}).get("path")),
                                   "broll": len(effects.get("broll") or []), "titles": len(effects.get("titles") or []),
                                   "watermark": bool((effects.get("watermark") or {}).get("path")),
                                   "voice_track": effects.get("voice_track") if effects.get("voice_track_path") else "original"}}}]
    if preset.get("sidecar_srt") and words:
        from .captions import build_srt
        srt = out_dir / f"{name}.srt"
        srt.write_text(build_srt(words), encoding="utf-8")
        files.append({"kind": "subtitle", "path": srt, "mime": "application/x-subrip", "label": preset["id"], "meta": {"preset": preset["id"]}})
    warnings = []
    max_s = preset.get("max_seconds")
    if max_s and full_dur > max_s:
        warnings.append(f"{preset.get('label')}: वीडियो {full_dur:.0f}s है, सीमा {max_s}s — upload नहीं होगा")
    return {"files": files, "duration": round(full_dur, 2), "warnings": warnings,
            "segmented": {"pieces": len(pieces), "reused": reused}}


# ---------------------------------------------------------------- cache upkeep
def prune(days: int = CACHE_DAYS, max_gb: float = CACHE_GB) -> dict:
    """Drop pieces older than `days`, then the oldest until the cache is under `max_gb`."""
    root = cache_root()
    if not root.exists():
        return {"removed": 0, "bytes": 0}
    now = time.time()
    files = [f for f in root.rglob("*") if f.is_file()]
    removed, freed = 0, 0
    for f in files:
        try:
            if now - f.stat().st_mtime > days * 86400:
                freed += f.stat().st_size
                f.unlink()
                removed += 1
        except OSError:
            pass
    rest = sorted((f for f in files if f.exists()), key=lambda f: f.stat().st_mtime)
    total = sum(f.stat().st_size for f in rest)
    while rest and total > max_gb * 1e9:
        f = rest.pop(0)
        try:
            total -= f.stat().st_size
            freed += f.stat().st_size
            f.unlink()
            removed += 1
        except OSError:
            pass
    for d in [d for d in root.iterdir() if d.is_dir()]:
        if not any(d.iterdir()):
            d.rmdir()
    return {"removed": removed, "bytes": freed, "total": total}
