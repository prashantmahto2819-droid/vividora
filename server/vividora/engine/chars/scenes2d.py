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
        # --- new props for expanded scenes ---
        "temple_arch": '<path d="M-180 0 v-320 q0 -60 30 -90 q30 -30 60 -30 h60 q30 0 60 30 q30 30 30 90 v320" fill="#D4A017" stroke="#B8860B" stroke-width="8"/>'
                       + '<path d="M-140 -340 q140 -90 280 0" fill="#D4A017" stroke="#B8860B" stroke-width="6"/>'
                       + '<circle cx="0" cy="-380" r="30" fill="#FF6F00"/>'
                       + '<path d="M-10 -420 l10 -30 l10 30" fill="#FF6F00"/>',
        "diya": '<ellipse cx="0" cy="-14" rx="24" ry="10" fill="#D4A017"/><ellipse cx="0" cy="-20" rx="18" ry="6" fill="#FFD54F"/>'
                + '<path d="M0 -20 q-4 -16 0 -32 q4 16 0 32" fill="#FF6F00" opacity=".9"/><ellipse cx="0" cy="-50" rx="6" ry="10" fill="#FFAB00" opacity=".8"/>',
        "bell": '<path d="M0 -100 v-20" stroke="#B8860B" stroke-width="6"/><path d="M-40 -30 q0 -70 40 -70 q40 0 40 70z" fill="#D4A017" stroke="#B8860B" stroke-width="4"/>'
                + '<circle cx="0" cy="-26" r="8" fill="#B8860B"/>',
        "market_stall": _rect(-200, -220, 400, 220, "#8D6E63", 6) + _rect(-210, -230, 420, 18, "#6D4C41", 4)
                        + '<path d="M-220 -230 l-30 -60 h500 l-30 60" fill="#E53935"/>'
                        + "".join(f'<rect x="{-180 + i * 50}" y="-200" width="40" height="60" rx="4" fill="{c}"/>' for i, c in enumerate(["#FF7043", "#66BB6A", "#42A5F5", "#FFA726", "#AB47BC", "#EF5350", "#26C6DA"])),
        "awning": '<path d="M-300 -300 h600 l40 80 h-680z" fill="#E53935"/>' + "".join(f'<path d="M{-300 + i * 100} -300 q50 40 100 0" fill="#C62828"/>' for i in range(6)),
        "chai_kettle": '<ellipse cx="0" cy="-30" rx="50" ry="30" fill="#78909C"/><path d="M-50 -30 q-20 -10 -20 -30 q0 -14 14 -14" stroke="#546E7A" stroke-width="6" fill="none"/>'
                       + '<path d="M-10 -60 q-6 -30 0 -50 M10 -58 q6 -24 0 -44" stroke="#B0BEC5" stroke-width="4" fill="none" opacity=".6"/>'
                       + "".join(f'<rect x="{-40 + i * 22}" y="-8" width="16" height="20" rx="4" fill="{c}"/>' for i, c in enumerate(["#ECEFF1", "#CFD8DC", "#ECEFF1", "#CFD8DC"])),
        "chai_bench": _rect(-100, -50, 200, 10, "#8D6E63") + _rect(-90, -40, 8, 40, "#6D4C41") + _rect(82, -40, 8, 40, "#6D4C41"),
        "train_platform": _rect(-400, -20, 800, 20, "#9E9E9E", 4) + '<path d="M-400 -20 h800" stroke="#FFC107" stroke-width="8"/>'
                          + _rect(-400, 0, 800, 60, "#757575")
                          + '<text x="0" y="-40" font-size="36" fill="#1A237E" text-anchor="middle" font-family="sans-serif">प्लेटफ़ॉर्म 1</text>',
        "train_roof": '<rect x="-500" y="-500" width="1000" height="120" fill="#BDBDBD" rx="20"/>'
                      + "".join(f'<rect x="{-400 + i * 200}" y="-380" width="160" height="100" rx="6" fill="#E3F2FD" stroke="#90A4AE" stroke-width="4"/>' for i in range(4))
                      + '<rect x="-500" y="-380" width="1000" height="12" fill="#9E9E9E"/>',
        "auto_rickshaw": '<path d="M-120 -40 h240 v-120 q0 -40 -40 -40 h-160 q-40 0 -40 40z" fill="#2E7D32"/>'
                         + '<rect x="-100" y="-190" width="200" height="70" rx="6" fill="#E8F5E9"/>'
                         + '<circle cx="-100" cy="-30" r="30" fill="#212121"/><circle cx="100" cy="-30" r="30" fill="#212121"/>'
                         + '<circle cx="-100" cy="-30" r="12" fill="#9E9E9E"/><circle cx="100" cy="-30" r="12" fill="#9E9E9E"/>'
                         + '<path d="M-120 -190 l-30 -30 h280 l-30 30" fill="#1B5E20"/>',
        "mandap": '<rect x="-220" y="-400" width="440" height="400" fill="none"/>'
                  + "".join(f'<rect x="{x}" y="-400" width="20" height="400" fill="#D4A017"/>' for x in [-220, 200])
                  + '<rect x="-240" y="-420" width="480" height="30" fill="#D4A017" rx="4"/>'
                  + '<path d="M-240 -420 q240 -80 480 0" fill="#C62828"/>'
                  + "".join(f'<circle cx="{-220 + i * 55}" cy="{-415 - (1 - abs(i - 4) / 4) * 40}" r="12" fill="{c}"/>' for i, c in enumerate(["#FF8F00", "#E53935", "#FF8F00", "#E53935", "#FF8F00", "#E53935", "#FF8F00", "#E53935", "#FF8F00"])),
        "fire_pit": '<ellipse cx="0" cy="-10" rx="60" ry="20" fill="#5D4037" stroke="#3E2723" stroke-width="4"/>'
                    + '<path d="M-20 -10 q0 -50 20 -60 q20 10 20 60" fill="#FF6F00" opacity=".85"/>'
                    + '<path d="M-8 -10 q0 -30 8 -40 q8 10 8 40" fill="#FFAB00" opacity=".9"/>',
        "wheat_field": "".join(f'<path d="M{-500 + i * 30} 0 v-{120 + (i * 7) % 40}" stroke="#8BC34A" stroke-width="4"/>'
                               f'<ellipse cx="{-500 + i * 30}" cy="{-120 - (i * 7) % 40}" rx="6" ry="14" fill="#CDDC39"/>' for i in range(34)),
        "tractor": '<rect x="-140" y="-100" width="200" height="70" rx="8" fill="#E53935"/>'
                   + '<rect x="-160" y="-130" width="80" height="40" rx="6" fill="#B3E5FC"/>'
                   + '<circle cx="-120" cy="-20" r="40" fill="#212121"/><circle cx="80" cy="-20" r="50" fill="#212121"/>'
                   + '<circle cx="-120" cy="-20" r="16" fill="#9E9E9E"/><circle cx="80" cy="-20" r="22" fill="#9E9E9E"/>',
        "news_desk": _rect(-280, -100, 560, 100, "#1A237E", 8) + _rect(-260, -110, 520, 16, "#283593", 4)
                     + '<text x="0" y="-130" font-size="48" font-weight="700" fill="#FFFFFF" text-anchor="middle" font-family="sans-serif">BREAKING NEWS</text>'
                     + _rect(140, -90, 90, 60, "#B3E5FC", 4),
        "camera": _rect(-30, -120, 60, 80, "#37474F", 4) + '<circle cx="0" cy="-80" r="22" fill="#263238" stroke="#546E7A" stroke-width="4"/>'
                  + _rect(-6, -40, 12, 40, "#37474F") + _rect(-40, -10, 80, 10, "#546E7A", 4),
        "flag": _rect(-6, -300, 12, 300, "#616161") + '<rect x="6" y="-300" width="120" height="80" fill="none"/>'
                + '<rect x="6" y="-300" width="120" height="27" fill="#FF9933"/>'
                + '<rect x="6" y="-273" width="120" height="26" fill="#FFFFFF"/>'
                + '<rect x="6" y="-247" width="120" height="27" fill="#138808"/>'
                + '<circle cx="66" cy="-260" r="9" fill="#000080" stroke="#000080" stroke-width="1.5"/>',
        "podium": _rect(-100, -60, 200, 60, "#5D4037", 6) + _rect(-80, -100, 160, 40, "#8D6E63", 4)
                  + '<rect x="-4" y="-140" width="8" height="50" fill="#616161"/><circle cx="0" cy="-150" r="12" fill="#424242"/>',
        "judge_bench": _rect(-240, -180, 480, 180, "#5D4037", 6) + _rect(-250, -190, 500, 16, "#3E2723", 4)
                       + '<path d="M-40 -200 v-40 l40 -30 l40 30 v40" fill="#5D4037" stroke="#3E2723" stroke-width="4"/>',
        "gavel": '<path d="M-30 -20 l60 -40" stroke="#8D6E63" stroke-width="14" stroke-linecap="round"/>'
                 + '<rect x="20" y="-70" width="30" height="20" rx="4" fill="#6D4C41" transform="rotate(-34 35 -60)"/>',
        "barricade": _rect(-80, -80, 160, 10, "#FF6F00") + _rect(-80, -50, 160, 10, "#FFFFFF") + _rect(-80, -20, 160, 10, "#FF6F00")
                     + _rect(-70, -10, 8, 10, "#616161") + _rect(62, -10, 8, 10, "#616161"),
        "police_desk": _rect(-180, -100, 360, 100, "#455A64", 6) + _rect(-190, -110, 380, 16, "#37474F", 4)
                       + _rect(-160, -90, 80, 60, "#B3E5FC", 4)
                       + '<text x="80" y="-60" font-size="30" fill="#ECEFF1" text-anchor="middle" font-family="sans-serif">FIR</text>',
        "college_gate": '<rect x="-200" y="-350" width="20" height="350" fill="#795548"/><rect x="180" y="-350" width="20" height="350" fill="#795548"/>'
                        + '<rect x="-220" y="-370" width="440" height="30" fill="#795548" rx="4"/>'
                        + '<text x="0" y="-380" font-size="28" fill="#1A237E" text-anchor="middle" font-family="sans-serif">विद्यालय</text>',
        "village_hut": '<path d="M-160 -180 l160 -100 l160 100z" fill="#E65100"/>'
                       + _rect(-140, -180, 280, 180, "#FFCC80", 4)
                       + _rect(-40, -120, 80, 120, "#8D6E63", 4)
                       + _rect(-120, -150, 50, 40, "#B3E5FC", 4) + _rect(70, -150, 50, 40, "#B3E5FC", 4),
        "well": '<ellipse cx="0" cy="-10" rx="60" ry="22" fill="#78909C" stroke="#546E7A" stroke-width="6"/>'
                + '<ellipse cx="0" cy="-30" rx="52" ry="18" fill="#29B6F6"/>'
                + '<rect x="-4" y="-100" width="8" height="70" fill="#795548"/><rect x="-50" y="-110" width="100" height="10" rx="4" fill="#795548"/>',
        "dhaba_table": _rect(-120, -80, 240, 12, "#A1887F", 4) + _rect(-110, -68, 10, 68, "#8D6E63") + _rect(100, -68, 10, 68, "#8D6E63")
                       + "".join(f'<circle cx="{-80 + i * 50}" cy="-92" r="14" fill="{c}"/>' for i, c in enumerate(["#BDBDBD", "#E53935", "#43A047", "#BDBDBD"])),
        "bookshelf": _rect(-160, -360, 320, 360, "#6D4C41", 4) + "".join(
            _rect(-150, -350 + i * 70, 300, 8, "#5D4037") + "".join(
                f'<rect x="{-140 + j * 34}" y="{-342 + i * 70}" width="28" height="54" rx="3" fill="{c}"/>'
                for j, c in enumerate(["#1565C0", "#C62828", "#2E7D32", "#6A1B9A", "#E65100", "#00838F", "#AD1457", "#F57F17"])
            ) for i in range(5)),
        "reading_lamp": '<rect x="-6" y="-160" width="12" height="140" fill="#37474F"/>'
                        + '<path d="M-50 -170 q50 -30 100 0 l-10 20 h-80z" fill="#FDD835"/>'
                        + '<rect x="-30" y="-10" width="60" height="10" rx="4" fill="#455A64"/>',
        "curtain": '<rect x="-20" y="-500" width="40" height="500" fill="#C62828" opacity=".9"/>'
                   + '<path d="M-20 -500 q-80 100 -80 250 q0 120 60 250 h20z" fill="#B71C1C" opacity=".85"/>'
                   + '<path d="M20 -500 q80 100 80 250 q0 120 -60 250 h-20z" fill="#B71C1C" opacity=".85"/>',
        "spotlight": '<circle cx="0" cy="-600" r="30" fill="#FFEE58"/><path d="M-30 -580 l-100 580 h260 l-100 -580z" fill="#FFF176" opacity=".15"/>',
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
    # --- 20 new Indian-market scenes ---
    "temple": {"label": "मंदिर", "wall": "#FFF3E0", "floor": "#D7CCC8",
               "props": [("temple_arch", .5, .99, 1.0), ("diya", .25, .99, .9), ("diya", .75, .99, .9), ("bell", .5, .72, .8), ("garland", .5, .9, .8), ("flag", .92, .99, .7)],
               "slots": [(.35, .99, 1.0), (.65, .99, 1.0)]},
    "bazaar": {"label": "बाज़ार / स्ट्रीट मार्केट", "sky": True, "wall": "#FFF9C4", "floor": "#9E9E9E",
               "props": [("market_stall", .22, .99, .9), ("market_stall", .78, .99, .9), ("awning", .5, .72, .6), ("fruitstand", .5, .95, .9), ("lamp", .1, .99, .9), ("sign", .5, .58, .4)],
               "slots": [(.5, .99, 1.0), (.35, .99, .95)]},
    "train_station": {"label": "रेलवे स्टेशन", "wall": "#ECEFF1", "floor": "#757575",
                      "props": [("train_roof", .5, .55, .9), ("train_platform", .5, .99, 1.0), ("bench", .3, .99, .9), ("clock", .5, .3, .8), ("lamp", .12, .99, 1.0), ("lamp", .88, .99, 1.0)],
                      "slots": [(.5, .99, 1.0), (.72, .99, .95)]},
    "auto_stand": {"label": "ऑटो रिक्शा स्टैंड", "sky": True, "wall": "#B3E5FC", "floor": "#616161", "road": True,
                   "props": [("auto_rickshaw", .35, .99, .9), ("auto_rickshaw", .7, .99, .8), ("tree", .06, .72, 1.0), ("sign", .88, .68, .4), ("lamp", .5, .99, 1.0)],
                   "slots": [(.22, .99, 1.0), (.55, .99, 1.0)]},
    "farm": {"label": "खेत / फ़ार्म", "sky": True, "wall": "#AED581", "floor": "#8BC34A",
             "props": [("wheat_field", .5, .92, 1.0), ("tractor", .82, .99, .8), ("tree", .06, .8, 1.1), ("well", .3, .94, .9)],
             "slots": [(.45, .99, 1.0), (.65, .99, .95)]},
    "chai_tapri": {"label": "चाय की टपरी", "sky": True, "wall": "#FFF9C4", "floor": "#9E9E9E",
                   "props": [("market_stall", .4, .99, .7), ("chai_kettle", .4, .92, .9), ("chai_bench", .7, .99, .9), ("tree", .06, .8, 1.0), ("lamp", .92, .99, .9), ("sign", .4, .62, .35)],
                   "slots": [(.55, .99, 1.0), (.8, .99, .95)]},
    "wedding": {"label": "शादी / मंडप", "wall": "#880E4F", "floor": "#AD1457",
                "props": [("mandap", .5, .99, 1.0), ("fire_pit", .5, .95, .8), ("garland", .25, .88, .7), ("garland", .75, .88, .7), ("diya", .15, .99, .8), ("diya", .85, .99, .8), ("stage_light", .5, .98, .7)],
                "slots": [(.35, .99, 1.0), (.65, .99, 1.0)]},
    "college": {"label": "कॉलेज कैंपस", "sky": True, "wall": "#B3E5FC", "floor": "#8BC34A",
                "props": [("college_gate", .5, .88, .9), ("tree", .12, .82, 1.0), ("tree", .88, .82, 1.0), ("bench", .3, .99, .9), ("lamp", .7, .99, .9), ("flag", .95, .99, .6)],
                "slots": [(.4, .99, 1.0), (.65, .99, 1.0)]},
    "news_studio": {"label": "न्यूज़ स्टूडियो", "wall": "#1A237E", "floor": "#0D47A1",
                    "props": [("news_desk", .5, .99, 1.0), ("camera", .15, .99, .9), ("camera", .85, .99, .9), ("stage_light", .3, .98, .6), ("stage_light", .7, .98, .6)],
                    "slots": [(.5, .99, 1.0), (.35, .99, .9)]},
    "hospital_ward": {"label": "अस्पताल (गहन चिकित्सा)", "wall": "#E8F5E9", "floor": "#C8E6C9",
                      "props": [("bed", .3, .99, 1.1), ("bed", .75, .99, 1.1), ("cabinet", .05, .99, .9), ("window", .5, .62, .9), ("clock", .88, .3, .7), ("curtain", .53, .99, .7)],
                      "slots": [(.15, .99, 1.0), (.6, .99, .95)]},
    "police_station": {"label": "पुलिस स्टेशन", "wall": "#ECEFF1", "floor": "#B0BEC5",
                       "props": [("police_desk", .5, .99, 1.0), ("flag", .9, .99, .6), ("barricade", .2, .99, .7), ("clock", .5, .3, .7), ("chair", .5, .99, .9)],
                       "slots": [(.3, .99, 1.0), (.72, .99, 1.0)]},
    "courtroom": {"label": "कोर्ट रूम", "wall": "#EFEBE9", "floor": "#D7CCC8",
                  "props": [("judge_bench", .5, .85, 1.0), ("gavel", .5, .78, .8), ("flag", .88, .99, .6), ("chair", .3, .99, .9), ("chair", .7, .99, .9), ("desk", .3, .99, .8), ("desk", .7, .99, .8)],
                  "slots": [(.3, .99, 1.0), (.7, .99, 1.0)]},
    "village": {"label": "गाँव", "sky": True, "wall": "#B3E5FC", "floor": "#8BC34A",
                "props": [("village_hut", .3, .88, .9), ("village_hut", .75, .88, .7), ("well", .55, .95, .8), ("tree", .08, .8, 1.1), ("tree", .95, .8, .9)],
                "slots": [(.45, .99, 1.0), (.65, .99, .95)]},
    "dhaba": {"label": "ढाबा / रेस्टोरेंट", "wall": "#FFF3E0", "floor": "#BCAAA4",
              "props": [("dhaba_table", .35, .99, 1.0), ("dhaba_table", .7, .99, .9), ("chai_kettle", .1, .92, .8), ("tv", .85, .78, .7), ("plant", .95, .99, .8), ("awning", .5, .68, .5)],
              "slots": [(.5, .99, 1.0), (.25, .99, .95)]},
    "library": {"label": "पुस्तकालय", "wall": "#EFEBE9", "floor": "#D7CCC8",
                "props": [("bookshelf", .12, .99, 1.0), ("bookshelf", .88, .99, 1.0), ("desk", .5, .99, .9), ("reading_lamp", .5, .9, .8), ("chair", .5, .99, .8), ("window", .5, .62, .8)],
                "slots": [(.35, .99, 1.0), (.7, .99, 1.0)]},
    "stage": {"label": "मंच / स्टेज", "wall": "#1A237E", "floor": "#283593",
              "props": [("curtain", .02, .99, .8), ("curtain", .98, .99, .8), ("spotlight", .5, .99, .6), ("podium", .5, .99, .9), ("stage_light", .25, .98, .6), ("stage_light", .75, .98, .6)],
              "slots": [(.5, .99, 1.0), (.3, .99, .95)]},
    "home_kitchen": {"label": "घर का किचन (मॉडर्न)", "wall": "#FAFAFA", "floor": "#EEEEEE",
                     "props": [("fridge", .08, .99, 1.0), ("stove", .4, .99, 1.0), ("counter", .4, .99, .9), ("cabinet", .7, .99, .9), ("window", .85, .66, .8), ("plant", .95, .99, .7)],
                     "slots": [(.55, .99, 1.0), (.25, .99, .95)]},
    "garden": {"label": "बगीचा / गार्डन", "sky": True, "wall": "#B3E5FC", "floor": "#66BB6A",
               "props": [("tree", .1, .82, 1.2), ("tree", .9, .82, 1.0), ("bench", .5, .99, .9), ("plant", .3, .99, 1.0), ("plant", .7, .99, 1.0), ("lamp", .5, .99, .8)],
               "slots": [(.35, .99, 1.0), (.65, .99, 1.0)]},
    "yoga_studio": {"label": "योगा स्टूडियो", "wall": "#E8F5E9", "floor": "#C8E6C9",
                    "props": [("mirror", .5, .72, 1.1), ("plant", .05, .99, 1.0), ("plant", .95, .99, 1.0), ("window", .25, .62, .9), ("window", .75, .62, .9)],
                    "slots": [(.35, .99, 1.0), (.65, .99, 1.0), (.5, .99, .95)]},
    "warehouse": {"label": "गोदाम / वेयरहाउस", "wall": "#CFD8DC", "floor": "#90A4AE",
                  "props": [("shelf", .15, .99, 1.2), ("shelf", .85, .99, 1.2), ("shelf", .5, .99, 1.0), ("barricade", .35, .99, .6), ("lamp", .3, .99, 1.0), ("lamp", .7, .99, 1.0)],
                  "slots": [(.3, .99, 1.0), (.7, .99, .95)]},
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
