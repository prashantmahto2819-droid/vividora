"""2D vector environments for the Scene builder: classroom, office, clinic, shop… drawn as SVG at a
1920×1080 base, with a prop library (tables, chairs, computers, vehicles, shelves, signs), camera
framing (wide / medium / close = viewBox), lighting (day / evening / night tint) and character
slots (where a person stands, how big by depth).

scene_svg(spec, w, h) renders a scene; spec = {env, framing, light, props: [{id, x, y, s}],
chars: [{params, x, y, s, flip, pose}], title?}. x/y are fractions of the base frame (y = feet).
"""

from __future__ import annotations

from . import rig

BW, BH = 1920, 1080
FLOOR_Y = 900
PROP_K = 2.0      # props are drawn ~200–400 px wide; people stand ~650 px tall in the base frame
CHAR_K = 0.70


def _f(v: float) -> str:
    return f"{v:.1f}"


# ------------------------------------------------------------------ props (origin: bottom-centre)
def _rect(x, y, w, h, fill, rx=0, extra=""):
    return f'<rect x="{_f(x)}" y="{_f(y)}" width="{_f(w)}" height="{_f(h)}" rx="{rx}" fill="{fill}" {extra}/>'


def prop_svg(pid: str) -> str:
    """Each prop is drawn around (0,0) = bottom centre, about 200–400 px wide at scale 1."""
    P = {
        "table": _rect(-130, -90, 260, 14, "#8D6E63", 3) + _rect(-118, -76, 14, 76, "#6D4C41") + _rect(104, -76, 14, 76, "#6D4C41"),
        "desk": _rect(-150, -100, 300, 16, "#5D4037", 3) + _rect(-140, -84, 70, 84, "#4E342E") + _rect(70, -84, 70, 84, "#4E342E") + _rect(-130, -76, 50, 12, "#3E2723", 2),
        "chair": _rect(-40, -150, 80, 70, "#546E7A", 8) + _rect(-44, -82, 88, 14, "#455A64", 4) + _rect(-36, -68, 8, 68, "#37474F") + _rect(28, -68, 8, 68, "#37474F"),
        "computer": _rect(-60, -110, 120, 76, "#263238", 6) + _rect(-54, -104, 108, 64, "#B3E5FC") + _rect(-8, -34, 16, 20, "#37474F") + _rect(-40, -14, 80, 8, "#455A64", 3) + _rect(-70, -10, 50, 10, "#CFD8DC", 3),
        "laptop": _rect(-50, -70, 100, 64, "#37474F", 4) + _rect(-45, -65, 90, 52, "#B3E5FC") + _rect(-56, -6, 112, 6, "#546E7A", 2),
        "board": _rect(-260, -340, 520, 300, "#2E6B47", 6, 'stroke="#8D6E63" stroke-width="10"') + f'<text x="0" y="-220" font-size="44" fill="#F1F8E9" text-anchor="middle" font-family="sans-serif">a + b = c</text><path d="M-200 -170 h240 M-200 -130 h180" stroke="#F1F8E9" stroke-width="5"/>',
        "whiteboard": _rect(-260, -340, 520, 300, "#FAFAFA", 6, 'stroke="#90A4AE" stroke-width="10"') + '<path d="M-200 -250 h200 M-200 -200 h300 M-200 -150 h140" stroke="#1E88E5" stroke-width="6"/>',
        "shelf": _rect(-140, -300, 280, 300, "#A1887F", 4) + "".join(_rect(-130, -290 + i * 72, 260, 8, "#6D4C41") for i in range(4))
                 + "".join(_rect(-120 + j * 42, -282 + i * 72, 32, 54, c, 4) for i in range(4) for j, c in enumerate(["#E53935", "#FDD835", "#43A047", "#1E88E5", "#8E24AA", "#FB8C00"])),
        "counter": _rect(-220, -120, 440, 120, "#8D6E63", 6) + _rect(-230, -130, 460, 16, "#6D4C41", 4) + _rect(-200, -100, 400, 70, "#A1887F", 4),
        "bed": _rect(-200, -90, 400, 60, "#90A4AE", 10) + _rect(-190, -120, 380, 40, "#FFFFFF", 8) + _rect(-180, -140, 90, 30, "#ECEFF1", 8) + _rect(-205, -200, 20, 200, "#607D8B") + _rect(185, -200, 20, 200, "#607D8B"),
        "plant": _rect(-30, -60, 60, 60, "#A1887F", 6) + '<path d="M0 -60 q-40 -60 -20 -120 M0 -60 q40 -60 20 -120 M0 -60 q0 -80 0 -140 M0 -70 q-60 -20 -70 -80 M0 -70 q60 -20 70 -80" stroke="#43A047" stroke-width="12" stroke-linecap="round" fill="none"/>',
        "window": _rect(-160, -360, 320, 240, "#81D4FA", 4, 'stroke="#ECEFF1" stroke-width="14"') + '<path d="M0 -360 v240 M-160 -240 h320" stroke="#ECEFF1" stroke-width="10"/><circle cx="90" cy="-300" r="26" fill="#FFF59D"/>',
        "door": _rect(-70, -300, 140, 300, "#8D6E63", 4, 'stroke="#5D4037" stroke-width="8"') + '<circle cx="48" cy="-150" r="8" fill="#FFD54F"/>',
        "clock": '<circle cx="0" cy="-60" r="50" fill="#FFFFFF" stroke="#37474F" stroke-width="6"/><path d="M0 -60 v-34 M0 -60 h24" stroke="#37474F" stroke-width="5" stroke-linecap="round"/>',
        "car": '<path d="M-220 -40 h440 v-70 l-90 -70 h-180 l-90 70z" fill="#E53935"/>' + _rect(-150, -170, 110, 60, "#B3E5FC", 6) + _rect(-20, -170, 120, 60, "#B3E5FC", 6)
               + '<circle cx="-130" cy="-30" r="38" fill="#212121"/><circle cx="130" cy="-30" r="38" fill="#212121"/><circle cx="-130" cy="-30" r="16" fill="#9E9E9E"/><circle cx="130" cy="-30" r="16" fill="#9E9E9E"/>',
        "scooter": '<path d="M-120 -30 q-20 -80 30 -90 h60 l20 -90 h40" stroke="#1E88E5" stroke-width="14" fill="none" stroke-linecap="round"/><circle cx="-120" cy="-30" r="30" fill="#212121"/><circle cx="110" cy="-30" r="30" fill="#212121"/>' + _rect(-40, -140, 100, 40, "#1E88E5", 10),
        "tree": _rect(-18, -140, 36, 140, "#6D4C41", 6) + '<circle cx="0" cy="-200" r="90" fill="#43A047"/><circle cx="-60" cy="-160" r="60" fill="#388E3C"/><circle cx="60" cy="-160" r="60" fill="#388E3C"/>',
        "bench": _rect(-120, -70, 240, 16, "#8D6E63", 4) + _rect(-120, -120, 240, 14, "#8D6E63", 4) + _rect(-110, -54, 12, 54, "#5D4037") + _rect(98, -54, 12, 54, "#5D4037"),
        "lamp": _rect(-8, -300, 16, 300, "#37474F") + '<path d="M-60 -300 h120 l-20 -60 h-80z" fill="#FFD54F"/>',
        "treadmill": _rect(-150, -30, 300, 30, "#37474F", 8) + _rect(-140, -20, 280, 10, "#212121") + _rect(120, -170, 20, 150, "#546E7A") + _rect(60, -180, 120, 20, "#546E7A", 6),
        "rack": _rect(-150, -140, 300, 12, "#616161") + _rect(-150, -80, 300, 12, "#616161") + _rect(-146, -140, 10, 140, "#424242") + _rect(136, -140, 10, 140, "#424242")
                + "".join(f'<rect x="{-120 + i * 50}" y="{-172 + (i % 2) * 60}" width="34" height="30" rx="6" fill="#212121"/>' for i in range(5)),
        "mirror": _rect(-110, -330, 220, 290, "#B3E5FC", 8, 'stroke="#FFD54F" stroke-width="10"') + '<path d="M-80 -300 l-20 60" stroke="#FFFFFF" stroke-width="8" opacity=".6"/>',
        "salonchair": _rect(-50, -170, 100, 90, "#212121", 10) + _rect(-56, -84, 112, 14, "#424242", 4) + _rect(-8, -70, 16, 60, "#9E9E9E") + _rect(-50, -14, 100, 14, "#9E9E9E", 6),
        "sign": _rect(-200, -420, 400, 110, "#F4B400", 10) + '<text x="0" y="-345" font-size="60" font-weight="700" fill="#212121" text-anchor="middle" font-family="sans-serif">दुकान</text>' + _rect(-10, -310, 20, 310, "#616161"),
        "fruitstand": _rect(-180, -110, 360, 110, "#8D6E63", 6) + "".join(f'<circle cx="{-140 + i * 36}" cy="{-130 - (i % 3) * 10}" r="18" fill="{c}"/>' for i, c in enumerate(["#E53935", "#FB8C00", "#FDD835", "#43A047", "#E53935", "#FB8C00", "#FDD835", "#43A047"])),
        "crane": _rect(-14, -600, 28, 600, "#FFB300") + _rect(-320, -600, 640, 20, "#FFB300") + '<path d="M-320 -580 l320 -120 l320 120" stroke="#FFB300" stroke-width="8" fill="none"/>' + _rect(220, -580, 6, 200, "#616161") + _rect(190, -380, 66, 40, "#616161", 4),
        "building_frame": "".join(_rect(-300 + j * 150, -500 + i * 120, 140, 110, "none", 0, 'stroke="#90A4AE" stroke-width="10"') for i in range(4) for j in range(4)),
        "stage_light": "".join(f'<path d="M{-400 + i * 200} -700 l-140 700 h280z" fill="#FFF176" opacity=".18"/><circle cx="{-400 + i * 200}" cy="-700" r="24" fill="#FFEE58"/>' for i in range(5)),
        "garland": '<path d="M-500 -620 q500 180 1000 0" stroke="#F57C00" stroke-width="10" fill="none"/>' + "".join(f'<circle cx="{-480 + i * 80}" cy="{-610 + (1 - abs(i - 6) / 6) * 85}" r="16" fill="{c}"/>' for i, c in enumerate(["#FFD54F", "#E53935", "#FFD54F", "#E53935", "#FFD54F", "#E53935", "#FFD54F", "#E53935", "#FFD54F", "#E53935", "#FFD54F", "#E53935", "#FFD54F"])),
        "cabinet": _rect(-90, -260, 180, 260, "#ECEFF1", 6, 'stroke="#B0BEC5" stroke-width="6"') + _rect(-80, -250, 160, 70, "#B3E5FC") + "".join(f'<rect x="{-70 + i * 40}" y="-240" width="20" height="50" rx="4" fill="{c}"/>' for i, c in enumerate(["#E53935", "#43A047", "#1E88E5", "#FB8C00"])),
        "microscope": _rect(-40, -20, 80, 20, "#37474F", 4) + '<path d="M0 -20 v-110 M0 -130 l40 -40" stroke="#37474F" stroke-width="16" stroke-linecap="round"/><circle cx="46" cy="-176" r="14" fill="#546E7A"/>',
        "stove": _rect(-120, -120, 240, 120, "#B0BEC5", 6) + '<circle cx="-60" cy="-120" r="30" fill="#37474F"/><circle cx="60" cy="-120" r="30" fill="#37474F"/>' + _rect(-80, -200, 160, 60, "#78909C", 6),
        "fridge": _rect(-70, -320, 140, 320, "#ECEFF1", 8, 'stroke="#B0BEC5" stroke-width="6"') + '<path d="M-70 -200 h140" stroke="#B0BEC5" stroke-width="6"/>' + _rect(40, -260, 10, 40, "#90A4AE", 3),
        "sofa": _rect(-200, -110, 400, 80, "#7E57C2", 12) + _rect(-210, -150, 420, 60, "#9575CD", 14) + _rect(-215, -120, 40, 90, "#5E35B1", 10) + _rect(175, -120, 40, 90, "#5E35B1", 10),
        "tv": _rect(-170, -330, 340, 200, "#212121", 8) + _rect(-160, -320, 320, 180, "#1565C0") + _rect(-40, -130, 80, 14, "#424242", 4),
    }
    return P.get(pid, "")


