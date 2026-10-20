"""Stylish captions as ASS subtitles (burned in by ffmpeg/libass) and SRT.

libass shapes Devanagari with HarfBuzz, so matras and conjuncts render
correctly with the Devanagari fonts shipped in server/fonts.

A caption style (presets/captions/*.json) has:
  mode        line · karaoke · pop · wordbox · typewriter
  font, weight(bold), italic, uppercase (Latin only)
  size, outline, shadow, glow      fractions of the short side of the frame
  primary, highlight, outline_color, shadow_color, box_color, box_alpha
  box         false · "line" (box behind each line) · "word" (box behind the spoken word)
  position    bottom · center · top
  max_words, max_chars, max_lines, pop_scale, fade
The render request may override size_scale, position, primary, highlight, font.
"""

from __future__ import annotations

from typing import Any

ALIGN = {"bottom": 2, "center": 5, "top": 8}


def ass_color(hex_color: str, transparency: float = 0.0) -> str:
    h = (hex_color or "#FFFFFF").lstrip("#")
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
        breaks = cur and (
            len(cur) >= max_words
            or chars + 1 + len(text) > max_chars
            or (prev is not None and w["start"] - prev["end"] > gap_break)
            or (prev is not None and prev["w"].rstrip().endswith(("।", ".", "?", "!", "॥")))
        )
        if breaks:
            chunks.append(cur)
            cur, chars = [], 0
        cur.append(w)
        chars += (1 if chars else 0) + len(text)
    if cur:
        chunks.append(cur)
    return chunks


def _wrap(texts: list[str], max_line_chars: int, max_lines: int) -> set[int]:
    """Indices after which to insert a line break (at most max_lines-1)."""
    if max_lines < 2:
        return set()
    total = sum(len(t) for t in texts) + len(texts) - 1
    if total <= max_line_chars:
        return set()
    best, best_diff, run = None, 10**9, 0
    for i, t in enumerate(texts[:-1]):
        run += len(t) + (1 if i else 0)
        diff = abs(total - run - 1 - run)
        if diff < best_diff:
            best, best_diff = i, diff
    return {best} if best is not None else set()


def _is_latin(s: str) -> bool:
    return all(ord(c) < 0x250 for c in s)


def resolve_style(style: dict, overrides: dict | None) -> dict:
    """Apply the user's render-time choices on top of a preset."""
    s = dict(style)
    o = overrides or {}
    if o.get("primary"):
        s["primary"] = o["primary"]
    if o.get("highlight"):
        s["highlight"] = o["highlight"]
    if o.get("font"):
        s["font"] = o["font"]
    if o.get("position") in ALIGN:
        s["position"] = o["position"]
    if o.get("italic") is not None and o.get("italic") != "":
        s["italic"] = bool(o["italic"])
    if o.get("uppercase") is not None and o.get("uppercase") != "":
        s["uppercase"] = bool(o["uppercase"])
    if o.get("bold") is not None and o.get("bold") != "":
        s["bold"] = bool(o["bold"])
    try:
        if o.get("letter_spacing") not in (None, ""):
            s["letter_spacing"] = max(-0.01, min(0.03, float(o["letter_spacing"])))
    except (TypeError, ValueError):
        pass
    for key, lo, hi in (("outline_scale", 0.0, 3.0), ("shadow_scale", 0.0, 3.0)):
        try:
            if o.get(key) not in (None, ""):
                base_key = key.replace("_scale", "")
                s[base_key] = float(s.get(base_key, 0.005 if base_key == "outline" else 0.0)) * max(lo, min(hi, float(o[key])))
                if base_key == "shadow" and s[base_key] == 0 and float(o[key]) > 0:
                    s[base_key] = 0.004 * float(o[key])
        except (TypeError, ValueError):
            pass
    if o.get("outline_color"):
        s["outline_color"] = o["outline_color"]
    try:
        sc = float(o.get("size_scale", 1.0) or 1.0)
    except (TypeError, ValueError):
        sc = 1.0
    s["size"] = float(s.get("size", 0.06)) * max(0.5, min(2.0, sc))
    return s


