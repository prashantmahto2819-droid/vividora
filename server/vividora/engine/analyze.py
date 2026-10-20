"""Look at a recording and say what it needs.

measure()  — numbers from a handful of frames (light, contrast, colour, colour
             cast) and from the voice track (noise floor, level, clipping).
auto_grade() — a gentle colour correction from those numbers.
suggest()  — the "क्या कमी है" list for the editor: each item says what is
             missing and carries a one-click fix (a patch for render settings).

Everything is plain arithmetic on ffmpeg output: no model, runs in a second.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import numpy as np

from . import ffmpeg

SAMPLE_W = 160


def _frames(video: Path, duration: float, n: int = 10) -> np.ndarray | None:
    """n small RGB frames spread over the video → array (n, h, w, 3) in 0..1."""
    info = ffmpeg.probe(video)
    w0, h0 = int(info.get("width") or 0), int(info.get("height") or 0)
    if not w0 or not h0:
        return None
    w = SAMPLE_W
    h = max(2, int(round(h0 * w / w0 / 2)) * 2)
    out = []
    for i in range(n):
        t = duration * (i + 0.5) / n
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                              "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        if len(raw) == w * h * 3:
            out.append(np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3))
    if not out:
        return None
    return np.stack(out).astype(np.float32) / 255.0


def _video_stats(video: Path, duration: float) -> dict:
    f = _frames(video, duration)
    if f is None:
        return {}
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    mx, mn = f.max(axis=-1), f.min(axis=-1)
    sat = np.where(mx > 1e-3, (mx - mn) / np.maximum(mx, 1e-3), 0)
    # centre region ≈ the speaker; skin tones should sit warm there
    h, w = luma.shape[1:]
    cy, cx = slice(h // 5, h * 4 // 5), slice(w // 4, w * 3 // 4)
    mid = (luma > 0.08) & (luma < 0.92)
    rb = float(((r - b)[mid]).mean()) if mid.any() else 0.0
    gm = float(((g - (r + b) / 2)[mid]).mean()) if mid.any() else 0.0
    return {
        "luma": round(float(luma.mean()), 3),
        "luma_center": round(float(luma[:, cy, cx].mean()), 3),
        "contrast": round(float(luma.std()), 3),
        "p05": round(float(np.percentile(luma, 5)), 3),
        "p95": round(float(np.percentile(luma, 95)), 3),
        "saturation": round(float(sat.mean()), 3),
        "warmth": round(rb, 3),   # R−B; skin-lit talking heads are usually +0.05…+0.15
        "tint": round(gm, 3),     # G−(R+B)/2; >0 green cast, <0 magenta
        "clipped": round(float((luma > 0.98).mean()), 4),
        "crushed": round(float((luma < 0.02).mean()), 4),
        "flat_frames": int(sum(1 for x in luma if x.std() < 0.05)),
    }


def _audio_stats(wav: Path) -> dict:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(wav), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True).stdout
    y = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if len(y) < 16000:
        return {}
    win = 800  # 50 ms
    n = len(y) // win
    rms = np.sqrt((y[: n * win].reshape(n, win) ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    floor = float(np.percentile(db, 10))
    speech = float(np.percentile(db, 90))
    return {
        "noise_db": round(floor, 1),
        "speech_db": round(speech, 1),
        "snr_db": round(speech - floor, 1),
        "peak": round(float(np.abs(y).max()), 3),
        "clip_ratio": round(float((np.abs(y) > 0.985).mean()), 5),
        "dynamic_db": round(float(np.percentile(db, 95) - np.percentile(db, 60)), 1),
    }


def measure(video: Path, duration: float, audio_wav: Path | None = None) -> dict:
    out: dict = {"version": 1}
    try:
        out["video"] = _video_stats(video, duration)
    except Exception as e:  # noqa: BLE001
        out["video_error"] = str(e)[:200]
    if audio_wav is not None and Path(audio_wav).exists():
        try:
            out["audio"] = _audio_stats(audio_wav)
        except Exception as e:  # noqa: BLE001
            out["audio_error"] = str(e)[:200]
    return out


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def auto_grade(analysis: dict | None) -> dict:
    """Small correcting moves only — the look presets do the styling on top."""
    v = (analysis or {}).get("video") or {}
    if not v:
        return {}
    g: dict[str, float] = {}
    L = v.get("luma_center") or v.get("luma") or 0.45
    target = 0.46
    if abs(L - target) > 0.05:
        stops = math.log2(max(0.05, target) / max(0.05, L)) * 2.2 * 0.6
        g["exposure"] = round(_clamp(stops, -0.7, 0.8), 2)
    c = v.get("contrast", 0.2)
    if c < 0.15:
        g["contrast"] = round(_clamp((0.19 - c) * 2.5, 0, 0.25), 2)
    elif c > 0.29:
        g["contrast"] = round(_clamp(-(c - 0.25) * 2, -0.2, 0), 2)
    if v.get("clipped", 0) > 0.03:
        g["highlights"] = -0.25
    if v.get("crushed", 0) > 0.05:
        g["shadows"] = 0.2
    s = v.get("saturation", 0.3)
    if s < 0.18:
        g["vibrance"] = round(_clamp((0.26 - s) * 2.5, 0, 0.35), 2)
    elif s > 0.5:
        g["saturation"] = round(_clamp(-(s - 0.42) * 1.5, -0.25, 0), 2)
    warm = v.get("warmth", 0.08)
    if warm < 0.0:
        g["temperature"] = round(_clamp((0.06 - warm) * 2.5, 0, 0.4), 2)
    elif warm > 0.2:
        g["temperature"] = round(_clamp(-(warm - 0.14) * 2.5, -0.35, 0), 2)
    tint = v.get("tint", 0)
    if abs(tint) > 0.03:
        g["tint"] = round(_clamp(-tint * 4, -0.3, 0.3), 2)
    return g


def auto_voice(analysis: dict | None, base_preset: str = "studio") -> dict:
    a = (analysis or {}).get("audio") or {}
    if not a:
        return {"preset": base_preset}
    out = {"preset": base_preset}
    snr = a.get("snr_db", 40)
    if snr < 22:
        out.update({"denoise": "strong", "gate": 0.45})
    if a.get("dynamic_db", 0) > 14:
        out["compress"] = 0.7
    if a.get("speech_db", -20) < -32:
        out["volume"] = 1.4
    return out


def pace(project: dict) -> dict:
    tr = project.get("transcript") or {}
    words = [w for s in tr.get("segments") or [] for w in s.get("words") or []]
    dur = float((project.get("meta") or {}).get("duration") or 0)
    edl = project.get("edl") or {}
    out_dur = dur - float((edl.get("stats") or {}).get("removed_seconds") or 0)
    wpm = len(words) / (out_dur / 60) if out_dur > 5 else 0
    return {"words": len(words), "wpm": round(wpm), "out_dur": round(out_dur, 1)}


def _item(id_, level, title, detail, fix=None, action=None):
    return {"id": id_, "level": level, "title": title, "detail": detail, "fix": fix, "action": action}


def suggest(project: dict, render_settings: dict, analysis: dict | None, *, library: list[dict] | None = None) -> list[dict]:
    """What's missing or could be better, most important first."""
    rs = render_settings or {}
    fx = rs.get("effects") or {}
    meta = project.get("meta") or {}
    v = (analysis or {}).get("video") or {}
    a = (analysis or {}).get("audio") or {}
    p = pace(project)
    out: list[dict] = []
    is_short = p["out_dur"] <= 75

    # ---- picture
    g = auto_grade(analysis)
    cur = fx.get("grade") or {}
    if v:
        L = v.get("luma_center") or v.get("luma") or 0.45
        if L < 0.36:
            out.append(_item("dark", "high", "वीडियो अंधेरा है", f"चेहरे के पास रोशनी {int(L * 100)}% — ठीक 45–50% होती है। अगली बार सामने से light रखें।",
                             {"effects": {"grade": {**cur, **g}}}))
        elif L > 0.62:
            out.append(_item("bright", "mid", "वीडियो ज़्यादा चमकीला है", "highlights दबाकर चेहरा साफ़ करें।", {"effects": {"grade": {**cur, **g}}}))
        if v.get("contrast", 0.2) < 0.15:
            out.append(_item("flat", "mid", "रंग फीके / धुँधले लग रहे हैं", "contrast और vibrance थोड़ा बढ़ाएँ।", {"effects": {"grade": {**cur, **g}}}))
        if v.get("warmth", 0.08) < 0.0 or v.get("warmth", 0.08) > 0.2 or abs(v.get("tint", 0)) > 0.03:
            kind = "नीला/ठंडा" if v.get("warmth", 0.08) < 0 else "ज़्यादा पीला/लाल" if v.get("warmth", 0) > 0.2 else "हरा/गुलाबी"
            out.append(_item("cast", "mid", f"रंग में {kind} झुकाव", "white balance ठीक करने से skin tone नेचुरल लगेगा।", {"effects": {"grade": {**cur, **g}}}))
        if g and not any(x["id"] in ("dark", "bright", "flat", "cast") for x in out) and not cur:
            out.append(_item("grade", "low", "Auto color correction", "हल्का सुधार तैयार है।", {"effects": {"grade": g}}))
    if int(meta.get("height") or 0) and min(int(meta.get("width") or 0), int(meta.get("height") or 0)) < 720:
        out.append(_item("lowres", "mid", "Resolution कम है", f"{meta.get('width')}×{meta.get('height')} — अगली बार 1080p या 4K में record करें।",
                         {"effects": {"extras": sorted(set((fx.get("extras") or []) + ["sharpen"]))}}))

    # ---- sound
    vc = fx.get("voice") or {}
    if a:
        if a.get("snr_db", 40) < 22:
            out.append(_item("noise", "high", "पीछे शोर (noise) ज़्यादा है", f"आवाज़ और शोर का फ़र्क़ {a['snr_db']} dB — 30+ अच्छा है। तेज़ noise हटाना + gate।",
                             {"effects": {"voice": {**vc, "denoise": "strong", "gate": 0.45}}}))
        if a.get("clip_ratio", 0) > 0.0005:
            out.append(_item("clip", "high", "आवाज़ कहीं-कहीं फट रही है (clipping)", "recording के समय mic का gain कम करें / मुँह से थोड़ा दूर रखें। अभी limiter से नरम कर दें।",
                             {"effects": {"voice": {**vc, "compress": max(0.6, float(vc.get("compress") or 0))}}}))
        if a.get("dynamic_db", 0) > 14:
            out.append(_item("uneven", "mid", "आवाज़ कहीं धीमी कहीं तेज़", "compressor से बराबर करें।", {"effects": {"voice": {**vc, "compress": 0.7}}}))
        if a.get("speech_db", -20) < -32:
            out.append(_item("quiet", "mid", "आवाज़ धीमी रिकॉर्ड हुई", "volume बढ़ाएँ।", {"effects": {"voice": {**vc, "volume": 1.4}}}))
    if (vc.get("preset") or "studio") == "off":
        out.append(_item("voiceoff", "mid", "Voice enhance बंद है", "Studio preset से आवाज़ साफ़ और भरी हुई लगेगी।", {"effects": {"voice": {"preset": "studio"}}}))

    music = fx.get("music") or {}
    if not music.get("id"):
        lib = [x for x in (library or []) if x.get("kind") == "music"]
        fix = {"effects": {"music": {**music, "id": lib[0]["id"], "volume": 0.12, "duck": True}}} if lib else None
        out.append(_item("music", "mid", "Background music नहीं है", "हल्का music (duck के साथ) retention बढ़ाता है।", fix))
    elif float(music.get("volume", 0.18)) > 0.3:
        out.append(_item("musicloud", "mid", "Music आवाज़ को दबा सकता है", "volume 10–18% रखें।", {"effects": {"music": {**music, "volume": 0.14}}}))

    # ---- story / retention
    hook = (rs.get("hook") or {}).get("text")
    if not hook:
        out.append(_item("hook", "high", "शुरू में hook/heading नहीं है", "पहले 3 सेकंड में बड़ा text — लोग रुकते हैं।", None, "hook"))
    if not rs.get("burn_captions", True):
        out.append(_item("captions", "high", "Captions बंद हैं", "80% लोग बिना आवाज़ देखते हैं।", {"burn_captions": True}))
    zoom = fx.get("zoom") or {}
    if not zoom.get("enabled") and p["out_dur"] > 15:
        out.append(_item("zoom", "mid", "Auto zoom बंद है", "बोलते चेहरे पर हल्का zoom in/out वीडियो को ज़िंदा रखता है।",
                         {"effects": {"zoom": {**zoom, "enabled": True, "mode": "punch" if is_short else "push", "strength": 0.9}}}))
    visuals = len(fx.get("broll") or []) + len(fx.get("titles") or [])
    if p["out_dur"] > 45 and visuals < p["out_dur"] / 40:
        out.append(_item("visuals", "mid", "लंबे हिस्से में कुछ नया नहीं दिखता", f"{int(p['out_dur'])}s में सिर्फ़ {visuals} B-roll/text — हर 15–25s पर sticker, text या B-roll डालें।", None, "media"))
    if (fx.get("transition") or "none") == "none" and is_short:
        out.append(_item("transition", "low", "कट पर transition नहीं", "Shorts में punch/whip से तेज़ flow लगता है।", {"effects": {"transition": "punch"}}))
    if p["wpm"] and p["wpm"] < 95 and p["out_dur"] > 20:
        out.append(_item("slow", "mid", "बोलने की रफ़्तार धीमी है", f"{p['wpm']} शब्द/मिनट — कट और कड़े करें या 1.1× speed।", None, "cuts"))
    if not any(b.get("anim") and "cta" in (b.get("_id") or "") for b in fx.get("broll") or []) and p["out_dur"] > 10:
        out.append(_item("cta", "low", "Subscribe/Follow popup नहीं है", "अंत के पास CTA popup (हर platform का अपना)।", None, "cta"))
    if not is_short and not (meta.get("shorts") or []):
        out.append(_item("shorts", "low", "इस वीडियो से Shorts नहीं बने", "AI से 3–5 Shorts निकालें।", None, "shorts"))
    order = {"high": 0, "mid": 1, "low": 2}
    out.sort(key=lambda x: order[x["level"]])
    return out
