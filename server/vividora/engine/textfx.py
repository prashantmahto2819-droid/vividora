"""Text on video: templates, animations and the ASS (libass) compiler.

One description drives both the editor preview (web/dist/assets/textfx.js reads
the same tables from /api/presets) and the final render, so what the creator sees
is what gets burned in.

An animation is a list of keyframes over its phase (0 → 1):
    [[t, {prop: value, ...}, easing], ...]
props (missing = resting value):
    x, y      offset as a fraction of frame width / height
    sx, sy    scale (1 = 100 %)
    rz        rotation in degrees (counter-clockwise, like ASS \\frz)
    rx, ry    3-D tilt in degrees
    a         opacity 0…1
    blur      blur in pixels at 1080 p
    fax       horizontal shear
    w         mix towards white 0…1 (flash)
    cl, cr    visible part, left / right edge, as a fraction of the text box (wipes)
    ct, cb    same, top / bottom
"in" animations end at rest, "out" animations start at rest, "loop" animations
repeat every `period` ms while the text is on screen. "unit" animations reveal the
text letter by letter or word by word.
"""

from __future__ import annotations

import math
import unicodedata

REST = {"x": 0.0, "y": 0.0, "sx": 1.0, "sy": 1.0, "rz": 0.0, "rx": 0.0, "ry": 0.0, "a": 1.0, "blur": 0.0,
        "fax": 0.0, "w": 0.0, "cl": 0.0, "cr": 1.0, "ct": 0.0, "cb": 1.0}

# ---------------------------------------------------------------- animations
ANIM_IN: dict[str, dict] = {
    "none": {"label": "कोई नहीं", "cat": "basic", "kf": []},
    "fade": {"label": "Fade", "cat": "basic", "kf": [[0, {"a": 0}], [1, {}, "out"]]},
    "pop": {"label": "Pop", "cat": "basic", "kf": [[0, {"sx": .4, "sy": .4, "a": 0}], [.6, {"sx": 1.12, "sy": 1.12}, "out"], [1, {}, "inout"]]},
    "zoom_in": {"label": "Zoom in", "cat": "zoom", "kf": [[0, {"sx": .2, "sy": .2, "a": 0}], [1, {}, "out"]]},
    "zoom_out": {"label": "Zoom out (बड़े से)", "cat": "zoom", "kf": [[0, {"sx": 2.5, "sy": 2.5, "a": 0}], [1, {}, "out"]]},
    "zoom_blur": {"label": "Zoom blur", "cat": "zoom", "kf": [[0, {"sx": 1.6, "sy": 1.6, "blur": 14, "a": 0}], [1, {}, "out"]]},
    "elastic": {"label": "Elastic", "cat": "zoom", "kf": [[0, {"sx": 0, "sy": 0}], [.4, {"sx": 1.25, "sy": 1.25}, "out"], [.6, {"sx": .9, "sy": .9}, "inout"], [.8, {"sx": 1.06, "sy": 1.06}, "inout"], [1, {}, "inout"]]},
    "stretch": {"label": "Stretch", "cat": "zoom", "kf": [[0, {"sx": 2.4, "sy": .4, "a": 0}], [1, {}, "back"]]},
    "squeeze": {"label": "Squeeze", "cat": "zoom", "kf": [[0, {"sx": .2, "sy": 1.8, "a": 0}], [1, {}, "back"]]},
    "slide_up": {"label": "Slide up", "cat": "slide", "kf": [[0, {"y": .08, "a": 0}], [1, {}, "out"]]},
    "slide_down": {"label": "Slide down", "cat": "slide", "kf": [[0, {"y": -.08, "a": 0}], [1, {}, "out"]]},
    "slide_left": {"label": "Slide ← (दाएँ से)", "cat": "slide", "kf": [[0, {"x": .15, "a": 0}], [1, {}, "out"]]},
    "slide_right": {"label": "Slide → (बाएँ से)", "cat": "slide", "kf": [[0, {"x": -.15, "a": 0}], [1, {}, "out"]]},
    "fly_left": {"label": "Fly in ←", "cat": "slide", "kf": [[0, {"x": 1.0}], [1, {}, "back"]]},
    "fly_right": {"label": "Fly in →", "cat": "slide", "kf": [[0, {"x": -1.0}], [1, {}, "back"]]},
    "fly_up": {"label": "Fly in ↑", "cat": "slide", "kf": [[0, {"y": .6}], [1, {}, "back"]]},
    "fly_down": {"label": "Fly in ↓", "cat": "slide", "kf": [[0, {"y": -.6}], [1, {}, "back"]]},
    "lift": {"label": "Lift (हल्का ऊपर)", "cat": "slide", "kf": [[0, {"y": .025, "a": 0}], [1, {}, "out"]]},
    "drop_bounce": {"label": "आसमान से गिरे", "cat": "bounce", "kf": [[0, {"y": -.4}], [.55, {"sy": .8, "sx": 1.1}, "in"], [.75, {"sy": 1.1, "sx": .95}, "out"], [1, {}, "inout"]]},
    "rise_bounce": {"label": "नीचे से उछले", "cat": "bounce", "kf": [[0, {"y": .4}], [.55, {"sy": 1.15, "sx": .9}, "out"], [.75, {"sy": .92, "sx": 1.05}, "inout"], [1, {}, "inout"]]},
    "bounce_in": {"label": "Bounce", "cat": "bounce", "kf": [[0, {"y": -.12, "a": 0}], [.45, {"y": 0, "a": 1}, "in"], [.65, {"y": -.03}, "out"], [.82, {"y": 0}, "in"], [.92, {"y": -.008}, "out"], [1, {}, "in"]]},
    "rotate_in": {"label": "Rotate in", "cat": "rotate", "kf": [[0, {"rz": -90, "a": 0}], [1, {}, "out"]]},
    "spin_in": {"label": "Spin in", "cat": "rotate", "kf": [[0, {"rz": 360, "sx": .2, "sy": .2, "a": 0}], [1, {}, "out"]]},
    "swing_in": {"label": "Swing", "cat": "rotate", "kf": [[0, {"rz": 25, "a": 0}], [.5, {"rz": -10, "a": 1}, "out"], [.8, {"rz": 4}, "inout"], [1, {}, "inout"]]},
    "flip_x": {"label": "Flip ↔", "cat": "3d", "kf": [[0, {"sx": 0}], [1, {}, "out"]]},
    "flip_y": {"label": "Flip ↕", "cat": "3d", "kf": [[0, {"sy": 0}], [1, {}, "out"]]},
    "flip_3d": {"label": "3D flip", "cat": "3d", "kf": [[0, {"ry": 90, "a": 0}], [1, {}, "out"]]},
    "tilt_in": {"label": "3D tilt", "cat": "3d", "kf": [[0, {"rx": 80, "a": 0}], [1, {}, "out"]]},
    "blur_in": {"label": "Blur in", "cat": "light", "kf": [[0, {"blur": 25, "a": 0}], [1, {}, "out"]]},
    "color_flash": {"label": "Flash", "cat": "light", "kf": [[0, {"w": 1, "blur": 10}], [1, {}, "out"]]},
    "flicker_in": {"label": "Neon flicker", "cat": "light", "kf": [[0, {"a": 0}], [.15, {"a": 1}, "step"], [.25, {"a": 0}, "step"], [.4, {"a": 1}, "step"], [.5, {"a": .2}, "step"], [.7, {"a": 1}, "step"], [1, {}, "step"]]},
    "glitch_in": {"label": "Glitch", "cat": "light", "kf": [[0, {"a": 0, "x": .02, "fax": .3}], [.2, {"a": 1, "x": -.02, "fax": -.3}, "step"], [.4, {"x": .015, "fax": .2}, "step"], [.6, {"x": -.01, "fax": -.1}, "step"], [.8, {"x": .005}, "step"], [1, {}, "step"]]},
    "shake_in": {"label": "Shake", "cat": "light", "kf": [[0, {"x": -.03, "a": 0}], [.2, {"x": .03, "a": 1}], [.4, {"x": -.02}], [.6, {"x": .015}], [.8, {"x": -.008}], [1, {}]]},
    "wipe_right": {"label": "Wipe →", "cat": "wipe", "kf": [[0, {"cr": 0}], [1, {}, "inout"]]},
    "wipe_left": {"label": "Wipe ←", "cat": "wipe", "kf": [[0, {"cl": 1}], [1, {}, "inout"]]},
    "wipe_down": {"label": "Wipe ↓", "cat": "wipe", "kf": [[0, {"cb": 0}], [1, {}, "inout"]]},
    "wipe_up": {"label": "Wipe ↑", "cat": "wipe", "kf": [[0, {"ct": 1}], [1, {}, "inout"]]},
    "reveal_center": {"label": "बीच से खुले", "cat": "wipe", "kf": [[0, {"cl": .5, "cr": .5}], [1, {}, "out"]]},
    "typewriter": {"label": "Typewriter", "cat": "letters", "unit": "char", "step": True, "from": {"a": 0}, "stagger": 1.0},
    "letter_fade": {"label": "अक्षर-अक्षर fade", "cat": "letters", "unit": "char", "from": {"a": 0}, "stagger": .75},
    "letter_pop": {"label": "अक्षर pop", "cat": "letters", "unit": "char", "from": {"sx": 2.2, "sy": 2.2, "a": 0}, "stagger": .7},
    "letter_blur": {"label": "अक्षर blur", "cat": "letters", "unit": "char", "from": {"blur": 20, "a": 0}, "stagger": .7},
    "word_fade": {"label": "शब्द-शब्द fade", "cat": "letters", "unit": "word", "from": {"a": 0}, "stagger": .75},
    "word_pop": {"label": "शब्द pop", "cat": "letters", "unit": "word", "from": {"sx": .3, "sy": .3, "a": 0}, "stagger": .7},
    "word_flash": {"label": "शब्द flash", "cat": "letters", "unit": "word", "from": {"w": 1, "a": 0}, "stagger": .7},
}


