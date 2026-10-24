"""Thumbnail studio engine: 1280×720 YouTube thumbnails and 1080×1920 Shorts /
Reels covers, drawn with Pillow. Text goes through libraqm (Pillow's RAQM
layout), so Devanagari conjuncts and matras shape correctly (क्ष, ि, ँ …).

Pieces:
  best_frames()   sample ~20 frames, score sharpness / face / eyes / exposure
  rvm_alpha()     person cutout for ONE frame (Robust Video Matting, ONNX)
  render()        background + person + text + stickers + badge + logo → RGB image
  lint()          title / thumbnail checks (too many words, repeats title, small, low contrast)
  suggest_texts() 2–5 punchy words (LLM when a key is set, heuristics otherwise)

Templates are plain data (TEMPLATES) so the dashboard can list and preview them.
Any colour written as "accent" is replaced by the chosen accent colour.
"""

from __future__ import annotations

import copy
import functools
import math
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, features

FONTS_DIR = Path(__file__).resolve().parent.parent.parent / "fonts"
SIZES = {"yt": (1280, 720), "vertical": (1080, 1920)}
# Template studio formats: key → (width, height, label). "yt" / "vertical" stay the thumbnail keys; every other
# format borrows one of those two layouts ("base") and keeps its own placement under settings.layout[key].
FORMATS = {
    "yt": (1280, 720, "YouTube thumbnail 16:9"),
    "vertical": (1080, 1920, "Shorts / Reels cover 9:16"),
    "story": (1080, 1920, "Story / Reel 9:16"),
    "wa": (1080, 1920, "WhatsApp status 9:16"),
    "square": (1080, 1080, "Instagram post 1:1"),
    "portrait": (1080, 1350, "Instagram portrait 4:5"),
    "fb": (1200, 628, "Facebook post 1.91:1"),
    "custom": (1080, 1080, "Custom size"),
}


def size_px(settings: dict) -> tuple[int, int]:
    """Canvas pixels for a settings dict (custom formats carry their own [w, h])."""
    key = settings.get("size") if settings.get("size") in FORMATS else "yt"
    if key == "custom":
        try:
            w, h = int(settings.get("custom_size", [1080, 1080])[0]), int(settings.get("custom_size", [1080, 1080])[1])
            return max(200, min(4096, w)), max(200, min(4096, h))
        except (TypeError, ValueError, IndexError):
            return 1080, 1080
    return FORMATS[key][0], FORMATS[key][1]


def base_of(settings_or_key, h: int | None = None) -> str:
    """Which thumbnail layout a format uses: wide → "yt", tall/square → "vertical"."""
    if isinstance(settings_or_key, dict):
        w, h = size_px(settings_or_key)
    else:
        w = settings_or_key
    return "yt" if h and w / h >= 1.2 else "vertical"
# family → (file, variable-font instance)
FONTS = {
    "Mukta": ("Mukta-ExtraBold.ttf", None),
    "Baloo 2": ("Baloo2.ttf", b"ExtraBold"),
    "Hind": ("Hind-Bold.ttf", None),
    "Poppins": ("Poppins-Black.ttf", None),
    "Noto Sans Devanagari": ("NotoSansDevanagari.ttf", b"Black"),
    "Baloo 2 Bold": ("Baloo2.ttf", b"SemiBold"),
    "Mukta Bold": ("Mukta-Bold.ttf", None),
    "FreeSerif": ("FreeSerifBold.ttf", None),
    "Inter": ("Inter-Black.otf", None),
    "Lora": ("Lora.ttf", b"Bold"),
}
STYLES = {"outline": "मोटी outline", "shadow": "soft shadow", "box": "पट्टी / box", "highlight": "highlight शब्द",
          "block": "3D block", "double": "दो outline", "neon": "neon glow", "banner": "ribbon / banner", "long": "long shadow"}
GRADES = {"pop": "Pop (चटक)", "vivid": "Vivid", "warm": "Warm / सुनहरा", "cool": "Cool / नीला", "teal": "Teal & orange",
          "cinema": "Cinematic", "dark": "Dark / moody", "mono": "Black & white", "none": "कुछ नहीं"}
OVERLAYS = {"": "कोई नहीं", "rays": "रोशनी की किरणें", "spotlight": "spotlight", "bokeh": "bokeh", "grain": "film grain",
            "haze": "धुंध / smoke"}
BG_TYPES = {"": "template जैसा", "photo": "पूरा frame", "blur": "धुँधला frame", "solid": "एक रंग", "gradient": "gradient",
            "image": "library image"}
SHAPES = {"arrow": "तीर", "curve": "मुड़ा तीर", "circle": "गोला", "underline": "underline", "rect": "box / frame",
          "burst": "burst / star", "cross": "✕ गलत", "tick": "✓ सही", "rrect": "rectangle", "disc": "circle (भरा)", "line": "line",
          "pill": "pill / button"}
RAQM = features.check("raqm")


def _t(id_, label, desc, **kw) -> dict:
    return {"id": id_, "label": label, "desc": desc, **kw}


