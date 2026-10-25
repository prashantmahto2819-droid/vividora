"""SaaS layer: plans, subscriptions, usage, quotas, login lockout, rate limits.

Everything here is a no-op unless SAAS_MODE=1 (env). The self-hosted single
workspace keeps working exactly as before: no signup page, no quotas, no
billing UI. With SAAS_MODE=1:

  * every workspace has a subscription (Free trial on signup);
  * quotas from the plan's `limits` are enforced at the choke points
    (queue.claim, request_render, uploads, LLM calls, premium voices);
  * usage per billing period is counted in the `usage` table.

Prices are NOT hardcoded: PLANS_JSON (env, a JSON list) or
server/presets/plans.json overrides the seed below.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db
from .config import settings

log = logging.getLogger("vividora.saas")

TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "14"))

# Placeholder limits — business numbers come from PLANS_JSON / presets/plans.json
SEED_PLANS = [
    {"id": "free", "name": "Free (trial)", "price_inr": {"monthly": 0, "quarterly": 0, "annual": 0}, "order": 0,
     "limits": {"ai_credits": 30, "render_minutes": 30, "storage_gb": 5, "max_export_height": 1080,
                "concurrent_jobs": 1, "premium_voices": False, "music_gen": False, "templates": 10}},
    {"id": "creator", "name": "Creator", "price_inr": {"monthly": 499, "quarterly": 1299, "annual": 4799}, "order": 1,
     "limits": {"ai_credits": 300, "render_minutes": 300, "storage_gb": 50, "max_export_height": 1080,
                "concurrent_jobs": 1, "premium_voices": True, "music_gen": False, "templates": 100}},
    {"id": "studio", "name": "Studio", "price_inr": {"monthly": 1499, "quarterly": 3999, "annual": 14399}, "order": 2,
     "limits": {"ai_credits": 1500, "render_minutes": 1500, "storage_gb": 250, "max_export_height": 2160,
                "concurrent_jobs": 2, "premium_voices": True, "music_gen": True, "templates": 1000}},
]
UNLIMITED = {"ai_credits": 10**9, "render_minutes": 10**9, "storage_gb": 10**6, "max_export_height": 4320,
             "concurrent_jobs": 10**3, "premium_voices": True, "music_gen": True, "templates": 10**6}


def enabled() -> bool:
    return settings.saas_mode


class QuotaError(Exception):
    """A plan limit was hit. `code` names the limit (storage, ai_credits, render_minutes, export_height,
    premium_voices, concurrent_jobs); message is for the creator (Hindi)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ----------------------------------------------------------------------------- plans


def _plan_source() -> list[dict]:
    raw = os.getenv("PLANS_JSON")
    if raw:
        try:
            return json.loads(raw)
        except ValueError:
            log.warning("PLANS_JSON is not valid JSON — using presets/plans.json / seed")
    f = Path(settings.presets_dir) / "plans.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            log.warning("presets/plans.json is not valid JSON — using seed plans")
    return SEED_PLANS


def seed_plans(c) -> None:
    """Insert / refresh the plan rows from the configured source (idempotent)."""
    for p in _plan_source():
        row = {"id": p["id"], "name": p["name"], "price_inr": p.get("price_inr") or {}, "limits": p.get("limits") or {},
               "active": bool(p.get("active", True)), "sort": int(p.get("order", 0)), "updated_at": db.now()}
        if c.execute("SELECT 1 FROM plans WHERE id = ?", (p["id"],)).fetchone():
            db.update(c, "plans", p["id"], row)
        else:
            db.insert(c, "plans", {**row, "created_at": db.now()})


def plans() -> list[dict]:
    return db.rows(db.conn().execute("SELECT * FROM plans WHERE active = 1 ORDER BY sort, id"))


def plan(plan_id: str) -> dict | None:
    return db.get("plans", plan_id)


# ----------------------------------------------------------------------------- subscriptions


def subscription(workspace_id: str) -> dict | None:
    return db.row(db.conn().execute("SELECT * FROM subscriptions WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 1",
                                    (workspace_id,)).fetchone())


def start_trial(c, workspace_id: str) -> dict:
    now = datetime.now(timezone.utc)
    sub = {"id": db.new_id(), "workspace_id": workspace_id, "plan_id": "free", "status": "trialing",
           "period_start": now.isoformat(timespec="seconds"), "period_end": (now + timedelta(days=TRIAL_DAYS)).isoformat(timespec="seconds"),
           "trial_end": (now + timedelta(days=TRIAL_DAYS)).isoformat(timespec="seconds"), "cycle": "monthly",
           "razorpay_subscription_id": None, "razorpay_customer_id": None, "meta": {}, "created_at": db.now(), "updated_at": db.now()}
    db.insert(c, "subscriptions", sub)
    return sub