def _mirror(kf: list) -> list:
    """An in-animation played backwards (rest → start state)."""
    out = []
    for i, k in enumerate(reversed(kf)):
        t = 1 - k[0]
        ease = kf[len(kf) - i - 1][2] if len(kf[len(kf) - i - 1]) > 2 else "lin"
        flip = {"out": "in", "in": "out"}.get(ease, ease)
        out.append([t, k[1], flip] if i else [t, k[1]])
    return out


ANIM_OUT: dict[str, dict] = {
    "none": {"label": "कोई नहीं", "cat": "basic", "kf": []},
    "fade": {"label": "Fade", "cat": "basic", "kf": [[0, {}], [1, {"a": 0}, "in"]]},
    "pop_out": {"label": "Pop out", "cat": "basic", "kf": [[0, {}], [.4, {"sx": 1.12, "sy": 1.12}, "out"], [1, {"sx": 0, "sy": 0, "a": 0}, "in"]]},
    "grow_out": {"label": "Grow & fade", "cat": "zoom", "kf": [[0, {}], [1, {"sx": 2.5, "sy": 2.5, "a": 0}, "in"]]},
    "shrink": {"label": "Shrink", "cat": "zoom", "kf": [[0, {}], [1, {"sx": .1, "sy": .1, "a": 0}, "in"]]},
    "zoom_blur_out": {"label": "Zoom blur", "cat": "zoom", "kf": [[0, {}], [1, {"sx": 1.6, "sy": 1.6, "blur": 14, "a": 0}, "in"]]},
    "stretch_out": {"label": "Stretch", "cat": "zoom", "kf": [[0, {}], [1, {"sx": 2.4, "sy": .3, "a": 0}, "in"]]},
    "squeeze_out": {"label": "Squeeze", "cat": "zoom", "kf": [[0, {}], [1, {"sx": .1, "sy": 1.8, "a": 0}, "in"]]},
    "slide_up_out": {"label": "Slide up", "cat": "slide", "kf": [[0, {}], [1, {"y": -.08, "a": 0}, "in"]]},
    "slide_down_out": {"label": "Slide down", "cat": "slide", "kf": [[0, {}], [1, {"y": .08, "a": 0}, "in"]]},
    "slide_left_out": {"label": "Slide ←", "cat": "slide", "kf": [[0, {}], [1, {"x": -.15, "a": 0}, "in"]]},
    "slide_right_out": {"label": "Slide →", "cat": "slide", "kf": [[0, {}], [1, {"x": .15, "a": 0}, "in"]]},
    "fly_left_out": {"label": "Fly out ←", "cat": "slide", "kf": [[0, {}], [.25, {"x": .03}, "out"], [1, {"x": -1.0}, "in"]]},
    "fly_right_out": {"label": "Fly out →", "cat": "slide", "kf": [[0, {}], [.25, {"x": -.03}, "out"], [1, {"x": 1.0}, "in"]]},
    "fly_up_out": {"label": "Fly out ↑", "cat": "slide", "kf": [[0, {}], [.25, {"y": .03}, "out"], [1, {"y": -.6}, "in"]]},
    "drop_out": {"label": "नीचे गिरे", "cat": "slide", "kf": [[0, {}], [.3, {"y": -.03}, "out"], [1, {"y": .6, "a": 0}, "in"]]},
    "rotate_out": {"label": "Rotate out", "cat": "rotate", "kf": [[0, {}], [1, {"rz": 90, "a": 0}, "in"]]},
    "spin_out": {"label": "Spin out", "cat": "rotate", "kf": [[0, {}], [1, {"rz": -360, "sx": .2, "sy": .2, "a": 0}, "in"]]},
    "flip_x_out": {"label": "Flip ↔", "cat": "3d", "kf": [[0, {}], [1, {"sx": 0}, "in"]]},
    "flip_y_out": {"label": "Flip ↕", "cat": "3d", "kf": [[0, {}], [1, {"sy": 0}, "in"]]},
    "flip_3d_out": {"label": "3D flip", "cat": "3d", "kf": [[0, {}], [1, {"ry": -90, "a": 0}, "in"]]},
    "blur_out": {"label": "Blur out", "cat": "light", "kf": [[0, {}], [1, {"blur": 25, "a": 0}, "in"]]},
    "flash_out": {"label": "Flash out", "cat": "light", "kf": [[0, {}], [.5, {"w": 1, "blur": 6}, "in"], [1, {"w": 1, "a": 0, "blur": 12}]]},
    "flicker_out": {"label": "Flicker", "cat": "light", "kf": [[0, {}], [.2, {"a": .1}, "step"], [.35, {"a": 1}, "step"], [.55, {"a": 0}, "step"], [.7, {"a": .8}, "step"], [1, {"a": 0}, "step"]]},
    "glitch_out": {"label": "Glitch", "cat": "light", "kf": [[0, {}], [.2, {"x": .015, "fax": .2}, "step"], [.4, {"x": -.02, "fax": -.3}, "step"], [.6, {"x": .02, "fax": .3, "a": .6}, "step"], [.8, {"x": -.01, "a": .3}, "step"], [1, {"a": 0}, "step"]]},
    "wipe_right_out": {"label": "Wipe →", "cat": "wipe", "kf": [[0, {}], [1, {"cl": 1}, "inout"]]},
    "wipe_left_out": {"label": "Wipe ←", "cat": "wipe", "kf": [[0, {}], [1, {"cr": 0}, "inout"]]},
    "wipe_up_out": {"label": "Wipe ↑", "cat": "wipe", "kf": [[0, {}], [1, {"cb": 0}, "inout"]]},
    "wipe_down_out": {"label": "Wipe ↓", "cat": "wipe", "kf": [[0, {}], [1, {"ct": 1}, "inout"]]},
    "collapse": {"label": "बीच में बंद", "cat": "wipe", "kf": [[0, {}], [1, {"cl": .5, "cr": .5}, "in"]]},
    "typewriter_out": {"label": "Typewriter मिटे", "cat": "letters", "unit": "char", "step": True, "to": {"a": 0}, "stagger": 1.0, "reverse": True},
    "letter_fade_out": {"label": "अक्षर-अक्षर fade", "cat": "letters", "unit": "char", "to": {"a": 0}, "stagger": .75},
    "word_out": {"label": "शब्द-शब्द गायब", "cat": "letters", "unit": "word", "to": {"a": 0, "sx": .4, "sy": .4}, "stagger": .7},
}

