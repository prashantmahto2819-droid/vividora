"""Standalone AI script generator — topic → ready-to-speak script.

Works with any LLM backend (Gemini or Claude via engine.llm), completely
independent of the ideas/planner workflow.  The generated script is TTS-ready:
supports `Name: …` dialogue, `*emphasis*`, `[pause 0.5]` markers.
"""

from __future__ import annotations

from . import llm
from .metadata import voice_text
from .planner import FORMATS, parse_sections, structured

# ---- script styles: each has its own section structure + prompt guidance ----

STYLES = {
    "motivational": {
        "label": "Motivational",
        "sections": "[HOOK] [SETUP] [STORY] [TURN] [LESSON] [CTA]",
        "guide": (
            "Write a motivational story-driven script. Start with a shocking hook that grabs in 2 seconds. "
            "Tell a real or realistic story with a dramatic turn, then deliver one clear lesson. "
            "End with a strong call-to-action. Use emotional pauses, rhetorical questions, and vivid imagery."
        ),
    },
    "educational": {
        "label": "Educational",
        "sections": "[HOOK] [PROBLEM] [EXPLANATION] [EXAMPLES] [SUMMARY] [CTA]",
        "guide": (
            "Write an educational script that teaches a concept or skill. Start with why this matters "
            "(a surprising fact or common mistake). Break the concept into simple steps with real examples. "
            "Use analogies to make complex ideas simple. End with a quick summary and next steps."
        ),
    },
    "tutorial": {
        "label": "Tutorial / How-to",
        "sections": "[HOOK] [OVERVIEW] [STEP1] [STEP2] [STEP3] [TIPS] [CTA]",
        "guide": (
            "Write a step-by-step tutorial. Start with what the viewer will achieve. "
            "Number each step clearly. Give specific details — tools, settings, quantities. "
            "Add pro tips and common mistakes to avoid. Keep it practical and actionable."
        ),
    },
    "story": {
        "label": "Story / Narrative",
        "sections": "[HOOK] [SETUP] [RISING] [CLIMAX] [RESOLUTION] [TAKEAWAY]",
        "guide": (
            "Write a compelling narrative. Open with a moment of tension or mystery. "
            "Build characters the viewer cares about. Create rising tension with obstacles. "
            "Deliver a satisfying climax and resolution. End with a universal takeaway."
        ),
    },
    "explainer": {
        "label": "Explainer",
        "sections": "[HOOK] [WHAT] [WHY] [HOW] [EXAMPLE] [CTA]",
        "guide": (
            "Explain a concept, event or phenomenon simply. Start with why the viewer should care. "
            "Break it into What → Why → How. Use one vivid analogy. Give a concrete real-world example. "
            "Assume the viewer knows nothing — no jargon."
        ),
    },
    "listicle": {
        "label": "Listicle",
        "sections": "[HOOK] [ITEM1] [ITEM2] [ITEM3] [ITEM4] [ITEM5] [CTA]",
        "guide": (
            "Write a list-format script ('5 ways to…', '7 things…'). Hook with the count and promise. "
            "Each item: one headline sentence + 2–3 support sentences. Save the best/most surprising for last. "
            "Keep items roughly equal length. Transition smoothly between items."
        ),
    },
    "product_review": {
        "label": "Product Review",
        "sections": "[HOOK] [OVERVIEW] [PROS] [CONS] [VERDICT] [CTA]",
        "guide": (
            "Write an honest, detailed product review. Start with your verdict teaser. "
            "Cover what it is, who it's for. List specific pros with real-use examples. "
            "Be honest about cons. Give a clear final verdict with who should/shouldn't buy."
        ),
    },
    "podcast_intro": {
        "label": "Podcast / Show Intro",
        "sections": "[COLD_OPEN] [INTRO] [TOPIC_SETUP] [MAIN] [CLOSING]",
        "guide": (
            "Write a podcast-style script. Start with a provocative cold open — a question or bold claim. "
            "Introduce yourself and the show briefly. Set up today's topic with stakes. "
            "Deliver the main content conversationally as if talking to a friend. Close warmly."
        ),
    },
    "news": {
        "label": "News Commentary",
        "sections": "[HOOK] [CONTEXT] [ANALYSIS] [IMPACT] [OPINION] [CTA]",
        "guide": (
            "Write a news commentary script. Open with the headline in a punchy way. "
            "Give brief factual context. Analyze what it means — go deeper than headlines. "
            "Explain the real-world impact on the viewer. Share a measured opinion. "
            "Cite specific facts and numbers."
        ),
    },
    "comparison": {
        "label": "Comparison (X vs Y)",
        "sections": "[HOOK] [OVERVIEW] [ROUND1] [ROUND2] [ROUND3] [VERDICT] [CTA]",
        "guide": (
            "Write a fair comparison of two options. Hook with the dilemma the viewer faces. "
            "Compare across specific criteria (rounds): price, features, quality, etc. "
            "Be specific with numbers and examples. Give a clear verdict — who should pick which."
        ),
    },
}

