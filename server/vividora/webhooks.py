"""Optional `callback_url` for long jobs: when a job ends Vividora POSTs a small JSON to your URL.
The body carries only ids/status — fetch the details with GET /api/v1/jobs/{id} using your API key (that is the check
that the call is genuine). Private / local addresses are refused (SSRF)."""

from __future__ import annotations

import ipaddress
import json
import logging
import socket
import threading
import urllib.request
from urllib.parse import urlparse

log = logging.getLogger("vividora.webhooks")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):  # noqa: D401 — never follow redirects
        return None


def check_url(url: str) -> str:
    """Return the cleaned URL or raise ValueError (Hindi message)."""
    url = (url or "").strip()
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname or len(url) > 500:
        raise ValueError("callback_url सही http(s) URL होना चाहिए")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except OSError:
        raise ValueError("callback_url का host नहीं मिला")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError("callback_url private/local address पर नहीं हो सकता")
    return url


def _post(url: str, payload: dict) -> None:
    try:
        check_url(url)  # re-check at send time
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "Vividora-Webhook/1"})
        opener = urllib.request.build_opener(_NoRedirect)
        opener.open(req, timeout=10).read(1024)
    except Exception as e:  # noqa: BLE001 — a dead receiver must never hurt the job
        log.warning("webhook %s failed: %s", urlparse(url).netloc, e)


def notify(st: dict, job_id: str, kind: str) -> None:
    """Fire (in a thread) if the job asked for a callback."""
    url = st.get("callback")
    if not url:
        return
    payload = {"event": "job.finished", "job_id": job_id, "kind": kind, "status": st.get("status"),
               "item_id": (st.get("item") or {}).get("id"), "error": st.get("error")}
    threading.Thread(target=_post, args=(url, payload), daemon=True).start()
