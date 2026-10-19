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
