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
  export: '<svg viewBox="0 0 24 24"><path d="M12 16V4M6 10l6-6 6 6M4 20h16"/></svg>',
  play: '<svg viewBox="0 0 24 24"><path d="M7 4l12 8-12 8z" fill="currentColor" stroke="none"/></svg>',
  pause: '<svg viewBox="0 0 24 24"><rect x="6" y="4" width="4" height="16" fill="currentColor" stroke="none"/><rect x="14" y="4" width="4" height="16" fill="currentColor" stroke="none"/></svg>',
  prev: '<svg viewBox="0 0 24 24"><path d="M18 5v14L8 12zM6 5v14"/></svg>',
  next: '<svg viewBox="0 0 24 24"><path d="M6 5v14l10-7zM18 5v14"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>',
  back: '<svg viewBox="0 0 24 24"><path d="M15 5l-7 7 7 7"/></svg>',
  plus: '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>',
};
const TABS = [["cuts", "कट"], ["captions", "Caption"], ["text", "Text"], ["media", "Media"], ["audio", "Audio"], ["effects", "Effects"], ["overlay", "Overlay"]];
const TITLE_PRESETS = [
  { id: "headline", label: "Headline", pos: "top", size: 0.08, color: "#FFFFFF", bg: "", text: "यहाँ बड़ा टाइटल" },
  { id: "lower3", label: "Lower third", pos: "bottom", size: 0.05, color: "#FFFFFF", bg: "#000000", text: "नाम | पहचान" },
  { id: "center", label: "Center punch", pos: "center", size: 0.11, color: "#FFD400", bg: "", text: "एक लाइन" },
  { id: "note", label: "Note box", pos: "top", size: 0.055, color: "#111111", bg: "#FFD400", text: "ध्यान दें" },
];
const LOOK_CSS = { none: "", warm: "sepia(.15) saturate(1.1)", cinematic: "contrast(1.1) saturate(.9) brightness(.97)", vivid: "saturate(1.35) contrast(1.05)",
  soft: "contrast(.95) saturate(.95) blur(.3px)", bw: "grayscale(1) contrast(1.12)", cool: "hue-rotate(-8deg) saturate(1.02)", vintage: "sepia(.35) contrast(.95)" };
const LIB_KINDS = [["music", "Music"], ["sfx", "SFX"], ["broll", "B-roll"], ["image", "Image"], ["logo", "Logo"], ["lut", "LUT"]];
const uid = () => Math.random().toString(36).slice(2, 10);