TONES = {
    "conversational": "spoken naturally as if talking to a friend across a table",
    "inspirational": "passionate, emotionally charged, with dramatic pauses and rising intensity",
    "professional": "clear, authoritative, confident — like a TED talk",
    "casual": "relaxed, informal, with slang and humour — like a vlog",
    "dramatic": "cinematic, intense, with vivid imagery and short punchy sentences",
    "humorous": "witty, with jokes and unexpected twists — entertaining first, informative second",
}


def generate(
    topic: str,
    *,
    style: str = "motivational",
    fmt: str = "short",
    language: str = "hi",
    target_seconds: int | None = None,
    audience: str = "",
    tone: str = "conversational",
) -> dict:
    """Generate a complete script from a topic description.

    Returns {script, shotlist, overlays, title_options, sections, source, words, seconds}.
    """
    sty = STYLES.get(style, STYLES["motivational"])
    tone_desc = TONES.get(tone, TONES["conversational"])
    secs = target_seconds or (45 if fmt == "short" else 480 if fmt == "long" else 30)
    words = int(secs * 2.3)
    lang_desc = "spoken Hindi/Hinglish as an Indian creator talks" if language != "en" else "English"

    # fallback template when no LLM is available
    fallback = _template_script(topic, sty, secs)
    if not llm.available():
        return fallback

    voice = voice_text()
    prompt = (
        (f"Creator voice & style:\n{voice}\n\n" if voice else "")
        + f"Topic/Title: {topic}\n"
        + f"Script style: {sty['label']} — {sty['guide']}\n"
        + f"Section structure: {sty['sections']}\n"
        + f"Format: {FORMATS.get(fmt, fmt)}, about {secs} seconds (~{words} words).\n"
        + f"Tone: {tone_desc}\n"
        + f"Language: {lang_desc}.\n"
        + (f"Target audience: {audience}\n" if audience else "")
        + "\nWrite the complete on-camera script. Rules:\n"
        "- Mark sections in square brackets with a blank line between each\n"
        "- Spoken, not written — short sentences, no headings inside the speech\n"
        "- Use *word* for emphasis, [pause 0.5] for dramatic pauses\n"
        "- For dialogue/multiple speakers: use 'Name: ...' format on separate lines\n"
        "- HOOK must be ≤12 words, create instant curiosity or shock\n"
        "- NO generic openings like 'aaj hum baat karenge'\n"
        "- Each section should have 1-2 blank lines for breathing room\n"
        "\nAlso provide:\n"
        "- 4-6 shot/B-roll suggestions (shotlist)\n"
        "- 3-4 on-screen text overlay suggestions\n"
        "- 3 title options for the video\n"
        '\nReply JSON: {"script":"...","shotlist":["..."],"overlays":["..."],"title_options":["..."]}'
    )

    system = f"You are a professional screenwriter specializing in {sty['label'].lower()} video scripts. JSON only."
    data = llm.ask_json(prompt, system=system, max_tokens=4000, timeout=120)

    if isinstance(data, dict) and data.get("script"):
        script_text = str(data["script"])
        return {
            "script": script_text,
            "shotlist": [str(x) for x in (data.get("shotlist") or [])][:8],
            "overlays": [str(x) for x in (data.get("overlays") or [])][:6],
            "title_options": [str(x) for x in (data.get("title_options") or [])][:5],
            "sections": parse_sections(script_text),
            "words": len(script_text.split()),
            "seconds": secs,
            "source": "llm",
        }
    return fallback


