"""Export options: resolution, frame rate, container, codec, quality, audio — plus the render
signature that tells whether a finished output still matches the project (docs/editor-schema.md).

The platform preset decides the frame (aspect, native size, fps cap); the user's export
overrides narrow it: a smaller resolution, a fixed frame rate, another codec. Nothing here
upscales beyond the source unless `upscale` is ticked.
"""

from __future__ import annotations

import functools
import hashlib
import json
import subprocess

RENDER_VERSION = 4  # bump when render output changes for the same inputs (invalidates every signature)

RESOLUTIONS = ["source", "360p", "480p", "720p", "1080p", "1440p", "2160p", "custom"]
_SHORT = {"360p": 360, "480p": 480, "720p": 720, "1080p": 1080, "1440p": 1440, "2160p": 2160}
FPS = ["source", "23.976", "24", "25", "29.97", "30", "50", "59.94", "60"]
CODECS = {
    # id: encoder, containers it can live in, ffmpeg codec tag, est. bitrate factor vs H.264
    "h264": {"enc": "libx264", "label": "H.264 (सब जगह चलता है)", "containers": ["mp4", "mov"], "factor": 1.0, "crf": 20},
    "h265": {"enc": "libx265", "label": "H.265 / HEVC (छोटी file)", "containers": ["mp4", "mov"], "factor": 0.62, "crf": 24},
    "vp9": {"enc": "libvpx-vp9", "label": "VP9 (web)", "containers": ["webm", "mp4"], "factor": 0.7, "crf": 31},
    "av1": {"enc": "libsvtav1", "label": "AV1 (सबसे छोटी, धीमा)", "containers": ["mp4", "webm"], "factor": 0.55, "crf": 32},
}
CONTAINERS = {"mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm"}
AUDIO = {"aac": {"enc": "aac", "containers": ["mp4", "mov"]}, "opus": {"enc": "libopus", "containers": ["webm", "mp4"]}}
# ~kbps a CRF-20 H.264 talking-head needs per short side; used only for the "लगभग" size estimate
_KBPS = {360: 700, 480: 1200, 720: 2600, 1080: 5500, 1440: 9500, 2160: 17000}

DEFAULT = {"resolution": "source", "width": 0, "height": 0, "fps": "source", "container": "mp4", "codec": "h264",
           "mode": "crf", "crf": 0, "bitrate_kbps": 0, "two_pass": False, "audio_codec": "aac", "audio_kbps": 192,
           "sample_rate": 48000, "mono": False, "upscale": False}


@functools.lru_cache(maxsize=1)
def available() -> dict:
    """Which encoders this ffmpeg has (asked once per process)."""
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20).stdout
    except Exception:  # noqa: BLE001 — no ffmpeg here: everything is reported missing, H.264 is assumed by the worker
        out = ""
    have = {name for name in ("libx264", "libx265", "libvpx-vp9", "libsvtav1", "aac", "libopus") if f" {name} " in out}
    return {"codecs": [c for c, d in CODECS.items() if d["enc"] in have] or ["h264"],
            "audio": [a for a, d in AUDIO.items() if d["enc"] in have] or ["aac"],
            "containers": list(CONTAINERS), "resolutions": RESOLUTIONS, "fps": FPS,
            "labels": {c: d["label"] for c, d in CODECS.items()}}


def normalize(raw: dict | None) -> dict:
    """Sanitised export overrides (anything odd falls back to the default = the preset's own choice)."""
    r = raw if isinstance(raw, dict) else {}
    e = dict(DEFAULT)
    e["resolution"] = r.get("resolution") if r.get("resolution") in RESOLUTIONS else "source"
    e["width"] = max(0, min(7680, int(r.get("width") or 0)))
    e["height"] = max(0, min(4320, int(r.get("height") or 0)))
    if e["resolution"] == "custom" and not (e["width"] and e["height"]):
        e["resolution"] = "source"
    e["fps"] = str(r.get("fps")) if str(r.get("fps")) in FPS else "source"
    e["codec"] = r.get("codec") if r.get("codec") in CODECS else "h264"
    e["container"] = r.get("container") if r.get("container") in CONTAINERS else "mp4"
    if e["container"] not in CODECS[e["codec"]]["containers"]:
        e["container"] = CODECS[e["codec"]]["containers"][0]
    e["mode"] = "bitrate" if r.get("mode") == "bitrate" else "crf"
    e["crf"] = max(0, min(51, int(r.get("crf") or 0)))
    e["bitrate_kbps"] = max(0, min(200_000, int(r.get("bitrate_kbps") or 0)))
    if e["mode"] == "bitrate" and not e["bitrate_kbps"]:
        e["mode"] = "crf"
    e["two_pass"] = bool(r.get("two_pass")) and e["mode"] == "bitrate"
    e["audio_codec"] = r.get("audio_codec") if r.get("audio_codec") in AUDIO else "aac"
    if e["container"] not in AUDIO[e["audio_codec"]]["containers"]:
        e["audio_codec"] = "opus" if e["container"] == "webm" else "aac"
    e["audio_kbps"] = max(32, min(320, int(r.get("audio_kbps") or 192)))
    e["sample_rate"] = 44100 if int(r.get("sample_rate") or 48000) == 44100 else 48000
    e["mono"] = bool(r.get("mono"))
    e["upscale"] = bool(r.get("upscale"))
    return e


