"""Autopilot's editing touches, chosen from what is actually said.

* keyword stickers — "पैसा" → 💰, "गलती" → ❌ … popped next to the speaker at the
  moment the word is spoken (with a soft pop sound)
* highlight titles — the strongest lines get a big animated text on top
Everything is placed on the OUTPUT timeline (after cuts), as normal editor items,
so the creator can move or delete any of it before approving.
"""

from __future__ import annotations

import re

from . import shorts
from .autocut import keep_segments

# keyword (normalised) → emoji sticker name in the starter pack, optional sfx
KEYWORDS: list[tuple[tuple[str, ...], str, str | None]] = [
    (("पैसा", "पैसे", "रुपये", "रुपया", "कमाई", "कमाना", "अमीर", "money", "rich", "income", "salary"), "money_bag", "cash"),
    (("सफलता", "सफल", "कामयाब", "कामयाबी", "जीत", "जीता", "success", "win", "winner", "victory"), "trophy", "ding"),
    (("मेहनत", "परिश्रम", "ताकत", "ताक़त", "मज़बूत", "strong", "strength", "hardwork", "gym"), "muscle", None),
    (("सपना", "सपने", "ख्वाब", "ख़्वाब", "dream", "dreams"), "sparkles", "magic_sparkle"),
    (("दिल", "प्यार", "मोहब्बत", "love", "heart"), "heart", None),
    (("समय", "वक्त", "वक़्त", "टाइम", "time", "घंटे", "minutes"), "hourglass", None),
    (("दिमाग", "दिमाग़", "सोच", "सोचो", "सोचिए", "brain", "mind", "think"), "brain", None),
    (("आइडिया", "विचार", "idea", "ideas", "उपाय", "तरीका", "तरीक़ा", "trick"), "bulb", "ding"),
    (("आग", "जोश", "जुनून", "fire", "passion"), "fire", None),
    (("गलती", "गलत", "ग़लती", "भूल", "mistake", "mistakes", "wrong"), "x", "error_buzz"),
    (("सही", "बिल्कुल", "correct", "right"), "check", None),
    (("क्यों", "कैसे", "सवाल", "why", "how", "question"), "thinking", None),
    (("लक्ष्य", "मंज़िल", "मंजिल", "goal", "goals", "target"), "target", None),
    (("तेज़", "तेज", "ग्रोथ", "बढ़", "बढ़ो", "आगे", "growth", "fast", "grow"), "rocket", "whoosh"),
    (("नुकसान", "घाटा", "हार", "loss", "fail", "failure"), "chart_down", None),
    (("दुख", "दर्द", "आँसू", "रोना", "रोया", "sad", "pain", "tears"), "cry", None),
    (("हँसी", "मज़ा", "मजा", "funny", "laugh"), "joy", None),
    (("डर", "खतरा", "ख़तरा", "fear", "danger", "scared"), "warning", None),
    (("पढ़ाई", "किताब", "किताबें", "पढ़ो", "study", "book", "books", "exam"), "book", None),
    (("घर", "परिवार", "family", "home"), "house", None),
    (("भगवान", "प्रार्थना", "दुआ", "god", "pray"), "pray", None),
    (("सुबह", "सवेरे", "morning", "sunrise"), "sunrise", None),
    (("रात", "night"), "moon", None),
    (("नंबर", "पहला", "सबसे", "best", "first", "number"), "hundred_up", None),
    (("हैरान", "चौंक", "shocking", "shock", "unbelievable"), "mind_blown", "impact_boom"),
    (("दोस्त", "दोस्तों", "friends", "friend"), "wave", None),
]
_STRIP = re.compile(r"[^\wऀ-ॿ]")


def _norm(w: str) -> str:
    return _STRIP.sub("", w.lower())


def _to_out(keep: list[tuple[float, float]]):
    def f(t: float) -> float | None:
        o = 0.0
        for a, b in keep:
            if a <= t < b:
                return o + (t - a)
            o += b - a
        return None
    return f


