"""SaaS layer checks: signup/lockout/invites, quotas, round-robin claim, Razorpay webhook signature,
secrets encryption, backup. Runs in-process against a temp DB with SAAS_MODE=1 (no network).

    python3 tests/test_saas.py
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="vividora-saas-")
os.environ.update({"SAAS_MODE": "1", "DATA_ROOT": TMP, "DATABASE_PATH": str(Path(TMP) / "t.db"), "MEDIA_ROOT": str(Path(TMP) / "m"),
                   "SECRET_KEY": "unit-test-secret-key-that-is-long-enough-0123456789", "WORKER_TOKEN": "unit-test-worker-token-1234",
                   "RAZORPAY_WEBHOOK_SECRET": "whsec_unit", "WEB_DIST": str(Path(TMP) / "nope"), "TRIAL_DAYS": "14",
                   "LLM_CACHE": "0"})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient  # noqa: E402

from vividora import db, saas, queue, crypto, backup  # noqa: E402
from vividora.app import create_app  # noqa: E402
from vividora.billing import razorpay  # noqa: E402

app = create_app()
client = TestClient(app)


def _auth(tok: str) -> dict:
    return {"authorization": f"Bearer {tok}"}


def _signup(email: str, name: str = "T", password: str = "strongpass123", **extra) -> dict:
    r = client.post("/api/auth/signup", json={"email": email, "password": password, "name": name, **extra})
    assert r.status_code in (200, 201), r.text
    return r.json()


class SaasTests(unittest.TestCase):
    def setUp(self):
        saas.reset_limits()

    def test_01_signup_creates_workspace_with_trial(self):
        s = _signup("one@example.com", "One")
        self.assertTrue(s["token"])
        self.assertTrue(s["saas"])
        ws = s["workspace"]["id"]
        eff = saas.effective(ws)
        self.assertEqual(eff["status"], "trialing")
        self.assertEqual(eff["plan"]["id"], "free")
        self.assertFalse(eff["expired"])
        # duplicate email refused
        r = client.post("/api/auth/signup", json={"email": "one@example.com", "password": "strongpass123", "name": "X"})
        self.assertEqual(r.status_code, 409)
        # weak password refused
        r = client.post("/api/auth/signup", json={"email": "two@example.com", "password": "password", "name": "X"})
        self.assertEqual(r.status_code, 422)

    def test_02_login_lockout_after_5_fails(self):
        _signup("lock@example.com")
        for _ in range(5):
            r = client.post("/api/auth/login", json={"email": "lock@example.com", "password": "wrong-pass-1"})
            self.assertEqual(r.status_code, 401)
        r = client.post("/api/auth/login", json={"email": "lock@example.com", "password": "strongpass123"})
        self.assertEqual(r.status_code, 429, r.text)
        saas.reset_limits()
        r = client.post("/api/auth/login", json={"email": "lock@example.com", "password": "strongpass123"})
        self.assertEqual(r.status_code, 200)

    def test_03_invite_joins_existing_workspace(self):
        owner = _signup("owner@example.com", "Owner")
        r = client.post("/api/invites", json={"role": "editor"}, headers=_auth(owner["token"]))
        self.assertEqual(r.status_code, 201, r.text)
        code = r.json()["code"]
        joined = _signup("member@example.com", "Mem", invite=code)
        self.assertEqual(joined["workspace"]["id"], owner["workspace"]["id"])
        self.assertEqual(joined["user"]["role"], "editor")
        # a one-use invite is spent
        r = client.post("/api/auth/signup", json={"email": "m2@example.com", "password": "strongpass123", "name": "M2", "invite": code})
        self.assertEqual(r.status_code, 410)

    def test_04_logout_all_kills_old_tokens(self):
        s = _signup("lo@example.com")
        tok = s["token"]
        self.assertEqual(client.get("/api/auth/me", headers=_auth(tok)).status_code, 200)
        self.assertEqual(client.post("/api/auth/logout-all", headers=_auth(tok)).status_code, 200)
        self.assertEqual(client.get("/api/auth/me", headers=_auth(tok)).status_code, 401)

    def test_05_quotas(self):
        s = _signup("q@example.com")
        ws = s["workspace"]["id"]
        # export height cap (free plan: 1080)
        with self.assertRaises(saas.QuotaError) as cm:
            saas.check_export(ws, 2160, 10)
        self.assertEqual(cm.exception.code, "export_height")
        saas.check_export(ws, 1080, 10)  # fine
        # render minutes: use them up
        with db.tx() as c:
            saas.add_usage(c, ws, render_seconds=30 * 60)
        with self.assertRaises(saas.QuotaError) as cm:
            saas.check_export(ws, 1080, 5)
        self.assertEqual(cm.exception.code, "render_minutes")
        # AI credits: 30 on the trial → gate opens, then closes
        self.assertEqual(saas.ai_credits_left(ws), 30)
        saas.set_workspace(ws)
        self.assertTrue(saas.llm_gate())
        with db.tx() as c:
            saas.add_usage(c, ws, ai_calls=30)
        self.assertFalse(saas.llm_gate())
        saas.set_workspace(None)
        # storage cap: 5 GB on the trial
        with self.assertRaises(saas.QuotaError) as cm:
            saas.check_storage(db.conn(), ws, 6 * 1024 ** 3)
        self.assertEqual(cm.exception.code, "storage")
        saas.check_storage(db.conn(), ws, 1024)
        # an API call that hits a quota becomes a 402 with the code
        r = client.post("/api/projects", json={"title": "x"}, headers=_auth(s["token"]))
        self.assertEqual(r.status_code, 201, r.text)
        pid = r.json()["id"]
        r = client.post(f"/api/projects/{pid}/uploads", json={"filename": "a.mp4", "size": 7 * 1024 ** 3}, headers=_auth(s["token"]))
        self.assertEqual(r.status_code, 402, r.text)
        self.assertEqual(r.json().get("quota"), "storage")
        # premium voices blocked on the trial, allowed on studio
        with self.assertRaises(saas.QuotaError):
            saas.check_voice(ws, True)
        saas.check_voice(ws, False)
        with db.tx() as c:
            sub = saas.subscription(ws)
            db.update(c, "subscriptions", sub["id"], {"plan_id": "studio", "status": "active"})
        saas.check_voice(ws, True)

    def test_06_expired_plan_blocks_render(self):
        s = _signup("exp@example.com")
        ws = s["workspace"]["id"]
        with db.tx() as c:
            db.update(c, "subscriptions", saas.subscription(ws)["id"], {"period_end": "2000-01-01T00:00:00+00:00"})
        self.assertTrue(saas.effective(ws)["expired"])
        with self.assertRaises(saas.QuotaError) as cm:
            saas.check_export(ws, 720, 1)
        self.assertEqual(cm.exception.code, "expired")

    def test_07_round_robin_claim_and_concurrency(self):
        a = _signup("rr-a@example.com")
        b = _signup("rr-b@example.com")
        pa = client.post("/api/projects", json={"title": "A"}, headers=_auth(a["token"])).json()["id"]
        pb = client.post("/api/projects", json={"title": "B"}, headers=_auth(b["token"])).json()["id"]
        with db.tx() as c:
            for i in range(3):
                queue.enqueue(c, pa, "render", {"n": i})
            queue.enqueue(c, pb, "render", {"n": 0})
            queue.enqueue(c, pb, "render", {"n": 1})
        with db.tx() as c:
            j1 = queue.claim(c, ["render"], "w1")
            j2 = queue.claim(c, ["render"], "w2")
        # free plan: 1 concurrent job per workspace → the second claim must go to the other workspace
        self.assertNotEqual(j1["project_id"], j2["project_id"])
        with db.tx() as c:
            j3 = queue.claim(c, ["render"], "w3")
        self.assertIsNone(j3, "both workspaces at their concurrent limit → nothing to claim")
        with db.tx() as c:
            db.update(c, "jobs", j1["id"], {"status": "done"})
            j4 = queue.claim(c, ["render"], "w1")
        self.assertEqual(j4["project_id"], j1["project_id"])

    def test_08_webhook_signature_and_events(self):
        s = _signup("pay@example.com")
        ws = s["workspace"]["id"]
        sub = saas.subscription(ws)
        with db.tx() as c:
            db.update(c, "subscriptions", sub["id"], {"razorpay_subscription_id": "sub_test1"})
        body = {"event": "subscription.charged", "created_at": 1700000000,
                "payload": {"subscription": {"entity": {"id": "sub_test1", "customer_id": "cust_1", "current_start": 1900000000,
                                                        "current_end": 1902592000, "notes": {"workspace_id": ws, "plan": "creator", "cycle": "monthly"}}},
                            "payment": {"entity": {"id": "pay_1", "amount": 99900, "currency": "INR", "method": "upi", "email": "pay@example.com"}}}}
        raw = json.dumps(body).encode()
        bad = client.post("/api/hooks/razorpay", content=raw, headers={"x-razorpay-signature": "nope", "content-type": "application/json"})
        self.assertEqual(bad.status_code, 401)
        sig = hmac.new(b"whsec_unit", raw, hashlib.sha256).hexdigest()
        good = client.post("/api/hooks/razorpay", content=raw, headers={"x-razorpay-signature": sig, "content-type": "application/json",
                                                                       "x-razorpay-event-id": "evt_1"})
        self.assertEqual(good.status_code, 200, good.text)
        self.assertEqual(good.json()["status"], "active")
        eff = saas.effective(ws)
        self.assertEqual(eff["plan"]["id"], "creator")
        self.assertEqual(eff["status"], "active")
        inv = razorpay.invoices(ws)
        self.assertEqual(len(inv), 1)
        self.assertAlmostEqual(inv[0]["amount_inr"], 999.0)
        self.assertGreater(inv[0]["gst_inr"], 0)
        # duplicate delivery is ignored
        again = client.post("/api/hooks/razorpay", content=raw, headers={"x-razorpay-signature": sig, "content-type": "application/json",
                                                                        "x-razorpay-event-id": "evt_1"})
        self.assertEqual(again.json()["status"], "duplicate")
        self.assertEqual(len(razorpay.invoices(ws)), 1)
        # failed payment → past_due → limits collapse
        body2 = {"event": "payment.failed", "payload": {"subscription": {"entity": {"id": "sub_test1", "notes": {"workspace_id": ws}}},
                                                        "payment": {"entity": {"id": "pay_2", "amount": 99900}}}}
        raw2 = json.dumps(body2).encode()
        r = client.post("/api/hooks/razorpay", content=raw2, headers={"x-razorpay-signature": hmac.new(b"whsec_unit", raw2, hashlib.sha256).hexdigest(),
                                                                     "content-type": "application/json", "x-razorpay-event-id": "evt_2"})
        self.assertEqual(r.json()["status"], "past_due")
        self.assertEqual(saas.effective(ws)["limits"]["ai_credits"], 0)
        # receipt renders
        r = client.get(f"/api/billing/invoices/{inv[0]['id']}", headers=_auth(s["token"]))
        self.assertEqual(r.status_code, 200)
        self.assertIn("Total paid", r.text)

    def test_09_secrets_encrypted_at_rest(self):
        self.assertTrue(crypto.available())
        s = _signup("sec@example.com")
        ws = s["workspace"]["id"]
        with db.tx() as c:
            db.insert(c, "connections", {"id": "conn1", "workspace_id": ws, "platform": "youtube", "name": "ch", "external_id": "x",
                                         "secrets": {"refresh_token": "rt-SECRET", "access_token": "at"}, "meta": {}, "created_by": None,
                                         "created_at": db.now(), "updated_at": db.now()})
        raw = db.conn().execute("SELECT secrets FROM connections WHERE id = 'conn1'").fetchone()[0]
        self.assertTrue(raw.startswith("enc:"))
        self.assertNotIn("rt-SECRET", raw)
        self.assertEqual(db.get("connections", "conn1")["secrets"]["refresh_token"], "rt-SECRET")
        with db.tx() as c:
            db.update(c, "connections", "conn1", {"secrets": {"refresh_token": "rt-NEW"}})
        raw2 = db.conn().execute("SELECT secrets FROM connections WHERE id = 'conn1'").fetchone()[0]
        self.assertTrue(raw2.startswith("enc:"))
        self.assertEqual(db.get("connections", "conn1")["secrets"]["refresh_token"], "rt-NEW")
        # legacy plaintext row is read and re-encrypted by init()
        with db.tx() as c:
            c.execute("UPDATE connections SET secrets = ? WHERE id = 'conn1'", (json.dumps({"refresh_token": "plain"}),))
        self.assertEqual(db.get("connections", "conn1")["secrets"]["refresh_token"], "plain")
        db.init()
        self.assertTrue(db.conn().execute("SELECT secrets FROM connections WHERE id = 'conn1'").fetchone()[0].startswith("enc:"))

    def test_10_backup(self):
        out = backup.run(keep_days=7)
        self.assertTrue(out.exists() and out.stat().st_size > 0)
        import sqlite3
        n = sqlite3.connect(str(out)).execute("SELECT COUNT(*) FROM users").fetchone()[0]
        self.assertGreater(n, 0)
        self.assertIsNotNone(backup.latest())
        self.assertFalse(backup.due())

    def test_11_rate_limit(self):
        for _ in range(120):
            if not saas.rate_ok("t:x", 60, 60):
                break
        else:
            self.fail("bucket never emptied")
        saas.reset_limits()
        self.assertTrue(saas.rate_ok("t:x", 60, 60))

    def test_12_worker_file_scope(self):
        a = _signup("wa@example.com")
        b = _signup("wb@example.com")
        pa = client.post("/api/projects", json={"title": "A"}, headers=_auth(a["token"])).json()["id"]
        pb = client.post("/api/projects", json={"title": "B"}, headers=_auth(b["token"])).json()["id"]
        with db.tx() as c:
            from vividora import service
            asset = service.add_asset(c, pa, "raw", f"ws_{a['workspace']['id']}/p_{pa}/raw/x.bin")
            jb = queue.enqueue(c, pb, "render", {})
            ja = queue.enqueue(c, pa, "render", {})
        h = {"x-worker-token": "unit-test-worker-token-1234"}
        # a worker on B's job must not read A's file; on A's job it may (404 for missing bytes is fine, 403/404 scope first)
        r = client.get(f"/api/worker/files/{asset['id']}", headers={**h, "x-job": jb["id"]})
        self.assertEqual(r.status_code, 404)
        r = client.get(f"/api/worker/files/{asset['id']}", headers={**h, "x-job": ja["id"]})
        self.assertIn(r.status_code, (200, 404))
        self.assertNotEqual(r.json().get("error") if r.status_code == 404 else None, "asset not found")


if __name__ == "__main__":
    unittest.main(verbosity=1)
