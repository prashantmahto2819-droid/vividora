"""Visuals from the voice (Smart B-roll): plan + fetch from library / stock / AI, with the providers stubbed.

    python3 tests/test_visuals.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="vividora-visuals-")
os.environ.update({"DATA_ROOT": TMP, "DATABASE_PATH": str(Path(TMP) / "t.db"), "MEDIA_ROOT": str(Path(TMP) / "m"), "ADMIN_PASSWORD": "test-pass-123",
                   "SECRET_KEY": "unit-test-secret-key-that-is-long-enough-0123456789", "WEB_DIST": str(Path(TMP) / "nope")})
for k in ("PIXABAY_API_KEY", "GEMINI_API_KEY", "FAL_KEY", "CLOUDFLARE_API_TOKEN", "HF_TOKEN", "OLLAMA_URL"):
    os.environ.pop(k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient  # noqa: E402

from vividora import db  # noqa: E402
from vividora.api import documentary_api, library, visuals_api  # noqa: E402
from vividora.app import create_app  # noqa: E402
from vividora.engine import aiimage, aivideo, llm  # noqa: E402

SEGS = [{"start": 0.2, "end": 2.4, "text": "नमस्ते दोस्तों आज की वीडियो में"},
        {"start": 3.0, "end": 7.5, "text": "सुबह 5 बजे उठकर पहाड़ पर दौड़ने से शरीर मजबूत होता है"},
        {"start": 9.5, "end": 13.0, "text": "किसान अपने खेत में ट्रैक्टर चला रहा था"},
        {"start": 16.0, "end": 20.0, "text": "शहर की भीड़ और ट्रैफिक में 2 घंटे लगते हैं"}]


def media(tmp: Path) -> tuple[Path, Path]:
    img, vid = tmp / "pic.jpg", tmp / "clip.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360", "-frames:v", "1", str(img)], check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:d=2:r=25", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(vid)], check=True)
    return img, vid


def main() -> None:
    img, vid = media(Path(TMP))
    with TestClient(create_app()) as client:
        tok = client.post("/api/auth/login", json={"email": "admin@vividora.local", "password": "test-pass-123"}).json()["token"]
        h = {"authorization": f"Bearer {tok}"}
        pid = client.post("/api/projects", json={"title": "x"}, headers=h).json()["id"]
        base = f"/api/projects/{pid}/visuals"

        def wait(job: str) -> dict:
            for _ in range(200):
                j = client.get(f"/api/visuals/jobs/{job}", headers=h).json()
                if j["status"] != "running":
                    return j
                time.sleep(0.05)
            raise AssertionError("job did not finish")

        def fetch(**kw) -> dict:
            r = client.post(base + "/fetch", json=kw, headers=h)
            assert r.status_code == 202, r.text
            return wait(r.json()["job"])

        r = client.post(base + "/plan", json={}, headers=h)
        assert r.status_code == 409 and "transcript" in r.json()["error"], r.text                     # no transcript yet
        with db.tx() as c:
            db.update(c, "projects", pid, {"transcript": {"segments": SEGS}, "edl": {"duration": 22, "cuts": [{"start": 9, "end": 13.5, "enabled": True}]},
                                          "meta": {"duration": 22}})
        # ---- plan without an LLM: prompts from the words; the line inside the cut and the greeting are left out
        r = client.post(base + "/plan", json={}, headers=h).json()
        texts = [x["text"] for x in r["items"]]
        assert len(r["items"]) == 2 and all(x["by"] == "words" for x in r["items"]) and not any("किसान" in t or "नमस्ते" in t for t in texts), r["items"]
        assert r["providers"] == {"stock": False, "ai_image": None, "ai_video": None, "ai_video_usd": None, "ai_video_max": r["providers"]["ai_video_max"], "llm": None}
        # ---- plan with an LLM
        llm.available, keep_av = (lambda: "fake"), llm.available
        llm.ask_json, keep_ask = (lambda prompt, **k: [{"n": 0, "query": "mountain runner sunrise", "image_prompt": "A runner on a mountain trail at sunrise",
                                                         "video_prompt": "runner moves forward", "effect": "slide", "layout": "pip"},
                                                        {"n": 1, "query": "city traffic jam", "image_prompt": "Crowded city street with traffic", "effect": "zoom"}]), llm.ask_json
        it = client.post(base + "/plan", json={}, headers=h).json()["items"]
        assert [x["by"] for x in it] == ["ai", "ai"] and it[0]["query"] == "mountain runner sunrise" and it[0]["layout"] == "pip" and it[1]["layout"] == "cover", it
        llm.available, llm.ask_json = keep_av, keep_ask
        # ---- fetch: providers not configured → a clear reason, nothing saved
        j = fetch(source="stock_video", query="city traffic")
        assert j["status"] == "error" and "PIXABAY_API_KEY" in j["error"], j
        j = fetch(source="ai_image", prompt="a mountain")
        assert j["status"] == "error" and "AI image" in j["error"], j
        j = fetch(source="library", query="mountain runner", text="पहाड़")
        assert j["status"] == "error" and "Library" in j["error"], j
        assert client.post(base + "/fetch", json={"source": "torrent"}, headers=h).status_code == 422
        # ---- stock (Pixabay stubbed)
        os.environ["PIXABAY_API_KEY"] = "k"
        seen = []

        def http_json(url, *a, **k):
            seen.append(url)
            if "/api/videos/" in url:
                return {"hits": [{"id": 7, "user": "Asha", "pageURL": "https://pixabay.com/videos/7", "videos": {"medium": {"url": "https://cdn.pixabay.com/v/7.mp4"}}}]} if "nothing" not in url else {"hits": []}
            return {"hits": [{"id": 9, "user": "Ravi", "pageURL": "https://pixabay.com/photos/9", "largeImageURL": "https://pixabay.com/get/9.jpg"}]} if "nothing" not in url else {"hits": []}
        library._http_json = http_json
        documentary_api._download = lambda url, dest: (dest.write_bytes((vid if url.endswith(".mp4") else img).read_bytes()), dest)[1]
        j = fetch(source="stock_video", query="city traffic")
        assert j["status"] == "done" and j["item"]["kind"] == "broll" and j["item"]["source"] == "pixabay" and "Asha" in j["item"]["license"], j
        assert j["item"]["url"] and "path" not in j["item"]
        j = fetch(source="stock_photo", query="city traffic", vertical=True)
        assert j["status"] == "done" and j["item"]["kind"] == "image" and "Ravi" in j["item"]["license"] and any("orientation=vertical" in u for u in seen), (j, seen)
        assert not any("/api/videos/" in u for u in seen[-1:]), seen                                      # photo search did not ask for videos
        j = fetch(source="stock_video", query="nothing here")
        assert j["status"] == "error" and "नहीं मिला" in j["error"], j
        # ---- the saved stock clip is now found as a library match
        j = fetch(source="library", query="city traffic")
        assert j["status"] == "done" and j["item"]["source"] == "pixabay", j
        # ---- AI image / AI video (stubbed)
        aiimage.provider = lambda: "cloudflare"
        asked = []
        aiimage.generate = lambda prompt, dest, size=(1280, 720), http=None: (asked.append((prompt, size)), (dest.with_suffix(".jpg").write_bytes(img.read_bytes()), (dest.with_suffix(".jpg"), "cloudflare"))[1])[1]
        j = fetch(source="ai_image", prompt="A runner on a mountain trail at sunrise", vertical=True)
        assert j["status"] == "done" and j["item"]["kind"] == "image" and j["item"]["source"] == "ai" and "synthetic" in j["item"]["license"], j
        assert asked[-1][1] == (720, 1280) and "runner" in asked[-1][0], asked
        j = fetch(source="ai_video", prompt="A runner")
        assert j["status"] == "error" and "FAL_KEY" in j["error"], j                                      # image ok, no video provider
        aivideo.provider = lambda: "fal"
        aivideo.animate = lambda image, prompt, dest, **k: (dest.write_bytes(vid.read_bytes()), dest)[1]
        j = fetch(source="ai_video", prompt="A runner", video_prompt="runner moves forward")
        assert j["status"] == "done" and j["item"]["kind"] == "broll" and "AI video" in j["item"]["license"], j
        # ---- everything landed in the library with its credit; another workspace cannot read a job
        lib = client.get("/api/library", headers=h).json()
        mine = [x for x in lib if x["source"] in ("pixabay", "ai")]
        assert len(mine) == 4 and all(x["license"] for x in mine), [(x["name"], x["source"]) for x in mine]
        any_job = next(iter(visuals_api._JOBS))
        visuals_api._JOBS[any_job]["ws"] = "someone-else"
        assert client.get(f"/api/visuals/jobs/{any_job}", headers=h).status_code == 404
        # ---- no more than 3 at once per workspace
        aivideo.animate = lambda image, prompt, dest, **k: (time.sleep(1.0), dest.write_bytes(vid.read_bytes()), dest)[2]
        codes = [client.post(base + "/fetch", json={"source": "ai_video", "prompt": "x"}, headers=h).status_code for _ in range(5)]
        assert codes.count(202) == 3 and codes.count(429) == 2, codes
    print("OK")


if __name__ == "__main__":
    main()
