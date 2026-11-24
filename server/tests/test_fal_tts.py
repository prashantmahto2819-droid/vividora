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
        assert self.headers.get("Authorization") == "Key test-key"
        SEEN.append((self.path.strip("/"), body))
        n = len(SEEN)
        base = f"http://127.0.0.1:{self.server.server_port}"
        self._json({"request_id": f"r{n}", "status_url": f"{base}/st/{n}", "response_url": f"{base}/res/{n}"})

    def do_GET(self):
        base = f"http://127.0.0.1:{self.server.server_port}"
        if self.path.startswith("/st/"):
            return self._json({"status": "COMPLETED"})
        if self.path.startswith("/res/"):
            return self._json({"audio": {"url": f"{base}/file/{self.path.split('/')[-1]}.wav"}})
        if self.path.startswith("/file/"):
            n = int(self.path.split("/")[-1].split(".")[0])
            text = SEEN[n - 1][1].get("text") or SEEN[n - 1][1].get("prompt") or ""
            d = wav_bytes(len(text) / 14.0)
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
    assert all(k == "fal_tts" for k, _, _ in spent) and abs(sum(u for _, u, _ in spent) - chars / 1000) < 0.01
    assert abs(sum(c for _, _, c in spent) - chars / 1000 * 0.025) < 1e-3, spent
    # the spending limit stops the next line
    meter.configure(lambda e: None, lambda: 0.0)
    try:
        with tempfile.TemporaryDirectory() as d:
            tts.backend_for("fal").synth("एक और", tts.voice_preset("fal_kokoro_psi"), "hi", 1.0, Path(d) / "c.wav")
        raise AssertionError("limit reached → must stop")
    except meter.SpendCap:
        pass
    print(f"fal voices: {len(calls)} Chatterbox requests (≤ 300 chars each, nothing lost), Kokoro body ✓, ${sum(c for _, _, c in spent):.4f} recorded, limit stops ✓")
    print("ALL PASS")


if __name__ == "__main__":
    main()
