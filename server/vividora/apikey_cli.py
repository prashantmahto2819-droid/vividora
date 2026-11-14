"""Make an API key on the server itself (no login needed):

    docker compose exec api python -m vividora.apikey_cli "AI App Builder" tts,3d

Prints the key once. The key belongs to the first admin's workspace.
"""

from __future__ import annotations

import sys

from . import db
from .security import API_SCOPES, new_api_key


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("use: python -m vividora.apikey_cli <name> [tts,3d]")
        return 2
    name = argv[1][:60]
    scopes = [s.strip() for s in (argv[2] if len(argv) > 2 else ",".join(API_SCOPES)).split(",") if s.strip()]
    if not scopes or any(s not in API_SCOPES for s in scopes):
        print("scopes: " + ", ".join(API_SCOPES))
        return 2
    db.init()
    u = db.row(db.conn().execute("SELECT * FROM users WHERE role = 'admin' AND active = 1 ORDER BY created_at LIMIT 1").fetchone())
    if not u:
        print("koi admin user nahi mila")
        return 1
    key, prefix, h = new_api_key()
    with db.tx() as c:
        db.insert(c, "api_keys", {"id": db.new_id(), "workspace_id": u["workspace_id"], "user_id": u["id"], "name": name, "prefix": prefix,
                                  "key_hash": h, "scopes": ",".join(scopes), "created_at": db.now()})
    print(key)
    print("(yeh key dobara nahi dikhegi — abhi copy karein. Scopes: " + ",".join(scopes) + ")", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
