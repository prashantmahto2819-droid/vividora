"""Title, description, tags for a finished video — the creator's voice, not
generic SEO soup. LLM when a key is set, offline heuristics otherwise.
The voice file (VOICE_FILE env or server/voice.md) is prepended as style
guidance so suggestions sound like the channel.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import llm
from .captions import plain_text
from .shorts import HOOK_WORDS

STOP = {"है", "हैं", "था", "थी", "थे", "और", "का", "की", "के", "को", "में", "से", "पर", "यह", "वह", "एक", "भी", "तो", "ही",
        "मैं", "आप", "आपको", "हम", "तुम", "उसके", "उसकी", "उसका", "उसने", "जो", "कि", "कुछ", "नहीं", "हूँ", "हो", "था।", "अब",
        "फिर", "वो", "ये", "इस", "उस", "सिर्फ़", "सिर्फ", "बस", "क्या", "लिए", "साथ", "बाद", "पहले", "कर", "करो", "किया",
        "the", "a", "an", "and", "or", "is", "are", "was", "to", "of", "in", "on", "for", "it", "that", "this", "you", "i"}
BASE_TAGS = {"hi": ["motivation", "hindi motivation", "motivational story", "success", "inspiration", "life lessons"],
             "en": ["motivation", "motivational story", "success", "inspiration", "life lessons"]}


def voice_text() -> str:
    for cand in (os.getenv("VOICE_FILE"), str(Path(__file__).resolve().parent.parent.parent / "voice.md")):
        if cand and Path(cand).exists():
            return Path(cand).read_text(encoding="utf-8")[:6000]
    return ""


def _keywords(text: str, n: int = 12) -> list[str]:
    freq: dict[str, int] = {}
    for w in re.findall(r"[\w\u0900-\u0963\u0966-\u097F]+", text.lower()):
        w = w.strip("\u0964\u0965_")
        if len(w) < 3 or w in STOP:
            continue
        freq[w] = freq.get(w, 0) + (3 if w in HOOK_WORDS else 1)
    return [w for w, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:n]]


def _brand(project: dict) -> dict:
    try:
        from .. import db
        ch = db.get("channels", project.get("channel_id") or "")
        return ((ch or {}).get("settings") or {}).get("brand", {}) or {}
    except Exception:  # noqa: BLE001
        return {}


def heuristic(project: dict, platform: str, label: str | None) -> dict:
    tr = project.get("transcript") or {}
    text = plain_text(tr) if tr else ""
    lang = project.get("language") if project.get("language") in ("hi", "en") else "hi"
    short = None
    if label and label.startswith("short-"):
        short = next((s for s in project.get("meta", {}).get("shorts", []) if f"short-{s['id']}" == label), None)
    first = (short or {}).get("text") or text
    sents = re.split(r"(?<=[।.?!])\s+", first.strip())
    title = (short or {}).get("title") or project.get("title") or (sents[0] if sents else "")
    title = title.strip(" ।.")[:95]
    hook = (short or {}).get("hook") or (sents[0][:120] if sents else "")
    summary = " ".join(sents[:4])[:420]
    kws = _keywords(first)
    brand = _brand(project)
    tags = list(dict.fromkeys([*kws[:10], *[h.lstrip("#") for h in (brand.get("hashtags") or "").split()], *BASE_TAGS[lang]]))[:25]
    hashtags = " ".join("#" + t.replace(" ", "") for t in tags[:8])
    cta = brand.get("cta") or "ऐसी और कहानियों के लिए channel subscribe करें।"
    is_short = platform != "youtube" or (label or "").startswith("short-") or label in ("yt-short", "ig-reel", "fb-reel")
    if is_short:
        desc = f"{hook}\n\n{hashtags}"
    else:
        desc = (f"{hook}\n\n{summary}\n\n"
                f"👉 {cta}\n\n{hashtags}")
    return {"title": title, "description": desc.strip(), "tags": tags, "source": "heuristic"}


HASHTAG_CAP = {"youtube": 3, "instagram": 5, "facebook": 5}


def chapters(project: dict, min_total: float = 180, every: float = 90) -> list[tuple[float, str]]:
    """YouTube chapters from the transcript: 00:00 first, ≥ 3 chapters, each ≥ 10 s (YouTube's rules)."""
    from . import shorts
    from .autocut import keep_segments
    tr = project.get("transcript") or {}
    edl = project.get("edl") or {}
    dur = float((project.get("meta") or {}).get("duration") or 0)
    keep = keep_segments({"duration": dur, **edl}) if edl.get("cuts") is not None else [(0.0, dur)]
    # the creator's chapter markers (render settings `markers`, output timeline) win over auto chapters
    from .markers import chapters as marker_chapters
    mk = marker_chapters(((project.get("settings") or {}).get("render") or {}).get("markers"),
                         sum(b - a for a, b in keep or [(0.0, dur)]))
    if mk:
        return mk

    def to_out(t: float) -> float | None:
        o = 0.0
        for a, b in keep or [(0.0, dur)]:
            if a <= t < b:
                return o + (t - a)
            o += b - a
        return None
    out_dur = sum(b - a for a, b in keep or [(0.0, dur)])
    if out_dur < min_total:
        return []
    sents = [s for s in shorts._sentences(tr) if to_out(float(s["start"])) is not None]
    if not sents:
        return []
    n = max(3, min(12, int(out_dur // every)))
    marks: list[tuple[float, str]] = []
    for k in range(n):
        lo, hi = out_dur * k / n, out_dur * (k + 1) / n
        part = [s for s in sents if lo <= (to_out(float(s["start"])) or -1) < hi]
        if not part:
            continue
        best = max(part, key=shorts._score)
        t = 0.0 if not marks else to_out(float(part[0]["start"])) or lo
        title = " ".join(w["w"].strip(" ,।.!?") for w in best["words"][:6])
        if marks and t - marks[-1][0] < 10:
            continue
        marks.append((t, title))
    return marks if len(marks) >= 3 else []


def _stamp(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60:02d}:{t % 60:02d}"


def finalize(md: dict, project: dict, platform: str, label: str | None) -> dict:
    """Platform rules: hashtag caps (YouTube shows 3, Instagram allows 5) and chapters on long YouTube videos."""
    desc = md.get("description") or ""
    cap = HASHTAG_CAP.get(platform, 5)
    seen = 0

    def keep_tag(m):
        nonlocal seen
        seen += 1
        return m.group(0) if seen <= cap else ""
    desc = re.sub(r"#[\w\u0900-\u097F]+", keep_tag, desc)
    desc = re.sub(r"[ \t]+\n", "\n", re.sub(r"[ \t]{2,}", " ", desc)).strip()
    if platform == "youtube" and label == "yt-long" and "00:00" not in desc:
        ch = chapters(project)
        if ch:
            block = "\n".join(f"{_stamp(t)} {title}" for t, title in ch)
            parts = desc.rsplit("\n\n", 1)
            desc = (parts[0] + "\n\n" + block + ("\n\n" + parts[1] if len(parts) > 1 else "")).strip()
    return {**md, "description": desc[:5000]}


def suggest(project: dict, *, platform: str = "youtube", label: str | None = None) -> dict:
    return finalize(_suggest(project, platform=platform, label=label), project, platform, label)


def _suggest(project: dict, *, platform: str = "youtube", label: str | None = None) -> dict:
    base = heuristic(project, platform, label)
    if not llm.available():
        return base
    is_short = platform != "youtube" or (label or "").startswith("short-") or label in ("yt-short", "ig-reel", "fb-reel")
    from . import aipack
    packed = aipack.meta_for(project, platform, is_short and platform == "youtube")
    if packed:
        if not packed["tags"]:
            packed["tags"] = base["tags"]
        return packed
    tr = project.get("transcript") or {}
    text = plain_text(tr)[:6000] if tr else ""
    is_short = platform != "youtube" or (label or "").startswith("short-") or label in ("yt-short", "ig-reel", "fb-reel")
    voice = voice_text()
    head = ("Creator voice & style notes:\n" + voice + "\n\n") if voice else ""
    prompt = (head +
              f"Platform: {platform}{' (short-form, under 60s)' if is_short else ' (long-form video)'}.\n"
              f"Language: {'Hindi (Devanagari), Hinglish allowed' if project.get('language') != 'en' else 'English'}.\n"
              "Write metadata for this video from its transcript. Title: curiosity + benefit, no clickbait lies, "
              "max 70 chars. Description: 2–4 short lines in the creator's voice, then a call to action, then "
              "8–12 hashtags on the last line. Tags: 15–25 search phrases (no #). Reply JSON: "
              '{"title":"...","description":"...","tags":["..."]}\n\nTranscript:\n' + text)
    data = llm.ask_json(prompt, system="You are a YouTube growth editor for a Hindi motivational channel. JSON only.")
    if isinstance(data, dict) and data.get("title"):
        return {"title": str(data["title"])[:100], "description": str(data.get("description") or base["description"])[:5000],
                "tags": [str(t)[:40] for t in (data.get("tags") or base["tags"])][:40], "source": "llm"}
    return base