def keyword_stickers(project: dict, library: list[dict], *, out_dur: float, every: float = 7.0,
                     avoid: list[tuple[float, float]] | None = None, sfx_on: bool = True) -> tuple[list[dict], list[dict]]:
    """→ (broll items, sfx items)"""
    tr = project.get("transcript") or {}
    edl = project.get("edl") or {}
    dur = float((project.get("meta") or {}).get("duration") or 0)
    keep = keep_segments(edl) if edl.get("cuts") is not None else [(0.0, dur)]
    to_out = _to_out(keep or [(0.0, dur)])
    stickers = {(x.get("name") or "").lower(): x["id"] for x in library if x.get("kind") == "sticker"}
    sfx_lib = {(x.get("name") or "").lower(): x["id"] for x in library if x.get("kind") == "sfx"}
    lookup = {}
    for words, emoji, snd in KEYWORDS:
        for w in words:
            lookup[_norm(w)] = (emoji, snd)
    items, sounds = [], []
    last = -999.0
    side = 0
    used: dict[str, int] = {}
    for seg in tr.get("segments") or []:
        for w in seg.get("words") or []:
            hit = lookup.get(_norm(w.get("w", "")))
            if not hit:
                continue
            t = to_out(float(w["start"]))
            if t is None or t < 3.0 or t > out_dur - 2.5 or t - last < every:
                continue
            if any(a - 1.5 <= t <= b + .5 for a, b in (avoid or [])):
                continue
            emoji, snd = hit
            sid = stickers.get(emoji) or stickers.get(emoji.replace("_", " "))
            if not sid or used.get(emoji, 0) >= 2:
                continue
            used[emoji] = used.get(emoji, 0) + 1
            x = (.2, .8)[side % 2]
            side += 1
            items.append({"_id": f"ap_kw{len(items)}", "id": sid, "start": round(t, 2), "end": round(min(out_dur, t + 1.6), 2),
                          "fit": "free", "x": x, "y": .32, "scale": .17, "opacity": 1, "rotate": (-8, 8)[side % 2],
                          "anim": "pop", "track": 1, "auto": "keyword"})
            if sfx_on:
                sname = snd or "pop"
                sid2 = sfx_lib.get(sname) or sfx_lib.get(sname.replace("_", " ")) or sfx_lib.get("pop")
                if sid2:
                    sounds.append({"_id": f"ap_kws{len(sounds)}", "id": sid2, "at": round(t, 2), "volume": .35, "track": 1})
            last = t
    return items, sounds


def highlight_titles(project: dict, *, out_dur: float, hook_until: float = 3.5, count: int | None = None,
                     style: dict | None = None, avoid: list[tuple[float, float]] | None = None) -> list[dict]:
    """Big animated text for the strongest lines (not the hook)."""
    tr = project.get("transcript") or {}
    edl = project.get("edl") or {}
    dur = float((project.get("meta") or {}).get("duration") or 0)
    keep = keep_segments(edl) if edl.get("cuts") is not None else [(0.0, dur)]
    to_out = _to_out(keep or [(0.0, dur)])
    sents = shorts._sentences(tr)
    if count is None:
        count = max(1, min(6, int(out_dur // 45) + 1))
    ranked = sorted(sents, key=shorts._score, reverse=True)
    out: list[dict] = []
    st = {"font": "Baloo 2", "size": .075, "color": "#FFD400", "outline": "#000000", "outline_w": .008, "pos": "top", **(style or {})}
    for s in ranked:
        if len(out) >= count:
            break
        t = to_out(float(s["start"]))
        if t is None or t < hook_until or t > out_dur - 3:
            continue
        if any(abs(t - o["start"]) < 12 for o in out) or any(a - 1 <= t <= b for a, b in (avoid or [])):
            continue
        words = [w["w"].strip(" ,।.!?") for w in s["words"]][:6]
        text = " ".join(x for x in words if x)
        if len(text) < 6:
            continue
        end = min(out_dur, t + max(2.0, min(3.5, float(s["end"]) - float(s["start"]))))
        out.append({"_id": f"ap_hl{len(out)}", "text": text, "start": round(t, 2), "end": round(end, 2), **st,
                    "anim_in": "word_pop", "anim_out": "fade", "anim_loop": "none", "track": 0, "auto": "highlight"})
    return sorted(out, key=lambda x: x["start"])
