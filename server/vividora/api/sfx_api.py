"""Auto SFX endpoint: POST /api/sfx/auto  (also /api/v1/auto-sfx for other software).

Body: {effects?: {...}, project_id?: str, duration?: seconds, cut_times?: [seconds], density?: low|normal|high, level?: 0.3-1.5}
With project_id the saved effects + cuts of that project are used; otherwise pass `effects` (+ `duration`).
Returns {sfx: [...all sfx items incl. the creator's own...], added: n}. Nothing is saved — the editor / your code decides."""

from __future__ import annotations

from starlette.requests import Request
from starlette.routing import Route

from .. import db
from ..engine import autosfx
from .deps import ApiError, body, ok, require


def _cut_times(project: dict) -> tuple[list[float], float]:
    """Joins between kept parts of the source, in OUTPUT seconds, and the output length."""
    from ..engine.autocut import keep_segments
    edl = project.get("edl") or {}
    dur = float((project.get("meta") or {}).get("duration") or edl.get("duration") or 0)
    if not edl.get("cuts"):
        return [], dur
    keep = keep_segments({"duration": dur, **edl})
    out, acc = [], 0.0
    for a, b in keep[:-1]:
        acc += b - a
        out.append(round(acc, 3))
    return out, sum(b - a for a, b in keep)


@require("editor")
async def auto(request: Request, user: dict):
    d = await body(request)
    cuts = [float(x) for x in (d.get("cut_times") or []) if isinstance(x, (int, float))][:500]
    effects = d.get("effects") if isinstance(d.get("effects"), dict) else {}
    out_dur = float(d.get("duration") or 0)
    pid = d.get("project_id")
    if pid:
        p = db.get("projects", str(pid))
        if not p or p["workspace_id"] != user["workspace_id"]:
            raise ApiError(404, "project नहीं मिला")
        cuts, out_dur = _cut_times(p)
        effects = effects or ((((p.get("settings") or {}).get("render")) or {}).get("effects") or {})
    if out_dur <= 1:
        raise ApiError(422, "duration (seconds) चाहिए")
    density = str(d.get("density") or "normal")
    if density not in autosfx.DENSITY:
        raise ApiError(422, "density: low | normal | high")
    level = max(0.3, min(1.5, float(d.get("level") or 1.0)))
    library = db.rows(db.conn().execute(
        "SELECT id, name, kind FROM library WHERE workspace_id = ? AND kind = 'sfx'", (user["workspace_id"],)))
    if not library:
        raise ApiError(409, "Library में कोई SFX नहीं — पहले Starter pack install करें")
    before = [s for s in effects.get("sfx") or [] if not str(s.get("_id", "")).startswith(autosfx.PREFIX)]
    res = autosfx.apply(effects, library, out_dur=out_dur, cut_times=cuts, density=density, level=level)
    return ok({"sfx": res["sfx"], "added": len(res["sfx"]) - len(before), "density": density})


routes = [Route("/sfx/auto", auto, methods=["POST"])]
