"""First run: create the workspace and the admin account from .env."""

from __future__ import annotations

import logging

from . import db
from .config import settings
from .security import hash_password

log = logging.getLogger("vividora")


def ensure_admin() -> None:
    c = db.conn()
    if c.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        return
    with db.tx() as tx:
        ws = {"id": db.new_id(), "name": "Vividora", "settings": {}, "created_at": db.now()}
        db.insert(tx, "workspaces", ws)
        db.insert(tx, "users", {
            "id": db.new_id(), "workspace_id": ws["id"], "email": settings.admin_email.lower(),
            "name": settings.admin_name, "password_hash": hash_password(settings.admin_password),
            "role": "admin", "active": True, "created_at": db.now(), "last_login_at": None})
    log.warning("पहला admin बनाया: %s — login के बाद password ज़रूर बदलें", settings.admin_email)
    if settings.admin_password == "change-me-now":
        log.warning("ADMIN_PASSWORD .env में सेट नहीं है — default password इस्तेमाल हो रहा है")


def ensure_starter() -> None:
    """Fill the library with the bundled starter pack. Runs on every start: an
    empty library gets everything; an existing one gets only items added to the
    pack since its last sync (so items the user deleted are not brought back)."""
    import json as _json
    from .api.library import install_starter, STARTER
    try:
        version = int(_json.loads((STARTER / "manifest.json").read_text()).get("version", 1))
    except Exception:  # noqa: BLE001
        version = 1
    for ws in db.rows(db.conn().execute("SELECT id, settings FROM workspaces")):
        raw = ws.get("settings") or {}
        settings = dict(raw) if isinstance(raw, dict) else _json.loads(raw or "{}")
        has = db.conn().execute("SELECT COUNT(*) FROM library WHERE workspace_id = ? AND source = 'starter'", (ws["id"],)).fetchone()[0]
        seen = int(settings.get("starter_version", 1 if has else 0))
        if has and seen >= version:
            continue
        try:
            n = install_starter(ws["id"], only_new_since=seen if has else None)
            settings["starter_version"] = version
            with db.tx() as c:
                db.update(c, "workspaces", ws["id"], {"settings": settings})
            log.info("starter pack: %s items added", n)
        except Exception as e:  # noqa: BLE001
            log.warning("starter pack failed: %s", e)
