"""Supporting clips → the right moment of a talk (podcast, interview, lesson).

The creator uploads the main recording and, separately, the clips / photos that belong to it. `match()` reads the
transcript and decides where each one goes:

  1. a time written in the note or the file name ("1:23", "at 2m10s")           → exactly there         (how: "time")
  2. the LLM, when one is configured: transcript lines + what each clip is       → the line it belongs to (how: "ai")
  3. the words of the name / tags / note against the spoken words — Hindi in
     Devanagari and the same word typed in Latin letters are matched too          → best line            (how: "words")
  4. whatever is left: in the order of the names, spread over the free parts      → (how: "order"), only when asked

Pure functions, no network (the LLM is passed in). All times are SOURCE seconds (the transcript's clock).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .visualplan import _STOP, _WORD

# Devanagari → rough Latin, only good enough to compare "ताज महल" with "taj mahal" (not a real transliteration)
_CONS = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n", "ट": "t", "ठ": "th",
         "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n", "प": "p", "फ": "f", "ब": "b", "भ": "bh",
         "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ळ": "l",
         "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f"}
_VOW = {"अ": "a", "आ": "aa", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऋ": "ri", "ऑ": "o"}
_SIGN = {"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ृ": "ri", "ॉ": "o", "ं": "n", "ँ": "n", "ः": "h"}


def translit(word: str) -> str:
    out = []
    i, n = 0, len(word)
    while i < n:
        ch = word[i]
        two = word[i:i + 2]
        if two in _CONS:
            ch, i = two, i + 1
        if ch in _CONS:
            out.append(_CONS[ch])
            nxt = word[i + 1] if i + 1 < n else ""
            if nxt == "्":                       # virama: no vowel after this consonant
                i += 1
            elif nxt in _SIGN:
                out.append(_SIGN[nxt])
                i += 1
            elif i + 1 < n:                      # inherent "a", dropped at the end of a word (महल → mahal)
                out.append("a")
        elif ch in _VOW:
            out.append(_VOW[ch])
        elif ch in _SIGN:
            out.append(_SIGN[ch])
        elif ch.isascii():
            out.append(ch.lower())
        i += 1
    return "".join(out)


def _skel(w: str) -> str:
    """Consonant skeleton: 'mahal' / 'mehel' / 'mahaal' → 'mhl' — spelling of vowels in Hinglish is free."""
    w = _norm(w)
    s = w[0] + re.sub(r"[aeiouyh]", "", w[1:])        # h too: delhi / dilli, khana / kana — aspiration is spelt loosely
    return re.sub(r"(.)\1+", r"\1", s)


def _norm(w: str) -> str:
    return w.replace("ph", "f").replace("w", "v").replace("z", "j").replace("q", "k").replace("c", "k") if not w.startswith("ch") else w


def tokens(text: str) -> list[str]:
    """Meaningful words of a name / note / spoken line, lower-case Latin (Devanagari transliterated)."""
    text = re.sub(r"\.(mp4|mov|mkv|webm|jpe?g|png|webp|heic|gif|avi|m4v)$", "", str(text or ""), flags=re.I)
    text = re.sub(r"[_\-.,/()\[\]]+", " ", text)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    out = []
    for w in _WORD.findall(text):
        lw = w.lower()
        if lw in _STOP or lw.isdigit() or re.fullmatch(r"(img|vid|dsc|pxl|mvi|clip|video|photo|image|final|copy|new|edit|whatsapp|screenshot)\d*", lw):
            continue
        t = translit(lw) if re.search(r"[ऀ-ॿ]", lw) else lw
        if len(t) >= 3 and t not in _STOP:
            out.append(t)
    return out


def _sim(a: str, b: str) -> float:
    if a == b:
        return 1.0
    a, b = _norm(a), _norm(b)
    if a == b:
        return 0.95
    if a[0] != b[0] or abs(len(a) - len(b)) > 3:
        return 0.0
    sa, sb = _skel(a), _skel(b)
    if len(sa) >= 2 and sa == sb:
        return 0.85
    if len(a) >= 5 and len(b) >= 5 and (a.startswith(b[:5]) or b.startswith(a[:5])):
        return 0.7                                   # same stem: invest / investing / investment
    r = SequenceMatcher(None, a, b).ratio()
    return 0.65 if r >= 0.84 else 0.0


def _score(clip_tokens: list[str], line_tokens: list[str]) -> float:
    if not clip_tokens or not line_tokens:
        return 0.0
    got = sum(max((_sim(c, l) for l in line_tokens), default=0.0) for c in clip_tokens)
    return got / len(clip_tokens)


_TIME = re.compile(r"(?<!\d)(\d{1,2}):([0-5]\d)(?::([0-5]\d))?(?!\d)|(?<!\w)(\d{1,3})\s*m(?:in)?\s*(\d{1,2})\s*s(?:ec)?\b", re.I)


def explicit_time(text: str) -> float | None:
    m = _TIME.search(str(text or ""))
    if not m:
        return None
    if m.group(4) is not None:
        return int(m.group(4)) * 60 + int(m.group(5))
    a, b, c = int(m.group(1)), int(m.group(2)), m.group(3)
    return a * 3600 + b * 60 + int(c) if c is not None else a * 60 + b


def _natural(name: str):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", str(name or ""))]


def match(segments: list[dict], clips: list[dict], *, cuts: list[dict] | None = None, duration: float | None = None,
          min_gap: float = 2.5, image_seconds: float = 4.0, video_seconds: float = 6.0, spread: bool = True, ask=None) -> list[dict]:
    """clips: [{id, name, tags?, note?, kind ("image"/"video"), duration?}] →
    [{id, start, end, i (line index or None), line, score, how}] in the order of `clips`; an unplaced clip has start None."""
    gone = [(float(c["start"]), float(c["end"])) for c in cuts or [] if c.get("enabled", True)]
    lines = []
    for i, s in enumerate(segments or []):
        a, b = float(s.get("start") or 0), float(s.get("end") or 0)
        text = (s.get("text") or "").strip()
        if b <= a or not text or any(a < y and b > x and (min(b, y) - max(a, x)) > 0.5 * (b - a) for x, y in gone):
            continue
        lines.append({"i": i, "start": a, "end": b, "text": text, "tok": tokens(text)})
    total = float(duration or (lines[-1]["end"] if lines else 0) or 0)
    res: list[dict] = [{"id": c.get("id"), "start": None, "end": None, "i": None, "line": "", "score": 0.0, "how": "none"} for c in clips]
    used: list[float] = []

    def length(c: dict) -> float:
        if (c.get("kind") or "") == "image":
            return float(image_seconds)
        d = float(c.get("duration") or 0)
        return min(d, float(video_seconds)) if d > 0 else float(video_seconds)

    def free(t: float) -> bool:
        return all(abs(t - u) >= min_gap for u in used)

    def put(k: int, t: float, how: str, line: dict | None = None, score: float = 0.0) -> None:
        t = max(0.0, min(t, max(0.0, total - 0.5))) if total else max(0.0, t)
        res[k].update({"start": round(t, 2), "end": round(t + length(clips[k]), 2), "i": line["i"] if line else None,
                       "line": line["text"] if line else "", "score": round(score, 2), "how": how})
        used.append(t)

    def slot_in(ln: dict) -> float | None:
        """The line's start, or a little later inside the same line when another visual already sits there."""
        t = ln["start"]
        while t <= max(ln["start"], ln["end"] - 1.0):
            if free(t):
                return t
            t += min_gap
        return None

    def line_at(t: float) -> dict | None:
        return next((ln for ln in lines if ln["start"] - 0.3 <= t <= ln["end"] + 0.3), None)

    desc = [" ".join(str(x) for x in (c.get("note") or "", c.get("name") or "", " ".join(c.get("tags") or [])) if x) for c in clips]

    # 1. a time the creator wrote
    for k, c in enumerate(clips):
        t = explicit_time(c.get("note") or "")
        if t is None:
            t = explicit_time(re.sub(r"\.\w{2,5}$", "", str(c.get("name") or "")))
        if t is not None and (not total or t < total):
            put(k, float(t), "time", line_at(float(t)), 1.0)

    # 2. the LLM reads the talk and the clip descriptions
    todo = [k for k in range(len(clips)) if res[k]["start"] is None and tokens(desc[k])]
    if ask and todo and lines:
        shown = lines[:400]
        prompt = ("A creator recorded a talk and has supporting clips / photos for it. Decide at which spoken line each clip should appear: "
                  "the line where the speaker talks about what the clip shows. The talk may be Hindi, Hinglish or English; clip names are short "
                  "human labels and may be in another script than the transcript.\n\nSPOKEN LINES:\n"
                  + "\n".join(f'{n}. [{ln["start"]:.0f}s] {ln["text"][:160]}' for n, ln in enumerate(shown))
                  + "\n\nCLIPS:\n" + "\n".join(f'{chr(65 + j % 26)}{j // 26 or ""}. {desc[k][:140]}' for j, k in enumerate(todo))
                  + '\n\nReturn a JSON array with one object per clip that clearly belongs somewhere: {"clip": the clip label, "line": line number}. '
                  "Leave a clip out when no line is about it. Do not put two clips on the same line.")
        label = {f"{chr(65 + j % 26)}{j // 26 or ''}": k for j, k in enumerate(todo)}
        try:
            ans = ask(prompt, system="You are a careful video editor matching B-roll to a transcript. JSON only.")
            for r in (ans if isinstance(ans, list) else (ans or {}).get("items") or []):
                if not isinstance(r, dict):
                    continue
                k = label.get(str(r.get("clip") or "").strip().rstrip("."))
                n = r.get("line")
                if k is None or not isinstance(n, int) or not (0 <= n < len(shown)) or res[k]["start"] is not None:
                    continue
                ln = shown[n]
                t = slot_in(ln)
                if t is not None:
                    put(k, t, "ai", ln, 1.0)
        except Exception:  # noqa: BLE001 — the words below still do the job
            pass

    # 3. the words themselves
    cand = []
    for k in range(len(clips)):
        if res[k]["start"] is not None:
            continue
        ct = list(dict.fromkeys(tokens(desc[k])))
        for ln in lines:
            sc = _score(ct, ln["tok"])
            if sc >= 0.34:
                cand.append((sc, -ln["start"], k, ln))
    for sc, _, k, ln in sorted(cand, key=lambda x: (x[0], x[1]), reverse=True):
        if res[k]["start"] is None:
            t = slot_in(ln)
            if t is not None:
                put(k, t, "words", ln, sc)

    # 4. the rest, in the order of their names, over the parts that are still free
    left = [k for k in sorted(range(len(clips)), key=lambda k: _natural(clips[k].get("name"))) if res[k]["start"] is None]
    if spread and left and lines:
        slots = [ln for ln in lines if ln["start"] >= 2.5 and free(ln["start"])]
        picked: list[dict] = []
        for j in range(len(left)):
            if not slots:
                break
            want = (j + 1) / (len(left) + 1) * (total or lines[-1]["end"])
            ln = min(slots, key=lambda s_: abs(s_["start"] - want))
            picked.append(ln)
            slots = [s_ for s_ in slots if abs(s_["start"] - ln["start"]) >= min_gap]
        for k, ln in zip(left, sorted(picked, key=lambda s_: s_["start"])):
            put(k, ln["start"], "order", ln, 0.0)

    # a visual never runs into the next one
    order = sorted((r for r in res if r["start"] is not None), key=lambda r: r["start"])
    for a, b in zip(order, order[1:]):
        if a["end"] > b["start"] - 0.15:
            a["end"] = round(max(a["start"] + 1.0, b["start"] - 0.15), 2)
    if total:
        for r in order:
            r["end"] = round(min(r["end"], total), 2)
    return res
