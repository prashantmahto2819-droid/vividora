"""Options a character is built from, and the 200-profile library.

Every option is a plain id → {label (Hindi), …} so the UI lists them straight from the API, and
rig.validate() rejects anything unknown.
"""

from __future__ import annotations

import hashlib
import random

AGES = {"child": "बच्चा", "young": "युवा", "adult": "वयस्क", "elderly": "बुज़ुर्ग"}
GENDERS = {"m": "पुरुष", "f": "महिला"}
BODIES = {"slim": "पतला", "average": "सामान्य", "broad": "चौड़ा", "heavy": "भारी"}
SKIN = ["#F6D7C3", "#EFC3A4", "#E0A981", "#C98A5E", "#B5724A", "#9A5B3A", "#7A452C", "#5C3320"]
HAIR_COLOURS = {"black": "#1B1410", "dark": "#2E1F14", "brown": "#5A3A22", "grey": "#9A9A9A", "white": "#E8E4DC", "auburn": "#7A3A1E"}
HAIR = {
    "short": "छोटे बाल", "buzz": "बहुत छोटे", "side": "साइड पार्टिंग", "spiky": "खड़े बाल", "curly": "घुँघराले",
    "bun": "जूड़ा", "ponytail": "पोनीटेल", "long": "लंबे खुले", "bob": "बॉब कट", "braid": "चोटी", "bald": "गंजा",
    "wavy": "लहरदार",
}
FACIAL = {"none": "कोई नहीं", "moustache": "मूँछ", "beard": "दाढ़ी", "stubble": "हल्की दाढ़ी", "full": "पूरी दाढ़ी"}
EXPRESSIONS = ["neutral", "happy", "sad", "angry", "surprised", "thinking"]
VISEMES = ["rest", "AA", "EE", "OO", "MBP", "FV", "L", "DD"]