// ---------- mount / state ----------
export function mount(root, project, ctx) {
  if (E && E.pid === project.id && root.contains(E.root)) { update(project); return; }
  unmount();
  const rs = JSON.parse(JSON.stringify(project.render_defaults || {}));
  rs.effects = { zoom: { enabled: false, strength: 1 }, look: "none", flash: false, music: { id: "", volume: 0.18, duck: true },
    broll: [], titles: [], watermark: { id: "", opacity: 0.75, size: 0.14, pos: "tr" }, sfx: [], ...(rs.effects || {}) };
  rs.captions = { size_scale: 1, position: "", primary: "", highlight: "", font: "", ...(rs.captions || {}) };
  rs.hook = { text: "", seconds: 3, ...(rs.hook || {}) };
  for (const t of rs.effects.titles) t._id = t._id || uid();
  for (const b of rs.effects.broll) b._id = b._id || uid();
  for (const s of rs.effects.sfx) s._id = s._id || uid();
  E = { pid: project.id, p: project, ctx, root: null, rs, cuts: JSON.parse(JSON.stringify(project.edl?.cuts || [])),
    words: (project.transcript?.segments || []).flatMap((s) => s.words || []),
    tab: "cuts", sel: null, pps: 40, t: 0, markIn: null, markOut: null, skipCuts: true, ratio: "9:16", dirty: false, saveT: null,
    lib: null, libKind: "music", exportOpen: false, drag: null, raf: null, canEdit: ctx.S.user.role !== "viewer" };
  E.dur = project.edl?.duration || project.meta?.duration || 1;
  E.pps = clamp(Math.floor(900 / E.dur), 6, 120);
  root.innerHTML = skeleton();
  E.root = root.firstElementChild;
  bindStatic();
  renderAll();
  loadLib();
}
export function unmount() {
  if (!E) return;
  document.removeEventListener("keydown", onKey);
  cancelAnimationFrame(E.raf);
  clearTimeout(E.saveT);
  E = null;
}
function update(project) {
  const was = E.p.status;
  if (E.transcriptDirty) project.transcript = E.p.transcript;
  E.p = project;
  if (project.edl?.duration) E.dur = project.edl.duration;
  renderTop();
  if (E.exportOpen) renderExport();
  if (was !== project.status && project.status === "review_output") { E.exportOpen = true; renderExport(); }
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
        <span id="ed-save" class="small muted"></span>
        <div class="seg" id="ratio"><button data-r="9:16" class="on">9:16</button><button data-r="16:9">16:9</button><button data-r="1:1">1:1</button></div>
        <button class="btn primary" id="ed-export">${ICON.export} Export</button>
      </div>
    </header>
    <nav class="ed-tabs">${TABS.map(([id, l]) => `<button data-tab="${id}" class="${id === E.tab ? "on" : ""}">${ICON[id]}<span>${l}</span></button>`).join("")}</nav>
    <section class="ed-panel" id="ed-panel"></section>
    <section class="ed-stage">
      <div class="ed-viewport" id="viewport">
        <div class="ed-frame" id="frame">
          <video id="pv" playsinline preload="auto" src="${(E.p.assets.find((a) => a.kind === "proxy") || {}).url || ""}"></video>
          <div class="ed-mask" id="mask"></div>
          <div class="ed-safe" id="safe"></div>
          <div class="ed-ovl" id="ovl"><div id="ovl-media"></div><div id="ovl-text"></div></div>
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
        <span class="muted small" id="t-marks"></span>
      </div>
    </section>
    <aside class="ed-inspector" id="inspector"></aside>
    <section class="ed-tl">
      <div class="ed-tl-head">
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

function bindStatic() {
  const { api, toast, load } = E.ctx;
  $$(".ed-tabs button", E.root).forEach((b) => (b.onclick = () => { E.tab = b.dataset.tab; $$(".ed-tabs button", E.root).forEach((x) => x.classList.toggle("on", x === b)); renderPanel(); }));
  $$("#ratio button", E.root).forEach((b) => (b.onclick = () => { E.ratio = b.dataset.r; $$("#ratio button", E.root).forEach((x) => x.classList.toggle("on", x === b)); layoutFrame(); renderOverlay(); }));
  $("#ed-export", E.root).onclick = () => { E.exportOpen = true; renderExport(); };
  const name = $("#ed-name", E.root);
  if (name.isContentEditable) name.onblur = async () => { const t = name.textContent.trim(); if (t && t !== E.p.title) { await api("PATCH", `/projects/${E.pid}`, { title: t }); toast("नाम बदला"); E.p.title = t; } };
  const v = $("#pv", E.root);
  v.onloadedmetadata = () => { layoutFrame(); renderOverlay(); };
  v.onplay = () => { $("#t-play", E.root).innerHTML = ICON.pause; tick(); };
  v.onpause = () => { $("#t-play", E.root).innerHTML = ICON.play; cancelAnimationFrame(E.raf); renderOverlay(); };
  $("#t-play", E.root).onclick = togglePlay;
  $("#t-prev", E.root).onclick = () => { const c = [...E.cuts].filter((c) => c.start < E.t - 0.3).sort((a, b) => b.start - a.start)[0]; seek(c ? c.start - 0.5 : 0); };
  $("#t-next", E.root).onclick = () => { const c = [...E.cuts].filter((c) => c.start > E.t + 0.05).sort((a, b) => a.start - b.start)[0]; seek(c ? c.start - 0.5 : E.dur); };
  $("#t-skip", E.root).onchange = (e) => (E.skipCuts = e.target.checked);
  $("#t-in", E.root).onclick = () => mark("in");
  $("#t-out", E.root).onclick = () => mark("out");
  $("#t-cut", E.root).onclick = addCutFromMarks;
  $("#tl-zoom", E.root).oninput = (e) => { E.pps = +e.target.value; renderTimeline(); };
  window.addEventListener("resize", layoutFrame);
  document.addEventListener("keydown", onKey);
  $("#tl-scroll", E.root).addEventListener("wheel", (e) => { if (e.ctrlKey) { e.preventDefault(); E.pps = clamp(E.pps * (e.deltaY < 0 ? 1.15 : 0.87), 4, 160); $("#tl-zoom", E.root).value = E.pps; renderTimeline(); } }, { passive: false });
}

function onKey(e) {
  if (!E || e.target.closest("input,textarea,select,[contenteditable=true]")) return;
  const v = $("#pv", E.root); const fps = E.p.meta?.fps || 30;
  if (e.code === "Space") { e.preventDefault(); togglePlay(); }
  else if (e.key === "i" || e.key === "I") mark("in");
  else if (e.key === "o" || e.key === "O") mark("out");
  else if (e.key === "ArrowLeft") { e.preventDefault(); seek(E.t - (e.shiftKey ? 1 : 1 / fps)); }
  else if (e.key === "ArrowRight") { e.preventDefault(); seek(E.t + (e.shiftKey ? 1 : 1 / fps)); }
  else if (e.key === "Delete" || e.key === "Backspace") { if (E.sel) { e.preventDefault(); deleteSel(); } }
  else if (e.key === "x" || e.key === "X") addCutFromMarks();
  else if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(true); }
  else if (e.key === "Escape") { if (E.exportOpen) { E.exportOpen = false; renderExport(); } else select(null); }
  else if (e.key === "Home") seek(0);
  else if (e.key === "End") seek(E.dur);
}
function togglePlay() { const v = $("#pv", E.root); if (!v.src) return; if (v.paused) { if (E.skipCuts) { const c = cutAt(v.currentTime); if (c) v.currentTime = c.end; } v.play(); } else v.pause(); }
function seek(t) { const v = $("#pv", E.root); E.t = clamp(t, 0, E.dur); if (v) v.currentTime = E.t; renderOverlay(); renderPlayhead(); }
function tick() {
  const v = $("#pv", E.root); if (!v) return;
  E.t = v.currentTime;
  if (E.skipCuts && !v.paused) { const c = cutAt(E.t); if (c) { v.currentTime = Math.min(E.dur, c.end + 0.02); E.t = v.currentTime; } }
  renderOverlay(); renderPlayhead(true);
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
function frameRatio() { const [a, b] = E.ratio.split(":").map(Number); return a / b; }
function layoutFrame() {
  const vp = $("#viewport", E.root), fr = $("#frame", E.root), v = $("#pv", E.root);
  if (!vp || !v) return;
  const vw = v.videoWidth || E.p.meta?.width || 1280, vh = v.videoHeight || E.p.meta?.height || 720;
  const W = vp.clientWidth - 24, H = vp.clientHeight - 24;
  // the video keeps its own aspect; the frame mask shows what the chosen ratio keeps
  let w = W, h = W * vh / vw; if (h > H) { h = H; w = H * vw / vh; }
  fr.style.width = w + "px"; fr.style.height = h + "px";
  const r = frameRatio(), srcR = vw / vh; const mask = $("#mask", E.root), safe = $("#safe", E.root);
  let fw = w, fh = h, fx = 0, fy = 0;
  if (Math.abs(r - srcR) > 0.02) {
    if (r < srcR) { fw = h * r; fx = (w - fw) * (E.rs.focus_x ?? 0.5); } else { fh = w / r; fy = (h - fh) * (E.rs.focus_y ?? 0.5); }
  }
  E.frameBox = { x: fx, y: fy, w: fw, h: fh, scale: fw / (r >= 1 ? 1920 : 1080) };
  mask.style.cssText = `left:${fx}px;top:${fy}px;width:${fw}px;height:${fh}px;box-shadow:0 0 0 9999px rgba(10,13,18,.72)`;
  safe.style.cssText = `left:${fx}px;top:${fy}px;width:${fw}px;height:${fh}px;display:${E.ratio === "9:16" ? "block" : "none"}`;
  $("#ovl", E.root).style.cssText = `left:${fx}px;top:${fy}px;width:${fw}px;height:${fh}px`;
  v.style.filter = LOOK_CSS[E.rs.effects.look] || "";
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
  return out.map((ws) => ({ start: ws[0].start, end: ws[ws.length - 1].end + 0.15, words: ws }));
}
function styleOf() { return (E.ctx.S.presets?.caption_styles || []).find((s) => s.id === E.rs.caption_style); }
function renderOverlay() {
  const ovl = $("#ovl", E.root); if (!ovl || !E.frameBox) return;
  const { esc } = E.ctx; const t = E.t, ot = outOf(t); const fb = E.frameBox; const base = Math.min(fb.w, fb.h);
  const cs = styleOf(); const ov = E.rs.captions; let html = "";
  // B-roll + watermark: rebuilt only when the visible set changes (so <video> keeps playing)
  const active = E.rs.effects.broll.filter((b) => ot >= b.start && ot < b.end);
  const wm = E.rs.effects.watermark; const wmi = wm.id && libItem(wm.id);
  const mkey = active.map((b) => `${b._id}:${b.id}:${b.fit}:${b.pos}`).join("|") + `#${wm.id}:${wm.opacity}:${wm.size}:${wm.pos}` + (E.sel?.type === "broll" ? E.sel.id : "");
  if (mkey !== E.mkey) {
    E.mkey = mkey; let mh = "";
    for (const b of active) {
    const item = libItem(b.id); const pip = b.fit === "pip";
    const style = pip ? `width:42%;aspect-ratio:${fb.w > fb.h ? "16/9" : "9/16"};${{ tl: "left:4%;top:3%", tr: "right:4%;top:3%", bl: "left:4%;bottom:28%", br: "right:4%;bottom:28%" }[b.pos || "tr"]}` : "inset:0";
      mh += `<div class="ov-broll ${E.sel?.type === "broll" && E.sel.id === b._id ? "sel" : ""}" style="position:absolute;${style};overflow:hidden;border-radius:${pip ? 6 : 0}px">${item?.kind === "image" ? `<img src="${item.url}" style="width:100%;height:100%;object-fit:cover">` : item ? `<video src="${item.url}" muted autoplay loop playsinline style="width:100%;height:100%;object-fit:cover"></video>` : ""}<span class="ov-tag">${esc(item?.name || "B-roll")}</span></div>`;
    }
    if (wmi) mh += `<img src="${wmi.url}" style="position:absolute;width:${(wm.size * 100).toFixed(0)}%;opacity:${wm.opacity};${{ tl: "left:3.5%;top:3.5%", tr: "right:3.5%;top:3.5%", bl: "left:3.5%;bottom:3.5%", br: "right:3.5%;bottom:3.5%" }[wm.pos]}">`;
    $("#ovl-media", ovl).innerHTML = mh;
  }
  // hook
  if (E.rs.hook.text && ot < (E.rs.hook.seconds || 3)) html += `<div class="ov-hook" style="font-size:${0.085 * base}px;top:${fb.h > fb.w ? 13 : 6}%;background:${cs?.highlight || "#FFD400"}">${esc(E.rs.hook.text).replace(/\|/g, "<br>")}</div>`;
  // titles
  for (const ti of E.rs.effects.titles) if (ot >= ti.start && ot < ti.end) {
    const pos = { top: "top:10%", center: "top:50%;transform:translateY(-50%)", bottom: "bottom:10%" }[ti.pos || "top"];
    html += `<div class="ov-title ${E.sel?.type === "title" && E.sel.id === ti._id ? "sel" : ""}" data-id="${ti._id}" style="${pos};font-size:${(ti.size || 0.075) * base}px;color:${ti.color || "#fff"};${ti.bg ? `-webkit-text-stroke:${0.012 * base}px ${ti.bg};paint-order:stroke fill;` : `text-shadow:0 2px ${0.01 * base}px #000;`}">${esc(ti.text).replace(/\|/g, "<br>")}</div>`;
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
      html += `<div class="ov-cap" style="${place};font-family:'${font}',var(--font);font-weight:${cs.bold === false ? 400 : 800};font-size:${size}px;color:${primary};${glow}${box}">${words}</div>`;
    }
  }
  $("#ovl-text", ovl).innerHTML = html;
  $$(".ov-title", ovl).forEach((el) => (el.onmousedown = (e) => { e.preventDefault(); select({ type: "title", id: el.dataset.id }); }));
}

