"""Disk space: what is using the server's disk, and safe ways to free it.

usage()  — totals per project and per kind of file, the library, unfinished
           uploads and "orphan" files that nothing points to any more.
clean()  — removes only what the creator picked:
   orphans      files/folders no project or library item uses (always safe)
   uploads      half-finished uploads older than a day
   cache        regenerable helpers of finished projects (preview copy, speech
                audio, cutout mask, waveform) — the editor can rebuild them
   sources      original recordings of finished projects (keeps final videos)
   renders      final videos of projects that are already published
Finished = approved or published, and older than `days`.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db, storage
from .config import settings

CACHE_KINDS = ("proxy", "audio_asr", "alpha", "waveform")
SOURCE_KINDS = ("raw", "clip", "audio_clean")
RENDER_KINDS = ("render", "subtitle", "short")


def _size(p: Path) -> int:
    try:
        if p.is_file():
            return p.stat().st_size
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    except OSError:
        return 0


def _referenced(workspace_id: str) -> set[str]:
    refs = set()
    for r in db.conn().execute("SELECT a.path FROM assets a JOIN projects p ON p.id = a.project_id WHERE p.workspace_id = ?", (workspace_id,)):
        refs.add(str(storage.abs_path(r[0])))
    for r in db.conn().execute("SELECT path, json_extract(meta, '$.alpha.path') FROM library WHERE workspace_id = ?", (workspace_id,)):
        for v in r:  # the library file and its cached person matte (cutout.py)
            if v:
                refs.add(str(storage.abs_path(v)))
    for r in db.conn().execute("SELECT u.path FROM uploads u JOIN projects p ON p.id = u.project_id WHERE p.workspace_id = ?", (workspace_id,)):
        if r[0]:
            refs.add(str(storage.abs_path(r[0])))
    return refs


def _young(f: Path, hours: float = 6) -> bool:
    """Files written in the last few hours may belong to a job that is still running."""
    try:
        return (datetime.now().timestamp() - f.stat().st_mtime) < hours * 3600
    except OSError:
        return True


def _finished_projects(workspace_id: str, days: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(0, days))).isoformat(timespec="seconds")
    return db.rows(db.conn().execute(
        "SELECT * FROM projects WHERE workspace_id = ? AND kind != 'tools' AND updated_at < ? AND (status = 'approved' OR id IN "
        "(SELECT project_id FROM publications WHERE remote_id IS NOT NULL AND remote_id != ''))",
        (workspace_id, cutoff)))


def _published_ids(workspace_id: str) -> set[str]:
    return {r[0] for r in db.conn().execute(
        "SELECT DISTINCT project_id FROM publications WHERE workspace_id = ? AND remote_id IS NOT NULL AND remote_id != ''",
        (workspace_id,))}


def usage(workspace_id: str) -> dict:
    ws_dir = storage.abs_path(Path(storage.project_dir(workspace_id, "x")).parent)
    projects = {p["id"]: p for p in db.rows(db.conn().execute(
        "SELECT id, title, status, updated_at FROM projects WHERE workspace_id = ?", (workspace_id,)))}
    published = _published_ids(workspace_id)
    per: list[dict] = []
    kinds_total: dict[str, int] = {}
    for p in projects.values():
        sizes: dict[str, int] = {}
        for a in db.rows(db.conn().execute("SELECT kind, path, archived FROM assets WHERE project_id = ?", (p["id"],))):
            if a.get("archived"):
                continue
            s = _size(storage.abs_path(a["path"]))
            group = "cache" if a["kind"] in CACHE_KINDS else "source" if a["kind"] in SOURCE_KINDS else "render" if a["kind"] in RENDER_KINDS else "other"
            sizes[group] = sizes.get(group, 0) + s
            kinds_total[group] = kinds_total.get(group, 0) + s
        total = _size(storage.abs_path(storage.project_dir(workspace_id, p["id"])))
        per.append({"id": p["id"], "title": p["title"], "status": p["status"], "updated_at": p["updated_at"],
                    "published": p["id"] in published, "total": total, **sizes})
    per.sort(key=lambda x: -x["total"])
    lib_total = sum(_size(storage.abs_path(r[0])) for r in db.conn().execute(
        "SELECT path FROM library WHERE workspace_id = ? AND path IS NOT NULL AND path != ''", (workspace_id,)))
    refs = _referenced(workspace_id)
    orphan_bytes, orphan_n = 0, 0
    if ws_dir.exists():
        for f in ws_dir.rglob("*"):
            if f.is_file() and str(f) not in refs and not _young(f):
                orphan_bytes += f.stat().st_size
                orphan_n += 1
    stale_uploads = db.rows(db.conn().execute(
        "SELECT u.* FROM uploads u JOIN projects p ON p.id = u.project_id WHERE p.workspace_id = ? AND u.done = 0 AND u.created_at < ?",
        (workspace_id, (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds"))))
    return {"disk": storage.disk_usage(), "projects": per, "groups": kinds_total, "library": lib_total,
            "orphans": {"bytes": orphan_bytes, "files": orphan_n},
            "uploads": {"bytes": sum(_size(storage.abs_path(u["path"])) for u in stale_uploads), "count": len(stale_uploads)},
            "finished_projects": len(_finished_projects(workspace_id, 7))}


def _rm(path: Path) -> int:
    n = _size(path)
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    except OSError:
        return 0
    return n


def clean(workspace_id: str, what: list[str], days: int = 7) -> dict:
    freed = 0
    done: dict[str, int] = {}
    if "uploads" in what:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
        rows = db.rows(db.conn().execute(
            "SELECT u.* FROM uploads u JOIN projects p ON p.id = u.project_id WHERE p.workspace_id = ? AND u.done = 0 AND u.created_at < ?",
            (workspace_id, cutoff)))
        for u in rows:
            freed += _rm(storage.abs_path(u["path"]))
            with db.tx() as c:
                c.execute("DELETE FROM uploads WHERE id = ?", (u["id"],))
        done["uploads"] = len(rows)

    def drop_kinds(projects: list[dict], kinds: tuple[str, ...], tag: str) -> int:
        nonlocal freed
        n = 0
        for p in projects:
            rows = db.rows(db.conn().execute(
                f"SELECT * FROM assets WHERE project_id = ? AND archived = 0 AND kind IN ({','.join('?' * len(kinds))})",
                (p["id"], *kinds)))
            for a in rows:
                freed += _rm(storage.abs_path(a["path"]))
                with db.tx() as c:
                    c.execute("DELETE FROM assets WHERE id = ?", (a["id"],))
                n += 1
            if rows:
                with db.tx() as c:
                    cur = db.get("projects", p["id"]) or {}
                    meta = {**(cur.get("meta") or {}), f"cleaned_{tag}": db.now()}
                    db.update(c, "projects", p["id"], {"meta": meta})
        return n

    finished = _finished_projects(workspace_id, days)
    if "cache" in what:
        done["cache"] = drop_kinds(finished, CACHE_KINDS, "cache")
        fr = storage.abs_path("cache") / "frames"   # plan thumbnails — rebuilt on demand
        if fr.exists():
            for f in fr.glob("*.jpg"):
                if not _young(f):
                    freed += _rm(f)
    if "sources" in what:
        done["sources"] = drop_kinds(finished, SOURCE_KINDS, "sources")
    if "renders" in what:
        pub = _published_ids(workspace_id)
        done["renders"] = drop_kinds([p for p in finished if p["id"] in pub], RENDER_KINDS, "renders")
    if "orphans" in what:
        ws_dir = storage.abs_path(Path(storage.project_dir(workspace_id, "x")).parent)
        refs = _referenced(workspace_id)
        known = {r[0] for r in db.conn().execute("SELECT id FROM projects WHERE workspace_id = ?", (workspace_id,))}
        n = 0
        if ws_dir.exists():
            for d in ws_dir.iterdir():
                # whole folders of projects that no longer exist
                if d.is_dir() and d.name.startswith("p_") and d.name[2:] not in known and not any(_young(x) for x in d.rglob("*")):
                    freed += _rm(d)
                    n += 1
            for f in list(ws_dir.rglob("*")):
                if f.is_file() and str(f) not in refs and not _young(f):
                    freed += _rm(f)
                    n += 1
            for d in sorted((x for x in ws_dir.rglob("*") if x.is_dir()), key=lambda x: -len(x.parts)):
                try:
                    d.rmdir()  # only empty folders
                except OSError:
                    pass
        done["orphans"] = n
    return {"freed": freed, "done": done, "disk": storage.disk_usage()}


def delete_archive_copy(workspace_id: str, project_id: str) -> bool:
    """Remove a deleted project's copy from the archive drive / Google Drive too."""
    from . import archive
    rel = str(storage.project_dir(workspace_id, project_id))
    if archive.REMOTE:
        r = archive._rclone("purge", f"{archive.REMOTE}/{rel}")
        return r.returncode == 0
    if settings.archive_root:
        p = settings.archive_root / rel
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
        return True
    return False
