"""Generates the built-in industry ad templates (run once: python3 _make.py). Placeholders {{business}} … are
filled by engine/templates.fill(); the main headline comes from the "offer" field."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
IND = {
    "healthcare": ("#00C2A8", "#0B3C49", "#0E6E6B", "Poppins", "पहली जाँच *मुफ़्त*", "आपकी सेहत, हमारी ज़िम्मेदारी"),
    "grocery": ("#FFD400", "#B71C1C", "#E53935", "Mukta", "आज की *भारी छूट*", "ताज़ा सामान, सही दाम"),
    "electronics": ("#00E5FF", "#0D1B2A", "#1B3A5C", "Poppins", "नया मॉडल *आ गया*", "Latest gadgets · EMI available"),
    "automobile": ("#FF6A00", "#111111", "#2B2B2B", "Poppins", "Test drive *आज ही*", "Best deals on new & used cars"),
    "clothing": ("#E040FB", "#1A0B2E", "#4A1C6B", "Lora", "नया *collection*", "Festival special"),
    "fitness": ("#00E676", "#0B1F14", "#13452A", "Poppins", "पहला महीना *free*", "Join today, transform tomorrow"),
    "education": ("#F2B33D", "#132238", "#1E3A5F", "Mukta", "Admission *खुले हैं*", "Batch शुरू — सीट सीमित"),
    "realestate": ("#FFD400", "#0F1319", "#2E3A4F", "Inter", "2 BHK *₹ 45 लाख* से", "Site visit free"),
    "local": ("#FF3B30", "#FFFFFF", "#F2F2F2", "Mukta", "घर बैठे *service*", "Call करें, हम आते हैं"),
    "corporate": ("#00E5FF", "#0A0F1E", "#15213B", "Inter", "हम बनाते हैं *भरोसा*", "Professional services"),
}
LAYOUTS = [
    ("square", "headline", dict(text=dict(x=.5, y=.30, s=1.0), name=(.5, .08), price=(.5, .62), cta=(.5, .80), phone=(.5, .91), addr=(.5, .955))),
    ("vertical", "big_top", dict(text=dict(x=.5, y=.28, s=1.05), name=(.5, .07), price=(.5, .55), cta=(.5, .72), phone=(.5, .88), addr=(.5, .93))),
    ("yt", "spotlight", dict(text=dict(x=.33, y=.45, s=1.0), name=(.33, .10), price=(.78, .40), cta=(.78, .62), phone=(.33, .84), addr=(.33, .92))),
    ("portrait", "gold", dict(text=dict(x=.5, y=.32, s=1.0), name=(.5, .08), price=(.5, .60), cta=(.5, .78), phone=(.5, .90), addr=(.5, .95))),
    ("fb", "headline", dict(text=dict(x=.34, y=.45, s=.95), name=(.34, .10), price=(.80, .38), cta=(.80, .62), phone=(.34, .84), addr=(.34, .93))),
]
NAMES = {
    "healthcare": [("clinic_offer", "Clinic — Offer"), ("clinic_doctor", "Clinic — Doctor timing"), ("hospital_camp", "Health camp")],
    "grocery": [("grocery_sale", "Kirana — Sale"), ("grocery_delivery", "Kirana — Home delivery")],
    "electronics": [("electronics_launch", "Electronics — New launch"), ("electronics_emi", "Electronics — EMI offer")],
    "automobile": [("auto_testdrive", "Automobile — Test drive"), ("auto_exchange", "Automobile — Exchange offer")],
    "clothing": [("fashion_collection", "Fashion — New collection"), ("fashion_sale", "Fashion — Sale"), ("fashion_festive", "Fashion — Festive")],
    "fitness": [("gym_join", "Gym — Join offer"), ("salon_offer", "Salon / Spa — Offer")],
    "education": [("coaching_admission", "Coaching — Admission"), ("coaching_result", "Coaching — Results"), ("coaching_demo", "Coaching — Free demo")],
    "realestate": [("realestate_flat", "Real estate — Flats"), ("construction_service", "Construction — Services")],
    "local": [("local_service", "Local — Service at home"), ("local_repair", "Local — Repair")],
    "corporate": [("corporate_intro", "Corporate — Intro"), ("corporate_hiring", "Corporate — Hiring"), ("creator_promo", "Creator — Channel promo")],
}
HEAD2 = {"clinic_doctor": "डॉक्टर उपलब्ध *रोज़ 10–7*", "hospital_camp": "मुफ़्त *health camp*", "grocery_delivery": "Free *home delivery*",
         "electronics_emi": "0% EMI *आज से*", "auto_exchange": "Exchange पर *₹ 50,000* तक", "fashion_sale": "Flat *50% off*",
         "fashion_festive": "त्योहार का *खास offer*", "salon_offer": "Bridal package *20% off*", "coaching_result": "हमारे students *टॉप पर*",
         "coaching_demo": "Free *demo class*", "construction_service": "घर बनवाएँ *भरोसे से*", "local_repair": "Repair *1 घंटे में*",
         "corporate_hiring": "हम *hire* कर रहे हैं", "creator_promo": "नया video *हर रोज़*"}


def main() -> int:
    made = 0
    for i, (ind, (acc, bg1, bg2, font, head, tag)) in enumerate(IND.items()):
        for n, (tid, label) in enumerate(NAMES[ind]):
            fmt, tpl, L = LAYOUTS[(i + n) % len(LAYOUTS)]
            light = bg1.upper() == "#FFFFFF"
            txtcol = "#111111" if light else "#FFFFFF"

            def lab(key, pos, size, color=txtcol, bgc="", fontf=None):
                d = {"uid": key, "txt": "{{%s}}" % key, "x": pos[0], "y": pos[1], "size": size, "color": color, "font": fontf or font}
                if bgc:
                    d["bg"] = bgc
                return d
            side = fmt in ("yt", "fb")
            stickers = [
                lab("business", L["name"], .05, color=acc),
                {"uid": "pricebox", "shape": "pill", "x": L["price"][0], "y": L["price"][1], "w": .36, "h": .22, "fill": 1, "color": "accent",
                 "shadow": 1, "stroke": "#FFFFFF", "stroke_w": .012},
                {**lab("price", L["price"], .07 if fmt in ("square", "yt", "fb") else .042, color="#111111", fontf="Poppins"), "stroke_w": 0},
                lab("cta", L["cta"], .042, color="#FFFFFF", bgc="#111111" if not light else acc),
                lab("phone", L["phone"], .038, color=txtcol, fontf="Poppins"),
                lab("address", L["addr"], .028, color=txtcol),
                {"uid": "product", "role": "product", "x": .78 if side else .5, "y": .42 if side else .47, "w": .3, "id": None},
            ]
            headline = HEAD2.get(tid, head)
            settings = {"template": tpl, "size": fmt, "no_person": True, "accent": acc, "font": font, "text": "{{offer}}",
                        "style": "box" if n % 3 == 1 else "outline", "hl": acc, "color": txtcol,
                        "bg": {"type": "gradient", "color": bg1, "color2": bg2, "angle": [110, 160, 35, 90, 135][(i + n) % 5]},
                        "vignette": 0 if light else .25, "stickers": stickers, "cutout": False,
                        "layout": {fmt: {"text": L["text"], "_order": ["text", "s:pricebox", "s:price", "s:product", "s:business", "s:cta", "s:phone", "s:address"]}}}
            d = {"id": tid, "name": label, "industry": ind, "format": fmt, "tags": [ind, "ad", fmt],
                 "fields": ["business", "offer", "price", "phone", "address", "cta", "product"],
                 "defaults": {"business": "आपका business", "price": "₹ 999 से", "phone": "98765 43210", "address": "मुख्य बाज़ार, आपका शहर",
                              "cta": "आज ही call करें", "offer": headline, "tagline": tag},
                 "settings": settings}
            (OUT / f"{tid}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            made += 1
    return made


if __name__ == "__main__":
    print("made", main())
