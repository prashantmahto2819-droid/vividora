"""Hook studio: how strong are the first seconds, and three better options.

score()   — 0–100 for the opening (what viewers decide on): how fast speech starts,
            whether the first line asks / promises / shocks, length of the first
            sentence, on-screen hook text, motion and sound in second one.
options() — three hook lines (heading text + an opening line to say/re-record);
            LLM if a key is set, otherwise rules over the transcript.
"""

from __future__ import annotations

import re

from . import llm, shorts
from .autocut import keep_segments

QUESTION = ("क्या", "क्यों", "कैसे", "कौन", "कब", "कितना", "किसने", "?", "why", "how", "what", "who")
PROMISE = ("राज़", "राज", "तरीका", "तरीक़ा", "सीक्रेट", "secret", "सच", "truth", "कभी", "never", "सबसे", "biggest",
           "गलती", "mistake", "बदल", "change", "पहले", "before", "सिर्फ़", "सिर्फ", "only")
NUM = re.compile(r"\d|एक|दो|तीन|चार|पाँच|पांच|सात|दस|सौ|हज़ार|लाख|करोड़")


def _words_out(project: dict) -> list[dict]:
    tr = project.get("transcript") or {}
    edl = project.get("edl") or {}
    dur = float((project.get("meta") or {}).get("duration") or 0)
    keep = keep_segments({"duration": dur, **edl}) if edl.get("cuts") is not None else [(0.0, dur)]
    out, o = [], 0.0
    words = [w for s in tr.get("segments") or [] for w in s.get("words") or []]
    for a, b in keep or [(0.0, dur)]:
        for w in words:
            if a <= w["start"] < b:
                out.append({**w, "o": o + (w["start"] - a)})
        o += b - a
    return out


def score(project: dict, render_settings: dict | None = None, platform: str = "short") -> dict:
    rs = render_settings or {}
    fx = rs.get("effects") or {}
    ws = _words_out(project)
    reasons, fixes = [], []
    pts = 0
    first = ws[0]["o"] if ws else 99
    window = 3.0 if platform != "long" else 8.0
    early = [w for w in ws if w["o"] < window]
    text = " ".join(w["w"] for w in early)
    low = text.lower()
    # 1) speech starts immediately
    if first <= 0.4:
        pts += 20
    elif first <= 1.0:
        pts += 12
        fixes.append("पहला शब्द 1 सेकंड के अंदर है — शुरू का खाली हिस्सा काटें तो और अच्छा।")
    else:
        fixes.append(f"बोलना {first:.1f}s पर शुरू होता है — पहले {first:.1f}s काट दें (कट tab)।")
    # 2) question / promise / number
    q = any(k in low for k in QUESTION)
    pr = any(k in low for k in PROMISE)
    nm = bool(NUM.search(text))
    pts += 15 if q else 0
    pts += 15 if pr else 0
    pts += 8 if nm else 0
    if q:
        reasons.append("शुरू में सवाल है ✓")
    if pr:
        reasons.append("कुछ नया/राज़ बताने का वादा ✓")
    if nm:
        reasons.append("number/गिनती ✓")
    if not (q or pr):
        fixes.append("पहली line में सवाल या वादा नहीं — नीचे के hook options में से कोई बोलें/लिखें।")
    # 3) first sentence length (short punchy)
    sents = shorts._sentences(project.get("transcript") or {})
    if sents:
        n = len(sents[0]["words"])
        if n <= 12:
            pts += 12
            reasons.append("पहली line छोटी और सीधी ✓")
        else:
            fixes.append(f"पहली line {n} शब्दों की है — 8–12 शब्द में बात कहें।")
    # 4) on-screen hook text
    hk = (rs.get("hook") or {}).get("text") or ""
    if hk:
        pts += 15
        reasons.append("स्क्रीन पर hook heading ✓")
        if len(hk.split()) > 8:
            fixes.append("Hook heading 8 शब्दों से लंबी है — छोटा करें।")
    else:
        fixes.append("स्क्रीन पर hook heading नहीं — Text tab → Heading जोड़ें।")
    # 5) motion + sound in the first second
    zoom = (fx.get("zoom") or {}).get("enabled")
    sfx0 = any(float(s.get("at", 9)) < 1.0 for s in fx.get("sfx") or [])
    pts += 8 if zoom else 0
    pts += 7 if sfx0 else 0
    if not zoom:
        fixes.append("Auto zoom बंद — पहले second में हल्का punch-in ध्यान खींचता है।")
    if not sfx0:
        fixes.append("पहले second में whoosh/pop जैसी आवाज़ नहीं।")
    return {"score": max(0, min(100, pts)), "reasons": reasons, "fixes": fixes, "first_word_at": round(first, 2) if ws else None,
            "opening": text[:160]}