PROPS = {"table": "मेज़", "desk": "डेस्क", "chair": "कुर्सी", "computer": "कंप्यूटर", "laptop": "लैपटॉप", "board": "ग्रीनबोर्ड", "whiteboard": "व्हाइटबोर्ड",
         "shelf": "शेल्फ़ (सामान)", "counter": "काउंटर", "bed": "बेड", "plant": "पौधा", "window": "खिड़की", "door": "दरवाज़ा", "clock": "घड़ी",
         "car": "कार", "scooter": "स्कूटर", "tree": "पेड़", "bench": "बेंच", "lamp": "लैंप", "treadmill": "ट्रेडमिल", "rack": "डम्बल रैक", "mirror": "आईना",
         "salonchair": "सैलून कुर्सी", "sign": "साइनबोर्ड", "fruitstand": "फल-सब्ज़ी", "crane": "क्रेन", "building_frame": "इमारत का ढाँचा",
         "stage_light": "स्टेज लाइट", "garland": "फूल-माला", "cabinet": "दवा कैबिनेट", "microscope": "माइक्रोस्कोप", "stove": "चूल्हा", "fridge": "फ़्रिज",
         "sofa": "सोफ़ा", "tv": "टीवी"}

# environment → background + default props + character slots
ENVS: dict[str, dict] = {
    "classroom": {"label": "क्लासरूम (ग्रीनबोर्ड)", "wall": "#FFF3E0", "floor": "#D7CCC8", "props": [("board", .5, .78, 1.0), ("desk", .22, .98, .9), ("chair", .22, .98, .8), ("window", .9, .7, .7), ("clock", .1, .3, .7)],
                  "slots": [(.68, .98, 1.0), (.3, .98, .9)]},
    "office": {"label": "ऑफ़िस", "wall": "#ECEFF1", "floor": "#B0BEC5", "props": [("window", .25, .68, .9), ("window", .75, .68, .9), ("desk", .5, .99, 1.0), ("computer", .5, .91, .9), ("chair", .5, .99, .9), ("plant", .92, .99, 1.0)],
               "slots": [(.3, .99, 1.0), (.72, .99, 1.0)]},
    "meeting": {"label": "मीटिंग रूम", "wall": "#E8EAF6", "floor": "#9FA8DA", "props": [("whiteboard", .5, .75, .9), ("table", .5, .99, 1.4), ("chair", .25, .99, .9), ("chair", .75, .99, .9), ("laptop", .5, .9, .8)],
                "slots": [(.2, .99, .95), (.8, .99, .95), (.5, .99, .9)]},
    "clinic": {"label": "क्लिनिक", "wall": "#E0F7FA", "floor": "#B2EBF2", "props": [("cabinet", .12, .99, 1.0), ("bed", .72, .99, 1.1), ("desk", .35, .99, .8), ("clock", .5, .3, .7), ("plant", .95, .99, .8)],
               "slots": [(.3, .99, 1.0), (.62, .99, .95)]},
    "hospital": {"label": "अस्पताल वार्ड", "wall": "#F1F8E9", "floor": "#C5E1A5", "props": [("bed", .3, .99, 1.1), ("bed", .75, .99, 1.1), ("window", .5, .62, .9), ("cabinet", .05, .99, .9)],
                 "slots": [(.52, .99, 1.0), (.1, .99, .9)]},
    "lab": {"label": "लैब", "wall": "#E3F2FD", "floor": "#90CAF9", "props": [("shelf", .12, .99, 1.0), ("table", .5, .99, 1.2), ("microscope", .5, .91, .9), ("cabinet", .9, .99, .9)],
            "slots": [(.3, .99, 1.0), (.7, .99, 1.0)]},
    "home": {"label": "घर (लिविंग रूम)", "wall": "#FFF8E1", "floor": "#BCAAA4", "props": [("window", .22, .66, .9), ("tv", .5, .76, 1.0), ("sofa", .5, .99, 1.1), ("plant", .9, .99, 1.0), ("lamp", .1, .99, .9)],
             "slots": [(.25, .99, 1.0), (.75, .99, 1.0)]},
    "kitchen": {"label": "रसोई", "wall": "#FBE9E7", "floor": "#D7CCC8", "props": [("fridge", .12, .99, 1.0), ("stove", .5, .99, 1.1), ("counter", .5, .99, 1.0), ("window", .78, .66, .8), ("shelf", .92, .99, .8)],
                "slots": [(.3, .99, 1.0), (.72, .99, 1.0)]},
    "grocery": {"label": "किराना दुकान", "wall": "#FFFDE7", "floor": "#E0E0E0", "props": [("sign", .5, .62, .5), ("shelf", .15, .99, 1.1), ("shelf", .85, .99, 1.1), ("counter", .5, .99, 1.0), ("fruitstand", .5, .9, .9)],
                "slots": [(.5, .99, .95), (.28, .99, 1.0)]},
    "showroom": {"label": "शोरूम", "wall": "#F5F5F5", "floor": "#CFD8DC", "props": [("window", .2, .62, 1.0), ("window", .8, .62, 1.0), ("car", .62, .99, 1.1), ("plant", .05, .99, 1.0), ("sign", .25, .62, .45)],
                 "slots": [(.25, .99, 1.0), (.9, .99, .95)]},
    "gym": {"label": "जिम", "wall": "#37474F", "floor": "#263238", "props": [("mirror", .5, .72, 1.1), ("rack", .15, .99, 1.0), ("treadmill", .82, .99, 1.0), ("clock", .9, .3, .7)],
            "slots": [(.45, .99, 1.0), (.62, .99, .95)]},
    "salon": {"label": "सैलून", "wall": "#FCE4EC", "floor": "#F8BBD0", "props": [("mirror", .3, .72, 1.0), ("mirror", .7, .72, 1.0), ("salonchair", .3, .99, 1.0), ("salonchair", .7, .99, 1.0), ("shelf", .95, .99, .8)],
              "slots": [(.5, .99, 1.0), (.1, .99, .95)]},
    "park": {"label": "पार्क / सड़क", "sky": True, "wall": "#B3E5FC", "floor": "#8BC34A", "props": [("tree", .12, .9, 1.2), ("tree", .88, .9, 1.0), ("bench", .5, .99, 1.0), ("lamp", .7, .99, 1.0), ("scooter", .3, .99, .8)],
             "slots": [(.5, .99, 1.0), (.8, .99, .95)]},
    "road": {"label": "सड़क", "sky": True, "wall": "#B3E5FC", "floor": "#616161", "road": True, "props": [("tree", .08, .72, .9), ("car", .7, .99, 1.1), ("sign", .2, .66, .45), ("lamp", .9, .72, 1.0)],
             "slots": [(.3, .99, 1.0), (.5, .99, 1.0)]},
    "construction": {"label": "कंस्ट्रक्शन साइट", "sky": True, "wall": "#FFE0B2", "floor": "#A1887F", "props": [("building_frame", .3, .9, 1.0), ("crane", .78, .9, 1.0), ("sign", .1, .68, .4)],
                     "slots": [(.55, .99, 1.0), (.85, .99, .95)]},
    "festival": {"label": "त्योहार / स्टेज", "wall": "#4A148C", "floor": "#6A1B9A", "props": [("stage_light", .5, .98, 1.0), ("garland", .5, .95, 1.0), ("plant", .05, .99, 1.0), ("plant", .95, .99, 1.0)],
                 "slots": [(.35, .99, 1.0), (.65, .99, 1.0), (.5, .99, .95)]},
    "studio": {"label": "स्टूडियो (सादा)", "wall": "#1E293B", "floor": "#0F172A", "props": [("stage_light", .5, .98, .8)], "slots": [(.5, .99, 1.0), (.25, .99, 1.0), (.75, .99, 1.0)]},
}
FRAMING = {"wide": (0, 0, BW, BH), "medium": (BW * .18, BH * .12, BW * .64, BH * .64 * 1.0), "close": (BW * .3, BH * .18, BW * .4, BH * .4)}
LIGHT = {"day": None, "evening": ("#FF8F00", .22), "night": ("#0D1B4B", .45), "warm": ("#FFCC80", .12), "cool": ("#90CAF9", .15)}


