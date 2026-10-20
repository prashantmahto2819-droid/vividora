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
# family → (file, variable-font instance)
FONTS = {
    "Mukta": ("Mukta-ExtraBold.ttf", None),
    "Baloo 2": ("Baloo2.ttf", b"ExtraBold"),
    "Hind": ("Hind-Bold.ttf", None),
    "Poppins": ("Poppins-Black.ttf", None),
    "Noto Sans Devanagari": ("NotoSansDevanagari.ttf", b"Black"),
}
STYLES = {"outline": "मोटी outline", "shadow": "soft shadow", "box": "पट्टी / box", "highlight": "highlight शब्द",
          "block": "3D block"}
BG_TYPES = {"": "template जैसा", "photo": "पूरा frame", "blur": "धुँधला frame", "solid": "एक रंग", "gradient": "gradient",
            "image": "library image"}
SHAPES = {"arrow": "तीर", "circle": "गोला", "underline": "underline"}
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
_HL = re.compile(r"(\*[^*]+\*)")


def parse_text(text: str, *, strip_number: bool = False, upper: bool = False) -> list[list[tuple[str, bool]]]:
    """'3 *बड़ी* गलतियाँ\\nजो आप करते हो' → [[('3',F),('बड़ी',T),('गलतियाँ',F)], [...]]"""
    lines = []
    for raw in (text or "").replace("\r", "").split("\n")[:3]:
        words: list[tuple[str, bool]] = []
        for part in _HL.split(raw):
            if not part:
                continue
            hl = part.startswith("*") and part.endswith("*") and len(part) > 2
            for w in (part[1:-1] if hl else part).split():
                words.append((w.upper() if upper else w, hl))
        if strip_number and not lines and words and re.fullmatch(r"[0-9०-९]+", words[0][0]):
            words = words[1:]
        if words:
            lines.append(words)
    return lines


def leading_number(text: str) -> str:
    m = re.match(r"\s*\*?([0-9०-९]{1,3})\b", text or "")
    return m.group(1) if m else ""


def plain(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("*", " ")).strip()


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
    return img


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


