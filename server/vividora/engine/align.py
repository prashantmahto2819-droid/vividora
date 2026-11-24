"""Exact word times (optional): WhisperX forced alignment over a transcript that already exists.

Whisper's own word times can sit 0.1–0.3 s off; WhisperX lines every word up against the sound with a small speech model
of the language. It needs `pip install whisperx` (PyTorch) on the worker and downloads that language's model once —
so it is off unless WORD_ALIGN=whisperx (API & Keys) AND the package is installed. Anything going wrong leaves the
transcript exactly as it was.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path

log = logging.getLogger("vividora.align")
_MODELS: dict[str, tuple] = {}


def wanted() -> bool:
    return (os.getenv("WORD_ALIGN") or "").strip().lower() == "whisperx"


def available() -> bool:
    return importlib.util.find_spec("whisperx") is not None


def _whisperx(segments: list[dict], audio: Path, lang: str) -> list[dict]:
    import whisperx
    dev = os.getenv("WORD_ALIGN_DEVICE") or "cpu"
    if lang not in _MODELS:
        _MODELS[lang] = whisperx.load_align_model(language_code=lang, device=dev)
    model, meta = _MODELS[lang]
    res = whisperx.align([{"start": s["start"], "end": s["end"], "text": s["text"]} for s in segments], model, meta,
                         whisperx.load_audio(str(audio)), dev, return_char_alignments=False)
    return res.get("segments") or []


def merge(transcript: dict, aligned: list[dict], *, max_shift: float = 1.0) -> tuple[dict, int]:
    """Take the aligned word times into the transcript → (transcript, words moved). A segment is only touched when the
    aligner returns the same number of words for it; a word without a time (numbers, symbols) or one that would jump
    more than `max_shift` seconds, go backwards or leave its segment keeps the time it had."""
    segs = transcript.get("segments") or []
    if len(aligned) != len(segs):
        return transcript, 0
    moved = 0
    out = []
    for sg, al in zip(segs, aligned):
        words, aw = sg.get("words") or [], al.get("words") or []
        if not words or len(aw) != len(words):
            out.append(sg)
            continue
        new, prev_end = [], float(sg.get("start", 0)) - 0.3
        for w, a in zip(words, aw):
            s, e = a.get("start"), a.get("end")
            ok = (isinstance(s, (int, float)) and isinstance(e, (int, float)) and e > s and abs(s - float(w["start"])) <= max_shift
                  and s >= prev_end - 0.02 and e <= float(sg.get("end", e)) + 0.5)
            if ok:
                if abs(s - float(w["start"])) > 0.01 or abs(e - float(w["end"])) > 0.01:
                    moved += 1
                new.append({**w, "start": round(float(s), 3), "end": round(float(e), 3)})
            else:
                keep_s = max(float(w["start"]), prev_end)
                new.append({**w, "start": round(keep_s, 3), "end": round(max(float(w["end"]), keep_s + 0.03), 3)})
            prev_end = new[-1]["end"]
        out.append({**sg, "words": new, "start": round(min(float(sg["start"]), new[0]["start"]), 3), "end": round(max(float(sg["end"]), new[-1]["end"]), 3)})
    return {**transcript, "segments": out, "aligned": "whisperx"}, moved


def refine(transcript: dict, audio: Path, language: str | None, backend=None) -> tuple[dict, int]:
    """→ (transcript with better word times, how many words moved); (the same transcript, 0) when alignment is off,
    not installed, or fails."""
    if backend is None and not (wanted() and available()):
        return transcript, 0
    segs = [s for s in transcript.get("segments") or [] if s.get("words")]
    if not segs or len(segs) != len(transcript.get("segments") or []):
        return transcript, 0
    lang = (transcript.get("language") or language or "hi")[:2]
    try:
        aligned = (backend or _whisperx)(segs, Path(audio), lang)
        return merge(transcript, aligned)
    except Exception as e:  # noqa: BLE001 — a nicety: never lose the transcript over it
        log.warning("word alignment skipped: %s", str(e)[:200])
        return transcript, 0
