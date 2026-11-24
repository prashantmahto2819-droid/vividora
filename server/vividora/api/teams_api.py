"""Teams: groups of users inside a workspace. A team has its own Library folder that its members (and its leader) share.

GET    /teams              the teams I can see (admin: all), each with members; plus `scopes` = where I may put Library items
POST   /teams              {name, leader_id?, members: [user ids]}          admin
PATCH  /teams/{id}         {name?, leader_id?, members?}                    admin, or the team's leader (members only)
DELETE /teams/{id}         its Library items become shared with everyone     admin

Library scopes (library.scope): 'ws' shared with the whole workspace · 'user:<id>' personal · 'team:<id>' that team.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.routing import Route

from .. import db, service
from .deps import ApiError, body, ok, require


def my_team_ids(user: dict) -> list[str]:
    rows = db.conn().execute(
        "SELECT t.id FROM teams t LEFT JOIN team_members m ON m.team_id = t.id AND m.user_id = ? "
        "WHERE t.workspace_id = ? AND (m.user_id IS NOT NULL OR t.leader_id = ?)", (user["id"], user["workspace_id"], user["id"])).fetchall()
    return [r[0] for r in rows]


def visible_scopes(user: dict) -> list[str]:
    """Library scopes this user sees: shared, their own folder, their teams. An admin also sees every team (never
    another person's personal folder)."""
    if user.get("role") == "admin":
        teams = [r[0] for r in db.conn().execute("SELECT id FROM teams WHERE workspace_id = ?", (user["workspace_id"],)).fetchall()]
    else:
        teams = my_team_ids(user)
    return ["ws", f"user:{user['id']}", *[f"team:{t}" for t in teams]]


def check_scope(user: dict, scope: str | None) -> str:
    """The scope a new / moved item may get: 'me' → the caller's own folder. Raises 403 for a scope that is not theirs."""
    scope = (scope or "ws").strip()
    if scope in ("me", "mine", "user"):
        scope = f"user:{user['id']}"
    if scope not in visible_scopes(user):
        raise ApiError(403, "यह folder आपका नहीं है — साझा, अपना, या अपनी team का folder चुनें")
    return scope


def _team(request: Request, user: dict) -> dict:
    t = db.get("teams", request.path_params["team_id"])
    if not t or t["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "team नहीं मिली")
    return t


def _users(ws: str) -> dict:
    return {r[0]: {"id": r[0], "name": r[1], "role": r[2]} for r in
            db.conn().execute("SELECT id, name, role FROM users WHERE workspace_id = ?", (ws,)).fetchall()}


def _view(t: dict, users: dict) -> dict:
    ids = [r[0] for r in db.conn().execute("SELECT user_id FROM team_members WHERE team_id = ?", (t["id"],)).fetchall()]
    n = db.conn().execute("SELECT COUNT(*) FROM library WHERE scope = ?", (f"team:{t['id']}",)).fetchone()[0]
    return {"id": t["id"], "name": t["name"], "leader_id": t.get("leader_id"), "leader": (users.get(t.get("leader_id")) or {}).get("name"),
            "members": [users[i] for i in ids if i in users], "items": n}


@require("viewer")
async def list_teams(request: Request, user: dict):
    users = _users(user["workspace_id"])
    mine = set(my_team_ids(user))
    rows = db.rows(db.conn().execute("SELECT * FROM teams WHERE workspace_id = ? ORDER BY name", (user["workspace_id"],)))
    teams = [_view(t, users) for t in rows if user["role"] == "admin" or t["id"] in mine]
    scopes = [{"id": "ws", "label": "साझा — सबके लिए"}, {"id": f"user:{user['id']}", "label": "🔒 मेरा folder"},
              *[{"id": f"team:{t['id']}", "label": "👥 " + t["name"]} for t in teams]]
    return ok({"teams": teams, "scopes": scopes, "can_manage": user["role"] == "admin",
               "users": sorted(users.values(), key=lambda u: u["name"].lower()) if user["role"] == "admin" else []})


def _set_members(c, team_id: str, ids, users: dict) -> None:
    keep = [i for i in dict.fromkeys(str(x) for x in (ids or [])) if i in users][:500]
    c.execute("DELETE FROM team_members WHERE team_id = ?", (team_id,))
    for i in keep:
        c.execute("INSERT INTO team_members (team_id, user_id) VALUES (?, ?)", (team_id, i))


@require("admin")
async def create_team(request: Request, user: dict):
    d = await body(request)
    name = str(d.get("name") or "").strip()[:60]
    if not name:
        raise ApiError(422, "team का नाम लिखें")
    users = _users(user["workspace_id"])
    leader = str(d.get("leader_id") or "") or None
    if leader and leader not in users:
        raise ApiError(422, "leader इस workspace का user होना चाहिए")
    t = {"id": db.new_id(), "workspace_id": user["workspace_id"], "name": name, "leader_id": leader, "created_by": user["id"], "created_at": db.now()}
    with db.tx() as c:
        db.insert(c, "teams", t)
        _set_members(c, t["id"], d.get("members"), users)
        service.log(c, user["workspace_id"], "team.create", user_id=user["id"], detail={"name": name})
    return ok(_view(t, users), status=201)


@require("editor")
async def update_team(request: Request, user: dict):
    t = _team(request, user)
    admin = user["role"] == "admin"
    if not admin and t.get("leader_id") != user["id"]:
        raise ApiError(403, "सिर्फ़ admin या इस team का leader बदल सकता है")
    d = await body(request)
    users = _users(user["workspace_id"])
    changes = {}
    if admin and d.get("name"):
        changes["name"] = str(d["name"]).strip()[:60]
    if admin and "leader_id" in d:
        leader = str(d.get("leader_id") or "") or None
        if leader and leader not in users:
            raise ApiError(422, "leader इस workspace का user होना चाहिए")
        changes["leader_id"] = leader
    with db.tx() as c:
        if changes:
            db.update(c, "teams", t["id"], changes)
        if isinstance(d.get("members"), list):
            _set_members(c, t["id"], d["members"], users)
    return ok(_view(db.get("teams", t["id"]), users))


@require("admin")
async def delete_team(request: Request, user: dict):
    t = _team(request, user)
    with db.tx() as c:
        c.execute("UPDATE library SET scope = 'ws' WHERE scope = ?", (f"team:{t['id']}",))     # nothing is lost with the team
        c.execute("DELETE FROM team_members WHERE team_id = ?", (t["id"],))
        c.execute("DELETE FROM teams WHERE id = ?", (t["id"],))
    return ok()


routes = [Route("/teams", list_teams), Route("/teams", create_team, methods=["POST"]),
          Route("/teams/{team_id}", update_team, methods=["PATCH"]), Route("/teams/{team_id}", delete_team, methods=["DELETE"])]
