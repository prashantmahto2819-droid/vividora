"""One-click themes: look + captions + text + transitions + effects + music + voice + montage feel, in one go.

A theme is a JSON file in presets/themes (built-in) or a saved copy in the `themes` table
(workspace). Applying one writes its parts into the project's render settings; every part can be
left out, and everything stays editable afterwards. Parts that cannot apply (captions on a project
without transcript) are reported, never silently dropped.
"""

from __future__ import annotations

import json
import random
from functools import lru_cache
from pathlib import Path

from .. import db
from ..config import settings
from .catalog import EFFECTS, GRADE_PRESETS
from .effects import EXTRAS, LOOKS, TRANSITIONS, VOICE_PRESETS
from .presets import caption_styles

PARTS = [("look", "रंग / grade"), ("captions", "caption style"), ("text", "text style"), ("transition", "transitions"),
         ("effects", "effects"), ("music", "music mood + volume"), ("voice", "आवाज़ preset"), ("zoom", "auto zoom"),
         ("montage", "montage feel (cuts, effects)")]
PART_IDS = [p for p, _ in PARTS]

_FX_IDS = {e["id"] for e in EFFECTS}


@lru_cache(maxsize=1)
def builtin() -> dict[str, dict]:
    d: Path = settings.presets_dir / "themes"
    out: dict[str, dict] = {}
    if not d.exists():
        return out
    for f in sorted(d.glob("*.json")):
        t = json.loads(f.read_text(encoding="utf-8"))
        t.setdefault("id", f.stem)
        t["builtin"] = True
        out[t["id"]] = t
    return out


def saved(workspace_id: str) -> list[dict]:
    c = db.conn()
    if True:
        rows = c.execute("SELECT id, name, settings, created_at, updated_at FROM themes WHERE workspace_id = ? ORDER BY name", (workspace_id,)).fetchall()
    out = []
    for r in rows:
        t = json.loads(r[2] or "{}")
        t.update(id=r[0], label=r[1], builtin=False, saved=True)
        out.append(t)
    return out


def get(theme_id: str, workspace_id: str | None = None) -> dict | None:
    if theme_id in builtin():
        return builtin()[theme_id]
    if workspace_id:
        for t in saved(workspace_id):
            if t["id"] == theme_id:
                return t
    return None


def listing(workspace_id: str) -> list[dict]:
    return [_public(t) for t in builtin().values()] + [_public(t) for t in saved(workspace_id)]


def _public(t: dict) -> dict:
    cs = caption_styles().get(t.get("caption_style") or "", {})
    st = text_style(t.get("text_style"))
    return {**t, "caption_label": cs.get("label") or t.get("caption_style"), "parts": PART_IDS,
            "text_font": st.get("font") or "Poppins", "text_color": st.get("color") or "#FFFFFF"}


def text_style(style_id: str | None) -> dict:
    from .textfx import _STYLES
    for sid, _label, _cat, st in _STYLES:
        if sid == style_id:
            return dict(st)
    return {}


def pick_music(library: list[dict], mood: str | None, seed: str = "") -> str:
    musics = [m for m in library if m.get("kind") == "music"]
    if not musics:
        return ""
    mood = (mood or "").lower()
    hit = [m for m in musics if mood and (mood in str(m.get("tags") or "").lower() or mood in str(m.get("name") or "").lower())]
    return random.Random(seed or mood).choice(hit or musics)["id"]


def apply(render: dict, theme: dict, parts: list[str] | None = None, *, has_transcript: bool = True,
          library: list[dict] | None = None, seed: str = "") -> tuple[dict, list[str], list[str]]:
    """render settings (project.settings.render) → new settings, applied parts, skipped parts (with reason)."""
    parts = [p for p in (parts or PART_IDS) if p in PART_IDS]
    rs = json.loads(json.dumps(render or {}))
    e = rs.setdefault("effects", {})
    applied: list[str] = []
    skipped: list[str] = []
    if "look" in parts:
        gp = theme.get("grade_preset") or ""
        if gp and gp in GRADE_PRESETS:
            e["grade_preset"] = gp
            e["grade"] = {k: v for k, v in GRADE_PRESETS[gp].items() if k not in ("label", "cat")}
        look = theme.get("look") or "none"
        if look in LOOKS:
            e["look"] = look
        ex = [x for x in (theme.get("extras") or []) if x in EXTRAS]
        e["extras"] = ex
        applied.append("look")
    if "captions" in parts:
        cs = theme.get("caption_style")
        if not has_transcript:
            skipped.append("captions: transcript नहीं है — «Transcript बनाएँ» के बाद लगेगा")
        elif cs and cs in caption_styles():
            rs["caption_style"] = cs
            applied.append("captions")
        else:
            skipped.append("captions: style नहीं मिला")
    if "text" in parts:
        st = text_style(theme.get("text_style"))
        if st:
            e["text_default"] = {**st, "template": theme.get("text_style")}
            for t in e.get("titles") or []:
                if t.get("text") and not t.get("locked"):
                    for k, v in st.items():
                        t[k] = v
            applied.append("text")
        else:
            skipped.append("text: style नहीं मिला")
    if "transition" in parts:
        tr = theme.get("transition") or "none"
        if tr in TRANSITIONS:
            e["transition"] = tr
            e["transition_duration"] = float(theme.get("transition_duration") or 0.3)
            applied.append("transition")
    if "effects" in parts:
        stack = [{"id": s["id"], "params": s.get("params") or {}, "enabled": True, "theme": True}
                 for s in (theme.get("stack") or []) if isinstance(s, dict) and s.get("id") in _FX_IDS]
        e["stack"] = [s for s in (e.get("stack") or []) if not s.get("theme")] + stack
        applied.append("effects")
    if "music" in parts:
        m = theme.get("music") or {}
        cur = dict(e.get("music") or {})
        cur.update({"volume": float(m.get("volume", cur.get("volume", 0.15))), "duck": True,
                    "duck_amount": float(m.get("duck_amount", cur.get("duck_amount", 0.6))), "mood": m.get("mood") or ""})
        if library is not None:
            mid = pick_music(library, m.get("mood"), seed)
            if mid:
                cur["id"] = mid
            else:
                skipped.append("music: library में music नहीं है")
        e["music"] = cur
        applied.append("music")
    if "voice" in parts:
        vp = theme.get("voice") or "studio"
        if vp in VOICE_PRESETS:
            e["voice"] = {**(e.get("voice") or {}), "preset": vp}
            applied.append("voice")
    if "zoom" in parts:
        z = theme.get("zoom") or {}
        e["zoom"] = {"enabled": bool(z.get("enabled", True)), "strength": float(z.get("strength", 0.9))}
        applied.append("zoom")
    if "montage" in parts:
        rs["theme_montage"] = montage_opts(theme)
        applied.append("montage")
    rs["theme_id"] = theme.get("id")
    return rs, applied, skipped


