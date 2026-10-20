"""Autopilot: the whole sequence from upload to "ready for approval", one step at a time.

     1 prepare        file check + voice clean                     (CPU worker job)
     2 transcribe     speech → words                               (GPU worker / TRANSCRIBE_LOCAL)
     3 autocut        pauses / retakes cut                         (CPU worker job)
     4 plan           hook, captions, grade, music, stickers,       (here, instant)
                      highlights, CTA, zoom — engine/autopilot.plan
     5 preflight      platform rules + hook score, auto-fixed       (here, instant)
     6 render         the main video(s)                            (CPU worker jobs)
     7 shorts_plan    best 20–60 s moments                         (CPU worker job)
     8 shorts_render  one render per Short, its own stickers/hook  (CPU worker jobs)
     9 thumbnails     3 A/B thumbnails + a 9:16 cover              (here, background thread)
    10 metadata       titles / descriptions / tags — ONE AI pack call (here, background thread)
    11 publish_plan   which output goes where + posting times      (here, background thread)
        → status review_output + ONE WhatsApp message with the approval code.

Every step starts only after the previous one has really finished: worker steps advance from
service.after_job / fail_job (inside the job's write transaction), the last three run in a
background thread after that transaction commits. meta.autopilot.stage is the step the project
is in; each transition checks it first, so a step never runs twice (a late or repeated "done",
a worker restart, an API restart in the middle — `kick()` picks the sequence up again).
Nothing is ever published here: approval (dashboard or "ok CODE" on WhatsApp) and the Publish
button stay with the owner.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from . import db, notify, queue
from .engine import autopilot as ap_eng

log = logging.getLogger("vividora.autopilot")
FINISH = ("thumbnails", "metadata", "publish_plan")
STATUS_FOR = {"prepare": "preparing", "transcribe": "transcribing", "autocut": "cutting"}
_running: set[str] = set()
_run_lock = threading.Lock()


# ---------------------------------------------------------------- state
def state(project: dict | None) -> dict:
    return dict(((project or {}).get("meta") or {}).get("autopilot") or {})


def active(project: dict | None) -> bool:
    """Autopilot drives this project now (switched on and not finished yet)."""
    return bool(project and (project.get("settings") or {}).get("autopilot")
                and state(project).get("stage") not in (ap_eng.READY, "review"))  # "review" = finished, older versions


def _save_state(c, pid: str, **changes: Any) -> dict:
    p = db.get("projects", pid) or {}
    meta = dict(p.get("meta") or {})
    st = {**(meta.get("autopilot") or {}), **changes}
    meta["autopilot"] = st
    db.update(c, "projects", pid, {"meta": meta, "updated_at": db.now()})
    return st


def enter(c, pid: str, stage: str, detail: str = "", status: str | None = None) -> None:
    """Move to `stage` and say so: status_note "n/11 · …", meta.autopilot.{stage, step, total, percent}."""
    n, total = ap_eng.step_no(stage), len(ap_eng.STEPS)
    p = db.get("projects", pid) or {}
    hist = list(state(p).get("history") or [])
    if not hist or hist[-1].get("stage") != stage:
        hist.append({"stage": stage, "at": db.now()})
    _save_state(c, pid, stage=stage, step=n, total=total, label=dict(ap_eng.STEPS).get(stage, stage),
                percent=round((n - 1) * 100 / total), history=hist[-30:], failed=None)
    db.update(c, "projects", pid, {"status": status or STATUS_FOR.get(stage, "rendering"),
                                   "status_note": ap_eng.step_note(stage, detail), "updated_at": db.now()})


def note(c, pid: str, stage: str, detail: str) -> None:
    """Progress inside a step (e.g. "2/3 Shorts तैयार") without changing the step."""
    db.update(c, "projects", pid, {"status_note": ap_eng.step_note(stage, detail), "updated_at": db.now()})


def fail(c, pid: str, stage: str, what: str, action: str | None = None) -> None:
    """Stop the sequence: status failed, the note says what failed and the one thing to do. One WhatsApp message."""
    p = db.get("projects", pid) or {"id": pid}
    already = p.get("status") == "failed"
    c.execute("UPDATE jobs SET status='cancelled', finished_at=? WHERE project_id=? AND status='queued' AND kind != 'publish'",
              (db.now(), pid))
    _save_state(c, pid, failed=stage)
    txt = ap_eng.fail_note(stage, what, action or ap_eng.FAIL_ACTION.get(stage, "“Autopilot फिर चलाएँ” दबाएँ"))
    db.update(c, "projects", pid, {"status": "failed", "status_note": txt, "updated_at": db.now()})
    if not already:
        notify.on_event("failed", p, txt)


def warn(c, pid: str, text: str) -> None:
    st = state(db.get("projects", pid))
    _save_state(c, pid, warnings=[*(st.get("warnings") or []), text][-12:])


# ---------------------------------------------------------------- steps 1–3
def begin(c, project: dict) -> None:
    """A new recording arrived: a fresh autopilot round."""
    hist = [{"stage": "prepare", "at": db.now()}]
    meta = {**(project.get("meta") or {})}
    meta.pop("publish_plan", None)
    meta["autopilot"] = {"stage": "prepare", "step": 1, "total": len(ap_eng.STEPS), "label": ap_eng.STEPS[0][1],
                         "percent": 0, "history": hist, "warnings": [], "round": db.new_id()[:8]}
    db.update(c, "projects", project["id"], {"meta": meta})


def no_speech(c, project: dict) -> None:
    """No audio track: nothing to transcribe or cut — edit and render straight away."""
    warn(c, project["id"], "वीडियो में आवाज़ नहीं — captions/कट नहीं")
    plan_and_render(c, db.get("projects", project["id"]))


# ---------------------------------------------------------------- steps 4–6
def channel_and_library(project: dict, c=None) -> tuple[dict, list[dict]]:
    """The project's channel settings (brand kit, switches, niche) and the library autopilot may use:
    the channel's own items + workspace-wide ones + the starter pack, only files that really exist."""
    from . import storage
    c = c or db.conn()
    ch = db.get("channels", project.get("channel_id") or "") or db.row(c.execute(
        "SELECT * FROM channels WHERE workspace_id = ? ORDER BY created_at LIMIT 1", (project["workspace_id"],)).fetchone())
    ch_settings = {**((ch or {}).get("settings") or (db.get("workspaces", project["workspace_id"]) or {}).get("settings") or {}),
                   "niche": (ch or {}).get("niche") or ""}
    rows = db.rows(c.execute("SELECT id, kind, name, tags, path FROM library WHERE workspace_id = ? "
                             "AND (channel_id IS NULL OR channel_id = ? OR source = 'starter')",
                             (project["workspace_id"], (ch or {}).get("id"))))
    lib = []
    for r in rows:
        try:
            if storage.abs_path(r["path"]).exists():
                lib.append({k: r[k] for k in ("id", "kind", "name", "tags")})
        except (ValueError, OSError):
            pass
    return ch_settings, lib


