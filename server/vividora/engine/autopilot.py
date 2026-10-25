"""Autopilot: upload → finished videos + Shorts + titles, with no clicks in
between. Every decision is a plain rule (or the workspace's learned
defaults), written into the project's settings so the editor shows exactly
what was chosen and the creator can change anything before approving.
"""

from __future__ import annotations

import random
import re

from . import analyze, autoedit, metadata, shorts
from .catalog import GRADE_PRESETS

HOOK_MAX_WORDS = 8

# The autopilot sequence. Each step starts only after the previous one has really finished
# (service.after_job / autopilot_flow move the project along); meta.autopilot.stage holds the key,
# and status_note always reads "<n>/<total> · <what is happening>" so the dashboard can show progress.
STEPS = [
    ("prepare", "फ़ाइल जाँच + आवाज़ साफ़"),
    ("transcribe", "बोले गए शब्द लिखे जा रहे हैं"),
    ("autocut", "कट ढूँढ रहे हैं"),
    ("plan", "edit plan: hook, captions, color, music, stickers"),
    ("preflight", "platform नियम जाँच + अपने-आप सुधार"),
    ("render", "मुख्य वीडियो render"),
    ("shorts_plan", "Shorts चुने जा रहे हैं"),
    ("shorts_render", "Shorts render"),
    ("thumbnails", "thumbnails बन रहे हैं"),
    ("metadata", "title, description, tags (AI)"),
    ("publish_plan", "publish plan + समय तय"),
]
STEP_KEYS = [k for k, _ in STEPS]
READY = "ready"


def step_no(key: str) -> int:
    return STEP_KEYS.index(key) + 1 if key in STEP_KEYS else len(STEPS)


def step_note(key: str, detail: str = "") -> str:
    """'3/11 · कट ढूँढ रहे हैं — detail' (the progress line the dashboard shows)."""
    label = dict(STEPS).get(key, key)
    return f"{step_no(key)}/{len(STEPS)} · {label}" + (f" — {detail}" if detail else "")


def fail_note(key: str, what: str, action: str) -> str:
    """What failed + the one thing to do about it."""
    return f"✖ {step_no(key)}/{len(STEPS)} · {dict(STEPS).get(key, key)} असफल: {what[:140]} → {action}"


# what the owner should do when a step fails (one action each)
FAIL_ACTION = {
    "prepare": "फ़ाइल ठीक से upload हुई है? दोबारा upload करें",
    "transcribe": "transcribe worker (GPU PC या TRANSCRIBE_LOCAL=1) चालू करें, फिर “Autopilot फिर चलाएँ”",
    "autocut": "“Autopilot फिर चलाएँ” दबाएँ",
    "render": "worker का log देखें, फिर “Autopilot फिर चलाएँ”",
    "shorts_plan": "Shorts tab से हाथ से Shorts चुनें",
    "shorts_render": "Shorts tab से दोबारा render करें",
}


def _first_hook(project: dict) -> str:
    """A short on-screen line from the strongest early sentence."""
    tr = project.get("transcript") or {}
    sents = shorts._sentences(tr)
    if not sents:
        return ""
    head = sents[:6]
    best = max(head, key=shorts._score)
    words = best["text"].split()
    cut = words[:HOOK_MAX_WORDS]
    if len(words) > HOOK_MAX_WORDS:  # cut mid-sentence: don't end on "का / की / से / सबसे…"
        while len(cut) > 3 and cut[-1].strip(" ,।.!?").lower() in DANGLING:
            cut = cut[:-1]
    line = " ".join(cut).strip(" ।.,!?")
    return line if len(line) >= 8 else ""


DANGLING = {"का", "की", "के", "कि", "और", "से", "में", "को", "पर", "एक", "सबसे", "जो", "या", "तो", "भी", "ही", "बहुत",
            "the", "a", "an", "of", "to", "and", "that", "your", "my", "is", "for", "in"}


def _grade_with_correction(preset: dict, analysis: dict) -> dict:
    """Brand look + the measured correction for this recording (dark room, cold light…)."""
    g = {k: v for k, v in (preset or {}).items() if k not in ("label", "cat") and not k.startswith("_")}
    for k, v in analyze.auto_grade(analysis).items():
        g[k] = round(max(-1.0, min(1.0, float(g.get(k, 0)) + float(v))), 3)
    return g


