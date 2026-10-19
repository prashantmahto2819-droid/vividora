"""Dispatch a publication to the right platform. Runs inside the worker."""

from __future__ import annotations

from pathlib import Path

from . import meta, youtube
from .http import PublishError

__all__ = ["run", "PublishError"]


def run(platform: str, secrets: dict, payload: dict, *, video: Path | None, public_url: str | None,
        thumb: Path | None = None, dry_run: bool = False, on_progress=None) -> dict:
    """Returns {remote_id, url, secrets (maybe refreshed)}."""
    if dry_run:
        return {"remote_id": "dry-run", "url": f"https://example.invalid/{platform}/dry-run", "secrets": secrets}
    title = (payload.get("title") or "Untitled")[:100]
    desc = payload.get("description") or ""
    tags = [t.strip().lstrip("#") for t in (payload.get("tags") or []) if t.strip()]
    caption = desc if not tags else f"{desc}\n\n" + " ".join("#" + t.replace(" ", "") for t in tags[:30])

    if platform == "youtube":
        if video is None:
            raise PublishError("video file missing")
        token, new = youtube.access_token(secrets)
        r = youtube.upload_video(token, video, title=title, description=caption, tags=tags,
                                 privacy=payload.get("privacy", "private"), publish_at=payload.get("publish_at"),
                                 category=youtube.CATEGORIES.get(payload.get("category", "people"), "22"),
                                 language=payload.get("language"), on_progress=on_progress)
        if thumb and thumb.exists():
            try:
                youtube.set_thumbnail(token, r["remote_id"], thumb)
            except PublishError as e:  # a missing custom thumbnail is not a failed upload
                r["warning"] = str(e)
        return {**r, "secrets": new}

    if platform in ("instagram", "facebook"):
        if not public_url:
            raise PublishError("PUBLIC_URL सेट नहीं है — Instagram/Facebook को वीडियो का public link चाहिए")
        page_token = secrets["page_token"]
        if platform == "instagram":
            r = meta.ig_publish_reel(secrets["ig_id"], page_token, public_url, caption,
                                     cover_url=payload.get("cover_url"), on_progress=on_progress)
        else:
            sched = payload.get("scheduled_at")
            if payload.get("kind") == "video":
                r = meta.fb_publish_video(secrets["page_id"], page_token, public_url, caption, title=title,
                                          scheduled_at=sched)
            else:
                r = meta.fb_publish_reel(secrets["page_id"], page_token, public_url, caption, title=title,
                                         scheduled_at=sched, on_progress=on_progress)
        return {**r, "secrets": secrets}

    raise PublishError(f"unknown platform {platform}")