ANIM_LOOP: dict[str, dict] = {
    "none": {"label": "कोई नहीं", "cat": "basic", "period": 1000, "kf": []},
    "pulse": {"label": "Pulse", "cat": "scale", "period": 900, "kf": [[0, {}], [.5, {"sx": 1.08, "sy": 1.08}, "inout"], [1, {}, "inout"]]},
    "heartbeat": {"label": "Heartbeat ❤", "cat": "scale", "period": 1100, "kf": [[0, {}], [.12, {"sx": 1.12, "sy": 1.12}, "out"], [.24, {}, "in"], [.36, {"sx": 1.09, "sy": 1.09}, "out"], [.5, {}, "in"], [1, {}]]},
    "breathe": {"label": "Breathe (धीमा)", "cat": "scale", "period": 2600, "kf": [[0, {}], [.5, {"sx": 1.04, "sy": 1.04}, "inout"], [1, {}, "inout"]]},
    "zoom_slow": {"label": "धीरे-धीरे बड़ा", "cat": "scale", "span": True, "kf": [[0, {}], [1, {"sx": 1.15, "sy": 1.15}, "lin"]]},
    "float": {"label": "Float (तैरे)", "cat": "move", "period": 2000, "kf": [[0, {}], [.5, {"y": -.012}, "inout"], [1, {}, "inout"]]},
    "bob": {"label": "Bob", "cat": "move", "period": 700, "kf": [[0, {}], [.5, {"y": -.006}, "inout"], [1, {}, "inout"]]},
    "shake": {"label": "Shake", "cat": "move", "period": 140, "kf": [[0, {"x": -.003}], [.5, {"x": .003}], [1, {"x": -.003}]]},
    "jitter": {"label": "Jitter", "cat": "move", "period": 240, "kf": [[0, {}], [.25, {"x": .003, "y": -.002}, "step"], [.5, {"x": -.002, "y": .003}, "step"], [.75, {"x": .002, "y": .002}, "step"], [1, {}, "step"]]},
    "wiggle": {"label": "Wiggle", "cat": "rotate", "period": 500, "kf": [[0, {}], [.25, {"rz": 3}, "inout"], [.75, {"rz": -3}, "inout"], [1, {}, "inout"]]},
    "swing": {"label": "Swing", "cat": "rotate", "period": 1600, "kf": [[0, {}], [.25, {"rz": 6}, "inout"], [.75, {"rz": -6}, "inout"], [1, {}, "inout"]]},
    "rotate": {"label": "घूमे", "cat": "rotate", "period": 4000, "kf": [[0, {}], [1, {"rz": -360}, "lin"]]},
    "tilt": {"label": "3D tilt", "cat": "rotate", "period": 2000, "kf": [[0, {}], [.25, {"ry": 15}, "inout"], [.75, {"ry": -15}, "inout"], [1, {}, "inout"]]},
    "flicker": {"label": "Flicker", "cat": "light", "period": 600, "kf": [[0, {}], [.3, {"a": .45}, "step"], [.4, {}, "step"], [.75, {"a": .7}, "step"], [.85, {}, "step"], [1, {}]]},
    "blink": {"label": "Blink", "cat": "light", "period": 900, "kf": [[0, {}], [.6, {"a": 0}, "step"], [1, {}, "step"]]},
    "glow": {"label": "Glow pulse", "cat": "light", "period": 1400, "kf": [[0, {}], [.5, {"blur": 6}, "inout"], [1, {}, "inout"]]},
    "shine": {"label": "Shine (चमक)", "cat": "light", "period": 1200, "kf": [[0, {}], [.5, {"w": .55}, "inout"], [1, {}, "inout"]]},
}