def effective(workspace_id: str) -> dict:
    """{plan, limits, status, period_start, period_end, expired} for the workspace. Without SAAS_MODE
    everything is unlimited."""
    if not enabled():
        return {"plan": None, "limits": dict(UNLIMITED), "status": "self-hosted", "period_start": None, "period_end": None,
                "expired": False}
    sub = subscription(workspace_id)
    if sub is None:
        # a workspace from before SAAS_MODE was switched on: give it the trial so nothing breaks today
        with db.tx() as c:
            sub = start_trial(c, workspace_id)
    p = plan(sub["plan_id"]) or {"limits": SEED_PLANS[0]["limits"]}
    now = db.now()
    expired = sub["status"] in ("cancelled", "expired", "past_due") or (sub.get("period_end") or "9") < now
    limits = dict(p["limits"] or {})
    if expired:
        # expired / unpaid: read-only-ish — no new AI, renders capped low, uploads blocked
        limits = {**limits, "ai_credits": 0, "render_minutes": 0, "storage_gb": 0, "concurrent_jobs": 1}
    return {"plan": {k: p.get(k) for k in ("id", "name", "price_inr")} if p.get("id") else None, "limits": limits,
            "status": "expired" if expired and sub["status"] not in ("cancelled", "past_due") else sub["status"],
            "period_start": sub.get("period_start"), "period_end": sub.get("period_end"), "expired": expired,
            "trial_end": sub.get("trial_end"), "cycle": sub.get("cycle")}


# ----------------------------------------------------------------------------- usage


def period_key(sub: dict | None = None) -> str:
    """Usage buckets follow the subscription period; without one, the calendar month."""
    if sub and sub.get("period_start"):
        return sub["period_start"][:10]
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _usage_row(c, workspace_id: str) -> dict:
    key = period_key(subscription(workspace_id) if enabled() else None)
    r = db.row(c.execute("SELECT * FROM usage WHERE workspace_id = ? AND period = ?", (workspace_id, key)).fetchone())
    if r is None:
        r = {"id": db.new_id(), "workspace_id": workspace_id, "period": key, "ai_calls": 0, "render_seconds": 0,
             "storage_bytes": 0, "updated_at": db.now()}
        db.insert(c, "usage", r)
    return r


def add_usage(c, workspace_id: str, *, ai_calls: int = 0, render_seconds: float = 0) -> None:
    if not ai_calls and not render_seconds:
        return
    r = _usage_row(c, workspace_id)
    db.update(c, "usage", r["id"], {"ai_calls": r["ai_calls"] + int(ai_calls),
                                     "render_seconds": r["render_seconds"] + int(render_seconds), "updated_at": db.now()})


def storage_bytes(c, workspace_id: str) -> int:
    a = c.execute("SELECT COALESCE(SUM(a.size),0) FROM assets a JOIN projects p ON p.id = a.project_id "
                  "WHERE p.workspace_id = ? AND a.archived = 0", (workspace_id,)).fetchone()[0]
    b = c.execute("SELECT COALESCE(SUM(size),0) FROM library WHERE workspace_id = ?", (workspace_id,)).fetchone()[0]
    return int(a or 0) + int(b or 0)


def usage(workspace_id: str) -> dict:
    c = db.conn()
    r = _usage_row(c, workspace_id) if enabled() else {"ai_calls": 0, "render_seconds": 0, "period": period_key()}
    return {"period": r["period"], "ai_calls": r["ai_calls"], "render_seconds": r["render_seconds"],
            "storage_bytes": storage_bytes(c, workspace_id)}


