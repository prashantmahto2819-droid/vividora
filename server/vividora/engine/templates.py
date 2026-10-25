"""Template studio — reusable designs on the thumbnail engine.

A template is a thumbnail-studio `settings` dict (template id, format, text, stickers, layout…) saved
with a name, format, tags and industry. Built-in industry ad templates live in server/presets/templates/
*.json with `{{placeholders}}` in their texts; `fill()` replaces them from a form, `variations()` makes
colour/layout variants, `adapt()` moves a design to another format by anchor (never by stretching).
"""

from __future__ import annotations

import copy
import csv
import io
import json
import random
import re
from pathlib import Path

from . import thumbnail as T

PRESETS = Path(__file__).resolve().parent.parent.parent / "presets" / "templates"
SAFE = 0.06  # safe margin (fraction of the canvas) layers are pulled into when the format changes
PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
FIELDS = {"business": "Business का नाम", "offer": "Offer / headline", "price": "कीमत", "phone": "Phone", "address": "पता",
          "cta": "CTA (जैसे: आज ही call करें)", "tagline": "Tagline", "hours": "समय", "website": "Website / link"}
VARIANT_ACCENTS = ["#FFD400", "#FF3B30", "#00E5FF", "#00E676", "#FF6A00", "#E040FB", "#F2B33D", "#FFFFFF"]
INDUSTRIES = {"healthcare": "Clinic / Hospital", "grocery": "Grocery / Kirana", "electronics": "Electronics / FMCG",
              "automobile": "Automobile", "clothing": "Clothing / Fashion", "fitness": "Gym / Spa / Salon",
              "education": "Coaching / Education", "realestate": "Real estate / Construction", "local": "Local service",
              "corporate": "Corporate / Professional", "creator": "YouTube / Social",
              "restaurant": "Restaurant / Café / Dhaba", "wedding": "Wedding / Event",
              "astrology": "Astrology / Pandit", "travel": "Travel / Tourism",
              "tech": "Tech / Startup", "podcast": "Podcast / Show",
              "festival": "Festival / Occasion", "jewellery": "Jewellery / Gold"}


def _load_builtin() -> list[dict]:
    out = []
    if PRESETS.exists():
        for f in sorted(PRESETS.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            d.setdefault("id", f.stem)
            d["builtin"] = True
            d.setdefault("format", (d.get("settings") or {}).get("size") or "square")
            d.setdefault("tags", [])
            d.setdefault("fields", [k for k in FIELDS if "{{" + k in json.dumps(d.get("settings") or {}, ensure_ascii=False)])
            out.append(d)
    return out


BUILTIN = _load_builtin()


def builtin(tid: str) -> dict | None:
    t = next((x for x in BUILTIN if x["id"] == tid), None)
    return copy.deepcopy(t) if t else None


# ---------------------------------------------------------------- text helpers
def _walk_strings(obj, fn):
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, list):
        return [_walk_strings(x, fn) for x in obj]
    if isinstance(obj, dict):
        return {k: _walk_strings(v, fn) for k, v in obj.items()}
    return obj


def all_text(tpl_or_settings: dict) -> str:
    s = tpl_or_settings.get("settings") if "settings" in tpl_or_settings else tpl_or_settings
    parts: list[str] = []
    _walk_strings(s, lambda x: parts.append(x) or x)
    return "\n".join(parts)


def fill(tpl: dict, fields: dict) -> dict:
    """Return the template's settings with every {{placeholder}} replaced (missing fields → the template's default,
    else removed; a text sticker whose whole text was an empty placeholder is dropped)."""
    defaults = {k: v for k, v in (tpl.get("defaults") or {}).items()}
    vals = {**defaults, **{k: str(v).strip() for k, v in (fields or {}).items() if v is not None}}

    def sub(x: str) -> str:
        return PLACEHOLDER.sub(lambda m: vals.get(m.group(1), ""), x)

    s = _walk_strings(copy.deepcopy(tpl.get("settings") or {}), sub)
    for st in s.get("stickers") or []:  # image slots (product photo / logo) take a library item id from the form
        if st.get("role") and (fields or {}).get(st["role"]):
            st["id"] = str(fields[st["role"]])
    s["stickers"] = [st for st in s.get("stickers") or [] if not (st.get("txt") is not None and not str(st.get("txt")).strip())
                     and not (st.get("role") and st.get("id") is None and st.get("txt") is None)]
    s["labels"] = [x for x in (s.get("labels") or [])]
    s["size"] = s.get("size") if s.get("size") in T.FORMATS else tpl.get("format", "square")
    s["no_person"] = s.get("no_person", True)
    return s


