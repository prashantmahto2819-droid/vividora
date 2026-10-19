"""Project workflow: what happens between jobs.

uploading → preparing → transcribing → cutting → review_cuts → rendering
→ review_output → approved        (any step can land in failed)
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from . import db, notify, queue, storage
from .config import settings
from .engine import autocut, autopilot
from .engine.presets import caption_styles, platforms

DEFAULT_EFFECTS = {
    "zoom": {"enabled": False, "strength": 1.0},     # auto punch-in on cuts
    "look": "none",                                   # colour look id, or lut:<library_id>
    "flash": False,                                   # (legacy) white flash at cuts
    "transition": "none",                             # default per-cut transition: none|flash|dip|punch|whip|glitch|flashpunch
    "grade": {},                                      # colour grading sliders (engine/catalog.py GRADE_PARAMS)
    "grade_preset": "",
    "stack": [],                                      # effects stack [{id, params, enabled}] from engine/catalog.py
    "extras": [],                                     # global extras: vignette, grain, sharpen, mirror, letterbox, shake, soft_glow, fade_in
    "music": {"id": "", "volume": 0.18, "duck": True},
    "broll": [],        # [{id, start, end, fit: cover|pip, pos: tl|tr|bl|br}]
    "titles": [],       # [{start, end, text, pos: top|center|bottom, size, color, bg}]
    "watermark": {"id": "", "opacity": 0.75, "size": 0.14, "pos": "tr"},
    "frame": {"id": "", "opacity": 1.0},             # full-frame PNG border/frame from the library
    "body": {"enabled": False, "bg": "blur", "bg_blur": 18, "bg_color": "#111111", "bg_color2": "#F2B33D", "bg_image": "", "bg_video": "",
             "stroke": False, "stroke_color": "#FFFFFF", "stroke_width": 8, "glow": False, "glow_color": "#F2B33D", "glow_size": 24,
             "glow_strength": 1.6, "afterimage": False, "after_decay": 0.9, "clones": 0, "anim": "none", "anim_seconds": 0.9,
             "blink_period": 0.4},
    "sfx": [],          # [{id, at, volume}]
}

DEFAULT_RENDER = {
    "presets": ["yt-long", "yt-short"],
    "caption_style": "karaoke",
    "captions": {"size_scale": 1.0, "position": "", "primary": "", "highlight": "", "font": "", "italic": "", "uppercase": "",
                 "letter_spacing": "", "outline_scale": "", "shadow_scale": "", "outline_color": ""},
    "burn_captions": True,
    "focus_x": 0.5,
    "focus_y": 0.5,
    "hook": {"text": "", "seconds": 3},
    "effects": DEFAULT_EFFECTS,
}


def log(c, workspace_id: str, action: str, *, user_id: str | None = None,
        project_id: str | None = None, detail: dict | None = None) -> None:
    db.insert(c, "activity", {"workspace_id": workspace_id, "user_id": user_id,
                              "project_id": project_id, "action": action,
                              "detail": detail or {}, "created_at": db.now()})


def set_status(c, project_id: str, status: str, note: str | None = None) -> None:
    db.update(c, "projects", project_id, {"status": status, "status_note": note,
                                          "updated_at": db.now()})


def add_asset(c, project_id: str, kind: str, rel_path: str, *, label: str | None = None,
              mime: str | None = None, meta: dict | None = None) -> dict:
    a = {"id": db.new_id(), "project_id": project_id, "kind": kind, "label": label,
         "path": rel_path, "size": storage.file_size(rel_path),
         "mime": mime or storage.guess_mime(rel_path), "meta": meta or {},
         "archived": False, "created_at": db.now()}
    db.insert(c, "assets", a)
    return a


def replace_assets(c, project_id: str, kind: str, label: str | None = None,
                   keep_path: str | None = None) -> None:
    """Drop older files of this kind (e.g. a previous render for the same preset).
    A file at `keep_path` is the one being added — never delete it from disk."""
    q = "SELECT * FROM assets WHERE project_id = ? AND kind = ?"
    args: list[Any] = [project_id, kind]
    if label:
        q += " AND label = ?"
        args.append(label)
    for a in db.rows(c.execute(q, args)):
        if a["path"] != keep_path:
            try:
                storage.abs_path(a["path"]).unlink(missing_ok=True)
            except (ValueError, OSError):
                pass
        c.execute("DELETE FROM assets WHERE id = ?", (a["id"],))


def asset_of(project_id: str, kind: str, label: str | None = None) -> dict | None:
    q = "SELECT * FROM assets WHERE project_id = ? AND kind = ?"
    args: list[Any] = [project_id, kind]
    if label:
        q += " AND label = ?"
        args.append(label)
    return db.row(db.conn().execute(q + " ORDER BY created_at DESC LIMIT 1", args).fetchone())


def start_pipeline(c, project: dict, merge: bool = False) -> dict:
    """Called when the upload finished: inspect, clean audio, make preview.
    merge=True joins the project's clips into one recording first."""
    c.execute("UPDATE jobs SET status='cancelled', finished_at=? WHERE project_id=? AND status='queued'",
              (db.now(), project["id"]))
    db.update(c, "projects", project["id"], {"transcript": None, "edl": None})
    set_status(c, project["id"], "preparing", "clips जोड़े जा रहे हैं" if merge else "फ़ाइल जाँची जा रही है")
    return queue.enqueue(c, project["id"], "prepare", {"merge": merge})


