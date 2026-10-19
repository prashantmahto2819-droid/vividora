"""Find what to cut: long pauses, filler sounds and repeated takes.

Produces an edit decision list (EDL). Nothing is removed until render, and
every cut can be switched off in the dashboard.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

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
}

_PUNCT = re.compile(r"[\s\.,!?।॥\"'“”‘’…\-–—:;()\[\]]+")


def norm(word: str) -> str:
    w = unicodedata.normalize("NFC", word).strip().lower()
    return _PUNCT.sub("", w)


def words_of(transcript: dict) -> list[dict]:
    out: list[dict] = []
    for seg in transcript.get("segments", []):
        for w in seg.get("words") or []:
            if w.get("end") is None or w.get("start") is None:
                continue
            text = (w.get("w") or w.get("word") or "").strip()
            if not text:
                continue
            out.append({"w": text, "start": float(w["start"]), "end": float(w["end"]),
                        "p": float(w.get("p", w.get("probability", 1.0)) or 1.0)})
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


def _merge(cuts: list[dict]) -> list[dict]:
    cuts = sorted(cuts, key=lambda c: c["start"])
    merged: list[dict] = []
    for c in cuts:
        if merged and c["start"] <= merged[-1]["end"] + 0.15:
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

    if words:
        if words[0]["start"] - pad > min_cut:
            raw.append({"start": 0.0, "end": words[0]["start"] - pad, "reason": "silence"})
        if duration - (words[-1]["end"] + pad) > min_cut:
            raw.append({"start": words[-1]["end"] + pad, "end": duration, "reason": "silence"})
        for a, b in zip(words, words[1:]):
            gap = b["start"] - a["end"]
            if gap > max_pause:
                raw.append({"start": a["end"] + pad, "end": b["start"] - pad, "reason": "silence"})

    for s, e in silences or []:
        if e - s > max_pause:
            c = _protect_words({"start": s + pad, "end": e - pad, "reason": "silence"}, words, pad)
            if c:
                raw.append(c)

    if opt["cut_fillers"]:
        for i, w in enumerate(words):
            if norm(w["w"]) in {norm(f) for f in FILLERS}:
                prev_end = words[i - 1]["end"] if i else 0.0
                nxt_start = words[i + 1]["start"] if i + 1 < len(words) else duration
                raw.append({
                    "start": max(prev_end, w["start"] - 0.04),
                    "end": min(nxt_start, w["end"] + 0.04),
                    "reason": "filler", "text": w["w"],
                })

    if opt["cut_retakes"]:
        sents = _sentences(words)
        for a, b in zip(sents, sents[1:]):
            aw = [norm(x["w"]) for x in a if norm(x["w"])]
            bw = [norm(x["w"]) for x in b if norm(x["w"])]
            if len(aw) < 2 or len(bw) < 2:
                continue
            ratio = SequenceMatcher(None, aw, bw[: len(aw) + 1]).ratio()
            if ratio >= opt["retake_similarity"]:
                raw.append({
                    "start": max(0.0, a[0]["start"] - 0.05),
                    "end": max(a[0]["start"], b[0]["start"] - 0.05),
                    "reason": "retake",
                    "text": " ".join(x["w"] for x in a),
                })

    cuts = [c for c in _merge([c for c in raw if c["end"] - c["start"] >= min_cut])
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
    """Move word times onto the new, shorter timeline. Words inside cuts are dropped."""
    out: list[dict] = []
    offset = 0.0
    seg_starts = []
    for s, e in keep:
        seg_starts.append((s, e, offset))
        offset += e - s
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        for s, e, off in seg_starts:
            if s <= mid <= e:
                ns = max(s, w["start"]) - s + off
                ne = min(e, w["end"]) - s + off
                out.append({**w, "start": round(ns, 3), "end": round(max(ns + 0.05, ne), 3)})
                break
    return out