ANIM_CATS = {"basic": "Basic", "zoom": "Zoom", "slide": "Slide", "bounce": "Bounce", "rotate": "Rotate", "3d": "3D",
             "light": "Light / Glitch", "wipe": "Wipe", "letters": "अक्षर / शब्द", "scale": "Scale", "move": "Move"}

# legacy single "anim" values from older projects → (in, out, loop)
LEGACY = {"none": ("none", "none", "none"), "fade": ("fade", "fade", "none"), "pop": ("pop", "fade", "none"),
          "slide_up": ("slide_up", "fade", "none"), "slide_left": ("slide_left", "fade", "none"),
          "zoom_out": ("zoom_out", "fade", "none"), "typewriter": ("typewriter", "fade", "none"),
          "bounce": ("bounce_in", "fade", "none"), "glow": ("fade", "fade", "glow"), "shake": ("shake_in", "fade", "none")}

# ---------------------------------------------------------------- text styles / templates
STYLE_KEYS = ("font", "size", "color", "bold", "italic", "underline", "spacing", "outline", "outline_w", "shadow",
              "shadow_d", "box", "box_color", "box_alpha", "box_pad", "rotate", "opacity", "align", "pos", "x", "y")

_STYLES = [
    # id, label, category, style
    ("bold_white", "Bold white", "heading", {"font": "Poppins", "size": .085, "color": "#FFFFFF", "outline": "#000000", "outline_w": .006, "shadow": "#000000", "shadow_d": .004}),
    ("yellow_punch", "Yellow punch", "heading", {"font": "Poppins", "size": .095, "color": "#FFD400", "outline": "#000000", "outline_w": .009}),
    ("red_box", "Red box", "highlight", {"font": "Poppins", "size": .065, "color": "#FFFFFF", "box": True, "box_color": "#E5252A", "box_pad": .018}),
    ("black_box_yellow", "Black box", "highlight", {"font": "Poppins", "size": .065, "color": "#FFD400", "box": True, "box_color": "#000000", "box_alpha": .15, "box_pad": .018}),
    ("white_box", "White box", "highlight", {"font": "Poppins", "size": .062, "color": "#111111", "box": True, "box_color": "#FFFFFF", "box_pad": .016}),
    ("marker", "Highlighter", "highlight", {"font": "Mukta", "size": .07, "color": "#111111", "box": True, "box_color": "#FFE066", "box_pad": .012}),
    ("neon_cyan", "Neon cyan", "neon", {"font": "Poppins", "size": .08, "color": "#E8FFFF", "outline": "#00E5FF", "outline_w": .004, "shadow": "#00E5FF", "shadow_d": 0}),
    ("neon_pink", "Neon pink", "neon", {"font": "Poppins", "size": .08, "color": "#FFE8F6", "outline": "#FF2D95", "outline_w": .004}),
    ("neon_green", "Neon green", "neon", {"font": "Poppins", "size": .08, "color": "#EFFFE8", "outline": "#39FF14", "outline_w": .004}),
    ("gold", "Gold premium", "premium", {"font": "Baloo 2", "size": .09, "color": "#F2C14E", "outline": "#3B2A07", "outline_w": .007, "shadow": "#000000", "shadow_d": .005}),
    ("saffron", "केसरिया", "premium", {"font": "Baloo 2", "size": .09, "color": "#FF9933", "outline": "#FFFFFF", "outline_w": .007}),
    ("royal", "Royal purple", "premium", {"font": "Baloo 2", "size": .085, "color": "#FFFFFF", "outline": "#5B21B6", "outline_w": .009}),
    ("news_red", "News lower third", "news", {"font": "Hind", "size": .05, "color": "#FFFFFF", "box": True, "box_color": "#C8102E", "box_pad": .014, "pos": "bottom"}),
    ("news_blue", "News blue", "news", {"font": "Hind", "size": .05, "color": "#FFFFFF", "box": True, "box_color": "#0B3D91", "box_pad": .014, "pos": "bottom"}),
    ("breaking", "Breaking", "news", {"font": "Poppins", "size": .075, "color": "#FFFFFF", "box": True, "box_color": "#D00000", "box_pad": .02, "pos": "top"}),
    ("quote_serif", "Quote (serif)", "quote", {"font": "Lora", "size": .062, "color": "#FFFFFF", "italic": True, "shadow": "#000000", "shadow_d": .003, "bold": False}),
    ("quote_hindi", "विचार", "quote", {"font": "FreeSerif", "size": .068, "color": "#FFF7E0", "shadow": "#000000", "shadow_d": .004}),
    ("cinematic", "Cinematic", "minimal", {"font": "Poppins", "size": .055, "color": "#FFFFFF", "spacing": .02, "bold": False}),
    ("minimal_dark", "Minimal dark", "minimal", {"font": "Poppins", "size": .055, "color": "#111111", "bold": True}),
    ("big_number", "बड़ा नंबर", "number", {"font": "Poppins", "size": .2, "color": "#FFD400", "outline": "#000000", "outline_w": .012}),
    ("list_item", "List point", "number", {"font": "Mukta", "size": .065, "color": "#FFFFFF", "box": True, "box_color": "#1F2937", "box_alpha": .2, "box_pad": .014}),
    ("comic", "Comic", "fun", {"font": "Baloo 2", "size": .1, "color": "#FF3B30", "outline": "#FFFFFF", "outline_w": .012, "rotate": -4}),
    ("stamp", "Stamp", "fun", {"font": "Poppins", "size": .075, "color": "#E11D48", "outline": "#E11D48", "outline_w": .002, "rotate": -10}),
    ("retro", "Retro", "fun", {"font": "Baloo 2", "size": .09, "color": "#FFB703", "shadow": "#9A3412", "shadow_d": .01}),
    ("cta_red", "Subscribe button", "cta", {"font": "Poppins", "size": .06, "color": "#FFFFFF", "box": True, "box_color": "#FF0000", "box_pad": .02}),
    ("cta_insta", "Insta follow", "cta", {"font": "Poppins", "size": .06, "color": "#FFFFFF", "box": True, "box_color": "#C13584", "box_pad": .02}),
    ("whatsapp", "WhatsApp green", "cta", {"font": "Hind", "size": .06, "color": "#FFFFFF", "box": True, "box_color": "#25D366", "box_pad": .018}),
    ("question", "सवाल", "hook", {"font": "Baloo 2", "size": .085, "color": "#FFFFFF", "outline": "#7C3AED", "outline_w": .008}),
    ("warning", "चेतावनी", "hook", {"font": "Poppins", "size": .075, "color": "#111111", "box": True, "box_color": "#FACC15", "box_pad": .02}),
    ("success", "Success green", "hook", {"font": "Mukta", "size": .08, "color": "#22C55E", "outline": "#052E16", "outline_w": .008}),
]