def after_job(c, job: dict, result: dict) -> None:
    """Move the project to its next step once a job reports success."""
    pid = job["project_id"]
    project = db.get("projects", pid)
    if project is None:
        return
    kind = job["kind"]

    if kind == "prepare":
        meta = {**project.get("meta", {}), **result.get("meta", {})}
        if result.get("clips") is not None:
            meta["clips"] = result["clips"]
        db.update(c, "projects", pid, {"meta": meta, "updated_at": db.now()})
        for f in result.get("files", []):
            replace_assets(c, pid, f["kind"], keep_path=f["path"])
            add_asset(c, pid, f["kind"], f["path"], mime=f.get("mime"), meta=f.get("meta"))
        if meta.get("has_audio"):
            set_status(c, pid, "transcribing", "transcript बन रहा है (GPU worker)")
            queue.enqueue(c, pid, "transcribe", {"language": project.get("language", "hi")})
        else:
            # no speech → nothing to cut or caption; go straight to review
            db.update(c, "projects", pid, {"transcript": {"segments": [], "text": ""},
                                           "edl": autocut.build_edl({"segments": []}, meta["duration"]),
                                           "updated_at": db.now()})
            set_status(c, pid, "review_cuts", "कोई आवाज़ नहीं मिली — सीधे render करें")

    elif kind == "transcribe":
        tr = result.get("transcript") or {}
        changes = {"transcript": tr, "updated_at": db.now()}
        if tr.get("language"):
            changes["language"] = tr["language"]  # detected when the project was set to auto
        db.update(c, "projects", pid, changes)
        set_status(c, pid, "cutting", "कट ढूँढे जा रहे हैं")
        queue.enqueue(c, pid, "autocut", {"options": project.get("settings", {}).get("autocut", {})})

    elif kind == "autocut":
        db.update(c, "projects", pid, {"edl": result.get("edl"), "updated_at": db.now()})
        st = result.get("edl", {}).get("stats", {})
        if project.get("settings", {}).get("autopilot"):
            project = db.get("projects", pid)
            ch = db.get("channels", project.get("channel_id") or "") or db.row(c.execute(
                "SELECT * FROM channels WHERE workspace_id = ? ORDER BY created_at LIMIT 1", (project["workspace_id"],)).fetchone())
            ch_settings = (ch or {}).get("settings") or (db.get("workspaces", project["workspace_id"]) or {}).get("settings") or {}
            lib = db.rows(c.execute("SELECT id, kind, name, tags FROM library WHERE workspace_id = ? AND (channel_id IS NULL OR channel_id = ?)",
                                    (project["workspace_id"], (ch or {}).get("id"))))
            opts = autopilot.plan(project, ch_settings, lib)
            ap = opts.pop("autopilot")
            try:
                request_render(c, project, opts)
            except ValueError:
                set_status(c, pid, "review_cuts", "autopilot render नहीं चला — settings जाँचें")
                return
            meta = {**project.get("meta", {}), "autopilot": {**ap, "stage": "render", "shorts_pending": ap["shorts"] > 0}}
            db.update(c, "projects", pid, {"meta": meta})
            if ap["shorts"]:
                queue.enqueue(c, pid, "shorts_plan", {"options": {"count": ap["shorts"]}})
            set_status(c, pid, "rendering", f"autopilot: {st.get('cuts', 0)} कट, captions, zoom, music… render हो रहा")
        else:
            set_status(c, pid, "review_cuts",
                       f"{st.get('cuts', 0)} कट सुझाए, {st.get('removed_seconds', 0)}s हटेंगे — जाँचें")
            notify.on_event("review_cuts", project)

    elif kind == "shorts_plan":
        meta = {**project.get("meta", {}), "shorts": result.get("clips") or []}
        ap = meta.get("autopilot") or {}
        if ap.get("shorts_pending"):
            meta["autopilot"] = {**ap, "shorts_pending": False}
            db.update(c, "projects", pid, {"meta": meta, "updated_at": db.now()})
            clips = [{k: sc.get(k) for k in ("id", "start", "end", "title", "hook")} for sc in meta["shorts"] if sc.get("selected", True)]
            if clips:
                project = db.get("projects", pid)
                try:
                    for cl in clips:
                        payload = {k: v for k, v in {**DEFAULT_RENDER, **project.get("settings", {}).get("render", {})}.items()
                                   if k not in ("presets", "shorts_preset")}
                        payload.update(preset="yt-short", label=f"short-{cl['id']}", clip={"start": float(cl["start"]), "end": float(cl["end"])},
                                       hook={"text": cl.get("hook") or "", "seconds": 3}, title=cl.get("title"))
                        queue.enqueue(c, pid, "render", payload)
                except (ValueError, TypeError):
                    pass
            return
        db.update(c, "projects", pid, {"meta": meta, "updated_at": db.now(),
                                       "status_note": f"{len(meta['shorts'])} Shorts सुझाए — Shorts tab में देखें"})
        notify.on_event("shorts", project, str(len(meta["shorts"])))

    elif kind == "publish":
        pub_id = job["payload"].get("publication_id")
        if pub_id:
            db.update(c, "publications", pub_id, {"status": "done", "remote_id": result.get("remote_id"),
                                                  "url": result.get("url"), "error": result.get("warning"),
                                                  "finished_at": db.now()})
        if result.get("secrets"):  # refreshed OAuth tokens
            conn_id = db.get("publications", pub_id)["connection_id"] if pub_id else None
            if conn_id:
                db.update(c, "connections", conn_id, {"secrets": result["secrets"], "updated_at": db.now()})
        db.update(c, "projects", pid, {"status_note": f"{job['payload'].get('platform')} पर publish हुआ", "updated_at": db.now()})
        notify.on_event("published", project, f"{job['payload'].get('platform')}: {result.get('url') or ''}")

    elif kind == "matte":
        for f in result.get("files", []):
            replace_assets(c, pid, "alpha", keep_path=f["path"])
            add_asset(c, pid, "alpha", f["path"], mime=f.get("mime"), meta=f.get("meta"))
        db.update(c, "projects", pid, {"status_note": "cutout तैयार — Body effects लगाएँ", "updated_at": db.now()})
        # if a render is waiting on the cutout, start it now
        pend = (project.get("meta") or {}).get("render_after_matte")
        if pend:
            meta = {k: v for k, v in project["meta"].items() if k != "render_after_matte"}
            db.update(c, "projects", pid, {"meta": meta})
            try:
                request_render(c, db.get("projects", pid), pend)
            except ValueError:
                pass

    elif kind == "montage":
        for f in result.get("files", []):
            replace_assets(c, pid, f["kind"], f.get("label"), keep_path=f["path"])
            add_asset(c, pid, f["kind"], f["path"], label=f.get("label"), mime=f.get("mime"), meta=f.get("meta"))
        meta = {**project.get("meta", {}), "duration": result.get("duration"), "bpm": result.get("bpm"),
                "segments": result.get("segments")}
        db.update(c, "projects", pid, {"meta": meta, "updated_at": db.now()})
        set_status(c, pid, "review_output", f"montage तैयार · {result.get('bpm')} BPM · {result.get('segments')} cuts")
        notify.on_event("review_output", project, "montage")

    elif kind == "render":
        for f in result.get("files", []):
            replace_assets(c, pid, f["kind"], f.get("label"), keep_path=f["path"])
            add_asset(c, pid, f["kind"], f["path"], label=f.get("label"), mime=f.get("mime"),
                      meta=f.get("meta"))
        # when every render job of this round is finished, ask for review
        pending = c.execute(
            "SELECT COUNT(*) FROM jobs WHERE project_id = ? AND kind IN ('render','shorts_plan') "
            "AND status IN ('queued','running')", (pid,)).fetchone()[0]
        if pending == 0:
            warns = result.get("warnings") or []
            project = db.get("projects", pid)
            if (project.get("meta") or {}).get("autopilot"):
                outs = db.rows(c.execute("SELECT * FROM assets WHERE project_id = ? AND kind = 'render'", (pid,)))
                conns = db.rows(c.execute("SELECT id, platform FROM connections WHERE workspace_id = ? AND (channel_id = ? OR channel_id IS NULL) "
                                          "ORDER BY CASE WHEN channel_id = ? THEN 0 ELSE 1 END", (project["workspace_id"], project.get("channel_id"), project.get("channel_id"))))
                seen = set(); conns = [cn for cn in conns if not (cn["platform"] in seen or seen.add(cn["platform"]))]
                try:
                    pp = autopilot.publish_plan(project, outs, conns)
                except Exception:  # noqa: BLE001 — metadata is a nicety
                    pp = []
                db.update(c, "projects", pid, {"meta": {**project["meta"], "publish_plan": pp,
                                                        "autopilot": {**project["meta"]["autopilot"], "stage": "review"}}})
                set_status(c, pid, "review_output", f"autopilot पूरा: {len(outs)} वीडियो तैयार — देखें, मंज़ूरी दें, publish")
            else:
                set_status(c, pid, "review_output", " · ".join(warns) if warns else "render तैयार — देखें और मंज़ूरी दें")
            notify.on_event("review_output", project, " · ".join(warns))


