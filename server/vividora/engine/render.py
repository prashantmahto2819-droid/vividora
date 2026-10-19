"""Turn the original recording + cut list + captions + effects into a finished
video for one platform.

`effects` (already resolved by the worker: library ids → local paths):
  zoom      {enabled, strength}            auto punch-in at every cut
  look      colour look id                 lut_path: a .cube file instead
  flash     bool                           white flash on cuts
  music     {path, volume, duck}           background music, ducked under speech
  broll     [{path, type: video|image, start, end, fit: cover|pip, pos}]
  titles    [{start, end, text, pos, size, color, bg}]
  watermark {path, opacity, size, pos}
  sfx       [{path, at, volume}]
Times are on the output (post-cut) timeline.
"""

from __future__ import annotations

import math
from pathlib import Path

from . import effects as fx
from . import ffmpeg
from .autocut import keep_segments, remap_words, words_of
from .captions import build_ass, build_srt, resolve_style
from .ffmpeg import ProgressFn

FONTS_DIR = Path(__file__).resolve().parent.parent.parent / "fonts"


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


def _cut_points(keep: list[tuple[float, float]]) -> list[float]:
    """Output-timeline times where a jump cut happens."""
    pts, t = [], 0.0
    for a, b in keep:
        t += b - a
        pts.append(t)
    return pts[:-1]


