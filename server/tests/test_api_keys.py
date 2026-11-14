#!/usr/bin/env python3
"""End-to-end test of API keys + the public /api/v1 API against a real booted server.

    cd server && python3 tests/test_api_keys.py
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="vivi_keys_"))
    env = {**os.environ, "DATA_ROOT": str(tmp / "data"), "MEDIA_ROOT": str(tmp / "media"), "ADMIN_PASSWORD": "test-pass-123",
           "SECRET_KEY": "t", "WEB_DIST": str(tmp / "web"), "TRIPOSR_URL": "http://127.0.0.1:9"}
    port = free_port()
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "vividora.app:app", "--port", str(port), "--log-level", "warning"],
                           cwd=str(HERE), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}/api"
    fails = 0

    def call(method, path, body=None, token=None, headers=None, raw=False, multipart=None):
        h = dict(headers or {})
        data = None
        if multipart is not None:
            bd = uuid.uuid4().hex
            parts = []
            for k, v in multipart.items():
                if isinstance(v, tuple):
                    parts.append(f'--{bd}\r\nContent-Disposition: form-data; name="{k}"; filename="{v[0]}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + v[1] + b"\r\n")
                else:
                    parts.append(f'--{bd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
            data = b"".join(parts) + f"--{bd}--\r\n".encode()
            h["content-type"] = f"multipart/form-data; boundary={bd}"
        elif body is not None:
            data = json.dumps(body).encode()
            h["content-type"] = "application/json"
        if token:
            h["authorization"] = f"Bearer {token}"
        req = urllib.request.Request(base + path, method=method, data=data, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read()
                return r.status, (b if raw else json.loads(b or b"null"))
        except urllib.error.HTTPError as e:
            b = e.read()
            try:
                return e.code, json.loads(b or b"null")
            except ValueError:
                return e.code, b

    def check(label, cond, val=None):
        nonlocal fails
        print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"  → {str(val)[:300]}"))
        fails += 0 if cond else 1

    try:
        for _ in range(400):
            try:
                if call("GET", "/health")[0] == 200:
                    break
            except OSError:
                time.sleep(0.3)
        st, r = call("POST", "/auth/login", {"email": "admin@vividora.local", "password": "test-pass-123"})
        check("login", st == 200, r)
        tok = r["token"]

        st, r = call("POST", "/keys", {"name": "n8n"}, token=tok)
        check("create key", st == 201 and r["key"].startswith("vk_") and r["info"]["role"] == "editor", r)
        key, kid = r["key"], r["info"]["id"]
        check("key secret not in info", key not in json.dumps(r["info"]))
        st, r = call("GET", "/keys", token=tok)
        check("list keys (no secret)", st == 200 and len(r["keys"]) == 1 and "key" not in r["keys"][0] and "key_hash" not in r["keys"][0], r)

        st, r = call("GET", "/v1/me", token=key)
        check("v1/me with key (Bearer)", st == 200 and r["via_api_key"] and r["role"] == "editor", r)
        st, r = call("GET", "/v1/me", headers={"x-api-key": key})
        check("v1/me with X-API-Key", st == 200 and r["via_api_key"], r)
        st, r = call("GET", "/v1/me", token="vk_wrong")
        check("wrong key → 401", st == 401, (st, r))
        st, r = call("GET", "/v1/me")
        check("no auth → 401", st == 401, (st, r))

        st, r = call("POST", "/keys", {"name": "x"}, token=key)
        check("key cannot create keys", st == 403, (st, r))
        st, r = call("GET", "/keys", token=key)
        check("key cannot list keys", st == 403, (st, r))

        st, r = call("GET", "/v1/docs", raw=True)
        check("docs page public", st == 200 and b"Vividora API" in r, st)
        st, r = call("GET", "/v1/openapi.json")
        check("openapi.json", st == 200 and "/v1/text-to-speech" in r["paths"] and r["openapi"].startswith("3."), r)
        st, r = call("GET", "/v1/voices", token=key)
        check("voices list", st == 200 and isinstance(r["voices"], list), r)

        # validation / safety
        st, r = call("POST", "/v1/text-to-speech", {"text": ""}, token=key)
        check("tts empty text → 422", st == 422, (st, r))
        st, r = call("POST", "/v1/text-to-speech", {"text": "hello", "callback_url": "http://127.0.0.1:8000/x"}, token=key)
        check("callback to localhost refused (SSRF)", st == 422, (st, r))
        st, r = call("POST", "/v1/text-to-speech", {"text": "hello", "callback_url": "http://169.254.169.254/latest"}, token=key)
        check("callback to metadata IP refused", st == 422, (st, r))
        st, r = call("POST", "/v1/image-to-3d", multipart={"file": ("a.png", b"x" * 500)}, token=key)
        check("image-to-3d with TripoSR offline → 503", st == 503, (st, r))

        # .glb import → list → character-video validation → file download
        glb = b"glTF" + b"\x02\x00\x00\x00" + b"\x00" * 200
        st, r = call("POST", "/v1/models3d", multipart={"file": ("box.glb", glb), "name": "box"}, token=key)
        check("import glb", st == 201 and r["item"]["kind"] == "3d_model", (st, r))
        mid = r["item"]["id"] if st == 201 else ""
        st, r = call("GET", "/v1/models3d", token=key)
        check("list models3d", st == 200 and any(m["id"] == mid for m in r["models"]), r)
        st, r = call("GET", f"/v1/files/{mid}", token=key, raw=True)
        check("download file with key", st == 200 and r[:4] == b"glTF", (st, r[:40] if isinstance(r, bytes) else r))
        st, r = call("GET", f"/v1/files/{mid}")
        check("download without key → 401", st == 401, st)
        st, r = call("POST", "/v1/character-video", {"glb": mid, "lines": [{"text": "hi"}], "seconds": 3, "camera": "full"}, token=key)
        check("character-video queued", st == 202 and r.get("job_id"), (st, r))
        jid = r.get("job_id")
        st, r = call("GET", f"/v1/jobs/{jid}", token=key)
        check("job status (queued)", st == 200 and r["status"] in ("queued", "running"), (st, r))
        st, r = call("GET", "/v1/jobs/doesnotexist", token=key)
        check("unknown job → 404", st == 404, (st, r))

        # viewer-capped key cannot write
        st, r = call("POST", "/keys", {"name": "ro", "role": "viewer"}, token=tok)
        check("create viewer key", st == 201 and r["info"]["role"] == "viewer", r)
        vkey = r["key"]
        st, r = call("GET", "/v1/models3d", token=vkey)
        check("viewer key can read", st == 200, (st, r))
        st, r = call("POST", "/v1/text-to-speech", {"text": "hello"}, token=vkey)
        check("viewer key cannot write → 403", st == 403, (st, r))

        # revoke
        st, r = call("DELETE", f"/keys/{kid}", token=tok)
        check("revoke key", st == 200, (st, r))
        st, r = call("GET", "/v1/me", token=key)
        check("revoked key → 401", st == 401, (st, r))
    finally:
        srv.terminate()
        try:
            out = srv.communicate(timeout=10)[0].decode(errors="replace")
        except Exception:  # noqa: BLE001
            out = ""
        if fails:
            print("---- server log ----\n" + out[-2500:])
    print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
