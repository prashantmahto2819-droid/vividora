"""AI voice-over / dubbing: text → speech → one timed voice track.

Self-contained on purpose (standard library + the ffmpeg binary; the TTS
packages are imported lazily), so install.ps1 can copy this file to the
Windows GPU worker as lib/vividora_tts.py.

Models (commercial-safe licences only):
  * Hindi + Indian English — ai4bharat/indic-parler-tts (Apache-2.0) via the
    `parler_tts` package + transformers. The voice is chosen by a text
    description ("Rohit speaks with a deep, confident…").
  * English (lighter) — Kokoro-82M (Apache-2.0) via the `kokoro` package.
No MusicGen, Piper hi voices, Coqui XTTS (non-commercial) or AGPL code.

Backends are pluggable: `VIVIDORA_TTS=fake` swaps every engine for a tone
generator of realistic length (tests, machines without a model).

The job payload (built by engine/dub.py on the server) already carries the
text of every segment and, for re-voice / dub, the output-timeline slot it must
fit in. This module synthesises each piece, fits it into its slot with ffmpeg
atempo (0.85–1.25×; longer → runs into the following silence and pushes the
next line; shorter → padded), joins everything into one track and
loudness-normalises it.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import struct
import subprocess
import wave
from pathlib import Path
from typing import Callable

ProgressFn = Callable[[float, str], None]

SR = 48000          # the assembled track
RATE_MIN, RATE_MAX = 0.85, 1.25
LOUDNESS = -16      # LUFS of the finished voice track (render normalises the mix again)

PARLER_MODEL = os.getenv("PARLER_MODEL", "ai4bharat/indic-parler-tts")
_CLEAR = "The recording is of very high quality, with very clear audio and no background noise."

# One table → the presets API → the editor's voice list.
VOICE_PRESETS: list[dict] = [
    {"id": "hi_rohit_deep", "label": "रोहित — गहरी, भरोसेमंद (पुरुष)", "lang": "hi", "gender": "m", "engine": "parler",
     "description": f"Rohit speaks with a deep, confident, warm tone at a moderate pace. {_CLEAR}"},
    {"id": "hi_rohit_energetic", "label": "रोहित — जोशीला motivational (पुरुष)", "lang": "hi", "gender": "m", "engine": "parler",
     "description": f"Rohit speaks with an energetic, powerful and highly expressive tone at a slightly fast pace, with rising intensity. {_CLEAR}"},
    {"id": "hi_aman_story", "label": "अमन — कहानी सुनाने वाला (पुरुष)", "lang": "hi", "gender": "m", "engine": "parler",
     "description": f"Aman speaks in a warm, expressive storytelling voice at a moderate pace with natural pauses and a slightly low pitch. {_CLEAR}"},
    {"id": "hi_divya_soft", "label": "दिव्या — नरम, शांत (महिला)", "lang": "hi", "gender": "f", "engine": "parler",
     "description": f"Divya speaks in a soft, calm and soothing voice at a slightly slow pace. {_CLEAR}"},
    {"id": "hi_divya_energetic", "label": "दिव्या — जोशीली (महिला)", "lang": "hi", "gender": "f", "engine": "parler",
     "description": f"Divya speaks with a bright, energetic and expressive tone at a moderate pace. {_CLEAR}"},
    {"id": "hi_rani_news", "label": "रानी — न्यूज़ एंकर (महिला)", "lang": "hi", "gender": "f", "engine": "parler",
     "description": f"Rani speaks in a clear, crisp, formal news-anchor style at a moderate pace with a neutral tone. {_CLEAR}"},
    {"id": "en_thoma_deep", "label": "Thoma — deep Indian English (पुरुष)", "lang": "en", "gender": "m", "engine": "parler",
     "description": f"Thoma speaks with a deep, confident and warm tone at a moderate pace. {_CLEAR}"},
    {"id": "en_mary_warm", "label": "Mary — warm Indian English (महिला)", "lang": "en", "gender": "f", "engine": "parler",
     "description": f"Mary speaks in a warm, friendly and expressive voice at a moderate pace. {_CLEAR}"},
    {"id": "en_kokoro_michael", "label": "Michael — American English, हल्का model (पुरुष)", "lang": "en", "gender": "m", "engine": "kokoro",
     "kokoro_voice": "am_michael", "kokoro_lang": "a"},
    {"id": "en_kokoro_heart", "label": "Heart — American English, हल्का model (महिला)", "lang": "en", "gender": "f", "engine": "kokoro",
     "kokoro_voice": "af_heart", "kokoro_lang": "a"},
]
LANGS = {"hi": "हिन्दी", "en": "English"}

INSTALL_HINT = ("GPU PC पर gpu-worker फ़ोल्डर में चलाएँ: "
                ".venv\\Scripts\\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu121 ; "
                ".venv\\Scripts\\python.exe -m pip install -r requirements-tts.txt  (देखें gpu-worker/README.md → AI voice-over)")


class TTSMissing(ValueError):
    """ValueError → the worker does not retry; the message is shown in the dashboard."""


def voice_preset(vid: str | None) -> dict | None:
    return next((v for v in VOICE_PRESETS if v["id"] == vid), None)


# ---------------------------------------------------------------- wav helpers
def write_wav(path: Path, pcm: bytes, sr: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return path


def read_pcm(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{path.name}: mono 16-bit wav चाहिए")
        return w.readframes(w.getnframes()), w.getframerate()


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate() or 1)


def _float_to_pcm(samples) -> bytes:
    """numpy float array (−1..1) → int16 bytes."""
    import numpy as np  # present wherever a real TTS model runs
    a = np.asarray(samples, dtype=np.float32).reshape(-1)
    a = np.clip(a, -1.0, 1.0)
    return (a * 32767.0).astype("<i2").tobytes()


# ---------------------------------------------------------------- backends
class FakeBackend:
    """A soft tone as long as the text would take to say (~14 chars/s). For tests and dry runs."""
    name = "fake"
    native_speed = False

    def synth(self, text: str, voice: dict, lang: str, speed: float, out: Path) -> Path:
        sr = 24000
        n_chars = len(re.sub(r"\s+", " ", text.strip()))
        dur = max(0.35, n_chars / 14.0)
        f = 180.0 if (voice.get("gender") or "m") == "m" else 260.0
        n = int(sr * dur)
        fade = int(sr * 0.02)
        buf = bytearray()
        for i in range(n):
            env = min(1.0, i / fade, (n - i) / fade)
            buf += struct.pack("<h", int(9000 * env * math.sin(2 * math.pi * f * i / sr)))
        # Parler-like leading/trailing silence, which the trimmer has to remove
        pad = b"\x00\x00" * int(sr * 0.15)
        return write_wav(out, pad + bytes(buf) + pad, sr)


class ParlerBackend:
    name = "parler"
    native_speed = False
    _model = None

    def _load(self):
        if ParlerBackend._model is not None:
            return ParlerBackend._model
        try:
            import torch
            from parler_tts import ParlerTTSForConditionalGeneration
            from transformers import AutoTokenizer
        except ImportError as e:
            raise TTSMissing(f"AI आवाज़ (Indic Parler-TTS) का package नहीं मिला: {e.name or e}. {INSTALL_HINT}") from None
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        dtype = torch.float32
        if device != "cpu" and os.getenv("PARLER_DTYPE", "float16") == "float16":
            dtype = torch.float16
        cache = os.getenv("TTS_CACHE") or None
        model = ParlerTTSForConditionalGeneration.from_pretrained(PARLER_MODEL, torch_dtype=dtype, cache_dir=cache).to(device)
        tok = AutoTokenizer.from_pretrained(PARLER_MODEL, cache_dir=cache)
        desc_tok = AutoTokenizer.from_pretrained(model.config.text_encoder._name_or_path, cache_dir=cache)
        ParlerBackend._model = (torch, model, tok, desc_tok, device)
        return ParlerBackend._model

    def synth(self, text: str, voice: dict, lang: str, speed: float, out: Path) -> Path:
        torch, model, tok, desc_tok, device = self._load()
        desc = voice.get("description") or VOICE_PRESETS[0]["description"]
        d = desc_tok(desc, return_tensors="pt").to(device)
        p = tok(text, return_tensors="pt").to(device)
        # same seed every line → the same speaker throughout the video
        torch.manual_seed(int(voice.get("seed", 1234)))
        with torch.inference_mode():
            gen = model.generate(input_ids=d.input_ids, attention_mask=d.attention_mask,
                                 prompt_input_ids=p.input_ids, prompt_attention_mask=p.attention_mask)
        audio = gen.to(torch.float32).cpu().numpy().squeeze()
        return write_wav(out, _float_to_pcm(audio), int(model.config.sampling_rate))


class KokoroBackend:
    name = "kokoro"
    native_speed = True
    _pipes: dict = {}

    def synth(self, text: str, voice: dict, lang: str, speed: float, out: Path) -> Path:
        try:
            import numpy as np
            from kokoro import KPipeline
        except ImportError as e:
            raise TTSMissing(f"English AI आवाज़ (Kokoro) का package नहीं मिला: {e.name or e}. {INSTALL_HINT}") from None
        code = voice.get("kokoro_lang") or "a"
        if code not in KokoroBackend._pipes:
            KokoroBackend._pipes[code] = KPipeline(lang_code=code, repo_id="hexgrad/Kokoro-82M")
        parts = []
        for _gs, _ps, audio in KokoroBackend._pipes[code](text, voice=voice.get("kokoro_voice") or "am_michael",
                                                           speed=max(0.5, min(2.0, float(speed or 1.0)))):
            if audio is not None:
                parts.append(audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio))
        if not parts:
            raise RuntimeError("Kokoro ने आवाज़ नहीं बनाई")
        return write_wav(out, _float_to_pcm(np.concatenate(parts)), 24000)


def backend_for(engine: str):
    forced = (os.getenv("VIVIDORA_TTS") or "").strip().lower()
    if forced == "fake" or engine == "fake":
        return FakeBackend()
    if engine == "kokoro":
        return KokoroBackend()
    return ParlerBackend()


def check_ready(engine: str) -> None:
    """Fail early (before any download/synthesis) with a clear Hindi message."""
    if not shutil.which("ffmpeg"):
        raise TTSMissing("ffmpeg नहीं मिला — AI voice-over के लिए ffmpeg चाहिए। Windows: winget install Gyan.FFmpeg (फिर नया PowerShell खोलें)")
    b = backend_for(engine)
    if isinstance(b, FakeBackend):
        return
    import importlib.util
    need = ["torch", "parler_tts", "transformers"] if isinstance(b, ParlerBackend) else ["torch", "kokoro"]
    missing = [m for m in need if importlib.util.find_spec(m) is None]
    if missing:
        raise TTSMissing(f"AI आवाज़ के packages नहीं मिले ({', '.join(missing)}). {INSTALL_HINT}")


# ---------------------------------------------------------------- text helpers
_SENT = re.compile(r"(?<=[।॥.!?])\s+")


def split_sentences(text: str, max_chars: int = 220) -> list[str]:
    """Sentences, long ones broken at commas/spaces (Parler drifts on very long prompts)."""
    out: list[str] = []
    for s in _SENT.split(re.sub(r"[ \t]+", " ", text.strip())):
        s = s.strip()
        while len(s) > max_chars:
            cut = max(s.rfind(",", 0, max_chars), s.rfind("،", 0, max_chars))
            if cut < max_chars // 3:
                cut = s.rfind(" ", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            out.append(s[:cut + 1].strip())
            s = s[cut + 1:].strip()
        if s:
            out.append(s)
    return out


def script_lines(script: str) -> list[dict]:
    """Script → [{text, pause_after}] — a blank line is a longer pause (new paragraph)."""
    items: list[dict] = []
    for para in re.split(r"\n\s*\n", script.strip()):
        sents = [x for line in para.splitlines() for x in split_sentences(line)]
        for i, s in enumerate(sents):
            items.append({"text": s, "pause": 0.65 if i == len(sents) - 1 else 0.28})
    return items


def word_times(text: str, start: float, end: float) -> list[dict]:
    """Approximate per-word timing (TTS gives no alignment): spread by character length."""
    words = [w for w in text.split() if w.strip()]
    if not words:
        return []
    weights = [len(w) + 1 for w in words]
    total = float(sum(weights))
    t, out = start, []
    for w, k in zip(words, weights):
        d = (end - start) * k / total
        out.append({"w": w, "start": round(t, 3), "end": round(t + d * 0.92, 3)})
        t += d
    return out


# ---------------------------------------------------------------- audio steps
def _ff(args: list[str]) -> None:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg: " + (r.stderr or "").strip()[-400:])


def _atempo(rate: float) -> str:
    parts, r = [], rate
    while r > 2.0:
        parts.append("atempo=2.0"); r /= 2.0
    while r < 0.5:
        parts.append("atempo=0.5"); r /= 0.5
    parts.append(f"atempo={r:.4f}")
    return ",".join(parts)


_TRIM = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03,areverse,"
         "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.06,afade=t=in:d=0.02,areverse,afade=t=in:d=0.01")


def clean_piece(src: Path, dst: Path) -> float:
    """Trim the model's leading/trailing silence, mono 48 kHz → seconds."""
    _ff(["-i", str(src), "-af", f"aformat=channel_layouts=mono,aresample={SR},{_TRIM}", "-ac", "1", "-ar", str(SR),
         "-c:a", "pcm_s16le", str(dst)])
    return wav_seconds(dst)


