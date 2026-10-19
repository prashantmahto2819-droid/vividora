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
    publish_dry_run: bool = field(default_factory=lambda: _bool("PUBLISH_DRY_RUN"))


settings = Settings()
