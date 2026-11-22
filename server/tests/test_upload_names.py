"""Upload start: which file names are accepted, and that a refused file is NAMED in the error.

    python3 tests/test_upload_names.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="vividora-upnames-")
os.environ.update({"DATA_ROOT": TMP, "DATABASE_PATH": str(Path(TMP) / "t.db"), "MEDIA_ROOT": str(Path(TMP) / "m"), "ADMIN_PASSWORD": "test-pass-123",
                   "SECRET_KEY": "unit-test-secret-key-that-is-long-enough-0123456789", "WEB_DIST": str(Path(TMP) / "nope")})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient  # noqa: E402

from vividora import db  # noqa: E402
from vividora.app import create_app  # noqa: E402


def main() -> None:
    with TestClient(create_app()) as client:
        tok = client.post("/api/auth/login", json={"email": "admin@vividora.local", "password": "test-pass-123"}).json()["token"]
        h = {"authorization": f"Bearer {tok}"}
        pid = client.post("/api/projects", json={"title": "x"}, headers=h).json()["id"]

        def start(name: str):
            return client.post(f"/api/projects/{pid}/uploads", json={"filename": name, "size": 1000, "clip": True}, headers=h)
        for ok_name in ("warrior.mp4", "Warrior.MP4", "clip.MOV", "old.wmv", "cam.mpg", "song.aac", "voice.ogg", "tape.m2ts"):
            r = start(ok_name)
            assert r.status_code in (200, 201), (ok_name, r.status_code, r.text)
        r = start("वीडियो.mp4")                       # a Hindi name keeps its extension on disk
        assert r.status_code in (200, 201), r.text
        fn = db.get("uploads", r.json()["upload_id"])["filename"]
        assert fn.lower().endswith(".mp4") and len(fn) > 4, fn
        r = start("IMG_4307.JPG")                     # a photo: refused, named, and told where photos go
        assert r.status_code == 422 and "IMG_4307.JPG" in r.json()["error"] and "Montage" in r.json()["error"], r.text
        r = start("notes.pdf")
        assert r.status_code == 422 and "notes.pdf" in r.json()["error"] and ".pdf" in r.json()["error"], r.text
        r = start("noextension")
        assert r.status_code == 422 and "noextension" in r.json()["error"], r.text
        r = start("evil.mp4.exe")
        assert r.status_code == 422, r.text
    print("OK")


if __name__ == "__main__":
    main()
