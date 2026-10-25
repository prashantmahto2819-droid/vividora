"""Content planner: trends + the creator's voice → ideas → scripts.

With an LLM key the ideas are written for this channel; without one the
planner still proposes angles by pairing trending topics with the channel's
proven story formats, so the calendar never sits empty.
"""

from __future__ import annotations

import random
import re

from . import llm
from .metadata import voice_text

FORMATS = {
    "short": "YouTube Short / Reel, 30–60 s, one idea, hook in the first 2 s",
    "long": "YouTube video, 6–12 min, story-driven, 3 acts",
    "montage": "music montage, no voice-over, on-screen text lines over B-roll, 20–40 s",
}

ANGLES_HI = [
    "{t} — इससे हमें क्या सीखना चाहिए", "{t}: जो लोग नहीं बताते", "{t} और एक लड़के की कहानी", "क्यों {t} आपकी ज़िंदगी बदल सकता है",
    "{t} से पहले यह 3 बातें जान लो", "{t} — सच या सिर्फ़ शोर?", "अगर आप {t} से परेशान हैं तो यह सुनो",
]
EVERGREEN_HI = [
    "सुबह 4 बजे उठने वाले लड़के की कहानी", "असफलता के बाद क्या करें", "जब कोई साथ न दे", "छोटे शहर से बड़ा सपना",
    "पैसा नहीं, आदत बनाओ", "डर को कैसे हराएँ", "एक साल में ज़िंदगी कैसे बदलें", "मेहनत vs किस्मत",
]


def heuristic_ideas(topics: list[str], count: int, fmt: str, language: str) -> list[dict]:
    out = []
    pool = list(topics)
    random.shuffle(pool)
    for t in pool[: max(0, count - 2)]:
        tmpl = random.choice(ANGLES_HI)
        out.append({"title": tmpl.format(t=t), "hook": f"{t}… लेकिन असली बात कोई नहीं बता रहा।", "angle": f"trend '{t}' को channel के motivational storytelling में बदलें",
                    "outline": "1. hook (2s)\n2. trend का 1-line context\n3. कहानी / उदाहरण\n4. सीख\n5. CTA", "format": fmt, "source": "trend"})
    for t in random.sample(EVERGREEN_HI, min(2, count)):
        out.append({"title": t, "hook": t + " — सुनो।", "angle": "evergreen motivational story", "outline": "1. hook\n2. कहानी\n3. मोड़\n4. सीख\n5. CTA",
                    "format": fmt, "source": "evergreen"})
    return out[:count]


def ideas(topics: list[str], *, count: int = 6, fmt: str = "short", language: str = "hi",
          topic: str | None = None, recent_titles: list[str] | None = None) -> list[dict]:
    base = heuristic_ideas(([topic] if topic else []) + topics, count, fmt, language)
    if not llm.available():
        return base
    voice = voice_text()
    prompt = ((f"Creator voice & style:\n{voice}\n\n" if voice else "") +
              f"Format: {FORMATS.get(fmt, fmt)}. Language: {'Hindi (Devanagari) / Hinglish' if language != 'en' else 'English'}.\n"
              + (f"The creator wants ideas around: {topic}\n" if topic else "") +
              "Trending right now (use only the ones that fit a motivational/story channel; ignore the rest):\n- " + "\n- ".join(topics[:25]) +
              (("\n\nAlready made recently (avoid repeating):\n- " + "\n- ".join(recent_titles[:15])) if recent_titles else "") +
              f"\n\nPropose {count} video ideas. For each: title (max 60 chars, curiosity + benefit), hook (the exact first "
              "sentence to say on camera), angle (why this works for this channel, 1 line), outline (4–6 beats, one per line), "
              'why_now (1 line, or "evergreen"). Reply JSON: {"ideas":[{"title":"","hook":"","angle":"","outline":"","why_now":""}]}')
    data = llm.ask_json(prompt, system="You are the head writer of a Hindi motivational YouTube channel. JSON only.", max_tokens=3000)
    if isinstance(data, dict) and isinstance(data.get("ideas"), list) and data["ideas"]:
        out = []
        for i in data["ideas"][:count]:
            if not isinstance(i, dict) or not i.get("title"):
                continue
            out.append({"title": str(i["title"])[:120], "hook": str(i.get("hook") or "")[:300], "angle": str(i.get("angle") or "")[:300],
                        "outline": str(i.get("outline") or "")[:1500], "format": fmt,
                        "source": "llm" + (f": {i['why_now']}" if i.get("why_now") else "")})
        if out:
            return out
    return base


