"""System resource monitoring and guards for multi-user safety.

On a 64 GB / 12-core HP Z440 serving 4 simultaneous users, heavy jobs
(render, montage, matte, dub, transcribe) can spike to 2-3 GB RAM each.
This module prevents the server from running out of memory or disk space
by checking system resources before accepting new heavy work.

Usage:
    from . import sysguard
    sysguard.check_memory()       # raises if < MIN_FREE_GB
    sysguard.check_disk()         # raises if < MIN_DISK_FREE_GB
    sysguard.system_snapshot()    # full stats dict for /api/health
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import settings

log = logging.getLogger("vividora.sysguard")

# ---- thresholds (tuneable via env) ----

MIN_FREE_GB = float(os.getenv("SYSGUARD_MIN_FREE_GB", "3"))       # reject heavy jobs below this
WARN_FREE_GB = float(os.getenv("SYSGUARD_WARN_FREE_GB", "6"))     # log warning below this
MIN_DISK_FREE_GB = float(os.getenv("SYSGUARD_MIN_DISK_GB", "5"))  # reject render/prepare below this
MAX_CONCURRENT_HEAVY = int(os.getenv("SYSGUARD_MAX_HEAVY", "3"))   # max simultaneous heavy jobs


class ResourceError(Exception):
    """Raised when the system does not have enough resources."""
    no_retry = False  # the job can be retried later when resources free up

    def __init__(self, message: str, retry_after: int = 30):
        super().__init__(message)
        self.retry_after = retry_after


# ---- memory ----

def _mem_info() -> dict[str, float]:
    """Return memory info in GB. Uses /proc/meminfo (Linux) for accuracy."""
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    info[key] = int(parts[1])  # kB
        total = info.get("MemTotal", 0) / (1024 * 1024)
        # MemAvailable is the best estimate of how much memory is actually free
        available = info.get("MemAvailable", info.get("MemFree", 0)) / (1024 * 1024)
        return {"total_gb": round(total, 2), "available_gb": round(available, 2),
                "used_gb": round(total - available, 2),
                "percent_used": round((1 - available / total) * 100, 1) if total else 0}
    except (OSError, ValueError, ZeroDivisionError):
        # fallback: try psutil if available
        try:
            import psutil
            m = psutil.virtual_memory()
            return {"total_gb": round(m.total / (1024**3), 2),
                    "available_gb": round(m.available / (1024**3), 2),
                    "used_gb": round(m.used / (1024**3), 2),
                    "percent_used": round(m.percent, 1)}
        except ImportError:
            return {"total_gb": 0, "available_gb": 0, "used_gb": 0, "percent_used": 0}


def check_memory(threshold_gb: float | None = None) -> dict[str, float]:
    """Check if enough RAM is available. Raises ResourceError if below threshold."""
    mem = _mem_info()
    threshold = threshold_gb or MIN_FREE_GB
    if mem["available_gb"] < threshold:
        raise ResourceError(
            f"RAM कम है: {mem['available_gb']:.1f} GB free (min {threshold:.1f} GB) — "
            f"भारी काम queue में रहेगा",
            retry_after=60
        )
    if mem["available_gb"] < WARN_FREE_GB:
        log.warning("⚠ RAM low: %.1f GB free (warn at %.1f GB)", mem["available_gb"], WARN_FREE_GB)
    return mem


def memory_ok(threshold_gb: float | None = None) -> bool:
    """Non-raising version: True if enough RAM is available."""
    try:
        check_memory(threshold_gb)
        return True
    except ResourceError:
        return False


# ---- CPU ----

def _cpu_info() -> dict[str, Any]:
    """Return CPU load averages and count."""
    try:
        load1, load5, load15 = os.getloadavg()
        cores = os.cpu_count() or 1
        return {"load_1m": round(load1, 2), "load_5m": round(load5, 2),
                "load_15m": round(load15, 2), "cores": cores,
                "percent_1m": round(load1 / cores * 100, 1)}
    except OSError:
        return {"load_1m": 0, "load_5m": 0, "load_15m": 0, "cores": os.cpu_count() or 1, "percent_1m": 0}


# ---- disk ----

def _disk_info() -> dict[str, Any]:
    """Return disk usage for media_root (and raw_root if set)."""
    out: dict[str, Any] = {}
    for label, path in [("media", settings.media_root), ("raw", settings.raw_root)]:
        if path is None or not path.exists():
            continue
        try:
            du = shutil.disk_usage(path)
            out[label] = {"total_gb": round(du.total / (1024**3), 2),
                          "used_gb": round(du.used / (1024**3), 2),
                          "free_gb": round(du.free / (1024**3), 2),
                          "percent_used": round(du.used / du.total * 100, 1) if du.total else 0}
        except OSError:
            pass
    return out


def check_disk(threshold_gb: float | None = None) -> dict[str, Any]:
    """Check if enough disk space is available on media_root. Raises ResourceError if below threshold."""
    threshold = threshold_gb or MIN_DISK_FREE_GB
    try:
        du = shutil.disk_usage(settings.media_root)
        free_gb = du.free / (1024**3)
        if free_gb < threshold:
            raise ResourceError(
                f"Disk space कम है: {free_gb:.1f} GB free (min {threshold:.1f} GB) — "
                f"पुराने renders हटाएँ या disk बढ़ाएँ",
                retry_after=120
            )
        return {"free_gb": round(free_gb, 2), "total_gb": round(du.total / (1024**3), 2)}
    except OSError as e:
        log.warning("disk check failed: %s", e)
        return {"free_gb": 0, "total_gb": 0}


def disk_ok(threshold_gb: float | None = None) -> bool:
    """Non-raising version: True if enough disk space is available."""
    try:
        check_disk(threshold_gb)
        return True
    except ResourceError:
        return False


# ---- concurrent heavy job limiter ----

def heavy_job_count(c) -> int:
    """Count currently running heavy jobs."""
    row = c.execute(
        "SELECT COUNT(*) FROM jobs WHERE status = 'running' "
        "AND kind IN ('render', 'montage', 'matte', 'dub', 'transcribe', 'compress')"
    ).fetchone()
    return row[0] if row else 0


def check_heavy_slots(c) -> bool:
    """Return True if a new heavy job can be started."""
    return heavy_job_count(c) < MAX_CONCURRENT_HEAVY


# ---- full system snapshot (for /api/health) ----

_BOOT = time.monotonic()


def system_snapshot() -> dict[str, Any]:
    """Full system resource snapshot for the enhanced health endpoint."""
    from . import db
    c = db.conn()

    # job stats
    job_rows = c.execute(
        "SELECT status, COUNT(*) FROM jobs WHERE status IN ('queued', 'running') GROUP BY status"
    ).fetchall()
    jobs = {r[0]: r[1] for r in job_rows}

    # heavy breakdown
    heavy_rows = c.execute(
        "SELECT kind, COUNT(*) FROM jobs WHERE status = 'running' "
        "AND kind IN ('render', 'montage', 'matte', 'dub', 'transcribe', 'compress') "
        "GROUP BY kind"
    ).fetchall()
    heavy = {r[0]: r[1] for r in heavy_rows}

    # workers
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(timespec="seconds")
    worker_rows = c.execute(
        "SELECT name, kinds, last_seen_at FROM workers WHERE last_seen_at > ?", (cutoff,)
    ).fetchall()
    workers_online = len(worker_rows)

    # active workspaces
    active_ws = c.execute(
        "SELECT COUNT(DISTINCT p.workspace_id) FROM jobs j JOIN projects p ON p.id = j.project_id "
        "WHERE j.status = 'running'"
    ).fetchone()

    return {
        "memory": _mem_info(),
        "cpu": _cpu_info(),
        "disk": _disk_info(),
        "jobs": {
            "queued": jobs.get("queued", 0),
            "running": jobs.get("running", 0),
            "heavy_running": heavy,
            "heavy_total": sum(heavy.values()),
            "heavy_max": MAX_CONCURRENT_HEAVY,
        },
        "workers_online": workers_online,
        "active_workspaces": active_ws[0] if active_ws else 0,
        "thresholds": {
            "min_free_ram_gb": MIN_FREE_GB,
            "warn_free_ram_gb": WARN_FREE_GB,
            "min_free_disk_gb": MIN_DISK_FREE_GB,
            "max_concurrent_heavy": MAX_CONCURRENT_HEAVY,
        },
        "uptime_seconds": round(time.monotonic() - _BOOT),
    }


# ---- pre-job guard (called before claiming heavy jobs) ----

def pre_job_check(c, kind: str) -> str | None:
    """Run resource checks before a heavy job is claimed.
    Returns None if OK, or an error message if the job should not be claimed now."""
    from .queue import HEAVY
    if kind not in HEAVY:
        return None  # quick jobs always allowed

    # check concurrent heavy limit
    if not check_heavy_slots(c):
        return (f"भारी काम limit ({MAX_CONCURRENT_HEAVY}) पर है — "
                f"चालू काम: {heavy_job_count(c)}")

    # check memory
    mem = _mem_info()
    if mem["available_gb"] < MIN_FREE_GB:
        return (f"RAM कम है: {mem['available_gb']:.1f} GB free "
                f"(min {MIN_FREE_GB:.1f} GB)")

    # check disk for render/montage/prepare
    if kind in ("render", "montage", "prepare"):
        try:
            check_disk()
        except ResourceError as e:
            return str(e)

    return None