# outfit → how it is drawn: top/bottom colours, sleeve length, extra drapes
OUTFITS = {
    "casual": {"label": "कैज़ुअल (टी-शर्ट, जींस)", "top": "#3B82C4", "bottom": "#2F3E5C", "sleeve": "short", "cat": "general"},
    "formal": {"label": "शर्ट-पैंट", "top": "#E9EEF5", "bottom": "#2B2F3A", "sleeve": "long", "cat": "office", "collar": True},
    "suit": {"label": "बिज़नेस सूट", "top": "#23283A", "bottom": "#23283A", "sleeve": "long", "cat": "office", "jacket": True, "tie": "#B3261E"},
    "doctor": {"label": "डॉक्टर (सफ़ेद कोट)", "top": "#F7F7F7", "bottom": "#2B2F3A", "sleeve": "long", "cat": "medical", "coat": True, "prop_default": "stethoscope"},
    "nurse": {"label": "नर्स", "top": "#7FB5E6", "bottom": "#7FB5E6", "sleeve": "short", "cat": "medical", "cap": "nurse"},
    "labcoat": {"label": "लैब कोट", "top": "#F2F2F2", "bottom": "#3A3F4B", "sleeve": "long", "cat": "medical", "coat": True},
    "scrubs": {"label": "सर्जन (स्क्रब्स)", "top": "#2E8B6E", "bottom": "#2E8B6E", "sleeve": "short", "cat": "medical", "mask": True},
    "apron": {"label": "दुकानदार (एप्रन)", "top": "#D9D3C7", "bottom": "#4A4A4A", "sleeve": "short", "cat": "retail", "apron": "#8B2E2E"},
    "teacher": {"label": "शिक्षक (कुर्ता/शर्ट)", "top": "#C8A96E", "bottom": "#3B3B3B", "sleeve": "long", "cat": "education", "collar": True},
    "engineer": {"label": "इंजीनियर (हेलमेट, जैकेट)", "top": "#F2A900", "bottom": "#3D4450", "sleeve": "long", "cat": "industry", "vest": "#FF7A00", "hat": "helmet"},
    "gym": {"label": "जिम (टैंक टॉप)", "top": "#1E1E1E", "bottom": "#4A4A4A", "sleeve": "none", "cat": "fitness"},
    "salon": {"label": "सैलून (काला एप्रन)", "top": "#2B2B2B", "bottom": "#2B2B2B", "sleeve": "short", "cat": "beauty", "apron": "#111111"},
    "driver": {"label": "ड्राइवर (वर्दी)", "top": "#F5F5F5", "bottom": "#1F2A44", "sleeve": "short", "cat": "transport", "hat": "cap"},
    "delivery": {"label": "डिलीवरी (जैकेट, बैग)", "top": "#E8572A", "bottom": "#2B2B2B", "sleeve": "long", "cat": "transport", "prop_default": "bag"},
    "student": {"label": "स्कूल यूनिफ़ॉर्म", "top": "#FFFFFF", "bottom": "#2B3A67", "sleeve": "short", "cat": "education", "tie": "#2B3A67"},
    "police": {"label": "पुलिस", "top": "#8B6B3E", "bottom": "#8B6B3E", "sleeve": "short", "cat": "service", "hat": "cap"},
    "chef": {"label": "शेफ़", "top": "#FFFFFF", "bottom": "#2B2B2B", "sleeve": "long", "cat": "food", "hat": "chef"},
    "kurta": {"label": "कुर्ता-पायजामा", "top": "#F3E9D2", "bottom": "#F3E9D2", "sleeve": "long", "cat": "traditional", "kurta": True},
    "saree": {"label": "साड़ी", "top": "#C2185B", "bottom": "#C2185B", "sleeve": "short", "cat": "traditional", "saree": "#F9C74F"},
    "lehenga": {"label": "लहंगा-चोली (गरबा)", "top": "#E53935", "bottom": "#F4B400", "sleeve": "short", "cat": "festival", "lehenga": True, "mirror": True},
    "punjabi": {"label": "पंजाबी सूट", "top": "#1E88E5", "bottom": "#1E88E5", "sleeve": "long", "cat": "traditional", "kurta": True, "dupatta": "#FFD54F"},
    "turban": {"label": "कुर्ता + पगड़ी", "top": "#FAFAFA", "bottom": "#FAFAFA", "sleeve": "long", "cat": "traditional", "kurta": True, "hat": "turban"},
    "veshti": {"label": "वेष्टि (दक्षिण भारतीय)", "top": "#FFFFFF", "bottom": "#FFFFFF", "sleeve": "short", "cat": "traditional", "veshti": "#C8A600"},
    "halfsaree": {"label": "हाफ़ साड़ी", "top": "#2E7D32", "bottom": "#AD1457", "sleeve": "short", "cat": "traditional", "lehenga": True, "saree": "#FFB300"},
    "kids": {"label": "बच्चों के कपड़े", "top": "#FF8A65", "bottom": "#4FC3F7", "sleeve": "short", "cat": "general"},
    "sportsjersey": {"label": "खेल जर्सी", "top": "#1565C0", "bottom": "#FFFFFF", "sleeve": "short", "cat": "fitness", "number": True},
}
PROPS = {"none": "कुछ नहीं", "stethoscope": "स्टेथोस्कोप", "phone": "फ़ोन", "laptop": "लैपटॉप", "tablet": "टैबलेट", "bag": "बैग",
         "book": "किताब", "clipboard": "क्लिपबोर्ड", "dumbbell": "डम्बल", "scissors": "कैंची", "wrench": "रिंच", "mic": "माइक"}
ACCESSORIES = {"glasses": "चश्मा", "sunglasses": "धूप का चश्मा", "earrings": "कान की बाली", "bindi": "बिंदी", "watch": "घड़ी", "mask": "मास्क"}
HATS = {"none": "कुछ नहीं", "cap": "टोपी", "helmet": "हेलमेट", "chef": "शेफ़ टोपी", "turban": "पगड़ी", "nurse": "नर्स कैप", "hat": "हैट"}
PALETTE = ["#E53935", "#D81B60", "#8E24AA", "#3949AB", "#1E88E5", "#00897B", "#43A047", "#F4B400", "#FB8C00", "#6D4C41", "#546E7A", "#212121", "#F5F5F5"]

