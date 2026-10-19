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


def suggest(project: dict, *, platform: str = "youtube", label: str | None = None) -> dict:
    base = heuristic(project, platform, label)
    if not llm.available():
        return base
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
