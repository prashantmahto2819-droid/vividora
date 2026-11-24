"""RunPod public endpoints (engine/runpod.py): voices and AI video against a stand-in server. Run: python3 tests/test_runpod.py"""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_fal_tts import wav_bytes  # noqa: E402

SEEN: list[tuple[str, dict]] = []
POLLS: dict[str, int] = {}
T = Path(tempfile.mkdtemp(prefix="vividora-rp-"))


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        d = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(d)))
        self.end_headers()
        self.wfile.write(d)

    def do_POST(self):
        assert self.headers.get("Authorization") == "Bearer rp-test"
        body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
        model, op = self.path.strip("/").split("/")[-2:]
        assert op == "run" and set(body) == {"input"}, (self.path, body)
        SEEN.append((model, body["input"]))
        self._json({"id": f"j{len(SEEN)}", "status": "IN_QUEUE"})

    def do_GET(self):
        base = f"http://127.0.0.1:{self.server.server_port}"
        parts = self.path.strip("/").split("/")
        if parts[0] == "file":
            n = int(parts[1].split(".")[0])
            model, inp = SEEN[n - 1]
            if model == "p-video":
                d = (T / "v.mp4").read_bytes()
            else:
                d = wav_bytes(len(inp["prompt"]) / 14.0)
            self.send_response(200)
            self.send_header("content-length", str(len(d)))
            self.end_headers()
            return self.wfile.write(d)
        assert self.headers.get("Authorization") == "Bearer rp-test"
        model, _, jid = parts[-3:]
        n = int(jid[1:])
        POLLS[jid] = POLLS.get(jid, 0) + 1
        if POLLS[jid] < 2:
            return self._json({"id": jid, "status": "IN_PROGRESS"})
        inp = SEEN[n - 1][1]
        if inp.get("voice_id") == "Nobody":
            return self._json({"id": jid, "status": "FAILED", "error": "Invalid voice_id"})
        if model == "p-video":
            return self._json({"id": jid, "status": "COMPLETED", "output": {"result": f"{base}/file/{n}.mp4", "cost": 0.02 * inp["duration"]}})
        if model == "chatterbox-turbo":
            return self._json({"id": jid, "status": "COMPLETED", "output": {"audio_url": f"{base}/file/{n}.wav"}})       # no cost in the answer
        return self._json({"id": jid, "status": "COMPLETED", "output": {"audio_url": f"{base}/file/{n}.wav", "cost": round(len(inp["prompt"]) * 0.00005, 6)}})


def main():
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:d=1:r=24", "-pix_fmt", "yuv420p", str(T / "v.mp4")], check=True)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["RUNPOD_API_BASE"] = f"http://127.0.0.1:{srv.server_port}/v2"
    for k in ("RUNPOD_API_KEY", "FAL_KEY", "AI_VIDEO_PROVIDER"):
        os.environ.pop(k, None)
    from vividora.engine import aivideo, dub, meter, runpod, tts
    assert not any(v["engine"] == "runpod" for v in tts.available_voices()) and aivideo.provider() is None
    try:
        tts.check_ready("runpod")
        raise AssertionError("no key → must refuse")
    except tts.TTSMissing:
        pass
    os.environ["RUNPOD_API_KEY"] = "rp-test"
    assert {"rp_mm_wise", "rp_cb_lucy"} <= {v["id"] for v in tts.available_voices()} and aivideo.provider() == "runpod"
    spent = []
    meter.configure(lambda e: spent.append((e["service"], e["units"], e["usd"])), lambda: 5.0)
    orig_sleep = runpod.time.sleep
    runpod.time.sleep = lambda s: orig_sleep(0.01)
    # MiniMax: body as documented, the answer's own cost is recorded; the editor's voice path keeps the fields
    v = dub.resolve_voice("rp_mm_happy", None, "hi")
    assert v["rp_model"] == "minimax-speech-02-hd" and v["rp_emotion"] == "happy", v
    text = "नमस्ते दोस्तों, आज हम एक नई बात करेंगे।"
    out = tts.backend_for("runpod").synth(text, v, "hi", 1.0, T / "a.wav")
    m, b = SEEN[-1]
    assert m == "minimax-speech-02-hd" and b == {"prompt": text, "voice_id": "Friendly_Person", "speed": 1, "emotion": "happy"}, (m, b)
    assert abs(tts.wav_seconds(out) - len(text) / 14) < 0.2 and tts.read_pcm(out)[1] == 24000
    assert spent[-1][0] == "runpod_tts" and abs(spent[-1][2] - len(text) * 0.00005) < 1e-5, spent[-1]
    # Chatterbox Turbo: priced by the seconds of audio when the answer names no cost
    out = tts.backend_for("runpod").synth("Hello friends, welcome back to the channel.", tts.voice_preset("rp_cb_ethan"), "en", 1.0, T / "b.wav")
    m, b = SEEN[-1]
    assert m == "chatterbox-turbo" and b == {"prompt": "Hello friends, welcome back to the channel.", "voice": "ethan", "format": "wav"}, (m, b)
    secs = tts.wav_seconds(out)
    assert spent[-1][0] == "runpod_tts_sec" and abs(spent[-1][2] - secs * 0.001) < 1e-4, (spent[-1], secs)
    # RunPod's own error text reaches the user
    try:
        tts.backend_for("runpod").synth("hello", {"engine": "runpod", "rp_model": "minimax-speech-02-hd", "rp_voice": "Nobody"}, "en", 1.0, T / "c.wav")
        raise AssertionError("a failed job must raise")
    except RuntimeError as e:
        assert "Invalid voice_id" in str(e), e
    n_spent = len(spent)
    # AI video: p-video from the description, in the picture's shape; provider switch
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=360x640", "-frames:v", "1", str(T / "tall.png")], check=True)
    os.environ["AI_VIDEO_SECONDS"] = "4"
    clip = aivideo.animate(T / "tall.png", "a river at sunrise, slow camera move", T / "clip.mp4")
    m, b = SEEN[-1]
    assert m == "p-video" and b == {"prompt": "a river at sunrise, slow camera move", "duration": 4, "resolution": "720p", "fps": 24,
                                    "aspect_ratio": "9:16", "save_audio": False}, (m, b)
    assert clip.exists() and clip.stat().st_size > 500 and len(spent) == n_spent + 1 and spent[-1] == ("runpod_video", 4, 0.08), spent[-1]
    assert aivideo.estimate_usd(2) == 0.16
    os.environ["FAL_KEY"] = "x"
    assert aivideo.provider() == "fal"                      # both keys: fal unless the switch says RunPod
    os.environ["AI_VIDEO_PROVIDER"] = "runpod"
    assert aivideo.provider() == "runpod"
    os.environ["AI_VIDEO_PROVIDER"] = "fal"
    os.environ.pop("FAL_KEY")
    assert aivideo.provider() is None                       # the chosen one has no key: nothing is sent elsewhere by surprise
    os.environ.pop("AI_VIDEO_PROVIDER")
    # the spending limit stops RunPod too
    meter.configure(lambda e: None, lambda: 0.0)
    for fn in (lambda: tts.backend_for("runpod").synth("hi", tts.voice_preset("rp_mm_wise"), "hi", 1.0, T / "d.wav"),
               lambda: aivideo.animate(T / "tall.png", "x", T / "e.mp4")):
        try:
            fn()
            raise AssertionError("limit reached → must stop")
        except meter.SpendCap:
            pass
    print("RunPod: MiniMax + Chatterbox voices (documented bodies, cost recorded), p-video clip in the picture's shape, provider switch, limit ✓")
    print("ALL PASS")


if __name__ == "__main__":
    main()
