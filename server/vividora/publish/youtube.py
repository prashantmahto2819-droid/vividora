"""YouTube Data API v3: OAuth (refresh-token) + resumable video upload.

Setup (once, free): Google Cloud project → enable "YouTube Data API v3" →
OAuth consent screen (External, add your Google account as test user) →
Credentials → OAuth client ID (Web application) with redirect URI
  {PUBLIC_URL}/api/connect/youtube/callback
Put the client id/secret in .env as YT_CLIENT_ID / YT_CLIENT_SECRET.
Quota: 10 000 units/day; one upload costs ~1 600 units (≈6 uploads/day).
"""

from __future__ import annotations

import time
import urllib.parse
from pathlib import Path

from ..config import settings
from .http import PublishError, request, upload_file

SCOPES = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"

CATEGORIES = {"people": "22", "education": "27", "entertainment": "24", "howto": "26", "news": "25"}


def configured() -> bool:
    return bool(settings.yt_client_id and settings.yt_client_secret and settings.public_url)


def redirect_uri() -> str:
    return f"{settings.public_url}/api/connect/youtube/callback"


def auth_url(state: str) -> str:
    q = {"client_id": settings.yt_client_id, "redirect_uri": redirect_uri(), "response_type": "code",
         "scope": SCOPES, "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true",
         "state": state}
    return AUTH_URL + "?" + urllib.parse.urlencode(q)


def exchange_code(code: str) -> dict:
    tok = request("POST", TOKEN_URL, form={"code": code, "client_id": settings.yt_client_id,
                                           "client_secret": settings.yt_client_secret,
                                           "redirect_uri": redirect_uri(), "grant_type": "authorization_code"})
    if "refresh_token" not in tok:
        raise PublishError("Google ने refresh token नहीं दिया — पहले से दी गई अनुमति हटाकर दोबारा जोड़ें")
    return {"refresh_token": tok["refresh_token"], "access_token": tok.get("access_token"),
            "expires_at": time.time() + float(tok.get("expires_in", 3600)) - 60}


def access_token(secrets: dict) -> tuple[str, dict]:
    """Returns (token, updated_secrets)."""
    if secrets.get("access_token") and time.time() < float(secrets.get("expires_at", 0)):
        return secrets["access_token"], secrets
    tok = request("POST", TOKEN_URL, form={"refresh_token": secrets["refresh_token"],
                                           "client_id": settings.yt_client_id,
                                           "client_secret": settings.yt_client_secret,
                                           "grant_type": "refresh_token"})
    new = {**secrets, "access_token": tok["access_token"],
           "expires_at": time.time() + float(tok.get("expires_in", 3600)) - 60}
    return new["access_token"], new


def channel_info(token: str) -> dict:
    r = request("GET", f"{API}/channels", params={"part": "snippet,statistics", "mine": "true"},
                headers={"Authorization": f"Bearer {token}"})
    items = r.get("items") or []
    if not items:
        raise PublishError("इस Google account पर कोई YouTube channel नहीं मिला")
    ch = items[0]
    return {"id": ch["id"], "title": ch["snippet"]["title"],
            "thumbnail": (ch["snippet"].get("thumbnails") or {}).get("default", {}).get("url"),
            "subscribers": (ch.get("statistics") or {}).get("subscriberCount")}


def upload_video(token: str, path: Path, *, title: str, description: str, tags: list[str],
                 privacy: str = "private", publish_at: str | None = None, category: str = "22",
                 language: str | None = None, made_for_kids: bool = False, on_progress=None) -> dict:
    status = {"privacyStatus": privacy if privacy in ("private", "unlisted", "public") else "private",
              "selfDeclaredMadeForKids": made_for_kids}
    if publish_at:
        status["privacyStatus"] = "private"  # YouTube requires private + publishAt for scheduling
        status["publishAt"] = publish_at
    snippet = {"title": title[:100], "description": description[:5000], "tags": tags[:60],
               "categoryId": category}
    if language:
        snippet["defaultLanguage"] = language
        snippet["defaultAudioLanguage"] = language
    body = {"snippet": snippet, "status": status}
    size = path.stat().st_size
    # step 1: start a resumable session
    import json
    import urllib.request
    req = urllib.request.Request(
        UPLOAD + "?uploadType=resumable&part=snippet,status", data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "video/*"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            session = r.headers.get("Location")
    except urllib.error.HTTPError as e:
        raise PublishError(f"YouTube {e.code}: {e.read().decode(errors='replace')[:400]}",
                           retry=e.code in (429, 500, 503)) from None
    if not session:
        raise PublishError("YouTube ने upload session नहीं दिया")
    # step 2: send the bytes
    result = upload_file(session, path, headers={"Authorization": f"Bearer {token}", "Content-Type": "video/*"},
                         on_progress=on_progress)
    vid = result.get("id")
    if not vid:
        raise PublishError(f"upload finished without a video id: {str(result)[:200]}")
    return {"remote_id": vid, "url": f"https://youtu.be/{vid}",
            "status": (result.get("status") or {}).get("uploadStatus")}


def set_thumbnail(token: str, video_id: str, image: Path) -> None:
    import urllib.request
    data = image.read_bytes()
    req = urllib.request.Request(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={video_id}",
                                 data=data, method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg",
                                          "Content-Length": str(len(data))})
    try:
        urllib.request.urlopen(req, timeout=120).read()
    except urllib.error.HTTPError as e:
        raise PublishError(f"thumbnail {e.code}: {e.read().decode(errors='replace')[:300]}") from None