# What autopilot does — each switch can be turned off per channel (brand kit → Autopilot)
AUTOPILOT_DEFAULTS = {"captions": True, "hook": True, "music": True, "cta": True, "zoom": True, "transitions": True,
                      "keyword_stickers": True, "highlights": True, "sfx": True, "auto_color": True, "voice": True,
                      "logo": True, "lower_thirds": True, "auto_broll": True, "shorts": 3}
AUTOPILOT_LABELS = {"captions": "Captions (बोले हुए शब्द)", "hook": "शुरू में Hook heading", "music": "Background music",
                    "cta": "Subscribe / Follow popup", "zoom": "Auto zoom in/out", "transitions": "Transitions (Shorts)",
                    "keyword_stickers": "शब्दों पर emoji sticker (पैसा → 💰)", "highlights": "ज़रूरी lines पर बड़ा text",
                    "sfx": "Sound effects (pop, whoosh)", "auto_color": "Auto color correction", "voice": "Voice enhance + noise हटाना",
                    "logo": "Logo / watermark", "lower_thirds": "Speaker name plate (शुरू में नाम पट्टी)",
                    "auto_broll": "Auto B-roll (transcript से matching images)", "shorts": "लंबी video से कितने Shorts"}


def settings_for(brand: dict, channel_switches: dict | None = None) -> dict:
    """The channel's autopilot switches: brand.autopilot (Settings → Autopilot), with the older
    channel-level `autopilot` dict (PATCH /channels) underneath."""
    ap = dict(AUTOPILOT_DEFAULTS)
    merged = {**(channel_switches or {}), **((brand or {}).get("autopilot") or {})}
    for k, v in merged.items():
        if k not in ap:
            continue
        if k == "shorts":
            try:
                ap[k] = max(0, min(10, int(v)))
            except (TypeError, ValueError):
                pass
        else:
            ap[k] = v in (True, 1, "1", "true", "on", "yes")
    return ap


def clip_edl(project: dict, clip: dict) -> dict:
    """The project's cuts + everything outside [start, end] cut away: the output timeline of a Short."""
    dur = float((project.get("meta") or {}).get("duration") or 0)
    edl = project.get("edl") or {}
    cs, ce = max(0.0, float(clip["start"])), min(dur, float(clip["end"])) if dur else float(clip["end"])
    cuts = [c for c in (edl.get("cuts") or []) if c.get("enabled", True)]
    cuts = cuts + [{"start": 0.0, "end": cs, "reason": "short", "enabled": True},
                   {"start": ce, "end": max(ce, dur), "reason": "short", "enabled": True}]
    from .autocut import keep_segments
    kept = sum(b - a for a, b in keep_segments({"duration": dur, "cuts": cuts}))
    return {**edl, "duration": dur, "cuts": cuts, "stats": {**(edl.get("stats") or {}), "removed_seconds": round(dur - kept, 3)}}