def _background(env: dict) -> str:
    s = ""
    if env.get("sky"):
        s += f'<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#64B5F6"/><stop offset="1" stop-color="{env["wall"]}"/></linearGradient></defs>'
        s += f'<rect width="{BW}" height="{FLOOR_Y}" fill="url(#sky)"/><circle cx="1640" cy="160" r="70" fill="#FFF59D"/>'
        s += '<ellipse cx="300" cy="220" rx="140" ry="50" fill="#FFFFFF" opacity=".9"/><ellipse cx="420" cy="200" rx="110" ry="40" fill="#FFFFFF" opacity=".9"/>'
        s += '<ellipse cx="1200" cy="300" rx="150" ry="50" fill="#FFFFFF" opacity=".8"/>'
        if env.get("road"):
            s += f'<rect y="{FLOOR_Y - 60}" width="{BW}" height="{BH - FLOOR_Y + 60}" fill="{env["floor"]}"/><path d="M0 {FLOOR_Y + 60} H{BW}" stroke="#FFFFFF" stroke-width="10" stroke-dasharray="80 60"/>'
            s += f'<rect y="{FLOOR_Y - 90}" width="{BW}" height="30" fill="#9E9E9E"/>'
        else:
            s += f'<rect y="{FLOOR_Y - 40}" width="{BW}" height="{BH - FLOOR_Y + 40}" fill="{env["floor"]}"/>'
    else:
        s += f'<rect width="{BW}" height="{BH}" fill="{env["wall"]}"/>'
        s += f'<rect width="{BW}" height="{BH}" fill="none"/>'
        s += f'<rect y="{FLOOR_Y}" width="{BW}" height="{BH - FLOOR_Y}" fill="{env["floor"]}"/>'
        s += f'<rect y="{FLOOR_Y - 14}" width="{BW}" height="14" fill="{_darker(env["wall"])}"/>'
        # floor planks
        s += "".join(f'<path d="M{i * 240} {FLOOR_Y} L{i * 240 - 120} {BH}" stroke="{_darker(env["floor"])}" stroke-width="3"/>' for i in range(10))
    return s