def improve(
    script: str,
    *,
    mode: str = "improve",
    language: str = "hi",
) -> dict:
    """Rewrite / improve / shorten / expand an existing script.

    Returns {script, sections, source}.
    """
    if not script or not script.strip():
        return {"script": "", "sections": [], "source": "empty"}

    if not llm.available():
        return {"script": script, "sections": parse_sections(script), "source": "no_llm"}

    voice = voice_text()
    lang_desc = "spoken Hindi/Hinglish as an Indian creator talks" if language != "en" else "English"

    mode_instructions = {
        "rewrite": (
            "Completely rewrite this script with a fresh angle. Keep the same topic and message, "
            "but use different words, structure and rhythm. Make every sentence earn its place."
        ),
        "improve": (
            "Make this script stronger: more vivid, more emotional, tighter pacing. "
            "Fix weak openings, add punchy transitions, sharpen the hook. Keep length within ±20%."
        ),
        "shorten": (
            "Cut this script to about half its length. Keep the hook and the strongest points. "
            "Remove filler, merge similar ideas, make every word count."
        ),
        "expand": (
            "Expand this script to roughly double its length. Add more examples, stories, "
            "analogies and details. Deepen the emotional impact. Add more pauses and transitions."
        ),
    }

    instruction = mode_instructions.get(mode, mode_instructions["improve"])

    prompt = (
        (f"Creator voice & style:\n{voice}\n\n" if voice else "")
        + f"Language: {lang_desc}.\n\n"
        + f"Current script:\n{script}\n\n"
        + f"Task: {instruction}\n\n"
        "Rules:\n"
        "- Keep section markers [HOOK] [SETUP] etc. — or add them if missing\n"
        "- Spoken, not written — short sentences\n"
        "- Use *word* for emphasis, [pause 0.5] for pauses\n"
        "- Keep the same language as the original\n"
        '\nReply JSON: {"script": "..."}'
    )

    data = llm.ask_json(
        prompt,
        system="You are a script editor for video creators. JSON only.",
        max_tokens=4000,
        timeout=120,
        cache=False,  # each improve call should be unique
    )

    if isinstance(data, dict) and str(data.get("script") or "").strip():
        script_text = str(data["script"])
        return {
            "script": script_text,
            "sections": parse_sections(script_text),
            "source": "llm",
        }

    return {
        "script": script,
        "sections": parse_sections(script),
        "source": "error",
        "error": llm.LAST_ERROR or "AI से जवाब नहीं आया",
    }


def _template_script(topic: str, sty: dict, secs: int) -> dict:
    """Fallback template when no LLM is available."""
    sections = sty["sections"].replace("[", "\n\n\n[").replace("]", "]\n\n").strip()
    lines = []
    for part in sections.split("\n\n\n"):
        part = part.strip()
        if part.startswith("[") and part.endswith("]"):
            key = part[1:-1]
            lines.append(f"[{key}]")
            lines.append("")
            lines.append(f"({topic} — {key.lower()} यहाँ लिखें)")
            lines.append("")
    script_text = "\n".join(lines)
    return {
        "script": script_text,
        "shotlist": ["talking head, eye-level", f"B-roll: {topic} से जुड़ा footage", "text overlay on key point"],
        "overlays": [topic],
        "title_options": [topic],
        "sections": parse_sections(script_text),
        "words": 0,
        "seconds": secs,
        "source": "template",
    }
