"""Nightly SQLite backup: a consistent copy via the online backup API into DATA_ROOT/backups
(keeps BACKUP_KEEP_DAYS, default 7), pushed to the archive remote (rclone / local archive) when one
is configured. The media archive (archive.py) already covers the big files; this covers the database
— projects, settings, transcripts, users, subscriptions."""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db
from .config import settings

log = logging.getLogger("vividora.backup")


def backup_dir() -> Path:
    d = settings.data_root / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run(keep_days: int | None = None) -> Path:
    """Make one backup file now; prune old ones; push to the archive remote if configured."""
    keep = settings.backup_keep_days if keep_days is None else keep_days
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = backup_dir() / f"vividora-{stamp}.db"
    src = db.conn()
    dst = sqlite3.connect(str(out))
    try:
        src.backup(dst)  # consistent even while the app writes (WAL)
    finally:
        dst.close()
    # keep the file small-ish: a VACUUMed copy is fully self-contained (no -wal/-shm)
    try:
        subprocess.run(["sqlite3", str(out), "VACUUM"], capture_output=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired):
        pass
    prune(keep)
    _push(out)
    log.info("db backup %s (%d KB)", out.name, out.stat().st_size // 1024)
    return out


def prune(keep_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    n = 0
    for f in backup_dir().glob("vividora-*.db"):
        try:
            when = datetime.strptime(f.name[9:24], "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if when < cutoff:
            f.unlink(missing_ok=True)
            n += 1
    return n


def _push(path: Path) -> None:
    from . import archive
    try:
        if archive.REMOTE:
            r = archive._rclone("copyto", str(path), f"{archive.REMOTE}/backups/{path.name}")
            if r.returncode != 0:
                log.warning("backup push failed: %s", r.stderr[-200:])
        elif settings.archive_root:
            d = settings.archive_root / "backups"
            d.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(path), str(d / path.name))
    except Exception as e:  # noqa: BLE001
        log.warning("backup push: %s", e)


def latest() -> dict | None:
    files = sorted(backup_dir().glob("vividora-*.db"))
    if not files:
        return None
    f = files[-1]
    return {"file": f.name, "size": f.stat().st_size, "at": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
            "count": len(files)}


def due() -> bool:
    """One backup per UTC day."""
    lt = latest()
    if not lt:
        return True
    return lt["at"][:10] != datetime.now(timezone.utc).strftime("%Y-%m-%d")


def restore_hint() -> str:
    return (f"restore: stop the app, copy DATA_ROOT/backups/<file>.db over {os.path.basename(settings.database_path)} "
            "(delete the -wal/-shm files next to it), start the app")