def viewbox(spec: dict, w: int, h: int) -> tuple[float, float, float, float]:
    """The camera: framing viewBox widened/narrowed to the output aspect."""
    vx, vy, vw, vh = FRAMING.get(spec.get("framing") or "wide", FRAMING["wide"])
    want = w / h
    if abs(vw / vh - want) > 1e-3:
        if want > vw / vh:
            nw = vh * want
            vx -= (nw - vw) / 2
            vw = nw
        else:
            nh = vw / want
            vy -= (nh - vh) / 2
            vh = nh
    return vx, vy, vw, vh


def char_xy(ch: dict, spec: dict, w: int, h: int) -> tuple[float, float]:
    """Where a character's feet go in base coordinates. Wide: x/y are fractions of the base frame.
    Medium/close (a zoomed camera): x is a fraction of the visible frame and the feet sit just below
    its bottom edge, so people show waist-up instead of standing outside the picture."""
    x, y = float(ch.get("x", .5)), float(ch.get("y", .99))
    if (spec.get("framing") or "wide") == "wide":
        return x * BW, y * BH
    vx, vy, vw, vh = viewbox(spec, w, h)
    return vx + x * vw, vy + vh * (1.0 + 0.22 * (y - 0.6) / 0.4)


def _darker(hex_: str, f: float = 0.85) -> str:
    r, g, b = int(hex_[1:3], 16), int(hex_[3:5], 16), int(hex_[5:7], 16)
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(c * f))) for c in (r, g, b))


