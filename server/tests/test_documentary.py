#!/usr/bin/env python3
"""Auto Documentary: units (planner parsing, picture choice, ffmpeg clips/mix) + end-to-end build with the fake TTS.
    cd server && VIVIDORA_TTS=fake python3 tests/test_documentary.py"""
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
os.environ["VIVIDORA_TTS"] = "fake"
for k in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "PIXABAY_API_KEY"):
    os.environ.pop(k, None)
fails = 0


def check(label, cond, val=None):
    global fails
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"  → {str(val)[:300]}"))
    fails += 0 if cond else 1


def probe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration", "-of", "json", str(p)],
                       capture_output=True, text=True)
    j = json.loads(r.stdout)
    return {s["codec_type"] for s in j["streams"]}, float(j["format"]["duration"]), j["streams"]


def units():
    from vividora.engine import documentary as doc
    from vividora.engine import tts
    n = doc.normalize({"title": "T", "scenes": [{"narration": "  नमस्ते   दुनिया ", "visual": "aerial himalaya", "on_screen": "x"}, {"narration": ""}, "bad", {"narration": "ok text"}]})
    check("normalize drops empty/bad scenes, squeezes spaces", n and len(n["scenes"]) == 2 and n["scenes"][0]["narration"] == "नमस्ते दुनिया", n)
    check("normalize rejects garbage", doc.normalize(None) is None and doc.normalize({"scenes": []}) is None and doc.normalize({"scenes": "x"}) is None)
    s = doc.scenes_from_script("पहला भाग।\n\nदूसरा भाग।\n\nतीसरा भाग।")
    check("paragraphs → scenes", s and len(s["scenes"]) == 3, s)
    long = " ".join(f"This is sentence number {i} of a long paragraph." for i in range(30))
    s = doc.scenes_from_script(long)
    check("one long paragraph is cut into several scenes", s and len(s["scenes"]) >= 4 and all(len(x["narration"]) <= 400 for x in s["scenes"]), s and len(s["scenes"]))
    check("no llm key → plan() is None", doc.plan("Himalaya") is None)
    lib = [{"id": "a", "kind": "image", "name": "Himalaya mountains sunrise", "tags": "nature", "meta": {}},
           {"id": "b", "kind": "broll", "name": "city traffic", "tags": "urban,cars", "meta": {}},
           {"id": "c", "kind": "image", "name": "himalaya cutout", "tags": "", "meta": {"alpha": True}},
           {"id": "d", "kind": "music", "name": "himalaya song", "tags": "", "meta": {}}]
    check("keyword match picks the himalaya image", doc.pick_visual({"visual": "aerial view himalaya mountains"}, lib, set())["id"] == "a")
    check("no overlap → None (title card)", doc.pick_visual({"visual": "ocean whales"}, lib, set()) is None)
    check("explicit library_id wins", doc.pick_visual({"visual": "x", "library_id": "b"}, lib, set())["id"] == "b")
    check("durations have a floor", doc.scene_durations([0.5, 10.0]) == [doc.MIN_SCENE, 10.45], doc.scene_durations([0.5, 10.0]))
    sc = [{"narration": f"scene number {i} with some words", "on_screen": ("Intro" if i == 0 else "")} for i in range(8)]
    ch = doc.chapters(sc, [6.0] * 8)
    check("chapters start at 0:00, ≥10 s apart, titles from on_screen/narration", ch and ch[0] == (0.0, "Intro") and all(b[0] - a[0] >= 10 for a, b in zip(ch, ch[1:])), ch)
    check("too short for 3 chapters → none", doc.chapters(sc[:3], [3.0] * 3) == [])
    text = doc.description("My Film", ch, ["scene 2: someone (Pixabay) https://x"])
    check("description has 0:00 line, credits and the AI note", "0:00 Intro" in text and "Footage credits:" in text and "AI voice" in text, text)
    text2 = doc.description("My Film", ch, [], [{"title": "Himalaya", "url": "https://en.wikipedia.org/wiki/Himalayas"}])
    check("description lists Wikipedia sources with CC BY-SA", "CC BY-SA" in text2 and "wikipedia.org/wiki/Himalayas" in text2, text2)
    urls = []

    def wiki(url):
        urls.append(url)
        if "hi.wikipedia" in url:
            raise OSError("down")
        return {"query": {"pages": {"1": {"title": "Himalayas", "fullurl": "https://en.wikipedia.org/wiki/Himalayas", "index": 1,
                                           "extract": "The Himalayas is a mountain range in Asia. " * 5},
                                   "2": {"title": "Tiny", "fullurl": "x", "index": 2, "extract": "short"}}}}
    r = doc.research("Himalaya", "hi", wiki)
    check("research: hi fails → falls back to en, drops tiny extracts", len(r) == 1 and r[0]["title"] == "Himalayas" and len(urls) == 2, (r, urls))
    check("research: total failure → []", doc.research("x", "en", lambda u: (_ for _ in ()).throw(OSError("no"))) == [])
    from vividora.engine import llm
    seen = {}
    old_av, old_ask = llm.available, llm.ask_json
    llm.available = lambda: "gemini"
    llm.ask_json = lambda prompt, **k: (seen.setdefault("p", prompt), {"title": "T", "scenes": [{"narration": "one"}, {"narration": "two"}]})[1]
    try:
        res = doc.plan("Himalaya", language="en", http_json=wiki)
        check("plan: facts + only-from-facts rule in prompt, sources returned",
              "REFERENCE FACTS" in seen["p"] and "ONLY from the reference facts" in seen["p"] and res["sources"][0]["title"] == "Himalayas", (seen["p"][:200], res))
        seen.clear()
        res = doc.plan("Himalaya", language="en", ground=False, http_json=wiki)
        check("plan ground=False: no facts, no sources", "REFERENCE FACTS" not in seen["p"] and res["sources"] == [], res)
    finally:
        llm.available, llm.ask_json = old_av, old_ask
    calls = []

    def fake(url):
        calls.append(url)
        if "/videos/" in url:
            return {"hits": []}
        return {"hits": [{"largeImageURL": "https://cdn.pixabay.com/x.jpg", "user": "bob", "pageURL": "https://pixabay.com/p/1", "id": 1}]}
    cands = doc.stock_candidates("snow peaks", "KEY", fake)
    check("no videos → falls back to a photo", len(cands) == 1 and cands[0]["kind"] == "image" and len(calls) == 2, (cands, calls))
    cands = doc.stock_candidates("snow", "KEY", lambda u: {"hits": [{"videos": {"medium": {"url": "https://cdn.pixabay.com/v.mp4"}}, "user": "a", "id": 2}]})
    check("videos found → videos only", len(cands) == 1 and cands[0]["kind"] == "broll", cands)
    tmp = Path(tempfile.mkdtemp(prefix="doc_u_"))
    try:
        size = (640, 360)
        card = doc.title_card("हिमालय — दुनिया की छत", tmp / "c.png", size, 1)
        check("title card (Devanagari) written", card.exists() and card.stat().st_size > 2000)
        c1 = doc.render_scene(card, "image", 3.0, tmp / "c1.mp4", size, 0)
        c2 = doc.render_scene(card, "image", 2.8, tmp / "c2.mp4", size, 1)
        kinds, d, st = probe(c1)
        check("image clip: 3.0 s video, right size", kinds == {"video"} and abs(d - 3.0) < 0.15 and st[0]["width"] == 640, (kinds, d))
        src = tmp / "src.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=1", "-pix_fmt", "yuv420p", str(src)], check=True)
        c3 = doc.render_scene(src, "video", 3.0, tmp / "c3.mp4", size, 2)
        kinds, d, st = probe(c3)
        check("short video loops to 3.0 s, filled to frame", abs(d - 3.0) < 0.15 and st[0]["height"] == 360, (d, st))
        th = doc.make_thumbnail(c1, "हिमालय — दुनिया की छत", tmp / "th.png", at=1.0)
        from PIL import Image
        check("thumbnail written at video size", th.exists() and Image.open(th).size == (640, 360) and not (tmp / "th.frame.png").exists(), th)
        w1, w2 = tmp / "w1.wav", tmp / "w2.wav"
        be = tts.FakeBackend()
        be.synth("one two three", {"gender": "m"}, "en", 1.0, w1)
        be.synth("another line of narration here", {"gender": "f"}, "en", 1.0, w2)
        durs = [3.0, 2.8]
        track = doc.narration_track([w1, w2], durs, tmp / "n.wav")
        check("narration padded to the sum of scene lengths", abs(tts.wav_seconds(track) - 5.8) < 0.05, tts.wav_seconds(track))
        sfx = tmp / "sfx.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=800:duration=0.4", str(sfx)], check=True)
        mus = tmp / "mus.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=2", str(mus)], check=True)
        ass = doc.build_captions(["पहला वाक्य है। दूसरा वाक्य भी है।", "तीसरा scene"], [2.4, 1.0], durs, (640, 360), tmp / "c.ass")
        txt = ass.read_text(encoding="utf-8")
        ev = [l for l in txt.splitlines() if l.startswith("Dialogue")]
        check("captions: one line per phrase, inside scene windows", len(ev) >= 3 and "0:00:03.00" in ev[-1] or "0:00:03.10" in ev[-1], ev)
        capped = doc.assemble([c1, c2], durs, track, tmp / "cap.mp4", work=tmp, captions=ass)
        kinds, d, _ = probe(capped)
        check("assemble with burned captions: audio+video, 5.8 s", kinds == {"video", "audio"} and abs(d - 5.8) < 0.2, (kinds, d))
        for label, kw in (("voice only", {}), ("voice + sfx", {"sfx": sfx}), ("voice + sfx + music (looped)", {"sfx": sfx, "music": mus})):
            out = doc.assemble([c1, c2], durs, track, tmp / f"o_{len(kw)}.mp4", work=tmp, **kw)
            kinds, d, _ = probe(out)
            check(f"assemble {label}: audio+video, 5.8 s", kinds == {"video", "audio"} and abs(d - 5.8) < 0.2, (kinds, d))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ollama():
    """LLM provider 'ollama': a fake local server answers /api/chat; plan() turns its JSON into scenes."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from vividora.engine import documentary as doc
    from vividora.engine import llm
    seen = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            seen["body"] = json.loads(self.rfile.read(int(self.headers["content-length"])))
            reply = {"message": {"content": json.dumps({"title": "हिमालय", "scenes": [
                {"narration": "यह पहला दृश्य है।", "visual": "aerial himalaya"}, {"narration": "यह दूसरा दृश्य है।", "visual": "snow peaks"}]})}}
            b = json.dumps(reply).encode()
            self.send_response(200); self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    old = {k: os.environ.get(k) for k in ("OLLAMA_URL", "OLLAMA_MODEL", "LLM_PROVIDER", "LLM_CACHE")}
    os.environ.update(OLLAMA_URL=f"http://127.0.0.1:{srv.server_port}/", OLLAMA_MODEL="test-model", LLM_CACHE="0")
    try:
        check("ollama is picked when only OLLAMA_URL is set", llm.available() == "ollama", llm.available())
        os.environ["GEMINI_API_KEY"] = "x"
        check("gemini still wins by default", llm.available() == "gemini")
        os.environ["LLM_PROVIDER"] = "ollama"
        check("LLM_PROVIDER forces ollama", llm.available() == "ollama")
        os.environ.pop("GEMINI_API_KEY"); os.environ.pop("LLM_PROVIDER")
        res = doc.plan("Himalaya", minutes=1)
        check("plan() via ollama gives scenes", res and len(res["scenes"]) == 2 and res["title"] == "हिमालय", res)
        check("request went to /api/chat with json format + model", seen.get("path") == "/api/chat" and seen["body"].get("format") == "json"
              and seen["body"].get("model") == "test-model" and seen["body"].get("stream") is False, seen)
    finally:
        srv.shutdown()
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def e2e():
    tmp = Path(tempfile.mkdtemp(prefix="vivi_doc_"))
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    env = {**os.environ, "DATA_ROOT": str(tmp / "data"), "MEDIA_ROOT": str(tmp / "media"), "ADMIN_PASSWORD": "test-pass-123",
           "SECRET_KEY": "t", "WEB_DIST": str(tmp / "web"), "TRIPOSR_URL": "http://127.0.0.1:9", "VIVIDORA_TTS": "fake"}
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "vividora.app:app", "--port", str(port), "--log-level", "warning"],
                           cwd=str(HERE), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}/api"

    def call(method, path, body=None, token=None, raw=False):
        h = {"content-type": "application/json"} if body is not None else {}
        if token:
            h["authorization"] = f"Bearer {token}"
        req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                blob = r.read()
                return r.status, (blob if raw else json.loads(blob or b"null"))
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
        tok = call("POST", "/auth/login", {"email": "admin@vividora.local", "password": "test-pass-123"})[1]["token"]
        key = call("POST", "/keys", {"name": "t"}, tok)[1]["key"]
        st, r = call("POST", "/v1/documentary/plan", {"topic": "Himalaya"}, key)
        check("plan from topic without LLM key → 409 with the way out", st == 409 and "script" in json.dumps(r, ensure_ascii=False), (st, r))
        st, r = call("POST", "/v1/documentary/plan", {"script": "पहला भाग बहुत लंबा नहीं है।\n\nदूसरा भाग भी छोटा है।\n\nतीसरा और आख़िरी भाग।"}, key)
        check("plan from own script", st == 200 and len(r["scenes"]) == 3 and r["source"] == "script", (st, r))
        scenes = r["scenes"]
        st, r2 = call("POST", "/v1/documentary/build", {"scenes": []}, key)
        check("build without scenes → 422", st == 422, (st, r2))
        st, r2 = call("POST", "/v1/documentary/build", {"scenes": scenes, "orientation": "tall"}, key)
        check("bad orientation → 422", st == 422, (st, r2))
        st, r2 = call("POST", "/v1/documentary/build", {"scenes": scenes, "title": "Test डॉक्यूमेंट्री", "orientation": "portrait", "voice": "hi_rohit_deep"}, key)
        check("build accepted (202 + job_id)", st == 202 and r2.get("job_id"), (st, r2))
        jid = r2["job_id"]
        st, pv = call("POST", "/documentary/preview", {"scenes": scenes}, tok)
        check("preview: one entry per scene, no stock key", st == 200 and len(pv["matches"]) == 3 and pv["has_stock"] is False, (st, pv))
        st, again = call("POST", "/v1/documentary/build", {"scenes": scenes}, key)
        check("second build while running → 429", st == 429, (st, again))
        t0, j = time.time(), None
        while time.time() - t0 < 240:
            st, j = call("GET", f"/v1/jobs/{jid}", None, key)
            if j.get("status") in ("done", "failed"):
                break
            time.sleep(2)
        check("job finishes done", j and j.get("status") == "done", j)
        if j and j.get("status") == "done":
            f = j["file"]
            st, blob = call("GET", f"/v1/files/{f['id']}", None, key, raw=True)
            p = tmp / "out.mp4"
            p.write_bytes(blob)
            kinds, d, streams = probe(p)
            vs = next(s for s in streams if s["codec_type"] == "video")
            check("downloaded MP4 has audio+video, portrait", kinds == {"video", "audio"} and vs["height"] > vs["width"], (kinds, vs))
            check("length = sum of scene lengths (≥ 3×2.8 s)", d >= 8.3, d)
            st, jj = call("GET", f"/documentary/{jid}", None, tok)
            check("editor status route agrees", st == 200 and jj["status"] == "done" and jj["progress"] == 100, jj)
            check("job result carries the YouTube description (title + AI note)", "Test डॉक्यूमेंट्री" in (jj.get("description") or "") and "AI voice" in jj["description"], jj.get("description"))
            th = jj.get("thumbnail")
            check("job result carries a thumbnail library item", bool(th) and th.get("kind") == "image", th)
        st, lib = call("GET", "/library?kind=broll", None, tok)
        items = lib if isinstance(lib, list) else lib.get("items", [])
        check("saved in Library with tags", any("documentary" in (i.get("tags") or "") for i in items), items[:2])
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except subprocess.TimeoutExpired:
            srv.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    units()
    ollama()
    e2e()
    print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAILED'}")
    sys.exit(1 if fails else 0)
