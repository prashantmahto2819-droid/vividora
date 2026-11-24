"""Speech → words on somebody else's GPU, paid only while it runs.

Three places can make the transcript; `engine()` says which one a job uses (TRANSCRIBE_ENGINE, set in the dashboard):

  local   this server's own CPU / GPU (worker/transcribe.py, faster-whisper) — free, slow on a CPU
  fal     fal.ai Whisper — billed per second of GPU time, nothing to keep running
  runpod  a RunPod *serverless* endpoint running the stock "Faster Whisper" worker — starts for the job, stops after
  auto    local for short recordings, the cloud for long ones (TRANSCRIBE_AUTO_MIN minutes, default 8)

The recording is cut into pieces of a few minutes (small MP3s, sent inline — no storage account, no public URL needed),
each piece comes back with word times, and the pieces are joined on one clock. The result has the same shape as the
local transcriber's: {language, model, segments: [{start, end, text, words: [{w, start, end, p}]}]}.

Network calls go through `call` so tests can stand in for the services.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

ENGINES = {"local": "यह server (Z440) — free", "fal": "fal.ai Whisper — हर काम के पैसे", "runpod": "RunPod serverless — हर काम के पैसे",
           "auto": "Auto — छोटी recording यहीं, लंबी cloud पर"}
CHUNK_SECONDS = 420.0          # 7 min of 32 kbps mono MP3 ≈ 1.7 MB → fits every request-size limit when sent inline


def engine_setting() -> str:
    e = (os.getenv("TRANSCRIBE_ENGINE") or "local").strip().lower()
    return e if e in ENGINES else "local"


def cloud_ready(name: str) -> bool:
    if name == "fal":
        return bool(os.getenv("FAL_KEY"))
    if name == "runpod":
        return bool(os.getenv("RUNPOD_API_KEY") and (os.getenv("RUNPOD_WHISPER_ENDPOINT") or os.getenv("RUNPOD_WHISPER_URL")))
    return False


def first_cloud() -> str | None:
    return next((n for n in ("fal", "runpod") if cloud_ready(n)), None)


def engine(duration: float | None = None, *, window: bool = False) -> str:
    """Which engine THIS job uses → "local" | "fal" | "runpod". A setting whose key is missing falls back to local."""
    want = engine_setting()
    if want in ("fal", "runpod"):
        return want if cloud_ready(want) else "local"
    if want == "auto":
        cloud = first_cloud()
        try:
            limit = float(os.getenv("TRANSCRIBE_AUTO_MIN") or 8) * 60
        except ValueError:
            limit = 480.0
        if cloud and not window and float(duration or 0) >= limit:
            return cloud
    return "local"


# ------------------------------------------------------------------ audio pieces
def _duration(audio: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def pieces(audio: Path, work: Path, *, window: tuple[float, float] | None = None, chunk: float = CHUNK_SECONDS) -> list[tuple[float, Path]]:
    """[(offset seconds, small mp3)] covering the recording (or just `window`)."""
    work.mkdir(parents=True, exist_ok=True)
    total = _duration(audio)
    a, b = (max(0.0, window[0]), min(total or window[1], window[1])) if window else (0.0, total)
    if b - a <= 0.05:
        return []
    n = max(1, int((b - a + chunk - 1) // chunk))
    step = (b - a) / n                                   # equal pieces: no tiny tail that Whisper would hallucinate on
    out = []
    for i in range(n):
        off = a + i * step
        dst = work / f"asr_{i:03d}.mp3"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{off:.3f}", "-t", f"{step:.3f}", "-i", str(audio), "-vn", "-ac", "1", "-ar", "16000",
                            "-c:a", "libmp3lame", "-b:a", "32k", str(dst)], capture_output=True, text=True)
        if r.returncode != 0 or not dst.exists() or dst.stat().st_size < 200:
            raise RuntimeError("audio का हिस्सा नहीं बना: " + r.stderr[-200:])
        out.append((off, dst))
    return out


# ------------------------------------------------------------------ http
def _http(method: str, url: str, body: dict | None, headers: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "Vividora/1.0", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}") from None


def _poll(get: Callable[[], dict], done, failed, *, poll_s: float, max_wait: float, what: str) -> dict:
    t0 = time.time()
    while True:
        s = get()
        if done(s):
            return s
        if failed(s) or time.time() - t0 > max_wait:
            raise RuntimeError(f"{what}: {str(s.get('error') or s.get('status') or 'timeout')[:200]}")
        time.sleep(poll_s)


def fal_run(model: str, body: dict, *, call=None, poll_s: float = 1.5, max_wait: float = 900) -> dict:
    """One request to a fal.ai model through its queue → the model's answer (used for the transcript and the voices).
    The GPU there is billed only while this request runs."""
    call = call or _http
    h = {"Authorization": f"Key {os.environ['FAL_KEY']}"}
    base = os.getenv("FAL_QUEUE_BASE", "https://queue.fal.run")
    job = call("POST", f"{base}/{model.strip('/')}", body, h)
    su, ru = job.get("status_url"), job.get("response_url")
    if not su or not ru:
        if job.get("request_id") is None and job:      # answered at once (a stand-in server, or fal.run)
            return job
        raise RuntimeError("fal: " + json.dumps(job)[:200])
    _poll(lambda: call("GET", su, None, h), lambda s_: s_.get("status") == "COMPLETED", lambda s_: s_.get("status") in ("FAILED", "ERROR"),
          poll_s=poll_s, max_wait=max_wait, what="fal")
    return call("GET", ru, None, h)


# ------------------------------------------------------------------ the two services → [(word, start, end)]
def _fal_piece(mp3: Path, language: str | None, prompt: str | None, call, poll_s: float, max_wait: float) -> tuple[list[tuple[str, float, float]], str]:
    model = (os.getenv("FAL_WHISPER_MODEL") or "fal-ai/whisper").strip("/")
    body = {"audio_url": "data:audio/mpeg;base64," + base64.b64encode(mp3.read_bytes()).decode(), "task": "transcribe", "chunk_level": "word"}
    if language and language != "auto":
        body["language"] = language
    if prompt:
        body["prompt"] = prompt[:400]
    out = fal_run(model, body, call=call, poll_s=poll_s, max_wait=max_wait)
    words = []
    for c in out.get("chunks") or []:
        ts = c.get("timestamp") if isinstance(c, dict) else None
        txt = str((c or {}).get("text") or "").strip()
        if not txt or not isinstance(ts, (list, tuple)) or len(ts) < 2 or ts[0] is None:
            continue
        a = float(ts[0])
        words.append((txt, a, float(ts[1]) if ts[1] is not None else a + 0.3))
    langs = out.get("inferred_languages") or out.get("languages") or []
    return words, (langs[0] if langs else (language or ""))


def _runpod_piece(mp3: Path, language: str | None, prompt: str | None, call, poll_s: float, max_wait: float) -> tuple[list[tuple[str, float, float]], str]:
    h = {"Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}"}
    base = (os.getenv("RUNPOD_WHISPER_URL") or f"https://api.runpod.ai/v2/{os.environ['RUNPOD_WHISPER_ENDPOINT']}").rstrip("/")
    inp = {"audio_base64": base64.b64encode(mp3.read_bytes()).decode(), "model": os.getenv("RUNPOD_WHISPER_MODEL") or "large-v3",
           "word_timestamps": True, "transcription": "plain_text", "enable_vad": True}
    if language and language != "auto":
        inp["language"] = language
    if prompt:
        inp["initial_prompt"] = prompt[:400]
    job = call("POST", f"{base}/run", {"input": inp}, h)
    jid = job.get("id")
    if not jid:
        raise RuntimeError("runpod: " + json.dumps(job)[:200])
    s = job if job.get("status") == "COMPLETED" else _poll(
        lambda: call("GET", f"{base}/status/{jid}", None, h), lambda x: x.get("status") == "COMPLETED",
        lambda x: x.get("status") in ("FAILED", "CANCELLED", "TIMED_OUT"), poll_s=poll_s, max_wait=max_wait, what="runpod")
    out = s.get("output") or {}
    if isinstance(out, list):
        out = out[0] if out else {}
    words = []
    for w in out.get("word_timestamps") or []:
        txt = str(w.get("word") or "").strip()
        if txt and w.get("start") is not None:
            words.append((txt, float(w["start"]), float(w.get("end") if w.get("end") is not None else float(w["start"]) + 0.3)))
    if not words:                                         # an endpoint without word times: spread each segment's words evenly
        for sg in out.get("segments") or []:
            ws = str(sg.get("text") or "").split()
            a, b = float(sg.get("start") or 0), float(sg.get("end") or 0)
            for k, x in enumerate(ws):
                words.append((x, a + (b - a) * k / len(ws), a + (b - a) * (k + 1) / len(ws)))
    return words, str(out.get("detected_language") or language or "")


# ------------------------------------------------------------------ words → lines
def to_segments(words: list[tuple[str, float, float]], *, max_words: int = 14, max_len: float = 7.0, gap: float = 0.7) -> list[dict]:
    """A new line after a pause, after sentence punctuation, or when the line gets long — like Whisper's own segments."""
    segs, cur = [], []

    def flush() -> None:
        if cur:
            segs.append({"start": round(cur[0][1], 3), "end": round(cur[-1][2], 3), "text": " ".join(w[0] for w in cur),
                         "words": [{"w": w[0], "start": round(w[1], 3), "end": round(max(w[2], w[1] + 0.02), 3), "p": 0.9} for w in cur]})
            cur.clear()
    for w in sorted(words, key=lambda x: x[1]):
        if cur and (w[1] - cur[-1][2] > gap or len(cur) >= max_words or w[2] - cur[0][1] > max_len):
            flush()
        cur.append(w)
        if w[0][-1:] in ".?!।॥" and len(cur) >= 3:
            flush()
    flush()
    return segs


