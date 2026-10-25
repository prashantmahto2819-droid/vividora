"""Creator performance dashboard — aggregated stats for the workspace/channel."""

from __future__ import annotations

import json

from starlette.requests import Request
from starlette.routing import Route

from .. import db
from .deps import ok, require


def _project_stats(workspace_id: str, channel_id: str | None) -> dict:
    cn = db.conn()
    base = "SELECT status, COUNT(*) as cnt FROM projects WHERE workspace_id = ?"
    args: list = [workspace_id]
    if channel_id:
        base += " AND channel_id = ?"
        args.append(channel_id)
    rows = db.rows(cn.execute(base + " GROUP BY status", args))
    by_status = {r["status"]: r["cnt"] for r in rows}
    total = sum(by_status.values())
    return {"total": total, "by_status": by_status}


def _publish_stats(workspace_id: str, channel_id: str | None) -> dict:
    cn = db.conn()
    q = ("SELECT p.platform, p.status, COUNT(*) as cnt "
         "FROM publications p "
         "JOIN projects pr ON pr.id = p.project_id "
         "WHERE p.workspace_id = ?")
    args: list = [workspace_id]
    if channel_id:
        q += " AND pr.channel_id = ?"
        args.append(channel_id)
    q += " GROUP BY p.platform, p.status"
    rows = db.rows(cn.execute(q, args))

    by_platform: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for r in rows:
        by_platform[r["platform"]] = by_platform.get(r["platform"], 0) + r["cnt"]
        by_status[r["status"]] = by_status.get(r["status"], 0) + r["cnt"]
    return {"total": sum(by_platform.values()), "by_platform": by_platform, "by_status": by_status}


def _render_stats(workspace_id: str, channel_id: str | None) -> dict:
    cn = db.conn()
    q = ("SELECT COUNT(*) as cnt, "
         "COALESCE(SUM(CASE WHEN j.status='done' THEN 1 ELSE 0 END),0) as done, "
         "COALESCE(SUM(CASE WHEN j.status='failed' THEN 1 ELSE 0 END),0) as failed "
         "FROM jobs j JOIN projects pr ON pr.id = j.project_id "
         "WHERE pr.workspace_id = ? AND j.kind = 'render'")
    args: list = [workspace_id]
    if channel_id:
        q += " AND pr.channel_id = ?"
        args.append(channel_id)
    r = db.row(cn.execute(q, args).fetchone()) or {"cnt": 0, "done": 0, "failed": 0}
    return {"total": r["cnt"], "done": r["done"], "failed": r["failed"]}


def _recent_activity(workspace_id: str, channel_id: str | None, limit: int = 15) -> list[dict]:
    cn = db.conn()
    q = ("SELECT j.kind, j.status, j.created_at, j.finished_at, pr.title "
         "FROM jobs j JOIN projects pr ON pr.id = j.project_id "
         "WHERE pr.workspace_id = ? AND j.status IN ('done','failed')")
    args: list = [workspace_id]
    if channel_id:
        q += " AND pr.channel_id = ?"
        args.append(channel_id)
    q += " ORDER BY j.finished_at DESC LIMIT ?"
    args.append(limit)
    return [{"kind": r["kind"], "status": r["status"], "title": r["title"],
             "created_at": r["created_at"], "finished_at": r["finished_at"]}
            for r in db.rows(cn.execute(q, args))]


def _storage_stats(workspace_id: str) -> dict:
    cn = db.conn()
    assets = cn.execute(
        "SELECT COALESCE(SUM(a.size),0) FROM assets a JOIN projects p ON p.id = a.project_id "
        "WHERE p.workspace_id = ? AND a.archived = 0", (workspace_id,)).fetchone()[0]
    library = cn.execute(
        "SELECT COALESCE(SUM(size),0) FROM library WHERE workspace_id = ?",
        (workspace_id,)).fetchone()[0]
    total = int(assets or 0) + int(library or 0)
    return {"total_bytes": total, "assets_bytes": int(assets or 0), "library_bytes": int(library or 0)}


def _weekly_publishes(workspace_id: str, channel_id: str | None, weeks: int = 12) -> list[dict]:
    """Publish counts per ISO week for the last N weeks."""
    cn = db.conn()
    q = ("SELECT strftime('%Y-W%W', p.finished_at) as week, COUNT(*) as cnt "
         "FROM publications p "
         "JOIN projects pr ON pr.id = p.project_id "
         "WHERE p.workspace_id = ? AND p.status = 'done' "
         "AND p.finished_at >= date('now', ?)")
    args: list = [workspace_id, f"-{weeks * 7} days"]
    if channel_id:
        q += " AND pr.channel_id = ?"
        args.append(channel_id)
    q += " GROUP BY week ORDER BY week"
    return [{"week": r["week"], "count": r["cnt"]} for r in db.rows(cn.execute(q, args))]


def _top_templates(workspace_id: str, channel_id: str | None, limit: int = 10) -> list[dict]:
    """Most-used templates (by project settings.template_id)."""
    cn = db.conn()
    q = ("SELECT json_extract(settings, '$.template_id') as tid, COUNT(*) as cnt "
         "FROM projects WHERE workspace_id = ? AND json_extract(settings, '$.template_id') IS NOT NULL")
    args: list = [workspace_id]
    if channel_id:
        q += " AND channel_id = ?"
        args.append(channel_id)
    q += " GROUP BY tid ORDER BY cnt DESC LIMIT ?"
    args.append(limit)
    rows = db.rows(cn.execute(q, args))
    return [{"template_id": r["tid"], "count": r["cnt"]} for r in rows]


@require("viewer")
async def dashboard(request: Request, user: dict):
    ch = request.query_params.get("channel") or None
    ws = user["workspace_id"]
    return ok({
        "projects": _project_stats(ws, ch),
        "publishes": _publish_stats(ws, ch),
        "renders": _render_stats(ws, ch),
        "storage": _storage_stats(ws),
        "recent": _recent_activity(ws, ch),
        "weekly": _weekly_publishes(ws, ch),
        "templates": _top_templates(ws, ch),
    })


routes = [
    Route("/dashboard", dashboard),
]
