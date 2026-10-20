"""Make transcript words safe to use: every spoken word keeps a place and a sane time.

Whisper sometimes gives words without timestamps, zero-length or reversed
times, the same word twice, overlapping words, punctuation as a separate
"word" (। , ?) or a segment with text but no words at all. Before this module
those words were silently dropped from captions and from the plain transcript.
Here we never drop a word that has text; we repair its timing instead.

Pure Python, no package imports: the Windows GPU worker gets a copy of this
file as lib/vividora_wordfix.py (gpu-worker/install.ps1).
"""

from __future__ import annotations

import math

MIN_DUR = 0.06          # shortest time a word is given (s)
EST_PER_CHAR = 0.07     # rough speaking time per character when a time has to be guessed
_PUNCT = set("।॥,.!?;:\"'“”‘’()[]{}…-–—|·•")


def is_punct(text: str) -> bool:
    t = text.strip()
    return bool(t) and all(ch in _PUNCT or ch.isspace() for ch in t)


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) and f >= 0 else None


def _norm(text: str) -> str:
    return "".join(ch for ch in text.strip().lower() if ch not in _PUNCT)


def text_words(text: str, start: float, end: float, p: float = 0.5) -> list[dict]:
    """Words for a segment that has text but no word timings: spread over the segment by length."""
    toks = [t for t in (text or "").split() if t.strip()]
    if not toks:
        return []
    start = _num(start) or 0.0
    end = _num(end)
    total_chars = sum(len(t) for t in toks)
    if end is None or end <= start:
        end = start + max(MIN_DUR * len(toks), EST_PER_CHAR * total_chars)
    out, t = [], start
    span = end - start
    for tok in toks:
        d = span * len(tok) / total_chars
        out.append({"w": tok, "start": round(t, 3), "end": round(t + d, 3), "p": p, "est": True})
        t += d
    return out


def _fill_missing(words: list[dict], lo: float | None, hi: float | None) -> None:
    """Give words without start/end a time between their timed neighbours (in place)."""
    n = len(words)
    i = 0
    while i < n:
        if words[i]["start"] is not None and words[i]["end"] is not None:
            i += 1
            continue
        j = i
        while j < n and (words[j]["start"] is None or words[j]["end"] is None):
            j += 1
        # run i..j-1 lacks a time (one of the two may be known)
        left = words[i - 1]["end"] if i > 0 else (lo if lo is not None else None)
        right = words[j]["start"] if j < n else (hi if hi is not None else None)
        if left is None:
            left = words[i]["start"] if words[i]["start"] is not None else (
                (right - sum(EST_PER_CHAR * max(1, len(w["w"])) for w in words[i:j])) if right is not None else 0.0)
            left = max(0.0, left)
        if right is None or right <= left:
            right = left + sum(EST_PER_CHAR * max(1, len(w["w"])) for w in words[i:j])
        chars = sum(max(1, len(w["w"])) for w in words[i:j])
        t = left
        for w in words[i:j]:
            d = (right - left) * max(1, len(w["w"])) / chars
            s = w["start"] if w["start"] is not None and t <= w["start"] < right else t
            e = w["end"] if w["end"] is not None and s < w["end"] <= right else s + d
            w["start"], w["end"] = s, e
            w["est"] = True
            t = e
        i = j


def resolve_overlaps(words: list[dict]) -> list[dict]:
    """Sorted words, no reversed / zero / overlapping times, exact duplicates merged.

    Works in place on the dicts and returns the (possibly shorter) list. Only a
    true duplicate (same text, mostly the same time) is merged away."""
    words.sort(key=lambda w: (w["start"], w["end"]))
    out: list[dict] = []
    for w in words:
        if w["end"] < w["start"]:
            w["start"], w["end"] = w["end"], w["start"]
        if out:
            prev = out[-1]
            ov = min(prev["end"], w["end"]) - max(prev["start"], w["start"])
            shorter = max(1e-6, min(prev["end"] - prev["start"], w["end"] - w["start"]))
            if _norm(prev["w"]) == _norm(w["w"]) and _norm(w["w"]) and (
                    ov >= 0.5 * shorter or abs(prev["start"] - w["start"]) < 0.02):
                prev["end"] = max(prev["end"], w["end"])
                prev["p"] = max(prev.get("p", 0) or 0, w.get("p", 0) or 0)
                continue
            if w["start"] < prev["end"]:
                if w["start"] >= prev["start"] + MIN_DUR:
                    prev["end"] = w["start"]
                else:
                    w["start"] = prev["start"] + MIN_DUR
                    prev["end"] = w["start"]
        if w["end"] < w["start"] + MIN_DUR:
            w["end"] = w["start"] + MIN_DUR
        out.append(w)
    for w in out:
        w["start"], w["end"] = round(w["start"], 3), round(w["end"], 3)
    return out


