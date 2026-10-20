"""Transcript quality helpers.

* prompt()       — a Devanagari "style hint" plus the channel's own words (names,
                   places, catch-phrases) for Whisper's initial prompt. Whisper
                   copies spelling and script from the prompt, so this alone fixes
                   a lot of wrongly spelled names and Hinglish words.
* learn()        — when the creator corrects caption words in the editor, remember
                   each wrong→right pair for that channel.
* apply_fixes()  — apply those remembered corrections to every new transcript.
* llm_polish()   — optional: if an LLM key is set, fix obvious spelling mistakes
                   segment by segment, keeping the word count (so timings stay).
"""

from __future__ import annotations

import re

from . import llm

STYLE_HINT = {
    # the "अं… उम्म" in the hint makes Whisper write filler sounds instead of silently
    # dropping them, so autocut can find and cut them
    "hi": "नमस्ते दोस्तों। अं… तो आज मैं, उम्म, आपको एक सच्ची कहानी सुनाने वाला हूँ, जो आपकी ज़िंदगी बदल सकती है।",
    "en": "Hello friends. Um, so today I'm, uh, going to tell you a true story.",
}
MAX_FIXES = 600
MAX_PROMPT_VOCAB_CHARS = 120
_PUNCT = "।॥,.!?;:\"'“”‘’()[]…-"


def norm(w: str) -> str:
    return w.strip().strip(_PUNCT).lower()


def prompt(language: str, settings: dict | None) -> str:
    s = settings or {}
    raw = s.get("vocab_words") or (s.get("brand") or {}).get("vocab_words") or ""
    words = [w.strip() for w in re.split(r"[,\n]", str(raw)) if w.strip()]
    fixes = list(reversed(list((s.get("vocab_fixes") or {}).values())))  # newest corrections first
    extra = []
    for w in words + fixes:
        if w not in extra:
            extra.append(w)
    base = STYLE_HINT.get(language, STYLE_HINT["hi"])
    # Keep it SHORT. Whisper keeps only the last ~223 prompt tokens (Devanagari ≈ 1 token per
    # 1–2 characters), so a long word list pushed out the style hint, and a prompt that is a
    # comma list makes Whisper answer with lists or skip quiet speech. The channel's own words
    # first, then the newest learned corrections.
    tail = ""
    for w in extra:
        if len(tail) + len(w) + 2 > MAX_PROMPT_VOCAB_CHARS:
            break
        tail = f"{tail}, {w}" if tail else w
    return base + (" " + tail + "।" if tail else "")


def learn(old: dict | None, new: dict | None) -> dict[str, str]:
    """wrong→right word pairs from an edited transcript (only where word counts line up)."""
    out: dict[str, str] = {}
    if not old or not new:
        return out
    os_, ns = old.get("segments") or [], new.get("segments") or []
    if len(os_) != len(ns):
        return out
    for a, b in zip(os_, ns):
        aw, bw = a.get("words") or [], b.get("words") or []
        if len(aw) != len(bw):
            continue
        for x, y in zip(aw, bw):
            nx, ny = norm(x.get("w", "")), norm(y.get("w", ""))
            if nx and ny and nx != ny and " " not in ny and len(nx) <= 40:
                out[nx] = y.get("w", "").strip().strip(_PUNCT)
    return out


def merge_fixes(current: dict | None, new: dict[str, str]) -> dict[str, str]:
    cur = dict(current or {})
    for k, v in new.items():
        cur.pop(k, None)
        cur[k] = v  # newest last
    if len(cur) > MAX_FIXES:
        cur = dict(list(cur.items())[-MAX_FIXES:])
    return cur


def _replace_word(w: str, fixes: dict[str, str]) -> str:
    n = norm(w)
    if not n or n not in fixes or not str(fixes[n] or "").strip().strip(_PUNCT):
        return w  # never turn a word into nothing
    lead = w[: len(w) - len(w.lstrip(_PUNCT))]
    trail = w[len(w.rstrip(_PUNCT)):]
    return f"{lead}{fixes[n]}{trail}"


