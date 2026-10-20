"""One AI call per video, used everywhere.

Instead of separate paid calls for hooks, metadata (YouTube / Shorts / Instagram /
Facebook), thumbnail texts, B-roll / hook / background prompts and the pinned
comment, `get(project)` asks once and keeps the answer (keyed by the transcript,
so it only changes when the words change). Every feature reads from this pack
first and falls back to its own rules when no key is set.
"""

from __future__ import annotations

import hashlib

from . import llm, shorts

BROLL = 6


def _text(project: dict) -> tuple[str, list[dict]]:
    sents = shorts._sentences(project.get("transcript") or {})
    return "\n".join(f"[{i}] {s['text']}" for i, s in enumerate(sents[:70])), sents


def key(project: dict) -> str:
    body, _ = _text(project)
    return hashlib.sha1(body.encode()).hexdigest()[:12]


def get(project: dict) -> dict | None:
    if not llm.available():
        return None
    body, sents = _text(project)
    if not sents:
        return None
    from .metadata import voice_text
    voice = voice_text()
    hindi = project.get("language") != "en"
    lang = "Hindi in Devanagari (Hinglish words allowed)" if hindi else "English"
    prompt = (
        ("Creator voice & style notes:\n" + voice + "\n\n" if voice else "") +
        f"Transcript lines of one video by a Hindi motivational creator (language: {lang}):\n{body}\n\n"
        "Do ALL of the following in one JSON reply. No clickbait lies — only what the video delivers.\n"
        "hooks: 3 scroll-stopping hooks {heading (≤6 words, on-screen), say (≤14 words, line to re-record), type: question|shock|promise|story}.\n"
        "meta.youtube: long-form {title ≤70 chars, description 3–5 lines + CTA + 3 hashtags last line, tags: 15–25 search phrases}.\n"
        "meta.short: YouTube Shorts {title ≤60 chars with #shorts, description 1–2 lines + 3 hashtags, tags 10–15}.\n"
        "meta.instagram: {title (first caption line), description: caption 2–4 lines + CTA + exactly 5 hashtags, tags: []}.\n"
        "meta.facebook: {title, description: 2–3 lines + 3–5 hashtags, tags: []}.\n"
        "thumb_texts: 4 thumbnail texts, 2–5 words, mark one key word as *word*, not repeating the title.\n"
        "pinned_comment: one engaging question to pin under the video.\n"
        "prompts (for AI image/video generators like Grok Imagine, ChatGPT, Veo — write `idea` in ENGLISH, one vivid sentence: "
        "subject, action, setting, camera, light, mood, Indian context, no text in frame, no real celebrities; `hindi` = meaning in Hindi): "
        f"hook {{idea, hindi}} for a 6 s opener; background {{idea}} for behind a person cut-out; thumbnail {{idea}} with empty space for text; "
        f"broll: exactly {BROLL} items {{line: <index of the transcript line>, idea, hindi}} spread through the video.\n"
        'Reply JSON {"hooks": [...], "meta": {"youtube": {...}, "short": {...}, "instagram": {...}, "facebook": {...}}, '
        '"thumb_texts": [...], "pinned_comment": "...", "prompts": {"hook": {...}, "background": {...}, "thumbnail": {...}, "broll": [...]}}')
    res = llm.ask_json(prompt, system="You are the editor, growth strategist and art director of a Hindi motivational channel. JSON only.",
                       max_tokens=6000, timeout=150)
    if not isinstance(res, dict) or not res.get("hooks"):
        return None
    res["key"] = key(project)
    return res


def meta_for(project: dict, platform: str, is_short: bool) -> dict | None:
    pack = get(project)
    m = ((pack or {}).get("meta") or {})
    k = {"instagram": "instagram", "facebook": "facebook"}.get(platform) or ("short" if is_short else "youtube")
    d = m.get(k)
    if isinstance(d, dict) and d.get("title"):
        return {"title": str(d["title"])[:100], "description": str(d.get("description") or "")[:5000],
                "tags": [str(t)[:40] for t in (d.get("tags") or [])][:40], "source": "llm"}
    return None
