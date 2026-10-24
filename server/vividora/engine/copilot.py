"""Channel Copilot engine: hook scores, weekly audits, comment reply drafts.

hook_score()     — first 3 seconds vs overall retention: did the hook grab?
weekly_audit()   — best/worst videos, hook distribution, posting-time analysis
comment_drafts() — AI-drafted replies for top comments
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone

from . import llm


# ---------------------------------------------------------------------------
# Hook score
# ---------------------------------------------------------------------------

def hook_score(video: dict) -> dict:
    """Score 0-100 for a single video based on its retention, CTR and velocity.

    Input `video` must contain:
      - yta.retention  (list of [fraction, relative_retention] pairs)
      - yta.metrics    (averageViewPercentage, impressionClickThroughRate, etc.)
      - views, published_at  (for velocity)

    Returns {"score": int, "breakdown": {...}, "verdict": str}.
    """
    yta = video.get("yta") or {}
    metrics = yta.get("metrics") or {}
    retention = yta.get("retention") or []

    # 1) Retention at ~3s vs ~30s (or average)
    ret_3s = _retention_at(retention, 0.05)  # ~first 3s of a 60s video = 5%
    ret_30s = _retention_at(retention, 0.50)
    avg_pct = float(metrics.get("averageViewPercentage") or 0)

    if ret_3s is not None and ret_30s is not None and ret_30s > 0:
        hook_ratio = ret_3s / max(ret_30s, 0.01)
    elif ret_3s is not None and avg_pct > 0:
        hook_ratio = (ret_3s * 100) / max(avg_pct, 1)
    else:
        hook_ratio = 1.0

    retention_score = min(40, max(0, int((hook_ratio - 0.5) * 80)))

    # 2) Click-through rate component (0-30)
    ctr = float(metrics.get("impressionClickThroughRate") or 0)
    ctr_score = min(30, max(0, int(ctr * 3)))  # 10% CTR = 30 points

    # 3) View velocity component (0-30)
    views = int(video.get("views") or 0)
    published = video.get("published_at") or ""
    velocity = _view_velocity(views, published)
    vel_score = min(30, max(0, int(velocity / 100)))  # 3000 views/day = 30

    total = min(100, retention_score + ctr_score + vel_score)

    if total >= 70:
        verdict = "Hook काम कर रहा है — दर्शक रुक रहे हैं"
    elif total >= 40:
        verdict = "ठीक-ठाक — hook में और दम चाहिए"
    else:
        verdict = "Hook कमज़ोर — पहले 3 सेकंड में लोग जा रहे हैं"

    return {
        "score": total,
        "breakdown": {
            "retention": retention_score,
            "ctr": ctr_score,
            "velocity": vel_score,
            "hook_ratio": round(hook_ratio, 2),
            "ctr_pct": round(ctr, 1),
            "views_per_day": int(velocity),
        },
        "verdict": verdict,
    }


def _retention_at(retention: list, fraction: float) -> float | None:
    """Interpolate the retention curve at a given fraction (0..1)."""
    if not retention:
        return None
    pts = [(p[0], p[1]) for p in retention if p and len(p) >= 2 and p[1] is not None]
    if not pts:
        return None
    # find closest
    best = min(pts, key=lambda p: abs(p[0] - fraction))
    if abs(best[0] - fraction) > 0.15:
        return None
    return float(best[1])


def _view_velocity(views: int, published_at: str) -> float:
    """Views per day since publication."""
    if not published_at or views <= 0:
        return 0.0
    try:
        pub = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        days = max(0.2, (datetime.now(timezone.utc) - pub).total_seconds() / 86400)
        return views / days
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Weekly audit
# ---------------------------------------------------------------------------

def weekly_audit(videos: list[dict], channel_name: str = "") -> dict:
    """Generate a weekly audit report from published video rows (with yta data).

    Returns a dict with: best, worst, hook_scores, posting_analysis,
    retention_patterns, suggestions.
    """
    if not videos:
        return {"summary": "इस हफ़्ते कोई video नहीं — audit के लिए published videos चाहिए।", "videos": 0}

    # Compute hook scores for all videos that have retention data
    scored = []
    for v in videos:
        hs = hook_score(v)
        scored.append({**v, "hook": hs})

    scored.sort(key=lambda v: v.get("views") or 0, reverse=True)

    best = scored[:3]
    worst = list(reversed(scored[-3:])) if len(scored) > 3 else []

    # Hook score distribution
    scores = [s["hook"]["score"] for s in scored]
    dist = {
        "avg": round(statistics.mean(scores)) if scores else 0,
        "median": round(statistics.median(scores)) if scores else 0,
        "green": sum(1 for s in scores if s >= 70),
        "yellow": sum(1 for s in scores if 40 <= s < 70),
        "red": sum(1 for s in scores if s < 40),
    }

    # Posting time analysis
    posting = _posting_analysis(videos)

    # Retention patterns
    retention_notes = _retention_patterns(scored)

    # Suggestions (LLM-powered if available, else heuristic)
    suggestions = _generate_suggestions(scored, dist, posting)

    return {
        "videos": len(scored),
        "channel": channel_name,
        "best": [_video_summary(v) for v in best],
        "worst": [_video_summary(v) for v in worst],
        "hook_distribution": dist,
        "posting": posting,
        "retention_notes": retention_notes,
        "suggestions": suggestions,
    }


def _video_summary(v: dict) -> dict:
    return {
        "title": v.get("title", ""),
        "views": v.get("views", 0),
        "likes": v.get("likes", 0),
        "hook_score": v["hook"]["score"],
        "hook_verdict": v["hook"]["verdict"],
        "url": v.get("url", ""),
        "published_at": v.get("published_at", ""),
    }


def _posting_analysis(videos: list[dict]) -> dict:
    """What days/hours get the most views?"""
    by_day: dict[int, list[int]] = {}
    by_hour: dict[int, list[int]] = {}
    day_names = ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]

    for v in videos:
        pub = v.get("published_at", "")
        if not pub:
            continue
        try:
            dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            views = int(v.get("views") or 0)
            by_day.setdefault(dt.weekday(), []).append(views)
            by_hour.setdefault(dt.hour, []).append(views)
        except (ValueError, TypeError):
            pass

    best_day = max(by_day, key=lambda d: statistics.mean(by_day[d])) if by_day else None
    best_hour = max(by_hour, key=lambda h: statistics.mean(by_hour[h])) if by_hour else None

    return {
        "best_day": day_names[best_day] if best_day is not None else None,
        "best_hour": f"{best_hour}:00" if best_hour is not None else None,
        "by_day": {day_names[d]: {"avg_views": int(statistics.mean(v)), "count": len(v)} for d, v in sorted(by_day.items())},
        "by_hour": {f"{h}:00": {"avg_views": int(statistics.mean(v)), "count": len(v)} for h, v in sorted(by_hour.items())},
    }


def _retention_patterns(scored: list[dict]) -> list[str]:
    """Plain-language notes about retention across the batch."""
    notes: list[str] = []
    good_hooks = [s for s in scored if s["hook"]["score"] >= 70]
    bad_hooks = [s for s in scored if s["hook"]["score"] < 40]

    if good_hooks:
        titles = ", ".join(f'"{s["title"][:30]}"' for s in good_hooks[:2])
        notes.append(f"अच्छे hooks: {titles} — इनकी शुरुआत दोहराएँ")
    if bad_hooks:
        titles = ", ".join(f'"{s["title"][:30]}"' for s in bad_hooks[:2])
        notes.append(f"कमज़ोर hooks: {titles} — पहले 3 सेकंड बदलें")

    # Average CTR
    ctrs = [s["hook"]["breakdown"]["ctr_pct"] for s in scored if s["hook"]["breakdown"]["ctr_pct"] > 0]
    if ctrs:
        avg_ctr = statistics.mean(ctrs)
        if avg_ctr < 4:
            notes.append(f"औसत CTR {avg_ctr:.1f}% — thumbnail और title में सुधार करें")
        elif avg_ctr > 8:
            notes.append(f"औसत CTR {avg_ctr:.1f}% — thumbnail बहुत अच्छे चल रहे हैं")

    return notes


def _generate_suggestions(scored: list[dict], dist: dict, posting: dict) -> list[str]:
    """Generate improvement suggestions. Uses LLM if available, else heuristics."""
    # Try LLM first
    if llm.available():
        prompt = (
            f"You are a YouTube growth coach for a Hindi content channel.\n"
            f"Hook score distribution: {dist['green']} good (70+), {dist['yellow']} average (40-69), {dist['red']} weak (<40).\n"
            f"Average hook score: {dist['avg']}. Best posting day: {posting.get('best_day')}. Best hour: {posting.get('best_hour')}.\n"
            f"Top videos: {', '.join(s['title'][:40] for s in scored[:3])}.\n\n"
            f"Give 4-5 specific, actionable suggestions in Hindi to improve the channel's hook game and overall performance.\n"
            f"Return JSON: {{\"suggestions\": [\"suggestion1\", \"suggestion2\", ...]}}"
        )
        result = llm.ask_json(prompt, system="YouTube growth expert. Reply in Hindi. JSON only.")
        if result and isinstance(result.get("suggestions"), list):
            return result["suggestions"][:5]

    # Heuristic fallback
    tips: list[str] = []
    if dist["red"] > dist["green"]:
        tips.append("ज़्यादातर hooks कमज़ोर हैं — पहले 3 सेकंड में सवाल या shocking fact डालें")
    if dist["avg"] < 50:
        tips.append("Hook score औसत से नीचे है — top videos की शुरुआत कॉपी करें")
    if posting.get("best_day"):
        tips.append(f"{posting['best_day']} को upload करें — इस दिन views सबसे ज़्यादा मिलते हैं")
    if posting.get("best_hour"):
        tips.append(f"{posting['best_hour']} के आसपास publish करें — audience इस समय active है")
    if not tips:
        tips.append("Hooks अच्छे चल रहे हैं — consistent रहें और नए formats try करें")
    return tips


# ---------------------------------------------------------------------------
# Comment reply drafts
# ---------------------------------------------------------------------------

def comment_drafts(video_title: str, comments: list[dict], channel_name: str = "") -> list[dict]:
    """Generate AI reply drafts for a list of comments.

    Each comment: {"id": str, "author": str, "text": str, "likes": int}.
    Returns: [{"comment_id": str, "draft": str}, ...].
    """
    if not comments:
        return []

    if not llm.available():
        # Simple template fallback
        return [{"comment_id": c["id"], "draft": _template_reply(c)} for c in comments[:10]]

    # Build the prompt
    comment_lines = "\n".join(
        f'{i+1}. [{c["id"]}] {c["author"]}: {c["text"][:200]}'
        for i, c in enumerate(comments[:10])
    )
    prompt = (
        f"Channel: {channel_name or 'Hindi motivational'}\n"
        f"Video: {video_title}\n\n"
        f"Top comments:\n{comment_lines}\n\n"
        f"Draft a friendly, engaging Hindi reply for each comment. Keep replies short (1-2 lines).\n"
        f"Match the commenter's energy. Use their name. Be genuine, not generic.\n"
        f"Return JSON: {{\"replies\": [{{\"comment_id\": \"...\", \"draft\": \"...\"}}, ...]}}"
    )
    result = llm.ask_json(prompt, system="You are a Hindi YouTube creator replying to fans. Be warm, real, motivational. JSON only.")
    if result and isinstance(result.get("replies"), list):
        return result["replies"][:10]

    return [{"comment_id": c["id"], "draft": _template_reply(c)} for c in comments[:10]]


def _template_reply(comment: dict) -> str:
    """Simple template reply when LLM is unavailable."""
    name = (comment.get("author") or "").split()[0] or "दोस्त"
    text = comment.get("text", "").lower()
    if any(w in text for w in ("धन्यवाद", "thank", "शुक्रिया", "great", "best")):
        return f"{name} जी, बहुत शुक्रिया! आपका साथ हमें और बेहतर बनाता है 🙏"
    if "?" in comment.get("text", ""):
        return f"{name} जी, बहुत अच्छा सवाल! अगले video में ज़रूर cover करेंगे 👍"
    return f"{name} जी, comment के लिए धन्यवाद! ऐसे ही जुड़े रहिए 🔥"
