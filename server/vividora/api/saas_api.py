"""SaaS routes: plan + usage (every user), billing (admin), workspaces overview + audit log + backups
(admin). The Razorpay webhook is public (signature-verified)."""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route

from .. import backup, db, saas, service
from ..billing import razorpay
from ..config import settings
from .deps import ApiError, body, ok, rate_limit, require

log = logging.getLogger("vividora.saas")


@require("viewer")
async def my_plan(request: Request, user: dict):
    s = saas.summary(user["workspace_id"])
    return ok({**s, "saas": saas.enabled(), "plans": saas.plans() if saas.enabled() else [],
               "billing": razorpay.configured(), "invoices": razorpay.invoices(user["workspace_id"]) if saas.enabled() else []})


@require("admin")
async def checkout(request: Request, user: dict):
    if not saas.enabled():
        raise ApiError(404, "SaaS mode बंद है")
    rate_limit(request, "billing", 10, 10)
    data = await body(request)
    try:
        r = razorpay.checkout(user["workspace_id"], user, str(data.get("plan") or ""), str(data.get("cycle") or "monthly"))
    except ValueError as e:
        raise ApiError(422, str(e))
    except RuntimeError as e:
        raise ApiError(502, str(e))
    with db.tx() as c:
        service.log(c, user["workspace_id"], "billing.checkout", user_id=user["id"], detail={"plan": data.get("plan"), "cycle": data.get("cycle")})
    return ok(r)


@require("admin")
async def cancel(request: Request, user: dict):
    data = await body(request)
    try:
        r = razorpay.cancel(user["workspace_id"], at_cycle_end=bool(data.get("at_cycle_end", True)))
    except ValueError as e:
        raise ApiError(422, str(e))
    except RuntimeError as e:
        raise ApiError(502, str(e))
    with db.tx() as c:
        service.log(c, user["workspace_id"], "billing.cancel", user_id=user["id"])
    return ok(r)