def clean_words(raw: list, seg_start=None, seg_end=None) -> list[dict]:
    """Repair one segment's words. Never drops a word that has text."""
    words: list[dict] = []
    pending = ""  # punctuation seen before any word → glued to the next word
    for r in raw or []:
        if not isinstance(r, dict):
            continue
        text = str(r.get("w") if r.get("w") is not None else (r.get("word") or "")).strip()
        if not text:
            continue
        if is_punct(text):
            if words:
                words[-1]["w"] += text
                e = _num(r.get("end"))
                if e is not None and words[-1]["end"] is not None and words[-1]["end"] < e < words[-1]["end"] + 0.5:
                    words[-1]["end"] = e
            else:
                pending += text
            continue
        p = _num(r.get("p", r.get("probability")))
        w = {**{k: v for k, v in r.items() if k not in ("word", "probability")},
             "w": pending + text, "start": _num(r.get("start")), "end": _num(r.get("end")),
             "p": round(p, 3) if p is not None else 0.5}
        pending = ""
        words.append(w)
    if pending:  # only punctuation in the whole segment: keep it on its own
        s = _num(seg_start) or 0.0
        e = _num(seg_end)
        words.append({"w": pending, "start": s, "end": e if e and e > s else s + MIN_DUR, "p": 0.5, "est": True})
    if not words:
        return []
    _fill_missing(words, _num(seg_start), _num(seg_end))
    return resolve_overlaps(words)


def clean_segment(seg: dict) -> dict:
    """A copy of the segment with repaired words; a segment with only text gets estimated words."""
    s = dict(seg)
    words = clean_words(seg.get("words") or [], seg.get("start"), seg.get("end"))
    if not words and (seg.get("text") or "").strip():
        words = clean_words(text_words(seg["text"], seg.get("start") or 0.0, seg.get("end") or 0.0),
                            seg.get("start"), seg.get("end"))
    s["words"] = words
    if words:
        s["start"] = words[0]["start"]
        s["end"] = max(w["end"] for w in words)
        s["text"] = " ".join(w["w"] for w in words)
    return s


def clean_transcript(tr: dict | None) -> dict | None:
    """Every segment repaired, segments in time order, no overlap between segments' words."""
    if not tr or not isinstance(tr, dict):
        return tr
    segs = [clean_segment(s) for s in (tr.get("segments") or []) if isinstance(s, dict)]
    segs = [s for s in segs if s.get("words") or (s.get("text") or "").strip()]
    segs.sort(key=lambda s: (float(s.get("start") or 0.0), float(s.get("end") or 0.0)))
    # words of neighbouring segments may overlap (or repeat at the seam) — fix across the seams
    flat = [(si, w) for si, s in enumerate(segs) for w in s["words"]]
    keep_ids = {id(w) for w in resolve_overlaps([w for _, w in flat])}
    for s in segs:
        if any(id(w) not in keep_ids for w in s["words"]):
            s["words"] = [w for w in s["words"] if id(w) in keep_ids]
            if s["words"]:
                s["text"] = " ".join(w["w"] for w in s["words"])
        s["words"].sort(key=lambda w: w["start"])
        if s["words"]:
            s["start"], s["end"] = s["words"][0]["start"], max(w["end"] for w in s["words"])
    segs = [s for s in segs if s.get("words") or (s.get("text") or "").strip()]
    out = {**tr, "segments": segs}
    out["text"] = " ".join((s.get("text") or "").strip() for s in segs).strip()
    return out


def all_words(tr: dict | None) -> list[dict]:
    """All words of a transcript, repaired and in time order (copies — the transcript is untouched)."""
    if not tr:
        return []
    import copy
    ct = clean_transcript(copy.deepcopy(tr)) or {}
    return [w for s in ct.get("segments") or [] for w in s.get("words") or []]
