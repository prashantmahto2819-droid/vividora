"""Person cutout for library clips ("सिर्फ़ इंसान" overlays, B-roll, montage clips).

The main video's matte is a project asset (kind "alpha", job "matte"). A library clip's
matte is cached ON THE LIBRARY ITEM — computed once (job "matte_lib", run in the context
of the project that asked for it), stored next to the library files and reused by every
project of the workspace:

  library.meta.alpha = {path, frames, width, height, fps, quality, ms_per_frame, bytes}
  file: MEDIA_ROOT/ws_<ws>/library/alpha/<item id>.mp4

Kept separate from service.py on purpose; service only calls the hooks below.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import db, queue, storage

QUALITIES = ("fast", "balanced", "hair")


def lib_alpha(item: dict | None) -> dict | None:
    a = ((item or {}).get("meta") or {}).get("alpha")
    if not isinstance(a, dict) or not a.get("path"):
        return None
    try:
        return a if storage.abs_path(a["path"]).exists() else None
    except (ValueError, OSError):
        return None


def lib_alpha_path(item: dict | None) -> Path | None:
    a = lib_alpha(item)
    return storage.abs_path(a["path"]) if a else None


def wanted(effects: dict | None) -> list[str]:
    """Library ids of the overlays that want a person-only cutout."""
    out = []
    for it in (effects or {}).get("broll") or []:
        if isinstance(it, dict) and it.get("cutout") and it.get("id") and it["id"] not in out:
            out.append(it["id"])
    return out


def running_job(c, lib_id: str) -> dict | None:
    return db.row(c.execute("SELECT * FROM jobs WHERE kind = 'matte_lib' AND status IN ('queued','running') "
                            "AND json_extract(payload, '$.library_id') = ? LIMIT 1", (lib_id,)).fetchone())


def queue_lib(c, project_id: str, lib_id: str, quality: str = "balanced", force: bool = False) -> dict | None:
    """Queue the cutout of one library video (None when it is cached or already being made)."""
    item = db.get("library", lib_id)
    if not item or item["kind"] not in ("broll",):
        raise ValueError("cutout सिर्फ़ library video (B-roll) का बनता है")
    if running_job(c, lib_id):
        return None
    if lib_alpha(item) and not force:
        return None
    q = quality if quality in QUALITIES else "balanced"
    return queue.enqueue(c, project_id, "matte_lib", {"library_id": lib_id, "quality": q, "name": item["name"]})


def missing(c, project: dict, effects: dict | None) -> list[str]:
    """Overlay cutouts of this render that still need their matte → queue them; returns those ids."""
    need = []
    for lid in wanted(effects):
        item = db.get("library", lid)
        if not item or item["workspace_id"] != project["workspace_id"] or item["kind"] != "broll":
            continue
        if lib_alpha(item):
            continue
        need.append(lid)
        try:
            queue_lib(c, project["id"], lid)
        except ValueError:
            pass
    return need


def after_lib(c, job: dict, result: dict) -> None:
    """A library clip's matte arrived (uploaded into the project's work folder) → move it next to
    the library files and remember it on the item."""
    lid = (job.get("payload") or {}).get("library_id")
    item = db.get("library", lid or "")
    f = (result.get("files") or [{}])[0]
    if not item or not f.get("path"):
        return
    src = storage.abs_path(f["path"])
    rel = str(Path(f"ws_{item['workspace_id']}") / "library" / "alpha" / f"{item['id']}.mp4")
    dst = storage.ensure_parent(rel)
    if src.exists():
        shutil.move(str(src), str(dst))
    meta = {**(item.get("meta") or {}), "alpha": {"path": rel, **{k: v for k, v in (f.get("meta") or {}).items() if k != "path"},
                                                   "created_at": db.now()}}
    db.update(c, "library", item["id"], {"meta": meta})
    project = db.get("projects", job["project_id"])
    if project is None:
        return
    db.update(c, "projects", project["id"], {"status_note": f"“{item['name'][:40]}” का cutout तैयार", "updated_at": db.now()})


def delete_lib_alpha(item: dict) -> None:
    p = lib_alpha_path(item)
    if p:
        p.unlink(missing_ok=True)


def view_meta(item: dict, url: str | None) -> dict:
    """Library item meta for the browser: the alpha's file path is replaced by a link."""
    meta = dict(item.get("meta") or {})
    a = meta.get("alpha")
    if isinstance(a, dict):
        if lib_alpha(item) and url:
            meta["alpha"] = {**{k: v for k, v in a.items() if k != "path"}, "url": url}
        else:
            meta.pop("alpha", None)
    return meta