# Layout templates. Fractions are of the canvas (x of width, y of height).
TEMPLATES: list[dict] = [
    _t("face_right", "चेहरा दाएँ · text बाएँ", "सबसे ज़्यादा चलने वाला layout",
       accent="#FFD400", bg={"type": "blur", "blur": 22, "dim": 0.45},
       person={"x": 0.73, "face_y": 0.40, "face_h": 0.40, "stroke": "#FFFFFF", "shadow": True},
       text={"box": [0.04, 0.08, 0.54, 0.92], "align": "left", "valign": "center", "max": 0.21, "font": "Mukta",
             "color": "#FFFFFF", "hl": "accent", "style": "outline"},
       scrim={"side": "left", "color": "#000000", "alpha": 0.55, "extent": 0.62}, grade="pop",
       vertical={"person": {"x": 0.5, "face_y": 0.66, "face_h": 0.26},
                 "text": {"box": [0.06, 0.07, 0.94, 0.42], "align": "center", "valign": "center", "max": 0.075},
                 "scrim": {"side": "top", "extent": 0.55}}),
    _t("face_left", "चेहरा बाएँ · text दाएँ", "उल्टा layout — variety के लिए",
       accent="#00E5FF", bg={"type": "blur", "blur": 22, "dim": 0.45},
       person={"x": 0.27, "face_y": 0.40, "face_h": 0.40, "stroke": "#FFFFFF", "shadow": True},
       text={"box": [0.47, 0.08, 0.96, 0.92], "align": "right", "valign": "center", "max": 0.21, "font": "Mukta",
             "color": "#FFFFFF", "hl": "accent", "style": "outline"},
       scrim={"side": "right", "color": "#000000", "alpha": 0.55, "extent": 0.62}, grade="pop",
       vertical={"person": {"x": 0.5, "face_y": 0.66, "face_h": 0.26},
                 "text": {"box": [0.06, 0.07, 0.94, 0.42], "align": "center", "valign": "center", "max": 0.075},
                 "scrim": {"side": "top", "extent": 0.55}}),
    _t("big_top", "बड़ा text ऊपर · चेहरा नीचे", "text सबसे बड़ा, चेहरा नीचे बीच में",
       accent="#FF3B30", bg={"type": "gradient", "color": "#0F2027", "color2": "#2C5364", "angle": 90},
       person={"x": 0.5, "face_y": 0.68, "face_h": 0.34, "stroke": "#FFFFFF", "glow": None, "shadow": True},
       text={"box": [0.04, 0.03, 0.96, 0.45], "align": "center", "valign": "center", "max": 0.2, "font": "Baloo 2",
             "color": "#FFFFFF", "hl": "accent", "style": "block", "stroke": "#000000"},
       scrim={"side": "top", "color": "#000000", "alpha": 0.5, "extent": 0.5}, grade="pop",
       vertical={"person": {"face_y": 0.7, "face_h": 0.24}, "text": {"box": [0.05, 0.05, 0.95, 0.45], "max": 0.08}}),
    _t("split", "पहले / बाद में", "दो frames — before / after, तुलना",
       accent="#FFD400", bg={"type": "split"}, person=None,
       text={"box": [0.04, 0.03, 0.96, 0.30], "align": "center", "valign": "top", "max": 0.14, "font": "Mukta",
             "color": "#FFFFFF", "hl": "accent", "style": "outline"},
       labels=[{"text": "पहले", "x": 0.25, "y": 0.88, "bg": "#D71920", "color": "#FFFFFF", "size": 0.075},
               {"text": "बाद में", "x": 0.75, "y": 0.88, "bg": "#1FAA59", "color": "#FFFFFF", "size": 0.075}],
       shapes=[{"type": "arrow", "x": 0.5, "y": 0.6, "len": 0.16, "rot": 0, "color": "accent"}], grade="pop",
       vertical={"text": {"box": [0.05, 0.03, 0.95, 0.16], "max": 0.06},
                 "labels": [{"text": "पहले", "x": 0.5, "y": 0.46, "size": 0.04}, {"text": "बाद में", "x": 0.5, "y": 0.95, "size": 0.04}],
                 "shapes": [{"type": "arrow", "x": 0.86, "y": 0.5, "len": 0.14, "rot": 90}]}),
    _t("number", "Number badge", "“3 गलतियाँ” — बड़ा नंबर, list वाले वीडियो",
       accent="#FFD400", bg={"type": "solid", "color": "#111827"},
       person={"x": 0.74, "face_y": 0.42, "face_h": 0.40, "stroke": "#FFFFFF", "glow": "accent", "shadow": True},
       badge={"x": 0.15, "y": 0.30, "r": 0.15, "color": "accent", "text_color": "#111111"},
       text={"box": [0.04, 0.50, 0.56, 0.94], "align": "left", "valign": "center", "max": 0.17, "font": "Mukta",
             "color": "#FFFFFF", "hl": "accent", "style": "outline", "strip_number": True},
       scrim={"side": "left", "color": "#000000", "alpha": 0.4, "extent": 0.6}, grade="pop",
       vertical={"person": {"x": 0.5, "face_y": 0.68, "face_h": 0.25}, "badge": {"x": 0.5, "y": 0.13, "r": 0.15},
                 "text": {"box": [0.06, 0.23, 0.94, 0.46], "align": "center", "max": 0.07}}),
    _t("red_arrow", "लाल तीर", "तीर + गोला — किसी चीज़ की तरफ़ ध्यान",
       accent="#FF2D2D", bg={"type": "photo"},
       person={"x": 0.70, "face_y": 0.42, "face_h": 0.40, "stroke": "#FFFFFF", "shadow": True},
       text={"box": [0.04, 0.06, 0.52, 0.62], "align": "left", "valign": "top", "max": 0.19, "font": "Mukta",
             "color": "#FFFFFF", "hl": "accent", "style": "outline"},
       shapes=[{"type": "arrow", "x": 0.30, "y": 0.80, "len": 0.22, "rot": -15, "color": "accent"},
               {"type": "circle", "x": 0.5, "y": 0.72, "w": 0.16, "color": "accent"}],
       scrim={"side": "left", "color": "#000000", "alpha": 0.6, "extent": 0.6}, grade="pop",
       vertical={"person": {"x": 0.5, "face_y": 0.66, "face_h": 0.25},
                 "text": {"box": [0.06, 0.06, 0.94, 0.38], "align": "center", "max": 0.075},
                 "shapes": [{"type": "arrow", "x": 0.25, "y": 0.5, "len": 0.25, "rot": 35},
                            {"type": "circle", "x": 0.72, "y": 0.6, "w": 0.3}],
                 "scrim": {"side": "top", "extent": 0.5}}),
    _t("news", "News style", "Breaking-news पट्टी — खबर / update",
       accent="#D71920", bg={"type": "photo"},
       person={"x": 0.70, "face_y": 0.36, "face_h": 0.38, "stroke": None, "shadow": False},
       text={"box": [0.0, 0.62, 1.0, 0.98], "align": "left", "valign": "bottom", "max": 0.13, "font": "Hind",
             "color": "#FFFFFF", "hl": "#FFD400", "style": "box", "box_color": "accent",
             "line_boxes": ["accent", "#FFFFFF", "#111111"], "line_colors": ["#FFFFFF", "#111111", "#FFFFFF"], "pad_x": 0.035},
       labels=[{"text": "BREAKING", "x": 0.11, "y": 0.09, "bg": "#FFFFFF", "color": "accent", "size": 0.055, "font": "Poppins"}],
       grade="pop", vignette=0.25,
       vertical={"person": {"x": 0.5, "face_y": 0.36, "face_h": 0.22},
                 "text": {"box": [0.0, 0.62, 1.0, 0.92], "max": 0.06},
                 "labels": [{"text": "BREAKING", "x": 0.22, "y": 0.06, "size": 0.03}]}),
    _t("minimal", "Minimal", "साफ़ frame, छोटा सधा हुआ text",
       accent="#FFFFFF", bg={"type": "photo"},
       person={"x": 0.66, "face_y": 0.42, "face_h": 0.34, "stroke": None, "shadow": False},
       text={"box": [0.05, 0.55, 0.62, 0.93], "align": "left", "valign": "bottom", "max": 0.13, "font": "Poppins",
             "color": "#FFFFFF", "hl": "#FFD400", "style": "shadow"},
       scrim={"side": "bottom", "color": "#000000", "alpha": 0.7, "extent": 0.55}, grade=None,
       vertical={"person": {"x": 0.5, "face_y": 0.4, "face_h": 0.22},
                 "text": {"box": [0.07, 0.62, 0.93, 0.9], "align": "center", "max": 0.06}}),
    _t("emotional", "Emotional dark", "गहरा, भावुक — कहानी / दर्द / संघर्ष",
       accent="#FF4D4D", bg={"type": "blur", "blur": 28, "dim": 0.7, "gray": True},
       person={"x": 0.70, "face_y": 0.42, "face_h": 0.42, "stroke": None, "glow": "#FFFFFF", "shadow": True},
       text={"box": [0.04, 0.12, 0.55, 0.88], "align": "left", "valign": "center", "max": 0.17, "font": "Baloo 2",
             "color": "#F5F5F5", "hl": "accent", "style": "shadow"},
       grade="dark", vignette=0.75,
       vertical={"person": {"x": 0.5, "face_y": 0.66, "face_h": 0.26},
                 "text": {"box": [0.06, 0.08, 0.94, 0.42], "align": "center", "max": 0.075}}),
    _t("gold", "Gold premium", "काला + सुनहरा — premium / success / पैसा",
       accent="#F2B33D", bg={"type": "gradient", "color": "#000000", "color2": "#2B1F08", "angle": 120},
       person={"x": 0.72, "face_y": 0.42, "face_h": 0.40, "stroke": "accent", "glow": "accent", "shadow": True},
       text={"box": [0.05, 0.12, 0.55, 0.88], "align": "left", "valign": "center", "max": 0.18, "font": "Poppins",
             "color": "accent", "hl": "#FFFFFF", "style": "block", "stroke": "#3A2600"},
       border={"color": "accent", "width": 0.012}, grade="warm",
       vertical={"person": {"x": 0.5, "face_y": 0.67, "face_h": 0.26},
                 "text": {"box": [0.07, 0.08, 0.93, 0.42], "align": "center", "max": 0.075}}),
    _t("bold_box", "Yellow box", "पीली पट्टी पर काला text — दूर से पढ़ने में आसान",
       accent="#FFD400", bg={"type": "blur", "blur": 16, "dim": 0.3},
       person={"x": 0.28, "face_y": 0.42, "face_h": 0.42, "stroke": "#FFFFFF", "shadow": True},
       text={"box": [0.50, 0.12, 0.97, 0.88], "align": "right", "valign": "center", "max": 0.16, "font": "Mukta",
             "color": "#111111", "hl": "#D71920", "style": "box", "box_color": "accent", "rotate": -3},
       grade="pop",
       vertical={"person": {"x": 0.5, "face_y": 0.66, "face_h": 0.26},
                 "text": {"box": [0.06, 0.08, 0.94, 0.42], "align": "center", "max": 0.07}}),
    _t("question", "सवाल ?", "बड़ा ? — curiosity वाले वीडियो",
       accent="#00E676", bg={"type": "gradient", "color": "#1A0033", "color2": "#3D0066", "angle": 45},
       person={"x": 0.70, "face_y": 0.42, "face_h": 0.42, "stroke": "#FFFFFF", "glow": "accent", "shadow": True},
       labels=[{"text": "?", "x": 0.88, "y": 0.22, "bg": "", "color": "accent", "size": 0.36, "font": "Poppins", "rotate": 12}],
       text={"box": [0.04, 0.10, 0.54, 0.90], "align": "left", "valign": "center", "max": 0.19, "font": "Mukta",
             "color": "#FFFFFF", "hl": "accent", "style": "highlight"},
       grade="pop",
       vertical={"person": {"x": 0.5, "face_y": 0.66, "face_h": 0.26},
                 "labels": [{"text": "?", "x": 0.84, "y": 0.5, "size": 0.16}],
                 "text": {"box": [0.06, 0.06, 0.94, 0.42], "align": "center", "max": 0.075}}),
    _t("shock", "Shock / reaction", "बीच में चेहरा, दोनों तरफ़ text, glow",
       accent="#FF6A00", bg={"type": "blur", "blur": 30, "dim": 0.35},
       person={"x": 0.5, "face_y": 0.40, "face_h": 0.40, "stroke": "#FFFFFF", "glow": "accent", "shadow": True},
       text={"box": [0.03, 0.66, 0.97, 0.97], "align": "center", "valign": "bottom", "max": 0.16, "font": "Mukta",
             "color": "#FFFFFF", "hl": "accent", "style": "outline"},
       scrim={"side": "bottom", "color": "#000000", "alpha": 0.6, "extent": 0.45}, grade="pop", vignette=0.4,
       vertical={"person": {"face_y": 0.45, "face_h": 0.28}, "text": {"box": [0.05, 0.70, 0.95, 0.95], "max": 0.07}}),
    # ---- pro layouts (story / motivational niche) — same layer model, every piece movable
    _t("mega_word", "बड़ा शब्द पीछे", "एक विशाल शब्द चेहरे के पीछे — story / reaction style",
       accent="#FFD400", bg={"type": "gradient", "color": "#0B0B12", "color2": "#2A1B3D", "angle": 100},
       person={"x": 0.5, "face_y": 0.6, "face_h": 0.36, "stroke": "#FFFFFF", "stroke_w": 12, "shadow": True,
               "adj": {"sat": 1.12, "contrast": 1.08, "sharp": 1.4}},
       text={"box": [0.02, -0.04, 0.98, 0.56], "align": "center", "valign": "center", "max": 0.62, "font": "Noto Sans Devanagari",
             "color": "#FFFFFF", "fill2": "#FFD400", "hl": "accent", "style": "outline", "stroke": "#000000", "stroke_w": 0.04,
             "shadow": "soft"},
       text_behind=True, overlay="rays", grade="pop", vignette=0.45, demo_text="सच",
       vertical={"person": {"x": 0.5, "face_y": 0.58, "face_h": 0.26}, "text": {"box": [0.02, 0.06, 0.98, 0.5], "max": 0.22}}),
    _t("story_cinema", "Cinematic story", "teal-orange फ़िल्मी रंग, gradient text — कहानी वाले वीडियो",
       accent="#FFB000", bg={"type": "blur", "blur": 26, "dim": 0.55},
       person={"x": 0.70, "face_y": 0.42, "face_h": 0.44, "stroke": None, "glow": "#FFB000", "glow_w": 18, "shadow": True,
               "adj": {"sat": 1.1, "contrast": 1.12, "sharp": 1.3}},
       text={"box": [0.04, 0.10, 0.52, 0.90], "align": "left", "valign": "center", "max": 0.19, "font": "Baloo 2",
             "color": "#FFFFFF", "fill2": "#FFD9A0", "hl": "accent", "style": "shadow", "shadow": "hard", "shadow_color": "#000000",
             "stroke": "#000000", "stroke_w": 0.04, "line_h": 0.9},
       scrim={"side": "left", "color": "#02121A", "alpha": 0.7, "extent": 0.65}, grade="teal", overlay="bokeh", vignette=0.5,
       demo_text="वो एक *फ़ैसला*\nजिसने सब बदला",
       vertical={"person": {"x": 0.5, "face_y": 0.64, "face_h": 0.26},
                 "text": {"box": [0.06, 0.07, 0.94, 0.42], "align": "center", "max": 0.075}, "scrim": {"side": "top", "extent": 0.55}}),
    _t("spotlight", "Spotlight", "काला background, चेहरे पर रोशनी — गंभीर / emotional",
       accent="#FF3B30", bg={"type": "solid", "color": "#050505"},
       person={"x": 0.68, "face_y": 0.42, "face_h": 0.44, "stroke": None, "glow": "#FFFFFF", "glow_w": 10, "shadow": True,
               "adj": {"contrast": 1.15, "sharp": 1.3}},
       text={"box": [0.04, 0.12, 0.50, 0.88], "align": "left", "valign": "center", "max": 0.19, "font": "Mukta",
             "color": "#FFFFFF", "hl": "accent", "style": "outline", "stroke_w": 0.06, "shadow": "glow", "glow": "#000000"},
       overlay="spotlight", grade="cinema", vignette=0.6, demo_text="अकेले *लड़ना*\nपड़ता है",
       vertical={"person": {"x": 0.5, "face_y": 0.62, "face_h": 0.26}, "text": {"box": [0.06, 0.06, 0.94, 0.40], "align": "center", "max": 0.075}}),
    _t("ribbon", "Ribbon / banner", "text लाल ribbon पर — दूर से पढ़ने में सबसे आसान",
       accent="#E50914", bg={"type": "blur", "blur": 20, "dim": 0.35},
       person={"x": 0.72, "face_y": 0.40, "face_h": 0.42, "stroke": "#FFFFFF", "stroke_w": 14, "shadow": True,
               "adj": {"sat": 1.15, "contrast": 1.08, "sharp": 1.3}},
       text={"box": [0.03, 0.20, 0.56, 0.80], "align": "center", "valign": "center", "max": 0.17, "font": "Mukta",
             "color": "#FFFFFF", "hl": "#FFD400", "style": "banner", "banner": "accent", "skew": -6, "rotate": 4},
       overlay="rays", grade="pop", vignette=0.3, demo_text="ये *गलती* मत करना",
       vertical={"person": {"x": 0.5, "face_y": 0.66, "face_h": 0.26}, "text": {"box": [0.05, 0.08, 0.95, 0.40], "max": 0.075}}),
    _t("quote", "Quote / विचार", "बड़े quote चिह्न, serif text — motivational विचार",
       accent="#F2B33D", bg={"type": "gradient", "color": "#0E0E0E", "color2": "#1F2A30", "angle": 135},
       person={"x": 0.76, "face_y": 0.40, "face_h": 0.38, "stroke": None, "glow": None, "shadow": True, "adj": {"sat": 0.9, "contrast": 1.12}},
       labels=[{"text": "“", "x": 0.09, "y": 0.2, "bg": "", "color": "accent", "size": 0.42, "font": "FreeSerif"}],
       text={"box": [0.06, 0.22, 0.56, 0.86], "align": "left", "valign": "center", "max": 0.16, "font": "FreeSerif",
             "color": "#F5F1E8", "hl": "accent", "style": "shadow", "line_h": 1.15},
       scrim={"side": "left", "color": "#000000", "alpha": 0.6, "extent": 0.6}, grade="cinema", vignette=0.5, overlay="grain",
       demo_text="जो *हार* नहीं मानता\nवही जीतता है",
       vertical={"person": {"x": 0.5, "face_y": 0.68, "face_h": 0.24}, "labels": [{"text": "“", "x": 0.14, "y": 0.08, "size": 0.16}],
                 "text": {"box": [0.08, 0.10, 0.92, 0.45], "align": "center", "max": 0.07}}),
    _t("money", "पैसा / success", "हरा-सुनहरा gradient text, किरणें — पैसा, business, success",
       accent="#2EE59D", bg={"type": "gradient", "color": "#03140C", "color2": "#0B3B24", "angle": 60},
       person={"x": 0.72, "face_y": 0.42, "face_h": 0.42, "stroke": "#FFFFFF", "stroke_w": 12, "glow": "accent", "glow_w": 22, "shadow": True,
               "adj": {"sat": 1.12, "contrast": 1.1, "sharp": 1.3}},
       text={"box": [0.04, 0.10, 0.54, 0.90], "align": "left", "valign": "center", "max": 0.2, "font": "Baloo 2",
             "color": "#FFF6C2", "fill2": "#F2B33D", "hl": "accent", "style": "double", "stroke": "#06301C", "stroke2": "#FFFFFF",
             "stroke2_w": 0.05},
       overlay="rays", grade="vivid", vignette=0.35, demo_text="₹1 लाख *महीना*",
       vertical={"person": {"x": 0.5, "face_y": 0.66, "face_h": 0.26}, "text": {"box": [0.06, 0.07, 0.94, 0.42], "align": "center", "max": 0.075}}),
    _t("fire", "Fire / जोश", "लाल-काला, long shadow — जोश, challenge, motivation",
       accent="#FF6A00", bg={"type": "gradient", "color": "#1A0000", "color2": "#5C0A00", "angle": 90},
       person={"x": 0.70, "face_y": 0.42, "face_h": 0.44, "stroke": "#FFD400", "stroke_w": 10, "glow": "accent", "glow_w": 30, "shadow": True,
               "adj": {"sat": 1.15, "contrast": 1.12, "sharp": 1.4}},
       text={"box": [0.04, 0.08, 0.54, 0.92], "align": "left", "valign": "center", "max": 0.21, "font": "Mukta",
             "color": "#FFD400", "fill2": "#FF6A00", "hl": "#FFFFFF", "style": "long", "shadow_color": "#3A0000", "stroke": "#000000"},
       overlay="haze", grade="warm", vignette=0.55, demo_text="अब *रुकना*\nनहीं है",
       vertical={"person": {"x": 0.5, "face_y": 0.66, "face_h": 0.26}, "text": {"box": [0.06, 0.07, 0.94, 0.42], "align": "center", "max": 0.075}}),
    _t("right_wrong", "सही ✓ / गलत ✕", "दो frames, ✕ और ✓ — गलत तरीका vs सही तरीका",
       accent="#1FAA59", bg={"type": "split"}, person=None,
       text={"box": [0.04, 0.03, 0.96, 0.28], "align": "center", "valign": "top", "max": 0.13, "font": "Mukta",
             "color": "#FFFFFF", "hl": "#FFD400", "style": "outline"},
       shapes=[{"type": "cross", "x": 0.12, "y": 0.80, "w": 0.12, "color": "#E50914"},
               {"type": "tick", "x": 0.88, "y": 0.80, "w": 0.12, "color": "#1FAA59"}],
       labels=[{"text": "गलत", "x": 0.25, "y": 0.9, "bg": "#E50914", "color": "#FFFFFF", "size": 0.07},
               {"text": "सही", "x": 0.75, "y": 0.9, "bg": "#1FAA59", "color": "#FFFFFF", "size": 0.07}],
       grade="pop", demo_text="ऐसे *मत* करो",
       vertical={"text": {"box": [0.05, 0.03, 0.95, 0.16], "max": 0.06},
                 "shapes": [{"type": "cross", "x": 0.15, "y": 0.4, "w": 0.18}, {"type": "tick", "x": 0.15, "y": 0.9, "w": 0.18}],
                 "labels": [{"text": "गलत", "x": 0.5, "y": 0.46, "size": 0.04}, {"text": "सही", "x": 0.5, "y": 0.95, "size": 0.04}]}),
    _t("neon_night", "Neon", "बैंगनी-नीली neon glow — tech, रात, mystery",
       accent="#00E5FF", bg={"type": "blur", "blur": 30, "dim": 0.7},
       person={"x": 0.70, "face_y": 0.42, "face_h": 0.42, "stroke": "#00E5FF", "stroke_w": 8, "glow": "#E040FB", "glow_w": 34, "shadow": True,
               "adj": {"contrast": 1.1, "sharp": 1.3}},
       text={"box": [0.04, 0.10, 0.54, 0.90], "align": "left", "valign": "center", "max": 0.19, "font": "Baloo 2",
             "color": "#FFFFFF", "hl": "#FF5BE1", "style": "neon", "glow": "#00E5FF"},
       scrim={"side": "left", "color": "#12002A", "alpha": 0.75, "extent": 0.7}, grade="cool", overlay="bokeh", vignette=0.5,
       demo_text="रात *3 बजे*\nक्या हुआ?",
       vertical={"person": {"x": 0.5, "face_y": 0.66, "face_h": 0.26}, "text": {"box": [0.06, 0.07, 0.94, 0.42], "align": "center", "max": 0.075},
                 "scrim": {"side": "top", "extent": 0.55}}),
    _t("headline", "Headline पट्टी", "ऊपर सफ़ेद पट्टी पर काला text, नीचे चेहरा — साफ़ और पढ़ने में आसान",
       accent="#FFD400", bg={"type": "blur", "blur": 18, "dim": 0.25},
       person={"x": 0.5, "face_y": 0.68, "face_h": 0.42, "stroke": "#FFFFFF", "stroke_w": 12, "shadow": True, "adj": {"sat": 1.1, "sharp": 1.3}},
       text={"box": [0.0, 0.02, 1.0, 0.42], "align": "center", "valign": "top", "max": 0.16, "font": "Mukta",
             "color": "#111111", "hl": "#E50914", "style": "box", "box_color": "#FFFFFF", "line_boxes": ["#FFFFFF", "accent"],
             "line_colors": ["#111111", "#111111"]},
       grade="pop", vignette=0.4, overlay="spotlight", demo_text="किसी ने *नहीं* बताया\nये सच",
       vertical={"person": {"face_y": 0.66, "face_h": 0.24}, "text": {"box": [0.0, 0.05, 1.0, 0.3], "max": 0.06}}),
    _t("challenge", "Challenge / दिन", "burst badge में नंबर — 30 दिन challenge, list",
       accent="#FFD400", bg={"type": "gradient", "color": "#0A1A3A", "color2": "#1E4FA0", "angle": 45},
       person={"x": 0.72, "face_y": 0.42, "face_h": 0.42, "stroke": "#FFFFFF", "stroke_w": 14, "shadow": True,
               "adj": {"sat": 1.12, "contrast": 1.08, "sharp": 1.3}},
       shapes=[{"type": "burst", "x": 0.17, "y": 0.3, "w": 0.27, "color": "accent", "rot": 8}],
       badge={"x": 0.17, "y": 0.30, "r": 0.13, "color": "#E50914", "text_color": "#FFFFFF"},
       text={"box": [0.04, 0.52, 0.56, 0.95], "align": "left", "valign": "center", "max": 0.16, "font": "Mukta",
             "color": "#FFFFFF", "hl": "accent", "style": "double", "stroke": "#000000", "stroke2": "accent", "stroke2_w": 0.04,
             "strip_number": True},
       overlay="rays", grade="pop", vignette=0.35, demo_text="30 दिन *सुबह 5 बजे*",
       vertical={"person": {"x": 0.5, "face_y": 0.68, "face_h": 0.25}, "shapes": [{"type": "burst", "x": 0.5, "y": 0.14, "w": 0.56}],
                 "badge": {"x": 0.5, "y": 0.14, "r": 0.11}, "text": {"box": [0.06, 0.26, 0.94, 0.47], "align": "center", "max": 0.07}}),
]
TEMPLATE_IDS = [t["id"] for t in TEMPLATES]


