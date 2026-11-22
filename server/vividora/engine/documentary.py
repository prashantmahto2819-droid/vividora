"""Auto Documentary — topic (or your own script) → scenes → narration → picture per scene → one finished video.

plan()      topic → [{narration, visual, on_screen}] via the LLM (engine.llm: Gemini / Claude), or scenes_from_script()
            for a script you wrote. No LLM key → plan() returns None and the caller asks for a script.
pick_visual()  library image/B-roll by keyword match, else stock (Pixabay, if PIXABAY_API_KEY), else a title card.
render_scene() Ken-Burns pan/zoom on a picture, or a trimmed/looped clip, with short fades.
assemble()  scenes + narration wavs (+ SFX on scene changes, + music ducked under the voice) → one MP4.

Everything here is plain functions on paths (ffmpeg + Pillow + numpy), so it is testable without a server.
Captions (optional, on by default) are burned in with libass from the narration text, timed by sentence length inside each scene.
Phase 1 limits (on purpose): no per-scene editing UI — the result is a finished MP4 in the Library.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import llm, tts
from . import ffmpeg as _ffm
from .ffmpeg import still as _still

FPS = 30
PAD = 0.45          # seconds of air after each narrated scene
MIN_SCENE = 2.8
SIZES = {"landscape": (1280, 720), "portrait": (720, 1280), "square": (1080, 1080)}

_PROMPT = """You are a documentary writer. Topic: {topic}
{facts}
Write a {minutes}-minute explainer documentary in {lang}, as {n} scenes (about {per} seconds of narration each).
Rules: facts only — {factrule}if unsure of a number or date, leave it out; calm, curious, cinematic voice; short sentences that are easy to speak;
the first scene is a hook, the last scene a closing thought. No scene numbers inside the narration.
Return ONLY JSON: {{"title": str, "scenes": [{{"narration": str (spoken text in {lang}), "visual": str (3-6 ENGLISH stock-footage search words: concrete things you can film, e.g. "aerial view himalaya mountains clouds"), "on_screen": str (<= 6 words or "")}}]}}"""

_LANG = {"hi": "Hindi (Devanagari)", "en": "English", "hinglish": "Hinglish (Hindi in Roman letters)"}


def research(topic: str, language: str = "en", http_json=None, limit: int = 3) -> list[dict]:
    """Grounding facts: intro extracts of the best Wikipedia articles for the topic (free, no key).
    Returns [{title, url, text}] — empty on any failure (the plan then simply has no grounding).
    Wikipedia text is CC BY-SA 4.0: the build adds these pages to the description as sources."""
    import json as _json
    import urllib.parse
    import urllib.request

    def _get(url: str) -> dict:
        req = urllib.request.Request(url, headers={"User-Agent": "Vividora/1.0 (self-hosted video studio; documentary research)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return _json.loads(r.read().decode())
    get = http_json or _get
    out: list[dict] = []
    for lang in dict.fromkeys([language if language in ("hi", "en") else "en", "en"]):  # topic language first, then English
        try:
            q = urllib.parse.quote(topic[:200])
            data = get(f"https://{lang}.wikipedia.org/w/api.php?action=query&format=json&generator=search&gsrsearch={q}&gsrlimit={limit}"
                       f"&prop=extracts|info&exintro=1&explaintext=1&exlimit={limit}&inprop=url&redirects=1")
            pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
            for pg in pages:
                text = re.sub(r"\s+", " ", pg.get("extract") or "").strip()
                if len(text) > 80:
                    out.append({"title": pg.get("title", ""), "url": pg.get("fullurl", ""), "text": text[:1800], "lang": lang})
        except Exception:  # noqa: BLE001 — research is a bonus
            continue
        if len(out) >= 2:
            break
    return out[:limit]


def plan(topic: str, *, minutes: float = 3.0, language: str = "hi", ground: bool = True, http_json=None) -> dict | None:
    """Scenes from the LLM; None when no LLM key is configured or the answer was unusable.
    With ground=True the prompt carries Wikipedia extracts and the model is told to take numbers/dates/names only from them;
    the pages used come back as result["sources"] ([{title, url}])."""
    topic = (topic or "").strip()
    if not topic or not llm.available():
        return None
    minutes = max(1.0, min(10.0, float(minutes)))
    n = max(4, min(24, round(minutes * 60 / 12)))
    src = research(topic, language, http_json) if ground else []
    facts = ("\nREFERENCE FACTS (use these):\n" + "\n".join(f"[{i + 1}] {s['title']}: {s['text']}" for i, s in enumerate(src)) + "\n") if src else ""
    rule = "numbers, dates and names must come ONLY from the reference facts above; " if src else ""
    out = llm.ask_json(_PROMPT.format(topic=topic[:400], minutes=int(minutes) if minutes == int(minutes) else minutes,
                                      lang=_LANG.get(language, language), n=n, per=12, facts=facts, factrule=rule),
                       max_tokens=4096, timeout=120)
    res = normalize(out)
    if res:
        res["sources"] = [{"title": s["title"], "url": s["url"]} for s in src]
    return res


def _num(v, lo: float, hi: float) -> float:
    try:
        return round(max(lo, min(hi, float(v))), 2)
    except (TypeError, ValueError):
        return 0.0


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
                       "on_screen": str(s.get("on_screen") or "")[:60].strip(), **({"library_id": str(s["library_id"])} if s.get("library_id") else {}),
                       **({"motion": True} if s.get("motion") is True else {}),
                       **({"hold": hold} if (hold := _num(s.get("hold"), 0, 30)) else {})})
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
    """Pixabay for a query (safe-search on): videos first, photos when there are no videos.
    Returns [{url, kind: broll|image, license, creator, page, id}]."""
    import urllib.parse
    q = urllib.parse.quote(query)
    out = []
    data = http_json(f"https://pixabay.com/api/videos/?key={key}&q={q}&per_page=5&safesearch=true")
    for r in data.get("hits", []):
        v = (r.get("videos") or {}).get("medium") or (r.get("videos") or {}).get("small") or {}
        if v.get("url"):
            out.append({"url": v["url"], "kind": "broll", "license": "Pixabay Content License", "creator": r.get("user"),
                        "page": r.get("pageURL"), "id": str(r.get("id"))})
    if out:
        return out
    data = http_json(f"https://pixabay.com/api/?key={key}&q={q}&per_page=5&safesearch=true&image_type=photo&orientation=horizontal")
    for r in data.get("hits", []):
        u = r.get("largeImageURL") or r.get("webformatURL")
        if u:
            out.append({"url": u, "kind": "image", "license": "Pixabay Content License", "creator": r.get("user"),
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
              f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={FPS},{fade},{_ffm.UNIFORM_VF}")
        _ff(["-loop", "1", "-i", str(_still(src)), "-vf", vf, "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             *_ffm.UNIFORM_ENC, str(out)])
    else:
        # scenes are joined with the concat demuxer → every scene must have identical properties (ffmpeg.UNIFORM_VF)
        def _vf(tonemap: str) -> str:
            return (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS},"
                    f"{tonemap + ',' if tonemap else ''}{fade},{_ffm.UNIFORM_VF}")
        tm = _ffm.hdr_to_sdr(src)
        cmd = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", *_ffm.UNIFORM_ENC, str(out)]
        try:
            _ff(["-stream_loop", "-1", "-i", str(src), "-t", f"{dur:.3f}", "-vf", _vf(tm), *cmd])
        except Exception:  # noqa: BLE001 — an HDR file the converter cannot read: keep the scene without the conversion
            if not tm:
                raise
            _ff(["-stream_loop", "-1", "-i", str(src), "-t", f"{dur:.3f}", "-vf", _vf(""), *cmd])
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
             music: Path | None = None, work: Path | None = None, captions: Path | None = None, music_volume: float = 0.14) -> Path:
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
        chain.append(f"[{n}:a]volume={max(0.02, min(0.6, float(music_volume))):.3f}[m];[m][sc]sidechaincompress=threshold=0.04:ratio=8:attack=20:release=400[md]")
        mix.append("[md]")
        n += 1
    total = sum(durations)
    chain.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,atrim=0:{total:.3f}[aout]")
    if captions:
        fonts = str(Path(__file__).resolve().parents[2] / "fonts")
        esc = lambda x: str(x).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")  # noqa: E731
        chain.append(f"[0:v]subtitles='{esc(captions)}':fontsdir='{esc(fonts)}'[vout]")
        vmap, vcodec = "[vout]", ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
    else:
        vmap, vcodec = "0:v", ["-c:v", "copy"]
    _ff([*ins, "-filter_complex", ";".join(chain), "-map", vmap, "-map", "[aout]", *vcodec, "-c:a", "aac", "-b:a", "160k",
         "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)])
    return out


def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def build_captions(scenes: list[str], narr: list[float], durations: list[float], size: tuple[int, int], out: Path) -> Path:
    """ASS file: each scene's narration cut at sentence/phrase ends (≤ ~46 chars a line), shown for a time proportional to its
    length inside the spoken part of the scene (the real narration seconds, so lines follow the voice)."""
    w, h = size
    fs = max(26, int(min(w, h) * (0.055 if w >= h else 0.05)))
    font = Path(__file__).resolve().parents[2] / "fonts"
    fname = "Hind" if (font / "Hind-Bold.ttf").exists() else "Noto Sans Devanagari"
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 0", "",
             "[V4+ Styles]",
             "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
             f"Style: Cap,{fname},{fs},&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,3,6,0,2,{int(w * 0.07)},{int(w * 0.07)},{int(h * (0.1 if w >= h else 0.18))},1",
             "", "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"]
    t0 = 0.0
    for text, spoken, total in zip(scenes, narr, durations):
        parts = [p for p in tts.split_sentences(text, max_chars=46) if p.strip()] or [text]
        weight = sum(len(p) for p in parts) or 1
        t = t0 + 0.1
        span = max(0.5, min(spoken, total - 0.2))
        for p in parts:
            d = span * len(p) / weight
            safe = p.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")
            lines.append(f"Dialogue: 0,{_ass_time(t)},{_ass_time(t + d)},Cap,,0,0,0,,{safe}")
            t += d
        t0 += total
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def _clock(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def chapters(scenes: list[dict], durations: list[float], min_len: float = 10.0) -> list[tuple[float, str]]:
    """YouTube chapters: starts at 0:00, every chapter ≥ min_len s (scenes are merged), at least 3 or none."""
    out: list[tuple[float, str]] = []
    t, acc = 0.0, min_len
    for sc, d in zip(scenes, durations):
        if acc >= min_len:
            title = (sc.get("on_screen") or " ".join(sc["narration"].split()[:6])).strip(" ।.,")
            out.append((t, title[:60] or "Part"))
            acc = 0.0
        acc += d
        t += d
    return out if len(out) >= 3 else []


def description(title: str, chaps: list[tuple[float, str]], credits: list[str], sources: list[dict] | None = None,
                series: dict | None = None) -> str:
    lines = [title, ""]
    if series and series.get("titles"):
        lines += [f"Series: {series.get('name', '')} — part {series.get('i', 1)} of {len(series['titles'])}"] + \
                 [f"{k + 1}. {t}" for k, t in enumerate(series["titles"])] + [""]
    if chaps:
        lines += [f"{_clock(t)} {name}" for t, name in chaps] + [""]
    if sources:
        lines += ["Sources (Wikipedia, CC BY-SA 4.0):"] + [f"{x.get('title', '')} — {x.get('url', '')}" for x in sources[:6]] + [""]
    if credits:
        lines += ["Footage credits:"] + credits + [""]
    lines.append("Narration: AI voice. Facts compiled by the creator — please verify before relying on them.")
    return "\n".join(lines)


def est_seconds(narration: str) -> float:
    """Rough spoken length before TTS exists (≈2.3 words/s) — only used to plan Shorts."""
    return max(MIN_SCENE, len(narration.split()) / 2.3 + PAD)


def _scene_score(sc: dict, i: int) -> float:
    from .shorts import HOOK_WORDS
    words = re.findall(r"[\w']+", sc["narration"].lower())
    sc_ = sum(1 for w in words if w in HOOK_WORDS) / max(1, len(words)) * 10
    sc_ += 1.5 if "?" in sc["narration"] or "?" in (sc.get("on_screen") or "") else 0
    sc_ += 1.0 if re.search(r"\d", sc["narration"]) else 0
    sc_ += 0.8 if sc.get("on_screen") else 0
    sc_ += 1.0 if i == 0 else 0
    return sc_


def shorts_plan(scenes: list[dict], *, count: int = 3, min_s: float = 20.0, max_s: float = 58.0) -> list[dict]:
    """Best self-contained runs of consecutive scenes (20–58 s) → [{title, indices, seconds, score}], best first, non-overlapping.
    A run starts at a strong scene (a hook comes first), then grows until it is long enough to be a Short."""
    n = len(scenes)
    est = [est_seconds(sc["narration"]) for sc in scenes]
    sco = [_scene_score(sc, i) for i, sc in enumerate(scenes)]
    cands = []
    for i in range(n):
        tot, j = 0.0, i
        while j < n and tot + est[j] <= max_s:
            tot += est[j]
            j += 1
            if tot >= min_s:
                break
        if tot < min_s:
            continue
        idx = list(range(i, j))
        cands.append({"indices": idx, "seconds": round(tot, 1), "score": round(sco[i] * 1.6 + sum(sco[k] for k in idx) / len(idx), 2)})
    cands.sort(key=lambda c: -c["score"])
    out, used = [], set()
    for c in cands:
        if used & set(c["indices"]):
            continue
        used |= set(c["indices"])
        first = scenes[c["indices"][0]]
        title = (first.get("on_screen") or first["narration"]).strip()
        title = (title[:57] + "…") if len(title) > 58 else title
        out.append({**c, "title": title})
        if len(out) >= max(1, min(8, count)):
            break
    return out


_SERIES = """You plan a documentary series. Topic: {topic}. Write {n} episodes in {lang}, each a different angle, in watching order,
no overlap. Reply ONLY with JSON: {{"series": "<series title>", "episodes": [{{"title": "<short episode title>", "summary": "<one sentence>"}}]}}"""


def series_plan(topic: str, episodes: int = 4, language: str = "hi") -> dict | None:
    topic = (topic or "").strip()
    if not topic or not llm.available():
        return None
    n = max(2, min(10, int(episodes)))
    out = llm.ask_json(_SERIES.format(topic=topic[:300], n=n, lang=_LANG.get(language, language)), max_tokens=2048, timeout=90)
    if not isinstance(out, dict) or not isinstance(out.get("episodes"), list):
        return None
    eps = [{"title": str(e.get("title") or "").strip()[:100], "summary": str(e.get("summary") or "").strip()[:300]}
           for e in out["episodes"][:n] if isinstance(e, dict) and str(e.get("title") or "").strip()]
    return {"series": str(out.get("series") or topic)[:100], "episodes": eps} if len(eps) >= 2 else None


def make_thumbnail(video: Path, title: str, out: Path, at: float = 2.0) -> Path:
    """A frame from the film with a dark band and the title — ready as a YouTube thumbnail (1280×720 for landscape)."""
    from PIL import Image, ImageDraw, ImageFont
    frame = out.with_suffix(".frame.png")
    _ff(["-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1", str(frame)])
    img = Image.open(frame).convert("RGB")
    w, h = img.size
    band = Image.new("RGBA", (w, int(h * 0.34)), (0, 0, 0, 170))
    img.paste(band, (0, h - band.size[1]), band)
    d = ImageDraw.Draw(img)
    fp = _font("hi")
    size_px = max(30, int(min(w, h) * 0.09))
    font = ImageFont.truetype(fp, size_px) if fp else ImageFont.load_default()
    words, lines, cur = title.split(), [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if d.textlength(t, font=font) > w * 0.88 and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = t
    if cur:
        lines.append(cur)
    lines = lines[:2]
    y = h - band.size[1] + (band.size[1] - int(size_px * 1.25) * len(lines)) // 2
    for ln in lines:
        d.text(((w - d.textlength(ln, font=font)) / 2, y), ln, font=font, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
        y += int(size_px * 1.25)
    img.save(out)
    frame.unlink(missing_ok=True)
    return out


def scene_durations(narr_seconds: list[float], holds: list[float] | None = None) -> list[float]:
    """Scene length = narration + pad, never below MIN_SCENE, and never below the creator's own `hold` (seconds)."""
    holds = holds or [0.0] * len(narr_seconds)
    return [round(max(MIN_SCENE, s + PAD, h or 0.0), 3) for s, h in zip(narr_seconds, holds)]


