"""Archive: move big files of finished projects off the working disk.

Two backends, picked by .env:
  ARCHIVE_ROOT=/archive                   a local/USB/NAS path (copy via shutil)
  ARCHIVE_RCLONE_REMOTE=gdrive:Vividora   any rclone remote (Google Drive, OneDrive, S3…)

What moves: raw recordings, clips, work audio (the heavy stuff). Proxies and
finished renders stay local so the dashboard keeps playing them; renders are
COPIED to the archive as a backup. Restore brings the raw files back when a
project is reopened for re-editing.

Set up Google Drive once on the VM:
  sudo apt install rclone && rclone config     (n → gdrive → drive → follow prompts)
  ARCHIVE_RCLONE_REMOTE=gdrive:Vividora  in .env, mount ~/.config/rclone into the api container
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db, storage
from .config import settings

log = logging.getLogger("vividora.archive")
REMOTE = os.getenv("ARCHIVE_RCLONE_REMOTE", "").strip()
HEAVY = ("raw", "clip", "audio_asr", "audio_clean")


def backend() -> str | None:
    if REMOTE:
        return "rclone"
    if settings.archive_root:
        return "local"
    return None


def _rclone(*args: str) -> subprocess.CompletedProcess:
    cfg = os.getenv("RCLONE_CONFIG")
    env = {**os.environ, **({"RCLONE_CONFIG": cfg} if cfg else {})}
    return subprocess.run(["rclone", *args], capture_output=True, text=True, env=env, timeout=6 * 3600)


def _put(rel: str, move: bool) -> bool:
    src = storage.abs_path(rel)
    if not src.exists():
        return False
    if REMOTE:
        r = _rclone("moveto" if move else "copyto", str(src), f"{REMOTE}/{rel}", "--drive-chunk-size", "64M")
        if r.returncode != 0:
            log.warning("rclone failed for %s: %s", rel, r.stderr[-300:])
            return False
        return True
    dst = settings.archive_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    (shutil.move if move else shutil.copy2)(str(src), str(dst))
    return True


def _get(rel: str) -> bool:
    dst = storage.ensure_parent(rel)
    if REMOTE:
        r = _rclone("copyto", f"{REMOTE}/{rel}", str(dst))
        return r.returncode == 0 and dst.exists()
    src = settings.archive_root / rel
    if not src.exists():
        return False
    shutil.move(str(src), str(dst))
    return True


def archive_project(project_id: str) -> dict:
    """Move heavy files out, back up renders. Safe to run twice."""
    if not backend():
        return {"moved": 0, "backed_up": 0, "error": "ARCHIVE_ROOT या ARCHIVE_RCLONE_REMOTE सेट नहीं"}
    moved = backed = 0
    cn = db.conn()
    rows = db.rows(cn.execute("SELECT * FROM assets WHERE project_id = ? AND archived = 0", (project_id,)))
    for a in rows:
        if a["kind"] in HEAVY:
            if _put(a["path"], move=True):
                with db.tx() as c:
                    db.update(c, "assets", a["id"], {"archived": True})
                moved += 1
        elif a["kind"] in ("render", "subtitle"):
            if _put(a["path"], move=False):
                backed += 1
    with db.tx() as c:
        p = db.get("projects", project_id)
        if p:
            db.update(c, "projects", project_id, {"meta": {**p.get("meta", {}), "archived_at": db.now(), "archive": backend()}})
    return {"moved": moved, "backed_up": backed}


def restore_project(project_id: str) -> dict:
    if not backend():
        return {"restored": 0, "error": "archive backend सेट नहीं"}
    n = 0
    for a in db.rows(db.conn().execute("SELECT * FROM assets WHERE project_id = ? AND archived = 1", (project_id,))):
        if _get(a["path"]):
            with db.tx() as c:
                db.update(c, "assets", a["id"], {"archived": False})
            n += 1
    with db.tx() as c:
        p = db.get("projects", project_id)
        if p:
            meta = {k: v for k, v in p.get("meta", {}).items() if k != "archived_at"}
            db.update(c, "projects", project_id, {"meta": meta})
    return {"restored": n}


def sweep() -> dict:
    """Archive approved projects older than ARCHIVE_AFTER_DAYS. Called by the scheduler."""
    if not backend():
        return {"archived": 0}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=settings.archive_after_days)).isoformat(timespec="seconds")
    rows = db.rows(db.conn().execute(
        "SELECT id FROM projects WHERE status = 'approved' AND approved_at < ? AND id IN "
        "(SELECT project_id FROM assets WHERE archived = 0 AND kind IN ('raw','clip'))", (cutoff,)))
    done = 0
    for r in rows[:20]:
        try:
            archive_project(r["id"])
            done += 1
        except Exception as e:  # noqa: BLE001
            log.warning("archive %s failed: %s", r["id"], e)
    return {"archived": done}


def remote_usage() -> dict | None:
    if not REMOTE:
        return None
    r = _rclone("about", REMOTE.split(":")[0] + ":", "--json")
    if r.returncode != 0:
        return {"error": r.stderr[-200:]}
    import json
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None
