"""Re-transcription bookkeeping: put a re-heard line into an existing transcript,
keep the creator's cut choices when the whole transcript is rebuilt, and keep an
editor that still has an older transcript from writing old words back.

Transcript fields used here:
  rev       int, +1 every time a transcribe job lands (whole or one line)
  history   [{rev, range: [s, e]} | {rev, full: true}] — the last 50 changes
"""

from __future__ import annotations

from . import wordfix

PAD = 0.3          # seconds of audio heard on each side of the chosen part
MAX_PART = 120.0   # longest part that can be re-heard in one go
HISTORY = 50


def part_window(transcript: dict | None, part: dict | None) -> tuple[float, float] | None:
    """The source-time window [start, end] chosen in a retranscribe request, or None for the whole file.

    part = {"start": s, "end": e} or {"segments": [i, ...]} (indexes into transcript.segments)."""
    if not part:
        return None
    if part.get("start") is not None and part.get("end") is not None:
        try:
            s, e = float(part["start"]), float(part["end"])
        except (TypeError, ValueError):
            raise ValueError("start / end सेकंड में होने चाहिए") from None
    elif part.get("segments") not in (None, []):
        segs = (transcript or {}).get("segments") or []
        idx = part["segments"] if isinstance(part["segments"], list) else [part["segments"]]
        try:
            chosen = [segs[int(i)] for i in idx]
        except (IndexError, TypeError, ValueError):
            raise ValueError("ऐसी line नहीं मिली") from None
        times = [(float(w["start"]), float(w["end"])) for sg in chosen for w in (sg.get("words") or [])
                 if w.get("start") is not None and w.get("end") is not None]
        times += [(float(sg["start"]), float(sg["end"])) for sg in chosen
                  if not sg.get("words") and sg.get("start") is not None and sg.get("end") is not None]
        if not times:
            raise ValueError("इस line का समय नहीं मिला")
        s, e = min(t[0] for t in times), max(t[1] for t in times)
    else:
        return None
    if e < s:
        s, e = e, s
    s = max(0.0, s)
    if e - s < 0.2:
        raise ValueError("चुना हुआ हिस्सा बहुत छोटा है")
    if e - s > MAX_PART:
        raise ValueError("एक बार में 2 मिनट तक का हिस्सा ही दोबारा सुना जा सकता है")
    return round(s, 3), round(e, 3)


def _mid(w: dict) -> float:
    return (float(w["start"]) + float(w["end"])) / 2


def _inside(w: dict, s: float, e: float) -> bool:
    return w.get("start") is not None and w.get("end") is not None and s <= _mid(w) <= e


def _seg_from(seg: dict, words: list[dict]) -> dict:
    out = {k: v for k, v in seg.items() if k not in ("alts",)}
    out["words"] = words
    out["text"] = " ".join(w["w"] for w in words)
    out["start"], out["end"] = words[0]["start"], max(float(w["end"]) for w in words)
    return out


def splice_window(transcript: dict | None, core: tuple[float, float] | list, new_segments: list[dict] | None,
                  alts: list[dict] | None = None) -> dict:
    """A new transcript where only the words whose middle lies in core = [s, e] are replaced.

    Segments with no word in the window are kept as the very same objects (byte-identical
    after JSON), segments cut by the window keep their words outside it (split in two when
    the window is in their middle). The new words become one segment; `alts` (other
    readings: [{text, words}]) are stored on it for the editor to offer."""
    s, e = float(core[0]), float(core[1])
    tr = dict(transcript or {})
    out: list[dict] = []
    for seg in tr.get("segments") or []:
        words = seg.get("words") or []
        if not words:
            if seg.get("start") is not None and seg.get("end") is not None and s <= (float(seg["start"]) + float(seg["end"])) / 2 <= e:
                continue  # a text-only line inside the window is replaced
            out.append(seg)
            continue
        if not any(_inside(w, s, e) for w in words):
            out.append(seg)
            continue
        before = [w for w in words if w.get("start") is not None and _mid(w) < s]
        after = [w for w in words if w.get("start") is not None and _mid(w) > e]
        if before:
            out.append(_seg_from(seg, before))
        if after:
            out.append(_seg_from(seg, after))
    new_words = [w for sg in new_segments or [] for w in (wordfix.clean_segment(sg).get("words") or []) if _inside(w, s, e)]
    if new_words:
        seg = {"start": new_words[0]["start"], "end": max(w["end"] for w in new_words),
               "text": " ".join(w["w"] for w in new_words), "words": new_words, "redo": True}
        good_alts = []
        for a in alts or []:
            aw = [w for w in wordfix.clean_words(a.get("words") or []) if _inside(w, s, e)]
            if aw:
                txt = " ".join(w["w"] for w in aw)
                if txt != seg["text"] and txt not in (x["text"] for x in good_alts):
                    good_alts.append({"text": txt, "words": aw})
        if good_alts:
            seg["alts"] = good_alts
        out.append(seg)
    out.sort(key=lambda sg: (float(sg.get("start") or 0.0), float(sg.get("end") or 0.0)))
    tr["segments"] = out
    tr["text"] = " ".join((sg.get("text") or "").strip() for sg in out).strip()
    return tr