def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def plan(export: dict | None, preset: dict, src_meta: dict, fps_now: float) -> dict:
    """Effective frame size, fps, container and encoder arguments for one render."""
    e = normalize(export)
    w, h = int(preset["width"]), int(preset["height"])
    short = min(w, h)
    if e["resolution"] == "custom":
        w2, h2 = _even(e["width"]), _even(e["height"])
    elif e["resolution"] in _SHORT:
        want = _SHORT[e["resolution"]]
        if not e["upscale"]:
            src_short = min(int(src_meta.get("width") or want), int(src_meta.get("height") or want))
            want = min(want, max(src_short, 240))
        scale = want / short
        w2, h2 = _even(w * scale), _even(h * scale)
    else:
        w2, h2 = w, h
    fps = fps_now
    if e["fps"] != "source":
        fps = {"23.976": 23.976, "29.97": 29.97, "59.94": 59.94}.get(e["fps"], float(e["fps"]))
    codec = CODECS[e["codec"]]
    crf = e["crf"] or codec["crf"]
    if e["codec"] == "h264" and e["mode"] == "crf" and not e["crf"]:
        crf = int(preset.get("video", {}).get("crf", 20))
    vargs: list[str] = ["-c:v", codec["enc"]]
    if e["codec"] == "h264":
        vargs += ["-profile:v", "high", "-pix_fmt", "yuv420p"]
    elif e["codec"] == "h265":
        vargs += ["-pix_fmt", "yuv420p", "-x265-params", "log-level=error"]
        if e["container"] in ("mp4", "mov"):
            vargs += ["-tag:v", "hvc1"]
    elif e["codec"] == "vp9":
        vargs += ["-pix_fmt", "yuv420p", "-row-mt", "1", "-deadline", "good", "-cpu-used", "2"]
    elif e["codec"] == "av1":
        vargs += ["-pix_fmt", "yuv420p", "-preset", "8"]
    if e["mode"] == "bitrate":
        kb = e["bitrate_kbps"]
        if e["codec"] == "vp9":
            vargs += ["-b:v", f"{kb}k", "-minrate", f"{kb // 2}k", "-maxrate", f"{int(kb * 1.45)}k"]
        else:
            vargs += ["-b:v", f"{kb}k", "-maxrate", f"{int(kb * 1.3)}k", "-bufsize", f"{kb * 2}k"]
    else:
        if e["codec"] == "vp9":
            vargs += ["-crf", str(crf), "-b:v", "0"]
        else:
            vargs += ["-crf", str(crf)]
    a = AUDIO[e["audio_codec"]]
    aargs = ["-c:a", a["enc"], "-b:a", f"{e['audio_kbps']}k", "-ar", str(e["sample_rate"])]
    if e["mono"]:
        aargs += ["-ac", "1"]
    extra = ["-movflags", "+faststart"] if e["container"] in ("mp4", "mov") else []
    return {"export": e, "width": w2, "height": h2, "fps": round(fps, 3), "container": e["container"],
            "mime": CONTAINERS[e["container"]], "vargs": vargs, "aargs": aargs, "extra": extra,
            "two_pass": e["two_pass"], "crf": crf, "codec": e["codec"], "preset_arg_ok": e["codec"] == "h264" or e["codec"] == "h265",
            "resized": (w2, h2) != (w, h)}


def estimate_bytes(export: dict | None, preset: dict, src_meta: dict, duration: float) -> int:
    """Rough output size ("लगभग"): duration × (video kbps + audio kbps)."""
    p = plan(export, preset, src_meta, float(src_meta.get("fps") or 30))
    e = p["export"]
    if e["mode"] == "bitrate":
        vk = e["bitrate_kbps"]
    else:
        short = min(p["width"], p["height"])
        base = next((k for s, k in sorted(_KBPS.items()) if short <= s), _KBPS[2160])
        ref = CODECS[p["codec"]]["crf"]
        vk = base * CODECS[p["codec"]]["factor"] * (2 ** ((ref - p["crf"]) / 6))
        if p["fps"] > 31:
            vk *= 1.4
    return int(max(0.0, duration) * (vk + e["audio_kbps"]) * 1000 / 8)


def signature(render_opts: dict, preset_id: str, project: dict, source_ids: list[str]) -> str:
    """Changes whenever the output for this preset would change: cuts, words, every render setting,
    the source files, and the render code itself."""
    tr = project.get("transcript") or {}
    words = [(round(float(w.get("start", 0)), 2), w.get("text")) for s in tr.get("segments", []) for w in (s.get("words") or [])]
    core = {"v": RENDER_VERSION, "preset": preset_id, "src": sorted(source_ids), "edl": project.get("edl"),
            "words": words, "lang": project.get("language"),
            "opts": {k: v for k, v in render_opts.items() if k not in ("presets", "shorts_preset")}}
    return hashlib.sha1(json.dumps(core, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]