def _deep(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep(out[k], v)
        elif isinstance(v, list) and isinstance(out.get(k), list) and v and isinstance(v[0], dict) and len(v) == len(out[k]):
            out[k] = [_deep(x, y) for x, y in zip(out[k], v)]
        else:
            out[k] = copy.deepcopy(v)
    return out


def template(tid: str, size: str = "yt") -> dict:
    base = next((t for t in TEMPLATES if t["id"] == tid), TEMPLATES[0])
    t = {k: v for k, v in base.items() if k != "vertical"}
    if size in FORMATS and size not in SIZES:
        size = base_of(*FORMATS[size][:2])
    if size == "vertical":
        t = _deep(t, base.get("vertical") or {})
        if t.get("text"):
            t["text"]["max"] = t["text"].get("max", 0.07) * 1.18
    return copy.deepcopy(t)


def templates_json() -> list[dict]:
    return [{k: v for k, v in t.items()} for t in TEMPLATES]


# ---------------------------------------------------------------- colours / fonts
def _rgb(c: str | None, accent: str = "#FFD400", default=(255, 255, 255)) -> tuple[int, int, int]:
    if c == "accent":
        c = accent
    if not c or not isinstance(c, str):
        return default
    c = c.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except (ValueError, IndexError):
        return default


@functools.lru_cache(maxsize=64)
def font(family: str, px: int) -> ImageFont.FreeTypeFont:
    fname, var = FONTS.get(family) or FONTS["Mukta"]
    if not (FONTS_DIR / fname).exists() and family == "Inter":
        fname = "Poppins-Black.ttf"
    path = FONTS_DIR / fname
    if not path.exists():
        path = FONTS_DIR / "NotoSansDevanagari.ttf"
    f = ImageFont.truetype(str(path), max(8, int(px)), layout_engine=ImageFont.Layout.RAQM if RAQM else ImageFont.Layout.BASIC)
    if var:
        try:
            f.set_variation_by_name(var)
        except Exception:  # noqa: BLE001
            pass
    return f


def _lum(rgb) -> float:
    def ch(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb[:3]
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# ---------------------------------------------------------------- text parsing
_HL = re.compile(r"(\*[^*]+\*|(?<![\w])_[^_\s][^_]*_(?![\w]))")
EMOJI_RE = re.compile("([\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2190-\u21FF\u2300-\u23FF\u2700-\u27BF]"
                      "[\uFE0F\u200D\U0001F3FB-\U0001F3FF\U0001F000-\U0001FAFF\u2600-\u27BF]*)")


def parse_text(text: str, *, strip_number: bool = False, upper: bool = False) -> list[list[tuple[str, bool | int]]]:
    """'3 *बड़ी* गलतियाँ\\nजो आप करते हो' → [[('3',F),('बड़ी',T),('गलतियाँ',F)], [...]]
    *word* = highlight colour, _word_ = second highlight colour (hl = 2). Emoji become their own words."""
    lines = []
    for raw in (text or "").replace("\r", "").split("\n")[:3]:
        words: list[tuple[str, bool | int]] = []
        for part in _HL.split(raw):
            if not part:
                continue
            hl: bool | int = False
            if part.startswith("*") and part.endswith("*") and len(part) > 2:
                hl, part = True, part[1:-1]
            elif part.startswith("_") and part.endswith("_") and len(part) > 2:
                hl, part = 2, part[1:-1]
            for w in part.split():
                for piece in EMOJI_RE.split(w):
                    if piece and piece not in ("\uFE0F", "\u200D"):
                        words.append((piece.upper() if upper else piece, hl))
        if strip_number and not lines and words and re.fullmatch(r"[0-9०-९]+", words[0][0]):
            words = words[1:]
        if words:
            lines.append(words)
    return lines


def leading_number(text: str) -> str:
    m = re.match(r"\s*\*?([0-9०-९]{1,3})\b", text or "")
    return m.group(1) if m else ""


def plain(text: str) -> str:
    return re.sub(r"\s+", " ", _HL.sub(lambda m: " " + m.group(0)[1:-1] + " ", text or "").replace("*", " ")).strip()


# ---------------------------------------------------------------- frames
def grab_frame(video: Path, t: float, max_w: int = 1920) -> Image.Image:
    """One RGB frame at time t (fast input seek)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale='min({max_w},iw)':-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                       capture_output=True, timeout=60)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError("frame नहीं निकला: " + r.stderr.decode(errors="ignore")[-200:])
    from io import BytesIO
    return Image.open(BytesIO(r.stdout)).convert("RGB")


def grab_alpha(alpha_video: Path, t: float, size: tuple[int, int]) -> Image.Image | None:
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(alpha_video), "-frames:v", "1",
                        "-vf", f"scale={size[0]}:{size[1]},format=gray", "-f", "image2pipe", "-vcodec", "png", "-"],
                       capture_output=True, timeout=60)
    if r.returncode != 0 or not r.stdout:
        return None
    from io import BytesIO
    return Image.open(BytesIO(r.stdout)).convert("L")


def _cascades():
    try:
        import cv2
    except ImportError:
        return None, None, None
    if not hasattr(cv2, "CascadeClassifier"):  # OpenCV 5 dropped the Haar module
        return None, None, None
    base = Path(cv2.data.haarcascades)
    if not (base / "haarcascade_frontalface_default.xml").exists():
        return None, None, None
    face = cv2.CascadeClassifier(str(base / "haarcascade_frontalface_default.xml"))
    eye = cv2.CascadeClassifier(str(base / "haarcascade_eye.xml")) if (base / "haarcascade_eye.xml").exists() else None
    return cv2, face, eye


def detect_face(img: Image.Image) -> dict | None:
    """Biggest face → {cx, cy, w, h} in 0..1 of the image, plus eyes count."""
    cv2, det, eye = _cascades()
    if det is None:
        return None
    sw = 480
    sh = max(2, int(img.height * sw / img.width))
    g = np.asarray(img.convert("L").resize((sw, sh)))
    faces = det.detectMultiScale(g, scaleFactor=1.12, minNeighbors=5, minSize=(28, 28))
    if not len(faces):
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    eyes = 0
    if eye is not None:
        roi = g[y:y + int(h * 0.6), x:x + w]
        eyes = len(eye.detectMultiScale(roi, scaleFactor=1.1, minNeighbors=4, minSize=(8, 8)))
    return {"cx": (x + w / 2) / sw, "cy": (y + h / 2) / sh, "w": w / sw, "h": h / sh, "eyes": int(eyes)}


def _sharpness(gray: np.ndarray) -> float:
    g = gray.astype(np.float32)
    lap = -4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
    return float(lap.var())


def best_frames(video: Path, duration: float, *, samples: int = 20, top: int = 6) -> list[dict]:
    """Score ~20 evenly spaced frames; return the best `top` (spread out in time)."""
    if duration <= 0:
        return [{"t": 0.0, "score": 0, "face": False}]
    a, b = duration * 0.03, duration * 0.97
    n = max(1, min(samples, int(duration * 2) or 1))
    times = [a + (b - a) * (i + 0.5) / n for i in range(n)]
    rows = []
    for t in times:
        try:
            img = grab_frame(video, t, max_w=480)
        except Exception:  # noqa: BLE001
            continue
        arr = np.asarray(img.convert("L"))
        sharp = _sharpness(arr)
        bright = float(arr.mean()) / 255
        rgb = np.asarray(img).astype(np.float32)
        rg = rgb[..., 0] - rgb[..., 1]
        yb = 0.5 * (rgb[..., 0] + rgb[..., 1]) - rgb[..., 2]
        colorful = float(np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2)) / 100
        face = detect_face(img)
        rows.append({"t": round(t, 2), "sharp": sharp, "bright": bright, "colorful": colorful, "face": face})
    if not rows:
        return [{"t": round(duration / 2, 2), "score": 0, "face": False}]
    smax = max(r["sharp"] for r in rows) or 1.0
    for r in rows:
        s = 0.35 * (r["sharp"] / smax)
        s += 0.15 * max(0.0, 1 - abs(r["bright"] - 0.5) / 0.5)
        s += 0.10 * min(1.0, r["colorful"])
        f = r["face"]
        if f:
            s += 0.25 + min(0.10, f["h"] * 0.4)
            s += 0.08 if f["eyes"] >= 2 else 0.03 if f["eyes"] == 1 else 0
            s -= 0.05 * abs(f["cx"] - 0.5)
        r["score"] = round(s, 4)
    rows.sort(key=lambda r: -r["score"])
    gap = max(0.5, duration / (top * 3))
    out: list[dict] = []
    for r in rows:
        if all(abs(r["t"] - o["t"]) >= gap for o in out):
            out.append(r)
        if len(out) >= top:
            break
    return [{"t": r["t"], "score": r["score"], "face": bool(r["face"]), "eyes": (r["face"] or {}).get("eyes", 0),
             "sharp": round(r["sharp"] / smax, 3)} for r in out]


# ---------------------------------------------------------------- cutout (one frame)
_rvm = {"sess": None}


def rvm_alpha(img: Image.Image) -> Image.Image | None:
    """Person matte for a single image with Robust Video Matting; None when unavailable."""
    try:
        from . import matting
        if not matting.available():
            return None
        if _rvm["sess"] is None:
            import onnxruntime as ort
            p = matting.models_dir() / matting.MODEL_NAME
            if not p.exists():
                import socket
                old = socket.getdefaulttimeout()
                socket.setdefaulttimeout(20)
                try:
                    p = matting.model_path()
                finally:
                    socket.setdefaulttimeout(old)
            so = ort.SessionOptions()
            so.intra_op_num_threads = 4
            _rvm["sess"] = ort.InferenceSession(str(p), so, providers=["CPUExecutionProvider"])
        sess = _rvm["sess"]
        w, h = img.width // 2 * 2, img.height // 2 * 2
        src = np.asarray(img.resize((w, h))).astype(np.float32).transpose(2, 0, 1)[None] / 255.0
        rec = [np.zeros([1, 1, 1, 1], np.float32)] * 4
        dsr = np.array([min(1.0, 512 / max(w, h))], np.float32)
        pha = None
        for _ in range(3):  # the recurrent state settles over a few passes of the same frame
            _fgr, pha, *rec = sess.run(None, {"src": src, "r1i": rec[0], "r2i": rec[1], "r3i": rec[2], "r4i": rec[3],
                                              "downsample_ratio": dsr})
        a = (np.clip(pha[0, 0], 0, 1) * 255).astype(np.uint8)
        return Image.fromarray(a, "L").resize(img.size) if matte_ok(a) else None
    except Exception:  # noqa: BLE001 — cutout is a nicety
        return None


def matte_ok(a) -> bool:
    """Reject broken mattes (nearly empty, or the whole frame): a person covers ~5–85 % of the
    frame and the solid part spans at least a quarter of its height."""
    a = np.asarray(a)
    solid = a > 128
    frac = float(solid.mean())
    if not 0.04 <= frac <= 0.85:
        return False
    rows = np.where(solid.mean(axis=1) > 0.01)[0]
    if not len(rows) or (rows.max() - rows.min()) < a.shape[0] * 0.25:
        return False
    # the head must be solid too: a matte that only caught the shirt would cut the face out
    soft = np.where((a > 40).mean(axis=1) > 0.01)[0]
    top, bot = soft.min(), soft.max()
    head = solid[top: top + max(1, int((bot - top) * 0.35))]
    return float((head.mean(axis=1) > 0.01).mean()) >= 0.6


# ---------------------------------------------------------------- drawing helpers
def _cover(img: Image.Image, size: tuple[int, int], focus_x: float = 0.5, focus_y: float = 0.45) -> Image.Image:
    W, H = size
    s = max(W / img.width, H / img.height)
    nw, nh = max(W, round(img.width * s)), max(H, round(img.height * s))
    im = img.resize((nw, nh), Image.LANCZOS)
    x = int(min(max(0, focus_x * nw - W / 2), nw - W))
    y = int(min(max(0, focus_y * nh - H / 2), nh - H))
    return im.crop((x, y, x + W, y + H))


def _gradient(size, c1, c2, angle: float = 90) -> Image.Image:
    W, H = size
    a = math.radians(angle)
    xs = np.linspace(-0.5, 0.5, W)[None, :]
    ys = np.linspace(-0.5, 0.5, H)[:, None]
    d = xs * math.cos(a) * (W / max(W, H)) + ys * math.sin(a) * (H / max(W, H))
    d = (d - d.min()) / max(1e-6, d.max() - d.min())
    c1, c2 = np.array(c1, np.float32), np.array(c2, np.float32)
    arr = c1[None, None, :] * (1 - d[..., None]) + c2[None, None, :] * d[..., None]
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def _grade(img: Image.Image, mode: str | None) -> Image.Image:
    if mode == "pop":
        img = ImageEnhance.Color(img).enhance(1.28)
        img = ImageEnhance.Contrast(img).enhance(1.12)
        return ImageEnhance.Brightness(img).enhance(1.04)
    if mode == "dark":
        img = ImageEnhance.Color(img).enhance(0.75)
        return ImageEnhance.Contrast(img).enhance(1.15)
    if mode == "warm":
        img = ImageEnhance.Contrast(img).enhance(1.1)
        r, g, b = img.split()
        r = r.point(lambda v: min(255, int(v * 1.06)))
        b = b.point(lambda v: int(v * 0.9))
        return Image.merge("RGB", (r, g, b))
    if mode == "vivid":
        img = ImageEnhance.Color(img).enhance(1.5)
        img = ImageEnhance.Contrast(img).enhance(1.18)
        return ImageEnhance.Sharpness(img).enhance(1.4)
    if mode == "cool":
        img = ImageEnhance.Contrast(img).enhance(1.1)
        r, g, b = img.split()
        return Image.merge("RGB", (r.point(lambda v: int(v * 0.92)), g, b.point(lambda v: min(255, int(v * 1.08 + 6)))))
    if mode == "teal":  # teal shadows, warm highlights
        a = np.asarray(ImageEnhance.Contrast(img).enhance(1.12)).astype(np.float32)
        lum = a.mean(axis=2, keepdims=True) / 255
        warm = np.array([18, 6, -14], np.float32)
        teal = np.array([-16, 6, 14], np.float32)
        a = a + warm * lum + teal * (1 - lum)
        return ImageEnhance.Color(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")).enhance(1.15)
    if mode == "cinema":
        img = ImageEnhance.Color(img).enhance(0.85)
        img = ImageEnhance.Contrast(img).enhance(1.25)
        r, g, b = img.split()
        return Image.merge("RGB", (r, g, b.point(lambda v: min(255, int(v * 0.95 + 10)))))
    if mode == "mono":
        return ImageEnhance.Contrast(ImageOps.grayscale(img).convert("RGB")).enhance(1.2)
    return img


def adjust(img: Image.Image, adj: dict | None) -> Image.Image:
    """Photo adjustments {bright, contrast, sat, sharp} as multipliers around 1.0 (+ vibrance-ish sat)."""
    if not adj:
        return img
    for key, enh in (("bright", ImageEnhance.Brightness), ("contrast", ImageEnhance.Contrast), ("sat", ImageEnhance.Color),
                     ("sharp", ImageEnhance.Sharpness)):
        v = _num(adj, key, 1.0, 0.0, 3.0)
        if abs(v - 1.0) > 0.01:
            img = enh(img).enhance(v)
    return img


def _overlay(size, kind: str, accent_rgb, cx: float = 0.5, cy: float = 0.4) -> Image.Image | None:
    """Light / texture layers over the background (rays, spotlight, bokeh, grain, haze)."""
    W, H = size
    rng = np.random.default_rng(7)
    if kind == "rays":
        ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
        ang = np.arctan2(ys - cy * H, xs - cx * W)
        rays = (np.sin(ang * 14) * 0.5 + 0.5) ** 3
        dist = np.sqrt((xs - cx * W) ** 2 + (ys - cy * H) ** 2) / max(W, H)
        a = rays * np.clip(1.15 - dist * 1.3, 0, 1) * 0.34
        lay = Image.new("RGBA", size, (*accent_rgb, 0))
        lay.putalpha(Image.fromarray((a * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(3)))
        return lay
    if kind == "spotlight":
        ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.sqrt(((xs - cx * W) / (W * 0.42)) ** 2 + ((ys - cy * H) / (H * 0.55)) ** 2)
        light = np.clip(1 - d, 0, 1) ** 1.8 * 0.5
        dark = np.clip((d - 0.5) / 0.8, 0, 1) * 0.65
        lay = Image.new("RGBA", size, (0, 0, 0, 0))
        dk = Image.new("RGBA", size, (0, 0, 0, 0))
        dk.putalpha(Image.fromarray((dark * 255).astype(np.uint8), "L"))
        lt = Image.new("RGBA", size, (255, 244, 222, 0))
        lt.putalpha(Image.fromarray((light * 255).astype(np.uint8), "L"))
        lay.alpha_composite(dk)
        lay.alpha_composite(lt)
        return lay
    if kind == "bokeh":
        lay = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        unit = max(W, H) / 1280
        for _ in range(26):
            r = float(rng.uniform(12, 48)) * unit
            x, y = float(rng.uniform(0, W)), float(rng.uniform(0, H))
            tint = tuple(int(c) for c in (np.array(accent_rgb) * 0.5 + np.array([255, 255, 255]) * 0.5))
            d.ellipse((x - r, y - r, x + r, y + r), fill=(*tint, int(rng.uniform(40, 110))))
        return lay.filter(ImageFilter.GaussianBlur(4 * unit))
    if kind == "grain":
        n = rng.normal(0, 1, (H, W)).astype(np.float32)
        a = np.clip(np.abs(n) * 22, 0, 60).astype(np.uint8)
        col = np.where(n[..., None] > 0, 255, 0).astype(np.uint8)
        arr = np.concatenate([np.repeat(col, 3, axis=2), a[..., None]], axis=2)
        return Image.fromarray(arr, "RGBA")
    if kind == "haze":
        small = Image.fromarray((rng.random((max(4, H // 60), max(4, W // 60))) * 255).astype(np.uint8), "L")
        cloud = small.resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(max(W, H) / 60))
        ramp = np.linspace(0, 1, H)[:, None] ** 1.5
        a = (np.asarray(cloud).astype(np.float32) / 255) * ramp * 0.55 * 255
        lay = Image.new("RGBA", size, (230, 230, 240, 0))
        lay.putalpha(Image.fromarray(a.astype(np.uint8), "L"))
        return lay
    return None


def _scrim(size, side: str, color, alpha: float, extent: float) -> Image.Image:
    W, H = size
    if side in ("left", "right"):
        n = W
        ramp = np.clip(1 - np.linspace(0, 1, n) / max(0.05, extent), 0, 1) ** 1.3
        if side == "right":
            ramp = ramp[::-1]
        mask = np.tile(ramp[None, :], (H, 1))
    else:
        n = H
        ramp = np.clip(1 - np.linspace(0, 1, n) / max(0.05, extent), 0, 1) ** 1.3
        if side == "bottom":
            ramp = ramp[::-1]
        mask = np.tile(ramp[:, None], (1, W))
    a = Image.fromarray((mask * alpha * 255).astype(np.uint8), "L")
    layer = Image.new("RGBA", size, (*color, 0))
    layer.putalpha(a)
    return layer


def _vignette(size, strength: float) -> Image.Image:
    W, H = size
    xs = np.linspace(-1, 1, W)[None, :]
    ys = np.linspace(-1, 1, H)[:, None]
    d = np.sqrt(xs ** 2 + ys ** 2) / math.sqrt(2)
    m = np.clip((d - 0.45) / 0.55, 0, 1) ** 1.5 * strength
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.putalpha(Image.fromarray((m * 255).astype(np.uint8), "L"))
    return layer


def _expand(alpha: Image.Image, px: int) -> Image.Image:
    """Grow a matte outward by ~px (blur + threshold — fast at any size)."""
    if px <= 0:
        return alpha
    b = alpha.filter(ImageFilter.GaussianBlur(px / 2))
    return b.point(lambda v: 255 if v > 10 else v * 25)


def _arrow(color, length: int, rot: float, outline=(255, 255, 255)) -> Image.Image:
    L = max(20, length)
    th = L * 0.16
    head = L * 0.36
    pad = int(L * 0.15)
    im = Image.new("RGBA", (L + pad * 2, int(head * 1.4) + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cy = im.height / 2
    x0, x1 = pad, pad + L
    pts = [(x0, cy - th / 2), (x1 - head, cy - th / 2), (x1 - head, cy - head * 0.62), (x1, cy),
           (x1 - head, cy + head * 0.62), (x1 - head, cy + th / 2), (x0, cy + th / 2)]
    d.polygon(pts, fill=(*color, 255), outline=(*outline, 255), width=max(3, int(L * 0.025)))
    return im.rotate(-rot, expand=True, resample=Image.BICUBIC)


def _ring(color, w: int, outline=(255, 255, 255)) -> Image.Image:
    h = int(w * 0.72)
    im = Image.new("RGBA", (w + 12, h + 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    lw = max(6, int(w * 0.055))
    d.ellipse((6, 6, w + 6, h + 6), outline=(*outline, 230), width=lw + 6)
    d.ellipse((9, 9, w + 3, h + 3), outline=(*color, 255), width=lw)
    return im.rotate(-8, expand=True, resample=Image.BICUBIC)


def _underline(color, w: int) -> Image.Image:
    im = Image.new("RGBA", (w, max(12, w // 9)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.line([(4, im.height * 0.7), (w * 0.5, im.height * 0.35), (w - 4, im.height * 0.55)], fill=(*color, 255),
           width=max(6, w // 22), joint="curve")
    return im


def _curve_arrow(color, w: int, outline=(255, 255, 255)) -> Image.Image:
    """Hand-drawn style curved arrow, pointing right/down."""
    h = int(w * 0.6)
    im = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts = []
    for i in range(41):
        t = i / 40
        x = 10 + t * w * 0.82
        y = 10 + h * 0.15 + (1 - (2 * t - 1) ** 2) * -h * 0.05 + t * t * h * 0.62
        pts.append((x, y))
    lw = max(6, w // 16)
    d.line(pts, fill=(*outline, 255), width=lw + max(4, lw // 2), joint="curve")
    ex, ey = pts[-1]
    px_, py_ = pts[-4]
    ang = math.atan2(ey - py_, ex - px_)
    hl = w * 0.2
    head = [(ex + math.cos(ang) * hl * 0.45, ey + math.sin(ang) * hl * 0.45),
            (ex + math.cos(ang + 2.4) * hl, ey + math.sin(ang + 2.4) * hl),
            (ex + math.cos(ang - 2.4) * hl, ey + math.sin(ang - 2.4) * hl)]
    d.polygon(head, fill=(*color, 255), outline=(*outline, 255), width=max(3, lw // 3))
    d.line(pts[:-2], fill=(*color, 255), width=lw, joint="curve")
    return im


def _rect(color, w: int, fill: bool = False, outline=(255, 255, 255)) -> Image.Image:
    h = int(w * 0.62)
    lw = max(6, int(w * 0.04))
    im = Image.new("RGBA", (w + 8, h + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if fill:
        d.rounded_rectangle((4, 4, w + 4, h + 4), radius=int(w * 0.06), fill=(*color, 255), outline=(*outline, 255), width=max(3, lw // 2))
    else:
        d.rounded_rectangle((4, 4, w + 4, h + 4), radius=int(w * 0.06), outline=(*outline, 230), width=lw + 6)
        d.rounded_rectangle((7, 7, w + 1, h + 1), radius=int(w * 0.06), outline=(*color, 255), width=lw)
    return im


def _burst(color, w: int, outline=(255, 255, 255), points: int = 14) -> Image.Image:
    im = Image.new("RGBA", (w + 12, w + 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = (w + 12) / 2
    pts = []
    for i in range(points * 2):
        r = w / 2 if i % 2 == 0 else w * 0.36
        a = math.pi * i / points - math.pi / 2
        pts.append((c + math.cos(a) * r, c + math.sin(a) * r))
    d.polygon(pts, fill=(*color, 255), outline=(*outline, 255), width=max(3, w // 40))
    return im


def _mark(kind: str, color, w: int, outline=(255, 255, 255)) -> Image.Image:
    im = Image.new("RGBA", (w + 16, w + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    lw = max(8, int(w * 0.16))
    if kind == "cross":
        segs = [[(8 + w * 0.12, 8 + w * 0.12), (8 + w * 0.88, 8 + w * 0.88)], [(8 + w * 0.88, 8 + w * 0.12), (8 + w * 0.12, 8 + w * 0.88)]]
    else:
        segs = [[(8 + w * 0.08, 8 + w * 0.55), (8 + w * 0.38, 8 + w * 0.85), (8 + w * 0.92, 8 + w * 0.18)]]
    for sg in segs:
        d.line(sg, fill=(*outline, 255), width=lw + 8, joint="curve")
    for sg in segs:
        d.line(sg, fill=(*color, 255), width=lw, joint="curve")
    return im


def _simple_shape(kind: str, color, w: int, *, stroke=None, stroke_w: float | None, radius: float | None,
                  aspect: float | None, shadow: bool) -> Image.Image:
    """Template-studio shapes: filled rectangle / circle / line / pill with optional stroke, radius, shadow."""
    aspect = aspect if aspect else (1.0 if kind == "disc" else 0.62 if kind == "rrect" else 0.3 if kind == "pill" else 0.04)
    h = max(2, int(w * aspect))
    sw = int((stroke_w if stroke_w is not None else (0.0 if stroke is None else 0.02)) * w)
    pad = sw + (max(6, w // 30) if shadow else 0) + 4
    im = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    box = (pad, pad, pad + w, pad + h)
    r = int((radius if radius is not None else (0.06 if kind == "rrect" else 0.5)) * min(w, h))
    if shadow:
        off = max(4, w // 40)
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        sbox = (box[0] + off, box[1] + off, box[2] + off, box[3] + off)
        if kind == "disc":
            sd.ellipse(sbox, fill=(0, 0, 0, 140))
        else:
            sd.rounded_rectangle(sbox, radius=r, fill=(0, 0, 0, 140))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(max(2, w // 60))))
        d = ImageDraw.Draw(im)
    kw = {"fill": (*color, 255)}
    if stroke is not None and sw > 0:
        kw.update(outline=(*stroke, 255), width=sw)
    if kind == "disc":
        d.ellipse(box, **kw)
    elif kind == "line":
        d.rounded_rectangle(box, radius=h // 2, **kw)
    else:
        d.rounded_rectangle(box, radius=r, **kw)
    return im


def qr_image(data: str, w: int, fg, bg) -> Image.Image | None:
    try:
        import qrcode  # optional dependency
    except ImportError:
        return None
    q = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(data)
    q.make(fit=True)
    im = q.make_image(fill_color=_hex(fg), back_color=_hex(bg)).convert("RGBA")
    return im.resize((w, w), Image.NEAREST)


def shape_image(kind: str, color, w: int, fill: bool = False, *, stroke=None, stroke_w: float | None = None,
                radius: float | None = None, aspect: float | None = None, shadow: bool = False) -> Image.Image:
    if kind in ("rrect", "disc", "line", "pill"):
        return _simple_shape(kind, color, w, stroke=stroke, stroke_w=stroke_w, radius=radius, aspect=aspect, shadow=shadow)
    if kind == "arrow":
        return _arrow(color, w, 0)
    if kind == "curve":
        return _curve_arrow(color, w)
    if kind == "circle":
        return _ring(color, w)
    if kind == "rect":
        return _rect(color, w, fill)
    if kind == "burst":
        return _burst(color, w)
    if kind in ("cross", "tick"):
        return _mark(kind, color, w)
    return _underline(color, w)


def _paste_center(base: Image.Image, layer: Image.Image, cx: float, cy: float) -> None:
    full = Image.new("RGBA", base.size, (0, 0, 0, 0))
    full.paste(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))
    base.alpha_composite(full)


def _sticker(path: Path, w: int, rot: float = 0) -> Image.Image | None:
    try:
        im = Image.open(path).convert("RGBA")
    except Exception:  # noqa: BLE001
        return None
    s = w / max(1, im.width)
    im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    return im.rotate(-rot, expand=True, resample=Image.BICUBIC) if rot else im


def _label(text: str, *, px: int, fam: str, color, bg, rotate: float = 0, stroke=None, accent: str = "#FFD400",
           stroke_w: float | None = None) -> Image.Image:
    """stroke_w = outline as a fraction of the font size (None = the default thin outline, 0 = none)."""
    f = _wfont(fam, px, text)
    l, t, r, b = f.getbbox(text, anchor="ls")
    padx, pady = (int(px * 0.35), int(px * 0.18)) if bg else (int(px * 0.08), int(px * 0.08))
    stroke_c = _rgb(stroke, accent, (0, 0, 0)) if stroke else (0, 0, 0)
    stroke = 0 if bg else (max(0, int(round(stroke_w * px))) if stroke_w is not None else max(2, px // 16))
    im = Image.new("RGBA", (r - l + padx * 2 + stroke * 2, b - t + pady * 2 + stroke * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if bg:
        d.rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=int(px * 0.18), fill=(*bg, 255))
    d.text((padx + stroke - l, pady + stroke - t), text, font=f, fill=(*color, 255), anchor="ls",
           stroke_width=stroke, stroke_fill=(*stroke_c, 255))
    return im.rotate(-rotate, expand=True, resample=Image.BICUBIC) if rotate else im


# ---------------------------------------------------------------- text block
# Style presets = starting values; every key can be overridden per template / by the user:
#   stroke_w / stroke2_w (fraction of the font size), stroke / stroke2 (colours),
#   shadow: none | soft | hard | long | glow | block,  shadow_color, glow (colour),
#   fill2 (gradient fill, top → bottom of each line), spacing (letter spacing, em),
#   line_h (line gap multiplier), skew (degrees, italic slant), hl_box (box behind *highlight* words),
#   banner (colour of one ribbon behind the whole block), box_color / line_boxes (style "box").
STYLE_DEF = {
    "outline": {"stroke_w": 0.085, "shadow": "soft"},
    "shadow": {"stroke_w": 0.0, "shadow": "soft"},
    "box": {"stroke_w": 0.0, "shadow": "none"},
    "highlight": {"stroke_w": 0.03, "shadow": "soft", "hl_box": True},
    "block": {"stroke_w": 0.085, "shadow": "block"},
    "double": {"stroke_w": 0.06, "stroke2_w": 0.07, "stroke2": "accent", "shadow": "hard"},
    "neon": {"stroke_w": 0.0, "shadow": "glow"},
    "banner": {"stroke_w": 0.0, "shadow": "none", "banner": "accent"},
    "long": {"stroke_w": 0.05, "shadow": "long"},
}
TEXT_KEYS = ("stroke_w", "stroke2_w", "stroke", "stroke2", "shadow", "shadow_color", "glow", "fill2", "spacing", "line_h",
             "skew", "hl_box", "banner", "hl2")
SHADOWS = {"none": "कोई नहीं", "soft": "soft", "hard": "hard (कड़ी)", "long": "long shadow", "glow": "glow / neon", "block": "3D block"}
LATIN_ONLY = {"Inter", "Lora"}  # no Devanagari glyphs → Hindi words fall back to Mukta
_DEVA = re.compile("[\u0900-\u097F]")
EMOJI_FONTS = [FONTS_DIR / "NotoColorEmoji.ttf", Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
               Path("/usr/share/fonts/noto/NotoColorEmoji.ttf"), Path("/usr/local/share/fonts/NotoColorEmoji.ttf")]


@functools.lru_cache(maxsize=128)
def _emoji(seq: str, px: int) -> Image.Image | None:
    """A colour emoji at ~px tall (Noto Color Emoji is a bitmap font: drawn at 109 px, then scaled)."""
    path = next((p for p in EMOJI_FONTS if p.exists()), None)
    if path is None:
        return None
    try:
        f = ImageFont.truetype(str(path), 109, layout_engine=ImageFont.Layout.RAQM if RAQM else ImageFont.Layout.BASIC)
        im = Image.new("RGBA", (360, 180), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((180, 90), seq, font=f, embedded_color=True, anchor="mm")
        bb = im.getchannel("A").getbbox()
        if not bb:
            return None
        im = im.crop(bb)
        s = px / max(1, im.height)
        return im.resize((max(1, int(im.width * s)), max(1, int(px))), Image.LANCZOS)
    except Exception:  # noqa: BLE001
        return None


def _is_emoji(w: str) -> bool:
    return bool(EMOJI_RE.fullmatch(w))


def _clusters(w: str) -> list[str]:
    """Grapheme-ish clusters: a base letter + its matras / nukta / virama-joined consonants (so क्ष stays whole)."""
    import unicodedata
    out: list[str] = []
    for ch in w:
        join = out and (unicodedata.category(ch).startswith("M") or ch in "\u200c\u200d" or out[-1].endswith("\u094d"))
        if join:
            out[-1] += ch
        else:
            out.append(ch)
    return out


def _wfont(fam: str, px: int, w: str) -> ImageFont.FreeTypeFont:
    return font("Mukta", px) if fam in LATIN_ONLY and _DEVA.search(w) else font(fam, px)


def _wlen(fam: str, px: int, w: str, spacing: float) -> float:
    if _is_emoji(w):
        e = _emoji(w, px)
        return e.width if e is not None else 0
    f = _wfont(fam, px, w)
    if not spacing:
        return f.getlength(w)
    cl = _clusters(w)
    return sum(f.getlength(c) for c in cl) + spacing * px * (len(cl) - 1)


def _wbox(fam: str, px: int, w: str) -> tuple[float, float]:
    if _is_emoji(w):
        return -px * 0.82, px * 0.12
    b = _wfont(fam, px, w).getbbox(w, anchor="ls")
    return b[1], b[3]


def _wdraw(d: ImageDraw.ImageDraw, x: float, y: float, w: str, fam: str, px: int, spacing: float, **kw) -> None:
    f = _wfont(fam, px, w)
    if not spacing:
        d.text((x, y), w, font=f, anchor="ls", **kw)
        return
    cl = _clusters(w)
    passes = [kw]
    if kw.get("stroke_width"):  # all strokes first, then all fills — so a neighbour's stroke never cuts a letter
        passes = [{**kw, "fill": kw.get("stroke_fill", kw.get("fill"))}, {k: v for k, v in kw.items() if k not in ("stroke_width", "stroke_fill")}]
    for pkw in passes:
        xx = x
        for c in cl:
            d.text((xx, y), c, font=f, anchor="ls", **pkw)
            xx += f.getlength(c) + spacing * px


def _measure(lines, fam: str, px: int, spacing: float):
    space = font(fam, px).getlength(" ") * 1.05
    out = []
    for words in lines:
        ws = [_wlen(fam, px, w, spacing) for w, _ in words]
        bb = [_wbox(fam, px, w) for w, _ in words]
        out.append({"w": sum(ws) + space * (len(words) - 1), "ws": ws, "top": min(b[0] for b in bb), "bot": max(b[1] for b in bb),
                    "space": space})
    return out


def _text_opts(spec: dict) -> dict:
    style = spec.get("style", "outline")
    o = {"stroke_w": 0.0, "stroke2_w": 0.0, "shadow": "none", **STYLE_DEF.get(style, STYLE_DEF["outline"])}
    for k in TEXT_KEYS:
        if spec.get(k) not in (None, ""):
            o[k] = spec[k]
    for k, lo, hi in (("stroke_w", 0, 0.3), ("stroke2_w", 0, 0.3), ("spacing", -0.1, 0.5), ("line_h", 0.5, 2.5), ("skew", -25, 25)):
        o[k] = _num(o, k, 0.0 if k != "line_h" else 1.0, lo, hi)
    return o


def _fit(lines, fam: str, box_w: int, box_h: int, max_px: int, style: str, o: dict | None = None) -> tuple[int, list[dict]]:
    o = o or _text_opts({"style": style})
    px = max_px
    while px > 14:
        m = _measure(lines, fam, px, o["spacing"])
        boxy = style == "box" or bool(o.get("banner"))
        pad = px * (0.5 if boxy else 0.04 + o["stroke_w"] + o["stroke2_w"] + (0.06 if o["shadow"] in ("long", "block", "glow") else 0))
        gap = px * (0.18 if style == "box" else 0.06) * o["line_h"] + px * (o["line_h"] - 1) * 0.5
        tot_h = sum(x["bot"] - x["top"] for x in m) + gap * (len(m) - 1) + (pad * 0.6 * len(m) if style == "box" else 0)
        if max(x["w"] for x in m) + pad * 2 <= box_w and tot_h + pad <= box_h:
            return px, m
        px = int(px * 0.94)
    return px, _measure(lines, fam, px, o["spacing"])


def _grad_fill(mask: Image.Image, bands: list[tuple[float, float]], c1, c2) -> Image.Image:
    """Vertical gradient c1 → c2 inside each line band, shown through `mask`."""
    W, H = mask.size
    t = np.zeros(H, np.float32)
    for top, bot in bands:
        a, b = max(0, int(top)), min(H, int(bot) + 1)
        if b > a:
            t[a:b] = np.linspace(0, 1, b - a)
    c1, c2 = np.array(c1, np.float32), np.array(c2, np.float32)
    rows = (c1[None, :] * (1 - t[:, None]) + c2[None, :] * t[:, None]).astype(np.uint8)
    img = Image.fromarray(np.repeat(rows[:, None, :], W, axis=1), "RGB").convert("RGBA")
    img.putalpha(mask)
    return img


def _skew(im: Image.Image, deg: float, cy: float) -> Image.Image:
    if not deg:
        return im
    k = math.tan(math.radians(deg))
    return im.transform(im.size, Image.AFFINE, (1, k, -k * cy, 0, 1, 0), resample=Image.BICUBIC)


def draw_text(canvas: Image.Image, text_spec: dict, lines, accent: str) -> dict:
    """Draw the text block onto `canvas` (RGBA). Returns size/box info for the linter."""
    W, H = canvas.size
    x0, y0, x1, y1 = text_spec["box"]
    bx, by, bw, bh = int(x0 * W), int(y0 * H), int((x1 - x0) * W), int((y1 - y0) * H)
    style = text_spec.get("style", "outline")
    fam = text_spec.get("font", "Mukta")
    if fam not in FONTS:
        fam = "Mukta"
    o = _text_opts(text_spec)
    spacing = o["spacing"]
    max_px = int(text_spec.get("max", 0.18) * H * float(text_spec.get("scale", 1.0)))
    # one long line → also try balanced 2 / 3 line breaks and keep whichever gives the biggest text
    cands = [lines]
    if len(lines) == 1 and len(lines[0]) >= 3:
        ws = lines[0]
        for k in (2, 3):
            if len(ws) >= k + (1 if k == 3 else 0):
                per = math.ceil(len(ws) / k)
                cands.append([ws[i:i + per] for i in range(0, len(ws), per)])
    best = None
    for cand in cands:
        px_c, m_c = _fit(cand, fam, bw, bh, max_px, style, o)
        if best is None or px_c > best[0] * 1.08:
            best = (px_c, m_c, cand)
    px, m, lines = best
    sp = m[0]["space"] if m else 0
    fill = _rgb(text_spec.get("color"), accent)
    hl = _rgb(text_spec.get("hl"), accent, (255, 212, 0))
    hl2 = _rgb(o.get("hl2") or "#FFFFFF", accent)
    stroke_c = _rgb(o.get("stroke") or "#000000", accent, (0, 0, 0))
    stroke2_c = _rgb(o.get("stroke2") or "#FFFFFF", accent)
    shadow_c = _rgb(o.get("shadow_color") or ("#000000" if o["shadow"] != "glow" else o.get("glow") or text_spec.get("color")), accent, (0, 0, 0))
    fill2 = _rgb(o["fill2"], accent) if o.get("fill2") else None
    box_c = _rgb(text_spec.get("box_color") or "#000000", accent, (0, 0, 0))
    line_boxes = text_spec.get("line_boxes") or []
    line_colors = text_spec.get("line_colors") or []
    gap = px * (0.18 if style == "box" else 0.06) * o["line_h"] + px * (o["line_h"] - 1) * 0.5
    bpad_y = px * 0.14 if style == "box" else 0
    heights = [x["bot"] - x["top"] + bpad_y * 2 for x in m]
    total = sum(heights) + gap * (len(m) - 1)
    va = text_spec.get("valign", "center")
    cy = by + (0 if va == "top" else (bh - total) if va == "bottom" else (bh - total) / 2)
    al = text_spec.get("align", "left")
    padx = int((text_spec.get("pad_x") or 0) * W) if style == "box" else 0
    sw = int(round(px * o["stroke_w"])) if o["stroke_w"] else 0
    sw2 = sw + int(round(px * o["stroke2_w"])) if o["stroke2_w"] else 0
    back = Image.new("RGBA", canvas.size, (0, 0, 0, 0))      # banner, boxes, highlight boxes
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))    # shadow / glow / 3D (below the letters)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))     # outer stroke, stroke, fill
    db_, sd, d = ImageDraw.Draw(back), ImageDraw.Draw(shadow), ImageDraw.Draw(layer)
    fill_mask = Image.new("L", canvas.size, 0) if fill2 else None
    fm = ImageDraw.Draw(fill_mask) if fill_mask is not None else None
    regions, bands, placed = [], [], []
    # pass 1: positions + backgrounds
    for i, (words, mm) in enumerate(zip(lines, m)):
        lw = mm["w"]
        bpad_x = px * 0.22 if style == "box" else 0
        if al == "center":
            lx = bx + (bw - lw) / 2
        elif al == "right":
            lx = bx + bw - lw - bpad_x
        else:
            lx = bx + bpad_x + padx
        base_y = cy + bpad_y - mm["top"]
        bands.append((base_y + mm["top"], base_y + mm["bot"]))
        lfill = _rgb(line_colors[i], accent) if i < len(line_colors) and line_colors[i] else fill
        if style == "box":
            lb = _rgb(line_boxes[i], accent) if i < len(line_boxes) and line_boxes[i] else box_c
            rx0 = (bx if (padx and al == "left") else lx - bpad_x)
            db_.rectangle((rx0, cy, lx + lw + bpad_x, cy + heights[i]), fill=(*lb, 255))
        x = lx
        for (w, is_hl), ww in zip(words, mm["ws"]):
            col = lfill
            if is_hl:
                hc = hl if is_hl is True else hl2
                if style == "box":
                    db_.rectangle((x - px * 0.08, cy + px * 0.03, x + ww + px * 0.08, cy + heights[i] - px * 0.03), fill=(*hc, 255))
                    col = (17, 17, 17) if _lum(hc) > 0.35 else (255, 255, 255)
                elif o.get("hl_box"):
                    db_.rounded_rectangle((x - px * 0.12, base_y + mm["top"] - px * 0.08, x + ww + px * 0.12, base_y + mm["bot"] + px * 0.08),
                                          radius=int(px * 0.14), fill=(*hc, 255))
                    col = (17, 17, 17) if _lum(hc) > 0.35 else (255, 255, 255)
                else:
                    col = hc
            placed.append((x, base_y, w, col, bool(is_hl), ww))
            regions.append((int(x), int(base_y + mm["top"]), int(x + ww), int(base_y + mm["bot"]), col))
            x += ww + sp
        cy += heights[i] + gap
    if o.get("banner") and placed:
        bc = _rgb(o["banner"], accent)
        xs0 = min(r[0] for r in regions) - px * 0.35
        xs1 = max(r[2] for r in regions) + px * 0.35
        ys0 = min(b[0] for b in bands) - px * 0.22
        ys1 = max(b[1] for b in bands) + px * 0.22
        sl = px * 0.25
        db_.polygon([(xs0 + sl, ys0), (xs1 + sl * 0.3, ys0), (xs1 - sl, ys1), (xs0 - sl * 0.3, ys1)], fill=(*bc, 255))
    # pass 2: shadow / glow / 3D
    kind = o["shadow"]
    for x, base_y, w, col, is_hl, ww in placed:
        if _is_emoji(w):
            continue
        boxed = is_hl and (style == "box" or o.get("hl_box"))
        if kind == "soft":
            off = max(2, int(px * 0.05))
            _wdraw(sd, x + off, base_y + off, w, fam, px, spacing, fill=(*shadow_c, 200 if style != "shadow" else 230),
                   stroke_width=max(sw, sw2), stroke_fill=(*shadow_c, 200))
        elif kind == "hard":
            off = max(3, int(px * 0.07))
            _wdraw(sd, x + off, base_y + off, w, fam, px, spacing, fill=(*shadow_c, 255), stroke_width=max(sw, sw2), stroke_fill=(*shadow_c, 255))
        elif kind == "long":
            n = max(6, int(px * 0.22))
            for k in range(n, 0, -1):
                _wdraw(sd, x + k, base_y + k, w, fam, px, spacing, fill=(*shadow_c, 255), stroke_width=max(sw, sw2), stroke_fill=(*shadow_c, 255))
        elif kind == "glow":
            gc = _rgb(o.get("glow"), accent) if (o.get("glow") and not is_hl) else (col if not boxed else shadow_c)
            _wdraw(sd, x, base_y, w, fam, px, spacing, fill=(*gc, 255), stroke_width=max(sw, sw2) + max(2, int(px * 0.06)), stroke_fill=(*gc, 255))
        elif kind == "block":
            depth = max(3, int(px * 0.07))
            bc3 = stroke_c
            for k in range(depth, 0, -1):
                _wdraw(d, x + k, base_y + k, w, fam, px, spacing, fill=(*bc3, 255), stroke_width=max(sw, sw2), stroke_fill=(*bc3, 255))
            off = max(2, int(px * 0.05))
            _wdraw(sd, x + off, base_y + off, w, fam, px, spacing, fill=(0, 0, 0, 200), stroke_width=sw, stroke_fill=(0, 0, 0, 200))
    # pass 3: outer stroke, then stroke + fill
    for x, base_y, w, col, is_hl, ww in placed:
        if _is_emoji(w):
            e = _emoji(w, int(px * 0.92))
            if e is not None:
                layer.alpha_composite(e, (int(x), int(base_y - e.height * 0.86)))
            continue
        boxed = is_hl and (style == "box" or o.get("hl_box"))
        if sw2 and not boxed:
            _wdraw(d, x, base_y, w, fam, px, spacing, fill=(*stroke2_c, 255), stroke_width=sw2, stroke_fill=(*stroke2_c, 255))
    for x, base_y, w, col, is_hl, ww in placed:
        if _is_emoji(w):
            continue
        boxed = is_hl and (style == "box" or o.get("hl_box"))
        st = 0 if boxed and style != "box" else sw
        if style == "box":
            st = 0
        if fm is not None and not is_hl:
            if st:
                _wdraw(d, x, base_y, w, fam, px, spacing, fill=(*stroke_c, 255), stroke_width=st, stroke_fill=(*stroke_c, 255))
            _wdraw(fm, x, base_y, w, fam, px, spacing, fill=255)
        else:
            _wdraw(d, x, base_y, w, fam, px, spacing, fill=(*col, 255), stroke_width=st, stroke_fill=(*stroke_c, 255))
    if fill_mask is not None:
        layer.alpha_composite(_grad_fill(fill_mask, bands, fill, fill2))
    if kind in ("soft", "glow"):
        blur = px * (0.09 if style == "shadow" else 0.03) if kind == "soft" else px * 0.14
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(2, blur)))
    rot = float(text_spec.get("rotate") or 0)
    pcx, pcy = bx + bw / 2, by + bh / 2
    for im in (back, shadow, layer):
        if kind == "glow" and im is shadow:
            pass
        im2 = _skew(im, o["skew"], pcy)
        if rot:
            im2 = im2.rotate(rot, center=(pcx, pcy), resample=Image.BICUBIC)
        canvas.alpha_composite(im2)
        if kind == "glow" and im is shadow:
            canvas.alpha_composite(im2)
    return {"px": px, "box": [bx, by, bw, bh], "regions": regions, "style": style, "stroke": sw, "fill": fill}


# ---------------------------------------------------------------- render
def resolve(settings: dict) -> dict:
    """Template + user settings → one flat spec."""
    size = settings.get("size") if settings.get("size") in FORMATS else "yt"
    base = base_of(settings)
    t = template(settings.get("template") or "face_right", base)
    accent = settings.get("accent") or t.get("accent") or "#FFD400"
    tx = t.setdefault("text", {})
    for k_in, k_t in (("font", "font"), ("color", "color"), ("hl", "hl"), ("style", "style"), ("stroke", "stroke")):
        if settings.get(k_in):
            tx[k_t] = settings[k_in]
    if settings.get("text_scale"):
        tx["scale"] = max(0.4, min(1.6, float(settings["text_scale"])))
    if settings.get("box_color"):
        tx["box_color"] = settings["box_color"]
    bg = settings.get("bg") or {}
    if bg.get("type"):
        t["bg"] = {**({} if bg["type"] != (t.get("bg") or {}).get("type") else t.get("bg") or {}), **bg}
        t["bg"].setdefault("blur", 22)
        t["bg"].setdefault("dim", 0.4 if bg["type"] == "blur" else 0)
    p = t.get("person")
    if p is not None:
        if "person_stroke" in settings:
            p["stroke"] = settings["person_stroke"] or None
        if "person_glow" in settings:
            p["glow"] = settings["person_glow"] or None
        if settings.get("person_scale"):
            p["face_h"] = p["face_h"] * max(0.5, min(1.8, float(settings["person_scale"])))
    for k in ("stroke_w", "glow_w"):
        if p is not None and settings.get("person_" + k) not in (None, ""):
            p[k] = max(0.0, min(80.0, float(settings["person_" + k])))
    if p is not None and "person_shadow" in settings:
        p["shadow"] = bool(settings["person_shadow"])
    for k in TEXT_KEYS + ("align",):
        if settings.get(k) not in (None, ""):
            tx[k] = settings[k]
    if settings.get("overlay") is not None:
        t["overlay"] = settings["overlay"] or None
    if settings.get("vignette") not in (None, ""):
        t["vignette"] = max(0.0, min(1.0, float(settings["vignette"])))
    if settings.get("grade") is not None and settings.get("grade") != "":
        t["grade"] = None if settings["grade"] == "none" else settings["grade"]
    if settings.get("labels") and t.get("labels"):
        for lab, txt in zip(t["labels"], settings["labels"]):
            if txt:
                lab["text"] = str(txt)[:30]
    if settings.get("no_shapes"):
        t["shapes"] = []
    if settings.get("flip") and base == "yt":
        t = _flip(t)
    if settings.get("no_person"):
        t["person"] = None
    t["accent"] = accent
    t["size"] = size
    t["base"] = base
    return t


def _flip(t: dict) -> dict:
    t = copy.deepcopy(t)
    if t.get("person"):
        t["person"]["x"] = 1 - t["person"]["x"]
    tx = t.get("text") or {}
    if tx.get("box"):
        x0, y0, x1, y1 = tx["box"]
        tx["box"] = [1 - x1, y0, 1 - x0, y1]
        tx["align"] = {"left": "right", "right": "left"}.get(tx.get("align"), tx.get("align"))
        if tx.get("rotate"):
            tx["rotate"] = -tx["rotate"]
    if t.get("scrim"):
        t["scrim"]["side"] = {"left": "right", "right": "left"}.get(t["scrim"]["side"], t["scrim"]["side"])
    for s in t.get("shapes") or []:
        s["x"] = 1 - s["x"]
        if "rot" in s:
            s["rot"] = 180 - s["rot"]
    for lab in t.get("labels") or []:
        lab["x"] = 1 - lab["x"]
    if t.get("badge"):
        t["badge"]["x"] = 1 - t["badge"]["x"]
    return t


def _person_layer(frame: Image.Image, alpha: Image.Image | None, face: dict | None, spec: dict, size, accent: str,
                  free: bool = False):
    """Scale/position the subject. Returns (rgba layer full-canvas, placement dict).
    `free`: the user placed the person by hand — no "body touches the bottom" snapping."""
    W, H = size
    fx, fy, fh = (face["cx"], face["cy"], face["h"]) if face else (None, None, None)
    if alpha is not None:
        a = np.asarray(alpha)
        ys, xs = np.where(a > 40)
        if len(xs) < 50:
            alpha = None
        else:
            # harden the matte: dark hair often comes out half-transparent and the stroke would shine through
            alpha = alpha.point(lambda v: max(0, min(255, int((v - 25) * 1.9))))
            bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
            if fx is None:  # no face found: the head is the narrow part at the top of the matte
                bh = by1 - by0
                rows = [(y, np.where(a[y] > 40)[0]) for y in range(int(by0 + bh * 0.04), int(by0 + bh * 0.25))]
                rows = [(y, r) for y, r in rows if len(r)]
                if rows:
                    head_w = float(np.median([r.max() - r.min() for _, r in rows]))
                    fx = float(np.median([(r.max() + r.min()) / 2 for _, r in rows])) / frame.width
                else:
                    head_w, fx = (bx1 - bx0) * 0.4, (bx0 + bx1) / 2 / frame.width
                fh_px = min(head_w * 1.25, bh * 0.6)
                fh = fh_px / frame.height
                fy = (by0 + fh_px * 0.55) / frame.height
    if fx is None:
        fx, fy, fh = 0.5, 0.42, 0.3
    target_fh = spec.get("face_h", 0.4) * H
    s = target_fh / max(1.0, fh * frame.height)
    if alpha is None:
        s = max(s, W / frame.width, H / frame.height)  # the photo must cover the canvas
    s = min(s, 4.0)
    nw, nh = int(frame.width * s), int(frame.height * s)
    ox = spec.get("x", 0.7) * W - fx * nw
    oy = spec.get("face_y", 0.42) * H - fy * nh
    if alpha is None:
        ox = min(0, max(W - nw, ox))
        oy = min(0, max(H - nh, oy))
    else:
        # keep the body anchored: the bottom of the matte should reach the canvas bottom when it touched the frame bottom
        a = np.asarray(alpha)
        touches = a[-max(2, a.shape[0] // 50):, :].mean() > 8
        if touches and oy + nh < H and not free:
            oy = H - nh
    img = frame.resize((nw, nh), Image.LANCZOS)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    if alpha is None:
        layer.paste(img, (int(ox), int(oy)))
        return layer, {"cutout": False, "x": ox, "y": oy, "w": nw, "h": nh, "ax": ox + fx * nw, "ay": oy + fy * nh}
    al = alpha.resize((nw, nh), Image.LANCZOS)
    full_a = Image.new("L", size, 0)
    full_a.paste(al, (int(ox), int(oy)))
    full_rgb = Image.new("RGB", size, (0, 0, 0))
    full_rgb.paste(img, (int(ox), int(oy)))
    subj = full_rgb.convert("RGBA")
    subj.putalpha(full_a)
    unit = max(W, H) / 1280
    if spec.get("shadow"):
        sh = Image.new("RGBA", size, (0, 0, 0, 0))
        sh.putalpha(full_a.filter(ImageFilter.GaussianBlur(14 * unit)).point(lambda v: int(v * 0.6)))
        layer.alpha_composite(sh, (int(10 * unit), int(8 * unit)))
    if spec.get("glow"):
        gw = float(spec.get("glow_w") or 26)
        g = _expand(full_a, int(gw * unit)).filter(ImageFilter.GaussianBlur(gw * 0.85 * unit))
        gl = Image.new("RGBA", size, (*_rgb(spec["glow"], accent), 0))
        gl.putalpha(g)
        layer.alpha_composite(gl)
        layer.alpha_composite(gl)
    if spec.get("stroke"):
        st = _expand(full_a, int(float(spec.get("stroke_w") or 16) * unit))
        sl = Image.new("RGBA", size, (*_rgb(spec["stroke"], accent), 0))
        sl.putalpha(st)
        layer.alpha_composite(sl)
    layer.alpha_composite(subj)
    return layer, {"cutout": True, "x": ox, "y": oy, "w": nw, "h": nh, "ax": int(ox) + fx * nw, "ay": int(oy) + fy * nh}


# ---------------------------------------------------------------- layers (direct manipulation)
# Every movable thing is drawn as its own layer: an unrotated RGBA piece, trimmed to its pixels,
# then rotated about its own centre and pasted. The studio gets the same pieces (sprites) so what
# the user drags on screen is exactly what the final render pastes.
#
# Hand placement lives in settings["layout"][size][layer_id] = {x, y, s, rot, hidden} (fractions
# of the canvas; x/y = the layer's anchor: text-box centre, face point, sticker centre …; s =
# scale vs the template; rot = degrees clockwise). settings["layout"][size]["_order"] = layer ids
# bottom → top. User stickers keep their own x / y / w / rot (+ uid) in settings["stickers"].
MAX_STICKERS = 12


def layout_of(settings: dict, size: str) -> dict:
    lay = settings.get("layout")
    lay = lay.get(size) if isinstance(lay, dict) else None
    return lay if isinstance(lay, dict) else {}


def _num(d, k: str, default=None, lo: float | None = None, hi: float | None = None):
    try:
        v = float(d.get(k))
    except (TypeError, ValueError, AttributeError):
        return default
    if not math.isfinite(v):
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _ovr(lay: dict, lid: str) -> dict:
    o = lay.get(lid)
    return o if isinstance(o, dict) else {}


def _pos(o: dict, dx: float, dy: float) -> tuple[float, float]:
    return _num(o, "x", dx, -0.5, 1.5), _num(o, "y", dy, -0.5, 1.5)


def _layer(lid: str, kind: str, name: str, im: Image.Image | None, ox: float, oy: float, *, rot: float = 0.0,
           anchor: tuple[float, float] | None = None, s: float = 1.0, locked: bool = False, trim: bool = True, **extra) -> dict | None:
    """`im` = unrotated piece whose top-left sits at (ox, oy) on the canvas."""
    if im is None:
        return None
    im = im.convert("RGBA") if im.mode != "RGBA" else im
    bb = im.getchannel("A").getbbox()
    if not bb:
        return None
    if trim and bb != (0, 0, im.width, im.height):
        im = im.crop(bb)
        ox, oy = ox + bb[0], oy + bb[1]
    w, h = im.size
    cx, cy = ox + w / 2, oy + h / 2
    rot = float(rot or 0)
    if rot % 360:
        im = im.rotate(-rot, expand=True, resample=Image.BICUBIC)
    return {"id": lid, "kind": kind, "name": name, "img": im, "x": int(round(cx - im.width / 2)), "y": int(round(cy - im.height / 2)),
            "frame": (cx, cy, w, h, rot), "anchor": anchor or (cx, cy), "s": s, "locked": locked, **extra}


def _place(canvas: Image.Image, im: Image.Image, x: int, y: int) -> None:
    """alpha_composite that also accepts pieces hanging over the canvas edge."""
    W, H = canvas.size
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + im.width), min(H, y + im.height)
    if x1 <= x0 or y1 <= y0:
        return
    canvas.alpha_composite(im, dest=(x0, y0), source=(x0 - x, y0 - y, x1 - x, y1 - y))


def _hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(int(v) for v in rgb[:3])


def sticker_uid(st: dict, i: int) -> str:
    return str(st.get("uid") or f"i{i}")[:24]


def render(frame: Image.Image | None, settings: dict, *, alpha: Image.Image | None = None, face: dict | None = None,
           frame2: Image.Image | None = None, paths: dict | None = None, layers: bool = False) -> tuple[Image.Image, dict]:
    """Compose one thumbnail. `paths`: resolved files {bg_image, logo, stickers: {id: path}}.
    layers=True also returns info["_layers"] = {base, layers, hidden} for the studio's direct editing."""
    paths = paths or {}
    t = resolve(settings)
    W, H = size_px(settings)
    base_key = t.get("base", t["size"])
    if frame is None:  # template studio without a video: no person, photo backgrounds become a gradient
        t["person"] = None
        frame = _gradient((W, H), (24, 28, 38), (52, 60, 80), 110).convert("RGB")
        if (t.get("bg") or {}).get("type") in ("blur", "photo", "split", None, ""):
            t["bg"] = {"type": "gradient", "color": "#1F2633", "color2": "#3B4660", "angle": 110}
    accent = t["accent"]
    unit = max(W, H) / 1280
    lay_ov = layout_of(settings, t["size"])
    bg = t.get("bg") or {"type": "blur"}
    want_cutout = settings.get("cutout", True) and t.get("person") is not None
    use_alpha = alpha if want_cutout else None
    person = t.get("person")
    btype = bg.get("type", "blur")
    if btype == "image" and not paths.get("bg_image"):
        btype = "blur"
    # without a cutout, solid/gradient/image backgrounds would hide the person → the photo fills the frame
    if person is not None and use_alpha is None and btype in ("solid", "gradient", "image", "blur"):
        photo_mode = True
    else:
        photo_mode = btype == "photo"
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    focus_x = face["cx"] if face else 0.5
    out_layers: list[dict] = []
    hidden: list[dict] = []

    def add(lay: dict | None) -> None:
        if lay is not None:
            out_layers.append(lay)

    def is_hidden(lid: str, name: str, kind: str) -> bool:
        if _ovr(lay_ov, lid).get("hidden"):
            hidden.append({"id": lid, "name": name, "kind": kind})
            return True
        return False

    if btype == "split":
        a2 = frame2 or frame
        if base_key == "vertical":
            top = _grade(_cover(a2, (W, H // 2), focus_x), "dark")
            top = ImageEnhance.Color(top).enhance(0.15)
            canvas.paste(top, (0, 0))
            canvas.paste(_grade(_cover(frame, (W, H - H // 2), focus_x), "pop"), (0, H // 2))
            ImageDraw.Draw(canvas).rectangle((0, H // 2 - int(5 * unit), W, H // 2 + int(5 * unit)), fill=(*_rgb("accent", accent), 255))
        else:
            left = ImageEnhance.Brightness(ImageEnhance.Color(_cover(a2, (W // 2, H), focus_x)).enhance(0.15)).enhance(0.8)
            canvas.paste(left, (0, 0))
            canvas.paste(_grade(_cover(frame, (W - W // 2, H), focus_x), "pop"), (W // 2, 0))
            ImageDraw.Draw(canvas).rectangle((W // 2 - int(5 * unit), 0, W // 2 + int(5 * unit), H), fill=(*_rgb("accent", accent), 255))
        canvas.alpha_composite(_scrim((W, H), "top", (0, 0, 0), 0.7, 0.45))
    elif photo_mode and person is not None:
        # no cutout: the photo IS the background (not a movable layer)
        lay, _ = _person_layer(adjust(_grade(frame, t.get("grade")), settings.get("person_adj") or person.get("adj")), None, face, person, (W, H), accent)
        canvas.alpha_composite(lay)
        if btype in ("solid", "gradient") and t.get("scrim") is None:
            col = _rgb(bg.get("color"), accent, (0, 0, 0))
            canvas.alpha_composite(_scrim((W, H), "left" if person.get("x", 0.5) > 0.5 else "right", col, 0.8, 0.55))
    else:
        if btype == "solid":
            canvas.paste(Image.new("RGB", (W, H), _rgb(bg.get("color"), accent, (17, 24, 39))), (0, 0))
        elif btype == "gradient":
            canvas.paste(_gradient((W, H), _rgb(bg.get("color"), accent, (15, 32, 39)), _rgb(bg.get("color2"), accent, (44, 83, 100)),
                                   float(bg.get("angle", 90))), (0, 0))
        elif btype == "image":
            canvas.paste(_cover(Image.open(paths["bg_image"]).convert("RGB"), (W, H)), (0, 0))
        else:  # blur / photo (no person)
            b = _cover(frame, (W, H), focus_x)
            if btype == "blur":
                b = b.filter(ImageFilter.GaussianBlur(float(bg.get("blur", 22)) * unit))
                if bg.get("gray"):
                    b = ImageEnhance.Color(b).enhance(0.2)
                b = ImageEnhance.Brightness(b).enhance(1 - float(bg.get("dim", 0.4)))
            canvas.paste(_grade(b, t.get("grade")), (0, 0))
        if person is not None:
            if t.get("scrim"):  # scrim between background and person keeps the person bright
                sc = t["scrim"]
                canvas.alpha_composite(_scrim((W, H), sc.get("side", "left"), _rgb(sc.get("color"), accent, (0, 0, 0)),
                                              float(sc.get("alpha", 0.5)), float(sc.get("extent", 0.6))))
            if t.get("overlay"):  # light behind the person
                po = _ovr(lay_ov, "person")
                ov_img = _overlay((W, H), t["overlay"], _rgb("accent", accent), *_pos(po, person.get("x", 0.5), person.get("face_y", 0.4)))
                if ov_img is not None:
                    canvas.alpha_composite(ov_img)
            o = _ovr(lay_ov, "person")
            if not is_hidden("person", "Person", "person"):
                spec = dict(person)
                free = any(k in o for k in ("x", "y", "s"))
                spec["x"], spec["face_y"] = _pos(o, spec.get("x", 0.7), spec.get("face_y", 0.42))
                ps = _num(o, "s", 1.0, 0.1, 6.0)
                spec["face_h"] = spec.get("face_h", 0.4) * ps
                lay, pl = _person_layer(adjust(_grade(frame, t.get("grade")), settings.get("person_adj") or spec.get("adj")), use_alpha, face, spec, (W, H),
                                        accent, free=free)
                add(_layer("person", "person", "Person", lay, 0, 0, rot=_num(o, "rot", 0.0, -360, 360), anchor=(pl["ax"], pl["ay"]), s=ps))
    if t.get("scrim") and (photo_mode or person is None) and btype != "split":
        sc = t["scrim"]
        canvas.alpha_composite(_scrim((W, H), sc.get("side", "left"), _rgb(sc.get("color"), accent, (0, 0, 0)),
                                      float(sc.get("alpha", 0.5)), float(sc.get("extent", 0.6))))
    if t.get("overlay") and (photo_mode or person is None):
        ov_img = _overlay((W, H), t["overlay"], _rgb("accent", accent), (person or {}).get("x", 0.5), (person or {}).get("face_y", 0.4))
        if ov_img is not None:
            canvas.alpha_composite(ov_img)
    base = canvas
    if t.get("vignette"):
        add(_layer("vignette", "fx", "Vignette", _vignette((W, H), float(t["vignette"])), 0, 0, locked=True, trim=False))
    # template shapes
    shape_names = SHAPES
    for i, s in enumerate(t.get("shapes") or []):
        lid = f"shape{i}"
        if is_hidden(lid, shape_names.get(s["type"], s["type"]), "shape"):
            continue
        o = _ovr(lay_ov, lid)
        k = _num(o, "s", 1.0, 0.1, 6.0)
        col = _rgb(s.get("color") or "accent", accent)
        size_f = s.get("len", 0.2) if s["type"] == "arrow" else s.get("w", 0.15 if s["type"] != "underline" else 0.25)
        lay = shape_image(s["type"], col, int(size_f * W * k), bool(s.get("fill")))
        rot0 = float(s.get("rot", 0))
        x, y = _pos(o, s["x"], s["y"])
        add(_layer(lid, "shape", shape_names.get(s["type"], s["type"]), lay, x * W - lay.width / 2, y * H - lay.height / 2,
                   rot=_num(o, "rot", rot0, -360, 360), anchor=(x * W, y * H), s=k))
    # user stickers: library images, shapes, free text
    for i, s in enumerate((settings.get("stickers") or [])[:MAX_STICKERS]):
        if not isinstance(s, dict):
            continue
        uid = sticker_uid(s, i)
        x, y = _num(s, "x", 0.5, -0.5, 1.5), _num(s, "y", 0.5, -0.5, 1.5)
        rot = _num(s, "rot", 0.0, -360, 360)
        w = int(_num(s, "w", 0.15, 0.01, 3.0) * W)
        extra: dict = {"uid": uid}
        if s.get("txt") is not None:
            txt = str(s.get("txt") or "").strip()[:80]
            if not txt:
                continue
            px = int(_num(s, "size", 0.08, 0.01, 0.6) * H)
            fam = s.get("font") if s.get("font") in FONTS else "Mukta"
            col = _rgb(s.get("color") or "#FFFFFF", accent)
            bgc = _rgb(s["bg"], accent) if s.get("bg") else None
            if _is_emoji(txt):
                lay = _emoji(txt, px)
                kind, name = "emoji", txt
            else:
                lay = _label(txt, px=px, fam=fam, color=col, bg=bgc, stroke=s.get("stroke"), accent=accent, stroke_w=_num(s, "stroke_w", None, 0, 0.5))
                kind, name = "textsticker", txt[:24]
            extra["edit"] = {"value": txt, "font": fam, "px": px / H, "color": _hex(col), "bg": _hex(bgc) if bgc else "", "align": "center"}
        elif s.get("shape") in SHAPES:
            col = _rgb(s.get("color") or "accent", accent)
            lay = shape_image(s["shape"], col, w, bool(s.get("fill")), stroke=_rgb(s["stroke"], accent) if s.get("stroke") else None,
                              stroke_w=_num(s, "stroke_w", None, 0, 0.2), radius=_num(s, "radius", None, 0, 0.5),
                              aspect=_num(s, "h", None, 0.02, 4.0), shadow=bool(s.get("shadow")))
            kind, name = "shape", SHAPES[s["shape"]]
        elif s.get("qr"):
            lay = qr_image(str(s["qr"])[:400], w, _rgb(s.get("color") or "#111111", accent), _rgb(s.get("bg") or "#FFFFFF", accent))
            kind, name = "qr", "QR"
            if lay is None:
                continue
        else:
            p = (paths.get("stickers") or {}).get(s.get("id"))
            lay = _sticker(Path(p), w) if p else None
            kind, name = "sticker", "sticker"
        if lay is not None:
            add(_layer(f"s:{uid}", kind, name, lay, x * W - lay.width / 2, y * H - lay.height / 2, rot=rot, anchor=(x * W, y * H), **extra))
    # labels (before/after, BREAKING, ?)
    for i, lab in enumerate(t.get("labels") or []):
        lid = f"label{i}"
        if is_hidden(lid, str(lab["text"])[:24], "label"):
            continue
        o = _ovr(lay_ov, lid)
        k = _num(o, "s", 1.0, 0.1, 6.0)
        bgc = _rgb(lab["bg"], accent) if lab.get("bg") else None
        fam = lab.get("font") or "Mukta"
        col = _rgb(lab.get("color") or "#FFFFFF", accent)
        px = int(lab.get("size", 0.06) * H * k)
        lay = _label(str(lab["text"]), px=px, fam=fam, color=col, bg=bgc)
        x, y = _pos(o, lab["x"], lab["y"])
        add(_layer(lid, "label", str(lab["text"])[:24], lay, x * W - lay.width / 2, y * H - lay.height / 2,
                   rot=_num(o, "rot", float(lab.get("rotate", 0)), -360, 360), anchor=(x * W, y * H), s=k,
                   edit={"value": str(lab["text"]), "font": fam, "px": px / H, "color": _hex(col), "bg": _hex(bgc) if bgc else "",
                         "align": "center", "index": i}))
    # number badge
    text = settings.get("text") or ""
    badge_txt = str(settings.get("badge") or "").strip() or (leading_number(text) if t.get("badge") else "")
    if t.get("badge") and badge_txt and not is_hidden("badge", "Badge " + badge_txt, "badge"):
        bd = t["badge"]
        o = _ovr(lay_ov, "badge")
        k = _num(o, "s", 1.0, 0.1, 6.0)
        r = int(bd.get("r", 0.14) * H * k)
        cx, cy = _pos(o, bd["x"], bd["y"])
        lay = Image.new("RGBA", (r * 2 + 20, r * 2 + 20), (0, 0, 0, 0))
        dd = ImageDraw.Draw(lay)
        dd.ellipse((4, 8, r * 2 + 12, r * 2 + 16), fill=(0, 0, 0, 120))
        dd.ellipse((0, 0, r * 2 + 8, r * 2 + 8), fill=(255, 255, 255, 255))
        dd.ellipse((int(r * 0.07) + 2, int(r * 0.07) + 2, r * 2 + 6 - int(r * 0.07), r * 2 + 6 - int(r * 0.07)),
                   fill=(*_rgb(bd.get("color") or "accent", accent), 255))
        fpx = int(r * (1.25 if len(badge_txt) <= 1 else 1.0 if len(badge_txt) == 2 else 0.75))
        bf = font("Poppins", max(8, fpx))
        dd.text((r + 4, r + 4), badge_txt, font=bf, fill=(*_rgb(bd.get("text_color") or "#111111", accent), 255), anchor="mm")
        lay = lay.rotate(-6, expand=True, resample=Image.BICUBIC)
        add(_layer("badge", "badge", "Badge " + badge_txt, lay, cx * W - lay.width / 2, cy * H - lay.height / 2,
                   rot=_num(o, "rot", 0.0, -360, 360), anchor=(cx * W, cy * H), s=k))
    # main text
    tx = dict(t.get("text") or {})
    lines = parse_text(text, strip_number=bool(tx.get("strip_number") and badge_txt), upper=bool(settings.get("upper")))
    tinfo = {"px": 0, "regions": [], "box": [0, 0, 0, 0], "style": tx.get("style"), "stroke": 0, "fill": (255, 255, 255)}
    if lines and tx.get("box") and not is_hidden("text", "Text", "text"):
        o = _ovr(lay_ov, "text")
        k = _num(o, "s", 1.0, 0.1, 6.0)
        x0, y0, x1, y1 = tx["box"]
        bcx, bcy = _pos(o, (x0 + x1) / 2, (y0 + y1) / 2)
        bw, bh = (x1 - x0) * k, (y1 - y0) * k
        tx["box"] = [bcx - bw / 2, bcy - bh / 2, bcx + bw / 2, bcy + bh / 2]
        tx["max"] = tx.get("max", 0.18) * k
        rot = _num(o, "rot", -float(tx.get("rotate") or 0), -360, 360)
        tx["rotate"] = 0
        tl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        tinfo = draw_text(tl, tx, lines, accent)
        add(_layer("text", "text", "Text", tl, 0, 0, rot=rot, anchor=(bcx * W, bcy * H), s=k,
                   edit={"value": text, "font": tx.get("font", "Mukta"), "px": tinfo["px"] / H, "color": _hex(tinfo["fill"]),
                         "hl": _hex(_rgb(tx.get("hl"), accent, (255, 212, 0))), "align": tx.get("align", "left"), "style": tinfo["style"]}))
    # logo
    if settings.get("logo") and paths.get("logo") and not is_hidden("logo", "Logo", "logo"):
        o = _ovr(lay_ov, "logo")
        k = _num(o, "s", 1.0, 0.1, 6.0)
        lw = int(W * (0.11 if base_key == "yt" else 0.16) * k)
        lay = _sticker(Path(paths["logo"]), lw)
        if lay is not None:
            pos = settings.get("logo_pos") or "tr"
            m = int(0.025 * W)
            x = m if pos[1] == "l" else W - m - lay.width
            y = m if pos[0] == "t" else H - m - lay.height
            cx, cy = _pos(o, (max(0, x) + lay.width / 2) / W, (max(0, y) + lay.height / 2) / H)
            add(_layer("logo", "logo", "Logo", lay, cx * W - lay.width / 2, cy * H - lay.height / 2,
                       rot=_num(o, "rot", 0.0, -360, 360), anchor=(cx * W, cy * H), s=k))
    # z-order: the user's order first (bottom → top), anything new goes on top
    order = lay_ov.get("_order")
    if not (isinstance(order, list) and order) and t.get("text_behind"):
        order = ["text", "person"]
    if isinstance(order, list) and order:
        rank = {str(k): n for n, k in enumerate(order)}
        known = sorted((x for x in out_layers if x["id"] in rank), key=lambda x: rank[x["id"]])
        out_layers = known + [x for x in out_layers if x["id"] not in rank]
    if t.get("border"):
        bwid = max(2, int(float(t["border"].get("width", 0.01)) * W))
        bl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(bl).rectangle((bwid // 2, bwid // 2, W - 1 - bwid // 2, H - 1 - bwid // 2),
                                     outline=(*_rgb(t["border"].get("color"), accent), 255), width=bwid)
        add(_layer("border", "fx", "Border", bl, 0, 0, locked=True, trim=False))
    for ly in out_layers:  # per-layer opacity / lock from the layout overrides
        o = _ovr(lay_ov, ly["id"])
        op = _num(o, "op", 1.0, 0.0, 1.0)
        if op < 1.0:
            im = ly["img"].copy()
            im.putalpha(im.getchannel("A").point(lambda a, _o=op: int(a * _o)))
            ly["img"] = im
            ly["op"] = op
        if o.get("locked"):
            ly["locked"] = True
    comp = base.copy() if layers else base
    for ly in out_layers:
        _place(comp, ly["img"], ly["x"], ly["y"])
    out = comp.convert("RGB")
    info = {"template": t["id"], "size": t["size"], "width": W, "height": H, "font_px": tinfo["px"], "style": tinfo["style"],
            "lines": len(lines), "words": sum(len(x) for x in lines), "cutout": bool(use_alpha is not None and not photo_mode),
            "text_box": tinfo["box"], "contrast": _text_contrast(out, tinfo)}
    if layers:
        info["_layers"] = {"base": base.convert("RGB"), "layers": out_layers, "hidden": hidden}
    return out, info


def _text_contrast(img: Image.Image, tinfo: dict) -> float | None:
    """Rough legibility: text fill vs the pixels just around each word (the outline counts as background)."""
    regs = tinfo.get("regions") or []
    if not regs:
        return None
    arr = np.asarray(img).astype(np.float32)
    H, W = arr.shape[:2]
    worst = 99.0
    for x0, y0, x1, y1, col in regs[:12]:
        pad = max(4, int((y1 - y0) * 0.35))
        xa, ya, xb, yb = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
        if xb <= xa or yb <= ya:
            continue
        patch = arr[ya:yb, xa:xb].reshape(-1, 3)
        # background = pixels that are clearly not the text colour
        dist = np.abs(patch - np.array(col, np.float32)).sum(axis=1)
        bgpx = patch[dist > 120]
        if len(bgpx) < 10:
            continue
        bgc = tuple(np.median(bgpx, axis=0))
        worst = min(worst, float(contrast(col, tuple(float(x) for x in bgc))))
    return round(worst, 2) if worst < 99 else None


def to_jpeg(img: Image.Image, max_bytes: int = 1_900_000) -> bytes:
    """YouTube allows 2 MB; step the quality down until it fits."""
    from io import BytesIO
    for q in (92, 88, 84, 80, 74, 68, 60):
        buf = BytesIO()
        img.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
        if buf.tell() <= max_bytes:
            return buf.getvalue()
    return buf.getvalue()


# ---------------------------------------------------------------- linter
def _norm(s: str) -> str:
    return re.sub(r"[^\wऀ-ॿ]+", " ", plain(s).lower()).strip()


def lint(settings: dict, info: dict | None, title: str = "") -> list[dict]:
    """Warnings for the thumbnail text (and how it relates to the video title)."""
    out = []
    text = plain(settings.get("text") or "")
    words = text.split()
    size = base_of(settings)
    if not words:
        out.append({"level": "info", "code": "no_text", "msg": "कोई text नहीं — 2–4 बड़े शब्द CTR अक्सर बढ़ाते हैं"})
    elif len(words) > 5:
        out.append({"level": "warn", "code": "too_many_words", "msg": f"{len(words)} शब्द हैं — 5 से कम रखें (phone पर 2–4 सबसे अच्छे)"})
    if len((settings.get("text") or "").strip().split("\n")) > 3:
        out.append({"level": "warn", "code": "too_many_lines", "msg": "3 से ज़्यादा लाइनें — सिर्फ़ पहली 3 दिखेंगी"})
    if title and words:
        nt, nx = _norm(title), _norm(text)
        tw = set(nt.split())
        overlap = sum(1 for w in nx.split() if w in tw) / max(1, len(nx.split()))
        if nx and (nx == nt or (nx in nt and len(nx.split()) >= 4) or (overlap >= 0.85 and len(nx.split()) >= 4)):
            out.append({"level": "warn", "code": "repeats_title", "msg": "text title को दोहरा रहा है — thumbnail पर title से अलग, उत्सुकता जगाने वाले शब्द लिखें"})
    if info:
        H = info.get("height") or 720
        rel = (info.get("font_px") or 0) / H
        min_rel = 0.085 if size == "yt" else 0.035
        if words and info.get("font_px") and rel < min_rel:
            out.append({"level": "warn", "code": "too_small", "msg": "text बहुत छोटा है — phone पर नहीं पढ़ा जाएगा; शब्द कम करें या size बढ़ाएँ"})
        c = info.get("contrast")
        style = info.get("style")
        need = 2.0 if style in ("outline", "block", "box", "highlight") else 3.0
        if words and c is not None and c < need:
            out.append({"level": "warn", "code": "low_contrast", "msg": f"text और background का contrast कम है ({c}:1) — outline / box style या दूसरा रंग चुनें"})
    if base_of(settings) == "yt" and not settings.get("cutout", True) and (settings.get("bg") or {}).get("type") in ("solid", "gradient"):
        out.append({"level": "info", "code": "no_cutout", "msg": "cutout बंद है, इसलिए पूरा frame background में लगा है"})
    return out


# ---------------------------------------------------------------- text suggestions
STOP_EXTRA = {"कैसे", "क्यों", "वीडियो", "video", "part", "भाग", "|", "-", "–"}


def _heuristic_texts(title: str, transcript_text: str) -> list[str]:
    from .metadata import STOP, _keywords
    from .shorts import HOOK_WORDS
    title = plain(title)
    tw = [w.strip("।.,!?:;\"'()[]") for w in title.split()]
    tw = [w for w in tw if w]
    num = next((w for w in tw if re.fullmatch(r"[0-9०-९]+", w)), "")
    keys = [w for w in tw if len(w) >= 3 and w.lower() not in STOP and w.lower() not in STOP_EXTRA and not re.fullmatch(r"[0-9०-९]+", w)]
    kw = _keywords(transcript_text, 8) if transcript_text else []
    opts: list[str] = []
    if num and keys:
        opts.append(f"{num} *{keys[0]}*" + (f" {keys[1]}" if len(keys) > 1 else ""))
    if len(keys) >= 2:
        opts.append(f"{keys[0]} *{keys[1]}*")
    hook = [w for w in kw if w in HOOK_WORDS][:2]
    if hook:
        opts.append(" ".join(f"*{w}*" if i == len(hook) - 1 else w for i, w in enumerate(hook)) + ("?" if len(hook) == 1 else ""))
    if kw:
        top = [w for w in kw if w not in {k.lower() for k in keys}][:3] or kw[:3]
        if top:
            opts.append(" ".join(top[:2]) + (f" *{top[2]}*" if len(top) > 2 else ""))
    lang_hi = bool(re.search(r"[ऀ-ॿ]", title + transcript_text[:200]))
    generic = ["ये *गलती* मत करना", "*सच* जो कोई नहीं बताता", "सब *बदल* गया"] if lang_hi else ["Don't do *THIS*", "The *truth*", "It *changed* everything"]
    for g in generic:
        if len(opts) >= 4:
            break
        opts.append(g)
    seen, out = set(), []
    for o in opts:
        k = plain(o)
        if k and k not in seen and len(k.split()) <= 5:
            seen.add(k)
            out.append(o)
    return out[:5]


def suggest_texts(title: str, transcript_text: str = "", language: str = "hi", n: int = 4) -> dict:
    from . import llm
    base = _heuristic_texts(title, transcript_text)
    if not llm.available():
        return {"options": base[:n], "source": "heuristic"}
    prompt = (f"Video title: {title}\nLanguage: {'Hindi (Devanagari), Hinglish ok' if language != 'en' else 'English'}\n"
              f"Transcript start: {transcript_text[:1500]}\n\n"
              f"Write {n} different YouTube THUMBNAIL texts. Rules: 2–5 words each, punchy, curiosity or emotion, "
              "must NOT repeat the title, may use a number, mark exactly one key word as *word* (it gets a highlight colour), "
              "use \\n for a line break if it helps (max 2 lines). Reply JSON: {\"options\": [\"...\"]}")
    data = llm.ask_json(prompt, system="You design high-CTR YouTube thumbnails for a Hindi creator. JSON only.", max_tokens=400)
    opts = [str(o).strip()[:60] for o in ((data or {}).get("options") or []) if str(o).strip()] if isinstance(data, dict) else []
    opts = [o for o in opts if len(plain(o).split()) <= 5]
    if not opts:
        return {"options": base[:n], "source": "heuristic"}
    return {"options": opts[:n], "source": "llm"}