_TEXTS = {
    "heading": [("hi", "ज़िंदगी बदल देगी ये बात"), ("hi", "सफलता का असली राज़"), ("en", "THIS CHANGED MY LIFE"), ("en", "Stop Doing This")],
    "highlight": [("hi", "सबसे ज़रूरी बात"), ("hi", "ध्यान से सुनो"), ("en", "Key point"), ("en", "Remember this")],
    "neon": [("hi", "रात की बात"), ("hi", "नया सफ़र"), ("en", "NIGHT MODE"), ("en", "Level Up")],
    "premium": [("hi", "राजा बनो"), ("hi", "शुभ आरंभ"), ("en", "PREMIUM"), ("en", "The Golden Rule")],
    "news": [("hi", "ताज़ा ख़बर | आज की बड़ी अपडेट"), ("hi", "प्रशांत महतो | मोटिवेशनल स्पीकर"), ("en", "Breaking | Big update today"), ("en", "Your Name | Creator")],
    "quote": [("hi", "“मेहनत कभी बेकार नहीं जाती”"), ("hi", "“जो रुकता नहीं, वही जीतता है”"), ("en", "“Dream big, start small”"), ("en", "“Discipline beats talent”")],
    "minimal": [("hi", "एक नई शुरुआत"), ("hi", "बस इतना ही"), ("en", "A new beginning"), ("en", "Chapter One")],
    "number": [("hi", "1"), ("hi", "नंबर 1 | पहली आदत"), ("en", "3"), ("en", "Tip #2")],
    "fun": [("hi", "वाह!"), ("hi", "क्या बात है!"), ("en", "WOW!"), ("en", "OMG")],
    "cta": [("hi", "▶ सब्सक्राइब करें"), ("hi", "फ़ॉलो करें"), ("en", "▶ SUBSCRIBE"), ("en", "+ FOLLOW")],
    "hook": [("hi", "क्या आप जानते हैं?"), ("hi", "ये गलती मत करना!"), ("en", "Did you know?"), ("en", "Don't make this mistake!")],
}

