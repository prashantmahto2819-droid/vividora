"""Text-based editing: delete words in the transcript → cuts in the EDL (Descript-style).

Words are addressed by their index in autocut.words_of(transcript) (the order the editor shows),
or by source-time ranges. Cuts made here carry "source": "text"; the creator's other cuts (manual
or automatic) are never moved — a new cut only covers what is not already cut.

apply(edl, transcript, ops) where ops may contain:
  delete:        [i, …] | [[start, end], …]    words / time ranges to remove
  restore:       [i, …] | [[start, end], …]    bring words back (cuts over them are trimmed / switched off)
  keep_text:     "the full text to keep"       words not found in it (in order) are deleted
  fillers:       true                          remove every filler word (um, अं, …)
  silences_over: 0.8                           remove pauses between words longer than this (s)
  keep_pause:    0.12                          breathing room left at each side of a removed gap
→ {"edl": new edl, "added": n, "changed": n, "removed_words": [i, …]}
"""

from __future__ import annotations

from difflib import SequenceMatcher

from .autocut import _FILLER_NORM, keep_segments, norm, words_of

MIN_CUT = 0.04


def _word_index_ranges(sel, words: list[dict]) -> list[tuple[int, int]]:
    """Selection → sorted runs of consecutive word indexes [(i0, i1)] (inclusive)."""
    idx: set[int] = set()
    for s in sel or []:
        if isinstance(s, (int, float)) and not isinstance(s, bool):
            i = int(s)
            if 0 <= i < len(words):
                idx.add(i)
        elif isinstance(s, (list, tuple)) and len(s) >= 2:
            a, b = float(s[0]), float(s[1])
            for i, w in enumerate(words):
                mid = (w["start"] + w["end"]) / 2
                if a <= mid <= b:
                    idx.add(i)
        elif isinstance(s, dict) and "start" in s and "end" in s:
            a, b = float(s["start"]), float(s["end"])
            for i, w in enumerate(words):
                if a <= (w["start"] + w["end"]) / 2 <= b:
                    idx.add(i)
    runs: list[tuple[int, int]] = []
    for i in sorted(idx):
        if runs and i == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], i)
        else:
            runs.append((i, i))
    return runs


def _run_span(run: tuple[int, int], words: list[dict], duration: float, keep: float) -> tuple[float, float]:
    """Time span to cut for words i0..i1, swallowing the pauses around them (leaving `keep` s)."""
    i0, i1 = run
    a, b = words[i0]["start"], words[i1]["end"]
    if i0 > 0:
        prev_end = words[i0 - 1]["end"]
        a = min(a, max(prev_end + min(keep, (a - prev_end) / 2), prev_end))
    else:
        a = max(0.0, a - 0.05)
    if i1 + 1 < len(words):
        nxt = words[i1 + 1]["start"]
        b = max(b, min(nxt - min(keep, (nxt - b) / 2), nxt))
    else:
        b = min(duration, b + 0.05)
    return max(0.0, a), min(duration, b)


def _uncovered(a: float, b: float, cuts: list[dict]) -> list[tuple[float, float]]:
    """Parts of [a, b] not already inside an enabled cut."""
    spans = sorted((float(c["start"]), float(c["end"])) for c in cuts if c.get("enabled", True))
    out, t = [], a
    for s, e in spans:
        if e <= t or s >= b:
            continue
        if s > t:
            out.append((t, s))
        t = max(t, e)
    if t < b:
        out.append((t, b))
    return [(x, y) for x, y in out if y - x >= MIN_CUT]


def _next_id(cuts: list[dict]) -> int:
    n = 0
    for c in cuts:
        cid = str(c.get("id", ""))
        if cid.startswith("t") and cid[1:].isdigit():
            n = max(n, int(cid[1:]))
    return n + 1


def stats(edl: dict) -> dict:
    cuts = edl.get("cuts") or []
    on = [c for c in cuts if c.get("enabled", True)]
    removed = float(edl["duration"]) - sum(b - a for a, b in keep_segments(edl))
    by = {}
    for c in on:
        by[c.get("reason", "manual")] = by.get(c.get("reason", "manual"), 0) + 1
    return {**(edl.get("stats") or {}), "cuts": len(on), "removed_seconds": round(removed, 2),
            "final_seconds": round(float(edl["duration"]) - removed, 2), "by_reason": by}


