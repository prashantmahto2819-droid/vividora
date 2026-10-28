"""3D Studio engine — characters, scenes, lip-sync and headless rendering.

The 3D work itself (rig, animation, scenes) lives in web/dist/assets/chars3d.js and runs in Chromium
(three.js, software GL). This module drives it from the worker:

  render_frames(spec, out_dir)   headless Chromium → PNG frames (alpha or opaque), cached by spec hash
  encode(frames, out, audio)     PNG sequence → VP9 webm with alpha (overlay clip) or H.264 mp4 (scene)
  speak(lines, work)             TTS per line (engine/tts backends) → wav + word timings + viseme events
  storyboard(...)                scenes × characters × lines → one explainer mp4 + transcript

Nothing is downloaded at runtime; three.js is vendored (web/dist/assets/three.module.min.js, MIT).
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Callable

from .. import ffmpeg
from .profiles import BY_ID, CATEGORIES, PROFILES

ANIMATIONS = ["idle", "walk", "run", "sit", "talk1", "talk2", "talk3", "wave", "point", "type", "nod", "laugh", "dance", "teach"]
ANIM_LABELS = {"idle": "खड़ा (idle)", "walk": "चलना", "run": "दौड़ना", "sit": "बैठना", "talk1": "बोलना 1", "talk2": "बोलना 2", "talk3": "बोलना 3",
               "wave": "हाथ हिलाना", "point": "इशारा", "type": "typing", "nod": "हाँ (nod)", "laugh": "हँसना", "dance": "नाचना", "teach": "पढ़ाना"}
SCENES = ["classroom", "office", "clinic", "home", "shop", "gym", "park", "stage"]
SCENE_LABELS = {"classroom": "Classroom (greenboard)", "office": "Office", "clinic": "Clinic / hospital", "home": "घर (living room)", "shop": "दुकान / store",
                "gym": "Gym", "park": "सड़क / park", "stage": "Stage / event"}
LIGHTING = ["day", "evening", "night"]
CAMERAS = ["wide", "medium", "closeup", "twoshot", "low", "high", "full"]
EXPRESSIONS = ["smile", "sad", "angry", "surprised", "think"]
VISEMES = ["sil", "aa", "ee", "oh", "oo", "mm", "ff", "ss"]

ProgressFn = Callable[[float, str], None]

# ---------------------------------------------------------------- lip-sync (same tables as chars3d.js)
_DEV_V = {"अ": 1, "आ": 1, "ा": 1, "इ": 2, "ई": 2, "ि": 2, "ी": 2, "उ": 4, "ऊ": 4, "ु": 4, "ू": 4, "ए": 2, "ऐ": 2, "े": 2, "ै": 2, "ओ": 3, "औ": 3, "ो": 3, "ौ": 3,
          "ऋ": 2, "ृ": 2, "ं": 5, "ँ": 5}
_DEV_C = {"प": 5, "फ": 6, "ब": 5, "भ": 5, "म": 5, "व": 6, "स": 7, "श": 7, "ष": 7, "ज": 7, "च": 7, "छ": 7, "झ": 7, "त": 7, "थ": 7, "द": 7, "ध": 7, "न": 7,
          "ट": 1, "ठ": 1, "ड": 1, "ढ": 1, "ण": 1, "क": 1, "ख": 1, "ग": 1, "घ": 1, "ह": 1, "ल": 7, "र": 1, "य": 2}
_LAT = {"a": 1, "e": 2, "i": 2, "o": 3, "u": 4, "y": 2, "p": 5, "b": 5, "m": 5, "f": 6, "v": 6, "w": 4, "s": 7, "z": 7, "t": 7, "d": 7, "n": 7, "l": 7,
        "c": 7, "j": 7, "k": 1, "g": 1, "h": 1, "r": 1, "q": 1, "x": 7}


def visemes_for_word(w: str) -> list[int]:
    out = [v for ch in w.lower() for v in [_DEV_V.get(ch, _DEV_C.get(ch, _LAT.get(ch)))] if v is not None]
    return out or [1]


def viseme_events(words: list[dict], energy: list[float] | None = None, step: float = 0.04) -> list[list]:
    """[{w,start,end}] → [[t, viseme, weight]] — weight follows the audio envelope when given (step 0.02 s)."""
    ev: list[list] = []
    for wd in words:
        vs = visemes_for_word(wd["w"])
        span = max(0.05, float(wd["end"]) - float(wd["start"]))
        per = span / len(vs)
        for i, v in enumerate(vs):
            t0 = float(wd["start"]) + i * per
            t = t0
            while t < t0 + per:
                ev.append([round(t, 3), v, 1.0])
                t += step
    if energy:
        for e in ev:
            k = min(len(energy) - 1, max(0, int(round(e[0] / 0.02))))
            e[2] = round(0.35 + 0.65 * energy[k], 3)
    return ev


def envelope(wav: Path, step: float = 0.02) -> list[float]:
    """RMS envelope of a wav (0..1), one value per `step` seconds — the jaw follows loudness."""
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(wav), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    n = len(pcm) // 2
    if not n:
        return []
    win = int(16000 * step)
    out = []
    for i in range(0, n, win):
        chunk = pcm[i * 2:(i + win) * 2]
        m = len(chunk) // 2
        if not m:
            break
        vals = struct.unpack(f"<{m}h", chunk)
        out.append(math.sqrt(sum(v * v for v in vals) / m) / 32768.0)
    peak = max(out) or 1.0
    sm = []
    for i, v in enumerate(out):  # light smoothing
        a = out[max(0, i - 1)]
        b = out[min(len(out) - 1, i + 1)]
        sm.append(min(1.0, (0.25 * a + 0.5 * v + 0.25 * b) / peak))
    return sm


# ---------------------------------------------------------------- speech
def speak(lines: list[dict], work: Path, *, engine: str | None = None, gap: float = 0.35, on_progress: ProgressFn | None = None) -> dict:
    """lines: [{text, voice?, speaker?, lang?}] → one wav for the whole dialogue + per-line timing + words.
    Uses the project's TTS backends (Parler / Kokoro / fake for tests). Returns
    {wav, duration, lines:[{start,end,speaker,text,words}], words:[...]}"""
    from .. import tts
    work.mkdir(parents=True, exist_ok=True)
    pcm = bytearray()
    t = 0.0
    out_lines, all_words = [], []
    for i, ln in enumerate(lines):
        text = (ln.get("text") or "").strip()
        if not text:
            continue
        voice = tts.voice_preset(ln.get("voice"))
        if not voice:  # no voice chosen: first one that can actually run on this box (Parler may not be installed), preferring the speaker's gender
            try:
                av = sorted(tts.available_voices(), key=lambda v: v.get("engine") != "voicestudio")
            except Exception:  # noqa: BLE001
                av = []
            g = ln.get("gender") or "m"
            voice = next((v for v in av if v.get("gender") == g), None) or (av[0] if av else None) or tts.VOICE_PRESETS[0 if g == "m" else 3]
        eng = engine or voice.get("engine") or "parler"
        backend = tts.backend_for(eng)
        lang = ln.get("lang") or voice.get("lang") or "hi"
        wav = tts.synth_text(backend, text, voice, lang, float(ln.get("speed") or 1.0), work, f"line{i}")
        data, _ = tts.read_pcm(wav)
        dur = len(data) / 2 / tts.SR
        words = tts.word_times(text, t, t + dur)
        out_lines.append({"start": round(t, 3), "end": round(t + dur, 3), "speaker": ln.get("speaker", 0), "text": text, "words": words})
        all_words += words
        pcm += data + b"\x00\x00" * int(tts.SR * gap)
        t += dur + gap
        if on_progress:
            on_progress((i + 1) / max(1, len(lines)), f"आवाज़ {i + 1}/{len(lines)}")
    full = tts.write_wav(work / "dialogue.wav", bytes(pcm), tts.SR)
    return {"wav": full, "duration": round(t, 3), "lines": out_lines, "words": all_words}


# ---------------------------------------------------------------- headless render
def _chromium_args() -> list[str]:
    return ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--no-sandbox",
            "--disable-dev-shm-usage", "--hide-scrollbars"]


def _browser(p):
    kw = {"args": _chromium_args()}
    exe = os.getenv("CHROMIUM_PATH")
    if exe:
        kw["executable_path"] = exe
    elif Path("/opt/pw-browsers/chromium").exists():
        kw["executable_path"] = "/opt/pw-browsers/chromium"
    return p.chromium.launch(**kw)


def spec_hash(spec: dict) -> str:
    return hashlib.sha1(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def render_frames(spec: dict, out_dir: Path, *, page_url: str, on_progress: ProgressFn | None = None, jpeg: bool = False) -> dict:
    """Render every frame of `spec` (see chars3d.js buildShot) into out_dir/00001.png… Returns {frames, width, height, info}."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("3D render के लिए playwright चाहिए: pip install playwright && playwright install chromium") from e
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = "jpg" if jpeg else "png"
    with sync_playwright() as p:
        b = _browser(p)
        try:
            pg = b.new_page(viewport={"width": int(spec.get("width", 1280)), "height": int(spec.get("height", 720))})
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(page_url, wait_until="load", timeout=60000)
            pg.wait_for_function("window.__ready", timeout=60000)
            info = pg.evaluate("s => window.setup3d(s)", spec)
            if errors:
                raise RuntimeError("3D page error: " + errors[0][:300])
            n = int(info["frames"])
            q = '"jpeg"' if jpeg else "null"
            for i in range(n):
                ffmpeg.check_cancel()
                data = pg.evaluate(f"window.frame3d({i}, {q})")
                (out_dir / f"{i + 1:05d}.{ext}").write_bytes(base64.b64decode(data.split(",", 1)[1]))
                if on_progress and (i % 5 == 0 or i == n - 1):
                    on_progress((i + 1) / n, f"frame {i + 1}/{n}")
            if errors:
                raise RuntimeError("3D page error: " + errors[0][:300])
        finally:
            b.close()
    return {"frames": n, "width": info["width"], "height": info["height"], "info": info, "ext": ext}


