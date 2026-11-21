#!/usr/bin/env python3
"""Vividora MCP server (tools/vividora_mcp.py) against a real local server.   cd server && python3 tests/test_mcp.py"""
from __future__ import annotations

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
fails = 0


def check(label, cond, val=None):
    global fails
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"  → {str(val)[:300]}"))
    fails += 0 if cond else 1


def mcp(env, msgs):
    p = subprocess.run([sys.executable, str(HERE / "tools" / "vividora_mcp.py")], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                       capture_output=True, text=True, env={**os.environ, **env}, timeout=60)
    return [json.loads(x) for x in p.stdout.splitlines() if x.strip()], p.stderr


def call(i, name, args=None):
    return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args or {}}}


def main():
    tmp = Path(tempfile.mkdtemp(prefix="vivi_mcp_"))
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    env = {**os.environ, "DATA_ROOT": str(tmp / "data"), "MEDIA_ROOT": str(tmp / "media"), "ADMIN_PASSWORD": "test-pass-123",
           "SECRET_KEY": "t", "WEB_DIST": str(tmp / "web"), "TRIPOSR_URL": "http://127.0.0.1:9"}
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "vividora.app:app", "--port", str(port), "--log-level", "warning"],
                           cwd=str(HERE), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"

    def api(method, path, body=None, tok=None):
        r = urllib.request.Request(base + "/api" + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                   headers={"content-type": "application/json", **({"authorization": f"Bearer {tok}"} if tok else {})})
        return json.loads(urllib.request.urlopen(r, timeout=60).read())

    try:
        for _ in range(400):
            try:
                api("GET", "/health"); break
            except OSError:
                time.sleep(0.3)
        tok = api("POST", "/auth/login", {"email": "admin@vividora.local", "password": "test-pass-123"})["token"]
        key = api("POST", "/keys", {"name": "mcp"}, tok)["key"]
        e = {"VIVIDORA_URL": base, "VIVIDORA_API_KEY": key}
        eff = {"titles": [{"start": 5, "end": 8}], "broll": [{"id": "x", "start": 12, "end": 16, "fit": "cover"}], "sfx": []}
        out, err = mcp(e, [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            call(3, "vividora_whoami"),
            call(4, "vividora_auto_sfx", {"duration": 60, "effects": eff, "density": "normal"}),
            call(5, "vividora_nope"),
            call(6, "vividora_job_status", {"job_id": "zzz"}),
            call(7, "vividora_image_to_3d", {"image_path": "/no/such.png"}),
            call(8, "vividora_text_to_speech", {}),
            {"jsonrpc": "2.0", "id": 9, "method": "bogus"},
        ])
        by = {o["id"]: o for o in out}
        check("one reply per request (notification gets none)", sorted(by) == [1, 2, 3, 4, 5, 6, 7, 8, 9], sorted(by))
        check("initialize", by[1]["result"]["serverInfo"]["name"] == "vividora" and "tools" in by[1]["result"]["capabilities"], by[1])
        names = [t["name"] for t in by[2]["result"]["tools"]]
        check("8+ tools listed with schemas", len(names) >= 8 and all(t["inputSchema"]["type"] == "object" for t in by[2]["result"]["tools"]), names)
        who = json.loads(by[3]["result"]["content"][0]["text"])
        check("whoami works with the key", who["via_api_key"] is True and who["role"], who)
        sfx = json.loads(by[4]["result"]["content"][0]["text"])
        check("auto_sfx via MCP", sfx["added"] >= 2 and all(x["_id"].startswith("asfx_") for x in sfx["sfx"]), sfx)
        check("unknown tool → JSON-RPC error", "error" in by[5], by[5])
        check("unknown job → isError with message", by[6]["result"].get("isError") and "404" in by[6]["result"]["content"][0]["text"], by[6])
        check("missing image → isError", by[7]["result"].get("isError"), by[7])
        check("tts without text → isError", by[8]["result"].get("isError"), by[8])
        check("unknown method → -32601", by[9]["error"]["code"] == -32601, by[9])
        out, _ = mcp({"VIVIDORA_URL": base, "VIVIDORA_API_KEY": "vk_wrong"}, [call(1, "vividora_whoami")])
        t = out[0]["result"]
        check("wrong key → isError 401", t.get("isError") and "401" in t["content"][0]["text"], out)
        out, _ = mcp({"VIVIDORA_URL": "", "VIVIDORA_API_KEY": ""}, [call(1, "vividora_whoami")])
        check("no env → clear message", out[0]["result"].get("isError") and "VIVIDORA_URL" in out[0]["result"]["content"][0]["text"], out)
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except subprocess.TimeoutExpired:
            srv.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAILED'}")
    sys.exit(1 if fails else 0)


main()
