"""TikTok Content Publishing API: OAuth + video upload.

Setup (once): developers.tiktok.com → create an app → add "Content Posting API"
and "Login Kit" products → set redirect URI to
  {PUBLIC_URL}/api/connect/tiktok/callback
Put the client key/secret in .env as TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET.

TikTok uses "pull" uploads: we give TikTok a PUBLIC URL to our rendered
video and TikTok's servers download it. Same pattern as Instagram/Facebook,
served via /pub/<signed token> (see api/publish.py).

Limits: 20 posts / day per user (Content Posting API rate limit).
Video: min 3s, max 10min, max 4GB, H.264, AAC audio.
"""

from __future__ import annotations

import time
import urllib.parse

from ..config import settings
from .http import PublishError, request

API = "https://open.tiktokapis.com/v2"
AUTH = "https://www.tiktok.com/v2/auth/authorize/"

SCOPES = "user.info.basic,video.publish,video.upload"


def configured() -> bool:
    return bool(settings.tiktok_client_key and settings.tiktok_client_secret and settings.public_url)


def redirect_uri() -> str:
    return f"{settings.public_url}/api/connect/tiktok/callback"


def auth_url(state: str) -> str:
    q = {"client_key": settings.tiktok_client_key, "redirect_uri": redirect_uri(),
         "scope": SCOPES, "response_type": "code", "state": state}
    return AUTH + "?" + urllib.parse.urlencode(q)


def exchange_code(code: str) -> dict:
    """Exchange authorization code for access + refresh token."""
    r = request("POST", f"{API}/oauth/token/", form={
        "client_key": settings.tiktok_client_key,
        "client_secret": settings.tiktok_client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri(),
    })
    if r.get("error"):
        raise PublishError(f"TikTok token exchange failed: {r.get('error_description', r.get('error'))}")
    return {
        "access_token": r["access_token"],
        "refresh_token": r.get("refresh_token", ""),
        "open_id": r.get("open_id", ""),
        "expires_at": time.time() + float(r.get("expires_in", 86400)),
        "refresh_expires_at": time.time() + float(r.get("refresh_expires_in", 365 * 86400)),
    }


def refresh_token(secrets: dict) -> dict:
    """Refresh the access token using the refresh token."""
    r = request("POST", f"{API}/oauth/token/", form={
        "client_key": settings.tiktok_client_key,
        "client_secret": settings.tiktok_client_secret,
        "grant_type": "refresh_token",
        "refresh_token": secrets["refresh_token"],
    })
    if r.get("error"):
        raise PublishError(f"TikTok refresh failed: {r.get('error_description', r.get('error'))}")
    return {
        "access_token": r["access_token"],
        "refresh_token": r.get("refresh_token", secrets["refresh_token"]),
        "open_id": secrets.get("open_id", r.get("open_id", "")),
        "expires_at": time.time() + float(r.get("expires_in", 86400)),
        "refresh_expires_at": time.time() + float(r.get("refresh_expires_in", 365 * 86400)),
    }


def access_token(secrets: dict) -> tuple[str, dict]:
    """Return a valid access token, refreshing if expired. Returns (token, updated_secrets)."""
    if time.time() < secrets.get("expires_at", 0) - 300:
        return secrets["access_token"], secrets
    new = refresh_token(secrets)
    return new["access_token"], new


def user_info(token: str) -> dict:
    """Get the TikTok user's display name and avatar."""
    r = request("GET", f"{API}/user/info/",
                params={"fields": "open_id,display_name,avatar_url"},
                headers={"Authorization": f"Bearer {token}"})
    data = (r.get("data") or {}).get("user") or {}
    return {
        "open_id": data.get("open_id", ""),
        "display_name": data.get("display_name", ""),
        "avatar_url": data.get("avatar_url", ""),
    }


# ---- Video Publishing (pull-from-URL method)

def publish_video(token: str, video_url: str, title: str, *,
                  privacy_level: str = "SELF_ONLY",
                  disable_duet: bool = False,
                  disable_stitch: bool = False,
                  disable_comment: bool = False,
                  on_progress=None) -> dict:
    """Upload a video to TikTok via URL pull (Content Posting API).

    privacy_level: SELF_ONLY | MUTUAL_FOLLOW_FRIENDS | FOLLOWER_OF_CREATOR | PUBLIC_TO_EVERYONE
    TikTok requires the creator to have the corresponding privacy setting enabled.

    Flow:
    1. POST /v2/post/publish/video/init/ → get publish_id
    2. TikTok pulls the video from video_url
    3. Poll /v2/post/publish/status/fetch/ until done
    """
    # Step 1: Initialize the publish
    init_body = {
        "post_info": {
            "title": title[:150],  # TikTok caption limit
            "privacy_level": privacy_level,
            "disable_duet": disable_duet,
            "disable_stitch": disable_stitch,
            "disable_comment": disable_comment,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "video_url": video_url,
        },
    }

    r = request("POST", f"{API}/post/publish/video/init/",
                data=init_body,
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json; charset=UTF-8"})
    err = r.get("error") or {}
    if isinstance(err, dict) and err.get("code") and err["code"] != "ok":
        raise PublishError(f"TikTok init failed: {err.get('message', err.get('code'))}")

    data = r.get("data") or {}
    publish_id = data.get("publish_id")
    if not publish_id:
        raise PublishError(f"TikTok publish_id not returned: {r}")

    if on_progress:
        on_progress(0.3)

    # Step 2: Poll for completion — TikTok fetches + processes the video
    for i in range(120):  # up to 10 minutes
        st = request("POST", f"{API}/post/publish/status/fetch/",
                     data={"publish_id": publish_id},
                     headers={"Authorization": f"Bearer {token}",
                              "Content-Type": "application/json; charset=UTF-8"})
        status_data = (st.get("data") or {})
        status = status_data.get("status")

        if on_progress:
            on_progress(min(0.9, 0.3 + i * 0.005))

        if status == "PUBLISH_COMPLETE":
            return {
                "remote_id": publish_id,
                "url": f"https://www.tiktok.com/@user/video/{publish_id}",
            }
        if status in ("FAILED",):
            fail_reason = status_data.get("fail_reason", "unknown")
            raise PublishError(f"TikTok processing failed: {fail_reason}")

        time.sleep(5)
    else:
        raise PublishError("TikTok processing timed out (10 min)", retry=True)
