"""Speech → text with word timestamps, in the transcript format the engine uses:

{"language": "hi", "text": "...", "segments": [
   {"start": 0.0, "end": 3.2, "text": "...", "words": [{"w": "...", "start": 0.0, "end": 0.4, "p": 0.9}]}
]}

Backend order: faster-whisper (GPU on Windows / CPU fallback). The model name
comes from WHISPER_MODEL; for Hindi, `large-v3` is best, `medium` is fine on
weaker GPUs. Set WHISPER_MODEL=stub to get a fake transcript for testing.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

ProgressFn = Callable[[float, str], None]


def transcribe_file(audio: Path, *, language: str = "hi", on_progress: ProgressFn | None = None) -> dict:
    model_name = os.getenv("WHISPER_MODEL", "large-v3")
    if model_name == "stub":
        return _stub(audio)
    from faster_whisper import WhisperModel  # heavy import, only when needed

    device = os.getenv("WHISPER_DEVICE", "auto")
    compute = os.getenv("WHISPER_COMPUTE", "float16" if device != "cpu" else "int8")
    if on_progress:
        on_progress(0.02, f"model {model_name} लोड हो रहा है")
    model = WhisperModel(model_name, device=device, compute_type=compute,
                         cpu_threads=int(os.getenv("WHISPER_THREADS", "0") or 0),
                         download_root=os.getenv("WHISPER_CACHE") or None)
    segments, info = model.transcribe(
        _load_wav(audio), language=None if language == "auto" else language, word_timestamps=True,
        vad_filter=True, vad_parameters={"min_silence_duration_ms": 400},
        beam_size=int(os.getenv("WHISPER_BEAM", "5")), condition_on_previous_text=False,
        initial_prompt=os.getenv("WHISPER_PROMPT") or None,
    )
    total = float(info.duration or 0) or 1.0
    out_segs = []
    for s in segments:
        words = [{"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3),
                  "p": round(float(w.probability), 3)} for w in (s.words or []) if w.word.strip()]
        out_segs.append({"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip(),
                         "words": words})
        if on_progress:
            on_progress(min(0.98, 0.05 + 0.93 * s.end / total), f"{int(s.end)}s / {int(total)}s")
    return {"language": info.language, "model": model_name,
            "text": " ".join(s["text"] for s in out_segs), "segments": out_segs}


def _load_wav(path: Path):
    """Read a 16 kHz mono PCM WAV (what prepare.py writes) as float32 samples.

    Passing an array skips faster-whisper's PyAV decoder, whose API keeps
    changing between releases."""
    import wave
    import numpy as np

    with wave.open(str(path), "rb") as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError("audio_asr must be 16 kHz mono 16-bit PCM")
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def _stub(audio: Path) -> dict:
    """Fake Hindi transcript spread over the audio length — for tests and demos."""
    from ..engine import ffmpeg
    dur = ffmpeg.probe(audio)["duration"]
    sample = ("आज मैं आपको एक सच्ची कहानी सुनाता हूँ। अं एक लड़का था जो रोज़ सुबह चार बजे उठता था। "
              "उसके पास कुछ नहीं था, सिर्फ़ एक सपना। सिर्फ़ एक सपना था उसके पास। "
              "और उसी सपने ने उसकी ज़िंदगी बदल दी।").split()
    sil = ffmpeg.silences(audio)
    busy = []
    t = 0.0
    for s, e in sil:
        if s > t:
            busy.append((t, s))
        t = e
    if t < dur:
        busy.append((t, dur))
    speak = sum(e - s for s, e in busy) or dur
    per = speak / len(sample)
    words, seg_words, segs = [], [], []
    bi, pos = 0, busy[0][0] if busy else 0.0
    for w in sample:
        while bi < len(busy) and pos + per > busy[bi][1] + 1e-6:
            bi += 1
            if bi < len(busy):
                pos = busy[bi][0]
        start, end = pos, pos + per * 0.85
        pos += per
        word = {"w": w, "start": round(start, 3), "end": round(end, 3), "p": 0.9}
        seg_words.append(word)
        if w.endswith("।"):
            segs.append({"start": seg_words[0]["start"], "end": seg_words[-1]["end"],
                         "text": " ".join(x["w"] for x in seg_words), "words": seg_words})
            seg_words = []
    if seg_words:
        segs.append({"start": seg_words[0]["start"], "end": seg_words[-1]["end"],
                     "text": " ".join(x["w"] for x in seg_words), "words": seg_words})
    return {"language": "hi", "model": "stub", "text": " ".join(sample), "segments": segs}