def bump(transcript: dict, prev: dict | None, entry: dict) -> dict:
    """Give a transcript that just landed the next rev and a history entry."""
    rev = int((prev or {}).get("rev") or 0) + 1
    hist = [] if entry.get("full") else list((prev or {}).get("history") or [])
    transcript["rev"] = rev
    transcript["history"] = (hist + [{**entry, "rev": rev}])[-HISTORY:]
    return transcript


def reconcile(current: dict | None, incoming: dict) -> dict | None:
    """The transcript to store when the editor saves `incoming`.

    Same rev (or no rev tracking yet) → incoming as is. Older rev and only single lines were
    re-heard since → the editor's transcript with those lines taken from the current one
    (both the creator's edits and the new lines survive). A whole re-transcribe since, or
    unknown history → None (don't write old words back)."""
    if not current or current.get("rev") is None:
        return incoming
    cur_rev = int(current["rev"])
    in_rev = incoming.get("rev") or 0  # loaded before rev tracking existed
    try:
        in_rev = int(in_rev)
    except (TypeError, ValueError):
        return None
    if in_rev == cur_rev:
        return incoming
    if in_rev > cur_rev:
        return None
    newer = [h for h in current.get("history") or [] if int(h.get("rev") or 0) > in_rev]
    if len(newer) != cur_rev - in_rev or any(not h.get("range") for h in newer):
        return None
    out = incoming
    for h in sorted(newer, key=lambda h: h["rev"]):
        s, e = h["range"]
        segs_now = [sg for sg in current.get("segments") or []
                    if any(_inside(w, s, e) for w in sg.get("words") or [])]
        alts = next((sg.get("alts") for sg in segs_now if sg.get("alts")), None)
        out = splice_window(out, (s, e), [{**sg, "words": [w for w in sg["words"] if _inside(w, s, e)]} for sg in segs_now], alts)
    out["rev"], out["history"] = cur_rev, current.get("history") or []
    return out


def carry_cut_choices(old_edl: dict | None, new_edl: dict) -> dict:
    """After a whole re-transcribe the cut list is rebuilt; keep what the creator decided:
    manual cuts stay, and a suggested cut they switched off stays off (matched by time)."""
    if not old_edl or not old_edl.get("cuts"):
        return new_edl
    old = old_edl["cuts"]
    cuts = [dict(c) for c in new_edl.get("cuts") or []]
    off = [c for c in old if c.get("enabled") is False and c.get("reason") != "manual"]
    for c in cuts:
        for o in off:
            ov = min(c["end"], float(o["end"])) - max(c["start"], float(o["start"]))
            if ov > 0.5 * min(c["end"] - c["start"], float(o["end"]) - float(o["start"])):
                c["enabled"] = False
                break
    manual = [dict(o) for o in old if o.get("reason") == "manual" or "manual" in (o.get("reasons") or [])]
    cuts += manual
    cuts.sort(key=lambda c: c["start"])
    used = set()
    for i, c in enumerate(cuts):
        if not c.get("id") or c["id"] in used:
            c["id"] = f"c{i + 1}" if f"c{i + 1}" not in used else f"m{i + 1}"
        used.add(c["id"])
    on = [c for c in cuts if c.get("enabled", True)]
    removed = sum(c["end"] - c["start"] for c in on)
    stats = {**(new_edl.get("stats") or {}), "cuts": len(on), "removed_seconds": round(removed, 2),
             "final_seconds": round(float(new_edl.get("duration") or 0) - removed, 2),
             "kept_manual": len(manual)}
    return {**old_edl, **new_edl, "cuts": cuts, "stats": stats}
