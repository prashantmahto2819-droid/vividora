"""Instagram Reels + Facebook Reels via the Graph API.

Setup (once): developers.facebook.com → create an app (Business) → add
"Facebook Login for Business" + "Instagram Graph API" products → in
Facebook Login settings add the redirect URI
  {PUBLIC_URL}/api/connect/meta/callback
Put the app id/secret in .env as META_APP_ID / META_APP_SECRET.
The Instagram account must be a Business/Creator account linked to a
Facebook Page you manage. Limits: Instagram 100 posts / 24 h, Facebook
Reels ~30 / 24 h. Both platforms download the video from a PUBLIC URL,
so Vividora serves finished renders at /pub/<signed token> (see api/publish.py).
"""

from __future__ import annotations

import time
import urllib.parse

from ..config import settings
from .http import PublishError, request

GRAPH = "https://graph.facebook.com/v21.0"
SCOPES = ("pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,"
          "instagram_content_publish,business_management")


def configured() -> bool:
    return bool(settings.meta_app_id and settings.meta_app_secret and settings.public_url)


def redirect_uri() -> str:
    return f"{settings.public_url}/api/connect/meta/callback"


def auth_url(state: str) -> str:
    q = {"client_id": settings.meta_app_id, "redirect_uri": redirect_uri(), "scope": SCOPES,
         "response_type": "code", "state": state}
    return "https://www.facebook.com/v21.0/dialog/oauth?" + urllib.parse.urlencode(q)


def exchange_code(code: str) -> dict:
    tok = request("GET", f"{GRAPH}/oauth/access_token",
                  params={"client_id": settings.meta_app_id, "client_secret": settings.meta_app_secret,
                          "redirect_uri": redirect_uri(), "code": code})
    long = request("GET", f"{GRAPH}/oauth/access_token",
                   params={"grant_type": "fb_exchange_token", "client_id": settings.meta_app_id,
                           "client_secret": settings.meta_app_secret, "fb_exchange_token": tok["access_token"]})
    return {"user_token": long["access_token"], "expires_at": time.time() + float(long.get("expires_in", 60 * 86400))}


def pages(user_token: str) -> list[dict]:
    """Pages the user manages, with the linked Instagram business account (if any)."""
    r = request("GET", f"{GRAPH}/me/accounts",
                params={"fields": "id,name,access_token,instagram_business_account{id,username}",
                        "access_token": user_token, "limit": 50})
    out = []
    for p in r.get("data", []):
        ig = p.get("instagram_business_account") or {}
        out.append({"page_id": p["id"], "page_name": p["name"], "page_token": p["access_token"],
                    "ig_id": ig.get("id"), "ig_username": ig.get("username")})
    return out


# ---- Instagram Reels
def ig_publish_reel(ig_id: str, page_token: str, video_url: str, caption: str, *, cover_url: str | None = None,
                    share_to_feed: bool = True, on_progress=None) -> dict:
    container = request("POST", f"{GRAPH}/{ig_id}/media",
                        params={"media_type": "REELS", "video_url": video_url, "caption": caption[:2200],
                                "share_to_feed": "true" if share_to_feed else "false",
                                "cover_url": cover_url, "access_token": page_token})
    cid = container.get("id")
    if not cid:
        raise PublishError(f"Instagram container नहीं बना: {container}")
    # Instagram fetches + transcodes the video; poll until FINISHED
    for i in range(90):
        st = request("GET", f"{GRAPH}/{cid}", params={"fields": "status_code,status", "access_token": page_token})
        code = st.get("status_code")
        if on_progress:
            on_progress(min(0.9, 0.2 + i * 0.01))
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise PublishError(f"Instagram processing failed: {st.get('status')}")
        time.sleep(5)
    else:
        raise PublishError("Instagram processing timed out", retry=True)
    pub = request("POST", f"{GRAPH}/{ig_id}/media_publish", params={"creation_id": cid, "access_token": page_token})
    mid = pub.get("id")
    if not mid:
        raise PublishError(f"Instagram publish failed: {pub}")
    link = request("GET", f"{GRAPH}/{mid}", params={"fields": "permalink", "access_token": page_token}).get("permalink")
    return {"remote_id": mid, "url": link or f"https://www.instagram.com/reel/{mid}"}


# ---- Facebook Reels (Pages)
def fb_publish_reel(page_id: str, page_token: str, video_url: str, description: str, *,
                    title: str | None = None, scheduled_at: int | None = None, on_progress=None) -> dict:
    start = request("POST", f"{GRAPH}/{page_id}/video_reels",
                    params={"upload_phase": "start", "access_token": page_token})
    vid = start.get("video_id")
    if not vid:
        raise PublishError(f"Facebook reel session नहीं बना: {start}")
    # hosted-file upload: Facebook pulls the file from our public URL
    import urllib.request
    req = urllib.request.Request(f"https://rupload.facebook.com/video-upload/v21.0/{vid}", method="POST",
                                 headers={"Authorization": f"OAuth {page_token}", "file_url": video_url})
    try:
        urllib.request.urlopen(req, timeout=120).read()
    except urllib.error.HTTPError as e:
        raise PublishError(f"Facebook upload {e.code}: {e.read().decode(errors='replace')[:300]}") from None
    if on_progress:
        on_progress(0.5)
    params = {"upload_phase": "finish", "video_id": vid, "description": description[:5000],
              "video_state": "SCHEDULED" if scheduled_at else "PUBLISHED", "access_token": page_token}
    if title:
        params["title"] = title[:100]
    if scheduled_at:
        params["scheduled_publish_time"] = scheduled_at
    fin = request("POST", f"{GRAPH}/{page_id}/video_reels", params=params)
    if not fin.get("success", True):
        raise PublishError(f"Facebook finish failed: {fin}")
    return {"remote_id": vid, "url": f"https://www.facebook.com/reel/{vid}"}


# ---- Facebook normal video (landscape long-form)
def fb_publish_video(page_id: str, page_token: str, video_url: str, description: str, *,
                     title: str | None = None, scheduled_at: int | None = None) -> dict:
    params = {"file_url": video_url, "description": description[:5000], "access_token": page_token}
    if title:
        params["title"] = title[:100]
    if scheduled_at:
        params.update(published="false", scheduled_publish_time=scheduled_at)
    r = request("POST", f"{GRAPH}/{page_id}/videos", params=params)
    vid = r.get("id")
    if not vid:
        raise PublishError(f"Facebook video failed: {r}")
    return {"remote_id": vid, "url": f"https://www.facebook.com/{page_id}/videos/{vid}"}