def script(idea: dict, *, fmt: str = "short", language: str = "hi", target_seconds: int | None = None) -> dict:
    secs = target_seconds or (45 if fmt == "short" else 480 if fmt == "long" else 30)
    words = int(secs * 2.3)  # ~140 Hindi words/minute on camera
    fallback = {"script": (f"[HOOK]\n\n{idea.get('hook') or idea.get('title')}\n\n\n"
                           f"[SETUP]\n\n(किसकी कहानी? कहाँ? एक लाइन में समस्या)\n\n\n"
                           f"[STORY]\n\n{idea.get('outline') or '…'}\n\n\n"
                           f"[TURN]\n\n(वो एक पल जहाँ सब बदला)\n\n\n"
                           f"[LESSON]\n\n(एक लाइन में सीख — वही जो title promise करता है)\n\n\n"
                           f"[CTA]\n\nअगर यह बात दिल को लगी तो follow करो — ऐसी कहानियाँ रोज़ आती हैं।"),
                "words": words, "seconds": secs, "source": "template",
                "shotlist": ["talking head, eye-level", "B-roll: सुबह / रास्ता / मेहनत", "text overlay on the lesson line"]}
    if not llm.available():
        return fallback
    voice = voice_text()
    prompt = ((f"Creator voice & style:\n{voice}\n\n" if voice else "") +
              f"Write the on-camera script for: {idea.get('title')}\nHook: {idea.get('hook')}\nAngle: {idea.get('angle')}\n"
              f"Outline: {idea.get('outline')}\nFormat: {FORMATS.get(fmt, fmt)}, about {secs} seconds (~{words} words).\n"
              f"Language: {'spoken Hindi/Hinglish as this creator talks' if language != 'en' else 'English'}. Spoken, not written — short "
              "sentences, no headings inside the speech. Mark sections in square brackets with a blank line between each: "
              "[HOOK] [SETUP] [STORY] [TURN] [LESSON] [CTA].\n"
              "HOOK RULES (first 2 seconds — most important):\n"
              "- Must create instant curiosity or shock — the viewer decides to stay or scroll in 1.5 seconds\n"
              "- Use one of: a bold contrarian claim, a specific number/stat, a 'what if' question, a pattern interrupt, or an emotional punch\n"
              "- NO generic openings like 'aaj hum baat karenge' or 'kya aapne socha hai'\n"
              "- Keep it under 12 words — punchy, specific, surprising\n"
              "Each section should have 1-2 blank lines between them for breathing room.\n"
              "Also give 4–6 shot/B-roll suggestions and 3 on-screen text lines. "
              'Reply JSON: {"script":"...","shotlist":["..."],"overlays":["..."],"title_options":["..."]}')
    data = llm.ask_json(prompt, system="You are a screenwriter for short motivational videos. JSON only.", max_tokens=3500)
    if isinstance(data, dict) and data.get("script"):
        return {"script": str(data["script"]), "shotlist": [str(x) for x in (data.get("shotlist") or [])][:8],
                "overlays": [str(x) for x in (data.get("overlays") or [])][:6],
                "title_options": [str(x) for x in (data.get("title_options") or [])][:5],
                "words": len(str(data["script"]).split()), "seconds": secs, "source": "llm"}
    return fallback


# ---- script sections: the teleprompter shows [HOOK] … [CTA] as separate blocks and can redo one at a time ----
SECTION_LABELS = {"HOOK": "Hook — पहले 2 सेकंड", "SETUP": "Setup", "STORY": "Story", "TURN": "Turn — वो पल", "LESSON": "Lesson — सीख",
                  "POINTS": "मुख्य बातें", "MAIN": "मुख्य बात", "CTA": "CTA", "CLOSING": "Closing"}
_SEC_RE = re.compile(r"^[ \t]*\[([A-Za-z][A-Za-z /\-]*?)(?:[ \t]*[—\-–:].*?)?\][ \t]*$", re.M)


def parse_sections(script: str) -> list[dict]:
    """[HOOK]…[CTA] markers → [{key, label, text}] in order; a script with no markers is one MAIN block."""
    text = script or ""
    hits = list(_SEC_RE.finditer(text))
    if not hits:
        return [{"key": "MAIN", "label": SECTION_LABELS["MAIN"], "text": text.strip()}] if text.strip() else []
    out = []
    lead = text[:hits[0].start()].strip()
    if lead:
        out.append({"key": "MAIN", "label": SECTION_LABELS["MAIN"], "text": lead})
    for n, h in enumerate(hits):
        key = re.sub(r"[^A-Z]", "", h.group(1).split()[0].upper()) or "MAIN"
        end = hits[n + 1].start() if n + 1 < len(hits) else len(text)
        out.append({"key": key, "label": SECTION_LABELS.get(key, key.title()), "text": text[h.end():end].strip()})
    return out


def structured(script: str) -> dict:
    """The same script as {hook, main, points[], cta, closing} for clients that want fixed slots."""
    secs = parse_sections(script)

    def get(k: str) -> str:
        return "\n\n".join(s["text"] for s in secs if s["key"] == k)
    return {"hook": get("HOOK"), "main": "\n\n".join(x for x in (get("SETUP"), get("STORY"), get("MAIN")) if x),
            "points": [s["text"] for s in secs if s["key"] in ("TURN", "LESSON", "POINTS")],
            "cta": get("CTA"), "closing": get("CLOSING"), "sections": secs}