def scene_svg(spec: dict, w: int = BW, h: int = BH, with_chars: bool = True) -> str:
    env = ENVS.get(spec.get("env") or "studio", ENVS["studio"])
    g = [_background(env)]
    props = spec.get("props")
    if props is None:
        props = [{"id": p[0], "x": p[1], "y": p[2], "s": p[3]} for p in env["props"]]
    items = []
    for pr in props:
        items.append(("prop", float(pr.get("y", .99)), pr))
    if with_chars:
        for i, ch in enumerate(spec.get("chars") or []):
            items.append(("char", float(ch.get("y", .99)), {**ch, "_i": i}))
    # painter's order: things higher on the floor (smaller y) are further away → drawn first
    items.sort(key=lambda it: it[1])
    for kind, _, it in items:
        x, y = float(it.get("x", .5)) * BW, float(it.get("y", .99)) * BH
        if kind == "char":
            x, y = char_xy(it, spec, w, h)
        s = float(it.get("s", 1.0))
        if kind == "prop":
            g.append(f'<g transform="translate({_f(x)},{_f(y)}) scale({_f(s * PROP_K)})">{prop_svg(it["id"])}</g>')
        else:
            depth = 0.55 + 0.45 * float(it.get("y", .99))  # further back = smaller
            cs = s * depth * (BH / rig.VIEW_H) * CHAR_K
            pose = dict(it.get("pose") or {})
            if it.get("flip"):
                pose["flip"] = 1
            body = rig.svg(it["params"], pose, bare=True)
            idx = it.get("_i")
            tag = f' data-char="{int(idx)}" style="cursor:move"' if idx is not None else ""
            g.append(f'<g{tag} transform="translate({_f(x - rig.VIEW_W / 2 * cs)},{_f(y - rig.GROUND * cs)}) scale({_f(cs)})">{body}</g>')
    light = LIGHT.get(spec.get("light") or "day")
    if light:
        g.append(f'<rect width="{BW}" height="{BH}" fill="{light[0]}" opacity="{light[1]}"/>')
    if spec.get("title"):
        g.append(f'<text x="{BW / 2}" y="120" font-size="72" font-weight="700" fill="#FFFFFF" stroke="#000000" stroke-width="6" paint-order="stroke" text-anchor="middle" font-family="sans-serif">{_esc(spec["title"])}</text>')
    vx, vy, vw, vh = viewbox(spec, w, h)
    inner = "".join(g)
    # outside the base frame (tall outputs) the wall/floor colours continue
    bg = env["wall"] if not env.get("sky") else "#64B5F6"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="{_f(vx)} {_f(vy)} {_f(vw)} {_f(vh)}" preserveAspectRatio="none">'
            f'<rect x="{_f(vx)}" y="{_f(vy)}" width="{_f(vw)}" height="{_f(vh)}" fill="{bg}"/>'
            f'<rect x="{_f(vx)}" y="{FLOOR_Y}" width="{_f(vw)}" height="{_f(max(0, vy + vh - FLOOR_Y))}" fill="{env["floor"]}"/>{inner}</svg>')


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def env_list() -> list[dict]:
    return [{"id": k, "label": v["label"], "slots": v["slots"], "props": [{"id": p[0], "x": p[1], "y": p[2], "s": p[3]} for p in v["props"]]}
            for k, v in ENVS.items()]


def char_place(spec_char: dict, w: int, h: int, spec: dict) -> dict:
    """Where a character of a scene lands in the OUTPUT frame as an overlay: centre x/y fractions and
    width fraction (fit:"free" items of the editor), honouring the framing viewBox."""
    vx, vy, vw, vh = viewbox(spec, w, h)
    x, y = char_xy(spec_char, spec, w, h)
    s = float(spec_char.get("s", 1.0))
    depth = 0.55 + 0.45 * float(spec_char.get("y", .99))
    cs = s * depth * (BH / rig.VIEW_H) * CHAR_K
    cw, chh = rig.VIEW_W * cs, rig.VIEW_H * cs
    cx, cy = x, y - chh / 2
    return {"x": round((cx - vx) / vw, 4), "y": round((cy - vy) / vh, 4), "scale": round(cw / vw, 4), "h_frac": round(chh / vh, 4)}
