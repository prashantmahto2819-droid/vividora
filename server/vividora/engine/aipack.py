"""One AI call per video, used everywhere.

Instead of separate paid calls for hooks, metadata (YouTube / Shorts / Instagram /
Facebook), thumbnail texts, B-roll / hook / background prompts and the pinned
comment, `get(project)` asks once and keeps the answer (keyed by the transcript,
so it only changes when the words change). Every feature reads from this pack
first and falls back to its own rules when no key is set.
"""

from __future__ import annotations

import hashlib
import threading
import time

from . import llm, shorts

BROLL = 6


def _text(project: dict) -> tuple[str, list[dict]]:
    sents = shorts._sentences(project.get("transcript") or {})
    return "\n".join(f"[{i}] {s['text']}" for i, s in enumerate(sents[:70])), sents


def key(project: dict) -> str:
    body, _ = _text(project)
    return hashlib.sha1(body.encode()).hexdigest()[:12]


_memo: dict[str, tuple[float, dict | None]] = {}
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()
RETRY_FAILED_AFTER = 600  # a failed call (no key credit, network down) is not repeated for 10 min


def failed(project: dict) -> bool:
    """The pack call for this transcript failed recently — callers skip their own extra AI calls too."""
    hit = _memo.get(key(project))
    return bool(hit and hit[1] is None and time.time() - hit[0] < RETRY_FAILED_AFTER)


def get(project: dict) -> dict | None:
    """The pack for this transcript: from the project (autopilot stores it in meta.aipack), from this
    process' memory, from the LLM disk cache, or — once — from the LLM. Concurrent callers (thumbnail
    thread + metadata) wait for the one call instead of starting their own."""
    if not llm.available():
        return None
    body, sents = _text(project)
    if not sents:
        return None
    k = key(project)
    stored = (project.get("meta") or {}).get("aipack")
    if isinstance(stored, dict) and stored.get("key") == k and stored.get("hooks"):
        return stored
    with _guard:
        lock = _locks.setdefault(k, threading.Lock())
    with lock:
        hit = _memo.get(k)
        if hit and (hit[1] is not None or time.time() - hit[0] < RETRY_FAILED_AFTER):
            return hit[1]
        res = _ask(project, body)
        _memo[k] = (time.time(), res)
        return res


def _ask(project: dict, body: str) -> dict | None:
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