# ---------------------------------------------------------------- automatic background music (from the user's own library)
_SAFE_SOURCES = {"starter", "upload"}          # bundled pack / the user's own files
_RISKY = ("youtube", "yt", "trending", "chart")  # yt-dlp pulls can trigger Content ID on a monetised channel


def music_is_nc(m: dict) -> bool:
    """A library track under a non-commercial licence (e.g. Jamendo CC BY-NC) — not for monetised uploads."""
    blob = f"{m.get('license') or ''} {m.get('tags') or ''} {m.get('source') or ''}".lower()
    return "non-commercial" in blob or "-nc" in blob or "jamendo-nc" in blob


def detect_mood(title: str, scenes: list[dict]) -> str:
    """Cheap keyword vote over the title + narration → one of musictag.MOODS (defaults to 'story')."""
    from . import musictag
    text = (title + " " + " ".join(sc.get("narration", "") for sc in scenes)).lower()
    best, score = "story", 0
    for m in musictag.MOODS:
        n = sum(text.count(w) for w in musictag._WORDS.get(m, ()))
        if n > score:
            best, score = m, n
    return best


def pick_music(library: list[dict], mood: str, seed: str = "") -> dict | None:
    """Best track for a mood: safe licences first (bundled/own upload, CC0), then mood match from the analysis (meta.moods) or tags."""
    import random
    musics = [m for m in library if m.get("kind") == "music"]
    if not musics:
        return None

    def safe(m: dict) -> bool:
        lic = str(m.get("license") or "").lower()
        src = str(m.get("source") or "").lower()
        return (src in _SAFE_SOURCES or lic in ("own", "cc0") or "cc0" in lic or "public domain" in lic) and not any(x in src for x in _RISKY)

    def fits(m: dict) -> bool:
        moods = [str(x).lower() for x in ((m.get("meta") or {}).get("moods") or [])]
        return mood in moods or mood in str(m.get("tags") or "").lower() or mood in str(m.get("name") or "").lower()
    for pool in ([m for m in musics if safe(m) and fits(m)], [m for m in musics if safe(m)]):
        if pool:
            return random.Random(seed or mood).choice(pool)
    return None   # only risky sources left → no music is safer than a Content ID claim
