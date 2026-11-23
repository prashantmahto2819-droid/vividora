"""Visuals from the voice — which spoken lines deserve a picture, and what that picture should be.

`moments()` picks the lines (pure, no network). `plan()` adds for every line a stock-search query, an AI-image prompt,
an AI-video motion prompt and a suggested entrance — from the LLM when one is configured, otherwise from the words
themselves. Nothing is fetched or generated here; the editor shows the plan and the user decides line by line.
All times are SOURCE seconds (the transcript's clock)."""

from __future__ import annotations

import re

EFFECTS = ["none", "zoom", "pop", "slide"]              # entrance of the visual; the editor maps these to its own fields
LAYOUTS = ["cover", "pip"]                              # full screen · small window over the speaker
_STOP = set("""the a an and or but of to in on at for with from by is are was were be been this that these those it its as i you we they he she
me my our your their not no yes so if then than too very just can will would should could have has had do does did about into over under
hai hain tha thi the ka ki ke ko se me mein par aur ya to bhi hi nahi nahin kya kyon kaise jo jab tab yeh ye woh wo is us un in ek ho hota hoti
hote kar karna karte karta raha rahi rahe liye sath saath bahut kuch koi sab apna apni apne hum tum aap main mera meri mere
thing things very good really actually basically like okay well also there here what when where which who how why
है हैं था थी थे का की के को से में पर और या तो भी ही नहीं क्या क्यों कैसे जो जब तब यह ये वह वो इस उस इन उन एक हो होता होती होते कर करना करते
करता रहा रही रहे लिए साथ बहुत कुछ कोई सब अपना अपनी अपने हम तुम आप मैं मेरा मेरी मेरे हाँ आज अभी फिर बस वाला वाली वाले दोस्तों नमस्ते""".split())
# a word = letters incl. the Indic blocks (Devanagari … Malayalam): their vowel signs are not "\w" for Python
_WORD = re.compile(r"(?:[^\W\d_]|[\u0900-\u0DFF]){3,}|\d[\d,.]*")


def _words(text: str) -> list[str]:
    return [w for w in _WORD.findall((text or "").lower()) if w not in _STOP]


def _score(text: str) -> float:
    """How 'showable' a line is: concrete words and numbers beat filler."""
    ws = _words(text)
    return len(ws) + 1.5 * sum(1 for w in ws if w[0].isdigit()) + 0.3 * sum(1 for w in ws if len(w) >= 7)


def moments(segments: list[dict], *, max_items: int = 8, min_gap: float = 5.0, skip_first: float = 2.5,
            cuts: list[dict] | None = None, duration: float | None = None) -> list[dict]:
    """Lines worth illustrating, spread over the video. Lines inside an enabled cut, in the opening seconds (the face /
    hook stays on screen) or too short to read are skipped. Returns [{i, start, end, text}] sorted by time."""
    gone = [(float(c["start"]), float(c["end"])) for c in cuts or [] if c.get("enabled", True)]
    cand = []
    for i, s in enumerate(segments or []):
        a, b, text = float(s.get("start") or 0), float(s.get("end") or 0), (s.get("text") or "").strip()
        if b - a < 1.2 or a < skip_first or len(_words(text)) < 2:
            continue
        if any(a < y and b > x and (min(b, y) - max(a, x)) > 0.5 * (b - a) for x, y in gone):
            continue
        cand.append((_score(text), i, a, b, text))
    if not cand:
        return []
    if duration:
        max_items = max(1, min(max_items, int(duration // max(min_gap, 4)) + 1))
    picked: list[tuple] = []
    for c in sorted(cand, reverse=True):                     # best lines first, but never two close together
        if len(picked) >= max_items:
            break
        if all(abs(c[2] - p[2]) >= min_gap for p in picked):
            picked.append(c)
    out = []
    for _, i, a, b, text in sorted(picked, key=lambda c: c[2]):
        out.append({"i": i, "start": round(a, 2), "end": round(min(b, a + 4.5), 2), "text": text})
    return out


def _fallback(m: dict, niche: str) -> dict:
    ws = _words(m["text"])
    key = " ".join(sorted(set(ws), key=lambda w: (-len(w), ws.index(w)))[:3]) or niche or "background"
    return {"query": key, "image_prompt": f"cinematic photo illustrating: {m['text'][:180]}",
            "video_prompt": "slow cinematic camera push-in, natural motion", "effect": "zoom", "layout": "cover", "by": "words"}


def plan(segments: list[dict], *, niche: str = "", language: str = "", max_items: int = 8, cuts: list[dict] | None = None,
         duration: float | None = None, ask=None) -> list[dict]:
    """moments() + {query, image_prompt, video_prompt, effect, layout, by} for each. `ask(prompt, system=...)` is the LLM
    (engine.llm.ask_json by default); any failure or missing key falls back to the line's own words ("by": "words")."""
    ms = moments(segments, max_items=max_items, cuts=cuts, duration=duration)
    if not ms:
        return []
    ideas: dict[int, dict] = {}
    if ask is None:
        from . import llm
        ask = llm.ask_json if llm.available() else None
    if ask:
        lines = "\n".join(f'{k}. "{m["text"][:220]}"' for k, m in enumerate(ms))
        prompt = (f"A creator is speaking in a video{(' about ' + niche) if niche else ''}. For each numbered spoken line below, describe ONE "
                  "supporting visual (B-roll) that makes the line clearer or more vivid. The lines may be in Hindi or Hinglish; answer in English.\n\n"
                  f"{lines}\n\n"
                  'Return a JSON array, one object per line, in the same order: {"n": line number, '
                  '"query": "2-4 plain English keywords for a stock-footage search (concrete things one can film, no abstract words)", '
                  '"image_prompt": "one sentence for an AI image generator: subject, setting, light, mood — photorealistic, no text or logos, no real named people", '
                  '"video_prompt": "one short sentence describing natural motion for an image-to-video model", '
                  f'"effect": one of {EFFECTS}, "layout": "cover" for a full-screen cutaway or "pip" for a small window while the speaker stays visible}}')
        try:
            res = ask(prompt, system="You are a video editor choosing B-roll. Be concrete and literal. JSON only.")
            for k, r in enumerate(res if isinstance(res, list) else (res or {}).get("items") or []):
                if not isinstance(r, dict):
                    continue
                n = r.get("n") if isinstance(r.get("n"), int) and 0 <= r.get("n") < len(ms) else k
                q = re.sub(r"\s+", " ", str(r.get("query") or "")).strip()[:80]
                ip = re.sub(r"\s+", " ", str(r.get("image_prompt") or "")).strip()[:400]
                if q and ip and n < len(ms):
                    ideas[n] = {"query": q, "image_prompt": ip,
                                "video_prompt": re.sub(r"\s+", " ", str(r.get("video_prompt") or "")).strip()[:200] or "slow cinematic camera push-in",
                                "effect": r.get("effect") if r.get("effect") in EFFECTS else "zoom",
                                "layout": r.get("layout") if r.get("layout") in LAYOUTS else "cover", "by": "ai"}
        except Exception:  # noqa: BLE001 — the plan must still come back; words are the fallback
            ideas = {}
    return [{"id": f"vp{k}", **m, **(ideas.get(k) or _fallback(m, niche))} for k, m in enumerate(ms)]
