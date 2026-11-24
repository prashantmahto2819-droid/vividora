"""The month's spending on paid services: a log, a total, a limit (SPEND_CAP_USD, set in the dashboard).

One instance = one wallet: the keys belong to the server's owner, so the log is instance-wide (the workspace is kept
for information). engine/meter.py does the counting; this module is where the API process keeps it.
"""

from __future__ import annotations

import os
import time

from . import db
from .engine import meter

SCHEMA = """CREATE TABLE IF NOT EXISTS spend_log (
  id TEXT PRIMARY KEY, ts TEXT NOT NULL, period TEXT NOT NULL, service TEXT NOT NULL, what TEXT, units REAL NOT NULL DEFAULT 0,
  unit TEXT, usd REAL NOT NULL DEFAULT 0, workspace_id TEXT, project_id TEXT, worker TEXT);
CREATE INDEX IF NOT EXISTS spend_period ON spend_log(period);"""


def period() -> str:
    return time.strftime("%Y-%m", time.gmtime())


def cap() -> float | None:
    """None = no limit. 0 = paid services are switched off."""
    v = os.getenv("SPEND_CAP_USD")
    if v in (None, ""):
        return None
    try:
        return max(0.0, float(v))
    except ValueError:
        return None


def month_total(p: str | None = None) -> float:
    r = db.conn().execute("SELECT COALESCE(SUM(usd), 0) FROM spend_log WHERE period = ?", (p or period(),)).fetchone()
    return round(float(r[0] or 0), 4)


def left() -> float | None:
    c = cap()
    return None if c is None else round(c - month_total(), 4)


def record(entry: dict, *, workspace_id: str | None = None, project_id: str | None = None, worker: str | None = None) -> None:
    if entry.get("service") not in meter.PRICES:
        return
    with db.tx() as c:
        c.execute("INSERT INTO spend_log (id, ts, period, service, what, units, unit, usd, workspace_id, project_id, worker) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (db.new_id(), db.now(), period(), entry["service"], str(entry.get("what") or "")[:160], float(entry.get("units") or 0),
                   str(entry.get("unit") or "")[:30], max(0.0, min(1000.0, float(entry.get("usd") or 0))), workspace_id or entry.get("workspace_id"),
                   project_id or entry.get("project_id"), worker))


def _sink(entry: dict) -> None:
    from . import saas
    record(entry, workspace_id=saas.current_workspace())


def init() -> None:
    with db.conn() as c:
        c.executescript(SCHEMA)
    meter.configure(sink=_sink, left=left, track_local=False)


def summary() -> dict:
    p = period()
    rows = db.conn().execute("SELECT service, COUNT(*), COALESCE(SUM(units), 0), COALESCE(SUM(usd), 0) FROM spend_log WHERE period = ? GROUP BY service ORDER BY 4 DESC", (p,)).fetchall()
    recent = db.conn().execute("SELECT ts, service, what, units, unit, usd, worker FROM spend_log ORDER BY ts DESC LIMIT 40").fetchall()
    months = db.conn().execute("SELECT period, COALESCE(SUM(usd), 0) FROM spend_log GROUP BY period ORDER BY period DESC LIMIT 6").fetchall()
    c = cap()
    total = month_total(p)
    return {"period": p, "cap": c, "total": total, "left": None if c is None else round(c - total, 4),
            "by_service": [{"service": s, "label": meter.PRICES.get(s, ("", 0, "", s))[3], "calls": n, "units": round(u, 2),
                            "unit": meter.PRICES.get(s, ("", 0, "", ""))[2], "usd": round(x, 4)} for s, n, u, x in rows],
            "recent": [{"ts": t, "service": s, "label": meter.PRICES.get(s, ("", 0, "", s))[3], "what": w, "units": u, "unit": un, "usd": x, "worker": wk}
                       for t, s, w, u, un, x, wk in recent],
            "months": [{"period": a, "usd": round(b, 4)} for a, b in months],
            "prices": [{"service": k, "label": v[3], "unit": v[2], "usd": meter.price(k), "env": v[0]} for k, v in meter.PRICES.items()]}