def _label(text: str, *, px: int, fam: str, color, bg, rotate: float = 0) -> Image.Image:
    f = font(fam, px)
    l, t, r, b = f.getbbox(text, anchor="ls")
    padx, pady = (int(px * 0.35), int(px * 0.18)) if bg else (int(px * 0.08), int(px * 0.08))
    stroke = 0 if bg else max(2, px // 16)
    im = Image.new("RGBA", (r - l + padx * 2 + stroke * 2, b - t + pady * 2 + stroke * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if bg:
        d.rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=int(px * 0.18), fill=(*bg, 255))
    d.text((padx + stroke - l, pady + stroke - t), text, font=f, fill=(*color, 255), anchor="ls",
           stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
    return im.rotate(-rotate, expand=True, resample=Image.BICUBIC) if rotate else im


# ---------------------------------------------------------------- text block
def _measure(lines, f, space: float):
    out = []
    for words in lines:
        ws = [f.getlength(w) for w, _ in words]
        bb = [f.getbbox(w, anchor="ls") for w, _ in words]
        top = min(b[1] for b in bb)
        bot = max(b[3] for b in bb)
        out.append({"w": sum(ws) + space * (len(words) - 1), "ws": ws, "top": top, "bot": bot})
    return out


def _fit(lines, fam: str, box_w: int, box_h: int, max_px: int, style: str) -> tuple[int, list[dict]]:
    px = max_px
    while px > 14:
        f = font(fam, px)
        sp = f.getlength(" ") * 1.05
        m = _measure(lines, f, sp)
        pad = px * (0.5 if style == "box" else 0.12 if style in ("outline", "block", "highlight") else 0.04)
        gap = px * (0.18 if style == "box" else 0.06)
        tot_h = sum(x["bot"] - x["top"] for x in m) + gap * (len(m) - 1) + (pad * 0.6 * len(m) if style == "box" else 0)
        if max(x["w"] for x in m) + pad * 2 <= box_w and tot_h + pad <= box_h:
            return px, m
        px = int(px * 0.94)
    f = font(fam, px)
    return px, _measure(lines, f, f.getlength(" ") * 1.05)


def draw_text(canvas: Image.Image, text_spec: dict, lines, accent: str) -> dict:
    """Draw the text block onto `canvas` (RGBA). Returns size/box info for the linter."""
    W, H = canvas.size
    x0, y0, x1, y1 = text_spec["box"]
    bx, by, bw, bh = int(x0 * W), int(y0 * H), int((x1 - x0) * W), int((y1 - y0) * H)
    style = text_spec.get("style", "outline")
    fam = text_spec.get("font", "Mukta")
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
        px_c, m_c = _fit(cand, fam, bw, bh, max_px, style)
        if best is None or px_c > best[0] * 1.08:
            best = (px_c, m_c, cand)
    px, m, lines = best
    f = font(fam, px)
    sp = f.getlength(" ") * 1.05
    fill = _rgb(text_spec.get("color"), accent)
    hl = _rgb(text_spec.get("hl"), accent, (255, 212, 0))
    stroke_c = _rgb(text_spec.get("stroke") or "#000000", accent, (0, 0, 0))
    box_c = _rgb(text_spec.get("box_color") or "#000000", accent, (0, 0, 0))
    line_boxes = text_spec.get("line_boxes") or []
    line_colors = text_spec.get("line_colors") or []
    gap = px * (0.18 if style == "box" else 0.06)
    bpad_y = px * 0.14 if style == "box" else 0
    heights = [x["bot"] - x["top"] + bpad_y * 2 for x in m]
    total = sum(heights) + gap * (len(m) - 1)
    va = text_spec.get("valign", "center")
    cy = by + (0 if va == "top" else (bh - total) if va == "bottom" else (bh - total) / 2)
    al = text_spec.get("align", "left")
    padx = int((text_spec.get("pad_x") or 0) * W) if style == "box" else 0
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0)) if style in ("shadow", "outline", "highlight", "block") else None
    d = ImageDraw.Draw(layer)
    sd = ImageDraw.Draw(shadow) if shadow is not None else None
    sw = max(2, int(px * 0.085)) if style in ("outline", "block") else max(1, int(px * 0.03)) if style == "highlight" else 0
    regions = []
    for i, (words, mm) in enumerate(zip(lines, m)):
        lw = mm["w"]
        bpad_x = px * 0.22 if style == "box" else 0
        if al == "center":
            lx = bx + (bw - lw) / 2
        elif al == "right":
            lx = bx + bw - lw - bpad_x - padx * 0
        else:
            lx = bx + bpad_x + padx
        base_y = cy + bpad_y - mm["top"]
        lfill = _rgb(line_colors[i], accent) if i < len(line_colors) and line_colors[i] else fill
        if style == "box":
            lb = _rgb(line_boxes[i], accent) if i < len(line_boxes) and line_boxes[i] else box_c
            rx0 = (bx if (padx and al == "left") else lx - bpad_x)
            d.rectangle((rx0, cy, lx + lw + bpad_x, cy + heights[i]), fill=(*lb, 255))
        x = lx
        for (w, is_hl), ww in zip(words, mm["ws"]):
            col = lfill
            if is_hl:
                if style == "box":
                    d.rectangle((x - px * 0.08, cy + px * 0.03, x + ww + px * 0.08, cy + heights[i] - px * 0.03), fill=(*hl, 255))
                    col = (17, 17, 17) if _lum(hl) > 0.35 else (255, 255, 255)
                elif style == "highlight":
                    d.rounded_rectangle((x - px * 0.12, base_y + mm["top"] - px * 0.08, x + ww + px * 0.12, base_y + mm["bot"] + px * 0.08),
                                        radius=int(px * 0.14), fill=(*hl, 255))
                    col = (17, 17, 17) if _lum(hl) > 0.35 else (255, 255, 255)
                else:
                    col = hl
            if style == "block" and sd is not None:
                depth = max(3, int(px * 0.07))
                for k in range(depth, 0, -1):
                    d.text((x + k, base_y + k), w, font=f, fill=(*stroke_c, 255), anchor="ls", stroke_width=sw, stroke_fill=(*stroke_c, 255))
            if sd is not None:
                off = max(2, int(px * 0.05))
                sd.text((x + off, base_y + off), w, font=f, fill=(0, 0, 0, 200 if style != "shadow" else 230), anchor="ls",
                        stroke_width=sw, stroke_fill=(0, 0, 0, 200))
            stroke_this = sw if not (is_hl and style == "highlight") else 0
            d.text((x, base_y), w, font=f, fill=(*col, 255), anchor="ls", stroke_width=stroke_this, stroke_fill=(*stroke_c, 255))
            regions.append((int(x), int(base_y + mm["top"]), int(x + ww), int(base_y + mm["bot"]), col))
            x += ww + sp
        cy += heights[i] + gap
    rot = float(text_spec.get("rotate") or 0)
    if shadow is not None:
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(2, px * (0.09 if style == "shadow" else 0.03))))
        if rot:
            shadow = shadow.rotate(rot, center=(bx + bw / 2, by + bh / 2), resample=Image.BICUBIC)
        canvas.alpha_composite(shadow)
    if rot:
        layer = layer.rotate(rot, center=(bx + bw / 2, by + bh / 2), resample=Image.BICUBIC)
    canvas.alpha_composite(layer)
    return {"px": px, "box": [bx, by, bw, bh], "regions": regions, "style": style, "stroke": sw, "fill": fill}


