"""AI motion for a still picture (image → short video clip) through a hosted GPU API. Paid per clip — always opt-in per scene.

Provider: fal.ai queue API (FAL_KEY). Any fal image-to-video model works without code changes:
  AI_VIDEO_MODEL        model id (default fal-ai/ltx-video/image-to-video)
  AI_VIDEO_IMAGE_FIELD  name of the image input (default image_url)
  AI_VIDEO_PROMPT_FIELD name of the prompt input (default prompt; empty = send none)
  AI_VIDEO_EXTRA_JSON   extra inputs as JSON, e.g. {"duration": "5", "resolution": "720p"}
  AI_VIDEO_PRICE_PER_SEC / AI_VIDEO_SECONDS  your model's price (from its fal page) + clip length → cost estimate shown before a build
Output is read from video.url (the fal convention). Not exercised against the real service in tests (fake server via FAL_QUEUE_BASE); check your fal dashboard for the
current model id and price before a big run. AI_VIDEO_MAX caps clips per film (default 4).
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.request
from pathlib import Path

MAX_BYTES = 80 * 1024 * 1024


def provider() -> str | None:
    return "fal" if os.getenv("FAL_KEY") else None


def max_clips() -> int:
    try:
        return max(0, min(20, int(os.getenv("AI_VIDEO_MAX", "4"))))
    except ValueError:
        return 4


def estimate_usd(clips: int) -> float | None:
    """Rough cost of `clips` AI clips from the price you configured (None when no price is set)."""
    try:
        price = float(os.getenv("AI_VIDEO_PRICE_PER_SEC") or 0)
        secs = float(os.getenv("AI_VIDEO_SECONDS") or 5)
    except ValueError:
        return None
    return round(price * secs * max(0, clips), 2) if price > 0 else None


def _call(method: str, url: str, body: dict | None = None, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Key {os.environ['FAL_KEY']}", "Content-Type": "application/json", "User-Agent": "Vividora/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def animate(image: Path, prompt: str, dest: Path, *, call=None, download=None, poll_s: float = 4.0, max_wait: float = 420.0) -> Path:
    """Image → MP4 at dest. Raises RuntimeError on any failure or timeout."""
    if not provider():
        raise RuntimeError("AI video provider not configured")
    from . import meter
    meter.check("ai_video")
    call = call or _call
    base = os.getenv("FAL_QUEUE_BASE", "https://queue.fal.run")
    model = os.getenv("AI_VIDEO_MODEL", "fal-ai/ltx-video/image-to-video").strip("/")
    mime = mimetypes.guess_type(image.name)[0] or "image/png"
    uri = f"data:{mime};base64,{base64.b64encode(image.read_bytes()).decode()}"
    body = {os.getenv("AI_VIDEO_IMAGE_FIELD", "image_url"): uri}
    pf = os.getenv("AI_VIDEO_PROMPT_FIELD", "prompt")
    if pf:
        body[pf] = prompt[:400]
    try:
        extra = json.loads(os.getenv("AI_VIDEO_EXTRA_JSON") or "{}")
        body.update(extra if isinstance(extra, dict) else {})
    except ValueError:
        raise RuntimeError("AI_VIDEO_EXTRA_JSON सही JSON नहीं है") from None
    job = call("POST", f"{base}/{model}", body)
    status_url, resp_url = job.get("status_url"), job.get("response_url")
    if not status_url or not resp_url:
        raise RuntimeError("fal: " + json.dumps(job)[:200])
    t0 = time.time()
    while True:
        s = call("GET", status_url)
        if s.get("status") == "COMPLETED":
            break
        if s.get("status") in ("FAILED", "ERROR") or time.time() - t0 > max_wait:
            raise RuntimeError("fal: " + (str(s.get("error") or s.get("status")))[:200])
        time.sleep(poll_s)
    out = call("GET", resp_url)
    url = ((out.get("video") or {}).get("url")) or ""
    if not url.startswith("https://") and not url.startswith("http://127.0.0.1"):
        raise RuntimeError("fal: no video url")
    (download or _download)(url, dest)
    if not dest.exists() or dest.stat().st_size < 1000:
        raise RuntimeError("fal: empty video")
    try:
        secs = float(os.getenv("AI_VIDEO_SECONDS") or 5)
    except ValueError:
        secs = 5.0
    meter.add("ai_video", prompt[:80], secs)
    return dest


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "Vividora/1.0"})
    n = 0
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            n += len(chunk)
            if n > MAX_BYTES:
                raise RuntimeError("video too large")
            f.write(chunk)
