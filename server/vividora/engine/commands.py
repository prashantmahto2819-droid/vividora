"""Spoken / typed commands in Hindi, Hinglish or English → an intent.

Used by the 🎤 button in the app and by WhatsApp messages / voice notes.
Rules first (fast, offline); an LLM is asked only when no rule matches.
"""

from __future__ import annotations

import re

from . import llm

# intent → patterns (any match). Order matters: first hit wins.
RULES: list[tuple[str, tuple[str, ...]]] = [
    ("help", ("help", "मदद", "क्या कर सकते", "क्या-क्या", "commands")),
    ("status", ("status", "स्टेटस", "क्या हाल", "कहाँ तक", "कितना हुआ", "हो गया क्या", "update दो", "अपडेट")),
    ("shorts", ("short", "शॉर्ट", "शॉर्ट्स", "reel", "रील")),
    ("render", ("render", "रेंडर", "export", "एक्सपोर्ट", "वीडियो बना", "video bana", "फाइनल बना", "final")),
    ("autopilot", ("autopilot", "ऑटोपायलट", "अपने आप edit", "auto edit", "खुद edit", "editing कर दो", "एडिट कर दो")),
    ("music_off", ("music हटा", "म्यूजिक हटा", "music बंद", "म्यूजिक बंद", "गाना हटा", "no music")),
    ("music", ("music", "म्यूजिक", "म्यूज़िक", "गाना", "background song")),
    ("captions_off", ("caption हटा", "कैप्शन हटा", "caption बंद", "कैप्शन बंद", "subtitle हटा")),
    ("captions_on", ("caption लगा", "कैप्शन लगा", "caption चालू", "subtitle लगा", "captions on")),
    ("zoom_off", ("zoom बंद", "ज़ूम बंद", "zoom हटा", "ज़ूम हटा")),
    ("zoom_on", ("zoom", "ज़ूम", "जूम")),
    ("hook", ("hook", "हुक", "heading", "हेडिंग")),
    ("voice", ("आवाज़", "आवाज", "voice", "noise", "शोर")),
    ("color", ("color", "कलर", "रंग", "filter", "फ़िल्टर", "फिल्टर")),
    ("ideas", ("idea", "आइडिया", "trend", "ट्रेंड", "क्या बनाऊँ", "क्या बनाऊं", "topic")),
    ("thumbnail", ("thumbnail", "थंबनेल")),
    ("schedule", ("schedule", "शेड्यूल", "कब डालें", "कब post", "समय तय")),
    ("publish", ("publish", "पब्लिश", "upload कर", "अपलोड कर", "डाल दो", "post कर", "पोस्ट कर")),
    ("record", ("record", "रिकॉर्ड", "रिकॉर्डिंग")),
    ("new", ("नया project", "नया प्रोजेक्ट", "new project", "upload करना")),
    ("open", ("खोलो", "open", "दिखाओ", "दिखा दो")),
]
NUM_WORDS = {"एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "one": 1, "two": 2,
             "three": 3, "four": 4, "five": 5}
MOODS = {"motivational": ("motivat", "मोटिव", "जोश", "inspir"), "emotional": ("emotion", "इमोशन", "भावुक", "sad", "दुख"),
         "lofi": ("lofi", "लोफ़ी", "chill", "शांत", "calm"), "upbeat": ("upbeat", "happy", "खुश", "energetic", "तेज़"),
         "cinematic": ("cinematic", "सिनेमैटिक", "epic", "dramatic"), "story": ("story", "कहानी")}
VOICE_PRESETS = {"soft": ("soft", "मुलायम", "warm"), "podcast": ("podcast", "पॉडकास्ट", "भारी", "radio"),
                 "bright": ("clear", "साफ़", "साफ", "bright"), "phone": ("phone", "फ़ोन", "फोन", "mobile"), "studio": ("studio", "स्टूडियो")}


def _num(text: str) -> int | None:
    m = re.search(r"\d+", text)
    if m:
        return int(m.group(0))
    for w, n in NUM_WORDS.items():
        if w in text:
            return n
    return None


def parse(text: str) -> dict:
    t = (text or "").strip()
    low = t.lower()
    if not t:
        return {"intent": "none", "text": t}
    for intent, pats in RULES:
        if any(p.lower() in low for p in pats):
            out = {"intent": intent, "text": t}
            if intent == "shorts":
                out["count"] = max(1, min(8, _num(low) or 3))
            if intent == "music":
                out["mood"] = next((m for m, ks in MOODS.items() if any(k in low for k in ks)), None)
            if intent == "voice":
                out["preset"] = next((m for m, ks in VOICE_PRESETS.items() if any(k in low for k in ks)), "studio")
            if intent == "hook":
                q = re.search(r"[\"“'‘](.+?)[\"”'’]", t)
                out["value"] = q.group(1) if q else None
            if intent == "render":
                pres = []
                if "short" in low or "शॉर्ट" in low:
                    pres.append("yt-short")
                if "instagram" in low or "इंस्टा" in low or "reel" in low:
                    pres.append("ig-reel")
                if "facebook" in low or "फेसबुक" in low:
                    pres.append("fb-reel")
                if "youtube" in low or "यूट्यूब" in low or "लंबा" in low or "long" in low:
                    pres.append("yt-long")
                out["presets"] = pres or None
            return out
    if llm.available():
        res = llm.ask_json(
            "A Hindi video creator spoke this command to his video-editing app: " + repr(t) + "\n"
            "Pick one intent from: help, status, shorts, render, autopilot, music, music_off, captions_on, captions_off, zoom_on, zoom_off, "
            "hook, voice, color, ideas, thumbnail, schedule, publish, record, new, open, none. "
            'Reply JSON {"intent": "...", "count": n|null, "mood": str|null, "value": str|null}', max_tokens=200)
        if isinstance(res, dict) and res.get("intent"):
            return {**{k: v for k, v in res.items() if v is not None}, "text": t, "via": "llm"}
    return {"intent": "none", "text": t}


HELP = ("बोलकर / लिखकर ये कर सकते हैं:\n"
        "• “इसके 3 शॉर्ट्स बना दो”  • “render करो” / “instagram reel बनाओ”\n"
        "• “autopilot से edit कर दो”  • “motivational music लगाओ” / “music हटाओ”\n"
        "• “captions हटाओ / लगाओ”  • “zoom बंद करो”  • “आवाज़ podcast जैसी करो”\n"
        "• “hook ‘ज़िंदगी बदल देगी’ लगाओ”  • “आज के ideas दो”  • “status बताओ”\n"
        "Publish हमेशा आपकी मंज़ूरी के बाद ही होगा।")
