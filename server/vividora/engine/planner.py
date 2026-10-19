"""Content planner: trends + the creator's voice → ideas → scripts.

With an LLM key the ideas are written for this channel; without one the
planner still proposes angles by pairing trending topics with the channel's
proven story formats, so the calendar never sits empty.
"""

from __future__ import annotations

import random

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
    fallback = {"script": (f"[HOOK — पहले 2 सेकंड]\n{idea.get('hook') or idea.get('title')}\n\n[SETUP]\n(किसकी कहानी? कहाँ? एक लाइन में समस्या)\n\n"
                           f"[STORY]\n{idea.get('outline') or '…'}\n\n[TURN]\n(वो एक पल जहाँ सब बदला)\n\n[LESSON]\n(एक लाइन में सीख — वही जो title promise करता है)\n\n"
                           f"[CTA]\nअगर यह बात दिल को लगी तो follow करो — ऐसी कहानियाँ रोज़ आती हैं।"),
                "words": words, "seconds": secs, "source": "template",
                "shotlist": ["talking head, eye-level", "B-roll: सुबह / रास्ता / मेहनत", "text overlay on the lesson line"]}
    if not llm.available():
        return fallback
    voice = voice_text()
    prompt = ((f"Creator voice & style:\n{voice}\n\n" if voice else "") +
              f"Write the on-camera script for: {idea.get('title')}\nHook: {idea.get('hook')}\nAngle: {idea.get('angle')}\n"
              f"Outline: {idea.get('outline')}\nFormat: {FORMATS.get(fmt, fmt)}, about {secs} seconds (~{words} words).\n"
              f"Language: {'spoken Hindi/Hinglish as this creator talks' if language != 'en' else 'English'}. Spoken, not written — short "
              "sentences, no headings inside the speech. Mark sections in square brackets: [HOOK] [SETUP] [STORY] [TURN] [LESSON] [CTA]. "
              "Also give 4–6 shot/B-roll suggestions and 3 on-screen text lines. "
              'Reply JSON: {"script":"...","shotlist":["..."],"overlays":["..."],"title_options":["..."]}')
    data = llm.ask_json(prompt, system="You are a screenwriter for short motivational videos. JSON only.", max_tokens=3500)
    if isinstance(data, dict) and data.get("script"):
        return {"script": str(data["script"]), "shotlist": [str(x) for x in (data.get("shotlist") or [])][:8],
                "overlays": [str(x) for x in (data.get("overlays") or [])][:6],
                "title_options": [str(x) for x in (data.get("title_options") or [])][:5],
                "words": len(str(data["script"]).split()), "seconds": secs, "source": "llm"}
    return fallback
