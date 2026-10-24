"""Dashboard overview: running jobs with progress, the publish queue / calendar."""

from __future__ import annotations

from starlette.requests import Request
from starlette.routing import Route

from .. import db
from .deps import ok, require


def _pubs(workspace_id: str, channel: str | None, limit: int = 200) -> list[dict]:
    q = ("SELECT pb.id, pb.project_id, pb.platform, pb.status, pb.payload, pb.url, pb.error, pb.created_at, pb.finished_at, "
         "p.title AS project_title, p.channel_id, c.name AS connection_name FROM publications pb "
         "JOIN projects p ON p.id = pb.project_id LEFT JOIN connections c ON c.id = pb.connection_id WHERE pb.workspace_id = ?")
    args: list = [workspace_id]
    if channel:
        q += " AND p.channel_id = ?"
        args.append(channel)
    q += " ORDER BY pb.created_at DESC LIMIT ?"
    args.append(limit)
    out = []
    for r in db.rows(db.conn().execute(q, args)):
        pl = r.pop("payload") or {}
        r["title"] = pl.get("title") or r["project_title"]
        r["when"] = pl.get("publish_at") or pl.get("scheduled_at") or None
        r["privacy"] = pl.get("privacy")
        out.append(r)
    return out


@require("viewer")
async def overview(request: Request, user: dict):
    ws = user["workspace_id"]
    channel = request.query_params.get("channel") or None
    jq = ("SELECT j.id, j.project_id, j.kind, j.status, j.progress, j.message, j.created_at, j.started_at, p.title AS project_title, p.channel_id "
          "FROM jobs j JOIN projects p ON p.id = j.project_id WHERE p.workspace_id = ? AND j.status IN ('queued','running')")
    args: list = [ws]
    if channel:
        jq += " AND p.channel_id = ?"
        args.append(channel)
    jobs = db.rows(db.conn().execute(jq + " ORDER BY j.status = 'running' DESC, j.created_at LIMIT 30", args))
    pubs = _pubs(ws, channel, 120)
    now = db.now()
    upcoming = sorted([p for p in pubs if p["status"] in ("queued", "running") or (p["when"] and p["when"] > now)],
                      key=lambda p: p["when"] or p["created_at"])
    recent = [p for p in pubs if p["status"] == "done" and not (p["when"] and p["when"] > now)][:10]
    counts = dict(db.conn().execute("SELECT status, COUNT(*) FROM projects WHERE workspace_id = ? AND kind != 'tools'" + (" AND channel_id = ?" if channel else "")
                                    + " GROUP BY status", [ws, channel] if channel else [ws]).fetchall())
    return ok({"jobs": jobs, "upcoming": upcoming[:20], "recent": recent, "counts": counts})


@require("viewer")
async def publications(request: Request, user: dict):
    return ok(_pubs(user["workspace_id"], request.query_params.get("channel") or None, 300))


routes = [
    Route("/overview", overview),
    Route("/publications", publications),
]
