"""Step 1 after upload: inspect the video, clean the voice, make a preview."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from . import ffmpeg
from .ffmpeg import ProgressFn

# Gentle voice cleanup used when DeepFilterNet is not installed:
# cut rumble, reduce steady background noise, even out level a little.
FFMPEG_VOICE_CLEAN = "highpass=f=80,afftdn=nf=-25:tn=1,acompressor=threshold=-21dB:ratio=2.5:attack=5:release=120"


def _deepfilter(src_wav: Path, out_wav: Path) -> bool:
    """Use DeepFilterNet if it is installed (much better than ffmpeg on fans/traffic)."""
    exe = shutil.which("deep-filter")
    if not exe:
        return False
    tmp = out_wav.parent / "df"
    tmp.mkdir(exist_ok=True)
    r = subprocess.run([exe, "-o", str(tmp), str(src_wav)], capture_output=True, text=True)
    produced = next(tmp.glob("*.wav"), None)
    if r.returncode != 0 or produced is None:
        shutil.rmtree(tmp, ignore_errors=True)
        return False
    produced.replace(out_wav)
    shutil.rmtree(tmp, ignore_errors=True)
    return True


def merge(clips: list[Path], out: Path, *, on_progress: ProgressFn | None = None) -> dict:
    """Join several recordings into one file (same size/fps as the largest clip).
    Returns {"path", "boundaries": [{"name", "start", "end"}]}."""
    infos = [ffmpeg.probe(c) for c in clips]
    best = max(infos, key=lambda i: i.get("width", 0) * i.get("height", 0))
    w, h = int(best.get("width", 1280)), int(best.get("height", 720))
    fps = min(60.0, max(24.0, float(best.get("fps") or 30)))
    has_audio = all(i.get("has_audio") for i in infos)
    inputs, parts, bounds, t = [], [], [], 0.0
    for n, (c, i) in enumerate(zip(clips, infos)):
        inputs += ["-i", str(c)]
        parts.append(f"[{n}:v]scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                     f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p[v{n}]")
        if has_audio:
            parts.append(f"[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS[a{n}]")
        d = float(i.get("duration") or 0)
        bounds.append({"name": c.name, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    labels = "".join(f"[v{n}]" + (f"[a{n}]" if has_audio else "") for n in range(len(clips)))
    parts.append(f"{labels}concat=n={len(clips)}:v=1:a={1 if has_audio else 0}[v]" + ("[a]" if has_audio else ""))
    maps = ["-map", "[v]"] + (["-map", "[a]"] if has_audio else [])
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run([*inputs, "-filter_complex", ";".join(parts), *maps, "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)],
               duration=t, on_progress=on_progress, label="clips जोड़े जा रहे हैं")
    return {"path": out, "boundaries": bounds, "duration": round(t, 3)}


def prepare(raw: Path, work: Path, *, denoise: bool = True, on_progress: ProgressFn | None = None) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    info = ffmpeg.probe(raw)
    if not info.get("has_video"):
        raise ValueError("इस फ़ाइल में वीडियो नहीं मिला")
    dur = info["duration"]
    report = (lambda f, m: on_progress(f, m)) if on_progress else None
    files: list[dict] = []

    # Preview copy that every browser can play (phones often record HEVC)
    proxy = work / "proxy.mp4"
    ffmpeg.run(
        [
            "-i", str(raw), "-map", "0:v:0", "-map", "0:a:0?",
            "-vf", "scale=-2:'min(720,ih)'", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "28", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
            "-movflags", "+faststart", str(proxy),
        ],
        duration=dur, label="preview बन रहा है",
        on_progress=(lambda f, m: report(f * 0.6, m)) if report else None,
    )
    files.append({"kind": "proxy", "path": proxy, "mime": "video/mp4"})

    thumb = work / "thumb.jpg"
    ffmpeg.run(
        ["-ss", str(min(1.0, dur / 2)), "-i", str(raw), "-frames:v", "1",
         "-vf", "scale=-2:360", "-q:v", "4", str(thumb)],
        label="thumbnail",
    )
    files.append({"kind": "thumb", "path": thumb, "mime": "image/jpeg"})

    if info.get("has_audio"):
        # 16 kHz mono for speech recognition
        asr = work / "audio_asr.wav"
        ffmpeg.run(["-i", str(raw), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(asr)],
                   label="audio")
        files.append({"kind": "audio_asr", "path": asr, "mime": "audio/wav"})
        if report:
            report(0.75, "आवाज़ साफ़ हो रही है")

        # 48 kHz cleaned voice used for the final render
        full = work / "audio_full.wav"
        ffmpeg.run(["-i", str(raw), "-vn", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(full)],
                   label="audio")
        clean = work / "audio_clean.wav"
        method = "none"
        if denoise and _deepfilter(full, clean):
            method = "deepfilternet"
        elif denoise:
            ffmpeg.run(["-i", str(full), "-af", FFMPEG_VOICE_CLEAN, "-c:a", "pcm_s16le", str(clean)],
                       label="आवाज़ साफ़")
            method = "ffmpeg"
        else:
            full.replace(clean)
        full.unlink(missing_ok=True)
        files.append({"kind": "audio_clean", "path": clean, "mime": "audio/wav",
                      "meta": {"method": method}})
        info["denoise"] = method

    if report:
        report(0.9, "चेहरा ढूँढा जा रहा है")
    try:
        from .facetrack import track
        pw, ph = int(info.get("width", 1280)), int(info.get("height", 720))
        if pw > ph:  # only landscape sources need a moving 9:16 window
            info["face_track"] = track(proxy, dur, pw, ph)
    except Exception as e:  # tracking is a nicety, never a reason to fail
        info["face_track_error"] = str(e)[:200]

    if report:
        report(1.0, "तैयार")
    return {"meta": info, "files": files}
