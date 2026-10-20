"""Posting schedule: when each finished video goes out, per channel and platform.

Each channel keeps weekly posting slots per platform (local time). Autopilot
puts every approved output into the next free slot:
  * the long video first (YouTube slot),
  * Shorts after it, `short_gap_hours` apart (and never two in one slot),
  * Instagram / Facebook versions after the YouTube Short, `cross_gap_hours` later.
YouTube and Facebook are scheduled natively (publishAt / scheduled_publish_time);
Instagram's API cannot schedule, so its job simply waits in our queue until the time.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DEFAULT = {
    "auto": True,                 # autopilot fills times in the publish plan
    "timezone": "Asia/Kolkata",
    "slots": {                    # local times; days = which weekdays
        "youtube_long": [{"days": DAYS, "time": "18:30"}],
        "youtube_short": [{"days": DAYS, "time": "12:30"}, {"days": DAYS, "time": "20:30"}],
        "instagram": [{"days": DAYS, "time": "19:00"}, {"days": DAYS, "time": "13:00"}],
        "facebook": [{"days": DAYS, "time": "19:30"}],
    },
    "short_gap_hours": 4,         # between two Shorts of the same video
    "cross_gap_hours": 1,         # YouTube Short → IG / FB of the same clip
    "min_lead_minutes": 20,       # never schedule closer than this to "now"
    "max_per_day": {"youtube_long": 1, "youtube_short": 3, "instagram": 2, "facebook": 2},
}


def settings_of(channel_settings: dict | None) -> dict:
    s = dict(DEFAULT)
    user = (channel_settings or {}).get("schedule") or {}
    for k, v in user.items():
        if k == "slots" and isinstance(v, dict):
            s["slots"] = {**DEFAULT["slots"], **v}
        elif k == "max_per_day" and isinstance(v, dict):
            s["max_per_day"] = {**DEFAULT["max_per_day"], **v}
        elif k in DEFAULT:
            s[k] = v
    return s


def _tz(name: str):
    if ZoneInfo:
        try:
            return ZoneInfo(name)
        except Exception:  # noqa: BLE001
            pass
    return timezone(timedelta(hours=5, minutes=30))


def lane(platform: str, label: str) -> str:
    if platform == "youtube":
        return "youtube_long" if label == "yt-long" else "youtube_short"
    return platform


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except (TypeError, ValueError):
            return None


def candidates(s: dict, ln: str, after: datetime, days_ahead: int = 21):
    tz = _tz(s.get("timezone") or "Asia/Kolkata")
    loc = after.astimezone(tz)
    slots = s["slots"].get(ln) or []
    for d in range(days_ahead + 1):
        day = (loc + timedelta(days=d)).date()
        dname = DAYS[day.weekday()]
        times = []
        for sl in slots:
            if dname not in (sl.get("days") or DAYS):
                continue
            try:
                hh, mm = (int(x) for x in str(sl.get("time", "18:00")).split(":")[:2])
            except ValueError:
                continue
            times.append(datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz))
        for t in sorted(times):
            if t > after:
                yield t.astimezone(timezone.utc)


def next_free(s: dict, ln: str, after: datetime, taken: list[datetime]) -> datetime:
    limit = int((s.get("max_per_day") or {}).get(ln, 99))
    tz = _tz(s.get("timezone") or "Asia/Kolkata")
    for t in candidates(s, ln, after):
        if any(abs((t - x).total_seconds()) < 1800 for x in taken):
            continue
        day = t.astimezone(tz).date()
        if sum(1 for x in taken if x.astimezone(tz).date() == day) >= limit:
            continue
        return t
    return after + timedelta(hours=1)  # no slots configured → soon


def assign(items: list[dict], s: dict, *, now: datetime | None = None, booked: dict[str, list[datetime]] | None = None) -> list[dict]:
    """Fill `when` (UTC ISO) for every publish-plan item. booked = already scheduled times per lane."""
    now = now or datetime.now(timezone.utc)
    start = now + timedelta(minutes=int(s.get("min_lead_minutes", 20)))
    taken: dict[str, list[datetime]] = {k: list(v) for k, v in (booked or {}).items()}
    order = {"yt-long": 0}
    items = sorted(items, key=lambda it: (order.get(it.get("label"), 1), 0 if it.get("platform") == "youtube" else 1, it.get("label", "")))
    yt_short_time: dict[str, datetime] = {}
    last_short: datetime | None = None
    long_at: datetime | None = None
    for it in items:
        if not it.get("selected", True):
            continue
        ln = lane(it["platform"], it.get("label", ""))
        after = start
        if ln == "youtube_short":
            if long_at:
                after = max(after, long_at + timedelta(hours=1))
            if last_short:
                after = max(after, last_short + timedelta(hours=float(s.get("short_gap_hours", 4))))
        elif ln in ("instagram", "facebook"):
            ref = yt_short_time.get(it.get("label", "")) or last_short or long_at
            if ref:
                after = max(after, ref + timedelta(hours=float(s.get("cross_gap_hours", 1))))
        t = next_free(s, ln, after, taken.get(ln, []))
        taken.setdefault(ln, []).append(t)
        it["when"] = t.isoformat().replace("+00:00", "Z")
        if ln == "youtube_long":
            long_at = t
        elif ln == "youtube_short":
            last_short = t
            yt_short_time[it.get("label", "")] = t
    return items


def best_slots(stats: list[dict], tz_name: str = "Asia/Kolkata", top: int = 2) -> list[dict]:
    """From own published videos: which posting hours got the most views per day (needs ≥ 6 videos)."""
    tz = _tz(tz_name)
    buckets: dict[int, list[float]] = {}
    now = datetime.now(timezone.utc)
    for v in stats:
        t = _parse(v.get("published"))
        views = float(v.get("views") or 0)
        if not t:
            continue
        age = max(1.0, (now - t).total_seconds() / 86400)
        buckets.setdefault(t.astimezone(tz).hour, []).append(views / age)
    if sum(len(x) for x in buckets.values()) < 6:
        return []
    avg = sorted(((sum(v) / len(v), h, len(v)) for h, v in buckets.items()), reverse=True)
    return [{"time": f"{h:02d}:00", "views_per_day": round(a, 1), "videos": n} for a, h, n in avg[:top]]
