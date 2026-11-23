#!/usr/bin/env python3
"""Auto SFX: pure-function checks + end-to-end (starter pack → /v1/auto-sfx → folder import).

    cd server && python3 tests/test_autosfx.py
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
fails = 0


def check(label, cond, val=None):
    global fails
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"  → {str(val)[:300]}"))
    fails += 0 if cond else 1


def units():
    from vividora.engine import autosfx
    names = ["pop", "pop soft", "whoosh", "whoosh soft", "swipe", "tick", "click", "ding"]
    lib = [{"id": f"id_{n.replace(' ', '_')}", "name": n, "kind": "sfx"} for n in names] + [{"id": "m1", "name": "song", "kind": "music"}]
    eff = {"titles": [{"_id": "a", "start": 5.0, "end": 8.0, "text": "x"}, {"_id": "ap_lower_third", "start": 3.0, "end": 6.0, "text": "n"}],
           "broll": [{"_id": "b", "id": "v", "start": 12.0, "end": 16.0, "fit": "cover"},
                     {"_id": "c", "id": "s", "start": 20.0, "end": 22.0, "fit": "free"}],
           "transition": "none", "sfx": [{"_id": "mine", "id": "id_ding", "at": 5.2, "volume": 0.9}]}
    out = autosfx.plan(eff, lib, out_dur=60, cut_times=[30.0, 40.0], density="normal")
    ids = [s["_id"] for s in out]
    check("all ids prefixed asfx_", ids and all(i.startswith("asfx_") for i in ids), ids)
    check("lower-third gets no sound", not any(abs(s["at"] - 3.0) < 0.2 for s in out), out)
    check("nothing within min gap of creator's own sound (5.2)", not any(abs(s["at"] - 5.2) < 1.0 for s in out), out)
    b = [s for s in out if s["auto"] == "broll"]
    check("b-roll whoosh leads the picture", b and b[0]["at"] < 12.0, b)
    check("sfx duck under voice", all(s["duck"] for s in out))
    check("volumes sane (0<v<=1)", all(0 < s["volume"] <= 1 for s in out))
    check("no jump-cut ticks on normal", not any(s["auto"] == "cut" for s in out), out)
    hi = autosfx.plan({**eff, "sfx": []}, lib, out_dur=60, cut_times=[30.0, 40.0], density="high")
    check("high density adds cut ticks", any(s["auto"] == "cut" for s in hi), hi)
    lo = autosfx.plan({**eff, "sfx": []}, lib, out_dur=60, cut_times=[30.0, 40.0], density="low")
    check("low density ≤ normal", len(lo) <= len(autosfx.plan({**eff, "sfx": []}, lib, out_dur=60, cut_times=[30, 40])), lo)
    check("min gap respected", all(b2["at"] - a["at"] >= 0.59 for a, b2 in zip(hi, hi[1:])), hi)
    # ---- richer sound families: hook hit, CTA ding, photo shutter, glitch cuts — and fall-backs for a small library
    names = ["pop", "pop soft", "click", "ding", "bubble pop", "whoosh", "whoosh soft", "swipe", "swoosh long", "whoosh fast", "slide", "tick",
             "impact boom", "hit deep", "drop bass", "notification", "bell chime", "camera shutter", "glitch"]
    big = [{"id": "s_" + n.replace(" ", "_"), "kind": "sfx", "name": n} for n in names] + [
        {"id": "img1", "kind": "image", "name": "photo of temple"}, {"id": "vid1", "kind": "broll", "name": "city drone"},
        {"id": "st1", "kind": "sticker", "name": "subscribe button", "tags": "starter,popup"}, {"id": "st2", "kind": "sticker", "name": "fire emoji", "tags": "emoji"}]
    fx2 = {"titles": [{"text": "Hook", "start": 0.3, "end": 2}, {"text": "Second", "start": 8, "end": 10}],
           "broll": [{"id": "img1", "start": 14, "end": 17}, {"id": "vid1", "start": 22, "end": 26},
                     {"id": "st1", "fit": "free", "start": 30, "end": 33}, {"id": "st2", "fit": "free", "start": 38, "end": 40}],
           "transition": "glitch", "sfx": []}
    out2 = autosfx.plan(fx2, big, out_dur=60, cut_times=[46.0], density="high")
    kinds = {s["auto"]: s["id"] for s in out2}
    check("opening title gets a deep hit, later titles a pop", kinds.get("hook") in ("s_impact_boom", "s_hit_deep", "s_drop_bass") and kinds.get("title") in ("s_pop", "s_pop_soft", "s_click"), kinds)
    check("still photo → shutter/slide, video B-roll → whoosh", kinds.get("photo") in ("s_camera_shutter", "s_slide") and kinds.get("broll", "").startswith(("s_whoosh", "s_swipe", "s_swoosh")), kinds)
    check("subscribe popup → ding/notification/bell, emoji → pop", kinds.get("cta") in ("s_ding", "s_notification", "s_bell_chime") and kinds.get("sticker") in ("s_pop", "s_bubble_pop", "s_pop_soft"), kinds)
    check("glitch transition → glitch sound on the cut", kinds.get("glitch") == "s_glitch", kinds)
    small = [x for x in big if x["kind"] != "sfx" or x["name"] in ("pop", "whoosh", "swipe")]
    out3 = autosfx.plan(fx2, small, out_dur=60, cut_times=[46.0], density="high")
    k3 = {s["auto"]: s["id"] for s in out3}
    check("small library: every event still gets a basic sound", k3.get("hook") == "s_pop" and k3.get("cta") == "s_pop" and k3.get("photo") in ("s_whoosh", "s_swipe") and k3.get("glitch") in ("s_swipe", "s_whoosh"), k3)
    used = set()
    for dens in ("low", "normal", "high"):
        used |= {s["id"] for s in autosfx.plan(fx2, big, out_dur=60, cut_times=[46.0, 50.0, 54.0], density=dens)}
    check("uses many different sounds, not the same two", len(used) >= 7, sorted(used))
    ap = autosfx.apply(eff, lib, out_dur=60)
    again = autosfx.apply(ap, lib, out_dur=60)
    check("apply is idempotent (replaces only asfx_)", [s["_id"] for s in ap["sfx"]] == [s["_id"] for s in again["sfx"]])
    check("creator's sound kept", any(s["_id"] == "mine" for s in again["sfx"]))
    check("empty library → nothing", autosfx.plan(eff, [], out_dur=60) == [])
    many = {"titles": [{"start": float(i), "end": i + 1.0, "text": "t"} for i in range(120)]}
    cap = autosfx.plan(many, lib, out_dur=120, density="normal")
    check("per-minute cap (≤ ~17 in 2 min)", len(cap) <= 17, len(cap))
    seq = [s["id"] for s in autosfx.plan({"titles": [{"start": 10.0 * i, "end": 10.0 * i + 2, "text": "t"} for i in range(1, 6)]}, lib, out_dur=80)]
    check("same sound not twice in a row", all(a != b for a, b in zip(seq, seq[1:])), seq)


def e2e():
    tmp = Path(tempfile.mkdtemp(prefix="vivi_sfx_"))
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    env = {**os.environ, "DATA_ROOT": str(tmp / "data"), "MEDIA_ROOT": str(tmp / "media"), "ADMIN_PASSWORD": "test-pass-123",
           "SECRET_KEY": "t", "WEB_DIST": str(tmp / "web"), "TRIPOSR_URL": "http://127.0.0.1:9"}
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "vividora.app:app", "--port", str(port), "--log-level", "warning"],
                           cwd=str(HERE), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}/api"

    def call(method, path, body=None, token=None):
        h = {"content-type": "application/json"} if body is not None else {}
        if token:
            h["authorization"] = f"Bearer {token}"
        req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"null")
            except ValueError:
                return e.code, None

    try:
        for _ in range(400):
            try:
                if call("GET", "/health")[0] == 200:
                    break
            except OSError:
                time.sleep(0.3)
        st, r = call("POST", "/auth/login", {"email": "admin@vividora.local", "password": "test-pass-123"})
        tok = r["token"]
        st, r = call("POST", "/keys", {"name": "t"}, token=tok)
        key = r["key"]
        st, r = call("POST", "/library/starter", {}, token=tok)
        st2, lib = call("GET", "/library?kind=sfx", token=tok)
        items = lib if isinstance(lib, list) else lib.get("items", [])
        names = {i["name"] for i in items}
        check("starter has new sounds (whoosh soft, tick, hit deep)", {"whoosh soft", "tick", "hit deep", "pop"} <= names, sorted(names))
        eff = {"titles": [{"start": 5, "end": 8}], "broll": [{"id": "x", "start": 12, "end": 16, "fit": "cover"}], "transition": "none", "sfx": []}
        st, r = call("POST", "/v1/auto-sfx", {"duration": 60, "effects": eff}, token=key)
        check("auto-sfx via API key", st == 200 and r["added"] >= 2 and all(x["_id"].startswith("asfx_") for x in r["sfx"]), (st, r))
        st, r = call("POST", "/v1/auto-sfx", {"duration": 60, "effects": eff, "density": "wild"}, token=key)
        check("bad density → 422", st == 422, (st, r))
        st, r = call("POST", "/v1/auto-sfx", {"effects": eff}, token=key)
        check("missing duration → 422", st == 422, (st, r))
        st, r = call("POST", "/v1/auto-sfx", {"project_id": "nope"}, token=key)
        check("unknown project → 404", st == 404, (st, r))
        st, r = call("POST", "/sfx/auto", {"duration": 60, "effects": eff}, token=tok)
        check("editor route works too", st == 200, (st, r))
        d = tmp / "media" / "incoming" / "sfx" / "whoosh"
        d.mkdir(parents=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.3", str(d / "earshot_test.wav")], check=True)
        st, r = call("POST", "/library/import-sfx-dir", {}, token=tok)
        check("folder import adds 1", st == 200 and r["added"] == 1, (st, r))
        st, r = call("POST", "/library/import-sfx-dir", {}, token=tok)
        check("folder import is idempotent", st == 200 and r["added"] == 0 and r["skipped"] == 1, (st, r))
        st, lib = call("GET", "/library?kind=sfx", token=tok)
        items = lib if isinstance(lib, list) else lib.get("items", [])
        imp = [i for i in items if i["name"] == "earshot test"]
        check("imported item tagged by folder", imp and "whoosh" in imp[0]["tags"], imp)
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except subprocess.TimeoutExpired:
            srv.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    units()
    e2e()
    print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAILED'}")
    sys.exit(1 if fails else 0)
