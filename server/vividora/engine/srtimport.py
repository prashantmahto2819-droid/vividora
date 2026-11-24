"""A subtitle file made elsewhere (SRT / WebVTT) → Vividora's transcript, so no speech recognition is needed.

Each cue becomes a segment; its words share the cue's time by their length (a subtitle file has no word times —
karaoke captions and text-editing still work, a word's time is right to within a fraction of the cue)."""

from __future__ import annotations

import re

_TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
_TAG = re.compile(r"<[^>]{0,60}>|\{\\[^}]{0,60}\}")


def _sec(h, m, s, ms) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000.0


def parse(text: str, duration: float | None = None) -> dict:
    """→ {"segments": [{start, end, text, words: [{w, start, end}]}], "imported": "srt" | "vtt"}.
    Raises ValueError (Hindi message) when the text holds no timed lines."""
    text = (text or "").replace("﻿", "").replace("\r\n", "\n").replace("\r", "\n")
    kind = "vtt" if text.lstrip().upper().startswith("WEBVTT") else "srt"
    cues: list[tuple[float, float, str]] = []
    cur: list | None = None
    for line in text.split("\n"):
        m = _TIME.search(line)
        if m:
            if cur and len(cur[2]) > 1 and cur[2][-1].isdigit():
                cur[2].pop()                 # no blank line between cues: that number was this cue's index
            if cur and cur[2]:
                cues.append((cur[0], cur[1], " ".join(cur[2])))
            cur = [_sec(*m.group(1, 2, 3, 4)), _sec(*m.group(5, 6, 7, 8)), []]
            continue
        if cur is None:
            continue
        t = _TAG.sub("", line).strip()
        if not t:
            if cur[2]:
                cues.append((cur[0], cur[1], " ".join(cur[2])))
                cur = None
            continue
        cur[2].append(t)
    if cur and cur[2]:
        cues.append((cur[0], cur[1], " ".join(cur[2])))
    cues = sorted((c for c in cues if c[1] > c[0] and c[2].strip()), key=lambda c: c[0])
    if not cues:
        raise ValueError("इस फ़ाइल में समय वाली कोई line नहीं मिली — SRT या VTT फ़ाइल चाहिए (00:00:01,000 --> 00:00:04,000 जैसी lines)")
    segs = []
    for i, (a, b, t) in enumerate(cues):
        if i + 1 < len(cues):
            b = min(b, max(a + 0.2, cues[i + 1][0]))       # subtitles may overlap; spoken words do not
        if duration and a >= duration:
            break
        if duration:
            b = min(b, duration)
        words = [w for w in re.sub(r"\s+", " ", t).strip().split(" ") if w]
        if not words or b - a < 0.05:
            continue
        total = sum(len(w) + 1 for w in words)
        out, pos = [], a
        for w in words:
            d = (b - a) * (len(w) + 1) / total
            out.append({"w": w, "start": round(pos, 3), "end": round(pos + d * 0.94, 3), "p": 1.0})
            pos += d
        segs.append({"start": round(a, 3), "end": round(b, 3), "text": " ".join(words), "words": out})
    if not segs:
        raise ValueError("SRT की सारी lines वीडियो की लंबाई के बाहर हैं — क्या यह इसी वीडियो की फ़ाइल है?")
    return {"segments": segs, "imported": kind}