def stretch(src: Path, dst: Path, rate: float) -> float:
    if abs(rate - 1.0) < 0.015:
        shutil.copyfile(src, dst)
    else:
        _ff(["-i", str(src), "-af", _atempo(rate), "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(dst)])
    return wav_seconds(dst)


def synth_text(backend, text: str, voice: dict, lang: str, speed: float, work: Path, tag: str) -> Path:
    """Long text → several model calls joined with short breaths → one clean 48 kHz wav."""
    chunks = split_sentences(text)
    pcm = bytearray()
    for k, ch in enumerate(chunks):
        raw = backend.synth(ch, voice, lang, speed, work / f"{tag}_{k}_raw.wav")
        cl = work / f"{tag}_{k}.wav"
        clean_piece(raw, cl)
        data, _ = read_pcm(cl)
        if pcm:
            pcm += b"\x00\x00" * int(SR * 0.12)
        pcm += data
    return write_wav(work / f"{tag}.wav", bytes(pcm), SR)


def fit_rate(natural: float, slot: float, speed: float = 1.0) -> float:
    """atempo factor that fits `natural` seconds of speech into `slot` seconds, clamped 0.85–1.25;
    `speed` is the creator's bias (1.1 = a bit faster)."""
    if slot <= 0.05:
        return RATE_MAX
    r = natural / slot
    r = max(RATE_MIN, min(RATE_MAX, r))
    if abs(speed - 1.0) > 1e-3:
        r = max(RATE_MIN, min(RATE_MAX, r * speed))
    return r


def build_track(payload: dict, work: Path, on_progress: ProgressFn | None = None) -> dict:
    """payload: {mode, language, voice{engine, description|kokoro_voice…}, speed, segments[{text, start?, end?}], total?}
    → {path (m4a), duration, segments[{text,start,end,slot_start,slot_end,rate,words}], drift_max, engine}"""
    work.mkdir(parents=True, exist_ok=True)
    voice = payload.get("voice") or {}
    engine = voice.get("engine") or "parler"
    check_ready(engine)
    backend = backend_for(engine)
    lang = payload.get("language") or "hi"
    speed = max(0.7, min(1.4, float(payload.get("speed") or 1.0)))
    mode = payload.get("mode") or "revoice"
    segs = [s for s in (payload.get("segments") or []) if str(s.get("text") or "").strip()]
    if not segs:
        raise ValueError("बोलने के लिए कोई text नहीं मिला")
    prog = on_progress or (lambda f, m: None)

    placed: list[dict] = []
    pcm = bytearray()          # the assembled track, 48 kHz mono s16
    cursor = 0.0               # end of what is already placed
    drift_max = 0.0
    timed = mode != "script" and all(s.get("start") is not None and s.get("end") is not None for s in segs)
    t = 0.35 if not timed else 0.0
    for i, s in enumerate(segs):
        prog(0.05 + 0.85 * i / len(segs), f"AI आवाज़: line {i + 1}/{len(segs)}")
        text = str(s["text"]).strip()
        nat_speed = speed if backend.native_speed and not timed else 1.0
        raw = synth_text(backend, text, voice, lang, nat_speed, work, f"s{i}")
        natural = wav_seconds(raw)
        if timed:
            slot_a, slot_b = float(s["start"]), float(s["end"])
            rate = fit_rate(natural, slot_b - slot_a, speed)
            start = max(slot_a, cursor + (0.04 if placed else 0.0))
        else:
            rate = 1.0 if backend.native_speed else speed
            slot_a = slot_b = None
            start = max(t, cursor)
        fitted = work / f"s{i}_fit.wav"
        length = stretch(raw, fitted, rate)
        data, _ = read_pcm(fitted)
        # place: silence up to `start`, then the line (no overlaps — a long line pushes the next one)
        at = int(round(start * SR)) * 2
        if len(pcm) < at:
            pcm += b"\x00" * (at - len(pcm))
        else:
            del pcm[at:]
        pcm += data
        end = start + length
        cursor = end
        if timed:
            drift_max = max(drift_max, start - slot_a)
        else:
            t = end + float(s.get("pause", 0.3))
        placed.append({"i": i, "text": text, "start": round(start, 3), "end": round(end, 3),
                       "slot_start": slot_a, "slot_end": slot_b, "rate": round(rate, 3),
                       "words": word_times(text, start, end)})
        for f in work.glob(f"s{i}_*"):
            f.unlink(missing_ok=True)
    total = max(cursor + (0.5 if not timed else 0.0), float(payload.get("total") or 0))
    at = int(round(total * SR)) * 2
    if len(pcm) < at:
        pcm += b"\x00" * (at - len(pcm))
    raw_track = write_wav(work / "dub_raw.wav", bytes(pcm), SR)
    prog(0.93, "आवाज़ का loudness ठीक हो रहा है")
    out = work / f"dub_{lang}.m4a"
    _ff(["-i", str(raw_track), "-af", f"highpass=f=70,loudnorm=I={LOUDNESS}:TP=-1.5:LRA=11,aresample={SR}",
         "-ac", "1", "-ar", str(SR), "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])
    raw_track.unlink(missing_ok=True)
    return {"path": out, "duration": round(total, 3), "segments": placed, "drift_max": round(drift_max, 3),
            "engine": backend.name}


def handle_job(client, job: dict, work: Path, on_progress: ProgressFn | None = None) -> dict:
    """The whole `dub` job for any worker (CPU with TTS_LOCAL=1, or the GPU PC)."""
    p = job["payload"]
    r = build_track(p, work, on_progress)
    lang = p.get("language") or "hi"
    name = f"dub_{lang}_{job['id'][:8]}.m4a"
    final = r["path"].with_name(name)
    r["path"].rename(final)
    up = client.upload(job["id"], final, "dub", lang)
    v = p.get("voice") or {}
    meta = {"mode": p.get("mode"), "language": lang, "source_language": p.get("source_language"),
            "voice": {k: v.get(k) for k in ("id", "label", "engine", "description", "kokoro_voice") if v.get(k)},
            "engine": r["engine"], "speed": p.get("speed", 1.0), "duration": r["duration"], "drift_max": r["drift_max"],
            "sig": p.get("sig"), "segments": r["segments"]}
    return {"files": [{"kind": "dub", "path": up["path"], "mime": "audio/mp4", "label": lang, "meta": meta}]}