def plan_and_render(c, project: dict) -> None:
    from . import service
    from .engine import hooks
    pid = project["id"]
    enter(c, pid, "plan")
    try:
        ch_settings, lib = channel_and_library(project, c)
        opts = ap_eng.plan(project, ch_settings, lib)
        missing = [k for k in ("music", "sticker", "sfx") if not any(x["kind"] == k for x in lib)]
        if missing:
            warn(c, pid, f"library में {', '.join(missing)} नहीं — उनके बिना edit (Library → starter pack लगाएँ)")
        enter(c, pid, "preflight")
        opts, fixes = ap_eng.preflight_fix(project, opts, hooks.options(project, 3, ai=False))
    except Exception as e:  # noqa: BLE001 — a planning bug must not leave the project hanging
        log.exception("autopilot plan failed for %s", pid)
        fail(c, pid, "plan", f"{type(e).__name__}: {e}", "editor में settings देखकर खुद render करें")
        return
    apm = opts.pop("autopilot")
    try:
        jobs = service.request_render(c, project, opts)
    except ValueError as e:
        fail(c, pid, "render", str(e), "editor में platform/caption चुनकर render करें")
        return
    _save_state(c, pid, shorts=int(apm.get("shorts") or 0), switches=apm.get("switches"), preflight=fixes,
                hook_score=apm.get("hook_score"), main=list(opts["presets"]))
    st = ((project.get("edl") or {}).get("stats") or {})
    detail = f"{len(jobs)} वीडियो ({', '.join(opts['presets'])}) · {st.get('cuts', 0)} कट"
    if fixes:
        detail += " · " + "; ".join(fixes)[:160]
    enter(c, pid, "render", detail)


def _pending(c, pid: str, kind: str = "render") -> int:
    return c.execute("SELECT COUNT(*) FROM jobs WHERE project_id = ? AND kind = ? AND status IN ('queued','running')",
                     (pid, kind)).fetchone()[0]