def apply_fixes(tr: dict, fixes: dict | None) -> tuple[dict, int]:
    if not fixes or not tr:
        return tr, 0
    n = 0
    for seg in tr.get("segments") or []:
        for w in seg.get("words") or []:
            new = _replace_word(w.get("w", ""), fixes)
            if new != w.get("w"):
                w["w"] = new
                n += 1
        if seg.get("words"):
            seg["text"] = " ".join(w["w"] for w in seg["words"])
    if n:
        tr["text"] = " ".join(s.get("text", "") for s in tr.get("segments") or [])
    return tr, n


def polish_line(words: list[dict], line: str) -> list[str] | None:
    """The LLM's corrected words for one segment, or None when it is not a safe 1:1 spelling fix.

    Rejected: a different word count (words merged / deleted / added), an empty or
    punctuation-only word where a real word was, or so many changed words that the
    line was probably rewritten or shifted by one word."""
    if not words:
        return None
    line = re.sub(r"^\s*\d+[.)]\s+", "", line)
    new = line.split()
    if len(new) != len(words):
        return None
    out, changed, shifted = [], 0, 0
    for i, (w, nw) in enumerate(zip(words, new)):
        old = w.get("w", "")
        if not norm(nw) and norm(old):
            return None
        if nw == old:
            out.append(nw)
            continue
        changed += 1
        # keep the original punctuation around the word (the LLM is told not to touch it)
        lead = old[: len(old) - len(old.lstrip(_PUNCT))]
        trail = old[len(old.rstrip(_PUNCT)):]
        core = nw.strip(_PUNCT)
        if i and norm(nw) == norm(words[i - 1].get("w", "")) and norm(nw) != norm(old):
            shifted += 1
        out.append(f"{lead}{core}{trail}" if core else nw)
    if shifted or (len(words) >= 3 and changed > max(2, len(words) // 2)):
        return None
    return out


def llm_polish(tr: dict, language: str = "hi", context: str = "", batch: int = 40) -> tuple[dict, int]:
    """Fix spelling with an LLM, segment by segment, never changing the number of words."""
    if not llm.available() or not tr:
        return tr, 0
    segs = tr.get("segments") or []
    changed = 0
    for i in range(0, len(segs), batch):
        part = segs[i:i + batch]
        lines = [" ".join(w["w"] for w in s.get("words") or []) or s.get("text", "") for s in part]
        ask = (
            "These are speech-recognition lines from a " + ("Hindi" if language == "hi" else language)
            + " YouTube video" + (f" about: {context}" if context else "") + ".\n"
            "Fix only clear spelling/recognition mistakes (wrong word that sounds similar, broken Devanagari, "
            "misspelled names). Keep Hindi in Devanagari, keep English words the speaker used. "
            "IMPORTANT: every output line must have EXACTLY the same number of space-separated words as its input line. "
            "Do not add or remove words, do not translate, do not add punctuation.\n"
            'Return JSON: {"lines": ["...", ...]} with the same number of lines.\n\n'
            + "\n".join(f"{n + 1}. {ln}" for n, ln in enumerate(lines))
        )
        res = llm.ask_json(ask, max_tokens=4096)
        fixed = (res or {}).get("lines") if isinstance(res, dict) else None
        if not isinstance(fixed, list) or len(fixed) != len(part):
            continue
        for s, new in zip(part, fixed):
            ws = s.get("words") or []
            new = polish_line(ws, str(new))
            if new is None:
                continue  # the LLM merged / dropped / shifted words — keep Whisper's words
            for w, nw in zip(ws, new):
                if nw != w["w"]:
                    w["w"] = nw
                    changed += 1
            s["text"] = " ".join(w["w"] for w in ws)
    if changed:
        tr["text"] = " ".join(s.get("text", "") for s in segs)
        tr["polished"] = llm.available()
    return tr, changed
