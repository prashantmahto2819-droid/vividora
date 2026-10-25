"""Turn the original recording + cut list + captions + effects into a finished
video for one platform.

`effects` (already resolved by the worker: library ids → local paths):
  zoom      {enabled, strength}            auto punch-in at every cut
  look      colour look id                 lut_path: a .cube file instead
  flash     bool                           white flash on cuts
  music     {path, volume, duck}           background music, ducked under speech
  broll     [{path, type: video|image, start, end, fit: cover|pip, pos}]
            cutout + alpha_path (worker-resolved person matte) → only the person is overlaid
  titles    [{start, end, text, pos, size, color, bg}]
  watermark {path, opacity, size, pos}
  sfx       [{path, at, volume}]
  fxclips   [{kind: effect|filter, id | grade, params, start, end, track}]  effect/filter only for that range
  voice_track      "original" | dub asset id; the worker adds voice_track_path / _words
  voice_track_mode  "replace" (AI voice only) | "both" (original quieter under it, voice_track_under 0..1)
Times are on the output (post-cut) timeline.
"""

from __future__ import annotations

import logging

import math
import re
from pathlib import Path

from . import catalog, encode
from . import compose, protools  # pro compositing / main-video pro tools (additive)
from . import effects as fx
from . import ffmpeg
from .autocut import keep_segments, map_words, remap_words, words_of
from .captions import build_ass, build_srt, resolve_style
from .ffmpeg import ProgressFn

FONTS_DIR = Path(__file__).resolve().parent.parent.parent / "fonts"


def fonts_with(extra: list[Path] | None, work: Path) -> Path:
    """Bundled fonts + the creator's uploaded fonts in one folder (libass reads a single fontsdir)."""
    if not extra:
        return FONTS_DIR
    d = work / "fonts"
    d.mkdir(parents=True, exist_ok=True)
    for f in [*FONTS_DIR.glob("*.[ot]tf"), *extra]:
        dst = d / f.name
        if not dst.exists():
            try:
                dst.symlink_to(f.resolve())
            except OSError:
                import shutil
                shutil.copy2(f, dst)
    return d


def _snap(t: float, fps: float) -> float:
    return round(t * fps) / fps


def _select_expr(keep: list[tuple[float, float]], fps: float) -> str:
    # half a frame of tolerance so each kept piece has an exact number of frames;
    # audio uses the same snapped times, so lips stay in sync after many cuts
    eps = 0.5 / fps
    return "+".join(f"gte(t\\,{a - eps:.4f})*lt(t\\,{b - eps:.4f})" for a, b in keep)