_ANIM_BY_CAT = {
    "heading": [("pop", "fade", "none"), ("drop_bounce", "fly_up_out", "none"), ("zoom_out", "blur_out", "pulse"), ("word_pop", "word_out", "none")],
    "highlight": [("wipe_right", "wipe_right_out", "none"), ("stretch", "shrink", "none"), ("slide_up", "slide_down_out", "none"), ("reveal_center", "collapse", "none")],
    "neon": [("flicker_in", "flicker_out", "flicker"), ("blur_in", "blur_out", "glow"), ("color_flash", "flash_out", "glow"), ("glitch_in", "glitch_out", "jitter")],
    "premium": [("letter_fade", "fade", "shine"), ("zoom_blur", "zoom_blur_out", "breathe"), ("flip_3d", "flip_3d_out", "none"), ("spin_in", "spin_out", "none")],
    "news": [("slide_right", "slide_left_out", "none"), ("wipe_right", "wipe_left_out", "none"), ("fly_right", "fly_left_out", "none"), ("reveal_center", "collapse", "none")],
    "quote": [("word_fade", "fade", "none"), ("letter_fade", "letter_fade_out", "float"), ("blur_in", "blur_out", "breathe"), ("typewriter", "fade", "none")],
    "minimal": [("lift", "fade", "none"), ("fade", "fade", "zoom_slow"), ("letter_blur", "blur_out", "none"), ("wipe_up", "wipe_down_out", "none")],
    "number": [("elastic", "pop_out", "heartbeat"), ("spin_in", "shrink", "none"), ("slide_left", "slide_left_out", "none"), ("flip_x", "flip_x_out", "none")],
    "fun": [("elastic", "pop_out", "wiggle"), ("drop_bounce", "drop_out", "bob"), ("shake_in", "spin_out", "shake"), ("squeeze", "stretch_out", "pulse")],
    "cta": [("pop", "pop_out", "pulse"), ("rise_bounce", "drop_out", "heartbeat"), ("bounce_in", "shrink", "pulse"), ("elastic", "pop_out", "bob")],
    "hook": [("zoom_out", "fade", "shake"), ("typewriter", "typewriter_out", "none"), ("swing_in", "rotate_out", "wiggle"), ("word_flash", "word_out", "none")],
}

TEMPLATE_CATS = {"heading": "Heading", "highlight": "Highlight / Box", "neon": "Neon", "premium": "Premium / Gold",
                 "news": "News / Lower third", "quote": "Quote / विचार", "minimal": "Minimal", "number": "Number / List",
                 "fun": "Fun / Comic", "cta": "CTA / Subscribe", "hook": "Hook / सवाल"}


def _templates() -> list[dict]:
    out = []
    for sid, label, cat, st in _STYLES:
        for i, (lang, text) in enumerate(_TEXTS[cat]):
            a_in, a_out, a_loop = _ANIM_BY_CAT[cat][(i + len(out)) % len(_ANIM_BY_CAT[cat])]
            font = st.get("font", "Poppins")
            if lang == "hi" and font in ("Poppins", "Lora"):
                font = "Baloo 2" if cat in ("fun", "number", "heading") else "Mukta"
            if lang == "en" and font in ("FreeSerif",):
                font = "Lora"
            out.append({"id": f"{sid}_{i}", "label": label, "cat": cat, "lang": lang, "text": text,
                        "style": {"pos": "center", **st, "font": font},
                        "anim_in": a_in, "anim_out": a_out, "anim_loop": a_loop})
    return out


TEMPLATES = _templates()


def presets_json() -> dict:
    return {"anim_in": ANIM_IN, "anim_out": ANIM_OUT, "anim_loop": ANIM_LOOP, "anim_cats": ANIM_CATS,
            "templates": TEMPLATES, "template_cats": TEMPLATE_CATS}


# ---------------------------------------------------------------- keyframe maths (mirrored in textfx.js)
def ease(name: str | None, u: float) -> float:
    u = max(0.0, min(1.0, u))
    if name == "out":
        return 1 - (1 - u) ** 3
    if name == "in":
        return u ** 3
    if name == "inout":
        return 4 * u ** 3 if u < .5 else 1 - (-2 * u + 2) ** 3 / 2
    if name == "back":
        c1, c3 = 1.70158, 2.70158
        return 1 + c3 * (u - 1) ** 3 + c1 * (u - 1) ** 2
    if name == "step":
        return 0.0 if u < 1 else 1.0
    return u


def state(kf: list, p: float) -> dict:
    """Props at progress p (0…1) of a keyframe list; untouched props stay at rest."""
    s = dict(REST)
    if not kf:
        return s
    full = []
    prev = dict(REST)
    for k in kf:
        cur = {**REST, **k[1]} if not full else {**REST, **k[1]}
        full.append((float(k[0]), cur, k[2] if len(k) > 2 else "lin"))
        prev = cur
    if p <= full[0][0]:
        return dict(full[0][1])
    for (t0, a, _), (t1, b, e) in zip(full, full[1:]):
        if p <= t1:
            u = ease(e, (p - t0) / max(1e-6, t1 - t0))
            return {k: a[k] + (b[k] - a[k]) * u for k in REST}
    return dict(full[-1][1])


# ---------------------------------------------------------------- ASS compiler
def _hex(c: str) -> tuple[int, int, int]:
    c = (c or "#FFFFFF").lstrip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except ValueError:
        return 255, 255, 255


def _ass_c(rgb: tuple[int, int, int]) -> str:
    r, g, b = (max(0, min(255, int(round(v)))) for v in rgb)
    return f"&H{b:02X}{g:02X}{r:02X}&"


def _mix(rgb, w):
    return tuple(v + (255 - v) * w for v in rgb)


def _alpha(a: float) -> str:
    return f"&H{max(0, min(255, int(round(255 * (1 - max(0.0, min(1.0, a))))))):02X}&"


def clusters(text: str) -> list[str]:
    """Split into grapheme clusters (aksharas) so Devanagari shaping stays intact."""
    out: list[str] = []
    for ch in text:
        cat = unicodedata.category(ch)
        if out and (cat.startswith("M") or out[-1].endswith("्") or ch in "‍‌" or out[-1].endswith("‍")):
            out[-1] += ch
        else:
            out.append(ch)
    return out


def _fmt_t(ms: float) -> str:
    cs = int(round(ms / 10))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(t: str) -> str:
    return t.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def normalize(t: dict) -> dict:
    """Older title items (single `anim`, `bg` outline) → the current fields."""
    t = dict(t)
    if "anim_in" not in t:
        a_in, a_out, a_loop = LEGACY.get(t.get("anim") or "fade", ("fade", "fade", "none"))
        t["anim_in"], t["anim_out"], t["anim_loop"] = a_in, a_out, a_loop
    if t.get("bg") and not t.get("outline") and not t.get("box"):
        t["outline"] = t["bg"]
        t.setdefault("outline_w", .02 * .5)
    return t


