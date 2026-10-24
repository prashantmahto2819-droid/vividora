"""Channel Copilot API: weekly audit, hook scores, comment reply drafts."""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.routing import Route

from .. import db
from ..engine import copilot
from .channels import get_channel
from .deps import ApiError, body, ok, require


def _published_videos(workspace_id: str, channel_id: str | None) -> list[dict]:
    """Re-use the analytics row builder to get videos with yta data."""
    from .analytics import _rows
    return _rows(workspace_id, channel_id)


@require("viewer")
async def audit(request: Request, user: dict):
    """GET /api/copilot/audit?channel=ID — weekly channel audit."""
    ch = get_channel(user["workspace_id"], request.query_params.get("channel"))
    if not ch:
        raise ApiError(404, "channel नहीं मिला")

    def work():
        videos = _published_videos(user["workspace_id"], ch["id"])
        return copilot.weekly_audit(videos, ch.get("name") or "")

    report = await run_in_threadpool(work)
    return ok(report)


@require("viewer")
async def hooks(request: Request, user: dict):
    """GET /api/copilot/hooks?channel=ID — hook-score analysis for recent videos."""
    ch = get_channel(user["workspace_id"], request.query_params.get("channel"))
    if not ch:
        raise ApiError(404, "channel नहीं मिला")

    def work():
        videos = _published_videos(user["workspace_id"], ch["id"])
        results = []
        for v in videos:
            hs = copilot.hook_score(v)
            results.append({
                "id": v["id"],
                "title": v.get("title", ""),
                "url": v.get("url", ""),
                "views": v.get("views", 0),
                "published_at": v.get("published_at", ""),
                "hook": hs,
            })
        results.sort(key=lambda r: r["hook"]["score"], reverse=True)
        return results

    rows = await run_in_threadpool(work)
    return ok(rows)


@require("editor")
async def comment_drafts(request: Request, user: dict):
    """POST /api/copilot/comment-drafts — AI-generated comment reply drafts.

    Body: {"video_id": "...", "video_title": "...", "comments": [...]}
    """
    data = await body(request)
    ch = get_channel(user["workspace_id"], data.get("channel_id"))
    video_title = data.get("video_title") or ""
    comments = data.get("comments") or []

    if not isinstance(comments, list) or not comments:
        raise ApiError(422, "comments list चाहिए")

    channel_name = (ch or {}).get("name") or ""

    def work():
        return copilot.comment_drafts(video_title, comments[:10], channel_name)

    drafts = await run_in_threadpool(work)
    return ok({"drafts": drafts})


routes = [
    Route("/copilot/audit", audit),
    Route("/copilot/hooks", hooks),
    Route("/copilot/comment-drafts", comment_drafts, methods=["POST"]),
]
