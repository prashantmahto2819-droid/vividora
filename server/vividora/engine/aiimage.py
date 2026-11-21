"""AI picture generation through a hosted GPU API (this server has no CUDA, so the GPU is rented per image).

Providers (first configured wins; AI_IMAGE_PROVIDER forces one):
  cloudflare   Workers AI FLUX.1-schnell   CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN (Workers AI permission) — free daily allowance
  huggingface  FLUX.1-schnell Inference    HF_TOKEN — free tier with limits
  pollinations FLUX, no key                AI_IMAGE_PROVIDER=pollinations only (prompts go to a public service, uptime not guaranteed)

generate() returns the path of a written image or raises. `post` / `get` are injectable for tests."""

from __future__ import annotations

import base64
import json
import os
import urllib.request
from pathlib import Path

STYLE = "cinematic documentary photograph, natural light, realistic, high detail, no text, no watermark"
MAX_BYTES = 12 * 1024 * 1024


def provider() -> str | None:
    forced = (os.getenv("AI_IMAGE_PROVIDER") or "").strip().lower()
    if forced in ("cloudflare", "huggingface", "pollinations"):
        ok = {"cloudflare": bool(os.getenv("CLOUDFLARE_ACCOUNT_ID") and os.getenv("CLOUDFLARE_API_TOKEN")),
              "huggingface": bool(os.getenv("HF_TOKEN")), "pollinations": True}[forced]
        return forced if ok else None
    if os.getenv("CLOUDFLARE_ACCOUNT_ID") and os.getenv("CLOUDFLARE_API_TOKEN"):
        return "cloudflare"
    if os.getenv("HF_TOKEN"):
        return "huggingface"
    return None


def _http(url: str, data: bytes | None, headers: dict, timeout: int = 90) -> tuple[bytes, str]:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "Vividora/1.0", **headers}, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        blob = r.read(MAX_BYTES + 1)
        if len(blob) > MAX_BYTES:
            raise RuntimeError("image too large")
        return blob, r.headers.get("content-type", "")


def prompt_for(visual: str, narration: str = "") -> str:
    base = (visual or narration or "").strip()[:300]
    return f"{base}, {STYLE}"


def generate(prompt: str, dest: Path, size: tuple[int, int] = (1280, 720), http=None) -> tuple[Path, str]:
    """Write an image for `prompt` to dest; returns (path, provider). Raises RuntimeError on any failure."""
    prov = provider()
    if not prov:
        raise RuntimeError("AI image provider not configured")
    http = http or _http
    w, h = size
    if prov == "cloudflare":
        url = (f"{os.getenv('CLOUDFLARE_API_BASE', 'https://api.cloudflare.com')}/client/v4/accounts/{os.environ['CLOUDFLARE_ACCOUNT_ID']}"
               "/ai/run/@cf/black-forest-labs/flux-1-schnell")
        blob, _ = http(url, json.dumps({"prompt": prompt, "steps": 6}).encode(),
                       {"Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}", "Content-Type": "application/json"})
        j = json.loads(blob)
        b64 = ((j.get("result") or {}).get("image")) if j.get("success", True) else None
        if not b64:
            raise RuntimeError("cloudflare: " + json.dumps(j.get("errors") or j)[:200])
        data = base64.b64decode(b64)
    elif prov == "huggingface":
        data, ctype = http("https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell",
                           json.dumps({"inputs": prompt}).encode(),
                           {"Authorization": f"Bearer {os.environ['HF_TOKEN']}", "Content-Type": "application/json", "Accept": "image/png"})
        if "image" not in ctype:
            raise RuntimeError("huggingface: " + data[:200].decode("utf-8", "replace"))
    else:
        from urllib.parse import quote
        data, ctype = http(f"https://image.pollinations.ai/prompt/{quote(prompt)}?width={w}&height={h}&nologo=true&model=flux", None, {})
        if "image" not in ctype:
            raise RuntimeError("pollinations: not an image")
    if not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:4] == b"RIFF"):
        raise RuntimeError("provider did not return an image")
    dest = dest.with_suffix(".jpg" if data[:3] == b"\xff\xd8\xff" else ".png" if data[:4] == b"\x89PNG" else ".webp")
    dest.write_bytes(data)
    return dest, prov