def plan(project: dict, workspace_settings: dict, library: list[dict], clip: dict | None = None) -> dict:
    """Render settings for this recording. Pure function: no I/O.
    clip={start, end, hook}: settings for one Short cut from it (stickers / text / CTA timed on the Short)."""
    learned = (workspace_settings or {}).get("render_defaults", {}) or {}
    rec = (workspace_settings or {}).get("recommend", {}) or {}
    brand = (workspace_settings or {}).get("brand", {}) or {}
    if clip:
        project = {**project, "edl": clip_edl(project, clip)}
    duration = float(project.get("meta", {}).get("duration") or 0)
    analysis = (project.get("meta") or {}).get("analysis") or {}
    removed0 = float(((project.get("edl") or {}).get("stats") or {}).get("removed_seconds") or 0)
    # short source = what is LEFT after the cuts fits a Reel/Short (a 90 s take with 30 s of pauses is a Short)
    is_short_source = bool(clip) or (duration - removed0) <= 75
    lang = project.get("language") or "hi"
    ap = settings_for(brand, (workspace_settings or {}).get("autopilot"))

    caption_style = learned.get("caption_style") or brand.get("caption_style") or ("hormozi" if is_short_source else "karaoke")
    hook = str(clip.get("hook") or "") if clip else _first_hook(project)
    music = ""
    niche = " ".join([str(workspace_settings.get("niche") or ""), str(brand.get("music_mood") or "")]).lower()
    mood = next((m for m in ("motivational", "emotional", "news", "lofi", "upbeat", "cinematic", "story", "energetic") if m in niche), None)
    if not mood:
        mood = "news" if "news" in niche else "motivational"
    musics = [m for m in library if m.get("kind") == "music"]
    bg = [m for m in musics if mood in (m.get("tags") or "") or mood in (m.get("name") or "").lower()] or musics
    if bg and brand.get("music", True) and ap["music"]:
        music = random.Random(project["id"]).choice(bg)["id"]
    stickers = [m for m in library if m.get("kind") == "sticker"]
    sfx = {(m.get("name") or "").lower(): m["id"] for m in library if m.get("kind") == "sfx"}

    def find(names: list[str]) -> str:
        for n in names:
            for m in stickers:
                nm = (m.get("name") or "").lower()
                if n in nm and not any(x in nm for x in ("hindi", "subscribed", "हिंदी")):
                    return m["id"]
        return ""
    logo = (brand.get("logo_id") or next((l["id"] for l in library if l.get("kind") == "logo"), "")) if ap["logo"] else ""
    grade_preset = brand.get("grade_preset") or "natural_skin"
    effects = {
        "zoom": {"enabled": rec.get("zoom", "on") != "off" and ap["zoom"], "strength": 0.9},
        "look": learned.get("effects", {}).get("look", "none") if isinstance(learned.get("effects"), dict) else "none",
        "transition": "punch" if is_short_source else "none",
        "extras": [],
        "grade": _grade_with_correction(GRADE_PRESETS.get(grade_preset, {}), analysis if ap["auto_color"] else {}),
        "grade_preset": grade_preset,
        "stack": [],
        "music": {"id": music, "volume": 0.12, "duck": True, "duck_amount": 0.6, "fade": 1.5},
        "voice": analyze.auto_voice(analysis, brand.get("voice_preset") or "studio") if ap["voice"] else {"preset": "off", "denoise": "off"},
        "broll": [], "broll_layout": "behind",  # Smart B-roll: नया B-roll इंसान के पीछे (behind mode)
        "titles": [], "sfx": [],
        "watermark": {"id": logo, "opacity": 0.7, "size": 0.12, "pos": "tr"},
    }
    # CTA popup + SFX (output timeline ≈ source minus cuts; place relative to the end)
    out_dur = duration - float(((project.get("edl") or {}).get("stats") or {}).get("removed_seconds") or 0)
    # Call-to-action popups — English text on every platform, and the right ask per platform:
    # Subscribe on YouTube, Follow on Instagram / Facebook (each item only renders on its platform).
    ctas = [("youtube", ["subscribe red", "subscribe"]), ("instagram", ["follow insta", "follow"]),
            ("facebook", ["follow facebook", "follow insta", "follow"])]
    cta_at = None
    if out_dur > 8 and brand.get("cta_popup", True) and ap["cta"]:
        at = max(2.0, out_dur * (0.72 if not is_short_source else 0.82))
        cta_at = at
        added = False
        for fam, names in ctas:
            sid = find(names)
            if not sid:
                continue
            effects["broll"].append({"_id": f"ap_cta_{fam}", "id": sid, "start": round(at, 2), "end": round(min(out_dur, at + 2.8), 2),
                                     "fit": "free", "x": 0.5, "y": 0.6, "scale": 0.6, "opacity": 1, "rotate": 0, "anim": "pop",
                                     "platforms": [fam]})
            added = True
        if added and sfx.get("pop") and ap["sfx"]:
            effects["sfx"].append({"_id": "ap_pop", "id": sfx["pop"], "at": round(at, 2), "volume": 0.7})
    if not ap["hook"]:
        hook = ""
    if hook and sfx.get("whoosh") and ap["sfx"]:
        effects["sfx"].append({"_id": "ap_whoosh", "id": sfx["whoosh"], "at": 0.0, "volume": 0.6})
    if not is_short_source and out_dur > 40 and brand.get("cta_popup", True) and ap["cta"]:
        bell = find(["like sub bell"])
        if bell:
            effects["broll"].append({"_id": "ap_bell", "id": bell, "start": 6.0, "end": 9.0, "fit": "free", "x": 0.5, "y": 0.62,
                                     "scale": 0.7, "opacity": 1, "rotate": 0, "anim": "slide_up", "platforms": ["youtube"]})
    pc = analyze.pace(project)
    fast = pc["wpm"] >= 150
    effects["zoom"]["mode"] = "punch" if is_short_source else ("emphasis" if fast else "push")
    if is_short_source and ap["transitions"]:
        effects["transition"] = "punch" if not fast else "whip"
    elif not ap["transitions"]:
        effects["transition"] = "none"
    # what is said → stickers and highlight text
    avoid = [(cta_at, cta_at + 2.8)] if cta_at is not None else []
    if ap["keyword_stickers"]:
        kb, ks = autoedit.keyword_stickers(project, library, out_dur=out_dur, every=6.0 if is_short_source else 9.0,
                                           avoid=avoid, sfx_on=ap["sfx"])
        effects["broll"].extend(kb)
        effects["sfx"].extend(ks)
    if ap["highlights"]:
        effects["titles"].extend(autoedit.highlight_titles(project, out_dur=out_dur, avoid=avoid,
                                                            style=(brand.get("title_style") or None)))
    # Lower thirds: auto-add speaker name plate near the start (brand name + tagline or channel niche)
    if ap.get("lower_thirds") and not clip:
        speaker_name = brand.get("name") or brand.get("speaker_name") or ""
        speaker_title = brand.get("tagline") or brand.get("speaker_title") or (workspace_settings or {}).get("niche") or ""
        if speaker_name:
            lt_text = f"{speaker_name}|{speaker_title}" if speaker_title else speaker_name
            # pick a lower_third style: use brand preference or default lt_modern
            lt_style = brand.get("lower_third_style") or "lt_modern"
            # place at 3-5 seconds (after hook settles), show for 3 seconds
            lt_start = 3.0 if is_short_source else 4.0
            lt_end = lt_start + 3.0
            if lt_end < out_dur - 1:
                effects["titles"].append({
                    "_id": "ap_lower_third", "text": lt_text, "style": lt_style,
                    "start": round(lt_start, 2), "end": round(lt_end, 2),
                    "pos": "bottom_left", "anim_in": "slide_right", "anim_out": "slide_left_out",
                })
    # Auto B-roll: search library for clips matching transcript keywords and place them on the timeline
    if ap.get("auto_broll") and not clip:
        broll_clips = [m for m in library if m.get("kind") in ("video", "broll")]
        if broll_clips:
            tr = project.get("transcript") or {}
            segments = tr.get("segments") or []
            # gather unique topic words from transcript
            topic_words: set[str] = set()
            for seg in segments:
                for w in seg.get("words") or []:
                    word = str(w.get("w") or w.get("word") or "").strip().lower()
                    if len(word) >= 4:
                        topic_words.add(word)
            # match library items by name/tags against topic words
            placed = 0
            last_broll = -999.0
            broll_interval = 15.0 if is_short_source else 25.0  # how often to place B-roll
            for bc in broll_clips:
                if placed >= (3 if is_short_source else 5):
                    break
                bc_name = (bc.get("name") or "").lower()
                bc_tags = (bc.get("tags") or "").lower()
                bc_text = bc_name + " " + bc_tags
                # check if any topic word matches this B-roll
                matched = any(tw in bc_text for tw in topic_words) if topic_words else False
                if not matched and placed > 0:
                    continue  # first one can be random, rest must match
                # find a good placement time: after the hook, spread across the video
                place_at = max(6.0, last_broll + broll_interval)
                if place_at >= out_dur - 4:
                    break
                bc_dur = min(float(bc.get("duration") or 5), 5.0, out_dur - place_at - 1)
                if bc_dur < 2:
                    break
                # avoid overlapping with CTA
                if any(a - 1 <= place_at <= b + 1 for a, b in avoid):
                    place_at = max(place_at, avoid[0][1] + 1.5) if avoid else place_at
                    if place_at >= out_dur - 4:
                        break
                effects["broll"].append({
                    "_id": f"ap_broll_{placed}", "id": bc["id"],
                    "start": round(place_at, 2), "end": round(place_at + bc_dur, 2),
                    "fit": "cover", "opacity": 1, "anim": "fade",
                })
                last_broll = place_at
                placed += 1
    if not is_short_source and out_dur > 90:
        effects["extras"] = ["soft_glow"] if (analysis.get("video") or {}).get("contrast", 0.2) < 0.15 else []
    # Smart Layout: autopilot B-roll clips (not stickers/CTAs) default to "behind" mode
    # so the person stays visible with B-roll as background replacement
    default_layout = effects.pop("broll_layout", "behind")
    for b in effects["broll"]:
        if b.get("fit") != "free" and not b.get("layout"):
            b["layout"] = default_layout
    presets = (["yt-short"] if clip else ["yt-short", "ig-reel", "fb-reel"]) if is_short_source else ["yt-long"]
    return {
        "presets": presets,
        "caption_style": caption_style,
        "captions": {"size_scale": 1.0, "position": "", "primary": brand.get("primary", ""), "highlight": brand.get("highlight", ""),
                     "font": brand.get("font", ""), "italic": "", "uppercase": "", "letter_spacing": "", "outline_scale": "",
                     "shadow_scale": "", "outline_color": ""},
        "burn_captions": ap["captions"],
        "focus_x": 0.5, "focus_y": 0.5,
        "hook": {"text": hook, "seconds": 3},
        "effects": effects,
        "face_track": "auto",
        "shorts_preset": "yt-short",
        "autopilot": {"shorts": 0 if is_short_source else ap["shorts"], "language": lang, "switches": ap},
    }


