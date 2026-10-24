"""Where files live on disk.

MEDIA_ROOT/
  ws_<workspace>/p_<project>/
    raw/<original>          the upload
    work/                   proxy, audio, intermediate files
    out/                    finished renders

With RAW_ROOT set (e.g. the Windows D: drive shared into the VM) the big
originals — raw/ uploads and library videos/music/images — are written there
instead, while proxies, renders and the database stay on MEDIA_ROOT. Paths in
the database stay the same; abs_path() finds the file on whichever disk has it.
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


COLD_LIBRARY = {"broll", "music", "image", "video", "sfx"}


def is_cold(rel: str | Path) -> bool:
    """Big originals that belong on RAW_ROOT."""
    parts = Path(rel).parts
    if len(parts) >= 3 and parts[1].startswith("p_") and parts[2] in ("raw", "clips"):
        return True
    return len(parts) >= 3 and parts[1] == "library" and parts[2] in COLD_LIBRARY


def _under(root: Path, rel: str | Path) -> Path:
    p = (root / rel).resolve()
    if root not in p.parents and p != root:  # never allow escaping the root
        raise ValueError("path outside media root")
    return p


MARKER = ".vividora-share"


def raw_active() -> bool:
    """The D-drive share is used only when it is really mounted: the folder must contain the
    marker file (created once on Windows). If the share is missing after a reboot, files go to
    the VM disk instead of silently filling the empty mount point."""
    return bool(settings.raw_root) and (settings.raw_root / MARKER).exists()


def abs_path(rel: str | Path) -> Path:
    p = _under(settings.media_root, rel)
    if settings.raw_root and is_cold(rel) and (raw_active() or _under(settings.raw_root, rel).exists()):
        r = _under(settings.raw_root, rel)
        # new files go to the share; files written before it was set up are still found on MEDIA_ROOT
        if r.exists() or not p.exists():
            return r
    return p


def ensure_parent(rel: str | Path) -> Path:
    p = abs_path(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


_IMAGE_MAGIC = (b"\x89PNG", b"\xff\xd8\xff", b"RIFF", b"GIF8")
_FONT_MAGIC = (b"\x00\x01\x00\x00", b"OTTO", b"true", b"wOFF", b"wOF2")


def validate_media(path: str | Path, kind: str) -> None:
    """Refuse files whose bytes are not the media the name says (upload validation).
    video/music/sfx/broll → ffprobe must find a stream; images → magic bytes; font → sfnt/woff header."""
    from .api.deps import ApiError
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        raise ApiError(422, "फ़ाइल खाली है")
    if kind in ("video", "music", "sfx", "broll", "audio", "clip"):
        import json as _json
        import subprocess
        try:
            out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(p)],
                                 capture_output=True, text=True, timeout=60).stdout
            types = {s.get("codec_type") for s in (_json.loads(out or "{}").get("streams") or [])}
        except (OSError, ValueError, subprocess.TimeoutExpired):
            types = set()
        need = {"video", "audio"} if kind in ("video", "broll", "clip", "music") else {"audio"}
        if not types & need:
            raise ApiError(422, "यह video/audio फ़ाइल नहीं है या टूटी हुई है — दूसरी फ़ाइल चुनें")
    elif kind in ("image", "logo", "frame", "sticker"):
        with p.open("rb") as f:
            head = f.read(16)
        if not head.startswith(_IMAGE_MAGIC) and not head.lstrip().startswith((b"<svg", b"<?xml")):
            raise ApiError(422, "यह image फ़ाइल नहीं है")
    elif kind == "font":
        with p.open("rb") as f:
            head = f.read(4)
        if head not in _FONT_MAGIC:
            raise ApiError(422, "यह font फ़ाइल नहीं है (ttf/otf/woff)")


def guess_mime(path: str | Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def file_size(rel: str | Path) -> int:
    p = abs_path(rel)
    return p.stat().st_size if p.exists() else 0


def remove_project_files(workspace_id: str, project_id: str) -> None:
    rel = project_dir(workspace_id, project_id)
    for root in (settings.media_root, settings.raw_root):
        if root:
            p = _under(root, rel)
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)


def disk_usage() -> dict:
    root = settings.media_root
    root.mkdir(parents=True, exist_ok=True)
    du = shutil.disk_usage(root)
    out = {"media": {"total": du.total, "used": du.used, "free": du.free}}
    if settings.raw_root and settings.raw_root.exists():
        dr = shutil.disk_usage(settings.raw_root)
        out["raw"] = {"total": dr.total, "used": dr.used, "free": dr.free, "active": raw_active()}
    if settings.archive_root and settings.archive_root.exists():
        da = shutil.disk_usage(settings.archive_root)
        out["archive"] = {"total": da.total, "used": da.used, "free": da.free}
    return out