@require("viewer")
async def receipt(request: Request, user: dict):
    inv = db.get("invoices", request.path_params["invoice_id"])
    if not inv or inv["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "receipt नहीं मिली")
    if request.query_params.get("format") == "json":
        return ok(inv)
    ws = db.get("workspaces", user["workspace_id"])
    return HTMLResponse(razorpay.receipt_html(inv, ws, saas.plan(inv["plan_id"])))


async def razorpay_hook(request: Request):
    """Public. Razorpay signs the raw body; nothing is written before the signature checks out."""
    rate_limit(request, "hook", 120, 120)
    raw = await request.body()
    sig = request.headers.get("x-razorpay-signature")
    if not razorpay.verify_signature(raw, sig):
        raise ApiError(401, "bad signature")
    import json
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        raise ApiError(400, "invalid JSON")
    r = razorpay.handle_event(payload, request.headers.get("x-razorpay-event-id"))
    return ok(r)


# ------------------------------------------------------------------ admin: workspaces, audit, backups


@require("admin")
async def workspaces(request: Request, user: dict):
    """Every workspace with plan + usage. The operator's own workspace is the one bootstrap created
    (OPERATOR_WORKSPACE env can pin it); other admins see only theirs."""
    op = settings.operator_workspace or db.conn().execute("SELECT id FROM workspaces ORDER BY created_at LIMIT 1").fetchone()[0]
    if user["workspace_id"] != op:
        rows = [db.get("workspaces", user["workspace_id"])]
    else:
        rows = db.rows(db.conn().execute("SELECT * FROM workspaces ORDER BY created_at"))
    out = []
    for ws in rows:
        s = saas.summary(ws["id"])
        n_users = db.conn().execute("SELECT COUNT(*) FROM users WHERE workspace_id = ?", (ws["id"],)).fetchone()[0]
        n_proj = db.conn().execute("SELECT COUNT(*) FROM projects WHERE workspace_id = ? AND kind != 'tools'", (ws["id"],)).fetchone()[0]
        owner = db.get("users", ws.get("owner_id")) if ws.get("owner_id") else None
        out.append({"id": ws["id"], "name": ws["name"], "created_at": ws["created_at"], "users": n_users, "projects": n_proj,
                    "owner": owner["email"] if owner else None, "plan": s.get("plan"), "status": s.get("status"),
                    "period_end": s.get("period_end"), "usage": s.get("usage"), "left": s.get("left")})
    return ok({"operator": user["workspace_id"] == op, "workspaces": out})


@require("admin")
async def set_plan(request: Request, user: dict):
    """Operator only: give a workspace a plan by hand (comp, testing, offline payment)."""
    op = settings.operator_workspace or db.conn().execute("SELECT id FROM workspaces ORDER BY created_at LIMIT 1").fetchone()[0]
    if user["workspace_id"] != op:
        raise ApiError(403, "सिर्फ़ operator")
    data = await body(request)
    ws = db.get("workspaces", request.path_params["workspace_id"])
    if not ws:
        raise ApiError(404, "workspace नहीं")
    plan = saas.plan(str(data.get("plan") or ""))
    if not plan:
        raise ApiError(422, "plan नहीं")
    from datetime import datetime, timedelta, timezone
    days = int(data.get("days") or 30)
    now = datetime.now(timezone.utc)
    with db.tx() as c:
        sub = saas.subscription(ws["id"]) or saas.start_trial(c, ws["id"])
        db.update(c, "subscriptions", sub["id"], {"plan_id": plan["id"], "status": "active", "cycle": data.get("cycle") or "monthly",
                                                   "period_start": now.isoformat(timespec="seconds"),
                                                   "period_end": (now + timedelta(days=days)).isoformat(timespec="seconds"),
                                                   "trial_end": None, "updated_at": db.now(),
                                                   "meta": {**(sub.get("meta") or {}), "manual_by": user["id"]}})
        service.log(c, ws["id"], "billing.manual_plan", user_id=user["id"], detail={"plan": plan["id"], "days": days})
    return ok(saas.summary(ws["id"]))


@require("admin")
async def audit(request: Request, user: dict):
    q = request.query_params
    limit = max(1, min(500, int(q.get("limit") or 200)))
    before = q.get("before")
    sql = "SELECT a.*, u.name AS user_name, u.email AS user_email FROM activity a LEFT JOIN users u ON u.id = a.user_id WHERE a.workspace_id = ?"
    args: list = [user["workspace_id"]]
    if q.get("action"):
        sql += " AND a.action LIKE ?"
        args.append(q["action"] + "%")
    if before:
        sql += " AND a.id < ?"
        args.append(int(before))
    sql += " ORDER BY a.id DESC LIMIT ?"
    args.append(limit)
    return ok(db.rows(db.conn().execute(sql, args)))


@require("admin")
async def backups(request: Request, user: dict):
    return ok({"latest": backup.latest(), "keep_days": settings.backup_keep_days, "dir": str(backup.backup_dir()),
               "restore": backup.restore_hint()})


@require("admin")
async def backup_now(request: Request, user: dict):
    from starlette.concurrency import run_in_threadpool
    out = await run_in_threadpool(backup.run)
    with db.tx() as c:
        service.log(c, user["workspace_id"], "backup.run", user_id=user["id"], detail={"file": out.name})
    return ok({"file": out.name, "size": out.stat().st_size})


routes = [
    Route("/plan", my_plan),
    Route("/billing/checkout", checkout, methods=["POST"]),
    Route("/billing/cancel", cancel, methods=["POST"]),
    Route("/billing/invoices/{invoice_id}", receipt),
    Route("/hooks/razorpay", razorpay_hook, methods=["POST"]),
    Route("/admin/workspaces", workspaces),
    Route("/admin/workspaces/{workspace_id}/plan", set_plan, methods=["POST"]),
    Route("/admin/audit", audit),
    Route("/admin/backups", backups),
    Route("/admin/backups", backup_now, methods=["POST"]),
]