def _frame_filter(src_w: int, src_h: int, w: int, h: int, fit: str, focus_x: float, focus_y: float,
                  track_cmds: Path | None = None) -> str:
    src_ratio, dst_ratio = src_w / max(1, src_h), w / h
    if abs(src_ratio - dst_ratio) / dst_ratio < 0.02:
        return f"scale={w}:{h}:flags=lanczos,setsar=1"
    if track_cmds is not None and fit == "crop" and src_ratio > dst_ratio:
        # the crop window follows the face (sendcmd moves crop@face.x over time)
        return (f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"sendcmd=f='{ffmpeg.escape_filter_path(track_cmds)}',"
                f"crop@face={w}:{h}:(iw-{w})*{focus_x:.3f}:(ih-{h})*{focus_y:.3f},setsar=1")
    if fit == "crop" or (fit == "blur" and src_ratio > dst_ratio and dst_ratio >= 1):
        # fill the frame and cut the sides; focus_x moves the window left/right
        return (f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={w}:{h}:(iw-{w})*{focus_x:.3f}:(ih-{h})*{focus_y:.3f},setsar=1")
    if fit == "pad":
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1")
    # blur: the same video, blurred and darkened, fills the empty space
    return (f"split[bgsrc][fgsrc];"
            f"[bgsrc]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            f"gblur=sigma=28,eq=brightness=-0.08:saturation=0.9[bg];"
            f"[fgsrc]scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")


def _plan_segments(keep: list[tuple[float, float]], edl: dict, default_tr: str, speed: list[dict] | None):
    """Segments (a, b, rate, transition_before) on the SOURCE timeline. Speed ranges split
    keep segments; a transition belongs to the boundary that starts a segment."""
    cut_tr: dict[float, str] = {}
    for cdef in (edl.get("cuts") or []):
        if cdef.get("enabled", True):
            cut_tr[round(float(cdef.get("end", -1)), 2)] = cdef.get("transition") or default_tr
    rates = sorted(((float(r["start"]), float(r["end"]), max(0.25, min(4.0, float(r.get("rate", 1))))) for r in (speed or [])
                    if float(r.get("end", 0)) > float(r.get("start", 0))))
    segs = []
    for i, (a, b) in enumerate(keep):
        bounds = sorted({a, b, *[x for r in rates for x in (r[0], r[1]) if a < x < b]})
        first = True
        for x, y in zip(bounds, bounds[1:]):
            rate = next((r[2] for r in rates if r[0] <= x and y <= r[1]), 1.0)
            tr = (cut_tr.get(round(a, 2), default_tr) if i > 0 else "none") if first else "none"
            segs.append({"a": x, "b": y, "rate": rate, "tr": tr if fx.is_xfade(tr) or tr in fx.TRANSITIONS else "none"})
            first = False
    return segs


def _segment_timeline(segs: list[dict]) -> list[dict]:
    """Add output start/duration to each segment, accounting for xfade overlaps."""
    t = 0.0
    for sgm in segs:
        d = (sgm["b"] - sgm["a"]) / sgm["rate"]
        if fx.is_xfade(sgm["tr"]):
            t -= min(fx.XFADE_SECONDS, d / 2, (segs[segs.index(sgm) - 1]["out_dur"] / 2) if segs.index(sgm) > 0 else d)
        sgm["out_start"] = max(0.0, t)
        sgm["out_dur"] = d
        t += d
    return segs


def _src_to_out(segs: list[dict]):
    def f(t: float) -> float | None:
        for sgm in segs:
            if sgm["a"] <= t < sgm["b"] or (t == sgm["b"] and sgm is segs[-1]):
                return sgm["out_start"] + (t - sgm["a"]) / sgm["rate"]
        return None
    return f


def _atempo(rate: float) -> str:
    parts = []
    r = rate
    while r > 2.0:
        parts.append("atempo=2.0"); r /= 2.0
    while r < 0.5:
        parts.append("atempo=0.5"); r /= 0.5
    parts.append(f"atempo={r:.4f}")
    return ",".join(parts)


def _body(body: dict, w: int, h: int, v_in: str, a_in: str, out: str, extra_in: dict, work: Path, e: dict, dur: float,
          fps: float = 30.0) -> list[str]:
    behind = [t for t in (e.get("titles") or []) if t.get("text") and t.get("behind")]
    ass_path = None
    if behind:
        from .captions import build_ass
        t_style, t_events = fx.title_events(behind, w, h, "Poppins")
        p = work / "behind.ass"
        p.write_text(build_ass([], {}, w, h, margin_v_ratio=0.2, extra_styles=[t_style], extra_events=t_events), encoding="utf-8")
        ass_path = ffmpeg.escape_filter_path(p)
    return fx.body_chain(body, w, h, v_in, a_in, out, extra_inputs=extra_in, ass_behind=ass_path,
                         fonts_dir=ffmpeg.escape_filter_path(FONTS_DIR) if FONTS_DIR.exists() else None,
                         fps=fps, duration=dur)


def _cut_points(keep: list[tuple[float, float]]) -> list[float]:
    """Output-timeline times where a jump cut happens."""
    pts, t = [], 0.0
    for a, b in keep:
        t += b - a
        pts.append(t)
    return pts[:-1]


def out_timeline(edl: dict, fps: float, effects: dict | None = None):
    """Source time → output time of the FULL video (same cuts / speed ramps / clip transitions as
    render). → (to_out(t) → float | None, output duration). The AI voice-over is timed with this."""
    fps = float(fps or 30.0)
    keep = [(_snap(a, fps), _snap(b, fps)) for a, b in keep_segments(edl)]
    keep = [(a, b) for a, b in keep if b - a >= 1 / fps]
    if not keep:
        return (lambda t: None), 0.0
    e = effects or {}
    segs = _segment_timeline(_plan_segments(keep, edl, e.get("transition") or "none", e.get("speed") or edl.get("speed")))
    if any(fx.is_xfade(sg["tr"]) or sg["rate"] != 1.0 for sg in segs):
        return _src_to_out(segs), segs[-1]["out_start"] + segs[-1]["out_dur"]

    def to_out(t: float) -> float | None:
        o = 0.0
        for a, b in keep:
            if a <= t < b:
                return o + (t - a)
            o += b - a
        return None
    return to_out, sum(b - a for a, b in keep)


def _shift_items(e: dict, off: float) -> None:
    """Move timed items `off` seconds earlier (dropping what ends before 0)."""
    if off <= 1e-3:
        return
    for key in ("titles", "broll", "fxclips"):
        out = []
        for it in e.get(key) or []:
            if not isinstance(it, dict):
                continue
            s, en = float(it.get("start", 0)) - off, float(it.get("end", 0)) - off
            if en <= 0.05:
                continue
            if s < 0 and (key == "fxclips" or compose.is_pro(it)):
                it = compose.advance(it, -s) if key == "broll" else {
                    **it, "kf": {k: compose._shift_pts(compose.K.normalize(v), -s) for k, v in (it.get("kf") or {}).items()}}
            out.append({**it, "start": round(max(0.0, s), 3), "end": round(en, 3)})
        e[key] = out
    sfx = []
    for s in e.get("sfx") or []:
        if not isinstance(s, dict):
            continue
        at = float(s.get("at", 0)) - off
        it = {**s, "at": round(max(0.0, at), 3)}
        if at < 0:
            dur = float(s.get("dur", 0) or 0)
            if dur and dur + at <= 0.05:
                continue
            it["trim"] = round(float(s.get("trim", 0) or 0) - at, 3)
            if dur:
                it["dur"] = round(dur + at, 3)
        sfx.append(it)
    e["sfx"] = sfx


def _fx_clips(e: dict, w: int, h: int, fps: float, dur: float, cur: str, chains: list[str]) -> str:
    """Effect / filter clips from the timeline's FX tracks: the effect is computed only for its own
    time range and laid over the picture there (other frames pass through untouched)."""
    hidden = set(e.get("hidden_tracks") or [])
    for i, c in enumerate(e.get("fxclips") or []):
        if not isinstance(c, dict) or c.get("enabled") is False or f"fx:{int(c.get('track', 0) or 0)}" in hidden:
            continue
        s, en = max(0.0, float(c.get("start", 0))), min(dur, float(c.get("end", 0)))
        if en - s < 1.0 / fps:
            continue
        if c.get("kind") == "filter":
            chain = catalog.grade_filter(c.get("grade"))
        else:
            chain = catalog.stack_filter([{"id": c.get("id"), "params": c.get("params") or {}, "kf": c.get("kf"), "enabled": True}],
                                         w, h, fps, en - s)
        if not chain:
            continue
        chain = re.sub(r"\[([A-Za-z]\w*)\]", lambda m: f"[{m.group(1)}_c{i}]", chain)
        chains.append(f"{cur}split[fxm{i}][fxs{i}];"
                      f"[fxs{i}]trim=start={s:.3f}:end={en:.3f},setpts=PTS-STARTPTS,{chain},"
                      f"scale={w}:{h},setsar=1,format=yuv420p,setpts=PTS+{s:.3f}/TB[fxe{i}];"
                      f"[fxm{i}][fxe{i}]overlay=0:0:eof_action=pass:enable='between(t\\,{s:.3f}\\,{en:.3f})'[fxo{i}]")
        cur = f"[fxo{i}]"
    return cur


def render(*, video: Path, audio: Path | None, meta: dict, edl: dict, transcript: dict | None,
           preset: dict, style: dict | None, out_dir: Path, name: str, hook: dict | None = None,
           focus_x: float = 0.5, focus_y: float = 0.5, burn_captions: bool | None = None,
           caption_overrides: dict | None = None, effects: dict | None = None,
           clip: dict | None = None, face_track: str = "auto",
           encoder_preset: str | None = None, on_progress: ProgressFn | None = None,
           export: dict | None = None, seek: float | None = None, video_only: bool = False,
           audio_only: bool = False, boundary_cut: str | None = None, trailing_cut: str | None = None,
           zoom_plan_override: list[tuple[float, float]] | None = None) -> dict:
    """seek / video_only / audio_only / boundary_cut / trailing_cut / zoom_plan_override are used by
    engine/segrender.py, which renders the video in cached ~15 s pieces: `seek` starts decoding the
    source there (timestamps kept), `boundary_cut` is the transition of the cut this piece starts on,
    `trailing_cut` the one it ends on, `zoom_plan_override` the slice of the full video's zoom plan."""
    out_dir.mkdir(parents=True, exist_ok=True)
    e = dict(effects or {})
    if video_only:
        # the sound is rendered once for the whole video — pieces carry no audio at all
        audio = None
        meta = {**meta, "has_audio": False}
        for k in ("music", "sfx", "voice_track_path", "voice_track_words"):
            e.pop(k, None)
        e["voice_track"] = "original"
        e["broll"] = [({**it, "volume": 0} if isinstance(it, dict) else it) for it in (e.get("broll") or [])]
    # items can be limited to some platforms (Subscribe popup only on YouTube, Follow on IG/FB…)
    pid = preset.get("id", "")
    family = "youtube" if pid.startswith("yt") else "instagram" if pid.startswith("ig") else "facebook" if pid.startswith("fb") else pid

    def _for_me(item: dict) -> bool:
        pl = item.get("platforms")
        return not pl or pid in pl or family in pl
    hidden = set(e.get("hidden_tracks") or [])
    lane = {"broll": "broll", "sfx": "audio", "titles": "text"}
    for key in ("broll", "sfx", "titles"):
        if isinstance(e.get(key), list):
            items = [x for x in e[key] if not isinstance(x, dict) or (_for_me(x) and f"{lane[key]}:{int(x.get('track', 0) or 0)}" not in hidden)]
            # higher track = drawn on top (stable within a track)
            e[key] = sorted(items, key=lambda x: int(x.get("track", 0) or 0) if isinstance(x, dict) else 0)
    w, h = int(preset["width"]), int(preset["height"])
    src_fps = float(meta.get("fps") or 30.0)
    fps_max = float(preset.get("video", {}).get("fps_max", 60))
    fps = src_fps if src_fps <= fps_max + 0.5 else fps_max
    fps = round(fps, 3) or 30.0
    # user export overrides (resolution / fps / codec…) — see engine/encode.py
    enc = encode.plan(export, preset, meta, fps)
    w, h, fps = enc["width"], enc["height"], enc["fps"]
    if enc["export"].get("quality") == "draft":
        # the slow pro passes are for the final file
        pro0 = dict(e.get("pro") or {})
        for k in ("denoise", "stabilize", "face_refine"):
            pro0.pop(k, None)
        e["pro"] = pro0
        encoder_preset = "veryfast"

    keep = [(_snap(a, fps), _snap(b, fps)) for a, b in keep_segments(edl)]
    dub_path = e.get("voice_track_path") if e.get("voice_track") not in (None, "", "original") else None
    if dub_path and not Path(dub_path).exists():
        dub_path = None
    if clip and clip.get("end", 0) > clip.get("start", 0):
        # a Short: only the chosen window of the recording (cuts inside it still apply)
        cs, ce = _snap(float(clip["start"]), fps), _snap(float(clip["end"]), fps)
        keep = [(max(a, cs), min(b, ce)) for a, b in keep if b > cs and a < ce]
    keep = [(a, b) for a, b in keep if b - a >= 1 / fps]
    if not keep:
        raise ValueError("कट के बाद कुछ नहीं बचा — कुछ कट बंद करें")
    if clip:
        # text / overlays / sfx / effect clips are timed on the FULL video's output timeline;
        # a Short (or a preview frame) starts somewhere inside it → move them to the Short's own clock
        full_out, _ = out_timeline(edl, fps, effects)
        _shift_items(e, full_out(keep[0][0]) or 0.0)
    seek = _snap(float(seek), fps) if seek else 0.0
    if seek > 0:
        # the source inputs are opened with -ss: their clock starts at `seek`, so every source time used below
        # (kept ranges, cut lookups, the face path) moves by the same amount
        keep = [(_snap(a - seek, fps), _snap(b - seek, fps)) for a, b in keep]
        edl = {**edl, "cuts": [{**c, "start": float(c.get("start", 0)) - seek, "end": float(c.get("end", 0)) - seek}
                               for c in (edl.get("cuts") or []) if isinstance(c, dict)]}
        meta = {**meta, "face_track": [[float(t) - seek, cx] for t, cx in (meta.get("face_track") or [])]}
        if transcript:
            transcript = {**transcript, "segments": [
                {**sg, "start": float(sg.get("start", 0)) - seek, "end": float(sg.get("end", 0)) - seek,
                 "words": [{**wd, "start": float(wd.get("start", 0)) - seek, "end": float(wd.get("end", 0)) - seek}
                           for wd in (sg.get("words") or [])]}
                for sg in (transcript.get("segments") or [])]}
    e_tr_default = (effects or {}).get("transition") or "none"
    segs = _segment_timeline(_plan_segments(keep, edl, e_tr_default, (effects or {}).get("speed") or edl.get("speed")))
    use_segments = any(fx.is_xfade(sg["tr"]) or sg["rate"] != 1.0 for sg in segs)
    if use_segments:
        new_dur = segs[-1]["out_start"] + segs[-1]["out_dur"]
        cuts = [sg["out_start"] for sg in segs[1:] if not fx.is_xfade(sg["tr"])]
        to_out = _src_to_out(segs)
        raw_words = words_of(transcript) if transcript else []
        # a word that starts just inside a cut (or ends on a segment edge) used to vanish here;
        # map_words keeps every mostly-kept word
        words = map_words([{**wd, "end": min(wd["end"], wd["start"] + 3)} for wd in raw_words],
                          [(sg["a"], sg["b"]) for sg in segs],
                          lambda t: to_out(t) if to_out(t) is not None else to_out(t - 1e-3))
    else:
        new_dur = sum(b - a for a, b in keep)
        cuts = _cut_points(keep)
        words = remap_words(words_of(transcript), keep) if transcript else []
    dub_offset = 0.0
    if dub_path:
        # the dub is timed on the full video's output timeline; a Short starts somewhere inside it
        if clip:
            full_out, _ = out_timeline(edl, fps, effects)
            dub_offset = max(0.0, full_out(keep[0][0]) or 0.0)
        dub_words = e.get("voice_track_words")
        if isinstance(dub_words, list) and dub_words:
            # captions follow what is actually heard (translated / re-voiced text)
            words = [{**wd, "start": max(0.0, round(float(wd["start"]) - dub_offset, 3)), "end": round(float(wd["end"]) - dub_offset, 3)}
                     for wd in dub_words if float(wd["end"]) - dub_offset > 0 and float(wd["start"]) - dub_offset < new_dur]
    style = resolve_style(style, caption_overrides) if style else style
    burn = preset.get("burn_captions", True) if burn_captions is None else burn_captions
    work = out_dir / f".{name}"
    work.mkdir(exist_ok=True)
    # pro tools that must see the uncut source (stabilise, face refine) — no-op when off
    tap = protools.source_tap(e, video, meta, work, max(b for _, b in keep), need_from=min(a for a, _ in keep),
                              preview=bool(clip) and float(clip.get("end", 0)) - float(clip.get("start", 0)) < 1.0)

    seek_args = ["-ss", f"{seek:.3f}"] if seek > 0 else []
    inputs: list[str] = [*seek_args, "-i", str(video)]
    next_in = 1
    chains: list[str] = []

    # ---- video base: cuts → frame fit → zoom → look → flash
    sel = _select_expr(keep, fps)
    seg_audio_label = None
    body = (e.get("body") or {}) if e.get("body", {}).get("enabled") and e.get("body", {}).get("alpha_path") else None
    src_w0, src_h0 = int(meta.get("width", w)), int(meta.get("height", h))
    if body:
        inputs += [*seek_args, "-i", str(body["alpha_path"])]
        body_alpha_in = next_in
        next_in += 1
        extra_in = {}
        for key in ("bg_image", "bg_video"):
            if body.get(key + "_path"):
                if key == "bg_image":
                    inputs += ["-loop", "1", "-i", str(body[key + "_path"])]
                else:
                    inputs += ["-stream_loop", "-1", "-i", str(body[key + "_path"])]
                extra_in[key] = next_in
                next_in += 1
    if use_segments:
        # trim/concat/xfade path: real transitions and speed ramps
        a_src = "[1:a]" if audio is not None else ("[0:a]" if meta.get("has_audio") else None)
        if audio is not None:
            inputs += [*seek_args, "-i", str(audio)]
            next_in += 1
        next_in = tap.attach(inputs, chains, next_in, len(segs))
        vlabels, alabels, mlabels = [], [], []
        for i, sg in enumerate(segs):
            chains.append(f"{tap.label(i)}trim=start={sg['a']:.3f}:end={sg['b']:.3f},setpts=(PTS-STARTPTS)/{sg['rate']:.4f},"
                          f"{protools.warp_main(e, sg['rate'], fps)}fps={fps},settb=AVTB,format=yuv420p[sv{i}]")
            vlabels.append(f"[sv{i}]")
            if body:
                chains.append(f"[{body_alpha_in}:v]extractplanes=y,scale={src_w0}:{src_h0},trim=start={sg['a']:.3f}:end={sg['b']:.3f},"
                              f"setpts=(PTS-STARTPTS)/{sg['rate']:.4f},fps={fps},settb=AVTB,format=gray[sm{i}]")
                mlabels.append(f"[sm{i}]")
            if a_src:
                chains.append(f"{a_src}atrim=start={sg['a']:.3f}:end={sg['b']:.3f},asetpts=PTS-STARTPTS,"
                              f"{_atempo(sg['rate'])},aformat=sample_rates=48000:channel_layouts=mono[sa{i}]")
                alabels.append(f"[sa{i}]")
        cur_v, cur_a = vlabels[0], (alabels[0] if alabels else None)
        cur_m = mlabels[0] if body else None
        acc = segs[0]["out_dur"]
        for i in range(1, len(segs)):
            sg = segs[i]
            if fx.is_xfade(sg["tr"]):
                d = acc - sg["out_start"]  # overlap length
                chains.append(f"{cur_v}{vlabels[i]}xfade=transition={sg['tr'][2:]}:duration={d:.3f}:offset={sg['out_start']:.3f},settb=AVTB[xv{i}]")
                cur_v = f"[xv{i}]"
                if body:
                    chains.append(f"{cur_m}{mlabels[i]}xfade=transition=fade:duration={d:.3f}:offset={sg['out_start']:.3f},settb=AVTB[xm{i}]")
                    cur_m = f"[xm{i}]"
                if cur_a:
                    chains.append(f"{cur_a}{alabels[i]}acrossfade=d={d:.3f}:c1=tri:c2=tri[xa{i}]")
                    cur_a = f"[xa{i}]"
            else:
                chains.append(f"{cur_v}{vlabels[i]}concat=n=2:v=1:a=0,settb=AVTB[xv{i}]")
                cur_v = f"[xv{i}]"
                if body:
                    chains.append(f"{cur_m}{mlabels[i]}concat=n=2:v=1:a=0,settb=AVTB[xm{i}]")
                    cur_m = f"[xm{i}]"
                if cur_a:
                    chains.append(f"{cur_a}{alabels[i]}concat=n=2:v=0:a=1[xa{i}]")
                    cur_a = f"[xa{i}]"
            acc = sg["out_start"] + sg["out_dur"]
        if body:
            chains.append(f"{cur_v}setpts=PTS-STARTPTS[vseg0]")
            chains.append(f"{cur_m}setpts=PTS-STARTPTS[mseg]")
            chains.extend(_body(body, src_w0, src_h0, "[vseg0]", "[mseg]", "[vseg]", extra_in, work, e, new_dur, src_fps))
        else:
            chains.append(f"{cur_v}setpts=PTS-STARTPTS[vseg]")
        if cur_a:
            chains.append(f"{cur_a}asetpts=PTS-STARTPTS[voice]")
            seg_audio_label = "[voice]"
    src_w, src_h = int(meta.get("width", w)), int(meta.get("height", h))
    track_cmds = None
    kf = meta.get("face_track") or []
    if face_track != "off" and kf and preset.get("fit") == "crop" and src_w / src_h > w / h:
        from .facetrack import crop_commands
        factor = max(w / src_w, h / src_h)
        scaled_w = int(round(src_w * factor))

        if use_segments:
            to_out_fn = _src_to_out(segs)
        else:
            def to_out_fn(t: float) -> float | None:
                o = 0.0
                for a, b in keep:
                    if a <= t < b:
                        return o + (t - a)
                    o += b - a
                return None

        track_cmds = work / "face.cmd"
        track_cmds.write_text(crop_commands(kf, scaled_w, w, to_out_fn, focus_x), encoding="utf-8")
    tf = e.get("transform") or {}
    pre_tf, src_w, src_h = fx.transform_pre(tf, src_w, src_h)
    if pre_tf and (tf.get("crop") or int(tf.get("rotate", 0) or 0) % 360):
        track_cmds = None  # the face track was measured on the uncropped picture
    frame = (pre_tf + "," if pre_tf else "") + _frame_filter(src_w, src_h, w, h, preset.get("fit", "crop"), focus_x, focus_y, track_cmds)
    pro_pre = protools.pre_grade(e, work)  # denoise + colour wheels/curves/HSL/match LUT
    if pro_pre:
        frame += "," + pro_pre
    post_tf = protools.transform_kf(tf, w, h, fps, new_dur, work) or fx.transform_post(tf, w, h)
    if post_tf:
        frame += "," + post_tf
    if not use_segments:
        next_in = tap.attach(inputs, chains, next_in, 1)
    if body and not use_segments:
        chains.append(f"{tap.label(0)}fps={fps},select='{sel}',setpts=N/({fps})/TB[vcut0]")
        chains.append(f"[{body_alpha_in}:v]extractplanes=y,scale={src_w0}:{src_h0},fps={fps},select='{sel}',setpts=N/({fps})/TB,format=gray[mcut]")
        chains.extend(_body(body, src_w0, src_h0, "[vcut0]", "[mcut]", "[vseg]", extra_in, work, e, new_dur, src_fps))
        v = f"[vseg]{frame}"
    else:
        v = (f"[vseg]{frame}" if use_segments else f"{tap.label(0)}fps={fps},select='{sel}',setpts=N/({fps})/TB,{frame}")
    # transitions: per-cut kind (edl cut.transition) or the global default
    default_tr = e.get("transition") or ("flash" if e.get("flash") else "none")
    tr_cuts = []
    if use_segments:
        for sg in segs[1:]:
            if sg["tr"] and sg["tr"] != "none" and not fx.is_xfade(sg["tr"]):
                tr_cuts.append((sg["out_start"], sg["tr"]))
    else:
        for t, (a, b) in zip(cuts, keep[1:]):
            kind = default_tr
            for cdef in (edl.get("cuts") or []):
                if cdef.get("enabled", True) and abs(float(cdef.get("end", -1)) - a) < 0.08 and cdef.get("transition"):
                    kind = cdef["transition"]
            if kind and kind != "none" and not fx.is_xfade(kind):
                tr_cuts.append((t, kind))
    if boundary_cut and boundary_cut != "none" and not fx.is_xfade(boundary_cut):
        tr_cuts.insert(0, (0.0, boundary_cut))
    if trailing_cut and trailing_cut != "none" and not fx.is_xfade(trailing_cut):
        tr_cuts.append((new_dur, trailing_cut))  # only the leading half of that transition falls inside this piece
    bump, tr_filters = fx.transition_filters(tr_cuts, new_dur)
    zoom = e.get("zoom") or {}
    emph = None
    if zoom.get("enabled") and zoom.get("mode") == "emphasis" and words:
        from .shorts import HOOK_WORDS
        import re as _re
        emph = [wd["start"] for wd in words if _re.sub(r"[^\w]", "", wd["w"].lower()) in HOOK_WORDS or wd["w"].rstrip().endswith("!")]
    if zoom_plan_override is not None:
        plan = list(zoom_plan_override) or [(0.0, 1.0)]
    else:
        plan = (fx.zoom_plan(cuts, new_dur, float(zoom.get("strength", 1.0)), mode=zoom.get("mode") or "punch", emphasis=emph)
                if zoom.get("enabled") else [(0.0, 1.0)])
    if len(plan) > 1 or bump:
        v += "," + fx.zoom_filter(plan, w, h, fx=0.5, fy=min(0.9, max(0.1, focus_y)), bump=bump)
    look = fx.look_filter(e.get("look"), Path(e["lut_path"]) if e.get("lut_path") else None, e.get("lut_amount"))
    if look:
        v += "," + look
    grade = catalog.grade_filter(e.get("grade"))
    if grade:
        v += "," + grade
    extras = fx.extras_filter([x for x in (e.get("extras") or []) if isinstance(x, str)])
    if extras:
        v += "," + extras
    # separate color_pop from normal stack (it needs the alpha matte, not a simple filter chain)
    raw_stack = e.get("stack") or []
    has_color_pop = any(isinstance(s, dict) and s.get("id") == "color_pop" and s.get("enabled", True) for s in raw_stack)
    normal_stack = [s for s in raw_stack if not (isinstance(s, dict) and s.get("id") == "color_pop")]
    stack = catalog.stack_filter(normal_stack, w, h, fps, new_dur)
    if stack:
        v += "," + stack
    pro_post = protools.post_grade(e)  # sharpen (cas / unsharp)
    if pro_post:
        v += "," + pro_post
    if tr_filters:
        v += "," + tr_filters
    mmask = protools.main_mask(e, w, h, fps, new_dur, work)
    if mmask:
        inputs += mmask[0]
        v += "," + mmask[1].replace("{IN0}", str(next_in))
        next_in += 1
    # Color Pop: person in full color, background B&W — requires alpha matte
    if has_color_pop and body:
        v += "[cpvin]"
        chains.append(v)
        cp_alpha = f"[{body_alpha_in}:v]"
        cp_chains = fx.color_pop_filter(cp_alpha, "[cpvin]", "[vbase]")
        chains.extend(cp_chains)
    elif has_color_pop and not body:
        # no matte available — fall back to simple desaturate (still useful, just not person-aware)
        v += ",eq=saturation=0.15[vbase]"
        chains.append(v)
    else:
        v += "[vbase]"
        chains.append(v)
    # morph cuts: smooth jump cuts (optical-flow frames across the cut), output timeline
    seg_bounds = [sg["out_start"] for sg in segs[1:]] if use_segments else cuts
    cur = protools.morph_graph(protools.morph_points(e, edl, keep, segs, use_segments, cuts), e, fps, new_dur,
                               "[vbase]", chains, seg_bounds=seg_bounds)
    cur = _fx_clips(e, w, h, fps, new_dur, cur, chains)

    # ---- B-roll / image overlays
    pro_audio: list[tuple[str, str]] = []
    broll_items, tr_notes = compose.apply_transitions(e.get("broll") or [])
    for n_ in tr_notes:
        logging.getLogger("vividora.render").warning(n_)
    from .layout import layout_filter as smart_layout_filter
    for i, item in enumerate(broll_items):
        path = item.get("path")
        if not path or float(item.get("end", 0)) <= float(item.get("start", 0)):
            continue
        if compose.is_pro(item):
            # speed / ramps / trim / per-clip colour+effects / masks / blend modes / keyframes / own audio
            p_args, p_chains, next_in, p_audio = compose.wire(compose.build(item, i, w, h, fps, cur, work), next_in)
            inputs += p_args
            chains.extend(p_chains)
            cur = f"[vo{i}]"
            if p_audio:
                pro_audio.append(p_audio)
            continue
        # Smart Layout: try pip / split / behind / overlay before falling back to fullscreen
        inputs += fx.overlay_input_args(item, Path(path))
        smart_f = smart_layout_filter(item, next_in, w, h, cur, f"[vo{i}]", i,
                                      main_alpha_index=body_alpha_in if body else None)
        if smart_f is not None:
            chains.append(smart_f)
            cur = f"[vo{i}]"
            next_in += 1
            continue
        a_idx = None
        if item.get("cutout") and item.get("alpha_path") and item.get("type") != "image" and Path(item["alpha_path"]).exists():
            # "सिर्फ़ इंसान": the clip's cached person matte (engine/matting.py, job matte_lib) as its alpha
            inputs += fx.overlay_input_args(item, Path(item["alpha_path"]))
            a_idx = next_in + 1
        chains.append(fx.overlay_filter(item, next_in, w, h, cur, f"[vo{i}]", i, alpha_index=a_idx))
        cur = f"[vo{i}]"
        next_in += 2 if a_idx is not None else 1

    # ---- frame / border overlay (full-frame PNG with transparency)
    fr = e.get("frame") or {}
    if fr.get("path"):
        inputs += ["-loop", "1", "-i", str(fr["path"])]
        chains.append(f"[{next_in}:v]scale={w}:{h},format=rgba,colorchannelmixer=aa={float(fr.get('opacity', 1.0)):.2f}[frm];"
                      f"{cur}[frm]overlay=0:0:shortest=1[vfr]")
        cur = "[vfr]"
        next_in += 1
    # ---- watermark
    wm = e.get("watermark") or {}
    if wm.get("path"):
        inputs += ["-i", str(wm["path"])]
        chains.append(fx.watermark_filter(next_in, w, h, cur, "[vwm]", float(wm.get("opacity", 0.75)),
                                          float(wm.get("size", 0.14)), wm.get("pos", "tr"),
                                          x=float(wm["x"]) if wm.get("x") is not None else None,
                                          y=float(wm["y"]) if wm.get("y") is not None else None,
                                          rotate=float(wm.get("rotate", 0))))
        cur = "[vwm]"
        next_in += 1

    # ---- captions + hook + titles (one ASS file)
    titles = [t for t in (e.get("titles") or []) if t.get("text") and not (t.get("behind") and body)]
    has_text = (burn and words and style) or (hook and hook.get("text")) or titles
    tail = ""
    if has_text:
        t_style, t_events = fx.title_events(titles, w, h, (style or {}).get("font", "Poppins")) if titles else ("", [])
        ass = work / "captions.ass"
        ass.write_text(
            build_ass(words if (burn and style) else [], style or {}, w, h,
                      margin_v_ratio=float(preset.get("caption_margin_v", 0.2)),
                      scale=float(preset.get("caption_scale", 1.0)), hook=hook, duration=new_dur,
                      extra_styles=[t_style] if t_style else None, extra_events=t_events),
            encoding="utf-8",
        )
        # ass + complex shaping: HarfBuzz places Devanagari matras (ि, र्) correctly
        sub = f"ass=filename='{ffmpeg.escape_filter_path(ass)}':shaping=complex"
        fdir = fonts_with([Path(x) for x in (e.get("font_paths") or [])], work)
        if fdir.exists():
            sub += f":fontsdir='{ffmpeg.escape_filter_path(fdir)}'"
        tail += f"{sub},"
    chains.append(f"{cur}{tail}format=yuv420p[v]")
    maps = ["-map", "[v]"]
    if audio_only:
        chains.append("[v]nullsink")
        maps = []

    # ---- audio: voice (cut) → music duck → sfx → loudnorm
    a_cfg = preset.get("audio", {})
    has_orig = bool(seg_audio_label) or (not use_segments and (audio is not None or bool(meta.get("has_audio"))))
    dub_mode = "both" if (dub_path and has_orig and e.get("voice_track_mode") == "both") else "replace"
    if (has_orig or dub_path) and not video_only:
        cur_a = None
        if has_orig and not (dub_path and dub_mode == "replace"):
            if not use_segments:
                if audio is not None:
                    inputs += [*seek_args, "-i", str(audio)]
                    a_in = f"[{next_in}:a]"
                    next_in += 1
                else:
                    a_in = "[0:a]"
                chains.append(f"{a_in}aselect='{sel}',asetpts=N/SR/TB,aformat=sample_rates=48000:channel_layouts=mono[voice]")
            cur_a = "[voice]"
            vchain = fx.voice_chain(e.get("voice"), new_dur)
            if vchain:
                chains.append(f"[voice]{vchain}[voicefx]")
                cur_a = "[voicefx]"
        elif seg_audio_label:
            chains.append(f"{seg_audio_label}anullsink")  # the cut original is not heard
        if dub_path:
            # AI voice-over / dub: already timed + loudness-normalised; pad/trim to this video
            inputs += ["-i", str(dub_path)]
            chains.append(f"[{next_in}:a]aformat=sample_rates=48000:channel_layouts=mono,atrim=start={dub_offset:.3f},"
                          f"asetpts=PTS-STARTPTS,apad,atrim=0:{new_dur:.3f}[dubv]")
            next_in += 1
            if cur_a:
                under = max(0.0, min(1.0, float(e.get("voice_track_under", 0.25) or 0)))
                chains.append(f"{cur_a}volume={under:.3f}[vunder];[dubv][vunder]amix=inputs=2:duration=first:"
                              f"dropout_transition=0:normalize=0[vdub]")
                cur_a = "[vdub]"
            else:
                cur_a = "[dubv]"
        # SFX clips marked "बोलते समय धीमा" are side-chained against the voice (before music joins it)
        ducked = [i for i, s_ in enumerate(e.get("sfx") or []) if s_.get("path") and s_.get("duck")
                  and fx.track_gain(e, f"audio:{int(s_.get('track', 0) or 0)}") > 0.001]
        if ducked and cur_a:
            chains.append(f"{cur_a}asplit={1 + len(ducked)}[avoice]" + "".join(f"[vsc{i}]" for i in ducked))
            cur_a = "[avoice]"
        else:
            ducked = []
        music = e.get("music") or {}
        if music.get("path") and music.get("fit"):
            # remix the song to the video length, ending on a bar (engine/musicfit.py)
            from .musicfit import fit_file
            music = {**music, "path": str(fit_file(Path(music["path"]), new_dur, work))}
        if music.get("path"):
            inputs += ["-stream_loop", "-1", "-i", str(music["path"])]
            chain, cur_a = fx.music_chain(cur_a, next_in, volume=float(music.get("volume", 0.18)),
                                          duck=bool(music.get("duck", True)), duration=new_dur,
                                          fade=float(music.get("fade", 1.5)), duck_amount=float(music.get("duck_amount", 0.6)))
            chains.append(chain)
            next_in += 1
        g1 = fx.track_gain(e, "audio")  # lane A1: voice + AI voice-over + music
        if abs(g1 - 1.0) > 1e-3:
            chains.append(f"{cur_a}volume={g1:.3f}[a1g]")
            cur_a = "[a1g]"
        sfx_labels = []
        for i, s in enumerate(e.get("sfx") or []):
            if not s.get("path"):
                continue
            gk = fx.track_gain(e, f"audio:{int(s.get('track', 0) or 0)}")
            if gk <= 0.001:
                continue
            inputs += ["-i", str(s["path"])]
            ms = int(float(s.get("at", 0)) * 1000)
            trim, dur = float(s.get("trim", 0) or 0), float(s.get("dur", 0) or 0)
            clip = f"atrim=start={trim:.3f}" + (f":duration={dur:.3f}" if dur > 0 else "") + ",asetpts=PTS-STARTPTS," if (trim or dur) else ""
            fades = ""
            if float(s.get("fade_in", 0) or 0) > 0:
                fades += f"afade=t=in:d={float(s['fade_in']):.2f},"
            if float(s.get("fade_out", 0) or 0) > 0 and dur > 0:
                fades += f"afade=t=out:st={max(0.0, dur - float(s['fade_out'])):.3f}:d={float(s['fade_out']):.2f},"
            if i in ducked:
                chains.append(f"[{next_in}:a]{clip}aformat=sample_rates=48000:channel_layouts=mono,{fades}"
                              f"volume={float(s.get('volume', 0.8)) * gk:.3f},adelay={ms}|{ms}[sfxr{i}];"
                              f"[sfxr{i}][vsc{i}]sidechaincompress=threshold=0.02:ratio=8:attack=15:release=450:makeup=1[sfx{i}]")
            else:
                chains.append(f"[{next_in}:a]{clip}aformat=sample_rates=48000:channel_layouts=mono,{fades}"
                              f"volume={float(s.get('volume', 0.8)) * gk:.3f},adelay={ms}|{ms}[sfx{i}]")
            sfx_labels.append(f"[sfx{i}]")
            next_in += 1
        for a_chain, a_label in pro_audio:  # overlay clips' own sound
            chains.append(a_chain)
            sfx_labels.append(a_label)
        if sfx_labels:
            chains.append(f"{cur_a}{''.join(sfx_labels)}amix=inputs={1 + len(sfx_labels)}:duration=first:"
                          f"dropout_transition=0:normalize=0[asfx]")
            cur_a = "[asfx]"
        target = fx.voice_settings(e.get("voice")).get("loudness") if (e.get("voice") or {}).get("loudness") not in (None, "") else a_cfg.get("loudness", -14)
        tail = fx.voice_tail(e.get("voice"))
        chains.append(f"{cur_a}loudnorm=I={target}:TP={a_cfg.get('true_peak', -1.5)}:LRA=11,"
                      f"aresample=48000{',' + tail if tail else ''}[a]")
        maps += ["-map", "[a]"]

    script = work / "filter.txt"
    script.write_text(";\n".join(chains), encoding="utf-8")

    vcfg = preset.get("video", {})
    out = out_dir / f"{name}.{enc['container']}"
    gop = max(1, int(math.ceil(fps * 2)))
    # ── memory-aware preset + x264/x265 thread limits ──────────────────
    from . import hwaccel
    _enc_preset = encoder_preset
    if enc["preset_arg_ok"] and not _enc_preset:
        _enc_preset = hwaccel.smart_preset(None, enc["codec"])
    speed: list[str] = []
    if enc["preset_arg_ok"] and _enc_preset:
        speed = ["-preset", _enc_preset]
    # Limit encoder-internal threads to prevent RAM spikes
    if enc["codec"] == "h264":
        speed += ["-x264-params", hwaccel.x264_thread_args()]
    elif enc["codec"] == "h265":
        # x265-params may already exist in vargs from encode.plan(); append
        existing = ""
        for i, a in enumerate(enc["vargs"]):
            if a == "-x265-params" and i + 1 < len(enc["vargs"]):
                existing = enc["vargs"][i + 1]
                break
        pool_args = hwaccel.x265_pool_args()
        if existing:
            # Replace the existing x265-params with the merged version
            for i, a in enumerate(enc["vargs"]):
                if a == "-x265-params" and i + 1 < len(enc["vargs"]):
                    enc["vargs"][i + 1] = f"{existing}:{pool_args}"
                    break
        else:
            speed += ["-x265-params", pool_args]
    ts_args: list[str] = []
    label = f"{preset.get('label', name)} रेंडर"
    if audio_only:
        if "-map" not in maps:
            import shutil as _sh
            _sh.rmtree(work, ignore_errors=True)
            return {"files": [], "duration": round(new_dur, 2), "warnings": [], "audio": None}
        out = out_dir / f"{name}.{'webm' if enc['export']['audio_codec'] == 'opus' else 'm4a'}"
        ffmpeg.run([*inputs, *ts_args, "-filter_complex_script", str(script), *maps, "-vn", *enc["aargs"], "-t", f"{new_dur:.3f}", str(out)],
                   duration=new_dur, on_progress=on_progress, label=label + " (आवाज़)", is_heavy=True)
        import shutil as _sh
        _sh.rmtree(work, ignore_errors=True)
        return {"files": [], "duration": round(new_dur, 2), "warnings": [], "audio": out}
    base = [*inputs, *ts_args, "-filter_complex_script", str(script), *maps, *enc["vargs"], *speed, "-g", str(gop)]
    if video_only:
        # a piece: exact frame count, keyframe first, no audio; the pieces are later joined without re-encoding
        frames = max(1, int(round(new_dur * fps)))
        ffmpeg.run([*base, "-an", "-frames:v", str(frames), "-force_key_frames", "0", *enc["extra"], str(out)],
                   duration=new_dur, on_progress=on_progress, label=label, is_heavy=True)
        import shutil as _sh
        _sh.rmtree(work, ignore_errors=True)
        return {"files": [{"kind": "render", "path": out, "mime": enc["mime"], "label": preset["id"], "meta": {"frames": frames}}],
                "duration": round(new_dur, 2), "warnings": [], "fps": fps, "frames": frames}
    if enc["two_pass"]:
        # target-bitrate mode: a first pass only measures, the second one writes
        passlog = str(work / "pass")
        ffmpeg.run([*base, "-pass", "1", "-passlogfile", passlog, "-an", "-t", f"{new_dur:.3f}", "-f", "null", "/dev/null"],
                   duration=new_dur, on_progress=(lambda f, m: on_progress(f * 0.5, m + " (pass 1)")) if on_progress else None, label=label, is_heavy=True)
        ffmpeg.run([*base, "-pass", "2", "-passlogfile", passlog, *enc["aargs"], *enc["extra"], "-t", f"{new_dur:.3f}", str(out)],
                   duration=new_dur, on_progress=(lambda f, m: on_progress(0.5 + f * 0.5, m + " (pass 2)")) if on_progress else None, label=label, is_heavy=True)
    else:
        ffmpeg.run([*base, *enc["aargs"], *enc["extra"], "-t", f"{new_dur:.3f}", str(out)],
                   duration=new_dur, on_progress=on_progress, label=label, is_heavy=True)

    files = [{"kind": "render", "path": out, "mime": enc["mime"], "label": preset["id"],
              "meta": {"preset": preset["id"], "width": w, "height": h, "duration": round(new_dur, 2),
                       "fps": fps, "codec": enc["codec"], "container": enc["container"],
                       "export": enc["export"] if export else None, "captions": style.get("id") if (burn and style) else None,
                       "clip": clip, "face_track": track_cmds is not None, "segments": len(segs) if use_segments else None,
                       "pro": tap.notes or None,
                       "effects": {"zoom": bool(zoom.get("enabled")), "look": e.get("look") or None,
                                   "music": bool((e.get("music") or {}).get("path")),
                                   "broll": len(e.get("broll") or []), "titles": len(titles),
                                   "watermark": bool(wm.get("path")),
                                   "voice_track": e.get("voice_track") if dub_path else "original",
                                   "voice_track_mode": dub_mode if dub_path else None}}}]
    if preset.get("sidecar_srt") and words:
        srt = out_dir / f"{name}.srt"
        srt.write_text(build_srt(words), encoding="utf-8")
        files.append({"kind": "subtitle", "path": srt, "mime": "application/x-subrip",
                      "label": preset["id"], "meta": {"preset": preset["id"]}})

    warnings = []
    max_s = preset.get("max_seconds")
    if max_s and new_dur > max_s:
        warnings.append(f"{preset.get('label')}: वीडियो {new_dur:.0f}s है, सीमा {max_s}s — upload नहीं होगा")
    rec = preset.get("recommended_seconds")
    if rec and new_dur > rec and not (max_s and new_dur > max_s):
        warnings.append(f"{preset.get('label')}: {rec}s से छोटा रखने पर reach अच्छी रहती है")
    import shutil as _sh
    _sh.rmtree(work, ignore_errors=True)
    return {"files": files, "duration": round(new_dur, 2), "warnings": warnings}