def transcribe(audio: Path, *, engine_name: str, language: str | None = "hi", prompt: str | None = None, work: Path | None = None,
               window: tuple[float, float] | None = None, on_progress=None, call=None, poll_s: float = 2.0, max_wait: float = 900.0) -> dict:
    """→ {language, model, segments, engine, audio_seconds, cloud_seconds}. Raises RuntimeError with a readable reason."""
    if engine_name not in ("fal", "runpod"):
        raise RuntimeError("cloud engine: fal | runpod")
    if not cloud_ready(engine_name) and call is None:
        raise RuntimeError(f"{engine_name} की key नहीं डाली है (API & Keys page)")
    import tempfile
    work = work or Path(tempfile.mkdtemp(prefix="vividora-asr-"))
    call = call or _http
    one = _fal_piece if engine_name == "fal" else _runpod_piece
    parts = pieces(audio, work, window=window)
    total = sum(_duration(p) for _, p in parts) or 1.0
    words: list[tuple[str, float, float]] = []
    lang, done, t0 = "", 0.0, time.time()
    for k, (off, mp3) in enumerate(parts):
        if on_progress:
            on_progress(0.03 + 0.9 * done / total, f"{ENGINES[engine_name].split(' — ')[0]}: हिस्सा {k + 1}/{len(parts)}")
        ln = _duration(mp3)
        ws, lg = one(mp3, language, prompt, call, poll_s, max_wait)
        lang = lang or lg
        # a word that starts in the last moment of a piece can spill past it: keep it inside the piece
        words += [(w, off + max(0.0, a), off + min(max(b, a + 0.02), ln + 0.5)) for w, a, b in ws]
        done += ln
    return {"language": lang or (language if language and language != "auto" else "hi"), "model": f"{engine_name}-whisper", "segments": to_segments(words),
            "engine": engine_name, "audio_seconds": round(total, 1), "cloud_seconds": round(time.time() - t0, 1)}
