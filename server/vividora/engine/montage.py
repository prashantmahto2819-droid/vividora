"""Music montage without a voice-over: clips cut on the beat, text lines on top.

beats()   onset-strength → tempo (autocorrelation) → beat grid, numpy only
render()  N short segments (one per `every` beats) from the chosen clips/images,
          concat, colour look, beat flash, text lines (ASS), music under it.
"""

from __future__ import annotations

import math
import random
import subprocess
from pathlib import Path

import numpy as np

from . import ffmpeg
from .captions import _esc, _t, ass_color
from .effects import LOOKS

SR = 22050
HOP = 512
WIN = 1024


def _decode(path: Path, max_seconds: float = 600) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-t", f"{max_seconds}", "-ac", "1", "-ar", str(SR),
           "-f", "f32le", "-"]
    out = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(out, dtype=np.float32)


def onset_envelope(y: np.ndarray) -> np.ndarray:
    if len(y) < WIN * 2:
        return np.zeros(1)
    n = (len(y) - WIN) // HOP
    win = np.hanning(WIN).astype(np.float32)
    frames = np.lib.stride_tricks.as_strided(y, shape=(n, WIN), strides=(y.strides[0] * HOP, y.strides[0]))
    mag = np.abs(np.fft.rfft(frames * win, axis=1))
    mag = np.log1p(mag * 10)
    flux = np.diff(mag, axis=0, prepend=mag[:1])
    env = np.maximum(flux, 0).sum(axis=1)
    # local-mean subtraction so loud passages do not dominate
    k = 16
    kernel = np.ones(k) / k
    env = env - np.convolve(env, kernel, mode="same")
    env = np.maximum(env, 0)
    return env / (env.max() or 1.0)


def tempo(env: np.ndarray, lo: float = 60, hi: float = 190) -> float:
    fps = SR / HOP
    if len(env) < fps * 4:
        return 120.0
    ac = np.correlate(env, env, mode="full")[len(env) - 1:]
    ac /= ac[0] or 1.0
    lag_lo, lag_hi = int(fps * 60 / hi), int(fps * 60 / lo)
    seg = ac[lag_lo:lag_hi]
    if not len(seg):
        return 120.0
    lag = lag_lo + int(np.argmax(seg))
    bpm = 60 * fps / lag
    while bpm > 150:  # prefer the slower reading for cuts
        bpm /= 2
    return float(bpm)


def beats(path: Path, duration_hint: float | None = None) -> dict:
    y = _decode(path)
    dur = len(y) / SR
    env = onset_envelope(y)
    bpm = tempo(env)
    fps = SR / HOP
    period = 60 / bpm
    step = period * fps
    # pick the phase that lands beats on the strongest onsets
    best, best_phase = -1.0, 0.0
    for ph in np.linspace(0, step, 24, endpoint=False):
        idx = np.arange(ph, len(env), step).astype(int)
        s = env[idx].sum()
        if s > best:
            best, best_phase = s, ph
    times = [round(float(t), 3) for t in np.arange(best_phase / fps, dur, period)]
    return {"bpm": round(bpm, 1), "beats": times, "duration": round(dur, 2)}


def _segments(total_beats: list[float], every: int, max_seconds: float) -> list[tuple[float, float]]:
    segs = []
    for i in range(0, len(total_beats) - every, every):
        a, b = total_beats[i], total_beats[i + every]
        if b > max_seconds:
            break
        segs.append((a, b))
    return segs


