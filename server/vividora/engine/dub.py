"""AI voice-over / dubbing — the server-side plan for a `dub` job.

Three modes:
  revoice  "आवाज़ बदलें / साफ़ AI आवाज़" — the creator's own words (after cuts), same language,
           spoken by an AI voice, each line fitted into the slot where it was said.
  dub      translate hi→en / en→hi (ONE LLM call for all lines, cached on disk) and voice it,
           fitted the same way.
  script   the creator types a script (faceless / montage videos) → a voice track whose
           timing doubles as a transcript for captions.

The plan (text + output-timeline slots) is built here, where the transcript, cuts and the
LLM key live; the worker (GPU PC, or CPU with TTS_LOCAL=1) only synthesises — see engine/tts.py.
Autopilot never calls this: dubbing is always the creator's own click.
"""

from __future__ import annotations

import hashlib
import json
import re

from . import llm
from .autocut import keep_segments, norm
from .render import out_timeline
from .tts import LANGS, VOICE_PRESETS, voice_preset

MODES = {"revoice": "आवाज़ बदलें / साफ़ AI आवाज़", "dub": "Dub (दूसरी भाषा)", "script": "Script से voice-over"}
_DEVA = re.compile(r"[ऀ-ॿ]")


def presets_json() -> dict:
    return {"voices": VOICE_PRESETS, "langs": LANGS, "modes": MODES}


def detect_lang(text: str, hint: str | None = None) -> str:
    if hint in LANGS:
        return hint
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return "hi"
    deva = sum(1 for ch in letters if _DEVA.match(ch))
    return "hi" if deva / len(letters) > 0.3 else "en"


def timeline_sig(edl: dict | None, effects: dict | None) -> str:
    """Changes when cuts / speed ramps / clip transitions change → the dub's timing is stale."""
    edl = edl or {}
    e = effects or {}
    keep = [(round(a, 2), round(b, 2)) for a, b in keep_segments(edl)] if edl.get("duration") else []
    tr = e.get("transition") or "none"
    data = {"keep": keep, "speed": e.get("speed") or edl.get("speed") or [], "xfade": tr if tr.startswith("x_") else "",
            "cut_tr": sorted(str(c.get("transition")) for c in (edl.get("cuts") or []) if str(c.get("transition") or "").startswith("x_"))}
    return hashlib.sha1(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]


def resolve_voice(voice_id: str | None, description: str | None, lang: str) -> dict:
    """Preset id (or a custom Parler description) → the voice block of the job payload."""
    v = voice_preset(voice_id)
    desc = (description or "").strip()[:600]
    if v and v["lang"] != lang and v["engine"] == "kokoro":
        raise ValueError("Kokoro आवाज़ सिर्फ़ English के लिए है — हिन्दी के लिए रोहित/दिव्या/अमन/रानी चुनें")
    if v is None:
        v = next(x for x in VOICE_PRESETS if x["lang"] == lang)
    out = {k: v.get(k) for k in ("id", "label", "engine", "gender", "description", "kokoro_voice", "kokoro_lang") if v.get(k)}
    if desc:
        # a custom description always goes to Parler (Kokoro has fixed voices)
        out.update(engine="parler", description=desc, id="custom", label="अपनी आवाज़ (description)")
        out.pop("kokoro_voice", None)
        out.pop("kokoro_lang", None)
    return out


def transcript_lines(project: dict, effects: dict | None) -> tuple[list[dict], float]:
    """Transcript segments → [{text, start, end}] on the OUTPUT timeline (cut words dropped), output duration."""
    tr = project.get("transcript") or {}
    meta = project.get("meta") or {}
    dur = float(meta.get("duration") or 0)
    edl = {"duration": dur, "cuts": [], **(project.get("edl") or {})}
    to_out, out_dur = out_timeline(edl, float(meta.get("fps") or 30), effects)
    lines: list[dict] = []
    for seg in tr.get("segments") or []:
        words = [w for w in (seg.get("words") or []) if w.get("start") is not None and w.get("end") is not None]
        kept = []
        for w in words:
            t = to_out(float(w["start"]))
            text = (w.get("w") or w.get("word") or "").strip()
            if t is None or not text or not norm(text):
                continue
            kept.append((t, t + max(0.05, min(3.0, float(w["end"]) - float(w["start"]))), text))
        if not words:  # transcript without word timing
            a, b = to_out(float(seg.get("start", 0))), to_out(max(float(seg.get("start", 0)), float(seg.get("end", 0)) - 0.02))
            if a is not None and b is not None and (seg.get("text") or "").strip():
                lines.append({"text": seg["text"].strip(), "start": round(a, 3), "end": round(max(b, a + 0.3), 3)})
            continue
        if not kept:
            continue
        # a jump cut inside a segment that skips > 1.2 s of output → two lines
        group = [kept[0]]
        for k in kept[1:]:
            if k[0] - group[-1][1] > 1.2:
                lines.append(_line(group))
                group = []
            group.append(k)
        lines.append(_line(group))
    return [ln for ln in lines if ln["text"]], out_dur


def _line(group: list[tuple[float, float, str]]) -> dict:
    return {"text": " ".join(g[2] for g in group).strip(), "start": round(group[0][0], 3), "end": round(group[-1][1], 3)}