def _outputs(c, pid: str) -> list[dict]:
    return db.rows(c.execute("SELECT * FROM assets WHERE project_id = ? AND kind = 'render' ORDER BY created_at", (pid,)))


def on_render_finished(c, pid: str, warnings: list[str] | None = None) -> bool:
    """A render job of an autopilot project ended (done or failed). Returns True when handled here."""
    p = db.get("projects", pid)
    if not active(p):
        return False
    stage = state(p).get("stage")
    for w in warnings or []:
        warn(c, pid, w)
    if stage not in ("render", "shorts_render"):
        return stage not in (None, ap_eng.READY)  # a render outside the sequence: leave the status alone
    left = _pending(c, pid)
    # only outputs made in this round count (a re-run must not pass on an old file)
    since = next((h["at"] for h in reversed(state(p).get("history") or []) if h.get("stage") == "render"), "")
    outs = [o for o in _outputs(c, pid) if (o.get("created_at") or "") >= since]
    if stage == "render":
        main = state(p).get("main") or []
        if left:
            note(c, pid, "render", f"{len([o for o in outs if o['label'] in main])}/{len(main)} तैयार")
            return True
        if not any(o["label"] in main for o in outs):
            err = c.execute("SELECT error FROM jobs WHERE project_id = ? AND kind = 'render' AND status = 'failed' "
                            "ORDER BY finished_at DESC LIMIT 1", (pid,)).fetchone()
            fail(c, pid, "render", ((err[0] if err else "") or "कोई वीडियो नहीं बना").strip().splitlines()[-1][:160])
            return True
        failed_main = [m for m in main if m not in {o["label"] for o in outs}]
        if failed_main:
            warn(c, pid, f"{', '.join(failed_main)} render नहीं हुआ")
        start_shorts(c, db.get("projects", pid))
        return True
    # shorts_render
    want = state(p).get("shorts_labels") or []
    done = [o for o in outs if o["label"] in want]
    if left:
        note(c, pid, "shorts_render", f"{len(done)}/{len(want)} Shorts तैयार")
        return True
    if len(done) < len(want):
        warn(c, pid, f"{len(want) - len(done)} Shorts render नहीं हुए")
    start_finish(c, pid)
    return True


# ---------------------------------------------------------------- steps 7–8
def start_shorts(c, project: dict) -> None:
    pid = project["id"]
    st = state(project)
    n = int(st.get("shorts") or 0)
    if n <= 0:
        main = st.get("main") or []
        why = "वीडियो खुद Short/Reel है — अलग Shorts नहीं" if main and all(m in ap_eng.VERTICAL for m in main) \
            else "Shorts बंद (autopilot settings में 0)"
        start_finish(c, pid, why)
        return
    if not ((project.get("transcript") or {}).get("segments")):
        warn(c, pid, "बोले शब्द नहीं मिले — Shorts नहीं बने")
        start_finish(c, pid)
        return
    enter(c, pid, "shorts_plan", f"{n} Shorts ढूँढ रहे हैं")
    if not _pending(c, pid, "shorts_plan"):
        queue.enqueue(c, pid, "shorts_plan", {"options": {"count": n}, "autopilot": True})


def on_shorts_plan(c, pid: str, clips: list[dict] | None, error: str | None = None) -> bool:
    """Shorts plan finished (or failed) → one render per Short with its own stickers / hook / CTA."""
    from . import service
    p = db.get("projects", pid)
    if not active(p) or state(p).get("stage") != "shorts_plan":
        return False
    if error is not None:
        warn(c, pid, f"Shorts plan असफल: {error[:120]}")
        start_finish(c, pid)
        return True
    good = [cl for cl in (clips or []) if cl.get("selected", True) and float(cl["end"]) - float(cl["start"]) >= 5]
    if not good:
        warn(c, pid, "अच्छा Short नहीं मिला")
        start_finish(c, pid)
        return True
    ch_settings, lib = channel_and_library(p, c)
    base = {**service.DEFAULT_RENDER, **(p.get("settings") or {}).get("render", {})}
    fonts = [r[0] for r in c.execute("SELECT id FROM library WHERE workspace_id = ? AND kind = 'font'", (p["workspace_id"],))]
    labels = []
    for cl in good:
        try:
            sp = ap_eng.plan(p, ch_settings, lib, clip=cl)
            sp.pop("autopilot", None)
            sp, _ = ap_eng.preflight_fix({**p, "edl": ap_eng.clip_edl(p, cl)}, {**sp, "autopilot": {"switches": state(p).get("switches")}})
            sp.pop("autopilot", None)
        except Exception as e:  # noqa: BLE001
            log.warning("short plan %s failed: %s", cl.get("id"), e)
            sp = {k: v for k, v in base.items() if k not in ("presets", "shorts_preset")}
        payload = {**{k: v for k, v in sp.items() if k not in ("presets", "shorts_preset")}, "fonts": fonts}
        payload.update(preset=base.get("shorts_preset") or "yt-short", label=f"short-{cl['id']}",
                       clip={"start": float(cl["start"]), "end": float(cl["end"])}, title=cl.get("title"))
        # the Short's own effects travel in the job; the project's render settings stay those of the main video
        queue.enqueue(c, pid, "render", payload)
        labels.append(f"short-{cl['id']}")
    _save_state(c, pid, shorts_labels=labels)
    enter(c, pid, "shorts_render", f"0/{len(labels)} Shorts")
    return True