def join_sections(secs: list[dict]) -> str:
    return "\n\n\n".join(f"[{s['key']}]\n\n{s['text'].strip()}" for s in secs if s.get("text", "").strip() or s.get("key") == "HOOK")


SECTION_MODES = {"rewrite": "Rewrite this section from scratch with a fresh angle; same meaning, different words and rhythm.",
                 "improve": "Make this section stronger: more vivid, more emotional, tighter — keep its length within ±20%.",
                 "shorten": "Cut this section to about half its length without losing the point."}


def regenerate_section(idea: dict, script: str, key: str, mode: str = "rewrite", language: str = "hi") -> dict:
    """One LLM call that rewrites ONLY `key` (HOOK/SETUP/…); the other sections are passed as context and kept verbatim."""
    secs = parse_sections(script)
    key = (key or "").upper()
    cur = next((s for s in secs if s["key"] == key), None)
    if cur is None:
        return {"ok": False, "error": "यह section script में नहीं है"}
    if not llm.available():
        return {"ok": False, "error": "AI key नहीं — section हाथ से बदलें"}
    voice = voice_text()
    others = "\n\n".join(f"[{s['key']}]\n{s['text']}" for s in secs if s["key"] != key)
    prompt = ((f"Creator voice & style:\n{voice}\n\n" if voice else "") +
              f"Video: {idea.get('title')}\nFormat: {FORMATS.get(idea.get('format') or 'short', idea.get('format'))}\n"
              f"Language: {'spoken Hindi/Hinglish as this creator talks' if language != 'en' else 'English'}.\n\n"
              f"The full on-camera script (keep every other section exactly as it is):\n{others}\n\n"
              f"Current [{key}] section:\n{cur['text']}\n\n{SECTION_MODES.get(mode, SECTION_MODES['rewrite'])} "
              'Spoken, short sentences, no headings. Reply JSON: {"text": "..."}')
    data = llm.ask_json(prompt, system="You are a screenwriter for short motivational videos. JSON only.", max_tokens=1200)
    if not isinstance(data, dict) or not str(data.get("text") or "").strip():
        return {"ok": False, "error": llm.LAST_ERROR or "AI से जवाब नहीं आया"}
    new = [{**s, "text": str(data["text"]).strip()} if s["key"] == key else s for s in secs]
    return {"ok": True, "key": key, "text": str(data["text"]).strip(), "script": join_sections(new), "sections": new}


def hook_options(idea: dict, script: str, language: str = "hi", pack: dict | None = None) -> dict:
    """3 alternative hooks. When the project already has an AI pack (transcript) its hooks are reused — no new credit."""
    if pack and isinstance(pack.get("hooks"), list) and pack["hooks"]:
        opts = [str((h.get("say") or h.get("heading")) if isinstance(h, dict) else h) for h in pack["hooks"] if h][:3]
        if opts:
            return {"ok": True, "hooks": opts, "source": "aipack"}
    if not llm.available():
        return {"ok": False, "error": "AI key नहीं", "hooks": []}
    cur = structured(script).get("hook") or idea.get("hook") or ""
    voice = voice_text()
    prompt = ((f"Creator voice & style:\n{voice}\n\n" if voice else "") +
              f"Video: {idea.get('title')}\nAngle: {idea.get('angle')}\nOutline: {idea.get('outline')}\nCurrent hook: {cur}\n"
              f"Language: {'spoken Hindi/Hinglish' if language != 'en' else 'English'}. Write 3 different scroll-stopping opening lines "
              "(≤12 words each, spoken). Each hook MUST:\n"
              "- Use a specific number, name, or detail — never vague\n"
              "- Create a gap the viewer NEEDS to close (curiosity, disbelief, or fear of missing out)\n"
              "- Sound like a friend grabbing your shoulder, not a teacher starting a lecture\n"
              "Types: one a bold contrarian claim, one a 'did you know' with a shocking stat, one an emotional gut-punch. "
              "No clickbait lies. No 'aaj hum baat karenge' or 'kya aapne kabhi socha'. "
              'Reply JSON: {"hooks": ["...", "...", "..."]}')
    data = llm.ask_json(prompt, system="You write viral hooks for short Hindi motivational videos. Every word must earn its place. JSON only.", max_tokens=600)
    hooks = [str(h).strip() for h in ((data.get("hooks") if isinstance(data, dict) else None) or []) if str(h).strip()][:3]
    if not hooks:
        return {"ok": False, "error": llm.LAST_ERROR or "AI से जवाब नहीं आया", "hooks": []}
    return {"ok": True, "hooks": hooks, "source": "llm"}