# profession → outfit, props, category (the library spreads age/gender/skin/hair over these)
PROFESSIONS = [
    ("doctor", "डॉक्टर", "medical", "doctor", "stethoscope"), ("dentist", "दंत चिकित्सक", "medical", "labcoat", "none"),
    ("gynecologist", "स्त्री रोग विशेषज्ञ", "medical", "doctor", "clipboard"), ("cardiologist", "हृदय रोग विशेषज्ञ", "medical", "doctor", "stethoscope"),
    ("pediatrician", "बाल रोग विशेषज्ञ", "medical", "doctor", "none"), ("surgeon", "सर्जन", "medical", "scrubs", "none"),
    ("physio", "फ़िज़ियोथेरेपिस्ट", "medical", "scrubs", "none"), ("nurse", "नर्स", "medical", "nurse", "clipboard"),
    ("labtech", "लैब टेक्नीशियन", "medical", "labcoat", "tablet"), ("pharmacist", "फ़ार्मासिस्ट", "medical", "labcoat", "none"),
    ("grocer", "किराना दुकानदार", "retail", "apron", "none"), ("retailer", "रिटेल सेल्समैन", "retail", "formal", "tablet"),
    ("cardealer", "ऑटोमोबाइल डीलर", "retail", "suit", "phone"), ("clothseller", "कपड़ा व्यापारी", "retail", "kurta", "none"),
    ("electronics", "इलेक्ट्रॉनिक्स दुकानदार", "retail", "formal", "phone"), ("sweetshop", "मिठाई वाला", "food", "apron", "none"),
    ("chef", "शेफ़", "food", "chef", "none"), ("teacher", "शिक्षक", "education", "teacher", "book"),
    ("professor", "प्रोफ़ेसर", "education", "suit", "book"), ("student", "छात्र", "education", "student", "book"),
    ("collegestudent", "कॉलेज छात्र", "education", "casual", "laptop"), ("engineer", "इंजीनियर", "industry", "engineer", "tablet"),
    ("architect", "आर्किटेक्ट", "industry", "formal", "tablet"), ("mechanic", "मैकेनिक", "industry", "apron", "wrench"),
    ("electrician", "इलेक्ट्रिशियन", "industry", "engineer", "wrench"), ("business", "बिज़नेस मालिक", "office", "suit", "phone"),
    ("entrepreneur", "उद्यमी", "office", "casual", "laptop"), ("employee", "ऑफ़िस कर्मचारी", "office", "formal", "laptop"),
    ("executive", "एग्ज़ीक्यूटिव", "office", "suit", "tablet"), ("hr", "HR मैनेजर", "office", "formal", "clipboard"),
    ("banker", "बैंकर", "office", "suit", "none"), ("trainer", "जिम ट्रेनर", "fitness", "gym", "dumbbell"),
    ("yoga", "योग प्रशिक्षक", "fitness", "gym", "none"), ("athlete", "खिलाड़ी", "fitness", "sportsjersey", "none"),
    ("salon", "सैलून आर्टिस्ट", "beauty", "salon", "scissors"), ("spa", "स्पा थेरेपिस्ट", "beauty", "nurse", "none"),
    ("driver", "ड्राइवर", "transport", "driver", "none"), ("delivery", "डिलीवरी पार्टनर", "transport", "delivery", "bag"),
    ("police", "पुलिस", "service", "police", "none"), ("anchor", "न्यूज़ एंकर", "media", "suit", "mic"),
    ("youtuber", "यूट्यूबर", "media", "casual", "mic"), ("farmer", "किसान", "rural", "kurta", "none"),
    ("homemaker", "गृहिणी", "home", "saree", "none"), ("grandfather", "दादाजी", "home", "kurta", "none"),
    ("grandmother", "दादीजी", "home", "saree", "none"), ("child", "बच्चा", "home", "kids", "none"),
    ("garba", "गरबा डांसर", "festival", "lehenga", "none"), ("punjabi", "पंजाबी (लोहड़ी)", "festival", "punjabi", "none"),
    ("sardar", "सरदार जी", "festival", "turban", "none"), ("south", "दक्षिण भारतीय", "festival", "veshti", "none"),
    ("halfsaree", "हाफ़ साड़ी (दक्षिण)", "festival", "halfsaree", "none"),
]
CATEGORIES = {"medical": "मेडिकल", "retail": "दुकान / रिटेल", "food": "खाना", "education": "शिक्षा", "industry": "इंजीनियरिंग / उद्योग",
              "office": "ऑफ़िस / बिज़नेस", "fitness": "फ़िटनेस", "beauty": "ब्यूटी", "transport": "परिवहन", "service": "सेवा",
              "media": "मीडिया", "rural": "गाँव", "home": "घर-परिवार", "festival": "त्योहार / पारंपरिक"}

