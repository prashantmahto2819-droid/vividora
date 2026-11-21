"""Auto Documentary — topic (or your own script) → scenes → narration → picture per scene → one finished video.

plan()      topic → [{narration, visual, on_screen}] via the LLM (engine.llm: Gemini / Claude), or scenes_from_script()
            for a script you wrote. No LLM key → plan() returns None and the caller asks for a script.
pick_visual()  library image/B-roll by keyword match, else stock (Pixabay, if PIXABAY_API_KEY), else a title card.
render_scene() Ken-Burns pan/zoom on a picture, or a trimmed/looped clip, with short fades.
assemble()  scenes + narration wavs (+ SFX on scene changes, + music ducked under the voice) → one MP4.

Everything here is plain functions on paths (ffmpeg + Pillow + numpy), so it is testable without a server.
Phase 1 limits (on purpose): no captions yet, no per-scene editing UI — the result is a finished MP4 in the Library.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import llm, tts

FPS = 30
PAD = 0.45          # seconds of air after each narrated scene
MIN_SCENE = 2.8
SIZES = {"landscape": (1280, 720), "portrait": (720, 1280), "square": (1080, 1080)}

_PROMPT = """You are a documentary writer. Topic: {topic}
Write a {minutes}-minute explainer documentary in {lang}, as {n} scenes (about {per} seconds of narration each).
Rules: facts only — if unsure of a number or date, leave it out; calm, curious, cinematic voice; short sentences that are easy to speak;
the first scene is a hook, the last scene a closing thought. No scene numbers inside the narration.
Return ONLY JSON: {{"title": str, "scenes": [{{"narration": str (spoken text in {lang}), "visual": str (3-6 ENGLISH stock-footage search words: concrete things you can film, e.g. "aerial view himalaya mountains clouds"), "on_screen": str (<= 6 words or "")}}]}}"""

_LANG = {"hi": "Hindi (Devanagari)", "en": "English", "hinglish": "Hinglish (Hindi in Roman letters)"}


def plan(topic: str, *, minutes: float = 3.0, language: str = "hi") -> dict | None:
    """Scenes from the LLM; None when no LLM key is configured or the answer was unusable."""
    topic = (topic or "").strip()
    if not topic or not llm.available():
        return None
    minutes = max(1.0, min(10.0, float(minutes)))
    n = max(4, min(24, round(minutes * 60 / 12)))
    out = llm.ask_json(_PROMPT.format(topic=topic[:400], minutes=int(minutes) if minutes == int(minutes) else minutes,
                                      lang=_LANG.get(language, language), n=n, per=12), max_tokens=4096, timeout=120)
    return normalize(out)


def normalize(out) -> dict | None:
    if not isinstance(out, dict) or not isinstance(out.get("scenes"), list):
        return None
    scenes = []
    for s in out["scenes"][:40]:
        if not isinstance(s, dict):
            continue
        text = re.sub(r"\s+", " ", str(s.get("narration") or "")).strip()[:900]
        if len(text) < 3:
            continue
        scenes.append({"narration": text, "visual": str(s.get("visual") or "")[:120].strip(),
                       "on_screen": str(s.get("on_screen") or "")[:60].strip(), **({"library_id": str(s["library_id"])} if s.get("library_id") else {})})
    if not scenes:
        return None
    return {"title": str(out.get("title") or "Documentary")[:120], "scenes": scenes}


def scenes_from_script(script: str, *, per_scene_chars: int = 260) -> dict | None:
    """Your own script → scenes: paragraphs are scenes; one long paragraph is cut at sentence ends."""
    script = (script or "").strip()
    if not script:
        return None
    paras = [p.strip() for p in re.split(r"\n\s*\n", script) if p.strip()]
    if len(paras) < 3:
        paras = []
        buf = ""
        for sent in tts.split_sentences(script, max_chars=per_scene_chars):
            if buf and len(buf) + len(sent) > per_scene_chars:
                paras.append(buf)
                buf = ""
            buf = (buf + " " + sent).strip()
        if buf:
            paras.append(buf)
    return normalize({"title": paras[0][:60], "scenes": [{"narration": p, "visual": ""} for p in paras]})


# ---------------------------------------------------------------- pictures
_STOP = {"the", "a", "an", "of", "in", "on", "and", "with", "view", "shot", "footage", "video"}


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", (s or "").lower()) if w not in _STOP}


def pick_visual(scene: dict, library: list[dict], used: set[str]) -> dict | None:
    """Best library image/B-roll for the scene: explicit library_id, else most keyword overlap with name+tags."""
    if scene.get("library_id"):
        for m in library:
            if m["id"] == scene["library_id"]:
                return m
    want = _tokens(scene.get("visual", ""))
    best, score = None, 0
    for m in library:
        if m.get("kind") not in ("image", "broll") or (m.get("meta") or {}).get("alpha"):
            continue
        have = _tokens(f'{m.get("name", "")} {m.get("tags", "")}')
        s = len(want & have) * 10 - (3 if m["id"] in used else 0)
        if s > score:
            best, score = m, s
    return best


def stock_candidates(query: str, key: str, http_json) -> list[dict]:
    """Pixabay videos for a query (safe-search on). Returns [{url, kind, license, creator, page, id}]."""
    import urllib.parse
    out = []
    data = http_json(f"https://pixabay.com/api/videos/?key={key}&q={urllib.parse.quote(query)}&per_page=5&safesearch=true")
    for r in data.get("hits", []):
        v = (r.get("videos") or {}).get("medium") or (r.get("videos") or {}).get("small") or {}
        if v.get("url"):
            out.append({"url": v["url"], "kind": "broll", "license": "Pixabay Content License", "creator": r.get("user"),
                        "page": r.get("pageURL"), "id": str(r.get("id"))})
    return out


def _font(lang: str) -> str | None:
    d = Path(__file__).resolve().parents[2] / "fonts"
    for n in ("Hind-Bold.ttf", "NotoSansDevanagari.ttf", "Poppins-Black.ttf", "Inter-Black.otf"):
        if (d / n).exists():
            return str(d / n)
    return None


def title_card(text: str, out: Path, size: tuple[int, int], seed: int = 0) -> Path:
    """Dark gradient + the line of text — used when no picture is found, so a scene is never blank."""
    from PIL import Image, ImageDraw, ImageFont
    w, h = size
    palettes = [((18, 24, 38), (60, 40, 90)), ((16, 32, 30), (40, 80, 70)), ((34, 22, 20), (110, 60, 40)), ((14, 20, 40), (30, 70, 120))]
    c1, c2 = palettes[seed % len(palettes)]
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        row = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = row
    d = ImageDraw.Draw(img)
    fp = _font("hi")
    size_px = max(28, w // 18)
    font = ImageFont.truetype(fp, size_px) if fp else ImageFont.load_default()
    words, lines, cur = (text or "").split(), [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if d.textlength(trial, font=font) > w * 0.8 and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = trial
    if cur:
        lines.append(cur)
    lines = lines[:5]
    lh = int(size_px * 1.4)
    y0 = (h - lh * len(lines)) // 2
    for i, ln in enumerate(lines):
        tw = d.textlength(ln, font=font)
        d.text(((w - tw) / 2, y0 + i * lh), ln, font=font, fill=(240, 240, 245))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


# ---------------------------------------------------------------- video
def _ff(args: list[str]) -> None:
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("ffmpeg: " + (r.stderr or "")[-400:])


def render_scene(src: Path, kind: str, dur: float, out: Path, size: tuple[int, int], idx: int = 0, caption: str = "") -> Path:
    """One silent clip of exactly `dur` seconds: image → slow zoom (in/out alternating), video → fill-crop loop."""
    w, h = size
    frames = max(2, int(dur * FPS))
    fade = f"fade=t=in:st=0:d=0.3,fade=t=out:st={max(0.0, dur - 0.3):.2f}:d=0.3"
    if kind == "image":
        zoom = "min(zoom+0.0007,1.2)" if idx % 2 == 0 else "if(eq(on,0),1.2,max(zoom-0.0007,1.0))"
        vf = (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
              f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={FPS},{fade},format=yuv420p")
        _ff(["-loop", "1", "-i", str(src), "-vf", vf, "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", str(out)])
    else:
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS},{fade},format=yuv420p"
        _ff(["-stream_loop", "-1", "-i", str(src), "-t", f"{dur:.3f}", "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", str(out)])
    return out


def narration_track(wavs: list[Path], durations: list[float], out: Path) -> Path:
    """Narration wavs joined, each padded with silence to its scene length (so audio and picture stay locked)."""
    chunks = []
    for wav, dur in zip(wavs, durations):
        pcm, sr = tts.read_pcm(wav)
        if sr != tts.SR:
            tmp = wav.with_suffix(".sr.wav")
            _ff(["-i", str(wav), "-ar", str(tts.SR), "-ac", "1", str(tmp)])
            pcm, sr = tts.read_pcm(tmp)
        need = int(dur * tts.SR) * 2
        pcm = pcm[:need] + b"\x00" * max(0, need - len(pcm))
        chunks.append(pcm)
    return tts.write_wav(out, b"".join(chunks), tts.SR)


def assemble(clips: list[Path], durations: list[float], narration: Path, out: Path, *, sfx: Path | None = None,
             music: Path | None = None, work: Path | None = None) -> Path:
    """clips (concat) + narration; whoosh at every scene change; music at ~12% ducked under the voice; loudness normalised."""
    work = work or out.parent
    lst = work / "clips.txt"
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips))
    ins = ["-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(narration)]
    chain = ["[1:a]asplit=2[vo][sc]" if music else "[1:a]anull[vo]"]
    mix = ["[vo]"]
    n = 2
    if sfx:
        starts, t = [], 0.0
        for d in durations[:-1]:
            t += d
            starts.append(t)
        for i, st in enumerate(starts):
            ins += ["-i", str(sfx)]
            chain.append(f"[{n}:a]adelay={int(max(0, st - 0.12) * 1000)}|{int(max(0, st - 0.12) * 1000)},volume=0.35[s{i}]")
            mix.append(f"[s{i}]")
            n += 1
    if music:
        ins += ["-stream_loop", "-1", "-i", str(music)]
        chain.append(f"[{n}:a]volume=0.14[m];[m][sc]sidechaincompress=threshold=0.04:ratio=8:attack=20:release=400[md]")
        mix.append("[md]")
        n += 1
    total = sum(durations)
    chain.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,atrim=0:{total:.3f}[aout]")
    _ff([*ins, "-filter_complex", ";".join(chain), "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
         "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)])
    return out


def scene_durations(narr_seconds: list[float]) -> list[float]:
    return [round(max(MIN_SCENE, s + PAD), 3) for s in narr_seconds]
