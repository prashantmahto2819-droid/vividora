"""Razorpay subscriptions for Vividora plans.

Flow: the Plan page asks `POST /billing/checkout {plan, cycle}` → we create a Razorpay Subscription
for the mapped Razorpay plan id (env RAZORPAY_PLAN_<plan>_<cycle>, e.g. RAZORPAY_PLAN_creator_monthly)
and return its `short_url` (hosted checkout) — no card data ever touches this server.
Razorpay then calls `POST /api/hooks/razorpay`; the signature (HMAC-SHA256 of the raw body with
RAZORPAY_WEBHOOK_SECRET) is verified before anything is written.

Events handled → subscriptions/invoices:
  subscription.activated / subscription.charged   → status active, period from the payload, invoice row
  payment.captured (one-time order)               → invoice row (period = one cycle from now)
  subscription.pending / payment.failed            → status past_due (plan limits drop to the expired set)
  subscription.halted / cancelled / completed      → status cancelled
Every event is stored in billing_events (idempotent by provider event id).

Tests never call the network: `_api` is swapped for a stub.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from .. import db, saas
from ..config import settings
from ..publish.http import PublishError, request

log = logging.getLogger("vividora.billing")
API = "https://api.razorpay.com/v1"
CYCLES = {"monthly": 1, "quarterly": 3, "annual": 12}


def configured() -> bool:
    return bool(settings.razorpay_key_id and settings.razorpay_key_secret)


def razorpay_plan_id(plan_id: str, cycle: str) -> str | None:
    return os.getenv(f"RAZORPAY_PLAN_{plan_id}_{cycle}") or os.getenv(f"RAZORPAY_PLAN_{plan_id.upper()}_{cycle.upper()}")


def _auth() -> dict:
    tok = base64.b64encode(f"{settings.razorpay_key_id}:{settings.razorpay_key_secret}".encode()).decode()
    return {"Authorization": f"Basic {tok}"}


def _api(method: str, path: str, data: dict | None = None) -> dict:
    try:
        return request(method, API + path, data=data, headers=_auth(), timeout=30)
    except PublishError as e:
        raise RuntimeError(f"Razorpay: {e}") from None


def checkout(workspace_id: str, user: dict, plan_id: str, cycle: str) -> dict:
    """Create a subscription at Razorpay and return {url, subscription_id}."""
    if not configured():
        raise ValueError("payment अभी चालू नहीं है (RAZORPAY_KEY_ID/SECRET .env में डालें)")
    if cycle not in CYCLES:
        raise ValueError("cycle: monthly / quarterly / annual")
    plan = saas.plan(plan_id)
    if not plan or not plan.get("active"):
        raise ValueError("यह plan नहीं है")
    rp_plan = razorpay_plan_id(plan_id, cycle)
    if not rp_plan:
        raise ValueError(f"इस plan/cycle का Razorpay plan id .env में नहीं है (RAZORPAY_PLAN_{plan_id}_{cycle})")
    total_count = {"monthly": 120, "quarterly": 40, "annual": 10}[cycle]
    sub = _api("POST", "/subscriptions", {"plan_id": rp_plan, "total_count": total_count, "customer_notify": 1,
                                          "notes": {"workspace_id": workspace_id, "plan": plan_id, "cycle": cycle,
                                                    "email": user.get("email", "")}})
    with db.tx() as c:
        cur = saas.subscription(workspace_id)
        row = {"plan_id": plan_id, "cycle": cycle, "status": "created", "razorpay_subscription_id": sub.get("id"),
               "meta": {"checkout_url": sub.get("short_url"), "requested_by": user.get("id")}, "updated_at": db.now()}
        if cur:
            db.update(c, "subscriptions", cur["id"], row)
        else:
            db.insert(c, "subscriptions", {"id": db.new_id(), "workspace_id": workspace_id, "period_start": None,
                                           "period_end": None, "trial_end": None, "razorpay_customer_id": None,
                                           "created_at": db.now(), **row})
    return {"url": sub.get("short_url"), "subscription_id": sub.get("id")}


def cancel(workspace_id: str, at_cycle_end: bool = True) -> dict:
    sub = saas.subscription(workspace_id)
    if not sub or not sub.get("razorpay_subscription_id"):
        raise ValueError("कोई चालू subscription नहीं")
    if configured():
        _api("POST", f"/subscriptions/{sub['razorpay_subscription_id']}/cancel", {"cancel_at_cycle_end": 1 if at_cycle_end else 0})
    with db.tx() as c:
        db.update(c, "subscriptions", sub["id"], {"status": "cancelled" if not at_cycle_end else sub["status"],
                                                   "meta": {**(sub.get("meta") or {}), "cancel_at_cycle_end": at_cycle_end},
                                                   "updated_at": db.now()})
    return {"ok": True}


# ----------------------------------------------------------------------------- webhook


def verify_signature(body: bytes, signature: str | None, secret: str | None = None) -> bool:
    secret = secret if secret is not None else settings.razorpay_webhook_secret
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature.strip())


def _ts(v) -> str | None:
    try:
        return datetime.fromtimestamp(int(v), tz=timezone.utc).isoformat(timespec="seconds") if v else None
    except (TypeError, ValueError):
        return None


def _find_subscription(c, rp_sub_id: str | None, notes: dict) -> dict | None:
    if rp_sub_id:
        r = db.row(c.execute("SELECT * FROM subscriptions WHERE razorpay_subscription_id = ?", (rp_sub_id,)).fetchone())
        if r:
            return r
    ws = (notes or {}).get("workspace_id")
    return saas.subscription(ws) if ws else None


def handle_event(payload: dict, event_id: str | None = None) -> dict:
    """Apply one verified webhook payload. Returns {handled, status}."""
    event = payload.get("event") or ""
    ent = payload.get("payload") or {}
    sub_e = (ent.get("subscription") or {}).get("entity") or {}
    pay_e = (ent.get("payment") or {}).get("entity") or {}
    notes = sub_e.get("notes") or pay_e.get("notes") or {}
    eid = event_id or payload.get("id") or f"{event}:{pay_e.get('id') or sub_e.get('id')}:{payload.get('created_at')}"
    with db.tx() as c:
        if c.execute("SELECT 1 FROM billing_events WHERE id = ?", (eid,)).fetchone():
            return {"handled": False, "status": "duplicate"}
        sub = _find_subscription(c, sub_e.get("id"), notes)
        db.insert(c, "billing_events", {"id": eid, "provider": "razorpay", "event": event, "external_id": sub_e.get("id") or pay_e.get("id"),
                                        "workspace_id": sub["workspace_id"] if sub else notes.get("workspace_id"),
                                        "payload": payload, "created_at": db.now()})
        if not sub:
            log.warning("razorpay %s for unknown subscription %s", event, sub_e.get("id"))
            return {"handled": False, "status": "unknown_subscription"}
        plan_id = notes.get("plan") or sub["plan_id"]
        cycle = notes.get("cycle") or sub.get("cycle") or "monthly"
        upd: dict = {"updated_at": db.now(), "plan_id": plan_id, "cycle": cycle}
        if event in ("subscription.activated", "subscription.charged", "subscription.authenticated", "subscription.resumed"):
            start = _ts(sub_e.get("current_start")) or db.now()
            end = _ts(sub_e.get("current_end")) or (datetime.now(timezone.utc) + timedelta(days=30 * CYCLES[cycle])).isoformat(timespec="seconds")
            upd.update(status="active", period_start=start, period_end=end, trial_end=None,
                       razorpay_customer_id=sub_e.get("customer_id") or sub.get("razorpay_customer_id"))
            if event == "subscription.charged" and pay_e.get("id"):
                _invoice(c, sub, plan_id, pay_e, start, end)
        elif event == "payment.captured" and not sub_e:
            # one-time order (no subscription object): one cycle from now
            start = db.now()
            end = (datetime.now(timezone.utc) + timedelta(days=30 * CYCLES[cycle])).isoformat(timespec="seconds")
            upd.update(status="active", period_start=start, period_end=end, trial_end=None)
            _invoice(c, sub, plan_id, pay_e, start, end)
        elif event in ("subscription.pending", "payment.failed"):
            upd.update(status="past_due")
        elif event in ("subscription.halted", "subscription.cancelled", "subscription.completed", "subscription.expired"):
            upd.update(status="cancelled")
        else:
            return {"handled": False, "status": "ignored"}
        db.update(c, "subscriptions", sub["id"], upd)
        return {"handled": True, "status": upd.get("status")}


def _invoice(c, sub: dict, plan_id: str, pay: dict, start: str, end: str) -> None:
    if c.execute("SELECT 1 FROM invoices WHERE razorpay_payment_id = ?", (pay["id"],)).fetchone():
        return
    amount = float(pay.get("amount") or 0) / 100.0
    gst_rate = float(os.getenv("GST_RATE", "0.18"))
    gst = round(amount - amount / (1 + gst_rate), 2) if gst_rate > 0 else 0.0  # GST inclusive price
    db.insert(c, "invoices", {"id": db.new_id(), "workspace_id": sub["workspace_id"], "subscription_id": sub["id"],
                              "plan_id": plan_id, "amount_inr": amount, "gst_inr": gst, "currency": (pay.get("currency") or "INR"),
                              "status": "paid", "razorpay_payment_id": pay["id"], "period_start": start, "period_end": end,
                              "meta": {"method": pay.get("method"), "email": pay.get("email"), "contact": pay.get("contact")},
                              "created_at": db.now()})


def invoices(workspace_id: str) -> list[dict]:
    return db.rows(db.conn().execute("SELECT * FROM invoices WHERE workspace_id = ? ORDER BY created_at DESC", (workspace_id,)))


def receipt_html(inv: dict, ws: dict, plan: dict | None) -> str:
    """A printable receipt (no PDF library needed — the browser prints it)."""
    seller = os.getenv("BILLING_SELLER_NAME", "Vividora")
    gstin = os.getenv("BILLING_GSTIN", "")
    net = inv["amount_inr"] - inv["gst_inr"]
    return f"""<!doctype html><html lang="hi"><meta charset="utf-8"><title>Receipt {inv['id'][:8]}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:640px;margin:2rem auto;padding:0 1rem;color:#111}}table{{width:100%;border-collapse:collapse}}td{{padding:.4rem 0;border-bottom:1px solid #ddd}}h1{{font-size:1.3rem}}.r{{text-align:right}}</style>
<h1>{seller} — Payment receipt</h1>
<p>Receipt no: <b>{inv['id'][:12]}</b><br>Date: {inv['created_at'][:10]}<br>Workspace: {ws.get('name', '')}<br>{('GSTIN: ' + gstin) if gstin else ''}</p>
<table><tr><td>Plan</td><td class="r">{(plan or {}).get('name') or inv['plan_id']}</td></tr>
<tr><td>Period</td><td class="r">{(inv.get('period_start') or '')[:10]} → {(inv.get('period_end') or '')[:10]}</td></tr>
<tr><td>Amount (excl. GST)</td><td class="r">₹ {net:,.2f}</td></tr>
<tr><td>GST</td><td class="r">₹ {inv['gst_inr']:,.2f}</td></tr>
<tr><td><b>Total paid</b></td><td class="r"><b>₹ {inv['amount_inr']:,.2f}</b></td></tr>
<tr><td>Razorpay payment id</td><td class="r">{inv.get('razorpay_payment_id') or ''}</td></tr></table>
<p style="color:#666;font-size:.85rem">यह receipt Razorpay से मिले payment के आधार पर बनी है। Print: Ctrl+P</p></html>"""
