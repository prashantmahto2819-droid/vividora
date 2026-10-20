"""Speech → text with word timestamps, in the transcript format the engine uses:

{"language": "hi", "text": "...", "segments": [
   {"start": 0.0, "end": 3.2, "text": "...", "words": [{"w": "...", "start": 0.0, "end": 0.4, "p": 0.9}]}
]}

Backend: faster-whisper (GPU on Windows / CPU in Docker). The model name comes
from WHISPER_MODEL; for Hindi, `large-v3` is best. WHISPER_MODEL=stub gives a
fake transcript for testing.

How we avoid losing speech (the "captions skip parts" bug):
  1. Main pass with a *gentle* VAD (low threshold, long min-silence, wide pad),
     no previous-text conditioning, no "hallucination_silence" skipping, and a
     high no_speech threshold — Whisper skips a whole 30 s window when
     no_speech_prob > threshold and avg_logprob is low, which is common for Hindi.
  2. Gap re-pass: find stretches with speech energy in the audio but no words
     (> WHISPER_GAP_MIN s), transcribe just those (VAD off, several gaps packed
     into one ≤28 s buffer so CPU time stays low), keep only words that fall in
     the gaps and look real, and merge them in time order.
  3. Every word is kept and its timing repaired (engine/wordfix.py).

window=(start, end) transcribes only that part of the recording (re-transcribe
one line) with a stronger search and optional alternative readings.
"""

from __future__ import annotations

import logging
import os
import zlib
from collections.abc import Callable
from pathlib import Path

try:
    from ..engine import wordfix
except ImportError:  # the GPU worker's standalone copy (lib/vividora_transcribe.py)
    import vividora_wordfix as wordfix  # type: ignore

ProgressFn = Callable[[float, str], None]
log = logging.getLogger("vividora.transcribe")
SR = 16000
_MODELS: dict[tuple, object] = {}
# Whisper's favourite inventions on noise / silence (checked only for re-pass output)
HALLUCINATIONS = (
    "सब्सक्राइब", "subscribe", "thanks for watching", "thank you for watching", "धन्यवाद", "शुक्रिया",
    "like और share", "लाइक", "बेल आइकन", "bell icon", "amara.org", "subtitles by", "उपशीर्षक",
)
_INDIC = {"hi", "mr", "ne", "sa", "bn", "pa", "gu", "or", "ta", "te", "kn", "ml", "ur", "as"}


def _env(name: str, default: float) -> float:
    try:
        v = os.getenv(name)
        return float(v) if v not in (None, "") else default
    except ValueError:
        return default


def _on(name: str, default: bool = True) -> bool:
    v = os.getenv(name)
    if v in (None, ""):
        return default
    return v.strip().lower() not in ("0", "false", "no", "off")


def _model(name: str):
    """Load once per worker process: a second job (or a one-line re-transcribe) skips the 10–30 s load."""
    from faster_whisper import WhisperModel  # heavy import, only when needed
    device = os.getenv("WHISPER_DEVICE", "auto")
    compute = os.getenv("WHISPER_COMPUTE", "float16" if device != "cpu" else "int8")
    key = (name, device, compute)
    if key not in _MODELS:
        if len(_MODELS) >= 2:  # keep RAM bounded: at most two different models
            _MODELS.pop(next(iter(_MODELS)))
        _MODELS[key] = WhisperModel(name, device=device, compute_type=compute,
                                    cpu_threads=int(os.getenv("WHISPER_THREADS", "0") or 0),
                                    download_root=os.getenv("WHISPER_CACHE") or None)
    return _MODELS[key]


def decode_options(language: str | None, prompt: str | None, *, vad: bool) -> dict:
    """Whisper settings for the main pass (env vars override every default)."""
    lang = None if language in (None, "", "auto") else language
    o = dict(
        language=lang, word_timestamps=True, task="transcribe",
        beam_size=int(_env("WHISPER_BEAM", 5)), best_of=int(_env("WHISPER_BEST_OF", 5)),
        patience=_env("WHISPER_PATIENCE", 1.0),
        temperature=[0.0, 0.2, 0.4, 0.6, 0.8],
        # conditioning on the previous window makes Whisper loop or skip a chunk after one bad window
        condition_on_previous_text=_on("WHISPER_CONDITION", False),
        # Devanagari UTF-8 compresses well — 2.4 throws good Hindi windows into high-temperature retries
        compression_ratio_threshold=_env("WHISPER_COMPRESSION", 2.8 if (lang or "hi") in _INDIC else 2.4),
        log_prob_threshold=_env("WHISPER_LOGPROB", -1.0),
        # a window is SKIPPED when no_speech_prob > this and logprob is low: keep it near 1
        no_speech_threshold=_env("WHISPER_NO_SPEECH", 0.9),
        initial_prompt=prompt or os.getenv("WHISPER_PROMPT") or None,
        # "।" belongs to the word before it, not a separate word
        append_punctuations="\"'.。,，!！?？:：”)]}、।॥",
        language_detection_segments=3,
        vad_filter=vad,
    )
    hst = os.getenv("WHISPER_HALLUCINATION_SILENCE", "")  # off: it drops fast, low-confidence Hindi words
    if hst:
        o["hallucination_silence_threshold"] = float(hst)
    if vad:
        o["vad_parameters"] = {
            "threshold": _env("WHISPER_VAD_THRESHOLD", 0.3),
            "min_speech_duration_ms": int(_env("WHISPER_VAD_MIN_SPEECH_MS", 120)),
            "min_silence_duration_ms": int(_env("WHISPER_VAD_MIN_SILENCE_MS", 1000)),
            "speech_pad_ms": int(_env("WHISPER_VAD_PAD_MS", 500)),
        }
    return o


