"""Parametric 2D character rig → SVG.

A character is `params` (who: age, gender, skin, hair, outfit, props… see catalog.DEFAULT_PARAMS)
plus a `pose` (how, right now: joint angles, head tilt, eyes, mouth viseme…). svg(params, pose)
returns a self-contained SVG (viewBox 0 0 400 800, transparent background) that librsvg / a
browser renders identically — the same function makes every preview frame and every render frame.

Pose keys (all optional, degrees / 0–1):
  bob, lean, head_tilt, head_turn (−1…1), l_sh, l_el, r_sh, r_el (shoulder / elbow),
  l_hip, l_knee, r_hip, r_knee, eye_open, gaze_x, gaze_y, brow, smile, viseme, mouth_open,
  expr (neutral|happy|sad|angry|surprised|thinking), flip (mirror), squash
Layers (back → front): back hair, back arm, legs / skirt, torso, front arm, neck, head, hair, hat, props.
"""

from __future__ import annotations

import math

from . import catalog as C

VIEW_W, VIEW_H = 400, 800
GROUND = 760.0
SKIN_SHADE = 0.82

POSE_DEFAULT = {
    "bob": 0.0, "lean": 0.0, "head_tilt": 0.0, "head_turn": 0.0,
    "l_sh": 8.0, "l_el": 10.0, "r_sh": 8.0, "r_el": 10.0,
    "l_hip": 0.0, "l_knee": 0.0, "r_hip": 0.0, "r_knee": 0.0,
    "eye_open": 1.0, "gaze_x": 0.0, "gaze_y": 0.0, "brow": 0.0, "smile": 0.15,
    "viseme": "rest", "mouth_open": 0.0, "expr": "neutral", "flip": 0.0, "squash": 0.0,
    "l_hand": "open", "r_hand": "open",
}
EXPR = {  # brow, smile, eye_open, extra mouth open
    "neutral": (0.0, 0.15, 1.0, 0.0), "happy": (0.3, 0.9, 0.9, 0.1), "sad": (-0.6, -0.7, 0.8, 0.0),
    "angry": (-1.0, -0.4, 0.75, 0.15), "surprised": (1.0, 0.0, 1.0, 0.6), "thinking": (0.4, -0.1, 0.7, 0.0),
}


def validate(params: dict) -> dict:
    """Unknown ids → ValueError (Hindi). Returns a full params dict with defaults filled in."""
    p = {**C.DEFAULT_PARAMS, **{k: v for k, v in (params or {}).items() if k in C.DEFAULT_PARAMS}}
    checks = [("age", C.AGES), ("gender", C.GENDERS), ("body", C.BODIES), ("hair", C.HAIR), ("hair_color", C.HAIR_COLOURS),
              ("facial", C.FACIAL), ("outfit", C.OUTFITS), ("prop", C.PROPS), ("hat", C.HATS)]
    for key, table in checks:
        if p[key] not in table:
            raise ValueError(f"{key} '{p[key]}' नहीं है — विकल्प: {', '.join(list(table)[:8])}…")
    for a in p.get("accessories") or []:
        if a not in C.ACCESSORIES:
            raise ValueError(f"accessory '{a}' नहीं है")
    for key in ("skin", "top", "bottom", "shoes", "glasses_color"):
        v = p.get(key)
        if v is not None and not _is_hex(v):
            raise ValueError(f"{key} का रंग #RRGGBB में दें")
    return p


def _is_hex(v) -> bool:
    return isinstance(v, str) and len(v) == 7 and v[0] == "#" and all(ch in "0123456789abcdefABCDEF" for ch in v[1:])


def _mix(hex_: str, f: float) -> str:
    """Darken (f<1) / lighten (f>1) a #RRGGBB."""
    r, g, b = int(hex_[1:3], 16), int(hex_[3:5], 16), int(hex_[5:7], 16)
    out = [max(0, min(255, int(round(c * f)))) for c in (r, g, b)]
    return "#%02X%02X%02X" % tuple(out)


def _pt(x: float, y: float, ang: float, ln: float, side: float) -> tuple[float, float]:
    """End of a limb segment: angle in degrees from straight down, `side` = +1 right / −1 left (outward)."""
    a = math.radians(ang)
    return x + side * math.sin(a) * ln, y + math.cos(a) * ln


def _f(v: float) -> str:
    return f"{v:.1f}"


# ------------------------------------------------------------------ body measures
def measures(p: dict) -> dict:
    age, body = p["age"], p["body"]
    scale = {"child": 0.72, "young": 0.96, "adult": 1.0, "elderly": 0.95}[age]
    head = {"child": 1.18, "young": 1.0, "adult": 1.0, "elderly": 0.98}[age]
    width = {"slim": 0.86, "average": 1.0, "broad": 1.15, "heavy": 1.3}[body]
    if p["gender"] == "f":
        width *= 0.92
    return {"scale": scale, "head": head, "width": width, "sw": 64 * width, "hip": 34 * width,
            "arm": (104, 96) if age != "child" else (90, 80), "leg": (136, 124) if age != "child" else (112, 100),
            "lean_extra": 4.0 if age == "elderly" else 0.0}


# ------------------------------------------------------------------ parts
def _limb(x0, y0, a1, l1, a2, l2, side, w, c1, c2, hand_r, skin, hand_kind="open", prop_svg: str = "") -> str:
    """Two-joint limb (shoulder→elbow→hand). Returns svg and the hand position via a trailing comment."""
    ex, ey = _pt(x0, y0, a1, l1, side)
    hx, hy = _pt(ex, ey, a1 + a2, l2, side)
    s = (f'<path d="M{_f(x0)} {_f(y0)} L{_f(ex)} {_f(ey)}" stroke="{c1}" stroke-width="{_f(w)}" stroke-linecap="round" fill="none"/>'
         f'<path d="M{_f(ex)} {_f(ey)} L{_f(hx)} {_f(hy)}" stroke="{c2}" stroke-width="{_f(w * 0.9)}" stroke-linecap="round" fill="none"/>')
    if hand_kind == "fist":
        s += f'<circle cx="{_f(hx)}" cy="{_f(hy)}" r="{_f(hand_r * 0.95)}" fill="{skin}"/>'
    else:
        s += (f'<ellipse cx="{_f(hx)}" cy="{_f(hy + 4)}" rx="{_f(hand_r)}" ry="{_f(hand_r * 1.15)}" fill="{skin}"/>'
              f'<path d="M{_f(hx - hand_r * .6)} {_f(hy + 2)} l0 10 M{_f(hx)} {_f(hy + 2)} l0 12 M{_f(hx + hand_r * .6)} {_f(hy + 2)} l0 10" stroke="{_mix(skin, SKIN_SHADE)}" stroke-width="1.5" stroke-linecap="round"/>')
    return s.replace("{HX}", _f(hx)).replace("{HY}", _f(hy)) + prop_svg.replace("{HX}", _f(hx)).replace("{HY}", _f(hy))


