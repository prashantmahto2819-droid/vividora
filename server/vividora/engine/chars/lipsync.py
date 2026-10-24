"""Lip-sync without a phoneme model: text → viseme sequence spread over each word's time window
(word timings come from the TTS build: engine/tts.word_times), jaw amplitude from the audio's
loudness (RMS per 20 ms) so the mouth moves with the voice, closes in pauses, and stays shut on
silence. Hindi (Devanagari) and English/Hinglish (Latin) are both mapped.
"""

from __future__ import annotations

import math
import wave
from pathlib import Path

# Devanagari: vowel signs / independent vowels → mouth shape, consonants by articulation
_DEV_VOWEL = {"अ": "AA", "आ": "AA", "ा": "AA", "इ": "EE", "ई": "EE", "ि": "EE", "ी": "EE", "ए": "EE", "ै": "EE", "े": "EE",
              "उ": "OO", "ऊ": "OO", "ु": "OO", "ू": "OO", "ओ": "OO", "ो": "OO", "ौ": "OO", "ऑ": "AA", "ॉ": "AA", "ऋ": "DD"}
_DEV_CONS = {"म": "MBP", "प": "MBP", "ब": "MBP", "भ": "MBP", "फ": "FV", "व": "FV", "ल": "L", "ळ": "L"}
_LAT_VOWEL = {"a": "AA", "e": "EE", "i": "EE", "o": "OO", "u": "OO", "y": "EE"}
_LAT_CONS = {"m": "MBP", "b": "MBP", "p": "MBP", "f": "FV", "v": "FV", "w": "OO", "l": "L", "r": "DD"}


def visemes_of(word: str) -> list[str]:
    out: list[str] = []
    for ch in word:
        lo = ch.lower()
        v = _DEV_VOWEL.get(ch) or _DEV_CONS.get(ch) or _LAT_VOWEL.get(lo) or _LAT_CONS.get(lo)
        if v is None:
            if "ऀ" <= ch <= "ॿ" or lo.isalpha():
                v = "DD"
            else:
                continue
        if out and out[-1] == v:
            continue
        out.append(v)
    return out or ["DD"]


def schedule(words: list[dict], rest_gap: float = 0.08) -> list[tuple[float, float, str]]:
    """[{w, start, end}] → [(t0, t1, viseme)], mouth at rest between words."""
    ev: list[tuple[float, float, str]] = []
    for wd in words:
        a, b = float(wd["start"]), float(wd["end"])
        if b - a < 0.03:
            continue
        vs = visemes_of(str(wd.get("w") or wd.get("word") or ""))
        step = (b - a) / len(vs)
        for i, v in enumerate(vs):
            ev.append((a + i * step, a + (i + 1) * step, v))
    # rest in gaps longer than rest_gap
    out: list[tuple[float, float, str]] = []
    for i, (a, b, v) in enumerate(ev):
        out.append((a, b, v))
        if i + 1 < len(ev) and ev[i + 1][0] - b > rest_gap:
            out.append((b, ev[i + 1][0], "rest"))
    return out


def viseme_at(sched: list[tuple[float, float, str]], t: float) -> str:
    lo, hi = 0, len(sched) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        a, b, v = sched[mid]
        if t < a:
            hi = mid - 1
        elif t >= b:
            lo = mid + 1
        else:
            return v
    return "rest"


def loudness(path: Path, hop: float = 0.02) -> list[float]:
    """RMS envelope (0…1) of a mono/stereo 16-bit wav, one value per `hop` seconds."""
    with wave.open(str(path), "rb") as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = w.readframes(n)
    step = max(1, int(sr * hop))
    vals: list[float] = []
    import array
    a = array.array("h")
    a.frombytes(raw[: len(raw) - (len(raw) % 2)])
    stride = ch
    total = len(a) // stride
    for i in range(0, total, step):
        seg = a[i * stride:(i + step) * stride:stride]
        if not seg:
            break
        rms = math.sqrt(sum(x * x for x in seg) / len(seg)) / 32768.0
        vals.append(rms)
    peak = max(vals) if vals else 1.0
    if peak <= 1e-6:
        return [0.0] * len(vals)
    out = []
    prev = 0.0
    for v in vals:
        x = min(1.0, (v / peak) ** 0.6)
        prev = max(x, prev * 0.6)  # fast attack, slow release
        out.append(prev)
    return out


def jaw_at(env: list[float], t: float, hop: float = 0.02) -> float:
    if not env:
        return 0.0
    i = int(t / hop)
    if i < 0 or i >= len(env):
        return 0.0
    return env[i]


def mouth_at(sched, env, t: float, hop: float = 0.02) -> tuple[str, float]:
    v = viseme_at(sched, t)
    if v == "rest":
        return "rest", 0.0
    j = jaw_at(env, t, hop) if env else 0.7
    if j < 0.08:
        return ("rest" if v == "MBP" else v), 0.0
    return v, j
