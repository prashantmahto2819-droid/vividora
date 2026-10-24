"""Video compressor: shrink any video to a target size (WhatsApp, email, social) without touching
the original. Bitrate is computed from duration and the target, resolution/fps are lowered only
when the bits-per-pixel would be too thin, two-pass H.264 hits the target closely, and the result
is measured — over target → a slightly lower bitrate, at most twice.
"""

from __future__ import annotations

from pathlib import Path

from . import ffmpeg
from .ffmpeg import ProgressFn

PRESETS = {
    "high": {"label": "High quality", "target_mb": 0, "crf": 20, "max_h": 2160, "fps": 0, "audio_kbps": 160},
    "whatsapp": {"label": "WhatsApp", "target_mb": 16, "max_h": 720, "fps": 30, "audio_kbps": 96},
    "social": {"label": "Social media", "target_mb": 50, "max_h": 1080, "fps": 30, "audio_kbps": 128},
    "email": {"label": "Email / low data", "target_mb": 10, "max_h": 480, "fps": 30, "audio_kbps": 64},
    "custom": {"label": "Custom", "target_mb": 25, "max_h": 1080, "fps": 0, "audio_kbps": 96},
}
_LADDER = [2160, 1440, 1080, 720, 540, 480, 360, 240]
MIN_BPP = 0.055          # bits per pixel per frame below which H.264 turns to mush
FLOOR_KBPS = {2160: 6000, 1440: 3500, 1080: 1800, 720: 800, 540: 500, 480: 350, 360: 220, 240: 120}


def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def plan(info: dict, *, target_mb: float, max_h: int = 1080, fps: float = 0, audio_kbps: int = 96, crf: int = 0) -> dict:
    """Decide size, fps and bitrates. target_mb=0 → CRF mode (quality preset)."""
    w, h = int(info.get("width") or 0), int(info.get("height") or 0)
    dur = max(0.1, float(info.get("duration") or 0))
    src_fps = float(info.get("fps") or 30)
    out_fps = min(src_fps, fps) if fps else src_fps
    if not w or not h:
        raise ValueError("यह video नहीं है (कोई video stream नहीं)")
    has_audio = bool(info.get("has_audio"))
    a_kbps = audio_kbps if has_audio else 0
    short = min(w, h)
    cap = min(short, max_h)
    warnings: list[str] = []
    if not target_mb:
        scale = cap / short
        return {"mode": "crf", "crf": crf or 20, "width": _even(w * scale), "height": _even(h * scale), "fps": round(out_fps, 3),
                "audio_kbps": a_kbps, "video_kbps": 0, "target_bytes": 0, "warnings": warnings, "has_audio": has_audio}
    target_bytes = int(target_mb * 1_000_000)
    budget_bits = target_bytes * 8 * 0.965 - a_kbps * 1000 * dur  # 3.5% for the container
    if budget_bits <= 0:
        # even audio alone does not fit — squeeze audio, then video gets the crumbs
        a_kbps = 32 if has_audio else 0
        budget_bits = max(target_bytes * 8 * 0.965 - a_kbps * 1000 * dur, target_bytes * 8 * 0.3)
        warnings.append("target इतना छोटा है कि audio भी 32 kbps करना पड़ा")
    v_kbps = budget_bits / dur / 1000
    # lower the frame until the bitrate buys enough bits per pixel
    for cand in ([s for s in _LADDER if s <= cap] or [cap]):
        scale = cand / short
        cw, ch = _even(w * scale), _even(h * scale)
        bpp = v_kbps * 1000 / (cw * ch * out_fps)
        if bpp >= MIN_BPP or cand == 240:
            break
    if bpp < MIN_BPP and out_fps > 24:
        out_fps = 24.0
    short_out = min(cw, ch)
    floor = next((k for s, k in sorted(FLOOR_KBPS.items()) if short_out <= s), 120)
    if v_kbps < floor:
        warnings.append(f"{target_mb:g} MB के लिए सिर्फ़ {v_kbps:.0f} kbps बचता है ({short_out}p) — quality साफ़ तौर पर गिरेगी; बड़ा target बेहतर रहेगा")
    return {"mode": "bitrate", "crf": 0, "width": cw, "height": ch, "fps": round(out_fps, 3), "audio_kbps": a_kbps,
            "video_kbps": int(v_kbps), "target_bytes": target_bytes, "warnings": warnings, "has_audio": has_audio}


def _args(src: Path, pl: dict, kbps: int) -> list[str]:
    vf = f"scale={pl['width']}:{pl['height']}:flags=lanczos,fps={pl['fps']},format=yuv420p"
    cmd = ["-i", str(src), "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-profile:v", "high"]
    if pl["mode"] == "crf":
        cmd += ["-crf", str(pl["crf"])]
    else:
        cmd += ["-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.15)}k", "-bufsize", f"{kbps * 2}k"]
    return cmd


def run(src: Path, out: Path, pl: dict, *, on_progress: ProgressFn | None = None, label: str = "compress") -> dict:
    """Encode (two-pass in bitrate mode), measure, and tighten up to twice if still over target."""
    out.parent.mkdir(parents=True, exist_ok=True)
    dur = float(ffmpeg.probe(src).get("duration") or 0) or None
    audio = ["-c:a", "aac", "-b:a", f"{pl['audio_kbps']}k", "-ar", "44100"] if pl["has_audio"] else ["-an"]
    tail = [*audio, "-movflags", "+faststart", str(out)]
    kbps = int(pl["video_kbps"])
    attempts = 0
    while True:
        attempts += 1
        base = _args(src, pl, kbps)
        if pl["mode"] == "crf":
            ffmpeg.run([*base, *tail], duration=dur, on_progress=on_progress, label=label)
        else:
            log = str(out.with_suffix("")) + ".pass"
            n = attempts
            ffmpeg.run([*base, "-pass", "1", "-passlogfile", log, "-an", "-f", "null", "/dev/null"], duration=dur, label=label,
                       on_progress=(lambda f, m: on_progress(f * 0.45, f"pass 1 (कोशिश {n})")) if on_progress else None)
            ffmpeg.run([*base, "-pass", "2", "-passlogfile", log, *tail], duration=dur, label=label,
                       on_progress=(lambda f, m: on_progress(0.45 + f * 0.5, f"pass 2 (कोशिश {n})")) if on_progress else None)
            for p in out.parent.glob(Path(log).name + "*"):
                p.unlink(missing_ok=True)
        size = out.stat().st_size
        if pl["mode"] == "crf" or size <= pl["target_bytes"] or attempts >= 3:
            break
        over = size / pl["target_bytes"]
        kbps = max(60, int(kbps * min(0.92, 1 / over) * 0.99))
    info = ffmpeg.probe(out)
    return {"size": size, "attempts": attempts, "video_kbps": kbps, "width": pl["width"], "height": pl["height"],
            "fps": pl["fps"], "duration": info.get("duration"), "hit_target": pl["mode"] == "crf" or size <= pl["target_bytes"],
            "warnings": list(pl.get("warnings") or [])}