def fail_job(c, job: dict, error: str) -> None:
    pid = job["project_id"]
    db.update(c, "jobs", job["id"], {"status": "failed", "error": error[:4000],
                                     "finished_at": db.now()})
    if job["kind"] in ("publish", "shorts_plan"):
        # side jobs never take the project out of its editing state
        if job["kind"] == "publish" and job["payload"].get("publication_id"):
            db.update(c, "publications", job["payload"]["publication_id"],
                      {"status": "failed", "error": error[-500:], "finished_at": db.now()})
            notify.on_event("publish_failed", db.get("projects", pid) or {"id": pid}, error.splitlines()[-1][:160] if error else "")
        db.update(c, "projects", pid, {"status_note": f"{job['kind']} असफल: {error.splitlines()[-1][:160] if error else 'error'}",
                                       "updated_at": db.now()})
        return
    set_status(c, pid, "failed", f"{job['kind']}: {error.splitlines()[-1][:200] if error else 'error'}")
    notify.on_event("failed", db.get("projects", pid) or {"id": pid}, f"{job['kind']}: {error.splitlines()[-1][:160] if error else ''}")


def request_render(c, project: dict, settings_in: dict) -> list[dict]:
    """Validate render settings, store them, queue one render job per preset."""
    pid = project["id"]
    opts = {**DEFAULT_RENDER, **project.get("settings", {}).get("render", {}), **settings_in}
    unknown = [p for p in opts["presets"] if p not in platforms()]
    if unknown:
        raise ValueError(f"unknown preset: {', '.join(unknown)}")
    if not opts["presets"]:
        raise ValueError("कम से कम एक platform चुनें")
    if opts["caption_style"] not in caption_styles():
        raise ValueError("unknown caption style")
    new_settings = {**project.get("settings", {}), "render": opts}
    db.update(c, "projects", pid, {"settings": new_settings, "updated_at": db.now()})
    body = (opts.get("effects") or {}).get("body") or {}
    if body.get("enabled") and not asset_of(pid, "alpha"):
        running = c.execute("SELECT COUNT(*) FROM jobs WHERE project_id = ? AND kind = 'matte' AND status IN ('queued','running')", (pid,)).fetchone()[0]
        if not running:
            queue.enqueue(c, pid, "matte", {})
        db.update(c, "projects", pid, {"meta": {**project.get("meta", {}), "render_after_matte": settings_in}})
        set_status(c, pid, "rendering", "पहले cutout बन रहा है (CPU, कुछ मिनट) — फिर render")
        return [{"deferred": "matte"}]
    # cancel renders still waiting from an earlier click
    c.execute("UPDATE jobs SET status='cancelled', finished_at=? WHERE project_id=? "
              "AND kind='render' AND status='queued'", (db.now(), pid))
    set_status(c, pid, "rendering", f"{len(opts['presets'])} वीडियो render हो रहे हैं")
    return [queue.enqueue(c, pid, "render", {"preset": p, **{k: v for k, v in opts.items() if k != 'presets'}})
            for p in opts["presets"]]