def encode(frames_dir: Path, out: Path, *, fps: int = 25, audio: Path | None = None, alpha: bool = True, ext: str = "png",
           on_progress: ProgressFn | None = None, duration: float | None = None) -> Path:
    """PNG sequence → VP9 webm with alpha (an overlay clip the editor can place anywhere) or H.264 mp4."""
    args = ["-framerate", str(fps), "-i", str(frames_dir / f"%05d.{ext}")]
    if audio:
        args += ["-i", str(audio)]
    if alpha:
        args += ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "26", "-row-mt", "1", "-auto-alt-ref", "0", "-deadline", "good", "-cpu-used", "2"]
        if audio:
            args += ["-c:a", "libopus", "-b:a", "96k"]
    else:
        args += ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        if audio:
            args += ["-c:a", "aac", "-b:a", "160k"]
    args += ["-shortest"] if audio else []
    args += [str(out)]
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(args, duration=duration, on_progress=on_progress, label="3D encode")
    return out


def default_lines_spec(profile_spec: dict, *, animation: str = "idle", expression: str | None = None, pos=None, ry: float = 0.0) -> dict:
    return {"spec": profile_spec, "animation": animation, "expression": expression or profile_spec.get("expression", "smile"),
            "expressionAmount": 0.4, **({"pos": pos} if pos else {}), "ry": ry}


