"""YouTube → Shorts/Reels converter API.

POST /api/yt-shorts          start a yt-shorts job (download + optional autopilot)
GET  /api/yt-shorts          list recent yt-shorts jobs for this workspace
POST /api/yt-shorts/{id}/cancel   cancel a queued/running job
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.routing import Route

from .. import db, queue, service
from .deps import ApiError, body, need, ok, require


@require("editor")
async def start(request: Request, user: dict):
    """Accept a YouTube URL, queue a yt_shorts job that downloads, creates a project,
    and optionally runs highlight detection."""
    data = await body(request)
    need(data, "url")
    url = str(data["url"]).strip()
    if not _valid_yt_url(url):
        raise ApiError(422, "YouTube URL नहीं दिख रहा — पूरा link डालें (https://youtube.com/watch?v=… या youtu.be/…)")

    fmt = data.get("format") or "shorts"
    if fmt not in ("shorts", "reels", "both", "square"):
        fmt = "shorts"

    auto_edit = bool(data.get("auto_edit", True))
    count = min(int(data.get("count") or 5), 10)
    min_len = max(10.0, float(data.get("min_len") or 25))
    max_len = min(90.0, float(data.get("max_len") or 58))

    with db.tx() as c:
        tp = service.tools_project(c, user["workspace_id"])
        payload = {
            "url": url,
            "format": fmt,
            "auto_edit": auto_edit,
            "count": count,
            "min_len": min_len,
            "max_len": max_len,
            "user_id": user["id"],
            "workspace_id": user["workspace_id"],
            "channel_id": data.get("channel_id") or "",
        }
        job = queue.enqueue(c, tp["id"], "yt_shorts", payload)
        service.log(c, user["workspace_id"], "ytshorts.start", user_id=user["id"],
                    project_id=tp["id"], detail={"url": url, "format": fmt})

    return ok({"job": job}, 201)


@require("viewer")
async def list_jobs(request: Request, user: dict):
    """Recent yt-shorts jobs for the workspace."""
    cn = db.conn()
    tp = db.row(cn.execute(
        "SELECT id FROM projects WHERE workspace_id = ? AND kind = 'tools' LIMIT 1",
        (user["workspace_id"],)).fetchone())
    if not tp:
        return ok({"jobs": []})

    jobs = db.rows(cn.execute(
        "SELECT * FROM jobs WHERE project_id = ? AND kind = 'yt_shorts' ORDER BY created_at DESC LIMIT 20",
        (tp["id"],)))

    out = []
    for j in jobs:
        res = j.get("result") or {}
        pl = j.get("payload") or {}
        project = db.get("projects", res["project_id"]) if res.get("project_id") else None
        out.append({
            "id": j["id"],
            "status": j["status"],
            "progress": j.get("progress"),
            "message": j.get("message"),
            "error": j.get("error"),
            "created_at": j["created_at"],
            "finished_at": j.get("finished_at"),
            "url": pl.get("url"),
            "format": pl.get("format"),
            "auto_edit": pl.get("auto_edit"),
            "result": {k: v for k, v in res.items() if k not in ("files",)},
            "project": {"id": project["id"], "title": project["title"], "status": project["status"]}
            if project else None,
        })
    return ok({"jobs": out})


@require("editor")
async def cancel(request: Request, user: dict):
    job = db.get("jobs", request.path_params["job_id"])
    pr = db.get("projects", job["project_id"]) if job else None
    if not job or not pr or pr["workspace_id"] != user["workspace_id"] or job["kind"] != "yt_shorts":
        raise ApiError(404, "job not found")
    with db.tx() as c:
        if job["status"] in ("queued", "running"):
            db.update(c, "jobs", job["id"], {"status": "cancelled", "finished_at": db.now(), "message": "रद्द"})
    return ok()


def _valid_yt_url(url: str) -> bool:
    import re
    return bool(re.match(
        r"https?://(www\.)?(youtube\.com/(watch\?|shorts/|embed/|live/)|youtu\.be/|m\.youtube\.com/)", url))


routes = [
    Route("/yt-shorts", list_jobs),
    Route("/yt-shorts", start, methods=["POST"]),
    Route("/yt-shorts/{job_id}/cancel", cancel, methods=["POST"]),
]
