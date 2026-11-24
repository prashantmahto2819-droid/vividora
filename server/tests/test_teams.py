"""Library folders: shared / personal / team (api/teams_api.py + library.scope). Run: python3 tests/test_teams.py"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="vividora-teams-")
os.environ.update({"DATA_ROOT": TMP, "DATABASE_PATH": str(Path(TMP) / "t.db"), "MEDIA_ROOT": str(Path(TMP) / "m"), "ADMIN_PASSWORD": "test-pass-123",
                   "SECRET_KEY": "unit-test-secret-key-that-is-long-enough-0123456789", "WEB_DIST": str(Path(TMP) / "nope"),
                   "WORKER_TOKEN": "unit-test-worker-token-0123456789-abcdefghij"})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient  # noqa: E402

from vividora.app import create_app  # noqa: E402

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
       b"\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82")


def main() -> None:
    with TestClient(create_app()) as c:
        def login(email, pw):
            return {"authorization": "Bearer " + c.post("/api/auth/login", json={"email": email, "password": pw}).json()["token"]}
        admin = login("admin@vividora.local", "test-pass-123")

        def mk(name, email, role="editor"):
            r = c.post("/api/users", headers=admin, json={"name": name, "email": email, "password": "Pass-word-123", "role": role})
            assert r.status_code < 300, r.text
            return r.json()["id"], login(email, "Pass-word-123")
        ravi_id, ravi = mk("Ravi", "ravi@example.com")
        sita_id, sita = mk("Sita", "sita@example.com")
        amit_id, amit = mk("Amit", "amit@example.com")

        def up(h, name, scope=None):
            r = c.put(f"/api/library?kind=image&filename={name}" + (f"&scope={scope}" if scope else ""), headers={**h, "content-type": "application/octet-stream"}, content=PNG)
            return r
        def names(h, q=""):
            return sorted(x["name"] for x in c.get("/api/library?kind=image" + q, headers=h).json() if x.get("source") != "starter")

        # a team: Ravi leads, Sita is a member, Amit is outside
        r = c.post("/api/teams", headers=ravi, json={"name": "x"})
        assert r.status_code == 403, "only an admin creates teams"
        team = c.post("/api/teams", headers=admin, json={"name": "Editing team", "leader_id": ravi_id, "members": [sita_id]}).json()
        tid = team["id"]
        assert team["leader"] == "Ravi" and [m["name"] for m in team["members"]] == ["Sita"]

        assert up(admin, "shared.png").status_code < 300                       # default: shared with everyone
        assert up(ravi, "ravi_private.png", "me").status_code < 300
        assert up(sita, "team_logo.png", f"team:{tid}").status_code < 300
        assert up(amit, "sneaky.png", f"team:{tid}").status_code == 403, "not a member → cannot put files into the team folder"
        assert up(amit, "sneaky.png", f"user:{ravi_id}").status_code == 403

        assert names(ravi) == ["ravi_private.png", "shared.png", "team_logo.png"]
        assert names(sita) == ["shared.png", "team_logo.png"]
        assert names(amit) == ["shared.png"]
        assert names(admin) == ["shared.png", "team_logo.png"], "an admin sees every team, never a personal folder"
        assert names(ravi, "&scope=me") == ["ravi_private.png"] and names(ravi, f"&scope=team:{tid}") == ["team_logo.png"] and names(ravi, "&scope=ws") == ["shared.png"]
        assert names(amit, f"&scope=team:{tid}") == []

        # the folders the upload box offers
        sc = [s["id"] for s in c.get("/api/teams", headers=sita).json()["scopes"]]
        assert sc == ["ws", f"user:{sita_id}", f"team:{tid}"], sc
        assert [s["id"] for s in c.get("/api/teams", headers=amit).json()["scopes"]] == ["ws", f"user:{amit_id}"]

        # another person's item cannot be touched or even opened by id
        priv = next(x for x in c.get("/api/library?kind=image", headers=ravi).json() if x["name"] == "ravi_private.png")
        assert c.patch(f"/api/library/{priv['id']}", headers=amit, json={"name": "hacked"}).status_code == 404
        assert c.delete(f"/api/library/{priv['id']}", headers=amit).status_code == 404
        # the owner moves it: personal → team → shared
        assert c.patch(f"/api/library/{priv['id']}", headers=ravi, json={"scope": f"team:{tid}"}).json()["scope"] == f"team:{tid}"
        assert "ravi_private.png" in names(sita)
        tl = next(x for x in c.get("/api/library?kind=image", headers=ravi).json() if x["name"] == "team_logo.png")
        assert c.patch(f"/api/library/{tl['id']}", headers=ravi, json={"scope": "ws"}).status_code == 403, "only the one who added it (or an admin) moves it"
        assert c.patch(f"/api/library/{tl['id']}", headers=sita, json={"scope": "ws"}).json()["scope"] == "ws"
        assert "team_logo.png" in names(amit)

        # the leader manages members; a member cannot
        assert c.patch(f"/api/teams/{tid}", headers=sita, json={"members": [sita_id, amit_id]}).status_code == 403
        t2 = c.patch(f"/api/teams/{tid}", headers=ravi, json={"members": [sita_id, amit_id], "name": "renamed by leader"}).json()
        assert sorted(m["name"] for m in t2["members"]) == ["Amit", "Sita"] and t2["name"] == "Editing team", t2      # the name is the admin's
        assert "ravi_private.png" in names(amit)
        # deleting the team loses nothing: its items become shared
        assert c.delete(f"/api/teams/{tid}", headers=ravi).status_code == 403
        assert c.delete(f"/api/teams/{tid}", headers=admin).status_code == 200
        assert c.get("/api/teams", headers=admin).json()["teams"] == []
        c.patch(f"/api/teams/{tid}", headers=admin, json={"members": []})
        assert "ravi_private.png" in names(admin)
        print("teams: shared / personal / team folders, visibility, moving, leader rights, nothing lost when a team is removed ✓")
    print("ALL PASS")


if __name__ == "__main__":
    main()
