"""API keys for other platforms: create (admin only, shown once), scoped access, revoke.

    python3 tests/test_apikeys.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="vividora-keys-")
os.environ.update({"SAAS_MODE": "1", "DATA_ROOT": TMP, "DATABASE_PATH": str(Path(TMP) / "t.db"), "MEDIA_ROOT": str(Path(TMP) / "m"),
                   "SECRET_KEY": "unit-test-secret-key-that-is-long-enough-0123456789", "WORKER_TOKEN": "unit-test-worker-token-1234",
                   "WEB_DIST": str(Path(TMP) / "nope"), "TRIAL_DAYS": "14", "LLM_CACHE": "0",
                   "TRIPOSR_URL": "http://127.0.0.1:9", "VIVIDORA_TTS": "fake"})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient  # noqa: E402

from vividora import db, saas  # noqa: E402
from vividora.app import create_app  # noqa: E402

client = TestClient(create_app())
H = lambda t: {"authorization": f"Bearer {t}"}  # noqa: E731


def signup(email):
    r = client.post("/api/auth/signup", json={"email": email, "password": "strongpass123", "name": "T"})
    assert r.status_code in (200, 201), r.text
    client.cookies.clear()  # signup sets a login cookie; tests must use explicit headers
    return r.json()["token"]


class KeyTests(unittest.TestCase):
    def setUp(self):
        saas.reset_limits()

    def test_keys(self):
        admin = signup("k1@example.com")
        # no login → no key
        self.assertEqual(client.post("/api/keys", json={"name": "x"}).status_code, 401)
        r = client.post("/api/keys", json={"name": "builder", "scopes": ["tts", "3d"]}, headers=H(admin))
        self.assertEqual(r.status_code, 201, r.text)
        key, kid = r.json()["key"], r.json()["id"]
        self.assertTrue(key.startswith("vvk_") and len(key) > 40)
        # bad scope refused
        self.assertEqual(client.post("/api/keys", json={"name": "x", "scopes": ["admin"]}, headers=H(admin)).status_code, 422)
        # listing never reveals the key / hash
        lst = client.get("/api/keys", headers=H(admin)).json()["keys"]
        self.assertEqual(len(lst), 1)
        self.assertNotIn("key", lst[0]); self.assertNotIn("key_hash", lst[0])
        self.assertNotIn(key, str(db.conn().execute("SELECT * FROM api_keys").fetchall()), "plain key stored in DB")

        # allowed: scoped endpoints (3D job status of an unknown job → 404, i.e. auth passed; TTS with empty text → 422)
        self.assertEqual(client.get("/api/triposr/job/" + "a" * 16, headers=H(key)).status_code, 404)
        self.assertEqual(client.post("/api/voiceover", json={"text": ""}, headers=H(key)).status_code, 422)
        # not allowed: everything outside the scopes, including key management and the library
        for method, path in (("get", "/api/keys"), ("post", "/api/keys"), ("get", "/api/library"), ("delete", "/api/keys/" + kid),
                             ("get", "/api/plan"), ("post", "/api/projects"), ("get", "/api/triposr/models")):
            r = getattr(client, method)(path, headers=H(key), **({"json": {"name": "x"}} if method == "post" else {}))
            self.assertEqual(r.status_code, 403, f"{method} {path} -> {r.status_code} {r.text}")
        # tts-only key cannot use 3D
        tts_only = client.post("/api/keys", json={"name": "t", "scopes": ["tts"]}, headers=H(admin)).json()["key"]
        self.assertEqual(client.post("/api/triposr/generate", headers=H(tts_only)).status_code, 403)
        self.assertEqual(client.post("/api/voiceover", json={"text": ""}, headers=H(tts_only)).status_code, 422)
        # wrong key
        self.assertEqual(client.get("/api/triposr/job/" + "a" * 16, headers=H("vvk_nonsense")).status_code, 401)
        # last use recorded
        self.assertTrue(client.get("/api/keys", headers=H(admin)).json()["keys"][0]["last_used_at"])

        # revoke → dead immediately
        self.assertEqual(client.delete("/api/keys/" + kid, headers=H(admin)).status_code, 200)
        self.assertEqual(client.get("/api/triposr/job/" + "a" * 16, headers=H(key)).status_code, 401)

    def test_other_workspace_cannot_touch(self):
        a, b = signup("k2@example.com"), signup("k3@example.com")
        kid = client.post("/api/keys", json={"name": "a"}, headers=H(a)).json()["id"]
        self.assertEqual(client.delete("/api/keys/" + kid, headers=H(b)).status_code, 404)
        self.assertEqual(client.get("/api/keys", headers=H(b)).json()["keys"], [])


if __name__ == "__main__":
    unittest.main()