def request_shorts_plan(c, project: dict, options: dict | None = None) -> dict:
    if not project.get("transcript") or not project["transcript"].get("segments"):
        raise ValueError("पहले transcript बनने दें")
    db.update(c, "projects", project["id"], {"status_note": "Shorts ढूँढे जा रहे हैं", "updated_at": db.now()})
    return queue.enqueue(c, project["id"], "shorts_plan", {"options": options or {}})


def request_shorts_render(c, project: dict, clips: list[dict], settings_in: dict) -> list[dict]:
    """One render job per chosen Short; outputs are labelled short-<id>."""
    pid = project["id"]
    opts = {**DEFAULT_RENDER, **project.get("settings", {}).get("render", {}), **settings_in}
    preset = opts.get("shorts_preset") or "yt-short"
    if preset not in platforms():
        raise ValueError(f"unknown preset: {preset}")
    if opts["caption_style"] not in caption_styles():
        raise ValueError("unknown caption style")
    good = [cl for cl in clips if float(cl.get("end", 0)) - float(cl.get("start", 0)) >= 3]
    if not good:
        raise ValueError("कम से कम एक Short चुनें")
    meta = {**project.get("meta", {})}
    chosen = {cl["id"]: cl for cl in good}
    meta["shorts"] = [{**sc, **chosen.get(sc["id"], {}), "selected": sc["id"] in chosen} for sc in meta.get("shorts", [])] \
        + [cl for cl in good if cl["id"] not in {sc["id"] for sc in meta.get("shorts", [])}]
    db.update(c, "projects", pid, {"meta": meta, "settings": {**project.get("settings", {}), "render": opts},
                                   "updated_at": db.now()})
    set_status(c, pid, "rendering", f"{len(good)} Shorts render हो रहे हैं")
    jobs = []
    for cl in good:
        payload = {k: v for k, v in opts.items() if k not in ("presets", "shorts_preset")}
        payload.update(preset=preset, label=f"short-{cl['id']}", clip={"start": float(cl["start"]), "end": float(cl["end"])},
                       hook={"text": cl.get("hook") or "", "seconds": 3}, title=cl.get("title"))
        jobs.append(queue.enqueue(c, pid, "render", payload))
    return jobs