def _prop(kind: str, side: float, top: str) -> str:
    """Held in a hand; {HX} {HY} are replaced by the hand position."""
    if kind == "phone":
        return '<g transform="translate({HX},{HY}) rotate(-12)"><rect x="-9" y="-20" width="18" height="34" rx="3" fill="#1A1A1A"/><rect x="-7" y="-17" width="14" height="26" rx="1.5" fill="#4FC3F7"/></g>'
    if kind == "tablet":
        return '<g transform="translate({HX},{HY}) rotate(-8)"><rect x="-22" y="-14" width="44" height="34" rx="3" fill="#263238"/><rect x="-19" y="-11" width="38" height="28" rx="1" fill="#E3F2FD"/></g>'
    if kind == "laptop":
        return '<g transform="translate({HX},{HY})"><rect x="-30" y="-2" width="60" height="6" rx="2" fill="#546E7A"/><rect x="-28" y="-40" width="56" height="38" rx="3" fill="#37474F"/><rect x="-25" y="-37" width="50" height="32" fill="#B3E5FC"/></g>'
    if kind == "book":
        return '<g transform="translate({HX},{HY}) rotate(10)"><rect x="-16" y="-22" width="32" height="40" rx="2" fill="#C62828"/><rect x="-12" y="-18" width="24" height="32" fill="#FFF8E1"/><path d="M-6 -10h12M-6 -4h12M-6 2h8" stroke="#BDBDBD" stroke-width="1.5"/></g>'
    if kind == "clipboard":
        return '<g transform="translate({HX},{HY}) rotate(8)"><rect x="-16" y="-24" width="32" height="44" rx="2" fill="#8D6E63"/><rect x="-13" y="-19" width="26" height="36" fill="#FFFFFF"/><rect x="-6" y="-27" width="12" height="7" rx="2" fill="#455A64"/><path d="M-9 -10h18M-9 -3h18M-9 4h12" stroke="#90A4AE" stroke-width="1.5"/></g>'
    if kind == "dumbbell":
        return '<g transform="translate({HX},{HY})"><rect x="-26" y="-3" width="52" height="6" rx="3" fill="#616161"/><rect x="-32" y="-12" width="10" height="24" rx="2" fill="#212121"/><rect x="22" y="-12" width="10" height="24" rx="2" fill="#212121"/></g>'
    if kind == "scissors":
        return '<g transform="translate({HX},{HY}) rotate(-30)"><path d="M0 0 L-6 -30 M0 0 L6 -30" stroke="#B0BEC5" stroke-width="3" stroke-linecap="round"/><circle cx="-5" cy="8" r="5" fill="none" stroke="#37474F" stroke-width="2.5"/><circle cx="5" cy="8" r="5" fill="none" stroke="#37474F" stroke-width="2.5"/></g>'
    if kind == "wrench":
        return '<g transform="translate({HX},{HY}) rotate(-35)"><rect x="-4" y="-6" width="8" height="34" rx="2" fill="#78909C"/><path d="M-10 -16 a10 10 0 1 1 20 0 l-5 6 h-10z" fill="#78909C"/></g>'
    if kind == "mic":
        return '<g transform="translate({HX},{HY}) rotate(-20)"><rect x="-4" y="-6" width="8" height="30" rx="3" fill="#424242"/><ellipse cx="0" cy="-14" rx="10" ry="13" fill="#9E9E9E"/><path d="M-6 -20h12M-7 -14h14M-6 -8h12" stroke="#616161" stroke-width="1.2"/></g>'
    return ""


def _hair_back(p: dict, hx: float, hy: float, rx: float, ry: float, col: str) -> str:
    h = p["hair"]
    if h in ("long", "wavy"):
        wave = "" if h == "long" else f" q{_f(rx * .3)} 18 0 36 q{_f(-rx * .3)} 18 0 36"
        return (f'<path d="M{_f(hx - rx - 6)} {_f(hy - 10)} q0 {_f(ry * 2.3)} {_f(rx * .5)} {_f(ry * 2.5)}{wave} '
                f'h{_f(rx * 1.2)} q{_f(rx * .5)} {_f(-ry * .2)} {_f(rx * .5)} {_f(-ry * 2.5)} v{_f(-ry * 1.0)} z" fill="url(#hg)"/>')
    if h == "ponytail":
        return (f'<path d="M{_f(hx + rx * .6)} {_f(hy - 20)} q{_f(rx * .9)} {_f(ry * .4)} {_f(rx * .5)} {_f(ry * 1.9)} '
                f'q{_f(-rx * .3)} {_f(ry * .3)} {_f(-rx * .7)} {_f(ry * .1)} q{_f(rx * .4)} {_f(-ry)} 0 {_f(-ry * 1.6)}z" fill="url(#hg)"/>')
    if h == "braid":
        s = ""
        for i in range(5):
            s += f'<ellipse cx="{_f(hx + rx * .95)}" cy="{_f(hy + ry * .6 + i * 24)}" rx="10" ry="13" fill="{col if i % 2 else _mix(col, 1.15)}"/>'
        return s
    if h == "bun":
        return f'<circle cx="{_f(hx)}" cy="{_f(hy - ry - 6)}" r="{_f(rx * .42)}" fill="url(#hg)"/>'
    if h == "bob":
        return f'<path d="M{_f(hx - rx - 4)} {_f(hy - 20)} v{_f(ry * 1.25)} q{_f(rx)} 10 {_f(rx * 2 + 8)} 0 v{_f(-ry * 1.25)}z" fill="url(#hg)"/>'
    return ""


