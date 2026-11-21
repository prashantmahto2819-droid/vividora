"""TOTP (RFC 6238) with the standard library only — works with Google Authenticator, Microsoft Authenticator, Authy, 1Password…

SHA-1, 6 digits, 30 s step. verify() accepts ±1 step (clock drift) and returns the matched counter so the caller can refuse replays."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

STEP, DIGITS = 30, 6


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = mac[-1] & 0x0F
    return str((struct.unpack(">I", mac[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** DIGITS).zfill(DIGITS)


def now_code(secret: str, at: float | None = None) -> str:
    return _code(secret, int((time.time() if at is None else at) // STEP))


def verify(secret: str, code: str, *, last_counter: int = 0, at: float | None = None, window: int = 1) -> int | None:
    """Matched time-step counter, or None. A counter <= last_counter is a replay and is refused."""
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != DIGITS:
        return None
    cur = int((time.time() if at is None else at) // STEP)
    for c in range(cur - window, cur + window + 1):
        if c > last_counter and hmac.compare_digest(_code(secret, c), code):
            return c
    return None


def otpauth_uri(secret: str, account: str, issuer: str = "Vividora") -> str:
    label = urllib.parse.quote(f"{issuer}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={urllib.parse.quote(issuer)}&algorithm=SHA1&digits={DIGITS}&period={STEP}"


def new_recovery_codes(n: int = 8) -> list[str]:
    """Readable one-time codes like 'k7m2-9xqa' (shown once, stored hashed)."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return ["".join(secrets.choice(alphabet) for _ in range(4)) + "-" + "".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(n)]


def hash_recovery(code: str) -> str:
    return hashlib.sha256(code.strip().lower().replace(" ", "").encode()).hexdigest()
