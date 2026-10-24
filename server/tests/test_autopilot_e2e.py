"""Autopilot end to end: upload → … → review_output, with the real API, the real CPU worker code and
real ffmpeg renders. Only speech-to-text is mocked (Whisper models need a download): the mock
writes Hindi words exactly where the synthetic recording has "speech" (tone bursts), so cuts,
captions, stickers, Shorts and hooks all work on real timings.

    cd server && python3 tests/test_autopilot_e2e.py          # ~8–12 min on 2 CPU cores
    cd server && python3 -m pytest -q tests/test_autopilot_e2e.py

Scenarios (all run in parallel, two worker threads):
  A  150 s horizontal talk, NON-default channel with its own switches (2 Shorts, SFX on), YouTube +
     Instagram connected (dry run)  → yt-long + 2 Shorts with their own titles, thumbnails, metadata,
     publish plan with times, preflight + QA, exactly one WhatsApp message with the approval code.
  B  40 s vertical clip, default channel with music OFF and Shorts 0 → yt-short / ig-reel / fb-reel,
     no music, no Shorts.
  C  20 s recording without an audio track → still finishes (no transcript, no captions).
  D  an API restart in the middle of the last steps (simulated: project put back to step 10)
     → the watchdog finishes it, still one message.
Nothing is published: the test checks no publish job exists.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent
REPO = SERVER.parent
TIMEOUT = float(os.getenv("E2E_TIMEOUT", "1500"))

WORDS = ("आज मैं आपको एक सच्ची कहानी सुनाता हूँ जो आपकी ज़िंदगी बदल देगी। "
         "क्या आप जानते हैं कि सफलता का सबसे बड़ा राज़ क्या है? "
         "एक लड़का था जो रोज़ सुबह चार बजे उठकर मेहनत करता था। "
         "उसके पास पैसा नहीं था लेकिन एक बड़ा सपना था। "
         "लोग हँसते थे पर उसने कभी हार नहीं मानी। "
         "सबसे बड़ी गलती है डर के कारण शुरुआत ही न करना। "
         "समय किसी का इंतज़ार नहीं करता इसलिए आज से शुरू करो। "
         "अपने लक्ष्य को रोज़ याद करो और आगे बढ़ते रहो। "
         "दोस्तों याद रखो मेहनत का कोई विकल्प नहीं है। "
         "तीन साल बाद वही लड़का अपने शहर का सबसे सफल इंसान बना।").split()


# ---------------------------------------------------------------- helpers
def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def make_video(path: Path, seconds: int, size: str, audio: bool = True) -> None:
    """testsrc picture + 'speech' = a voiced tone 5 s on / 1 s pause (so autocut has real pauses)."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=s={size}:r=25:d={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i",
                f"aevalsrc=exprs=0.35*sin(2*PI*(170+50*sin(2*PI*3*t))*t)*lt(mod(t\\,6)\\,5)*(0.6+0.4*sin(2*PI*4*t)):s=48000:d={seconds}",
                "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True)


def fake_transcribe(audio: Path, *, language: str = "hi", prompt: str | None = None, on_progress=None, **_kw) -> dict:  # window/alternatives/model: ignored
    """Words where the recording actually has sound (ffmpeg silencedetect), sentences end with ।/?."""
    from vividora.engine import ffmpeg
    dur = ffmpeg.probe(audio)["duration"]
    sil = ffmpeg.silences(audio)
    busy, t = [], 0.0
    for s, e in sil:
        if s > t:
            busy.append((t, s))
        t = e
    if t < dur:
        busy.append((t, dur))
    segs, cur, k = [], [], 0
    for a, b in busy:
        x = a + 0.1
        while x + 0.32 < b:
            w = WORDS[k % len(WORDS)]
            k += 1
            cur.append({"w": w, "start": round(x, 3), "end": round(x + 0.3, 3), "p": 0.95})
            x += 0.38
            if w.endswith(("।", "?")):
                segs.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": " ".join(c["w"] for c in cur), "words": cur})
                cur = []
    if cur:
        segs.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": " ".join(c["w"] for c in cur), "words": cur})
    if on_progress:
        on_progress(1.0, "mock transcript")
    return {"language": "hi", "model": "mock", "text": " ".join(s["text"] for s in segs), "segments": segs}