def _hair_front(p: dict, hx: float, hy: float, rx: float, ry: float, col: str) -> str:
    h = p["hair"]
    if h == "bald":
        return f'<path d="M{_f(hx - rx + 4)} {_f(hy - ry * .15)} q{_f(rx * .3)} {_f(-ry * .25)} {_f(rx * .5)} {_f(-ry * .05)}" stroke="{col}" stroke-width="6" fill="none" stroke-linecap="round"/>' \
               f'<path d="M{_f(hx + rx - 4)} {_f(hy - ry * .15)} q{_f(-rx * .3)} {_f(-ry * .25)} {_f(-rx * .5)} {_f(-ry * .05)}" stroke="{col}" stroke-width="6" fill="none" stroke-linecap="round"/>'
    top = hy - ry
    if h == "buzz":
        return f'<path d="M{_f(hx - rx)} {_f(hy - ry * .35)} a{_f(rx)} {_f(ry)} 0 0 1 {_f(rx * 2)} 0 q{_f(-rx * .2)} {_f(-ry * .05)} {_f(-rx)} 0 q{_f(-rx * .8)} {_f(-ry * .05)} {_f(-rx)} 0z" fill="{col}" opacity=".9"/>'
    if h == "spiky":
        pts = "".join(f" L{_f(hx - rx * .8 + i * rx * .4)} {_f(top - 26 - (i % 2) * 10)} L{_f(hx - rx * .6 + i * rx * .4)} {_f(top + 6)}" for i in range(5))
        return f'<path d="M{_f(hx - rx)} {_f(hy - ry * .3)} Q{_f(hx - rx)} {_f(top + 6)} {_f(hx - rx * .8)} {_f(top + 4)}{pts} Q{_f(hx + rx)} {_f(top + 6)} {_f(hx + rx)} {_f(hy - ry * .3)}z" fill="url(#hg)"/>'
    if h == "curly":
        s = f'<path d="M{_f(hx - rx - 2)} {_f(hy - ry * .3)} a{_f(rx + 2)} {_f(ry * 1.05)} 0 0 1 {_f(rx * 2 + 4)} 0z" fill="url(#hg)"/>'
        for i in range(7):
            ang = math.pi * (0.1 + 0.8 * i / 6)
            s += f'<circle cx="{_f(hx - math.cos(ang) * (rx + 2))}" cy="{_f(hy - ry * .3 - math.sin(ang) * ry * 1.0)}" r="13" fill="{col}"/>'
        return s
    if h == "side":
        return (f'<path d="M{_f(hx - rx)} {_f(hy - ry * .3)} a{_f(rx)} {_f(ry)} 0 0 1 {_f(rx * 2)} 0 q{_f(-rx * .3)} {_f(-ry * .1)} {_f(-rx * 1.5)} {_f(ry * .35)} '
                f'q{_f(-rx * .2)} {_f(-ry * .2)} {_f(-rx * .5)} {_f(-ry * .35)}z" fill="url(#hg)"/>')
    if h in ("bun", "ponytail", "braid", "long", "wavy", "bob"):
        return (f'<path d="M{_f(hx - rx - 2)} {_f(hy - ry * .25)} a{_f(rx + 2)} {_f(ry * 1.02)} 0 0 1 {_f(rx * 2 + 4)} 0 '
                f'q{_f(-rx * .4)} {_f(-ry * .25)} {_f(-rx * 1.1)} {_f(ry * .2)} q{_f(-rx * .4)} {_f(-ry * .3)} {_f(-rx * .9)} {_f(-ry * .2)}z" fill="url(#hg)"/>')
    # short (default)
    return (f'<path d="M{_f(hx - rx)} {_f(hy - ry * .3)} a{_f(rx)} {_f(ry)} 0 0 1 {_f(rx * 2)} 0 q{_f(-rx * .5)} {_f(-ry * .15)} {_f(-rx)} {_f(ry * .15)} '
            f'q{_f(-rx * .5)} {_f(-ry * .3)} {_f(-rx)} {_f(-ry * .15)}z" fill="url(#hg)"/>')


def _hat(kind: str, hx: float, hy: float, rx: float, ry: float, col: str) -> str:
    top = hy - ry
    if kind == "cap":
        return (f'<path d="M{_f(hx - rx)} {_f(hy - ry * .35)} a{_f(rx)} {_f(ry * .95)} 0 0 1 {_f(rx * 2)} 0z" fill="{col}"/>'
                f'<path d="M{_f(hx - rx * .2)} {_f(hy - ry * .3)} h{_f(rx * 1.6)} q6 0 6 6 q-{_f(rx * 1.8)} 6 -{_f(rx * 1.8)} -2z" fill="{_mix(col, .8)}"/>')
    if kind == "helmet":
        return (f'<path d="M{_f(hx - rx - 6)} {_f(hy - ry * .3)} a{_f(rx + 6)} {_f(ry * 1.05)} 0 0 1 {_f(rx * 2 + 12)} 0z" fill="#FFC107"/>'
                f'<rect x="{_f(hx - rx - 10)}" y="{_f(hy - ry * .36)}" width="{_f(rx * 2 + 20)}" height="9" rx="4" fill="#FFA000"/>'
                f'<path d="M{_f(hx)} {_f(top - 2)} v{_f(ry * .6)}" stroke="#FFA000" stroke-width="6"/>')
    if kind == "chef":
        return (f'<rect x="{_f(hx - rx * .75)}" y="{_f(top - 34)}" width="{_f(rx * 1.5)}" height="{_f(ry * .55 + 34)}" fill="#FFFFFF"/>'
                f'<ellipse cx="{_f(hx)}" cy="{_f(top - 34)}" rx="{_f(rx * .95)}" ry="26" fill="#FFFFFF"/>')
    if kind == "turban":
        return (f'<path d="M{_f(hx - rx - 8)} {_f(hy - ry * .2)} a{_f(rx + 8)} {_f(ry * 1.15)} 0 0 1 {_f(rx * 2 + 16)} 0z" fill="{col}"/>'
                f'<path d="M{_f(hx - rx)} {_f(hy - ry * .35)} q{_f(rx)} {_f(-ry * .5)} {_f(rx * 2)} 0" stroke="{_mix(col, .78)}" stroke-width="5" fill="none"/>'
                f'<path d="M{_f(hx - rx * .6)} {_f(hy - ry * .9)} q{_f(rx * .6)} {_f(-ry * .4)} {_f(rx * 1.3)} 0" stroke="{_mix(col, .78)}" stroke-width="5" fill="none"/>')
    if kind == "nurse":
        return f'<path d="M{_f(hx - rx * .5)} {_f(top + 8)} l{_f(rx * .15)} -22 h{_f(rx * .7)} l{_f(rx * .15)} 22z" fill="#FFFFFF" stroke="#CFD8DC" stroke-width="2"/><path d="M{_f(hx - 6)} {_f(top - 8)} h12 M{_f(hx)} {_f(top - 14)} v12" stroke="#E53935" stroke-width="3"/>'
    if kind == "hat":
        return (f'<path d="M{_f(hx - rx)} {_f(hy - ry * .35)} a{_f(rx)} {_f(ry)} 0 0 1 {_f(rx * 2)} 0z" fill="{col}"/>'
                f'<ellipse cx="{_f(hx)}" cy="{_f(hy - ry * .32)}" rx="{_f(rx * 1.45)}" ry="9" fill="{_mix(col, .8)}"/>')
    return ""


