"""Runtime settings, all read from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_root: Path = field(
        default_factory=lambda: Path(os.getenv("DATA_ROOT", "./data")).resolve()
    )
    database_path: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_PATH", str(Path(os.getenv("DATA_ROOT", "./data")) / "vividora.db")
        )
    )
    media_root: Path = field(
        default_factory=lambda: Path(os.getenv("MEDIA_ROOT", "./media")).resolve()
    )
    # big originals (uploads, library videos/music) can live on another disk, e.g. the Windows D: drive
    # shared into the VM; proxies, renders and the database stay on MEDIA_ROOT (fast VM disk)
    raw_root: Path | None = field(
        default_factory=lambda: Path(os.environ["RAW_ROOT"]).resolve()
        if os.getenv("RAW_ROOT")
        else None
    )
    archive_root: Path | None = field(
        default_factory=lambda: Path(os.environ["ARCHIVE_ROOT"]).resolve()
        if os.getenv("ARCHIVE_ROOT")
        else None
    )
    secret_key: str = field(default_factory=lambda: os.getenv("SECRET_KEY", "dev-only-change-me"))
    worker_token: str = field(default_factory=lambda: os.getenv("WORKER_TOKEN", "dev-worker-token"))
    admin_email: str = field(default_factory=lambda: os.getenv("ADMIN_EMAIL", "admin@vividora.local"))
    admin_password: str = field(default_factory=lambda: os.getenv("ADMIN_PASSWORD", "change-me-now"))
    admin_name: str = field(default_factory=lambda: os.getenv("ADMIN_NAME", "Admin"))
    access_token_hours: int = field(default_factory=lambda: int(os.getenv("ACCESS_TOKEN_HOURS", "72")))
    web_dist: Path = field(
        default_factory=lambda: Path(os.getenv("WEB_DIST", "./web-dist")).resolve()
    )
    presets_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("PRESETS_DIR", str(Path(__file__).resolve().parent.parent / "presets"))
        )
    )
    # A job that has not sent a heartbeat for this long is handed to another worker.
    job_stale_minutes: int = field(default_factory=lambda: int(os.getenv("JOB_STALE_MINUTES", "15")))
    max_job_attempts: int = field(default_factory=lambda: int(os.getenv("MAX_JOB_ATTEMPTS", "3")))
    # Raw files are moved to ARCHIVE_ROOT this many days after a project is approved.
    archive_after_days: int = field(default_factory=lambda: int(os.getenv("ARCHIVE_AFTER_DAYS", "30")))
    cors_origins: list[str] = field(
        default_factory=lambda: [o for o in os.getenv("CORS_ORIGINS", "").split(",") if o]
    )
    debug: bool = field(default_factory=lambda: _bool("DEBUG"))
    # Publishing. PUBLIC_URL is how Google/Meta reach us (your Cloudflare Tunnel hostname).
    public_url: str = field(default_factory=lambda: os.getenv("PUBLIC_URL", "").rstrip("/"))
    yt_client_id: str = field(default_factory=lambda: os.getenv("YT_CLIENT_ID", ""))
    yt_client_secret: str = field(default_factory=lambda: os.getenv("YT_CLIENT_SECRET", ""))
    meta_app_id: str = field(default_factory=lambda: os.getenv("META_APP_ID", ""))
    meta_app_secret: str = field(default_factory=lambda: os.getenv("META_APP_SECRET", ""))
    yt_api_key: str = field(default_factory=lambda: os.getenv("YT_API_KEY", ""))
    trend_region: str = field(default_factory=lambda: os.getenv("TREND_REGION", "IN"))
    watch_channels: list[str] = field(default_factory=lambda: [c.strip() for c in os.getenv("WATCH_CHANNELS", "").split(",") if c.strip()])
    # WhatsApp / webhook notifications (Vivid Relay or any HTTP gateway)
    notify_url: str = field(default_factory=lambda: os.getenv("NOTIFY_URL", ""))
    notify_token: str = field(default_factory=lambda: os.getenv("NOTIFY_TOKEN", ""))
    notify_to: str = field(default_factory=lambda: os.getenv("NOTIFY_TO", ""))
    notify_template: str = field(default_factory=lambda: os.getenv("NOTIFY_TEMPLATE", '{"to": "{to}", "message": "{text}"}'))
    notify_inbound_secret: str = field(default_factory=lambda: os.getenv("NOTIFY_INBOUND_SECRET", ""))
    publish_dry_run: bool = field(default_factory=lambda: _bool("PUBLISH_DRY_RUN"))
    # SaaS: signup, plans, quotas, Razorpay. Off by default — the self-hosted single workspace is unchanged.
    saas_mode: bool = field(default_factory=lambda: _bool("SAAS_MODE"))
    razorpay_key_id: str = field(default_factory=lambda: os.getenv("RAZORPAY_KEY_ID", ""))
    razorpay_key_secret: str = field(default_factory=lambda: os.getenv("RAZORPAY_KEY_SECRET", ""))
    razorpay_webhook_secret: str = field(default_factory=lambda: os.getenv("RAZORPAY_WEBHOOK_SECRET", ""))
    # Razorpay plan ids per Vividora plan + cycle, e.g. RAZORPAY_PLAN_creator_monthly=plan_xxx
    signup_open: bool = field(default_factory=lambda: _bool("SIGNUP_OPEN", True))
    invite_only: bool = field(default_factory=lambda: _bool("INVITE_ONLY"))
    require_email_verify: bool = field(default_factory=lambda: _bool("REQUIRE_EMAIL_VERIFY"))
    backup_keep_days: int = field(default_factory=lambda: int(os.getenv("BACKUP_KEEP_DAYS", "7")))
    # Freesound.org API key (https://freesound.org/apiv2 — free tier)
    freesound_api_key: str = field(default_factory=lambda: os.getenv("FREESOUND_API_KEY", ""))
    # Tenor GIF/sticker API key (https://developers.google.com/tenor — free, or GOOGLE_API_KEY)
    tenor_api_key: str = field(default_factory=lambda: os.getenv("TENOR_API_KEY", os.getenv("GOOGLE_API_KEY", "")))
    # the operator's (your) workspace id: sees every workspace in Admin; default = the first workspace created
    operator_workspace: str = field(default_factory=lambda: os.getenv("OPERATOR_WORKSPACE", ""))


settings = Settings()