def removed_words(edl: dict, words: list[dict]) -> list[int]:
    """Indexes of words that are (mostly) cut away — the editor strikes these through."""
    keep = keep_segments(edl)
    out = []
    for i, w in enumerate(words):
        d = max(1e-3, w["end"] - w["start"])
        kept = sum(max(0.0, min(w["end"], b) - max(w["start"], a)) for a, b in keep)
        if kept / d < 0.5:
            out.append(i)
    return out


def apply(edl: dict, transcript: dict, ops: dict) -> dict:
    words = words_of(transcript or {})
    duration = float(edl.get("duration") or (words[-1]["end"] if words else 0))
    cuts = [dict(c) for c in (edl.get("cuts") or [])]
    keep_pause = max(0.0, min(0.5, float(ops.get("keep_pause", 0.12) or 0)))
    new_spans: list[tuple[float, float, str, str]] = []

    sel_runs = _word_index_ranges(ops.get("delete"), words)
    for run in sel_runs:
        a, b = _run_span(run, words, duration, keep_pause)
        new_spans.append((a, b, "text", " ".join(w["w"] for w in words[run[0]:run[1] + 1])[:80]))
    if ops.get("keep_text"):
        tgt = [norm(t) for t in str(ops["keep_text"]).split() if norm(t)]
        src = [norm(w["w"]) for w in words]
        sm = SequenceMatcher(a=src, b=tgt, autojunk=False)
        keep_idx = set()
        for blk in sm.get_matching_blocks():
            keep_idx.update(range(blk.a, blk.a + blk.size))
        for run in _word_index_ranges([i for i in range(len(words)) if i not in keep_idx and src[i]], words):
            a, b = _run_span(run, words, duration, keep_pause)
            new_spans.append((a, b, "text", " ".join(w["w"] for w in words[run[0]:run[1] + 1])[:80]))
    if ops.get("fillers"):
        fill = [i for i, w in enumerate(words) if norm(w["w"]) in _FILLER_NORM]
        for run in _word_index_ranges(fill, words):
            a, b = _run_span(run, words, duration, keep_pause)
            new_spans.append((a, b, "filler", " ".join(w["w"] for w in words[run[0]:run[1] + 1])[:80]))
    gap = ops.get("silences_over")
    if gap not in (None, "", False):
        g = max(0.1, float(gap))
        edges = [(0.0, words[0]["start"])] if words else []
        edges += [(words[i]["end"], words[i + 1]["start"]) for i in range(len(words) - 1)]
        if words:
            edges.append((words[-1]["end"], duration))
        last = len(edges) - 1
        for i, (a, b) in enumerate(edges):
            if b - a > g:
                lo = a if i == 0 else a + keep_pause            # leading silence: from 0
                hi = b if (i == last and words) else b - keep_pause  # trailing silence: to the end
                if hi - lo >= MIN_CUT:
                    new_spans.append((lo, hi, "silence", ""))

    added = 0
    nid = _next_id(cuts)
    for a, b, reason, text in sorted(new_spans):
        for x, y in _uncovered(a, b, cuts):
            cuts.append({"id": f"t{nid}", "start": round(x, 3), "end": round(y, 3), "enabled": True, "reason": reason,
                         "source": "text", **({"text": text} if text else {})})
            nid += 1
            added += 1

    changed = 0
    for run in _word_index_ranges(ops.get("restore"), words):
        a, b = words[run[0]]["start"], words[run[1]]["end"]
        out = []
        for c in cuts:
            s, e = float(c["start"]), float(c["end"])
            if not c.get("enabled", True) or e <= a or s >= b:
                out.append(c)
                continue
            changed += 1
            if s < a - MIN_CUT:
                out.append({**c, "end": round(a, 3)})
            if e > b + MIN_CUT:
                out.append({**c, "id": f"{c.get('id', 'c')}r", "start": round(b, 3)})
            if s >= a - MIN_CUT and e <= b + MIN_CUT:
                out.append({**c, "enabled": False, "restored": True})
        cuts = out

    cuts.sort(key=lambda c: (float(c["start"]), float(c["end"])))
    new = {**edl, "duration": duration, "cuts": cuts}
    new["stats"] = stats(new)
    return {"edl": new, "added": added, "changed": changed, "removed_words": removed_words(new, words)}