def publish_plan(project: dict, outputs: list[dict], connections: list[dict]) -> list[dict]:
    """Which output goes where, with drafted metadata. Only platforms that are connected
    (drafts() has the same texts for every output, connected or not).
    Each Short keeps its own title (the Shorts step wrote one per clip) — never 3 Shorts with one title."""
    by_platform = {c["platform"]: c for c in connections}
    plan = []
    used: set[tuple[str, str]] = set()
    for a in outputs:
        d = draft(project, a.get("label") or "")
        if not d or d["platform"] not in by_platform:
            continue
        n = 2
        base = d["title"]
        while (d["platform"], d["title"]) in used:  # two Shorts must never go out with the same title
            d["title"] = re.sub(r"(\s*#Shorts)?$", f" · भाग {n}\\1", base, count=1)[:100]
            n += 1
        used.add((d["platform"], d["title"]))
        plan.append({"asset_id": a["id"], **d, "connection_id": by_platform[d["platform"]]["id"],
                     "privacy": "public" if d["platform"] == "youtube" else None, "selected": True})
    return plan


ROUTE = {"yt-long": "youtube", "yt-short": "youtube", "ig-reel": "instagram", "fb-reel": "facebook"}


def draft(project: dict, label: str) -> dict | None:
    """Title / description / tags for one output, within the platform's limits."""
    platform = "youtube" if label.startswith("short-") else ROUTE.get(label)
    if not platform:
        return None
    md = metadata.suggest(project, platform=platform, label=label)
    title = md["title"]
    sc = next((s for s in (project.get("meta") or {}).get("shorts") or [] if f"short-{s.get('id')}" == label), None)
    if sc and str(sc.get("title") or "").strip():
        title = str(sc["title"]).strip()
    if label.startswith("short-") or label == "yt-short":
        title = re.sub(r"\s*#shorts\b", " ", title, flags=re.I).strip()[:90] + " #Shorts"
    return {"label": label, "platform": platform, "title": title[:100],
            "description": _cap_hashtags(md["description"], title, platform), "tags": md["tags"], "source": md.get("source")}


