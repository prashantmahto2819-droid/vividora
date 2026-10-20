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

from ..engine import autocut, ffmpeg, montage, prepare, render, shorts
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


def _is_image(p: Path) -> bool:
    """Library files are downloaded without an extension — sniff the header."""
    try:
        head = p.open("rb").read(16)
    except OSError:
        return False
    return (head.startswith(b"\x89PNG") or head[:3] == b"\xff\xd8\xff" or head[:4] == b"GIF8"
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"))


def _resolve_effects(client: ApiClient, effects: dict | None, tmp: Path, assets: list[dict] | None = None) -> dict:
    """Download library items the render refers to; replace ids with local paths."""
    e = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
         for k, v in (effects or {}).items()}
    cache: dict[str, Path] = {}

    def fetch(item_id: str) -> Path | None:
        if not item_id:
            return None
        if item_id not in cache:
            cache[item_id] = client.download_library(item_id, tmp / "lib" / item_id)
        return cache[item_id]

    look = e.get("look") or "none"
    if isinstance(look, str) and look.startswith("lut:"):
        p = fetch(look[4:])
        e["lut_path"] = str(p) if p else None
        e["look"] = "none"
    body = e.get("body") if isinstance(e.get("body"), dict) else None
    if body and body.get("enabled"):
        alpha = next((a for a in (assets or []) if a["kind"] == "alpha"), None)
        if alpha:
            body["alpha_path"] = str(client.download(alpha["id"], tmp / "alpha.mp4"))
            for key in ("bg_image", "bg_video"):
                if body.get(key):
                    p = fetch(body[key])
                    body[key + "_path"] = str(p) if p else None
        else:
            body["enabled"] = False
        e["body"] = body
    for key in ("music", "watermark", "frame"):
        d = e.get(key) or {}
        if isinstance(d, dict) and d.get("id"):
            p = fetch(d["id"])
            e[key] = {**d, "path": str(p) if p else None}
    for key in ("broll", "sfx"):
        out = []
        for item in e.get(key) or []:
            if isinstance(item, dict) and item.get("id"):
                p = fetch(item["id"])
                if p:
                    kind = "image" if (p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif") or _is_image(p)) else "video"
                    out.append({**item, "path": str(p), "type": kind})
        e[key] = out
    return e


def handle(client: ApiClient, job: dict, project: dict, assets: list[dict]) -> dict:
    with tempfile.TemporaryDirectory(prefix="vividora_") as td:
        tmp = Path(td)
        kind = job["kind"]

        if kind == "prepare":
            prog = _progress(client, job["id"])
            clips_meta = None
            if job["payload"].get("merge"):
                clip_assets = sorted([a for a in assets if a["kind"] == "clip"], key=lambda a: (a.get("meta") or {}).get("order", 0))
                paths = [client.download(a["id"], tmp / "clips" / Path(a["path"]).name) for a in clip_assets]
                if len(paths) == 1:
                    raw = paths[0]
                    clips_meta = [{"name": paths[0].name, "start": 0.0, "end": ffmpeg.probe(raw)["duration"]}]
                else:
                    m = prepare.merge(paths, tmp / "work" / "merged.mp4", on_progress=lambda f, msg: prog(f * 0.3, msg))
                    raw = m["path"]
                    clips_meta = m["boundaries"]
                merged_up = client.upload(job["id"], raw, "raw")
                out = prepare.prepare(raw, tmp / "work", on_progress=lambda f, msg: prog(0.3 + f * 0.7, msg))
                files = [{"kind": "raw", "path": merged_up["path"], "mime": "video/mp4", "meta": {"merged": len(paths) > 1}}]
            else:
                raw = _fetch(client, assets, "raw", tmp)
                out = prepare.prepare(raw, tmp / "work", on_progress=prog)
                files = []
            for f in out["files"]:
                up = client.upload(job["id"], f["path"], f["kind"])
                files.append({"kind": f["kind"], "path": up["path"], "mime": f.get("mime"),
                              "meta": f.get("meta", {})})
            return {"meta": out["meta"], "files": files, "clips": clips_meta}

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
            voice_cfg = (p.get("effects") or {}).get("voice") or {}
            # "strong" = the deep-cleaned track from prepare; "light"/"off" start from the original audio
            clean = None if voice_cfg.get("denoise") in ("light", "off") else _fetch(client, assets, "audio_clean", tmp, required=False)
            style = caption_style(p.get("caption_style", "karaoke"))
            preset = platform(p["preset"])
            out = render.render(
                video=raw, audio=clean, meta=project["meta"], edl=project["edl"] or
                autocut.build_edl({"segments": []}, float(project["meta"]["duration"])),
                transcript=project.get("transcript"), preset=preset, style=style,
                out_dir=tmp / "out", name=p.get("label") or preset["id"], hook=p.get("hook"),
                clip=p.get("clip"), face_track=p.get("face_track", "auto"),
                focus_x=float(p.get("focus_x", 0.5)), focus_y=float(p.get("focus_y", 0.5)),
                burn_captions=p.get("burn_captions"),
                caption_overrides=p.get("captions"),
                effects={**_resolve_effects(client, p.get("effects"), tmp, assets),
                         "font_paths": [str(client.download_library(fid, tmp / "fonts" / f"{fid}.ttf")) for fid in (p.get("fonts") or [])]},
                encoder_preset=os.getenv("X264_PRESET") or None,
                on_progress=_progress(client, job["id"]),
            )
            files = []
            for f in out["files"]:
                label = p.get("label") or f.get("label")
                up = client.upload(job["id"], f["path"], f["kind"], label)
                files.append({**f, "label": label, "path": up["path"],
                              "meta": {**f.get("meta", {}), "title": p.get("title")}})
            return {"files": files, "duration": out["duration"], "warnings": out["warnings"]}

        if kind == "publish":
            from .. import publish as pubmod
            p = job["payload"]
            video = thumb = None
            if p["platform"] == "youtube" and not p.get("dry_run"):
                video = client.download(p["asset_id"], tmp / "upload.mp4")
                if p.get("thumb_asset_id"):
                    try:
                        thumb = client.download(p["thumb_asset_id"], tmp / "thumb.jpg")
                    except Exception:
                        thumb = None
            prog = _progress(client, job["id"])
            try:
                r = pubmod.run(p["platform"], p.get("secrets") or {}, p.get("payload") or {}, video=video,
                               public_url=p.get("public_url"), thumb=thumb, dry_run=bool(p.get("dry_run")),
                               on_progress=lambda f: prog(f, "upload हो रहा है"))
            except pubmod.PublishError as e:
                err = RuntimeError(str(e))
                err.no_retry = not e.retry
                raise err from None
            return r

        if kind == "montage":
            p = job["payload"]
            lib = tmp / "lib"
            clips = []
            for item in p.get("clips") or []:
                path = client.download_library(item["id"], lib / item["id"])
                kind_ = "image" if (path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") or _is_image(path)) else "video"
                clips.append({"path": path, "type": kind_, "duration": item.get("duration")})
            music = client.download_library(p["music"], lib / p["music"])
            wm = client.download_library(p["watermark"], lib / p["watermark"]) if p.get("watermark") else None
            preset = platform(p.get("preset", "ig-reel"))
            out = montage.render(clips=clips, music=music, out_dir=tmp / "out", name=preset["id"], preset=preset,
                                 texts=p.get("texts") or [], look=p.get("look", "none"), every=int(p.get("every", 2)),
                                 max_seconds=float(p.get("max_seconds", 30)), flash=bool(p.get("flash", True)),
                                 font=p.get("font") or "Poppins", text_color=p.get("text_color") or "#FFFFFF",
                                 text_size=float(p.get("text_size", 0.07)), watermark=wm, seed=int(p.get("seed", 7)),
                                 encoder_preset=os.getenv("X264_PRESET") or None, on_progress=_progress(client, job["id"]))
            files = []
            for f in out["files"]:
                up = client.upload(job["id"], f["path"], f["kind"], f.get("label"))
                files.append({**f, "path": up["path"]})
            return {"files": files, "duration": out["duration"], "bpm": out["bpm"], "segments": out["segments"], "warnings": []}

        if kind == "matte":
            from ..engine import matting
            proxy = _fetch(client, assets, "proxy", tmp)
            info = ffmpeg.probe(proxy)
            out = tmp / "alpha.mp4"
            r = matting.matte(proxy, out, width=info["width"], height=info["height"], fps=float(info["fps"]),
                              duration=float(info["duration"]), downsample=float(job["payload"].get("downsample", 0.375)),
                              on_progress=_progress(client, job["id"]))
            up = client.upload(job["id"], out, "alpha")
            return {"files": [{"kind": "alpha", "path": up["path"], "mime": "video/mp4", "meta": r}]}

        if kind == "shorts_plan":
            o = job["payload"].get("options") or {}
            clips = shorts.plan(project.get("transcript") or {}, float(project["meta"].get("duration") or 0),
                                project.get("edl"), count=int(o.get("count", 5)), min_len=float(o.get("min_len", 22)),
                                max_len=float(o.get("max_len", 58)), language=project.get("language", "hi"))
            return {"clips": clips}

        if kind == "transcribe":
            from .transcribe import transcribe_file
            audio = _fetch(client, assets, "audio_asr", tmp)
            pl = job["payload"]
            prog = _progress(client, job["id"])
            tr = transcribe_file(audio, language=pl.get("language", "hi"), prompt=pl.get("prompt"),
                                 on_progress=lambda f, m: prog(f * 0.93, m))
            from ..engine import vocab
            tr, nfix = vocab.apply_fixes(tr, pl.get("fixes"))
            npol = 0
            if pl.get("polish", True):
                prog(0.95, "AI से spelling सुधार")
                try:
                    tr, npol = vocab.llm_polish(tr, tr.get("language") or pl.get("language", "hi"), pl.get("context", ""))
                except Exception as e:  # noqa: BLE001 — polishing is optional
                    log.warning("llm polish failed: %s", e)
            tr["fixes_applied"], tr["polished_words"] = nfix, npol
            return {"transcript": tr}

        raise ValueError(f"unknown job kind {kind}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    base = os.getenv("API_URL", "http://127.0.0.1:8000")
    token = os.getenv("WORKER_TOKEN", "dev-worker-token")
    name = os.getenv("WORKER_NAME", f"cpu@{socket.gethostname()}")
    kinds = ["prepare", "autocut", "render", "shorts_plan", "publish", "montage"]
    try:
        import onnxruntime  # noqa: F401
        kinds.append("matte")
    except ImportError:
        log.warning("onnxruntime नहीं — cutout (matte) jobs इस worker पर नहीं चलेंगे")
    if os.getenv("TRANSCRIBE_LOCAL", "").lower() in ("1", "true", "yes"):
        kinds.append("transcribe")
    client = ApiClient(base, token, name)
    run_loop(client, kinds, handle, poll=float(os.getenv("POLL_SECONDS", "3")),
             info={"ffmpeg": ffmpeg.have("ffmpeg"), "deepfilter": ffmpeg.have("deep-filter")},
             once=os.getenv("ONCE") == "1")


if __name__ == "__main__":
    main()
