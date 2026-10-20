"""Dispatch a publication to the right platform. Runs inside the worker."""

from __future__ import annotations

from pathlib import Path

from . import meta, youtube
from .http import PublishError

__all__ = ["run", "PublishError"]


def _thumb_ok(path: Path) -> bool:
    """Only a real custom thumbnail (≥ 1280 wide, ≤ 2 MB) — never a small preview still."""
    if path.stat().st_size > 2 * 1024 * 1024:
        return False
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.width >= 1280 and im.height >= 720
    except ImportError:
        return True
    except Exception:  # noqa: BLE001
        return False


def run(platform: str, secrets: dict, payload: dict, *, video: Path | None, public_url: str | None,
        thumb: Path | None = None, dry_run: bool = False, on_progress=None, captions_srt: str | None = None) -> dict:
    """Returns {remote_id, url, secrets (maybe refreshed), warning?, warnings?, chain?, reauth?}.
    Only the upload itself can fail the job; YouTube's after-upload steps (playlist, first comment,
    captions, localizations) are best-effort and come back as warnings."""
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
        lang = "en" if payload.get("language") == "en" else "hi"
        cat = str(payload.get("category") or "people")
        r = youtube.upload_video(token, video, title=title, description=caption, tags=tags,
                                 privacy=payload.get("privacy", "private"), publish_at=payload.get("publish_at"),
                                 category=cat if cat.isdigit() else youtube.CATEGORIES.get(cat, "22"),
                                 language=lang, made_for_kids=False, synthetic=bool(payload.get("ai_content")),
                                 on_progress=on_progress)
        warnings: list[str] = []
        if thumb and thumb.exists() and _thumb_ok(thumb):
            try:
                youtube.set_thumbnail(token, r["remote_id"], thumb)
            except PublishError as e:  # a missing custom thumbnail is not a failed upload
                warnings.append(str(e))
        chain = youtube.post_publish(token, r["remote_id"], new, playlist_id=payload.get("playlist_id"),
                                     first_comment=payload.get("first_comment"), srt=captions_srt, language=lang,
                                     localizations=payload.get("localizations"))
        warnings += chain["warnings"]
        if warnings:
            r["warning"] = " · ".join(warnings)[:1000]
            r["warnings"] = warnings
        return {**r, "secrets": new, "chain": chain["done"], "reauth": chain["reauth"]}

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