# ---------------------------------------------------------------- render
def resolve(settings: dict) -> dict:
    """Template + user settings → one flat spec."""
    size = settings.get("size") if settings.get("size") in SIZES else "yt"
    t = template(settings.get("template") or "face_right", size)
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
    if settings.get("grade") is not None and settings.get("grade") != "":
        t["grade"] = None if settings["grade"] == "none" else settings["grade"]
    if settings.get("labels") and t.get("labels"):
        for lab, txt in zip(t["labels"], settings["labels"]):
            if txt:
                lab["text"] = str(txt)[:30]
    if settings.get("no_shapes"):
        t["shapes"] = []
    if settings.get("flip") and size == "yt":
        t = _flip(t)
    t["accent"] = accent
    t["size"] = size
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


def _person_layer(frame: Image.Image, alpha: Image.Image | None, face: dict | None, spec: dict, size, accent: str):
    """Scale/position the subject. Returns (rgba layer full-canvas, placement dict)."""
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
        if touches and oy + nh < H:
            oy = H - nh
    img = frame.resize((nw, nh), Image.LANCZOS)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    if alpha is None:
        layer.paste(img, (int(ox), int(oy)))
        return layer, {"cutout": False, "x": ox, "y": oy, "w": nw, "h": nh}
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
        g = _expand(full_a, int(26 * unit)).filter(ImageFilter.GaussianBlur(22 * unit))
        gl = Image.new("RGBA", size, (*_rgb(spec["glow"], accent), 0))
        gl.putalpha(g)
        layer.alpha_composite(gl)
        layer.alpha_composite(gl)
    if spec.get("stroke"):
        st = _expand(full_a, int(16 * unit))
        sl = Image.new("RGBA", size, (*_rgb(spec["stroke"], accent), 0))
        sl.putalpha(st)
        layer.alpha_composite(sl)
    layer.alpha_composite(subj)
    return layer, {"cutout": True, "x": ox, "y": oy, "w": nw, "h": nh}


