"""Auto-rigging of a 3D model (.glb) on a cloud GPU — UniRig (skeleton + skin weights) running in your own serverless worker.

This server has no CUDA, so the model runs on a rented GPU. Contract (RunPod-serverless style; any host that speaks it works):

    POST {base}/run            {"input": {"glb_b64": "...", "template": "mixamo"}}  → {"id": "..."}
    GET  {base}/status/{id}    → {"status": "IN_QUEUE|IN_PROGRESS|COMPLETED|FAILED", "output": {"glb_b64": "..."} | "error": "..."}

    base  = UNIRIG_URL, or https://api.runpod.ai/v2/{UNIRIG_ENDPOINT_ID}     auth: Bearer RUNPOD_API_KEY (or UNIRIG_TOKEN)

The worker image lives in gpu-worker/unirig/ (deploy it once, see its README). `call` is injectable for tests."""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.request

MAX_INPUT = 8 * 1024 * 1024  # RunPod's request body limit is ~10 MB incl. base64
TEMPLATES = ("mixamo", "vroid", "articulationxl")


def base_url() -> str | None:
    u = (os.getenv("UNIRIG_URL") or "").rstrip("/")
    if u:
        return u
    eid = os.getenv("UNIRIG_ENDPOINT_ID")
    return f"https://api.runpod.ai/v2/{eid}" if eid else None


def configured() -> bool:
    return bool(base_url() and (os.getenv("RUNPOD_API_KEY") or os.getenv("UNIRIG_TOKEN") or os.getenv("UNIRIG_URL")))


def _call(method: str, url: str, body: dict | None = None, timeout: int = 60) -> dict:
    h = {"Content-Type": "application/json", "User-Agent": "Vividora/1.0"}
    tok = os.getenv("UNIRIG_TOKEN") or os.getenv("RUNPOD_API_KEY")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def rig(glb: bytes, template: str = "mixamo", *, call=None, poll_s: float = 5.0, max_wait: float = 900.0, on_status=None) -> bytes:
    """glb bytes → rigged glb bytes. Raises RuntimeError with a readable reason."""
    if not configured():
        raise RuntimeError("cloud GPU rigging सेट नहीं है (.env में UNIRIG_ENDPOINT_ID + RUNPOD_API_KEY)")
    if glb[:4] != b"glTF":
        raise RuntimeError("यह .glb फ़ाइल नहीं है")
    if len(glb) > MAX_INPUT:
        raise RuntimeError(f"model बहुत बड़ा ({len(glb) // 1048576} MB; max {MAX_INPUT // 1048576} MB) — पहले छोटा/decimate करें")
    template = template if template in TEMPLATES else "mixamo"
    call = call or _call
    base = base_url()
    job = call("POST", f"{base}/run", {"input": {"glb_b64": base64.b64encode(glb).decode(), "template": template}})
    jid = job.get("id")
    if not jid:
        raise RuntimeError("GPU worker ने job नहीं लिया: " + json.dumps(job)[:200])
    t0 = time.time()
    while True:
        s = call("GET", f"{base}/status/{jid}")
        stt = s.get("status")
        if on_status:
            on_status(stt)
        if stt == "COMPLETED":
            out = s.get("output") or {}
            if out.get("error"):
                raise RuntimeError("rigging नहीं हो पाई: " + str(out["error"])[:200])
            data = base64.b64decode(out.get("glb_b64") or "")
            if data[:4] != b"glTF":
                raise RuntimeError("worker ने सही .glb नहीं लौटाई")
            return data
        if stt in ("FAILED", "CANCELLED", "TIMED_OUT"):
            raise RuntimeError("GPU job " + str(stt).lower() + ": " + str(s.get("error") or "")[:200])
        if time.time() - t0 > max_wait:
            raise RuntimeError("GPU worker बहुत देर से जवाब नहीं दे रहा (cold start हो सकता है) — थोड़ी देर बाद फिर कोशिश करें")
        time.sleep(poll_s)
