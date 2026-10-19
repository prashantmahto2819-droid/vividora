"""Turn the original recording + cut list + captions into a finished video for one platform."""

from __future__ import annotations

import math
from pathlib import Path

from . import ffmpeg
from .autocut import keep_segments, remap_words, words_of
from .captions import build_ass, build_srt
from .ffmpeg import ProgressFn

FONTS_DIR = Path(__file__).resolve().parent.parent.parent / "fonts"


def _snap(t: float, fps: float) -> float:
    return round(t * fps) / fps


def _select_expr(keep: list[tuple[float, float]], fps: float) -> str:
    # half a frame of tolerance so each kept piece has an exact number of frames;
    # audio uses the same snapped times, so lips stay in sync after many cuts
    eps = 0.5 / fps
    return "+".join(f"gte(t\\,{a - eps:.4f})*lt(t\\,{b - eps:.4f})" for a, b in keep)


def _frame_filter(src_w: int, src_h: int, w: int, h: int, fit: str, focus_x: float, focus_y: float) -> str:
    src_ratio, dst_ratio = src_w / max(1, src_h), w / h
    if abs(src_ratio - dst_ratio) / dst_ratio < 0.02:
        return f"scale={w}:{h}:flags=lanczos,setsar=1"
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


def render(*, video: Path, audio: Path | None, meta: dict, edl: dict, transcript: dict | None,
           preset: dict, style: dict | None, out_dir: Path, name: str, hook: dict | None = None,
           focus_x: float = 0.5, focus_y: float = 0.5, burn_captions: bool | None = None,
           encoder_preset: str | None = None, on_progress: ProgressFn | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    w, h = int(preset["width"]), int(preset["height"])
    src_fps = float(meta.get("fps") or 30.0)
    fps_max = float(preset.get("video", {}).get("fps_max", 60))
    fps = src_fps if src_fps <= fps_max + 0.5 else fps_max
    fps = round(fps, 3) or 30.0

    keep = [(_snap(a, fps), _snap(b, fps)) for a, b in keep_segments(edl)]
    keep = [(a, b) for a, b in keep if b - a >= 1 / fps]
    if not keep:
        raise ValueError("कट के बाद कुछ नहीं बचा — कुछ कट बंद करें")
    new_dur = sum(b - a for a, b in keep)

    words = remap_words(words_of(transcript), keep) if transcript else []
    burn = preset.get("burn_captions", True) if burn_captions is None else burn_captions
    work = out_dir / f".{name}"
    work.mkdir(exist_ok=True)

    sel = _select_expr(keep, fps)
    frame = _frame_filter(int(meta.get("width", w)), int(meta.get("height", h)), w, h,
                          preset.get("fit", "crop"), focus_x, focus_y)
    vchain = f"[0:v]fps={fps},select='{sel}',setpts=N/({fps})/TB,{frame}"
    has_text = (burn and words and style) or (hook and hook.get("text"))
    if has_text:
        ass = work / "captions.ass"
        ass.write_text(
            build_ass(words if (burn and style) else [], style or {}, w, h,
                      margin_v_ratio=float(preset.get("caption_margin_v", 0.2)),
                      scale=float(preset.get("caption_scale", 1.0)), hook=hook, duration=new_dur),
            encoding="utf-8",
        )
        sub = f"subtitles=filename='{ffmpeg.escape_filter_path(ass)}'"
        if FONTS_DIR.exists():
            sub += f":fontsdir='{ffmpeg.escape_filter_path(FONTS_DIR)}'"
        vchain += f",{sub}"
    vchain += ",format=yuv420p[v]"

    inputs = ["-i", str(video)]
    chains = [vchain]
    maps = ["-map", "[v]"]
    a_cfg = preset.get("audio", {})
    if audio is not None or meta.get("has_audio"):
        if audio is not None:
            inputs += ["-i", str(audio)]
            a_in = "[1:a]"
        else:
            a_in = "[0:a]"
        chains.append(
            f"{a_in}aselect='{sel}',asetpts=N/SR/TB,"
            f"loudnorm=I={a_cfg.get('loudness', -14)}:TP={a_cfg.get('true_peak', -1.5)}:LRA=11,"
            f"aresample=48000[a]"
        )
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
                       "fps": fps, "captions": style.get("id") if (burn and style) else None}}]
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
