"""Vividora GPU worker — runs on the Windows PC with the NVIDIA card.

It only does `transcribe` jobs (Hindi speech → words with timestamps) using
faster-whisper on CUDA, and sends the result back to the Vividora API in the
Ubuntu VM. Everything else (cutting, captions, render) happens in the VM.

Setup: run install.ps1 once, fill gpu-worker.env, then run.ps1 (or let Task
Scheduler start it at logon — install.ps1 offers that).
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
# the shared client + transcriber live in the server package; copied here by install.ps1
sys.path.insert(0, str(HERE / "lib"))

from vividora_client import ApiClient, run_loop  # noqa: E402
from vividora_transcribe import transcribe_file  # noqa: E402


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))


def gpu_info() -> dict:
    try:
        import torch  # type: ignore
        if torch.cuda.is_available():
            return {"gpu": torch.cuda.get_device_name(0),
                    "vram_gb": round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1)}
    except Exception:
        pass
    try:
        import ctranslate2  # type: ignore
        return {"gpu": "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"}
    except Exception:
        return {"gpu": "unknown"}


def handle(client: ApiClient, job: dict, project: dict, assets: list[dict]) -> dict:
    audio_asset = next((a for a in assets if a["kind"] == "audio_asr"), None)
    if audio_asset is None:
        raise ValueError("project has no audio_asr file")
    with tempfile.TemporaryDirectory(prefix="vividora_gpu_") as td:
        audio = client.download(audio_asset["id"], Path(td) / "audio.wav")

        def progress(frac: float, msg: str) -> None:
            if not client.heartbeat(job["id"], frac * 100, msg):
                raise RuntimeError("job cancelled")

        transcript = transcribe_file(audio, language=job["payload"].get("language", "hi"),
                                     on_progress=progress)
    return {"transcript": transcript}


def main() -> None:
    load_env(HERE / "gpu-worker.env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    base = os.environ.get("API_URL")
    token = os.environ.get("WORKER_TOKEN")
    if not base or not token:
        print("gpu-worker.env में API_URL और WORKER_TOKEN भरें (देखें gpu-worker.env.example)")
        sys.exit(2)
    os.environ.setdefault("WHISPER_MODEL", "large-v3")
    os.environ.setdefault("WHISPER_DEVICE", "cuda")
    os.environ.setdefault("WHISPER_COMPUTE", "float16")
    os.environ.setdefault("WHISPER_CACHE", str(HERE / "models"))
    name = os.environ.get("WORKER_NAME", f"gpu@{socket.gethostname()}")
    info = {**gpu_info(), "model": os.environ["WHISPER_MODEL"]}
    logging.getLogger("vividora.worker").info("GPU worker %s → %s · %s", name, base, info)
    run_loop(ApiClient(base, token, name), ["transcribe"], handle,
             poll=float(os.environ.get("POLL_SECONDS", "4")), info=info)


if __name__ == "__main__":
    main()
