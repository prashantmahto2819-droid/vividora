"""Transcript on a rented GPU (fal.ai / RunPod serverless): the engine switch, the pieces, the two request shapes and the
joined result — with stand-ins for the services (no network).

    python3 tests/test_cloudasr.py
"""
from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vividora.engine import cloudasr as ca  # noqa: E402

T = Path(tempfile.mkdtemp(prefix="vividora-casr-"))


def env(**kw):
    for k in ("TRANSCRIBE_ENGINE", "FAL_KEY", "RUNPOD_API_KEY", "RUNPOD_WHISPER_ENDPOINT", "TRANSCRIBE_AUTO_MIN"):
        os.environ.pop(k, None)
    os.environ.update({k: str(v) for k, v in kw.items()})


def main() -> None:
    # ---- the switch
    env()
    assert ca.engine(3600) == "local"
    env(TRANSCRIBE_ENGINE="fal")
    assert ca.engine(60) == "local", "no key → stays on this server"
    env(TRANSCRIBE_ENGINE="fal", FAL_KEY="k")
    assert ca.engine(60) == "fal"
    env(TRANSCRIBE_ENGINE="runpod", RUNPOD_API_KEY="k")
    assert ca.engine(60) == "local", "no endpoint → local"
    env(TRANSCRIBE_ENGINE="runpod", RUNPOD_API_KEY="k", RUNPOD_WHISPER_ENDPOINT="abc")
    assert ca.engine(60) == "runpod"
    env(TRANSCRIBE_ENGINE="auto", FAL_KEY="k")
    assert ca.engine(120) == "local" and ca.engine(900) == "fal" and ca.engine(900, window=True) == "local"
    env(TRANSCRIBE_ENGINE="auto", FAL_KEY="k", TRANSCRIBE_AUTO_MIN=1)
    assert ca.engine(120) == "fal"
    env(TRANSCRIBE_ENGINE="auto")
    assert ca.engine(9000) == "local"
    env(TRANSCRIBE_ENGINE="nonsense", FAL_KEY="k")
    assert ca.engine(9000) == "local"
    print("PASS switch: local / fal / runpod / auto, a missing key always falls back to this server")

    # ---- pieces: 16 min → 3 equal pieces of small MP3s
    wav = T / "talk.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=300:d=960:r=16000", "-ac", "1", str(wav)], check=True)
    ps = ca.pieces(wav, T / "p")
    assert len(ps) == 3 and [round(o) for o, _ in ps] == [0, 320, 640], [o for o, _ in ps]
    assert all(p.stat().st_size < 2_000_000 for _, p in ps) and abs(ca._duration(ps[0][1]) - 320) < 1
    assert len(ca.pieces(wav, T / "w", window=(100.0, 130.0))) == 1 and round(ca.pieces(wav, T / "w", window=(100.0, 130.0))[0][0]) == 100
    print("PASS pieces: equal parts, small files, a window gives one part at its own offset")

    # ---- fal: request shape, queue polling, words joined on one clock
    env(TRANSCRIBE_ENGINE="fal", FAL_KEY="fal-secret")
    seen = []

    def fal(method, url, body, headers):
        seen.append((method, url, body, headers))
        if method == "POST":
            assert url == "https://queue.fal.run/fal-ai/whisper" and headers["Authorization"] == "Key fal-secret"
            assert body["chunk_level"] == "word" and body["language"] == "hi" and body["task"] == "transcribe" and body["prompt"] == "Vividora"
            assert body["audio_url"].startswith("data:audio/mpeg;base64,") and len(base64.b64decode(body["audio_url"].split(",", 1)[1])) > 1000
            n = sum(1 for s in seen if s[0] == "POST")
            return {"status_url": f"https://q/{n}/status", "response_url": f"https://q/{n}"}
        if url.endswith("/status"):
            return {"status": "COMPLETED"}
        n = int(url.rsplit("/", 1)[1])
        return {"text": "x", "inferred_languages": ["hi"], "chunks": [
            {"timestamp": [1.0, 1.4], "text": f" नमस्ते{n}"}, {"timestamp": [1.5, 2.0], "text": "दोस्तों।"},
            {"timestamp": [5.0, 5.5], "text": "आज"}, {"timestamp": [5.6, None], "text": "podcast"}, {"timestamp": [None, None], "text": "junk"}]}
    prog = []
    tr = ca.transcribe(wav, engine_name="fal", language="hi", prompt="Vividora", work=T / "f", call=fal, poll_s=0, on_progress=lambda f, m: prog.append((round(f, 2), m)))
    assert tr["engine"] == "fal" and tr["model"] == "fal-whisper" and tr["language"] == "hi" and abs(tr["audio_seconds"] - 960) < 3
    starts = [s["start"] for s in tr["segments"]]
    assert starts == [1.0, 5.0, 321.0, 325.0, 641.0, 645.0], starts                       # 3 pieces × 2 lines, each on the recording's clock
    first = tr["segments"][0]
    assert first["text"] == "नमस्ते1 दोस्तों।" and [w["w"] for w in first["words"]] == ["नमस्ते1", "दोस्तों।"] and first["words"][1]["end"] == 2.0
    assert tr["segments"][1]["words"][1]["end"] > tr["segments"][1]["words"][1]["start"]  # a missing end time is filled
    assert sum(1 for s in seen if s[0] == "POST") == 3 and len(prog) == 3 and "1/3" in prog[0][1]
    print("PASS fal: 3 pieces sent inline, polled, 6 lines on one clock, words with times")

    # ---- runpod: /run + /status, word_timestamps, failure is a readable error
    env(TRANSCRIBE_ENGINE="runpod", RUNPOD_API_KEY="rp-secret", RUNPOD_WHISPER_ENDPOINT="ep123")
    calls = []

    def rp(method, url, body, headers):
        calls.append((method, url))
        assert headers["Authorization"] == "Bearer rp-secret"
        if method == "POST":
            assert url == "https://api.runpod.ai/v2/ep123/run" and body["input"]["word_timestamps"] is True and body["input"]["model"] == "large-v3"
            assert len(base64.b64decode(body["input"]["audio_base64"])) > 1000 and body["input"]["language"] == "hi"
            return {"id": "job1", "status": "IN_QUEUE"}
        return {"status": "COMPLETED", "output": {"detected_language": "hi", "word_timestamps": [{"word": " हेलो", "start": 0.5, "end": 0.9}, {"word": "world", "start": 1.0, "end": 1.4}]}}
    tr = ca.transcribe(wav, engine_name="runpod", language="hi", work=T / "r", call=rp, poll_s=0, window=(100.0, 130.0))
    assert [s["start"] for s in tr["segments"]] == [100.5] and tr["segments"][0]["text"] == "हेलो world" and calls[1][1].endswith("/status/job1")

    def rp_fail(method, url, body, headers):
        return {"id": "j"} if method == "POST" else {"status": "FAILED", "error": "CUDA out of memory"}
    try:
        ca.transcribe(wav, engine_name="runpod", work=T / "r2", call=rp_fail, poll_s=0, window=(0.0, 20.0))
        raise SystemExit("a failed job must raise")
    except RuntimeError as e:
        assert "CUDA out of memory" in str(e)
    env(TRANSCRIBE_ENGINE="fal")
    try:
        ca.transcribe(wav, engine_name="fal", work=T / "x")
        raise SystemExit("no key must raise")
    except RuntimeError as e:
        assert "key" in str(e)
    print("PASS runpod: /run + /status, a window keeps its offset, failures and a missing key are readable errors")

    # ---- lines: pauses, punctuation and length start a new one
    ws = [("a", 0, .3), ("b", .4, .7), ("c।", .8, 1.1), ("d", 1.2, 1.5), ("e", 3.0, 3.3)] + [(f"w{i}", 4 + i * .3, 4.2 + i * .3) for i in range(20)]
    sg = ca.to_segments(ws)
    assert [s["text"].split()[0] for s in sg][:3] == ["a", "d", "e"] and all(len(s["words"]) <= 14 for s in sg) and ca.to_segments([]) == []
    print("PASS lines: a pause, sentence end or 14 words starts a new line")


if __name__ == "__main__":
    main()
    print("ALL PASS")