# ---------------------------------------------------------------- jobs
def character_clip(pl: dict, work: Path, *, page_url: str, on_progress: ProgressFn | None = None) -> dict:
    """One character, optional dialogue lines, transparent background → webm (alpha) + poster png.
    pl: {spec|profile, animation, talk_animation, expression, lines:[{text,voice}], seconds, fps, width, height, camera, scene?, lighting?}"""
    prog = on_progress or (lambda f, m: None)
    spec_c = dict(BY_ID[pl["profile"]]["spec"]) if pl.get("profile") in BY_ID else {}
    spec_c.update(pl.get("spec") or {})
    fps = int(pl.get("fps") or 25)
    lines = [ln for ln in (pl.get("lines") or []) if (ln.get("text") or "").strip()]
    audio = None
    visemes: list = []
    talk: list = []
    if lines:
        prog(0.02, "आवाज़ बन रही है")
        sp = speak(lines, work / "tts", on_progress=lambda f, m: prog(0.02 + 0.18 * f, m))
        audio = sp["wav"]
        env = envelope(audio)
        visemes = viseme_events(sp["words"], env)
        talk = [[ln["start"], ln["end"]] for ln in sp["lines"]]
        seconds = max(float(pl.get("seconds") or 0), sp["duration"] + 0.4)
    else:
        seconds = float(pl.get("seconds") or 5)
    seconds = min(seconds, 120.0)
    transparent = not pl.get("scene")
    glb_b64 = None
    if pl.get("glb_path"):  # an imported / generated .glb replaces the procedural body (see chars3d.js loadGlbRig)
        glb_b64 = base64.b64encode(Path(pl["glb_path"]).read_bytes()).decode()
    ch = {"spec": spec_c, "animation": pl.get("animation") or "idle", "talkAnimation": pl.get("talk_animation"), "expression": pl.get("expression"),
          "expressionAmount": float(pl.get("expression_amount") or 0.5), "visemes": visemes, "talk": talk, "speed": float(pl.get("speed") or 1)}
    if glb_b64:
        ch["glb"] = glb_b64
        ch["fit"] = pl.get("fit") or {}
    if pl.get("scene"):
        ch["slot"] = int(pl.get("slot") or 0)
    spec = {"width": int(pl.get("width") or (720 if transparent else 1280)), "height": int(pl.get("height") or (1080 if transparent else 720)),
            "fps": fps, "duration": seconds, "transparent": transparent, "characters": [ch],
            "camera": {"preset": ("full" if glb_b64 and (pl.get("camera") or "medium") == "medium" else pl.get("camera")) or ("medium" if transparent else "wide"), **(pl.get("camera_opts") or {})},
            **({"scene": {"name": pl["scene"], "lighting": pl.get("lighting") or "day"}} if pl.get("scene") else {})}
    fr = work / "frames"
    prog(0.2, "3D frames बन रहे हैं")
    r = render_frames(spec, fr, page_url=page_url, on_progress=lambda f, m: prog(0.2 + 0.6 * f, m), jpeg=not transparent)
    poster = work / "poster.png"
    shutil.copy(fr / f"00001.{r['ext']}", poster if transparent else work / "poster.jpg")
    out = work / ("character.webm" if transparent else "scene.mp4")
    prog(0.8, "encode")
    encode(fr, out, fps=fps, audio=audio, alpha=transparent, ext=r["ext"], on_progress=lambda f, m: prog(0.8 + 0.19 * f, m), duration=seconds)
    return {"file": out, "poster": poster if transparent else work / "poster.jpg", "duration": seconds, "width": spec["width"], "height": spec["height"],
            "alpha": transparent, "visemes": len(visemes), "lines": len(lines), "frames": r["frames"]}