# ---------------------------------------------------------------- steps 9–11 (background, after commit)
def start_finish(c, pid: str, detail: str = "") -> None:
    enter(c, pid, "thumbnails", detail)
    _spawn(pid, wait_for="thumbnails")


def _spawn(pid: str, wait_for: str | None = None) -> None:
    with _run_lock:
        if pid in _running:
            return
        _running.add(pid)
    threading.Thread(target=_finish_thread, args=(pid, wait_for), name=f"autopilot-{pid[:8]}", daemon=True).start()


def _finish_thread(pid: str, wait_for: str | None) -> None:
    try:
        # the stage was written inside the job's transaction: wait until that has committed
        for _ in range(240):
            p = db.get("projects", pid)
            if p is None:
                return
            if state(p).get("stage") in FINISH and (wait_for is None or state(p).get("stage") == wait_for):
                break
            time.sleep(0.25)
        else:
            return
        finish(pid)
    except Exception as e:  # noqa: BLE001
        log.exception("autopilot finish failed for %s", pid)
        try:
            with db.tx() as c:
                fail(c, pid, state(db.get("projects", pid)).get("stage") or "thumbnails", f"{type(e).__name__}: {e}")
        except Exception:  # noqa: BLE001
            pass
    finally:
        with _run_lock:
            _running.discard(pid)


def _still(pid: str, stage: str) -> dict | None:
    p = db.get("projects", pid)
    return p if p and active(p) and state(p).get("stage") == stage and p.get("status") != "failed" else None


