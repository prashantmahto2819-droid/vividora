#!/usr/bin/env python3
"""Cloud-GPU rigging: client contract, worker handler (stubbed stages), API e2e against a fake RunPod endpoint.
    cd server && python3 tests/test_unirig.py"""
from __future__ import annotations

import base64
import importlib.util
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
for k in ("UNIRIG_URL", "UNIRIG_ENDPOINT_ID", "RUNPOD_API_KEY", "UNIRIG_TOKEN"):
    os.environ.pop(k, None)
fails = 0
GLB = b"glTF" + b"\x02\x00\x00\x00" + b"x" * 5000
RIGGED = b"glTF" + b"\x02\x00\x00\x00" + b"RIGGED" * 900


def check(label, cond, val=None):
    global fails
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"  → {str(val)[:400]}"))
    fails += 0 if cond else 1


def raises(fn):
    try:
        fn()
        return False
    except Exception:  # noqa: BLE001
        return True


def units():
    from vividora.engine import unirig
    check("not configured by default", not unirig.configured() and raises(lambda: unirig.rig(GLB)))
    os.environ.update(UNIRIG_ENDPOINT_ID="ep1", RUNPOD_API_KEY="k")
    check("runpod base url from endpoint id", unirig.base_url() == "https://api.runpod.ai/v2/ep1" and unirig.configured())
    check("non-glb rejected", raises(lambda: unirig.rig(b"nope" * 100)))
    check("oversized rejected", raises(lambda: unirig.rig(b"glTF" + b"x" * (unirig.MAX_INPUT + 1))))
    seq = []

    def call(method, url, body=None, timeout=60):
        seq.append((method, url.replace("https://api.runpod.ai/v2/ep1", "")))
        if method == "POST":
            assert body["input"]["template"] == "vroid" and base64.b64decode(body["input"]["glb_b64"]) == GLB
            return {"id": "j1"}
        return {"status": "IN_QUEUE"} if len(seq) < 3 else {"status": "COMPLETED", "output": {"glb_b64": base64.b64encode(RIGGED).decode()}}
    seen = []
    out = unirig.rig(GLB, "vroid", call=call, poll_s=0.01, on_status=seen.append)
    check("submit → poll → decode rigged glb", out == RIGGED and seq[0] == ("POST", "/run") and seq[1] == ("GET", "/status/j1") and "IN_QUEUE" in seen, (seq, seen))
    check("worker error surfaces", raises(lambda: unirig.rig(GLB, call=lambda m, u, b=None, timeout=60: {"id": "j"} if m == "POST" else {"status": "COMPLETED", "output": {"error": "bad mesh"}}, poll_s=0.01)))
    check("FAILED status surfaces", raises(lambda: unirig.rig(GLB, call=lambda m, u, b=None, timeout=60: {"id": "j"} if m == "POST" else {"status": "FAILED", "error": "oom"}, poll_s=0.01)))
    check("timeout surfaces", raises(lambda: unirig.rig(GLB, call=lambda m, u, b=None, timeout=60: {"id": "j"} if m == "POST" else {"status": "IN_PROGRESS"}, poll_s=0.01, max_wait=0.05)))
    check("non-glb output rejected", raises(lambda: unirig.rig(GLB, call=lambda m, u, b=None, timeout=60: {"id": "j"} if m == "POST" else {"status": "COMPLETED", "output": {"glb_b64": base64.b64encode(b"zzzz").decode()}}, poll_s=0.01)))
    for k in ("UNIRIG_ENDPOINT_ID", "RUNPOD_API_KEY"):
        os.environ.pop(k)


def worker_units():
    spec = importlib.util.spec_from_file_location("unirig_handler", HERE.parent / "gpu-worker" / "unirig" / "handler.py")
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    calls = []

    def run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        calls.append(Path(cmd[1]).name)
        a = cmd[2:]
        out = Path(a[a.index("--output") + 1])
        out.write_bytes(RIGGED if out.suffix == ".glb" else b"fbx")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    r = h.rig({"glb_b64": base64.b64encode(GLB).decode()}, run=run)
    check("worker runs skeleton → skin → merge and returns the glb", calls == ["generate_skeleton.sh", "generate_skin.sh", "merge.sh"] and base64.b64decode(r["glb_b64"]) == RIGGED, (calls, r))
    check("worker rejects non-glb", "error" in h.rig({"glb_b64": base64.b64encode(b"nope").decode()}, run=run))
    bad = lambda cmd, **k: subprocess.CompletedProcess(cmd, 1, "", "CUDA out of memory")
    r = h.rig({"glb_b64": base64.b64encode(GLB).decode()}, run=bad)
    check("stage failure → error with stderr tail", "CUDA out of memory" in r.get("error", ""), r)