_NAMES_M = ["रोहित", "अमन", "विकास", "राजेश", "सुरेश", "अर्जुन", "कबीर", "आरव", "नवीन", "प्रकाश", "संजय", "दीपक", "मनोज", "राहुल", "आदित्य",
            "विवेक", "हर्ष", "करण", "गौरव", "निखिल", "सचिन", "राम", "श्याम", "मोहन", "अनिल", "भूपेंद्र", "गुरप्रीत", "हरजीत", "मुरली", "वेंकट"]
_NAMES_F = ["दिव्या", "प्रिया", "नेहा", "अंजलि", "पूजा", "सुनीता", "रानी", "कविता", "मीरा", "सीमा", "रिया", "ईशा", "आरती", "ज्योति", "सपना",
            "निशा", "रेखा", "गीता", "लक्ष्मी", "पद्मा", "सिमरन", "हरलीन", "दीपिका", "श्रेया", "मालती", "कमला", "अनीता", "वर्षा", "श्वेता", "तनु"]

DEFAULT_PARAMS = {
    "age": "adult", "gender": "m", "skin": SKIN[3], "body": "average", "hair": "short", "hair_color": "black",
    "facial": "none", "outfit": "casual", "top": None, "bottom": None, "prop": "none", "hat": "none",
    "accessories": [], "glasses_color": "#222222", "shoes": "#2B2B2B", "name": "", "profession": "",
}


def _rng(seed: str) -> random.Random:
    return random.Random(int(hashlib.sha1(seed.encode()).hexdigest()[:12], 16))


