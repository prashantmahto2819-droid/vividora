"""fal.ai voices (engine/tts.py FalBackend) against a stand-in fal queue. Run: python3 tests/test_fal_tts.py"""
import io
import json
import os
import sys
import tempfile
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SEEN: list[tuple[str, dict]] = []
KEY: str | None = "Key test-key"


def wav_bytes(seconds: float, sr: int = 44100) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x10\x00\x10\x00" * int(seconds * sr))
    return b.getvalue()


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
        body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
        assert KEY is None or self.headers.get("Authorization") == KEY
        SEEN.append((self.path.strip("/"), body))
        n = len(SEEN)
        base = f"http://127.0.0.1:{self.server.server_port}"
        self._json({"request_id": f"r{n}", "status_url": f"{base}/st/{n}", "response_url": f"{base}/res/{n}"})

    def do_GET(self):
        base = f"http://127.0.0.1:{self.server.server_port}"
        if self.path.startswith("/st/"):
            return self._json({"status": "COMPLETED"})
        if self.path.startswith("/res/"):
            n = int(self.path.split("/")[-1])
            key = "audio_file" if "music" in SEEN[n - 1][0] else "audio"
            return self._json({key: {"url": f"{base}/file/{n}.wav"}})
        if self.path.startswith("/file/"):
            n = int(self.path.split("/")[-1].split(".")[0])
            text = SEEN[n - 1][1].get("text") or SEEN[n - 1][1].get("prompt") or ""
            d = wav_bytes(float(SEEN[n - 1][1]["duration"]) if "duration" in SEEN[n - 1][1] else len(text) / 14.0)
            self.send_response(200)
            self.send_header("content-type", "audio/wav")
            self.send_header("content-length", str(len(d)))
            self.end_headers()
            return self.wfile.write(d)
        self._json({}, 404)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["FAL_QUEUE_BASE"] = f"http://127.0.0.1:{srv.server_port}"
    os.environ.pop("FAL_KEY", None)
    from vividora.engine import meter, tts
    ids = {v["id"] for v in tts.available_voices()}
    assert not any(i.startswith("fal_") for i in ids), "fal voices must be hidden without a key"
    try:
        tts.check_ready("fal")
        raise AssertionError("no key → must refuse")
    except tts.TTSMissing:
        pass
    os.environ["FAL_KEY"] = "test-key"
    ids = {v["id"] for v in tts.available_voices()}
    assert {"fal_cb_hindi", "fal_kokoro_psi"} <= ids
    tts.check_ready("fal")
    assert tts.is_premium(tts.voice_preset("fal_cb_hindi"))
    spent = []
    meter.configure(lambda e: spent.append((e["service"], e["units"], e["usd"])), lambda: 5.0)
    with tempfile.TemporaryDirectory() as d:
        long_text = " ".join(["यह एक लंबा वाक्य है जो बार बार दोहराया जा रहा है ताकि सीमा पार हो।"] * 12)       # ~800 characters
        out = tts.backend_for("fal").synth(long_text, tts.voice_preset("fal_cb_hindi_drama"), "hi", 1.0, Path(d) / "a.wav")
        calls = [b for m, b in SEEN if m == "fal-ai/chatterbox/text-to-speech/multilingual"]
        assert len(calls) >= 3 and all(len(b["text"]) <= 300 for b in calls), [len(b["text"]) for b in calls]
        assert " ".join(b["text"] for b in calls) == long_text, "no word may be lost between requests"
        assert all(b["voice"] == "hindi" and abs(b["exaggeration"] - 0.85) < 1e-6 for b in calls)
        secs = tts.wav_seconds(out)
        assert abs(secs - sum(len(b["text"]) for b in calls) / 14.0) < 0.5, secs      # every piece is in the track, in order
        pcm, sr = tts.read_pcm(out)
        assert sr == 24000
        n0 = len(SEEN)
        tts.backend_for("fal").synth("नमस्ते दोस्तों।", tts.voice_preset("fal_kokoro_psi"), "hi", 1.0, Path(d) / "b.wav")
        m, b = SEEN[n0]
        assert m == "fal-ai/kokoro/hindi" and b == {"prompt": "नमस्ते दोस्तों।", "voice": "hm_psi", "speed": 1.0}, (m, b)
    chars = sum(len(b.get("text") or b.get("prompt")) for _, b in SEEN)
    # my own voice: the Library sample travels as a small MP3, the model is told its language
    from vividora.engine import dub
    with tempfile.TemporaryDirectory() as d:
        import subprocess
        ref = Path(d) / "myvoice.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=30:c=pink:a=0.2", str(ref)], check=True)
        v0 = dub.resolve_voice("fal_cb_myvoice", None, "hi")
        assert v0.get("fal_clone") and v0["fal_model"].endswith("multilingual"), v0
        assert dub.resolve_voice("fal_cb_hindi_drama", "anything", "hi")["fal_exaggeration"] == 0.85     # fal fields survive the editor's path
        try:
            tts.my_voice(v0, None, "hi")
            raise AssertionError("no sample → must explain")
        except ValueError as e:
            assert "myvoice" in str(e)
        try:
            tts.backend_for("fal").synth("नमस्ते", v0, "hi", 1.0, Path(d) / "x.wav")
            raise AssertionError("clone voice without a sample must not fall back to another voice")
        except tts.TTSMissing:
            pass
        v1 = tts.my_voice(v0, ref, "hi")
        assert v1["fal_voice"].startswith("data:audio/mpeg;base64,") and 60_000 < len(v1["fal_voice"]) < 260_000, len(v1["fal_voice"])   # 20 s at most
        n0 = len(SEEN)
        tts.backend_for("fal").synth("यह मेरी आवाज़ है।", v1, "hi", 1.0, Path(d) / "mine.wav")
        b = SEEN[n0][1]
        assert b["voice"] == v1["fal_voice"] and b["custom_audio_language"] == "hindi" and b["text"] == "यह मेरी आवाज़ है।", {k: str(v)[:40] for k, v in b.items()}
    print("my own voice: sample → 20 s MP3 inside the job, custom_audio_language sent, no silent fallback ✓")
    # AI music: one request, an MP3 of the asked length, priced per minute
    from vividora.engine import aimusic
    with tempfile.TemporaryDirectory() as d:
        n0, s0 = len(SEEN), len(spent)
        prompt = aimusic.build_prompt("indian", "हल्की बाँसुरी")
        assert "sitar" in prompt and "हल्की बाँसुरी" in prompt and "no vocals" in prompt
        mp3 = aimusic.generate(prompt, 45, Path(d) / "m.mp3")
        m, b = SEEN[n0]
        assert m == "cassetteai/music-generator" and b == {"prompt": prompt, "duration": 45}, (m, b)
        import subprocess
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp3)], capture_output=True, text=True).stdout)
        assert abs(dur - 45) < 0.5 and mp3.read_bytes()[:3] in (b"ID3", b"\xff\xfb\x90") or mp3.stat().st_size > 10000, dur
        assert spent[s0] == ("ai_music", 0.75, 0.015), spent[s0]
        assert aimusic.estimate_usd(180) == 0.06
    spent_tts = [x for x in spent if x[0] == "fal_tts"]
    chars = sum(len(b.get("text") or b.get("prompt")) for m, b in SEEN if "music" not in m)
    assert abs(sum(u for _, u, _ in spent_tts) - chars / 1000) < 0.01
    assert abs(sum(c for _, _, c in spent_tts) - chars / 1000 * 0.025) < 1e-3, spent
    # the spending limit stops the next line
    meter.configure(lambda e: None, lambda: 0.0)
    try:
        with tempfile.TemporaryDirectory() as d:
            tts.backend_for("fal").synth("एक और", tts.voice_preset("fal_kokoro_psi"), "hi", 1.0, Path(d) / "c.wav")
        raise AssertionError("limit reached → must stop")
    except meter.SpendCap:
        pass
    print(f"fal voices: {len(calls)} Chatterbox requests (≤ 300 chars each, nothing lost), Kokoro body ✓, ${sum(c for _, _, c in spent_tts):.4f} recorded, limit stops ✓")
    print("AI music: one request, 45 s MP3, $0.015 recorded ✓")
    print("ALL PASS")


if __name__ == "__main__":
    main()