def _mouth(x: float, y: float, viseme: str, open_: float, smile: float, k: float, skin: str) -> str:
    lip = _mix(skin, 0.62)
    inner = "#5A1E1E"
    w = 15 * k
    o = max(0.0, min(1.0, open_))
    if viseme in ("rest", "MBP"):
        dy = -8 * smile * k
        thick = 3.2 if viseme == "MBP" else 2.4
        return f'<path d="M{_f(x - w)} {_f(y)} q{_f(w)} {_f(dy * 2 + 6 * o * k)} {_f(w * 2)} 0" stroke="{lip}" stroke-width="{thick}" fill="none" stroke-linecap="round"/>'
    if viseme == "AA":
        ry = (6 + 9 * o) * k
        return (f'<ellipse cx="{_f(x)}" cy="{_f(y + ry * .5)}" rx="{_f(w)}" ry="{_f(ry)}" fill="{inner}"/>'
                f'<path d="M{_f(x - w)} {_f(y + ry * .2)} q{_f(w)} -6 {_f(w * 2)} 0" stroke="{lip}" stroke-width="2" fill="none"/>'
                f'<ellipse cx="{_f(x)}" cy="{_f(y + ry * 1.1)}" rx="{_f(w * .55)}" ry="{_f(ry * .4)}" fill="#C65A5A"/>')
    if viseme == "EE":
        return (f'<ellipse cx="{_f(x)}" cy="{_f(y + 2)}" rx="{_f(w * 1.25)}" ry="{_f((3 + 3 * o) * k)}" fill="{inner}"/>'
                f'<rect x="{_f(x - w * .9)}" y="{_f(y - 1)}" width="{_f(w * 1.8)}" height="{_f(3 * k)}" fill="#FFFFFF"/>')
    if viseme == "OO":
        return f'<ellipse cx="{_f(x)}" cy="{_f(y + 3)}" rx="{_f((6 + 2 * o) * k)}" ry="{_f((7 + 3 * o) * k)}" fill="{inner}" stroke="{lip}" stroke-width="2"/>'
    if viseme == "FV":
        return (f'<path d="M{_f(x - w)} {_f(y)} q{_f(w)} {_f(4 * k)} {_f(w * 2)} 0" stroke="{lip}" stroke-width="2.4" fill="none"/>'
                f'<rect x="{_f(x - w * .7)}" y="{_f(y - 2)}" width="{_f(w * 1.4)}" height="{_f(4 * k)}" rx="1" fill="#FFFFFF"/>')
    if viseme == "L":
        ry = (6 + 5 * o) * k
        return (f'<ellipse cx="{_f(x)}" cy="{_f(y + ry * .5)}" rx="{_f(w * .8)}" ry="{_f(ry)}" fill="{inner}"/>'
                f'<ellipse cx="{_f(x)}" cy="{_f(y + ry * .35)}" rx="{_f(w * .35)}" ry="{_f(ry * .5)}" fill="#C65A5A"/>')
    # DD / default open
    ry = (5 + 6 * o) * k
    return (f'<ellipse cx="{_f(x)}" cy="{_f(y + ry * .5)}" rx="{_f(w * .95)}" ry="{_f(ry)}" fill="{inner}"/>'
            f'<rect x="{_f(x - w * .6)}" y="{_f(y - 1)}" width="{_f(w * 1.2)}" height="{_f(3 * k)}" fill="#FFFFFF"/>')


# ------------------------------------------------------------------ polished rendering defs
def _defs(skin: str, skin_d: str, hair_c: str, top: str, bottom: str) -> str:
    """SVG <defs> — gradients and shadows for studio-quality look."""
    skin_hi = _mix(skin, 1.15)
    hair_hi = _mix(hair_c, 1.35)
    hair_dk = _mix(hair_c, 0.72)
    top_hi = _mix(top, 1.14)
    top_dk = _mix(top, 0.80)
    bot_hi = _mix(bottom, 1.10)
    bot_dk = _mix(bottom, 0.82)
    return (
        '<defs>'
        # skin radial — warm highlight center, natural shadow at edges
        f'<radialGradient id="sk" cx=".44" cy=".36" r=".6">'
        f'<stop offset="0" stop-color="{skin_hi}"/>'
        f'<stop offset=".65" stop-color="{skin}"/>'
        f'<stop offset="1" stop-color="{skin_d}"/>'
        '</radialGradient>'
        # skin limb gradient — subtle depth along limbs
        f'<linearGradient id="sl" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{skin_d}"/>'
        f'<stop offset=".45" stop-color="{skin}"/>'
        f'<stop offset="1" stop-color="{skin_d}"/>'
        '</linearGradient>'
        # hair gradient — highlight band to deep shadow
        f'<linearGradient id="hg" x1=".3" y1="0" x2=".5" y2="1">'
        f'<stop offset="0" stop-color="{hair_hi}"/>'
        f'<stop offset=".35" stop-color="{hair_c}"/>'
        f'<stop offset="1" stop-color="{hair_dk}"/>'
        '</linearGradient>'
        # clothing top gradient
        f'<linearGradient id="tg" x1=".2" y1="0" x2=".6" y2="1">'
        f'<stop offset="0" stop-color="{top_hi}"/>'
        f'<stop offset="1" stop-color="{top_dk}"/>'
        '</linearGradient>'
        # clothing bottom gradient
        f'<linearGradient id="btg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{bot_hi}"/>'
        f'<stop offset="1" stop-color="{bot_dk}"/>'
        '</linearGradient>'
        # iris gradient — deep brown centre to lighter rim
        '<radialGradient id="ig" cx=".38" cy=".32" r=".55">'
        '<stop offset="0" stop-color="#795548"/>'
        '<stop offset=".6" stop-color="#4E342E"/>'
        '<stop offset="1" stop-color="#3E2723"/>'
        '</radialGradient>'
        # lip gradient
        f'<radialGradient id="lg" cx=".5" cy=".4" r=".6">'
        f'<stop offset="0" stop-color="{_mix(skin, 0.68)}"/>'
        f'<stop offset="1" stop-color="{_mix(skin, 0.52)}"/>'
        '</radialGradient>'
        '</defs>'
    )


