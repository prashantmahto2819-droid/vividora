"""AI Prompt Studio: ready-to-paste prompts for Grok Imagine / ChatGPT images / any video model.

From the transcript it proposes:
  * hook        — a 5–8 s cinematic opener matching the first line
  * broll       — one shot per key line (placed at that line's time)
  * background  — a backdrop for the person cut-out (Cutout tab)
  * thumbnail   — a background plate for the thumbnail studio (no text in it)
Every prompt states aspect ratio, camera, light and "no text, no logos, no watermark"
so the result drops straight into the edit. LLM writes richer prompts when a key is
set; otherwise topic rules build them.
"""

from __future__ import annotations

import re

from . import llm, shorts

STYLE = "cinematic, photorealistic, natural Indian setting, soft volumetric light, shallow depth of field, 4k detail"
NEG = "no text, no letters, no logos, no watermark, no subtitles, no distorted faces or hands"
OPEN = {"grok": "https://grok.com/imagine", "chatgpt": "https://chatgpt.com/", "gemini": "https://gemini.google.com/app"}

TOPICS = [  # Hindi/English keyword → visual idea
    (("सपना", "सपने", "dream"), "a young man looking at a glowing city skyline at night, dreaming of the future"),
    (("मेहनत", "परिश्रम", "hard work", "gym"), "close-up of sweat-soaked hands working late at a wooden desk under a single lamp"),
    (("पैसा", "पैसे", "money", "अमीर"), "slow push-in on stacked Indian rupee notes and coins on a table, warm light"),
    (("सुबह", "morning", "4 बजे", "चार बजे"), "sunrise over an Indian village rooftop, a young man stretching, golden mist"),
    (("गलती", "mistake", "हार", "fail"), "a chess king falling in slow motion on a dark board, dramatic rim light"),
    (("सफलता", "success", "जीत", "win"), "a runner breaking the finish tape in slow motion, crowd blurred, golden hour"),
    (("माँ", "माता", "mother", "पिता", "father", "परिवार"), "an Indian mother's hands serving food to her son, warm kitchen light, emotional"),
    (("समय", "time", "वक्त", "घड़ी"), "macro shot of an old pocket watch ticking, dust particles in a light beam"),
    (("किताब", "पढ़ाई", "study", "book"), "a student studying by candle light in a small room, pages turning"),
    (("डर", "fear", "अंधेरा"), "a lone figure standing at the edge of a dark forest, fog, moonlight"),
    (("रास्ता", "सफ़र", "journey", "road"), "a long empty road through mountains at dawn, drone shot moving forward"),
    (("भगवान", "प्रार्थना", "god", "pray"), "diyas glowing in a temple at dusk, slow dolly, peaceful mood"),
]


def _aspect(platform: str) -> str:
    return "9:16 vertical" if platform in ("short", "reel", "yt-short", "ig-reel", "fb-reel") else "16:9 horizontal"


def _visual_for(text: str) -> str:
    low = text.lower()
    for keys, vis in TOPICS:
        if any(k in low for k in keys):
            return vis
    return "a determined young Indian man walking towards a bright doorway, symbolic of a new beginning"


def _pack(kind: str, idea: str, *, aspect: str, seconds: int | None = None, at: float | None = None, line: str = "",
          hi: str = "") -> dict:
    motion = f"{seconds}-second video, slow cinematic camera move, smooth 24 fps" if seconds else "still image"
    prompt = f"{idea}. {STYLE}. {aspect}, {motion}. {NEG}."
    return {"kind": kind, "prompt": prompt, "aspect": aspect, "seconds": seconds, "at": at, "line": line,
            "hindi": hi or line, "open": OPEN,
            "chatgpt": f"Create an image: {idea}. {STYLE}. Aspect ratio {aspect.split()[0]}. {NEG}." if not seconds else None}


def _to_out(project: dict):
    from .autocut import keep_segments
    edl = project.get("edl") or {}
    dur = float((project.get("meta") or {}).get("duration") or 0)
    keep = keep_segments({"duration": dur, **edl}) if edl.get("cuts") is not None else [(0.0, dur)]

    def f(t: float) -> float | None:
        o = 0.0
        for a, b in keep or [(0.0, dur)]:
            if a <= t < b:
                return o + (t - a)
            o += b - a
        return None
    return f