def render(*, clips: list[dict], music: Path, out_dir: Path, name: str, preset: dict, texts: list[str],
           look: str = "none", every: int = 2, max_seconds: float = 30, flash: bool = True,
           font: str = "Poppins", text_color: str = "#FFFFFF", text_size: float = 0.07,
           watermark: Path | None = None, seed: int = 7, encoder_preset: str | None = None,
           on_progress=None) -> dict:
    """clips: [{path, type: video|image, duration}] — order is kept, clips cycle."""
    if not clips:
        raise ValueError("कम से कम एक clip या image चुनें")
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / f".{name}"
    work.mkdir(exist_ok=True)
    w, h = int(preset["width"]), int(preset["height"])
    fps = 30
    info = beats(music)
    bt = info["beats"]
    if len(bt) < 4:
        period = 0.5
        bt = [i * period for i in range(int(max_seconds / period) + 2)]
    segs = _segments(bt, max(1, every), min(max_seconds, info["duration"]))
    if not segs:
        raise ValueError("music बहुत छोटा है")
    rnd = random.Random(seed)
    offsets = {i: 0.0 for i in range(len(clips))}
    inputs: list[str] = []
    chains: list[str] = []
    labels = []
    for n, (a, b) in enumerate(segs):
        d = b - a
        ci = n % len(clips)
        c = clips[ci]
        if c.get("type") == "image":
            inputs += ["-loop", "1", "-t", f"{d + 0.1:.3f}", "-i", str(c["path"])]
            frames = int(math.ceil(d * fps))
            z = rnd.choice(["min(zoom+0.0012,1.18)", "if(eq(on,1),1.18,max(zoom-0.0012,1.0))"])
            chains.append(f"[{n}:v]scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
                          f"zoompan=z='{z}':d={frames}:s={w}x{h}:fps={fps},trim=duration={d:.3f},setpts=PTS-STARTPTS,setsar=1[s{n}]")
        else:
            cd = float(c.get("duration") or 5)
            off = offsets[ci]
            if off + d > cd:
                off = rnd.uniform(0, max(0.0, cd - d))
            offsets[ci] = off + d
            inputs += ["-ss", f"{off:.3f}", "-t", f"{d + 0.2:.3f}", "-i", str(c["path"])]
            chains.append(f"[{n}:v]scale={w}:{h}:force_original_aspect_ratio=increase:flags=bicubic,crop={w}:{h},"
                          f"fps={fps},trim=duration={d:.3f},setpts=PTS-STARTPTS,setsar=1[s{n}]")
        labels.append(f"[s{n}]")
    total = sum(b - a for a, b in segs)
    chains.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[vcat]")
    v = "[vcat]"
    tail = ""
    lk = LOOKS.get(look, LOOKS["none"])["filter"]
    if lk:
        tail += lk + ","
    if flash:
        cut_times = [b - segs[0][0] for a, b in segs[:-1]]
        en = "+".join(f"between(t\\,{t - 0.04:.3f}\\,{t + 0.04:.3f})" for t in cut_times[:200])
        tail += f"drawbox=color=white@0.45:t=fill:enable='{en}',"
    # text lines: spread over the montage, each line gets an equal share of segments
    if texts:
        base = min(w, h)
        size = round(text_size * base)
        lines = [l.strip() for l in texts if l.strip()][:12]
        per = max(1, len(segs) // len(lines))
        ass = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 2",
               "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
               "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
               "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
               f"Style: M,{font},{size},{ass_color(text_color)},&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,"
               f"{round(0.006 * base, 1)},{round(0.004 * base, 1)},5,{round(0.08 * w)},{round(0.08 * w)},0,1",
               "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
        t0 = segs[0][0]
        for i, line in enumerate(lines):
            s_i = segs[min(len(segs) - 1, i * per)][0] - t0
            e_i = (segs[min(len(segs) - 1, (i + 1) * per - 1)][1] - t0) if i < len(lines) - 1 else total
            txt = _esc(line).replace("|", "\\N")
            ass.append(f"Dialogue: 0,{_t(s_i)},{_t(e_i)},M,,0,0,0,,{{\\fad(120,160)\\fscx92\\fscy92\\t(0,250,\\fscx100\\fscy100)}}{txt}")
        f = work / "montage.ass"
        f.write_text("\n".join(ass) + "\n", encoding="utf-8")
        fonts = Path(__file__).resolve().parent.parent.parent / "fonts"
        tail += f"subtitles=filename='{ffmpeg.escape_filter_path(f)}':fontsdir='{ffmpeg.escape_filter_path(fonts)}',"
    mi = len(segs)
    inputs += ["-ss", f"{segs[0][0]:.3f}", "-t", f"{total + 0.5:.3f}", "-i", str(music)]
    if watermark is not None:
        inputs += ["-i", str(watermark)]
        chains.append(f"[{mi + 1}:v]scale={int(w * 0.14)}:-1,format=rgba,colorchannelmixer=aa=0.75[wm]")
        chains.append(f"{v}{tail}format=yuv420p[vt];[vt][wm]overlay=W-w-{int(min(w, h) * 0.035)}:{int(min(w, h) * 0.035)}[v]")
    else:
        chains.append(f"{v}{tail}format=yuv420p[v]")
    a_cfg = preset.get("audio", {})
    chains.append(f"[{mi}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,afade=t=out:st={max(0.0, total - 1.2):.3f}:d=1.2,"
                  f"loudnorm=I={a_cfg.get('loudness', -14)}:TP={a_cfg.get('true_peak', -1.5)}:LRA=11,aresample=48000[a]")
    script = work / "filter.txt"
    script.write_text(";\n".join(chains), encoding="utf-8")
    out = out_dir / f"{name}.mp4"
    vcfg = preset.get("video", {})
    ffmpeg.run([*inputs, "-filter_complex_script", str(script), "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", encoder_preset or vcfg.get("preset", "medium"), "-crf", str(vcfg.get("crf", 20)),
                "-g", str(fps * 2), "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-movflags", "+faststart", "-t", f"{total:.3f}", str(out)],
               duration=total, on_progress=on_progress, label="montage रेंडर")
    for f in work.iterdir():
        f.unlink()
    work.rmdir()
    return {"files": [{"kind": "render", "path": out, "mime": "video/mp4", "label": preset["id"],
                       "meta": {"preset": preset["id"], "width": w, "height": h, "duration": round(total, 2), "fps": fps,
                                "montage": True, "bpm": info["bpm"], "segments": len(segs), "effects": {"look": look, "music": True}}}],
            "duration": round(total, 2), "bpm": info["bpm"], "segments": len(segs), "warnings": []}
