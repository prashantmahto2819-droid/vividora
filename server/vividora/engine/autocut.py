"""Find what to cut: long pauses, filler sounds and repeated takes.

Produces an edit decision list (EDL). Nothing is removed until render, and
every cut can be switched off in the dashboard.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from . import wordfix

# Isolated filler sounds (Hindi + English). Real words like "मतलब" are kept on
# purpose — they often carry meaning in Hindi speech.
FILLERS = {
    "अं", "अंं", "आं", "आँ", "अँ", "उम", "उम्", "उम्म", "हम्म", "हम्", "हँ", "एं", "ऍ", "ऐं",
    "um", "umm", "uh", "uhh", "hmm", "hm", "ah", "er", "erm", "[um]", "[uh]", "[filler]",
}

DEFAULTS = {
    "max_pause": 0.55,      # a pause longer than this gets shortened
    "keep_pause": 0.14,     # breathing room left on each side of a cut
    "min_cut": 0.18,        # cuts shorter than this are not worth it
    "cut_fillers": True,
    "cut_retakes": True,
    "retake_similarity": 0.72,
    "retake_max_gap": 6.0,  # s between a failed take and its retry
}

_PUNCT = re.compile(r"[\s\.,!?।॥\"'“”‘’…\-–—:;()\[\]]+")


def norm(word: str) -> str:
    w = unicodedata.normalize("NFC", word).strip().lower()
    return _PUNCT.sub("", w)


_FILLER_NORM = {norm(f) for f in FILLERS}


def words_of(transcript: dict) -> list[dict]:
    """All words in time order. Words without timestamps, zero-length / reversed /
    overlapping words, punctuation tokens and segments with text but no words are
    repaired (engine/wordfix.py) instead of being dropped."""
    out: list[dict] = []
    for w in wordfix.all_words(transcript):
        out.append({"w": w["w"], "start": float(w["start"]), "end": float(w["end"]),
                    "p": float(w.get("p", 1.0) if w.get("p") is not None else 1.0)})
    out.sort(key=lambda x: x["start"])
    return out


def _sentences(words: list[dict], gap: float = 0.7) -> list[list[dict]]:
    sents: list[list[dict]] = []
    cur: list[dict] = []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        ends = w["w"].rstrip().endswith(("।", ".", "?", "!", "॥"))
        if nxt is None or ends or nxt["start"] - w["end"] > gap:
            sents.append(cur)
            cur = []
    return sents


def _word_between(a: float, b: float, words: list[dict]) -> bool:
    """Does a spoken (non-filler) word sit in the kept stretch a..b between two cuts?"""
    if b <= a:
        return False
    for w in words:
        if w["start"] >= b:
            break
        if min(w["end"], b) - max(w["start"], a) > 0.03 and norm(w["w"]) not in _FILLER_NORM:
            return True
    return False


def _merge(cuts: list[dict], words: list[dict] | None = None) -> list[dict]:
    cuts = sorted(cuts, key=lambda c: c["start"])
    merged: list[dict] = []
    for c in cuts:
        if merged and c["start"] <= merged[-1]["end"] + 0.15 and not _word_between(merged[-1]["end"], c["start"], words or []):
            m = merged[-1]
            m["end"] = max(m["end"], c["end"])
            if c["reason"] not in m["reasons"]:
                m["reasons"].append(c["reason"])
            if c.get("text"):
                m["text"] = (m.get("text", "") + " " + c["text"]).strip()
        else:
            merged.append({**c, "reasons": [c["reason"]]})
    return merged


def _protect_words(cut: dict, words: list[dict], pad: float) -> dict | None:
    """Shrink a pause-cut so it never swallows a spoken word."""
    s, e = cut["start"], cut["end"]
    for w in words:
        core_s, core_e = w["start"] + 0.03, w["end"] - 0.03
        if core_e <= s or core_s >= e:
            continue
        # word sits inside the cut — keep the side with more silence
        if core_s - s > e - core_e:
            e = min(e, w["start"] - pad)
        else:
            s = max(s, w["end"] + pad)
        if e <= s:
            return None
    return {**cut, "start": s, "end": e}


def build_edl(transcript: dict, duration: float, silences: list[tuple[float, float]] | None = None,
              options: dict | None = None) -> dict[str, Any]:
    opt = {**DEFAULTS, **(options or {})}
    words = words_of(transcript)
    pad, max_pause, min_cut = opt["keep_pause"], opt["max_pause"], opt["min_cut"]
    raw: list[dict] = []

    def pause(s: float, e: float) -> None:
        """A pause between words. When we know where the audio is really silent, cut only
        there: a stretch without words but with sound is often speech Whisper missed."""
        if not silences:
            raw.append({"start": s, "end": e, "reason": "silence"})
            return
        for a, b in silences:
            cs, ce = max(s, a + pad if a > 0 else 0.0), min(e, b - pad if b < duration - 0.05 else duration)
            if ce - cs > 0:
                raw.append({"start": cs, "end": ce, "reason": "silence"})

    if words:
        if words[0]["start"] - pad > min_cut:
            pause(0.0, words[0]["start"] - pad)
        if duration - (words[-1]["end"] + pad) > min_cut:
            pause(words[-1]["end"] + pad, duration)
        for a, b in zip(words, words[1:]):
            gap = b["start"] - a["end"]
            if gap > max_pause:
                pause(a["end"] + pad, b["start"] - pad)

    for s, e in silences or []:
        if e - s > max_pause:
            c = _protect_words({"start": s + pad, "end": e - pad, "reason": "silence"}, words, pad)
            if c:
                raw.append(c)

    if opt["cut_fillers"]:
        for i, w in enumerate(words):
            # the whole word must be a filler: "अं," is one, "अंदर" / "हम" are words
            if norm(w["w"]) in _FILLER_NORM:
                prev_end = words[i - 1]["end"] if i else 0.0
                nxt_start = words[i + 1]["start"] if i + 1 < len(words) else duration
                # Whisper sometimes stretches a filler over speech it did not write down —
                # cut at most the filler's own sound (≤ 0.8 s), never into the neighbours
                s0 = max(prev_end, w["start"] - 0.04)
                e0 = min(nxt_start, w["end"] + 0.04, s0 + 0.8)
                if e0 > s0:
                    raw.append({"start": s0, "end": e0, "reason": "filler", "text": w["w"]})

    if opt["cut_retakes"]:
        sents = _sentences(words)
        for a, b in zip(sents, sents[1:]):
            aw = [norm(x["w"]) for x in a if norm(x["w"]) and norm(x["w"]) not in _FILLER_NORM]
            bw = [norm(x["w"]) for x in b if norm(x["w"]) and norm(x["w"]) not in _FILLER_NORM]
            # 2-word lines ("बहुत अच्छा।" "बहुत अच्छा लगा।") are style, not retakes; and a retake
            # comes right after the failed try, not much later in the video
            if len(aw) < 3 or len(bw) < 3 or b[0]["start"] - a[-1]["end"] > float(opt.get("retake_max_gap", 6.0)):
                continue
            ratio = SequenceMatcher(None, aw, bw[: len(aw) + 1]).ratio()
            # the take that stays must say (almost) everything the cut one said
            kept = sum(m.size for m in SequenceMatcher(None, aw, bw).get_matching_blocks())
            if ratio >= opt["retake_similarity"] and kept >= 0.75 * len(aw):
                raw.append({
                    "start": max(0.0, a[0]["start"] - 0.05),
                    "end": max(a[0]["start"], b[0]["start"] - 0.05),
                    "reason": "retake",
                    "text": " ".join(x["w"] for x in a),
                })

    cuts = [c for c in _merge([c for c in raw if c["end"] - c["start"] >= min_cut], words)
            if c["end"] - c["start"] >= min_cut]
    for i, c in enumerate(cuts):
        c["id"] = f"c{i + 1}"
        c["start"] = round(max(0.0, c["start"]), 3)
        c["end"] = round(min(duration, c["end"]), 3)
        c["enabled"] = True
        c["reason"] = "retake" if "retake" in c["reasons"] else (
            "filler" if "filler" in c["reasons"] else "silence")
    removed = sum(c["end"] - c["start"] for c in cuts)
    return {
        "version": 1,
        "duration": round(duration, 3),
        "options": opt,
        "cuts": cuts,
        "stats": {
            "cuts": len(cuts),
            "removed_seconds": round(removed, 2),
            "final_seconds": round(duration - removed, 2),
            "by_reason": {r: sum(1 for c in cuts if c["reason"] == r) for r in ("silence", "filler", "retake")},
        },
    }


def keep_segments(edl: dict) -> list[tuple[float, float]]:
    """The parts of the original timeline that stay, after enabled cuts."""
    duration = float(edl["duration"])
    cuts = sorted(
        ((float(c["start"]), float(c["end"])) for c in edl.get("cuts", []) if c.get("enabled", True)),
    )
    keep: list[tuple[float, float]] = []
    t = 0.0
    for s, e in cuts:
        if s > t:
            keep.append((t, s))
        t = max(t, e)
    if t < duration:
        keep.append((t, duration))
    return [(round(s, 3), round(e, 3)) for s, e in keep if e - s >= 0.06]


def remap_words(words: list[dict], keep: list[tuple[float, float]]) -> list[dict]:
    """Move word times onto the new, shorter timeline.

    A word is shown when it is mostly kept (≥ 40 % of it, or ≥ 0.2 s of it, survives
    the cuts) — even when its middle falls in a cut or it straddles a cut and lands in
    two kept pieces. Only words (almost) entirely inside a cut are dropped."""
    offset = 0.0
    segs = []
    for s, e in keep:
        segs.append((s, e, offset))
        offset += e - s

    def to_out(t: float) -> float | None:
        for s, e, off in segs:
            if s <= t <= e:
                return t - s + off
        return None
    return map_words(words, segs, to_out)


def map_words(words: list[dict], keep: list, to_out, min_frac: float = 0.4, min_kept: float = 0.2) -> list[dict]:
    """Map words to output time with to_out(src) → out | None (None = cut away).

    `keep` = kept source ranges (first two items of each tuple are start, end)."""
    out: list[dict] = []
    ranges = sorted((float(k[0]), float(k[1])) for k in keep)
    for w in words:
        s, e = float(w["start"]), max(float(w["end"]), float(w["start"]))
        parts = [(max(s, a), min(e, b)) for a, b in ranges if min(e, b) > max(s, a)]
        if e - s <= 1e-6:  # a point: keep it if it sits in a kept range
            parts = [(s, s)] if any(a <= s <= b for a, b in ranges) else []
        if not parts:
            continue
        kept = sum(b - a for a, b in parts)
        if e - s > 1e-6 and kept / (e - s) < min_frac and kept < min(min_kept, e - s):
            continue
        ns, ne = to_out(parts[0][0]), to_out(parts[-1][1])
        if ns is None:
            continue
        if ne is None or ne < ns:
            ne = ns + (parts[0][1] - parts[0][0])
        out.append({**w, "start": round(ns, 3), "end": round(max(ns + 0.05, ne), 3)})
    out.sort(key=lambda x: x["start"])
    return out
