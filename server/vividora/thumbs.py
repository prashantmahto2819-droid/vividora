"""Thumbnail studio — the project-side glue around engine/thumbnail.py.

Best frames (cached in project.meta.thumb_frames), person cutout for one
frame (the project's alpha video if it exists, else RVM on that frame),
library files (background image, stickers, brand logo), saving thumbnails as
project assets (kind "thumbnail", label "yt" 1280×720 / "vertical" 1080×1920),
which one is selected (project.meta.thumbnail = {yt: asset_id, vertical: asset_id}),
the thumbnail used for publishing, and autopilot A/B variants.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from pathlib import Path

from . import db, service, storage
from .engine import thumbnail as T
from .security import media_token

log = logging.getLogger("vividora.thumbs")
KIND = "thumbnail"
_cache: OrderedDict = OrderedDict()
_lock = threading.Lock()


def _cached(key, make, limit: int = 24):
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    val = make()
    with _lock:
        _cache[key] = val
        while len(_cache) > limit:
            _cache.popitem(last=False)
    return val


def _file(asset: dict | None) -> Path | None:
    if not asset or asset.get("archived"):
        return None
    try:
        p = storage.abs_path(asset["path"])
    except ValueError:
        return None
    return p if p.exists() else None


def source_video(project: dict, quality: bool = True) -> Path | None:
    """The best file to take stills from: the original recording (sharper), else the 720p preview."""
    order = ("raw", "proxy") if quality else ("proxy", "raw")
    if project.get("kind") == "montage":
        order = ("render",) + order
    for kind in order:
        p = _file(service.asset_of(project["id"], kind))
        if p:
            return p
    return None


def duration(project: dict) -> float:
    return float((project.get("meta") or {}).get("duration") or 0)


# ---------------------------------------------------------------- frames
def best_frames(project: dict, refresh: bool = False) -> list[dict]:
    meta = project.get("meta") or {}
    src = source_video(project, quality=False)
    if src is None:
        return []
    cached = meta.get("thumb_frames") or {}
    if not refresh and cached.get("src") == src.name and cached.get("frames"):
        return cached["frames"]
    frames = T.best_frames(src, duration(project))
    with db.tx() as c:
        cur = db.get("projects", project["id"]) or project
        db.update(c, "projects", project["id"], {"meta": {**(cur.get("meta") or {}), "thumb_frames": {"src": src.name, "frames": frames}}})
    return frames


def frame_image(project: dict, t: float, max_w: int = 1920):
    src = source_video(project)
    if src is None:
        raise ValueError("वीडियो फ़ाइल नहीं मिली")
    t = round(max(0.0, min(t, max(0.0, duration(project) - 0.05))), 2)
    return _cached(("frame", str(src), t, max_w), lambda: T.grab_frame(src, t, max_w=max_w)).copy()


def frame_jpeg(project: dict, t: float, w: int = 320) -> bytes:
    img = frame_image(project, t, max_w=max(80, min(1280, w)))
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def _alpha(project: dict, frame, t: float):
    def make():
        a = _file(service.asset_of(project["id"], "alpha"))
        if a is not None:
            m = T.grab_alpha(a, t, frame.size)
            if m is not None and T.matte_ok(m):
                return m
        return T.rvm_alpha(frame)
    return _cached(("alpha", project["id"], round(t, 2), frame.size), make, limit=12)


def _face(project: dict, frame, t: float):
    return _cached(("face", project["id"], round(t, 2), frame.size), lambda: T.detect_face(frame), limit=32)


# ---------------------------------------------------------------- library files
def _lib_path(workspace_id: str, item_id: str | None) -> str | None:
    if not item_id:
        return None
    it = db.get("library", item_id)
    if not it or it["workspace_id"] != workspace_id:
        return None
    p = _file({"path": it["path"]})
    return str(p) if p else None


def brand(project: dict) -> dict:
    ch = service.project_channel(project)
    return ((ch.get("settings") or {}).get("brand") or {}) if ch else {}


def _paths(project: dict, s: dict) -> dict:
    ws = project["workspace_id"]
    out: dict = {"stickers": {}}
    bg = s.get("bg") or {}
    if bg.get("type") == "image":
        out["bg_image"] = _lib_path(ws, bg.get("image_id"))
    for st in s.get("stickers") or []:
        if isinstance(st, dict) and st.get("id"):
            p = _lib_path(ws, st["id"])
            if p:
                out["stickers"][st["id"]] = p
    if s.get("logo"):
        out["logo"] = _lib_path(ws, s.get("logo_id") or brand(project).get("logo_id"))
    return out


# ---------------------------------------------------------------- render / save
def clean_settings(s: dict | None) -> dict:
    s = dict(s or {})
    s["size"] = s.get("size") if s.get("size") in T.SIZES else "yt"
    if s.get("template") not in T.TEMPLATE_IDS:
        s["template"] = "face_right"
    s["text"] = str(s.get("text") or "")[:160]
    try:
        s["t"] = max(0.0, float(s.get("t") or 0))
    except (TypeError, ValueError):
        s["t"] = 0.0
    if s.get("t2") not in (None, ""):
        try:
            s["t2"] = max(0.0, float(s["t2"]))
        except (TypeError, ValueError):
            s.pop("t2", None)
    if not isinstance(s.get("stickers"), list):
        s["stickers"] = []
    if not isinstance(s.get("bg"), dict):
        s["bg"] = {}
    s.setdefault("cutout", True)
    return s


def render(project: dict, settings: dict) -> tuple[bytes, dict, list[dict]]:
    s = clean_settings(settings)
    if not s.get("t"):
        fr = best_frames(project)
        s["t"] = fr[0]["t"] if fr else min(1.0, duration(project) / 2)
    frame = frame_image(project, s["t"])
    tmpl = T.template(s["template"], s["size"])
    alpha = _alpha(project, frame, s["t"]) if s.get("cutout", True) and tmpl.get("person") is not None else None
    face = _face(project, frame, s["t"])
    frame2 = None
    if (tmpl.get("bg") or {}).get("type") == "split":
        t2 = s.get("t2")
        if t2 is None:
            fr = [f["t"] for f in best_frames(project) if abs(f["t"] - s["t"]) > 0.5]
            t2 = fr[0] if fr else 0.0
        frame2 = frame_image(project, t2)
    if s.get("logo") is None and brand(project).get("logo_id"):
        s["logo"] = True
    img, info = T.render(frame, s, alpha=alpha, face=face, frame2=frame2, paths=_paths(project, s))
    warnings = T.lint(s, info, project.get("title") or "")
    if s.get("cutout", True) and tmpl.get("person") is not None and alpha is None:
        warnings.append({"level": "info", "code": "no_cutout_model", "msg": "cutout नहीं बना (Effects → Body cutout चलाएँ या RVM model डाउनलोड होने दें) — पूरा frame इस्तेमाल हुआ"})
    return T.to_jpeg(img), {**info, "t": s["t"]}, warnings


def asset_view(a: dict, selected: dict | None = None) -> dict:
    v = {k: a.get(k) for k in ("id", "kind", "label", "size", "mime", "meta", "created_at")}
    v["url"] = f"/api/media/{a['id']}?t={media_token(a['id'])}"
    v["selected"] = bool(selected and selected.get(a.get("label")) == a["id"])
    return v


def selected_map(project: dict) -> dict:
    return dict((project.get("meta") or {}).get("thumbnail") or {})


def list_saved(project: dict) -> list[dict]:
    sel = selected_map(project)
    rows = db.rows(db.conn().execute("SELECT * FROM assets WHERE project_id = ? AND kind = ? ORDER BY created_at DESC",
                                     (project["id"], KIND)))
    return [asset_view(a, sel) for a in rows]


def _set_selected(c, project_id: str, label: str, asset_id: str | None) -> None:
    cur = db.get("projects", project_id) or {}
    meta = dict(cur.get("meta") or {})
    sel = dict(meta.get("thumbnail") or {})
    if asset_id:
        sel[label] = asset_id
    else:
        sel.pop(label, None)
    meta["thumbnail"] = sel
    db.update(c, "projects", project_id, {"meta": meta, "updated_at": db.now()})


def save(project: dict, settings: dict, *, user_id: str | None = None, select: bool = False, source: str = "manual") -> dict:
    s = clean_settings(settings)
    jpg, info, warnings = render(project, s)
    s["t"] = info["t"]
    aid = db.new_id()
    rel = str(storage.project_dir(project["workspace_id"], project["id"]) / "out" / "thumbs" / f"{s['size']}-{aid[:10]}.jpg")
    storage.ensure_parent(rel).write_bytes(jpg)
    with db.tx() as c:
        a = service.add_asset(c, project["id"], KIND, rel, label=s["size"], mime="image/jpeg",
                              meta={"settings": s, "template": s["template"], "text": s.get("text") or "", "width": info["width"],
                                    "height": info["height"], "warnings": warnings, "source": source, "by": user_id})
        cur = db.get("projects", project["id"]) or project
        if select or not selected_map(cur).get(s["size"]):
            _set_selected(c, project["id"], s["size"], a["id"])
        service.log(c, project["workspace_id"], "thumbnail.save", user_id=user_id, project_id=project["id"],
                    detail={"template": s["template"], "size": s["size"], "source": source})
    return asset_view(a, selected_map(db.get("projects", project["id"]) or {}))


def select(project: dict, asset_id: str) -> dict:
    a = db.get("assets", asset_id)
    if not a or a["project_id"] != project["id"] or a["kind"] != KIND:
        raise ValueError("thumbnail नहीं मिला")
    with db.tx() as c:
        _set_selected(c, project["id"], a["label"] or "yt", a["id"])
    return selected_map(db.get("projects", project["id"]) or {})


def delete(project: dict, asset_id: str) -> None:
    a = db.get("assets", asset_id)
    if not a or a["project_id"] != project["id"] or a["kind"] != KIND:
        raise ValueError("thumbnail नहीं मिला")
    p = _file(a)
    with db.tx() as c:
        c.execute("DELETE FROM assets WHERE id = ?", (a["id"],))
        if selected_map(db.get("projects", project["id"]) or {}).get(a["label"]) == a["id"]:
            nxt = c.execute("SELECT id FROM assets WHERE project_id = ? AND kind = ? AND label = ? ORDER BY created_at DESC LIMIT 1",
                            (project["id"], KIND, a["label"])).fetchone()
            _set_selected(c, project["id"], a["label"] or "yt", nxt[0] if nxt else None)
    if p:
        p.unlink(missing_ok=True)


# ---------------------------------------------------------------- AI text + variants
def auto_text(project: dict) -> dict:
    from .engine.captions import plain_text
    tr = project.get("transcript") or {}
    try:
        text = plain_text(tr) if tr else ""
    except Exception:  # noqa: BLE001
        text = ""
    from .engine import aipack
    pack = aipack.get(project) if tr else None
    opts = [str(o).strip()[:60] for o in ((pack or {}).get("thumb_texts") or []) if str(o).strip()]
    opts = [o for o in opts if len(T.plain(o).split()) <= 5]
    if opts:
        return {"options": opts[:4], "source": "llm"}
    return T.suggest_texts(project.get("title") or "", text, project.get("language") or "hi")


VARIANT_ROTATION = ["face_right", "number", "gold", "question", "bold_box", "big_top", "emotional", "face_left", "red_arrow", "shock"]
VARIANT_ACCENTS = ["#FFD400", "#FF3B30", "#00E5FF", "#00E676", "#FF6A00", "#F2B33D"]


def variant_settings(project: dict, n: int = 3, size: str = "yt", base: dict | None = None) -> list[dict]:
    base = clean_settings(base) if base else {}
    frames = [f["t"] for f in best_frames(project)] or [min(1.0, duration(project) / 2)]
    texts = [base["text"]] if base.get("text") else (auto_text(project).get("options") or [""])
    rot = list(VARIANT_ROTATION)
    if base.get("template") in rot:
        rot.remove(base["template"])
        rot.insert(0, base["template"])
    if not any(T.leading_number(x) for x in texts):
        rot = [r for r in rot if r != "number"]
    out = []
    for i in range(max(1, min(6, n))):
        s = {**base, "size": size, "template": rot[i % len(rot)], "t": frames[i % len(frames)], "text": texts[i % len(texts)]}
        if s["template"] == "number" and not T.leading_number(s["text"]):
            s["text"] = next((x for x in texts if T.leading_number(x)), s["text"])
        if i > 0:
            s.pop("accent", None)
            if i % 3 == 2:
                s["accent"] = VARIANT_ACCENTS[i % len(VARIANT_ACCENTS)]
        out.append(s)
    return out


def make_variants(project: dict, n: int = 3, size: str = "yt", base: dict | None = None, *, user_id: str | None = None,
                  source: str = "variants") -> list[dict]:
    out = []
    for s in variant_settings(project, n, size, base):
        try:
            out.append(save(project, s, user_id=user_id, source=source))
        except Exception as e:  # noqa: BLE001 — one bad variant should not lose the others
            log.warning("thumbnail variant %s failed: %s", s.get("template"), e)
    return out


# ---------------------------------------------------------------- publishing
def publish_thumb_asset_id(project: dict) -> str | None:
    """The 1280×720 thumbnail to upload: the selected one, else the newest, else a fresh
    auto-generated one (best frame + short text). Never the 360p preview still."""
    sel = selected_map(project).get("yt")
    if sel and _file(db.get("assets", sel)):
        return sel
    row = db.row(db.conn().execute("SELECT * FROM assets WHERE project_id = ? AND kind = ? AND label = 'yt' ORDER BY created_at DESC LIMIT 1",
                                   (project["id"], KIND)).fetchone())
    if row and _file(row):
        return row["id"]
    try:
        fr = best_frames(project)
        opts = auto_text(project).get("options") or [""]
        a = save(project, {"template": "face_right", "size": "yt", "t": fr[0]["t"] if fr else 0, "text": opts[0]},
                 select=True, source="auto-publish")
        return a["id"]
    except Exception as e:  # noqa: BLE001 — a missing thumbnail must not block the upload
        log.warning("auto thumbnail failed: %s", e)
        return None


# ---------------------------------------------------------------- autopilot
def _autopilot_now(project_id: str) -> None:
    p = db.get("projects", project_id)
    if not p or not (p.get("settings") or {}).get("autopilot"):
        return
    done = db.conn().execute("SELECT COUNT(*) FROM assets WHERE project_id = ? AND kind = ? AND meta LIKE '%\"source\": \"autopilot\"%'",
                             (project_id, KIND)).fetchone()[0]
    if done:
        return
    made = make_variants(p, 3, "yt", source="autopilot")
    try:
        p = db.get("projects", project_id)
        best = (variant_settings(p, 1, "vertical") or [None])[0]
        if best:
            save(p, best, source="autopilot")
    except Exception as e:  # noqa: BLE001
        log.warning("autopilot vertical cover failed: %s", e)
    log.info("autopilot: %d thumbnails for %s", len(made), project_id)


def autopilot_thumbnails(project_id: str) -> None:
    """Create 3 A/B thumbnail variants (+ a 9:16 cover) in the background — safe to call
    inside a DB transaction: the thread waits for the commit through SQLite's busy timeout."""
    def run():
        try:
            _autopilot_now(project_id)
        except Exception as e:  # noqa: BLE001
            log.warning("autopilot thumbnails failed for %s: %s", project_id, e)
    threading.Thread(target=run, name=f"thumbs-{project_id[:8]}", daemon=True).start()