def options(project: dict, n: int = 3, ai: bool = True) -> list[dict]:
    """ai=False: rules over the transcript only (no AI call — autopilot's plan step uses this, the
    one AI pack call happens later in the metadata step)."""
    tr = project.get("transcript") or {}
    sents = shorts._sentences(tr)
    lang = project.get("language") or "hi"
    from . import aipack
    pack = aipack.get(project) if (sents and ai) else None
    if pack and isinstance(pack.get("hooks"), list):
        hs = [{"heading": str(h.get("heading", ""))[:60], "say": str(h.get("say", ""))[:140], "type": h.get("type", ""), "source": "ai"}
              for h in pack["hooks"][:n] if isinstance(h, dict) and h.get("heading")]
        if hs:
            return hs
    if ai and llm.available() and sents and not pack and not aipack.failed(project):
        # Send the FULL transcript (up to 6000 chars) so AI understands the whole video topic
        body = " ".join(s["text"] for s in sents)[:6000]
        res = llm.ask_json(
            f"Video transcript ({'Hindi' if lang != 'en' else 'English'}):\n{body}\n\n"
            "Read the FULL transcript above. Understand the core topic/message of this video.\n"
            "Write 3 different scroll-stopping hook headings for the first 2 seconds.\n"
            "The heading must capture the VIDEO's MAIN TOPIC — NOT just copy the first line.\n"
            "Examples of good headings: 'ये गलती मत करना', '3 दिन में फ़र्क़ दिखेगा', 'Nobody told you this'\n"
            "Each: `heading` = punchy on-screen text summarizing the video, max 6 words; "
            "`say` = an opening line the creator can say/re-record, max 14 words; "
            "`type` = question | shock | promise | story. "
            "IMPORTANT: heading should be a catchy title about the video's TOPIC, not the first sentence.\n"
            "No clickbait lies — only what the video delivers. Same language as transcript.\n"
            "Return JSON {\"hooks\": [{\"heading\",\"say\",\"type\"}]}",
            max_tokens=800)
        hooks = (res or {}).get("hooks") if isinstance(res, dict) else None
        if isinstance(hooks, list) and hooks:
            return [{"heading": str(h.get("heading", ""))[:60], "say": str(h.get("say", ""))[:140], "type": h.get("type", ""), "source": "ai"}
                    for h in hooks[:n] if h.get("heading")]
    # Improved heuristic fallback: extract topic keywords instead of just taking first words
    out = []
    ranked = sorted(sents[:30], key=shorts._score, reverse=True)
    # Collect the most impactful/topic words across top sentences
    all_topic_words = []
    for s in ranked[:10]:
        for w in s["words"]:
            clean = w["w"].strip(" ,।.!?॥\"'")
            if clean and len(clean) > 2 and clean.lower() not in ("the", "and", "but", "for", "are", "was", "has", "its",
                "है", "हैं", "को", "से", "में", "की", "का", "के", "यह", "वो", "तो", "ने", "पर", "जो", "ये", "एक", "अपने"):
                all_topic_words.append(clean)
    # Deduplicate keeping order
    seen = set()
    topic_words = []
    for tw in all_topic_words:
        low = tw.lower()
        if low not in seen:
            seen.add(low)
            topic_words.append(tw)
    for s in ranked:
        words = [w["w"].strip(" ,।.!") for w in s["words"]]
        is_q = "?" in s["text"] or any(k in s["text"] for k in QUESTION[:7])
        is_p = any(k in s["text"].lower() for k in PROMISE)
        has_num = bool(NUM.search(s["text"]))
        # Build a heading from the sentence's key words (not just first 6)
        key_words = [w for w in words if len(w.strip()) > 2][:6]
        head = " ".join(key_words) if key_words else " ".join(words[:6])
        if len(head) < 6 or any(o["heading"] == head for o in out):
            continue
        kind = "question" if is_q else ("promise" if is_p or has_num else "story")
        out.append({"heading": head, "say": " ".join(words[:14]), "type": kind, "source": "transcript"})
        if len(out) >= n:
            break
    # If not enough, generate topic-based headings from collected keywords
    if len(out) < n and topic_words:
        topic_head = " ".join(topic_words[:5])
        if lang != "en":
            out.append({"heading": topic_head, "say": f"{topic_head} — यह वीडियो देखिए", "type": "story", "source": "topic"})
        else:
            out.append({"heading": topic_head, "say": f"Let me tell you about {topic_head}", "type": "story", "source": "topic"})
    if lang != "en" and len(out) < n and sents:
        topic = " ".join(w["w"] for w in sents[0]["words"][:4])
        out.append({"heading": "क्या आप ये जानते हैं?", "say": f"क्या आप जानते हैं — {topic}…", "type": "question", "source": "template"})
    return out[:n]