class Inbox:
    """Stands in for the WhatsApp gateway (NOTIFY_URL): records every message."""

    def __init__(self):
        self.messages: list[str] = []
        inbox = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("content-length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                inbox.messages.append(body.get("message") or "")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *a):
                pass
        self.port = free_port()
        self.srv = HTTPServer(("127.0.0.1", self.port), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()


class Api:
    def __init__(self, base: str, token: str):
        self.base, self.token = base, token

    def __call__(self, method: str, path: str, data=None, raw: bytes | None = None, headers: dict | None = None):
        h = {"Authorization": f"Bearer {self.token}", **(headers or {})}
        body = None
        if raw is not None:
            body, h["Content-Type"] = raw, "application/octet-stream"
        elif data is not None:
            body, h["Content-Type"] = json.dumps(data).encode(), "application/json"
        req = urllib.request.Request(self.base + "/api" + path, data=body, method=method, headers=h)
        with urllib.request.urlopen(req, timeout=120) as r:
            t = r.read().decode()
            return json.loads(t) if t else {}

    def upload(self, pid: str, path: Path) -> None:
        up = self("POST", f"/projects/{pid}/uploads", {"filename": path.name, "size": path.stat().st_size})
        data = path.read_bytes()
        for off in range(0, len(data), 8 << 20):
            self("PUT", f"/projects/{pid}/uploads/{up['upload_id']}/chunk", raw=data[off:off + (8 << 20)], headers={"X-Offset": str(off)})
        self("POST", f"/projects/{pid}/uploads/{up['upload_id']}/finish", {})


# ---------------------------------------------------------------- the test
def test_autopilot_end_to_end():
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required")
    tmp = Path(tempfile.mkdtemp(prefix="vividora_e2e_"))
    inbox = Inbox()
    port = free_port()
    env = {**os.environ, "DATA_ROOT": str(tmp), "MEDIA_ROOT": str(tmp / "media"), "DATABASE_PATH": str(tmp / "v.db"),
           "WEB_DIST": str(REPO / "web" / "dist"), "WORKER_TOKEN": "e2e-worker", "SECRET_KEY": "e2e-secret-key-0123456789abcdef0123",
           "NOTIFY_URL": f"http://127.0.0.1:{inbox.port}/send", "NOTIFY_TO": "919999999999", "PUBLISH_DRY_RUN": "1",
           "PUBLIC_URL": f"http://127.0.0.1:{port}", "GEMINI_API_KEY": "", "ANTHROPIC_API_KEY": "", "LLM_CACHE": "0"}
    for k in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        env.pop(k, None)
    os.environ.update({k: v for k, v in env.items() if k in ("DATA_ROOT", "MEDIA_ROOT", "DATABASE_PATH", "WORKER_TOKEN", "SECRET_KEY")})
    for k in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        os.environ.pop(k, None)
    log = open(tmp / "api.log", "w")
    api_proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "vividora.app:app", "--port", str(port)], cwd=SERVER, env=env,
                                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    try:
        _run(tmp, port, inbox)
    finally:
        api_proc.terminate()
        try:
            api_proc.wait(10)
        except subprocess.TimeoutExpired:
            api_proc.kill()
        if os.getenv("E2E_KEEP") != "1":
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            print("kept:", tmp)


def _run(tmp: Path, port: int, inbox: Inbox) -> None:
    sys.path.insert(0, str(SERVER))
    base = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=2)
            break
        except OSError:
            time.sleep(0.5)
    else:
        raise RuntimeError("API did not start:\n" + (tmp / "api.log").read_text()[-3000:])
    con = sqlite3.connect(tmp / "v.db")
    user_id, ws_id = con.execute("SELECT id, workspace_id FROM users LIMIT 1").fetchone()
    from vividora import security
    api = Api(base, security.access_token(user_id))
    n_lib = con.execute("SELECT kind, COUNT(*) FROM library GROUP BY kind").fetchall()
    assert dict(n_lib).get("music") and dict(n_lib).get("sticker"), f"starter pack not installed: {n_lib}"

    # workers: the real CPU worker code, in this process, with a mocked transcriber (two threads = two workers)
    os.environ.update({"X264_PRESET": "ultrafast"})
    from vividora.worker import client as wclient, cpu, transcribe as tmod
    tmod.transcribe_file = fake_transcribe
    kinds = ["prepare", "transcribe", "autocut", "render", "shorts_plan", "publish"]
    for i in range(2):
        cl = wclient.ApiClient(base, "e2e-worker", f"e2e-cpu-{i}")
        threading.Thread(target=wclient.run_loop, args=(cl, kinds, cpu.handle), kwargs={"poll": 0.5}, daemon=True).start()

    # channels: B = the default one (music off, no Shorts), A = a second channel with its own switches
    ch_b = api("POST", "/channels", {"name": "Main", "niche": "motivation"})["id"]
    ch_a = api("POST", "/channels", {"name": "Second", "niche": "hindi motivational stories"})["id"]
    api("PUT", f"/brand?channel={ch_b}", {"autopilot": {"music": False, "shorts": 0}})
    api("PUT", f"/brand?channel={ch_a}", {"autopilot": {"shorts": 2, "sfx": True}, "hashtags": "#motivation #hindi #story #success"})
    now = "2026-01-01T00:00:00+00:00"
    with con:
        for plat in ("youtube", "instagram"):
            con.execute("INSERT INTO connections (id, workspace_id, platform, name, secrets, meta, created_at, updated_at, channel_id) "
                        "VALUES (?,?,?,?,?,?,?,?,?)", (f"conn-{plat}", ws_id, plat, f"test {plat}", "{}", "{}", now, now, ch_a))

    vids = {"A": (tmp / "talk_150s.mp4", 150, "1280x720", True), "B": (tmp / "vertical_40s.mp4", 40, "720x1280", True),
            "C": (tmp / "silent_20s.mp4", 20, "1280x720", False)}
    for path, secs, size, audio in vids.values():
        make_video(path, secs, size, audio)
    projects = {}
    for key, ch in (("A", ch_a), ("B", ch_b), ("C", ch_b)):
        p = api("POST", "/projects", {"title": f"E2E {key} सपनों की कहानी", "autopilot": True, "language": "hi", "channel_id": ch})
        api.upload(p["id"], vids[key][0])
        projects[key] = p["id"]

    # wait; every status_note seen must be a numbered step while autopilot works
    notes: dict[str, list[str]] = {k: [] for k in projects}
    t0 = time.time()
    done: dict[str, dict] = {}
    while len(done) < len(projects):
        assert time.time() - t0 < TIMEOUT, f"timeout; notes: {json.dumps(notes, ensure_ascii=False)[:3000]}"
        for key, pid in projects.items():
            if key in done:
                continue
            v = api("GET", f"/projects/{pid}")
            if not notes[key] or notes[key][-1] != v["status_note"]:
                notes[key].append(v["status_note"])
                print(f"[{time.time() - t0:5.0f}s] {key}: {v['status']} · {v['status_note']}", flush=True)
            if v["status"] == "failed":
                raise AssertionError(f"{key} failed: {v['status_note']}\njobs: {[(j['kind'], j['status'], (j.get('error') or '')[-400:]) for j in v['jobs']]}")
            if v["status"] == "review_output" and ((v.get("meta") or {}).get("autopilot") or {}).get("stage") == "ready":
                done[key] = v
        time.sleep(2)

    for key, ns in notes.items():
        working = [n for n in ns[:-1] if n and n != "upload का इंतज़ार"]
        assert working and all("/11 · " in n for n in working), f"{key}: notes without a step number: {working}"
        steps = [int(n.split("/")[0].split()[-1]) for n in working]
        assert steps == sorted(steps), f"{key}: steps went backwards: {working}"
        assert done[key]["status_note"].startswith("✅"), done[key]["status_note"]

    def check_common(key: str, v: dict) -> dict:
        ap = v["meta"]["autopilot"]
        hist = [h["stage"] for h in ap["history"]]
        order = ["prepare", "transcribe", "autocut", "plan", "preflight", "render", "shorts_plan", "shorts_render",
                 "thumbnails", "metadata", "publish_plan", "ready"]
        assert [s for s in order if s in hist] == hist, f"{key}: steps out of order / repeated: {hist}"
        for s in ("prepare", "plan", "preflight", "render", "thumbnails", "metadata", "publish_plan", "ready"):
            assert s in hist, f"{key}: step {s} missing: {hist}"
        kinds = [(j["kind"], j["status"]) for j in v["jobs"]]
        assert not any(st == "failed" for _, st in kinds), f"{key}: failed jobs {kinds}"
        assert not any(k == "publish" for k, _ in kinds), f"{key}: something was published without approval"
        assert len([1 for k, _ in kinds if k == "prepare"]) == 1, f"{key}: prepare ran twice"
        assert any(a["kind"] == "thumbnail" for a in v["assets"]), f"{key}: no thumbnail"
        renders = [a for a in v["assets"] if a["kind"] == "render"]
        assert renders, f"{key}: no render"
        assert set(ap.get("drafts") or {}) == {a["label"] for a in renders}, f"{key}: metadata drafts missing"
        for a in renders:
            d = ap["drafts"][a["label"]]
            assert d["title"] and d["description"] is not None and d["tags"], f"{key}: empty metadata {d}"
            qa = (a.get("meta") or {}).get("qa") or {}
            assert qa, f"{key}/{a['label']}: no QA info"
            assert qa.get("black_start", 0) < 0.3, f"{key}/{a['label']}: black start {qa}"
            if qa.get("lufs") is not None:
                assert abs(qa["lufs"] + 14) <= 3, f"{key}/{a['label']}: loudness {qa['lufs']} LUFS"
        return ap

    # A: long talk in the second channel
    a = done["A"]
    ap = check_common("A", a)
    labels = sorted(x["label"] for x in a["assets"] if x["kind"] == "render")
    assert "yt-long" in labels and len([x for x in labels if x.startswith("short-")]) == 2, labels
    assert "ig-reel" not in labels and "yt-short" not in labels, f"long video pushed as a Reel/Short: {labels}"
    assert a["settings"]["autopilot"] and ap["shorts"] == 2 and ap["switches"]["sfx"] is True
    rs = a["settings"]["render"]
    assert rs["effects"]["music"]["id"], "channel A has music on — none chosen"
    assert rs["hook"]["text"], "no hook on screen"
    assert rs["burn_captions"] is True
    pp = a["meta"]["publish_plan"]
    assert {it["label"] for it in pp} == set(labels), f"publish plan does not cover every output: {pp}"
    assert all(it["platform"] == "youtube" and it["connection_id"] == "conn-youtube" and it.get("when") for it in pp), pp
    short_titles = [it["title"] for it in pp if it["label"].startswith("short-")]
    assert len(set(short_titles)) == len(short_titles) and all(t.endswith("#Shorts") for t in short_titles), short_titles
    for it in pp:
        n_tags = len([w for w in (it["title"] + " " + it["description"]).split() if w.startswith("#")])
        assert n_tags <= 3, f"too many hashtags for YouTube: {it}"
    whens = sorted(it["when"] for it in pp)
    assert next(it for it in pp if it["label"] == "yt-long")["when"] == whens[0], "long video should go out first"
    shorts_jobs = [j for j in a["jobs"] if j["kind"] == "render" and (j["payload"].get("label") or "").startswith("short-")]
    assert shorts_jobs and all(j["payload"]["preset"] == "yt-short" and j["payload"]["clip"] for j in shorts_jobs)
    for j in shorts_jobs:  # the Short's stickers / text are timed on the Short, not on the long video
        clip_len = j["payload"]["clip"]["end"] - j["payload"]["clip"]["start"]
        for it in (j["payload"]["effects"].get("titles") or []) + (j["payload"]["effects"].get("broll") or []):
            assert float(it["start"]) < clip_len, f"short item outside the Short: {it}"
    assert [j["kind"] for j in a["jobs"]].count("shorts_plan") == 1

    # B: vertical short clip, default channel, music off, Shorts 0
    b = done["B"]
    ap = check_common("B", b)
    labels = sorted(x["label"] for x in b["assets"] if x["kind"] == "render")
    assert labels == ["fb-reel", "ig-reel", "yt-short"], labels
    assert not b["settings"]["render"]["effects"]["music"]["id"], "music switch is off but music was added"
    assert "shorts_plan" not in [h["stage"] for h in ap["history"]]
    assert not b["meta"].get("publish_plan"), "no connection in this channel → no publish plan items"
    for x in b["assets"]:
        if x["kind"] == "render":
            assert not (x["meta"].get("effects") or {}).get("music"), f"music rendered on {x['label']}"

    # C: no audio track
    c = done["C"]
    ap = check_common("C", c)
    assert any("आवाज़ नहीं" in w for w in ap.get("warnings") or []), ap.get("warnings")

    # WhatsApp: exactly one "ready" message per project, with its approval code; no failure messages
    time.sleep(1.5)
    for key, pid in projects.items():
        code = pid[:4].upper()
        mine = [m for m in inbox.messages if f"ok {code}" in m]
        assert len(mine) == 1, f"{key}: expected one approval message, got {mine}"
        assert "autopilot पूरा" in mine[0]
    assert not any("रुक गया" in m for m in inbox.messages), inbox.messages

    # D: API restart during the last steps → the watchdog picks the project up again
    pid = projects["C"]
    row = con.execute("SELECT meta FROM projects WHERE id = ?", (pid,)).fetchone()
    meta = json.loads(row[0])
    meta["autopilot"]["stage"] = "metadata"
    with con:
        con.execute("UPDATE projects SET meta = ?, status = 'rendering', status_note = '10/11 · title, description, tags (AI)' WHERE id = ?",
                    (json.dumps(meta, ensure_ascii=False), pid))
    t1 = time.time()
    while True:
        v = api("GET", f"/projects/{pid}")
        if v["status"] == "review_output":
            break
        assert time.time() - t1 < 150, f"watchdog did not resume: {v['status_note']}"
        time.sleep(2)
    assert v["meta"]["autopilot"]["stage"] == "ready"
    assert len([m for m in inbox.messages if f"ok {pid[:4].upper()}" in m]) == 1, "resume sent a second message"

    # approval still works over WhatsApp-style code only through the dashboard; nothing got published
    st = api("GET", f"/projects/{projects['A']}/autopilot")
    assert st["stage"] == "ready" and all(s["state"] == "done" for s in st["steps"]), st
    print(f"OK — autopilot e2e passed in {time.time() - t0:.0f}s; messages: {len(inbox.messages)}")


if __name__ == "__main__":
    test_autopilot_end_to_end()
