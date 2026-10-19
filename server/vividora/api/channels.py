"""Channels: one workspace runs several brands/channels. Each channel owns its
brand kit, learned defaults, niche (for trends/ideas), platform connections,
library items and projects."""

from __future__ import annotations

from starlette.requests import Request
from starlette.routing import Route

from .. import db, service
from .deps import ApiError, body, need, ok, require

FIELDS = ("name", "handle", "niche", "language", "color")


def view(ch: dict) -> dict:
    st = ch.get("settings") or {}
    return {**{k: ch.get(k) for k in ("id", "name", "handle", "niche", "language", "color", "created_at")},
            "brand": st.get("brand", {}), "recommend": st.get("recommend", {}), "render_defaults": st.get("render_defaults", {}),
            "autopilot": st.get("autopilot", {}), "keywords": st.get("keywords", [])}


def get_channel(workspace_id: str, channel_id: str | None) -> dict | None:
    if channel_id:
        ch = db.get("channels", channel_id)
        if ch and ch["workspace_id"] == workspace_id:
            return ch
    return db.row(db.conn().execute("SELECT * FROM channels WHERE workspace_id = ? ORDER BY created_at LIMIT 1",
                                    (workspace_id,)).fetchone())


def channel_settings(workspace_id: str, channel_id: str | None) -> dict:
    ch = get_channel(workspace_id, channel_id)
    return (ch or {}).get("settings") or {}


@require("viewer")
async def list_channels(request: Request, user: dict):
    rows = db.rows(db.conn().execute("SELECT * FROM channels WHERE workspace_id = ? ORDER BY created_at", (user["workspace_id"],)))
    counts = {r["channel_id"]: r["n"] for r in db.rows(db.conn().execute(
        "SELECT channel_id, COUNT(*) AS n FROM projects WHERE workspace_id = ? GROUP BY channel_id", (user["workspace_id"],)))}
    conns = {}
    for r in db.rows(db.conn().execute("SELECT channel_id, platform FROM connections WHERE workspace_id = ?", (user["workspace_id"],))):
        conns.setdefault(r["channel_id"], []).append(r["platform"])
    return ok([{**view(ch), "projects": counts.get(ch["id"], 0), "platforms": conns.get(ch["id"], [])} for ch in rows])


@require("admin")
async def create_channel(request: Request, user: dict):
    data = await body(request)
    need(data, "name")
    ch = {"id": db.new_id(), "workspace_id": user["workspace_id"], "name": str(data["name"])[:80],
          "handle": (data.get("handle") or "")[:80] or None, "niche": (data.get("niche") or "")[:300] or None,
          "language": data.get("language") if data.get("language") in ("hi", "en", "auto") else "hi",
          "color": data.get("color") or "#F2B33D", "settings": {"brand": data.get("brand") or {}, "keywords": data.get("keywords") or []},
          "created_at": db.now(), "updated_at": db.now()}
    with db.tx() as c:
        db.insert(c, "channels", ch)
        service.log(c, user["workspace_id"], "channel.create", user_id=user["id"], detail={"name": ch["name"]})
    return ok(view(ch), 201)


def _own(request: Request, user: dict) -> dict:
    ch = db.get("channels", request.path_params["channel_id"])
    if not ch or ch["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "channel not found")
    return ch


@require("viewer")
async def get_one(request: Request, user: dict):
    return ok(view(_own(request, user)))


@require("admin")
async def update_channel(request: Request, user: dict):
    ch = _own(request, user)
    data = await body(request)
    changes = {k: (str(data[k])[:300] if data[k] is not None else None) for k in FIELDS if k in data}
    st = dict(ch.get("settings") or {})
    for k in ("brand", "autopilot", "render_defaults"):
        if isinstance(data.get(k), dict):
            st[k] = {**st.get(k, {}), **data[k]}
    if isinstance(data.get("keywords"), list):
        st["keywords"] = [str(x)[:60] for x in data["keywords"]][:30]
    changes["settings"] = st
    changes["updated_at"] = db.now()
    with db.tx() as c:
        db.update(c, "channels", ch["id"], changes)
        service.log(c, user["workspace_id"], "channel.update", user_id=user["id"], detail={"id": ch["id"], "fields": list(data)})
    return ok(view(db.get("channels", ch["id"])))


@require("admin")
async def delete_channel(request: Request, user: dict):
    ch = _own(request, user)
    n = db.conn().execute("SELECT COUNT(*) FROM channels WHERE workspace_id = ?", (user["workspace_id"],)).fetchone()[0]
    if n <= 1:
        raise ApiError(400, "आख़िरी channel नहीं हटा सकते")
    first = db.row(db.conn().execute("SELECT id FROM channels WHERE workspace_id = ? AND id != ? ORDER BY created_at LIMIT 1",
                                     (user["workspace_id"], ch["id"])).fetchone())
    with db.tx() as c:
        for t in ("projects", "connections", "ideas", "refs", "library"):
            c.execute(f"UPDATE {t} SET channel_id = ? WHERE channel_id = ?", (first["id"], ch["id"]))
        c.execute("DELETE FROM channels WHERE id = ?", (ch["id"],))
    return ok()


routes = [
    Route("/channels", list_channels),
    Route("/channels", create_channel, methods=["POST"]),
    Route("/channels/{channel_id}", get_one),
    Route("/channels/{channel_id}", update_channel, methods=["PATCH"]),
    Route("/channels/{channel_id}", delete_channel, methods=["DELETE"]),
]