def finish(pid: str) -> None:
    """Steps 9–11, each only if the project is still at that step (resumable after a restart)."""
    from . import service, thumbs
    from .engine import aipack, llm
    p = db.get("projects", pid)
    stage = state(p).get("stage")
    if stage == "thumbnails" and _still(pid, "thumbnails"):
        made = 0
        try:
            thumbs._autopilot_now(pid)
            made = db.conn().execute("SELECT COUNT(*) FROM assets WHERE project_id = ? AND kind = 'thumbnail'", (pid,)).fetchone()[0]
        except Exception as e:  # noqa: BLE001 — a thumbnail problem never blocks the videos
            log.warning("autopilot thumbnails failed for %s: %s", pid, e)
        with db.tx() as c:
            if not _still(pid, "thumbnails"):
                return
            if not made:
                warn(c, pid, "thumbnail नहीं बना — Thumbnail tab से बनाएँ")
            _save_state(c, pid, thumbnails=made)
            enter(c, pid, "metadata", "AI से title/description" if llm.available() else "transcript से title/description (AI key नहीं)")
        stage = "metadata"
    if stage == "metadata" and _still(pid, "metadata"):
        p = db.get("projects", pid)
        pack = None
        if llm.available() and (p.get("transcript") or {}).get("segments"):
            pack = aipack.get(p)  # the ONE AI call (thumbnail texts may already have made it — then it is reused)
        drafts = {}
        if pack:
            p = {**p, "meta": {**(p.get("meta") or {}), "aipack": pack}}
        for o in _outputs(db.conn(), pid):
            try:
                d = ap_eng.draft(p, o.get("label") or "")
            except Exception as e:  # noqa: BLE001
                log.warning("draft %s failed: %s", o.get("label"), e)
                d = None
            if d:
                drafts[o["label"]] = d
        with db.tx() as c:
            if not _still(pid, "metadata"):
                return
            if pack:
                cur = db.get("projects", pid)
                db.update(c, "projects", pid, {"meta": {**(cur.get("meta") or {}), "aipack": pack}})
            elif llm.available():
                warn(c, pid, "AI जवाब नहीं दे रहा — title/description transcript से बने")
            _save_state(c, pid, drafts=drafts, ai=bool(pack))
            enter(c, pid, "publish_plan")
        stage = "publish_plan"
    if stage == "publish_plan" and _still(pid, "publish_plan"):
        p = db.get("projects", pid)
        outs = _outputs(db.conn(), pid)
        conns = db.rows(db.conn().execute(
            "SELECT id, platform FROM connections WHERE workspace_id = ? AND (channel_id = ? OR channel_id IS NULL) "
            "ORDER BY CASE WHEN channel_id = ? THEN 0 ELSE 1 END", (p["workspace_id"], p.get("channel_id"), p.get("channel_id"))))
        seen: set = set()
        conns = [cn for cn in conns if not (cn["platform"] in seen or seen.add(cn["platform"]))]
        pp: list[dict] = []
        try:
            pp = ap_eng.publish_plan(p, outs, conns)
            pp = service.schedule_plan(p, pp)
        except Exception as e:  # noqa: BLE001
            log.warning("publish plan failed for %s: %s", pid, e)
        with db.tx() as c:
            if not _still(pid, "publish_plan"):
                return
            cur = db.get("projects", pid)
            db.update(c, "projects", pid, {"meta": {**(cur.get("meta") or {}), "publish_plan": pp}})
            if not conns:
                warn(c, pid, "कोई platform जुड़ा नहीं — Settings → Connections (drafts तैयार हैं)")
            ready(c, pid)


def ready(c, pid: str) -> None:
    """Done: review_output + one WhatsApp message with the approval code."""
    p = db.get("projects", pid)
    st = state(p)
    outs = _outputs(c, pid)
    n_short = len([o for o in outs if (o.get("label") or "").startswith("short-")])
    n_main = len(outs) - n_short
    pp = (p.get("meta") or {}).get("publish_plan") or []
    first = min((it["when"] for it in pp if it.get("when") and it.get("selected", True)), default=None)
    parts = [f"{n_main} वीडियो"] + ([f"{n_short} Shorts"] if n_short else []) + \
            ([f"{st.get('thumbnails')} thumbnails"] if st.get("thumbnails") else []) + \
            ([f"{len(pp)} posts का plan"] if pp else [])
    warns = st.get("warnings") or []
    hist = [*(st.get("history") or []), {"stage": ap_eng.READY, "at": db.now()}]
    _save_state(c, pid, stage=ap_eng.READY, step=len(ap_eng.STEPS), percent=100, history=hist[-30:],
                label="मंज़ूरी के लिए तैयार", first_post=first)
    txt = f"✅ autopilot पूरा: {', '.join(parts)} — देखें और मंज़ूरी दें (code {notify.code_for(pid)})"
    if warns:
        txt += " · ⚠ " + "; ".join(warns[:3])
    db.update(c, "projects", pid, {"status": "review_output", "status_note": txt[:480], "updated_at": db.now()})
    if st.get("notified") != st.get("round"):
        _save_state(c, pid, notified=st.get("round"))
        notify.on_event("autopilot_ready", p, " · ".join(parts) + (f"\nपहली post: {_local(first)}" if first else "")
                        + (f"\n⚠ {warns[0]}" if warns else ""))


def _local(iso: str | None) -> str:
    from datetime import datetime, timedelta, timezone
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=5, minutes=30)))
        return t.strftime("%d %b %H:%M")
    except (TypeError, ValueError):
        return str(iso or "")


def refresh_plan_assets(c, pid: str) -> None:
    """A re-render replaced an output (new asset id): point the publish plan at the new file."""
    p = db.get("projects", pid)
    pp = (p.get("meta") or {}).get("publish_plan") or []
    if not pp:
        return
    by_label = {o["label"]: o["id"] for o in _outputs(c, pid)}
    changed = False
    for it in pp:
        new = by_label.get(it.get("label"))
        if new and new != it.get("asset_id"):
            it["asset_id"] = new
            changed = True
    if changed:
        db.update(c, "projects", pid, {"meta": {**(p.get("meta") or {}), "publish_plan": pp}})