class _Ctx:
    def __init__(self, t: dict, W: int, H: int):
        self.t, self.W, self.H = t, W, H
        self.base = min(W, H)
        pos = t.get("pos") or "top"
        if pos == "free" or (t.get("x") is not None and pos == "free"):
            self.X, self.Y = float(t.get("x", .5)) * W, float(t.get("y", .5)) * H
        else:
            self.X = W / 2
            self.Y = {"top": .18, "center": .5, "bottom": .78}.get(pos, .18) * H
        self.size = float(t.get("size", .075)) * self.base
        self.rgb = _hex(t.get("color") or "#FFFFFF")
        self.opacity = max(0.0, min(1.0, float(t.get("opacity", 1.0))))
        lines = str(t.get("text", "")).split("|")
        longest = max((len(clusters(x)) for x in lines), default=1)
        self.bw = min(W * .96, longest * self.size * .62 + self.size)
        self.bh = len(lines) * self.size * 1.3 + self.size * .4

    def static(self) -> str:
        t = self.t
        tags = f"\\an5\\fs{self.size:.0f}"
        if t.get("font"):
            tags += f"\\fn{t['font']}"
        tags += f"\\b{0 if t.get('bold') is False else 1}"
        if t.get("italic"):
            tags += "\\i1"
        if t.get("underline"):
            tags += "\\u1"
        if t.get("spacing"):
            tags += f"\\fsp{float(t['spacing']) * self.base:.1f}"
        if t.get("box"):
            pad = float(t.get("box_pad", .016)) * self.base
            tags += f"\\bord{pad:.1f}\\3c{_ass_c(_hex(t.get('box_color') or '#000000'))}\\3a{_alpha(1 - float(t.get('box_alpha', 0)))}"
            tags += "\\shad0"
        else:
            ow = float(t.get("outline_w", 0) or 0) * self.base
            tags += f"\\bord{ow:.1f}" + (f"\\3c{_ass_c(_hex(t['outline']))}" if t.get("outline") else "")
            sd = float(t.get("shadow_d", 0) or 0) * self.base
            tags += f"\\shad{sd:.1f}" + (f"\\4c{_ass_c(_hex(t['shadow']))}\\4a&H60&" if t.get("shadow") else "")
            if t.get("outline") and not ow:
                tags += "\\bord0"
        q = {"left": 7, "right": 9}.get(t.get("align") or "", 0)
        if q:
            tags = tags.replace("\\an5", f"\\an{q - 3}")  # 4 = middle-left, 6 = middle-right
        return tags

    def dyn(self, s: dict) -> str:
        """Override tags for one animation state (no position)."""
        rz = s["rz"] + float(self.t.get("rotate", 0) or 0)
        tags = (f"\\fscx{100 * s['sx']:.1f}\\fscy{100 * s['sy']:.1f}\\frz{rz:.2f}\\frx{s['rx']:.1f}\\fry{s['ry']:.1f}"
                f"\\fax{s['fax']:.3f}\\blur{s['blur'] * self.base / 1080:.2f}\\1a{_alpha(s['a'] * self.opacity)}"
                f"\\1c{_ass_c(_mix(self.rgb, s['w']))}")
        a_rest = s["a"] * self.opacity
        tags += f"\\3a{_alpha(a_rest * (1 - float(self.t.get('box_alpha', 0)) if self.t.get('box') else a_rest))}\\4a{_alpha(a_rest * .6)}"
        return tags

    def clip(self, s: dict) -> str:
        if s["cl"] <= 0 and s["cr"] >= 1 and s["ct"] <= 0 and s["cb"] >= 1:
            return "\\clip(0,0,%d,%d)" % (self.W, self.H)
        x0, y0 = self.X - self.bw / 2, self.Y - self.bh / 2
        return "\\clip(%d,%d,%d,%d)" % (x0 + s["cl"] * self.bw, y0 + s["ct"] * self.bh, x0 + s["cr"] * self.bw, y0 + s["cb"] * self.bh)

    def pos(self, s: dict) -> tuple[float, float]:
        return self.X + s["x"] * self.W, self.Y + s["y"] * self.H


def _segment(ctx: _Ctx, a_ms: float, b_ms: float, A: dict, B: dict, text: str, layer: int) -> str:
    d = max(1, int(b_ms - a_ms))
    xa, ya = ctx.pos(A)
    xb, yb = ctx.pos(B)
    move = f"\\move({xa:.1f},{ya:.1f},{xb:.1f},{yb:.1f},0,{d})" if (abs(xa - xb) > .5 or abs(ya - yb) > .5) else f"\\pos({xa:.1f},{ya:.1f})"
    tags = ctx.static() + move + ctx.dyn(A) + ctx.clip(A)
    if any(abs(A[k] - B[k]) > 1e-4 for k in REST if k not in ("x", "y")):
        tags += f"\\t(0,{d},{ctx.dyn(B)}{ctx.clip(B)})"
    return f"Dialogue: {layer},{_fmt_t(a_ms)},{_fmt_t(b_ms)},Title,,0,0,0,,{{{tags}}}{text}"


def _sample(kf: list, a_ms: float, b_ms: float, step_ms: float = 45) -> list[tuple[float, dict]]:
    """States at sample points; extra points at keyframes so steps/bounces stay sharp."""
    span = max(1.0, b_ms - a_ms)
    ts = {0.0, 1.0}
    n = max(1, int(math.ceil(span / step_ms)))
    ts.update(i / n for i in range(n + 1))
    for k in kf:
        p = float(k[0])
        ts.add(p)
        if len(k) > 2 and k[2] == "step":
            ts.add(max(0.0, p - 1e-4))
    pts = sorted(ts)
    return [(a_ms + p * span, state(kf, p)) for p in pts]


