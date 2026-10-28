"""TripoSR proxy — Image-to-3D GLB model running on localhost:8090.

Proxies requests to the self-hosted TripoSR FastAPI server.

TripoSR API endpoints (localhost:8090):
  GET  /health                → {"status":"ok","model_loaded":true}
  POST /api/image-to-3d       → accepts image file, returns GLB binary
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

from ..config import settings

log = logging.getLogger("vividora.triposr")

_TIMEOUT = 300  # seconds — 3D generation on CPU is slow


def _url(path: str) -> str:
    return f"{settings.triposr_url.rstrip('/')}{path}"


def health() -> dict:
    """Check if TripoSR is reachable and model is loaded."""
    err = "offline"
    for path in ("/api/health", "/health"):  # the TripoSR server on the VM answers on /api/health
        try:
            with urllib.request.urlopen(_url(path), timeout=5) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            err = str(e)
    return {"status": "error", "error": err}


def image_to_3d(image_bytes: bytes, filename: str = "input.png",
                content_type: str = "image/png", out: Path | None = None) -> Path:
    """Send an image to TripoSR and get a GLB file back.

    Args:
        image_bytes:  Raw image file content (PNG/JPEG).
        filename:     Original filename (for the multipart upload).
        content_type: MIME type of the image.
        out:          Output .glb path.  Required.

    Returns the path to the generated GLB file.
    """
    if out is None:
        raise ValueError("out path is required")

    # Build multipart/form-data request manually (no requests library needed)
    boundary = "----VividoraTripoSR9f8e7d6c"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + image_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        _url("/api/image-to-3d"),
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            glb = r.read()
    except urllib.error.HTTPError as e:
        err = e.read().decode(errors="replace")[:500]
        raise RuntimeError(f"TripoSR error ({e.code}): {err}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"TripoSR unreachable: {e.reason}") from e

    if not glb or len(glb) < 100:
        raise RuntimeError("TripoSR returned empty or invalid GLB")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(glb)
    return out


def is_available() -> bool:
    """Quick check: is the TripoSR service running and model loaded?"""
    h = health()
    return h.get("status") == "ok" and h.get("model_loaded", False)