def _cap_hashtags(desc: str, title: str, platform: str) -> str:
    """Hashtags in title + description within the platform cap (YouTube shows 3, Instagram allows 5)."""
    cap = metadata.HASHTAG_CAP.get(platform, 5) - len(re.findall(r"#[\wऀ-ॿ]+", title))
    seen = 0

    def keep(mt):
        nonlocal seen
        seen += 1
        return mt.group(0) if seen <= max(0, cap) else ""
    out = re.sub(r"#[\wऀ-ॿ]+", keep, desc or "")
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"[ \t]{2,}", " ", out)).strip()


HOOK_MIN_SCORE = 50
VERTICAL = ("yt-short", "ig-reel", "fb-reel")


def preflight_fix(project: dict, opts: dict, hook_options: list[dict] | None = None) -> tuple[dict, list[str]]:
    """Run the platform pre-flight (platform_rules.check) + hook score on autopilot's settings and apply
    every fix that needs no human: drop formats the video is too long for (the Shorts step makes the
    vertical versions instead), put a hook on screen when there is none or the opening scores low, keep
    text / stickers inside the vertical safe zones. Returns (fixed opts, Hindi notes of what changed)."""
    import copy

    from . import hooks, platform_rules
    o = copy.deepcopy(opts)
    fx = o.setdefault("effects", {})
    apm = o.setdefault("autopilot", {})
    sw = apm.get("switches") or AUTOPILOT_DEFAULTS
    notes: list[str] = []
    # 1) duration limits → never push a 10-minute Reel
    m = project.get("meta") or {}
    out_dur = float(m.get("duration") or 0) - float(((project.get("edl") or {}).get("stats") or {}).get("removed_seconds") or 0)
    keep, dropped = [], []
    for pr in o.get("presets") or []:
        r = platform_rules.RULES.get(pr) or {}
        (dropped if r.get("max") and out_dur > r["max"] else keep).append(pr)
    if dropped:
        keep = keep or ["yt-long"]
        notes.append(f"{', '.join(dropped)} हटाया ({out_dur:.0f}s लंबा) — Shorts अलग से कटेंगे")
        if not apm.get("shorts") and sw.get("shorts"):
            apm["shorts"] = sw["shorts"]
    o["presets"] = keep
    # 2) hook: on screen in the first second, and a better line when the opening is weak
    plat = "long" if o["presets"] == ["yt-long"] else "short"
    if sw.get("hook", True):
        sc = hooks.score(project, o, plat)
        cur = (o.get("hook") or {}).get("text") or ""
        best = next((str(h.get("heading")) for h in (hook_options or []) if h.get("heading")), "")
        if best and best != cur and (not cur or sc["score"] < HOOK_MIN_SCORE):
            o["hook"] = {**(o.get("hook") or {}), "text": best[:60], "seconds": (o.get("hook") or {}).get("seconds", 3)}
            notes.append(f"hook score {sc['score']} → बेहतर hook “{best[:40]}”" if cur else f"hook जोड़ा: “{best[:40]}”")
    apm["hook_score"] = hooks.score(project, o, plat)["score"]
    # 3) safe zones on vertical formats: text and stickers away from the app's buttons / caption bar
    if any(p in VERTICAL for p in o["presets"]):
        z = {k: max(platform_rules.SAFE[p][k] for p in o["presets"] if p in VERTICAL) for k in ("top", "bottom", "right")}
        moved = 0
        for t in fx.get("titles") or []:
            if t.get("pos") == "free":
                y = float(t.get("y", .5))
                ny = min(max(y, z["top"] + .03), 1 - z["bottom"] - .03)
                if abs(ny - y) > 1e-6:
                    t["y"] = round(ny, 3)
                    moved += 1
            elif t.get("pos") == "bottom":
                t["pos"] = "center"
                moved += 1
        for b in fx.get("broll") or []:
            if b.get("fit") == "free" and float(b.get("x", .5)) > 1 - z["right"]:
                b["x"] = round(1 - z["right"] - .05, 3)
                moved += 1
        if moved:
            notes.append(f"{moved} text/sticker safe zone में खिसकाए")
    # 4) whatever the pre-flight still blocks goes into the note for the owner
    for f in platform_rules.check(project, o, o["presets"]):
        if f["level"] == "block":
            notes.append("⚠ " + f["msg"])
    apm["preflight"] = notes
    return o, notes