def _phase_events(ctx, kf, a_ms, b_ms, text, layer, out, step_ms=45):
    pts = _sample(kf, a_ms, b_ms, step_ms)
    for (ta, sa), (tb, sb) in zip(pts, pts[1:]):
        if tb - ta < 5:
            continue
        out.append(_segment(ctx, ta, tb, sa, sb, text, layer))


def _unit_event(ctx, anim: dict, a_ms: float, b_ms: float, raw: str, layer: int, entering: bool) -> str:
    """Letters/words appear (or vanish) one after another inside a single event."""
    d = max(1, int(b_ms - a_ms))
    lines = raw.split("|")
    units: list[tuple[str, bool]] = []  # (text, is_unit)
    for li, line in enumerate(lines):
        if li:
            units.append(("\\N", False))
        if anim.get("unit") == "word":
            words = line.split(" ")
            for wi, w in enumerate(words):
                if wi:
                    units.append((" ", False))
                units.append((w, True))
        else:
            for c in clusters(line):
                units.append((c, c.strip() != ""))
    n = max(1, sum(1 for _, u in units if u))
    stagger = float(anim.get("stagger", .7))
    each = d * (1 - stagger) if stagger < 1 else d / n
    rest = {**REST}
    frm = {**REST, **(anim.get("from") or {})}
    to = {**REST, **(anim.get("to") or {})}
    A, B = (frm, rest) if entering else (rest, to)
    order = list(range(n))
    if anim.get("reverse"):
        order.reverse()
    pieces, i = [], 0
    for txt, is_u in units:
        if not is_u:
            pieces.append(_esc(txt) if txt != "\\N" else "\\N")
            continue
        k = order[i]
        t0 = int(k * (d - each) / max(1, n - 1)) if n > 1 else 0
        t1 = t0 + max(1, int(1 if anim.get("step") else each))
        da, db = ctx.dyn(A), ctx.dyn(B)
        pieces.append(f"{{{da}\\t({t0},{t1},{db})}}{_esc(txt)}")
        i += 1
    x, y = ctx.pos(REST)
    head = ctx.static() + f"\\pos({x:.1f},{y:.1f})"
    return f"Dialogue: {layer},{_fmt_t(a_ms)},{_fmt_t(b_ms)},Title,,0,0,0,,{{{head}}}" + "".join(pieces)


def title_events(titles: list[dict], width: int, height: int, font: str = "Poppins") -> tuple[str, list[str]]:
    """ASS style + events for every text item (in / middle+loop / out phases)."""
    base = min(width, height)
    style = (f"Style: Title,{font},{round(0.075 * base)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
             f"-1,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1")
    style_box = style.replace("Style: Title,", "Style: TitleBox,").replace(",1,0,0,5,0,0,0,1", ",3,0,0,5,0,0,0,1")
    out: list[str] = []
    for raw_t in titles:
        t = normalize(raw_t)
        raw = str(t.get("text", ""))
        if not raw.strip():
            continue
        ctx = _Ctx(t, width, height)
        layer = 10 + int(t.get("track", 0) or 0)
        s_ms, e_ms = float(t["start"]) * 1000, float(t["end"]) * 1000
        dur = max(200.0, e_ms - s_ms)
        ain = ANIM_IN.get(t.get("anim_in") or "fade") or ANIM_IN["fade"]
        aout = ANIM_OUT.get(t.get("anim_out") or "fade") or ANIM_OUT["fade"]
        aloop = ANIM_LOOP.get(t.get("anim_loop") or "none") or ANIM_LOOP["none"]
        has_in = bool(ain.get("kf") or ain.get("unit"))
        has_out = bool(aout.get("kf") or aout.get("unit"))
        in_ms = float(t.get("in_ms") or (min(1600, 70 * len(clusters(raw))) if ain.get("unit") == "char" else 450)) if has_in else 0
        out_ms = float(t.get("out_ms") or 350) if has_out else 0
        if in_ms + out_ms > dur * .9:
            k = dur * .9 / (in_ms + out_ms)
            in_ms, out_ms = in_ms * k, out_ms * k
        text = _esc(raw).replace("|", "\\N")
        evs: list[str] = []
        a1, a2 = s_ms + in_ms, e_ms - out_ms
        if has_in:
            if ain.get("unit"):
                evs.append(_unit_event(ctx, ain, s_ms, a1, raw, layer, True))
            else:
                _phase_events(ctx, ain["kf"], s_ms, a1, text, layer, evs)
        # middle: rest or loop
        if a2 - a1 > 5:
            if aloop.get("kf"):
                if aloop.get("span"):
                    _phase_events(ctx, aloop["kf"], a1, a2, text, layer, evs, step_ms=400)
                else:
                    per = max(80.0, float(t.get("loop_ms") or aloop.get("period", 1000)))
                    tcur = a1
                    while tcur < a2 - 5 and len(evs) < 900:
                        tend = min(a2, tcur + per)
                        frac = (tend - tcur) / per
                        kf = aloop["kf"] if frac >= .999 else [k for k in aloop["kf"] if k[0] <= frac] + [[frac, state(aloop["kf"], frac)]]
                        sub = []
                        _phase_events(ctx, [[k[0] / frac if frac < .999 else k[0], k[1], *(k[2:] if len(k) > 2 else [])] for k in kf],
                                      tcur, tend, text, layer, sub, step_ms=max(40, per / 6))
                        evs.extend(sub)
                        tcur = tend
            else:
                evs.append(_segment(ctx, a1, a2, dict(REST), dict(REST), text, layer))
        if has_out:
            if aout.get("unit"):
                evs.append(_unit_event(ctx, aout, a2, e_ms, raw, layer, False))
            else:
                _phase_events(ctx, aout["kf"], a2, e_ms, text, layer, evs)
        if t.get("box"):
            evs = [ev.replace(",Title,,", ",TitleBox,,", 1) for ev in evs]
        out.extend(evs)
    return style + "\n" + style_box, out