def request_montage(c, project: dict, opts: dict) -> dict:
    clips = [cl for cl in (opts.get("clips") or []) if isinstance(cl, dict) and cl.get("id")]
    if not clips:
        raise ValueError("कम से कम एक clip/image चुनें")
    if not opts.get("music"):
        raise ValueError("music चुनें")
    preset = opts.get("preset") or "ig-reel"
    if preset not in platforms():
        raise ValueError("unknown preset")
    payload = {"clips": clips[:60], "music": opts["music"], "texts": [str(t)[:120] for t in (opts.get("texts") or [])][:12],
               "preset": preset, "look": opts.get("look") or "none", "every": max(1, min(8, int(opts.get("every", 2)))),
               "max_seconds": max(5.0, min(180.0, float(opts.get("max_seconds", 30)))), "flash": bool(opts.get("flash", True)),
               "watermark": opts.get("watermark") or None, "font": opts.get("font") or "Poppins",
               "text_color": opts.get("text_color") or "#FFFFFF", "text_size": max(0.03, min(0.14, float(opts.get("text_size", 0.07)))),
               "seed": int(opts.get("seed", 7))}
    db.update(c, "projects", project["id"], {"settings": {**project.get("settings", {}), "montage": payload},
                                             "updated_at": db.now()})
    c.execute("UPDATE jobs SET status='cancelled', finished_at=? WHERE project_id=? AND kind='montage' AND status='queued'",
              (db.now(), project["id"]))
    set_status(c, project["id"], "rendering", "montage बन रहा है")
    return queue.enqueue(c, project["id"], "montage", payload)


