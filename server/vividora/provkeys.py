"""Keys of the outside services Vividora uses (Gemini, Pixabay, fal, Cloudflare, Google/Meta login, PUBLIC_URL…),
set from the dashboard instead of editing .env on the server.

A value saved here is stored encrypted (crypto.py, Fernet from SECRET_KEY) in `provider_keys`, and applied to
`os.environ` — every place that already reads the variable keeps working unchanged. A value from the dashboard wins over
.env; removing it brings the .env value back. The few variables that `config.settings` read at start are updated on the
settings object too. Workers get the ones they need with every job they claim (api/workers.claim → worker/client).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from . import crypto, db
from .config import settings

log = logging.getLogger("vividora.provkeys")

# env → (group, label, secret?, what it is for, where to get it)
CATALOG: list[dict[str, Any]] = [
    {"env": "PUBLIC_URL", "group": "site", "label": "Site का पता (PUBLIC_URL)", "secret": False,
     "use": "Google / Meta / TikTok login वापस इसी पते पर आता है; Instagram / Facebook वीडियो यहीं से लेते हैं",
     "link": "", "placeholder": "https://studio.yourdomain.com"},
    {"env": "APP_WINDOWS_URL", "group": "site", "label": "Windows app का download link", "secret": False,
     "use": "Home page और “सीखें” पर “Windows app” बटन इसी link पर जाता है (GitHub Releases की .exe फ़ाइल — docs/apps.md)", "link": "", "placeholder": "https://github.com/…/releases/latest/download/Vividora-Setup.exe"},
    {"env": "APP_ANDROID_URL", "group": "site", "label": "Android app (APK) का download link", "secret": False,
     "use": "Home page पर “Android APK” बटन इसी link पर जाता है (docs/apps.md)", "link": "", "placeholder": "https://github.com/…/releases/latest/download/Vividora.apk"},
    {"env": "GEMINI_API_KEY", "group": "ai", "label": "Google Gemini", "secret": True,
     "use": "script, titles, plan, visuals के prompt, documentary, copilot", "link": "https://aistudio.google.com/apikey"},
    {"env": "ANTHROPIC_API_KEY", "group": "ai", "label": "Anthropic (Claude)", "secret": True,
     "use": "Gemini की जगह / साथ में — वही काम", "link": "https://console.anthropic.com/settings/keys"},
    {"env": "CLOUDFLARE_ACCOUNT_ID", "group": "media_ai", "label": "Cloudflare Account ID", "secret": False,
     "use": "AI images (Workers AI) — token के साथ", "link": "https://dash.cloudflare.com/"},
    {"env": "CLOUDFLARE_API_TOKEN", "group": "media_ai", "label": "Cloudflare API token (Workers AI)", "secret": True,
     "use": "AI images — documentary, visuals, thumbnails", "link": "https://dash.cloudflare.com/profile/api-tokens"},
    {"env": "FAL_KEY", "group": "media_ai", "label": "fal.ai", "secret": True,
     "use": "AI video clips, तेज़ transcript, और AI आवाज़ें (Chatterbox / Kokoro हिन्दी) — सिर्फ़ इस्तेमाल के सेकंड का पैसा", "link": "https://fal.ai/dashboard/keys"},
    {"env": "ELEVENLABS_API_KEY", "group": "media_ai", "label": "ElevenLabs", "secret": True,
     "use": "AI voice-over (चुनने पर)", "link": "https://elevenlabs.io/app/settings/api-keys"},
    {"env": "PIXABAY_API_KEY", "group": "stock", "label": "Pixabay", "secret": True,
     "use": "free stock video / photo / music — B-roll, documentary, visuals", "link": "https://pixabay.com/api/docs/"},
    {"env": "JAMENDO_CLIENT_ID", "group": "stock", "label": "Jamendo (client id)", "secret": True,
     "use": "music search (non-monetised channel के लिए NC tracks भी)", "link": "https://devportal.jamendo.com/"},
    {"env": "FREESOUND_API_KEY", "group": "stock", "label": "Freesound", "secret": True,
     "use": "sound effects search", "link": "https://freesound.org/apiv2/apply"},
    {"env": "TENOR_API_KEY", "group": "stock", "label": "Tenor (GIF / sticker)", "secret": True,
     "use": "GIF stickers search", "link": "https://developers.google.com/tenor/guides/quickstart"},
    {"env": "YT_API_KEY", "group": "social", "label": "YouTube Data API key", "secret": True,
     "use": "Trends, channel watch, reference videos", "link": "https://console.cloud.google.com/apis/credentials"},
    {"env": "YT_CLIENT_ID", "group": "social", "label": "Google OAuth client ID", "secret": False,
     "use": "“+ YouTube” से channel जोड़ना (upload, analytics)", "link": "https://console.cloud.google.com/apis/credentials"},
    {"env": "YT_CLIENT_SECRET", "group": "social", "label": "Google OAuth client secret", "secret": True,
     "use": "ऊपर वाले client ID के साथ", "link": "https://console.cloud.google.com/apis/credentials"},
    {"env": "META_APP_ID", "group": "social", "label": "Meta app ID", "secret": False,
     "use": "“+ Instagram / Facebook” से जोड़ना", "link": "https://developers.facebook.com/apps/"},
    {"env": "META_APP_SECRET", "group": "social", "label": "Meta app secret", "secret": True,
     "use": "ऊपर वाले app ID के साथ", "link": "https://developers.facebook.com/apps/"},
    {"env": "TIKTOK_CLIENT_KEY", "group": "social", "label": "TikTok client key", "secret": False,
     "use": "“+ TikTok” से जोड़ना", "link": "https://developers.tiktok.com/apps/"},
    {"env": "TIKTOK_CLIENT_SECRET", "group": "social", "label": "TikTok client secret", "secret": True,
     "use": "ऊपर वाले client key के साथ", "link": "https://developers.tiktok.com/apps/"},
]
CATALOG += [
    {"env": "TRANSCRIBE_ENGINE", "group": "run", "label": "Transcript कहाँ बने", "secret": False,
     "choices": {"local": "यह server (Z440) — free, CPU पर धीमा", "fal": "fal.ai Whisper — सिर्फ़ काम के पैसे", "runpod": "RunPod serverless — सिर्फ़ काम के पैसे",
                 "auto": "Auto — छोटी recording यहीं, लंबी cloud पर"},
     "use": "cloud चुनने पर भी key न हो या cloud fail हो तो यह server ही बनाता है", "link": ""},
    {"env": "TRANSCRIBE_AUTO_MIN", "group": "run", "label": "Auto: कितने मिनट से लंबी recording cloud पर जाए", "secret": False, "number": [1, 240],
     "use": "खाली = 8 मिनट", "link": "", "placeholder": "8"},
    {"env": "SPEND_CAP_USD", "group": "run", "label": "महीने की खर्च-सीमा (USD)", "secret": False, "number": [0, 100000],
     "use": "इतना खर्च होते ही सारे paid काम (cloud transcript, fal.ai / RunPod / ElevenLabs की आवाज़ें, AI music, AI video) रुक जाते हैं। खाली = कोई सीमा नहीं, 0 = सब paid बंद", "link": "", "placeholder": "10"},
    {"env": "RUNPOD_API_KEY", "group": "run", "label": "RunPod API key", "secret": True,
     "use": "एक key से: RunPod की आवाज़ें (MiniMax HD, Chatterbox Turbo) और AI video (p-video) — कुछ set up नहीं करना, सिर्फ़ नतीजे का पैसा; "
            "और आपका अपना Whisper endpoint (नीचे)", "link": "https://www.runpod.io/console/user/settings"},
    {"env": "AI_VIDEO_PROVIDER", "group": "run", "label": "AI video clips कहाँ बनें", "secret": False,
     "choices": {"auto": "Auto — fal.ai हो तो वही, नहीं तो RunPod", "fal": "fal.ai (AI तस्वीर को हिलाता है)", "runpod": "RunPod p-video (बात से सीधा clip, ~$0.02/सेकंड)"},
     "use": "दोनों keys हों तब चुनें; जिसकी key नहीं उसका विकल्प काम नहीं करेगा", "link": ""},
    {"env": "SILENCE_ENGINE", "group": "run", "label": "चुप्पी कैसे पहचानें (auto-cut)", "secret": False,
     "choices": {"loudness": "आवाज़ की ऊँचाई से (पहले जैसा)", "silero": "Silero — इंसानी आवाज़ पहचानकर (शोर / पंखे / music में बेहतर)"},
     "use": "नई upload और “transcript दोबारा बनाएँ” पर लागू। model न चले तो अपने-आप पहले वाला तरीका", "link": ""},
    {"env": "WORD_ALIGN", "group": "run", "label": "शब्दों का सटीक समय (WhisperX)", "secret": False,
     "choices": {"off": "बंद (Whisper का अपना समय)", "whisperx": "WhisperX — हर शब्द आवाज़ से मिलाकर (worker में whisperx install होना चाहिए)"},
     "use": "karaoke captions और text से कट ज़्यादा सटीक। install न हो तो कुछ नहीं बदलता। देखें docs/whisperx.md", "link": ""},
    {"env": "CLIP_MATCH", "group": "run", "label": "Clips को तस्वीर देखकर मिलाना (OpenCLIP, इसी server पर)", "secret": False,
     "choices": {"off": "बंद", "on": "चालू — बिना बाहर के AI के (worker नहीं, API image में open_clip install होना चाहिए)"},
     "use": "Supporting clips को बात से मिलाने में मदद; Gemini की जगह नहीं लेता, उसके बाद चलता है। देखें docs/openclip.md", "link": ""},
    {"env": "RUNPOD_WHISPER_ENDPOINT", "group": "run", "label": "RunPod Whisper endpoint ID", "secret": False,
     "use": "RunPod → Serverless → “Faster Whisper” endpoint की ID (Min workers = 0 रखें)", "link": "https://www.runpod.io/console/serverless"},
]
GROUPS = {"run": "कहाँ चलाएँ · खर्च", "site": "Site", "ai": "AI (लिखना / सोचना)", "media_ai": "AI image · video · voice",
          "stock": "Stock video · photo · music · sound", "social": "YouTube · Instagram · TikTok"}
BY_ENV = {c["env"]: c for c in CATALOG}
# variables config.settings read once at start → kept in step
_SETTINGS = {"PUBLIC_URL": "public_url", "YT_CLIENT_ID": "yt_client_id", "YT_CLIENT_SECRET": "yt_client_secret",
             "META_APP_ID": "meta_app_id", "META_APP_SECRET": "meta_app_secret",
             "TIKTOK_CLIENT_KEY": "tiktok_client_key", "TIKTOK_CLIENT_SECRET": "tiktok_client_secret"}
# what a worker process uses itself (AI calls made while a job runs)
WORKER_ENVS = ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "FAL_KEY", "ELEVENLABS_API_KEY",
               "TRANSCRIBE_ENGINE", "TRANSCRIBE_AUTO_MIN", "RUNPOD_API_KEY", "RUNPOD_WHISPER_ENDPOINT", "AI_VIDEO_PROVIDER", "SILENCE_ENGINE", "WORD_ALIGN")

SCHEMA = """CREATE TABLE IF NOT EXISTS provider_keys (
  env TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL, updated_by TEXT);"""

_base: dict[str, str | None] = {}      # what .env / the container gave us, before the dashboard values


def _remember_base() -> None:
    for env in BY_ENV:
        if env not in _base:
            _base[env] = os.environ.get(env) or None


def _stored() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        rows = db.conn().execute("SELECT env, value FROM provider_keys").fetchall()
    except Exception:  # noqa: BLE001 — table not there yet (first start)
        return out
    for env, value in rows:
        if env not in BY_ENV:
            continue
        v = crypto.decrypt_json(value)
        if isinstance(v, dict) and isinstance(v.get("v"), str) and v["v"]:
            out[env] = v["v"]
    return out


def _put(env: str, value: str | None) -> None:
    if value:
        os.environ[env] = value
    else:
        os.environ.pop(env, None)
    attr = _SETTINGS.get(env)
    if attr:
        v = (value or "").rstrip("/") if env == "PUBLIC_URL" else (value or "")
        object.__setattr__(settings, attr, v)      # Settings is frozen: these few are meant to follow the dashboard


def apply() -> None:
    """Dashboard values → os.environ (+ settings). Call at start and after every change."""
    _remember_base()
    stored = _stored()
    for env in BY_ENV:
        _put(env, stored.get(env) or _base.get(env))


def init() -> None:
    with db.conn() as c:
        c.executescript(SCHEMA)
    apply()


def clean(env: str, value: Any) -> str:
    c = BY_ENV.get(env)
    if not c:
        raise ValueError("यह key list में नहीं है")
    v = str(value or "").strip().strip('"').strip("'")
    if not v:
        raise ValueError("value खाली है")
    if len(v) > 400 or any(ch in v for ch in "\n\r\t\0"):
        raise ValueError("value बहुत लंबी है या उसमें line break है")
    if c.get("choices"):
        if v not in c["choices"]:
            raise ValueError("इनमें से एक चुनें: " + " | ".join(c["choices"]))
        return v
    if c.get("number"):
        try:
            n = float(v)
        except ValueError:
            raise ValueError("संख्या लिखें") from None
        lo, hi = c["number"]
        if n != n or not (lo <= n <= hi):
            raise ValueError(f"{lo} से {hi} के बीच की संख्या लिखें")
        return str(int(n)) if n == int(n) else str(n)
    if env == "PUBLIC_URL":
        v = v.rstrip("/")
        if not (v.startswith("https://") or v.startswith("http://")) or " " in v or len(v) < 11:
            raise ValueError("पूरा पता लिखें, जैसे https://studio.yourdomain.com")
    elif " " in v:
        raise ValueError("key में खाली जगह (space) नहीं होती — पूरा copy करके दोबारा चिपकाएँ")
    return v


def set_key(env: str, value: Any, user_id: str | None = None) -> None:
    v = clean(env, value)
    with db.tx() as c:
        c.execute("INSERT INTO provider_keys (env, value, updated_at, updated_by) VALUES (?, ?, ?, ?) "
                  "ON CONFLICT(env) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at, updated_by = excluded.updated_by",
                  (env, crypto.encrypt_json({"v": v}), db.now(), user_id))
    apply()


def clear_key(env: str) -> None:
    if env not in BY_ENV:
        raise ValueError("यह key list में नहीं है")
    with db.tx() as c:
        c.execute("DELETE FROM provider_keys WHERE env = ?", (env,))
    apply()


def _mask(v: str) -> str:
    return ("•" * 6 + v[-4:]) if len(v) >= 12 else "•" * 6


def status() -> list[dict]:
    """For the dashboard: never the secret itself — only whether it is set, from where, and its last 4 characters."""
    _remember_base()
    stored = _stored()
    meta = {}
    try:
        meta = {r[0]: r[1] for r in db.conn().execute("SELECT env, updated_at FROM provider_keys").fetchall()}
    except Exception:  # noqa: BLE001
        pass
    out = []
    from .adminguide import HELP
    for c in CATALOG:
        env = c["env"]
        v = stored.get(env) or _base.get(env) or ""
        out.append({**c, "group_label": GROUPS[c["group"]], "set": bool(v), "help": [{"state": s_, "effect": e_} for s_, e_ in HELP.get(env, [])],
                    "source": "dashboard" if stored.get(env) else ("env" if v else ""),
                    "shown": (v if not c["secret"] else _mask(v)) if v else "",
                    "updated_at": meta.get(env) if stored.get(env) else None})
    return out


def worker_env() -> dict:
    """{"set": {env: value}, "unset": [env]} — only what the dashboard changed, only what a worker uses."""
    stored = _stored()
    return {"set": {e: stored[e] for e in WORKER_ENVS if stored.get(e)}, "unset": [e for e in WORKER_ENVS if not stored.get(e)]}