// ---------- selection / inspector ----------
function select(sel) { E.sel = sel; E.root.classList.toggle("has-sel", !!sel); renderInspector(); renderTimeline(); renderOverlay(); }
function selItem() {
  if (!E.sel) return null;
  const { type, id } = E.sel; const fx = E.rs.effects;
  if (type === "cut") return E.cuts.find((c) => c.id === id);
  if (type === "title") return fx.titles.find((t) => t._id === id);
  if (type === "broll") return fx.broll.find((t) => t._id === id);
  if (type === "sfx") return fx.sfx.find((t) => t._id === id);
  if (type === "caption") return captionChunks()[id];
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
  else return;
  touch(); select(null);
}
function touch() { E.dirty = true; $("#ed-save", E.root).textContent = "बदलाव सेव हो रहे…"; clearTimeout(E.saveT); E.saveT = setTimeout(() => save(false), 1500); renderTimeline(); renderOverlay(); }
async function save(loud) {
  if (!E || !E.canEdit) return;
  const { api, toast } = E.ctx;
  const rs = JSON.parse(JSON.stringify(E.rs));
  try {
    const body = { settings: { render: rs }, edl: { cuts: E.cuts } };
    if (E.transcriptDirty) { body.transcript = E.p.transcript; E.transcriptDirty = false; }
    const p = await api("PATCH", `/projects/${E.pid}`, body);
    E.dirty = false; E.p = p; $("#ed-save", E.root).textContent = "सेव ✓";
    if (loud) toast("सेव हुआ");
  } catch (err) { $("#ed-save", E.root).textContent = "सेव नहीं हुआ"; toast(err.message); }
}
function field(label, inner) { return `<div class="ifield"><label>${label}</label>${inner}</div>`; }
function num(id, v, step = 0.1, min = 0, max = 9999) { return `<input type="number" data-k="${id}" value="${(+v).toFixed(step < 1 ? 2 : 0)}" step="${step}" min="${min}" max="${max}">`; }
function renderInspector() {
  const ins = $("#inspector", E.root); const { esc } = E.ctx; const it = selItem(); const dis = E.canEdit ? "" : "disabled";
  if (!E.sel || !it) {
    ins.innerHTML = `<h3>Project</h3><div class="ikv"><span>लंबाई</span><b>${fmt(E.dur)} → ${fmt(outDur())}</b></div><div class="ikv"><span>कट</span><b>${E.cuts.filter((c) => c.enabled !== false).length}</b></div>
      <div class="ikv"><span>भाषा</span><b>${{ hi: "हिंदी", en: "English", auto: "पहचान बाकी" }[E.p.language] || E.p.language}</b></div><div class="ikv"><span>source</span><b>${E.p.meta?.width}×${E.p.meta?.height} · ${E.p.meta?.fps} fps</b></div>
      <p class="small muted" style="margin-top:1rem">timeline पर किसी कट, caption, title या B-roll पर क्लिक करें — उसकी settings यहाँ आएँगी।<br><br><b>Keys:</b> Space चलाएँ · I/O हिस्सा चुनें · X हटाएँ · ←/→ frame · Del चुना हुआ हटाएँ · Ctrl+S सेव</p>`;
    return;
  }
  const { type } = E.sel; let h = "";
  if (type === "cut") {
    h = `<h3>कट <span class="tag ${it.reason}">${{ silence: "चुप्पी", filler: "अं-आं", retake: "दोबारा बोला", manual: "आपका" }[it.reason] || it.reason}</span></h3>
      ${it.text ? `<p class="small muted">“${esc(it.text)}”</p>` : ""}
      <div class="irow">${field("से", num("start", it.start, 0.05, 0, E.dur))}${field("तक", num("end", it.end, 0.05, 0, E.dur))}</div>
      <label class="chk"><input type="checkbox" data-k="enabled" ${it.enabled !== false ? "checked" : ""} ${dis}> यह हिस्सा हटेगा</label>
      <div class="irow"><button class="btn small" data-act="seek">यहाँ जाएँ</button><button class="btn small danger quiet" data-act="del">${ICON.trash} कट मिटाएँ</button></div>`;
  } else if (type === "title") {
    h = `<h3>Text</h3>${field("लिखें ( | से नई लाइन )", `<textarea data-k="text" rows="2" ${dis}>${esc(it.text)}</textarea>`)}
      <div class="irow">${field("शुरू", num("start", it.start, 0.1, 0))}${field("ख़त्म", num("end", it.end, 0.1, 0))}</div>
      <div class="irow">${field("जगह", `<select data-k="pos" ${dis}>${["top", "center", "bottom"].map((p) => `<option value="${p}" ${it.pos === p ? "selected" : ""}>${{ top: "ऊपर", center: "बीच", bottom: "नीचे" }[p]}</option>`).join("")}</select>`)}${field("आकार", `<input type="range" data-k="size" min="0.03" max="0.16" step="0.005" value="${it.size || 0.075}" ${dis}>`)}</div>
      <div class="irow">${field("रंग", `<input type="color" data-k="color" value="${it.color || "#ffffff"}" ${dis}>`)}${field("outline/box", `<div class="irow"><input type="color" data-k="bg" value="${it.bg || "#000000"}" ${dis}><label class="chk small"><input type="checkbox" data-k="_bgon" ${it.bg ? "checked" : ""} ${dis}> लगाएँ</label></div>`)}</div>
      <div class="irow"><button class="btn small" data-act="seek">यहाँ जाएँ</button><button class="btn small danger quiet" data-act="del">${ICON.trash} हटाएँ</button></div>`;
  } else if (type === "broll") {
    const item = libItem(it.id);
    h = `<h3>B-roll</h3><p class="small muted">${esc(item?.name || "?")}${item?.meta?.duration ? ` · ${fmt(item.meta.duration)}` : ""}</p>
      <div class="irow">${field("शुरू", num("start", it.start, 0.1, 0))}${field("ख़त्म", num("end", it.end, 0.1, 0))}</div>
      <div class="irow">${field("कैसे", `<select data-k="fit" ${dis}><option value="cover" ${it.fit !== "pip" ? "selected" : ""}>पूरा frame</option><option value="pip" ${it.fit === "pip" ? "selected" : ""}>छोटा box (PiP)</option></select>`)}
      ${field("कोना", `<select data-k="pos" ${dis}>${["tr", "tl", "br", "bl"].map((p) => `<option value="${p}" ${(it.pos || "tr") === p ? "selected" : ""}>${{ tr: "ऊपर दाएँ", tl: "ऊपर बाएँ", br: "नीचे दाएँ", bl: "नीचे बाएँ" }[p]}</option>`).join("")}</select>`)}</div>
      <div class="irow"><button class="btn small" data-act="seek">यहाँ जाएँ</button><button class="btn small danger quiet" data-act="del">${ICON.trash} हटाएँ</button></div>`;
  } else if (type === "sfx") {
    const item = libItem(it.id);
    h = `<h3>SFX</h3><p class="small muted">${esc(item?.name || "?")}</p><div class="irow">${field("कब", num("at", it.at, 0.05, 0))}${field("आवाज़", `<input type="range" data-k="volume" min="0" max="1.5" step="0.05" value="${it.volume ?? 0.8}" ${dis}>`)}</div>
      <div class="irow"><button class="btn small" data-act="seek">यहाँ जाएँ</button><button class="btn small danger quiet" data-act="del">${ICON.trash} हटाएँ</button></div>`;
  } else if (type === "caption") {
    h = `<h3>Caption</h3><p class="small muted">${fmt(it.start)} – ${fmt(it.end)}</p>${field("शब्द सुधारें", `<textarea data-k="_captext" rows="3" ${dis}>${esc(it.words.map((w) => w.w).join(" "))}</textarea>`)}
      <p class="small muted">शब्दों की गिनती वही रखें तो timing सटीक रहती है।</p><div class="irow"><button class="btn small" data-act="seek">यहाँ जाएँ</button><button class="btn small" data-act="captext">बदलें</button></div>`;
  }
  ins.innerHTML = h;
  $$("[data-k]", ins).forEach((el) => (el.oninput = el.onchange = () => {
    if (!E.canEdit) return;
    const k = el.dataset.k;
    if (k === "_bgon") { it.bg = el.checked ? ($('[data-k="bg"]', ins).value) : ""; }
    else if (k === "_captext") return;
    else if (el.type === "checkbox") it[k] = el.checked;
    else if (el.type === "number" || el.type === "range") it[k] = +el.value;
    else it[k] = el.value;
    if (k === "bg" && !$('[data-k="_bgon"]', ins).checked) it.bg = "";
    if (type === "cut") { it.start = clamp(it.start, 0, E.dur); it.end = clamp(it.end, it.start + 0.05, E.dur); }
    touch();
  }));
  $$("[data-act]", ins).forEach((b) => (b.onclick = () => {
    const a = b.dataset.act;
    if (a === "del") deleteSel();
    else if (a === "seek") seek(type === "cut" ? it.start : type === "caption" ? it.start : srcOf(it.start ?? it.at));
    else if (a === "captext") applyCaptionText(it, $('[data-k="_captext"]', ins).value);
  }));
}
function applyCaptionText(chunk, text) {
  const parts = text.trim().split(/\s+/).filter(Boolean); if (!parts.length) return;
  const ws = chunk.words; const s = ws[0].start, e = ws[ws.length - 1].end;
  if (parts.length === ws.length) ws.forEach((w, i) => (w.w = parts[i]));
  else {
    const step = (e - s) / parts.length; const fresh = parts.map((p, i) => ({ w: p, start: +(s + i * step).toFixed(3), end: +(s + (i + 1) * step).toFixed(3) }));
    // replace inside the transcript segment that holds these words
    for (const seg of E.p.transcript.segments) { const i = (seg.words || []).indexOf(ws[0]); if (i >= 0) { seg.words.splice(i, ws.length, ...fresh); seg.text = seg.words.map((w) => w.w).join(" "); break; } }
    E.words = E.p.transcript.segments.flatMap((sg) => sg.words || []);
  }
  E.transcriptDirty = true; touch(); select(null); E.ctx.toast("caption बदला");
}

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
        <input type="checkbox" ${c.enabled !== false ? "checked" : ""} ${dis}><span class="tag ${c.reason}">${{ silence: "चुप्पी", filler: "अं-आं", retake: "retake", manual: "आपका" }[c.reason] || c.reason}</span><span class="grow small">${esc(c.text || "")}</span><span class="small muted">${fmt(c.start)}</span></li>`).join("")}</ul>
      <p class="small muted">अपना कट: वीडियो में I दबाएँ, फिर O, फिर X (या “हटाएँ”)।</p>`;
  } else if (t === "captions") {
    const ov = E.rs.captions;
    h = `<div class="ph"><h3>Caption style</h3><label class="chk small"><input type="checkbox" id="burn" ${E.rs.burn_captions !== false ? "checked" : ""} ${dis}> वीडियो में जलाएँ</label></div>
      <div class="styles">${(S.presets?.caption_styles || []).map((cs) => stylePreview(cs, E.rs.caption_style === cs.id)).join("")}</div>
      <h4>अपने हिसाब से</h4>
      <div class="irow">${field("आकार", `<input type="range" id="cap-size" min="0.6" max="1.8" step="0.05" value="${ov.size_scale ?? 1}" ${dis}>`)}${field("जगह", `<select id="cap-pos" ${dis}><option value="">style जैसी</option>${["bottom", "center", "top"].map((p) => `<option value="${p}" ${ov.position === p ? "selected" : ""}>${{ bottom: "नीचे", center: "बीच", top: "ऊपर" }[p]}</option>`).join("")}</select>`)}</div>
      <div class="irow">${field("font", `<select id="cap-font" ${dis}><option value="">style जैसा</option>${(S.presets?.fonts || []).map((f) => `<option ${ov.font === f ? "selected" : ""}>${f}</option>`).join("")}</select>`)}</div>
      <div class="irow">${field("अक्षर", `<input type="color" id="cap-primary" value="${ov.primary || "#ffffff"}" ${dis}>`)}${field("highlight", `<input type="color" id="cap-highlight" value="${ov.highlight || "#ffd400"}" ${dis}>`)}${field("", `<label class="chk small"><input type="checkbox" id="cap-usecolors" ${ov.primary ? "checked" : ""} ${dis}> रंग लागू</label>`)}</div>
      <h4>Hook (शुरू के 3 सेकंड)</h4>${field("", `<input id="hook" value="${esc(E.rs.hook.text || "")}" placeholder="4 बजे उठने वाला लड़का" ${dis}>`)}`;
  } else if (t === "text") {
    h = `<div class="ph"><h3>Text</h3><span class="small muted">playhead पर जुड़ेगा</span></div>
      <div class="tgrid">${TITLE_PRESETS.map((tp) => `<button class="tcard" data-title="${tp.id}" ${dis}><span style="color:${tp.color};${tp.bg ? `background:${tp.bg};padding:.1em .4em;border-radius:4px` : ""};font-size:${tp.size * 220}px;font-weight:800">${esc(tp.text.split("|")[0])}</span><small>${tp.label}</small></button>`).join("")}</div>
      <h4>Timeline पर</h4><ul class="plist">${fx.titles.map((ti) => `<li class="${E.sel?.type === "title" && E.sel.id === ti._id ? "sel" : ""}" data-title-id="${ti._id}"><span class="grow small">${esc(ti.text)}</span><span class="small muted">${fmt(ti.start)}</span></li>`).join("") || `<li class="muted small">अभी कोई text नहीं</li>`}</ul>`;
  } else if (t === "media" || t === "audio" || t === "overlay") {
    const kinds = t === "media" ? ["broll", "image"] : t === "audio" ? ["music", "sfx"] : ["logo", "lut"];
    if (!kinds.includes(E.libKind)) E.libKind = kinds[0];
    const items = (E.lib || []).filter((x) => x.kind === E.libKind);
    const music = fx.music, wm = fx.watermark;
    h = `<div class="ph"><h3>${{ media: "Media library", audio: "Audio", overlay: "Logo & LUT" }[t]}</h3></div>
      <div class="seg">${kinds.map((k) => `<button data-kind="${k}" class="${E.libKind === k ? "on" : ""}">${LIB_KINDS.find((x) => x[0] === k)[1]}</button>`).join("")}</div>
      <label class="drop small ${dis ? "off" : ""}"><input type="file" id="lib-file" multiple hidden ${dis}>${ICON.plus} ${E.libKind} upload करें <span class="muted">(${{ music: "mp3/wav", sfx: "mp3/wav", broll: "mp4/mov", image: "png/jpg", logo: "png", lut: ".cube" }[E.libKind]})</span></label>
      <div id="lib-progress"></div>
      ${t === "audio" && E.libKind === "music" ? `<div class="box"><b>Background music</b>${music.id ? `<p class="small">${esc(libItem(music.id)?.name || music.id)}</p>` : `<p class="small muted">library से “लगाएँ” दबाएँ</p>`}
        <div class="irow">${field("आवाज़", `<input type="range" id="mus-vol" min="0" max="0.6" step="0.02" value="${music.volume}" ${dis}>`)}<label class="chk small"><input type="checkbox" id="mus-duck" ${music.duck !== false ? "checked" : ""} ${dis}> बोलते समय धीमा (duck)</label></div>
        ${music.id ? `<button class="btn small quiet" id="mus-clear">हटाएँ</button>` : ""}</div>` : ""}
      ${t === "overlay" && E.libKind === "logo" ? `<div class="box"><b>Watermark</b>${wm.id ? `<p class="small">${esc(libItem(wm.id)?.name || "")}</p>` : `<p class="small muted">logo चुनकर “लगाएँ”</p>`}
        <div class="irow">${field("पारदर्शिता", `<input type="range" id="wm-op" min="0.1" max="1" step="0.05" value="${wm.opacity}" ${dis}>`)}${field("आकार", `<input type="range" id="wm-size" min="0.06" max="0.3" step="0.01" value="${wm.size}" ${dis}>`)}</div>
        ${field("कोना", `<select id="wm-pos" ${dis}>${["tr", "tl", "br", "bl"].map((p) => `<option value="${p}" ${wm.pos === p ? "selected" : ""}>${{ tr: "ऊपर दाएँ", tl: "ऊपर बाएँ", br: "नीचे दाएँ", bl: "नीचे बाएँ" }[p]}</option>`).join("")}</select>`)}
        ${wm.id ? `<button class="btn small quiet" id="wm-clear">हटाएँ</button>` : ""}</div>` : ""}
      ${t === "overlay" && E.libKind === "lut" ? `<p class="small muted">LUT (.cube) लगाने पर Effects का look बदल जाता है। अभी: <b>${fx.look?.startsWith("lut:") ? esc(libItem(fx.look.slice(4))?.name || "LUT") : "कोई नहीं"}</b></p>` : ""}
      <ul class="lib">${E.lib === null ? `<li class="muted small">लोड हो रहा…</li>` : items.map((x) => `<li data-lib="${x.id}">
        ${x.kind === "image" || x.kind === "logo" ? `<img src="${x.url}" alt="">` : x.kind === "broll" ? `<video src="${x.url}#t=0.5" muted preload="metadata"></video>` : `<i class="libicon">${ICON.audio}</i>`}
        <div class="grow"><b class="small">${esc(x.name)}</b><span class="small muted">${x.meta?.duration ? fmt(x.meta.duration) : ""}${x.meta?.width ? ` · ${x.meta.width}×${x.meta.height}` : ""}</span></div>
        ${x.kind === "music" || x.kind === "sfx" || x.kind === "broll" ? `<button class="ibtn" data-prev="${x.id}" title="सुनें/देखें">${ICON.play}</button>` : ""}
        <button class="btn small primary" data-add="${x.id}" ${dis}>${{ music: "लगाएँ", logo: "लगाएँ", lut: "लगाएँ" }[x.kind] || "+ जोड़ें"}</button>
        <button class="ibtn" data-del="${x.id}" title="library से हटाएँ" ${dis}>${ICON.trash}</button></li>`).join("") || `<li class="muted small">अभी कुछ नहीं — ऊपर से upload करें।</li>`}</ul>`;
  } else if (t === "effects") {
    const looks = S.presets?.looks || Object.keys(LOOK_CSS).map((id) => ({ id, label: id }));
    const thumb = (E.p.assets.find((a) => a.kind === "thumb") || {}).url;
    h = `<div class="ph"><h3>Effects</h3></div>
      <div class="box"><label class="chk"><input type="checkbox" id="fx-zoom" ${fx.zoom.enabled ? "checked" : ""} ${dis}> <b>Auto zoom / punch-in</b></label><p class="small muted">हर कट पर हल्का zoom — jump cut की जगह deliberate लगता है।</p>
        ${field("कितना", `<input type="range" id="fx-zoom-str" min="0.3" max="2" step="0.1" value="${fx.zoom.strength}" ${dis}>`)}</div>
      <div class="box"><label class="chk"><input type="checkbox" id="fx-flash" ${fx.flash ? "checked" : ""} ${dis}> <b>Cut flash</b></label><p class="small muted">हर कट पर सफ़ेद flash transition।</p></div>
      <h4>Color look</h4><div class="looks">${looks.map((l) => `<button class="look ${fx.look === l.id ? "on" : ""}" data-look="${l.id}" ${dis}>${thumb ? `<img src="${thumb}" style="filter:${LOOK_CSS[l.id] || ""}" alt="">` : `<i style="filter:${LOOK_CSS[l.id] || ""}"></i>`}<small>${esc(l.label)}</small></button>`).join("")}</div>
      <p class="small muted">LUT फ़ाइल (.cube) Overlay → LUT से लगाएँ।</p>`;
  }
  panel.innerHTML = h;
  bindPanel();
}
function bindPanel() {
  const panel = $("#ed-panel", E.root); const { api, toast, load, S } = E.ctx; const fx = E.rs.effects;
  const on = (sel, ev, fn) => { const el = $(sel, panel); if (el) el[ev] = fn; };
  // cuts
  $$("[data-cut]", panel).forEach((li) => {
    li.onclick = (e) => { const c = E.cuts.find((x) => x.id === li.dataset.cut); if (e.target.type === "checkbox") { c.enabled = e.target.checked; touch(); renderPanel(); } else { select({ type: "cut", id: c.id }); seek(c.start); renderPanel(); } };
  });
  on("#cuts-all-on", "onclick", () => { E.cuts.forEach((c) => (c.enabled = true)); touch(); renderPanel(); });
  on("#cuts-all-off", "onclick", () => { E.cuts.forEach((c) => (c.enabled = false)); touch(); renderPanel(); });
  on("#recut", "onclick", async () => { await save(false); const ctx = E.ctx; await api("POST", `/projects/${E.pid}/recut`, { options: { max_pause: +$("#max-pause", panel).value } }); toast("कट दोबारा ढूँढे जा रहे हैं"); unmount(); await ctx.load(); ctx.render(); });
  // captions
  $$(".stylecard input", panel).forEach((i) => (i.onchange = () => { E.rs.caption_style = i.value; $$(".stylecard", panel).forEach((c) => c.classList.toggle("on", c.contains(i))); touch(); }));
  on("#burn", "onchange", (e) => { E.rs.burn_captions = e.target.checked; touch(); });
  const capSync = () => { const c = E.rs.captions; c.size_scale = +$("#cap-size", panel).value; c.position = $("#cap-pos", panel).value; c.font = $("#cap-font", panel).value;
    const use = $("#cap-usecolors", panel).checked; c.primary = use ? $("#cap-primary", panel).value : ""; c.highlight = use ? $("#cap-highlight", panel).value : ""; touch(); };
  ["#cap-size", "#cap-pos", "#cap-font", "#cap-primary", "#cap-highlight", "#cap-usecolors"].forEach((s) => on(s, "oninput", capSync));
  on("#hook", "oninput", (e) => { E.rs.hook.text = e.target.value; touch(); });
  // text
  $$("[data-title]", panel).forEach((b) => (b.onclick = () => { const tp = TITLE_PRESETS.find((x) => x.id === b.dataset.title); const st = +outOf(E.t).toFixed(2);
    const ti = { _id: uid(), start: st, end: +Math.min(outDur(), st + 3).toFixed(2), text: tp.text, pos: tp.pos, size: tp.size, color: tp.color, bg: tp.bg };
    fx.titles.push(ti); touch(); select({ type: "title", id: ti._id }); renderPanel(); }));
  $$("[data-title-id]", panel).forEach((li) => (li.onclick = () => { const ti = fx.titles.find((x) => x._id === li.dataset.titleId); select({ type: "title", id: ti._id }); seek(srcOf(ti.start)); }));
  // library
  $$("[data-kind]", panel).forEach((b) => (b.onclick = () => { E.libKind = b.dataset.kind; renderPanel(); }));
  on("#lib-file", "onchange", async (e) => { for (const f of e.target.files) await libUpload(E.libKind, f); renderPanel(); });
  $$("[data-prev]", panel).forEach((b) => (b.onclick = () => { const x = libItem(b.dataset.prev); if (E.audio) { E.audio.pause(); if (E.audio.src === x.url) { E.audio = null; return; } } E.audio = new Audio(x.url); E.audio.play(); }));
  $$("[data-add]", panel).forEach((b) => (b.onclick = () => libAdd(libItem(b.dataset.add))));
  $$("[data-del]", panel).forEach((b) => (b.onclick = async () => { if (!confirm("library से हटाएँ?")) return; await api("DELETE", `/library/${b.dataset.del}`); E.lib = E.lib.filter((x) => x.id !== b.dataset.del); renderPanel(); }));
  on("#mus-vol", "oninput", (e) => { fx.music.volume = +e.target.value; touch(); });
  on("#mus-duck", "onchange", (e) => { fx.music.duck = e.target.checked; touch(); });
  on("#mus-clear", "onclick", () => { fx.music.id = ""; touch(); renderPanel(); });
  on("#wm-op", "oninput", (e) => { fx.watermark.opacity = +e.target.value; touch(); });
  on("#wm-size", "oninput", (e) => { fx.watermark.size = +e.target.value; touch(); });
  on("#wm-pos", "onchange", (e) => { fx.watermark.pos = e.target.value; touch(); });
  on("#wm-clear", "onclick", () => { fx.watermark.id = ""; touch(); renderPanel(); });
  // effects
  on("#fx-zoom", "onchange", (e) => { fx.zoom.enabled = e.target.checked; touch(); });
  on("#fx-zoom-str", "oninput", (e) => { fx.zoom.strength = +e.target.value; touch(); });
  on("#fx-flash", "onchange", (e) => { fx.flash = e.target.checked; touch(); });
  $$("[data-look]", panel).forEach((b) => (b.onclick = () => { fx.look = b.dataset.look; $$(".look", panel).forEach((x) => x.classList.toggle("on", x === b)); layoutFrame(); touch(); }));
}
function libItem(id) { return (E.lib || []).find((x) => x.id === id); }
async function loadLib() { try { E.lib = await E.ctx.api("GET", "/library"); } catch { E.lib = []; } if (E && ["media", "audio", "overlay"].includes(E.tab)) renderPanel(); else renderOverlay(); }
async function libUpload(kind, file) {
  const { toast } = E.ctx; const prog = $("#lib-progress", E.root);
  prog.innerHTML = `<p class="small muted">${file.name} upload हो रहा…</p><div class="progress"><i style="width:30%"></i></div>`;
  try {
    const r = await fetch(`/api/library?kind=${kind}&filename=${encodeURIComponent(file.name)}`, { method: "PUT", headers: { authorization: "Bearer " + E.ctx.S.token, "content-type": "application/octet-stream" }, body: file });
    const data = await r.json(); if (!r.ok) throw new Error(data.error || r.statusText);
    E.lib = E.lib || []; E.lib.unshift(data); toast(`${file.name} जुड़ा`);
  } catch (err) { toast(err.message); }
  prog.innerHTML = "";
}
function libAdd(x) {
  if (!x || !E.canEdit) return; const fx = E.rs.effects; const st = +outOf(E.t).toFixed(2);
  if (x.kind === "music") fx.music.id = x.id;
  else if (x.kind === "logo") fx.watermark.id = x.id;
  else if (x.kind === "lut") fx.look = "lut:" + x.id;
  else if (x.kind === "sfx") { const s = { _id: uid(), id: x.id, at: st, volume: 0.8 }; fx.sfx.push(s); select({ type: "sfx", id: s._id }); }
  else { const d = x.kind === "image" ? 3 : Math.min(x.meta?.duration || 4, 8); const b = { _id: uid(), id: x.id, start: st, end: +Math.min(outDur(), st + d).toFixed(2), fit: x.kind === "image" ? "pip" : "cover", pos: "tr" }; fx.broll.push(b); select({ type: "broll", id: b._id }); }
  touch(); renderPanel();
}

// ---------- timeline ----------
const TRACKS = [["video", "Video"], ["captions", "Caption"], ["text", "Text"], ["broll", "B-roll"], ["audio", "Audio"]];
function renderTimeline() {
  const body = $("#tl-body", E.root), labels = $("#tl-labels", E.root); if (!body) return;
  const { esc } = E.ctx; const pps = E.pps; const W = Math.ceil(E.dur * pps) + 80; const fx = E.rs.effects;
  const X = (src) => (src * pps).toFixed(1); const OX = (out) => X(srcOf(out)); const OW = (a, b) => Math.max(6, (srcOf(b) - srcOf(a)) * pps).toFixed(1);
  const step = pps >= 80 ? 0.5 : pps >= 40 ? 1 : pps >= 16 ? 2 : pps >= 8 ? 5 : 10;
  let ruler = ""; for (let t = 0; t <= E.dur; t += step) ruler += `<span style="left:${X(t)}px" class="${t % (step * 5) === 0 ? "maj" : ""}">${t % (step * 5) === 0 ? fmt(t).replace(/\.0$/, "") : ""}</span>`;
  const sel = (type, id) => (E.sel?.type === type && E.sel.id === id ? "sel" : "");
  const ks = keeps();
  const video = ks.map(([a, b]) => `<div class="clip" style="left:${X(a)}px;width:${((b - a) * pps).toFixed(1)}px"><span>${fmt(b - a)}</span></div>`).join("")
    + E.cuts.map((c) => `<div class="cutblk ${c.enabled === false ? "off" : ""} ${sel("cut", c.id)}" data-cut="${c.id}" style="left:${X(c.start)}px;width:${Math.max(4, (c.end - c.start) * pps).toFixed(1)}px" title="${c.reason} ${fmt(c.start)}–${fmt(c.end)}"><i class="h l"></i><i class="h r"></i></div>`).join("")
    + (E.markIn != null && E.markOut != null ? `<div class="markrange" style="left:${X(E.markIn)}px;width:${((E.markOut - E.markIn) * pps).toFixed(1)}px"></div>` : "");
  const caps = captionChunks().map((c, i) => `<div class="capblk ${sel("caption", i)}" data-cap="${i}" style="left:${X(c.start)}px;width:${Math.max(6, (c.end - c.start) * pps).toFixed(1)}px"><span>${esc(c.words.map((w) => w.w).join(" "))}</span></div>`).join("");
  const text = fx.titles.map((t) => `<div class="itm title ${sel("title", t._id)}" data-item="title:${t._id}" style="left:${OX(t.start)}px;width:${OW(t.start, t.end)}px"><i class="h l"></i><span>${esc(t.text)}</span><i class="h r"></i></div>`).join("")
    + (E.rs.hook.text ? `<div class="itm hook" style="left:0;width:${OW(0, Math.min(outDur(), E.rs.hook.seconds || 3))}px"><span>HOOK ${esc(E.rs.hook.text)}</span></div>` : "");
  const broll = fx.broll.map((b) => `<div class="itm broll ${sel("broll", b._id)}" data-item="broll:${b._id}" style="left:${OX(b.start)}px;width:${OW(b.start, b.end)}px"><i class="h l"></i><span>${esc(libItem(b.id)?.name || "B-roll")}${b.fit === "pip" ? " · PiP" : ""}</span><i class="h r"></i></div>`).join("");
  const audio = (fx.music.id ? `<div class="itm music ${sel("music", "m")}" data-item="music:m" style="left:0;width:${(E.dur * pps).toFixed(1)}px"><span>♪ ${esc(libItem(fx.music.id)?.name || "music")} · ${Math.round(fx.music.volume * 100)}%${fx.music.duck !== false ? " · duck" : ""}</span></div>` : "")
    + fx.sfx.map((s) => `<div class="itm sfx ${sel("sfx", s._id)}" data-item="sfx:${s._id}" style="left:${OX(s.at)}px;width:${Math.max(14, 0.6 * pps).toFixed(1)}px" title="${esc(libItem(s.id)?.name || "sfx")}"><span>${esc(libItem(s.id)?.name || "sfx")}</span></div>`).join("");
  const rows = { video, captions: caps, text, broll, audio };
  labels.innerHTML = `<div class="tl-ruler-l"></div>` + TRACKS.map(([id, l]) => `<div class="tl-l">${l}</div>`).join("");
  body.style.width = W + "px";
  body.innerHTML = `<div class="tl-ruler" id="tl-ruler">${ruler}</div>` + TRACKS.map(([id]) => `<div class="tl-track ${id}" data-track="${id}">${rows[id]}</div>`).join("")
    + `<div class="tl-play" id="tl-play" style="left:${X(E.t)}px"><i></i></div>`;
  bindTimeline();
  $("#tl-info", E.root).textContent = `${fmt(E.dur)} source → ${fmt(outDur())} output · ${E.cuts.filter((c) => c.enabled !== false).length} कट · ${fx.titles.length} text · ${fx.broll.length} B-roll`;
  $("#t-dur", E.root).textContent = fmt(E.dur);
}
function renderPlayhead(scrollInto) {
  const ph = $("#tl-play", E.root); if (ph) ph.style.left = (E.t * E.pps).toFixed(1) + "px";
  $("#t-now", E.root).textContent = fmtF(E.t);
  if (scrollInto) { const sc = $("#tl-scroll", E.root); const x = E.t * E.pps + 110; if (x > sc.scrollLeft + sc.clientWidth - 40 || x < sc.scrollLeft + 110) sc.scrollLeft = x - 200; }
}
function bindTimeline() {
  const body = $("#tl-body", E.root); const pps = E.pps; const fx = E.rs.effects;
  const srcAt = (e) => clamp((e.clientX - body.getBoundingClientRect().left) / pps, 0, E.dur);
  // click / scrub on ruler + empty track area
  body.onmousedown = (e) => {
    if (e.target.closest(".itm,.cutblk,.capblk,.h")) return;
    const v = $("#pv", E.root); const wasPlaying = v && !v.paused; if (v) v.pause();
    const mv = (ev) => seek(srcAt(ev)); mv(e);
    const up = () => { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); if (wasPlaying) v.play(); };
    document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up);
  };
  $$(".cutblk", body).forEach((el) => { el.onmousedown = (e) => { e.stopPropagation(); const c = E.cuts.find((x) => x.id === el.dataset.cut); if (e.target.classList.contains("h")) return dragEdge(e, c, e.target.classList.contains("l") ? "start" : "end", "src"); select({ type: "cut", id: c.id }); };
    el.ondblclick = () => { const c = E.cuts.find((x) => x.id === el.dataset.cut); c.enabled = c.enabled === false; touch(); }; });
  $$(".capblk", body).forEach((el) => (el.onmousedown = (e) => { e.stopPropagation(); const i = +el.dataset.cap; select({ type: "caption", id: i }); seek(captionChunks()[i].start); }));
  $$(".itm", body).forEach((el) => (el.onmousedown = (e) => {
    e.stopPropagation(); const [type, id] = el.dataset.item?.split(":") || []; if (!type) return;
    if (type === "music") return select({ type: "music", id: "m" });
    const it = type === "title" ? fx.titles.find((x) => x._id === id) : type === "broll" ? fx.broll.find((x) => x._id === id) : fx.sfx.find((x) => x._id === id);
    select({ type, id });
    if (e.target.classList.contains("h")) return dragEdge(e, it, e.target.classList.contains("l") ? "start" : "end", "out");
    dragMove(e, it, type);
  }));
}
function dragEdge(e, it, key, clock) {
  if (!E.canEdit) return; const pps = E.pps; const x0 = e.clientX; const v0 = it[key];
  const mv = (ev) => { let t = (clock === "src" ? v0 : srcOf(v0)) + (ev.clientX - x0) / pps; t = clamp(t, 0, E.dur); if (clock === "out") t = outOf(t);
    if (key === "start") it.start = +Math.min(t, it.end - 0.1).toFixed(2); else it.end = +Math.max(t, it.start + 0.1).toFixed(2); renderTimeline(); renderInspector(); };
  const up = () => { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); touch(); };
  document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up);
}
function dragMove(e, it, type) {
  if (!E.canEdit) return; const pps = E.pps; const x0 = e.clientX; const s0 = type === "sfx" ? it.at : it.start; const len = type === "sfx" ? 0 : it.end - it.start; let moved = false;
  const mv = (ev) => { const dx = ev.clientX - x0; if (Math.abs(dx) < 3 && !moved) return; moved = true;
    let s = outOf(clamp(srcOf(s0) + dx / pps, 0, E.dur)); s = clamp(s, 0, Math.max(0, outDur() - len));
    if (type === "sfx") it.at = +s.toFixed(2); else { it.start = +s.toFixed(2); it.end = +(s + len).toFixed(2); } renderTimeline(); renderInspector(); };
  const up = () => { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); if (moved) touch(); };
  document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up);
}

// ---------- top / export ----------
function renderTop() {
  const ST = { review_cuts: "कट जाँचें", rendering: "render हो रहा है…", review_output: "मंज़ूरी बाकी", approved: "मंज़ूर", failed: "रुक गया" };
  const el = $("#ed-status", E.root); if (el) el.textContent = ST[E.p.status] || E.p.status;
  const b = $("#ed-export", E.root); if (b) b.disabled = E.p.status === "rendering";
}
function renderExport() {
  const m = $("#ed-modal", E.root); const { esc, S, api, toast, load } = E.ctx; const p = E.p;
  if (!E.exportOpen) { m.hidden = true; m.innerHTML = ""; return; }
  const outs = p.assets.filter((a) => a.kind === "render"); const job = p.jobs?.find((j) => j.kind === "render" && ["running", "queued"].includes(j.status));
  const fx = E.rs.effects; const summary = [E.cuts.filter((c) => c.enabled !== false).length + " कट", styleOf()?.label, fx.zoom.enabled && "zoom", fx.look !== "none" && ("look " + fx.look.replace(/^lut:.*/, "LUT")), fx.music.id && "music", fx.broll.length && fx.broll.length + " B-roll", fx.titles.length && fx.titles.length + " text", fx.watermark.id && "logo"].filter(Boolean).join(" · ");
  m.hidden = false;
  m.innerHTML = `<div class="modal"><div class="row between"><h2>Export</h2><button class="ibtn" id="mx">✕</button></div>
    <p class="small muted">${esc(summary)} · output ${fmt(outDur())}</p>
    <div class="ifield"><label>कहाँ के लिए</label><div class="choices">${(S.presets?.platforms || []).map((pl) => `<label class="chip ${E.rs.presets.includes(pl.id) ? "on" : ""}"><input type="checkbox" name="preset" value="${pl.id}" ${E.rs.presets.includes(pl.id) ? "checked" : ""}>${esc(pl.label)}</label>`).join("")}</div></div>
    <div class="irow">${field("9:16 में चेहरा", `<select id="focus"><option value="0.5" ${E.rs.focus_x == 0.5 ? "selected" : ""}>बीच</option><option value="0.25" ${E.rs.focus_x == 0.25 ? "selected" : ""}>बाएँ</option><option value="0.75" ${E.rs.focus_x == 0.75 ? "selected" : ""}>दाएँ</option></select>`)}</div>
    ${p.status === "rendering" ? `<div class="progress"><i style="width:${job ? job.progress : 0}%"></i></div><p class="small muted">${esc(job?.message || "queue में")}</p>` : ""}
    ${outs.length ? `<h3>तैयार वीडियो</h3><div class="outputs">${outs.map((a) => { const pl = S.presets?.platforms.find((x) => x.id === a.label); const srt = p.assets.find((s) => s.kind === "subtitle" && s.label === a.label);
      return `<div class="output ${a.meta.height > a.meta.width ? "vertical" : ""}"><video src="${a.url}" controls playsinline preload="metadata"></video><div class="row between"><b>${esc(pl ? pl.label : a.label)}</b><span class="muted small">${fmt(a.meta.duration)}</span></div><div class="row"><a class="btn small" href="${a.url}&download=1">download</a>${srt ? `<a class="btn quiet small" href="${srt.url}&download=1">SRT</a>` : ""}</div></div>`; }).join("")}</div>` : ""}
    <div class="row between" style="margin-top:1rem"><span class="small muted">${p.status === "review_output" && S.user.role !== "admin" ? "मंज़ूरी admin देंगे" : p.status === "approved" ? "मंज़ूर ✓" : ""}</span>
      <span class="row">${p.status === "review_output" && S.user.role === "admin" ? `<button class="btn" id="approve">मंज़ूरी दें</button>` : ""}${E.canEdit ? `<button class="btn primary" id="go-render" ${p.status === "rendering" ? "disabled" : ""}>${p.status === "rendering" ? "render हो रहा…" : outs.length ? "दोबारा render" : "render करें"}</button>` : ""}</span></div></div>`;
  $("#mx", m).onclick = () => { E.exportOpen = false; renderExport(); };
  m.onclick = (e) => { if (e.target === m) { E.exportOpen = false; renderExport(); } };
  $$(".chip input", m).forEach((i) => (i.onchange = () => i.closest(".chip").classList.toggle("on", i.checked)));
  const gr = $("#go-render", m); if (gr) gr.onclick = async () => {
    E.rs.presets = $$("input[name=preset]:checked", m).map((i) => i.value); E.rs.focus_x = +$("#focus", m).value;
    if (!E.rs.presets.length) return toast("कम से कम एक platform चुनें");
    await save(false);
    try { const rs = JSON.parse(JSON.stringify(E.rs)); await api("POST", `/projects/${E.pid}/render`, rs); toast("render शुरू"); await load(); } catch (err) { toast(err.message); }
  };
  const ap = $("#approve", m); if (ap) ap.onclick = async () => { if (confirm("यह वीडियो मंज़ूर करें?")) { await api("POST", `/projects/${E.pid}/approve`); toast("मंज़ूर"); await load(); } };
}

function renderAll() { renderTop(); renderPanel(); renderInspector(); renderTimeline(); layoutFrame(); renderOverlay(); renderPlayhead(); }
