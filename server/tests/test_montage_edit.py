"""Montage after the auto-edit: a hand-edited plan is cleaned (unknown clips dropped, an empty plan refused), and a
finished montage opens as a normal project for the full editor — as it is, with no auto-cut.

    python3 tests/test_montage_edit.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="vividora-moedit-")
os.environ.update({"DATA_ROOT": TMP, "DATABASE_PATH": str(Path(TMP) / "t.db"), "MEDIA_ROOT": str(Path(TMP) / "m"), "ADMIN_PASSWORD": "test-pass-123",
                   "SECRET_KEY": "unit-test-secret-key-that-is-long-enough-0123456789", "WEB_DIST": str(Path(TMP) / "nope")})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient  # noqa: E402

from vividora import db, service, storage  # noqa: E402
from vividora.app import create_app  # noqa: E402


def main() -> None:
    with TestClient(create_app()) as client:
        tok = client.post("/api/auth/login", json={"email": "admin@vividora.local", "password": "test-pass-123"}).json()["token"]
        h = {"authorization": f"Bearer {tok}"}
        pid = client.post("/api/projects", json={"title": "mo", "kind": "montage"}, headers=h).json()["id"]
        seg = lambda clip, **kw: {"clip": clip, "src_in": 1, "dur": 0.5, "speed": 1, "fx": "flash", "keep": True, **kw}  # noqa: E731
        base = {"mode": "auto", "replan": False, "clips": [{"id": "A"}, {"id": "B"}], "music": "M", "preset": "ig-reel"}

        # a cut that uses a clip which is not part of the montage is dropped; a new / duplicated cut is kept
        r = client.post(f"/api/projects/{pid}/montage", json={**base, "plan": {"period": 0.5, "segments": [
            seg("A"), seg("A", src_in=3, fx="vhs"), seg("GONE"), seg("B", keep=False), seg("B", speed=0.5, fx="nonsense")]}}, headers=h)
        assert r.status_code == 200, r.text
        pl = db.get("projects", pid)["settings"]["montage"]["plan"]
        assert [s["clip"] for s in pl["segments"]] == ["A", "A", "B", "B"], pl["segments"]
        assert pl["segments"][1]["fx"] == "vhs" and pl["segments"][3]["fx"] == "cut" and pl["segments"][3]["speed"] == 0.5
        assert pl["total"] == 1.5, pl["total"]
        print("PASS edited plan: unknown clip dropped, new cuts kept, total recomputed")

        # text placed / sized by hand: position kept as fractions (clamped), junk → the middle, only known "user" flags
        r = client.post(f"/api/projects/{pid}/montage", json={**base, "text_pos": [0.3, 1.7], "title_pos": "x", "text_size": 0.5, "text_user": ["size", "hack"],
                                                              "plan": {"period": 0.5, "segments": [seg("A")]}}, headers=h)
        assert r.status_code == 200, r.text
        m = db.get("projects", pid)["settings"]["montage"]
        assert m["text_pos"] == [0.3, 0.98] and m["title_pos"] == [0.5, 0.5] and m["text_size"] == 0.2 and m["text_user"] == ["size"], m
        print("PASS montage text position / size saved")

        # nothing left to show → refused with a clear message
        r = client.post(f"/api/projects/{pid}/montage", json={**base, "plan": {"segments": [seg("A", keep=False), seg("GONE")]}}, headers=h)
        assert r.status_code == 422 and "cut" in r.json()["error"], r.text
        print("PASS empty plan refused")

        # no video yet → the full editor cannot open it
        r = client.post(f"/api/projects/{pid}/montage/to-editor", json={}, headers=h)
        assert r.status_code == 400, r.text
        # a finished montage → a new normal project whose recording is that video
        p = db.get("projects", pid)
        rel = str(storage.project_dir(p["workspace_id"], pid) / "out" / "ig-reel.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=360x640:r=30:d=2", "-f", "lavfi", "-i", "sine=f=300:d=2",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(storage.ensure_parent(rel))], check=True)
        with db.tx() as c:
            service.add_asset(c, pid, "render", rel, label="ig-reel")
        r = client.post(f"/api/projects/{pid}/montage/to-editor", json={}, headers=h)
        assert r.status_code == 201, r.text
        np_ = r.json()["project"]
        assert np_["id"] != pid and np_["kind"] == "talking_head" and np_["title"] == "mo — edit", np_
        row = db.get("projects", np_["id"])
        assert row["settings"]["as_is"] is True and row["settings"]["from_montage"] == pid and row["status"] == "preparing"
        raws = [a for a in np_["assets"] if a["kind"] == "raw"]
        assert len(raws) == 1 and storage.abs_path(db.get("assets", raws[0]["id"])["path"]).stat().st_size > 1000
        assert r.json()["job"]["kind"] == "prepare"
        assert db.get("projects", pid)["kind"] == "montage" and storage.abs_path(rel).exists()      # the montage itself is untouched
        print("PASS montage → normal project (own copy of the video, prepare queued)")

        # the prepare result of an "as is" project: every frame kept — no auto-cut, no Whisper
        job = db.get("jobs", r.json()["job"]["id"])
        with db.tx() as c:
            service.after_job(c, job, {"meta": {"duration": 2.0, "has_audio": True, "width": 360, "height": 640, "fps": 30}, "files": []})
        row = db.get("projects", np_["id"])
        assert row["status"] == "review_cuts" and row["edl"]["cuts"] == [] and row["transcript"]["skipped"] is True, (row["status"], row["edl"])
        queued = [j["kind"] for j in db.rows(db.conn().execute("SELECT * FROM jobs WHERE project_id = ? AND status = 'queued' AND kind != 'prepare'", (np_["id"],)))]
        assert queued == [], queued
        print("PASS as-is pipeline: ready for editing with 0 cuts, nothing else queued")


if __name__ == "__main__":
    main()
    print("ALL PASS")