def e2e():
    tmp = Path(tempfile.mkdtemp(prefix="vivi_rig_"))
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    seen = {}

    class RP(BaseHTTPRequestHandler):
        def _send(self, d):
            b = json.dumps(d).encode()
            self.send_response(200); self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def do_POST(self):
            seen["auth"] = self.headers.get("Authorization")
            seen["body"] = json.loads(self.rfile.read(int(self.headers["content-length"])))
            self._send({"id": "job9"})

        def do_GET(self):
            self._send({"status": "COMPLETED", "output": {"glb_b64": base64.b64encode(RIGGED).decode()}})

        def log_message(self, *a): pass
    rp = HTTPServer(("127.0.0.1", 0), RP)
    threading.Thread(target=rp.serve_forever, daemon=True).start()
    env = {**os.environ, "DATA_ROOT": str(tmp / "data"), "MEDIA_ROOT": str(tmp / "media"), "ADMIN_PASSWORD": "test-pass-123", "SECRET_KEY": "t",
           "WEB_DIST": str(tmp / "web"), "TRIPOSR_URL": "http://127.0.0.1:9", "UNIRIG_URL": f"http://127.0.0.1:{rp.server_port}", "UNIRIG_TOKEN": "tok"}
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "vividora.app:app", "--port", str(port), "--log-level", "warning"],
                           cwd=str(HERE), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}/api"

    def call(method, path, body=None, token=None, raw=None, ctype=None):
        h = {"content-type": ctype or "application/json"} if (body is not None or raw) else {}
        if token:
            h["authorization"] = f"Bearer {token}"
        req = urllib.request.Request(base + path, method=method, data=raw if raw else (json.dumps(body).encode() if body is not None else None), headers=h)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"null")
            except ValueError:
                return e.code, None
    try:
        for _ in range(400):
            try:
                if call("GET", "/health")[0] == 200:
                    break
            except OSError:
                time.sleep(0.3)
        tok = call("POST", "/auth/login", {"email": "admin@vividora.local", "password": "test-pass-123"})[1]["token"]
        st, r = call("GET", "/rig/health", None, tok)
        check("rig health: configured", st == 200 and r["configured"] is True, (st, r))
        bnd = "XBND"
        raw = (f'--{bnd}\r\nContent-Disposition: form-data; name="file"; filename="hero.glb"\r\nContent-Type: model/gltf-binary\r\n\r\n').encode() + GLB + f"\r\n--{bnd}--\r\n".encode()
        st, r = call("POST", "/triposr/import", token=tok, raw=raw, ctype=f"multipart/form-data; boundary={bnd}")
        check("model imported", st == 201, (st, r))
        mid = r["item"]["id"]
        st, r = call("POST", "/rig", {"library_id": "nope"}, tok)
        check("unknown model → 404", st == 404, (st, r))
        st, r = call("POST", "/rig", {"library_id": mid, "template": "weird"}, tok)
        check("bad template → 422", st == 422, (st, r))
        st, r = call("POST", "/rig", {"library_id": mid, "template": "vroid"}, tok)
        check("rig accepted", st == 202 and r.get("job_id"), (st, r))
        jid, j = r["job_id"], None
        for _ in range(60):
            st, j = call("GET", "/rig/" + jid, None, tok)
            if j["status"] != "running":
                break
            time.sleep(0.5)
        check("rig done with a rigged item", j and j["status"] == "done" and j["item"]["name"] == "hero (rigged)", j)
        check("worker got the glb + template + bearer token", seen["body"]["input"]["template"] == "vroid" and seen["auth"] == "Bearer tok" and
              base64.b64decode(seen["body"]["input"]["glb_b64"]) == GLB, seen.get("auth"))
        st, lst = call("GET", "/triposr/models", None, tok)
        names = [m["name"] for m in lst["models"]]
        check("rigged model is in the 3D models list", "hero (rigged)" in names, names)
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except subprocess.TimeoutExpired:
            srv.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    units()
    worker_units()
    e2e()
    print("\nALL PASS" if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