_OPTIONAL = ("hallucination_silence_threshold", "append_punctuations", "language_detection_segments",
             "patience", "best_of", "task")


def _run(model, audio, opts: dict):
    """model.transcribe with a fallback for faster-whisper builds that lack some knobs."""
    try:
        return model.transcribe(audio, **opts)
    except TypeError as e:
        log.warning("faster-whisper rejected an option (%s) — retrying with the basic set", e)
        return model.transcribe(audio, **{k: v for k, v in opts.items() if k not in _OPTIONAL})


def _seg_dict(s, offset: float = 0.0) -> dict:
    words = [{"w": (w.word or ""), "start": None if w.start is None else round(w.start + offset, 3),
              "end": None if w.end is None else round(w.end + offset, 3),
              "p": round(float(w.probability or 0.0), 3)} for w in (s.words or [])]
    seg = {"start": round(s.start + offset, 3), "end": round(s.end + offset, 3), "text": (s.text or "").strip(),
           "words": words, "avg_logprob": round(float(getattr(s, "avg_logprob", 0.0) or 0.0), 3)}
    return wordfix.clean_segment(seg)


def transcribe_file(audio: Path, *, language: str = "hi", prompt: str | None = None,
                    on_progress: ProgressFn | None = None, window: tuple[float, float] | None = None,
                    alternatives: int = 0, model: str | None = None) -> dict:
    model_name = model or os.getenv("WHISPER_MODEL", "large-v3")
    if model_name == "stub" or os.getenv("WHISPER_MODEL") == "stub":
        tr = _stub(audio)
        if window:
            tr = _cut_window(tr, window)
        return wordfix.clean_transcript(tr)
    if on_progress:
        on_progress(0.02, f"model {model_name} लोड हो रहा है")
    m = _model(model_name)
    wav = _load_wav(audio)
    if window:
        return _transcribe_window(m, model_name, wav, window, language, prompt, alternatives, on_progress)

    opts = decode_options(language, prompt, vad=_on("WHISPER_VAD", True))
    segments, info = _run(m, wav, opts)
    total = float(info.duration or 0) or len(wav) / SR or 1.0
    gap_pass = _on("WHISPER_GAP_PASS", True)
    main_share = 0.8 if gap_pass else 0.96
    out_segs = []
    for s in segments:
        sd = _seg_dict(s)
        if sd["words"] or sd["text"]:
            out_segs.append(sd)
        if on_progress:
            on_progress(min(0.02 + main_share, 0.05 + main_share * s.end / total), f"{int(s.end)}s / {int(total)}s")
    lang = info.language or language
    added = 0
    if gap_pass:
        try:
            new = fill_gaps(m, wav, out_segs, lang, on_progress=on_progress, base=0.05 + main_share)
            added = sum(len(s["words"]) for s in new)
            out_segs += new
        except Exception as e:  # noqa: BLE001 — the main transcript is still good
            log.warning("gap re-pass failed: %s", e)
    tr = wordfix.clean_transcript({"language": lang, "model": model_name, "segments": out_segs}) or {}
    tr["gap_words"] = added
    return tr


# ---------------------------------------------------------------- one line / window

def _cut_window(tr: dict, window) -> dict:
    s, e = window
    segs = []
    for sg in tr.get("segments") or []:
        ws = [w for w in sg.get("words") or [] if s <= (w["start"] + w["end"]) / 2 <= e]
        if ws:
            segs.append({**sg, "words": ws, "text": " ".join(w["w"] for w in ws),
                         "start": ws[0]["start"], "end": ws[-1]["end"]})
    return {**tr, "segments": segs, "range": [s, e]}