def variations(settings: dict, n: int = 3, seed: str | None = None) -> list[dict]:
    """n colour / layout variants of a filled design: accent + bg colour swap, mirrored layout, text style."""
    rnd = random.Random(seed or json.dumps(settings, sort_keys=True)[:200])
    base_acc = (settings.get("accent") or "#FFD400").upper()
    accents = [a for a in VARIANT_ACCENTS if a != base_acc]
    rnd.shuffle(accents)
    styles = [s for s in ("outline", "box", "block", "shadow", "neon", "banner") if s != settings.get("style")]
    out = []
    for i in range(max(1, min(6, n))):
        v = copy.deepcopy(settings)
        v["accent"] = accents[i % len(accents)]
        bg = dict(v.get("bg") or {})
        if bg.get("type") in ("solid", "gradient") and i % 2 == 1:
            bg["color"], bg["color2"] = bg.get("color2") or bg.get("color"), bg.get("color")
            bg["angle"] = (float(bg.get("angle", 90)) + 90) % 360
        v["bg"] = bg
        if i % 3 == 2:
            v["style"] = styles[i % len(styles)]
        if i % 2 == 1 and T.base_of(v) == "yt":
            v["flip"] = not v.get("flip")
        for st in v.get("stickers") or []:
            if st.get("shape") and not st.get("color"):
                st["color"] = "accent"
        out.append(v)
    return out


def adapt(settings: dict, to_fmt: str) -> dict:
    """Move a design to another format: the anchor fractions carry over (sizes are already relative to the
    canvas), the target format gets its own layout entry if it has none, and every anchor is pulled into the safe
    area so nothing hangs off the new edges. The old format's layout stays untouched."""
    if to_fmt not in T.FORMATS:
        raise ValueError("unknown format")
    out = copy.deepcopy(settings)
    src = out.get("size") if out.get("size") in T.FORMATS else "yt"
    lay = out.setdefault("layout", {})
    if not isinstance(lay, dict):
        lay = out["layout"] = {}
    if to_fmt not in lay or not isinstance(lay.get(to_fmt), dict) or not lay[to_fmt]:
        lay[to_fmt] = copy.deepcopy(lay.get(src) or {})
    tw, th, _ = T.FORMATS[to_fmt]
    if to_fmt == "custom":
        cs = out.get("custom_size") or [tw, th]
        tw, th = int(cs[0]), int(cs[1])
    else:
        out["custom_size"] = [tw, th]
    sw, sh = T.size_px(settings)
    # wide → tall: things sized by width would grow huge relative to the height; scale them down and vice versa
    k = min(1.0, (tw / th) / (sw / sh)) if (tw / th) < (sw / sh) else min(1.0, (sw / sh) / (tw / th))
    k = k ** 0.5  # text is sized by height, shapes by width — the square root keeps both readable
    lo, hi = SAFE, 1 - SAFE
    for lid, o in lay[to_fmt].items():
        if not isinstance(o, dict) or lid.startswith("_"):
            continue
        if "x" in o:
            o["x"] = min(hi, max(lo, float(o["x"])))
        if "y" in o:
            o["y"] = min(hi, max(lo, float(o["y"])))
        if k < 0.999 and "s" in o:
            o["s"] = round(float(o["s"]) * max(0.5, k), 3)
    for st in out.get("stickers") or []:
        st["x"] = min(hi, max(lo, float(st.get("x", 0.5))))
        st["y"] = min(hi, max(lo, float(st.get("y", 0.5))))
        if k < 0.999 and st.get("w"):
            st["w"] = round(float(st["w"]) * max(0.5, k), 4)
    out["size"] = to_fmt
    return out


def apply_brand(settings: dict, brand: dict, handle: str | None = None) -> dict:
    """Brand kit → design: accent / highlight colours, font, logo and @handle in one go."""
    out = copy.deepcopy(settings)
    if brand.get("primary"):
        out["accent"] = brand["primary"]
    if brand.get("highlight"):
        out["hl"] = brand["highlight"]
    if brand.get("font") and brand["font"] in T.FONTS:
        out["font"] = brand["font"]
    if brand.get("logo_id"):
        out["logo"] = True
        out["logo_id"] = brand["logo_id"]
    if handle:
        sts = out.setdefault("stickers", [])
        h = handle if handle.startswith("@") else "@" + handle
        hit = next((s for s in sts if s.get("role") == "handle"), None)
        if hit:
            hit["txt"] = h
        else:
            sts.append({"uid": "handle", "role": "handle", "txt": h, "x": 0.5, "y": 0.955, "size": 0.032, "color": "#FFFFFF", "font": "Poppins"})
    return out


def parse_csv(text: str) -> list[dict]:
    rd = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    rows = []
    for r in rd:
        row = {str(k).strip().lower(): (v or "").strip() for k, v in r.items() if k}
        if any(row.values()):
            rows.append(row)
    return rows[:200]


def listing(builtin_only: bool = False) -> list[dict]:
    return [{k: v for k, v in t.items() if k != "settings"} | {"settings": t["settings"]} for t in BUILTIN]
