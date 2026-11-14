"""API keys for other software (n8n, Zapier, your own apps). Only a SHA-256 hash is stored; the full key is shown once."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from . import db

PREFIX = "vk_"
MAX_KEYS = 20


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create(workspace_id: str, user_id: str, name: str, role: str) -> tuple[str, dict]:
    key = PREFIX + secrets.token_urlsafe(32)
    rec = {"id": db.new_id(), "workspace_id": workspace_id, "user_id": user_id, "name": name, "prefix": key[:10],
           "key_hash": _hash(key), "role": role, "created_at": db.now(), "last_used_at": None, "revoked": 0}
    with db.tx() as c:
        db.insert(c, "api_keys", rec)
    return key, public(rec)


def lookup(key: str) -> dict | None:
    if not key or not key.startswith(PREFIX) or len(key) > 200:
        return None
    r = db.row(db.conn().execute("SELECT * FROM api_keys WHERE key_hash = ? AND revoked = 0", (_hash(key),)).fetchone())
    return r


def touch(k: dict) -> None:
    """last_used_at, at most once a minute (no write on every request)."""
    try:
        last = datetime.fromisoformat(k["last_used_at"]) if k.get("last_used_at") else None
        if last and (datetime.now(timezone.utc) - last).total_seconds() < 60:
            return
        with db.tx() as c:
            db.update(c, "api_keys", k["id"], {"last_used_at": db.now()})
    except Exception:  # noqa: BLE001 — bookkeeping must never fail a request
        pass


def public(k: dict) -> dict:
    return {f: k.get(f) for f in ("id", "name", "prefix", "role", "created_at", "last_used_at", "revoked")}


def list_for(workspace_id: str) -> list[dict]:
    rows = db.rows(db.conn().execute("SELECT * FROM api_keys WHERE workspace_id = ? AND revoked = 0 ORDER BY created_at DESC",
                                     (workspace_id,)))
    return [public(r) for r in rows]


def count(workspace_id: str) -> int:
    return db.conn().execute("SELECT COUNT(*) FROM api_keys WHERE workspace_id = ? AND revoked = 0", (workspace_id,)).fetchone()[0]


def revoke(workspace_id: str, key_id: str) -> bool:
    with db.tx() as c:
        cur = c.execute("UPDATE api_keys SET revoked = 1 WHERE id = ? AND workspace_id = ?", (key_id, workspace_id))
        return cur.rowcount > 0
