"""YouTube Data API v3: OAuth (refresh-token) + resumable video upload.

Setup (once, free): Google Cloud project → enable "YouTube Data API v3" and
"YouTube Analytics API" →
OAuth consent screen (External, add your Google account as test user) →
Credentials → OAuth client ID (Web application) with redirect URI
  {PUBLIC_URL}/api/connect/youtube/callback
Put the client id/secret in .env as YT_CLIENT_ID / YT_CLIENT_SECRET.
Quota (Data API, 10 000 units/day per project):
  videos.insert               ~100 units (uploads have their own quota bucket since 2025)
  thumbnails.set                50
  playlistItems.insert          50
  commentThreads.insert         50
  videos.update (localizations) 50
  captions.insert              400   <- the expensive one
The YouTube Analytics API (yt-analytics.readonly) has its own, separate quota.

Scopes: youtube.upload + youtube.force-ssl (comments, captions, playlists,
localizations) + yt-analytics.readonly (retention / watch time) + youtube.readonly.
Channels connected before these scopes were added keep uploading fine; the
post-publish steps then fail with 403 insufficientPermissions and we only add
REAUTH_NOTE as a warning — never a failed upload.

The API cannot pin a comment or set an end screen; those go into the WhatsApp
checklist (see checklist()) for the creator to do by hand in Studio.
"""

from __future__ import annotations

import time
import urllib.parse
from pathlib import Path

from ..config import settings
from .http import PublishError, request, upload_file

_G = "https://www.googleapis.com/auth/"
SCOPE_UPLOAD = _G + "youtube.upload"
SCOPE_FORCE_SSL = _G + "youtube.force-ssl"
SCOPE_ANALYTICS = _G + "yt-analytics.readonly"
SCOPES = " ".join([SCOPE_UPLOAD, _G + "youtube.readonly", SCOPE_FORCE_SSL, SCOPE_ANALYTICS])
REAUTH_NOTE = "YouTube दोबारा connect करें ताकि comment/playlist/analytics चलें"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
CAPTIONS_UPLOAD = "https://www.googleapis.com/upload/youtube/v3/captions"

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
            "expires_at": time.time() + float(tok.get("expires_in", 3600)) - 60, "scope": tok.get("scope") or ""}


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
    if tok.get("scope"):
        new["scope"] = tok["scope"]
    return new["access_token"], new


def missing_scope(secrets: dict | None, scope: str) -> bool:
    """True only when we KNOW the grant lacks `scope`. Old connections stored no scope list →
    unknown → we just try the call and catch the 403."""
    granted = (secrets or {}).get("scope")
    return bool(granted) and scope not in str(granted).split()


def is_scope_error(e: Exception) -> bool:
    """403 insufficientPermissions / ACCESS_TOKEN_SCOPE_INSUFFICIENT = connection made with fewer scopes."""
    reason = (getattr(e, "reason", None) or "").lower()
    msg = str(e).lower()
    if getattr(e, "status", None) not in (401, 403):
        return False
    return "insufficient" in reason or "scope" in reason or ("insufficient" in msg and ("scope" in msg or "permission" in msg))


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


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
                 language: str | None = None, made_for_kids: bool = False, synthetic: bool = False,
                 on_progress=None) -> dict:
    """videos.insert (~100 units). `synthetic` → status.containsSyntheticMedia, YouTube's
    "altered or synthetic content" disclosure (realistic AI-made/altered people, places, events)."""
    status = {"privacyStatus": privacy if privacy in ("private", "unlisted", "public") else "private",
              "selfDeclaredMadeForKids": bool(made_for_kids), "containsSyntheticMedia": bool(synthetic)}
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
                           retry=e.code in (429, 500, 503), status=e.code) from None
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
        with urllib.request.urlopen(req, timeout=120) as r:
            r.read()
    except urllib.error.HTTPError as e:
        raise PublishError(f"thumbnail {e.code}: {e.read().decode(errors='replace')[:300]}") from None


# ---- after-upload steps (each needs youtube.force-ssl; each is best-effort and independent)
def add_to_playlist(token: str, playlist_id: str, video_id: str) -> dict:
    """playlistItems.insert — 50 units."""
    return request("POST", f"{API}/playlistItems", params={"part": "snippet"}, headers=_bearer(token),
                   data={"snippet": {"playlistId": playlist_id,
                                     "resourceId": {"kind": "youtube#video", "videoId": video_id}}})


def list_playlists(token: str) -> list[dict]:
    """playlists.list mine=true — 1 unit. For the playlist picker in the publish form."""
    r = request("GET", f"{API}/playlists", params={"part": "snippet", "mine": "true", "maxResults": "50"},
                headers=_bearer(token))
    return [{"id": it["id"], "title": (it.get("snippet") or {}).get("title", "")} for it in r.get("items") or []]


def post_comment(token: str, video_id: str, text: str) -> dict:
    """commentThreads.insert — 50 units. (Pinning is NOT possible through the API.)"""
    return request("POST", f"{API}/commentThreads", params={"part": "snippet"}, headers=_bearer(token),
                   data={"snippet": {"videoId": video_id,
                                     "topLevelComment": {"snippet": {"textOriginal": text[:10000]}}}})


