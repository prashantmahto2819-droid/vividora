"""The CPU worker: prepare, autocut, render. Runs in Docker next to the API,
or anywhere with ffmpeg (`python -m vividora.worker.cpu`).

With TRANSCRIBE_LOCAL=1 it also transcribes on CPU using faster-whisper
(slow, but works when the Windows GPU worker is off).
"""

from __future__ import annotations

import logging
import os
import socket
import tempfile
from pathlib import Path

from ..engine import autocut, ffmpeg, prepare, render
from ..engine.presets import caption_style, platform
from .client import ApiClient, run_loop

log = logging.getLogger("vividora.worker")


def _asset(assets: list[dict], kind: str) -> dict | None:
    return next((a for a in assets if a["kind"] == kind), None)


def _fetch(client: ApiClient, assets: list[dict], kind: str, tmp: Path, required: bool = True) -> Path | None:
    a = _asset(assets, kind)
    if a is None:
        if required:
            raise ValueError(f"project has no {kind} file")
        return None
    return client.download(a["id"], tmp / f"{kind}_{Path(a['path']).name}")


def _progress(client: ApiClient, job_id: str):
    def cb(frac: float, msg: str) -> None:
        if not client.heartbeat(job_id, frac * 100, msg):
            raise RuntimeError("job cancelled")
    return cb


def handle(client: ApiClient, job: dict, project: dict, assets: list[dict]) -> dict:
    with tempfile.TemporaryDirectory(prefix="vividora_") as td:
        tmp = Path(td)
        kind = job["kind"]

        if kind == "prepare":
            raw = _fetch(client, assets, "raw", tmp)
            out = prepare.prepare(raw, tmp / "work", on_progress=_progress(client, job["id"]))
            files = []
            for f in out["files"]:
                up = client.upload(job["id"], f["path"], f["kind"])
                files.append({"kind": f["kind"], "path": up["path"], "mime": f.get("mime"),
                              "meta": f.get("meta", {})})
            return {"meta": out["meta"], "files": files}

        if kind == "autocut":
            transcript = project.get("transcript") or {"segments": []}
            duration = float(project["meta"].get("duration") or 0)
            audio = _fetch(client, assets, "audio_asr", tmp, required=False)
            sil = ffmpeg.silences(audio) if audio else []
            edl = autocut.build_edl(transcript, duration, sil, job["payload"].get("options"))
            return {"edl": edl}

        if kind == "render":
            p = job["payload"]
            raw = _fetch(client, assets, "raw", tmp)
            clean = _fetch(client, assets, "audio_clean", tmp, required=False)
            style = caption_style(p.get("caption_style", "karaoke"))
            preset = platform(p["preset"])
            out = render.render(
                video=raw, audio=clean, meta=project["meta"], edl=project["edl"] or
                autocut.build_edl({"segments": []}, float(project["meta"]["duration"])),
                transcript=project.get("transcript"), preset=preset, style=style,
                out_dir=tmp / "out", name=preset["id"], hook=p.get("hook"),
                focus_x=float(p.get("focus_x", 0.5)), focus_y=float(p.get("focus_y", 0.5)),
                burn_captions=p.get("burn_captions"),
                caption_overrides=p.get("captions"),
                encoder_preset=os.getenv("X264_PRESET") or None,
                on_progress=_progress(client, job["id"]),
            )
            files = []
            for f in out["files"]:
                up = client.upload(job["id"], f["path"], f["kind"], f.get("label"))
                files.append({**f, "path": up["path"]})
            return {"files": files, "duration": out["duration"], "warnings": out["warnings"]}

        if kind == "transcribe":
            from .transcribe import transcribe_file
            audio = _fetch(client, assets, "audio_asr", tmp)
            return {"transcript": transcribe_file(audio, language=job["payload"].get("language", "hi"),
                                                  on_progress=_progress(client, job["id"]))}

        raise ValueError(f"unknown job kind {kind}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    base = os.getenv("API_URL", "http://127.0.0.1:8000")
    token = os.getenv("WORKER_TOKEN", "dev-worker-token")
    name = os.getenv("WORKER_NAME", f"cpu@{socket.gethostname()}")
    kinds = ["prepare", "autocut", "render"]
    if os.getenv("TRANSCRIBE_LOCAL", "").lower() in ("1", "true", "yes"):
        kinds.append("transcribe")
    client = ApiClient(base, token, name)
    run_loop(client, kinds, handle, poll=float(os.getenv("POLL_SECONDS", "3")),
             info={"ffmpeg": ffmpeg.have("ffmpeg"), "deepfilter": ffmpeg.have("deep-filter")},
             once=os.getenv("ONCE") == "1")


if __name__ == "__main__":
    main()
