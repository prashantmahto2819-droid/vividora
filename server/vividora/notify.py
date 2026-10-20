"""WhatsApp (via your Vivid Relay gateway) or any HTTP webhook.

NOTIFY_URL       e.g. https://relay.example.com/api/send
NOTIFY_TOKEN     sent as  Authorization: Bearer <token>  and  X-Api-Key: <token>
NOTIFY_TO        phone / chat id the messages go to
NOTIFY_TEMPLATE  JSON body with {to} and {text} placeholders
                 default: {"to": "{to}", "message": "{text}"}

Replies: POST /api/hooks/inbound {"from": "...", "text": "ok 7F3A"} with header
X-Hook-Secret: NOTIFY_INBOUND_SECRET approves the project whose code matches.
Nothing is published from a reply — approval only unlocks the Publish button.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request

from .config import settings

log = logging.getLogger("vividora.notify")


def enabled() -> bool:
    return bool(settings.notify_url and settings.notify_to)


def send_now(text: str) -> tuple[bool, str]:
    """Send and report the gateway's answer (for the Settings test button)."""
    body = settings.notify_template.replace("{to}", settings.notify_to).replace("{text}", json.dumps(text)[1:-1])
    headers = {"Content-Type": "application/json"}
    if settings.notify_token:
        headers["Authorization"] = f"Bearer {settings.notify_token}"
        headers["X-Api-Key"] = settings.notify_token
    req = urllib.request.Request(settings.notify_url, data=body.encode(), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return True, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:200]
        return False, f"HTTP {e.code}: {detail}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:200]


def _send(text: str) -> None:
    body = settings.notify_template.replace("{to}", settings.notify_to).replace("{text}", json.dumps(text)[1:-1])
    headers = {"Content-Type": "application/json"}
    if settings.notify_token:
        headers["Authorization"] = f"Bearer {settings.notify_token}"
        headers["X-Api-Key"] = settings.notify_token
    req = urllib.request.Request(settings.notify_url, data=body.encode(), method="POST", headers=headers)
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:  # noqa: BLE001 — a lost notification must never break a job
        log.warning("notify failed: %s", e)


def send(text: str) -> None:
    if not enabled():
        return
    threading.Thread(target=_send, args=(text,), daemon=True).start()


def code_for(project_id: str) -> str:
    return project_id[:4].upper()


def project_link(project_id: str) -> str:
    base = settings.public_url or "http://localhost:8000"
    return f"{base}/#/projects/{project_id}"


def on_event(event: str, project: dict, extra: str = "") -> None:
    """Called by service.after_job / publish; keeps messages short and actionable."""
    title = project.get("title", "")
    code = code_for(project["id"])
    link = project_link(project["id"])
    msgs = {
        "review_cuts": f"✂️ {title}\nकट तैयार हैं — dashboard में जाँचें:\n{link}",
        "review_output": f"🎬 {title}\nrender तैयार है{(' · ' + extra) if extra else ''}\nदेखें: {link}\nमंज़ूरी देने के लिए reply करें: ok {code}",
        "failed": f"⚠️ {title}\nरुक गया: {extra}\n{link}",
        "published": f"🚀 {title}\n{extra}",
        "publish_failed": f"❌ {title}\npublish असफल: {extra}",
        "shorts": f"📱 {title}\n{extra} Shorts सुझाए गए — Shorts tab में देखें:\n{link}",
    }
    if event in msgs:
        send(msgs[event])
