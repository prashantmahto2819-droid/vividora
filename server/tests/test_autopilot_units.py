"""Fast autopilot checks without rendering (seconds): switches, pre-flight auto-fixes, Short plans,
the one-AI-call metadata step, failure notes, no double transitions.

    cd server && python3 tests/test_autopilot_units.py     (or: python3 -m pytest -q tests/test_autopilot_units.py)
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="vividora_units_"))
os.environ.update({"DATA_ROOT": str(TMP), "MEDIA_ROOT": str(TMP / "media"), "DATABASE_PATH": str(TMP / "v.db"), "LLM_CACHE": "0"})
for _k in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "NOTIFY_URL"):
    os.environ.pop(_k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vividora import autopilot_flow, db, notify, queue, service  # noqa: E402
from vividora.engine import aipack, autopilot, llm  # noqa: E402

SENT = ["आज मैं आपको एक सच्ची कहानी सुनाता हूँ।", "क्या आप जानते हैं सफलता का राज़ क्या है?",
        "एक लड़का रोज़ सुबह चार बजे उठकर मेहनत करता था।", "उसके पास पैसा नहीं था पर एक बड़ा सपना था।",
        "सबसे बड़ी गलती है डर के कारण शुरुआत न करना।", "समय किसी का इंतज़ार नहीं करता।"]


def transcript(seconds: float) -> dict:
    segs, t, i = [], 0.5, 0
    while t < seconds - 3:
        words = []
        for w in SENT[i % len(SENT)].split():
            words.append({"w": w, "start": round(t, 2), "end": round(t + 0.3, 2), "p": 0.9})
            t += 0.38
        segs.append({"start": words[0]["start"], "end": words[-1]["end"], "text": SENT[i % len(SENT)], "words": words})
        t += 0.6
        i += 1
    return {"language": "hi", "segments": segs, "text": " ".join(s["text"] for s in segs)}


def setup():
    db.init()
    from vividora.bootstrap import ensure_admin
    ensure_admin()
    ws = db.row(db.conn().execute("SELECT * FROM workspaces").fetchone())
    with db.tx() as c:
        ch = {"id": db.new_id(), "workspace_id": ws["id"], "name": "Two", "niche": "motivation", "language": "hi", "color": "#fff",
              "settings": {"brand": {"autopilot": {"shorts": 2, "music": False}}, "autopilot": {"zoom": False}},
              "created_at": db.now(), "updated_at": db.now()}
        db.insert(c, "channels", ch)
    return ws, ch


def project(ws, ch, seconds: float, autopilot_on: bool = True) -> dict:
    from vividora.engine import autocut
    tr = transcript(seconds)
    p = {"id": db.new_id(), "workspace_id": ws["id"], "created_by": None, "channel_id": ch["id"], "title": "टेस्ट", "kind": "talking_head",
         "language": "hi", "status": "cutting", "status_note": "", "meta": {"duration": seconds, "has_audio": True, "width": 1280, "height": 720},
         "transcript": tr, "edl": autocut.build_edl(tr, seconds), "settings": {"render": {}, "autocut": {}, "autopilot": autopilot_on},
         "approved_by": None, "approved_at": None, "created_at": db.now(), "updated_at": db.now()}
    with db.tx() as c:
        db.insert(c, "projects", p)
        autopilot_flow.begin(c, p)
    return db.get("projects", p["id"])


def test_switches_and_channel():
    ws, ch = setup()
    sw = autopilot.settings_for(ch["settings"]["brand"], ch["settings"]["autopilot"])
    assert sw["shorts"] == 2 and sw["music"] is False and sw["zoom"] is False
    assert autopilot.settings_for({"autopilot": {"shorts": "x"}})["shorts"] == 3  # bad value keeps the default
    # long recording: only yt-long (no 10-minute Reel), music switch respected, Shorts count from the channel
    p = project(ws, ch, 600)
    opts = service.autopilot_plan(p)
    assert opts["presets"] == ["yt-long"], opts["presets"]
    assert opts["effects"]["music"]["id"] == "" and opts["effects"]["zoom"]["enabled"] is False
    assert opts["autopilot"]["shorts"] == 2
    # pre-flight: a Reel preset on a 10-minute video is dropped, the hook gets set
    o, notes = autopilot.preflight_fix(p, {**opts, "presets": ["yt-long", "ig-reel"], "hook": {"text": ""}},
                                       [{"heading": "सफलता का असली राज़"}])
    assert o["presets"] == ["yt-long"] and any("ig-reel" in n for n in notes), notes
    assert o["hook"]["text"] == "सफलता का असली राज़"
    # a Short's plan: everything timed inside the Short
    clip = {"id": "s1", "start": 100.0, "end": 140.0, "hook": "क्या आप जानते हैं"}
    sp = autopilot.plan(p, {**ch["settings"], "niche": "motivation"}, [], clip=clip)
    assert sp["presets"] == ["yt-short"] and sp["hook"]["text"] == "क्या आप जानते हैं"
    for it in sp["effects"]["titles"] + sp["effects"]["broll"]:
        assert it["start"] < 40, it
    return ws, ch


def test_sequence_and_one_ai_call():
    ws, ch = setup()
    sent: list[str] = []
    notify.send = lambda text: sent.append(text)
    p = project(ws, ch, 300)
    # autocut done → plan + preflight + main render queued, status says step 6
    with db.tx() as c:
        job = queue.enqueue(c, p["id"], "autocut", {})
        service.after_job(c, {**job, "status": "running"}, {"edl": p["edl"]})
    p = db.get("projects", p["id"])
    assert p["status_note"].startswith("6/11 · "), p["status_note"]
    renders = db.rows(db.conn().execute("SELECT * FROM jobs WHERE project_id = ? AND kind = 'render' AND status = 'queued'", (p["id"],)))
    assert [r["payload"]["preset"] for r in renders] == ["yt-long"]
    assert not db.conn().execute("SELECT COUNT(*) FROM jobs WHERE project_id = ? AND kind = 'shorts_plan'", (p["id"],)).fetchone()[0], \
        "Shorts must wait for the main render"
    # main render done → shorts plan (exactly once, even if "done" arrives twice)
    for _ in range(2):
        with db.tx() as c:
            c.execute("UPDATE jobs SET status = 'done' WHERE id = ?", (renders[0]["id"],))
            service.after_job(c, renders[0], {"files": [], "warnings": []})
    # no output file was reported → render step fails with a clear note
    p = db.get("projects", p["id"])
    assert p["status"] == "failed" and p["status_note"].startswith("✖ 6/11") and "→" in p["status_note"], p["status_note"]
    assert len([m for m in sent if "रुक गया" in m]) == 1, sent
    # resume from the failed step
    with db.tx() as c:
        step = autopilot_flow.resume(c, p)
    assert step == "render"
    r2 = db.rows(db.conn().execute("SELECT * FROM jobs WHERE project_id = ? AND kind = 'render' AND status = 'queued'", (p["id"],)))
    (TMP / "media" / "o").mkdir(parents=True, exist_ok=True)
    (TMP / "media" / "o" / "long.mp4").write_bytes(b"x" * 10)
    with db.tx() as c:
        c.execute("UPDATE jobs SET status = 'done' WHERE id = ?", (r2[0]["id"],))
        service.after_job(c, r2[0], {"files": [{"kind": "render", "path": "o/long.mp4", "label": "yt-long", "meta": {}}], "warnings": []})
        service.after_job(c, r2[0], {"files": [{"kind": "render", "path": "o/long.mp4", "label": "yt-long", "meta": {}}], "warnings": []})
    sp = db.rows(db.conn().execute("SELECT * FROM jobs WHERE project_id = ? AND kind = 'shorts_plan'", (p["id"],)))
    assert len(sp) == 1 and sp[0]["payload"]["options"]["count"] == 2, sp
    assert db.get("projects", p["id"])["status_note"].startswith("7/11 · ")
    # shorts plan done → one render per Short, timed on the Short
    clips = [{"id": "s1", "start": 20.0, "end": 55.0, "title": "पहला Short", "hook": "क्या आप जानते हैं", "selected": True},
             {"id": "s2", "start": 120.0, "end": 160.0, "title": "दूसरा Short", "hook": "सबसे बड़ी गलती", "selected": True}]
    with db.tx() as c:
        c.execute("UPDATE jobs SET status = 'done' WHERE id = ?", (sp[0]["id"],))
        service.after_job(c, sp[0], {"clips": clips})
    sr = db.rows(db.conn().execute("SELECT * FROM jobs WHERE project_id = ? AND kind = 'render' AND status = 'queued'", (p["id"],)))
    assert sorted(j["payload"]["label"] for j in sr) == ["short-s1", "short-s2"]
    assert all(j["payload"]["hook"]["text"] for j in sr)
    # fake an AI key: the metadata step must make ONE call for all outputs
    calls = []
    os.environ["GEMINI_API_KEY"] = "test"
    llm._ask = lambda which, prompt, **k: calls.append(prompt) or {
        "hooks": [{"heading": "राज़", "say": "x", "type": "question"}],
        "meta": {"youtube": {"title": "लंबा title", "description": "a\n#a #b #c #d #e", "tags": ["x"]},
                 "short": {"title": "short title #shorts", "description": "b #a #b #c", "tags": ["y"]}},
        "thumb_texts": ["*सपना* सच"], "pinned_comment": "?"}
    import vividora.thumbs as thumbs
    thumbs._autopilot_now = lambda pid: None  # no frames to render here
    for j, cl in zip(sr, clips):
        (TMP / "media" / "o" / f"{cl['id']}.mp4").write_bytes(b"x" * 10)
        with db.tx() as c:
            c.execute("UPDATE jobs SET status = 'done' WHERE id = ?", (j["id"],))
            service.after_job(c, j, {"files": [{"kind": "render", "path": f"o/{cl['id']}.mp4", "label": j["payload"]["label"], "meta": {}}]})
    with db.tx() as c:  # a YouTube connection on this channel
        db.insert(c, "connections", {"id": "cy", "workspace_id": ws["id"], "platform": "youtube", "name": "yt", "secrets": {}, "meta": {},
                                     "created_at": db.now(), "updated_at": db.now(), "channel_id": ch["id"]})
    autopilot_flow.finish(p["id"])  # what the background thread runs
    os.environ.pop("GEMINI_API_KEY")
    p = db.get("projects", p["id"])
    assert p["status"] == "review_output" and p["status_note"].startswith("✅"), p["status_note"]
    assert len(calls) == 1, f"{len(calls)} AI calls"
    pp = p["meta"]["publish_plan"]
    assert len(pp) == 3 and all(it.get("when") for it in pp)
    titles = [it["title"] for it in pp if it["label"].startswith("short-")]
    assert titles == ["पहला Short #Shorts", "दूसरा Short #Shorts"] or sorted(titles) == sorted(["पहला Short #Shorts", "दूसरा Short #Shorts"]), titles
    for it in pp:
        assert len([w for w in (it["title"] + " " + it["description"]).split() if w.startswith("#")]) <= 3, it
    assert len([m for m in sent if "autopilot पूरा" in m and f"ok {p['id'][:4].upper()}" in m]) == 1, sent
    # finishing again (restart / watchdog) does nothing new
    autopilot_flow.finish(p["id"])
    assert len([m for m in sent if "autopilot पूरा" in m]) == 1
    # a manual re-render afterwards keeps the publish plan pointing at the new file
    with db.tx() as c:
        j = queue.enqueue(c, p["id"], "render", {"preset": "yt-long"})
        c.execute("UPDATE jobs SET status = 'done' WHERE id = ?", (j["id"],))
        (TMP / "media" / "o" / "long2.mp4").write_bytes(b"x" * 10)
        service.after_job(c, j, {"files": [{"kind": "render", "path": "o/long2.mp4", "label": "yt-long", "meta": {}}]})
    p = db.get("projects", p["id"])
    new_id = db.conn().execute("SELECT id FROM assets WHERE project_id = ? AND label = 'yt-long'", (p["id"],)).fetchone()[0]
    assert next(it for it in p["meta"]["publish_plan"] if it["label"] == "yt-long")["asset_id"] == new_id
    assert p["status"] == "review_output"


if __name__ == "__main__":
    try:
        test_switches_and_channel()
        test_sequence_and_one_ai_call()
        print("OK")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