def translate(lines: list[dict], src: str, dst: str) -> list[dict]:
    """ONE JSON call for all lines (llm.ask_json caches on disk — the same dub twice costs nothing)."""
    if not llm.available():
        raise ValueError("Dub के लिए translation चाहिए — server .env में GEMINI_API_KEY (या ANTHROPIC_API_KEY) डालें")
    names = {"hi": "Hindi (Devanagari script, natural spoken Hindi; common English words may stay as they are)",
             "en": "English (natural, simple spoken Indian English)"}
    items = [{"i": i, "t": ln["text"], "sec": round(ln["end"] - ln["start"], 1)} for i, ln in enumerate(lines)]
    prompt = (f"Translate these lines of a motivational YouTube video from {names[src]} to {names[dst]} for a voice-over dub.\n"
              "Rules: keep the meaning and emotion; each line must be speakable in about the same seconds (`sec`) — "
              "short, natural, no explanations; keep names; do not merge or split lines; keep every `i`.\n"
              'Reply as JSON: {"items": [{"i": 0, "t": "..."}]}\n\n' + json.dumps(items, ensure_ascii=False))
    chars = sum(len(x["t"]) for x in items)
    res = llm.ask_json(prompt, system="You are a professional dubbing translator. Reply with JSON only.",
                       max_tokens=min(16000, 600 + chars * 4), timeout=180)
    got = {}
    for it in (res or {}).get("items", []) if isinstance(res, dict) else (res or []):
        try:
            if str(it.get("t") or "").strip():
                got[int(it["i"])] = str(it["t"]).strip()
        except (TypeError, ValueError, KeyError, AttributeError):
            continue
    if not got or len(got) < 0.9 * len(lines):
        raise ValueError("AI translation पूरा नहीं आया — थोड़ी देर बाद फिर कोशिश करें")
    out = []
    for i, ln in enumerate(lines):
        if i in got:
            out.append({**ln, "text": got[i], "source": ln["text"]})
    return out


def mix_voice_over(video, voice, out, *, duck: bool = True) -> list[str]:
    """Montage / finished video + AI voice-over → same picture, voice on top, its music ducked
    under the voice, loudness -14 LUFS. → warnings."""
    from . import ffmpeg
    info = ffmpeg.probe(video)
    dur = float(info.get("duration") or 0)
    vdur = float(ffmpeg.probe(voice).get("duration") or 0)
    v = f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,apad,atrim=0:{dur:.3f}"
    if info.get("has_audio"):
        m = "[0:a]aformat=sample_rates=48000:channel_layouts=stereo"
        if duck:
            fc = (f"{v},asplit[vm][vs];{m}[mus];[mus][vs]sidechaincompress=threshold=0.02:ratio=12:attack=15:release=450:makeup=1[md];"
                  f"[md][vm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mx]")
        else:
            fc = f"{v}[vm];{m}[mus];[mus][vm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mx]"
    else:
        fc = f"{v}[mx]"
    fc += ";[mx]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]"
    ffmpeg.run(["-i", str(video), "-i", str(voice), "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{dur:.3f}", str(out)],
               label="voice-over mix")
    return [f"AI voice-over {vdur:.0f}s का है, वीडियो {dur:.0f}s — बाकी आवाज़ कट गई (montage लंबा करें)"] if vdur > dur + 0.5 else []


def plan(project: dict, *, mode: str, language: str | None, script: str = "", effects: dict | None = None) -> dict:
    """→ {mode, language, source_language, segments, total, sig}. Raises ValueError with a Hindi message."""
    if mode not in MODES:
        raise ValueError("mode: revoice / dub / script")
    eff = effects or {}
    edl = {"duration": float((project.get("meta") or {}).get("duration") or 0), "cuts": [], **(project.get("edl") or {})}
    sig = timeline_sig(edl, eff)
    if mode == "script":
        from .tts import script_lines
        text = (script or "").strip()
        if len(text) < 3:
            raise ValueError("script लिखें या paste करें")
        if len(text) > 20000:
            raise ValueError("script बहुत लंबी है (20,000 अक्षर तक)")
        lang = language if language in LANGS else detect_lang(text)
        return {"mode": mode, "language": lang, "source_language": lang, "segments": script_lines(text), "total": 0, "sig": sig}
    tr = project.get("transcript") or {}
    if not (tr.get("segments") or []):
        raise ValueError("इस project में transcript नहीं है — “Script से voice-over” चुनें")
    lines, out_dur = transcript_lines(project, eff)
    if not lines:
        raise ValueError("कट के बाद बोलने को कुछ नहीं बचा")
    src = detect_lang(" ".join(ln["text"] for ln in lines[:40]), tr.get("language") or project.get("language"))
    if mode == "revoice":
        lang = src
    else:
        lang = language if language in LANGS else ("en" if src == "hi" else "hi")
        if lang == src:
            raise ValueError(f"transcript पहले से {LANGS[src]} में है — दूसरी भाषा चुनें, या “आवाज़ बदलें” mode लें")
        lines = translate(lines, src, lang)
    return {"mode": mode, "language": lang, "source_language": src, "segments": lines, "total": round(out_dur, 3), "sig": sig}
