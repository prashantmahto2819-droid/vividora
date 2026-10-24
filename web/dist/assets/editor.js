// Vividora editor — CapCut-style layout: side tools, preview, inspector, multi-track timeline.
// Plain JS module; mounted by app.js for projects whose transcript/cuts exist.
//
// Two clocks: the proxy video plays SOURCE time; titles / B-roll / SFX are stored in
// OUTPUT time (after cuts) because that is what the renderer needs. outOf()/srcOf() map
// between them so the timeline can show everything on one ruler.

let E = null;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const ICON = {
  media: '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 15l5-5 4 4 3-3 6 6"/></svg>',
  cuts: '<svg viewBox="0 0 24 24"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M8.5 7.5L20 19M8.5 16.5L20 5"/></svg>',
  captions: '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 15h6M7 11h10"/></svg>',
  text: '<svg viewBox="0 0 24 24"><path d="M5 6h14M12 6v13M9 19h6"/></svg>',
  effects: '<svg viewBox="0 0 24 24"><path d="M12 3l2 5 5 2-5 2-2 5-2-5-5-2 5-2zM19 15l1 2 2 1-2 1-1 2-1-2-2-1 2-1z"/></svg>',
  audio: '<svg viewBox="0 0 24 24"><path d="M9 18V6l10-2v12"/><circle cx="6" cy="18" r="3"/><circle cx="16" cy="16" r="3"/></svg>',
  overlay: '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="12" height="12" rx="2"/><rect x="9" y="9" width="12" height="12" rx="2"/></svg>',
  montage: '<svg viewBox="0 0 24 24"><path d="M4 18V8M9 18V4M14 18v-8M19 18v-5"/><path d="M3 21h18"/></svg>',
  body: '<svg viewBox="0 0 24 24"><circle cx="12" cy="7" r="4"/><path d="M4 21c0-4 4-7 8-7s8 3 8 7"/><path d="M2 12l2-2M22 12l-2-2" stroke-dasharray="2 2"/></svg>',
  color: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 010 18c-2.5 0-3-2-1.5-3.5S13 15 11 13s-4-3-2.5-5S12 3 12 3z"/></svg>',
  undo: '<svg viewBox="0 0 24 24"><path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 010 10h-3"/></svg>',
  redo: '<svg viewBox="0 0 24 24"><path d="M15 14l5-5-5-5"/><path d="M20 9H9a5 5 0 000 10h3"/></svg>',
  refs: '<svg viewBox="0 0 24 24"><path d="M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1"/></svg>',
  shorts: '<svg viewBox="0 0 24 24"><rect x="7" y="2" width="10" height="20" rx="2"/><path d="M10 9l5 3-5 3z" fill="currentColor" stroke="none"/></svg>',
  export: '<svg viewBox="0 0 24 24"><path d="M12 16V4M6 10l6-6 6 6M4 20h16"/></svg>',
  play: '<svg viewBox="0 0 24 24"><path d="M7 4l12 8-12 8z" fill="currentColor" stroke="none"/></svg>',
  pause: '<svg viewBox="0 0 24 24"><rect x="6" y="4" width="4" height="16" fill="currentColor" stroke="none"/><rect x="14" y="4" width="4" height="16" fill="currentColor" stroke="none"/></svg>',
  prev: '<svg viewBox="0 0 24 24"><path d="M18 5v14L8 12zM6 5v14"/></svg>',
  next: '<svg viewBox="0 0 24 24"><path d="M6 5v14l10-7zM18 5v14"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>',
  back: '<svg viewBox="0 0 24 24"><path d="M15 5l-7 7 7 7"/></svg>',
  stickers: '<svg viewBox="0 0 24 24"><path d="M5 3h10l4 4v10a4 4 0 01-4 4H7a4 4 0 01-4-4V5a2 2 0 012-2z"/><path d="M15 3v4h4M8 13c1 1.5 2.3 2 4 2s3-.5 4-2M9 9h.01M15 9h.01"/></svg>',
  transitions: '<svg viewBox="0 0 24 24"><rect x="2" y="6" width="9" height="12" rx="1"/><rect x="13" y="6" width="9" height="12" rx="1"/><path d="M9 12h6M13 9l2 3-2 3"/></svg>',
  ai: '<svg viewBox="0 0 24 24"><path d="M12 3l1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg>',
  plus: '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>',
  pro: '<svg viewBox="0 0 24 24"><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/></svg>',
};
import * as TFX from "./textfx.js";
import * as CUT from "./cutout.js";
import * as PRO from "./pro.js";
const TABS_ALL = [["cuts", "कट"], ["media", "Media"], ["audio", "Audio"], ["text", "Text"], ["stickers", "Stickers"], ["effects", "Effects"], ["transitions", "Transitions"], ["color", "Filters"], ["pro", "Pro"], ["captions", "Captions"], ["body", "Cutout"], ["overlay", "Overlay"], ["shorts", "Shorts"], ["ai", "AI Studio"], ["refs", "Refs"]];
const TABS_MONTAGE = [["montage", "Montage"], ["media", "Media"], ["audio", "Audio"], ["overlay", "Overlay"], ["refs", "Refs"]];
let TABS = TABS_ALL;
const TITLE_PRESETS = [
  { id: "headline", label: "Headline", pos: "top", size: 0.08, color: "#FFFFFF", bg: "", text: "यहाँ बड़ा टाइटल" },
  { id: "lower3", label: "Lower third", pos: "bottom", size: 0.05, color: "#FFFFFF", bg: "#000000", text: "नाम | पहचान" },
  { id: "center", label: "Center punch", pos: "center", size: 0.11, color: "#FFD400", bg: "", text: "एक लाइन" },
  { id: "note", label: "Note box", pos: "top", size: 0.055, color: "#111111", bg: "#FFD400", text: "ध्यान दें" },
];
const LOOK_CSS = { none: "", warm: "sepia(.15) saturate(1.1)", cinematic: "contrast(1.1) saturate(.9) brightness(.97)", vivid: "saturate(1.35) contrast(1.05)",
  soft: "contrast(.95) saturate(.95) blur(.3px)", bw: "grayscale(1) contrast(1.12)", cool: "hue-rotate(-8deg) saturate(1.02)", vintage: "sepia(.35) contrast(.95)" };
const LIB_KINDS = [["music", "Music"], ["sfx", "SFX"], ["broll", "B-roll"], ["image", "Image"], ["sticker", "Sticker"], ["logo", "Logo"], ["frame", "Frame"], ["lut", "LUT"]];
const uid = () => Math.random().toString(36).slice(2, 10);

// ---------- mount / state ----------
export function mount(root, project, ctx) {
  if (E && E.pid === project.id && root.contains(E.root)) { update(project); return; }
  unmount();
  const rs = JSON.parse(JSON.stringify(project.render_defaults || {}));
  rs.effects = { zoom: { enabled: false, strength: 1 }, look: "none", flash: false, transition: "none", extras: [], grade: {}, grade_preset: "", stack: [], frame: { id: "", opacity: 1 },
    body: { enabled: false, bg: "blur", bg_blur: 18, bg_color: "#111111", bg_color2: "#F2B33D", bg_image: "", bg_video: "", stroke: false, stroke_color: "#FFFFFF", stroke_width: 8, glow: false, glow_color: "#F2B33D", glow_size: 24, glow_strength: 1.6, afterimage: false, after_decay: 0.9, clones: 0, anim: "none", anim_seconds: 0.9, blink_period: 0.4 }, music: { id: "", volume: 0.18, duck: true },
    broll: [], titles: [], watermark: { id: "", opacity: 0.75, size: 0.14, pos: "tr" }, sfx: [], ...(rs.effects || {}) };
  if (rs.effects.flash && (!rs.effects.transition || rs.effects.transition === "none")) rs.effects.transition = "flash";
  rs.captions = { size_scale: 1, position: "", primary: "", highlight: "", font: "", italic: "", uppercase: "", letter_spacing: "", outline_scale: "", shadow_scale: "", outline_color: "", ...(rs.captions || {}) };
  rs.hook = { text: "", seconds: 3, ...(rs.hook || {}) };
  rs.effects.voice = { preset: "studio", ...(rs.effects.voice || {}) };
  rs.effects.music = { id: "", volume: 0.18, duck: true, duck_amount: 0.6, fade: 1.5, ...(rs.effects.music || {}) };
  rs.effects.fxclips = Array.isArray(rs.effects.fxclips) ? rs.effects.fxclips : [];
  // every timeline item needs its own id (autopilot may have written the same id twice → select/delete hit the wrong one)
  const seenIds = new Set();
  for (const k of ["titles", "broll", "sfx", "fxclips"]) for (const x of rs.effects[k]) { if (!x._id || seenIds.has(x._id)) x._id = (String(x._id || "").startsWith("ap_") ? "ap_" : "") + uid(); seenIds.add(x._id); }
  E = { pid: project.id, p: project, ctx, root: null, rs, cuts: JSON.parse(JSON.stringify(project.edl?.cuts || [])),
    tr: JSON.parse(JSON.stringify(project.transcript || { segments: [] })), trSrv: JSON.stringify(project.transcript?.segments || []), words: [],
    splits: [...(project.edl?.splits || [])], ver: 0, savedVer: 0, jobSeen: new Map((project.jobs || []).map((j) => [j.id, j.status])), capSel: new Set(),
    tab: "cuts", sel: null, pps: 40, t: 0, markIn: null, markOut: null, skipCuts: true, ratio: "9:16", dirty: false, saveT: null,
    lib: null, libKind: "music", exportOpen: false, drag: null, raf: null, canEdit: ctx.S.user.role !== "viewer" };
  E.shorts = JSON.parse(JSON.stringify(project.meta?.shorts || []));
  E.montage = project.kind === "montage";
  TABS = E.montage ? TABS_MONTAGE : TABS_ALL;
  if (E.montage) { E.tab = "montage"; E.mo = { mode: "auto", pace: "auto", effects_level: "auto", reframe: "smart", slowmo: true, clips: [], music: "", texts: "", preset: "ig-reel", look: "none", every: 2, max_seconds: 30, flash: true, watermark: "", font: "Poppins", text_color: "#FFFFFF", text_size: 0.07, ...(project.settings?.montage || {}) }; if (Array.isArray(E.mo.texts)) E.mo.texts = E.mo.texts.join("\n"); const sp = E.mo.plan; E.moSig = sp ? `${sp.music_start}|${(sp.segments || []).length}|${sp.total}|${sp.bpm}` : ""; }
  E.speed = JSON.parse(JSON.stringify(project.edl?.speed || []));
  E.tr.segments = E.tr.segments || []; syncWords();
  E.locked = isLocked(project); if (E.locked) E.canEdit = false;
  E.hist = []; E.redo = [];
  E.dur = project.edl?.duration || project.meta?.duration || 1;
  E.pps = clamp(Math.floor(900 / E.dur), 6, 120);
  E.rs.markers = Array.isArray(E.rs.markers) ? E.rs.markers : [];
  if (!E.rs.effects.pro || typeof E.rs.effects.pro !== "object") E.rs.effects.pro = {};
  PRO.host({ get E() { return E; }, touch, select, selItem, renderInspector, renderTimeline, renderOverlay, renderPanel, renderJobs, layoutFrame, applyVideoCss, seek, outOf, srcOf, outDur, keeps, cutAt, libItem, fxDef, fxParams,
    stackCss, gradeCss, scaledGrade, flush, track, field, num, fmt, ICON, brollCutoutBox, follow: CUT.follow,
    rerender: () => { renderInspector(); if (E.tab === "pro") { const pn = $("#ed-panel", E.root); const sc = pn.scrollTop; renderPanel(); pn.scrollTop = sc; } } });
  try { if (localStorage.getItem("vividora_debug") === "1") window.VV = { get E() { return E; }, PRO, touch, renderAll, select, seek, flush }; } catch { /* storage blocked */ }
  root.innerHTML = skeleton();
  E.root = root.firstElementChild;
  bindStatic();
  renderAll();
  loadLib(); loadRefs();
}
export function unmount() {
  if (!E) return;
  // leaving the editor (route change, reload after recut…): don't drop edits still waiting for the debounce
  if (E.dirty && E.canEdit && !E.locked) { clearTimeout(E.saveT); doSave(E, false); }
  document.removeEventListener("keydown", onKey);
  window.removeEventListener("resize", layoutFrame);
  cancelAnimationFrame(E.raf); cutTeardown();
  clearTimeout(E.saveT); clearTimeout(E.pubT);
  E = null;
}
function update(project) {
  const was = E.p.status;
  E.p = project;
  if (project.edl?.duration) E.dur = project.edl.duration;
  const finished = trackJobs(project);
  // transcript changed on the server (re-listen of a line, full re-transcribe) → bring it in without losing local edits
  const srv = JSON.stringify(project.transcript?.segments || []);
  E.pendRanges = [...(E.pendRanges || []), ...finished.filter((j) => j.kind === "transcribe" && j.status === "done" && jobRange(j)).map(jobRange)];
  if (srv !== E.trSrv && !E.saving) {
    const ranges = E.pendRanges; E.pendRanges = [];
    if (ranges.length && E.transcriptDirty) mergeTranscript(project.transcript, ranges);
    else if (!E.transcriptDirty || finished.some((j) => j.kind === "transcribe" && j.status === "done" && !jobRange(j))) { E.tr = JSON.parse(JSON.stringify(project.transcript || { segments: [] })); E.tr.segments = E.tr.segments || []; E.transcriptDirty = false; }
    E.trSrv = srv; syncWords(); if (E.tab === "captions") renderPanel(); renderTimeline(); renderOverlay();
  }
  // a new cut list from the server (auto-cut after a re-transcribe) replaces the local one
  if (finished.some((j) => j.kind === "autocut" && j.status === "done") && project.edl) {
    E.cuts = JSON.parse(JSON.stringify(project.edl.cuts || [])); E.speed = JSON.parse(JSON.stringify(project.edl.speed || E.speed)); E.last = snapshot(); renderTimeline(); if (E.tab === "cuts") renderPanel();
  }
  const lockedNow = isLocked(project);
  if (lockedNow !== !!E.locked) { E.locked = lockedNow; E.canEdit = !lockedNow && E.ctx.S.user.role !== "viewer"; E.root.classList.toggle("ed-locked", lockedNow); renderPanel(); renderInspector(); }
  else {
    // a line started / stopped being re-listened → lock or unlock it in the list, timeline and inspector
    const rsig = activeJobs(project).map(jobRange).filter(Boolean).map((r) => `${r.start}-${r.end}`).join(",");
    if (rsig !== (E.rangeSig || "") || finished.length) { E.rangeSig = rsig; if (E.tab === "captions") { const pn = $("#ed-panel", E.root); const sc = pn.scrollTop; renderPanel(); pn.scrollTop = sc; } renderTimeline(); if (E.sel?.type === "caption") renderInspector(); }
  }
  if (E.montage) { const sp = project.settings?.montage?.plan; const sig = sp ? `${sp.music_start}|${(sp.segments || []).length}|${sp.total}|${sp.bpm}` : ""; if (sig !== E.moSig) { E.moSig = sig; if (sp && !E.moDirty) E.mo.plan = sp; } }
  if (E.montage) { const r = project.assets.find((a) => a.kind === "render"); const v = $("#pv", E.root); if (r && v && !v.src.includes(r.id)) { v.src = r.url; E.dur = project.meta?.duration || E.dur; renderTimeline(); } if (E.tab === "montage") renderPanel(); }
  const fresh = JSON.stringify(project.meta?.shorts || []);
  if (fresh !== E.shortsSeen) { E.shortsSeen = fresh; if (!E.shortsDirty) { E.shorts = JSON.parse(fresh); if (E.tab === "shorts") renderPanel(); renderTimeline(); } }
  // a cutout finished (main video or a library clip) → the live preview / overlay picks it up
  if (finished.some((j) => j.kind === "matte_lib" && j.status === "done")) loadLib();
  if (!E.montage) { cutSync(); const st = $("#bd-status", E.root); if (st) { const h2 = bodyStatus(); if (st._h !== h2) { st._h = h2; st.innerHTML = h2; bindBodyStatus(st); } } }
  if (E.sel?.type === "broll" && activeJobs(project).concat(finished).some((j) => j.kind === "matte_lib")) renderInspector();
  renderTop();
  if (E.exportOpen) renderExport();
  if (was !== project.status && project.status === "review_output") { E.exportOpen = true; renderExport(); }
}

// ---------- jobs (progress card + finish/fail toasts) ----------
const JOB_LABEL = { transcribe: "Transcript", autocut: "कट ढूँढना", render: "Render", shorts_plan: "Shorts ढूँढना", montage: "Montage", montage_plan: "Beat plan",
  matte: "Cutout", matte_lib: "Cutout (B-roll)", dub: "AI आवाज़", publish: "Publish", prepare: "तैयारी", thumbnail: "Thumbnail", autopilot: "Autopilot" };
function jobLabel(j) {
  if (jobRange(j)) return `Line दोबारा सुन रहे (${fmt(jobRange(j).start)}–${fmt(jobRange(j).end)})`;
  if (j.kind === "render" && j.payload?.label?.startsWith("short-")) return "Short render";
  if (j.kind === "render" && j.payload?.preset) return `Render · ${(E.ctx.S.presets?.platforms || []).find((p) => p.id === j.payload.preset)?.label || j.payload.preset}`;
  return JOB_LABEL[j.kind] || j.kind;
}
const activeJobs = (p) => (p.jobs || []).filter((j) => ["queued", "running"].includes(j.status));
// a full re-transcribe / auto-cut rewrites transcript + cuts: editing meanwhile would be overwritten
function isLocked(p) { return ["transcribing", "cutting", "preparing"].includes(p.status) || activeJobs(p).some((j) => (j.kind === "transcribe" && !jobRange(j)) || j.kind === "autocut" || j.kind === "prepare"); }
function plainError(err) {
  const last = String(err || "").trim().split("\n").filter(Boolean).pop() || "";
  if (/memory|killed|oom/i.test(last)) return "मशीन की memory कम पड़ गई";
  if (/no such file|not found|404/i.test(last)) return "ज़रूरी file नहीं मिली";
  if (/timeout|timed out/i.test(last)) return "बहुत देर लगी (timeout)";
  if (/ffmpeg/i.test(last)) return "video बनाते समय ffmpeg रुक गया";
  return last.replace(/^\w+(Error|Exception):\s*/, "").slice(0, 140) || "पता नहीं चला क्यों";
}
function trackJobs(p) {
  const done = [];
  for (const j of p.jobs || []) {
    const prev = E.jobSeen.get(j.id);
    // every job that existed when the editor opened is in jobSeen → an unknown one was started (and maybe finished) since
    if ((prev === undefined || (prev !== j.status && ["queued", "running"].includes(prev))) && ["done", "failed"].includes(j.status)) {
      if (j.status === "done") { done.push(j); E.ctx.toast(`✅ ${jobLabel(j)} पूरा हुआ`, 3200); }
      else if (j.status === "failed") { done.push(j); E.ctx.toast(`⚠ ${jobLabel(j)} असफल — ${plainError(j.error)}`, 6000); }
    }
    E.jobSeen.set(j.id, j.status);
  }
  return done;
}
// what a running job says about itself: queue place, attempt number, ETA from the worker's message
function jobSub(j) {
  if (j.status === "queued") return j.queue_pos ? `कतार में ${j.queue_pos}/${Math.max(j.queue_len || 0, j.queue_pos)}` : "queue में";
  const parts = [];
  if ((+j.attempts || 0) > 1) parts.push(`कोशिश ${j.attempts}/3`);
  parts.push((j.message || E.p.status_note || "").slice(0, 60));
  return parts.filter(Boolean).join(" · ");
}
function jobsPref() { try { return JSON.parse(localStorage.getItem("vividora_jobs_ui") || "{}"); } catch { return {}; } }
function saveJobsPref(p) { try { localStorage.setItem("vividora_jobs_ui", JSON.stringify({ ...jobsPref(), ...p })); } catch { /* private mode */ } }
function renderJobs() {
  const el = $("#ed-jobs", E.root); if (!el) return; const { esc } = E.ctx;
  const act = activeJobs(E.p); const ap = PRO.autopilotStrip();
  if (!act.length && !ap) { el.hidden = true; el.innerHTML = ""; el.classList.remove("mini"); return; }
  const pref = jobsPref(); const phone = matchMedia("(max-width: 640px)").matches;
  if (E.jobsMini === undefined) E.jobsMini = pref.mini !== undefined ? !!pref.mini : phone; // phones: never cover the preview
  el.hidden = false;
  el.classList.toggle("mini", !!E.jobsMini);
  if (pref.x !== undefined && pref.y !== undefined && !phone) { el.style.left = pref.x + "px"; el.style.top = pref.y + "px"; el.style.right = "auto"; }
  if (E.jobsMini) {
    const j0 = act[0]; const pc = j0 ? Math.max(0, Math.min(100, Math.round(+j0.progress || 0))) : 0;
    el.innerHTML = `<button class="jpill" id="jobs-open" title="काम देखें">⏳ ${act.length} काम${j0 && j0.status === "running" ? ` · ${pc}%` : ""}</button>`;
    $("#jobs-open", el).onclick = () => { E.jobsMini = false; saveJobsPref({ mini: false }); renderJobs(); };
    return;
  }
  el.innerHTML = `<div class="jhead" id="jobs-grip"><span class="small muted">⠿ काम चल रहे हैं</span><button class="ibtn" id="jobs-min" title="छोटा करें">—</button></div>` + ap + act.slice(0, 4).map((j) => { const pc = Math.max(0, Math.min(100, Math.round(+j.progress || 0)));
    return `<div class="jobrow" title="${esc(j.message || E.p.status_note || "")}"><span class="spin"></span><span class="jl"><b>${esc(jobLabel(j))}</b><span class="muted">${esc(jobSub(j))}</span></span><span class="jp">${j.status === "queued" ? "…" : pc + "%"}</span>${E.canEdit || E.ctx.S.user.role !== "viewer" ? `<button class="ibtn jx" data-jcancel="${j.id}" title="रद्द करें">✕</button>` : ""}<i style="width:${j.status === "queued" ? 0 : pc}%"></i></div>`; }).join("")
    + (act.length > 4 ? `<div class="small muted">+${act.length - 4} और</div>` : "") + (E.locked ? `<div class="small jlock">🔒 transcript/कट बन रहे हैं — तब तक editing बंद</div>` : "");
  PRO.bindAutopilot(el);
  $("#jobs-min", el).onclick = () => { E.jobsMini = true; saveJobsPref({ mini: true }); renderJobs(); };
  $$("[data-jcancel]", el).forEach((b) => (b.onclick = () => cancelJob(b.dataset.jcancel, b)));
  // drag the card anywhere over the stage (mouse + touch); the place is remembered
  const grip = $("#jobs-grip", el);
  grip.onpointerdown = (e) => { if (e.target.closest("button")) return; e.preventDefault(); const st = $(".ed-stage", E.root).getBoundingClientRect(); const r = el.getBoundingClientRect();
    const ox = e.clientX - r.left, oy = e.clientY - r.top; grip.setPointerCapture(e.pointerId);
    const mv = (ev) => { const x = Math.max(0, Math.min(st.width - r.width, ev.clientX - st.left - ox)); const y = Math.max(0, Math.min(st.height - 40, ev.clientY - st.top - oy)); el.style.left = x + "px"; el.style.top = y + "px"; el.style.right = "auto"; };
    const up = () => { grip.onpointermove = null; grip.onpointerup = null; saveJobsPref({ x: parseFloat(el.style.left), y: parseFloat(el.style.top) }); };
    grip.onpointermove = mv; grip.onpointerup = up; };
}
async function cancelJob(id, btn) {
  const j = (E.p.jobs || []).find((x) => x.id === id); if (!j) return;
  if (!confirm(`${jobLabel(j)} रद्द करें?`)) return;
  if (btn) btn.disabled = true;
  try { const r = await E.ctx.api("POST", `/projects/${E.pid}/jobs/${id}/cancel`); E.ctx.toast(`${jobLabel(j)} रद्द किया`); if (r.project && E) { E.ctx.S.project = r.project; update(r.project); } }
  catch (e) { E.ctx.toast(e.message); if (btn) btn.disabled = false; }
}
// a "re-listen one line" job: payload.core = [start, end] in recording seconds (older builds: payload.range)
function jobRange(j) { if (j.kind !== "transcribe") return null; const c = j.payload?.core; if (Array.isArray(c) && c.length === 2) return { start: +c[0], end: +c[1] }; const r = j.payload?.range; return r && r.end > r.start ? { start: +r.start, end: +r.end } : null; }
function rangeBusy(a, b) { return activeJobs(E.p).some((j) => j.kind === "transcribe" && jobRange(j) && jobRange(j).start < b && jobRange(j).end > a); }

// ---------- transcript (the editor owns its copy; server copy only comes in after a job changed it) ----------
function syncWords() { E.words = E.tr.segments.flatMap((s) => s.words || []).sort((a, b) => a.start - b.start); }
const trCanon = (segs) => (segs || []).map((s) => (s.words || []).map((w) => `${w.w}@${(+w.start).toFixed(3)}`).join(" ")).join("|");
// word objects held by an open text box may be from an older copy of the transcript → find the live ones by time
function liveWords(ws) {
  if (!ws?.length || E.words.includes(ws[0])) return ws || [];
  return ws.map((w) => E.words.find((x) => Math.abs(x.start - w.start) < 1e-3 && Math.abs(x.end - w.end) < 1e-3)).filter(Boolean);
}
function mergeTranscript(srvTr, ranges) {
  const inR = (s) => ranges.some((r) => s.start < r.end && s.end > r.start);
  const segs = [...E.tr.segments.filter((s) => !inR(s)), ...JSON.parse(JSON.stringify((srvTr?.segments || []).filter(inR)))].sort((a, b) => a.start - b.start);
  E.tr = { ...JSON.parse(JSON.stringify(srvTr || {})), segments: segs };
}
function segOfWord(w) { return E.tr.segments.find((s) => (s.words || []).includes(w)); }
function deleteWords(ws) {
  const del = new Set(liveWords(ws)); if (!del.size) return 0; let n = 0;
  for (const seg of E.tr.segments) { const before = (seg.words || []).length; seg.words = (seg.words || []).filter((w) => !del.has(w)); n += before - seg.words.length; seg.text = seg.words.map((w) => w.w).join(" "); if (seg.words.length) { seg.start = seg.words[0].start; seg.end = seg.words[seg.words.length - 1].end; } }
  E.tr.segments = E.tr.segments.filter((s) => (s.words || []).length || !s.words);
  syncWords(); E.transcriptDirty = true; return n;
}
function relisten(ranges) {
  const groups = [...ranges].sort((a, b) => a.start - b.start).reduce((acc, r) => { const l = acc[acc.length - 1]; if (l && r.start <= l.end + 0.3) l.end = Math.max(l.end, r.end); else acc.push({ ...r }); return acc; }, []);
  if (!groups.length) return;
  const ctx = E.ctx, pid = E.pid, dur = E.dur;
  return (async () => {
    try {
      await flush();
      for (const g of groups) await ctx.api("POST", `/projects/${pid}/retranscribe`, { start: +Math.max(0, g.start - 0.15).toFixed(2), end: +Math.min(dur, g.end + 0.15).toFixed(2) });
      ctx.toast(groups.length > 1 ? `${groups.length} हिस्से दोबारा सुने जा रहे हैं` : "यह line दोबारा सुनी जा रही है"); E?.capSel.clear();
      await ctx.load(); ctx.render();
    } catch (err) { ctx.toast(err.message || "नहीं हुआ"); }
  })();
}

// ---------- time mapping ----------
function keeps() {
  const on = E.cuts.filter((c) => c.enabled !== false && c.end > c.start).sort((a, b) => a.start - b.start);
  const out = []; let t = 0;
  for (const c of on) { if (c.start > t) out.push([t, Math.min(c.start, E.dur)]); t = Math.max(t, c.end); }
  if (t < E.dur) out.push([t, E.dur]);
  return out;
}
function outDur() { return keeps().reduce((s, [a, b]) => s + b - a, 0); }
function outOf(src) { let o = 0; for (const [a, b] of keeps()) { if (src <= a) break; o += Math.min(src, b) - a; } return o; }
function srcOf(out) { let o = 0; for (const [a, b] of keeps()) { if (out <= o + (b - a)) return a + (out - o); o += b - a; } return E.dur; }
function cutAt(t) { return E.cuts.find((c) => c.enabled !== false && c.start <= t && t < c.end); }
// a cut is morphed when it says so, or when morph cut is on for all cuts and it did not opt out (editor-schema §10)
function morphOn(c) { const g = E.rs.effects.pro?.morph_cut || {}; return c.morph === true || (c.morph !== false && !!g.enabled && !!g.all); }
const fmt = (t) => { t = Math.max(0, t || 0); const m = Math.floor(t / 60), s = t % 60; return `${m}:${s < 10 ? "0" : ""}${s.toFixed(1)}`; };
const fmtF = (t) => { const fps = E.p.meta?.fps || 30; const f = Math.round((t % 1) * fps); return `${fmt(Math.floor(t))}`.replace(/\.\d$/, "") + `:${f < 10 ? "0" : ""}${f}`; };

// ---------- skeleton ----------
function skeleton() {
  const { esc } = E.ctx;
  return `<div class="ed">
    <header class="ed-top">
      <a class="ibtn" href="#/" title="सभी projects">${ICON.back}</a>
      <div class="ed-title"><span id="ed-name" ${E.canEdit ? 'contenteditable="true" spellcheck="false"' : ""}>${esc(E.p.title)}</span><span id="ed-status" class="small muted"></span></div>
      <div class="ed-top-right">
        <button class="ibtn" id="ed-undo" title="Undo (Ctrl+Z)" disabled>${ICON.undo}</button><button class="ibtn" id="ed-redo" title="Redo (Ctrl+Y)" disabled>${ICON.redo}</button>
        <span id="ed-save" class="small muted"></span>
        <button class="ibtn" id="ed-keys" title="Keyboard shortcuts (?)">⌨</button>
        <div class="seg" id="ratio"><button data-r="9:16" class="on">9:16</button><button data-r="16:9">16:9</button><button data-r="1:1">1:1</button></div>
        <select id="pv-plat" class="small" title="किस platform का version देखें (CTA popup अलग होते हैं)"><option value="youtube">▶ YouTube</option><option value="instagram">◎ Instagram</option><option value="facebook">f Facebook</option></select>
        <button class="btn primary" id="ed-export">${ICON.export} Export</button>
      </div>
    </header>
    <nav class="ed-tabs">${TABS.map(([id, l]) => `<button data-tab="${id}" class="${id === E.tab ? "on" : ""}">${ICON[id]}<span>${l}</span></button>`).join("")}</nav>
    <section class="ed-panel" id="ed-panel"></section><div class="ed-gutter gx" id="g-panel" title="drag करके चौड़ाई बदलें"></div>
    <section class="ed-stage">
      <div class="ed-jobs" id="ed-jobs" hidden></div>
      <div class="ed-viewport" id="viewport">
        <div class="ed-frame" id="frame">
          <div class="vclip vbgclip"><canvas id="pv-bg" hidden></canvas></div><div class="vclip" id="vclip"><div class="vpost" id="vpost"><div class="vbox" id="vbox"><div class="vrot" id="vrot"><video id="pv" playsinline preload="auto" src="${(E.p.assets.find((a) => a.kind === (E.montage ? "render" : "proxy")) || {}).url || ""}" ${E.montage ? "controls" : ""}></video><canvas id="pv-cut" hidden></canvas></div></div></div></div>
          <div class="ed-mask" id="mask"></div>
          <div class="ed-safe" id="safe"></div>
          <div class="ed-ovl" id="ovl"><div id="ovl-media"></div><div id="ovl-text"></div></div>
          <div class="ed-hdl" id="hdl"></div>
          <div class="ed-cutbadge" id="cutbadge" hidden></div>
          <div class="ed-cutmedia" id="cutmedia" aria-hidden="true"></div>
          <div class="ed-frameprev" id="frameprev" hidden><img alt=""><button class="ibtn" id="frameprev-x">✕</button><span class="small">rendered frame @ <b></b></span></div>
        </div>
      </div>
      <div class="ed-transport">
        <button class="ibtn" id="t-prev" title="पिछला कट">${ICON.prev}</button>
        <button class="ibtn big" id="t-play" title="चलाएँ (space)">${ICON.play}</button>
        <button class="ibtn" id="t-next" title="अगला कट">${ICON.next}</button>
        <span class="ed-time"><b id="t-now">0:00:00</b><span class="muted"> / <span id="t-dur"></span></span></span>
        <label class="small muted chk"><input type="checkbox" id="t-skip" checked> कट छोड़कर चलाएँ</label>
        <span class="grow"></span>
        <button class="btn small quiet" id="t-in" title="I">In</button><button class="btn small quiet" id="t-out" title="O">Out</button>
        <button class="btn small" id="t-cut" title="In–Out के बीच हटाएँ">${ICON.cuts} हटाएँ</button>
        <select class="btn small quiet" id="t-speed" title="In–Out की speed"><option value="">speed…</option><option value="0.5">0.5×</option><option value="0.75">0.75×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2×</option><option value="3">3×</option></select>
        <span class="muted small" id="t-marks"></span>
        <button class="btn small quiet" id="t-frame" title="इस समय का असली rendered frame (effects/body/grade सहित)">🎞 Preview frame</button>
        <button class="ibtn" id="t-full" title="Full screen (F)">⛶</button>
      </div>
    </section>
    <div class="ed-gutter gx" id="g-insp"></div><aside class="ed-inspector" id="inspector"></aside>
    <div class="ed-gutter gy" id="g-tl" title="drag करके timeline की ऊँचाई बदलें"></div><section class="ed-tl">
      <div class="ed-tl-head">
        <span class="tl-tools">
          <button class="ibtn" data-tool="split" title="Split — चुने हुए text/B-roll/audio को playhead पर दो हिस्सों में (S)">✂</button>
          <button class="ibtn" data-tool="dup" title="Duplicate (Ctrl+D)">⧉</button>
          <button class="ibtn" data-tool="del" title="हटाएँ (Del)">🗑</button>
          <span class="tsep"></span>
          <button class="ibtn" data-tool="video" title="Main video: crop, rotate, size">▣</button>
          <button class="ibtn" data-tool="crop" title="Crop">⌗</button>
          <button class="ibtn" data-tool="rot" title="90° घुमाएँ">⟳</button>
          <button class="ibtn" data-tool="mirror" title="Mirror">⇋</button>
          <span class="tsep"></span>
          <button class="ibtn" data-tool="fit" title="पूरा timeline दिखाएँ">⤢</button>
          <button class="ibtn" data-tool="full" title="Full screen preview (F)">⛶</button>
        </span>
        <span class="small muted" id="tl-info"></span><span class="grow"></span>
        <label class="small muted">zoom <input type="range" id="tl-zoom" min="4" max="160" value="${E.pps}"></label>
      </div>
      <div class="ed-tl-scroll" id="tl-scroll">
        <div class="ed-tl-labels" id="tl-labels"></div>
        <div class="ed-tl-body" id="tl-body"></div>
      </div>
    </section>
    <div class="ed-modal" id="ed-modal" hidden></div>
  </div>`;
}

function layoutSizes() {
  if (!E.sizes) { let sz = {}; try { sz = JSON.parse(localStorage.getItem("vividora_layout") || "{}"); } catch {} E.sizes = { panel: 320, insp: 300, tl: 300, ...sz }; }
  E.root.style.setProperty("--w-panel", E.sizes.panel + "px"); E.root.style.setProperty("--w-insp", E.sizes.insp + "px"); E.root.style.setProperty("--h-tl", E.sizes.tl + "px");
}
function bindGutters() {
  const drag = (el, key, axis, min, max, invert) => {
    el.onmousedown = (e) => { e.preventDefault(); const start = axis === "x" ? e.clientX : e.clientY; const v0 = E.sizes[key]; document.body.style.cursor = axis === "x" ? "ew-resize" : "ns-resize"; document.body.style.userSelect = "none";
      const mv = (ev) => { const d = (axis === "x" ? ev.clientX : ev.clientY) - start; E.sizes[key] = clamp(v0 + (invert ? -d : d), min, max); layoutSizes(); layoutFrame(); };
      const up = () => { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); document.body.style.cursor = ""; document.body.style.userSelect = ""; try { localStorage.setItem("vividora_layout", JSON.stringify(E.sizes)); } catch {} renderTimeline(); };
      document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up); };
    el.ondblclick = () => { E.sizes[key] = { panel: 320, insp: 300, tl: 300 }[key]; layoutSizes(); layoutFrame(); try { localStorage.setItem("vividora_layout", JSON.stringify(E.sizes)); } catch {} };
  };
  drag($("#g-panel", E.root), "panel", "x", 220, 620, false);
  drag($("#g-insp", E.root), "insp", "x", 220, 560, true);
  drag($("#g-tl", E.root), "tl", "y", 160, 600, true);
}
function bindStatic() {
  const { api, toast, load } = E.ctx;
  layoutSizes(); bindGutters();
  $$(".ed-tabs button", E.root).forEach((b) => (b.onclick = () => {
    const pn = $("#ed-panel", E.root);
    // phones: tapping the open tab again folds the panel away so the preview gets the room back
    if (E.tab === b.dataset.tab && matchMedia("(max-width: 640px)").matches) { pn.classList.toggle("ed-panel-collapsed"); return; }
    pn.classList.remove("ed-panel-collapsed");
    E.tab = b.dataset.tab; $$(".ed-tabs button", E.root).forEach((x) => x.classList.toggle("on", x === b)); renderPanel(); }));
  const pp = $("#pv-plat", E.root); if (pp) { pp.value = E.pvPlat || "youtube"; pp.onchange = () => { E.pvPlat = pp.value; renderOverlay(); }; }
  $$("#ratio button", E.root).forEach((b) => (b.onclick = () => { E.ratio = b.dataset.r; $$("#ratio button", E.root).forEach((x) => x.classList.toggle("on", x === b)); layoutFrame(); renderOverlay(); }));
  $("#ed-export", E.root).onclick = () => { E.exportOpen = true; renderExport(); };
  $("#ed-undo", E.root).onclick = undo; $("#ed-redo", E.root).onclick = redo;
  $("#ed-keys", E.root).onclick = showKeys;
  E.last = snapshot();
  const name = $("#ed-name", E.root);
  if (name.isContentEditable) name.onblur = async () => { const t = name.textContent.trim(); if (t && t !== E.p.title) { await api("PATCH", `/projects/${E.pid}`, { title: t }); toast("नाम बदला"); E.p.title = t; } };
  const v = $("#pv", E.root);
  v.onloadedmetadata = () => { layoutFrame(); renderOverlay(); };
  v.onplay = () => { $("#t-play", E.root).innerHTML = ICON.pause; tick(); };
  v.onpause = () => { $("#t-play", E.root).innerHTML = ICON.play; cancelAnimationFrame(E.raf); renderOverlay(); };
  v.addEventListener("seeked", cutKick); v.addEventListener("loadeddata", cutKick);
  v.addEventListener("seeked", () => E && PRO.drawBg()); v.addEventListener("loadeddata", () => E && PRO.drawBg()); v.addEventListener("ratechange", cutKick); watchFrames(v);
  $("#t-play", E.root).onclick = togglePlay;
  $("#t-prev", E.root).onclick = () => { const c = [...E.cuts].filter((c) => c.start < E.t - 0.3).sort((a, b) => b.start - a.start)[0]; seek(c ? c.start - 0.5 : 0); };
  $("#t-next", E.root).onclick = () => { const c = [...E.cuts].filter((c) => c.start > E.t + 0.05).sort((a, b) => a.start - b.start)[0]; seek(c ? c.start - 0.5 : E.dur); };
  $("#t-skip", E.root).onchange = (e) => (E.skipCuts = e.target.checked);
  $("#t-in", E.root).onclick = () => mark("in");
  $("#t-out", E.root).onclick = () => mark("out");
  $("#t-cut", E.root).onclick = addCutFromMarks;
  $("#t-frame", E.root).onclick = async () => { const fp = $("#frameprev", E.root); const btn = $("#t-frame", E.root); btn.disabled = true; btn.textContent = "बन रहा…";
    try { await flush(); const rs = JSON.parse(JSON.stringify(E.rs)); const r = await fetch(`/api/projects/${E.pid}/frame`, { method: "POST", headers: { authorization: "Bearer " + E.ctx.S.token, "content-type": "application/json" }, body: JSON.stringify({ t: E.t, render: rs, preset: E.ratio === "16:9" ? "yt-long" : E.ratio === "1:1" ? "yt-short" : "yt-short" }) });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText); const blob = await r.blob(); fp.querySelector("img").src = URL.createObjectURL(blob); fp.querySelector("b").textContent = fmt(E.t); fp.hidden = false; }
    catch (err) { E.ctx.toast(err.message); } btn.disabled = false; btn.textContent = "🎞 Preview frame"; };
  $("#frameprev-x", E.root).onclick = () => ($("#frameprev", E.root).hidden = true);
  $("#t-speed", E.root).onchange = (e) => { const r = +e.target.value; e.target.value = ""; if (!r || !E.canEdit) return; if (E.markIn == null || E.markOut == null) return E.ctx.toast("पहले I और O से हिस्सा चुनें");
    const it = { id: uid(), start: +E.markIn.toFixed(3), end: +E.markOut.toFixed(3), rate: r }; E.speed.push(it); E.markIn = E.markOut = null; $("#t-marks", E.root).textContent = ""; touch(); select({ type: "speed", id: it.id }); };
  $("#tl-zoom", E.root).oninput = (e) => { E.pps = +e.target.value; renderTimeline(); };
  $$("[data-tool]", E.root).forEach((b) => (b.onclick = () => tool(b.dataset.tool)));
  const tfull = $("#t-full", E.root); if (tfull) tfull.onclick = () => toggleFull();
  document.addEventListener("fullscreenchange", () => setTimeout(() => { layoutFrame(); renderOverlay(); }, 60));
  window.addEventListener("resize", layoutFrame);
  document.addEventListener("keydown", onKey);
  bindCanvas();
  $("#tl-scroll", E.root).addEventListener("wheel", (e) => { if (e.ctrlKey) { e.preventDefault(); E.pps = clamp(E.pps * (e.deltaY < 0 ? 1.15 : 0.87), 4, 160); $("#tl-zoom", E.root).value = E.pps; renderTimeline(); } }, { passive: false });
}

function showKeys() {
  const m = $("#ed-modal", E.root); if (!m.hidden && m.querySelector(".shortcuts")) { m.hidden = true; m.innerHTML = ""; return; }
  m.hidden = false; m.innerHTML = PRO.shortcutsHtml(); const x = () => { m.hidden = true; m.innerHTML = ""; if (E.exportOpen) renderExport(); };
  $("[data-scx]", m).onclick = x; m.onclick = (e) => { if (e.target === m) x(); };
}
function onKey(e) {
  if (!E || e.target.closest("input,textarea,select,[contenteditable=true]")) return;
  if (PRO.onKey(e)) return;
  const v = $("#pv", E.root); const fps = E.p.meta?.fps || 30;
  if (e.key === "?" || (e.shiftKey && e.key === "/")) { e.preventDefault(); return showKeys(); }
  if (e.altKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) { if (PRO.jumpKey(e.key === "ArrowRight" ? 1 : -1)) { e.preventDefault(); return; } }
  if ((e.key === "m" || e.key === "M") && !e.ctrlKey && !e.metaKey) { e.preventDefault(); return PRO.addMarker(e.shiftKey ? "chapter" : "note"); }
  if ((e.key === "k" || e.key === "K") && !e.ctrlKey && !e.metaKey) { e.preventDefault(); if (!PRO.keyAll()) E.ctx.toast("◆ keyframe के लिए पहले overlay clip या main video चुनें"); return; }
  if (e.code === "Space") { e.preventDefault(); togglePlay(); }
  else if (e.key === "i" || e.key === "I") mark("in");
  else if (e.key === "o" || e.key === "O") mark("out");
  else if (e.key === "ArrowLeft") { e.preventDefault(); seek(E.t - (e.shiftKey ? 1 : 1 / fps)); }
  else if (e.key === "ArrowRight") { e.preventDefault(); seek(E.t + (e.shiftKey ? 1 : 1 / fps)); }
  else if (e.key === "Delete" || e.key === "Backspace") { if (E.sel) { e.preventDefault(); deleteSel(); } }
  else if (e.key === "x" || e.key === "X") addCutFromMarks();
  else if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(true); }
  else if ((e.ctrlKey || e.metaKey) && !e.shiftKey && (e.key === "z" || e.key === "Z")) { e.preventDefault(); undo(); }
  else if ((e.ctrlKey || e.metaKey) && (e.key === "y" || (e.shiftKey && (e.key === "z" || e.key === "Z")))) { e.preventDefault(); redo(); }
  else if (e.key === "Escape") { const m = $("#ed-modal", E.root); if (m.querySelector(".shortcuts")) { m.hidden = true; m.innerHTML = ""; if (E.exportOpen) renderExport(); } else if (E.exportOpen) { E.exportOpen = false; renderExport(); } else if (E.maskEdit) { E.maskEdit = false; renderInspector(); renderOverlay(); } else select(null); }
  else if (e.key === "Home") seek(0);
  else if (e.key === "f" || e.key === "F") toggleFull();
  else if ((e.key === "s" || e.key === "S") && !e.ctrlKey && !e.metaKey) tool("split");
  else if ((e.ctrlKey || e.metaKey) && (e.key === "d" || e.key === "D")) { e.preventDefault(); tool("dup"); }
  else if (e.key === "End") seek(E.dur);
}
function togglePlay() { const v = $("#pv", E.root); if (!v.src) return; if (v.paused) { if (E.skipCuts) { const c = cutAt(v.currentTime); if (c) v.currentTime = c.end; } v.play(); } else v.pause(); }
function seek(t) { const v = $("#pv", E.root); E.t = clamp(t, 0, E.dur); if (v) v.currentTime = E.t; renderOverlay(); renderPlayhead(); }
function tick() {
  const v = $("#pv", E.root); if (!v) return;
  E.t = v.currentTime;
  if (E.skipCuts && !v.paused) { const c = cutAt(E.t); if (c) { v.currentTime = Math.min(E.dur, c.end + 0.02); E.t = v.currentTime; } }
  if (E.stopAt != null && E.t >= E.stopAt) { v.pause(); E.stopAt = null; }
  renderOverlay(); renderPlayhead(true); PRO.drawBg();
  if (!v.paused) E.raf = requestAnimationFrame(tick);
}
function mark(which) {
  if (which === "in") E.markIn = E.t; else E.markOut = E.t;
  if (E.markIn != null && E.markOut != null && E.markOut < E.markIn) [E.markIn, E.markOut] = [E.markOut, E.markIn];
  $("#t-marks", E.root).textContent = E.markIn != null || E.markOut != null ? `${E.markIn != null ? fmt(E.markIn) : "…"} → ${E.markOut != null ? fmt(E.markOut) : "…"}` : "";
  renderTimeline();
}
function addCutFromMarks() {
  if (!E.canEdit) return;
  if (E.markIn == null || E.markOut == null || E.markOut - E.markIn < 0.05) { E.ctx.toast("पहले I और O से हिस्सा चुनें"); return; }
  const c = { id: uid(), start: +E.markIn.toFixed(3), end: +E.markOut.toFixed(3), reason: "manual", enabled: true, text: "" };
  E.cuts.push(c); E.markIn = E.markOut = null; $("#t-marks", E.root).textContent = "";
  touch(); select({ type: "cut", id: c.id }); renderTimeline();
}

// ---------- preview frame ----------
// The frame IS the output picture (9:16 / 16:9 / 1:1). The main video inside it is laid out with the
// same steps as the render (engine/effects.py transform_pre → render._frame_filter → transform_post):
// crop (source) → 90° turns + mirror → fine angle (zoomed so no corners show) → fit to the frame → size / position.
function frameRatio() { const [a, b] = E.ratio.split(":").map(Number); return a / b; }
function srcSize() { const v = $("#pv", E.root); return [v?.videoWidth || E.p.meta?.width || 1280, v?.videoHeight || E.p.meta?.height || 720]; }
function cropView() { return !!E.cropMode && !E.montage && (E.sel?.type === "video" || E.sel?.type === "seg"); }
function mainGeom(W, H) {
  const [vw, vh] = srcSize(); const t = E.rs.effects.transform || {};
  const c = t.crop && (+t.crop.w < 0.999 || +t.crop.h < 0.999) ? t.crop : { x: 0, y: 0, w: 1, h: 1 };
  const rot = (((+t.rotate || 0) % 360) + 360) % 360; const side = rot === 90 || rot === 270;
  const cw = vw * c.w, ch = vh * c.h; const ew = side ? ch : cw, eh = side ? cw : ch;
  const sr = ew / eh, dr = W / H; let dw, dh, x0, y0;
  if (Math.abs(sr - dr) / dr < 0.02) { dw = W; dh = H; x0 = 0; y0 = 0; }
  else {
    // 16:9 previews the YouTube (blur-fit) preset; the vertical ones crop to fill
    const cover = E.ratio !== "16:9" || (sr > dr && dr >= 1);
    const k = cover ? Math.max(W / ew, H / eh) : Math.min(W / ew, H / eh); dw = ew * k; dh = eh * k;
    x0 = cover ? (W - dw) * (E.rs.focus_x ?? 0.5) : (W - dw) / 2; y0 = cover ? (H - dh) * (E.rs.focus_y ?? 0.5) : (H - dh) / 2;
  }
  return { vw, vh, c, rot, side, dw, dh, x0, y0, t };
}
function layoutFrame() {
  const vp = $("#viewport", E.root), fr = $("#frame", E.root), v = $("#pv", E.root);
  if (!vp || !v) return;
  const [vw, vh] = srcSize(); const crop = cropView();
  const r = E.montage || crop ? vw / vh : frameRatio();
  const W0 = vp.clientWidth - 24, H0 = vp.clientHeight - 24;
  let w = W0, h = W0 / r; if (h > H0) { h = H0; w = H0 * r; }
  fr.style.width = w + "px"; fr.style.height = h + "px"; fr.classList.toggle("cropview", crop);
  E.frameBox = { x: 0, y: 0, w, h, scale: w / (r >= 1 ? 1920 : 1080) };
  $("#mask", E.root).style.cssText = "display:none";
  $("#safe", E.root).style.cssText = `left:0;top:0;width:${w}px;height:${h}px;display:${E.ratio === "9:16" && !crop && !E.montage ? "block" : "none"}`;
  $("#ovl", E.root).style.cssText = `left:0;top:0;width:${w}px;height:${h}px;${crop ? "display:none" : ""}`;
  E.vf = videoFilter(); v.style.filter = E.vf;
  applyVideoCss();
}
function applyVideoCss() {
  const v = $("#pv", E.root), post = $("#vpost", E.root), box = $("#vbox", E.root), rot = $("#vrot", E.root); const fb = E.frameBox;
  if (!v || !post || !fb) return;
  const clip = $("#vclip", E.root);
  if (E.montage || cropView()) { // plain: the whole source fills the frame
    post.style.cssText = box.style.cssText = rot.style.cssText = "left:0;top:0;width:100%;height:100%;transform:none";
    v.style.cssText = `left:0;top:0;width:100%;height:100%;filter:${E.vf || ""}`; if (clip) clip.style.webkitMaskImage = clip.style.maskImage = ""; PRO.bgFill(null); cutCss(); renderHandles(); return;
  }
  // keyframed main transform (effects.transform.kf) → the values at the playhead
  const g = mainGeom(fb.w, fb.h); const t = PRO.mainTf();
  post.style.cssText = `left:0;top:0;width:${fb.w}px;height:${fb.h}px;transform:translate(${((+t.x || 0) * fb.w).toFixed(1)}px,${((+t.y || 0) * fb.h).toFixed(1)}px) scale(${+t.scale || 1});opacity:${t.opacity ?? 1}`;
  if (clip) { const mk = PRO.mainMaskCss(); if (clip._mk !== mk) { clip._mk = mk; clip.style.webkitMaskImage = clip.style.maskImage = mk; clip.style.webkitMaskSize = clip.style.maskSize = "100% 100%"; } }
  PRO.bgFill(g, t);
  box.style.cssText = `left:${g.x0.toFixed(1)}px;top:${g.y0.toFixed(1)}px;width:${g.dw.toFixed(1)}px;height:${g.dh.toFixed(1)}px`;
  const iw = g.side ? g.dh : g.dw, ih = g.side ? g.dw : g.dh;
  const ang = +t.angle || 0; const a = ang * Math.PI / 180;
  const k2 = Math.abs(ang) > 0.05 ? Math.abs(Math.cos(a)) + Math.abs(Math.sin(a)) * Math.max(g.dw / g.dh, g.dh / g.dw) : 1;
  rot.style.cssText = `left:50%;top:50%;width:${iw.toFixed(1)}px;height:${ih.toFixed(1)}px;transform:translate(-50%,-50%) rotate(${ang}deg) scale(${k2.toFixed(4)}) scale(${t.flip_h ? -1 : 1},${t.flip_v ? -1 : 1}) rotate(${g.rot}deg)`;
  const kk = iw / (g.vw * g.c.w);
  v.style.cssText = `left:${(-g.c.x * g.vw * kk).toFixed(1)}px;top:${(-g.c.y * g.vh * kk).toFixed(1)}px;width:${(g.vw * kk).toFixed(1)}px;height:${(g.vh * kk).toFixed(1)}px;filter:${E.vf || ""}`;
  cutCss(); renderHandles();
}

// ---------- on-canvas handles: move / scale / rotate / crop the selected thing right on the preview ----------
function canvasBox() {
  const s = E.sel; const fb = E.frameBox; if (!s || !fb) return null; const fr = $("#frame", E.root); if (!fr) return null;
  if (cropView()) { const c = (E.rs.effects.transform || {}).crop || { x: 0, y: 0, w: 1, h: 1 }; return { kind: "crop", cx: (c.x + c.w / 2) * fb.w, cy: (c.y + c.h / 2) * fb.h, w: c.w * fb.w, h: c.h * fb.h, rot: 0 }; }
  if (s.type === "video" || s.type === "seg") { const t = PRO.mainTf(); const sc = +t.scale || 1; return { kind: "video", cx: fb.w / 2 + (+t.x || 0) * fb.w, cy: fb.h / 2 + (+t.y || 0) * fb.h, w: fb.w * sc, h: fb.h * sc, rot: +t.angle || 0 }; }
  const el = s.type === "broll" ? $(`#ovl-media .ov-broll[data-bid="${s.id}"]`, E.root) : s.type === "title" ? $(`#ovl-text .ov-title[data-id="${s.id}"]`, E.root) : null;
  if (!el) return null; const fr0 = fr.getBoundingClientRect(), r = el.getBoundingClientRect(); const it = selItem(); if (!it) return null;
  return { kind: s.type, cx: r.left + r.width / 2 - fr0.left, cy: r.top + r.height / 2 - fr0.top, w: el.offsetWidth, h: el.offsetHeight, rot: s.type === "title" ? -(+it.rotate || 0) : PRO.clipGeom(it, outOf(E.t), fb).rot };
}
function renderHandles() {
  const L = $("#hdl", E.root); if (!L) return;
  // mask editing (✎ preview पर handles): the mask's own box replaces the clip's handles
  const mh = E.canEdit ? PRO.maskHandlesHtml() : "";
  if (mh) { if (L._key === mh) return; L._key = mh; L.innerHTML = mh; PRO.bindMaskHandles(L); return; }
  const b = E.canEdit ? canvasBox() : null; const key = b ? `${b.kind}|${b.cx.toFixed(1)}|${b.cy.toFixed(1)}|${b.w.toFixed(1)}|${b.h.toFixed(1)}|${b.rot}|${E.guides || ""}` : "";
  if (key === L._key) return; L._key = key;
  if (!b) { L.innerHTML = ""; return; }
  const crop = b.kind === "crop";
  const hs = crop ? ["nw", "n", "ne", "e", "se", "s", "sw", "w"] : ["nw", "ne", "se", "sw"];
  L.innerHTML = `<div class="hbox ${b.kind}" style="left:${(b.cx - b.w / 2).toFixed(1)}px;top:${(b.cy - b.h / 2).toFixed(1)}px;width:${b.w.toFixed(1)}px;height:${b.h.toFixed(1)}px;transform:rotate(${b.rot}deg)">`
    + hs.map((h) => `<i class="hh h-${h}" data-h="${h}"></i>`).join("") + (crop ? "" : `<i class="hrot" data-h="rot" title="घुमाएँ"></i>`) + `</div>`
    + (E.guides?.includes("v") ? `<div class="guide gv"></div>` : "") + (E.guides?.includes("h") ? `<div class="guide gh"></div>` : "")
    + (crop ? `<button class="btn small primary cropdone" id="crop-done">✓ Crop पूरा</button>` : "");
  const hb = $(".hbox", L);
  hb.onpointerdown = (e) => { if (e.button > 0) return; e.preventDefault(); e.stopPropagation(); canvasDrag(e, e.target.dataset.h || "move"); };
  const cd = $("#crop-done", L); if (cd) cd.onclick = () => { E.cropMode = false; layoutFrame(); renderOverlay(); renderInspector(); };
}
// drag on the canvas: mode = move | rot | nw/ne/se/sw (scale) | n/e/s/w + corners (crop edges)
function canvasDrag(e, mode, opts = {}) {
  if (!E.canEdit) return; const fb = E.frameBox; const fr = $("#frame", E.root).getBoundingClientRect();
  const b = canvasBox(); if (!b) return; const s = E.sel; const fx = E.rs.effects;
  const P = (ev) => [ev.clientX - fr.left, ev.clientY - fr.top]; const [px0, py0] = P(e);
  const t = fx.transform = fx.transform || {}; const it = s.type === "video" || s.type === "seg" ? t : selItem();
  // keyframe-aware: start from the values at the playhead; a property with keyframes gets a key here (auto-key)
  const st = JSON.parse(JSON.stringify(b.kind === "video" ? PRO.mainTf() : it)); const SNAP = 6;
  const ko = b.kind === "video" ? PRO.mainOwner() : b.kind === "broll" ? PRO.clipOwner(it) : null;
  const sc0 = ko ? PRO.val(ko, "scale") : 1; const rot0 = b.kind === "broll" ? b.rot : null;
  const crop0 = { x: 0, y: 0, w: 1, h: 1, ...(t.crop || {}) };
  const ang = (x, y) => Math.atan2(y - b.cy, x - b.cx) * 180 / Math.PI;
  const dist = (x, y) => Math.hypot(x - b.cx, y - b.cy) || 1;
  const a0 = ang(px0, py0), d0 = dist(px0, py0);
  const apply = (ev) => {
    const [px, py] = P(ev); const dx = px - px0, dy = py - py0; let guides = "";
    if (b.kind === "crop") {
      const c = { ...crop0 }; const fx_ = dx / fb.w, fy_ = dy / fb.h; const MIN = 0.05;
      if (mode === "move") { c.x = clamp(crop0.x + fx_, 0, 1 - c.w); c.y = clamp(crop0.y + fy_, 0, 1 - c.h); }
      else {
        if (mode.includes("w")) { const x = clamp(crop0.x + fx_, 0, crop0.x + crop0.w - MIN); c.w = crop0.x + crop0.w - x; c.x = x; }
        if (mode.includes("e")) c.w = clamp(crop0.w + fx_, MIN, 1 - crop0.x);
        if (mode.includes("n")) { const y = clamp(crop0.y + fy_, 0, crop0.y + crop0.h - MIN); c.h = crop0.y + crop0.h - y; c.y = y; }
        if (mode.includes("s")) c.h = clamp(crop0.h + fy_, MIN, 1 - crop0.y);
      }
      t.crop = Object.fromEntries(Object.entries(c).map(([k, v]) => [k, +v.toFixed(4)]));
    } else if (mode === "move") {
      if (b.kind === "video") { let x = (st.x || 0) + dx / fb.w, y = (st.y || 0) + dy / fb.h;
        if (Math.abs(x * fb.w) < SNAP) { x = 0; guides += "v"; } if (Math.abs(y * fb.h) < SNAP) { y = 0; guides += "h"; }
        PRO.setVal(ko, "x", +x.toFixed(4)); PRO.setVal(ko, "y", +y.toFixed(4)); }
      else { let x = (b.cx + dx) / fb.w, y = (b.cy + dy) / fb.h;
        if (Math.abs(x - 0.5) * fb.w < SNAP) { x = 0.5; guides += "v"; } if (Math.abs(y - 0.5) * fb.h < SNAP) { y = 0.5; guides += "h"; }
        if (b.kind === "title") { it.pos = "free"; it.x = +clamp(x, 0.02, 0.98).toFixed(3); it.y = +clamp(y, 0.02, 0.98).toFixed(3); }
        else { const to = it.to; const kx = PRO.setVal(ko, "x", +clamp(x, -0.5, 1.5).toFixed(3)); PRO.setVal(ko, "y", +clamp(y, -0.5, 1.5).toFixed(3)); if (!kx && to && st.to) { to.x = +(st.to.x + (it.x - (st.x ?? 0.5))).toFixed(3); to.y = +(st.to.y + (it.y - (st.y ?? 0.5))).toFixed(3); } } }
    } else if (mode === "rot") {
      let a = (b.kind === "title" ? -(+st.rotate || 0) : b.kind === "video" ? (+st.angle || 0) : rot0) + (ang(px, py) - a0);
      a = ((a + 540) % 360) - 180; for (const q of [-180, -90, 0, 90, 180]) if (Math.abs(a - q) < 3) a = q;
      if (b.kind === "video") PRO.setVal(ko, "rotation", +clamp(a, -45, 45).toFixed(1)); else if (b.kind === "title") it.rotate = +(-a).toFixed(1); else PRO.setVal(ko, "rotation", +a.toFixed(1));
    } else { // corner: uniform scale around the centre
      const k = dist(px, py) / d0;
      if (b.kind === "video") PRO.setVal(ko, "scale", +clamp((+st.scale || 1) * k, 0.2, 4).toFixed(3));
      else if (b.kind === "title") it.size = +clamp((+st.size || 0.075) * k, 0.015, 0.4).toFixed(4);
      else if (it.kf?.scale?.length || (it.fit || "cover") !== "free") PRO.setVal(ko, "scale", +clamp(sc0 * k, 0.05, 8).toFixed(3));
      else { it.scale = +clamp((+st.scale || 0.4) * k, 0.03, 2.5).toFixed(3); if (it.to && st.to) it.to.scale = +clamp((+st.to.scale || 0.4) * k, 0.03, 2.5).toFixed(3); }
    }
    PRO.refreshKfUi();
    E.guides = guides; applyVideoCss(); renderOverlay();
  };
  track(e, apply, (moved) => { E.guides = ""; if (moved) { touch(); renderInspector(); } renderHandles(); opts.done?.(moved); }, 2);
}
// pointer down on the preview: pick what is under the finger (text, overlay, else the main video) and drag it
function bindCanvas() {
  const fr = $("#frame", E.root); if (!fr || fr._bound) return; fr._bound = 1;
  fr.addEventListener("pointerdown", (e) => {
    if (e.button > 0 || E.montage || e.target.closest(".hbox,#crop-done,.ed-frameprev")) return;
    const tEl = e.target.closest(".ov-title"), bEl = e.target.closest(".ov-broll"), hk = e.target.closest(".ov-hook");
    if (hk) { e.preventDefault(); select({ type: "hook", id: "h" }); setTimeout(() => $('#inspector [data-k="text"]', E.root)?.focus(), 30); return; }
    if (tEl) { e.preventDefault(); const id = tEl.dataset.id; if (E.sel?.type !== "title" || E.sel.id !== id) select({ type: "title", id }); if (E.canEdit) canvasDrag(e, "move"); return; }
    if (bEl) { e.preventDefault(); const id = bEl.dataset.bid; if (E.sel?.type !== "broll" || E.sel.id !== id) select({ type: "broll", id }); const b = selItem();
      if (b && E.canEdit && b.fit !== "free") { // full-frame / PiP overlay → becomes freely movable the moment you drag it
        const x0 = e.clientX, y0 = e.clientY; const mv = (ev) => { if (Math.abs(ev.clientX - x0) + Math.abs(ev.clientY - y0) < 4) return; document.removeEventListener("pointermove", mv);
          const fb = E.frameBox, r = bEl.getBoundingClientRect(), f0 = fr.getBoundingClientRect(); Object.assign(b, { fit: "free", x: +((r.left + r.width / 2 - f0.left) / fb.w).toFixed(3), y: +((r.top + r.height / 2 - f0.top) / fb.h).toFixed(3), scale: +(r.width / fb.w).toFixed(3), rotate: 0, opacity: b.opacity ?? 1 });
          E.mkey = null; renderOverlay(); renderInspector(); E.ctx.toast("overlay अब free है — खींचें, कोने से size"); };
        const up = () => { document.removeEventListener("pointermove", mv); document.removeEventListener("pointerup", up); touch(); };
        document.addEventListener("pointermove", mv); document.addEventListener("pointerup", up); return; }
      if (E.canEdit) canvasDrag(e, "move"); return; }
    if (cropView()) { e.preventDefault(); return; }
    // empty canvas = the main video
    e.preventDefault(); if (E.sel?.type !== "video" && E.sel?.type !== "seg") select({ type: "video", id: "main" }); if (E.canEdit) canvasDrag(e, "move");
  });
}
function toggleFull() {
  const st = $(".ed-stage", E.root); if (!st) return;
  if (document.fullscreenElement) document.exitFullscreen(); else st.requestFullscreen?.().catch(() => E.ctx.toast("full screen नहीं खुला"));
}
function splitItem(it, type) {
  const fx = E.rs.effects; const ot = +outOf(E.t).toFixed(2);
  if (type === "sfx") { const len = it.dur || (libItem(it.id)?.meta?.duration || 0); if (!len || ot <= it.at + 0.05 || ot >= it.at + len - 0.05) return null;
    const a = ot - it.at; const b = { ...JSON.parse(JSON.stringify(it)), _id: uid(), at: ot, trim: +((it.trim || 0) + a).toFixed(2), dur: +(len - a).toFixed(2) }; it.dur = +a.toFixed(2); fx.sfx.push(b); return b; }
  if (ot <= it.start + 0.05 || ot >= it.end - 0.05) return null;
  const b = { ...JSON.parse(JSON.stringify(it)), _id: uid(), start: ot }; it.end = ot; ({ title: fx.titles, broll: fx.broll, fxclip: fx.fxclips })[type].push(b); return b;
}
function tool(name) {
  const fx = E.rs.effects; const sel = E.sel; const it = sel && selItem();
  if (name === "full") return toggleFull();
  if (name === "fit") { const sc = $("#tl-scroll", E.root); E.pps = Math.max(4, Math.min(160, (sc.clientWidth - 140) / Math.max(1, E.dur))); const z = $("#tl-zoom", E.root); if (z) z.value = E.pps; renderTimeline(); return; }
  if (!E.canEdit) return;
  if (["video", "crop", "rot", "mirror"].includes(name)) {
    const t = fx.transform = fx.transform || {};
    if (name === "rot") t.rotate = ((+t.rotate || 0) + 90) % 360;
    if (name === "mirror") t.flip_h = !t.flip_h;
    if (name === "crop") { if (!t.crop) t.crop = { x: 0, y: 0, w: 1, h: 1 }; select({ type: E.sel?.type === "seg" ? "seg" : "video", id: E.sel?.type === "seg" ? E.sel.id : "main" }); E.cropMode = !E.cropMode; renderInspector(); layoutFrame(); renderOverlay(); return; }
    if (name !== "video") touch(); applyVideoCss(); select({ type: "video", id: "main" }); return;
  }
  if (name === "split") return splitAtPlayhead();
  if (!sel || !it) return E.ctx.toast("पहले timeline पर कोई item चुनें");
  if (name === "del") return deleteSel();
  if (name === "dup") {
    const c = { ...JSON.parse(JSON.stringify(it)), _id: uid() };
    if (["title", "broll", "fxclip"].includes(sel.type)) { const len = it.end - it.start; c.start = it.end; c.end = +Math.min(outDur(), it.end + len).toFixed(2); ({ title: fx.titles, broll: fx.broll, fxclip: fx.fxclips })[sel.type].push(c); }
    else if (sel.type === "sfx") { c.at = +(it.at + (it.dur || 1)).toFixed(2); fx.sfx.push(c); } else return;
    touch(); select({ type: sel.type, id: c._id });
  }
}
const GRADE_DEF = () => Object.fromEntries((E.ctx.S.presets?.catalog?.grade_params || []).map((p) => [p.name, p.default]));
function gradeCss(g) {
  if (!g || !Object.keys(g).length) return "";
  const D = GRADE_DEF(); const v = { ...D, ...Object.fromEntries(Object.entries(g).filter(([k, x]) => k in D && x !== "" && x != null).map(([k, x]) => [k, +x])) };
  const css = [`brightness(${(1 + v.exposure * 0.35 + v.whites * 0.08 - v.blacks * 0.05).toFixed(3)})`, `contrast(${(1 + v.contrast * 0.6 - v.fade * 0.25 - v.shadows * 0.1).toFixed(3)})`, `saturate(${Math.max(0, 1 + v.saturation + v.vibrance * 0.6).toFixed(3)})`];
  if (v.hue || v.tint) css.push(`hue-rotate(${(v.hue + v.tint * 10).toFixed(1)}deg)`);
  if (v.temperature > 0) css.push(`sepia(${(v.temperature * 0.35).toFixed(3)})`); else if (v.temperature < 0) css.push(`hue-rotate(${Math.round(v.temperature * 12)}deg)`);
  return css.join(" ");
}
function fxDef(id) { return (E.ctx.S.presets?.catalog?.effects || []).find((e) => e.id === id); }
function fxParams(def, given) { const o = {}; for (const p of def.params || []) { let v = given?.[p.name] ?? p.default; if (p.type !== "color") v = Math.max(p.min, Math.min(p.max, +v || 0)); o[p.name] = v; } return o; }
function stackCss(stack) {
  return (stack || []).filter((it) => it.enabled !== false).map((it) => { const d = fxDef(it.id); if (!d || d.preview !== "css" || !d.css) return ""; const pr = fxParams(d, it.params);
    return d.css.replace(/\{(\w+)(?::([\w.]+))?\}/g, (m, k, mode) => { let v = pr[k]; if (mode && /^px/.test(mode)) return (v * +mode.slice(2)) + "px"; if (mode && /^n/.test(mode)) return v * +mode.slice(1); return v; }); }).filter(Boolean).join(" ");
}
function captionChunks() {
  const cs = styleOf(); if (!cs || !E.words.length) return [];
  const maxW = cs.max_words || 5, maxC = (cs.max_chars || 24) * (cs.max_lines || 2);
  const out = []; let cur = [], n = 0;
  E.words.forEach((w, i) => {
    const prev = E.words[i - 1];
    if (cur.length && (cur.length >= maxW || n + w.w.length > maxC || (prev && w.start - prev.end > 0.6) || /[।.?!]$/.test(prev?.w || ""))) { out.push(cur); cur = []; n = 0; }
    cur.push(w); n += w.w.length + 1;
  });
  if (cur.length) out.push(cur);
  // end at the next line's start (an overlap hid that line's first words) and never before own start
  return out.map((ws, i) => { const nx = out[i + 1]?.[0].start; let end = ws[ws.length - 1].end + 0.15; if (nx != null && nx < end) end = nx; return { start: ws[0].start, end: Math.max(end, Math.min(ws[0].start + 0.3, nx ?? Infinity)), words: ws }; });
}
function styleOf() { return (E.ctx.S.presets?.caption_styles || []).find((s) => s.id === E.rs.caption_style); }
function renderOverlay() {
  const ovl = $("#ovl", E.root); if (!ovl || !E.frameBox) return;
  const { esc } = E.ctx; const t = E.t, ot = outOf(t); const fb = E.frameBox; const base = Math.min(fb.w, fb.h);
  const cs = styleOf(); const ov = E.rs.captions; let html = "";
  // B-roll + watermark: rebuilt only when the visible set changes (so <video> keeps playing)
  const active = E.rs.effects.broll.filter((b) => ot >= b.start && ot < b.end && (!b.platforms?.length || b.platforms.includes(E.pvPlat || "youtube")) && !(E.rs.effects.hidden_tracks || []).includes(`broll:${b.track || 0}`)).sort((a, b) => (a.track || 0) - (b.track || 0));
  const wm = E.rs.effects.watermark; const wmi = wm.id && libItem(wm.id);
  // the DOM is rebuilt only when the visible set changes; position / keyframes / mask / blend / speed are applied every frame (PRO.overlayFrame)
  const mkey = active.map((b) => `${b._id}:${b.id}:${b.fit}:${cutOn(b, libItem(b.id)) ? "c" : ""}:${b.cutout ? 1 : 0}`).join("|") + `#${wm.id}:${wm.opacity}:${wm.size}:${wm.pos}#${E.rs.effects.frame?.id}:${E.rs.effects.frame?.opacity}#${(E.lib || []).length}#${E.pvPlat || ""}` + (E.sel?.type === "broll" ? E.sel.id : "");
  if (mkey !== E.mkey) {
    E.mkey = mkey; let mh = "";
    for (const b of active) {
      const item = libItem(b.id); const fit = b.fit || "cover"; const crop = fit === "cover" || fit === "pip"; const img = ["image", "sticker", "frame", "logo"].includes(item?.kind);
      const media = !item ? "" : img ? `<img src="${item.url}" draggable="false" style="width:100%;height:100%;display:block;object-fit:${crop ? "cover" : "fill"}">`
        : cutOn(b, item) ? `<div class="ov-cutslot" data-cut="${b._id}" data-fit="${fit === "free" ? "free" : "cover"}"></div>`
        : `<video src="${item.url}" muted playsinline preload="auto" style="width:100%;height:100%;display:block;object-fit:${crop ? "cover" : "fill"}"></video>`;
      mh += `<div class="ov-broll ${E.sel?.type === "broll" && E.sel.id === b._id ? "sel" : ""}" data-bid="${b._id}" style="position:absolute;overflow:hidden;border-radius:${fit === "pip" ? 6 : 0}px">${media}${crop ? `<span class="ov-tag">${esc(item?.name || "B-roll")}${b.cutout ? (cutOn(b, item) ? " · ✂ सिर्फ़ इंसान" : " · ✂ cutout बाकी") : ""}</span>` : ""}</div>`;
    }
    const frm = E.rs.effects.frame || {}; const frmi = frm.id && libItem(frm.id);
    if (frmi) mh += `<img src="${frmi.url}" style="position:absolute;inset:0;width:100%;height:100%;opacity:${frm.opacity ?? 1};pointer-events:none">`;
    if (wmi) mh += `<img src="${wmi.url}" style="position:absolute;width:${(wm.size * 100).toFixed(0)}%;opacity:${wm.opacity};${{ tl: "left:3.5%;top:3.5%", tr: "right:3.5%;top:3.5%", bl: "left:3.5%;bottom:3.5%", br: "right:3.5%;bottom:3.5%" }[wm.pos]}">`;
    $("#ovl-media", ovl).innerHTML = mh;
  }
  PRO.overlayFrame(ot);
  if (PRO.mainAnimated()) applyVideoCss();
  // hook
  if (E.rs.hook.text && ot < (E.rs.hook.seconds || 3)) { const hk = E.rs.hook; const hpos = { top: `top:${fb.h > fb.w ? 13 : 6}%`, center: "top:50%;transform:translateY(-50%)", bottom: "bottom:22%" }[hk.position || "top"];
    html += `<div class="ov-hook ${E.sel?.type === "hook" ? "sel" : ""}" title="क्लिक करके बदलें" style="font-size:${0.085 * base * (hk.size_scale || 1)}px;${hpos};background:${hk.bg || cs?.highlight || "#FFD400"};color:${hk.color || "#111"};font-style:${hk.italic ? "italic" : "normal"};${hk.font ? `font-family:'${hk.font}',var(--font);` : ""}">${esc(hk.text).replace(/\|/g, "<br>")}</div>`; }
  // titles (same animation tables as the render — textfx.js)
  const TP = E.ctx.S.presets?.textfx;
  for (const ti of [...E.rs.effects.titles].sort((a, b) => (a.track || 0) - (b.track || 0))) if (ot >= ti.start && ot < ti.end && !(E.rs.effects.hidden_tracks || []).includes(`text:${ti.track || 0}`)) {
    html += TFX.renderText(ti, TP, ot, fb, { selected: E.sel?.type === "title" && E.sel.id === ti._id });
  }
  // captions
  const burn = E.rs.burn_captions !== false;
  if (burn && cs) {
    const ch = captionChunks().find((c) => t >= c.start && t < c.end);
    if (ch) {
      const sc = (ov.size_scale || 1) * (E.ratio === "16:9" ? 0.8 : 1);
      const size = (cs.size || 0.06) * base * sc; const pos = ov.position || cs.position || "bottom";
      const primary = ov.primary || cs.primary, hl = ov.highlight || cs.highlight, font = ov.font || cs.font;
      const glow = cs.glow ? `text-shadow:0 0 ${cs.glow * base * 1.5}px ${cs.outline_color},0 0 ${cs.glow * base * 3}px ${cs.outline_color};` : "";
      const stroke = cs.outline ? `-webkit-text-stroke:${cs.outline * base * 2}px ${cs.outline_color};paint-order:stroke fill;` : "";
      const box = cs.box === "line" ? `background:${cs.box_color || "#000"}${Math.round((cs.box_alpha ?? 0.6) * 255).toString(16).padStart(2, "0")};padding:.1em .35em;border-radius:.12em;` : "";
      const words = ch.words.map((w) => {
        const active = cs.mode !== "line" && t >= w.start - 0.02 && t < (ch.words[ch.words.indexOf(w) + 1]?.start ?? ch.end);
        const past = t >= w.start;
        if (cs.mode === "typewriter" && !past) return "";
        const txt = cs.uppercase && /^[\x00-ɏ]+$/.test(w.w) ? w.w.toUpperCase() : w.w;
        if (active) return cs.box === "word" ? `<span style="background:${cs.box_color};color:${hl};padding:0 .18em;border-radius:.15em;${stroke}">${esc(txt)}</span>` : `<span style="color:${hl};${cs.mode === "pop" ? "display:inline-block;transform:scale(1.15);" : ""}${stroke}">${esc(txt)}</span>`;
        return `<span style="${stroke}">${esc(txt)}</span>`;
      }).join(" ");
      const place = pos === "center" ? "top:50%;transform:translateY(-50%)" : pos === "top" ? "top:12%" : `bottom:${E.ratio === "16:9" ? 8 : 20}%`;
      const italic = ov.italic === true || (ov.italic === "" && cs.italic); const boldOn = ov.bold === false ? 400 : (cs.bold === false ? 400 : 800);
      const spacing = ov.letter_spacing ? `letter-spacing:${ov.letter_spacing * base}px;` : "";
      html += `<div class="ov-cap" style="${place};font-family:'${font}',var(--font);font-weight:${boldOn};font-style:${italic ? "italic" : "normal"};${spacing}font-size:${size}px;color:${primary};${glow}${box}">${words}</div>`;
    }
  }
  $("#ovl-text", ovl).innerHTML = html;
  // effect/filter clips under the playhead change the look of the video while it plays
  const vf = videoFilter(); if (vf !== E.vf) { E.vf = vf; const v = $("#pv", E.root); if (v) v.style.filter = vf; const cv = $("#pv-cut", E.root); if (cv) cv.style.filter = vf; }
  cutOverlays(); cutSync();
  renderHandles();
}

// ---------- live cutout (cutout.js): the person over a new background, moving, in the preview ----------
// The main <video> keeps playing (it is the clock and the picture texture); its matte plays in a hidden
// <video> that follows it (seek on jumps / cuts, playbackRate nudges while playing) and a <canvas> on
// top of it composites both every frame. B-roll "सिर्फ़ इंसान" overlays get their own small canvas.
const alphaAsset = () => E.p.assets.find((a) => a.kind === "alpha");
// localStorage vividora_cut2d = "1" → the canvas-2D compositor (old / broken GPU drivers)
function cut2d() { try { return localStorage.getItem("vividora_cut2d") === "1"; } catch { return false; } }
function cutOn(b, item) { return !!b?.cutout && item?.kind === "broll" && !!item?.meta?.alpha?.url; }
function cutLiveWanted() { return !E.montage && !!E.rs.effects.body?.enabled && !cropView(); }
function hiddenVideo(src, loop) {
  const el = document.createElement("video"); el.muted = true; el.playsInline = true; el.preload = "auto"; el.loop = !!loop; el.crossOrigin = "anonymous";
  el.addEventListener("loadeddata", cutKick); el.addEventListener("seeked", cutKick); if (src) el.src = src;
  $("#cutmedia", E.root)?.appendChild(el); watchFrames(el); return el;
}
// requestVideoFrameCallback: which frame each <video> really shows (mediaTime) → composite only matching frames
function watchFrames(el) { if (!el.requestVideoFrameCallback) return; const cb = (_now, m) => { el._vvNew = true; el._vvT = m?.mediaTime; if (E) el.requestVideoFrameCallback(cb); }; el.requestVideoFrameCallback(cb); }
// playing: the two presented frames are the same moment (±½ frame); without rVFC fall back to the clocks
// (±1 frame; after 3 mismatches in a row draw anyway — a moving preview beats a frozen one)
function sameFrame(a, b, t, fps) {
  const ok = a._vvT != null && b._vvT != null && !a.seeking && !b.seeking ? Math.abs(a._vvT - b._vvT) <= 1.01 / fps : near(b, t, 0.12);
  b._vvMiss = ok ? 0 : (b._vvMiss || 0) + ((a._vvNew || b._vvNew) ? 1 : 0); return ok || (b._vvMiss > 3 && near(b, t, 0.3));
}
function cutCss() {
  const v = $("#pv", E.root), cv = $("#pv-cut", E.root); if (!v || !cv) return;
  v.style.opacity = ""; cv.style.cssText = v.style.cssText; cv.style.position = "absolute"; cv.style.pointerEvents = "none";
  if (E.cut?.live) v.style.opacity = "0";
}
function cutSync() {
  const v = $("#pv", E.root), cv = $("#pv-cut", E.root); if (!v || !cv) return;
  const want = cutLiveWanted(), al = alphaAsset(), b = E.rs.effects.body || {};
  const live = want && !!al;
  if (live) {
    const C = E.cut || (E.cut = {});
    if (C.alphaId !== al.id) { C.alphaId = al.id; if (C.av) C.av.src = al.url; else C.av = hiddenVideo(al.url); }
    if (!C.comp) { C.comp = CUT.compositor(cv, { force2d: cut2d() }); cv.dataset.kind = C.comp?.kind || "none"; }
    const bgId = b.bg === "image" ? b.bg_image : b.bg === "video" ? b.bg_video : "";
    if (bgId !== C.bgId) {
      C.bgId = bgId; if (C.bgEl?.tagName === "VIDEO") { C.bgEl.pause(); C.bgEl.remove(); } C.bgEl = null;
      const it = bgId && libItem(bgId);
      if (it && b.bg === "image") { C.bgEl = new Image(); C.bgEl.crossOrigin = "anonymous"; C.bgEl.onload = cutKick; C.bgEl.src = it.url; }
      else if (it) C.bgEl = hiddenVideo(it.url, true);
      if (bgId && !it) C.bgId = null; // library not loaded yet → try again next time
    }
    // canvas pixels = what is on screen (× devicePixelRatio), never more than the proxy → less GPU work on small previews
    const vw = v.videoWidth || E.p.meta?.width || 1280, vh = v.videoHeight || E.p.meta?.height || 720;
    const shown = (parseFloat(v.style.width) || vw) * (window.devicePixelRatio || 1); const k = Math.min(1, 1280 / Math.max(vw, vh), Math.max(0.25, shown / vw));
    const W = Math.round(vw * k), H = Math.round(vh * k); if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
  } else if (E.cut?.av && !E.cut.av.paused) E.cut.av.pause();
  if (E.cut) E.cut.live = live;
  if (cv.hidden === live) { cv.hidden = !live; cutCss(); }
  cutBadge(want && !al);
  E.cutDirty = true; cutLoop();
}
function cutBadge(show) {
  const el = $("#cutbadge", E.root); if (!el) return;
  if (!show) { el.hidden = true; el._k = ""; return; }
  const mj = (E.p.jobs || []).find((j) => j.kind === "matte" && ["queued", "running"].includes(j.status));
  const key = mj ? `${mj.status}|${mj.progress}|${mj.message}` : "btn";
  el.hidden = false; if (el._k === key) return; el._k = key;
  el.innerHTML = mj ? `<span class="spin"></span><span>${mj.status === "queued" ? "Cutout queue में…" : `Cutout बन रहा है ${Math.round(mj.progress || 0)}%`}<small>${E.ctx.esc(String(mj.message || "").replace(/^cutout \d+\/\d+ · /, ""))}</small></span>`
    : `<span>✂ यह preview अभी सादा है — person cutout नहीं बना</span><button class="btn small primary" id="cutbadge-go" ${E.canEdit ? "" : "disabled"}>Cutout बनाएँ</button>`;
  const go = $("#cutbadge-go", el); if (go) go.onclick = () => startMatte();
}
const MATTE_Q = [["fast", "तेज़ (512p)"], ["balanced", "बढ़िया (720p) — सुझाया"], ["hair", "बाल/बारीकी (1080p, धीमा)"]];
function bodyStatus() {
  const { esc } = E.ctx; const alpha = alphaAsset(); const mj = (E.p.jobs || []).find((j) => j.kind === "matte" && ["queued", "running"].includes(j.status));
  const q = E.rs.effects.body?.quality || "balanced"; const dis = E.canEdit ? "" : "disabled"; const m = alpha?.meta || {};
  const head = mj ? `<p class="small">⏳ cutout ${mj.status === "queued" ? "queue में" : `बन रहा है… ${Math.round(mj.progress || 0)}%`}</p><div class="progress"><i style="width:${mj.progress || 0}%"></i></div><p class="small muted">${esc(String(mj.message || "").replace(/^cutout /, ""))}</p>`
    : alpha ? `<p class="small">✅ cutout तैयार · ${m.frames || ""} frames${m.quality ? ` · ${esc(m.quality)}` : ""}${m.ms_per_frame ? ` · ${m.ms_per_frame} ms/frame` : ""}</p>`
    : `<p class="small muted">CapCut के "Auto cutout" जैसा — चलते वीडियो में इंसान को अलग करता है (CPU पर, एक बार; 1 min ≈ 1–4 min)।</p>`;
  return `${head}<div class="row"><select id="bd-q" class="small" ${dis || (mj ? "disabled" : "")} title="quality / speed">${MATTE_Q.map(([k, l]) => `<option value="${k}" ${q === k ? "selected" : ""}>${l}</option>`).join("")}</select>
    <button class="btn small ${alpha ? "quiet" : "primary"}" id="bd-matte" ${dis || (mj ? "disabled" : "")}>${alpha ? "cutout दोबारा बनाएँ" : "Cutout बनाएँ"}</button></div>`;
}
function bindBodyStatus(root) {
  const qs = $("#bd-q", root); if (qs) qs.onchange = () => { E.rs.effects.body.quality = qs.value; touch(); };
  const bt = $("#bd-matte", root); if (bt) bt.onclick = () => { bt.disabled = true; startMatte(); };
}
// B-roll / overlay clip: "सिर्फ़ इंसान" — its own matte, cached on the library item (job matte_lib)
function brollCutoutBox(it, item, dis) {
  const { esc } = E.ctx; const a = item?.meta?.alpha;
  const j = (E.p.jobs || []).find((x) => x.kind === "matte_lib" && x.payload?.library_id === item.id && ["queued", "running"].includes(x.status));
  const st = !it.cutout ? "" : a ? `<span class="small">✅ cutout तैयार${a.ms_per_frame ? ` · ${a.ms_per_frame} ms/frame` : ""}</span>`
    : j ? `<span class="small">⏳ cutout ${j.status === "queued" ? "queue में" : `${Math.round(j.progress || 0)}%`} <span class="muted">${esc(String(j.message || "").replace(/^cutout \d+\/\d+ · /, ""))}</span></span>`
    : `<button class="btn small primary" data-libmatte="${item.id}" ${dis}>Cutout बनाएँ</button>`;
  return `<div class="box"><label class="chk"><input type="checkbox" data-k="cutout" ${it.cutout ? "checked" : ""} ${dis}> <b>सिर्फ़ इंसान (cutout)</b></label> ${st}
    ${it.cutout ? `<p class="small muted">clip का background हटकर सिर्फ़ इंसान main video पर आएगा (preview में live)।</p><div class="irow">${field(`किनारा अंदर <b>${it.edge_shrink || 0}</b>`, `<input type="range" data-k="edge_shrink" min="0" max="6" step="0.5" value="${it.edge_shrink || 0}" ${dis}>`)}${field(`नरम <b>${it.edge_feather || 0}</b>`, `<input type="range" data-k="edge_feather" min="0" max="6" step="0.5" value="${it.edge_feather || 0}" ${dis}>`)}</div>` : ""}</div>`;
}
async function ensureLibMatte(libId, force) {
  const item = libItem(libId); if (!item || (item.meta?.alpha && !force)) return;
  try { const r = await E.ctx.api("POST", `/projects/${E.pid}/matte_lib`, { library_id: libId, quality: E.rs.effects.body?.quality || "balanced" });
    if (r.job) E.ctx.toast("इस clip का cutout बन रहा है — progress ऊपर दिखेगा"); await E.ctx.load(); E.ctx.render(); }
  catch (err) { E.ctx.toast(err.message); }
}
async function startMatte(quality) {
  try { await E.ctx.api("POST", `/projects/${E.pid}/matte`, { quality: quality || E.rs.effects.body?.quality || "balanced" }); E.ctx.toast("cutout बन रहा है — progress ऊपर दिखेगा"); await E.ctx.load(); E.ctx.render(); }
  catch (err) { E.ctx.toast(err.message); }
}
function cutKick() { if (!E) return; E.cutDirty = true; cutLoop(); }
function cutLoop() { if (!E || E.cutRaf) return; const ed = E; ed.cutRaf = requestAnimationFrame(() => { ed.cutRaf = 0; if (E !== ed) return; if (cutFrame()) cutLoop(); }); }
const near = (el, t, tol) => !el.seeking && el.readyState >= 2 && Math.abs(el.currentTime - Math.min(Math.max(0, t), (el.duration || Infinity) - 0.001)) <= tol;
// one animation frame: keep the followers on the main clock and redraw what changed → true = keep looping
function cutFrame() {
  const v = $("#pv", E.root); if (!v) return false;
  // main picture buffering (readyState < 3) → hold the followers too, so they do not run ahead
  const playing = !v.paused && !v.ended && v.readyState >= 3; const fps = E.p.meta?.fps || 30; const rate = v.playbackRate || 1; const ot = outOf(v.currentTime);
  let busy = playing; const dirty = E.cutDirty; E.cutDirty = false;
  const C = E.cut;
  if (C?.live && C.comp && C.av) {
    CUT.follow(C.av, v.currentTime, playing, rate, fps);
    const b = E.rs.effects.body || {};
    if (C.bgEl?.tagName === "VIDEO" && C.bgEl.duration) { const sp = Math.max(0.25, Math.min(4, +b.bg_speed || 1)); CUT.follow(C.bgEl, (ot * sp) % C.bgEl.duration, playing, rate * sp, fps); }
    const synced = playing ? sameFrame(v, C.av, v.currentTime, fps) : near(C.av, v.currentTime, 0.6 / fps);
    const fresh = v._vvNew || C.av._vvNew || C.bgEl?._vvNew || !v.requestVideoFrameCallback;
    if ((playing ? fresh : (dirty || C.pend)) && synced) {
      const ok = C.comp.draw({ vid: v, alpha: C.av, ...CUT.bodyState(b, ot, outDur(), C.bgEl) });
      v._vvNew = C.av._vvNew = false; if (C.bgEl) C.bgEl._vvNew = false;
      C.pend = !ok; if (!ok) busy = busy || C.av.readyState < 2;
      if (ok) { const cv = $("#pv-cut", E.root); cv.dataset.draws = (+cv.dataset.draws || 0) + 1; }
    } else if (!playing && (dirty || C.pend)) { C.pend = true; busy = busy || (!C.av.error && (C.av.seeking || !synced)); }
    else if (playing && fresh) { v._vvNew = C.av._vvNew = false; const cv = $("#pv-cut", E.root); cv.dataset.skips = (+cv.dataset.skips || 0) + 1; } // frames did not match → keep the last good composite
  }
  for (const [id, o] of E.cutOv || []) {
    const it = E.rs.effects.broll.find((x) => x._id === id); if (!it || !o.vid) continue;
    // the clip's own clock: trim_in + speed / ramp (same mapping as the render)
    const ct = Math.max(0, ot - (+it.start || 0)); const lt = (+it.trim_in || 0) + PRO.srcOffset(it, ct); const dur = it.trim_out != null && it.trim_out !== "" ? +it.trim_out : o.vid.duration || Infinity;
    o.cv.style.visibility = lt > dur ? "hidden" : ""; const crate = rate * PRO.speedAt(it, ct);
    CUT.follow(o.vid, lt, playing, crate, fps); CUT.follow(o.av, lt, playing, crate, fps);
    const synced = playing ? sameFrame(o.vid, o.av, lt, fps) && near(o.vid, lt, 0.3) : near(o.av, lt, 0.6 / fps) && near(o.vid, lt, 0.6 / fps);
    if (synced && (playing || dirty || o.pend)) { o.pend = !o.comp.draw({ vid: o.vid, alpha: o.av, edge: { shrink: +it.edge_shrink || 0, feather: +it.edge_feather || 0 } }); if (!o.pend) o.cv.dataset.draws = (+o.cv.dataset.draws || 0) + 1; }
    else if (!playing) { o.pend = true; busy = busy || (!o.av.error && !o.vid.error && (o.av.seeking || o.vid.seeking || !synced)); }
  }
  return busy;
}
// "सिर्फ़ इंसान" B-roll: persistent canvas + picture/matte videos per timeline item, re-attached when the overlay DOM is rebuilt
function cutOverlays() {
  E.cutOv = E.cutOv || new Map(); const seen = new Set();
  for (const slot of $$("#ovl-media .ov-cutslot", E.root)) {
    const id = slot.dataset.cut; const it = E.rs.effects.broll.find((x) => x._id === id); const item = it && libItem(it.id); if (!cutOn(it, item)) continue;
    seen.add(id); let o = E.cutOv.get(id);
    if (o && (o.libId !== item.id || o.alphaUrl !== item.meta.alpha.url)) { cutOvDrop(id); o = null; }
    if (!o) {
      const cv = document.createElement("canvas"); cv.className = "ov-cut";
      const k = Math.min(1, 960 / Math.max(item.meta?.width || 960, item.meta?.height || 540)); cv.width = Math.round((item.meta?.width || 960) * k); cv.height = Math.round((item.meta?.height || 540) * k);
      o = { cv, comp: CUT.compositor(cv, { overlay: true, force2d: cut2d() }), vid: hiddenVideo(item.url), av: hiddenVideo(item.meta.alpha.url), libId: item.id, alphaUrl: item.meta.alpha.url };
      cv.dataset.kind = o.comp?.kind || "none"; E.cutOv.set(id, o);
    }
    o.cv.style.cssText = slot.dataset.fit === "free" ? "width:100%;display:block" : "width:100%;height:100%;object-fit:cover;display:block";
    if (o.cv.parentNode !== slot) slot.appendChild(o.cv);
  }
  for (const id of [...E.cutOv.keys()]) if (!seen.has(id)) cutOvDrop(id);
  if (seen.size) cutKick();
}
function cutOvDrop(id) { const o = E.cutOv.get(id); if (!o) return; for (const el of [o.vid, o.av]) { el.pause(); el.removeAttribute("src"); el.load(); el.remove(); } o.comp?.destroy(); o.cv.remove(); E.cutOv.delete(id); }
function cutTeardown() {
  cancelAnimationFrame(E.cutRaf); E.cutRaf = 0;
  for (const id of [...(E.cutOv?.keys() || [])]) cutOvDrop(id);
  if (E.cut) { for (const el of [E.cut.av, E.cut.bgEl]) if (el?.tagName === "VIDEO") { el.pause(); el.removeAttribute("src"); el.load(); } E.cut.comp?.destroy(); E.cut = null; }
}

// ---------- selection / inspector ----------
function select(sel) {
  const wasCrop = cropView(); E.sel = sel; if (!(sel?.type === "video" || sel?.type === "seg")) E.cropMode = false;
  // a platform-only item (e.g. the Instagram "Follow" popup): show the preview of that platform so it can be seen/edited
  const it0 = sel?.type === "broll" ? selItem() : null; if (it0?.platforms?.length && !it0.platforms.includes(E.pvPlat || "youtube")) { E.pvPlat = it0.platforms[0]; const pp = $("#pv-plat", E.root); if (pp) pp.value = E.pvPlat; }
  E.root.classList.toggle("has-sel", !!sel); renderInspector(); renderTimeline(); if (wasCrop !== cropView()) layoutFrame(); renderOverlay(); renderHandles();
}
function selItem() {
  if (!E.sel) return null;
  const { type, id } = E.sel; const fx = E.rs.effects;
  if (type === "cut") return E.cuts.find((c) => c.id === id);
  if (type === "title") return fx.titles.find((t) => t._id === id);
  if (type === "broll") return fx.broll.find((t) => t._id === id);
  if (type === "sfx") return fx.sfx.find((t) => t._id === id);
  if (type === "caption") return captionAt(id);
  if (type === "fxclip") return (fx.fxclips || []).find((t) => t._id === id);
  if (type === "seg") return segAt(id);
  if (type === "fxglob") return id === "zoom" ? (fx.zoom?.enabled ? fx.zoom : null) : id === "transition" ? ((fx.transition || "none") !== "none" ? fx : null) : id === "grade" ? (Object.keys(fx.grade || {}).length ? fx : null) : id === "stack" ? ((fx.stack || []).length ? fx : null) : null;
  if (type === "hook") return E.rs.hook;
  if (type === "video") { fx.transform = fx.transform || {}; return fx.transform; }
  if (type === "music") return fx.music.id ? fx.music : null;
  if (type === "global") return id === "watermark" ? fx.watermark : id === "frame" ? fx.frame : { look: fx.look };
  if (type === "short") return E.shorts.find((t) => t.id === id);
  if (type === "speed") return E.speed.find((t) => t.id === id);
  return null;
}
function deleteSel() {
  if (!E.canEdit || !E.sel) return;
  const { type, id } = E.sel; const fx = E.rs.effects;
  if (type === "cut") E.cuts = E.cuts.filter((c) => c.id !== id);
  else if (type === "title") fx.titles = fx.titles.filter((t) => t._id !== id);
  else if (type === "broll") fx.broll = fx.broll.filter((t) => t._id !== id);
  else if (type === "sfx") fx.sfx = fx.sfx.filter((t) => t._id !== id);
  else if (type === "music") fx.music.id = "";
  else if (type === "hook") E.rs.hook.text = "";
  else if (type === "global") { if (id === "watermark") fx.watermark.id = ""; else if (id === "frame") fx.frame = { id: "", opacity: 1 }; else fx.look = "none"; }
  else if (type === "short") { E.shorts = E.shorts.filter((t) => t.id !== id); E.shortsDirty = true; }
  else if (type === "speed") E.speed = E.speed.filter((t) => t.id !== id);
  else if (type === "caption") { const c = captionAt(id); if (!c) return; deleteWords(c.words); }
  else if (type === "fxclip") fx.fxclips = (fx.fxclips || []).filter((t) => t._id !== id);
  else if (type === "seg") { const s = segAt(id); if (!s) return; E.cuts.push({ id: uid(), start: +s.a.toFixed(3), end: +s.b.toFixed(3), reason: "manual", enabled: true, text: "" }); E.splits = E.splits.filter((x) => Math.abs(x - s.a) > 0.01 && Math.abs(x - s.b) > 0.01); }
  else if (type === "fxglob") { if (id === "zoom") fx.zoom.enabled = false; else if (id === "transition") { fx.transition = "none"; fx.flash = false; } else if (id === "grade") { fx.grade = {}; fx.grade_preset = ""; } else if (id === "stack") fx.stack = []; layoutFrame(); }
  else return;
  touch(); select(null); if (["caption", "fxclip", "fxglob"].includes(type)) renderPanel();
}
function snapshot() { return JSON.stringify({ rs: E.rs, cuts: E.cuts, shorts: E.shorts, speed: E.speed, splits: E.splits, tr: E.tr.segments }); }
function restore(snap) { const o = JSON.parse(snap); const trChanged = JSON.stringify(o.tr) !== JSON.stringify(E.tr.segments);
  E.rs = o.rs; E.cuts = o.cuts; E.shorts = o.shorts; E.speed = o.speed || []; E.splits = o.splits || []; if (o.tr) { E.tr.segments = o.tr; syncWords(); if (trChanged) E.transcriptDirty = true; }
  E.shortsDirty = true; E.sel = null; E.last = snap; E.dirty = true; E.ver++; clearTimeout(E.saveT); E.saveT = setTimeout(() => save(false), 800); renderPanel(); renderInspector(); renderTimeline(); layoutFrame(); renderOverlay(); updateHistoryButtons(); }
function updateHistoryButtons() { const u = $("#ed-undo", E.root), r = $("#ed-redo", E.root); if (u) u.disabled = !E.hist.length; if (r) r.disabled = !E.redo.length; }
// a change made < 400 ms ago is still waiting to become a history step: settle it first (else undo/redo skip it or lose redo)
function commitHist() { clearTimeout(E.histT); if (E.histPending != null && E.histPending !== snapshot()) { E.hist.push(E.histPending); if (E.hist.length > 60) E.hist.shift(); E.redo = []; } E.histPending = null; updateHistoryButtons(); }
function undo() { commitHist(); if (!E.hist.length) return; E.redo.push(snapshot()); restore(E.hist.pop()); }
function redo() { commitHist(); if (!E.redo.length) return; E.hist.push(snapshot()); restore(E.redo.pop()); }
function touch() {
  const now = snapshot(); if (E.last == null) E.last = now;
  if (now !== E.last) { clearTimeout(E.histT); if (!E.histPending) { E.histPending = E.last; } E.histT = setTimeout(() => { if (E.histPending != null && E.histPending !== snapshot()) { E.hist.push(E.histPending); if (E.hist.length > 60) E.hist.shift(); E.redo = []; updateHistoryButtons(); } E.histPending = null; }, 400); E.last = now; }
  E.dirty = true; E.ver++; $("#ed-save", E.root).textContent = "बदलाव सेव हो रहे…"; clearTimeout(E.saveT); E.saveT = setTimeout(() => save(false), 1500); renderTimeline(); renderOverlay(); }
// Saves run one after another (never two PATCHes in flight — an older one finishing last would put old edits back).
function save(loud) {
  if (!E || !E.canEdit) return Promise.resolve(true);
  const ed = E; clearTimeout(ed.saveT);
  ed.saveQ = (ed.saveQ || Promise.resolve(true)).then(() => doSave(ed, loud));
  return ed.saveQ;
}
// Everything the user did so far is on the server (used before render / shorts / AI calls).
async function flush() { if (!E) return true; const ed = E; clearTimeout(ed.saveT); if (ed.saveQ) await ed.saveQ; if (ed.dirty || ed.transcriptDirty || ed.shortsDirty) return save(false); return true; }
async function doSave(ed, loud) {
  const { api, toast } = ed.ctx; const live = () => E === ed;
  if (ed.locked) return false;
  const ver = ed.ver; const rs = JSON.parse(JSON.stringify(ed.rs));
  const body = { settings: { render: rs }, edl: { cuts: ed.cuts, speed: ed.speed, splits: ed.splits } };
  const sentShorts = ed.shortsDirty, sentTr = ed.transcriptDirty;
  if (sentShorts) body.meta = { shorts: ed.shorts };
  // rev = the transcript version these edits started from (server merges re-listened lines into it)
  if (sentTr) { body.transcript = JSON.parse(JSON.stringify(ed.tr)); if (ed.tr.rev != null) body.rev = ed.tr.rev; }
  ed.saving = true;
  try {
    const p = await api("PATCH", `/projects/${ed.pid}`, body);
    if (sentShorts) { ed.shortsSeen = JSON.stringify(p.meta?.shorts || ed.shorts); if (ed.ver === ver) ed.shortsDirty = false; }
    if (sentTr) { ed.trSrv = JSON.stringify(p.transcript?.segments || []); if (p.transcript?.rev != null) ed.tr.rev = p.transcript.rev;
      if (JSON.stringify(ed.tr.segments) === JSON.stringify(body.transcript.segments)) ed.transcriptDirty = false;
      // the server merged re-listened lines into our edit → take its result if nothing changed meanwhile
      if (!ed.transcriptDirty && trCanon(p.transcript?.segments) !== trCanon(body.transcript.segments)) { ed.tr = JSON.parse(JSON.stringify(p.transcript)); ed.tr.segments = ed.tr.segments || []; if (live()) { syncWords(); renderTimeline(); renderOverlay(); } } }
    ed.p = p;
    if (ed.ver === ver) ed.dirty = false;
    ed.savedVer = ver;
    if (live()) { $("#ed-save", ed.root).textContent = ed.dirty ? "बदलाव सेव हो रहे…" : "सेव ✓"; if (loud) toast("सेव हुआ"); }
    return true;
  } catch (err) { if (live()) { $("#ed-save", ed.root).textContent = "सेव नहीं हुआ"; toast("सेव नहीं हुआ: " + err.message); } return false; }
  finally { ed.saving = false; }
}
function field(label, inner) { return `<div class="ifield"><label>${label}</label>${inner}</div>`; }
function num(id, v, step = 0.1, min = 0, max = 9999) { return `<input type="number" data-k="${id}" value="${(+v).toFixed(step < 1 ? 2 : 0)}" step="${step}" min="${min}" max="${max}">`; }
function renderInspector() {
  const ins = $("#inspector", E.root); const { esc } = E.ctx; let it = selItem(); const dis = E.canEdit ? "" : "disabled";
  if (!E.sel || !it) {
    if (E.montage) { ins.innerHTML = `<h3>Montage</h3><div class="ikv"><span>लंबाई</span><b>${fmt(E.p.meta?.duration || 0)}</b></div><div class="ikv"><span>BPM</span><b>${E.p.meta?.bpm || "—"}</b></div><div class="ikv"><span>cuts</span><b>${E.p.meta?.segments || "—"}</b></div><p class="small muted" style="margin-top:1rem">clips/music/text बाएँ panel में बदलकर "Montage बनाएँ" दबाएँ; फिर Export से download/publish।</p>`; return; }
    ins.innerHTML = `<h3>Project</h3><div class="ikv"><span>लंबाई</span><b>${fmt(E.dur)} → ${fmt(outDur())}</b></div><div class="ikv"><span>कट</span><b>${E.cuts.filter((c) => c.enabled !== false).length}</b></div>
      <div class="ikv"><span>भाषा</span><b>${{ hi: "हिंदी", en: "English", auto: "पहचान बाकी" }[E.p.language] || E.p.language}</b></div><div class="ikv"><span>source</span><b>${E.p.meta?.width}×${E.p.meta?.height} · ${E.p.meta?.fps} fps</b></div>
      <p class="small muted" style="margin-top:1rem">timeline पर किसी कट, caption, title या B-roll पर क्लिक करें — उसकी settings यहाँ आएँगी।<br><br><b>Keys:</b> Space चलाएँ · I/O हिस्सा चुनें · X हटाएँ · ←/→ frame · Del चुना हुआ हटाएँ · Ctrl+Z/Y undo/redo · Ctrl+S सेव · M marker · K keyframe · <b>?</b> सारे shortcuts</p>
      ${autopilotBox()}
      <div class="sugg" id="sugg"><div class="row between"><b>💡 क्या कमी है</b><button class="btn small quiet" id="sugg-load">जाँचें</button></div><div id="sugg-list" class="small muted">वीडियो की रोशनी, रंग, आवाज़ और editing जाँचकर सुझाव…</div></div>
      <details id="hist"><summary class="small muted">Version history</summary><ul class="plist" id="hist-list"><li class="small muted">लोड…</li></ul></details>`;
    $$("[data-apdel]", ins).forEach((b) => (b.onclick = () => { if (!E.canEdit) return; apRemove(b.dataset.apdel); E.ctx.toast("हटाया (Ctrl+Z से वापस)"); }));
    $$("[data-apgo]", ins).forEach((b) => (b.onclick = async () => { const mode = b.dataset.apgo;
      if (mode === "clear") { if (!E.canEdit) return; const fx = E.rs.effects; let n = 0; for (const k of ["broll", "titles", "sfx"]) { const before = fx[k].length; fx[k] = fx[k].filter((x) => !isAp(x)); n += before - fx[k].length; } if (E.sel && !selItem()) E.sel = null; touch(); renderInspector(); renderOverlay(); renderPanel(); return E.ctx.toast(`autopilot के ${n} items हटाए (Ctrl+Z से वापस)`); }
      if (mode === "all" && !confirm("Autopilot सारी settings (caption style, music, zoom, color, voice…) फिर से चुनेगा। आपके हाथ से जोड़े items रहेंगे। आगे बढ़ें?")) return;
      try { await flush(); await E.ctx.api("POST", `/projects/${E.pid}/autopilot/apply`, { mode }); const ctx = E.ctx; unmount(); await ctx.load(); ctx.render(); ctx.toast("Autopilot की editing लगी — timeline देखें"); } catch (e) { E.ctx.toast(e.message); } }));
    const sl = $("#sugg-load", ins); if (sl) { sl.onclick = () => loadSuggestions(true); loadSuggestions(false); }
    const hd = $("#hist", ins); if (hd) hd.ontoggle = async () => { if (!hd.open) return; try { const rows = await E.ctx.api("GET", `/projects/${E.pid}/history`); $("#hist-list", ins).innerHTML = rows.map((r) => `<li><span class="grow small">${esc(r.note || "")}<br><span class="muted">${new Date(r.created_at).toLocaleString("hi-IN")} · ${esc(r.user_name || "")}</span></span>${E.canEdit ? `<button class="btn small quiet" data-hr="${r.id}">वापस</button>` : ""}</li>`).join("") || `<li class="small muted">अभी कोई पुराना version नहीं</li>`;
      $$("[data-hr]", ins).forEach((b) => (b.onclick = async () => { if (!confirm("इस version पर वापस जाएँ? (अभी वाला भी history में रहेगा)")) return; await E.ctx.api("POST", `/projects/${E.pid}/history/${b.dataset.hr}/restore`); const ctx = E.ctx; unmount(); await ctx.load(); ctx.render(); })); } catch (e) { $("#hist-list", ins).innerHTML = `<li class="small muted">${esc(e.message)}</li>`; } };
    return;
  }
  const { type } = E.sel; let h = "";
  const segHead = type === "seg" ? `<h3>Main video clip</h3><p class="small muted">${fmt(it.a)} – ${fmt(it.b)} · ✂ split से बना हिस्सा</p><div class="irow"><button class="btn small" data-act="seek">यहाँ जाएँ</button><button class="btn small danger quiet" data-act="del" ${dis}>${ICON.trash} यह हिस्सा हटाएँ</button></div><hr>` : "";
  const segIt = it; if (type === "seg") { E.rs.effects.transform = E.rs.effects.transform || {}; it = E.rs.effects.transform; }
  if (type === "cut") {
    h = `<h3>कट <span class="tag ${it.reason}">${{ silence: "चुप्पी", filler: "अं-आं", retake: "दोबारा बोला", manual: "आपका" }[it.reason] || it.reason}</span></h3>
      ${it.text ? `<p class="small muted">“${esc(it.text)}”</p>` : ""}
      <div class="irow">${field("से", num("start", it.start, 0.05, 0, E.dur))}${field("तक", num("end", it.end, 0.05, 0, E.dur))}</div>
      <label class="chk"><input type="checkbox" data-k="enabled" ${it.enabled !== false ? "checked" : ""} ${dis}> यह हिस्सा हटेगा</label>
      <label class="chk" title="jump cut को optical-flow से smooth करें (Pro → Morph cut की settings)"><input type="checkbox" data-morph ${it.morph === true || (it.morph !== false && E.rs.effects.pro?.morph_cut?.enabled && E.rs.effects.pro?.morph_cut?.all) ? "checked" : ""} ${dis}> 🌗 Morph cut (smooth jump cut)</label>
      ${field("इस कट पर transition", `<select data-k="transition" ${dis}><option value="">default (${esc((E.ctx.S.presets?.transitions || []).find((t) => t.id === (E.rs.effects.transition || "none"))?.label || "none")})</option>${(E.ctx.S.presets?.transitions || []).map((t) => `<option value="${t.id}" ${it.transition === t.id ? "selected" : ""}>${esc(t.label)}</option>`).join("")}</select>`)}
      <div class="irow"><button class="btn small" data-act="seek">यहाँ जाएँ</button><button class="btn small danger quiet" data-act="del">${ICON.trash} कट मिटाएँ</button></div>`;
  } else if (type === "title") {
    h = titleInspector(it, dis);
  } else if (type === "hook") {
    h = `<h3>Heading / Hook</h3><p class="small muted">शुरू के कुछ सेकंड वीडियो पर बड़ा दिखता है।</p>${field("लिखें ( | से नई लाइन )", `<textarea data-k="text" rows="2" ${dis}>${esc(it.text || "")}</textarea>`)}
      <div class="irow">${field("कितने सेकंड", num("seconds", it.seconds || 3, 0.5, 1, 15))}${field("जगह", `<select data-k="position" ${dis}>${["top", "center", "bottom"].map((p) => `<option value="${p}" ${(it.position || "top") === p ? "selected" : ""}>${{ top: "ऊपर", center: "बीच", bottom: "नीचे" }[p]}</option>`).join("")}</select>`)}</div>
      <div class="irow">${field("आकार", `<input type="range" data-k="size_scale" min="0.5" max="1.8" step="0.05" value="${it.size_scale || 1}" ${dis}>`)}${field("font", `<select data-k="font" ${dis}><option value="">style जैसा</option>${fontList().map((f) => `<option ${it.font === f ? "selected" : ""}>${f}</option>`).join("")}</select>`)}</div>
      <div class="irow">${field("अक्षर रंग", `<input type="color" data-k="color" value="${it.color || "#111111"}" ${dis}>`)}${field("पीछे का रंग", `<input type="color" data-k="bg" value="${it.bg || "#FFD400"}" ${dis}>`)}<label class="chk small"><input type="checkbox" data-k="italic" ${it.italic ? "checked" : ""} ${dis}> <i>italic</i></label></div>
      <div class="irow"><button class="btn small" data-act="seek0">शुरू पर जाएँ</button><button class="btn small danger quiet" data-act="del">${ICON.trash} हटाएँ</button></div>`;
  } else if (type === "video" || type === "seg") {
    const c = it.crop || { x: 0, y: 0, w: 1, h: 1 }; const rng = (k, l, min, max, step, def, path) => field(`${l} <b>${(+((path ? c[k] : it[k]) ?? def)).toFixed(2)}</b>`, `<input type="range" data-tf="${path ? "crop." : ""}${k}" min="${min}" max="${max}" step="${step}" value="${(path ? c[k] : it[k]) ?? def}" ${dis}>`);
    h = segHead + `<h3>Main video</h3><p class="small muted">पूरी recording पर लागू · preview पर सीधे: बीच से खींचें = जगह, कोने = size, ऊपर का गोला = घुमाव</p><div class="irow"><button class="btn small ${E.cropMode ? "primary" : ""}" data-act="cropmode" ${dis}>⌗ ${E.cropMode ? "Crop पूरा" : "Preview पर crop करें"}</button></div>
      <details open class="insp"><summary>Position & Size ${it.kf && Object.keys(it.kf).length ? `<span class="tag">◆ ${Object.keys(it.kf).length}</span>` : ""}</summary>${(() => { const mo = PRO.mainOwner(); return ["scale", "x", "y", "rotation", "opacity"].map((p) => PRO.kfSlider(mo, p, dis)).join(""); })()}
        <p class="small muted">◆ = keyframe (zoom-in, pan, fade)। keyframe होने पर preview पर खींचना भी keyframe बनाता है। <b>K</b> = सब एक साथ।</p>
        ${it.kf && Object.keys(it.kf).length ? `<details class="insp sub" open><summary>Keyframes</summary>${PRO.kfListHtml(E.sel, dis)}</details>` : ""}
        ${field("खाली जगह", `<select data-tf="bg" ${dis}>${[["blur", "Blur"], ["black", "काला"], ["color", "रंग"]].map(([v, l]) => `<option value="${v}" ${(it.bg || "blur") === v ? "selected" : ""}>${l}</option>`).join("")}</select>`)}${it.bg === "color" ? field("रंग", `<input type="color" data-tf="bg_color" value="${it.bg_color || "#000000"}" ${dis}>`) : ""}</details>
      <details open class="insp"><summary>Crop</summary><div class="chips">${[["free", "Free"], ["9:16", "9:16"], ["16:9", "16:9"], ["1:1", "1:1"], ["4:5", "4:5"], ["reset", "Reset"]].map(([v, l]) => `<button data-cropr="${v}" ${dis}>${l}</button>`).join("")}</div>
        <div class="irow">${rng("x", "बाएँ", 0, 0.9, 0.01, 0, 1)}${rng("y", "ऊपर", 0, 0.9, 0.01, 0, 1)}</div><div class="irow">${rng("w", "चौड़ाई", 0.1, 1, 0.01, 1, 1)}${rng("h", "ऊँचाई", 0.1, 1, 0.01, 1, 1)}</div></details>
      <details open class="insp"><summary>Rotate & Mirror</summary><div class="irow">${[0, 90, 180, 270].map((r) => `<button class="btn small ${(+it.rotate || 0) === r ? "primary" : "quiet"}" data-rot="${r}" ${dis}>${r}°</button>`).join("")}</div>
        <div class="irow"><label class="chk small"><input type="checkbox" data-tf="flip_h" ${it.flip_h ? "checked" : ""} ${dis}> ⇋ Mirror</label><label class="chk small"><input type="checkbox" data-tf="flip_v" ${it.flip_v ? "checked" : ""} ${dis}> ⇅ Flip</label></div></details>
      <div class="irow"><button class="btn small quiet" data-act="tfreset" ${dis}>सब reset</button><button class="btn small" data-act="fxtab" data-tabto="pro" title="colour wheels, mask, stabilise, denoise, face refine, morph cut">🎛 Pro tools</button></div>`;
  } else if (type === "music") {
    h = `<h3>Background music</h3><p class="small muted">${esc(libItem(it.id)?.name || "")}</p>
      <div class="irow">${field("volume", `<input type="range" data-k="volume" min="0" max="1" step="0.01" value="${it.volume ?? 0.18}" ${dis}>`)}${field("fade (s)", `<input type="range" data-k="fade" min="0" max="6" step="0.5" value="${it.fade ?? 1.5}" ${dis}>`)}</div>
      <div class="irow"><label class="chk small"><input type="checkbox" data-k="duck" ${it.duck !== false ? "checked" : ""} ${dis}> बोलते समय धीमा</label>${field("कितना", `<input type="range" data-k="duck_amount" min="0.1" max="1" step="0.05" value="${it.duck_amount ?? 0.6}" ${dis}>`)}</div>
      <div class="irow"><button class="btn small" data-act="audiotab">🎙 आवाज़ settings</button><button class="btn small danger quiet" data-act="del">${ICON.trash} हटाएँ</button></div>`;
  } else if (type === "global") {
    const id = E.sel.id;
    if (id === "watermark") h = `<h3>Logo / Watermark</h3><p class="small muted">${esc(libItem(it.id)?.name || "")} · पूरे वीडियो पर</p>
      <div class="irow">${field("पारदर्शिता", `<input type="range" data-k="opacity" min="0.1" max="1" step="0.05" value="${it.opacity ?? 0.7}" ${dis}>`)}${field("आकार", `<input type="range" data-k="size" min="0.05" max="0.35" step="0.01" value="${it.size ?? 0.12}" ${dis}>`)}</div>
      ${field("कोना", `<select data-k="pos" ${dis}>${["tr", "tl", "br", "bl"].map((p) => `<option value="${p}" ${it.pos === p ? "selected" : ""}>${{ tr: "ऊपर दाएँ", tl: "ऊपर बाएँ", br: "नीचे दाएँ", bl: "नीचे बाएँ" }[p]}</option>`).join("")}</select>`)}`;
    else if (id === "frame") h = `<h3>Frame / Border</h3><p class="small muted">${esc(libItem(it.id)?.name || "")} · पूरे वीडियो पर</p>${field("opacity", `<input type="range" data-k="opacity" min="0.2" max="1" step="0.05" value="${it.opacity ?? 1}" ${dis}>`)}`;
    else h = `<h3>Color look</h3><p class="small muted">${esc(it.look?.startsWith("lut:") ? libItem(it.look.slice(4))?.name || "LUT" : it.look)} · पूरे वीडियो पर। Color tab में और settings।</p>`;
    h += `<div class="irow"><button class="btn small danger quiet" data-act="del">${ICON.trash} हटाएँ</button></div>`;
  } else if (type === "broll") {
    h = PRO.brollInspector(it, dis);   // overlay clip: speed / ramps / trim / colour / effects / blend / mask / keyframes / own audio
  } else if (type === "sfx") {
    const item = libItem(it.id);
    h = `<h3>${item?.kind === "music" ? "Audio clip" : "SFX / Audio"}</h3><p class="small muted">${esc(item?.name || "?")}${item?.meta?.duration ? " · " + fmt(item.meta.duration) : ""}</p><div class="irow">${field("कब", num("at", it.at, 0.05, 0))}${field("आवाज़", `<input type="range" data-k="volume" min="0" max="2" step="0.05" value="${it.volume ?? 0.8}" ${dis}>`)}</div>
      <div class="irow">${field("कितनी देर (s, खाली = पूरा)", `<input type="number" data-k="dur" min="0" step="0.1" value="${it.dur || ""}" placeholder="पूरा" ${dis}>`)}${field("शुरू से काटें (s)", num("trim", it.trim || 0, 0.1, 0))}${field("track", num("track", it.track || 0, 1, 0, 9))}</div>
      <div class="irow">${field("fade in (s)", num("fade_in", it.fade_in || 0, 0.1, 0, 10))}${field("fade out (s)", num("fade_out", it.fade_out || 0, 0.1, 0, 10))}<label class="chk small"><input type="checkbox" data-k="duck" ${it.duck ? "checked" : ""} ${dis}> बोलते समय धीमा</label></div>
      <div class="irow"><button class="btn small" data-act="seek">यहाँ जाएँ</button><button class="btn small danger quiet" data-act="del">${ICON.trash} हटाएँ</button></div>`;
  } else if (type === "speed") {
    h = `<h3>Speed <span class="tag manual">${it.rate}×</span></h3><div class="irow">${field("से", num("start", it.start, 0.1, 0, E.dur))}${field("तक", num("end", it.end, 0.1, 0, E.dur))}</div>
      ${field("rate", `<input type="range" data-k="rate" min="0.25" max="4" step="0.05" value="${it.rate}" ${dis}>`)}<p class="small muted">आवाज़ pitch वही रहती है (atempo)। 1 से कम = slow motion।</p>
      <div class="irow"><button class="btn small" data-act="seek">यहाँ जाएँ</button><button class="btn small danger quiet" data-act="del">${ICON.trash} हटाएँ</button></div>`;
  } else if (type === "short") {
    h = `<h3>Short <span class="tag manual">${(it.end - it.start).toFixed(0)}s</span></h3>
      ${field("Title (YouTube)", `<input data-k="title" value="${esc(it.title || "")}" ${dis}>`)}
      ${field("Hook (वीडियो पर 3s)", `<input data-k="hook" value="${esc(it.hook || "")}" ${dis}>`)}
      <div class="irow">${field("से", num("start", it.start, 0.1, 0, E.dur))}${field("तक", num("end", it.end, 0.1, 0, E.dur))}</div>
      <label class="chk"><input type="checkbox" data-k="selected" ${it.selected !== false ? "checked" : ""} ${dis}> render में शामिल</label>
      ${it.text ? `<p class="small muted" style="max-height:120px;overflow:auto">${esc(it.text)}</p>` : ""}
      <div class="irow"><button class="btn small" data-act="seek">यहाँ जाएँ</button><button class="btn small quiet" data-act="playshort">यह Short चलाएँ</button><button class="btn small danger quiet" data-act="del">${ICON.trash} हटाएँ</button></div>`;
  } else if (type === "caption") {
    const busy = rangeBusy(it.start, it.end); const seg = segOfWord(it.words[0]);
    h = `<h3>Caption</h3><p class="small muted">${fmt(it.start)} – ${fmt(it.end)} (recording का समय)</p>${field("शब्द सुधारें (लिखते ही preview में)", `<textarea data-k="_captext" rows="3" ${dis} ${busy ? "disabled" : ""}>${esc(it.words.map((w) => w.w).join(" "))}</textarea>`)}
      <p class="small muted">शब्दों की गिनती वही रखें तो timing सटीक रहती है। सब मिटा दें = यह caption हटेगा।</p>
      ${busy ? `<p class="small"><span class="spin"></span> यह line दोबारा सुनी जा रही है…</p>` : ""}${altsHtml(seg, dis)}
      <div class="irow"><button class="btn small" data-act="seek">यहाँ जाएँ</button><button class="btn small" data-act="relisten" ${dis} ${busy ? "disabled" : ""}>🔄 दोबारा सुनो</button><button class="btn small danger quiet" data-act="del" ${dis}>${ICON.trash} caption हटाएँ</button></div>`;
  } else if (type === "fxclip") {
    h = fxClipInspector(it, dis);
  } else if (type === "fxglob") {
    const id = E.sel.id; const fx = E.rs.effects;
    h = `<h3>${{ zoom: "Auto zoom", transition: "Transition (हर कट पर)", grade: "Filter (पूरे वीडियो पर)", stack: "Effects (पूरे वीडियो पर)" }[id]}</h3><p class="small muted">${id === "zoom" ? `pattern: ${esc(fx.zoom.mode || "punch")} · कितना ${fx.zoom.strength}` : id === "transition" ? esc((E.ctx.S.presets?.transitions || []).find((t) => t.id === fx.transition)?.label || fx.transition) : id === "grade" ? esc(E.ctx.S.presets?.catalog?.grade_presets?.[fx.grade_preset]?.label || "custom grade") : (fx.stack || []).map((s) => esc(fxDef(s.id)?.label || s.id)).join(", ")}</p>
      <div class="irow"><button class="btn small" data-act="fxtab" data-tabto="${{ zoom: "effects", transition: "transitions", grade: "color", stack: "effects" }[id]}">बदलें</button><button class="btn small danger quiet" data-act="del" ${dis}>${ICON.trash} हटाएँ</button></div>`;
  }
  ins.innerHTML = h;
  $$("[data-k]", ins).forEach((el) => (el.oninput = el.onchange = () => {
    if (!E.canEdit) return;
    const k = el.dataset.k;
    if (k === "_bgon") { it.bg = el.checked ? ($('[data-k="bg"]', ins).value) : ""; }
    else if (k === "_bold") { it.bold = el.checked; }
    else if (k === "_outline") { it.outline_w = el.checked ? (it.outline_w || 0.006) : 0; if (el.checked && !it.outline) it.outline = "#000000"; }
    else if (k === "_shadow") { if (el.checked) { it.shadow = it.shadow || "#000000"; it.shadow_d = it.shadow_d || 0.004; } else { it.shadow = ""; it.shadow_d = 0; } }
    else if (type === "title" && ["in_ms", "out_ms", "loop_ms"].includes(k)) { it[k] = el.value ? +el.value : ""; }
    else if (k === "_kf") { if (el.checked) it.to = { x: it.x ?? 0.5, y: it.y ?? 0.5, scale: it.scale ?? 0.4 }; else delete it.to; touch(); renderInspector(); return; }
    else if (k === "_captext") { clearTimeout(E.capT); const ws = el._ws || it.words; E.capT = setTimeout(() => { if (!E) return; const nw = applyCaptionText({ words: ws }, el.value, true); el._ws = nw; if (nw.length) E.sel = { type: "caption", id: nw[0].start }; if (E.tab === "captions") renderPanel(); }, 350); return; }
    else if (k.startsWith("to.")) { it.to = it.to || {}; it.to[k.slice(3)] = +el.value; }
    else if (el.type === "checkbox") it[k] = el.checked;
    else if (el.type === "number" || el.type === "range") it[k] = +el.value;
    else it[k] = el.value;
    if (k === "fit" || k === "blend") { touch(); renderInspector(); return; }
    if (k === "cutout") { touch(); if (it.cutout) ensureLibMatte(it.id); renderInspector(); return; }
    if (type === "title" && ["pos", "box", "_outline", "_shadow"].includes(k)) { touch(); renderInspector(); return; }
    if (el.type === "range") { const lb = el.closest(".ifield")?.querySelector("label b"); if (lb) lb.textContent = (+el.value).toFixed(+el.step < 0.01 ? 3 : +el.step < 1 ? 2 : 0); }
    if (k === "bg" && type !== "hook" && !$('[data-k="_bgon"]', ins).checked) it.bg = "";
    if (type === "cut" || type === "short" || type === "speed") { it.start = clamp(it.start, 0, E.dur); it.end = clamp(it.end, it.start + 0.05, E.dur); }
    if (type === "short") E.shortsDirty = true;
    touch();
  }));
  $$("[data-plat]", ins).forEach((el) => (el.onchange = () => { if (!E.canEdit) return; it.platforms = $$("[data-plat]", ins).filter((x) => x.checked).map((x) => x.dataset.plat); if (!it.platforms.length) delete it.platforms; touch(); renderOverlay(); renderTimeline(); }));
  $$("[data-tf]", ins).forEach((el) => (el.oninput = el.onchange = () => { if (!E.canEdit) return; const k = el.dataset.tf; const v = el.type === "checkbox" ? el.checked : el.type === "range" ? +el.value : el.value;
    if (k.startsWith("crop.")) { it.crop = { x: 0, y: 0, w: 1, h: 1, ...(it.crop || {}) }; it.crop[k.slice(5)] = v; it.crop.w = Math.min(it.crop.w, 1 - it.crop.x); it.crop.h = Math.min(it.crop.h, 1 - it.crop.y); } else it[k] = v;
    const lb = el.closest(".ifield")?.querySelector("label b"); if (lb && el.type === "range") lb.textContent = (+el.value).toFixed(2); applyVideoCss(); touch(); if (k === "bg") renderInspector(); }));
  $$("[data-cropr]", ins).forEach((b) => (b.onclick = () => { const r = b.dataset.cropr; const vw = E.p.meta?.width || 1280, vh = E.p.meta?.height || 720;
    if (r === "reset" || r === "free") { it.crop = r === "reset" ? null : { x: 0.05, y: 0.05, w: 0.9, h: 0.9 }; }
    else { const [a, c] = r.split(":").map(Number); const tr = a / c, sr = vw / vh; it.crop = tr < sr ? { w: +(tr / sr).toFixed(3), h: 1, x: +((1 - tr / sr) / 2).toFixed(3), y: 0 } : { w: 1, h: +(sr / tr).toFixed(3), x: 0, y: +((1 - sr / tr) / 2).toFixed(3) }; }
    touch(); applyVideoCss(); renderInspector(); }));
  $$("[data-rot]", ins).forEach((b) => (b.onclick = () => { it.rotate = +b.dataset.rot; touch(); applyVideoCss(); renderInspector(); }));
  bindAlts(ins);
  bindFxClipInspector(ins, it);
  if (type === "broll") PRO.bindBrollInspector(ins, it);
  if (type === "video" || type === "seg") { PRO.bindKf(ins, () => applyVideoCss()); PRO.bindKfList(ins); }
  const mc = $("[data-morph]", ins); if (mc) mc.onchange = () => { if (!E.canEdit) return; const g = E.rs.effects.pro?.morph_cut || {};
    if (mc.checked) it.morph = true; else if (g.enabled && g.all) it.morph = false; else delete it.morph; touch(); renderTimeline(); if (E.tab === "cuts") renderPanel(); };
  const lm = $("[data-libmatte]", ins); if (lm) lm.onclick = () => { lm.disabled = true; ensureLibMatte(lm.dataset.libmatte, true); };
  $$("[data-act]", ins).forEach((b) => (b.onclick = () => {
    const a = b.dataset.act;
    if (a === "del") deleteSel();
    else if (a === "seek0") seek(0);
    else if (a === "tfreset") { E.rs.effects.transform = {}; touch(); applyVideoCss(); select({ type: "video", id: "main" }); }
    else if (a === "tplay") { seek(srcOf(it.start)); E.stopAt = srcOf(it.end); $("#pv", E.root).play(); }
    else if (a === "tdup") { const c = { ...JSON.parse(JSON.stringify(it)), _id: uid(), start: it.end, end: +Math.min(outDur(), it.end + (it.end - it.start)).toFixed(2) }; E.rs.effects.titles.push(c); touch(); select({ type: "title", id: c._id }); }
    else if (a === "audiotab") { E.tab = "audio"; renderPanel(); document.querySelectorAll?.("[data-tab]").forEach((x) => x.classList.toggle("on", x.dataset.tab === "audio")); }
    else if (a === "seek") seek(type === "seg" ? segIt.a : type === "cut" || type === "short" || type === "speed" ? it.start : type === "caption" ? it.start : srcOf(it.start ?? it.at));
    else if (a === "playshort") { seek(it.start); E.stopAt = it.end; $("#pv", E.root).play(); }
    else if (a === "captext") applyCaptionText(it, $('[data-k="_captext"]', ins).value);
    else if (a === "relisten") relisten([{ start: it.start, end: it.end }]);
    else if (a === "fxtab") { E.tab = b.dataset.tabto; $$(".ed-tabs button", E.root).forEach((x) => x.classList.toggle("on", x.dataset.tab === E.tab)); renderPanel(); }
    else if (a === "fxglobal") { fxClipToGlobal(it); }
    else if (a === "cropmode") { E.cropMode = !E.cropMode; if (E.cropMode && !E.rs.effects.transform?.crop) { E.rs.effects.transform = E.rs.effects.transform || {}; E.rs.effects.transform.crop = { x: 0, y: 0, w: 1, h: 1 }; } renderInspector(); layoutFrame(); renderOverlay(); }
  }));
}
// New wording for one caption line (its words are objects inside E.tr). Empty text = delete the line.
// Returns the line's words after the change (callers keep editing the same line with it).
function applyCaptionText(chunk, text, quiet) {
  if (!chunk || !chunk.words?.length || !E.canEdit) return chunk?.words || [];
  const parts = String(text).trim().split(/\s+/).filter(Boolean);
  const ws = liveWords(chunk.words); if (!ws.length) return [];
  if (!parts.length) { deleteWords(ws); touch(); afterTranscriptEdit(quiet, "caption हटाया"); return []; }
  if (parts.length === ws.length && parts.every((p, i) => p === ws[i].w)) return ws;
  let out = ws;
  if (parts.length === ws.length) ws.forEach((w, i) => (w.w = parts[i]));
  else {
    const s = ws[0].start, e = ws[ws.length - 1].end; const step = (e - s) / parts.length;
    out = parts.map((p, i) => ({ w: p, start: +(s + i * step).toFixed(3), end: +(s + (i + 1) * step).toFixed(3) }));
    // the line may span two transcript segments: take its words out everywhere, put the new ones where it began
    const seg0 = segOfWord(ws[0]); const at = seg0 ? seg0.words.indexOf(ws[0]) : -1; const drop = new Set(ws);
    for (const seg of E.tr.segments) if (seg !== seg0) seg.words = (seg.words || []).filter((w) => !drop.has(w));
    if (seg0) { seg0.words = seg0.words.filter((w, i) => i < at || !drop.has(w)); seg0.words.splice(at, 0, ...out); }
    E.tr.segments = E.tr.segments.filter((sg) => !sg.words || sg.words.length);
  }
  for (const seg of E.tr.segments) if (seg.words?.length) { seg.text = seg.words.map((w) => w.w).join(" "); seg.start = Math.min(seg.start ?? seg.words[0].start, seg.words[0].start); seg.end = Math.max(seg.end ?? 0, seg.words[seg.words.length - 1].end); }
  syncWords(); E.transcriptDirty = true; touch(); afterTranscriptEdit(quiet, "caption बदला");
  return out;
}
// a re-listened segment may come with 2–3 candidate texts → one click picks one
function altsHtml(seg, dis) {
  const alts = (seg?.alts || []).map((a) => (typeof a === "string" ? a : a?.text)).filter(Boolean);
  if (!alts.length) return ""; const { esc } = E.ctx; const i = E.tr.segments.indexOf(seg);
  return `<div class="alts"><span class="small muted">दूसरे विकल्प:</span>${alts.map((a, k) => `<button class="btn small quiet altbtn" data-alt="${i}:${k}" ${dis} title="ये सही है">✓ ${esc(a)}</button>`).join("")}<button class="btn small quiet" data-alt="${i}:x" ${dis} title="अभी वाला ही ठीक है">✕</button></div>`;
}
function bindAlts(root) {
  $$("[data-alt]", root).forEach((b) => (b.onclick = (e) => { e.stopPropagation(); if (!E.canEdit) return; const [i, k] = b.dataset.alt.split(":"); const seg = E.tr.segments[+i]; if (!seg) return;
    if (k !== "x") { const a = seg.alts[+k]; const text = typeof a === "string" ? a : a?.text; const parts = String(text || "").trim().split(/\s+/).filter(Boolean);
      if (Array.isArray(a?.words) && a.words.length) { seg.words = JSON.parse(JSON.stringify(a.words)); seg.text = text || seg.words.map((w) => w.w).join(" "); }
      else if (parts.length) { const s = seg.words?.[0]?.start ?? seg.start, en = seg.words?.length ? seg.words[seg.words.length - 1].end : seg.end; const st = (en - s) / parts.length;
        seg.words = parts.map((p, n) => ({ w: p, start: +(s + n * st).toFixed(3), end: +(s + (n + 1) * st).toFixed(3) })); seg.text = parts.join(" "); } }
    delete seg.alts; syncWords(); E.transcriptDirty = true; touch(); afterTranscriptEdit(false, k === "x" ? "पुराना text रखा" : "चुना हुआ text लगा"); }));
}
function afterTranscriptEdit(quiet, msg) {
  if (E.sel?.type === "caption" && !captionAt(E.sel.id)) E.sel = null;
  renderTimeline(); renderOverlay();
  if (!quiet) { renderInspector(); if (E.tab === "captions") renderPanel(); E.ctx.toast(msg); }
}
// a caption line is identified by its start time (indices shift when lines are edited)
function captionAt(id) { const cs = captionChunks(); return cs.find((c) => Math.abs(c.start - id) < 1e-4) || cs.find((c) => c.start <= id && id < c.end) || null; }

// ---------- side panel ----------
function renderPanel() {
  const panel = $("#ed-panel", E.root); const { esc, stylePreview, S } = E.ctx; const fx = E.rs.effects; const dis = E.canEdit ? "" : "disabled";
  const t = E.tab; let h = "";
  if (t === "cuts") {
    const on = E.cuts.filter((c) => c.enabled !== false);
    h = `<div class="ph"><h3>Auto-cut</h3><span class="small muted">${on.length} कट · ${on.reduce((s, c) => s + c.end - c.start, 0).toFixed(1)}s हटेंगे</span></div>
      <div class="irow"><label class="small muted grow">रुकावट की सीमा <input type="number" id="max-pause" step="0.1" min="0.2" max="3" value="${E.p.edl?.options?.max_pause ?? 0.55}"> s</label><button class="btn small" id="recut" ${dis}>दोबारा ढूँढें</button></div>
      <div class="irow"><button class="btn small quiet" id="cuts-all-on" ${dis}>सब चालू</button><button class="btn small quiet" id="cuts-all-off" ${dis}>सब बंद</button></div>
      <ul class="plist">${[...E.cuts].sort((a, b) => a.start - b.start).map((c) => `<li class="${c.enabled === false ? "off" : ""} ${E.sel?.type === "cut" && E.sel.id === c.id ? "sel" : ""}" data-cut="${c.id}">
        <input type="checkbox" ${c.enabled !== false ? "checked" : ""} ${dis}><span class="tag ${c.reason}">${{ silence: "चुप्पी", filler: "अं-आं", retake: "retake", manual: "आपका" }[c.reason] || c.reason}</span><span class="grow small">${esc(c.text || "")}</span><button class="ibtn mbtn ${morphOn(c) ? "on" : ""}" data-cmorph="${c.id}" title="🌗 Morph cut — इस jump cut को smooth करें" ${dis}>🌗</button><span class="small muted">${fmt(c.start)}</span></li>`).join("")}</ul>
      <p class="small muted">अपना कट: वीडियो में I दबाएँ, फिर O, फिर X (या “हटाएँ”)।</p>`;
  } else if (t === "captions" && E.capMode === "text") {
    h = `<div class="seg capmode"><button data-capmode="style">💬 Captions</button><button data-capmode="text" class="on">✂ Text से edit</button></div>${PRO.textDocHtml(dis)}`;
  } else if (t === "captions") {
    const ov = E.rs.captions;
    h = `<div class="seg capmode"><button data-capmode="style" class="on">💬 Captions</button><button data-capmode="text" title="transcript को document की तरह edit करें — शब्द हटाओ, वीडियो कटे">✂ Text से edit</button></div><div class="ph"><h3>Caption style</h3><label class="chk small"><input type="checkbox" id="burn" ${E.rs.burn_captions !== false ? "checked" : ""} ${dis}> वीडियो में जलाएँ</label></div>
      <div class="styles">${(S.presets?.caption_styles || []).map((cs) => stylePreview(cs, E.rs.caption_style === cs.id)).join("")}</div>
      <h4>अपने हिसाब से</h4>
      <div class="irow">${field("आकार", `<input type="range" id="cap-size" min="0.6" max="1.8" step="0.05" value="${ov.size_scale ?? 1}" ${dis}>`)}${field("जगह", `<select id="cap-pos" ${dis}><option value="">style जैसी</option>${["bottom", "center", "top"].map((p) => `<option value="${p}" ${ov.position === p ? "selected" : ""}>${{ bottom: "नीचे", center: "बीच", top: "ऊपर" }[p]}</option>`).join("")}</select>`)}</div>
      <div class="irow">${field("font", `<select id="cap-font" ${dis}><option value="">style जैसा</option>${fontList().map((f) => `<option ${ov.font === f ? "selected" : ""}>${f}</option>`).join("")}</select>`)}</div>
      <div class="irow">${field("अक्षर", `<input type="color" id="cap-primary" value="${ov.primary || "#ffffff"}" ${dis}>`)}${field("highlight", `<input type="color" id="cap-highlight" value="${ov.highlight || "#ffd400"}" ${dis}>`)}${field("outline", `<input type="color" id="cap-outline-color" value="${ov.outline_color || "#000000"}" ${dis}>`)}${field("", `<label class="chk small"><input type="checkbox" id="cap-usecolors" ${ov.primary ? "checked" : ""} ${dis}> रंग लागू</label>`)}</div>
      <div class="irow"><label class="chk small"><input type="checkbox" id="cap-italic" ${ov.italic === true ? "checked" : ""} ${dis}> <i>तिरछा (italic)</i></label><label class="chk small"><input type="checkbox" id="cap-upper" ${ov.uppercase === true ? "checked" : ""} ${dis}> ABC uppercase</label><label class="chk small"><input type="checkbox" id="cap-bold" ${ov.bold === false ? "" : "checked"} ${dis}> <b>bold</b></label></div>
      <div class="irow">${field("अक्षरों के बीच जगह", `<input type="range" id="cap-spacing" min="-0.005" max="0.02" step="0.001" value="${ov.letter_spacing === "" || ov.letter_spacing == null ? 0 : ov.letter_spacing}" ${dis}>`)}${field("outline मोटाई", `<input type="range" id="cap-outline" min="0" max="3" step="0.1" value="${ov.outline_scale === "" || ov.outline_scale == null ? 1 : ov.outline_scale}" ${dis}>`)}${field("shadow", `<input type="range" id="cap-shadow" min="0" max="3" step="0.1" value="${ov.shadow_scale === "" || ov.shadow_scale == null ? 1 : ov.shadow_scale}" ${dis}>`)}</div>
      <h4>Hook (शुरू के 3 सेकंड)</h4>${field("", `<input id="hook" value="${esc(E.rs.hook.text || "")}" placeholder="4 बजे उठने वाला लड़का" ${dis}>`)}
      <h4>Caption text सुधारें · ${captionChunks().length}</h4><p class="small muted">किसी line पर क्लिक करके शब्द बदलें (गलत सुना हो तो)। Enter = सेव। आपके सुधार channel याद रखता है — अगली videos में अपने-आप ठीक होंगे।</p>
      <div class="irow"><input id="fr-find" placeholder="गलत शब्द" ${dis}><input id="fr-repl" placeholder="सही शब्द" ${dis}><button class="btn small" id="fr-go" ${dis}>सब बदलें</button></div>
      <div class="irow"><button class="btn small quiet" id="re-asr" ${dis} title="बेहतर model + आपकी शब्दावली के साथ">🔁 transcript दोबारा बनाएँ</button><span class="small muted">${E.p.transcript?.model ? `model: ${esc(E.p.transcript.model)}` : ""}${E.p.transcript?.fixes_applied ? ` · ${E.p.transcript.fixes_applied} शब्द याद से सुधरे` : ""}${E.p.transcript?.polished_words ? ` · AI ने ${E.p.transcript.polished_words} सुधारे` : ""}</span></div>
      <div class="irow capbar"><button class="btn small quiet" id="cap-io-del" ${dis} title="In–Out के बीच के सारे caption शब्द हटाएँ">🗑 I–O के captions</button><button class="btn small quiet" id="cap-io-rel" ${dis} title="In–Out वाला हिस्सा दोबारा सुनें">🔄 I–O दोबारा सुनो</button>
        ${E.capSel.size ? `<button class="btn small" id="cap-sel-rel" ${dis}>🔄 चुनी ${E.capSel.size} lines दोबारा सुनो</button><button class="btn small danger quiet" id="cap-sel-del" ${dis}>🗑 चुनी lines हटाएँ</button>` : `<span class="small muted">☐ से कई lines चुनें</span>`}</div>
      <ul class="plist caps">${(() => { const cs = captionChunks(); const firstOf = new Set(); return cs.map((c) => { const seg = segOfWord(c.words[0]); const showAlts = seg && seg.alts?.length && !firstOf.has(seg) && firstOf.add(seg);
        const busy = rangeBusy(c.start, c.end); const sel = E.sel?.type === "caption" && captionAt(E.sel.id)?.start === c.start;
        return `<li data-capst="${c.start}" class="${sel ? "sel" : ""} ${busy ? "busy" : ""}"><input type="checkbox" class="capchk" data-capst="${c.start}" ${E.capSel.has(c.start) ? "checked" : ""} ${dis}><span class="small muted capt">${fmt(c.start)}</span>
          <input class="capedit" data-capst="${c.start}" value="${esc(c.words.map((w) => w.w).join(" "))}" ${dis} ${busy ? "disabled" : ""}>
          ${busy ? `<span class="spin" title="दोबारा सुन रहे…"></span>` : `<button class="ibtn" data-caprel="${c.start}" title="🔄 दोबारा सुनो — सिर्फ़ यह line फिर से transcribe" ${dis}>🔄</button>`}<button class="ibtn" data-capdel="${c.start}" title="यह caption हटाएँ" ${dis} ${busy ? "disabled" : ""}>${ICON.trash}</button>
          ${showAlts ? altsHtml(seg, dis) : ""}</li>`; }).join(""); })() || `<li class="small muted">अभी कोई caption नहीं</li>`}</ul>`;
  } else if (t === "text") {
    h = `<div class="ph"><h3>Text</h3><span class="small muted">playhead पर जुड़ेगा</span></div>
      <div class="irow" style="margin-bottom:.6rem"><button class="btn small" id="hook-edit" ${dis}>🪝 Heading / Hook ${E.rs.hook.text ? "बदलें" : "जोड़ें"}</button>${E.rs.hook.text ? `<span class="small muted grow" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(E.rs.hook.text)}</span>` : ""}</div>
      <div class="box hookbox"><div class="row between"><b>🎯 Hook studio</b><button class="btn small" id="hk-load">score + options</button></div><div id="hk-body" class="small muted">पहले 3 सेकंड कितने दमदार हैं — score, सुधार और 3 hook options।</div></div>
      ${textGallery(dis)}
      <div class="box"><b>अपने fonts</b><p class="small muted">Google Fonts या किसी free site से .ttf/.otf font upload करें — text, captions और heading सब में चुन सकेंगे। ${(E.lib || []).filter((x) => x.kind === "font").map((x) => `<span class="pill small" style="font-family:'${esc(x.meta?.family || x.name)}'">${esc(x.meta?.family || x.name)}</span>`).join(" ")}</p>
        <label class="btn small">⬆ Font upload<input type="file" id="font-up" accept=".ttf,.otf" multiple hidden ${dis}></label><div id="lib-progress"></div></div>
      <h4>Timeline पर</h4><ul class="plist">${fx.titles.map((ti) => `<li class="${E.sel?.type === "title" && E.sel.id === ti._id ? "sel" : ""}" data-title-id="${ti._id}"><span class="grow small">${esc(ti.text)}</span><span class="small muted">${fmt(ti.start)}</span></li>`).join("") || `<li class="muted small">अभी कोई text नहीं</li>`}</ul>`;
  } else if (t === "ai") {
    const A = E.ai; const K = { hook: "🎬 Hook video (शुरुआत)", broll: "🎞 B-roll", background: "🖼 Cutout background", thumbnail: "🏷 Thumbnail background" };
    h = `<div class="ph"><h3>AI Prompt Studio</h3><span class="small muted">Grok · ChatGPT · Veo</span></div>
      <p class="small muted">Transcript से prompts बनते हैं। Copy करके Grok Imagine / ChatGPT में बनाएँ, फिर बना हुआ file यहीं “लगाएँ” से upload करें — सही जगह अपने-आप लग जाएगा।</p>
      <div class="irow"><select id="ai-plat"><option value="">platform: auto</option><option value="short">9:16 Shorts/Reels</option><option value="long">16:9 YouTube</option></select><select id="ai-n">${[2, 4, 6, 8].map((n) => `<option ${n === (E.aiN || 4) ? "selected" : ""}>${n}</option>`).join("")}</select><button class="btn small primary" id="ai-go">✨ prompts बनाएँ</button></div>
      ${A?.batch ? `<div class="box"><b>⚡ सब एक बार में</b><p class="small muted">${A.batch.count} prompts एक ही message में — ChatGPT/Grok में एक बार paste करें, सारी images/clips एक ही chat में बनेंगी (बार-बार credit नहीं)।</p>
        <div class="irow"><button class="btn small primary" data-aiall="chatgpt">सब copy → ChatGPT ↗</button>${A.batch.videos ? `<button class="btn small" data-aiall="grok">${A.batch.videos} video prompts → Grok ↗</button>` : ""}</div>
        ${E.aiPack?.pack?.pinned_comment ? `<p class="small">📌 Pin comment: “${esc(E.aiPack.pack.pinned_comment)}” <button class="btn small quiet" id="ai-pin">copy</button></p>` : ""}
        ${E.aiPack?.llm?.provider ? `<p class="small muted">AI: ${E.aiPack.llm.calls} calls · ${E.aiPack.llm.saved} बार cache से (credit बचा)</p>` : ""}</div>` : ""}
      <div id="ai-list">${A ? A.items.map((x, i) => `<div class="box aicard"><div class="row between"><b>${K[x.kind] || x.kind}</b><span class="small muted">${x.at != null ? "⏱ " + fmt(x.at) : ""} ${x.seconds ? `· ${x.seconds}s video` : "· image"} · ${esc(x.aspect)}${x.source === "ai" ? " · AI" : ""}</span></div>
          ${x.line ? `<p class="small muted">“${esc(x.line.slice(0, 120))}”</p>` : ""}${x.hindi && x.hindi !== x.line ? `<p class="small">${esc(x.hindi)}</p>` : ""}
          <textarea data-aip="${i}" rows="4">${esc(x.prompt)}</textarea>
          <div class="irow"><button class="btn small" data-aicopy="${i}">Copy</button><button class="btn small" data-aiopen="grok:${i}">Grok ↗</button><button class="btn small" data-aiopen="chatgpt:${i}">ChatGPT ↗</button><button class="btn small quiet" data-aiopen="gemini:${i}">Gemini ↗</button>
          <label class="btn small primary">⬆ बना file लगाएँ<input type="file" data-aiup="${i}" accept="video/*,image/*" hidden ${dis}></label></div></div>`).join("") : `<p class="small muted">ऊपर “prompts बनाएँ” दबाएँ।</p>`}</div><div id="lib-progress"></div>`;
  } else if (t === "transitions") {
    const nCuts = E.cuts.filter((c) => c.enabled !== false).length;
    h = `<div class="ph"><h3>Transitions</h3><span class="small muted">${nCuts} कट</span></div>
      <p class="small muted">यहाँ चुना हुआ transition हर कट पर लगेगा। किसी एक कट पर अलग चाहिए तो timeline में उस कट (लाल) पर क्लिक करें → “इस कट पर transition”।</p>
      <div class="box"><b>Transition (हर कट पर)</b><p class="small muted" style="margin:.2rem 0">Effect-style (cut पर flash/blur…):</p><div class="trgrid">${(S.presets?.transitions || []).filter((t) => !t.id.startsWith("x_")).map((t) => `<button class="trbtn ${(fx.transition || "none") === t.id ? "on" : ""}" data-tr="${t.id}" ${dis}><i class="tr-${t.id}"></i>${esc(t.label)}</button>`).join("")}</div>
        <p class="small muted" style="margin:.5rem 0 .2rem">Clip transitions (दोनों clips 0.4s overlap — wipe/slide/dissolve, CapCut जैसे):</p><div class="trgrid">${(S.presets?.transitions || []).filter((t) => t.id.startsWith("x_")).map((t) => `<button class="trbtn ${(fx.transition || "none") === t.id ? "on" : ""}" data-tr="${t.id}" ${dis}><i class="tr-x"></i>${esc(t.label)}</button>`).join("")}</div><p class="small muted">एक कट के लिए अलग: timeline पर कट चुनें → inspector।</p></div>`;
  } else if (t === "media" || t === "audio" || t === "overlay" || t === "stickers") {
    const kinds = t === "media" ? ["broll", "image", "sticker"] : t === "audio" ? ["music", "sfx"] : t === "stickers" ? ["sticker"] : ["sticker", "image", "logo", "frame", "lut"];
    if (!kinds.includes(E.libKind)) E.libKind = kinds[0];
    const subTags = { sticker: ["", "popup", "emoji", "social", "shape"], music: ["", "motivational", "emotional", "lofi", "upbeat", "cinematic", "story", "energetic", "news"], frame: ["", "vertical", "horizontal"], broll: ["", "background", "overlay"] }[E.libKind] || [];
    const lq = (E.libQ || "").toLowerCase();
    const items = (E.lib || []).filter((x) => x.kind === E.libKind && (!E.libTag || (`,${x.tags},`).includes(`,${E.libTag},`)) && (!lq || x.name.toLowerCase().includes(lq) || (x.tags || "").includes(lq)));
    const music = fx.music, wm = fx.watermark;
    const pclips = E.p.assets.filter((a) => a.kind === "clip").sort((a, b) => (a.meta?.order || 0) - (b.meta?.order || 0));
    const clipBox = t === "media" && !E.montage ? `<div class="box"><div class="row between"><b>Project clips · ${pclips.length || 1}</b>${E.canEdit ? `<label class="btn small">+ clip जोड़ें<input type="file" id="clip-file" accept="video/*,.mkv,.mts" multiple hidden></label>` : ""}</div>
        <p class="small muted">कई recordings एक timeline पर क्रम से जुड़ती हैं। clip जोड़ने/हटाने पर transcript और कट दोबारा बनते हैं।</p>
        ${pclips.length ? `<ol class="plist" style="padding-left:1.2rem">${pclips.map((c) => `<li><span class="grow small">${esc(c.label || "clip")}</span>${E.canEdit ? `<button class="ibtn" data-clipdel="${c.id}">${ICON.trash}</button>` : ""}</li>`).join("")}</ol><div class="row"><button class="btn small" id="clip-rebuild" ${E.canEdit ? "" : "disabled"}>दोबारा जोड़ें & process</button></div>` : `<p class="small muted">यह project एक ही recording से बना है — और clips जोड़ने पर सब एक साथ जुड़ जाएँगे।</p>`}
        <div id="clip-progress"></div></div>` : "";
    h = `<div class="ph"><h3>${{ media: "Media library", audio: "Audio", overlay: "Overlay", stickers: "Stickers" }[t]}</h3><span class="small muted">खींचकर preview/timeline पर छोड़ें या “+”</span></div>${clipBox}
      <div class="seg">${kinds.map((k) => `<button data-kind="${k}" class="${E.libKind === k ? "on" : ""}">${LIB_KINDS.find((x) => x[0] === k)[1]}</button>`).join("")}</div>
      <label class="drop small ${dis ? "off" : ""}"><input type="file" id="lib-file" multiple hidden ${dis}>${ICON.plus} ${E.libKind} upload करें <span class="muted">(${{ music: "mp3/wav", sfx: "mp3/wav", broll: "mp4/mov", image: "png/jpg", sticker: "png (transparent)", logo: "png", frame: "png 1080×1920/1920×1080 transparent", lut: ".cube" }[E.libKind]})</span></label>
      <div id="lib-progress"></div>
      <div class="irow"><input id="lib-q" placeholder="खोजें…" value="${esc(E.libQ || "")}" style="flex:1"><a class="btn small quiet" href="#/library" title="पूरी library">⤢</a></div>
      ${subTags.length ? `<div class="seg wrap" style="flex-wrap:wrap;margin:.3rem 0">${subTags.map((tg) => `<button data-ltag="${tg}" class="${(E.libTag || "") === tg ? "on" : ""}">${tg || "सब"}</button>`).join("")}</div>` : ""}
      ${t === "audio" ? audioControls(dis) + PRO.musicFitHtml(dis) + dubBox(dis) : ""}
      ${t === "overlay" && E.libKind === "logo" ? `<div class="box"><b>Watermark</b>${wm.id ? `<p class="small">${esc(libItem(wm.id)?.name || "")}</p>` : `<p class="small muted">logo चुनकर “लगाएँ”</p>`}
        <div class="irow">${field("पारदर्शिता", `<input type="range" id="wm-op" min="0.1" max="1" step="0.05" value="${wm.opacity}" ${dis}>`)}${field("आकार", `<input type="range" id="wm-size" min="0.06" max="0.3" step="0.01" value="${wm.size}" ${dis}>`)}</div>
        ${field("कोना", `<select id="wm-pos" ${dis}>${["tr", "tl", "br", "bl"].map((p) => `<option value="${p}" ${wm.pos === p ? "selected" : ""}>${{ tr: "ऊपर दाएँ", tl: "ऊपर बाएँ", br: "नीचे दाएँ", bl: "नीचे बाएँ" }[p]}</option>`).join("")}</select>`)}
        ${wm.id ? `<button class="btn small quiet" id="wm-clear">हटाएँ</button>` : ""}</div>` : ""}
      ${t === "overlay" && E.libKind === "frame" ? `<div class="box"><b>Frame / border</b>${fx.frame?.id ? `<p class="small">${esc(libItem(fx.frame.id)?.name || "")}</p>` : `<p class="small muted">frame PNG चुनकर “लगाएँ”</p>`}
        ${field("opacity", `<input type="range" id="frm-op" min="0.2" max="1" step="0.05" value="${fx.frame?.opacity ?? 1}" ${dis}>`)}${fx.frame?.id ? `<button class="btn small quiet" id="frm-clear">हटाएँ</button>` : ""}</div>` : ""}
      ${t === "overlay" && E.libKind === "lut" ? `<p class="small muted">LUT (.cube) लगाने पर Effects का look बदल जाता है। अभी: <b>${fx.look?.startsWith("lut:") ? esc(libItem(fx.look.slice(4))?.name || "LUT") : "कोई नहीं"}</b></p>` : ""}
      <ul class="lib ${["sticker", "image", "frame", "logo"].includes(E.libKind) ? "grid" : ""}">${E.lib === null ? `<li class="muted small">लोड हो रहा…</li>` : items.map((x) => `<li data-lib="${x.id}" draggable="${E.canEdit ? "true" : "false"}" title="खींचकर preview या timeline पर छोड़ें">
        ${["image", "logo", "sticker", "frame"].includes(x.kind) ? `<img src="${x.url}" alt="" loading="lazy" style="object-fit:contain;background:repeating-conic-gradient(#1a2130 0 25%,#222b3b 0 50%) 50%/10px 10px">` : x.kind === "broll" ? `<video src="${x.url}#t=0.5" muted preload="metadata"></video>` : `<i class="libicon">${ICON.audio}</i>`}
        <div class="grow"><b class="small">${esc(x.name)}</b><span class="small muted">${x.meta?.duration ? fmt(x.meta.duration) : ""}${x.meta?.width ? ` · ${x.meta.width}×${x.meta.height}` : ""}</span></div>
        ${x.kind === "music" || x.kind === "sfx" || x.kind === "broll" ? `<button class="ibtn" data-prev="${x.id}" title="सुनें/देखें">${ICON.play}</button>` : ""}
        ${x.kind === "music" ? `<button class="btn small" data-addclip="${x.id}" title="किसी audio track पर clip की तरह (playhead से)" ${dis}>+ clip</button>` : ""}<button class="btn small primary" data-add="${x.id}" ${dis}>${{ music: "लगाएँ", logo: "लगाएँ", lut: "लगाएँ", frame: "लगाएँ" }[x.kind] || "+ जोड़ें"}</button>
        <button class="ibtn" data-del="${x.id}" title="library से हटाएँ" ${dis}>${ICON.trash}</button></li>`).join("") || `<li class="muted small">अभी कुछ नहीं — ऊपर से upload करें।</li>`}</ul>`;
  } else if (t === "montage") {
    const mo = E.mo; const lib = E.lib || []; const clips = lib.filter((x) => x.kind === "broll" || x.kind === "image"); const musics = lib.filter((x) => x.kind === "music"); const logos = lib.filter((x) => x.kind === "logo");
    const vert = (S.presets?.platforms || []); const chosen = mo.clips.map((c) => lib.find((x) => x.id === c.id)).filter(Boolean);
    const looks = S.presets?.looks || []; const grades = Object.entries(S.presets?.catalog?.grade_presets || {}); const auto = mo.mode === "auto";
    const job = E.p.jobs?.find((j) => (j.kind === "montage" || j.kind === "montage_plan") && j.status === "running");
    const pl = mo.plan; const FXL = { cut: "सीधा cut", zoom_punch: "Zoom punch", flash: "Flash", shake: "Shake", rgb: "RGB split", glitch: "Glitch", blur_in: "Blur in", zoom_in: "Zoom in", zoom_out: "Zoom out", white_fade: "White fade", black_fade: "Black fade" };
    const sel = (id, opts, v) => `<select id="${id}" ${dis}>${opts.map(([k, l]) => `<option value="${k}" ${String(v) === String(k) ? "selected" : ""}>${l}</option>`).join("")}</select>`;
    const frm = (it, at) => it?.url ? (it.kind === "image" ? it.url : it.url.replace("/file?", "/frame?") + `&at=${(+at + 0.3).toFixed(2)}`) : "";
    const segRow = (sg, i) => { const it = libItem(sg.clip); const src = frm(it, sg.src_in);
      return `<li class="moseg ${sg.keep === false ? "off" : ""} ${E.moSel === i ? "sel" : ""}" data-mosel="${i}">
        <span class="mothumb">${src ? `<img src="${src}" alt="" loading="lazy">` : ""}</span>
        <span class="mobody"><span class="small"><b>${i + 1}.</b> ${esc((it?.name || "clip").slice(0, 14))} ${sg.highlight ? "⭐" : ""}${sg.face ? " 🙂" : ""}${sg.speed < 1 ? " 🐢" : ""} <span class="muted">${it?.kind === "image" ? "photo" : "⏱" + fmt(sg.src_in)} · ${(+sg.dur).toFixed(2)}s</span></span>
        <span class="morow"><select data-mofx="${i}" ${dis}>${Object.entries(FXL).map(([k, l]) => `<option value="${k}" ${sg.fx === k ? "selected" : ""}>${l}</option>`).join("")}</select>
        <button class="ibtn" data-moalt="${i}" title="इसी clip का दूसरा अच्छा हिस्सा" ${dis}>↻</button><button class="ibtn" data-momv="${i}:-1" title="ऊपर" ${dis}>↑</button></span></span>
        <label class="chk small" title="रखें / हटाएँ"><input type="checkbox" data-mokeep="${i}" ${sg.keep !== false ? "checked" : ""} ${dis}></label></li>`; };
    const keptDur = pl ? pl.segments.filter((x) => x.keep !== false).reduce((a, x) => a + (+x.dur), 0) : 0;
    h = `<div class="ph"><h3>Montage</h3><span class="small muted">${E.p.meta?.bpm ? `${E.p.meta.bpm} BPM · ${E.p.meta.segments} cuts` : "beat-synced"}</span></div>
      <div class="seg" style="margin-bottom:.6rem"><button data-momode="auto" class="${auto ? "on" : ""}">🤖 Auto beat-edit</button><button data-momode="classic" class="${auto ? "" : "on"}">Classic</button></div>
      <p class="small muted">${auto ? "कई clips + एक song डालें → हर clip के best हिस्से (चेहरा, movement, साफ़ frame) अपने-आप चुने जाते हैं, song के beat पर 0.5–2s के cut, beat पर effects (flash, zoom punch, shake, RGB, glitch), चेहरे के हिसाब से 9:16/1:1/16:9 में auto-crop, auto color। Plan बनने के बाद हर cut बदल/हटा/वापस ला सकते हैं।" : "हर beat पर cut, clips क्रम से, ऊपर text lines।"}</p>
      <div class="box"><div class="row between"><b>Clips · ${chosen.length}</b>${E.canEdit ? `<label class="btn small primary">⬆ clips/photos upload<input type="file" id="mo-up" accept="video/*,image/*,.mov,.mkv" multiple hidden></label>` : ""}</div>
      <div id="lib-progress"></div><ul class="plist">${chosen.map((x, i) => `<li><span class="small muted">${i + 1}.</span><span class="grow small">${esc(x.name)} <span class="muted">${x.meta?.duration ? fmt(x.meta.duration) : "photo"}${x.meta?.width ? ` · ${x.meta.width}×${x.meta.height}` : ""}</span></span><button class="ibtn" data-moup="${i}" title="ऊपर">↑</button><button class="ibtn" data-model="${i}">${ICON.trash}</button></li>`).join("") || `<li class="muted small">ऊपर से एक साथ कई clips upload करें (अलग-अलग ratio चलेगा)।</li>`}</ul>
      ${clips.some((x) => !mo.clips.some((c) => c.id === x.id)) ? `<details><summary class="small">library से जोड़ें</summary><div class="irow" style="flex-wrap:wrap"><button class="btn small" id="mo-addall" ${dis}>+ सब</button>${clips.filter((x) => !mo.clips.some((c) => c.id === x.id)).map((x) => `<button class="btn small quiet" data-moadd="${x.id}" ${dis}>+ ${esc(x.name.slice(0, 18))}</button>`).join("")}</div></details>` : ""}</div>
      <div class="box"><div class="row between"><b>Song / music</b>${E.canEdit ? `<label class="btn small">⬆ song<input type="file" id="mo-mup" accept="audio/*,video/*" hidden></label>` : ""}</div>${field("", `<select id="mo-music" ${dis}><option value="">— चुनें —</option>${musics.map((m) => `<option value="${m.id}" ${mo.music === m.id ? "selected" : ""}>${esc(m.name)}${m.meta?.duration ? ` (${fmt(m.meta.duration)})` : ""}</option>`).join("")}</select>`)}
      <p class="small muted">${auto ? "लंबा song हो तो सबसे जोशीला हिस्सा (drop/chorus) अपने-आप चुना जाता है।" : ""}</p></div>
      <div class="irow">${field("लंबाई", sel("mo-max", [10, 15, 20, 30, 45, 60, 90].map((n) => [n, n + "s"]), mo.max_seconds))}${field("format", sel("mo-preset", vert.map((x) => [x.id, x.label]), mo.preset))}</div>
      ${auto ? `<div class="irow">${field("cut speed", sel("mo-pace", [["auto", "Auto (song के हिसाब से)"], ["fast", "Fast · ½–1 beat"], ["medium", "Medium"], ["slow", "Slow · 2–4 beat"]], mo.pace))}${field("effects", sel("mo-fxl", [["auto", "Auto"], ["strong", "ज़्यादा (strong)"], ["subtle", "हल्के"], ["none", "बिना effect"]], mo.effects_level))}</div>
        <div class="irow">${field("frame / crop", sel("mo-reframe", [["smart", "Smart crop (चेहरा/subject)"], ["fit", "पूरा दिखाओ + blur background"], ["center", "बीच से crop"]], mo.reframe))}<label class="chk small"><input type="checkbox" id="mo-slow" ${mo.slowmo ? "checked" : ""} ${dis}> धीमे हिस्से में slow-mo</label></div>`
      : `<div class="irow">${field("हर कितने beat पर", sel("mo-every", [1, 2, 4, 8].map((n) => [n, n + " beat"]), mo.every))}<label class="chk small"><input type="checkbox" id="mo-flash" ${mo.flash ? "checked" : ""} ${dis}> beat flash</label></div>`}
      <div class="irow">${field("color / filter", `<select id="mo-look" ${dis}>${auto ? `<option value="auto" ${mo.look === "auto" ? "selected" : ""}>Auto (song के mood से)</option>` : ""}${looks.map((l) => `<option value="${l.id}" ${mo.look === l.id ? "selected" : ""}>${esc(l.label)}</option>`).join("")}${auto && grades.length ? `<optgroup label="Filters (115)">${grades.map(([k, g]) => `<option value="grade:${k}" ${mo.look === "grade:" + k ? "selected" : ""}>${esc(g.label)}</option>`).join("")}</optgroup>` : ""}</select>`)}
        ${field("logo", `<select id="mo-wm" ${dis}><option value="">नहीं</option>${logos.map((l) => `<option value="${l.id}" ${mo.watermark === l.id ? "selected" : ""}>${esc(l.name)}</option>`).join("")}</select>`)}</div>
      <details ${mo.texts ? "open" : ""}><summary class="small">Text lines (एक line = एक message, | से line break)</summary>${field("", `<textarea id="mo-texts" rows="3" ${dis}>${esc(mo.texts)}</textarea>`)}
      <div class="irow">${field("font", `<select id="mo-font" ${dis}>${fontList().map((f) => `<option ${mo.font === f ? "selected" : ""}>${f}</option>`).join("")}</select>`)}${field("रंग", `<input type="color" id="mo-color" value="${mo.text_color}" ${dis}>`)}${field("आकार", `<input type="range" id="mo-size" min="0.04" max="0.12" step="0.005" value="${mo.text_size}" ${dis}>`)}</div></details>
      ${auto ? `<div class="irow" style="margin-top:.6rem"><button class="btn primary" id="mo-auto" ${dis || (E.p.status === "rendering" ? "disabled" : "")}>✨ Auto edit करो (plan + video)</button><button class="btn" id="mo-plan" ${dis || (E.p.status === "rendering" ? "disabled" : "")}>सिर्फ़ plan</button></div>`
      : `<button class="btn primary" id="mo-render" ${dis || (E.p.status === "rendering" ? "disabled" : "")}>${E.p.status === "rendering" ? "बन रहा है…" : "Montage बनाएँ"}</button>`}
      ${E.p.status === "rendering" ? `<p class="small">${esc(E.p.status_note || "")}</p><div class="progress" style="margin-top:.5rem"><i style="width:${job?.progress || 0}%"></i></div>` : ""}
      ${auto && pl ? `<div class="box" style="margin-top:.8rem"><div class="row between"><b>Plan · ${pl.segments.filter((x) => x.keep !== false).length}/${pl.segments.length} cuts · ${keptDur.toFixed(1)}s · ${pl.bpm} BPM</b>${E.moDirty ? `<span class="small" style="color:var(--accent)">बदलाव बाकी</span>` : ""}</div>
        <p class="small muted">⭐ = सबसे अच्छे हिस्से · 🙂 = चेहरा मिला · ☐ हटाने से cut निकल जाता है (beat sync बना रहता है) · ↻ = उसी clip का दूसरा हिस्सा</p>
        <ul class="plist moplan">${pl.segments.map(segRow).join("")}</ul>
        ${(pl.alts || []).length ? `<h4>छूटे हुए अच्छे हिस्से — वापस डालें</h4><div class="moalts">${pl.alts.slice(0, 24).map((a, i) => { const it = libItem(a.clip); return `<button class="moalt" data-moins="${i}" title="चुने हुए cut के बाद डालें" ${dis}>${it?.url ? `<img src="${frm(it, a.src_in)}" alt="" loading="lazy">` : ""}<span class="small">${esc((it?.name || "").slice(0, 10))} ${fmt(a.src_in)}${a.face ? " 🙂" : ""}</span></button>`; }).join("")}</div>` : ""}
        <button class="btn primary" id="mo-rerender" style="margin-top:.6rem" ${dis || (E.p.status === "rendering" ? "disabled" : "")}>🎬 इस plan से video बनाओ</button></div>` : ""}`;
  } else if (t === "refs") {
    const refs = E.refs || []; const RK = { audio: "🎵 audio", video: "🎬 video", effect: "✨ effect", caption: "💬 caption", hook: "🪝 hook", other: "📌" };
    h = `<div class="ph"><h3>References</h3><span class="small muted">trend audio / video / effect</span></div>
      <p class="small muted">जो trend audio, video या effect आपको बनाना है — उसका link और note यहाँ रखें। project वाले यहीं दिखते हैं, बाकी Plan page के swipe-file में।</p>
      ${E.canEdit ? `<div class="box"><div class="irow">${field("kind", `<select id="ref-kind">${Object.entries(RK).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>`)}${field("link", `<input id="ref-url" placeholder="https://… (Instagram/YouTube/TikTok)">`)}</div>
        ${field("note", `<textarea id="ref-note" rows="2" placeholder="क्या चाहिए: 'इस audio पर 0:08 वाला beat drop', 'यह zoom effect'…"></textarea>`)}
        <div class="irow"><label class="chk small"><input type="checkbox" id="ref-global"> सब projects के लिए (swipe file)</label><span class="grow"></span><button class="btn small primary" id="ref-add">+ जोड़ें</button></div></div>` : ""}
      <ul class="plist refs">${refs.map((r) => `<li><span class="small">${RK[r.kind] || "📌"}</span><div class="grow" style="display:flex;flex-direction:column;min-width:0">${r.url ? `<a class="small" href="${esc(r.url)}" target="_blank" rel="noopener" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(r.url.replace(/^https?:\/\//, ""))}</a>` : ""}${r.note ? `<span class="small">${esc(r.note)}</span>` : ""}${!r.project_id ? `<span class="small muted">swipe file</span>` : ""}</div>${E.canEdit ? `<button class="ibtn" data-refdel="${r.id}">${ICON.trash}</button>` : ""}</li>`).join("") || `<li class="muted small">अभी कुछ नहीं</li>`}</ul>`;
  } else if (t === "shorts") {
    const planning = E.p.jobs?.some((j) => j.kind === "shorts_plan" && ["queued", "running"].includes(j.status));
    const vert = (S.presets?.platforms || []).filter((pl) => pl.height > pl.width);
    h = `<div class="ph"><h3>Shorts factory</h3><span class="small muted">${E.shorts.length} सुझाव</span></div>
      <p class="small muted">लंबी recording से 20–60s के हिस्से जो अकेले खड़े रहें — हर एक को title + hook मिलता है। चेहरा landscape से 9:16 में अपने-आप track होता है।</p>
      <div class="irow"><label class="small muted">कितने <input type="number" id="sh-count" min="1" max="12" value="5" style="width:60px"></label><button class="btn small" id="sh-plan" ${dis || (planning ? "disabled" : "")}>${planning ? "ढूँढ रहा है…" : "AI से सुझाव लें"}</button><button class="btn small quiet" id="sh-add" ${dis}>+ I–O से जोड़ें</button></div>
      <ul class="plist">${E.shorts.map((sc) => `<li class="${sc.selected === false ? "off" : ""} ${E.sel?.type === "short" && E.sel.id === sc.id ? "sel" : ""}" data-short="${sc.id}">
        <input type="checkbox" ${sc.selected !== false ? "checked" : ""} ${dis}><div class="grow" style="display:flex;flex-direction:column"><b class="small" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(sc.title || sc.id)}</b><span class="small muted">${fmt(sc.start)} → ${fmt(sc.end)} · ${(sc.end - sc.start).toFixed(0)}s${sc.hook ? ` · hook: ${esc(sc.hook)}` : ""}</span></div></li>`).join("") || `<li class="muted small">अभी कोई सुझाव नहीं — “AI से सुझाव लें” दबाएँ (बिना API key भी चलता है)।</li>`}</ul>
      ${E.shorts.length ? `<div class="box"><div class="irow">${field("format", `<select id="sh-preset" ${dis}>${vert.map((pl) => `<option value="${pl.id}" ${(E.rs.shorts_preset || "yt-short") === pl.id ? "selected" : ""}>${esc(pl.label)}</option>`).join("")}</select>`)}
        <label class="chk small"><input type="checkbox" id="sh-face" ${E.rs.face_track !== "off" ? "checked" : ""} ${dis}> चेहरा track करें</label></div>
        <button class="btn primary" id="sh-render" ${dis || (E.p.status === "rendering" ? "disabled" : "")}>${E.shorts.filter((x) => x.selected !== false).length} Shorts render करें</button></div>` : ""}`;
  } else if (t === "effects") {
    const cat = S.presets?.catalog || { categories: {}, effects: [] }; const q = (E.fxq || "").toLowerCase(); const fc = E.fxcat || "";
    const looks = S.presets?.looks || [];
    const thumb = (E.p.assets.find((a) => a.kind === "thumb") || {}).url;
    const list = cat.effects.filter((e) => (fc ? e.cat === fc : q || e.cat !== "trending") && (!q || e.label.toLowerCase().includes(q) || (e.tags || []).some((tg) => tg.includes(q)) || e.id.includes(q)));
    const stack = fx.stack || [];
    h = `<div class="ph"><h3>Effects</h3><span class="small muted">${stack.length} लगे</span></div>
      ${!q && (!fc || fc === "trending") ? PRO.trendingHtml(dis) : ""}
      <div class="box"><label class="chk"><input type="checkbox" id="fx-zoom" ${fx.zoom.enabled ? "checked" : ""} ${dis}> <b>Auto zoom / punch-in</b></label>
        <div class="irow">${field("pattern", `<select id="fx-zoom-mode" ${dis}>${(S.presets?.zoom_modes || []).map((z) => `<option value="${z.id}" ${(fx.zoom.mode || "punch") === z.id ? "selected" : ""}>${esc(z.label)}</option>`).join("")}</select>`)}${field("कितना", `<input type="range" id="fx-zoom-str" min="0.3" max="2" step="0.1" value="${fx.zoom.strength}" ${dis}>`)}</div></div>
      <div class="box"><b>Transitions</b><p class="small muted">अब अलग <b>Transitions</b> tab में हैं (बाएँ menu)।</p></div>
      ${stack.length ? `<h4>लगे हुए effects (ऊपर से नीचे)</h4><ul class="plist fxstack">${stack.map((it, i) => { const d = fxDef(it.id); if (!d) return ""; const pr = fxParams(d, it.params);
        return `<li class="${it.enabled === false ? "off" : ""}" data-fxi="${i}"><div class="grow"><div class="row between"><label class="chk small"><input type="checkbox" data-fxon="${i}" ${it.enabled === false ? "" : "checked"} ${dis}> <b>${esc(d.label)}</b> <span class="tag">${d.preview === "css" ? "preview ≈" : "सिर्फ़ render में"}</span></label><span class="row" style="gap:0"><button class="ibtn" data-fxup="${i}" title="ऊपर">↑</button><button class="ibtn" data-fxdown="${i}" title="नीचे">↓</button><button class="ibtn" data-fxdel="${i}">${ICON.trash}</button></span></div>
        ${(d.params || []).map((p) => p.type === "color" ? `<label class="small muted">${esc(p.label)} <input type="color" data-fxp="${i}:${p.name}" value="${pr[p.name]}" ${dis}></label>` : `<label class="small muted fxp"><span>${esc(p.label)}</span><input type="range" data-fxp="${i}:${p.name}" min="${p.min}" max="${p.max}" step="${p.step || 1}" value="${pr[p.name]}" ${dis}><b>${pr[p.name]}</b></label>`).join("")}</div></li>`; }).join("")}</ul>` : ""}
      ${fx.fxclips.length ? `<h4>Timeline पर effects · ${fx.fxclips.filter((c) => c.kind !== "filter").length}</h4><ul class="plist">${fx.fxclips.filter((c) => c.kind !== "filter").map((c) => `<li class="${E.sel?.type === "fxclip" && E.sel.id === c._id ? "sel" : ""}" data-fxclip="${c._id}"><span class="grow small">✨ ${esc(fxClipLabel(c))}</span><span class="small muted">${fmt(c.start)}–${fmt(c.end)}</span></li>`).join("")}</ul>` : ""}
      <h4>Catalog</h4>${fxModeSeg()}<div class="irow"><input id="fx-q" placeholder="खोजें… glitch, blur, film" value="${esc(E.fxq || "")}" style="flex:1"></div>
      <div class="seg wrap" style="flex-wrap:wrap;margin:.4rem 0"><button data-fxcat="" class="${!fc ? "on" : ""}">सब</button>${Object.entries(cat.categories).map(([k, v]) => `<button data-fxcat="${k}" class="${fc === k ? "on" : ""}">${esc(v)}</button>`).join("")}</div>
      <div class="fxgrid">${list.map((e) => `<button class="fxcard" data-fxadd="${e.id}" draggable="${E.canEdit}" title="${esc((e.tags || []).join(", "))} · क्लिक = ${E.fxMode === "global" ? "पूरे वीडियो पर" : "playhead पर 3s"} · timeline पर खींच भी सकते हैं" ${dis}>${thumb ? `<img src="${thumb}" alt="" style="filter:${e.preview === "css" && e.css ? stackCss([{ id: e.id }]) : ""}">` : `<i></i>`}<span>${esc(e.label)}</span><small>${e.preview === "css" ? "" : "render only"}</small></button>`).join("") || `<p class="small muted">कुछ नहीं मिला</p>`}</div>
      <h4>Quick looks</h4><div class="looks">${looks.map((l) => `<button class="look ${fx.look === l.id ? "on" : ""}" data-look="${l.id}" ${dis}>${thumb ? `<img src="${thumb}" style="filter:${LOOK_CSS[l.id] || ""}" alt="">` : `<i style="filter:${LOOK_CSS[l.id] || ""}"></i>`}<small>${esc(l.label)}</small></button>`).join("")}</div>
      <div class="box"><b>Extras</b><div class="irow" style="flex-wrap:wrap">${(S.presets?.extras || []).map((x) => `<label class="chk small"><input type="checkbox" data-extra="${x.id}" ${(fx.extras || []).includes(x.id) ? "checked" : ""} ${dis}> ${esc(x.label)}</label>`).join("")}</div></div>`;
  } else if (t === "body") {
    const b = fx.body; const alpha = E.p.assets.find((a) => a.kind === "alpha"); const mj = E.p.jobs?.find((j) => j.kind === "matte" && ["queued", "running"].includes(j.status));
    const lib = E.lib || [];
    h = `<div class="ph"><h3>Body effects</h3><span class="small muted">person cutout</span></div>
      <div class="box"><div id="bd-status">${bodyStatus()}</div>
        <div class="row"><label class="chk small"><input type="checkbox" id="bd-on" ${b.enabled ? "checked" : ""} ${dis}> <b>Body effects चालू</b></label></div>
        <p class="small muted">cutout बनने के बाद preview में <b>चलते वीडियो पर live</b> दिखता है (WebGL)। बिल्कुल final जैसा एक frame: "🎞 Preview frame"।</p></div>
      <h4>किनारा (edge)</h4><div class="irow">${field(`अंदर करें <b>${b.edge_shrink || 0}</b>`, `<input type="range" data-bd="edge_shrink" min="0" max="6" step="0.5" value="${b.edge_shrink || 0}" ${dis} title="पुराने background की पतली लकीर (halo) हटाएँ">`)}${field(`नरम <b>${b.edge_feather || 0}</b>`, `<input type="range" data-bd="edge_feather" min="0" max="6" step="0.5" value="${b.edge_feather || 0}" ${dis} title="किनारे को हल्का धुँधला करें">`)}</div>
      <h4>Background</h4><div class="irow">${field("", `<select id="bd-bg" ${dis}>${(S.presets?.body_bg || []).map((o) => `<option value="${o.id}" ${b.bg === o.id ? "selected" : ""}>${esc(o.label)}</option>`).join("")}</select>`)}
        ${b.bg === "blur" ? field("blur", `<input type="range" id="bd-blur" min="4" max="40" step="1" value="${b.bg_blur}" ${dis}>`) : ""}
        ${["flat", "gradient"].includes(b.bg) ? field("रंग", `<input type="color" id="bd-c1" value="${b.bg_color}" ${dis}>`) : ""}${b.bg === "gradient" ? field("रंग 2", `<input type="color" id="bd-c2" value="${b.bg_color2}" ${dis}>`) : ""}
        ${b.bg === "image" ? field("image (library)", `<select id="bd-img" ${dis}><option value="">—</option>${lib.filter((x) => x.kind === "image").map((x) => `<option value="${x.id}" ${b.bg_image === x.id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select>`) : ""}
        ${b.bg === "video" ? field("video (library)", `<select id="bd-vid" ${dis}><option value="">—</option>${lib.filter((x) => x.kind === "broll").map((x) => `<option value="${x.id}" ${b.bg_video === x.id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select>`) : ""}</div>
      ${["image", "video"].includes(b.bg) ? `<div class="irow"><label class="btn small">⬆ अपनी ${b.bg === "image" ? "image" : "video"} upload करें<input type="file" id="bd-up" accept="${b.bg === "image" ? "image/*" : "video/*"}" hidden ${dis}></label><div id="lib-progress" class="grow"></div></div>
        <div class="bdthumbs">${lib.filter((x) => (b.bg === "image" ? ["image"] : ["broll"]).includes(x.kind)).slice(0, 18).map((x) => `<button class="bdth ${(b.bg === "image" ? b.bg_image : b.bg_video) === x.id ? "on" : ""}" data-bdbg="${x.id}" title="${esc(x.name)}" ${dis}>${x.kind === "image" ? `<img src="${x.url}" loading="lazy">` : `<video src="${x.url}#t=0.5" muted preload="metadata"></video>`}</button>`).join("")}</div>` : ""}
      ${b.bg !== "none" ? `<details class="bdadv" ${E.bdBgOpen ? "open" : ""} id="bd-bgadv"><summary class="small">Background settings (zoom, blur, dark, tint${b.bg === "video" ? ", speed" : ""})</summary>
        <div class="irow">${["image", "video"].includes(b.bg) ? field("fit", `<select data-bd="bg_fit" ${dis}><option value="cover" ${b.bg_fit !== "contain" ? "selected" : ""}>पूरा भरें (crop)</option><option value="contain" ${b.bg_fit === "contain" ? "selected" : ""}>पूरा दिखाएँ (blur fill)</option></select>`) : ""}${b.bg === "video" ? field(`speed <b>${b.bg_speed || 1}×</b>`, `<input type="range" data-bd="bg_speed" min="0.25" max="3" step="0.25" value="${b.bg_speed || 1}" ${dis}>`) : ""}</div>
        <div class="irow">${field(`धीमा zoom-in <b>${b.bg_zoom || 0}</b>`, `<input type="range" data-bd="bg_zoom" min="0" max="0.5" step="0.05" value="${b.bg_zoom || 0}" ${dis}>`)}${b.bg !== "blur" ? field(`blur <b>${b.bg_blur2 || 0}</b>`, `<input type="range" data-bd="bg_blur2" min="0" max="30" step="1" value="${b.bg_blur2 || 0}" ${dis}>`) : ""}</div>
        <div class="irow">${field(`अंधेरा <b>${b.bg_dim || 0}</b>`, `<input type="range" data-bd="bg_dim" min="0" max="0.9" step="0.05" value="${b.bg_dim || 0}" ${dis}>`)}${field("tint रंग", `<input type="color" data-bd="bg_tint" value="${b.bg_tint || "#f2b33d"}" ${dis}>`)}${field(`tint <b>${b.bg_tint_amt || 0}</b>`, `<input type="range" data-bd="bg_tint_amt" min="0" max="0.8" step="0.05" value="${b.bg_tint_amt || 0}" ${dis}>`)}</div></details>` : ""}
      <h4>Person (cutout)</h4>
      <div class="irow">${field(`size <b>${b.subj_scale || 1}</b>`, `<input type="range" data-bd="subj_scale" min="0.4" max="1.6" step="0.05" value="${b.subj_scale || 1}" ${dis}>`)}${field(`← → <b>${b.subj_x || 0}</b>`, `<input type="range" data-bd="subj_x" min="-0.5" max="0.5" step="0.02" value="${b.subj_x || 0}" ${dis}>`)}${field(`↑ ↓ <b>${b.subj_y || 0}</b>`, `<input type="range" data-bd="subj_y" min="-0.5" max="0.5" step="0.02" value="${b.subj_y || 0}" ${dis}>`)}</div>
      <div class="irow"><label class="chk small"><input type="checkbox" data-bd="flip" ${b.flip ? "checked" : ""} ${dis}> mirror (उल्टा)</label><label class="chk small"><input type="checkbox" data-bd="shadow" ${b.shadow ? "checked" : ""} ${dis}> drop shadow</label></div><div class="irow">${b.shadow ? field("shadow गहराई", `<input type="range" data-bd="shadow_opacity" min="0.1" max="1" step="0.05" value="${b.shadow_opacity ?? 0.55}" ${dis}>`) + field("फैलाव", `<input type="range" data-bd="shadow_blur" min="2" max="60" step="2" value="${b.shadow_blur ?? 18}" ${dis}>`) : ""}</div>
      ${b.bg && ["blur", "dim", "none"].includes(b.bg) && ((b.subj_scale && b.subj_scale != 1) || b.subj_x || b.subj_y || b.flip) ? `<p class="small muted">⚠ person को हिलाने/छोटा करने पर पीछे वाला original भी दिखेगा — Background को image/video/colour पर रखें।</p>` : ""}
      <h4>Outline & glow</h4><div class="irow"><label class="chk small"><input type="checkbox" id="bd-stroke" ${b.stroke ? "checked" : ""} ${dis}> Stroke</label>${field("रंग", `<input type="color" id="bd-sc" value="${b.stroke_color}" ${dis}>`)}${field("मोटाई", `<input type="range" id="bd-sw" min="2" max="30" step="1" value="${b.stroke_width}" ${dis}>`)}</div>
      <div class="irow"><label class="chk small"><input type="checkbox" id="bd-glow" ${b.glow ? "checked" : ""} ${dis}> Glow / Neon</label>${field("रंग", `<input type="color" id="bd-gc" value="${b.glow_color}" ${dis}>`)}${field("फैलाव", `<input type="range" id="bd-gs" min="6" max="60" step="2" value="${b.glow_size}" ${dis}>`)}</div>
      <h4>Motion</h4><div class="irow">${field("entrance / blink", `<select id="bd-anim" ${dis}>${(S.presets?.body_anims || []).map((o) => `<option value="${o.id}" ${b.anim === o.id ? "selected" : ""}>${esc(o.label)}</option>`).join("")}</select>`)}${field("सेकंड", `<input type="range" id="bd-as" min="0.3" max="2" step="0.1" value="${b.anim_seconds}" ${dis}>`)}</div>
      <div class="irow"><label class="chk small"><input type="checkbox" id="bd-after" ${b.afterimage ? "checked" : ""} ${dis}> Afterimage (ghost trail)</label>${field("clones", `<select id="bd-clones" ${dis}>${[0, 1, 2, 3, 4].map((n) => `<option value="${n}" ${b.clones == n ? "selected" : ""}>${n}</option>`).join("")}</select>`)}</div>
      <p class="small muted">Text को person के पीछे रखने के लिए: Text item चुनें → "person के पीछे"।</p>
      <h4>Quick presets</h4><div class="irow" style="flex-wrap:wrap">${[["pop_white", "White stroke pop"], ["neon", "Neon glow"], ["sky", "आसमान से गिरे"], ["blink", "Blink cutout"], ["ghost", "Ghost trail"], ["flat", "Flat colour + outline"]].map(([k, l]) => `<button class="btn small quiet" data-bdp="${k}" ${dis}>${l}</button>`).join("")}</div>`;
  } else if (t === "color") {
    const cat = S.presets?.catalog || { grade_params: [], grade_presets: {} }; const g = fx.grade || {}; const def = GRADE_DEF();
    const thumb = (E.p.assets.find((a) => a.kind === "thumb") || {}).url;
    h = `<div class="ph"><h3>Color</h3><span class="row" style="gap:.3rem"><button class="btn small quiet" id="gr-ab" title="दबाए रखें = original">A/B</button><button class="btn small quiet" id="gr-copy">copy</button><button class="btn small quiet" id="gr-paste">paste</button><button class="btn small quiet" id="gr-reset">reset</button></span></div>
      <h4>Filters · ${Object.keys(cat.grade_presets).length}</h4>
      <div class="chips">${[["", "सब"], ...Object.entries(cat.grade_cats || {})].map(([k, l]) => `<button class="${(E.gCat || "") === k ? "on" : ""}" data-gcat="${k}">${esc(l)}</button>`).join("")}</div>
      <div class="irow">${field(`intensity <b id="gs-v">${Math.round((fx.grade_strength ?? 1) * 100)}%</b>`, `<input type="range" id="g-strength" min="0" max="1.5" step="0.05" value="${fx.grade_strength ?? 1}" ${dis}>`)}</div>
      ${fxModeSeg()}
      ${fx.fxclips.some((c) => c.kind === "filter") ? `<ul class="plist">${fx.fxclips.filter((c) => c.kind === "filter").map((c) => `<li class="${E.sel?.type === "fxclip" && E.sel.id === c._id ? "sel" : ""}" data-fxclip="${c._id}"><span class="grow small">🎨 ${esc(fxClipLabel(c))}</span><span class="small muted">${fmt(c.start)}–${fmt(c.end)}</span></li>`).join("")}</ul>` : ""}
      <p class="small muted">thumbnail पर mouse रखें = video पर झलक · क्लिक = ${E.fxMode === "global" ? "पूरे वीडियो पर लगाएँ" : "playhead पर 3s का filter clip (timeline पर खींच भी सकते हैं)"} · नीचे sliders = पूरे वीडियो का grade</p>
      <div class="looks">${Object.entries(cat.grade_presets).filter(([k, p]) => !E.gCat || p.cat === E.gCat).map(([k, p]) => `<button class="look ${fx.grade_preset === k ? "on" : ""}" data-gpre="${k}" draggable="${E.canEdit}" ${dis}>${thumb ? `<img src="${thumb}" style="filter:${gradeCss(p)}" alt="" loading="lazy">` : `<i></i>`}<small>${esc(p.label)}</small></button>`).join("")}</div>
      <h4>Adjust</h4>${cat.grade_params.map((p) => `<label class="small muted fxp grade"><span>${esc(p.label)}</span><input type="range" data-g="${p.name}" min="${p.min}" max="${p.max}" step="${p.step}" value="${g[p.name] ?? p.default}" ${dis}><b>${(+(g[p.name] ?? p.default)).toFixed(2).replace(/\.?0+$/, "")}</b></label>`).join("")}
      <p class="small muted">preview में अनुमान (CSS); असली grade render में ffmpeg से — exposure, curves, colortemperature, vibrance, hue, vignette, unsharp।</p>
      <h4>LUT</h4><p class="small muted">अपनी .cube LUT Overlay → LUT tab से लगाएँ; grade उसके बाद लगता है। ${fx.look?.startsWith("lut:") ? `<b>अभी: ${esc(libItem(fx.look.slice(4))?.name || "LUT")}</b>` : ""}</p>
      <div class="box"><b>🎨 Colour wheels · Curves · HSL · Colour match</b><p class="small muted">DaVinci जैसा pro colour — Pro tab में।</p><button class="btn small" data-tabgo="pro">🎛 Pro colour खोलें</button></div>`;
  } else if (t === "pro") {
    h = PRO.proPanel(dis);
  }
  panel.innerHTML = h;
  bindPanel();
}
function bindPanel() {
  const panel = $("#ed-panel", E.root); const { api, toast, load, S } = E.ctx; const fx = E.rs.effects;
  const on = (sel, ev, fn) => { const el = $(sel, panel); if (el) el[ev] = fn; };
  // pro features
  if (E.tab === "pro") PRO.bindProPanel(panel);
  if (E.tab === "audio") PRO.bindMusicFit(panel);
  if (E.tab === "captions" && E.capMode === "text") PRO.bindTextDoc(panel);
  $$("[data-capmode]", panel).forEach((b) => (b.onclick = () => { E.capMode = b.dataset.capmode; renderPanel(); if (E.capMode === "text") $("[data-tdoc]", panel)?.focus(); }));
  $$("[data-tabgo]", panel).forEach((b) => (b.onclick = () => { E.tab = b.dataset.tabgo; $$(".ed-tabs button", E.root).forEach((x) => x.classList.toggle("on", x.dataset.tab === E.tab)); renderPanel(); }));
  // cuts
  $$("[data-cut]", panel).forEach((li) => {
    li.onclick = (e) => { const c = E.cuts.find((x) => x.id === li.dataset.cut); if (e.target.type === "checkbox") { c.enabled = e.target.checked; touch(); renderPanel(); }
      else if (e.target.closest("[data-cmorph]")) { if (!E.canEdit) return; const g = E.rs.effects.pro?.morph_cut || {}; if (morphOn(c)) { if (g.enabled && g.all) c.morph = false; else delete c.morph; } else c.morph = true; touch(); renderPanel(); }
      else { select({ type: "cut", id: c.id }); seek(c.start); renderPanel(); } };
  });
  on("#cuts-all-on", "onclick", () => { E.cuts.forEach((c) => (c.enabled = true)); touch(); renderPanel(); });
  on("#cuts-all-off", "onclick", () => { E.cuts.forEach((c) => (c.enabled = false)); touch(); renderPanel(); });
  on("#recut", "onclick", async () => { await flush(); const ctx = E.ctx; await api("POST", `/projects/${E.pid}/recut`, { options: { max_pause: +$("#max-pause", panel).value } }); toast("कट दोबारा ढूँढे जा रहे हैं"); unmount(); await ctx.load(); ctx.render(); });
  // captions
  $$(".stylecard input", panel).forEach((i) => (i.onchange = () => { E.rs.caption_style = i.value; $$(".stylecard", panel).forEach((c) => c.classList.toggle("on", c.contains(i))); touch(); }));
  on("#burn", "onchange", (e) => { E.rs.burn_captions = e.target.checked; touch(); });
  const capSync = () => { const c = E.rs.captions; c.size_scale = +$("#cap-size", panel).value; c.position = $("#cap-pos", panel).value; c.font = $("#cap-font", panel).value;
    const use = $("#cap-usecolors", panel).checked; c.primary = use ? $("#cap-primary", panel).value : ""; c.highlight = use ? $("#cap-highlight", panel).value : ""; c.outline_color = use ? $("#cap-outline-color", panel).value : "";
    c.italic = $("#cap-italic", panel).checked ? true : ""; c.uppercase = $("#cap-upper", panel).checked ? true : ""; c.bold = $("#cap-bold", panel).checked ? "" : false;
    c.letter_spacing = +$("#cap-spacing", panel).value || ""; c.outline_scale = +$("#cap-outline", panel).value === 1 ? "" : +$("#cap-outline", panel).value; c.shadow_scale = +$("#cap-shadow", panel).value === 1 ? "" : +$("#cap-shadow", panel).value; touch(); };
  ["#cap-size", "#cap-pos", "#cap-font", "#cap-primary", "#cap-highlight", "#cap-outline-color", "#cap-usecolors", "#cap-italic", "#cap-upper", "#cap-bold", "#cap-spacing", "#cap-outline", "#cap-shadow"].forEach((s) => on(s, "oninput", capSync));
  // caption lines: typing updates preview + timeline right away (the input keeps pointing at the same words)
  $$(".capedit", panel).forEach((inp) => { inp._ws = captionAt(+inp.dataset.capst)?.words;
    const apply = () => { clearTimeout(E.capT); if (!inp._ws) return; const nw = applyCaptionText({ words: inp._ws }, inp.value, true); inp._ws = nw; if (nw.length) { E.sel = { type: "caption", id: nw[0].start }; renderInspector(); } };
    inp.onfocus = () => { const c = inp._ws?.length ? captionAt(inp._ws[0].start) : null; if (c) { seek(c.start + Math.min(0.2, (c.end - c.start) / 3)); E.sel = { type: "caption", id: c.start }; renderInspector(); renderTimeline(); } };
    inp.oninput = () => { clearTimeout(E.capT); E.capT = setTimeout(() => { if (E && inp.isConnected) apply(); }, 350); };
    inp.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); apply(); inp.blur(); renderPanel(); } else if (e.key === "Escape") inp.blur(); };
    inp.onchange = () => { apply(); if (!inp._ws.length) renderPanel(); }; });
  $$(".capchk", panel).forEach((cb) => (cb.onchange = () => { const st = +cb.dataset.capst; cb.checked ? E.capSel.add(st) : E.capSel.delete(st); const sc = panel.scrollTop; renderPanel(); panel.scrollTop = sc; }));
  $$("[data-capdel]", panel).forEach((b) => (b.onclick = () => { const c = captionAt(+b.dataset.capdel); if (!c || !E.canEdit) return; deleteWords(c.words); touch(); const sc = panel.scrollTop; afterTranscriptEdit(false, "caption हटाया"); $("#ed-panel", E.root).scrollTop = sc; }));
  $$("[data-caprel]", panel).forEach((b) => (b.onclick = () => { const c = captionAt(+b.dataset.caprel); if (c) relisten([{ start: c.start, end: c.end }]); }));
  const selLines = () => [...E.capSel].map((st) => captionAt(st)).filter(Boolean);
  on("#cap-sel-rel", "onclick", () => relisten(selLines().map((c) => ({ start: c.start, end: c.end }))));
  on("#cap-sel-del", "onclick", () => { const ws = selLines().flatMap((c) => c.words); if (!ws.length) return; if (!confirm(`${E.capSel.size} lines हटाएँ?`)) return; deleteWords(ws); E.capSel.clear(); touch(); afterTranscriptEdit(false, "lines हटाईं"); });
  on("#cap-io-del", "onclick", () => { if (E.markIn == null || E.markOut == null) return toast("पहले I और O से हिस्सा चुनें"); const ws = E.words.filter((w) => w.start < E.markOut && w.end > E.markIn); if (!ws.length) return toast("इस हिस्से में कोई शब्द नहीं"); deleteWords(ws); touch(); afterTranscriptEdit(false, `${ws.length} शब्द हटाए`); });
  on("#cap-io-rel", "onclick", () => { if (E.markIn == null || E.markOut == null) return toast("पहले I और O से हिस्सा चुनें"); relisten([{ start: E.markIn, end: E.markOut }]); });
  bindAlts(panel);
  on("#hook", "oninput", (e) => { E.rs.hook.text = e.target.value; touch(); });
  on("#fr-go", "onclick", () => { const f = $("#fr-find", panel).value.trim(), r = $("#fr-repl", panel).value.trim(); if (!f || !r || /\s/.test(f)) return toast("एक-एक शब्द लिखें");
    const strip = (w) => w.replace(/[।॥,.!?;:"'“”‘’()\[\]…-]/g, "").toLowerCase(); let n = 0;
    for (const seg of E.tr.segments) { for (const w of seg.words || []) if (strip(w.w) === strip(f)) { w.w = w.w.replace(new RegExp(f.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"), r); if (strip(w.w) !== strip(r)) w.w = r; n++; } seg.text = (seg.words || []).map((w) => w.w).join(" "); }
    syncWords(); if (n) { E.transcriptDirty = true; touch(); renderPanel(); renderOverlay(); } toast(n ? `${n} जगह बदला` : "नहीं मिला"); });
  on("#re-asr", "onclick", async () => { if (!confirm("transcript दोबारा बनेगा और कट फिर से ढूँढे जाएँगे (आपकी editing settings रहेंगी)। आगे बढ़ें?")) return; try { await flush(); await E.ctx.api("POST", `/projects/${E.pid}/retranscribe`); E.ctx.load().then(() => E && E.ctx.render()); toast("transcript दोबारा बन रहा है — कुछ मिनट"); } catch (e) { toast(e.message || "नहीं हुआ"); } });
  on("#hook-edit", "onclick", () => { if (!E.rs.hook.text) { E.rs.hook.text = "अपनी heading लिखें"; touch(); } seek(0); select({ type: "hook", id: "h" }); setTimeout(() => { const t = $('#inspector [data-k="text"]', E.root); if (t) { t.focus(); t.select(); } }, 40); });
  // text
  $$("[data-tpl]", panel).forEach((b) => (b.onclick = () => addTemplate(b.dataset.tpl)));
  $$("[data-tcat]", panel).forEach((b) => (b.onclick = () => { E.tCat = b.dataset.tcat; renderPanel(); }));
  $$("[data-tlang]", panel).forEach((b) => (b.onclick = () => { E.tLang = b.dataset.tlang; renderPanel(); }));
  on("#t-blank", "onclick", () => addTemplate(null));
  on("#ai-go", "onclick", async (e) => { e.target.disabled = true; e.target.textContent = "बन रहे…"; E.aiN = +$("#ai-n", panel).value; try { await flush(); E.ai = await api("GET", `/projects/${E.pid}/prompts?broll=${E.aiN}${$("#ai-plat", panel).value ? "&platform=" + $("#ai-plat", panel).value : ""}`); E.aiPack = await api("GET", `/projects/${E.pid}/aipack`).catch(() => null); } catch (er) { toast(er.message); } renderPanel(); });
  $$("[data-aiall]", panel).forEach((b) => (b.onclick = () => { const w = b.dataset.aiall; navigator.clipboard?.writeText(E.ai.batch[w]); window.open(w === "grok" ? "https://grok.com/imagine" : "https://chatgpt.com/", "_blank", "noopener"); toast("सारे prompts copy हुए — वहाँ एक बार paste करें"); }));
  on("#ai-pin", "onclick", () => { navigator.clipboard?.writeText(E.aiPack.pack.pinned_comment); toast("copy हुआ"); });
  $$("[data-aip]", panel).forEach((el) => (el.oninput = () => { E.ai.items[+el.dataset.aip].prompt = el.value; }));
  $$("[data-aicopy]", panel).forEach((b) => (b.onclick = () => { navigator.clipboard?.writeText(E.ai.items[+b.dataset.aicopy].prompt); toast("prompt copy हुआ"); }));
  $$("[data-aiopen]", panel).forEach((b) => (b.onclick = () => { const [svc, i] = b.dataset.aiopen.split(":"); const x = E.ai.items[+i]; const txt = svc === "chatgpt" && x.chatgpt ? x.chatgpt : x.prompt;
    navigator.clipboard?.writeText(txt); window.open(x.open?.[svc] || "https://grok.com/imagine", "_blank", "noopener"); toast("prompt copy हुआ — वहाँ paste करें"); }));
  $$("[data-aiup]", panel).forEach((el) => (el.onchange = async () => { const f = el.files[0]; if (!f) return; const x = E.ai.items[+el.dataset.aiup]; const isImg = f.type.startsWith("image/");
    const d = await libUpload(isImg ? "image" : "broll", f); if (!d) return; placeAi(x, d, isImg); }));
  on("#hk-load", "onclick", async () => { const box = $("#hk-body", panel); box.textContent = "जाँच हो रही है…"; try { await flush(); E.hk = await api("GET", `/projects/${E.pid}/hooks`); showHooks(); } catch (e) { box.textContent = e.message; } });
  if (E.hk) showHooks();
  on("#font-up", "onchange", async (e) => { for (const f of e.target.files) await libUpload("font", f); });
  on("#t-q", "oninput", (e) => { E.tQ = e.target.value; clearTimeout(E.tqT); E.tqT = setTimeout(() => { renderPanel(); const q = $("#t-q", panel); if (q) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); } }, 250); });
  $$("[data-title-id]", panel).forEach((li) => (li.onclick = () => { const ti = fx.titles.find((x) => x._id === li.dataset.titleId); select({ type: "title", id: ti._id }); seek(srcOf(ti.start)); }));
  // project clips
  on("#clip-file", "onchange", async (e) => { const files = [...e.target.files]; if (!files.length) return; const prog = $("#clip-progress", panel);
    const raw = E.p.assets.find((a) => a.kind === "raw"); const hasClips = E.p.assets.some((a) => a.kind === "clip");
    if (!hasClips && raw && !confirm("पहली recording को clip 1 बनाकर नई clips जोड़ें? (transcript दोबारा बनेगा)")) return;
    try {
      if (!hasClips && raw) await api("POST", `/projects/${E.pid}/clips/adopt`);
      for (let i = 0; i < files.length; i++) { const f = files[i]; await uploadClip(f, (d, tot) => { prog.innerHTML = `<p class="small muted">${esc(f.name)} ${(d / tot * 100).toFixed(0)}%</p><div class="progress"><i style="width:${(d / tot * 100).toFixed(0)}%"></i></div>`; }, i === files.length - 1); }
      toast("clips जुड़े — process शुरू"); const ctx = E.ctx; unmount(); await ctx.load(); ctx.render();
    } catch (err) { toast(err.message); prog.innerHTML = ""; } });
  $$("[data-clipdel]", panel).forEach((b) => (b.onclick = async () => { if (!confirm("clip हटाएँ? बाद में “दोबारा जोड़ें” दबाएँ।")) return; await api("DELETE", `/projects/${E.pid}/clips/${b.dataset.clipdel}`); E.p.assets = E.p.assets.filter((a) => a.id !== b.dataset.clipdel); renderPanel(); }));
  on("#clip-rebuild", "onclick", async () => { try { await api("POST", `/projects/${E.pid}/start`); toast("clips जुड़ रहे हैं"); const ctx = E.ctx; unmount(); await ctx.load(); ctx.render(); } catch (err) { toast(err.message); } });
  // library
  $$("[data-kind]", panel).forEach((b) => (b.onclick = () => { E.libKind = b.dataset.kind; E.libTag = ""; renderPanel(); }));
  $$("[data-ltag]", panel).forEach((b) => (b.onclick = () => { E.libTag = b.dataset.ltag; renderPanel(); }));
  on("#lib-q", "oninput", (e) => { E.libQ = e.target.value; const sc = panel.scrollTop; renderPanel(); panel.scrollTop = sc; const i = $("#lib-q", panel); i.focus(); i.setSelectionRange(i.value.length, i.value.length); });
  on("#lib-file", "onchange", async (e) => { for (const f of e.target.files) await libUpload(E.libKind, f); renderPanel(); });
  $$("[data-prev]", panel).forEach((b) => (b.onclick = () => { const x = libItem(b.dataset.prev); if (E.audio) { E.audio.pause(); if (E.audio.src === x.url) { E.audio = null; return; } } E.audio = new Audio(x.url); E.audio.play(); }));
  $$("[data-add]", panel).forEach((b) => (b.onclick = () => libAdd(libItem(b.dataset.add))));
  $$("[data-addclip]", panel).forEach((b) => (b.onclick = () => addAudioClip(libItem(b.dataset.addclip), E.t, 0)));
  $$("[data-del]", panel).forEach((b) => (b.onclick = async () => { if (!confirm("library से हटाएँ?")) return; await api("DELETE", `/library/${b.dataset.del}`); E.lib = E.lib.filter((x) => x.id !== b.dataset.del); renderPanel(); }));
  on("#mus-vol", "oninput", (e) => { fx.music.volume = +e.target.value; $("#mus-vol-v", panel) && ($("#mus-vol-v", panel).textContent = Math.round(fx.music.volume * 100) + "%"); touch(); });
  on("#mus-damt", "oninput", (e) => { fx.music.duck_amount = +e.target.value; touch(); });
  on("#mus-fade", "oninput", (e) => { fx.music.fade = +e.target.value; touch(); });
  on("#vc-preset", "onchange", (e) => { fx.voice = { preset: e.target.value }; touch(); renderPanel(); toast("आवाज़ preset बदला — Preview frame/Render में सुनें"); });
  on("#ap-go", "onclick", (e) => audioPreview(e.target));
  on("#vc-adv", "ontoggle", (e) => { E.audioOpen = e.target.open; });
  on("#vc-reset", "onclick", () => { fx.voice = { preset: fx.voice?.preset || "studio" }; touch(); renderPanel(); });
  $$("[data-vc]", panel).forEach((el) => (el.oninput = el.onchange = () => { fx.voice = fx.voice || { preset: "studio" }; const k = el.dataset.vc; fx.voice[k] = el.tagName === "SELECT" ? el.value : +el.value;
    const out = $(`[data-vcv="${k}"]`, panel); if (out) out.textContent = el.value; if (k === "volume") applyPreviewVolume(); touch(); }));
  on("#mus-duck", "onchange", (e) => { fx.music.duck = e.target.checked; touch(); });
  on("#mus-clear", "onclick", () => { fx.music.id = ""; touch(); renderPanel(); });
  if (E.tab === "audio") dubBox(null, panel);
  on("#wm-op", "oninput", (e) => { fx.watermark.opacity = +e.target.value; touch(); });
  on("#wm-size", "oninput", (e) => { fx.watermark.size = +e.target.value; touch(); });
  on("#wm-pos", "onchange", (e) => { fx.watermark.pos = e.target.value; touch(); });
  on("#wm-clear", "onclick", () => { fx.watermark.id = ""; touch(); renderPanel(); });
  on("#frm-op", "oninput", (e) => { fx.frame = fx.frame || {}; fx.frame.opacity = +e.target.value; touch(); });
  on("#frm-clear", "onclick", () => { fx.frame.id = ""; touch(); renderPanel(); });
  // montage
  if (E.montage && E.mo) {
    const mo = E.mo; const lib = E.lib || [];
    const sync = () => { const g = (id) => $(id, panel); mo.music = g("#mo-music")?.value ?? mo.music; mo.texts = g("#mo-texts")?.value ?? mo.texts; mo.font = g("#mo-font")?.value || mo.font; mo.text_color = g("#mo-color")?.value || mo.text_color;
      mo.text_size = +(g("#mo-size")?.value || mo.text_size); mo.every = +(g("#mo-every")?.value || mo.every); mo.max_seconds = +(g("#mo-max")?.value || mo.max_seconds); mo.preset = g("#mo-preset")?.value || mo.preset;
      mo.look = g("#mo-look")?.value || mo.look; if (g("#mo-flash")) mo.flash = g("#mo-flash").checked; mo.watermark = g("#mo-wm")?.value ?? mo.watermark;
      mo.pace = g("#mo-pace")?.value || mo.pace; mo.effects_level = g("#mo-fxl")?.value || mo.effects_level; mo.reframe = g("#mo-reframe")?.value || mo.reframe; if (g("#mo-slow")) mo.slowmo = g("#mo-slow").checked; };
    ["#mo-music", "#mo-texts", "#mo-font", "#mo-color", "#mo-size", "#mo-every", "#mo-max", "#mo-preset", "#mo-look", "#mo-flash", "#mo-wm", "#mo-pace", "#mo-fxl", "#mo-reframe", "#mo-slow"].forEach((sl) => on(sl, "onchange", sync));
    $$("[data-momode]", panel).forEach((b) => (b.onclick = () => { sync(); mo.mode = b.dataset.momode; if (mo.mode === "auto" && !mo.look) mo.look = "auto"; if (mo.mode !== "auto" && (mo.look === "auto" || String(mo.look).startsWith("grade:"))) mo.look = "none"; renderPanel(); }));
    $$("[data-moadd]", panel).forEach((b) => (b.onclick = () => { sync(); const x = lib.find((y) => y.id === b.dataset.moadd); mo.clips.push({ id: x.id, duration: x.meta?.duration }); renderPanel(); }));
    on("#mo-addall", "onclick", () => { sync(); lib.filter((x) => (x.kind === "broll" || x.kind === "image") && !mo.clips.some((c) => c.id === x.id)).forEach((x) => mo.clips.push({ id: x.id, duration: x.meta?.duration })); renderPanel(); });
    $$("[data-model]", panel).forEach((b) => (b.onclick = () => { sync(); mo.clips.splice(+b.dataset.model, 1); renderPanel(); }));
    $$("[data-moup]", panel).forEach((b) => (b.onclick = () => { sync(); const i = +b.dataset.moup; if (i > 0) { [mo.clips[i - 1], mo.clips[i]] = [mo.clips[i], mo.clips[i - 1]]; renderPanel(); } }));
    on("#mo-up", "onchange", async (e) => { sync(); for (const f of e.target.files) { const d = await libUpload(f.type.startsWith("image/") ? "image" : "broll", f); if (d) mo.clips.push({ id: d.id, duration: d.meta?.duration }); } renderPanel(); });
    on("#mo-mup", "onchange", async (e) => { sync(); const f = e.target.files[0]; if (!f) return; const d = await libUpload("music", f); if (d) mo.music = d.id; renderPanel(); });
    const body = (extra) => ({ ...mo, texts: String(mo.texts || "").split("\n").map((x) => x.trim()).filter(Boolean), ...extra });
    const send = async (extra, msg) => { sync(); if (!mo.clips.length) return toast("पहले clips डालें"); if (!mo.music) return toast("song/music चुनें");
      try { await api("POST", `/projects/${E.pid}/montage`, body(extra)); E.moDirty = false; toast(msg); await load(); renderPanel(); } catch (err) { toast(err.message); } };
    on("#mo-render", "onclick", () => send({ mode: "classic" }, "montage बन रहा है"));
    on("#mo-auto", "onclick", () => send({ mode: "auto", replan: true, auto_render: true, plan: null }, "clips देखे जा रहे हैं → plan → video ⏳"));
    on("#mo-plan", "onclick", () => send({ mode: "auto", replan: true, auto_render: false, plan: null }, "beat plan बन रहा है ⏳"));
    on("#mo-rerender", "onclick", () => send({ mode: "auto", replan: false, plan: mo.plan }, "आपके plan से video बन रहा है 🎬"));
    const pl = mo.plan; const dirty = () => { E.moDirty = true; renderPanel(); };
    if (pl) {
      $$("[data-mosel]", panel).forEach((li) => (li.onclick = (e) => { if (e.target.closest("select,button,input")) return; E.moSel = +li.dataset.mosel; renderPanel(); }));
      $$("[data-mokeep]", panel).forEach((c) => (c.onchange = () => { pl.segments[+c.dataset.mokeep].keep = c.checked; dirty(); }));
      $$("[data-mofx]", panel).forEach((c) => (c.onchange = () => { pl.segments[+c.dataset.mofx].fx = c.value; dirty(); }));
      $$("[data-momv]", panel).forEach((b) => (b.onclick = () => { const [i, d] = b.dataset.momv.split(":").map(Number); const j = i + d; if (j < 0) return; const a = pl.segments;
        // swap the moments, keep the durations on the beat grid
        const keys = ["clip", "src_in", "speed", "focus", "face", "highlight", "kind", "score"]; const t = {}; keys.forEach((k) => (t[k] = a[i][k])); keys.forEach((k) => (a[i][k] = a[j][k])); keys.forEach((k) => (a[j][k] = t[k])); dirty(); }));
      $$("[data-moalt]", panel).forEach((b) => (b.onclick = () => { const sg = pl.segments[+b.dataset.moalt]; const k = (pl.alts || []).findIndex((a) => a.clip === sg.clip) ;
        const k2 = k >= 0 ? k : (pl.alts || []).findIndex((a) => libItem(a.clip)?.kind !== "image"); if (k2 < 0) return toast("और हिस्से नहीं बचे");
        const a = pl.alts[k2]; pl.alts.splice(k2, 1, { clip: sg.clip, src_in: sg.src_in, score: sg.score, focus: sg.focus, face: sg.face }); Object.assign(sg, { clip: a.clip, src_in: a.src_in, focus: a.focus, face: a.face, score: a.score, speed: 1, kind: "video" }); dirty(); }));
      $$("[data-moins]", panel).forEach((b) => (b.onclick = () => { const a = pl.alts[+b.dataset.moins]; const at = E.moSel != null ? E.moSel + 1 : pl.segments.length; const d = +(2 * (pl.period || 0.5)).toFixed(3);
        pl.segments.splice(at, 0, { clip: a.clip, src_in: a.src_in, dur: d < 0.4 ? d * 2 : d, speed: 1, fx: "flash", pulse: [], focus: a.focus, face: a.face, score: a.score, keep: true, kind: "video", energy: .5 }); pl.alts.splice(+b.dataset.moins, 1); E.moSel = at; dirty(); }));
    }
  }
  // refs
  on("#ref-add", "onclick", async () => { const body = { kind: $("#ref-kind", panel).value, url: $("#ref-url", panel).value.trim(), note: $("#ref-note", panel).value.trim(), project_id: $("#ref-global", panel).checked ? null : E.pid };
    try { await api("POST", "/refs", body); await loadRefs(); } catch (err) { toast(err.message); } });
  $$("[data-refdel]", panel).forEach((b) => (b.onclick = async () => { await api("DELETE", `/refs/${b.dataset.refdel}`); await loadRefs(); }));
  // shorts
  on("#sh-plan", "onclick", async () => { await flush(); try { await api("POST", `/projects/${E.pid}/shorts/plan`, { options: { count: +$("#sh-count", panel).value } }); toast("Shorts ढूँढे जा रहे हैं"); E.shortsDirty = false; await load(); renderPanel(); } catch (err) { toast(err.message); } });
  on("#sh-add", "onclick", () => { if (E.markIn == null || E.markOut == null) return toast("पहले I और O से हिस्सा चुनें"); const sc = { id: "m" + uid().slice(0, 4), start: +E.markIn.toFixed(2), end: +E.markOut.toFixed(2), title: "", hook: "", selected: true }; E.shorts.push(sc); E.shortsDirty = true; E.markIn = E.markOut = null; $("#t-marks", E.root).textContent = ""; touch(); select({ type: "short", id: sc.id }); renderPanel(); });
  $$("[data-short]", panel).forEach((li) => (li.onclick = (e) => { const sc = E.shorts.find((x) => x.id === li.dataset.short); if (e.target.type === "checkbox") { sc.selected = e.target.checked; E.shortsDirty = true; touch(); renderPanel(); } else { select({ type: "short", id: sc.id }); seek(sc.start); renderPanel(); } }));
  on("#sh-preset", "onchange", (e) => { E.rs.shorts_preset = e.target.value; touch(); });
  on("#sh-face", "onchange", (e) => { E.rs.face_track = e.target.checked ? "auto" : "off"; touch(); });
  on("#sh-render", "onclick", async () => { E.rs.shorts_preset = $("#sh-preset", panel).value; E.dirty = true; if (!(await flush())) return toast("बदलाव सेव नहीं हुए — Shorts render नहीं चला");
    const clips = E.shorts.filter((x) => x.selected !== false).map(({ id, start, end, title, hook }) => ({ id, start, end, title, hook }));
    try { await api("POST", `/projects/${E.pid}/shorts/render`, { clips, render: JSON.parse(JSON.stringify(E.rs)) }); toast(`${clips.length} Shorts render शुरू`); E.shortsDirty = false; await load(); E.exportOpen = true; renderExport(); } catch (err) { toast(err.message); } });
  // effects
  on("#fx-zoom", "onchange", (e) => { fx.zoom.enabled = e.target.checked; touch(); });
  on("#fx-zoom-str", "oninput", (e) => { fx.zoom.strength = +e.target.value; touch(); });
  on("#fx-zoom-mode", "onchange", (e) => { fx.zoom.mode = e.target.value; fx.zoom.enabled = true; touch(); renderPanel(); });
  on("#fx-q", "oninput", (e) => { E.fxq = e.target.value; const sc = panel.scrollTop; renderPanel(); panel.scrollTop = sc; $("#fx-q", panel).focus(); const v = $("#fx-q", panel); v.setSelectionRange(v.value.length, v.value.length); });
  $$("[data-fxcat]", panel).forEach((b) => (b.onclick = () => { E.fxcat = b.dataset.fxcat; renderPanel(); }));
  $$("[data-fxmode]", panel).forEach((b) => (b.onclick = () => { E.fxMode = b.dataset.fxmode; const sc = panel.scrollTop; renderPanel(); $("#ed-panel", E.root).scrollTop = sc; }));
  $$("[data-fxclip]", panel).forEach((li) => (li.onclick = () => { const c = fx.fxclips.find((x) => x._id === li.dataset.fxclip); if (!c) return; seek(srcOf(c.start)); select({ type: "fxclip", id: c._id }); }));
  $$("[data-fxadd]", panel).forEach((b) => (b.onclick = () => { PRO.markTrendSeen(b.dataset.fxadd); if (E.fxMode !== "global") return addFxClip("effect", b.dataset.fxadd); fx.stack = fx.stack || []; if (fx.stack.length >= 8) return toast("एक साथ 8 effects तक"); fx.stack.push({ id: b.dataset.fxadd, params: {}, enabled: true }); touch(); layoutFrame(); renderPanel(); panel.scrollTop = 0; }));
  $$("[data-fxon]", panel).forEach((cb) => (cb.onchange = () => { fx.stack[+cb.dataset.fxon].enabled = cb.checked; touch(); layoutFrame(); renderPanel(); }));
  $$("[data-fxdel]", panel).forEach((b) => (b.onclick = () => { fx.stack.splice(+b.dataset.fxdel, 1); touch(); layoutFrame(); renderPanel(); }));
  $$("[data-fxup]", panel).forEach((b) => (b.onclick = () => { const i = +b.dataset.fxup; if (i > 0) { [fx.stack[i - 1], fx.stack[i]] = [fx.stack[i], fx.stack[i - 1]]; touch(); renderPanel(); } }));
  $$("[data-fxdown]", panel).forEach((b) => (b.onclick = () => { const i = +b.dataset.fxdown; if (i < fx.stack.length - 1) { [fx.stack[i + 1], fx.stack[i]] = [fx.stack[i], fx.stack[i + 1]]; touch(); renderPanel(); } }));
  $$("[data-fxp]", panel).forEach((inp) => (inp.oninput = () => { const [i, k] = inp.dataset.fxp.split(":"); const it = fx.stack[+i]; it.params = it.params || {}; it.params[k] = inp.type === "color" ? inp.value : +inp.value; const b = inp.parentElement.querySelector("b"); if (b) b.textContent = inp.value; touch(); layoutFrame(); }));
  // body
  if (fx.body) {
    const b = fx.body; const { api: api2, load: load2 } = E.ctx;
    bindBodyStatus(panel);
    on("#bd-on", "onchange", (e) => { b.enabled = e.target.checked; touch(); });
    on("#bd-bg", "onchange", (e) => { b.bg = e.target.value; touch(); renderPanel(); });
    on("#bd-blur", "oninput", (e) => { b.bg_blur = +e.target.value; touch(); });
    on("#bd-c1", "oninput", (e) => { b.bg_color = e.target.value; touch(); }); on("#bd-c2", "oninput", (e) => { b.bg_color2 = e.target.value; touch(); });
    $$("[data-bd]", panel).forEach((el) => (el.oninput = el.onchange = () => { const k = el.dataset.bd; b[k] = el.type === "checkbox" ? el.checked : el.type === "range" ? +el.value : el.value;
      const lab = el.closest(".ifield")?.querySelector("label b"); if (lab) lab.textContent = el.value + (k === "bg_speed" ? "×" : ""); touch(); if (el.type === "checkbox") renderPanel(); }));
    $$("[data-bdbg]", panel).forEach((el) => (el.onclick = () => { if (b.bg === "image") b.bg_image = el.dataset.bdbg; else b.bg_video = el.dataset.bdbg; touch(); renderPanel(); }));
    on("#bd-bgadv", "ontoggle", (e) => { E.bdBgOpen = e.target.open; });
    on("#bd-up", "onchange", async (e) => { const f = e.target.files[0]; if (!f) return; const d = await libUpload(b.bg === "image" ? "image" : "broll", f); if (d) { if (b.bg === "image") b.bg_image = d.id; else b.bg_video = d.id; touch(); } renderPanel(); });
    on("#bd-img", "onchange", (e) => { b.bg_image = e.target.value; touch(); }); on("#bd-vid", "onchange", (e) => { b.bg_video = e.target.value; touch(); });
    on("#bd-stroke", "onchange", (e) => { b.stroke = e.target.checked; touch(); }); on("#bd-sc", "oninput", (e) => { b.stroke_color = e.target.value; touch(); }); on("#bd-sw", "oninput", (e) => { b.stroke_width = +e.target.value; touch(); });
    on("#bd-glow", "onchange", (e) => { b.glow = e.target.checked; touch(); }); on("#bd-gc", "oninput", (e) => { b.glow_color = e.target.value; touch(); }); on("#bd-gs", "oninput", (e) => { b.glow_size = +e.target.value; touch(); });
    on("#bd-anim", "onchange", (e) => { b.anim = e.target.value; touch(); }); on("#bd-as", "oninput", (e) => { b.anim_seconds = +e.target.value; touch(); });
    on("#bd-after", "onchange", (e) => { b.afterimage = e.target.checked; touch(); }); on("#bd-clones", "onchange", (e) => { b.clones = +e.target.value; touch(); });
    $$("[data-bdp]", panel).forEach((btn) => (btn.onclick = () => { const P = { pop_white: { bg: "blur", stroke: true, stroke_color: "#FFFFFF", stroke_width: 10, glow: false, anim: "pop" }, neon: { bg: "dim", stroke: true, stroke_color: "#00FFD0", stroke_width: 4, glow: true, glow_color: "#00FFD0", glow_size: 30, anim: "none" }, sky: { bg: "blur", stroke: true, stroke_color: "#FFFFFF", stroke_width: 8, anim: "drop", anim_seconds: 0.9 }, blink: { bg: "flat", bg_color: "#0b0b0b", stroke: true, stroke_color: "#F2B33D", stroke_width: 6, anim: "blink", blink_period: 0.35 }, ghost: { bg: "dim", afterimage: true, after_decay: 0.92, clones: 0, anim: "none" }, flat: { bg: "flat", bg_color: "#F2B33D", stroke: true, stroke_color: "#111111", stroke_width: 6, glow: false } }[btn.dataset.bdp]; Object.assign(b, P, { enabled: true }); touch(); renderPanel(); }));
  }
  // color
  const setGrade = (name, val) => { fx.grade = fx.grade || {}; fx.grade[name] = val; fx.grade_preset = ""; touch(); layoutFrame(); };
  $$("[data-g]", panel).forEach((inp) => (inp.oninput = () => { setGrade(inp.dataset.g, +inp.value); inp.parentElement.querySelector("b").textContent = (+inp.value).toFixed(2).replace(/\.?0+$/, ""); $$(".look", panel).forEach((x) => x.classList.remove("on")); }));
  const scaledGrade = (id, k) => { const p = S.presets.catalog.grade_presets[id]; return Object.fromEntries(Object.entries(p).filter(([n]) => n !== "label" && n !== "cat").map(([n, v]) => [n, +(v * k).toFixed(3)])); };
  $$("[data-gpre]", panel).forEach((b) => { b.onclick = () => { if (E.fxMode !== "global") return addFxClip("filter", b.dataset.gpre); fx.grade =scaledGrade(b.dataset.gpre, fx.grade_strength ?? 1); fx.grade_preset = b.dataset.gpre; touch(); layoutFrame(); renderPanel(); };
    b.onmouseenter = () => { const v = $("#pv", E.root); if (v) v.style.filter = gradeCss(scaledGrade(b.dataset.gpre, fx.grade_strength ?? 1)); };
    b.onmouseleave = () => layoutFrame(); });
  $$("[data-gcat]", panel).forEach((b) => (b.onclick = () => { E.gCat = b.dataset.gcat; renderPanel(); }));
  on("#g-strength", "oninput", (e) => { fx.grade_strength = +e.target.value; $("#gs-v", panel).textContent = Math.round(fx.grade_strength * 100) + "%"; if (fx.grade_preset && S.presets.catalog.grade_presets[fx.grade_preset]) { fx.grade = scaledGrade(fx.grade_preset, fx.grade_strength); layoutFrame(); } touch(); });
  on("#gr-reset", "onclick", () => { fx.grade = {}; fx.grade_preset = ""; touch(); layoutFrame(); renderPanel(); });
  on("#gr-copy", "onclick", () => { try { localStorage.setItem("vividora_grade", JSON.stringify(fx.grade || {})); toast("grade copy हुआ"); } catch {} });
  on("#gr-paste", "onclick", () => { try { const g = JSON.parse(localStorage.getItem("vividora_grade") || "{}"); fx.grade = g; fx.grade_preset = ""; touch(); layoutFrame(); renderPanel(); } catch {} });
  const ab = $("#gr-ab", panel); if (ab) { ab.onmousedown = () => { E.bypass = true; layoutFrame(); }; ab.onmouseup = ab.onmouseleave = () => { E.bypass = false; layoutFrame(); }; }
  $$("[data-tr]", panel).forEach((b) => (b.onclick = () => { fx.transition = b.dataset.tr; fx.flash = false; $$(".trbtn", panel).forEach((x) => x.classList.toggle("on", x === b)); touch(); }));
  $$("[data-extra]", panel).forEach((cb) => (cb.onchange = () => { fx.extras = $$("[data-extra]:checked", panel).map((x) => x.dataset.extra); touch(); }));
  $$("[data-look]", panel).forEach((b) => (b.onclick = () => { fx.look = b.dataset.look; $$(".look", panel).forEach((x) => x.classList.toggle("on", x === b)); layoutFrame(); touch(); }));
}
async function uploadClip(file, onProgress, startAfter) {
  const { api } = E.ctx; const pid = E.pid;
  const up = await api("POST", `/projects/${pid}/uploads`, { filename: file.name, size: file.size, clip: true });
  let off = up.received; const chunk = up.chunk;
  while (off < file.size) { const part = file.slice(off, Math.min(file.size, off + chunk)); let r;
    try { r = await api("PUT", `/projects/${pid}/uploads/${up.upload_id}/chunk`, null, { data: part, offset: off }); } catch (err) { if (err.received != null) { off = err.received; continue; } throw err; }
    off = r.received; onProgress(off, file.size); }
  return api("POST", `/projects/${pid}/uploads/${up.upload_id}/finish`, { start: !!startAfter });
}
function libItem(id) { return (E.lib || []).find((x) => x.id === id); }
async function loadRefs() { try { E.refs = await E.ctx.api("GET", `/refs?project_id=${E.pid}`); } catch { E.refs = []; } if (E && E.tab === "refs") renderPanel(); }
function fontList() { return [...new Set([...(E.ctx.S.presets?.fonts || []), ...(E.lib || []).filter((x) => x.kind === "font").map((x) => x.meta?.family || x.name)])]; }
function injectFonts() {
  const fonts = (E.lib || []).filter((x) => x.kind === "font"); let st = document.getElementById("vivid-user-fonts");
  if (!st) { st = document.createElement("style"); st.id = "vivid-user-fonts"; document.head.appendChild(st); }
  st.textContent = fonts.map((f) => `@font-face{font-family:"${(f.meta?.family || f.name).replace(/"/g, "")}";src:url("${f.url}");}`).join("\n");
}
async function loadLib() { try { E.lib = await E.ctx.api("GET", "/library"); } catch { E.lib = []; } injectFonts(); if (E && ["media", "audio", "overlay", "montage"].includes(E.tab)) renderPanel(); else renderOverlay(); }
async function libUpload(kind, file) {
  const { toast } = E.ctx; const prog = $("#lib-progress", E.root) || document.createElement("div");
  prog.innerHTML = `<p class="small muted">${file.name} upload हो रहा…</p><div class="progress"><i style="width:30%"></i></div>`;
  try {
    const r = await fetch(`/api/library?kind=${kind}&filename=${encodeURIComponent(file.name)}`, { method: "PUT", headers: { authorization: "Bearer " + E.ctx.S.token, "content-type": "application/octet-stream" }, body: file });
    const data = await r.json(); if (!r.ok) throw new Error(data.error || r.statusText);
    E.lib = E.lib || []; E.lib.unshift(data); toast(`${file.name} जुड़ा`); prog.innerHTML = ""; if (kind === "font") { injectFonts(); renderPanel(); } return data;
  } catch (err) { toast(err.message); }
  prog.innerHTML = "";
}
// what autopilot put on the timeline, by kind — each kind can be removed on its own (single items: click them on the timeline → Del)
const isAp = (x) => String(x?._id || "").startsWith("ap_") || !!x?.auto;
function apGroups() {
  const fx = E.rs.effects;
  return [
    ["kw", "emoji sticker", fx.broll.filter((x) => isAp(x) && (x.auto === "keyword" || String(x._id).startsWith("ap_kw")))],
    ["hl", "highlight text", fx.titles.filter(isAp)],
    ["cta", "CTA popup", fx.broll.filter((x) => isAp(x) && /^ap_(cta|bell)/.test(String(x._id)))],
    ["obr", "दूसरे overlay", fx.broll.filter((x) => isAp(x) && x.auto !== "keyword" && !/^ap_(cta|bell|kw)/.test(String(x._id)))],
    ["sfx", "sound effect", fx.sfx.filter(isAp)],
  ].filter(([, , a]) => a.length);
}
function autopilotBox() {
  const fx = E.rs.effects; const dis = E.canEdit ? "" : "disabled"; const { esc } = E.ctx;
  const groups = apGroups();
  const globals = [fx.zoom?.enabled && ["zoom", "zoom"], (fx.transition || "none") !== "none" && ["tr", "transition"], Object.keys(fx.grade || {}).length && ["grade", "filter"], fx.music?.id && ["music", "music"], E.rs.hook?.text && ["hook", "hook heading"]].filter(Boolean);
  return `<div class="sugg apbox"><b>🤖 Autopilot</b><p class="small muted">${E.p.settings?.autopilot ? "इस project पर autopilot चला था।" : "Autopilot इस recording पर अपने-आप editing कर सकता है।"} timeline पर <b class="aptag">AP</b> वाले items autopilot के हैं — क्लिक करके बदलें, Del से हटाएँ।</p>
    ${groups.length || globals.length ? `<div class="apchips">${groups.map(([k, l, a]) => `<span class="apchip">${a.length} ${esc(l)}<button class="ibtn" data-apdel="${k}" title="सारे ${esc(l)} हटाएँ" ${dis}>✕</button></span>`).join("")}${globals.map(([k, l]) => `<span class="apchip">${esc(l)}<button class="ibtn" data-apdel="${k}" title="${esc(l)} हटाएँ" ${dis}>✕</button></span>`).join("")}</div>` : `<p class="small muted">अभी autopilot का कोई item नहीं।</p>`}
    <div class="irow"><button class="btn small primary" data-apgo="items" ${dis} title="stickers, highlight text, CTA, sfx दोबारा">✨ Auto stickers/text लगाएँ</button><button class="btn small" data-apgo="all" ${dis}>पूरी autopilot editing</button>${groups.length ? `<button class="btn small quiet" data-apgo="clear" ${dis}>सारे autopilot items हटाएँ</button>` : ""}</div>
    <p class="small muted">क्या-क्या करे — Settings → Brand kit → Autopilot में चुनें।</p></div>`;
}
function apRemove(kind) {
  const fx = E.rs.effects; let n = 0;
  if (kind === "zoom") fx.zoom.enabled = false; else if (kind === "tr") { fx.transition = "none"; fx.flash = false; } else if (kind === "grade") { fx.grade = {}; fx.grade_preset = ""; }
  else if (kind === "music") fx.music.id = ""; else if (kind === "hook") E.rs.hook.text = "";
  else { const g = apGroups().find(([k]) => k === kind); if (g) { const drop = new Set(g[2]); n = drop.size; for (const k of ["broll", "titles", "sfx"]) fx[k] = fx[k].filter((x) => !drop.has(x)); } }
  if (E.sel && !selItem()) E.sel = null;
  touch(); layoutFrame(); renderInspector(); renderPanel(); return n;
}
function toLocalInput(iso) { const d = new Date(iso); if (isNaN(d)) return ""; const z = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}T${z(d.getHours())}:${z(d.getMinutes())}`; }
function fromLocalInput(v) { if (!v) return null; const d = new Date(v); return isNaN(d) ? null : d.toISOString(); }
function pfHtml() {
  const { esc } = E.ctx; if (!E.pf) return `<span class="muted">duration, hook, safe zone, hashtags — हर platform के नियम</span>`;
  if (!E.pf.items.length) return "✅ सब platforms के नियम पूरे";
  const ic = { block: "⛔", warn: "⚠️", tip: "💡" };
  return E.pf.items.map((x, i) => `<div class="pfrow">${ic[x.level]} <b>${esc(x.platform)}</b> — ${esc(x.msg)}${x.fix && E.canEdit ? ` <button class="btn small" data-pffix="${i}">ठीक करें</button>` : ""}${x.item ? ` <button class="btn small quiet" data-pfsel="${esc(x.item)}">दिखाएँ</button>` : ""}</div>`).join("");
}
function bindPf(m) {
  $$("[data-pffix]", m).forEach((b) => (b.onclick = () => { applyPatch(E.rs, E.pf.items[+b.dataset.pffix].fix); E.pf.items.splice(+b.dataset.pffix, 1); touch(); renderExport(); }));
  $$("[data-pfsel]", m).forEach((b) => (b.onclick = () => { const id = b.dataset.pfsel; const fx = E.rs.effects; const t = fx.titles.find((x) => x._id === id); E.exportOpen = false; renderExport();
    if (t) { seek(srcOf(t.start)); select({ type: "title", id }); } else if (fx.broll.find((x) => x._id === id)) { const bb = fx.broll.find((x) => x._id === id); seek(srcOf(bb.start)); select({ type: "broll", id }); } }));
}
function applyPatch(target, patch) {
  for (const [k, v] of Object.entries(patch || {})) {
    if (k === "effects" && v && typeof v === "object") { target.effects = target.effects || {}; for (const [k2, v2] of Object.entries(v)) target.effects[k2] = JSON.parse(JSON.stringify(v2)); }
    else target[k] = JSON.parse(JSON.stringify(v));
  }
}
function addCtaPopups() {
  const fx = E.rs.effects; const at = +(outDur() * 0.75).toFixed(2); const lib = E.lib || [];
  const find = (names) => { for (const n of names) { const x = lib.find((i) => i.kind === "sticker" && i.name.toLowerCase().includes(n)); if (x) return x; } return null; };
  let n = 0;
  for (const [fam, names] of [["youtube", ["subscribe red", "subscribe"]], ["instagram", ["follow insta", "follow"]], ["facebook", ["follow facebook", "follow insta", "follow"]]]) {
    const x = find(names); if (!x) continue; fx.broll = fx.broll.filter((b) => b._id !== "ap_cta_" + fam);
    fx.broll.push({ _id: "ap_cta_" + fam, id: x.id, start: at, end: +Math.min(outDur(), at + 2.8).toFixed(2), fit: "free", x: 0.5, y: 0.6, scale: 0.6, opacity: 1, rotate: 0, anim: "pop", platforms: [fam] }); n++;
  }
  return n;
}
async function loadSuggestions(force) {
  const box = $("#sugg-list", E.root); if (!box) return;
  if (E.sugg && !force) return showSuggestions();
  box.innerHTML = "जाँच हो रही है…";
  try { if (E.dirty) await flush(); } catch (_) {}
  try { E.sugg = await E.ctx.api("GET", `/projects/${E.pid}/suggest`); showSuggestions(); } catch (e) { box.textContent = e.message || "नहीं हुआ"; }
}
function showSuggestions() {
  const box = $("#sugg-list", E.root); if (!box || !E.sugg) return; const { esc } = E.ctx; const items = E.sugg.items || [];
  const a = E.sugg.analysis || {}; const v = a.video || {}; const au = a.audio || {}; const pc = E.sugg.pace || {};
  const stats = `<div class="sstats">${v.luma != null ? `<span>रोशनी ${Math.round((v.luma_center ?? v.luma) * 100)}%</span><span>contrast ${Math.round(v.contrast * 100)}</span><span>रंग ${Math.round(v.saturation * 100)}%</span>` : ""}${au.snr_db != null ? `<span>आवाज़/शोर ${au.snr_db} dB</span>` : ""}${pc.wpm ? `<span>${pc.wpm} शब्द/मिनट</span>` : ""}</div>`;
  if (!items.length) { box.innerHTML = stats + `<p>✅ सब ठीक लग रहा है।</p>`; return; }
  const dot = { high: "🔴", mid: "🟡", low: "🔵" };
  box.innerHTML = stats + `<ul class="plist">${items.map((it, i) => `<li><span class="grow"><b>${dot[it.level]} ${esc(it.title)}</b><br><span class="muted">${esc(it.detail)}</span></span>${E.canEdit && (it.fix || it.action) ? `<button class="btn small" data-sfix="${i}">${it.fix ? "ठीक करें" : "खोलें"}</button>` : ""}</li>`).join("")}</ul>
    ${E.canEdit && items.some((x) => x.fix) ? `<button class="btn small primary" id="sugg-all">सब ठीक करें (${items.filter((x) => x.fix).length})</button>` : ""}`;
  const run = (it) => {
    if (it.fix) { applyPatch(E.rs, it.fix); }
    else if (it.action === "hook") { $("#hook-edit", E.root)?.click() || (E.tab = "text", renderPanel(), setTimeout(() => $("#hook-edit", E.root)?.click(), 30)); return; }
    else if (it.action === "cta") { const n = addCtaPopups(); E.ctx.toast(n ? `${n} platform के popup जुड़े` : "library में popup नहीं मिले"); }
    else if (["media", "cuts", "shorts"].includes(it.action)) { E.tab = it.action; renderPanel(); $$("[data-tab]", E.root).forEach((x) => x.classList.toggle("on", x.dataset.tab === it.action)); return; }
    touch(); renderPanel(); renderOverlay(); renderTimeline();
  };
  $$("[data-sfix]", box).forEach((b) => (b.onclick = () => { const it = items[+b.dataset.sfix]; run(it); if (it.fix || it.action === "cta") { E.sugg.items = items.filter((x) => x !== it); showSuggestions(); E.ctx.toast("लगाया — preview/Render में देखें"); } }));
  const all = $("#sugg-all", box); if (all) all.onclick = () => { for (const it of items.filter((x) => x.fix)) applyPatch(E.rs, it.fix); E.sugg.items = items.filter((x) => !x.fix); touch(); renderPanel(); renderOverlay(); renderTimeline(); showSuggestions(); E.ctx.toast("सारे सुधार लगाए"); };
}
async function audioPreview(btn) {
  btn.disabled = true; const old = btn.textContent; btn.textContent = "बन रहा है…";
  try { const r = await fetch(`/api/projects/${E.pid}/audio-preview`, { method: "POST", headers: { authorization: "Bearer " + E.ctx.S.token, "content-type": "application/json" }, body: JSON.stringify({ t: E.t, seconds: 12, render: JSON.parse(JSON.stringify(E.rs)) }) });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || "नहीं बना");
    const url = URL.createObjectURL(await r.blob()); const au = $("#ap-audio", E.root); $("#pv", E.root)?.pause(); au.src = url; au.hidden = false; au.play();
  } catch (e) { E.ctx.toast(e.message); } finally { btn.disabled = false; btn.textContent = old; }
}
function voiceValues() {
  const S = E.ctx.S; const P = S.presets?.voice_params || {}; const PR = S.presets?.voice_presets || {}; const v = E.rs.effects.voice || { preset: "studio" };
  const out = {}; for (const [k, spec] of Object.entries(P)) out[k] = spec.default;
  Object.assign(out, Object.fromEntries(Object.entries(PR[v.preset || "studio"] || {}).filter(([k]) => k !== "label")));
  for (const [k, val] of Object.entries(v)) if (k !== "preset" && val !== "" && val != null) out[k] = val;
  return out;
}
function applyPreviewVolume() { const pv = $("#pv", E.root); if (pv) pv.volume = Math.max(0, Math.min(1, +(voiceValues().volume ?? 1))); }
function audioControls(dis) {
  const { esc } = E.ctx; const S = E.ctx.S; const fx = E.rs.effects; const music = fx.music; const P = S.presets?.voice_params || {}; const PR = S.presets?.voice_presets || {};
  const v = fx.voice || { preset: "studio" }; const vals = voiceValues();
  const slider = (k) => { const sp = P[k]; if (!sp) return ""; if (sp.choices) return field(sp.label, `<select data-vc="${k}" ${dis}>${sp.choices.map((c) => `<option value="${c}" ${vals[k] === c ? "selected" : ""}>${{ strong: "तेज़ (AI)", light: "हल्का", off: "बंद" }[c] || c}</option>`).join("")}</select>`);
    return field(`${sp.label} <b data-vcv="${k}">${vals[k]}</b>`, `<input type="range" data-vc="${k}" min="${sp.min}" max="${sp.max}" step="${sp.step}" value="${vals[k]}" ${dis}>`); };
  return `<div class="box audioctl"><div class="row between"><b>🎙 आवाज़ (Voice)</b><button class="btn small quiet" id="vc-reset" ${dis}>preset पर वापस</button></div>
      <div class="irow"><button class="btn small primary" id="ap-go" title="playhead से 12 सेकंड final आवाज़ (voice + music)">🔊 बदलाव सुनें (12s)</button><audio id="ap-audio" controls hidden style="height:30px;flex:1"></audio></div>
      ${field("preset", `<select id="vc-preset" ${dis}>${Object.entries(PR).map(([k, x]) => `<option value="${k}" ${(v.preset || "studio") === k ? "selected" : ""}>${esc(x.label)}</option>`).join("")}</select>`)}
      <div class="irow">${slider("volume")}${slider("denoise")}</div>
      <details ${E.audioOpen ? "open" : ""} id="vc-adv"><summary class="small">EQ, compressor और बाकी settings</summary>
        <div class="irow">${slider("bass")}${slider("mud")}</div><div class="irow">${slider("presence")}${slider("treble")}</div>
        <div class="irow">${slider("highpass")}${slider("deess")}</div><div class="irow">${slider("compress")}${slider("gate")}</div>
        <div class="irow">${slider("fade_in")}${slider("fade_out")}</div>${slider("loudness")}
        <p class="small muted">noise “तेज़ (AI)” upload के समय DeepFilterNet से साफ़ हुई आवाज़ लेता है। बदलाव final render/preview frame में सुनाई देंगे।</p></details></div>
    <div class="box audioctl"><b>🎵 Background music</b>${music.id ? `<p class="small">${esc(libItem(music.id)?.name || music.id)}</p>` : `<p class="small muted">नीचे music में “लगाएँ” दबाएँ</p>`}
      <div class="irow">${field(`volume <b id="mus-vol-v">${Math.round((music.volume ?? 0.18) * 100)}%</b>`, `<input type="range" id="mus-vol" min="0" max="1" step="0.01" value="${music.volume ?? 0.18}" ${dis}>`)}${field("fade in/out (s)", `<input type="range" id="mus-fade" min="0" max="6" step="0.5" value="${music.fade ?? 1.5}" ${dis}>`)}</div>
      <div class="irow"><label class="chk small"><input type="checkbox" id="mus-duck" ${music.duck !== false ? "checked" : ""} ${dis}> बोलते समय धीमा (duck)</label>${field("कितना धीमा", `<input type="range" id="mus-damt" min="0.1" max="1" step="0.05" value="${music.duck_amount ?? 0.6}" ${dis}>`)}</div>
      ${music.id ? `<button class="btn small quiet" id="mus-clear">हटाएँ</button>` : ""}</div>
    <p class="small muted">SFX की volume: timeline पर SFX पर क्लिक करें।</p>`;
}
// AI voice-over / dubbing box (Audio tab). dubBox(dis) → HTML; dubBox(null, panel) → binds it.
function dubBox(dis, panel) {
  const { esc, api, toast } = E.ctx; const fx = E.rs.effects; const D = E.ctx.S.presets?.dub || { voices: [], langs: { hi: "हिन्दी", en: "English" }, modes: {} };
  const st = (E.dub = E.dub || { mode: E.montage ? "script" : "revoice", lang: E.p.language === "en" ? "en" : "hi", voice: "", speed: 1, script: "", desc: "" });
  if (E.montage) st.mode = "script";
  const tracks = E.p.assets.filter((a) => a.kind === "dub");
  const job = (E.p.jobs || []).filter((j) => j.kind === "dub").sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))[0];
  const active = job && ["queued", "running"].includes(job.status);
  const progText = (j) => !j ? "" : j.status === "queued" ? "⏳ queue में — GPU worker (या TTS_LOCAL वाला CPU worker) का इंतज़ार" : j.status === "running" ? `🔄 ${j.progress || 0}% · ${j.message || "बन रहा है"}`
    : j.status === "failed" ? `⚠️ नहीं बना: ${(j.error || "").split("\n")[0].replace(/^[\w.]*(TTSMissing|ValueError|RuntimeError): /, "")}` : "";
  if (panel) {
    const box = $("#dub-box", panel); if (!box) return;
    const q = (s) => $(s, box);
    const keep = () => { st.mode = q("#dub-mode")?.value || st.mode; st.lang = q("#dub-lang")?.value || st.lang; st.voice = q("#dub-voice")?.value ?? st.voice; st.speed = +(q("#dub-speed")?.value || st.speed); st.script = q("#dub-script")?.value ?? st.script; st.desc = q("#dub-desc")?.value ?? st.desc; };
    ["#dub-mode", "#dub-lang"].forEach((s) => { const el = q(s); if (el) el.onchange = () => { keep(); st.voice = ""; renderPanel(); }; });
    ["#dub-voice", "#dub-script", "#dub-desc"].forEach((s) => { const el = q(s); if (el) el.oninput = el.onchange = keep; });
    const sp = q("#dub-speed"); if (sp) sp.oninput = () => { keep(); q("#dub-speed-v").textContent = st.speed.toFixed(2) + "×"; };
    const go = q("#dub-go"); if (go) go.onclick = async () => {
      keep(); if (st.mode === "script" && st.script.trim().length < 3) return toast("पहले script लिखें");
      go.disabled = true; go.textContent = st.mode === "dub" ? "translate हो रहा…" : "भेज रहे…";
      try { await flush();
        const r = await api("POST", `/projects/${E.pid}/dub`, { mode: st.mode, language: st.mode === "revoice" ? null : st.lang, voice: st.voice || null, description: st.desc || null, speed: st.speed, script: st.mode === "script" ? st.script : "" });
        E.p.jobs = [{ ...r.job, status: "queued", created_at: new Date().toISOString() }, ...(E.p.jobs || [])];
        toast(`AI voice-over शुरू · ${r.lines} lines${r.translated?.length ? ` · “${r.translated[0].slice(0, 40)}…”` : ""}`); E.ctx.load().catch(() => {});
      } catch (er) { toast(er.message); }
      renderPanel(); };
    let audio = null;
    $$("[data-dubplay]", box).forEach((b) => (b.onclick = () => { const a = tracks.find((x) => x.id === b.dataset.dubplay); if (!a) return;
      if (audio && !audio.paused && audio.dataset.id === a.id) { audio.pause(); return; }
      if (audio) audio.pause(); audio = new Audio(a.url); audio.dataset.id = a.id; audio.play().catch((e) => toast(e.message)); }));
    $$("[data-dubdel]", box).forEach((b) => (b.onclick = async () => { if (!confirm("यह AI voice track हटाएँ?")) return;
      try { await api("DELETE", `/projects/${E.pid}/dub/${b.dataset.dubdel}`); E.p.assets = E.p.assets.filter((a) => a.id !== b.dataset.dubdel); if (fx.voice_track === b.dataset.dubdel) { fx.voice_track = "original"; touch(); } renderPanel(); } catch (er) { toast(er.message); } }));
    const use = q("#dub-use"); if (use) use.onchange = () => { const v = use.value; fx.voice_track = v === "original" ? "original" : v.replace(/^both:/, ""); fx.voice_track_mode = v.startsWith("both:") ? "both" : "replace";
      touch(); renderPanel(); toast(v === "original" ? "मूल आवाज़ — render में यही" : `AI आवाज़ लगी — ${E.montage ? "Montage दोबारा बनाएँ" : "Render"} में सुनें`); };
    const un = q("#dub-under"); if (un) un.oninput = () => { fx.voice_track_under = +un.value; q("#dub-under-v").textContent = Math.round(fx.voice_track_under * 100) + "%"; touch(); };
    clearInterval(E.dubT);
    if (active) { const me = E; E.dubT = setInterval(() => { if (E !== me || E.tab !== "audio") return clearInterval(me.dubT);
      const j = (E.p.jobs || []).find((x) => x.id === job.id) || job; const el = $("#dub-prog", E.root); if (el) el.textContent = progText(j);
      if (!["queued", "running"].includes(j.status)) { clearInterval(E.dubT); if (!(document.activeElement && box.contains(document.activeElement))) renderPanel(); if (j.status === "done") toast("AI voice-over तैयार 🎙"); } }, 2000); }
    return;
  }
  const lang = st.mode === "revoice" ? (E.p.transcript?.language === "en" || E.p.language === "en" ? "en" : "hi") : st.lang;
  const voices = D.voices.filter((v) => v.lang === lang);
  const cur = fx.voice_track || "original"; const curVal = cur === "original" ? "original" : (fx.voice_track_mode === "both" && !E.montage ? "both:" : "") + cur;
  const vlabel = (a) => `${D.langs[a.label] || a.label} · ${a.meta?.voice?.label || ""} · ${fmt(a.meta?.duration || 0)}`;
  return `<div class="box audioctl" id="dub-box"><b>🗣 AI voice-over / dubbing</b>
    <p class="small muted">अपनी बात साफ़ AI आवाज़ में, हिन्दी↔English dub, या लिखी script से voice-over (faceless/montage)। Models commercial इस्तेमाल के लिए safe हैं (Indic Parler-TTS, Kokoro)।</p>
    <div class="irow">${field("क्या बनाना है", `<select id="dub-mode" ${dis}>${(E.montage ? ["script"] : ["revoice", "dub", "script"]).map((m) => `<option value="${m}" ${st.mode === m ? "selected" : ""}>${esc(D.modes[m] || m)}</option>`).join("")}</select>`)}
      ${field("भाषा", st.mode === "revoice" ? `<select disabled><option>${esc(D.langs[lang] || lang)} (transcript जैसी)</option></select>` : `<select id="dub-lang" ${dis}>${Object.entries(D.langs).map(([k, l]) => `<option value="${k}" ${st.lang === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`)}</div>
    ${field("आवाज़", `<select id="dub-voice" ${dis}>${voices.map((v) => `<option value="${v.id}" ${st.voice === v.id ? "selected" : ""}>${esc(v.label)}</option>`).join("")}</select>`)}
    <div class="irow">${field(`speed <b id="dub-speed-v">${(+st.speed).toFixed(2)}×</b>`, `<input type="range" id="dub-speed" min="0.8" max="1.25" step="0.05" value="${st.speed}" ${dis}>`)}</div>
    <details><summary class="small">अपनी आवाज़ का description (English में, Parler)</summary><input id="dub-desc" value="${esc(st.desc)}" placeholder="Rohit speaks with a deep, confident, warm tone at a moderate pace, very clear audio" ${dis}></details>
    ${st.mode === "script" ? field("Script", `<textarea id="dub-script" rows="6" placeholder="यहाँ script लिखें या paste करें… (खाली line = नया paragraph, थोड़ा लंबा रुकना)" ${dis}>${esc(st.script)}</textarea>`) : ""}
    ${st.mode === "dub" ? `<p class="small muted">transcript एक ही AI call में translate होता है (server में GEMINI_API_KEY चाहिए), फिर हर line अपनी जगह fit होती है।</p>` : ""}
    <div class="irow"><button class="btn small primary" id="dub-go" ${dis || (active ? "disabled" : "")}>🎙 बनाएँ</button><span class="small muted grow" id="dub-prog">${esc(progText(job))}</span></div>
    ${tracks.length ? `<ul class="plist">${tracks.map((a) => `<li><button class="ibtn" data-dubplay="${a.id}" title="सुनें">${ICON.play}</button><span class="grow small">${esc(vlabel(a))}${a.meta?.mode ? ` <span class="muted">· ${esc(D.modes[a.meta.mode] || a.meta.mode)}</span>` : ""}</span>${E.canEdit ? `<button class="ibtn" data-dubdel="${a.id}" title="हटाएँ">${ICON.trash}</button>` : ""}</li>`).join("")}</ul>` : ""}
    ${field("इसे इस्तेमाल करें (render की आवाज़)", `<select id="dub-use" ${dis}><option value="original" ${curVal === "original" ? "selected" : ""}>${E.montage ? "कोई voice-over नहीं (सिर्फ़ music)" : "मूल आवाज़ (original)"}</option>${tracks.map((a) => `<option value="${a.id}" ${curVal === a.id ? "selected" : ""}>🗣 ${esc(vlabel(a))}</option>${E.montage ? "" : `<option value="both:${a.id}" ${curVal === "both:" + a.id ? "selected" : ""}>दोनों: ${esc(D.langs[a.label] || a.label)} AI + original धीमी</option>`}`).join("")}</select>`)}
    ${curVal.startsWith("both:") ? field(`original कितनी <b id="dub-under-v">${Math.round((fx.voice_track_under ?? 0.25) * 100)}%</b>`, `<input type="range" id="dub-under" min="0" max="0.8" step="0.05" value="${fx.voice_track_under ?? 0.25}" ${dis}>`) : ""}
    ${cur !== "original" ? `<p class="small muted">captions अब AI आवाज़ के शब्दों से बनेंगे। कट/speed बदलें तो dub दोबारा बनाएँ।</p>` : ""}</div>`;
}
function showHooks() {
  const box = $("#hk-body", E.root); const h = E.hk; if (!box || !h) return; const { esc } = E.ctx; const col = h.score >= 75 ? "#46a758" : h.score >= 50 ? "#f2b33d" : "#e5484d";
  box.innerHTML = `<div class="row" style="gap:.6rem;align-items:center"><span class="hkscore" style="border-color:${col};color:${col}">${h.score}</span><span>${h.platform === "long" ? "पहले 8s (long video)" : "पहले 3s (Shorts/Reels)"} · पहला शब्द ${h.first_word_at ?? "—"}s पर</span></div>
    ${h.reasons.map((r) => `<div>✅ ${esc(r)}</div>`).join("")}${h.fixes.map((r) => `<div>⚠️ ${esc(r)}</div>`).join("")}
    <h4 style="margin:.5rem 0 .2rem">Hook options</h4>${(h.options || []).map((o, i) => `<div class="hkopt"><b>${esc(o.heading)}</b><span class="muted">बोलें: “${esc(o.say)}” · ${esc(o.type || "")}${o.source === "ai" ? " · AI" : ""}</span>
      <span class="row" style="gap:.3rem"><button class="btn small" data-hkuse="${i}" ${E.canEdit ? "" : "disabled"}>heading लगाएँ</button><button class="btn small quiet" data-hkcopy="${i}">line copy</button></span></div>`).join("") || "<div>transcript से option नहीं बने</div>"}`;
  $$("[data-hkuse]", box).forEach((b) => (b.onclick = () => { E.rs.hook.text = h.options[+b.dataset.hkuse].heading; E.rs.hook.seconds = E.rs.hook.seconds || 3; touch(); seek(0); renderOverlay(); E.ctx.toast("Hook heading लगी"); }));
  $$("[data-hkcopy]", box).forEach((b) => (b.onclick = () => { navigator.clipboard?.writeText(h.options[+b.dataset.hkcopy].say); E.ctx.toast("copy हुआ — teleprompter में paste करके दोबारा record करें"); }));
}
function textGallery(dis) {
  const { esc } = E.ctx; const T = E.ctx.S.presets?.textfx; if (!T) return `<p class="small muted">लोड हो रहा…</p>`;
  const cat = E.tCat || "", lang = E.tLang || "", q = (E.tQ || "").toLowerCase();
  const list = T.templates.filter((x) => (!cat || x.cat === cat) && (!lang || x.lang === lang) && (!q || (x.text + " " + x.label).toLowerCase().includes(q)));
  return `<div class="irow"><button class="btn small primary" id="t-blank" ${dis}>+ खाली text</button><input id="t-q" class="grow" placeholder="खोजें…" value="${esc(E.tQ || "")}"></div>
    <div class="chips"><button class="${!lang ? "on" : ""}" data-tlang="">सब</button><button class="${lang === "hi" ? "on" : ""}" data-tlang="hi">हिंदी</button><button class="${lang === "en" ? "on" : ""}" data-tlang="en">English</button></div>
    <div class="chips">${[["", "सब"], ...Object.entries(T.template_cats)].map(([k, l]) => `<button class="${cat === k ? "on" : ""}" data-tcat="${k}">${esc(l)}</button>`).join("")}</div>
    <p class="small muted">${list.length} templates · क्लिक = playhead पर जुड़ेगा · animation बाद में बदलें</p>
    <div class="tplgrid">${list.map((x) => { const st = { ...x.style, size: Math.min(0.11, Math.max(0.05, (x.style.size || 0.075) * (x.text.length > 16 ? 0.62 : x.text.length > 9 ? 0.85 : 1.1))) };
      return `<button class="tpl" data-tpl="${x.id}" ${dis} title="${esc(x.label)} · ${esc(T.anim_in[x.anim_in]?.label || "")} → ${esc(T.anim_out[x.anim_out]?.label || "")}"><span class="tplv"><span style="${TFX.textStyle(st, 300)}color:${st.color || "#fff"};display:inline-block;max-width:100%;line-height:1.15;transform:rotate(${-(st.rotate || 0)}deg)">${esc(x.text.split("|")[0])}</span></span><small>${esc(x.label)}${x.anim_loop !== "none" ? " · ∞" : ""}</small></button>`; }).join("")}</div>`;
}
function addTemplate(id) {
  if (!E.canEdit) return; const T = E.ctx.S.presets?.textfx; const fx = E.rs.effects; const st = +outOf(E.t).toFixed(2);
  const x = id ? T.templates.find((t) => t.id === id) : null;
  const ti = { _id: uid(), start: st, end: +Math.min(outDur(), st + 3).toFixed(2), track: 0,
    ...(x ? x.style : { pos: "center", size: 0.075, color: "#FFFFFF", font: "Poppins", outline: "#000000", outline_w: 0.006 }),
    text: x ? x.text : "अपना text", anim_in: x ? x.anim_in : "pop", anim_out: x ? x.anim_out : "fade", anim_loop: x ? x.anim_loop : "none", template: id || "" };
  fx.titles.push(ti); touch(); select({ type: "title", id: ti._id }); renderPanel();
  setTimeout(() => { const ta = $('#inspector [data-k="text"]', E.root); if (ta) { ta.focus(); ta.select(); } }, 40);
}
function animSelect(kind, value, dis) {
  const T = E.ctx.S.presets?.textfx; const table = T?.[kind] || {}; const { esc } = E.ctx; const groups = {};
  for (const [k, a] of Object.entries(table)) (groups[a.cat] = groups[a.cat] || []).push([k, a]);
  return `<select data-k="${kind}" ${dis}>${Object.entries(groups).map(([c, arr]) => `<optgroup label="${esc(T.anim_cats[c] || c)}">${arr.map(([k, a]) => `<option value="${k}" ${value === k ? "selected" : ""}>${esc(a.label)}</option>`).join("")}</optgroup>`).join("")}</select>`;
}
function titleInspector(it, dis) {
  const { esc } = E.ctx; const ti = TFX.normalize(it); Object.assign(it, { anim_in: ti.anim_in, anim_out: ti.anim_out, anim_loop: ti.anim_loop }); delete it.anim;
  const fonts = E.ctx.S.presets?.fonts || []; const on = { _outline: (it.outline_w ?? 0) > 0 && !!it.outline, _shadow: !!it.shadow }; const chk = (k, l) => `<label class="chk small"><input type="checkbox" data-k="${k}" ${(k in on ? on[k] : it[k]) ? "checked" : ""} ${dis}> ${l}</label>`;
  const rng = (k, l, min, max, step, def) => field(`${l} <b>${(+(it[k] ?? def)).toFixed(step < 0.01 ? 3 : step < 1 ? 2 : 0)}</b>`, `<input type="range" data-k="${k}" min="${min}" max="${max}" step="${step}" value="${it[k] ?? def}" ${dis}>`);
  return `<h3>Text</h3>${field("लिखें ( | से नई लाइन )", `<textarea data-k="text" rows="2" ${dis}>${esc(it.text)}</textarea>`)}
    <div class="irow">${field("शुरू", num("start", it.start, 0.1, 0))}${field("ख़त्म", num("end", it.end, 0.1, 0))}${field("track", num("track", it.track || 0, 1, 0, 9))}</div>
    <details open class="insp"><summary>Style</summary>
      <div class="irow">${field("font", `<select data-k="font" ${dis}><option value="">Poppins</option>${fonts.map((f) => `<option ${it.font === f ? "selected" : ""}>${f}</option>`).join("")}</select>`)}${rng("size", "आकार", 0.025, 0.25, 0.005, 0.075)}</div>
      <div class="irow">${field("रंग", `<input type="color" data-k="color" value="${it.color || "#ffffff"}" ${dis}>`)}<label class="chk small"><input type="checkbox" data-k="_bold" ${it.bold === false ? "" : "checked"} ${dis}> <b>Bold</b></label>${chk("italic", "<i>Italic</i>")}${chk("underline", "<u>U</u>")}</div>
      <div class="irow">${field("align", `<select data-k="align" ${dis}>${[["", "बीच"], ["left", "बाएँ"], ["right", "दाएँ"]].map(([v, l]) => `<option value="${v}" ${(it.align || "") === v ? "selected" : ""}>${l}</option>`).join("")}</select>`)}${rng("spacing", "अक्षर दूरी", -0.005, 0.04, 0.001, 0)}</div>
      <div class="irow">${chk("_outline", "Outline")}${field("", `<input type="color" data-k="outline" value="${it.outline || "#000000"}" ${dis}>`)}${rng("outline_w", "मोटाई", 0, 0.03, 0.001, 0.006)}</div>
      <div class="irow">${chk("_shadow", "Shadow")}${field("", `<input type="color" data-k="shadow" value="${it.shadow || "#000000"}" ${dis}>`)}${rng("shadow_d", "दूरी", 0, 0.03, 0.001, 0.004)}</div>
      <div class="irow">${chk("box", "Box / background")}${field("", `<input type="color" data-k="box_color" value="${it.box_color || "#000000"}" ${dis}>`)}${rng("box_alpha", "पारदर्शी", 0, 0.9, 0.05, 0)}${rng("box_pad", "padding", 0.004, 0.05, 0.002, 0.016)}</div>
      <div class="irow">${rng("rotate", "घुमाव°", -45, 45, 1, 0)}${rng("opacity", "opacity", 0.1, 1, 0.05, 1)}</div>
    </details>
    <details open class="insp"><summary>जगह</summary>
      <div class="irow">${field("", `<select data-k="pos" ${dis}>${[["top", "ऊपर"], ["center", "बीच"], ["bottom", "नीचे"], ["free", "free (खींचें)"]].map(([v, l]) => `<option value="${v}" ${(it.pos || "top") === v ? "selected" : ""}>${l}</option>`).join("")}</select>`)}${it.pos === "free" ? rng("x", "X", 0.02, 0.98, 0.01, 0.5) + rng("y", "Y", 0.02, 0.98, 0.01, 0.5) : ""}</div>
      <p class="small muted">preview में text को खींचकर कहीं भी रखें।</p></details>
    <details open class="insp"><summary>Animation</summary>
      <div class="irow">${field("आना (in)", animSelect("anim_in", it.anim_in, dis))}${field("ms", `<input type="number" data-k="in_ms" min="100" max="4000" step="50" value="${it.in_ms || ""}" placeholder="auto" ${dis}>`)}</div>
      <div class="irow">${field("जाना (out)", animSelect("anim_out", it.anim_out, dis))}${field("ms", `<input type="number" data-k="out_ms" min="100" max="3000" step="50" value="${it.out_ms || ""}" placeholder="auto" ${dis}>`)}</div>
      <div class="irow">${field("बीच में (loop)", animSelect("anim_loop", it.anim_loop, dis))}${field("speed ms", `<input type="number" data-k="loop_ms" min="80" max="8000" step="20" value="${it.loop_ms || ""}" placeholder="auto" ${dis}>`)}</div>
      <button class="btn small" data-act="tplay">▶ animation देखें</button></details>
    <div class="irow"><button class="btn small" data-act="seek">यहाँ जाएँ</button><button class="btn small" data-act="tdup" ${dis}>Duplicate</button><button class="btn small danger quiet" data-act="del">${ICON.trash} हटाएँ</button></div>`;
}
function placeAi(x, item, isImg) {
  const fx = E.rs.effects; const len = x.seconds || 3;
  if (x.kind === "background") { fx.body = { ...(fx.body || {}), enabled: true, bg: isImg ? "image" : "video", [isImg ? "bg_image" : "bg_video"]: item.id }; touch(); E.ctx.toast("Cutout background लगा — Cutout tab में cutout बनाएँ/देखें"); return; }
  if (x.kind === "thumbnail") { E.ctx.toast("Library में जुड़ा — Thumbnail studio में background के रूप में चुनें"); return; }
  const st = +(x.at || 0).toFixed(2); const b = { _id: uid(), id: item.id, start: st, end: +Math.min(outDur(), st + Math.min(len, item.meta?.duration || len)).toFixed(2), fit: "cover", track: 0, ai: x.kind };
  if (x.kind === "broll" && isImg) Object.assign(b, { fit: "pip", pos: "tr" });
  fx.broll.push(b); touch(); select({ type: "broll", id: b._id }); renderTimeline(); E.ctx.toast(x.kind === "hook" ? "Hook video शुरुआत में लगा" : "B-roll उस line पर लगा");
}
function addAudioClip(x, src, track) {
  if (!x || !E.canEdit) return; const s = { _id: uid(), id: x.id, at: +outOf(src).toFixed(2), volume: x.kind === "music" ? 0.5 : 0.8, track: track || 0 };
  E.rs.effects.sfx.push(s); touch(); select({ type: "sfx", id: s._id }); E.ctx.toast(`${x.name} audio track पर जुड़ा`);
}
function libAdd(x, at) {
  if (!x || !E.canEdit) return; const fx = E.rs.effects; const st = +outOf(at?.src ?? E.t).toFixed(2);
  if (x.kind === "music") fx.music.id = x.id;
  else if (x.kind === "logo") fx.watermark.id = x.id;
  else if (x.kind === "lut") fx.look = "lut:" + x.id;
  else if (x.kind === "frame") fx.frame = { id: x.id, opacity: fx.frame?.opacity ?? 1 };
  else if (x.kind === "sticker" || (x.kind === "image" && at?.free)) { const b = { _id: uid(), id: x.id, start: st, end: +Math.min(outDur(), st + 3).toFixed(2), fit: "free", x: at?.x ?? 0.5, y: at?.y ?? 0.35, scale: (x.tags || "").includes("popup") ? 0.55 : 0.3, opacity: 1, rotate: 0, anim: "pop" }; fx.broll.push(b); select({ type: "broll", id: b._id }); }
  else if (x.kind === "sfx") { const s = { _id: uid(), id: x.id, at: st, volume: 0.8 }; fx.sfx.push(s); select({ type: "sfx", id: s._id }); }
  else { const d = x.kind === "image" ? 3 : Math.min(x.meta?.duration || 4, 8); const b = { _id: uid(), id: x.id, start: st, end: +Math.min(outDur(), st + d).toFixed(2), fit: x.kind === "image" ? "pip" : "cover", pos: "tr" }; fx.broll.push(b); select({ type: "broll", id: b._id }); }
  touch(); renderPanel();
  if (["logo", "frame", "lut"].includes(x.kind)) select({ type: "global", id: { logo: "watermark", frame: "frame", lut: "lut" }[x.kind] });
  E.ctx.toast(`${x.name} जुड़ा`);
}
function bindDrops() {
  // library items, effect cards and filter thumbnails can all be dragged onto the preview or a timeline lane
  const drag = (e) => { const li = e.target.closest?.("[data-lib],[data-fxadd],[data-gpre]"); if (!li) return;
    if (li.dataset.lib) e.dataTransfer.setData("text/vivid-lib", li.dataset.lib);
    else e.dataTransfer.setData("text/vivid-fx", li.dataset.fxadd ? "effect:" + li.dataset.fxadd : "filter:" + li.dataset.gpre);
    e.dataTransfer.effectAllowed = "copy"; };
  const panel = $("#ed-panel", E.root); if (panel && !panel._dnd) { panel._dnd = 1; panel.addEventListener("dragstart", drag); }
  const ours = (e) => [...(e.dataTransfer?.types || [])].some((t) => t === "text/vivid-lib" || t === "text/vivid-fx");
  const allow = (e) => { if (ours(e)) { e.preventDefault(); e.currentTarget.classList.add("dropon"); } };
  const leave = (e) => e.currentTarget.classList.remove("dropon");
  const fxOf = (e) => { const v = e.dataTransfer.getData("text/vivid-fx"); if (!v) return null; const i = v.indexOf(":"); return [v.slice(0, i), v.slice(i + 1)]; };
  const stage = $("#ovl", E.root)?.parentElement; const tl = $("#tl-scroll", E.root);
  if (stage && !stage._dnd) { stage._dnd = 1; stage.addEventListener("dragover", allow); stage.addEventListener("dragleave", leave);
    stage.addEventListener("drop", (e) => { e.preventDefault(); stage.classList.remove("dropon"); const f = fxOf(e); if (f) return addFxClip(f[0], f[1]);
      const x = libItem(e.dataTransfer.getData("text/vivid-lib")); const fb = E.frameBox; if (!x || !fb) return;
      const r = $("#ovl", E.root).getBoundingClientRect(); libAdd(x, { free: true, x: +clamp((e.clientX - r.left) / fb.w, 0, 1).toFixed(3), y: +clamp((e.clientY - r.top) / fb.h, 0, 1).toFixed(3) }); }); }
  if (tl && !tl._dnd) { tl._dnd = 1; tl.addEventListener("dragover", allow); tl.addEventListener("dragleave", leave);
    tl.addEventListener("drop", (e) => { e.preventDefault(); tl.classList.remove("dropon"); const body = $("#tl-body", E.root); if (!body) return;
      const src = clamp((e.clientX - body.getBoundingClientRect().left) / E.pps, 0, E.dur);
      const lane = e.target.closest("[data-track]")?.dataset.track || ""; const [lk, ln] = lane.split(":");
      const f = fxOf(e); if (f) { seek(src); return addFxClip(f[0], f[1], src, lk === "fx" && ln != null ? +ln : 0); }
      const x = libItem(e.dataTransfer.getData("text/vivid-lib")); if (!x) return; seek(src);
      if ((x.kind === "music" || x.kind === "sfx") && lk === "audio" && ln != null) return addAudioClip(x, src, +ln);
      const n0 = E.rs.effects.broll.length; libAdd(x, { src, free: x.kind === "image" && lk === "broll" });
      if (lk === "broll" && ln != null && E.rs.effects.broll.length > n0) { E.rs.effects.broll[E.rs.effects.broll.length - 1].track = +ln; touch(); renderTimeline(); } }); }
}

// ---------- effect / filter clips (a time range on an FX track; render applies them only there) ----------
function scaledGrade(id, k) { const p = E.ctx.S.presets?.catalog?.grade_presets?.[id]; if (!p) return {}; return Object.fromEntries(Object.entries(p).filter(([n]) => n !== "label" && n !== "cat").map(([n, v]) => [n, +(v * k).toFixed(3)])); }
function addFxClip(kind, key, at, track) {
  if (!E.canEdit) return; const fx = E.rs.effects; const total = outDur();
  let st = +outOf(at ?? E.t).toFixed(2); if (total - st < 0.5) st = +Math.max(0, total - 3).toFixed(2);
  const c = { _id: uid(), kind, start: st, end: +Math.min(total, st + 3).toFixed(2), track: track || 0, enabled: true };
  if (kind === "filter") Object.assign(c, { preset: key, strength: 1, grade: scaledGrade(key, 1) }); else Object.assign(c, { id: key, params: {} });
  fx.fxclips.push(c); touch(); select({ type: "fxclip", id: c._id }); renderPanel();
  E.ctx.toast(`${fxClipLabel(c)} ${fmt(c.start)}–${fmt(c.end)} पर लगा — किनारे खींचकर समय बदलें`);
}
function fxClipToGlobal(c) {
  const fx = E.rs.effects;
  if (c.kind === "filter") { fx.grade = JSON.parse(JSON.stringify(c.grade || {})); fx.grade_preset = c.preset || ""; fx.grade_strength = c.strength ?? 1; }
  else { fx.stack = fx.stack || []; fx.stack.push({ id: c.id, params: JSON.parse(JSON.stringify(c.params || {})), enabled: true }); }
  fx.fxclips = fx.fxclips.filter((x) => x !== c); touch(); select(null); layoutFrame(); renderPanel(); E.ctx.toast("अब पूरे वीडियो पर लगा");
}
function fxClipInspector(it, dis) {
  const { esc } = E.ctx; const d = it.kind === "effect" ? fxDef(it.id) : null; const pr = d ? fxParams(d, it.params) : {};
  return `<h3>${it.kind === "filter" ? "🎨 Filter" : "✨ Effect"} <span class="tag">${esc(fxClipLabel(it))}</span></h3><p class="small muted">सिर्फ़ इस समय पर लगेगा (export में भी)। किनारे खींचकर छोटा/बड़ा, बीच से खींचकर आगे-पीछे या दूसरे FX track पर।</p>
    <div class="irow">${field("शुरू", num("start", it.start, 0.1, 0))}${field("ख़त्म", num("end", it.end, 0.1, 0))}${field("track", num("track", it.track || 0, 1, 0, 9))}</div>
    <label class="chk small"><input type="checkbox" data-k="enabled" ${it.enabled !== false ? "checked" : ""} ${dis}> चालू</label>
    ${it.kind === "filter" ? field(`intensity <b>${Math.round((it.strength ?? 1) * 100)}%</b>`, `<input type="range" data-fstr="1" min="0" max="1.5" step="0.05" value="${it.strength ?? 1}" ${dis}>`)
      : d ? PRO.fxParamsHtml(it, d, dis) : ""}
    ${d && d.preview !== "css" ? `<p class="small muted">यह effect preview में नहीं दिखता — “🎞 Preview frame” या render में देखें।</p>` : ""}
    <div class="irow"><button class="btn small" data-act="seek">यहाँ जाएँ</button><button class="btn small quiet" data-act="fxglobal" ${dis}>पूरे वीडियो पर लगाएँ</button><button class="btn small danger quiet" data-act="del" ${dis}>${ICON.trash} हटाएँ</button></div>`;
}
function bindFxClipInspector(ins, it) {
  if (E.sel?.type !== "fxclip" || !it) return;
  PRO.bindFxParams(ins);
  $$("[data-fxcp]", ins).forEach((el) => (el.oninput = () => { if (!E.canEdit) return; it.params = it.params || {}; it.params[el.dataset.fxcp] = el.type === "color" ? el.value : +el.value; const b = el.closest(".ifield")?.querySelector("label b"); if (b) b.textContent = el.value; touch(); layoutFrame(); }));
  const fs = $("[data-fstr]", ins); if (fs) fs.oninput = () => { if (!E.canEdit) return; it.strength = +fs.value; it.grade = scaledGrade(it.preset, it.strength); const b = fs.closest(".ifield")?.querySelector("label b"); if (b) b.textContent = Math.round(it.strength * 100) + "%"; touch(); layoutFrame(); };
}
function fxModeSeg() { const g = E.fxMode === "global"; return `<div class="seg fxmode"><button data-fxmode="clip" class="${g ? "" : "on"}" title="playhead से 3 सेकंड, timeline के FX track पर">⏱ playhead पर (clip)</button><button data-fxmode="global" class="${g ? "on" : ""}">▭ पूरे वीडियो पर</button></div>`; }
// what the preview <video> looks like right now: whole-video look/grade/effects + the effect/filter clips under the playhead
function videoFilter() {
  if (E.bypass) return ""; const fx = E.rs.effects; const ot = outOf(E.t); const hid = new Set(fx.hidden_tracks || []);
  const act = (fx.fxclips || []).filter((c) => c.enabled !== false && ot >= c.start && ot < c.end && !hid.has(`fx:${c.track || 0}`)).sort((a, b) => (a.track || 0) - (b.track || 0));
  return [PRO.colorFilter(fx.pro?.color, "main"), LOOK_CSS[fx.look] || "", gradeCss(fx.grade), stackCss(fx.stack), ...act.map((c) => (c.kind === "filter" ? gradeCss(c.grade) : stackCss([{ id: c.id, params: c.params }])))].filter(Boolean).join(" ");
}

// ---------- timeline ----------
// main video pieces: kept ranges, further divided by the user's split points (source time)
function segments() {
  const out = [];
  for (const [a, b] of keeps()) {
    const pts = [a, ...E.splits.filter((x) => x > a + 0.02 && x < b - 0.02).sort((x, y) => x - y), b];
    for (let i = 0; i < pts.length - 1; i++) out.push({ a: pts[i], b: pts[i + 1] });
  }
  return out;
}
function segAt(id) { const ss = segments(); return ss.find((s) => Math.abs(s.a - id) < 1e-3) || ss.find((s) => s.a <= id && id < s.b) || null; }
function laneCounts() {
  const fx = E.rs.effects; const mx = (arr) => (arr || []).reduce((m, x) => Math.max(m, (x.track || 0) + 1), 1); const t = fx.tracks || {};
  return { text: Math.max(t.text || 1, mx(fx.titles)), broll: Math.max(t.broll || 1, mx(fx.broll)), audio: Math.max(t.audio || 1, mx(fx.sfx)), fx: Math.max(t.fx || 1, mx(fx.fxclips)) };
}
// items that overlap on one lane get their own row (otherwise the top one hides the others and can't be clicked)
function rowsOf(items, span) {
  const rows = []; const at = new Map();
  for (const it of [...items].sort((a, b) => span(a)[0] - span(b)[0])) {
    const [s, e] = span(it); let r = rows.findIndex((end) => end <= s + 1e-3); if (r < 0) { r = rows.length; rows.push(0); } rows[r] = e; at.set(it, r);
  }
  return { n: Math.max(1, rows.length), at };
}
const LANE_H = 46;
function fxClipLabel(c) { return c.kind === "filter" ? (E.ctx.S.presets?.catalog?.grade_presets?.[c.preset]?.label || "Filter") : (fxDef(c.id)?.label || c.id); }
function renderTimeline() {
  const body = $("#tl-body", E.root), labels = $("#tl-labels", E.root); if (!body) return;
  if (E.montage) { labels.innerHTML = ""; body.innerHTML = `<p class="small muted" style="padding:1rem">Montage beat पर अपने-आप कटता है — settings बाएँ panel में। Export से platform चुनें।</p>`; $("#tl-info", E.root).textContent = E.p.meta?.bpm ? `${E.p.meta.bpm} BPM · ${fmt(E.p.meta.duration || 0)}` : ""; return; }
  const { esc } = E.ctx; const pps = E.pps; const W = Math.ceil(E.dur * pps) + 80; const fx = E.rs.effects;
  const X = (src) => (src * pps).toFixed(1); const OX = (out) => X(srcOf(out)); const OW = (a, b) => Math.max(6, (srcOf(b) - srcOf(a)) * pps).toFixed(1);
  const step = pps >= 80 ? 0.5 : pps >= 40 ? 1 : pps >= 16 ? 2 : pps >= 8 ? 5 : 10;
  let ruler = ""; for (let t = 0; t <= E.dur; t += step) ruler += `<span style="left:${X(t)}px" class="${t % (step * 5) === 0 ? "maj" : ""}">${t % (step * 5) === 0 ? fmt(t).replace(/\.0$/, "") : ""}</span>`;
  const sel = (type, id) => (E.sel?.type === type && E.sel.id === id ? "sel" : "");
  const clipMarks = (E.p.meta?.clips || []).map((c, i) => `<div class="clipmark" style="left:${X(c.start)}px" title="${esc(c.name)}"><span>${i + 1}. ${esc(c.name.replace(/^clip\d+_/, "").slice(0, 16))}</span></div>`).join("");
  const speedRow = (E.speed || []).map((sp) => `<div class="speedblk ${sel("speed", sp.id)}" data-speed="${sp.id}" style="left:${X(sp.start)}px;width:${Math.max(6, (sp.end - sp.start) * pps).toFixed(1)}px" title="${sp.rate}×"><span>${sp.rate}×</span></div>`).join("");
  const segSel = E.sel?.type === "seg" ? segAt(E.sel.id) : null;
  const video = clipMarks + speedRow + segments().map((s) => `<div class="clip ${E.sel?.type === "video" || (segSel && Math.abs(segSel.a - s.a) < 1e-3) ? "sel" : ""}" data-mainclip="${s.a}" style="left:${X(s.a)}px;width:${((s.b - s.a) * pps).toFixed(1)}px"><span>${fmt(s.b - s.a)}</span></div>`).join("")
    + E.splits.filter((x) => !cutAt(x)).map((x) => `<div class="splitmark" style="left:${X(x)}px" title="split ${fmt(x)}"></div>`).join("")
    + E.cuts.map((c) => `<div class="cutblk ${c.enabled === false ? "off" : ""} ${sel("cut", c.id)}" data-cut="${c.id}" style="left:${X(c.start)}px;width:${Math.max(4, (c.end - c.start) * pps).toFixed(1)}px" title="${c.reason} ${fmt(c.start)}–${fmt(c.end)}${c.transition ? " · " + c.transition : ""}"><i class="h l"></i>${c.transition ? `<b class="trb">${c.transition.startsWith("x_") ? "⇄" : "✦"}</b>` : ""}${c.enabled !== false && morphOn(c) ? `<b class="mcb" title="🌗 morph cut">🌗</b>` : ""}<i class="h r"></i></div>`).join("")
    + (E.markIn != null && E.markOut != null ? `<div class="markrange" style="left:${X(E.markIn)}px;width:${((E.markOut - E.markIn) * pps).toFixed(1)}px"></div>` : "");
  const capSelSt = E.sel?.type === "caption" ? captionAt(E.sel.id)?.start : null;
  const caps = captionChunks().map((c) => `<div class="capblk ${capSelSt === c.start ? "sel" : ""} ${rangeBusy(c.start, c.end) ? "busy" : ""}" data-capst="${c.start}" style="left:${X(c.start)}px;width:${Math.max(6, (c.end - c.start) * pps).toFixed(1)}px" title="${esc(c.words.map((w) => w.w).join(" "))}"><span>${esc(c.words.map((w) => w.w).join(" "))}</span></div>`).join("");
  const rowCss = (R, it) => { if (R.n < 2) return ""; const r = R.at.get(it) || 0; const hh = (LANE_H * Math.max(1, R.n * 0.6) - 6) / R.n; return `top:${(3 + r * hh).toFixed(1)}px;bottom:auto;height:${(hh - 2).toFixed(1)}px;`; };
  const laneH = (R) => (R.n < 2 ? LANE_H : Math.round(LANE_H * R.n * 0.6));
  const apTag = (x) => (String(x._id || "").startsWith("ap_") ? `<b class="aptag" title="autopilot ने लगाया">AP</b>` : "");
  const titleEl = (t, R) => `<div class="itm title ${sel("title", t._id)}" data-item="title:${t._id}" style="left:${OX(t.start)}px;width:${OW(t.start, t.end)}px;${rowCss(R, t)}"><i class="h l"></i>${apTag(t)}<span>${esc(t.text)}</span><i class="h r"></i></div>`;
  const hookEl = E.rs.hook.text ? `<div class="itm hook ${sel("hook", "h")}" data-hook="1" style="left:0;width:${OW(0, Math.min(outDur(), E.rs.hook.seconds || 3))}px"><span>HOOK ${esc(E.rs.hook.text)}</span></div>` : "";
  const brollEl = (b, R) => `<div class="itm broll ${sel("broll", b._id)}" data-item="broll:${b._id}" style="left:${OX(b.start)}px;width:${OW(b.start, b.end)}px;${rowCss(R, b)}"><i class="h l"></i>${apTag(b)}<span>${esc(libItem(b.id)?.name || "B-roll")}${b.fit === "pip" ? " · PiP" : ""}${b.speed_ramp?.length > 1 ? " · ⤳" : +b.speed && +b.speed !== 1 ? ` · ${b.speed}×` : ""}${b.mask?.shape ? " · ⬭" : ""}${b.blend_mode && b.blend_mode !== "normal" ? " · " + b.blend_mode : ""}${+b.volume > 0 ? " · 🔊" : ""}${b.blend && b.blend !== "normal" ? " · " + b.blend : ""}${b.platforms?.length ? ` · ${b.platforms.map((x) => ({ youtube: "YT", instagram: "IG", facebook: "FB" }[x])).join("/")}` : ""}</span><i class="h r"></i></div>`;
  const sfxLen = (s) => { const it = libItem(s.id); return s.dur || Math.min(it?.meta?.duration || 0.6, 600); };
  const sfxEl = (s, R) => { const it = libItem(s.id); const w = Math.max(14, sfxLen(s) * pps); return `<div class="itm sfx ${sel("sfx", s._id)}" data-item="sfx:${s._id}" style="left:${OX(s.at)}px;width:${w.toFixed(1)}px;${rowCss(R, s)}" title="${esc(it?.name || "audio")}">${w >= 28 ? `<i class="h l"></i>` : ""}${apTag(s)}<span>${it?.kind === "music" ? "♪ " : ""}${esc(it?.name || "sfx")} · ${Math.round((s.volume ?? 0.8) * 100)}%</span>${w >= 28 ? `<i class="h r"></i>` : ""}</div>`; };
  const fxEl = (c, R) => `<div class="itm fxc ${c.kind === "filter" ? "filter" : ""} ${c.enabled === false ? "off" : ""} ${sel("fxclip", c._id)}" data-item="fxclip:${c._id}" style="left:${OX(c.start)}px;width:${OW(c.start, c.end)}px;${rowCss(R, c)}"><i class="h l"></i><span>${c.kind === "filter" ? "🎨" : "✨"} ${esc(fxClipLabel(c))}</span><i class="h r"></i></div>`;
  const audio = (fx.music.id ? `<div class="itm music ${sel("music", "m")}" data-item="music:m" style="left:0;width:${(E.dur * pps).toFixed(1)}px"><span>♪ ${esc(libItem(fx.music.id)?.name || "music")} · ${Math.round(fx.music.volume * 100)}%${fx.music.duck !== false ? " · duck" : ""}</span></div>` : "");
  const shortsRow = E.shorts.map((sc) => `<div class="itm short ${sc.selected === false ? "off" : ""} ${sel("short", sc.id)}" data-item="short:${sc.id}" style="left:${X(sc.start)}px;width:${Math.max(8, (sc.end - sc.start) * pps).toFixed(1)}px"><i class="h l"></i><span>${esc(sc.title || sc.id)} · ${(sc.end - sc.start).toFixed(0)}s</span><i class="h r"></i></div>`).join("");
  const peaks = E.p.meta?.peaks || [];
  const wave = peaks.length ? `<canvas class="wave" width="${Math.ceil(E.dur * pps)}" height="46"></canvas>` : "";
  // whole-video things (logo, frame, LUT/look, zoom, transitions, filter, effects) — each one selectable + deletable
  const gl = [];
  if (fx.watermark?.id) gl.push(["global", "watermark", `Logo · ${libItem(fx.watermark.id)?.name || ""}`]);
  if (fx.frame?.id) gl.push(["global", "frame", `Frame · ${libItem(fx.frame.id)?.name || ""}`]);
  if ((fx.look || "").startsWith("lut:")) gl.push(["global", "lut", `LUT · ${libItem(fx.look.slice(4))?.name || ""}`]);
  else if (fx.look && fx.look !== "none") gl.push(["global", "look", `Look · ${fx.look}`]);
  if (fx.zoom?.enabled) gl.push(["fxglob", "zoom", `Zoom · ${fx.zoom.mode || "punch"}`]);
  if ((fx.transition || "none") !== "none") gl.push(["fxglob", "transition", `Transition · ${(E.ctx.S.presets?.transitions || []).find((t) => t.id === fx.transition)?.label || fx.transition}`]);
  if (Object.keys(fx.grade || {}).length) gl.push(["fxglob", "grade", `Filter · ${E.ctx.S.presets?.catalog?.grade_presets?.[fx.grade_preset]?.label || "custom"}`]);
  if ((fx.stack || []).length) gl.push(["fxglob", "stack", `Effects · ${(fx.stack || []).map((s) => fxDef(s.id)?.label || s.id).join(", ")}`]);
  const gH = gl.length > 2 ? 16 * gl.length + 8 : LANE_H; const gRow = (gH - 6) / Math.max(1, gl.length);
  const ovRow = gl.map(([t, k, l], i) => `<div class="itm glob ${sel(t, k)}" ${t === "global" ? `data-glob="${k}"` : `data-fxglob="${k}"`} style="left:0;width:${(E.dur * pps).toFixed(1)}px;top:${(3 + i * gRow).toFixed(1)}px;bottom:auto;height:${Math.max(10, gRow - 2).toFixed(1)}px"><span>${esc(l)}</span></div>`).join("")
    || `<span class="small muted" style="position:absolute;left:8px;top:14px">Overlay tab से logo/frame/LUT लगाएँ या यहाँ खींचकर छोड़ें</span>`;
  const TC = laneCounts(); const hid = new Set(fx.hidden_tracks || []);
  const lanes = []; // [id, label, html, kind, height]
  const lane = (id, label, items, mk, span, kind, hint) => { const R = rowsOf(items, span); lanes.push([id, label, items.map((x) => mk(x, R)).join("") + (!items.length && hint ? `<span class="small muted lanehint">${hint}</span>` : ""), kind, laneH(R)]); return R; };
  for (let k = TC.text - 1; k >= 0; k--) { const R = lane(`text:${k}`, `T${k + 1} Text`, fx.titles.filter((t) => (t.track || 0) === k), titleEl, (t) => [t.start, t.end], "text"); if (k === 0 && hookEl) lanes[lanes.length - 1][2] += hookEl; }
  for (let k = TC.fx - 1; k >= 0; k--) lane(`fx:${k}`, `FX${k + 1} Effect`, fx.fxclips.filter((c) => (c.track || 0) === k), fxEl, (c) => [c.start, c.end], "fx", k === 0 ? "Effects / Filters यहाँ खींचें या “+ playhead पर”" : "");
  for (let k = TC.broll - 1; k >= 0; k--) lane(`broll:${k}`, `V${k + 2} Overlay`, fx.broll.filter((b) => (b.track || 0) === k), brollEl, (b) => [b.start, b.end], "broll", k === 0 ? "B-roll / sticker / video यहाँ खींचें" : "");
  lanes.push(["global", "पूरे वीडियो पर", ovRow, "global", gH]);
  lanes.push(["video", "V1 Main", video, "video", LANE_H]);
  lanes.push(["captions", "Caption", caps, "captions", LANE_H]);
  lanes.push(["audio", "A1 Voice + Music", wave + audio, "audio", LANE_H]);
  for (let k = 0; k < TC.audio; k++) lane(`audio:${k}`, `A${k + 2} Audio`, fx.sfx.filter((x) => (x.track || 0) === k), sfxEl, (s) => [s.at, s.at + sfxLen(s)], "sfx", k === 0 ? "SFX / music / voice-over यहाँ खींचें" : "");
  if (E.shorts.length) lanes.push(["shorts", "Shorts", shortsRow, "shorts", LANE_H]);
  const canHide = (id) => /^(text|broll|audio|fx):/.test(id);
  labels.innerHTML = `<div class="tl-ruler-l"><span class="row" style="gap:.2rem"><button class="lbtn" data-addtrack="text" title="नया text track">+T</button><button class="lbtn" data-addtrack="fx" title="नया effect track">+FX</button><button class="lbtn" data-addtrack="broll" title="नया overlay/video track">+V</button><button class="lbtn" data-addtrack="audio" title="नया audio track">+A</button></span></div>`
    + lanes.map(([id, l, , k, hh]) => `<div class="tl-l ${hid.has(id) ? "off" : ""}" data-lane="${id}" style="height:${hh}px"><span class="grow">${l}</span>${canHide(id) ? `<button class="lbtn" data-hidetrack="${id}" title="${k === "sfx" ? "mute" : "छिपाएँ"}">${hid.has(id) ? (k === "sfx" ? "🔇" : "🙈") : (k === "sfx" ? "🔊" : "👁")}</button>` : ""}</div>`).join("");
  body.style.width = W + "px";
  body.innerHTML = `<div class="tl-ruler" id="tl-ruler">${ruler}${PRO.tlMarkers(X)}<div class="tl-phead" id="tl-phead" style="left:${X(E.t)}px" title="playhead — खींचें"></div></div>`
    + lanes.map(([id, , html, k, hh]) => `<div class="tl-track ${k} ${hid.has(id) ? "off" : ""}" data-track="${id}" style="height:${hh}px">${html}</div>`).join("")
    + `<div class="tl-play" id="tl-play" style="left:${X(E.t)}px"><b class="tl-grip" title="playhead — खींचें"></b></div>` + PRO.tlDiamonds(E.sel, X);
  $$("[data-addtrack]", labels).forEach((bt) => (bt.onclick = () => { fx.tracks = { ...laneCounts(), ...(fx.tracks || {}) }; fx.tracks[bt.dataset.addtrack] = laneCounts()[bt.dataset.addtrack] + 1; touch(); renderTimeline(); E.ctx.toast("नया track जुड़ा — item उस पर खींचें"); }));
  $$("[data-hidetrack]", labels).forEach((bt) => (bt.onclick = () => { const id = bt.dataset.hidetrack; const hs = new Set(fx.hidden_tracks || []); hs.has(id) ? hs.delete(id) : hs.add(id); fx.hidden_tracks = [...hs]; touch(); renderTimeline(); renderOverlay(); }));
  const cv = $(".wave", body); if (cv) { const ctx2 = cv.getContext("2d"); ctx2.fillStyle = "rgba(127,196,138,.45)"; const n = peaks.length; const W2 = cv.width; for (let i = 0; i < n; i++) { const x = i / n * W2, w2 = Math.max(1, W2 / n - 0.5), hh = peaks[i] / 100 * 40; ctx2.fillRect(x, 23 - hh / 2, w2, hh); } }
  bindTimeline(); bindDrops(); PRO.bindTlMarkers(body); PRO.bindDiamonds(body);
  $("#tl-info", E.root).textContent = `${fmt(E.dur)} source → ${fmt(outDur())} output · ${E.cuts.filter((c) => c.enabled !== false).length} कट · ${fx.titles.length} text · ${fx.broll.length} B-roll${fx.fxclips.length ? ` · ${fx.fxclips.length} FX` : ""}`;
  $("#t-dur", E.root).textContent = fmt(E.dur);
}
function renderPlayhead(scrollInto) {
  const x = (E.t * E.pps).toFixed(1) + "px";
  const ph = $("#tl-play", E.root); if (ph) ph.style.left = x;
  const hd = $("#tl-phead", E.root); if (hd) hd.style.left = x;
  $("#t-now", E.root).textContent = fmtF(E.t);
  PRO.refreshKfUi(); PRO.textNow();
  if (scrollInto) { const sc = $("#tl-scroll", E.root); const lw = $("#tl-labels", E.root)?.offsetWidth || 110; const px = E.t * E.pps + lw; if (px > sc.scrollLeft + sc.clientWidth - 40 || px < sc.scrollLeft + lw) sc.scrollLeft = px - lw - 90; }
}
// pointer drag helper (mouse, pen and touch): fn(ev) on every move, done(moved) at the end
function track(e, fn, done, threshold = 3) {
  const x0 = e.clientX, y0 = e.clientY; let moved = false; const id = e.pointerId;
  const mv = (ev) => { if (id != null && ev.pointerId !== id) return; if (!moved && Math.abs(ev.clientX - x0) + Math.abs(ev.clientY - y0) < threshold) return; moved = true; ev.preventDefault?.(); fn(ev, ev.clientX - x0, ev.clientY - y0); };
  const up = (ev) => { if (id != null && ev.pointerId !== id) return; document.removeEventListener("pointermove", mv); document.removeEventListener("pointerup", up); document.removeEventListener("pointercancel", up); document.body.classList.remove("dragging"); done?.(moved, ev); };
  document.addEventListener("pointermove", mv, { passive: false }); document.addEventListener("pointerup", up); document.addEventListener("pointercancel", up);
  document.body.classList.add("dragging");
}
function bindTimeline() {
  const body = $("#tl-body", E.root); const fx = E.rs.effects;
  const srcAt = (e) => clamp((e.clientX - body.getBoundingClientRect().left) / E.pps, 0, E.dur);
  const scrub = (e) => { const v = $("#pv", E.root); const wasPlaying = v && !v.paused; if (v && wasPlaying) v.pause(); seek(srcAt(e)); track(e, (ev) => seek(srcAt(ev)), () => { if (wasPlaying) v.play(); }, 0); };
  // playhead: grab it anywhere on its line (or its head in the ruler) and drag
  const hd = $("#tl-phead", body); if (hd) hd.onpointerdown = (e) => { if (e.button > 0) return; e.preventDefault(); e.stopPropagation(); scrub(e); };
  // the line itself: dragging moves the playhead; a plain click goes to whatever is under it (an item at the playhead stays clickable)
  const grip = $("#tl-play .tl-grip", body); if (grip) grip.onpointerdown = (e) => { if (e.button > 0) return; e.preventDefault(); e.stopPropagation();
    const v = $("#pv", E.root); const wasPlaying = v && !v.paused;
    track(e, (ev) => { if (wasPlaying && !v.paused) v.pause(); seek(srcAt(ev)); }, (moved, ev) => {
      if (moved) { if (wasPlaying) v.play(); return; }
      const under = document.elementsFromPoint(e.clientX, e.clientY).find((x) => !x.closest(".tl-play") && x.closest(".ed-tl-body"));
      if (!under) return; const init = { bubbles: true, cancelable: true, clientX: e.clientX, clientY: e.clientY, button: 0, pointerId: 999, pointerType: e.pointerType };
      under.dispatchEvent(new PointerEvent("pointerdown", init)); document.dispatchEvent(new PointerEvent("pointerup", init)); }, 3); };
  // ruler + empty lane space: click / drag = move the playhead (touch: a tap, so the timeline can still be scrolled)
  body.onpointerdown = (e) => {
    if (e.button > 0 || e.target.closest(".itm,.cutblk,.capblk,.h,.clip,.speedblk,.tl-play,.tl-phead,.kfd,.tlmk")) return;
    if (e.pointerType === "touch" && !e.target.closest(".tl-ruler")) { const x0 = e.clientX, y0 = e.clientY; const up = (ev) => { document.removeEventListener("pointerup", up); if (Math.abs(ev.clientX - x0) + Math.abs(ev.clientY - y0) < 8) seek(srcAt(ev)); }; document.addEventListener("pointerup", up); return; }
    e.preventDefault(); scrub(e);
  };
  $$(".cutblk", body).forEach((el) => { el.onpointerdown = (e) => { e.stopPropagation(); const c = E.cuts.find((x) => x.id === el.dataset.cut); if (e.target.classList.contains("h")) return dragEdge(e, c, e.target.classList.contains("l") ? "start" : "end", "src"); select({ type: "cut", id: c.id }); };
    el.ondblclick = () => { const c = E.cuts.find((x) => x.id === el.dataset.cut); c.enabled = c.enabled === false; touch(); }; });
  $$(".speedblk", body).forEach((el) => (el.onpointerdown = (e) => { e.stopPropagation(); select({ type: "speed", id: el.dataset.speed }); }));
  $$(".capblk", body).forEach((el) => (el.onpointerdown = (e) => { e.stopPropagation(); const st = +el.dataset.capst; select({ type: "caption", id: st }); const c = captionAt(st); seek(c ? c.start + Math.min(0.2, (c.end - c.start) / 3) : st); }));
  // main video: click = select that piece and put the playhead there (so ✂ / S splits it right where you clicked)
  $$("[data-mainclip]", body).forEach((el) => (el.onpointerdown = (e) => { if (e.target.closest(".cutblk")) return; e.stopPropagation(); seek(srcAt(e)); select({ type: "seg", id: +el.dataset.mainclip }); }));
  $$("[data-hook]", body).forEach((el) => (el.onpointerdown = (e) => { e.stopPropagation(); select({ type: "hook", id: "h" }); seek(0); }));
  $$("[data-glob]", body).forEach((el) => (el.onpointerdown = (e) => { e.stopPropagation(); select({ type: "global", id: el.dataset.glob }); }));
  $$("[data-fxglob]", body).forEach((el) => (el.onpointerdown = (e) => { e.stopPropagation(); select({ type: "fxglob", id: el.dataset.fxglob }); }));
  $$(".itm[data-item]", body).forEach((el) => (el.onpointerdown = (e) => {
    if (e.button > 0) return; e.stopPropagation();
    const [type, id] = el.dataset.item.split(":");
    if (type === "music") return select({ type: "music", id: "m" });
    if (type === "short") { const sc = E.shorts.find((x) => x.id === id); select({ type, id }); E.shortsDirty = true;
      if (e.target.classList.contains("h")) return dragEdge(e, sc, e.target.classList.contains("l") ? "start" : "end", "src"); return dragMove(e, sc, "short"); }
    const it = itemOf(type, id); if (!it) return;
    if (E.sel?.type !== type || E.sel?.id !== id) select({ type, id });
    if (e.target.classList.contains("h")) return dragEdge(e, it, e.target.classList.contains("l") ? "start" : "end", "out", type);
    dragMove(e, it, type);
  }));
}
function itemOf(type, id) { const fx = E.rs.effects; return ({ title: fx.titles, broll: fx.broll, sfx: fx.sfx, fxclip: fx.fxclips }[type] || []).find((x) => x._id === id); }
// snap a time (output clock) to the playhead / other item edges when within ~7px
function snapOut(t, self) {
  const fx = E.rs.effects; const tol = 7 / E.pps; const cands = [0, outOf(E.t), outDur()];
  for (const arr of [fx.titles, fx.broll, fx.fxclips]) for (const x of arr) if (x !== self) cands.push(x.start, x.end);
  let best = t, bd = tol; for (const c of cands) { const d = Math.abs(srcOf(c) - srcOf(t)); if (d < bd) { bd = d; best = c; } } return best;
}
function dragEdge(e, it, key, clock, type) {
  if (!E.canEdit) return; const pps = E.pps; e.preventDefault();
  if (type === "sfx") { // audio clip: left edge trims the start, right edge sets the length
    const len0 = it.dur || libItem(it.id)?.meta?.duration || 1, at0 = it.at, trim0 = it.trim || 0;
    return track(e, (ev, dx) => { const d = dx / pps;
      if (key === "start") { const dd = clamp(d, -trim0, len0 - 0.1); it.at = +(at0 + dd).toFixed(2); it.trim = +(trim0 + dd).toFixed(2); it.dur = +(len0 - dd).toFixed(2); }
      else it.dur = +clamp(len0 + d, 0.1, 600).toFixed(2);
      renderTimeline(); renderInspector(); }, (m) => { if (m) touch(); }, 1);
  }
  const v0 = it[key];
  track(e, (ev, dx) => { let t = (clock === "src" ? v0 : srcOf(v0)) + dx / pps; t = clamp(t, 0, E.dur); if (clock === "out") t = snapOut(outOf(t), it);
    if (key === "start") it.start = +Math.min(t, it.end - 0.1).toFixed(2); else it.end = +Math.max(t, it.start + 0.1).toFixed(2); renderTimeline(); renderInspector(); },
  (m) => { if (m) { if (it.reason) { /* a cut */ } touch(); } }, 1);
}
function dragMove(e, it, type) {
  if (!E.canEdit) return; const pps = E.pps; const s0 = type === "sfx" ? it.at : it.start; const len = type === "sfx" ? 0 : it.end - it.start; let moved = false;
  const want = { title: "text", broll: "broll", sfx: "audio", fxclip: "fx" }[type];
  track(e, (ev, dx) => { moved = true;
    if (type === "short") { const st = clamp(s0 + dx / pps, 0, E.dur - len); it.start = +st.toFixed(2); it.end = +(st + len).toFixed(2); }
    else { let s = outOf(clamp(srcOf(s0) + dx / pps, 0, E.dur)); const ss = snapOut(s, it); if (ss !== s) s = ss; else if (len) { const se = snapOut(s + len, it); if (se !== s + len) s = se - len; }
      s = clamp(s, 0, Math.max(0, outDur() - len));
      if (type === "sfx") it.at = +s.toFixed(2); else { it.start = +s.toFixed(2); it.end = +(s + len).toFixed(2); } }
    // up/down: move to another track of the same kind
    if (want) { const ln = document.elementsFromPoint(ev.clientX, ev.clientY).map((x) => x.closest?.("[data-track],[data-lane]")).find(Boolean); const lane = ln?.dataset.track || ln?.dataset.lane || "";
      const [k, n] = lane.split(":"); if (k === want && n != null && +n !== (it.track || 0)) it.track = +n; }
    renderTimeline(); renderInspector(); },
  (m) => { if (m) { touch(); renderOverlay(); } });
}
// ✂ / S: split the selected item at the playhead; with nothing (or the main video) selected, split the main video there
function splitAtPlayhead() {
  if (!E.canEdit) return;
  const sel = E.sel; const it = sel && selItem(); const ot = outOf(E.t);
  if (sel && it && ["title", "broll", "sfx", "fxclip"].includes(sel.type)) {
    const b = splitItem(it, sel.type);
    if (b) { touch(); select({ type: sel.type, id: b._id }); E.ctx.toast("✂ दो हिस्से बने"); return; }
    const [a, e] = sel.type === "sfx" ? [it.at, it.at + (it.dur || libItem(it.id)?.meta?.duration || 0)] : [it.start, it.end];
    E.ctx.toast(`playhead ${fmt(ot)} पर है, चुना item ${fmt(a)}–${fmt(e)} पर — playhead को उस item के ऊपर लाएँ`); return;
  }
  if (sel && it && sel.type === "short") { if (E.t <= it.start + 0.5 || E.t >= it.end - 0.5) return E.ctx.toast("playhead इस Short के बीच रखें"); const b = { ...JSON.parse(JSON.stringify(it)), id: "m" + uid().slice(0, 4), start: +E.t.toFixed(2) }; it.end = +E.t.toFixed(2); E.shorts.push(b); E.shortsDirty = true; touch(); select({ type: "short", id: b.id }); return; }
  const t = +E.t.toFixed(3);
  if (cutAt(t)) return E.ctx.toast("playhead कटे हुए (लाल) हिस्से पर है — उसके बाहर रखें");
  const s = segAt(t); if (!s || t - s.a < 0.05 || s.b - t < 0.05) return E.ctx.toast("यहाँ पहले से split है");
  E.splits.push(t); touch(); select({ type: "seg", id: t }); E.ctx.toast("✂ Main video यहाँ से दो हिस्सों में — हिस्सा चुनकर Del से हटा सकते हैं");
}
// ---------- top / export ----------
function renderTop() {
  const ST = { review_cuts: "कट जाँचें", rendering: "render हो रहा है…", review_output: "मंज़ूरी बाकी", approved: "मंज़ूर", failed: "रुक गया" };
  const el = $("#ed-status", E.root); if (el) el.textContent = ST[E.p.status] || E.p.status;
  const b = $("#ed-export", E.root); if (b) b.disabled = E.p.status === "rendering";
  E.root.classList.toggle("ed-locked", !!E.locked);
  renderJobs();
}
async function loadPublishData() {
  const { api } = E.ctx;
  try { const [c, pubs] = await Promise.all([api("GET", "/connections"), api("GET", `/projects/${E.pid}/publications`)]); E.conns = c; E.pubs = pubs; } catch { E.conns = { connections: [], setup: {} }; E.pubs = []; }
  if (E.exportOpen) renderExport();
  clearTimeout(E.pubT);
  if (E.exportOpen && (E.pubs || []).some((x) => x.status === "queued")) E.pubT = setTimeout(loadPublishData, 4000);
}
const PLAT = { youtube: "YouTube", instagram: "Instagram", facebook: "Facebook" };
function renderExport() {
  const m = $("#ed-modal", E.root); const { esc, S, api, toast, load } = E.ctx; const p = E.p;
  if (!E.exportOpen) { m.hidden = true; m.innerHTML = ""; E.pubFor = null; return; }
  if (!E.conns) { E.conns = { connections: [], setup: {} }; E.pubs = []; loadPublishData(); }
  const outs = p.assets.filter((a) => a.kind === "render"); const job = p.jobs?.find((j) => j.kind === "render" && ["running", "queued"].includes(j.status));
  const fx = E.rs.effects; const summary = [E.cuts.filter((c) => c.enabled !== false).length + " कट", styleOf()?.label, fx.zoom.enabled && "zoom", fx.look !== "none" && ("look " + fx.look.replace(/^lut:.*/, "LUT")), fx.music.id && "music", fx.broll.length && fx.broll.length + " B-roll", fx.titles.length && fx.titles.length + " text", fx.watermark.id && "logo"].filter(Boolean).join(" · ");
  m.hidden = false;
  m.innerHTML = `<div class="modal"><div class="row between"><h2>Export</h2><button class="ibtn" id="mx">✕</button></div>
    <p class="small muted">${esc(summary)} · output ${fmt(outDur())}</p>
    ${E.montage ? "" : `<div class="box pfbox"><div class="row between"><b>✈ Platform check</b><button class="btn small quiet" id="pf-run">जाँचें</button></div><div id="pf-list" class="small">${pfHtml()}</div></div>`}
    ${E.montage ? "" : `<div class="ifield"><label>कहाँ के लिए</label><div class="choices">${(S.presets?.platforms || []).map((pl) => `<label class="chip ${E.rs.presets.includes(pl.id) ? "on" : ""}"><input type="checkbox" name="preset" value="${pl.id}" ${E.rs.presets.includes(pl.id) ? "checked" : ""}>${esc(pl.label)}</label>`).join("")}</div></div>
    <div class="irow">${field("9:16 में चेहरा", `<select id="focus"><option value="0.5" ${E.rs.focus_x == 0.5 ? "selected" : ""}>बीच</option><option value="0.25" ${E.rs.focus_x == 0.25 ? "selected" : ""}>बाएँ</option><option value="0.75" ${E.rs.focus_x == 0.75 ? "selected" : ""}>दाएँ</option></select>`)}</div>`}
    ${p.status === "rendering" ? `<div class="progress"><i style="width:${job ? job.progress : 0}%"></i></div><p class="small muted row between"><span>${esc(job ? jobSub(job) : "queue में")}</span>${job && E.canEdit ? `<button class="btn small quiet" data-jcancel="${job.id}">✕ रद्द करें</button>` : ""}</p>` : ""}
    ${outs.length ? `<h3>तैयार वीडियो</h3><div class="outputs">${outs.map((a) => { const pl = S.presets?.platforms.find((x) => x.id === a.label); const srt = p.assets.find((s) => s.kind === "subtitle" && s.label === a.label); const stale = a.meta?.edit_sig && p.edit_sig && a.meta.edit_sig !== p.edit_sig;
      return `<div class="output ${a.meta.height > a.meta.width ? "vertical" : ""} ${stale ? "stale" : ""}"><video src="${a.url}" controls playsinline preload="metadata"></video><div class="row between"><b>${esc(a.label?.startsWith("short-") ? (a.meta.title || a.label) : pl ? pl.label : a.label)}</b><span class="muted small">${fmt(a.meta.duration)}</span></div>${stale ? `<div class="small stalebadge" title="इस render के बाद कट/settings बदले हैं">⚠ पुराना — बदलाव के बाद दोबारा render करें</div>` : a.meta?.edit_sig ? `<div class="small muted">✓ मौजूदा edit से मेल</div>` : ""}<div class="row"><a class="btn small" href="${a.url}&download=1">download</a>${srt ? `<a class="btn quiet small" href="${srt.url}&download=1">SRT</a>` : ""}${p.status === "approved" && E.canEdit && (E.conns?.connections || []).length ? `<button class="btn small primary" data-pub="${a.id}">Publish</button>` : ""}</div>
        ${(E.pubs || []).filter((x) => x.asset_id === a.id).map((x) => `<div class="small pubrow ${x.status}">${PLAT[x.platform] || x.platform}: ${x.status === "done" ? `<a href="${x.url}" target="_blank" rel="noopener">${esc(x.url || "हो गया")}</a>` : x.status === "failed" ? `<span class="muted">असफल — ${esc((x.error || "").slice(0, 120))}</span>` : "upload हो रहा…"}</div>`).join("")}</div>`; }).join("")}</div>` : ""}
    ${(p.meta?.publish_plan || []).length && !E.pubFor ? `<div class="box" id="pplan"><div class="row between"><h3 style="margin:0">✈ Autopilot publish plan</h3>${p.status === "approved" && E.canEdit ? `<button class="btn primary small" id="pplan-go">सब publish करें</button>` : `<span class="small muted">${p.status === "approved" ? "" : "मंज़ूरी के बाद"}</span>`}</div>
      <div class="irow"><button class="btn small" id="pplan-slots" ${E.canEdit ? "" : "disabled"}>⏱ posting slots से समय भरें</button><button class="btn small quiet" id="pplan-now" ${E.canEdit ? "" : "disabled"}>सब अभी</button><span class="small muted">slots: Settings → Schedule</span></div>
      <ul class="plist">${p.meta.publish_plan.map((it, i) => `<li><input type="checkbox" data-pp="${i}" ${it.selected !== false ? "checked" : ""}><div class="grow" style="min-width:0"><b class="small">${PLAT[it.platform]} · ${esc(it.label)}</b><br><input class="small" data-ppt="${i}" value="${esc(it.title)}" style="width:100%"><label class="small muted">कब: <input type="datetime-local" data-ppw="${i}" value="${it.when ? toLocalInput(it.when) : ""}"> <span>${it.when ? "" : "(अभी)"}</span></label><details class="small"><summary class="muted">description / tags बदलें</summary><textarea class="small" data-ppd="${i}" rows="4" style="width:100%">${esc(it.description || "")}</textarea><input class="small" data-ppg="${i}" value="${esc((it.tags || []).join(", "))}" placeholder="tags, comma से" style="width:100%"></details></div></li>`).join("")}</ul>
      <p class="small muted">title/description AI ने transcript से लिखे — बदलना हो तो यहीं बदलें; अलग से publish करने के लिए ऊपर हर output का Publish button।</p></div>` : ""}
    ${E.pubFor ? publishForm(E.pubFor) : ""}
    <div class="row between" style="margin-top:1rem"><span class="small muted">${p.status === "review_output" && S.user.role !== "admin" ? "मंज़ूरी admin देंगे" : p.status === "approved" ? `मंज़ूर ✓ ${p.meta?.archived_at ? `· archived (${esc(p.meta.archive || "")}) <button class="btn small quiet" id="restore">raw वापस लाएँ</button>` : E.canEdit ? `<button class="btn small quiet" id="archive" title="raw files को Drive/archive पर भेजें, server खाली">☁ archive</button>` : ""}` : ""}</span>
      <span class="row">${p.status === "review_output" && S.user.role === "admin" ? `<button class="btn" id="approve">मंज़ूरी दें</button>` : ""}${E.canEdit && !E.montage ? `<button class="btn primary" id="go-render" ${p.status === "rendering" ? "disabled" : ""}>${p.status === "rendering" ? "render हो रहा…" : outs.length ? "दोबारा render" : "render करें"}</button>` : ""}</span></div></div>`;
  $("#mx", m).onclick = () => { E.exportOpen = false; renderExport(); };
  $$("[data-jcancel]", m).forEach((b) => (b.onclick = () => cancelJob(b.dataset.jcancel, b)));
  $$("[data-pub]", m).forEach((b) => (b.onclick = () => { const a = p.assets.find((x) => x.id === b.dataset.pub); E.pubFor = { asset: a, title: "", description: "", tags: "", conn: "", privacy: "private", when: "" }; renderExport(); $("#pubform", m)?.scrollIntoView({ behavior: "smooth" }); }));
  bindPublishForm(m);
  const pfr = $("#pf-run", m); if (pfr) pfr.onclick = async () => { await flush(); try { E.pf = await api("GET", `/projects/${E.pid}/preflight?presets=${encodeURIComponent((E.rs.presets || []).join(","))}`); $("#pf-list", m).innerHTML = pfHtml(); bindPf(m); } catch (e) { toast(e.message); } };
  if (!E.pf && pfr) pfr.click(); else bindPf(m);
  for (const [id, now] of [["#pplan-slots", false], ["#pplan-now", true]]) { const b = $(id, m); if (b) b.onclick = async () => { try { const r = await api("POST", `/projects/${E.pid}/publish-plan/schedule`, { now }); p.meta.publish_plan = r.items; renderExport(); toast(now ? "सब तुरंत publish होंगे" : "समय भरे गए — बदल सकते हैं"); } catch (e) { toast(e.message); } }; }
  const pg = $("#pplan-go", m); if (pg) pg.onclick = async () => { const items = p.meta.publish_plan.map((it, i) => ({ ...it, selected: $(`[data-pp="${i}"]`, m).checked, title: $(`[data-ppt="${i}"]`, m).value, when: fromLocalInput($(`[data-ppw="${i}"]`, m).value), description: $(`[data-ppd="${i}"]`, m).value, tags: $(`[data-ppg="${i}"]`, m).value.split(",").map((t) => t.trim()).filter(Boolean) })); if (!confirm(`${items.filter((x) => x.selected).length} videos publish करें?`)) return;
    try { const r = await api("POST", `/projects/${E.pid}/publish-plan`, { items }); toast(`${r.queued.length} uploads queue में`); await loadPublishData(); } catch (e) { toast(e.message); } };
  m.onclick = (e) => { if (e.target === m) { E.exportOpen = false; renderExport(); } };
  $$(".chip input", m).forEach((i) => (i.onchange = () => i.closest(".chip").classList.toggle("on", i.checked)));
  const gr = $("#go-render", m); if (gr) gr.onclick = async () => {
    E.rs.presets = $$("input[name=preset]:checked", m).map((i) => i.value); E.rs.focus_x = +$("#focus", m).value;
    if (!E.rs.presets.length) return toast("कम से कम एक platform चुनें");
    gr.disabled = true; gr.textContent = "सेव हो रहा…";
    // every edit must be on the server before the job is queued: the worker reads cuts/transcript from the project
    E.dirty = true; const ok = await flush();
    if (!ok) { gr.disabled = false; gr.textContent = "render करें"; return toast("बदलाव सेव नहीं हुए — render नहीं चला, फिर कोशिश करें"); }
    try { const rs = JSON.parse(JSON.stringify(E.rs)); await api("POST", `/projects/${E.pid}/render`, rs); toast("render शुरू — आपकी अभी की editing से"); await load(); } catch (err) { toast(err.message); gr.disabled = false; }
  };
  const ar = $("#archive", m); if (ar) ar.onclick = async () => { ar.disabled = true; ar.textContent = "भेज रहा है…"; try { const r = await api("POST", `/projects/${E.pid}/archive`); toast(`${r.moved} files archive, ${r.backed_up} renders backup`); await load(); } catch (e) { toast(e.message); ar.disabled = false; ar.textContent = "☁ archive"; } };
  const rs0 = $("#restore", m); if (rs0) rs0.onclick = async () => { rs0.disabled = true; try { const r = await api("POST", `/projects/${E.pid}/restore`); toast(`${r.restored} files वापस`); await load(); } catch (e) { toast(e.message); rs0.disabled = false; } };
  const ap = $("#approve", m); if (ap) ap.onclick = async () => { if (confirm("यह वीडियो मंज़ूर करें?")) { await api("POST", `/projects/${E.pid}/approve`); toast("मंज़ूर"); await load(); } };
}

function publishForm(f) {
  const { esc } = E.ctx; const a = f.asset; const conns = E.conns?.connections || []; const vertical = a.meta.height > a.meta.width;
  const fit = conns.filter((c) => vertical ? true : c.platform !== "instagram");
  const conn = conns.find((c) => c.id === f.conn) || fit[0]; f.conn = conn?.id || "";
  const label = a.label?.startsWith("short-") ? a.meta.title || a.label : (E.ctx.S.presets?.platforms.find((x) => x.id === a.label) || {}).label || a.label;
  return `<div class="box" id="pubform"><div class="row between"><h3 style="margin:0">Publish: ${esc(label)}</h3><button class="ibtn" id="pub-close">✕</button></div>
    <div class="irow">${field("कहाँ", `<select id="pub-conn">${fit.map((c) => `<option value="${c.id}" ${c.id === f.conn ? "selected" : ""}>${PLAT[c.platform]} · ${esc(c.name)}</option>`).join("")}</select>`)}
      ${conn?.platform === "youtube" ? field("दिखे", `<select id="pub-privacy">${[["private", "Private (बाद में public करेंगे)"], ["unlisted", "Unlisted"], ["public", "Public"]].map(([v, l]) => `<option value="${v}" ${f.privacy === v ? "selected" : ""}>${l}</option>`).join("")}</select>`) : ""}
      ${field("schedule (खाली = अभी)", `<input type="datetime-local" id="pub-when" value="${f.when}">`)}
      <button class="btn small" id="pub-ai" title="transcript से title/description/tags">✨ AI से लिखें</button></div>
    ${field("Title", `<input id="pub-title" maxlength="100" value="${esc(f.title)}" placeholder="वीडियो का title">`)}
    ${field("Description / caption", `<textarea id="pub-desc" rows="5" placeholder="description, hashtags…">${esc(f.description)}</textarea>`)}
    ${field("Tags (comma से अलग)", `<input id="pub-tags" value="${esc(f.tags)}">`)}
    ${conn?.platform === "youtube" ? `${field("पहला comment (upload के बाद अपने-आप; pin खुद करना होगा)", `<textarea id="pub-fc" rows="2" placeholder="${f.fc === undefined ? "AI pack से ला रहा है…" : "खाली = कोई comment नहीं"}">${esc(f.fc || "")}</textarea>`)}
    <div class="irow">${field("Playlist", `<input id="pub-pl" list="pub-pl-list" value="${esc(f.pl || "")}" placeholder="${f.plDefault ? "खाली = brand playlist" : "playlist ID या link (खाली = कोई नहीं)"}"><datalist id="pub-pl-list">${(f.playlists || []).map((x) => `<option value="${esc(x.id)}">${esc(x.title)}</option>`).join("")}</datalist>`)}
      <label class="small" style="align-self:end"><input type="checkbox" id="pub-synth" ${f.synth ? "checked" : ""}> AI-generated/altered content (YouTube को बताएँ)</label></div>
    ${f.ytNote ? `<p class="small muted">⚠️ ${esc(f.ytNote)}</p>` : ""}` : ""}
    <div class="row between"><span class="small muted">${conn?.platform === "youtube" ? "YouTube quota: ~6 upload/दिन" : conn?.platform === "instagram" ? "Instagram: Reel के रूप में, caption 2200 तक" : conn ? "Facebook: Page पर" : "पहले Settings → Channels में channel जोड़ें"}</span><button class="btn primary" id="pub-go" ${conn ? "" : "disabled"}>Upload करें</button></div></div>`;
}
function bindPublishForm(m) {
  const f = E.pubFor; if (!f) return; const { api, toast } = E.ctx;
  const sync = () => { f.title = $("#pub-title", m).value; f.description = $("#pub-desc", m).value; f.tags = $("#pub-tags", m).value; f.conn = $("#pub-conn", m).value; f.privacy = $("#pub-privacy", m)?.value || "private"; f.when = $("#pub-when", m).value;
    if ($("#pub-fc", m) && f.fc !== undefined) f.fc = $("#pub-fc", m).value; if ($("#pub-pl", m)) { f.pl = $("#pub-pl", m).value; f.synth = $("#pub-synth", m).checked; } };
  const yconn = (E.conns.connections || []).find((c) => c.id === f.conn);
  if (yconn?.platform === "youtube" && f.ytFor !== yconn.id) { f.ytFor = yconn.id; // prefill: AI pack's pinned comment + channel playlists
    Promise.all([f.fc === undefined ? api("GET", `/projects/${E.pid}/aipack`).catch(() => null) : null, api("GET", `/connections/${yconn.id}/playlists`).catch(() => null)]).then(([ap, pl]) => {
      if (E.pubFor !== f) return; if ($("#pub-title", m)) sync();
      if (f.fc === undefined) f.fc = $("#pub-fc", m)?.value || ap?.pack?.pinned_comment || "";
      if (pl) { f.playlists = pl.playlists || []; f.plDefault = pl.default || ""; f.ytNote = pl.note || (yconn.meta?.needs_reauth ? "YouTube दोबारा connect करें ताकि comment/playlist/analytics चलें" : ""); }
      renderExport(); }); }
  $("#pub-close", m).onclick = () => { E.pubFor = null; renderExport(); };
  $("#pub-conn", m).onchange = () => { sync(); renderExport(); };
  $("#pub-ai", m).onclick = async () => { sync(); const conn = (E.conns.connections || []).find((c) => c.id === f.conn); $("#pub-ai", m).disabled = true;
    try { const r = await api("POST", `/projects/${E.pid}/metadata`, { platform: conn?.platform || "youtube", label: f.asset.label }); f.title = r.title; f.description = r.description; f.tags = (r.tags || []).join(", "); renderExport(); toast(r.source === "llm" ? "AI ने लिखा" : "transcript से draft बना (AI key नहीं)"); } catch (e) { toast(e.message); $("#pub-ai", m).disabled = false; } };
  $("#pub-go", m).onclick = async () => { sync(); if (!f.title.trim()) return toast("title लिखें");
    const conn = (E.conns.connections || []).find((c) => c.id === f.conn); const when = f.when ? new Date(f.when) : null;
    const body = { asset_id: f.asset.id, connection_id: f.conn, title: f.title.trim(), description: f.description, tags: f.tags.split(",").map((t) => t.trim()).filter(Boolean), privacy: f.privacy };
    if (when) { if (conn?.platform === "youtube") body.publish_at = when.toISOString(); else body.scheduled_at = Math.floor(when.getTime() / 1000); }
    if (conn?.platform === "youtube") { body.ai_content = !!f.synth; body.playlist_id = (f.pl || "").trim(); if (f.fc !== undefined) body.first_comment = f.fc; }
    if (!confirm(`${PLAT[conn?.platform]} · ${conn?.name} पर upload करें?\n"${body.title}"`)) return;
    try { await api("POST", `/projects/${E.pid}/publications`, body); toast("upload queue में"); E.pubFor = null; await loadPublishData(); } catch (e) { toast(e.message); } };
}
function renderAll() { renderTop(); renderPanel(); renderInspector(); renderTimeline(); layoutFrame(); renderOverlay(); renderPlayhead(); }
