"""RunPod: ready-made "public endpoints" (no server to set up, paid per result) and the creator's own serverless endpoints.

One key (RUNPOD_API_KEY) for everything. Nothing runs between requests, so nothing is billed between them.
    POST {base}/{model}/run {"input": {...}}  →  {"id"}            GET {base}/{model}/status/{id}  →  {"status", "output"}
Public endpoints used here (docs.runpod.io/public-endpoints): `minimax-speech-02-hd` and `chatterbox-turbo` (voices,
output.audio_url) and `p-video` (video, output.result). The answer carries its own price in output.cost.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def ready() -> bool:
    return bool(os.getenv("RUNPOD_API_KEY"))


def base() -> str:
    return (os.getenv("RUNPOD_API_BASE") or "https://api.runpod.ai/v2").rstrip("/")


def _http(method: str, url: str, body: dict | None, timeout: int = 120) -> dict:
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "Vividora/1.0",
                                          "Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"RunPod HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}") from None


def run(model: str, inp: dict, *, poll_s: float = 2.0, max_wait: float = 900, call=None) -> dict:
    """One request → the endpoint's `output` (a dict). Raises RuntimeError with RunPod's own reason on failure."""
    if not ready():
        raise ValueError("RunPod की key नहीं है — Settings → API & Keys में RUNPOD_API_KEY डालें")
    call = call or _http
    url = f"{base()}/{model.strip('/')}"
    job = call("POST", f"{url}/run", {"input": inp})
    jid = job.get("id")
    if not jid:
        raise RuntimeError("RunPod: " + json.dumps(job)[:200])
    t0 = time.time()
    s = job
    while s.get("status") != "COMPLETED":
        if s.get("status") in ("FAILED", "CANCELLED", "TIMED_OUT"):
            raise RuntimeError("RunPod: " + str(s.get("error") or s.get("output") or s.get("status"))[:300])
        if time.time() - t0 > max_wait:
            raise RuntimeError("RunPod: समय ख़त्म — काम पूरा नहीं हुआ")
        time.sleep(poll_s)
        s = call("GET", f"{url}/status/{jid}", None)
    out = s.get("output")
    if isinstance(out, list):
        out = out[0] if out else {}
    if not isinstance(out, dict):
        out = {"result": out}
    if out.get("error"):
        raise RuntimeError("RunPod: " + str(out["error"])[:300])
    return out


def cost_of(out: dict) -> float | None:
    try:
        c = out.get("cost")
        return None if c is None else max(0.0, float(c))
    except (TypeError, ValueError):
        return None


def download(url: str, dest: Path, max_bytes: int = 200 * 1024 * 1024) -> Path:
    if not str(url).startswith(("https://", "http://127.0.0.1")):
        raise RuntimeError("RunPod: फ़ाइल का link नहीं मिला")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Vividora/1.0"}), timeout=300) as r:
        data = r.read(max_bytes + 1)
    if len(data) > max_bytes or len(data) < 500:
        raise RuntimeError("RunPod: फ़ाइल खाली या बहुत बड़ी है")
    dest.write_bytes(data)
    return dest