def storyboard(pl: dict, work: Path, *, page_url: str, on_progress: ProgressFn | None = None) -> dict:
    """pl: {title, width, height, fps, scenes:[{scene, lighting, camera, orbit, characters:[{profile|spec, slot, animation, expression}],
    lines:[{speaker (index into characters), text, voice}], hold}]} → one mp4 (scene + characters + voice) and a transcript."""
    prog = on_progress or (lambda f, m: None)
    fps = int(pl.get("fps") or 25)
    W, H = int(pl.get("width") or 1920), int(pl.get("height") or 1080)
    parts, transcript_segments, cursor = [], [], 0.0
    scenes = pl.get("scenes") or []
    for si, sc in enumerate(scenes):
        sw = work / f"scene{si}"
        sw.mkdir(parents=True, exist_ok=True)
        chars = sc.get("characters") or []
        lines = [ln for ln in (sc.get("lines") or []) if (ln.get("text") or "").strip()]
        for ln in lines:  # the speaker's profile decides the default voice gender
            spk = chars[int(ln.get("speaker") or 0) % max(1, len(chars))] if chars else {}
            sp_spec = dict(BY_ID.get(spk.get("profile"), {}).get("spec", {}))
            sp_spec.update(spk.get("spec") or {})
            ln.setdefault("gender", sp_spec.get("gender", "m"))
        audio, sp = None, None
        if lines:
            sp = speak(lines, sw / "tts", on_progress=lambda f, m: prog((si + 0.15 * f) / len(scenes), f"scene {si + 1}: {m}"))
            audio = sp["wav"]
            env = envelope(audio)
        dur = max(float(sc.get("hold") or 0), (sp["duration"] + 0.5) if sp else 4.0)
        dur = min(dur, 180.0)
        cs = []
        for ci, c in enumerate(chars):
            spec_c = dict(BY_ID[c["profile"]]["spec"]) if c.get("profile") in BY_ID else {}
            spec_c.update(c.get("spec") or {})
            mine = [ln for ln in (sp["lines"] if sp else []) if int(ln.get("speaker") or 0) == ci]
            words = [w for ln in mine for w in ln["words"]]
            cs.append({"spec": spec_c, "slot": int(c.get("slot", ci)), "animation": c.get("animation") or None, "expression": c.get("expression") or "smile",
                       "expressionAmount": 0.4, "visemes": viseme_events(words, env) if words else [], "talk": [[ln["start"], ln["end"]] for ln in mine],
                       "talkAnimation": c.get("talk_animation")})
            if cs[-1]["animation"] is None:
                del cs[-1]["animation"]
        spec = {"width": W, "height": H, "fps": fps, "duration": dur, "transparent": False, "characters": cs,
                "scene": {"name": sc.get("scene") or "office", "lighting": sc.get("lighting") or "day"},
                "camera": {"preset": sc.get("camera") or ("twoshot" if len(cs) > 1 else "medium"), "orbit": float(sc.get("orbit") or 0), "push": float(sc.get("push") or 0)}}
        fr = sw / "frames"
        r = render_frames(spec, fr, page_url=page_url, on_progress=lambda f, m: prog((si + 0.15 + 0.7 * f) / len(scenes), f"scene {si + 1}: {m}"), jpeg=True)
        seg = sw / "scene.mp4"
        encode(fr, seg, fps=fps, audio=audio, alpha=False, ext=r["ext"], duration=dur, on_progress=lambda f, m: prog((si + 0.85 + 0.14 * f) / len(scenes), f"scene {si + 1}: encode"))
        if not audio:  # keep a silent track so the concat has uniform streams
            seg2 = sw / "scene_a.mp4"
            ffmpeg.run(["-i", str(seg), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-shortest", "-c:v", "copy", "-c:a", "aac", "-b:a", "96k", str(seg2)], label="silent track")
            seg = seg2
        parts.append(seg)
        if sp:
            for ln in sp["lines"]:
                transcript_segments.append({"start": round(cursor + ln["start"], 3), "end": round(cursor + ln["end"], 3), "text": ln["text"],
                                            "words": [{"w": w["w"], "start": round(cursor + w["start"], 3), "end": round(cursor + w["end"], 3)} for w in ln["words"]]})
        cursor += dur
        shutil.rmtree(fr, ignore_errors=True)
    lst = work / "parts.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    out = work / "explainer.mp4"
    ffmpeg.run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", str(out)], label="3D explainer", duration=cursor, on_progress=lambda f, m: prog(0.98 + 0.02 * f, "जोड़ रहे हैं"))
    transcript = {"language": pl.get("language") or "hi", "text": " ".join(s["text"] for s in transcript_segments), "segments": transcript_segments, "source": "script3d"}
    return {"file": out, "duration": round(cursor, 3), "scenes": len(scenes), "transcript": transcript}


def catalogue() -> dict:
    return {"profiles": PROFILES, "categories": CATEGORIES, "animations": [{"id": a, "label": ANIM_LABELS[a]} for a in ANIMATIONS],
            "scenes": [{"id": s, "label": SCENE_LABELS[s]} for s in SCENES], "lighting": LIGHTING, "cameras": CAMERAS, "expressions": EXPRESSIONS}