def upload_captions(token: str, video_id: str, srt: str, *, language: str = "hi", name: str = "") -> dict:
    """captions.insert (multipart/related: JSON snippet + the SRT file) — 400 units."""
    import json
    import urllib.error
    import urllib.request
    boundary = f"vividora{int(time.time() * 1000)}"
    meta = {"snippet": {"videoId": video_id, "language": language, "name": name, "isDraft": False}}
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n"
            f"--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n").encode() + srt.encode("utf-8") + \
        f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(CAPTIONS_UPLOAD + "?uploadType=multipart&part=snippet", data=body, method="POST",
                                 headers={**_bearer(token), "Content-Type": f"multipart/related; boundary={boundary}",
                                          "Content-Length": str(len(body))})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            txt = r.read().decode()
            return json.loads(txt) if txt.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")[:1500]
        reason = None
        try:
            err = json.loads(raw).get("error", {})
            reason = ((err.get("errors") or [{}])[0].get("reason")) or err.get("status")
            raw = err.get("message") or raw
        except (ValueError, AttributeError):
            pass
        raise PublishError(f"{e.code}: {raw[:300]}", status=e.code, reason=reason,
                           retry=e.code in (429, 500, 502, 503, 504)) from None
    except urllib.error.URLError as e:
        raise PublishError(f"network: {e.reason}", retry=True) from None


def set_localizations(token: str, video_id: str, localizations: dict) -> dict:
    """videos.update part=localizations — 50 units. Needs snippet.defaultLanguage (set at upload).
    localizations: {"en": {"title": "...", "description": "..."}, ...}"""
    clean = {}
    for lang, v in (localizations or {}).items():
        if isinstance(v, dict) and (v.get("title") or v.get("description")):
            clean[str(lang)[:10]] = {"title": str(v.get("title") or "")[:100],
                                     "description": str(v.get("description") or "")[:5000]}
    if not clean:
        return {}
    return request("PUT", f"{API}/videos", params={"part": "localizations"}, headers=_bearer(token),
                   data={"id": video_id, "localizations": clean})


STEP_LABELS = {"playlist": "playlist", "comment": "first comment", "captions": "captions", "localizations": "localizations"}


def post_publish(token: str, video_id: str, secrets: dict | None, *, playlist_id: str | None = None,
                 first_comment: str | None = None, srt: str | None = None, language: str = "hi",
                 localizations: dict | None = None) -> dict:
    """Run every optional step independently. Returns {done: {step: id|True|False}, warnings, reauth}.
    Never raises — a failed comment must not turn a successful upload into a failed job.
    Cost if all run: 50 + 50 + 400 + 50 = 550 units."""
    steps = []
    if playlist_id:
        steps.append(("playlist", lambda: add_to_playlist(token, playlist_id, video_id)))
    if first_comment and first_comment.strip():
        steps.append(("comment", lambda: post_comment(token, video_id, first_comment.strip())))
    if srt and srt.strip():
        steps.append(("captions", lambda: upload_captions(token, video_id, srt, language=language)))
    if localizations:
        steps.append(("localizations", lambda: set_localizations(token, video_id, localizations)))
    done: dict = {}
    warnings: list[str] = []
    reauth = missing_scope(secrets, SCOPE_FORCE_SSL)
    for name, fn in steps:
        if reauth:  # we know (or just learned) the grant is too small — don't burn quota on more 403s
            done[name] = False
            continue
        try:
            r = fn() or {}
            done[name] = r.get("id") or True
        except PublishError as e:
            done[name] = False
            if is_scope_error(e):
                reauth = True
            else:
                warnings.append(f"{STEP_LABELS[name]}: {e}"[:300])
        except Exception as e:  # noqa: BLE001
            done[name] = False
            warnings.append(f"{STEP_LABELS[name]}: {e}"[:300])
    if reauth and steps:
        warnings.insert(0, REAUTH_NOTE)
    # None = "didn't find out" (nothing ran and no stored scope list) → leave the connection flag alone
    return {"done": done, "warnings": warnings, "reauth": reauth if (reauth or steps) else None}


def checklist(url: str, *, title: str = "", chain: dict | None = None, first_comment: str | None = None,
              video_id: str | None = None, warnings: list[str] | None = None) -> str:
    """WhatsApp message after a YouTube upload: what still needs a human in Studio
    (the API cannot pin comments or add end screens / cards)."""
    done = (chain or {}).get("done") or {}
    lines = [f"✅ अपलोड हो गया: {url}"]
    if title:
        lines.append(title)
    if done.get("comment"):
        lines.append("☐ comment pin करें (comment डल गया है)")
    else:
        fc = (first_comment or "").strip()
        lines.append("☐ comment डालें और pin करें" + (f": “{fc[:150]}”" if fc else ""))
    lines.append("☐ end screen लगाएँ (Studio → Editor → End screen)")
    lines.append("☐ cards जोड़ें (पुराना video / playlist)")
    if "playlist" in done:
        lines.append("✓ playlist में जुड़ा" if done["playlist"] else "☐ playlist में जोड़ें")
    if "captions" in done:
        lines.append("✓ captions upload हुए" if done["captions"] else "☐ captions (SRT) upload करें")
    if "localizations" in done:
        lines.append("✓ अनुवाद (localizations) जुड़े" if done["localizations"] else "☐ title/description अनुवाद जोड़ें")
    if video_id:
        lines.append(f"Studio: https://studio.youtube.com/video/{video_id}/edit")
    for w in (warnings or [])[:4]:
        lines.append(f"⚠️ {w[:160]}")
    return "\n".join(lines)