# ---------------------------------------------------------------- failures, resume, watchdog
def on_job_failed(c, job: dict, error: str) -> bool:
    """Called by service.fail_job for autopilot projects. True = handled (project state set here)."""
    pid = job["project_id"]
    p = db.get("projects", pid)
    if not active(p):
        return False
    last = (error or "error").strip().splitlines()[-1][:160]
    kind = job["kind"]
    if kind == "render":
        return on_render_finished(c, pid, [f"render असफल ({(job.get('payload') or {}).get('label') or (job.get('payload') or {}).get('preset')}): {last}"])
    if kind == "shorts_plan":
        return on_shorts_plan(c, pid, None, error=last)
    if kind in ("prepare", "transcribe", "autocut"):
        fail(c, pid, kind, last)
        return True
    return False


def resume(c, project: dict) -> str:
    """“Autopilot फिर चलाएँ”: continue from the step that failed / stalled. Returns the step started."""
    from . import service
    pid = project["id"]
    st = state(project)
    stage = st.get("failed") or st.get("stage") or "prepare"
    if stage == ap_eng.READY:
        stage = "plan"
    c.execute("UPDATE jobs SET status='cancelled', finished_at=? WHERE project_id=? AND status='queued' AND kind != 'publish'",
              (db.now(), pid))
    if not (project.get("settings") or {}).get("autopilot"):
        db.update(c, "projects", pid, {"settings": {**(project.get("settings") or {}), "autopilot": True}})
    _save_state(c, pid, round=db.new_id()[:8], warnings=[], failed=None)
    meta = project.get("meta") or {}
    if stage == "prepare" or not meta.get("duration"):
        service.start_pipeline(c, db.get("projects", pid))
        return "prepare"
    if (stage == "transcribe" or not project.get("transcript")) and meta.get("has_audio"):
        enter(c, pid, "transcribe")
        queue.enqueue(c, pid, "transcribe", service.transcribe_payload(project))
        return "transcribe"
    if stage == "autocut" or not project.get("edl"):
        enter(c, pid, "autocut")
        queue.enqueue(c, pid, "autocut", {"options": (project.get("settings") or {}).get("autocut", {})})
        return "autocut"
    if stage in ("plan", "preflight", "render"):
        plan_and_render(c, db.get("projects", pid))
        return "render"
    if stage in ("shorts_plan", "shorts_render"):
        start_shorts(c, db.get("projects", pid))
        return "shorts_plan"
    start_finish(c, pid)
    return "thumbnails"


def kick() -> None:
    """Watchdog (every minute + at start): finish steps lost to an API restart, wake a step whose
    jobs are all gone, and say so when no worker can take a waiting job."""
    rows = db.rows(db.conn().execute(
        "SELECT * FROM projects WHERE status IN ('preparing','transcribing','cutting','rendering') "
        "AND json_extract(settings, '$.autopilot') = 1"))
    for p in rows:
        st = state(p)
        stage = st.get("stage")
        pid = p["id"]
        try:
            if stage in FINISH:
                _spawn(pid)
                continue
            jobs = db.rows(db.conn().execute("SELECT kind, status, created_at FROM jobs WHERE project_id = ? AND status IN ('queued','running')", (pid,)))
            if stage in ("render", "shorts_render") and not jobs:
                with db.tx() as c:
                    on_render_finished(c, pid)
                continue
            if stage == "shorts_plan" and not jobs:
                with db.tx() as c:
                    start_finish(c, pid, "Shorts plan खो गया")
                continue
            waiting = [j for j in jobs if j["status"] == "queued"]
            if waiting and not any(j["status"] == "running" for j in jobs):
                kind = waiting[0]["kind"]
                from datetime import datetime, timedelta, timezone
                cutoff = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat(timespec="seconds")
                online = db.conn().execute("SELECT kinds FROM workers WHERE last_seen_at > ?", (cutoff,)).fetchall()
                if not any(kind in (r[0] or "") for r in online) and waiting[0]["created_at"] < cutoff:
                    who = "transcribe worker (GPU PC)" if kind == "transcribe" else "CPU worker"
                    msg = f"{who} online नहीं — उसे चालू करें, काम अपने-आप आगे बढ़ेगा"
                    if msg not in (p.get("status_note") or ""):
                        with db.tx() as c:
                            note(c, pid, stage or kind, msg)
        except Exception as e:  # noqa: BLE001
            log.warning("autopilot kick %s: %s", pid, e)
