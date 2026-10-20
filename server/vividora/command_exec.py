"""Carry out a parsed command (app 🎤, typed, or WhatsApp) on a project. Never publishes on its own."""

from __future__ import annotations

from . import db, service
from .engine import commands


def latest_project(workspace_id: str) -> dict | None:
    return db.row(db.conn().execute("SELECT * FROM projects WHERE workspace_id = ? ORDER BY updated_at DESC LIMIT 1",
                                    (workspace_id,)).fetchone())


def _rs(p: dict) -> dict:
    return {**service.DEFAULT_RENDER, **p.get("settings", {}).get("render", {})}


def _save_rs(c, p: dict, rs: dict) -> None:
    db.update(c, "projects", p["id"], {"settings": {**p.get("settings", {}), "render": rs}, "updated_at": db.now()})


def run(workspace_id: str, user_id: str | None, text: str, project_id: str | None = None, *, via: str = "app") -> dict:
    cmd = commands.parse(text)
    it = cmd.get("intent")
    p = db.get("projects", project_id) if project_id else None
    if p and p["workspace_id"] != workspace_id:
        p = None
    p = p or latest_project(workspace_id)
    name = f"“{p['title']}”" if p else ""
    res = {"intent": it, "parsed": cmd, "project_id": p["id"] if p else None, "changed": False}

    def need_p():
        if not p:
            raise ValueError("कोई project नहीं मिला — पहले recording upload करें")

    busy = p and p["status"] in ("uploading", "preparing", "transcribing", "cutting", "rendering")
    try:
        if it in ("none", "help"):
            res["reply"] = commands.HELP if it == "help" else "समझ नहीं आया 🙏 “help” बोलें/लिखें — क्या-क्या कर सकते हैं।"
        elif it == "status":
            need_p()
            jobs = db.rows(db.conn().execute("SELECT kind, status, progress FROM jobs WHERE project_id = ? AND status IN ('queued','running')", (p["id"],)))
            outs = db.conn().execute("SELECT COUNT(*) FROM assets WHERE project_id = ? AND kind = 'render'", (p["id"],)).fetchone()[0]
            res["reply"] = f"{name}: {p.get('status_note') or p['status']}" + (f" · चल रहा: " + ", ".join(f"{j['kind']} {j['progress']}%" for j in jobs) if jobs else "") + f" · {outs} वीडियो तैयार"
        elif it == "shorts":
            need_p()
            if busy:
                raise ValueError("अभी दूसरा काम चल रहा है — थोड़ी देर बाद")
            n = int(cmd.get("count") or 3)
            meta = p.get("meta") or {}
            with db.tx() as c:
                if meta.get("shorts"):
                    clips = [{k: sc.get(k) for k in ("id", "start", "end", "title", "hook")} for sc in meta["shorts"][:n]]
                    service.request_shorts_render(c, p, clips, {})
                    res["reply"] = f"{name} के {len(clips)} Shorts render हो रहे हैं 🎬"
                else:
                    db.update(c, "projects", p["id"], {"meta": {**meta, "shorts_render_after_plan": n}})
                    service.request_shorts_plan(c, db.get("projects", p["id"]), {"count": n})
                    res["reply"] = f"{name} से {n} Shorts ढूँढे जा रहे हैं, फिर अपने-आप render होंगे 🎬"
            res["changed"] = True
        elif it == "render":
            need_p()
            if busy:
                raise ValueError("अभी दूसरा काम चल रहा है")
            rs = _rs(p)
            if cmd.get("presets"):
                rs["presets"] = cmd["presets"]
            with db.tx() as c:
                service.request_render(c, p, rs)
            res["reply"] = f"{name} render हो रहा है: {', '.join(rs['presets'])} ⏳"
            res["changed"] = True
        elif it == "autopilot":
            need_p()
            plan = service.autopilot_plan(p)
            plan.pop("autopilot", None)
            cur = _rs(p)
            eff = dict(cur.get("effects") or {})
            for key in ("broll", "titles", "sfx"):
                eff[key] = [x for x in (eff.get(key) or []) if not str(x.get("_id", "")).startswith("ap_")] + plan["effects"].get(key, [])
            for k, v in plan["effects"].items():
                if k not in ("broll", "titles", "sfx"):
                    eff[k] = v
            cur.update({k: v for k, v in plan.items() if k != "effects"})
            cur["effects"] = eff
            with db.tx() as c:
                _save_rs(c, p, cur)
            res["reply"] = f"{name} पर autopilot editing लगी ✨ (stickers, highlight text, music, zoom, color, voice) — editor में देखें या “render करो” बोलें"
            res["changed"] = True
        elif it in ("music", "music_off", "captions_on", "captions_off", "zoom_on", "zoom_off", "voice", "hook", "color"):
            need_p()
            rs = _rs(p)
            fx = dict(rs.get("effects") or {})
            if it == "music_off":
                fx["music"] = {**(fx.get("music") or {}), "id": ""}
                msg = "music हटाया"
            elif it == "music":
                mood = cmd.get("mood") or "motivational"
                lib = db.rows(db.conn().execute("SELECT id, name, tags FROM library WHERE workspace_id = ? AND kind = 'music'", (workspace_id,)))
                pick = next((m for m in lib if mood in (m.get("tags") or "") or mood in (m.get("name") or "").lower()), lib[0] if lib else None)
                if not pick:
                    raise ValueError("library में music नहीं है")
                fx["music"] = {**(fx.get("music") or {}), "id": pick["id"], "volume": (fx.get("music") or {}).get("volume", .12), "duck": True}
                msg = f"music लगाया: {pick['name']}"
            elif it in ("captions_on", "captions_off"):
                rs["burn_captions"] = it == "captions_on"
                msg = "captions " + ("चालू" if rs["burn_captions"] else "बंद")
            elif it in ("zoom_on", "zoom_off"):
                fx["zoom"] = {**(fx.get("zoom") or {}), "enabled": it == "zoom_on"}
                msg = "auto zoom " + ("चालू" if it == "zoom_on" else "बंद")
            elif it == "voice":
                fx["voice"] = {"preset": cmd.get("preset") or "studio"}
                msg = f"आवाज़ preset: {fx['voice']['preset']}"
            elif it == "hook":
                if cmd.get("value"):
                    rs["hook"] = {**(rs.get("hook") or {}), "text": cmd["value"], "seconds": 3}
                    msg = f"hook heading: {cmd['value']}"
                else:
                    from .engine import hooks
                    opts = hooks.options(p)
                    if not opts:
                        raise ValueError("hook options नहीं बने")
                    rs["hook"] = {**(rs.get("hook") or {}), "text": opts[0]["heading"], "seconds": 3}
                    msg = "hook heading लगाई: " + opts[0]["heading"] + ("\nदूसरे options: " + " / ".join(o["heading"] for o in opts[1:]) if len(opts) > 1 else "")
            else:  # color
                from .engine import analyze, catalog
                a = (p.get("meta") or {}).get("analysis") or {}
                g = analyze.auto_grade(a)
                base = {k: v for k, v in catalog.GRADE_PRESETS["natural_skin"].items() if k not in ("label", "cat")}
                for k, v in g.items():
                    base[k] = round(float(base.get(k, 0)) + float(v), 3)
                fx["grade"], fx["grade_preset"] = base, "natural_skin"
                msg = "auto color correction लगा"
            rs["effects"] = fx
            with db.tx() as c:
                _save_rs(c, p, rs)
            res["reply"] = f"{name}: {msg} ✅ — “render करो” बोलकर नया वीडियो बनाएँ"
            res["changed"] = True
        elif it == "ideas":
            ideas = db.rows(db.conn().execute("SELECT title, hook FROM ideas WHERE workspace_id = ? AND status = 'new' ORDER BY created_at DESC LIMIT 5", (workspace_id,)))
            res["reply"] = ("ताज़ा ideas:\n" + "\n".join(f"• {i['title']}" + (f" — {i['hook']}" if i.get("hook") else "") for i in ideas)) if ideas else "अभी ideas नहीं — Trends page से radar चलाएँ"
            res["navigate"] = "#/plan"
        elif it == "thumbnail":
            need_p()
            res["reply"] = f"{name} का thumbnail studio खोल रहा हूँ"
            res["navigate"] = f"#/thumbs/{p['id']}"
        elif it == "schedule":
            res["reply"] = "Publish → Calendar में समय देखें; posting slots Settings में।"
            res["navigate"] = "#/publish"
        elif it == "publish":
            res["reply"] = ("Publish हमेशा आपकी मंज़ूरी से: " + (f"WhatsApp पर “ok {p['id'][:4].upper()}” भेजें या dashboard में Approve दबाएँ।" if p else "dashboard में Approve करें।"))
            res["navigate"] = f"#/projects/{p['id']}" if p else "#/publish"
        elif it == "record":
            res["reply"] = "Recorder खोल रहा हूँ 🎥"
            res["navigate"] = "#/record"
        elif it == "new":
            res["reply"] = "नया project खोल रहा हूँ"
            res["navigate"] = "#/new"
        elif it == "open":
            res["reply"] = f"{name} खोल रहा हूँ" if p else "कोई project नहीं"
            res["navigate"] = f"#/projects/{p['id']}" if p else "#/"
        else:
            res["reply"] = "समझ नहीं आया 🙏 “help” बोलें।"
    except ValueError as e:
        res["reply"] = f"⚠️ {e}"
    with db.tx() as c:
        service.log(c, workspace_id, "command", user_id=user_id, project_id=res.get("project_id"),
                    detail={"text": text[:200], "intent": it, "via": via})
    return res
