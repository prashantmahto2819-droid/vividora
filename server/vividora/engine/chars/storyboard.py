"""Storyboard → explainer video.

A storyboard is scenes in order, each with an environment, characters on their spots and dialogue
lines (who says what, how). build() runs on the CPU worker: every line is spoken by the character's
voice (engine/tts), scene lengths follow the speech, backgrounds become the project's main video
(with the dialogue as its sound) and every character becomes a transparent, lip-synced overlay clip
— so the result opens in the normal editor: captions from the dialogue, characters movable, voice
replaceable, music/CTA/thumbnail like any project.

spec = {title, preset: yt-long|ig-reel|yt-short, language: hi|en, scenes: [
          {env, framing, light, props?, title?, hold?,
           chars: [{profile | params, name?, x, y, s, flip?, base?, voice?}],
           lines: [{char: index, text, expr?, gesture?}]}]}
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .. import ffmpeg, tts
from . import anim, catalog, render, rig, scenes2d

PAUSE = 0.35          # between lines
MIN_SCENE = 2.0
PRESET_SIZE = {"yt-long": (1920, 1080), "yt-short": (1080, 1920), "ig-reel": (1080, 1920), "fb-reel": (1080, 1920)}
CHAR_PX = {"yt-long": (420, 840), "yt-short": (480, 960), "ig-reel": (480, 960), "fb-reel": (480, 960)}


def suggest_voice(params: dict, language: str = "hi") -> dict:
    """A TTS preset that fits the character (age / gender / language) + speed."""
    g, age = params.get("gender", "m"), params.get("age", "adult")
    if language == "en":
        vid = "en_mary_warm" if g == "f" else "en_thoma_deep"
    elif g == "f":
        vid = "hi_divya_energetic" if age in ("child", "young") else "hi_rani_news" if age == "adult" and params.get("profession") in ("न्यूज़ एंकर",) else "hi_divya_soft"
    else:
        vid = "hi_rohit_energetic" if age == "young" else "hi_aman_story" if age == "elderly" else "hi_rohit_deep"
    speed = {"child": 1.12, "young": 1.04, "adult": 1.0, "elderly": 0.92}[age]
    v = tts.voice_preset(vid) or tts.VOICE_PRESETS[0]
    return {**v, "speed": speed}


def normalise(spec: dict) -> dict:
    """Fill defaults, resolve profiles → params, validate everything (ValueError in Hindi)."""
    out = {"title": str(spec.get("title") or "Explainer")[:120], "preset": spec.get("preset") or "yt-long",
           "language": "en" if (spec.get("language") or "hi") == "en" else "hi", "theme_id": spec.get("theme_id") or "", "scenes": []}
    if out["preset"] not in PRESET_SIZE:
        raise ValueError("preset yt-long / yt-short / ig-reel में से चुनें")
    scenes = spec.get("scenes") or []
    if not scenes:
        raise ValueError("कम से कम एक scene चाहिए")
    for si, sc in enumerate(scenes):
        env = sc.get("env") or "studio"
        if env not in scenes2d.ENVS:
            raise ValueError(f"scene {si + 1}: environment '{env}' नहीं है")
        slots = scenes2d.ENVS[env]["slots"]
        chars = []
        for ci, ch in enumerate(sc.get("chars") or []):
            params = ch.get("params")
            if not params and ch.get("profile"):
                prof = catalog.get(ch["profile"])
                if not prof:
                    raise ValueError(f"scene {si + 1}: character '{ch['profile']}' नहीं मिला")
                params = prof["params"]
            if not params:
                raise ValueError(f"scene {si + 1}: character {ci + 1} का profile चुनें")
            params = rig.validate(params)
            slot = slots[ci % len(slots)]
            chars.append({"profile": ch.get("profile"), "params": params, "name": ch.get("name") or params.get("name") or f"पात्र {ci + 1}",
                          "x": float(ch.get("x", slot[0])), "y": float(ch.get("y", slot[1])), "s": float(ch.get("s", slot[2])),
                          "flip": bool(ch.get("flip", ci % 2 == 1)), "base": ch.get("base") if ch.get("base") in anim.CLIPS else "idle",
                          "voice": ch.get("voice") or None, "expr": ch.get("expr") or "neutral"})
        lines = []
        for li, ln in enumerate(sc.get("lines") or []):
            text = str(ln.get("text") or "").strip()
            if not text:
                continue
            ci = int(ln.get("char", 0) or 0)
            if chars and not (0 <= ci < len(chars)):
                raise ValueError(f"scene {si + 1}, line {li + 1}: बोलने वाला character नहीं मिला")
            lines.append({"char": ci, "text": text[:400], "expr": ln.get("expr") if ln.get("expr") in catalog.EXPRESSIONS else None,
                          "gesture": ln.get("gesture") if ln.get("gesture") in anim.CLIPS else "talk"})
        out["scenes"].append({"env": env, "framing": sc.get("framing") if sc.get("framing") in scenes2d.FRAMING else "wide",
                              "light": sc.get("light") if sc.get("light") in scenes2d.LIGHT else "day", "props": sc.get("props"),
                              "title": str(sc.get("title") or "")[:80], "hold": max(0.0, float(sc.get("hold", 0.6) or 0)),
                              "chars": chars, "lines": lines})
    return out


def _speak(backend, lang: str, line: dict, voice: dict, work: Path, tag: str) -> tuple[Path, float]:
    speed = float(voice.get("speed") or 1.0)
    raw = tts.synth_text(backend, line["text"], voice, lang, speed if getattr(backend, "native_speed", False) else 1.0, work, tag)
    if not getattr(backend, "native_speed", False) and abs(speed - 1.0) > 0.02:
        fitted = work / f"{tag}_sp.wav"
        tts.stretch(raw, fitted, speed)
        raw = fitted
    return raw, tts.wav_seconds(raw)


def build(spec_in: dict, work: Path, on_progress=None) -> dict:
    """Worker side. Returns {bg_video, raw_wav, duration, scenes[], overlays[], transcript, size}."""
    spec = normalise(spec_in)
    prog = on_progress or (lambda f, m: None)
    work.mkdir(parents=True, exist_ok=True)
    W, H = PRESET_SIZE[spec["preset"]]
    cw, chh = CHAR_PX[spec["preset"]]
    lang = spec["language"]
    engine = None
    backend = None
    # --- 1. voices: every line, in order, placed on one timeline
    n_lines = sum(len(s["lines"]) for s in spec["scenes"])
    pcm = bytearray()
    t = 0.4
    k = 0
    timeline = []  # scene timing
    for si, sc in enumerate(spec["scenes"]):
        start = t
        for li, ln in enumerate(sc["lines"]):
            ch = sc["chars"][ln["char"]] if sc["chars"] else None
            voice = (tts.voice_preset(ch["voice"]) if ch and ch.get("voice") else None) or suggest_voice(ch["params"] if ch else {}, lang)
            if voice.get("speed") is None:
                voice = {**voice, "speed": 1.0}
            eng = voice.get("engine") or "parler"
            if backend is None or engine != eng:
                tts.check_ready(eng)
                backend, engine = tts.backend_for(eng), eng
            k += 1
            prog(0.05 + 0.35 * k / max(1, n_lines), f"आवाज़ {k}/{n_lines}: {ln['text'][:30]}")
            wav, dur = _speak(backend, lang, ln, voice, work / "tts", f"s{si}_l{li}")
            data, _ = tts.read_pcm(wav)
            at = int(round(t * tts.SR)) * 2
            if len(pcm) < at:
                pcm += b"\x00" * (at - len(pcm))
            pcm += data
            ln.update({"start": round(t, 3), "end": round(t + dur, 3), "words": tts.word_times(ln["text"], t, t + dur),
                       "voice": voice.get("id")})
            t += dur + PAUSE
        end = max(t - PAUSE if sc["lines"] else t, start + MIN_SCENE) + sc["hold"]
        if sc["lines"]:
            end = max(end, sc["lines"][-1]["end"] + 0.3)
        t = end
        timeline.append({"start": round(start, 3), "end": round(end, 3)})
    total = round(t + 0.3, 3)
    at = int(round(total * tts.SR)) * 2
    if len(pcm) < at:
        pcm += b"\x00" * (at - len(pcm))
    raw_wav = tts.write_wav(work / "dialogue.wav", bytes(pcm), tts.SR)
    # --- 2. backgrounds → one video with the dialogue
    prog(0.42, "scene backgrounds")
    lst = work / "bg.txt"
    lines_txt = []
    for si, sc in enumerate(spec["scenes"]):
        png = work / f"bg{si:02d}.png"
        render.svg_to_png(scenes2d.scene_svg({**sc, "chars": []}, W, H, with_chars=False), png, W, H)
        d = timeline[si]["end"] - timeline[si]["start"]
        lines_txt.append(f"file '{png.as_posix()}'\nduration {d:.3f}")
    lines_txt.append(f"file '{(work / f'bg{len(spec['scenes']) - 1:02d}.png').as_posix()}'")
    lst.write_text("\n".join(lines_txt) + "\n", encoding="utf-8")
    bg = work / "explainer_bg.mp4"
    ffmpeg.run(["-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(raw_wav), "-vf", f"fps=25,scale={W}:{H},format=yuv420p",
                "-af", f"highpass=f=70,loudnorm=I=-16:TP=-1.5:LRA=11,aresample={tts.SR}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.3f}", "-movflags", "+faststart", str(bg)], label="explainer background")
    # --- 3. characters: one transparent clip per character per scene, lip-synced to its own lines
    overlays = []
    n_ch = sum(len(s["chars"]) for s in spec["scenes"])
    k = 0
    for si, sc in enumerate(spec["scenes"]):
        s0, s1 = timeline[si]["start"], timeline[si]["end"]
        d = s1 - s0
        sw = work / f"scene{si:02d}.wav"
        tts._ff(["-ss", f"{s0:.3f}", "-t", f"{d:.3f}", "-i", str(raw_wav), "-c:a", "pcm_s16le", str(sw)])
        for ci, ch in enumerate(sc["chars"]):
            k += 1
            prog(0.45 + 0.5 * k / max(1, n_ch), f"character {ch['name']} (scene {si + 1})")
            words = []
            segs = []
            for ln in sc["lines"]:
                if ln["char"] != ci:
                    continue
                words += [{"w": w["w"], "start": round(w["start"] - s0, 3), "end": round(w["end"] - s0, 3)} for w in ln["words"]]
                segs.append({"t0": round(ln["start"] - s0, 3), "t1": round(ln["end"] - s0 + 0.15, 3), "gesture": ln.get("gesture") or "talk",
                             "expr": ln.get("expr") or ch.get("expr")})
            spec_clip = {"dur": round(d, 3), "base": ch["base"], "expr": ch.get("expr") or "neutral", "seed": si * 10 + ci,
                         "phase": ci * 0.7, "flip": ch["flip"], "segments": segs,
                         "lip": {"words": words, "wav": str(sw), "wav_sig": f"{si}:{s0}:{d}:{len(words)}"} if words else None}
            clip = render.clip_webm(ch["params"], spec_clip, cw, chh, on_progress=lambda f, m, _k=k: prog(0.45 + 0.5 * (_k - 1 + f) / max(1, n_ch), m))
            dst = work / f"char_s{si:02d}_c{ci}.webm"
            shutil.copyfile(clip, dst)
            place = scenes2d.char_place(ch, W, H, sc)
            overlays.append({"label": f"s{si:02d}_c{ci}", "path": str(dst), "start": round(s0, 3), "end": round(s1, 3),
                             "x": place["x"], "y": place["y"], "scale": place["scale"], "name": ch["name"],
                             "char": {"profile": ch.get("profile"), "params": ch["params"], "base": ch["base"], "scene": si}})
    transcript = {"language": lang, "segments": [
        {"start": ln["start"], "end": ln["end"], "text": ln["text"], "speaker": sc["chars"][ln["char"]]["name"] if sc["chars"] else "",
         "words": ln["words"]} for sc in spec["scenes"] for ln in sc["lines"]]}
    transcript["text"] = " ".join(s["text"] for s in transcript["segments"])
    (work / "storyboard.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return {"bg_video": bg, "raw_wav": raw_wav, "duration": total, "scenes": timeline, "overlays": overlays,
            "transcript": transcript, "size": [W, H], "spec": spec}