def render(*, video: Path, audio: Path | None, meta: dict, edl: dict, transcript: dict | None,
           preset: dict, style: dict | None, out_dir: Path, name: str, hook: dict | None = None,
           focus_x: float = 0.5, focus_y: float = 0.5, burn_captions: bool | None = None,
           caption_overrides: dict | None = None, effects: dict | None = None,
           clip: dict | None = None, face_track: str = "auto",
           encoder_preset: str | None = None, on_progress: ProgressFn | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    e = effects or {}
    w, h = int(preset["width"]), int(preset["height"])
    src_fps = float(meta.get("fps") or 30.0)
    fps_max = float(preset.get("video", {}).get("fps_max", 60))
    fps = src_fps if src_fps <= fps_max + 0.5 else fps_max
    fps = round(fps, 3) or 30.0

    keep = [(_snap(a, fps), _snap(b, fps)) for a, b in keep_segments(edl)]
    if clip and clip.get("end", 0) > clip.get("start", 0):
        # a Short: only the chosen window of the recording (cuts inside it still apply)
        cs, ce = _snap(float(clip["start"]), fps), _snap(float(clip["end"]), fps)
        keep = [(max(a, cs), min(b, ce)) for a, b in keep if b > cs and a < ce]
    keep = [(a, b) for a, b in keep if b - a >= 1 / fps]
    if not keep:
        raise ValueError("कट के बाद कुछ नहीं बचा — कुछ कट बंद करें")
    new_dur = sum(b - a for a, b in keep)
    cuts = _cut_points(keep)

    words = remap_words(words_of(transcript), keep) if transcript else []
    style = resolve_style(style, caption_overrides) if style else style
    burn = preset.get("burn_captions", True) if burn_captions is None else burn_captions
    work = out_dir / f".{name}"
    work.mkdir(exist_ok=True)

    inputs: list[str] = ["-i", str(video)]
    next_in = 1
    chains: list[str] = []

    # ---- video base: cuts → frame fit → zoom → look → flash
    sel = _select_expr(keep, fps)
    src_w, src_h = int(meta.get("width", w)), int(meta.get("height", h))
    track_cmds = None
    kf = meta.get("face_track") or []
    if face_track != "off" and kf and preset.get("fit") == "crop" and src_w / src_h > w / h:
        from .facetrack import crop_commands
        factor = max(w / src_w, h / src_h)
        scaled_w = int(round(src_w * factor))

        def to_out(t: float) -> float | None:
            o = 0.0
            for a, b in keep:
                if a <= t < b:
                    return o + (t - a)
                o += b - a
            return None

        track_cmds = work / "face.cmd"
        track_cmds.write_text(crop_commands(kf, scaled_w, w, to_out, focus_x), encoding="utf-8")
    frame = _frame_filter(src_w, src_h, w, h, preset.get("fit", "crop"), focus_x, focus_y, track_cmds)
    v = f"[0:v]fps={fps},select='{sel}',setpts=N/({fps})/TB,{frame}"
    # transitions: per-cut kind (edl cut.transition) or the global default
    default_tr = e.get("transition") or ("flash" if e.get("flash") else "none")
    tr_cuts = []
    for t, (a, b) in zip(cuts, keep[1:]):
        kind = default_tr
        for cdef in (edl.get("cuts") or []):
            if cdef.get("enabled", True) and abs(float(cdef.get("end", -1)) - a) < 0.08 and cdef.get("transition"):
                kind = cdef["transition"]
        if kind and kind != "none":
            tr_cuts.append((t, kind))
    bump, tr_filters = fx.transition_filters(tr_cuts, new_dur)
    zoom = e.get("zoom") or {}
    plan = fx.zoom_plan(cuts, new_dur, float(zoom.get("strength", 1.0))) if zoom.get("enabled") else [(0.0, 1.0)]
    if len(plan) > 1 or bump:
        v += "," + fx.zoom_filter(plan, w, h, fx=0.5, fy=min(0.9, max(0.1, focus_y)), bump=bump)
    look = fx.look_filter(e.get("look"), Path(e["lut_path"]) if e.get("lut_path") else None)
    if look:
        v += "," + look
    extras = fx.extras_filter([x for x in (e.get("extras") or []) if isinstance(x, str)])
    if extras:
        v += "," + extras
    if tr_filters:
        v += "," + tr_filters
    v += "[vbase]"
    chains.append(v)
    cur = "[vbase]"

    # ---- B-roll / image overlays
    for i, item in enumerate(e.get("broll") or []):
        path = item.get("path")
        if not path or float(item.get("end", 0)) <= float(item.get("start", 0)):
            continue
        inputs += fx.overlay_input_args(item, Path(path))
        chains.append(fx.overlay_filter(item, next_in, w, h, cur, f"[vo{i}]", i))
        cur = f"[vo{i}]"
        next_in += 1

    # ---- watermark
    wm = e.get("watermark") or {}
    if wm.get("path"):
        inputs += ["-i", str(wm["path"])]
        chains.append(fx.watermark_filter(next_in, w, h, cur, "[vwm]", float(wm.get("opacity", 0.75)),
                                          float(wm.get("size", 0.14)), wm.get("pos", "tr")))
        cur = "[vwm]"
        next_in += 1

    # ---- captions + hook + titles (one ASS file)
    titles = [t for t in (e.get("titles") or []) if t.get("text")]
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
        sub = f"subtitles=filename='{ffmpeg.escape_filter_path(ass)}'"
        if FONTS_DIR.exists():
            sub += f":fontsdir='{ffmpeg.escape_filter_path(FONTS_DIR)}'"
        tail += f"{sub},"
    chains.append(f"{cur}{tail}format=yuv420p[v]")
    maps = ["-map", "[v]"]

    # ---- audio: voice (cut) → music duck → sfx → loudnorm
    a_cfg = preset.get("audio", {})
    if audio is not None or meta.get("has_audio"):
        if audio is not None:
            inputs += ["-i", str(audio)]
            a_in = f"[{next_in}:a]"
            next_in += 1
        else:
            a_in = "[0:a]"
        chains.append(f"{a_in}aselect='{sel}',asetpts=N/SR/TB,aformat=sample_rates=48000:channel_layouts=mono[voice]")
        cur_a = "[voice]"
        music = e.get("music") or {}
        if music.get("path"):
            inputs += ["-stream_loop", "-1", "-i", str(music["path"])]
            chain, cur_a = fx.music_chain(cur_a, next_in, volume=float(music.get("volume", 0.18)),
                                          duck=bool(music.get("duck", True)), duration=new_dur)
            chains.append(chain)
            next_in += 1
        sfx_labels = []
        for i, s in enumerate(e.get("sfx") or []):
            if not s.get("path"):
                continue
            inputs += ["-i", str(s["path"])]
            ms = int(float(s.get("at", 0)) * 1000)
            chains.append(f"[{next_in}:a]aformat=sample_rates=48000:channel_layouts=mono,"
                          f"volume={float(s.get('volume', 0.8)):.2f},adelay={ms}|{ms}[sfx{i}]")
            sfx_labels.append(f"[sfx{i}]")
            next_in += 1
        if sfx_labels:
            chains.append(f"{cur_a}{''.join(sfx_labels)}amix=inputs={1 + len(sfx_labels)}:duration=first:"
                          f"dropout_transition=0:normalize=0[asfx]")
            cur_a = "[asfx]"
        chains.append(f"{cur_a}loudnorm=I={a_cfg.get('loudness', -14)}:TP={a_cfg.get('true_peak', -1.5)}:LRA=11,"
                      f"aresample=48000[a]")
        maps += ["-map", "[a]"]

    script = work / "filter.txt"
    script.write_text(";\n".join(chains), encoding="utf-8")

    vcfg = preset.get("video", {})
    out = out_dir / f"{name}.mp4"
    gop = max(1, int(math.ceil(fps * 2)))
    ffmpeg.run(
        [*inputs, "-filter_complex_script", str(script), *maps,
         "-c:v", "libx264", "-preset", encoder_preset or vcfg.get("preset", "medium"),
         "-crf", str(vcfg.get("crf", 20)), "-g", str(gop), "-profile:v", "high",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-movflags", "+faststart", "-t", f"{new_dur:.3f}", str(out)],
        duration=new_dur, on_progress=on_progress, label=f"{preset.get('label', name)} रेंडर",
    )

    files = [{"kind": "render", "path": out, "mime": "video/mp4", "label": preset["id"],
              "meta": {"preset": preset["id"], "width": w, "height": h, "duration": round(new_dur, 2),
                       "fps": fps, "captions": style.get("id") if (burn and style) else None,
                       "clip": clip, "face_track": track_cmds is not None,
                       "effects": {"zoom": bool(zoom.get("enabled")), "look": e.get("look") or None,
                                   "music": bool((e.get("music") or {}).get("path")),
                                   "broll": len(e.get("broll") or []), "titles": len(titles),
                                   "watermark": bool(wm.get("path"))}}}]
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
    for f in work.iterdir():
        f.unlink()
    work.rmdir()
    return {"files": files, "duration": round(new_dur, 2), "warnings": warnings}