# ------------------------------------------------------------------ the character
def svg(params: dict, pose: dict | None = None, *, width: int | None = None, height: int | None = None,
        bare: bool = False) -> str:
    p = validate(params)
    q = {**POSE_DEFAULT, **(pose or {})}
    if q.get("expr") in EXPR:
        eb, es, eo, em = EXPR[q["expr"]]
        q["brow"] = q["brow"] + eb if (pose or {}).get("brow") is not None else eb
        q["smile"] = (pose or {}).get("smile", es)
        q["eye_open"] = min(float(q["eye_open"]), eo)
        q["mouth_open"] = max(float(q["mouth_open"]), em)
    m = measures(p)
    o = C.OUTFITS[p["outfit"]]
    skin = p["skin"]
    skin_d = _mix(skin, SKIN_SHADE)
    top = p.get("top") or o["top"]
    bottom = p.get("bottom") or o["bottom"]
    hair_c = C.HAIR_COLOURS[p["hair_color"]]
    female = p["gender"] == "f"
    # --- key points (unscaled adult frame; the whole body is scaled about the ground point)
    cx = 200.0
    bob = float(q["bob"])
    hip_y = 470.0 + bob
    sh_y = 255.0 + bob
    neck_top = 222.0 + bob
    hy = 150.0 + bob
    rx, ry = 60.0 * m["head"], 70.0 * m["head"]
    sw, hip = m["sw"], m["hip"]
    ua, fa = m["arm"]
    th, sh = m["leg"]
    sleeve = o.get("sleeve", "short")
    c_upper = top if sleeve in ("long", "short") else skin
    c_fore = top if sleeve == "long" else skin
    if o.get("coat"):
        c_upper = c_fore = o["top"]
    if o.get("jacket"):
        c_upper = c_fore = _mix(top, 0.95)
    g: list[str] = []
    skirt = o.get("saree") or o.get("lehenga") or o.get("veshti")
    # --- back hair
    g.append(_hair_back(p, cx, hy, rx, ry, hair_c))
    # --- legs (or skirt)
    lhx, rhx = cx - hip * .55, cx + hip * .55
    if skirt:
        col = bottom if not o.get("veshti") else "#FFFFFF"
        flare = 1.45 if o.get("lehenga") else 1.1
        g.append(f'<path d="M{_f(cx - hip - 6)} {_f(hip_y - 10)} q{_f(-hip * (flare - 1) * 2.2)} {_f(th + sh - 8)} {_f(-hip * (flare - 1))} {_f(th + sh)} '
                 f'h{_f((hip + 6) * 2 + hip * (flare - 1) * 2)} q{_f(hip * (flare - 1) * 1.2)} {_f(-(th + sh - 8))} {_f(-hip * (flare - 1))} {_f(-(th + sh))}z" fill="{col}"/>')
        if o.get("lehenga"):
            for i in range(6):
                g.append(f'<circle cx="{_f(cx - hip * 1.4 + i * hip * .56)}" cy="{_f(hip_y + th + sh - 40)}" r="5" fill="#FFFFFF" opacity=".8"/>')
            g.append(f'<rect x="{_f(cx - hip * 1.7)}" y="{_f(hip_y + th + sh - 22)}" width="{_f(hip * 3.4)}" height="12" fill="{_mix(bottom, .7)}"/>')
        if o.get("veshti"):
            g.append(f'<path d="M{_f(cx - hip - 6)} {_f(hip_y + th + sh - 14)} h{_f((hip + 6) * 2 + hip * .2)}" stroke="{o["veshti"]}" stroke-width="10"/>'
                     f'<path d="M{_f(cx)} {_f(hip_y)} q-10 {_f(th)} 6 {_f(th + sh - 20)}" stroke="{_mix("#FFFFFF", .85)}" stroke-width="3" fill="none"/>')
        if o.get("saree"):
            g.append(f'<path d="M{_f(cx - hip * .3)} {_f(hip_y + 20)} q-6 {_f(th)} 2 {_f(th + sh - 30)} M{_f(cx + 2)} {_f(hip_y + 20)} q-6 {_f(th)} 2 {_f(th + sh - 30)}" stroke="{_mix(bottom, .78)}" stroke-width="2.5" fill="none"/>')
        for lx in (lhx, rhx):  # feet
            g.append(f'<ellipse cx="{_f(lx)}" cy="{_f(hip_y + th + sh + 2)}" rx="19" ry="8" fill="{p["shoes"]}"/>')
    else:
        for side, hx_, ha, ka in ((-1, lhx, q["l_hip"], q["l_knee"]), (1, rhx, q["r_hip"], q["r_knee"])):
            kx, ky = _pt(hx_, hip_y, ha, th, side)
            fx_, fy_ = _pt(kx, ky, ha - ka, sh, side)
            w = 30 * m["width"] if m["width"] < 1.2 else 36
            g.append(f'<path d="M{_f(hx_)} {_f(hip_y)} L{_f(kx)} {_f(ky)} L{_f(fx_)} {_f(fy_)}" stroke="{bottom}" stroke-width="{_f(w)}" stroke-linecap="round" stroke-linejoin="round" fill="none"/>')
            g.append(f'<path d="M{_f(fx_ - 8 * side)} {_f(fy_ + 2)} l{_f(22 * side)} 0 q10 0 10 8 l0 4 h-{_f(36 * side if side > 0 else -36)}z" fill="{p["shoes"]}" transform="translate(0,6)"/>'
                     f'<ellipse cx="{_f(fx_ + 4 * side)}" cy="{_f(fy_ + 12)}" rx="20" ry="9" fill="{p["shoes"]}"/>')
    # --- back arm (left, behind torso)
    l_prop = ""
    g.append(_limb(cx - sw, sh_y, q["l_sh"], ua, q["l_el"], fa, -1, 24 * (1 if m["width"] < 1.2 else 1.2), c_upper, c_fore, 14, skin, q.get("l_hand", "open"), l_prop))
    # --- torso
    tw = sw + 10
    torso_bottom = hip_y + (70 if o.get("kurta") or o.get("coat") else 8)
    lean = float(q["lean"]) + m["lean_extra"]
    g.append(f'<g transform="rotate({_f(lean)} {_f(cx)} {_f(hip_y)})">')
    g.append(f'<path d="M{_f(cx - tw)} {_f(sh_y - 12)} q{_f(tw * .1)} -20 {_f(tw)} -20 q{_f(tw * .9)} 0 {_f(tw)} 20 '
             f'l{_f(-(tw - hip - 8))} {_f(torso_bottom - sh_y + 12)} h{_f(-(hip + 8) * 2)}z" fill="url(#tg)"/>'
             # subtle centre fold line for depth
             f'<path d="M{_f(cx)} {_f(sh_y + 10)} v{_f(torso_bottom - sh_y - 20)}" stroke="{_mix(top, 0.82)}" stroke-width="1.5" opacity=".25"/>')
    if female and not o.get("coat"):
        g.append(f'<path d="M{_f(cx - tw * .7)} {_f(sh_y + 40)} q{_f(tw * .7)} 26 {_f(tw * 1.4)} 0" stroke="{_mix(top, .85)}" stroke-width="2" fill="none" opacity=".6"/>')
    if o.get("collar"):
        g.append(f'<path d="M{_f(cx - 22)} {_f(sh_y - 28)} l22 30 l22 -30 l-10 -4 l-12 18 l-12 -18z" fill="{_mix(top, .9)}"/>')
    if o.get("tie"):
        g.append(f'<path d="M{_f(cx - 7)} {_f(sh_y - 4)} h14 l-4 8 l4 60 l-11 12 l-11 -12 l4 -60z" fill="{o["tie"]}"/>')
    if o.get("jacket"):
        g.append(f'<path d="M{_f(cx - tw + 4)} {_f(sh_y - 10)} l{_f(tw - 10)} 0 l{_f(-tw * .25)} 70 l{_f(-tw * .25)} 90 h{_f(-(tw - hip - 10))}z" fill="{_mix(top, .8)}"/>'
                 f'<path d="M{_f(cx + tw - 4)} {_f(sh_y - 10)} l{_f(-(tw - 10))} 0 l{_f(tw * .25)} 70 l{_f(tw * .25)} 90 h{_f(tw - hip - 10)}z" fill="{_mix(top, .8)}"/>'
                 f'<path d="M{_f(cx - 30)} {_f(sh_y - 12)} l30 36 l30 -36" fill="#F5F5F5"/>')
    if o.get("coat"):
        g.append(f'<path d="M{_f(cx - tw - 4)} {_f(sh_y - 10)} h{_f(tw - 6)} l0 {_f(torso_bottom - sh_y + 60)} h{_f(-(tw - hip - 2))}z" fill="{o["top"]}" stroke="#DDD" stroke-width="1.5"/>'
                 f'<path d="M{_f(cx + tw + 4)} {_f(sh_y - 10)} h{_f(-(tw - 6))} l0 {_f(torso_bottom - sh_y + 60)} h{_f(tw - hip - 2)}z" fill="{o["top"]}" stroke="#DDD" stroke-width="1.5"/>'
                 f'<path d="M{_f(cx - 28)} {_f(sh_y - 12)} l28 40 l28 -40" fill="{top if p.get("top") else "#90CAF9"}"/>'
                 f'<rect x="{_f(cx + tw - 34)}" y="{_f(sh_y + 60)}" width="26" height="22" rx="2" fill="none" stroke="#DDD" stroke-width="1.5"/>')
    if o.get("apron"):
        g.append(f'<path d="M{_f(cx - 36)} {_f(sh_y + 10)} h72 l10 {_f(hip_y - sh_y + 40)} h-92z" fill="{o["apron"]}"/>'
                 f'<path d="M{_f(cx - 30)} {_f(sh_y + 10)} q30 -40 60 0" stroke="{o["apron"]}" stroke-width="4" fill="none"/>')
    if o.get("vest"):
        g.append(f'<path d="M{_f(cx - tw + 8)} {_f(sh_y - 4)} h{_f(tw * .55)} v{_f(hip_y - sh_y - 10)} h{_f(-(tw * .55 - 10))}z M{_f(cx + tw - 8)} {_f(sh_y - 4)} h{_f(-tw * .55)} v{_f(hip_y - sh_y - 10)} h{_f(tw * .55 - 10)}z" fill="{o["vest"]}"/>'
                 f'<path d="M{_f(cx - tw + 10)} {_f(sh_y + 60)} h{_f(tw * 2 - 20)} M{_f(cx - tw + 10)} {_f(sh_y + 90)} h{_f(tw * 2 - 20)}" stroke="#E0E0E0" stroke-width="4"/>')
    if o.get("kurta"):
        g.append(f'<path d="M{_f(cx)} {_f(sh_y - 12)} v36" stroke="{_mix(top, .8)}" stroke-width="3"/>'
                 f'<path d="M{_f(cx - hip - 8)} {_f(torso_bottom - 30)} v30 M{_f(cx + hip + 8)} {_f(torso_bottom - 30)} v30" stroke="{_mix(top, .85)}" stroke-width="2"/>')
    if o.get("saree"):
        g.append(f'<path d="M{_f(cx + hip + 4)} {_f(hip_y - 6)} q{_f(-tw * .9)} {_f(-(hip_y - sh_y) * .5)} {_f(-tw - 18)} {_f(-(hip_y - sh_y) - 10)} '
                 f'q{_f(-16)} 20 {_f(-6)} 44 q{_f(tw * .6)} {_f((hip_y - sh_y) * .4)} {_f(tw + 10)} {_f((hip_y - sh_y) * .6)}z" fill="{o["saree"]}" opacity=".95"/>')
    if o.get("dupatta"):
        g.append(f'<path d="M{_f(cx + tw - 6)} {_f(sh_y - 8)} q{_f(-tw)} {_f((hip_y - sh_y) * .55)} {_f(-tw * 2 + 10)} {_f(hip_y - sh_y + 60)} l14 0 q{_f(tw)} {_f(-(hip_y - sh_y) * .6)} {_f(tw * 2 - 14)} {_f(-(hip_y - sh_y) - 48)}z" fill="{o["dupatta"]}" opacity=".9"/>')
    if o.get("number"):
        g.append(f'<text x="{_f(cx)}" y="{_f(sh_y + 80)}" font-size="54" font-weight="700" fill="#FFFFFF" text-anchor="middle" font-family="sans-serif">7</text>')
    if p["prop"] == "stethoscope":
        g.append(f'<path d="M{_f(cx - 30)} {_f(sh_y - 16)} q-10 70 20 92 M{_f(cx + 30)} {_f(sh_y - 16)} q10 70 -20 92" stroke="#37474F" stroke-width="4" fill="none"/>'
                 f'<circle cx="{_f(cx - 10)}" cy="{_f(sh_y + 80)}" r="11" fill="#90A4AE" stroke="#37474F" stroke-width="3"/>')
    if p["prop"] == "bag":
        g.append(f'<path d="M{_f(cx - sw + 10)} {_f(sh_y - 20)} l{_f(sw * 1.4)} {_f(hip_y - sh_y + 20)}" stroke="#4E342E" stroke-width="9"/>'
                 f'<rect x="{_f(cx + sw * .3)}" y="{_f(hip_y - 20)}" width="56" height="52" rx="6" fill="#6D4C41"/>')
    if "watch" in (p.get("accessories") or []):
        pass
    g.append("</g>")
    # --- front arm (right)
    r_prop = _prop(p["prop"], 1, top) if p["prop"] not in ("none", "stethoscope", "bag") else ""
    hand_kind = q.get("r_hand", "open")
    if r_prop:
        hand_kind = "fist"
    g.append(_limb(cx + sw, sh_y, q["r_sh"], ua, q["r_el"], fa, 1, 24 * (1 if m["width"] < 1.2 else 1.2), c_upper, c_fore, 14, skin, hand_kind, r_prop))
    # --- neck + head
    # neck with shadow under jaw
    g.append(f'<rect x="{_f(cx - 16)}" y="{_f(neck_top)}" width="32" height="40" rx="8" fill="{skin_d}"/>'
             f'<ellipse cx="{_f(cx)}" cy="{_f(neck_top + 4)}" rx="22" ry="6" fill="{_mix(skin_d, 0.85)}" opacity=".3"/>')
    tilt = float(q["head_tilt"])
    turn = max(-1.0, min(1.0, float(q["head_turn"])))
    g.append(f'<g transform="rotate({_f(tilt)} {_f(cx)} {_f(neck_top + 10)})">')
    g.append(f'<ellipse cx="{_f(cx - rx * .92)}" cy="{_f(hy + 4)}" rx="10" ry="14" fill="{skin_d}"/>'
             f'<ellipse cx="{_f(cx - rx * .92)}" cy="{_f(hy + 4)}" rx="6" ry="9" fill="{_mix(skin_d, 0.88)}" opacity=".35"/>'  # ear inner shadow
             f'<ellipse cx="{_f(cx + rx * .92)}" cy="{_f(hy + 4)}" rx="10" ry="14" fill="{skin_d}"/>'
             f'<ellipse cx="{_f(cx + rx * .92)}" cy="{_f(hy + 4)}" rx="6" ry="9" fill="{_mix(skin_d, 0.88)}" opacity=".35"/>')
    if "earrings" in (p.get("accessories") or []):
        g.append(f'<circle cx="{_f(cx - rx * .95)}" cy="{_f(hy + 20)}" r="4" fill="#FFD54F"/><circle cx="{_f(cx + rx * .95)}" cy="{_f(hy + 20)}" r="4" fill="#FFD54F"/>')
    jaw = 1.0 + 0.06 * float(q["mouth_open"])
    g.append(f'<ellipse cx="{_f(cx)}" cy="{_f(hy)}" rx="{_f(rx)}" ry="{_f(ry * jaw)}" fill="url(#sk)"/>'
             # subtle jaw shadow for depth
             f'<ellipse cx="{_f(cx)}" cy="{_f(hy + ry * jaw * 0.7)}" rx="{_f(rx * 0.75)}" ry="{_f(ry * 0.22)}" fill="{skin_d}" opacity=".18"/>')
    if p["age"] == "elderly":
        g.append(f'<path d="M{_f(cx - 30)} {_f(hy + 22)} q6 6 12 0 M{_f(cx + 18)} {_f(hy + 22)} q6 6 12 0 M{_f(cx - 14)} {_f(hy - 44)} h28" stroke="{skin_d}" stroke-width="2" fill="none"/>')
    if p["age"] == "child" or q.get("expr") == "happy":
        g.append(f'<circle cx="{_f(cx - 34)}" cy="{_f(hy + 16)}" r="9" fill="#F48FB1" opacity=".35"/><circle cx="{_f(cx + 34)}" cy="{_f(hy + 16)}" r="9" fill="#F48FB1" opacity=".35"/>')
    fx = cx + turn * 16
    # eyes
    eo = max(0.0, min(1.0, float(q["eye_open"])))
    for side in (-1, 1):
        ex = fx + side * 24 * (1 - abs(turn) * 0.12)
        ey = hy - 6
        g.append(f'<ellipse cx="{_f(ex)}" cy="{_f(ey)}" rx="11" ry="{_f(max(0.6, 7.5 * eo))}" fill="#FFFFFF"/>')
        # eyelid / lash line for depth
        if eo > 0.2:
            g.append(f'<path d="M{_f(ex - 12)} {_f(ey - 7.5 * eo)} q12 {_f(-2.5 * eo)} 24 0" stroke="{hair_c if p["hair"] != "bald" else "#3E2723"}" stroke-width="2.4" fill="none" stroke-linecap="round"/>')
        if eo > 0.12:
            ix = ex + float(q["gaze_x"]) * 4 + turn * 2
            iy = ey + float(q["gaze_y"]) * 3
            ir = 4.6 * min(1, eo + .3)
            g.append(f'<circle cx="{_f(ix)}" cy="{_f(iy)}" r="{_f(ir)}" fill="url(#ig)"/>'         # iris with gradient
                     f'<circle cx="{_f(ix)}" cy="{_f(iy)}" r="{_f(ir * 0.38)}" fill="#1B1B1B"/>'    # pupil
                     f'<circle cx="{_f(ix - 1.8)}" cy="{_f(iy - 1.8)}" r="2.0" fill="#FFFFFF"/>'    # main catchlight
                     f'<circle cx="{_f(ix + 1.4)}" cy="{_f(iy + 1.2)}" r="0.9" fill="#FFFFFF" opacity=".55"/>')  # secondary catchlight
        else:
            g.append(f'<path d="M{_f(ex - 10)} {_f(ey)} q10 4 20 0" stroke="{skin_d}" stroke-width="2.2" fill="none"/>')
        # brows
        b = float(q["brow"])
        inner = -b * 5 if q.get("expr") == "angry" else b * 5
        g.append(f'<path d="M{_f(ex - 13 * side)} {_f(ey - 20 - b * 5)} q{_f(13 * side)} {_f(-6 + (inner if q.get("expr") == "angry" else 0))} {_f(26 * side)} {_f(0 + (6 if q.get("expr") == "angry" else -b * 2))}" '
                 f'stroke="{hair_c if p["hair"] != "bald" else "#3E2723"}" stroke-width="3.4" fill="none" stroke-linecap="round"/>')
    if "glasses" in (p.get("accessories") or []) or "sunglasses" in (p.get("accessories") or []):
        dark = "sunglasses" in (p.get("accessories") or [])
        g.append(f'<g stroke="{p.get("glasses_color") or "#222"}" stroke-width="2.5" fill="{"#263238" if dark else "none"}" fill-opacity="{".85" if dark else "0"}">'
                 f'<rect x="{_f(fx - 38)}" y="{_f(hy - 18)}" width="28" height="22" rx="6"/><rect x="{_f(fx + 10)}" y="{_f(hy - 18)}" width="28" height="22" rx="6"/>'
                 f'<path d="M{_f(fx - 10)} {_f(hy - 8)} h20 M{_f(fx - 38)} {_f(hy - 10)} h-18 M{_f(fx + 38)} {_f(hy - 10)} h18"/></g>')
    # cheek blush (subtle warmth)
    blush_op = ".12" if p["age"] == "child" else ".06"
    g.append(f'<ellipse cx="{_f(fx - 26)}" cy="{_f(hy + 12)}" rx="14" ry="9" fill="#E57373" opacity="{blush_op}"/>'
             f'<ellipse cx="{_f(fx + 26)}" cy="{_f(hy + 12)}" rx="14" ry="9" fill="#E57373" opacity="{blush_op}"/>')
    # nose — bridge highlight + shadow
    g.append(f'<path d="M{_f(fx + 2)} {_f(hy + 2)} q6 12 -4 14" stroke="{skin_d}" stroke-width="2.4" fill="none" stroke-linecap="round"/>'
             f'<path d="M{_f(fx - 1)} {_f(hy - 6)} q1 8 0 14" stroke="#FFFFFF" stroke-width="1.2" fill="none" opacity=".2" stroke-linecap="round"/>')
    if "bindi" in (p.get("accessories") or []):
        g.append(f'<circle cx="{_f(fx)}" cy="{_f(hy - 36)}" r="4" fill="#C62828"/>')
    # facial hair + mouth
    k = 1.0 if p["age"] != "child" else 0.8
    if p["facial"] in ("beard", "full", "stubble"):
        g.append(f'<path d="M{_f(cx - rx + 8)} {_f(hy + 6)} q{_f(rx - 8)} {_f(ry * 1.05)} {_f(2 * rx - 16)} 0 v{_f(-ry * .2)} q{_f(-(rx - 8))} {_f(ry * .55)} {_f(-(2 * rx - 16))} 0z" fill="{hair_c}" opacity="{".45" if p["facial"] == "stubble" else ".95"}"/>')
        if p["facial"] == "full":
            g.append(f'<path d="M{_f(cx - rx + 6)} {_f(hy + 10)} q{_f(rx - 6)} {_f(ry * 1.5)} {_f(2 * rx - 12)} 0" fill="{hair_c}"/>')
    if o.get("mask") or "mask" in (p.get("accessories") or []):
        g.append(f'<path d="M{_f(cx - 40)} {_f(hy + 14)} h80 q6 30 -10 44 h-60 q-16 -14 -10 -44z" fill="#80CBC4"/><path d="M{_f(cx - 40)} {_f(hy + 18)} l-18 -8 M{_f(cx + 40)} {_f(hy + 18)} l18 -8" stroke="#80CBC4" stroke-width="3"/>')
    else:
        g.append(_mouth(fx, hy + 34 * k, str(q.get("viseme") or "rest"), float(q["mouth_open"]), float(q["smile"]), k, skin))
        if p["facial"] in ("moustache", "full"):
            g.append(f'<path d="M{_f(fx - 24)} {_f(hy + 28)} q12 -14 24 -2 q12 -12 24 2 q-12 8 -24 2 q-12 6 -24 -2z" fill="{hair_c}"/>')
    # hair front, hat
    g.append(_hair_front(p, cx, hy, rx, ry, hair_c))
    # hair highlight sheen for depth
    if p["hair"] not in ("bald", "buzz"):
        g.append(f'<ellipse cx="{_f(cx - 8)}" cy="{_f(hy - ry * 0.55)}" rx="{_f(rx * 0.45)}" ry="{_f(ry * 0.25)}" fill="#FFFFFF" opacity=".1"/>')
    if p["hat"] != "none":
        g.append(_hat(p["hat"], cx, hy, rx, ry, top if p["hat"] in ("cap", "hat") else "#F57C00" if p["hat"] == "turban" else top))
    g.append("</g>")
    # --- assemble, scaled about the ground point, optional mirror
    s = float(m["scale"]) * (1.0 - 0.06 * float(q.get("squash", 0)))
    body_svg = "".join(x for x in g if x)
    tf = f"translate({_f(cx)},{GROUND}) scale({_f(s)}) translate({_f(-cx)},{-GROUND})"
    if float(q.get("flip", 0)) > 0.5:
        tf = f"translate({VIEW_W},0) scale(-1,1) " + tf
    inner = f'<g transform="{tf}">{body_svg}</g>'
    if bare:
        return inner
    w = width or VIEW_W
    h = height or VIEW_H
    defs = _defs(skin, skin_d, hair_c, top, bottom)
    # ground contact shadow — soft ellipse beneath feet
    shadow = f'<ellipse cx="{_f(cx)}" cy="{_f(GROUND + 6)}" rx="{_f(62 * s)}" ry="{_f(10 * s)}" fill="#000" opacity=".12"/>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {VIEW_W} {VIEW_H}" '
            f'preserveAspectRatio="xMidYMax meet">{defs}{shadow}{inner}</svg>')
