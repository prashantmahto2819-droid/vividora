"""Platform export presets and caption styles, loaded from JSON files.

Add a new platform (LinkedIn, WhatsApp Status…) or a new caption look by
dropping a JSON file in presets/platforms or presets/captions — no code change.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..config import settings


def _load_dir(sub: str) -> dict[str, dict]:
    d: Path = settings.presets_dir / sub
    out: dict[str, dict] = {}
    if not d.exists():
        return out
    for f in sorted(d.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        data.setdefault("id", f.stem)
        out[data["id"]] = data
    return out


@lru_cache(maxsize=1)
def platforms() -> dict[str, dict]:
    return _load_dir("platforms")


@lru_cache(maxsize=1)
def caption_styles() -> dict[str, dict]:
    return _load_dir("captions")


def platform(pid: str) -> dict:
    p = platforms().get(pid)
    if not p:
        raise KeyError(f"unknown platform preset: {pid}")
    return p


def caption_style(sid: str) -> dict:
    s = caption_styles().get(sid)
    if not s:
        raise KeyError(f"unknown caption style: {sid}")
    return s
