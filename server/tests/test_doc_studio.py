#!/usr/bin/env python3
"""Documentary studio extras: timeline holds + music volume, drafts, Shorts, Series, YouTube private upload (dry run).
    cd server && VIVIDORA_TTS=fake python3 tests/test_doc_studio.py"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
os.environ["VIVIDORA_TTS"] = "fake"
for k in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "PIXABAY_API_KEY", "OLLAMA_URL"):
    os.environ.pop(k, None)
fails = 0


def check(label, cond, val=None):
    global fails
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"  → {str(val)[:400]}"))
    fails += 0 if cond else 1


def units():
    from vividora.engine import documentary as doc
    from vividora.engine import llm
    n = doc.normalize({"scenes": [{"narration": "hello there", "hold": "7.5"}, {"narration": "second one", "hold": 999}, {"narration": "third", "hold": "x"}]})
    check("normalize keeps hold (clamped 0–30), drops junk", [s.get("hold") for s in n["scenes"]] == [7.5, 30.0, None], n)
    check("hold lengthens a scene, never shortens", doc.scene_durations([1, 5, 1], [9, 1, 0]) == [9, 5.45, 2.8], doc.scene_durations([1, 5, 1], [9, 1, 0]))
    t = doc.description("T", [], [], None, {"name": "Himalaya", "i": 2, "titles": ["A", "B", "C"]})
    check("series block in description", "part 2 of 3" in t and "1. A" in t and "3. C" in t, t)
    sc = [{"narration": "Why did it happen? " + "word " * 40, "on_screen": "Hook"}] + [{"narration": "plain sentence " * 12} for _ in range(11)]
    sh = doc.shorts_plan(sc, count=3)
    check("shorts: runs of 20–58 s, non-overlapping, best first", sh and all(20 <= x["seconds"] <= 58 for x in sh) and
          len({i for x in sh for i in x["indices"]}) == sum(len(x["indices"]) for x in sh) and sh[0]["indices"][0] == 0, sh)
    check("shorts: too little material → []", doc.shorts_plan([{"narration": "tiny"}, {"narration": "also tiny"}]) == [])
    check("series_plan without LLM → None", doc.series_plan("x topic", 3) is None)
    old_av, old_ask = llm.available, llm.ask_json
    llm.available = lambda: "gemini"
    llm.ask_json = lambda prompt, **k: {"series": "S", "episodes": [{"title": "One", "summary": "a"}, {"title": ""}, {"title": "Two", "summary": "b"}]}
    try:
        r = doc.series_plan("Himalaya", 4)
        check("series_plan drops untitled episodes", r and [e["title"] for e in r["episodes"]] == ["One", "Two"], r)
        llm.ask_json = lambda prompt, **k: {"series": "S", "episodes": [{"title": "Only"}]}
        check("series_plan needs ≥2 episodes", doc.series_plan("Himalaya", 4) is None)
    finally:
        llm.available, llm.ask_json = old_av, old_ask


def e2e():
    tmp = Path(tempfile.mkdtemp(prefix="vivi_ds_"))
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    plans = []

    class Oll(BaseHTTPRequestHandler):
        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["content-length"])))
            prompt = req["messages"][-1]["content"]
            if "documentary series" in prompt:
                out = {"series": "हिमालय", "episodes": [{"title": "जन्म", "summary": "बनना"}, {"title": "जीवन", "summary": "लोग"}]}
            else:
                plans.append(prompt)
                out = {"title": "एपिसोड", "scenes": [{"narration": f"यह scene {i} का वाक्य है जिसमें कुछ शब्द हैं।", "visual": "mountain"} for i in range(4)]}
            b = json.dumps({"message": {"content": json.dumps(out)}}).encode()
            self.send_response(200); self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def log_message(self, *a): pass
    osrv = HTTPServer(("127.0.0.1", 0), Oll)
    threading.Thread(target=osrv.serve_forever, daemon=True).start()
    env = {**os.environ, "DATA_ROOT": str(tmp / "data"), "MEDIA_ROOT": str(tmp / "media"), "ADMIN_PASSWORD": "test-pass-123", "SECRET_KEY": "t",
           "WEB_DIST": str(tmp / "web"), "TRIPOSR_URL": "http://127.0.0.1:9", "VIVIDORA_TTS": "fake", "PUBLISH_DRY_RUN": "1",
           "OLLAMA_URL": f"http://127.0.0.1:{osrv.server_port}", "OLLAMA_MODEL": "m", "LLM_CACHE": "0"}
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "vividora.app:app", "--port", str(port), "--log-level", "warning"],
                           cwd=str(HERE), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}/api"

    def call(method, path, body=None, token=None):
        h = {"content-type": "application/json"} if body is not None else {}
        if token:
            h["authorization"] = f"Bearer {token}"
        req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"null")
            except ValueError:
                return e.code, None

    def wait(jid, tok, limit=300):
        t0, j = time.time(), None
        while time.time() - t0 < limit:
            st, j = call("GET", "/documentary/" + jid, None, tok)
            if st == 200 and j["status"] in ("done", "failed"):
                return j
            time.sleep(2)
        return j

    try:
        for _ in range(400):
            try:
                if call("GET", "/health")[0] == 200:
                    break
            except OSError:
                time.sleep(0.3)
        tok = call("POST", "/auth/login", {"email": "admin@vividora.local", "password": "test-pass-123"})[1]["token"]
        # ---- drafts
        sc = [{"narration": "पहला दृश्य यहाँ है।", "visual": "x", "hold": 6}, {"narration": "दूसरा दृश्य यहाँ है।"}]
        st, r = call("POST", "/documentary/drafts", {"title": "मेरी फ़िल्म", "scenes": sc, "music_volume": 0.3, "orientation": "portrait"}, tok)
        check("draft saved", st == 200 and r.get("id"), (st, r))
        did = r["id"]
        st, g = call("GET", f"/documentary/drafts/{did}", None, tok)
        check("draft loads with hold + options", st == 200 and g["scenes"][0]["hold"] == 6 and g["options"]["music_volume"] == 0.3 and g["title"] == "मेरी फ़िल्म", (st, g))
        st, r2 = call("POST", "/documentary/drafts", {"id": did, "name": "नया नाम", "title": "T2", "scenes": sc[:1] + sc}, tok)
        st, lst = call("GET", "/documentary/drafts", None, tok)
        check("draft update in place, listed with scene count", st == 200 and len(lst["drafts"]) == 1 and lst["drafts"][0]["name"] == "नया नाम" and lst["drafts"][0]["scenes"] == 3, lst)
        st, _ = call("DELETE", f"/documentary/drafts/{did}", None, tok)
        st, lst = call("GET", "/documentary/drafts", None, tok)
        check("draft deleted", lst["drafts"] == [], lst)
        st, r = call("POST", "/documentary/drafts", {"scenes": []}, tok)
        check("empty draft → 422", st == 422, (st, r))
        # ---- shorts
        long_scenes = [{"narration": ("क्यों हुआ ऐसा? " if i == 0 else "") + "यह एक लंबा वाक्य है जिसमें काफ़ी शब्द हैं और बोलने में समय लगेगा " * 2,
                        "on_screen": "Hook" if i == 0 else ""} for i in range(6)]
        st, r = call("POST", "/documentary/shorts", {"scenes": long_scenes, "count": 2}, tok)
        check("shorts plan returns candidates", st == 200 and r["shorts"] and r["shorts"][0]["seconds"] >= 20, (st, r))
        st, r = call("POST", "/documentary/shorts", {"scenes": [{"narration": "tiny one"}, {"narration": "tiny two"}]}, tok)
        check("too short → 422", st == 422, (st, r))
        st, r = call("POST", "/documentary/shorts", {"scenes": long_scenes, "count": 2, "build": True, "ai_images": False, "stock": False}, tok)
        check("shorts build accepted as a batch job", st == 202 and r.get("job_id"), (st, r))
        bid = r["job_id"]
        st, again = call("POST", "/documentary/build", {"scenes": long_scenes[:3]}, tok)
        check("another build while the batch runs → 429", st == 429, (st, again))
        j = wait(bid, tok, 420)
        check("shorts batch done, every item portrait with a file", j and j["status"] == "done" and j["items"] and all(i["status"] == "done" and i.get("item") for i in j["items"]), j)
        if j and j.get("items"):
            check("short titles carry #Shorts", all("#Shorts" in i["title"] for i in j["items"]), j["items"])
            it = j["items"][0]["item"]
            st, lib = call("GET", f"/library?kind=broll", None, tok)
            rows = lib if isinstance(lib, list) else lib.get("items", [])
            row = next((x for x in rows if x["id"] == it["id"]), None)
            check("short is in the Library", row is not None, rows[:1])
            # ---- youtube dry-run upload
            code = ("import os,sys;sys.path.insert(0,%r);from vividora import db;c=db.conn();ws=c.execute('select id from workspaces limit 1').fetchone()[0];"
                    "cid=db.new_id()\nwith db.tx() as t: db.insert(t,'connections',{'id':cid,'workspace_id':ws,'platform':'youtube','name':'t','external_id':'x',"
                    "'secrets':{'refresh_token':'r'},'meta':{},'created_by':None,'created_at':db.now(),'updated_at':db.now()})\nprint(cid)") % str(HERE)
            cid = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, cwd=str(HERE)).stdout.strip().splitlines()[-1]
            st, r = call("POST", "/documentary/youtube", {"library_id": it["id"], "connection_id": cid, "title": "Test", "privacy": "public", "synthetic": True}, tok)
            check("youtube upload accepted; 'public' is downgraded to private", st == 202 and r["privacy"] == "private", (st, r))
            j2 = wait(r["job_id"], tok, 60)
            check("dry-run upload finishes without touching YouTube", j2 and j2["status"] == "done" and j2["url"] == "(dry-run)", j2)
            st, r = call("POST", "/documentary/youtube", {"library_id": it["id"], "connection_id": "nope", "title": "x"}, tok)
            check("unknown connection → 404", st == 404, (st, r))
        # ---- series
        st, r = call("POST", "/documentary/series", {"topic": "हिमालय", "episodes": 2}, tok)
        check("series outline from the LLM", st == 200 and len(r["episodes"]) == 2 and r["series"] == "हिमालय", (st, r))
        st, r = call("POST", "/documentary/series", {"build": True, "series": "हिमालय", "episodes": r["episodes"], "ground": False, "ai_images": False, "stock": False, "captions": False}, tok)
        check("series build accepted", st == 202, (st, r))
        j = wait(r["job_id"], tok, 420)
        check("series: both episodes planned and built", j and j["status"] == "done" and len(j["items"]) == 2 and all(i["status"] == "done" for i in j["items"]), j)
        check("series: each episode's plan prompt names the other episodes", len(plans) == 2 and "जीवन" in plans[0] and "जन्म" in plans[1], [p[:300] for p in plans])
        if j and j.get("items"):
            check("series: description lists the whole series", "part 2 of 2" in (j["items"][1].get("description") or "") and "जन्म" in j["items"][1]["description"], j["items"][1].get("description"))
        st, r = call("POST", "/documentary/series", {"build": True, "episodes": [{"title": "only one"}]}, tok)
        check("series needs ≥2 episodes → 422", st == 422, (st, r))
        # ---- v1 job view for a batch
        key = call("POST", "/keys", {"name": "t"}, tok)[1]["key"]
        st, r = call("POST", "/v1/documentary/shorts", {"scenes": long_scenes, "count": 1}, key)
        check("v1 shorts plan", st == 200 and r["shorts"], (st, r))
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except subprocess.TimeoutExpired:
            srv.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    units()
    e2e()
    print("\nALL PASS" if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