def summary(workspace_id: str) -> dict:
    """What the Plan page shows: plan, limits, usage, remaining."""
    eff = effective(workspace_id)
    u = usage(workspace_id)
    lim = eff["limits"]
    return {**eff, "usage": u,
            "left": {"ai_credits": max(0, int(lim.get("ai_credits", 0)) - u["ai_calls"]),
                     "render_minutes": max(0, int(lim.get("render_minutes", 0)) - u["render_seconds"] // 60),
                     "storage_gb": round(max(0.0, float(lim.get("storage_gb", 0)) - u["storage_bytes"] / 1024 ** 3), 2)}}


# ----------------------------------------------------------------------------- enforcement


def check_storage(c, workspace_id: str, extra_bytes: int) -> None:
    if not enabled():
        return
    lim = effective(workspace_id)["limits"]
    cap = float(lim.get("storage_gb", 0)) * 1024 ** 3
    if storage_bytes(c, workspace_id) + max(0, int(extra_bytes)) > cap:
        raise QuotaError("storage", f"storage की सीमा ({lim.get('storage_gb', 0)} GB) पूरी — पुराने project हटाएँ या plan बढ़ाएँ")


def check_export(workspace_id: str, height: int, seconds: float) -> None:
    if not enabled():
        return
    eff = effective(workspace_id)
    lim = eff["limits"]
    if eff["expired"]:
        raise QuotaError("expired", "plan खत्म हो गया — render के लिए plan renew करें")
    if int(height) > int(lim.get("max_export_height", 1080)):
        raise QuotaError("export_height", f"इस plan में {lim.get('max_export_height')}p तक export होता है")
    used = usage(workspace_id)["render_seconds"]
    if used + max(0.0, seconds) > int(lim.get("render_minutes", 0)) * 60:
        raise QuotaError("render_minutes", f"इस महीने के render minutes ({lim.get('render_minutes')}) पूरे हो गए")


def ai_credits_left(workspace_id: str) -> int:
    if not enabled():
        return 10**9
    lim = effective(workspace_id)["limits"]
    return max(0, int(lim.get("ai_credits", 0)) - usage(workspace_id)["ai_calls"])


def check_voice(workspace_id: str, premium: bool) -> None:
    if not enabled() or not premium:
        return
    if not effective(workspace_id)["limits"].get("premium_voices"):
        raise QuotaError("premium_voices", "premium आवाज़ें इस plan में नहीं हैं — plan बढ़ाएँ")


def concurrent_limit(c, workspace_id: str) -> int:
    if not enabled():
        return 10**3
    return max(1, int(effective(workspace_id)["limits"].get("concurrent_jobs", 1)))


# ----------------------------------------------------------------------------- LLM accounting (API process)

import contextvars

_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("vividora_ws", default=None)


def set_workspace(workspace_id: str | None) -> None:
    """The API wrapper sets the current workspace (per request — contextvars follow run_in_threadpool)
    so llm.ask_json can count / block credits."""
    _ctx.set(workspace_id)


def current_workspace() -> str | None:
    return _ctx.get()


def llm_gate() -> bool:
    """Called by engine.llm before a paid call. False = blocked (credits exhausted)."""
    ws = current_workspace()
    if not enabled() or not ws:
        return True
    return ai_credits_left(ws) > 0


def llm_count(n: int = 1) -> None:
    ws = current_workspace()
    if not enabled() or not ws:
        return
    try:
        with db.tx() as c:
            add_usage(c, ws, ai_calls=n)
    except Exception as e:  # noqa: BLE001
        log.warning("usage count failed: %s", e)


# ----------------------------------------------------------------------------- login lockout + rate limit (in-memory)

_lock = threading.Lock()
_fails: dict[str, list[float]] = {}
_buckets: dict[str, tuple[float, float]] = {}
LOCK_FAILS = 5
LOCK_SECONDS = 15 * 60


def login_blocked(key: str) -> int:
    """Seconds left of a lockout for this email/IP key (0 = not locked)."""
    with _lock:
        t = time.time()
        hits = [x for x in _fails.get(key, []) if t - x < LOCK_SECONDS]
        _fails[key] = hits
        if len(hits) >= LOCK_FAILS:
            return int(LOCK_SECONDS - (t - hits[0]))
        return 0


def login_failed(key: str) -> None:
    with _lock:
        _fails.setdefault(key, []).append(time.time())


def login_ok(key: str) -> None:
    with _lock:
        _fails.pop(key, None)


def rate_ok(key: str, per_minute: int, burst: int | None = None) -> bool:
    """Token bucket per key (IP + route class). Fine for one node."""
    cap = float(burst or per_minute)
    rate = per_minute / 60.0
    with _lock:
        t = time.time()
        tokens, last = _buckets.get(key, (cap, t))
        tokens = min(cap, tokens + (t - last) * rate)
        if tokens < 1:
            _buckets[key] = (tokens, t)
            return False
        _buckets[key] = (tokens - 1, t)
        return True


def reset_limits() -> None:  # tests
    with _lock:
        _fails.clear()
        _buckets.clear()