def _transcribe_window(m, model_name: str, wav, window, language: str, prompt: str | None,
                       alternatives: int, on_progress: ProgressFn | None) -> dict:
    """Re-transcribe one part of the recording: VAD off, stronger beam, optional alternatives."""
    s = max(0.0, float(window[0]))
    e = min(len(wav) / SR, float(window[1]))
    if e - s < 0.2:
        raise ValueError("चुना हुआ हिस्सा बहुत छोटा है")
    if e - s > 120:
        raise ValueError("एक बार में 2 मिनट तक का हिस्सा ही दोबारा सुना जा सकता है")
    chunk = wav[int(s * SR):int(e * SR)]
    base = decode_options(language, prompt, vad=False)
    base.update(no_speech_threshold=None, beam_size=max(8, int(base["beam_size"])),
                best_of=max(5, int(base["best_of"])), patience=max(1.5, float(base["patience"])))
    tries = [base]
    if alternatives > 0:  # different readings for the creator to choose from
        tries.append({**base, "initial_prompt": None, "beam_size": 5, "patience": 1.0})
    if alternatives > 1:
        tries.append({**base, "initial_prompt": None, "temperature": 0.5, "beam_size": 1, "best_of": 5})
    if alternatives > 2:
        tries.append({**base, "temperature": 0.8, "beam_size": 1, "best_of": 5})
    results, lang = [], language
    for n, opts in enumerate(tries):
        if on_progress:
            on_progress(0.1 + 0.85 * n / len(tries), "line दोबारा सुन रहे हैं" if n == 0 else f"दूसरा रूप {n}")
        segs, info = _run(m, chunk, opts)
        segs = [_seg_dict(x, offset=s) for x in segs]
        lang = info.language or lang
        words = [w for sg in segs for w in sg["words"]]
        results.append(words)
    best = results[0]
    seg = {"start": best[0]["start"] if best else s, "end": best[-1]["end"] if best else e,
           "text": " ".join(w["w"] for w in best), "words": best}
    alts, seen = [], {seg["text"]}
    for words in results[1:]:
        txt = " ".join(w["w"] for w in words)
        if txt and txt not in seen:
            seen.add(txt)
            alts.append({"text": txt, "words": words})
    return {"language": lang, "model": model_name, "range": [round(s, 3), round(e, 3)],
            "segments": [seg] if best else [], "alts": alts, "text": seg["text"]}


# ---------------------------------------------------------------- gap re-pass

