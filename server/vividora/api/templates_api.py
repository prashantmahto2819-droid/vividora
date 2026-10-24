"""Template studio API — designs without a video, industry ad templates, trend research.

GET    /templates                         built-in + saved (filters: format, industry, mine=1)
POST   /templates                         {name, settings, format, industry, tags} → saved template
GET    /templates/{id}                    one (built-in ids too)
PATCH  /templates/{id}                    {name, settings, tags, industry}
DELETE /templates/{id}
POST   /templates/{id}/duplicate
POST   /templates/{id}/fill               {fields, variations?} → settings list (placeholders filled)
POST   /templates/{id}/bulk               {csv, fmt?} → zip of PNGs
POST   /templates/preview                 {settings, have} → layers pack (direct editing)
POST   /templates/render                  {settings, fmt: png|jpg} → image
POST   /templates/adapt                   {settings, to} → settings in the other format
POST   /templates/brand                   {settings, channel_id} → settings with the brand kit applied
POST   /templates/to-project              {settings, project_id} → PNG saved as a library image + overlay hint
GET    /trends/templates                  entries + report
POST   /trends/templates/refresh          {queries?} → collect
PATCH  /trends/templates/{id}             {status, note}
POST   /trends/templates/{id}/make        → original template saved
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from .. import db, service, storage, thumbs
from ..engine import templates as TP
from ..engine import thumbnail as T
from ..engine import trendtpl
from .deps import ApiError, body, ok, own_project, require


def _tags(v) -> list:
    """templates.tags is stored as a JSON string (the library table keeps a plain comma string in its own `tags`)."""
    if isinstance(v, list):
        return [str(x) for x in v]
    try:
        d = json.loads(v or "[]")
        return [str(x) for x in d] if isinstance(d, list) else []
    except ValueError:
        return [x.strip() for x in str(v).split(",") if x.strip()]


def _view(t: dict) -> dict:
    out = {k: t.get(k) for k in ("id", "name", "format", "industry", "tags", "fields", "defaults", "settings", "source", "created_at", "updated_at")}
    out["tags"] = _tags(t.get("tags"))
    out["builtin"] = bool(t.get("builtin"))
    if t.get("preview"):
        from ..security import media_token
        out["preview_url"] = f"/api/templates/{t['id']}/preview.png?t={media_token(t['id'])}"
    return out


def _get(tid: str, ws: str) -> dict | None:
    t = TP.builtin(tid)
    if t:
        return t
    row = db.get("templates", tid)
    if row and row["workspace_id"] == ws:
        return row
    return None


@require("viewer")
async def list_templates(request: Request, user: dict):
    q = request.query_params
    mine = db.rows(db.conn().execute("SELECT * FROM templates WHERE workspace_id = ? ORDER BY updated_at DESC", (user["workspace_id"],)))
    rows = [*mine, *([] if q.get("mine") == "1" else TP.BUILTIN)]
    if q.get("format"):
        rows = [r for r in rows if r.get("format") == q["format"]]
    if q.get("industry"):
        rows = [r for r in rows if r.get("industry") == q["industry"]]
    return ok({"templates": [_view(r) for r in rows], "formats": {k: {"w": v[0], "h": v[1], "label": v[2]} for k, v in T.FORMATS.items()},
               "industries": TP.INDUSTRIES, "fields": TP.FIELDS})


@require("editor")
async def create(request: Request, user: dict):
    data = await body(request)
    s = thumbs.clean_settings(data.get("settings") or {})
    row = {"id": db.new_id(), "workspace_id": user["workspace_id"], "name": str(data.get("name") or "नया template")[:80],
           "format": s.get("size") or "square", "industry": (data.get("industry") or None), "tags": json.dumps([str(t)[:30] for t in (data.get("tags") or [])][:12], ensure_ascii=False),
           "settings": s, "fields": data.get("fields") or [], "defaults": data.get("defaults") or {}, "preview": None,
           "source": data.get("source"), "created_by": user["id"], "created_at": db.now(), "updated_at": db.now()}
    with db.tx() as c:
        db.insert(c, "templates", row)
    await run_in_threadpool(_make_preview, row)
    return ok(_view(db.get("templates", row["id"])), 201)


def _make_preview(row: dict) -> None:
    try:
        png, _, _ = thumbs.render_design(row["workspace_id"], {**row["settings"], "size": row["settings"].get("size") or row["format"]}, "jpg")
        rel = str(Path(f"ws_{row['workspace_id']}") / "templates" / f"{row['id']}.jpg")
        storage.ensure_parent(rel).write_bytes(png)
        with db.tx() as c:
            db.update(c, "templates", row["id"], {"preview": rel})
    except Exception:  # noqa: BLE001
        pass


@require("viewer")
async def get_one(request: Request, user: dict):
    t = _get(request.path_params["tid"], user["workspace_id"])
    if not t:
        raise ApiError(404, "template नहीं मिला")
    return ok(_view(t))


async def preview_png(request: Request):
    """<img src> cannot send a bearer header: the short-lived ?t= media token (subject = template id) is the auth."""
    from ..security import read_token
    tid = request.path_params["tid"]
    data = read_token(request.query_params.get("t") or "", kind="media")
    if not data or data.get("sub") != tid:
        raise ApiError(401, "link expired")
    t = db.get("templates", tid)
    if not t or not t.get("preview"):
        raise ApiError(404, "preview नहीं")
    try:
        return Response(storage.abs_path(t["preview"]).read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=600"})
    except (ValueError, OSError):
        raise ApiError(404, "preview नहीं")


@require("editor")
async def patch(request: Request, user: dict):
    row = db.get("templates", request.path_params["tid"])
    if not row or row["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "built-in template नहीं बदल सकते — पहले copy बनाएँ" if TP.builtin(request.path_params["tid"]) else "template नहीं मिला")
    data = await body(request)
    ch = {"updated_at": db.now()}
    if data.get("name"):
        ch["name"] = str(data["name"])[:80]
    if isinstance(data.get("settings"), dict):
        ch["settings"] = thumbs.clean_settings(data["settings"])
        ch["format"] = ch["settings"].get("size") or row["format"]
    if "tags" in data:
        ch["tags"] = json.dumps([str(t)[:30] for t in (data.get("tags") or [])][:12], ensure_ascii=False)
    if "industry" in data:
        ch["industry"] = data.get("industry") or None
    for k in ("fields", "defaults"):
        if k in data:
            ch[k] = data[k]
    with db.tx() as c:
        db.update(c, "templates", row["id"], ch)
    row = db.get("templates", row["id"])
    if "settings" in ch:
        await run_in_threadpool(_make_preview, row)
        row = db.get("templates", row["id"])
    return ok(_view(row))


@require("editor")
async def delete(request: Request, user: dict):
    row = db.get("templates", request.path_params["tid"])
    if not row or row["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "template नहीं मिला")
    with db.tx() as c:
        c.execute("DELETE FROM templates WHERE id = ?", (row["id"],))
    if row.get("preview"):
        try:
            storage.abs_path(row["preview"]).unlink(missing_ok=True)
        except (ValueError, OSError):
            pass
    return ok()


@require("editor")
async def duplicate(request: Request, user: dict):
    t = _get(request.path_params["tid"], user["workspace_id"])
    if not t:
        raise ApiError(404, "template नहीं मिला")
    data = await body(request)
    row = {"id": db.new_id(), "workspace_id": user["workspace_id"], "name": str(data.get("name") or (t["name"] + " (copy)"))[:80],
           "format": t.get("format") or "square", "industry": t.get("industry"), "tags": json.dumps(_tags(t.get("tags")), ensure_ascii=False),
           "settings": thumbs.clean_settings(t.get("settings") or {}), "fields": list(t.get("fields") or []), "defaults": dict(t.get("defaults") or {}),
           "preview": None, "source": f"copy:{t['id']}", "created_by": user["id"], "created_at": db.now(), "updated_at": db.now()}
    with db.tx() as c:
        db.insert(c, "templates", row)
    await run_in_threadpool(_make_preview, row)
    return ok(_view(db.get("templates", row["id"])), 201)


@require("viewer")
async def fill(request: Request, user: dict):
    t = _get(request.path_params["tid"], user["workspace_id"])
    if not t:
        raise ApiError(404, "template नहीं मिला")
    data = await body(request)
    s = TP.fill(t, data.get("fields") or {})
    n = int(data.get("variations") or 0)
    out = [s] + (TP.variations(s, n, seed=t["id"]) if n else [])
    return ok({"settings": out})


@require("editor")
async def bulk(request: Request, user: dict):
    t = _get(request.path_params["tid"], user["workspace_id"])
    if not t:
        raise ApiError(404, "template नहीं मिला")
    data = await body(request)
    rows = TP.parse_csv(str(data.get("csv") or ""))
    if not rows:
        raise ApiError(422, "CSV खाली है — पहली पंक्ति में column के नाम (business, offer, phone…) चाहिए")
    fmt = "jpg" if data.get("fmt") == "jpg" else "png"
    to = data.get("to") if data.get("to") in T.FORMATS else None

    def work() -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for i, r in enumerate(rows[:100]):
                s = TP.fill(t, r)
                if to:
                    s = TP.adapt(s, to)
                png, _, _ = thumbs.render_design(user["workspace_id"], s, fmt)
                name = storage.safe_name((r.get("business") or r.get("name") or f"row{i + 1}")[:40], f"row{i + 1}")
                z.writestr(f"{i + 1:03d}_{name}.{fmt}", png)
        return buf.getvalue()
    out = await run_in_threadpool(work)
    return Response(out, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{t["id"]}_bulk.zip"'})


@require("viewer")
async def preview(request: Request, user: dict):
    data = await body(request)
    try:
        return ok(await run_in_threadpool(thumbs.design_layers, user["workspace_id"], data.get("settings") or {}, data.get("have") or []))
    except Exception as e:  # noqa: BLE001
        raise ApiError(500, f"design नहीं बना: {str(e)[-300:]}")


@require("viewer")
async def render(request: Request, user: dict):
    data = await body(request)
    fmt = "jpg" if data.get("fmt") == "jpg" else "png"
    try:
        png, _info, _w = await run_in_threadpool(thumbs.render_design, user["workspace_id"], data.get("settings") or {}, fmt)
    except Exception as e:  # noqa: BLE001
        raise ApiError(500, f"design नहीं बना: {str(e)[-300:]}")
    return Response(png, media_type="image/jpeg" if fmt == "jpg" else "image/png", headers={"Cache-Control": "no-store"})


@require("viewer")
async def adapt(request: Request, user: dict):
    data = await body(request)
    try:
        return ok({"settings": TP.adapt(thumbs.clean_settings(data.get("settings") or {}), str(data.get("to") or ""))})
    except ValueError:
        raise ApiError(422, "format गलत है")


@require("viewer")
async def brand_apply(request: Request, user: dict):
    from .channels import get_channel
    data = await body(request)
    ch = get_channel(user["workspace_id"], data.get("channel_id")) or {}
    br = ((ch.get("settings") or {}).get("brand") or {})
    return ok({"settings": TP.apply_brand(thumbs.clean_settings(data.get("settings") or {}), br, ch.get("handle")), "brand": br})


@require("editor")
async def to_project(request: Request, user: dict):
    """Render the design to a PNG in the library (kind image) and, when a project is given, add it as an overlay."""
    data = await body(request)
    s = thumbs.clean_settings(data.get("settings") or {})
    png, info, _w = await run_in_threadpool(thumbs.render_design, user["workspace_id"], s, "png")
    item_id = db.new_id()
    name = storage.safe_name(str(data.get("name") or "design")[:40], "design") + ".png"
    rel = str(Path(f"ws_{user['workspace_id']}") / "library" / "image" / f"{item_id[:8]}_{name}")
    storage.ensure_parent(rel).write_bytes(png)
    item = {"id": item_id, "workspace_id": user["workspace_id"], "kind": "image", "name": name, "path": rel, "size": len(png),
            "mime": "image/png", "meta": {"width": info["width"], "height": info["height"], "design": True}, "created_by": user["id"],
            "created_at": db.now(), "tags": "design", "source": "template", "license": "own", "channel_id": data.get("channel_id") or None}
    with db.tx() as c:
        db.insert(c, "library", item)
    added = None
    if data.get("project_id"):
        request.path_params["project_id"] = str(data["project_id"])
        p = own_project(request, user)
        st = dict(p.get("settings") or {})
        rs = dict(st.get("render") or service.DEFAULT_RENDER)
        fx = dict(rs.get("effects") or {})
        ov = list(fx.get("broll") or [])
        ov.append({"id": item_id, "start": float(data.get("start") or 0), "end": float(data.get("end") or 5), "track": 1,
                   "fit": "free", "x": 0.5, "y": 0.5, "scale": float(data.get("scale") or 0.6), "opacity": 1, "fade": True})
        fx["broll"] = ov
        rs["effects"] = fx
        st["render"] = rs
        with db.tx() as c:
            db.update(c, "projects", p["id"], {"settings": st, "updated_at": db.now()})
        added = {"project_id": p["id"], "overlay": ov[-1]}
    return ok({"library_id": item_id, "name": name, "added": added}, 201)


# ---------------------------------------------------------------- trend research
@require("viewer")
async def trends_list(request: Request, user: dict):
    rows = db.rows(db.conn().execute("SELECT * FROM trend_templates WHERE workspace_id = ? ORDER BY fetched_at DESC LIMIT 200", (user["workspace_id"],)))
    return ok({"entries": rows, "report": trendtpl.report(user["workspace_id"]), "statuses": list(trendtpl.STATUSES), "licence": trendtpl.LICENCE})


@require("editor")
async def trends_refresh(request: Request, user: dict):
    from .channels import get_channel
    from ..engine import radar
    data = await body(request)
    qs = [str(q)[:80] for q in (data.get("queries") or []) if str(q).strip()]
    if not qs:
        ch = get_channel(user["workspace_id"], data.get("channel_id")) or {}
        qs = radar.settings_of(ch.get("settings")).get("queries") or []
    res = await run_in_threadpool(trendtpl.collect, user["workspace_id"], qs)
    return ok(res)


@require("editor")
async def trends_patch(request: Request, user: dict):
    row = db.get("trend_templates", request.path_params["eid"])
    if not row or row["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "entry नहीं मिली")
    data = await body(request)
    ch = {}
    if data.get("status") in trendtpl.STATUSES:
        ch["status"] = data["status"]
    if "note" in data:
        ch["note"] = str(data.get("note") or "")[:500] or None
    with db.tx() as c:
        db.update(c, "trend_templates", row["id"], ch)
    return ok(db.get("trend_templates", row["id"]))


@require("editor")
async def trends_make(request: Request, user: dict):
    row = db.get("trend_templates", request.path_params["eid"])
    if not row or row["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "entry नहीं मिली")
    data = await body(request)
    t = trendtpl.original_template(row, data.get("name"))
    t["tags"] = json.dumps(t.get("tags") or [], ensure_ascii=False)
    rec = {"id": db.new_id(), "workspace_id": user["workspace_id"], **t, "preview": None, "created_by": user["id"],
           "created_at": db.now(), "updated_at": db.now()}
    with db.tx() as c:
        db.insert(c, "templates", rec)
        db.update(c, "trend_templates", row["id"], {"template_id": rec["id"], "status": "reviewed" if row["status"] == "draft" else row["status"]})
    await run_in_threadpool(_make_preview, rec)
    return ok(_view(db.get("templates", rec["id"])), 201)


routes = [
    Route("/templates", list_templates),
    Route("/templates", create, methods=["POST"]),
    Route("/templates/preview", preview, methods=["POST"]),
    Route("/templates/render", render, methods=["POST"]),
    Route("/templates/adapt", adapt, methods=["POST"]),
    Route("/templates/brand", brand_apply, methods=["POST"]),
    Route("/templates/to-project", to_project, methods=["POST"]),
    Route("/templates/{tid}", get_one),
    Route("/templates/{tid}", patch, methods=["PATCH"]),
    Route("/templates/{tid}", delete, methods=["DELETE"]),
    Route("/templates/{tid}/preview.png", preview_png),
    Route("/templates/{tid}/duplicate", duplicate, methods=["POST"]),
    Route("/templates/{tid}/fill", fill, methods=["POST"]),
    Route("/templates/{tid}/bulk", bulk, methods=["POST"]),
    Route("/trends/templates", trends_list),
    Route("/trends/templates/refresh", trends_refresh, methods=["POST"]),
    Route("/trends/templates/{eid}", trends_patch, methods=["PATCH"]),
    Route("/trends/templates/{eid}/make", trends_make, methods=["POST"]),
]
