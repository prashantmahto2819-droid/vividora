#!/usr/bin/env python3
"""API smoke test for the pro endpoints: boots the real server (uvicorn) on a temp data dir,
logs in, creates a project with a recording + transcript, and calls

  GET  /api/presets (→ pro)            GET /api/pro/catalog
  GET/POST /api/projects/{id}/textcut  POST /api/projects/{id}/scenes
  POST /api/projects/{id}/color/match  POST /api/projects/{id}/music/fit

    cd server && python3 tests/test_pro_api.py [--media DIR]   (DIR = media made by test_pro_render.py)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--media", default=os.getenv("VIVIDORA_TEST_OUT", "/tmp/vividora_pro_tests") + "/media")
    a = ap.parse_args()
    media_src = Path(a.media)
    tmp = Path(tempfile.mkdtemp(prefix="vivi_api_"))
    env = {**os.environ, "DATA_ROOT": str(tmp / "data"), "MEDIA_ROOT": str(tmp / "media"), "ADMIN_PASSWORD": "test-pass-123",
           "SECRET_KEY": "t", "WEB_DIST": str(tmp / "web")}
    os.environ.update(env)
    sys.path.insert(0, str(HERE))
    from vividora import db, service, storage  # noqa: E402  (after env)
    db.init()
    port = free_port()
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "vividora.app:app", "--port", str(port), "--log-level", "warning"],
                           cwd=str(HERE), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}/api"
    fails = 0

    def call(method: str, path: str, body=None, token=None):
        req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"content-type": "application/json", **({"authorization": f"Bearer {token}"} if token else {})})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def check(label, cond, val=None):
        nonlocal fails
        print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"  → {str(val)[:400]}"))
        fails += 0 if cond else 1

    try:
        for _ in range(400):  # a loaded machine installs the starter pack slowly (~40 s seen)
            try:
                if call("GET", "/health")[0] == 200:
                    break
            except OSError:
                time.sleep(0.3)
        st, r = call("POST", "/auth/login", {"email": "admin@vividora.local", "password": "test-pass-123"})
        check("login", st == 200, r)
        tok = r["token"]
        st, pres = call("GET", "/presets", token=tok)
        check("presets has pro catalogs", st == 200 and len(pres["pro"]["trending"]) == 25 and "blend_modes" in pres["pro"], st)
        check("presets catalog has trending category", "trending" in pres["catalog"]["categories"], pres["catalog"]["categories"])
        check("render defaults carry markers + effects.pro", pres["render_defaults"]["markers"] == [] and pres["render_defaults"]["effects"]["pro"] == {}, None)
        st, cat = call("GET", "/pro/catalog", token=tok)
        check("GET /pro/catalog", st == 200 and cat["capabilities"]["stabilize"] in ("vidstab", "deshake", "none"), cat.get("capabilities") if isinstance(cat, dict) else cat)
        st, p = call("POST", "/projects", {"title": "api test"}, token=tok)
        check("create project", st == 201, p)
        pid, ws = p["id"], p["workspace_id"]
        # attach a recording (proxy) + transcript + a library clip/song, the way the pipeline would
        rel = storage.project_dir(ws, pid) / "work" / "proxy.mp4"
        shutil.copy2(media_src / "face.mp4", storage.ensure_parent(rel))
        words = [("नमस्ते", 0.2, 0.6), ("अं", 0.8, 1.0), ("आज", 1.1, 1.4), ("हम", 1.5, 1.7), ("बात", 3.5, 3.9), ("करेंगे", 4.0, 4.5)]
        tr = {"segments": [{"start": 0.2, "end": 4.5, "text": " ".join(w for w, _, _ in words), "words": [{"w": w, "start": s, "end": e} for w, s, e in words]}]}
        lib = {}
        with db.tx() as c:
            service.add_asset(c, pid, "proxy", str(rel))
            db.update(c, "projects", pid, {"transcript": tr, "edl": {"duration": 8.0, "cuts": [{"id": "c1", "start": 6.0, "end": 6.5, "enabled": True, "reason": "manual"}]},
                                           "meta": {"duration": 8.0, "fps": 30, "width": 1280, "height": 720}, "status": "review_cuts"})
            for kind, name in (("broll", "scenes.mp4"), ("music", "music.wav")):
                lrel = Path(f"ws_{ws}") / "library" / kind / name
                shutil.copy2(media_src / name, storage.ensure_parent(lrel))
                lid = db.new_id()
                db.insert(c, "library", {"id": lid, "workspace_id": ws, "kind": kind, "name": name, "path": str(lrel), "size": 1,
                                         "mime": None, "meta": {}, "created_by": None, "created_at": db.now()})
                lib[kind] = lid
        st, r = call("GET", f"/projects/{pid}/textcut", token=tok)
        check("GET textcut words", st == 200 and len(r["words"]) == 6 and not any(w["removed"] for w in r["words"]), r)
        st, r = call("POST", f"/projects/{pid}/textcut", {"delete": [3], "fillers": True, "silences_over": 1.0, "dry_run": True}, token=tok)
        check("POST textcut dry_run", st == 200 and set(r["removed_words"]) >= {1, 3} and r["added"] >= 3, r)
        st, pv = call("GET", f"/projects/{pid}", token=tok)
        check("dry_run did not save", len(pv["edl"]["cuts"]) == 1, pv["edl"]["cuts"])
        st, r = call("POST", f"/projects/{pid}/textcut", {"delete": [3], "fillers": True}, token=tok)
        st2, pv = call("GET", f"/projects/{pid}", token=tok)
        check("textcut saved + manual cut kept", st == 200 and any(c["id"] == "c1" for c in pv["edl"]["cuts"]) and len(pv["edl"]["cuts"]) == 3, pv["edl"]["cuts"])
        st, r = call("POST", f"/projects/{pid}/textcut", {"restore": [3]}, token=tok)
        check("textcut restore", st == 200 and 3 not in r["removed_words"], r.get("removed_words"))
        st, r = call("POST", f"/projects/{pid}/scenes", {"source": {"kind": "library", "id": lib["broll"]}, "threshold": 0.3}, token=tok)
        check("scenes on a library clip", st == 200 and len(r["scenes"]) == 3, r)
        st, r = call("POST", f"/projects/{pid}/color/match", {"clip": {"kind": "library", "id": lib["broll"], "t": 1}, "ref": {"kind": "project", "t": 2}}, token=tok)
        check("colour match params", st == 200 and "match" in r["color"] and len(r["color"]["match"]["ref"]["mean"]) == 3, r)
        st, r = call("POST", f"/projects/{pid}/music/fit", {"music_id": lib["music"], "target": 12}, token=tok)
        check("music fit plan", st == 200 and abs(r["plan"]["output_length"] - 12) < 0.05, r)
        st, r = call("POST", f"/projects/{pid}/music/fit", {"music_id": lib["music"]}, token=tok)
        check("music fit plan (target = output length)", st == 200 and r["plan"]["target"] > 0, r)
        st, r = call("POST", f"/projects/{pid}/scenes", {}, token=None)
        check("auth required", st == 401, st)
    finally:
        srv.terminate()
        try:
            out = srv.communicate(timeout=10)[0].decode(errors="ignore")
        except subprocess.TimeoutExpired:
            srv.kill()
            out = ""
        if fails:
            print(out[-3000:])
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'all passed' if not fails else f'{fails} failed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
