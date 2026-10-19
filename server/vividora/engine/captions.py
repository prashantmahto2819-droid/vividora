"""Hindi-friendly captions as ASS subtitles (burned in by ffmpeg/libass) and SRT.

libass shapes Devanagari with HarfBuzz, so matras and conjuncts render
correctly as long as a Devanagari font (Noto Sans Devanagari, Mukta…) is
installed or shipped in the fonts folder.
"""

from __future__ import annotations

from typing import Any


def ass_color(hex_color: str, transparency: float = 0.0) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    r, g, b = h[0:2], h[2:4], h[4:6]
    a = max(0, min(255, round(transparency * 255)))
    return f"&H{a:02X}{b}{g}{r}".upper()


def _esc(text: str) -> str:
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def _t(sec: float) -> str:
    sec = max(0.0, sec)
    cs = int(round(sec * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _srt_t(sec: float) -> str:
    ms = int(round(max(0.0, sec) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def chunk_words(words: list[dict], max_words: int, max_chars: int, gap_break: float = 0.6) -> list[list[dict]]:
    chunks: list[list[dict]] = []
    cur: list[dict] = []
    chars = 0
    for i, w in enumerate(words):
        text = w["w"].strip()
        prev = words[i - 1] if i else None
        breaks = (
            cur
            and (
                len(cur) >= max_words
                or chars + 1 + len(text) > max_chars
                or (prev is not None and w["start"] - prev["end"] > gap_break)
                or (prev is not None and prev["w"].rstrip().endswith(("।", ".", "?", "!", "॥")))
            )
        )
        if breaks:
            chunks.append(cur)
            cur, chars = [], 0
        cur.append(w)
        chars += (1 if chars else 0) + len(text)
    if cur:
        chunks.append(cur)
    return chunks


def _wrap(texts: list[str], max_line_chars: int, max_lines: int) -> list[int]:
    """Indices after which to insert a line break (at most max_lines-1)."""
    if max_lines < 2:
        return []
    total = sum(len(t) for t in texts) + len(texts) - 1
    if total <= max_line_chars:
        return []
    best, best_diff, run = None, 10**9, 0
    for i, t in enumerate(texts[:-1]):
        run += len(t) + (1 if i else 0)
        diff = abs(total - run - 1 - run)
        if diff < best_diff:
            best, best_diff = i, diff
    return [best] if best is not None else []


def build_ass(words: list[dict], style: dict, width: int, height: int, *, margin_v_ratio: float,
              scale: float = 1.0, hook: dict | None = None, duration: float | None = None) -> str:
    base = min(width, height)
    size = round(style.get("size", 0.06) * base * scale)
    outline = round(style.get("outline", 0.005) * base, 1)
    shadow = round(style.get("shadow", 0.0) * base, 1)
    primary = ass_color(style.get("primary", "#FFFFFF"))
    hl = ass_color(style.get("highlight", "#FFD400"))
    outline_c = ass_color(style.get("outline_color", "#000000"))
    box = bool(style.get("box"))
    back = ass_color(style.get("box_color", "#000000"), 1 - float(style.get("box_alpha", 0.55))) if box \
        else ass_color("#000000", 0.4)
    border_style = 3 if box else 1
    bold = -1 if style.get("bold", True) else 0
    font = style.get("font", "Noto Sans Devanagari")
    margin_v = round(margin_v_ratio * height)
    margin_lr = round(0.06 * width)
    # wider frames fit more characters on a line
    max_chars = int(style.get("max_chars", 24) * max(1.0, width / base))
    max_words = int(style.get("max_words", 6))
    max_lines = int(style.get("max_lines", 2))
    mode = style.get("mode", "line")
    pop = int(style.get("pop_scale", 118))

    hook_size = round(0.085 * base * scale)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,{font},{size},{primary},{hl},{outline_c},{back},{bold},0,0,0,100,100,0,0,"
        f"{border_style},{outline},{shadow},2,{margin_lr},{margin_lr},{margin_v},1",
        f"Style: Hook,{font},{hook_size},{ass_color('#111111')},{hl},{hl},{hl},-1,0,0,0,100,100,0,0,"
        f"3,{round(0.02 * base, 1)},0,8,{margin_lr},{margin_lr},{round(0.13 * height if height > width else 0.06 * height)},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    chunks = chunk_words(words, max_words, max_chars * max_lines)
    for ci, chunk in enumerate(chunks):
        texts = [_esc(w["w"].strip()) for w in chunk]
        breaks = set(_wrap(texts, max_chars, max_lines))
        start = chunk[0]["start"]
        nxt = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else None
        end = chunk[-1]["end"] + 0.15
        if nxt is not None and nxt - end < 0.35:
            end = nxt  # no flicker between close lines
        if end <= start:
            end = start + 0.3

        def render(active: int | None) -> str:
            parts = []
            for i, t in enumerate(texts):
                if active is not None and i == active:
                    if mode == "pop":
                        t = (f"{{\\c{hl}\\fscx100\\fscy100\\t(0,90,\\fscx{pop}\\fscy{pop})"
                             f"\\t(90,180,\\fscx106\\fscy106)}}{t}{{\\c{primary}\\fscx100\\fscy100}}")
                    else:
                        t = f"{{\\c{hl}}}{t}{{\\c{primary}}}"
                parts.append(t)
                if i < len(texts) - 1:
                    parts.append("\\N" if i in breaks else " ")
            return "".join(parts)

        if mode == "line":
            lines.append(f"Dialogue: 0,{_t(start)},{_t(end)},Cap,,0,0,0,,{render(None)}")
        else:
            for wi, w in enumerate(chunk):
                ws = start if wi == 0 else w["start"]
                we = chunk[wi + 1]["start"] if wi + 1 < len(chunk) else end
                if we <= ws:
                    continue
                lines.append(f"Dialogue: 0,{_t(ws)},{_t(we)},Cap,,0,0,0,,{render(wi)}")

    if hook and hook.get("text"):
        hd = float(hook.get("seconds", 3.0))
        if duration:
            hd = min(hd, duration)
        text = _esc(hook["text"]).replace("|", "\\N")
        lines.append(f"Dialogue: 1,{_t(0)},{_t(hd)},Hook,,0,0,0,,{{\\fad(120,200)}}{text}")
    return "\n".join(lines) + "\n"


def build_srt(words: list[dict], max_words: int = 9, max_chars: int = 42) -> str:
    out = []
    chunks = chunk_words(words, max_words, max_chars)
    for i, chunk in enumerate(chunks, start=1):
        text = " ".join(w["w"].strip() for w in chunk)
        end = chunk[-1]["end"] + 0.1
        if i < len(chunks):
            end = min(end, chunks[i][0]["start"] - 0.01)
        end = max(end, chunk[0]["start"] + 0.3)
        out.append(f"{i}\n{_srt_t(chunk[0]['start'])} --> {_srt_t(end)}\n{text}\n")
    return "\n".join(out)


def plain_text(transcript: dict[str, Any]) -> str:
    return " ".join((s.get("text") or "").strip() for s in transcript.get("segments", [])).strip()
