"""Shorts factory: find the 20–60 s windows of a long recording that stand on
their own, give each a title + hook. Heuristic scoring works offline; with an
LLM key the candidates are re-ranked and titled by the model.
"""

from __future__ import annotations

import math
import re
from typing import Any

from . import llm
from .autocut import keep_segments

HOOK_WORDS = {
    # Hindi / Hinglish
    "क्यों", "कैसे", "सबसे", "कभी", "राज़", "सच", "गलती", "गलत", "सीख", "सीखा", "बदल", "ज़िंदगी", "जिंदगी", "सपना", "मेहनत",
    "सफल", "असफल", "पैसा", "समय", "आज", "आप", "तुम", "मत", "कभी", "हमेशा", "डर", "हार", "जीत", "सुनो", "याद", "रखो",
    "तीन", "पाँच", "एक", "सिर्फ़", "सिर्फ", "असली", "सच्ची", "कहानी",
    # English
    "why", "how", "secret", "never", "always", "mistake", "truth", "biggest", "best", "worst", "stop", "start",
    "you", "your", "money", "time", "life", "fear", "fail", "win", "lesson", "learn", "story", "one", "three", "five",
}
STRONG_END = ("।", ".", "?", "!", "॥")


def _sentences(transcript: dict) -> list[dict]:
    """Split the word stream at sentence punctuation or long pauses."""
    words = [w for s in transcript.get("segments", []) for w in (s.get("words") or [])]
    out: list[dict] = []
    cur: list[dict] = []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt["start"] - w["end"]) if nxt else 9
        if w["w"].rstrip().endswith(STRONG_END) or gap > 0.8 or len(cur) >= 28:
            out.append({"start": cur[0]["start"], "end": cur[-1]["end"], "words": cur,
                        "text": " ".join(x["w"].strip() for x in cur)})
            cur = []
    if cur:
        out.append({"start": cur[0]["start"], "end": cur[-1]["end"], "words": cur,
                    "text": " ".join(x["w"].strip() for x in cur)})
    return out


def _score(s: dict) -> float:
    toks = [re.sub(r"[^\w]", "", w["w"].lower()) for w in s["words"]]
    n = max(1, len(toks))
    hooks = sum(1 for t in toks if t in HOOK_WORDS)
    sc = hooks / math.sqrt(n) * 2.0
    if "?" in s["text"]:
        sc += 1.2
    if re.search(r"\d", s["text"]):
        sc += 0.6
    if n <= 4:
        sc *= 0.5  # fragments
    rate = n / max(0.5, s["end"] - s["start"])
    if rate < 1.2:
        sc *= 0.7  # slow / hesitant
    return sc


def _in_cut(t: float, keep: list[tuple[float, float]]) -> bool:
    return not any(a <= t <= b for a, b in keep)


def plan(transcript: dict, duration: float, edl: dict | None, *, count: int = 5,
         min_len: float = 22.0, max_len: float = 58.0, language: str = "hi") -> list[dict]:
    sents = _sentences(transcript or {})
    if not sents:
        return []
    if duration < min_len * 2:  # short recordings: still offer something
        min_len = max(5.0, duration * 0.35)
        max_len = max(max_len, duration)
    keep = keep_segments(edl) if edl else [(0.0, duration)]
    scores = [_score(s) for s in sents]
    cands: list[dict] = []
    for i, s in enumerate(sents):
        if _in_cut(s["start"], keep):
            continue
        total, j = 0.0, i
        while j < len(sents) and sents[j]["end"] - s["start"] <= max_len:
            total += scores[j]
            length = sents[j]["end"] - s["start"]
            if length >= min_len:
                n = j - i + 1
                sc = total / math.sqrt(n) + scores[i] * 0.8  # a strong first sentence = a hook
                sc += 0.5 if sents[j]["text"].rstrip().endswith(STRONG_END) else 0
                cands.append({"start": round(max(0.0, s["start"] - 0.25), 2), "end": round(sents[j]["end"] + 0.35, 2),
                              "score": round(sc, 3), "first": s["text"], "text": " ".join(x["text"] for x in sents[i:j + 1])})
            j += 1
    cands.sort(key=lambda c: -c["score"])
    picked: list[dict] = []
    for c in cands:
        if any(not (c["end"] <= p["start"] + 3 or c["start"] >= p["end"] - 3) for p in picked):
            continue
        picked.append(c)
        if len(picked) >= count:
            break
    picked.sort(key=lambda c: c["start"])
    out = []
    for i, c in enumerate(picked, start=1):
        out.append({"id": f"s{i}", "start": c["start"], "end": c["end"], "score": c["score"],
                    "title": _title(c["first"]), "hook": _hook(c["first"]), "text": c["text"][:600], "selected": True})
    return _refine_with_llm(out, language) or out


def _title(text: str, limit: int = 48) -> str:
    t = re.sub(r"\s+", " ", text).strip(" ।.?!")
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + "…"


def _hook(text: str) -> str:
    words = text.split()
    return " ".join(words[:7]).strip(" ।.?!,") if words else ""


def _refine_with_llm(clips: list[dict], language: str) -> list[dict] | None:
    if not clips or not llm.available():
        return None
    lang = {"hi": "Hindi (Devanagari)", "en": "English"}.get(language, "the same language as the transcript (Hindi/Hinglish)")
    prompt = ("You pick YouTube Shorts from a creator's talking-head video. For each candidate clip below, write a "
              f"short punchy title (max 45 chars, in {lang}) and a 3–7 word on-screen hook line (same language), "
              "and a score 1–10 for how well it stands alone. Reply as JSON: "
              '{"clips":[{"id":"s1","title":"...","hook":"...","score":7}]}\n\n'
              + "\n\n".join(f"[{c['id']}] {c['start']}s–{c['end']}s:\n{c['text']}" for c in clips))
    data = llm.ask_json(prompt, system="You are a sharp short-form video editor. JSON only.")
    if not isinstance(data, dict) or not isinstance(data.get("clips"), list):
        return None
    by_id = {c.get("id"): c for c in data["clips"] if isinstance(c, dict)}
    out = []
    for c in clips:
        r = by_id.get(c["id"]) or {}
        out.append({**c, "title": str(r.get("title") or c["title"])[:60], "hook": str(r.get("hook") or c["hook"])[:60],
                    "score": float(r.get("score") or c["score"]), "llm": bool(r)})
    out.sort(key=lambda c: c["start"])
    return out
