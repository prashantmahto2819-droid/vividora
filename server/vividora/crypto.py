"""Secrets at rest: `connections.secrets` (OAuth tokens) are encrypted with a Fernet key derived
from SECRET_KEY. Rows are stored as the string "enc:<token>"; plaintext JSON from older versions is
still read and re-encrypted on first start (db.init)."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from typing import Any

from .config import settings

log = logging.getLogger("vividora.crypto")
PREFIX = "enc:"

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # noqa: BLE001 — the package is in requirements; old images fall back to plaintext with a warning
    Fernet = None  # type: ignore[assignment]
    InvalidToken = ValueError  # type: ignore[assignment,misc]
    log.warning("cryptography नहीं मिला — connection tokens plaintext में रहेंगे (pip install cryptography)")

_f = None


def _fernet():
    global _f
    if _f is None and Fernet is not None:
        key = base64.urlsafe_b64encode(hashlib.sha256(("vividora-secrets:" + settings.secret_key).encode()).digest())
        _f = Fernet(key)
    return _f


def available() -> bool:
    return Fernet is not None


def encrypt_json(value: Any) -> str:
    """dict/list → "enc:..." (or plain JSON when the library is missing)."""
    raw = json.dumps(value, ensure_ascii=False)
    f = _fernet()
    if f is None:
        return raw
    return PREFIX + f.encrypt(raw.encode()).decode()


def decrypt_json(text: str | None) -> Any:
    if text is None:
        return None
    if not isinstance(text, str):
        return text
    if text.startswith(PREFIX):
        f = _fernet()
        if f is None:
            raise RuntimeError("encrypted secrets but cryptography is not installed")
        try:
            return json.loads(f.decrypt(text[len(PREFIX):].encode()).decode())
        except InvalidToken:
            # SECRET_KEY changed: the tokens are gone; the connection shows as "दोबारा connect करें"
            log.warning("connection secrets could not be decrypted (SECRET_KEY changed?) — reconnect needed")
            return {"_undecryptable": True}
    return json.loads(text) if text else {}


def is_encrypted(text: str | None) -> bool:
    return isinstance(text, str) and text.startswith(PREFIX)