def speech_regions(wav, frame: float = 0.03) -> list[tuple[float, float]]:
    """Where the audio has voice-like energy (RMS above an adaptive floor). Pure numpy."""
    import numpy as np
    hop = int(SR * frame)
    n = len(wav) // hop
    if n < 3:
        return []
    fr = wav[: n * hop].reshape(n, hop).astype("float64")
    rms = np.sqrt(np.mean(fr * fr, axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    floor, peak = float(np.percentile(db, 10)), float(np.percentile(db, 97))
    thr = max(floor + _env("WHISPER_GAP_ABOVE_FLOOR_DB", 9.0), peak - 30.0, -55.0)
    on = db > thr
    regions, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            regions.append([start * frame, i * frame])
            start = None
    if start is not None:
        regions.append([start * frame, n * frame])
    merged: list[list[float]] = []
    for r in regions:  # bridge short dips inside a word / between syllables
        if merged and r[0] - merged[-1][1] < 0.25:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [(round(a, 3), round(b, 3)) for a, b in merged if b - a >= 0.15]


def find_gaps(segs: list[dict], regions: list[tuple[float, float]], duration: float,
              min_gap: float | None = None, min_voiced: float | None = None) -> list[tuple[float, float, float]]:
    """(start, end, voiced seconds) of stretches with speech energy but no words."""
    min_gap = _env("WHISPER_GAP_MIN", 1.2) if min_gap is None else min_gap
    min_voiced = _env("WHISPER_GAP_MIN_VOICED", 0.4) if min_voiced is None else min_voiced
    cover: list[list[float]] = []
    for w in sorted((w for s in segs for w in s.get("words") or []), key=lambda w: w["start"]):
        a, b = w["start"] - 0.1, w["end"] + 0.1
        if cover and a <= cover[-1][1]:
            cover[-1][1] = max(cover[-1][1], b)
        else:
            cover.append([a, b])
    holes, t = [], 0.0
    for a, b in cover:
        if a > t:
            holes.append((t, a))
        t = max(t, b)
    if t < duration:
        holes.append((t, duration))
    out = []
    for ha, hb in holes:
        if hb - ha < min_gap:
            continue
        inside = [(max(ha, a), min(hb, b)) for a, b in regions if min(hb, b) > max(ha, a)]
        voiced = sum(b - a for a, b in inside)
        if voiced < min_voiced:
            continue
        s = max(ha, inside[0][0] - 0.3)
        e = min(hb, inside[-1][1] + 0.3)
        if e - s >= 0.3:
            out.append((round(s, 3), round(e, 3), round(voiced, 3)))
    return out


def _pack(gaps: list[tuple[float, float, float]], max_len: float = 28.0, spacer: float = 0.6):
    """Group gap windows into buffers of ≤ max_len s (one Whisper pass each)."""
    pieces = []
    for s, e, _ in gaps:
        while e - s > max_len:
            pieces.append((s, s + max_len - 2))
            s += max_len - 3  # small overlap so a word on the split is heard whole
        pieces.append((s, e))
    packs, cur, used = [], [], 0.0
    for s, e in pieces:
        need = (e - s) + (spacer if cur else 0.0)
        if cur and used + need > max_len:
            packs.append(cur)
            cur, used = [], 0.0
            need = e - s
        cur.append((s, e))
        used += need
    if cur:
        packs.append(cur)
    return packs


def _looks_real(words: list[dict], text: str) -> bool:
    if not words:
        return False
    low = text.lower()
    if any(h in low for h in HALLUCINATIONS):
        return False
    b = text.encode("utf-8")
    if len(b) > 60 and len(b) / max(1, len(zlib.compress(b))) > 3.0:  # "हाँ हाँ हाँ हाँ…" loops
        return False
    mean_p = sum(float(w.get("p", 0)) for w in words) / len(words)
    return mean_p >= _env("WHISPER_GAP_MIN_PROB", 0.3)


def fill_gaps(m, wav, segs: list[dict], language: str | None, *, on_progress: ProgressFn | None = None,
              base: float = 0.85) -> list[dict]:
    """Re-transcribe audio that has speech energy but got no words; return new segments."""
    import numpy as np
    duration = len(wav) / SR
    gaps = find_gaps(segs, speech_regions(wav), duration)
    if not gaps:
        return []
    cap = int(_env("WHISPER_GAP_MAX", 60))
    if len(gaps) > cap:  # the biggest voiced gaps first, then back in time order
        gaps = sorted(sorted(gaps, key=lambda g: -g[2])[:cap])
    log.info("gap re-pass: %d stretches, %.1fs of speech without words", len(gaps), sum(g[2] for g in gaps))
    opts = decode_options(language, None, vad=False)
    opts.update(no_speech_threshold=None, initial_prompt=None)
    spacer = np.zeros(int(0.6 * SR), dtype=np.float32)
    covered = sorted((w["start"], w["end"]) for s in segs for w in s.get("words") or [])
    starts = [a for a, _ in covered]
    import bisect

    def taken(mid: float) -> bool:
        i = bisect.bisect_right(starts, mid) - 1
        return i >= 0 and covered[i][0] - 0.05 <= mid <= covered[i][1] + 0.05

    packs = _pack(gaps)
    new_segs: list[dict] = []
    for pi, pack in enumerate(packs):
        if on_progress:
            on_progress(min(0.98, base + (0.97 - base) * pi / len(packs)), f"छूटे हिस्से दोबारा सुन रहे हैं {pi + 1}/{len(packs)}")
        bufs, table, t = [], [], 0.0  # table: (buf_start, buf_end, src_start)
        for s, e in pack:
            if bufs:
                bufs.append(spacer)
                t += len(spacer) / SR
            piece = wav[int(s * SR):int(e * SR)]
            table.append((t, t + len(piece) / SR, s))
            bufs.append(piece)
            t += len(piece) / SR
        segments, _ = _run(m, np.concatenate(bufs).astype(np.float32), opts)
        for sg in segments:
            sd = _seg_dict(sg)
            mapped = []
            for w in sd["words"]:
                mid = (w["start"] + w["end"]) / 2
                row = min(table, key=lambda r: 0 if r[0] <= mid <= r[1] else min(abs(mid - r[0]), abs(mid - r[1])))
                if not (row[0] - 0.3 <= mid <= row[1] + 0.3):
                    continue  # in the silent spacer: not from our audio
                off = row[2] - row[0]
                ns = min(max(w["start"], row[0]), row[1]) + off
                ne = min(max(w["end"], row[0]), row[1]) + off
                nw = {**w, "start": round(ns, 3), "end": round(max(ne, ns + wordfix.MIN_DUR), 3), "gap": True}
                if not taken((nw["start"] + nw["end"]) / 2):
                    mapped.append(nw)
            text = " ".join(w["w"] for w in mapped)
            if mapped and _looks_real(mapped, text):
                new_segs.append({"start": mapped[0]["start"], "end": mapped[-1]["end"], "text": text,
                                 "words": mapped, "repass": True})
    return new_segs


# ---------------------------------------------------------------- audio + stub

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
