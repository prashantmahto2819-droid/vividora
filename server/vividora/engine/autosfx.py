"""Auto SFX — sound effects placed from what is on the timeline (titles, B-roll, stickers, cuts, transitions).

Pure functions on the editor's `effects` dict (OUTPUT timeline, seconds). Nothing here touches the disk, so the editor
button, Autopilot and the public API all share it. Items it creates have `_id` starting with `asfx_`; running it again
replaces only those, never the creator's own sounds.

Rules (what makes it sound edited, not sprinkled):
* each event type has its own sound family and level — whoosh for B-roll/transitions, pop for titles and stickers,
  soft tick for jump cuts (only on "high" density);
* whoosh-type sounds start a few frames BEFORE the visual (the swoosh "arrives" with the picture), pops land exactly on it;
* a minimum gap between sounds and a per-minute cap by density, so nothing piles up;
* the same sound is never used twice in a row (rotates through the family);
* everything ducks under narration (`duck: true`), and levels are kept low — voice stays on top.
"""

from __future__ import annotations

PREFIX = "asfx_"

# density → (max sounds per minute, min gap seconds, include jump-cut ticks)
DENSITY = {"low": (4, 1.6, False), "normal": (8, 1.0, False), "high": (14, 0.6, True)}

# event → (sound-name candidates in preference order, base volume, lead-in seconds)
FAMILIES: dict[str, tuple[tuple[str, ...], float, float]] = {
    "title": (("pop", "pop soft", "click"), 0.55, 0.0),
    "sticker": (("pop", "bubble pop", "pop soft", "ding"), 0.5, 0.0),
    "broll": (("whoosh", "whoosh soft", "swipe", "swoosh long"), 0.5, 0.12),
    "photo": (("camera shutter", "slide", "whoosh soft"), 0.45, 0.0),         # a still picture as B-roll
    "cta": (("ding", "notification", "bell chime"), 0.5, 0.0),               # subscribe / follow / bell popups
    "hook": (("impact boom", "hit deep", "drop bass"), 0.6, 0.0),            # the opening title of the video
    "transition": (("swipe", "whoosh fast", "whoosh"), 0.45, 0.10),
    "glitch": (("glitch", "whoosh fast", "swipe"), 0.4, 0.05),               # cuts when the transition is a glitch
    "cut": (("tick", "click"), 0.3, 0.0),
    "hit": (("impact boom", "hit deep", "drop bass"), 0.6, 0.0),
}


_FALLBACK = {"hook": "title", "cta": "sticker", "photo": "broll", "glitch": "transition"}


def _library_sfx(library: list[dict]) -> dict[str, str]:
    return {(m.get("name") or "").strip().lower().replace("_", " "): m["id"]
            for m in library if m.get("kind") == "sfx" and m.get("id")}


_CTA_WORDS = ("subscribe", "follow", "like", "bell", "share", "comment", "cta", "popup")


def events(effects: dict, cut_times: list[float] | None = None, library: list[dict] | None = None) -> list[tuple[float, str, float]]:
    """Timeline events → [(time, event kind, weight)] sorted by time. Weight 1 = normal importance.
    With the library the event can be told apart further: a still photo, a subscribe/follow popup."""
    ev: list[tuple[float, str, float]] = []
    by_id = {m.get("id"): m for m in library or []}
    starts = sorted(float(t["start"]) for t in effects.get("titles") or [] if t.get("start") is not None and t.get("_id") != "ap_lower_third")
    for t in effects.get("titles") or []:
        if t.get("_id") == "ap_lower_third":
            continue  # a calm name-plate, no sound
        if t.get("start") is not None:
            first = float(t["start"]) == starts[0] and starts[0] <= 2.0      # the hook: a deep hit instead of a pop
            ev.append((float(t["start"]), "hook" if first else "title", 1.3 if first else 1.0))
    for b in effects.get("broll") or []:
        if b.get("start") is None:
            continue
        free = b.get("fit") == "free"  # stickers / emoji / CTA popups
        item = by_id.get(b.get("id")) or {}
        blob = f"{b.get('_id') or ''} {item.get('name') or ''} {item.get('tags') or ''}".lower()
        if free and (str(b.get("_id") or "").startswith(("ap_cta", "ap_bell"))
                     or any(w in blob for w in _CTA_WORDS)):
            ev.append((float(b["start"]), "cta", 1.0))
        elif free:
            ev.append((float(b["start"]), "sticker", 0.9))
        else:
            ev.append((float(b["start"]), "photo" if item.get("kind") == "image" else "broll", 1.1))
    if effects.get("transition") not in (None, "", "none"):
        kind = "glitch" if "glitch" in str(effects.get("transition")) else "transition"
        for c in cut_times or []:
            ev.append((float(c), kind, 0.8))
    else:
        for c in cut_times or []:
            ev.append((float(c), "cut", 0.5))
    ev.sort(key=lambda e: e[0])
    return ev


def plan(effects: dict, library: list[dict], *, out_dur: float, cut_times: list[float] | None = None,
         density: str = "normal", level: float = 1.0) -> list[dict]:
    """Return NEW sfx items (all `asfx_…`) for the given effects. Existing non-auto sfx items are respected:
    nothing is placed within the minimum gap of them."""
    per_min, gap, with_cuts = DENSITY.get(density, DENSITY["normal"])
    lib = _library_sfx(library)
    if not lib or out_dur <= 1:
        return []
    keep_old = [s for s in effects.get("sfx") or [] if not str(s.get("_id", "")).startswith(PREFIX)]
    taken = sorted(float(s.get("at") or 0) for s in keep_old)

    def free_at(t: float, extra: list[float]) -> bool:
        return all(abs(t - x) >= gap for x in taken + extra)

    chosen: list[dict] = []
    times: list[float] = []
    last_name: dict[str, str] = {}
    budget = max(1, int(round(per_min * out_dur / 60.0)) + 1)
    # important events first when the budget is tight, but keep timeline order in the result
    ranked = sorted(events(effects, cut_times, library), key=lambda e: -e[2])
    for t, kind, weight in ranked:
        if len(chosen) >= budget:
            break
        if kind == "cut" and not with_cuts:
            continue
        names, vol, lead = FAMILIES[kind]
        avail = [n for n in names if n in lib]
        if not avail and kind in _FALLBACK:      # an older / smaller sound library: fall back to the basic family
            names, vol, lead = FAMILIES[_FALLBACK[kind]]
            avail = [n for n in names if n in lib]
        if not avail:
            continue
        at = max(0.0, t - lead)
        if at >= out_dur - 0.2 or not free_at(at, times):
            continue
        pick = next((n for n in avail if n != last_name.get(kind)), avail[0])
        last_name[kind] = pick
        times.append(at)
        chosen.append({"_id": f"{PREFIX}{len(chosen)}_{kind}", "id": lib[pick], "at": round(at, 3),
                       "volume": round(min(1.0, vol * level * (0.9 + 0.1 * weight)), 2), "duck": True, "auto": kind})
    chosen.sort(key=lambda s: s["at"])
    return chosen


def apply(effects: dict, library: list[dict], **kw) -> dict:
    """effects with its old auto SFX replaced by a fresh plan (returns a new dict; the input is not mutated)."""
    out = dict(effects)
    kept = [s for s in effects.get("sfx") or [] if not str(s.get("_id", "")).startswith(PREFIX)]
    out["sfx"] = sorted(kept + plan({**effects, "sfx": kept}, library, **kw), key=lambda s: float(s.get("at") or 0))
    return out