def suggest(project: dict, platform: str = "short", broll_count: int = 4) -> list[dict]:
    tr = project.get("transcript") or {}
    sents = shorts._sentences(tr)
    aspect = _aspect(platform)
    to_out = _to_out(project)
    first = sents[0]["text"] if sents else project.get("title") or ""
    picks = [s for s in sorted(sents[1:], key=shorts._score, reverse=True)][: broll_count * 2]
    picks = sorted(picks[:broll_count], key=lambda s: s["start"])
    from . import aipack
    pack = aipack.get(project) if sents else None
    res = None
    if pack and isinstance(pack.get("prompts"), dict) and (pack["prompts"].get("hook") or {}).get("idea"):
        pr = pack["prompts"]
        res = {"hook": pr["hook"], "background": pr.get("background"), "thumbnail": pr.get("thumbnail"), "broll": pr.get("broll") or []}
    elif llm.available() and sents:
        body = "\n".join(f"[{i}] {s['text']}" for i, s in enumerate(sents[:60]))
        res = llm.ask_json(
            "You write prompts for AI video/image generators (Grok Imagine, Veo, ChatGPT images) for a Hindi motivational YouTube video.\n"
            f"Format: {aspect}. Transcript lines:\n{body}\n\n"
            "Return JSON {\"hook\": {\"idea\": \"...\", \"hindi\": \"...\"}, \"background\": {\"idea\": \"...\"}, \"thumbnail\": {\"idea\": \"...\"}, "
            f"\"broll\": [{{\"line\": <index>, \"idea\": \"...\", \"hindi\": \"...\"}}] (exactly {broll_count})}}. "
            "Each idea: one vivid English sentence (subject, action, setting, camera, light, mood), Indian context, no text in frame, "
            "no real celebrities. hindi = one-line meaning in Hindi.", max_tokens=1500)
    if sents and isinstance(res, dict) and res.get("hook"):
        if isinstance(res["hook"], dict):
            out = [_pack("hook", res["hook"].get("idea", ""), aspect=aspect, seconds=6, at=0.0, line=first, hi=res["hook"].get("hindi", ""))]
            for b in (res.get("broll") or [])[:broll_count]:
                try:
                    s = sents[int(b.get("line", 0))]
                except (ValueError, IndexError, TypeError):
                    continue
                out.append(_pack("broll", b.get("idea", ""), aspect=aspect, seconds=4, at=to_out(float(s["start"])), line=s["text"], hi=b.get("hindi", "")))
            out.append(_pack("background", (res.get("background") or {}).get("idea", "") or _visual_for(first), aspect=aspect, seconds=8))
            out.append(_pack("thumbnail", (res.get("thumbnail") or {}).get("idea", "") or _visual_for(first), aspect="16:9 horizontal"))
            for o in out:
                o["source"] = "ai"
            return out
    out = [_pack("hook", _visual_for(first), aspect=aspect, seconds=6, at=0.0, line=first)]
    used: dict[str, int] = {}
    angles = ["", ", extreme close-up detail shot", ", wide drone shot", ", silhouette against the light", ", slow-motion side angle"]
    for s in picks:
        v = _visual_for(s["text"])
        k = used.get(v, 0)
        used[v] = k + 1
        out.append(_pack("broll", v + angles[k % len(angles)], aspect=aspect, seconds=4, at=to_out(float(s["start"])), line=s["text"]))
    out.append(_pack("background", "an abstract slow-moving background of warm golden bokeh light and soft smoke, calm and premium", aspect=aspect, seconds=8))
    out.append(_pack("thumbnail", _visual_for(first) + ", dramatic contrast, space on one side for big text", aspect="16:9 horizontal"))
    for o in out:
        o["source"] = "rules"
    return out


def batch(items: list[dict]) -> dict:
    """All prompts in ONE message — paste once into ChatGPT / Grok and get every image/clip
    in the same chat, instead of a separate chat (and credit) per idea."""
    imgs = [x for x in items if not x.get("seconds") or x["kind"] in ("thumbnail",)]
    vids = [x for x in items if x.get("seconds")]
    head = ("Make the following images one by one in this same chat, in the given aspect ratio. "
            f"Same consistent cinematic style for all: {STYLE}. {NEG}.\n\n")
    lines = [f"{i + 1}. [{x['kind']}{' @' + str(round(x['at'], 1)) + 's' if x.get('at') is not None else ''}] "
             f"{x['prompt'].split('. ' + STYLE)[0]} — {x['aspect']}" for i, x in enumerate(items)]
    return {"chatgpt": head + "\n".join(lines),
            "grok": "\n\n".join(f"{i + 1}) {x['prompt']}" for i, x in enumerate(vids)),
            "count": len(items), "videos": len(vids), "images": len(imgs)}
