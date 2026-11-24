"""Outside-service keys set from the dashboard: stored encrypted, applied to the environment (and config.settings),
a dashboard value wins over .env and removing it brings .env back, only the server's owner may change them, the secret
is never sent back, and a worker receives what it needs with the job it claims.

    python3 tests/test_provider_keys.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="vividora-prov-")
os.environ.update({"DATA_ROOT": TMP, "DATABASE_PATH": str(Path(TMP) / "t.db"), "MEDIA_ROOT": str(Path(TMP) / "m"), "ADMIN_PASSWORD": "test-pass-123",
                   "SECRET_KEY": "unit-test-secret-key-that-is-long-enough-0123456789", "WEB_DIST": str(Path(TMP) / "nope"),
                   "PIXABAY_API_KEY": "from-dot-env-1234", "WORKER_TOKEN": "unit-test-worker-token-0123456789-abcdefghij", "SAAS_MODE": "1", "SIGNUP_OPEN": "1", "INVITE_ONLY": "0"})
for k in ("GEMINI_API_KEY", "PUBLIC_URL", "FAL_KEY"):
    os.environ.pop(k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient  # noqa: E402

from vividora import db, provkeys  # noqa: E402
from vividora.app import create_app  # noqa: E402
from vividora.config import settings  # noqa: E402
from vividora.worker import client as wclient  # noqa: E402


def main() -> None:
    with TestClient(create_app()) as c:
        tok = c.post("/api/auth/login", json={"email": "admin@vividora.local", "password": "test-pass-123"}).json()["token"]
        h = {"authorization": f"Bearer {tok}"}

        rows = {r["env"]: r for r in c.get("/api/providers", headers=h).json()["providers"]}
        assert c.get("/api/providers", headers=h).json()["can_edit"] is True
        assert rows["PIXABAY_API_KEY"]["set"] and rows["PIXABAY_API_KEY"]["source"] == "env" and rows["PIXABAY_API_KEY"]["shown"].endswith("1234")
        assert "from-dot-env" not in str(rows), "the secret itself must never be sent"
        assert not rows["GEMINI_API_KEY"]["set"] and rows["PUBLIC_URL"]["shown"] == ""
        print("PASS list: .env values show as set (masked), missing ones as not set")

        # save a key → environment, masked answer, encrypted at rest
        r = c.put("/api/providers/GEMINI_API_KEY", json={"value": '  "AIza-test-key-ABCD9876"  '}, headers=h)
        assert r.status_code == 200, r.text
        assert os.environ["GEMINI_API_KEY"] == "AIza-test-key-ABCD9876"
        p = r.json()["provider"]
        assert p["set"] and p["source"] == "dashboard" and p["shown"] == "••••••9876" and "AIza" not in r.text
        raw = sqlite3.connect(os.environ["DATABASE_PATH"]).execute("SELECT value FROM provider_keys WHERE env='GEMINI_API_KEY'").fetchone()[0]
        assert raw.startswith("enc:") and "AIza" not in raw, raw[:30]
        print("PASS saved key: in the environment, masked in the answer, encrypted in the database")

        # PUBLIC_URL also updates config.settings (read once at start) — and is validated
        assert c.put("/api/providers/PUBLIC_URL", json={"value": "studio.example.com"}, headers=h).status_code == 422
        assert c.put("/api/providers/PUBLIC_URL", json={"value": "https://studio.example.com/"}, headers=h).status_code == 200
        assert settings.public_url == "https://studio.example.com" and os.environ["PUBLIC_URL"] == "https://studio.example.com"
        assert c.put("/api/providers/SECRET_KEY", json={"value": "x" * 20}, headers=h).status_code == 422       # not in the list
        assert c.put("/api/providers/FAL_KEY", json={"value": "has space"}, headers=h).status_code == 422
        print("PASS PUBLIC_URL follows the dashboard; unknown names and broken values are refused")

        # the dashboard value wins over .env; removing it brings .env back
        assert c.put("/api/providers/PIXABAY_API_KEY", json={"value": "dashboard-key-5555"}, headers=h).status_code == 200
        assert os.environ["PIXABAY_API_KEY"] == "dashboard-key-5555"
        r = c.delete("/api/providers/PIXABAY_API_KEY", headers=h)
        assert r.status_code == 200 and r.json()["provider"]["source"] == "env" and os.environ["PIXABAY_API_KEY"] == "from-dot-env-1234"
        assert c.delete("/api/providers/GEMINI_API_KEY", headers=h).status_code == 200 and "GEMINI_API_KEY" not in os.environ
        print("PASS dashboard value wins; removing it restores .env (or nothing)")

        # a restart reads them again
        c.put("/api/providers/FAL_KEY", json={"value": "fal-key-0000-1111"}, headers=h)
        os.environ.pop("FAL_KEY")
        provkeys.apply()
        assert os.environ["FAL_KEY"] == "fal-key-0000-1111"
        print("PASS values come back after a restart")

        # a worker gets what it uses with a claimed job — and drops it again when it is removed
        env = provkeys.worker_env()
        assert env["set"] == {"FAL_KEY": "fal-key-0000-1111"} and "GEMINI_API_KEY" in env["unset"] and "PUBLIC_URL" not in str(env)
        os.environ.pop("FAL_KEY")
        wclient._apply_env(env)
        assert os.environ["FAL_KEY"] == "fal-key-0000-1111"
        wclient._apply_env({"set": {}, "unset": ["FAL_KEY"]})
        assert "FAL_KEY" not in os.environ
        print("PASS worker receives / drops the keys with a job")

        # an API key can not read or change them; another workspace's admin can not change them
        vk = c.post("/api/keys", json={"name": "n8n", "role": "editor"}, headers=h).json()["key"]
        r = c.get("/api/providers", headers={"authorization": f"Bearer {vk}"})
        assert r.status_code == 200 and r.json()["can_edit"] is False and all(not x["shown"] for x in r.json()["providers"])
        assert c.put("/api/providers/FAL_KEY", json={"value": "x" * 20}, headers={"authorization": f"Bearer {vk}"}).status_code == 403
        s = c.post("/api/auth/signup", json={"email": "other@example.com", "password": "another-pass-123", "name": "Other", "workspace": "Other Co"})
        if s.status_code in (200, 201) and s.json().get("token"):
            h2 = {"authorization": f"Bearer {s.json()['token']}"}
            g = c.get("/api/providers", headers=h2).json()
            assert g["can_edit"] is False and all(not x["shown"] for x in g["providers"])
            assert c.put("/api/providers/FAL_KEY", json={"value": "y" * 20}, headers=h2).status_code == 403
            assert c.delete("/api/providers/FAL_KEY", headers=h2).status_code == 403
            print("PASS another workspace's admin sees no value and can change nothing")
        else:
            print("SKIP second-workspace check (signup not available here):", s.status_code)
        assert os.environ.get("FAL_KEY") is None and db.conn().execute("SELECT COUNT(*) FROM provider_keys WHERE env='FAL_KEY'").fetchone()[0] == 1
        print("PASS an API key can not read or change service keys")


if __name__ == "__main__":
    main()
    print("ALL PASS")