def _profile(i: int, prof: tuple, variant: int) -> dict:
    pid, label, cat, outfit, prop = prof
    r = _rng(f"vividora-char-{pid}-{variant}")
    if pid in ("child", "student"):
        age = "child"
    elif pid in ("grandfather", "grandmother"):
        age = "elderly"
    elif pid in ("collegestudent", "athlete", "youtuber", "delivery", "garba"):
        age = "young"
    else:
        age = r.choice(["young", "adult", "adult", "elderly"]) if pid not in ("surgeon", "professor", "executive") else r.choice(["adult", "elderly"])
    if pid in ("gynecologist", "nurse", "homemaker", "grandmother", "spa", "garba", "halfsaree"):
        gender = "f"
    elif pid in ("grandfather", "sardar", "south", "farmer", "driver", "mechanic"):
        gender = "m"
    else:
        gender = "f" if variant % 2 else "m"
    o = OUTFITS[outfit]
    # women in traditional roles get the saree / suit variants of a neutral outfit
    if gender == "f" and outfit in ("kurta",):
        outfit = r.choice(["saree", "punjabi"])
    if gender == "f" and outfit == "veshti":
        outfit = "halfsaree"
    if gender == "m" and outfit in ("saree", "lehenga", "halfsaree"):
        outfit = "kurta"
    if age == "child" and outfit not in ("student",):
        outfit = "kids"
    o = OUTFITS[outfit]
    hair_pool_m = ["short", "buzz", "side", "curly", "wavy"] + (["spiky"] if age in ("child", "young") else []) + (["bald"] if age in ("adult", "elderly") else [])
    hair_pool_f = ["bun", "ponytail", "long", "bob", "braid", "wavy", "curly"]
    hair = r.choice(hair_pool_f if gender == "f" else hair_pool_m)
    if o.get("hat") == "turban":
        hair = "buzz"
    hair_color = "grey" if age == "elderly" and r.random() < 0.7 else ("white" if age == "elderly" else r.choice(["black", "black", "dark", "brown", "auburn"]))
    facial = "none"
    if gender == "m" and age in ("adult", "elderly"):
        facial = r.choice(["none", "moustache", "beard", "stubble", "none", "full"])
    if pid == "sardar":
        facial = "full"
    body = r.choice(["slim", "average", "average", "broad", "heavy"]) if age != "child" else r.choice(["slim", "average"])
    if pid in ("trainer", "athlete", "police"):
        body = r.choice(["average", "broad"])
    acc = []
    if r.random() < (0.5 if age in ("adult", "elderly") else 0.2):
        acc.append("glasses")
    if gender == "f" and r.random() < 0.6:
        acc.append("earrings")
    if gender == "f" and outfit in ("saree", "lehenga", "halfsaree", "punjabi") and r.random() < 0.8:
        acc.append("bindi")
    if r.random() < 0.3:
        acc.append("watch")
    top = o["top"] if variant == 0 else r.choice(PALETTE) if outfit in ("casual", "kurta", "saree", "lehenga", "punjabi", "kids", "formal", "teacher", "sportsjersey", "halfsaree") else o["top"]
    name = r.choice(_NAMES_F if gender == "f" else _NAMES_M)
    return {"id": f"c{i:03d}", "name": name, "profession": pid, "label": f"{name} — {label}", "category": cat,
            "params": {**DEFAULT_PARAMS, "age": age, "gender": gender, "skin": r.choice(SKIN), "body": body, "hair": hair,
                       "hair_color": hair_color, "facial": facial, "outfit": outfit, "top": top, "bottom": None,
                       "prop": prop if o.get("prop_default") is None or prop != "none" else o["prop_default"],
                       "hat": o.get("hat", "none"), "accessories": acc, "shoes": r.choice(["#2B2B2B", "#5D4037", "#1A237E", "#F5F5F5"]),
                       "name": name, "profession": label}}


_LIB: list[dict] | None = None


def library() -> list[dict]:
    """200 distinct profiles — four variants of every profession, de-duplicated on their visual tuple."""
    global _LIB
    if _LIB is not None:
        return _LIB
    out: list[dict] = []
    seen: set[tuple] = set()
    i = 1
    variant = 0
    while len(out) < 200:
        for prof in PROFESSIONS:
            if len(out) >= 200:
                break
            p = _profile(i, prof, variant)
            key = tuple((k, tuple(v) if isinstance(v, list) else v) for k, v in sorted(p["params"].items()) if k not in ("name", "profession"))
            if key in seen:
                p = _profile(i, prof, variant + 100)
                key = tuple((k, tuple(v) if isinstance(v, list) else v) for k, v in sorted(p["params"].items()) if k not in ("name", "profession"))
                if key in seen:
                    continue
            seen.add(key)
            out.append(p)
            i += 1
        variant += 1
    _LIB = out
    return out


def get(pid: str) -> dict | None:
    return next((p for p in library() if p["id"] == pid), None)


def options() -> dict:
    return {"ages": AGES, "genders": GENDERS, "bodies": BODIES, "skin": SKIN, "hair": HAIR, "hair_colors": HAIR_COLOURS,
            "facial": FACIAL, "outfits": {k: {"label": v["label"], "cat": v["cat"]} for k, v in OUTFITS.items()},
            "props": PROPS, "accessories": ACCESSORIES, "hats": HATS, "palette": PALETTE, "expressions": EXPRESSIONS,
            "visemes": VISEMES, "categories": CATEGORIES,
            "professions": [{"id": p[0], "label": p[1], "cat": p[2]} for p in PROFESSIONS]}
