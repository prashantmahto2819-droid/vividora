"""The CPU worker: prepare, autocut, render. Runs in Docker next to the API,
or anywhere with ffmpeg (`python -m vividora.worker.cpu`).

With TRANSCRIBE_LOCAL=1 it also transcribes on CPU using faster-whisper
(slow, but works when the Windows GPU worker is off). With TTS_LOCAL=1 it also
makes AI voice-overs (`dub` jobs, engine/tts.py) — slow on CPU.
"""

from __future__ import annotations

import logging
import os
import re
import socket
import tempfile
import urllib.error
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
            ffmpeg.cancel_all()  # the creator pressed ✕: stop every child process and unwind
            raise ffmpeg.Cancelled("रद्द किया")
    return cb


def _is_image(p: Path) -> bool:
    """Library files are downloaded without an extension — sniff the header."""
    try:
        head = p.open("rb").read(16)
    except OSError:
        return False
    return (head.startswith(b"\x89PNG") or head[:3] == b"\xff\xd8\xff" or head[:4] == b"GIF8"
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"))


def _font(client: ApiClient, fid: str, tmp: Path) -> Path | None:
    try:
        return client.download_library(fid, tmp / "fonts" / f"{fid}.ttf")
    except urllib.error.HTTPError as err:
        if err.code not in (404, 410):
            raise
        log.warning("font %s नहीं मिला", fid)
        return None


def _lib_alpha(client: ApiClient, item_id: str, tmp: Path, e: dict) -> str | None:
    """Person matte of a library video for a "सिर्फ़ इंसान" overlay; None (whole clip shown) if not made yet."""
    try:
        return str(client.download_library_alpha(item_id, tmp / "lib_alpha" / f"{item_id}.mp4"))
    except urllib.error.HTTPError as err:
        if err.code not in (404, 410):
            raise
        e.setdefault("_cutout_missing", []).append(item_id)
        return None


def _matte_resets(project: dict) -> list[float]:
    """Joins of merged clips: the matte's recurrent state starts fresh there (new shot, new light)."""
    clips = (project.get("meta") or {}).get("clips") or []
    return [float(c.get("start") or 0) for c in clips if isinstance(c, dict) and float(c.get("start") or 0) > 0]


def _resolve_effects(client: ApiClient, effects: dict | None, tmp: Path, assets: list[dict] | None = None) -> dict:
    """Download library items the render refers to; replace ids with local paths."""
    e = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
         for k, v in (effects or {}).items()}
    cache: dict[str, Path | None] = {}
    missing = e.setdefault("_missing", [])

    missing: list[str] = []

    def fetch(item_id: str) -> Path | None:
        """A library item deleted / not installed on this server: render without it (and say so)
        instead of failing the whole render on a 404."""
        if not item_id:
            return None
        if item_id not in cache:
            try:
                cache[item_id] = client.download_library(item_id, tmp / "lib" / item_id)
            except Exception as ex:  # noqa: BLE001 — HTTP 404 "file missing", network
                log.warning("library item %s नहीं मिला: %s", item_id, ex)
                cache[item_id] = None
                missing.append(item_id)
        return cache[item_id]
    e["_missing"] = missing

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
    if e.get("lut_path") is None and "lut_path" in e:
        e.pop("lut_path")
    for key in ("broll", "sfx"):
        out = []
        for item in e.get(key) or []:
            if isinstance(item, dict) and item.get("lut"):  # per-clip .cube from the library
                lp = fetch(item["lut"])
                item["lut_path"] = str(lp) if lp else None
            if isinstance(item, dict) and item.get("id"):
                p = fetch(item["id"])
                if p:
                    kind = "image" if (p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif") or _is_image(p)) else "video"
                    out.append({**item, "path": str(p), "type": kind})
                    if key == "broll" and item.get("cutout") and kind == "video":
                        out[-1]["alpha_path"] = _lib_alpha(client, item["id"], tmp, e)
        e[key] = out
    # AI voice-over / dub chosen as the voice: download that project file like the other assets
    vt = e.get("voice_track")
    if vt and vt != "original":
        dub = next((a for a in (assets or []) if a["id"] == vt and a["kind"] == "dub"), None)
        if dub:
            e["voice_track_path"] = str(client.download(dub["id"], tmp / f"dub_{Path(dub['path']).name}"))
            meta = dub.get("meta") or {}
            e["voice_track_words"] = [w for s in (meta.get("segments") or []) for w in (s.get("words") or [])]
            e["voice_track_sig"] = meta.get("sig")
        else:
            log.warning("voice track %s नहीं मिला — original आवाज़ से render", vt)
            e["voice_track"] = "original"
    return e


def _montage_voice(client: ApiClient, p: dict, assets: list[dict], out: dict, tmp: Path) -> list[str]:
    """Script voice-over (dub asset) chosen for a montage → mix it over the rendered video in place."""
    v = p.get("voice") or {}
    dub = next((a for a in assets if a["id"] == v.get("asset_id") and a["kind"] == "dub"), None) if v else None
    if not dub:
        return []
    from ..engine import dub as dub_eng
    voice = client.download(dub["id"], tmp / f"dub_{Path(dub['path']).name}")
    warns: list[str] = []
    for f in out["files"]:
        if f.get("kind") == "render":
            src = Path(f["path"])
            mixed = src.with_name(src.stem + "_vo.mp4")
            warns += dub_eng.mix_voice_over(src, voice, mixed, duck=bool(v.get("duck", True)))
            mixed.replace(src)
    return warns


def _qa(project: dict, p: dict, preset: dict, vid: dict, out: dict) -> dict:
    """engine/qa.check for one finished render: the words its captions should show, the platform's
    loudness target, whether there should be sound at all."""
    from ..engine import qa
    meta = project.get("meta") or {}
    clip = p.get("clip") or {}
    words = [w for s in ((project.get("transcript") or {}).get("segments") or []) for w in (s.get("words") or [])]
    if clip:
        words = [w for w in words if float(clip.get("start", 0)) <= float(w["start"]) < float(clip.get("end", 0))]
    burn = preset.get("burn_captions", True) if p.get("burn_captions") is None else bool(p.get("burn_captions"))
    music = bool(((p.get("effects") or {}).get("music") or {}).get("id"))
    return qa.check(Path(vid["path"]), target_lufs=float((preset.get("audio") or {}).get("loudness", -14)),
                    expect_audio=bool(meta.get("has_audio")) or music,
                    expect_captions=burn and bool(meta.get("has_audio")) and bool(project.get("transcript")),
                    caption_words=len(words), duration=float(out.get("duration") or 0),
                    # a sidecar SRT is timed on the untrimmed video — then only report the black start
                    fix=not any(f.get("kind") == "subtitle" for f in out.get("files") or []),
                    encoder_preset=os.getenv("X264_PRESET") or None)


HEAVY_KINDS = {"render", "montage", "matte", "dub", "transcribe"}


def _x264_preset(p: dict) -> str | None:
    """Export "draft" mode encodes fast; otherwise the X264_PRESET env (or the platform preset's own)."""
    if ((p.get("export") or {}).get("quality") == "draft"):
        return "veryfast"
    return os.getenv("X264_PRESET") or None


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
            if not job["payload"].get("visual"):
                return {"edl": edl}
            # transcript-free cut: scene changes (on the 720p proxy) become markers; long dead air is cut by the silences above
            from ..engine import scenes as scn
            proxy = _fetch(client, assets, "proxy", tmp, required=False) or _fetch(client, assets, "raw", tmp, required=False)
            found = []
            if proxy:
                try:
                    found = scn.detect(proxy, threshold=float(job["payload"].get("scene_threshold") or 0.35), min_gap=1.0)
                except Exception as ex:  # noqa: BLE001 — markers are a help, never a reason to fail the cut
                    log.warning("scene detect failed: %s", ex)
            return {"edl": edl, "scenes": found}

        if kind == "render":
            p = job["payload"]
            raw = _fetch(client, assets, "raw", tmp)
            voice_cfg = (p.get("effects") or {}).get("voice") or {}
            # "strong" = the deep-cleaned track from prepare; "light"/"off" start from the original audio
            clean = None if voice_cfg.get("denoise") in ("light", "off") else _fetch(client, assets, "audio_clean", tmp, required=False)
            style = caption_style(p.get("caption_style", "karaoke"))
            preset = platform(p["preset"])
            effects = _resolve_effects(client, p.get("effects"), tmp, assets)
            dub_warn = []
            if effects.pop("_missing", None):
                dub_warn.append("library की कुछ फ़ाइलें (music/sticker/sfx) नहीं मिलीं — उनके बिना render हुआ")
            font_paths = []
            for fid in p.get("fonts") or []:
                try:
                    font_paths.append(str(client.download_library(fid, tmp / "fonts" / f"{fid}.ttf")))
                except Exception as ex:  # noqa: BLE001 — a missing font falls back to the bundled ones
                    log.warning("font %s नहीं मिला: %s", fid, ex)
            if effects.get("voice_track_path") and effects.get("voice_track_sig"):
                from ..engine import dub
                edl0 = {"duration": float(project["meta"].get("duration") or 0), "cuts": [], **(project.get("edl") or {})}
                if dub.timeline_sig(edl0, p.get("effects")) != effects["voice_track_sig"]:
                    dub_warn.append("AI voice-over बनने के बाद कट/speed बदले हैं — आवाज़ खिसक सकती है, dub दोबारा बनाएँ")
            rkw = dict(
                video=raw, audio=clean, meta=project["meta"], edl=project["edl"] or
                autocut.build_edl({"segments": []}, float(project["meta"]["duration"])),
                transcript=project.get("transcript"), preset=preset, style=style,
                out_dir=tmp / "out", name=p.get("label") or preset["id"], hook=p.get("hook"),
                clip=p.get("clip"), face_track=p.get("face_track", "auto"),
                focus_x=float(p.get("focus_x", 0.5)), focus_y=float(p.get("focus_y", 0.5)),
                burn_captions=p.get("burn_captions"),
                caption_overrides=p.get("captions"),
                effects={**effects, "font_paths": font_paths},
                encoder_preset=_x264_preset(p), export=p.get("export"),
                on_progress=lambda f, m, _cb=_progress(client, job["id"]): _cb(f * 0.92, m),
            )
            out = None
            import time as _time
            _t0 = _time.time()
            if os.getenv("SEGMENT_RENDER", "1") != "0":
                # pieces cached by their inputs: after a small edit only the changed pieces render again
                from ..engine import segrender
                try:
                    segrender.prune()
                except Exception:  # noqa: BLE001
                    pass
                src_sig = "|".join(f"{a['id']}:{a.get('size')}" for a in assets if a["kind"] in ("raw", "audio_clean"))
                try:
                    out = segrender.render_segmented(project_id=project["id"], source_sig=src_sig, **rkw)
                    seg = out.get("segmented") or {}
                    log.info("segmented render: %s pieces, %s reused", seg.get("pieces"), seg.get("reused"))
                except ValueError as ex:
                    log.info("single-pass render (%s)", ex)
                except ffmpeg.Cancelled:
                    raise
                except Exception as ex:  # noqa: BLE001 — never lose a render to the cache path
                    log.warning("segmented render failed, rendering in one go: %s", ex)
            if out is None:
                out = render.render(**rkw)
            for f in out["files"]:
                if f.get("kind") == "render":
                    f.setdefault("meta", {})["render_seconds"] = round(_time.time() - _t0, 1)
            # output QA before anyone is asked to approve: black start (cut off), loudness, captions
            qa_warn: list[str] = []
            qa_info: dict = {}
            vid = next((f for f in out["files"] if f.get("kind") == "render"), None)
            if vid is not None and os.getenv("RENDER_QA", "1") != "0":
                _progress(client, job["id"])(0.94, "quality check (काले frames, loudness, captions)")
                try:
                    qa_info = _qa(project, p, preset, vid, out)
                    qa_warn = [f"{preset.get('label')}: {w}" for w in qa_info.get("warnings", [])]
                except Exception as ex:  # noqa: BLE001 — QA must never lose a finished render
                    log.warning("render QA failed: %s", ex)
            files = []
            for f in out["files"]:
                label = p.get("label") or f.get("label")
                up = client.upload(job["id"], f["path"], f["kind"], label)
                files.append({**f, "label": label, "path": up["path"],
                              "meta": {**f.get("meta", {}), "title": p.get("title"), "signature": p.get("signature"),
                                       **({"qa": qa_info} if qa_info and f is vid else {})}})
            if effects.get("_cutout_missing"):
                qa_warn = qa_warn + [f"{len(effects['_cutout_missing'])} overlay का cutout अभी नहीं बना — वह पूरा clip दिखा"]
            return {"files": files, "duration": out["duration"], "warnings": out["warnings"] + dub_warn + qa_warn}

        if kind == "compress":
            from ..engine import compress as cmp
            pl = job["payload"] or {}
            prog = _progress(client, job["id"])
            prog(0.01, "file ला रहे हैं")
            if pl.get("library_id"):
                src = client.download_library(pl["library_id"], tmp / "src" / pl["library_id"])
            else:
                src = client.download(pl["asset_id"], tmp / "src" / "asset.bin")
            info = ffmpeg.probe(src)
            plan = cmp.plan(info, target_mb=float(pl.get("target_mb") or 0), max_h=int(pl.get("max_h") or 1080),
                            fps=float(pl.get("fps") or 0), audio_kbps=int(pl.get("audio_kbps") or 96), crf=int(pl.get("crf") or 0))
            prog(0.03, f"{plan['width']}×{plan['height']} @ {plan['fps']:g} fps, {plan['video_kbps'] or 'CRF ' + str(plan['crf'])} kbps")
            stem = Path(str(pl.get("name") or "video")).stem[:60] or "video"
            out = tmp / "out" / f"{stem}.mp4"
            r = cmp.run(src, out, plan, on_progress=lambda f, m: prog(0.03 + f * 0.95, m), label="compress")
            prog(0.99, "upload")
            up = client.upload(job["id"], out, "compress", "compress")
            return {**r, "source_size": src.stat().st_size, "plan": {k: v for k, v in plan.items() if k != "warnings"},
                    "files": [{"kind": "compress", "path": up["path"], "mime": "video/mp4"}]}

        if kind == "dub":
            from ..engine import tts
            prog = _progress(client, job["id"])
            return tts.handle_job(client, job, tmp / "dub", on_progress=prog)

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
                               on_progress=lambda f: prog(f, "upload हो रहा है"), captions_srt=p.get("captions_srt"))
            except pubmod.PublishError as e:
                err = RuntimeError(str(e))
                err.no_retry = not e.retry
                raise err from None
            return r

        if kind in ("montage_plan", "montage") and (kind == "montage_plan" or job["payload"].get("plan")):
            from ..engine import beatcut
            p = job["payload"]
            lib = tmp / "lib"
            prog = _progress(client, job["id"])
            local = {}
            missing = []
            for n, item in enumerate(p.get("clips") or []):
                prog(0.0, f"clips ला रहे हैं {n + 1}/{len(p.get('clips') or [])}")
                try:
                    path = client.download_library(item["id"], lib / item["id"])
                except urllib.error.HTTPError as e:
                    if e.code != 404:
                        raise
                    missing.append(item.get("name") or item["id"])   # file gone from the library (share dropped, deleted) — skip it
                    continue
                k = "image" if (path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") or _is_image(path)) else "video"
                local[item["id"]] = {"path": path, "kind": k}
            if not local:
                raise ValueError("कोई clip नहीं मिली — library में files जाँचें (D: drive share बंद तो नहीं?)")
            try:
                music = client.download_library(p["music"], lib / p["music"])
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise ValueError("song की file library में नहीं मिली — दूसरा song चुनें") from None
                raise
            th = p.get("theme_opts") or {}
            if kind == "montage_plan":
                prog(0.02, "song सुन रहे हैं — beats, drops, सबसे जोशीला हिस्सा")
                max_s = float(p.get("max_seconds", 30) or 0)
                mu = beatcut.music(music, max_s if max_s > 0 else 10_000)
                infos, bad = [], []
                names = {it["id"]: it.get("name") for it in (p.get("clips") or [])}
                for n, (cid, c) in enumerate(local.items()):
                    prog(0.05 + 0.85 * n / max(1, len(local)), f"clip {n + 1}/{len(local)} देख रहे हैं — best moments, चेहरा, आवाज़")
                    try:
                        infos.append({"id": cid, **beatcut.clip(c["path"], c["kind"])})
                    except ffmpeg.Cancelled:
                        raise
                    except Exception as e:  # noqa: BLE001 — one bad file must not sink the whole montage
                        log.warning("montage clip %s skipped: %s", cid, e)
                        bad.append(names.get(cid) or cid)
                if not infos:
                    raise ValueError("कोई clip पढ़ी नहीं जा सकी — files जाँचें")
                prog(0.92, "beat plan बन रहा है — cuts, effects, slow-mo")
                pl = beatcut.plan(mu, infos, max_seconds=max_s, pace=th.get("pace") or p.get("pace") or "auto",
                                  effects=th.get("effects_level") or p.get("effects_level") or "auto",
                                  min_cut=float(th.get("min_cut", 0.4)), max_cut=float(th.get("max_cut", 2.2)),
                                  slowmo=bool(th.get("slowmo", p.get("slowmo", True))), seed=int(p.get("seed", 7)),
                                  fx_strong=th.get("fx_strong"), fx_soft=th.get("fx_soft"), speed_ramp=bool(th.get("speed_ramp", True)),
                                  pins=[x for x in (p.get("pins") or []) if x in local],
                                  intro=bool(p.get("intro", th.get("intro", False))), outro=bool(p.get("outro", th.get("outro", False))))
                pl["clip_info"] = {i["id"]: {"kind": i["kind"], "w": i["w"], "h": i["h"], "duration": i["duration"]} for i in infos}
                pl["theme"] = th.get("theme_id") or ""
                bad = missing + bad
                if bad:
                    pl["warnings"] = [f"{len(bad)} clip छोड़ी (file नहीं मिली / पढ़ी नहीं जा सकी): {', '.join(str(b) for b in bad[:5])}"]
                return {"plan": pl}
            for cid, c in local.items():
                try:
                    pr = ffmpeg.probe(c["path"])
                    c.update(w=pr.get("width"), h=pr.get("height"))
                except Exception:  # noqa: BLE001
                    pass
            wm = client.download_library(p["watermark"], lib / p["watermark"]) if p.get("watermark") else None
            preset = platform(p.get("preset", "ig-reel"))
            texts = list(p.get("texts") or [])
            if p.get("text_mode") == "names" or (p.get("text_mode") == "beats" and not texts):
                # words from the clip names: "bike_ride.mp4" → "bike ride"
                seen = set()
                for it in p.get("clips") or []:
                    w = re.sub(r"[_\-]+", " ", re.sub(r"\.[a-z0-9]+$", "", str(it.get("name") or ""), flags=re.I)).strip()
                    w = re.sub(r"^(img|vid|mov|dsc|pxl|video|clip)[ _]*\d*$", "", w, flags=re.I).strip()
                    if w and w.lower() not in seen:
                        seen.add(w.lower())
                        texts.append(w[:24])
            look = th.get("look") if th.get("look") and p.get("look") in (None, "", "auto") else p.get("look") or "auto"
            prog(0.0, "video बन रहा है — reframe, effects, रंग, text, music")
            out = beatcut.render(pl=p["plan"], clips=local, music_path=music, out_dir=tmp / "out", name=preset["id"], preset=preset,
                                 texts=texts, look=look, reframe=p.get("reframe") or "smart",
                                 font=p.get("font") or th.get("font") or "Poppins", text_color=p.get("text_color") or th.get("text_color") or "#FFFFFF",
                                 text_size=float(p.get("text_size") or th.get("text_size") or 0.07), watermark=wm,
                                 encoder_preset=os.getenv("X264_PRESET") or None, on_progress=prog,
                                 text_style=th.get("text_style") if p.get("theme_text", True) else None,
                                 text_mode="beats" if p.get("text_mode") in ("beats", "names") else "bars",
                                 intro_text=str(p.get("intro_text") or ""), outro_text=str(p.get("outro_text") or ""))
            warns = _montage_voice(client, p, assets, out, tmp)
            files = []
            for f in out["files"]:
                up = client.upload(job["id"], f["path"], f["kind"], f.get("label"))
                files.append({**f, "path": up["path"]})
            return {"files": files, "duration": out["duration"], "bpm": out["bpm"], "segments": out["segments"], "warnings": warns}

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
            warns = _montage_voice(client, p, assets, out, tmp)
            files = []
            for f in out["files"]:
                up = client.upload(job["id"], f["path"], f["kind"], f.get("label"))
                files.append({**f, "path": up["path"]})
            return {"files": files, "duration": out["duration"], "bpm": out["bpm"], "segments": out["segments"], "warnings": warns}

        if kind == "matte":
            # person cutout of the main video, on the 720p proxy (same size / clock as the editor's preview)
            from ..engine import matting
            proxy = _fetch(client, assets, "proxy", tmp)
            info = ffmpeg.probe(proxy)
            out = tmp / "alpha.mp4"
            pl = job["payload"] or {}
            r = matting.matte(proxy, out, width=info["width"], height=info["height"], fps=float(info["fps"]),
                              duration=float(info["duration"]), quality=pl.get("quality") or "balanced",
                              downsample=float(pl["downsample"]) if pl.get("downsample") else None,
                              resets=_matte_resets(project), on_progress=_progress(client, job["id"]))
            up = client.upload(job["id"], out, "alpha")
            return {"files": [{"kind": "alpha", "path": up["path"], "mime": "video/mp4", "meta": r}]}

        if kind == "matte_lib":
            # person cutout of a library video ("सिर्फ़ इंसान" overlay) — stored on the library item (cutout.py)
            from ..engine import matting
            pl = job["payload"] or {}
            src = client.download_library(pl["library_id"], tmp / "lib" / pl["library_id"])
            info = ffmpeg.probe(src)
            if not info.get("width") or float(info.get("duration") or 0) <= 0:
                raise ValueError("यह library item video नहीं है")
            q = pl.get("quality") or "balanced"
            size = matting.plan(info["width"], info["height"], q, out_short=720 if q != "hair" else 1080)["out"]
            out = tmp / "alpha_lib.mp4"
            r = matting.matte(src, out, width=info["width"], height=info["height"], fps=float(info["fps"] or 30),
                              duration=float(info["duration"]), quality=q, out_size=size,
                              on_progress=_progress(client, job["id"]))
            up = client.upload(job["id"], out, "alpha_lib")
            return {"files": [{"kind": "alpha_lib", "path": up["path"], "mime": "video/mp4",
                               "meta": {**r, "library_id": pl["library_id"]}}]}

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
            rng = pl.get("range")
            window = (float(rng[0]), float(rng[1])) if isinstance(rng, (list, tuple)) and len(rng) == 2 else None
            tr = transcribe_file(audio, language=pl.get("language", "hi"), prompt=pl.get("prompt"),
                                 on_progress=lambda f, m: prog(f * 0.93, m), window=window,
                                 alternatives=int(pl.get("alternatives", 0) or 0), model=pl.get("model") or None)
            from ..engine import vocab
            tr, nfix = vocab.apply_fixes(tr, pl.get("fixes"))
            for alt in tr.get("alts") or []:
                vocab.apply_fixes({"segments": [alt]}, pl.get("fixes"))
                alt["text"] = " ".join(w["w"] for w in alt.get("words") or [])
            npol = 0
            if pl.get("polish", True) and not window:  # one line: speed first, the creator picks / edits
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
    kinds = ["prepare", "autocut", "render", "shorts_plan", "publish", "montage", "montage_plan", "compress"]
    try:
        if not os.getenv("VIVIDORA_MATTE_MOCK"):
            import onnxruntime  # noqa: F401
        kinds += ["matte", "matte_lib"]
    except ImportError:
        log.warning("onnxruntime नहीं — cutout (matte) jobs इस worker पर नहीं चलेंगे")
    if os.getenv("TRANSCRIBE_LOCAL", "").lower() in ("1", "true", "yes"):
        kinds.append("transcribe")
    if os.getenv("TTS_LOCAL", "").lower() in ("1", "true", "yes"):
        kinds.append("dub")  # AI voice-over on CPU — works, but slow (normally the GPU worker does it)
    # lanes: a "quick" worker only takes the short pipeline steps, so a new upload's transcript / cuts / plan
    # never wait behind a long render running on the "heavy" worker (docker compose --profile quick up -d)
    lane = (os.getenv("WORKER_LANE") or "all").lower()
    if lane == "quick":
        kinds = [k for k in kinds if k not in HEAVY_KINDS]
    elif lane == "heavy":
        kinds = [k for k in kinds if k in HEAVY_KINDS]
    client = ApiClient(base, token, name)
    run_loop(client, kinds, handle, poll=float(os.getenv("POLL_SECONDS", "3")),
             info={"ffmpeg": ffmpeg.have("ffmpeg"), "deepfilter": ffmpeg.have("deep-filter"), "lane": lane},
             once=os.getenv("ONCE") == "1")


if __name__ == "__main__":
    main()