def resolve_effects_local(project: dict, effects: dict) -> dict:
    """Same as the worker's _resolve_effects, but with files already on this machine."""
    import copy
    e = copy.deepcopy(effects or {})

    def lib_path(item_id: str | None):
        it = db.get("library", item_id or "")
        if not it:
            return None
        p = storage.abs_path(it["path"])
        return p if p.exists() else None

    look = e.get("look") or "none"
    if isinstance(look, str) and look.startswith("lut:"):
        p = lib_path(look[4:]); e["lut_path"] = str(p) if p else None; e["look"] = "none"
    for key in ("music", "watermark", "frame"):
        d = e.get(key) or {}
        if isinstance(d, dict) and d.get("id"):
            p = lib_path(d["id"]); e[key] = {**d, "path": str(p) if p else None}
    for key in ("broll", "sfx"):
        out = []
        for item in e.get(key) or []:
            if isinstance(item, dict) and item.get("id"):
                p = lib_path(item["id"])
                if p:
                    kind = "image" if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif") else "video"
                    out.append({**item, "path": str(p), "type": item.get("type") or kind})
        e[key] = out
    body = e.get("body") if isinstance(e.get("body"), dict) else None
    if body and body.get("enabled"):
        alpha = asset_of(project["id"], "alpha")
        if alpha and storage.abs_path(alpha["path"]).exists():
            body["alpha_path"] = str(storage.abs_path(alpha["path"]))
            for key in ("bg_image", "bg_video"):
                if body.get(key):
                    p = lib_path(body[key]); body[key + "_path"] = str(p) if p else None
        else:
            body["enabled"] = False
    e["music"] = {}  # no audio in a frame preview
    e["sfx"] = []
    return e


def delete_project(c, project: dict) -> None:
    c.execute("DELETE FROM projects WHERE id = ?", (project["id"],))
    storage.remove_project_files(project["workspace_id"], project["id"])


def archive_raw(c, project: dict) -> int:
    """Move raw + work files of an approved project to the archive drive."""
    if not settings.archive_root:
        return 0
    moved = 0
    for a in db.rows(c.execute(
            "SELECT * FROM assets WHERE project_id = ? AND archived = 0 AND kind IN "
            "('raw','audio_asr','audio_clean')", (project["id"],))):
        src = storage.abs_path(a["path"])
        if not src.exists():
            continue
        dst = settings.archive_root / a["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        db.update(c, "assets", a["id"], {"archived": True})
        moved += 1
    return moved


def project_view(project: dict) -> dict:
    """What the dashboard sees: project + its assets + latest job per kind."""
    cn = db.conn()
    assets = db.rows(cn.execute("SELECT * FROM assets WHERE project_id = ? ORDER BY created_at",
                                (project["id"],)))
    jobs = db.rows(cn.execute("SELECT * FROM jobs WHERE project_id = ? ORDER BY created_at DESC LIMIT 20",
                              (project["id"],)))
    return {**project, "assets": [{k: v for k, v in a.items() if k != "path"} for a in assets],
            "jobs": jobs, "render_defaults": {**DEFAULT_RENDER, **project.get("settings", {}).get("render", {})}}
