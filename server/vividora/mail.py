"""Transactional email (SMTP).  No-op when SMTP_HOST is not set.

Usage::

    from . import mail
    mail.send_reset(email, reset_url)
    mail.send_verify(email, verify_url)

All sends happen in a background thread so they never block a request.
"""

from __future__ import annotations

import logging
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import settings

log = logging.getLogger("vividora.mail")


def configured() -> bool:
    """True when SMTP credentials are present and we can send mail."""
    return bool(settings.smtp_host and settings.smtp_from)


def _sender() -> str:
    return settings.smtp_from or settings.admin_email


def _connect() -> smtplib.SMTP:
    s = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
    if settings.smtp_tls:
        s.starttls()
    if settings.smtp_user:
        s.login(settings.smtp_user, settings.smtp_password)
    return s


def _send(to: str, subject: str, html: str, text: str | None = None) -> None:
    """Send one email synchronously (called from the background thread)."""
    msg = MIMEMultipart("alternative")
    msg["From"] = _sender()
    msg["To"] = to
    msg["Subject"] = subject
    if text:
        msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with _connect() as s:
            s.sendmail(_sender(), [to], msg.as_string())
        log.info("email sent to %s — %s", to, subject)
    except Exception:
        log.exception("email send failed to %s — %s", to, subject)


def send_async(to: str, subject: str, html: str, text: str | None = None) -> None:
    """Fire-and-forget email in a daemon thread so the API response isn't delayed."""
    if not configured():
        log.debug("SMTP not configured — skipping email to %s", to)
        return
    t = threading.Thread(target=_send, args=(to, subject, html, text), daemon=True)
    t.start()


# ----------------------------------------------------------------- templates


_STYLE = (
    "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; "
    "max-width: 480px; margin: 0 auto; padding: 32px 24px; color: #1a1a1a;"
)


def _wrap(body_html: str) -> str:
    return (
        f'<div style="{_STYLE}">'
        f'<h2 style="color:#6c3ce9; margin-top:0;">Vividora</h2>'
        f"{body_html}"
        f'<p style="margin-top:32px; font-size:12px; color:#888;">— Vividora Studio</p>'
        f"</div>"
    )


def send_reset(email: str, reset_url: str) -> None:
    """Password-reset email with a one-click link (valid 1 hour)."""
    html = _wrap(
        f"<p>Password reset करने के लिए नीचे दिया बटन दबाएँ। यह link 1 घंटे तक valid है।</p>"
        f'<p style="text-align:center; margin:24px 0;">'
        f'<a href="{reset_url}" style="background:#6c3ce9; color:#fff; padding:12px 28px; '
        f'border-radius:6px; text-decoration:none; font-weight:600;">Password Reset करें</a></p>'
        f'<p style="font-size:13px; color:#666;">अगर यह आपने नहीं किया तो ignore करें — कुछ नहीं बदलेगा।</p>'
        f'<p style="font-size:12px; color:#999; word-break:break-all;">Link: {reset_url}</p>'
    )
    text = f"Password reset link (1 hour valid): {reset_url}\n\nAgar aapne nahi kiya to ignore karein."
    send_async(email, "Vividora — Password Reset", html, text)


def send_verify(email: str, verify_url: str) -> None:
    """Email verification after signup."""
    html = _wrap(
        f"<p>Vividora में आपका account बन गया है! Email verify करने के लिए नीचे दिया बटन दबाएँ।</p>"
        f'<p style="text-align:center; margin:24px 0;">'
        f'<a href="{verify_url}" style="background:#6c3ce9; color:#fff; padding:12px 28px; '
        f'border-radius:6px; text-decoration:none; font-weight:600;">Email Verify करें</a></p>'
        f'<p style="font-size:12px; color:#999; word-break:break-all;">Link: {verify_url}</p>'
    )
    text = f"Email verify karne ke liye: {verify_url}"
    send_async(email, "Vividora — Email Verify करें", html, text)