def montage_opts(theme: dict | None) -> dict:
    """The montage-relevant part of a theme → options for beatcut.plan / render."""
    if not theme:
        return {}
    m = theme.get("montage") or {}
    st = text_style(theme.get("text_style"))
    return {"pace": m.get("pace") or "auto", "effects_level": m.get("effects_level") or "auto",
            "min_cut": float(m.get("min_cut", 0.4)), "max_cut": float(m.get("max_cut", 2.2)),
            "fx_strong": list(m.get("fx_strong") or []), "fx_soft": list(m.get("fx_soft") or []),
            "look": m.get("look") or "auto", "intro": bool(m.get("intro", True)), "outro": bool(m.get("outro", False)),
            "slowmo": bool(theme.get("slowmo", True)), "speed_ramp": bool(theme.get("speed_ramp", True)),
            "font": st.get("font") or "Poppins", "text_color": st.get("color") or "#FFFFFF",
            "text_size": float(st.get("size") or 0.07), "text_style": st, "theme_id": theme.get("id")}


def from_project(project: dict, name: str) -> dict:
    """The project's current settings as a theme the creator can reuse."""
    rs = (project.get("settings") or {}).get("render") or {}
    e = rs.get("effects") or {}
    mo = (project.get("settings") or {}).get("montage") or {}
    td = e.get("text_default") or {}
    return {"label": name, "emoji": "⭐", "hint": f"«{project.get('title') or ''}» की settings से बना",
            "swatch": [td.get("color") or "#F2B33D", "#1B1F2A"],
            "caption_style": rs.get("caption_style") or "karaoke", "text_style": td.get("template") or "bold_white",
            "look": e.get("look") or "none", "grade_preset": e.get("grade_preset") or "",
            "transition": e.get("transition") or "none", "transition_duration": float(e.get("transition_duration") or 0.3),
            "stack": [{"id": s["id"], "params": s.get("params") or {}} for s in (e.get("stack") or []) if s.get("id") in _FX_IDS][:6],
            "extras": list(e.get("extras") or []),
            "zoom": e.get("zoom") or {"enabled": True, "strength": 0.9},
            "music": {"mood": (e.get("music") or {}).get("mood") or "", "volume": (e.get("music") or {}).get("volume", 0.15),
                      "duck_amount": (e.get("music") or {}).get("duck_amount", 0.6)},
            "voice": (e.get("voice") or {}).get("preset") or "studio",
            "slowmo": bool(mo.get("slowmo", True)), "speed_ramp": True,
            "montage": {"pace": mo.get("pace") or "auto", "effects_level": mo.get("effects_level") or "auto",
                        "min_cut": 0.4, "max_cut": 2.2, "look": mo.get("look") or "auto", "intro": True, "outro": False}}


def save(c, workspace_id: str, name: str, data: dict, user_id: str | None = None, theme_id: str | None = None) -> dict:
    tid = theme_id or db.new_id()
    clean = {k: v for k, v in data.items() if k not in ("id", "builtin", "saved", "label", "parts", "caption_label")}
    row = {"id": tid, "workspace_id": workspace_id, "name": name[:60] or "Theme", "settings": clean,
           "created_by": user_id, "created_at": db.now(), "updated_at": db.now()}
    if db.get("themes", tid):
        db.update(c, "themes", tid, {"name": row["name"], "settings": clean, "updated_at": db.now()})
    else:
        db.insert(c, "themes", row)
    return {**clean, "id": tid, "label": row["name"], "builtin": False, "saved": True}
