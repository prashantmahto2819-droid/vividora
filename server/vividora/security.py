from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings

ALGO = "HS256"
ROLES = ("admin", "editor", "viewer")
ROLE_RANK = {"viewer": 0, "editor": 1, "admin": 2}

# scrypt from the standard library — no native package needed on Windows or Linux
_N, _R, _P = 2**14, 8, 1
_MAXMEM = 64 * 1024 * 1024


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32, maxmem=_MAXMEM)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(key).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_b64, key_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        salt, key = base64.b64decode(salt_b64), base64.b64decode(key_b64)
        cand = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32, maxmem=_MAXMEM)
        return hmac.compare_digest(cand, key)
    except (ValueError, TypeError):
        return False


def make_token(subject: str, *, kind: str, hours: float, extra: dict | None = None) -> str:
    payload = {"sub": subject, "kind": kind,
               "exp": datetime.now(timezone.utc) + timedelta(hours=hours)}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGO)


def read_token(token: str, *, kind: str) -> dict | None:
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[ALGO])
    except jwt.PyJWTError:
        return None
    return data if data.get("kind") == kind else None


def access_token(user_id: str, version: int = 0) -> str:
    """`tv` = the user's token_version: "logout everywhere" bumps it and every older token dies."""
    return make_token(user_id, kind="access", hours=settings.access_token_hours, extra={"tv": int(version or 0)})


API_KEY_PREFIX = "vvk_"
# What an API key may call (method, path after /api). Everything else (login, billing, library delete, keys…) is closed.
API_SCOPES = {
    "tts": [("POST", r"/voiceover"), ("GET", r"/voiceover/[0-9a-f]{8,32}"), ("GET", r"/voicestudio/(health|models|voices)")],
    "3d": [("POST", r"/triposr/generate"), ("GET", r"/triposr/(health|job/[0-9a-f]{8,32})")],
}


def new_api_key() -> tuple[str, str, str]:
    """(full key — shown once, prefix for display, sha256 hash stored). Keys are 256-bit random, so a plain hash is enough."""
    import secrets
    key = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return key, key[:10], hash_api_key(key)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def api_key_allows(scopes: str, method: str, path: str) -> bool:
    import re
    for sc in (scopes or "").split(","):
        for m, pat in API_SCOPES.get(sc.strip(), []):
            if m == method and re.fullmatch(pat, path):
                return True
    return False


PASSWORD_MIN = 8


def password_problem(pw: str) -> str | None:
    """Hindi reason why a password is too weak, or None."""
    if len(pw or "") < PASSWORD_MIN:
        return f"password कम से कम {PASSWORD_MIN} अक्षर का हो"
    if pw.lower() in {"password", "12345678", "qwertyui", "11111111", "vividora"}:
        return "यह password बहुत आम है"
    if not any(ch.isdigit() for ch in pw) or not any(ch.isalpha() for ch in pw):
        return "password में अक्षर और अंक दोनों हों"
    return None


def default_secrets_in_use() -> list[str]:
    bad = []
    if settings.secret_key == "dev-only-change-me" or len(settings.secret_key) < 32:
        bad.append("SECRET_KEY")
    if settings.worker_token == "dev-worker-token" or len(settings.worker_token) < 16:
        bad.append("WORKER_TOKEN")
    return bad


def media_token(asset_id: str, hours: float = 6) -> str:
    """Short-lived link token: <video> tags cannot send an Authorization header."""
    return make_token(asset_id, kind="media", hours=hours)


def worker_token_ok(token: str | None) -> bool:
    return bool(token) and hmac.compare_digest(token, settings.worker_token)