def build_ass(words: list[dict], style: dict, width: int, height: int, *, margin_v_ratio: float,
              scale: float = 1.0, hook: dict | None = None, duration: float | None = None,
              extra_styles: list[str] | None = None, extra_events: list[str] | None = None) -> str:
    base = min(width, height)
    size = round(style.get("size", 0.06) * base * scale)
    outline = round(style.get("outline", 0.005) * base, 1)
    shadow = round(style.get("shadow", 0.0) * base, 1)
    glow = round(style.get("glow", 0.0) * base, 1)
    primary = ass_color(style.get("primary", "#FFFFFF"))
    hl = ass_color(style.get("highlight", "#FFD400"))
    outline_c = ass_color(style.get("outline_color", "#000000"))
    shadow_c = ass_color(style.get("shadow_color", "#000000"), float(style.get("shadow_alpha", 0.35)))
    box = style.get("box") or False
    box_c = style.get("box_color", "#000000")
    box_alpha = float(style.get("box_alpha", 0.6))
    # BorderStyle 4 = box behind each line (libass); 1 = outline + shadow
    if box == "line":
        border_style, back = 4, ass_color(box_c, 1 - box_alpha)
    else:
        border_style, back = 1, shadow_c
    bold = -1 if style.get("bold", True) else 0
    italic = -1 if style.get("italic") else 0
    font = style.get("font", "Noto Sans Devanagari")
    spacing = round(float(style.get("letter_spacing", 0)) * base, 1)
    position = style.get("position", "bottom")
    align = ALIGN.get(position, 2)
    margin_v = round(margin_v_ratio * height) if position != "center" else 0
    margin_lr = round(0.06 * width)
    max_chars = int(style.get("max_chars", 24) * max(1.0, width / base))
    max_words = int(style.get("max_words", 6))
    max_lines = int(style.get("max_lines", 2))
    mode = style.get("mode", "line")
    pop = int(style.get("pop_scale", 118))
    fade = int(style.get("fade", 0))
    upper = bool(style.get("uppercase"))
    word_box = box == "word"

    hk = hook or {}
    hook_size = round(0.085 * base * scale * float(hk.get("size_scale") or 1.0))
    hook_font = hk.get("font") or style.get("hook_font", font)
    hook_fg = ass_color(hk.get("color") or "#111111")
    hook_bg = ass_color(hk["bg"]) if hk.get("bg") else hl
    hook_align = {"top": 8, "center": 5, "bottom": 2}.get(hk.get("position") or "top", 8)
    hook_mv = round(0.13 * height if height > width else 0.06 * height) if hook_align != 2 else round(0.22 * height)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,{font},{size},{primary},{hl},{outline_c},{back},{bold},{italic},0,0,100,100,{spacing},0,"
        f"{border_style},{outline},{shadow},{align},{margin_lr},{margin_lr},{margin_v},1",
        f"Style: Hook,{hook_font},{hook_size},{hook_fg},{hook_bg},{hook_bg},{hook_bg},-1,{-1 if hk.get('italic') else 0},0,0,100,100,0,0,"
        f"3,{round(0.02 * base, 1)},0,{hook_align},{margin_lr},{margin_lr},{hook_mv},1",
        *(extra_styles or []),
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    lines.extend(extra_events or [])

    prefix = ""
    if glow:
        prefix += f"\\blur{glow}"
    if fade:
        prefix += f"\\fad({fade},{fade})"
    head = "{" + prefix + "}" if prefix else ""

    def word_text(t: str) -> str:
        return t.upper() if (upper and _is_latin(t)) else t

    chunks = chunk_words(words, max_words, max_chars * max_lines)
    for ci, chunk in enumerate(chunks):
        texts = [word_text(_esc(w["w"].strip())) for w in chunk]
        breaks = _wrap(texts, max_chars, max_lines)
        start = chunk[0]["start"]
        nxt = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else None
        end = chunk[-1]["end"] + 0.15
        if nxt is not None and nxt - end < 0.35:
            end = nxt
        if end <= start:
            end = start + 0.3

        def render(active: int | None, upto: int | None = None) -> str:
            parts = []
            for i, t in enumerate(texts):
                if upto is not None and i > upto:
                    break
                if active is not None and i == active:
                    if mode == "pop":
                        t = (f"{{\\c{hl}\\fscx100\\fscy100\\t(0,90,\\fscx{pop}\\fscy{pop})"
                             f"\\t(90,180,\\fscx106\\fscy106)}}{t}{{\\c{primary}\\fscx100\\fscy100}}")
                    elif word_box:
                        bc = ass_color(box_c)
                        bw = round(0.012 * base, 1)
                        t = (f"{{\\c{hl}\\3c{bc}\\bord{bw}\\shad0}}{t}"
                             f"{{\\c{primary}\\3c{outline_c}\\bord{outline}\\shad{shadow}}}")
                    else:
                        t = f"{{\\c{hl}}}{t}{{\\c{primary}}}"
                parts.append(t)
                if i < len(texts) - 1 and (upto is None or i < upto):
                    parts.append("\\N" if i in breaks else " ")
            return head + "".join(parts)

        if mode == "line":
            lines.append(f"Dialogue: 0,{_t(start)},{_t(end)},Cap,,0,0,0,,{render(None)}")
        else:
            for wi, w in enumerate(chunk):
                ws = start if wi == 0 else w["start"]
                we = chunk[wi + 1]["start"] if wi + 1 < len(chunk) else end
                if we <= ws:
                    continue
                text = render(wi, upto=wi) if mode == "typewriter" else render(wi)
                lines.append(f"Dialogue: 0,{_t(ws)},{_t(we)},Cap,,0,0,0,,{text}")

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
