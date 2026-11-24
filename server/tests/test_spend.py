"""Spending on paid services: counted, shown, and stopped at the month's limit — in the API process and from a worker.

    python3 tests/test_spend.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="vividora-spend-")
os.environ.update({"DATA_ROOT": TMP, "DATABASE_PATH": str(Path(TMP) / "t.db"), "MEDIA_ROOT": str(Path(TMP) / "m"), "ADMIN_PASSWORD": "test-pass-123",
                   "SECRET_KEY": "unit-test-secret-key-that-is-long-enough-0123456789", "WEB_DIST": str(Path(TMP) / "nope"), "WORKER_TOKEN": "unit-test-worker-token-0123456789-abcdefghij"})
for k in ("SPEND_CAP_USD", "TRANSCRIBE_ENGINE", "FAL_KEY", "PRICE_FAL_WHISPER_MIN"):
    os.environ.pop(k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient  # noqa: E402

from vividora import provkeys, spend  # noqa: E402
from vividora.app import create_app  # noqa: E402
from vividora.engine import meter  # noqa: E402
from vividora.worker import client as wclient  # noqa: E402


def main() -> None:
    with TestClient(create_app()) as c:
        tok = c.post("/api/auth/login", json={"email": "admin@vividora.local", "password": "test-pass-123"}).json()["token"]
        h = {"authorization": f"Bearer {tok}"}
        wh = {"x-worker-token": os.environ["WORKER_TOKEN"]}

        # no limit set: nothing is blocked, calls are counted with the estimated price
        assert spend.cap() is None and meter.left() is None
        meter.check("fal_whisper")
        assert meter.add("fal_whisper", "podcast · 30 min", 30) == 0.18                     # 30 min × $0.006
        assert meter.add("ai_video", "clip", 5) == 0.15 and meter.add("ai_image", "cloudflare: x", 1) == 0.0
        s = c.get("/api/spend", headers=h).json()
        assert s["total"] == 0.33 and s["cap"] is None and s["left"] is None and s["can_edit"] is True, s
        assert [x["service"] for x in s["by_service"]][:2] == ["fal_whisper", "ai_video"] and s["by_service"][0]["units"] == 30
        assert len(s["recent"]) == 3 and s["recent"][0]["label"] and any(p["service"] == "runpod_whisper" for p in s["prices"])
        print("PASS counted with estimated prices, shown per service")

        # a limit from the dashboard: applies at once; reaching it blocks paid calls, free ones still run
        assert c.put("/api/providers/SPEND_CAP_USD", json={"value": "abc"}, headers=h).status_code == 422
        assert c.put("/api/providers/SPEND_CAP_USD", json={"value": "0.5"}, headers=h).status_code == 200
        assert spend.cap() == 0.5 and abs(meter.left() - 0.17) < 1e-6
        meter.check("ai_video")
        meter.add("fal_whisper", "long", 40)                                                 # +0.24 → 0.57 > 0.5
        try:
            meter.check("ai_video")
            raise SystemExit("over the limit must raise")
        except meter.SpendCap as e:
            assert "खर्च-सीमा" in str(e)
        meter.check("ai_image")                                                              # costs nothing → never blocked
        s = c.get("/api/spend", headers=h).json()
        assert s["cap"] == 0.5 and s["left"] < 0 and s["total"] == 0.57, s
        assert c.delete("/api/providers/SPEND_CAP_USD", headers=h).status_code == 200 and meter.left() is None
        print("PASS limit set in the dashboard blocks paid calls once reached; removing it frees them")

        # the engine switch is a dashboard setting too, validated, and reaches a worker with a claim (even with no job)
        assert c.put("/api/providers/TRANSCRIBE_ENGINE", json={"value": "gpu"}, headers=h).status_code == 422
        assert c.put("/api/providers/TRANSCRIBE_ENGINE", json={"value": "fal"}, headers=h).status_code == 200
        assert c.put("/api/providers/FAL_KEY", json={"value": "fal-key-123456"}, headers=h).status_code == 200
        r = c.post("/api/worker/claim", json={"kinds": ["render"], "worker": "w1"}, headers=wh).json()
        assert r["job"] is None and r["env"]["set"]["TRANSCRIBE_ENGINE"] == "fal" and r["env"]["set"]["FAL_KEY"] == "fal-key-123456", r
        os.environ.pop("TRANSCRIBE_ENGINE"); os.environ.pop("FAL_KEY")
        wclient._apply_env(r["env"])
        from vividora.engine import cloudasr
        assert cloudasr.engine(60) == "fal"
        rows = {x["env"]: x for x in c.get("/api/providers", headers=h).json()["providers"]}
        assert rows["TRANSCRIBE_ENGINE"]["shown"] == "fal" and "fal" in rows["TRANSCRIBE_ENGINE"]["choices"] and rows["SPEND_CAP_USD"]["set"] is False
        print("PASS engine switch: validated, saved, delivered to a waiting worker")

        # a worker reports what it spent; the server adds it to the same month
        before = spend.month_total()
        r = c.post("/api/worker/spend", json={"service": "runpod_whisper", "what": "talk", "units": 100, "unit": "GPU-second", "usd": 0.04}, headers=wh)
        assert r.status_code == 200 and abs(spend.month_total() - before - 0.04) < 1e-6
        assert c.post("/api/worker/spend", json={"service": "made-up", "usd": 99}, headers=wh).status_code == 200 and abs(spend.month_total() - before - 0.04) < 1e-6
        assert c.post("/api/worker/spend", json={"service": "ai_video", "usd": 1}).status_code == 401
        # the worker-side meter: budget from the claim, minus what it spent itself since
        sent = []
        meter.configure(sink=sent.append, left=lambda: 0.05)
        meter.check("runpod_whisper")
        meter.add("runpod_whisper", "x", 200)                                                # 200 s × $0.0004 = 0.08
        assert sent[0]["usd"] == 0.08 and sent[0]["unit"] == "GPU-second"
        try:
            meter.check("fal_whisper")
            raise SystemExit("worker over budget must raise")
        except meter.SpendCap:
            pass
        spend.init()
        print("PASS worker: reports its spending, stops itself when the job's budget is gone")

        # others see totals only
        vk = c.post("/api/keys", json={"name": "n8n", "role": "editor"}, headers=h).json()["key"]
        s2 = c.get("/api/spend", headers={"authorization": f"Bearer {vk}"}).json()
        assert s2["can_edit"] is False and "recent" not in s2 and "total" in s2
        print("PASS the log is for the server's owner only")


if __name__ == "__main__":
    main()
    print("ALL PASS")
