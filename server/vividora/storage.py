"""Where files live on disk.

MEDIA_ROOT/
  ws_<workspace>/p_<project>/
    raw/<original>          the upload
    work/                   proxy, audio, intermediate files
    out/                    finished renders
"""

from __future__ import annotations

import mimetypes
import re
import shutil
from pathlib import Path

from .config import settings

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(name: str, default: str = "file") -> str:
    stem = _SAFE.sub("_", Path(name).name).strip("._")
    return stem[:120] or default


def project_dir(workspace_id: str, project_id: str) -> Path:
    return Path(f"ws_{workspace_id}") / f"p_{project_id}"


def abs_path(rel: str | Path) -> Path:
    p = (settings.media_root / rel).resolve()
    # never allow escaping MEDIA_ROOT
    if settings.media_root not in p.parents and p != settings.media_root:
        raise ValueError("path outside media root")
    return p


def ensure_parent(rel: str | Path) -> Path:
    p = abs_path(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def guess_mime(path: str | Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def file_size(rel: str | Path) -> int:
    p = abs_path(rel)
    return p.stat().st_size if p.exists() else 0


def remove_project_files(workspace_id: str, project_id: str) -> None:
    p = abs_path(project_dir(workspace_id, project_id))
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)


def disk_usage() -> dict:
    root = settings.media_root
    root.mkdir(parents=True, exist_ok=True)
    du = shutil.disk_usage(root)
    out = {"media": {"total": du.total, "used": du.used, "free": du.free}}
    if settings.archive_root and settings.archive_root.exists():
        da = shutil.disk_usage(settings.archive_root)
        out["archive"] = {"total": da.total, "used": da.used, "free": da.free}
    return out