def render(frame: Image.Image, settings: dict, *, alpha: Image.Image | None = None, face: dict | None = None,
           frame2: Image.Image | None = None, paths: dict | None = None) -> tuple[Image.Image, dict]:
    """Compose one thumbnail. `paths`: resolved files {bg_image, logo, stickers: {id: path}}."""
    paths = paths or {}
    t = resolve(settings)
    W, H = SIZES[t["size"]]
    accent = t["accent"]
    unit = max(W, H) / 1280
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
    if btype == "split":
        a2 = frame2 or frame
        if t["size"] == "vertical":
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
        lay, _ = _person_layer(_grade(frame, t.get("grade")), None, face, person, (W, H), accent)
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
            lay, _ = _person_layer(_grade(frame, t.get("grade")), use_alpha, face, person, (W, H), accent)
            if t.get("scrim"):  # scrim between background and person keeps the person bright
                sc = t["scrim"]
                canvas.alpha_composite(_scrim((W, H), sc.get("side", "left"), _rgb(sc.get("color"), accent, (0, 0, 0)),
                                              float(sc.get("alpha", 0.5)), float(sc.get("extent", 0.6))))
            canvas.alpha_composite(lay)
    if t.get("scrim") and (photo_mode or person is None) and btype != "split":
        sc = t["scrim"]
        canvas.alpha_composite(_scrim((W, H), sc.get("side", "left"), _rgb(sc.get("color"), accent, (0, 0, 0)),
                                      float(sc.get("alpha", 0.5)), float(sc.get("extent", 0.6))))
    if t.get("vignette"):
        canvas.alpha_composite(_vignette((W, H), float(t["vignette"])))
    # shapes (template) + user stickers
    for s in (t.get("shapes") or []):
        col = _rgb(s.get("color") or "accent", accent)
        if s["type"] == "arrow":
            lay = _arrow(col, int(s.get("len", 0.2) * W), float(s.get("rot", 0)))
        elif s["type"] == "circle":
            lay = _ring(col, int(s.get("w", 0.15) * W))
        else:
            lay = _underline(col, int(s.get("w", 0.25) * W))
        _paste_center(canvas, lay, s["x"] * W, s["y"] * H)
    for s in (settings.get("stickers") or [])[:8]:
        if not isinstance(s, dict):
            continue
        x, y = float(s.get("x", 0.5)) * W, float(s.get("y", 0.5)) * H
        w = int(float(s.get("w", 0.15)) * W)
        rot = float(s.get("rot", 0))
        if s.get("shape") in SHAPES:
            col = _rgb(s.get("color") or "accent", accent)
            lay = _arrow(col, w, rot) if s["shape"] == "arrow" else _ring(col, w) if s["shape"] == "circle" else _underline(col, w)
        else:
            p = (paths.get("stickers") or {}).get(s.get("id"))
            lay = _sticker(Path(p), w, rot) if p else None
        if lay is not None:
            _paste_center(canvas, lay, x, y)
    # labels (before/after, BREAKING, ?)
    for lab in (t.get("labels") or []):
        bgc = _rgb(lab["bg"], accent) if lab.get("bg") else None
        lay = _label(str(lab["text"]), px=int(lab.get("size", 0.06) * H), fam=lab.get("font") or "Mukta",
                     color=_rgb(lab.get("color") or "#FFFFFF", accent), bg=bgc, rotate=float(lab.get("rotate", 0)))
        _paste_center(canvas, lay, lab["x"] * W, lab["y"] * H)
    # number badge
    text = settings.get("text") or ""
    badge_txt = str(settings.get("badge") or "").strip() or (leading_number(text) if t.get("badge") else "")
    if t.get("badge") and badge_txt:
        bd = t["badge"]
        r = int(bd.get("r", 0.14) * H)
        cx, cy = bd["x"] * W, bd["y"] * H
        lay = Image.new("RGBA", (r * 2 + 20, r * 2 + 20), (0, 0, 0, 0))
        dd = ImageDraw.Draw(lay)
        dd.ellipse((4, 8, r * 2 + 12, r * 2 + 16), fill=(0, 0, 0, 120))
        dd.ellipse((0, 0, r * 2 + 8, r * 2 + 8), fill=(255, 255, 255, 255))
        dd.ellipse((int(r * 0.07) + 2, int(r * 0.07) + 2, r * 2 + 6 - int(r * 0.07), r * 2 + 6 - int(r * 0.07)),
                   fill=(*_rgb(bd.get("color") or "accent", accent), 255))
        fpx = int(r * (1.25 if len(badge_txt) <= 1 else 1.0 if len(badge_txt) == 2 else 0.75))
        bf = font("Poppins", fpx)
        dd.text((r + 4, r + 4), badge_txt, font=bf, fill=(*_rgb(bd.get("text_color") or "#111111", accent), 255), anchor="mm")
        _paste_center(canvas, lay.rotate(-6, expand=True, resample=Image.BICUBIC), cx, cy)
    # text
    tx = t.get("text") or {}
    lines = parse_text(text, strip_number=bool(tx.get("strip_number") and badge_txt), upper=bool(settings.get("upper")))
    tinfo = {"px": 0, "regions": [], "box": [0, 0, 0, 0], "style": tx.get("style"), "stroke": 0, "fill": (255, 255, 255)}
    if lines:
        tinfo = draw_text(canvas, tx, lines, accent)
    # logo
    if settings.get("logo") and paths.get("logo"):
        lw = int(W * (0.11 if t["size"] == "yt" else 0.16))
        lay = _sticker(Path(paths["logo"]), lw)
        if lay is not None:
            pos = settings.get("logo_pos") or "tr"
            m = int(0.025 * W)
            x = m if pos[1] == "l" else W - m - lay.width
            y = m if pos[0] == "t" else H - m - lay.height
            canvas.alpha_composite(lay, (max(0, x), max(0, y)))
    if t.get("border"):
        bw = max(2, int(float(t["border"].get("width", 0.01)) * W))
        ImageDraw.Draw(canvas).rectangle((bw // 2, bw // 2, W - 1 - bw // 2, H - 1 - bw // 2),
                                         outline=(*_rgb(t["border"].get("color"), accent), 255), width=bw)
    out = canvas.convert("RGB")
    info = {"template": t["id"], "size": t["size"], "width": W, "height": H, "font_px": tinfo["px"], "style": tinfo["style"],
            "lines": len(lines), "words": sum(len(x) for x in lines), "cutout": bool(use_alpha is not None and not photo_mode),
            "text_box": tinfo["box"], "contrast": _text_contrast(out, tinfo)}
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
    size = settings.get("size") or "yt"
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
    if settings.get("size") == "yt" and not settings.get("cutout", True) and (settings.get("bg") or {}).get("type") in ("solid", "gradient"):
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
