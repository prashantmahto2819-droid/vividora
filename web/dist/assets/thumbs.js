// Vividora — Thumbnail studio (no build step). Mounted by app.js on #/thumbs/<project id>.
// Server: /api/projects/<id>/thumbnails* (server/vividora/api/thumbnails.py)
//
// Direct editing: the server renders the background and every layer (text, person cut-out, stickers,
// shapes, labels, badge, logo) as separate sprites (POST …/thumbnails/layers). The stage stacks those
// sprites, so dragging / resizing / rotating moves the exact pixels the final render will paste.
// Placement is stored in fractions of the canvas:
//   settings.layout[size][layerId] = {x, y, s, rot, hidden}   (x / y = the layer's anchor point)
//   settings.layout[size]._order    = layer ids bottom → top
//   settings.stickers[i]            = {uid, x, y, w | size, rot, id | shape | txt, …}

let T = null;
let TPLS = null; // cached /thumbnails/templates

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const fmtT = (t) => { t = Math.max(0, +t || 0); const m = Math.floor(t / 60), s = t % 60; return `${m}:${s < 10 ? "0" : ""}${s.toFixed(1)}`; };
const COLORS = ["#FFD400", "#FF3B30", "#E50914", "#00E5FF", "#00E676", "#FF6A00", "#F2B33D", "#FFFFFF", "#111111", "#E040FB"];
const FONT_CSS = { Mukta: "Mukta", "Mukta Bold": "Mukta", "Baloo 2": "'Baloo 2'", "Baloo 2 Bold": "'Baloo 2'", Hind: "Hind", Poppins: "Poppins",
  "Noto Sans Devanagari": "'Noto Sans Devanagari'", FreeSerif: "'Vividora FreeSerif'", Inter: "'Vividora Inter'", Lora: "Lora" };
const FONT_W = { "Baloo 2 Bold": 600, "Mukta Bold": 700, "Noto Sans Devanagari": 900, Lora: 700 };
const TEXT_STYLE_KEYS = ["stroke_w", "stroke2_w", "stroke", "stroke2", "shadow", "shadow_color", "glow", "fill2", "spacing", "line_h", "skew", "hl_box", "banner", "hl2", "align"];
const BADGES = [
  { txt: "NEW", bg: "#E50914", color: "#FFFFFF", font: "Poppins" }, { txt: "सच्ची कहानी", bg: "#FFD400", color: "#111111" },
  { txt: "LIVE", bg: "#E50914", color: "#FFFFFF", font: "Poppins" }, { txt: "100% सच", bg: "#1FAA59", color: "#FFFFFF" },
  { txt: "मत करना!", bg: "#111111", color: "#FFD400" }, { txt: "SHOCKING", bg: "#FF6A00", color: "#FFFFFF", font: "Poppins" },
  { txt: "PART 2", bg: "#FFFFFF", color: "#111111", font: "Poppins" }, { txt: "सबसे बड़ा राज़", bg: "", color: "#FFD400" },
  { txt: "नया text", bg: "", color: "#FFFFFF" }];
const EMOJI = ["🔥", "😱", "😭", "🤯", "💰", "❤️", "👉", "👀", "✅", "❌", "⚡", "💯", "😡", "🙏", "🏆", "⏰", "💔", "🚀"];
const SNAP_PX = 7;

async function authBlob(path, body, signal) {
  const r = await fetch("/api" + path, { method: body ? "POST" : "GET", headers: { authorization: "Bearer " + T.ctx.S.token, ...(body ? { "content-type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined, signal });
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).error || m; } catch {} throw new Error(m); }
  return { blob: await r.blob(), headers: r.headers };
}
async function postJSON(path, body, signal) {
  const r = await fetch("/api" + path, { method: "POST", headers: { authorization: "Bearer " + T.ctx.S.token, "content-type": "application/json" }, body: JSON.stringify(body), signal });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || r.statusText);
  return d;
}

export async function mount(root, pid, ctx) {
  unmount();
  T = { root, pid, ctx, p: null, ov: null, frames: [], frameUrls: {}, lib: [], sugg: null, s: null, lint: [], info: {}, timer: null, abort: null,
        canEdit: ctx.S.user.role !== "viewer", panel: localStorage.getItem("vividora_thpanel") || "text",
        view: null, sprites: {}, sel: null, hist: [], hi: -1, drag: null, pend: null, editing: null, pdrag: null };
  root.innerHTML = `<div class="th-loading"><div class="spin"></div><p class="muted">Thumbnail studio खुल रहा है…</p></div>`;
  try {
    const [p, ov, tp] = await Promise.all([ctx.api("GET", `/projects/${pid}`), ctx.api("GET", `/projects/${pid}/thumbnails`), TPLS ? Promise.resolve(TPLS) : ctx.api("GET", "/thumbnails/templates")]);
    if (!T || T.pid !== pid) return;
    TPLS = tp; T.p = p; T.ov = ov; T.frames = ov.frames || [];
  } catch (e) { root.innerHTML = `<div class="note err">${ctx.esc(e.message)}</div><a class="btn" href="#/thumbs">← वापस</a>`; return; }
  const sel = T.ov.saved.find((a) => a.selected && a.label === "yt") || T.ov.saved[0];
  T.s = sel?.meta?.settings ? JSON.parse(JSON.stringify(sel.meta.settings)) : { template: "face_right", size: "yt", t: T.frames[0]?.t || 0, text: "", cutout: true, logo: T.ov.brand_logo };
  T.hist = [JSON.stringify(T.s)]; T.hi = 0;
  shell();
  T.onKey = (e) => onKey(e); document.addEventListener("keydown", T.onKey);
  T.onResize = () => drawSel(); window.addEventListener("resize", T.onResize);
  if (!T.ov.has_video) { $("#th-stage-msg", root).innerHTML = `<div class="note">इस project में अभी वीडियो नहीं है — upload / preview बनने के बाद thumbnail बनेगा।</div>`; return; }
  loadFrames(false);
  if (!T.s.text) suggest(true);
  loadLib();
  refresh(0);
}

export function unmount() {
  if (!T) return;
  clearTimeout(T.timer); T.abort?.abort();
  document.removeEventListener("keydown", T.onKey); window.removeEventListener("resize", T.onResize);
  Object.values(T.frameUrls).forEach((u) => URL.revokeObjectURL(u));
  T = null;
}
function loadLib() { T.ctx.api("GET", "/library").then((l) => { if (!T) return; T.lib = l; if (["extras", "bg"].includes(T.panel)) renderPanel(); }).catch(() => {}); }

// ---------- layout ----------
function shell() {
  const { esc } = T.ctx; const s = T.s;
  T.root.innerHTML = `<div class="th">
    <div class="th-head">
      <a class="btn quiet small" href="#/projects/${T.pid}">← project</a>
      <div class="th-title"><h1>Thumbnail studio</h1><span class="muted small">${esc(T.p.title)}</span></div>
      <div class="seg th-size" role="tablist"><button data-size="yt" class="${s.size !== "vertical" ? "on" : ""}">▭ YouTube 16:9</button><button data-size="vertical" class="${s.size === "vertical" ? "on" : ""}">▯ Shorts / Reels 9:16</button></div>
      <span class="grow"></span>
      ${T.canEdit ? `<button class="btn" id="th-var">✨ 3 variants बनाएँ</button><button class="btn primary" id="th-save">✓ Save + चुनें</button>` : ""}
      <button class="btn quiet" id="th-dl" title="अभी का thumbnail (JPG) download करें">⬇</button>
    </div>
    <div class="th-grid">
      <section class="th-stage">
        <div id="th-stage-msg"></div>
        <div class="thx-bar" id="thx-bar"></div>
        <div class="th-canvas thx-stage ${s.size === "vertical" ? "vertical" : ""}" id="thx-stage" tabindex="0" aria-label="thumbnail canvas — क्लिक करके चुनें, खींचकर हिलाएँ">
          <div class="thx-layers" id="thx-layers"></div>
          <div class="thx-guides" id="thx-guides"></div>
          <div class="thx-sel" id="thx-sel" hidden><i class="h nw" data-h="nw"></i><i class="h ne" data-h="ne"></i><i class="h sw" data-h="sw"></i><i class="h se" data-h="se"></i><i class="rot" data-h="rot" title="घुमाएँ"></i></div>
          <div class="thx-hover" id="thx-hover" hidden></div>
          <div class="thx-drop" id="thx-drop" hidden>यहाँ छोड़ें</div>
          <div class="th-busy" id="th-busy" hidden><div class="spin"></div></div>
        </div>
        <div class="small muted thx-hint">क्लिक = चुनें · खींचें = हिलाएँ · कोने = बड़ा/छोटा · ⟳ = घुमाएँ · double-click = text लिखें · ←↑→↓ / Delete / Ctrl+Z · <b>Alt</b> = snapping बंद</div>
        <div id="th-lint" class="th-lint"></div>
        <div class="th-block"><div class="row between"><h3>Frame चुनें</h3><span class="row"><span class="small muted">sharpness · चेहरा · आँखें · रोशनी से चुने गए</span><button class="btn quiet small" id="th-fr-refresh" title="दोबारा ढूँढें">⟳</button></span></div>
          <div class="th-frames" id="th-frames"><div class="small muted">best frames ढूँढे जा रहे हैं…</div></div>
          <div class="th-scrub"><span class="small muted">कोई भी समय</span><input type="range" id="th-t" min="0" max="${Math.max(0.1, T.ov.duration || 0).toFixed(2)}" step="0.05" value="${s.t || 0}"><b class="small" id="th-tl">${fmtT(s.t)}</b></div></div>
        <div class="th-block"><div class="row between"><h3>Saved · A/B candidates</h3><span class="small muted">★ = publish पर यही जाएगा</span></div><div class="th-saved" id="th-saved"></div></div>
      </section>
      <aside class="th-side">
        <nav class="th-tabs">${[["text", "Text"], ["layout", "Layout"], ["bg", "Background"], ["person", "Person"], ["extras", "Elements"], ["layers", "Layers"]].map(([k, l]) => `<button data-panel="${k}" class="${T.panel === k ? "on" : ""}">${l}</button>`).join("")}</nav>
        <div id="th-panel" class="th-panel"></div>
      </aside>
    </div></div>`;
  $$("[data-size]", T.root).forEach((b) => (b.onclick = () => { T.s.size = b.dataset.size; $$("[data-size]", T.root).forEach((x) => x.classList.toggle("on", x === b)); $(".th-canvas", T.root).classList.toggle("vertical", T.s.size === "vertical"); select(null); T.view = null; paint(); renderPanel(); refresh(0); renderSaved(); }));
  $$("[data-panel]", T.root).forEach((b) => (b.onclick = () => openPanel(b.dataset.panel)));
  const tr = $("#th-t", T.root); tr.oninput = () => { $("#th-tl", T.root).textContent = fmtT(+tr.value); }; tr.onchange = () => { T.s.t = +tr.value; markFrames(); refresh(0); };
  $("#th-fr-refresh", T.root).onclick = () => loadFrames(true);
  const sv = $("#th-save", T.root); if (sv) sv.onclick = save;
  const vb = $("#th-var", T.root); if (vb) vb.onclick = variants;
  $("#th-dl", T.root).onclick = download;
  bindStage();
  renderBar(); renderPanel(); renderSaved();
}
function openPanel(k) {
  T.panel = k; try { localStorage.setItem("vividora_thpanel", k); } catch {}
  $$("[data-panel]", T.root).forEach((x) => x.classList.toggle("on", x.dataset.panel === k)); renderPanel();
}

function field(label, html, cls = "") { return `<div class="th-f ${cls}"><label>${label}</label>${html}</div>`; }
function swatches(key, cur, opts = {}) {
  return `<div class="th-sw">${opts.none ? `<button class="none ${!cur ? "on" : ""}" data-sw="${key}" data-c="" title="कोई नहीं">⌀</button>` : ""}${COLORS.map((c) => `<button style="--c:${c}" data-sw="${key}" data-c="${c}" class="${(cur || "").toUpperCase() === c ? "on" : ""}" title="${c}"></button>`).join("")}<input type="color" data-k="${key}" value="${cur && /^#[0-9a-f]{6}$/i.test(cur) ? cur : "#ffffff"}"></div>`;
}
function range(key, label, min, max, step, val, fmt = (v) => v) { return field(`${label} <b>${fmt(val)}</b>`, `<input type="range" data-k="${key}" data-fmt="${key}" min="${min}" max="${max}" step="${step}" value="${val}" ${T.canEdit ? "" : "disabled"}>`); }
function selectBox(key, label, entries, cur, def) { return field(label, `<select data-k="${key}" ${T.canEdit ? "" : "disabled"}>${def != null ? `<option value="">${def}</option>` : ""}${entries.map(([k, v]) => `<option value="${k}" ${String(cur ?? "") === String(k) ? "selected" : ""}>${v}</option>`).join("")}</select>`); }
function tplOf(id) { return TPLS.templates.find((t) => t.id === id) || TPLS.templates[0]; }
function tplText(tp) { const v = T.s.size === "vertical"; return { ...(tp.text || {}), ...((v && tp.vertical?.text) || {}) }; }
function fmtFor(k, v) { v = +v; return k === "bg.dim" || k === "vignette" ? Math.round(v * 100) + "%" : k === "bg.angle" || k === "skew" ? v + "°" : /scale|adj/.test(k) ? v.toFixed(2) + "×" : /_w$/.test(k) && !k.startsWith("person") ? Math.round(v * 100) + "%" : k === "spacing" ? v.toFixed(2) + "em" : k === "line_h" ? v.toFixed(2) + "×" : v; }

function renderPanel() {
  const { esc } = T.ctx; const s = T.s; const el = $("#th-panel", T.root); if (!el) return;
  const tp = tplOf(s.template); const tt = tplText(tp); const dis = T.canEdit ? "" : "disabled";
  const sty = s.style || tt.style || "outline"; const sd = { ...(TPLS.style_defaults?.[sty] || {}), ...Object.fromEntries(TEXT_STYLE_KEYS.filter((k) => tt[k] != null).map((k) => [k, tt[k]])) };
  const eff = (k, d) => (s[k] !== undefined && s[k] !== "" ? s[k] : sd[k] !== undefined ? sd[k] : d);
  let html = "";
  if (T.panel === "text") {
    html = `${field("Thumbnail text <span class='muted'>(2–5 शब्द · <b>*शब्द*</b> = highlight · <b>_शब्द_</b> = दूसरा रंग · Enter = नई लाइन · emoji चलेंगे)</span>", `<textarea id="th-text" rows="3" placeholder="3 *बड़ी* गलतियाँ" ${dis}>${esc(s.text || "")}</textarea>`)}
      <div class="row between"><span class="small muted">AI / title से सुझाव · canvas पर double-click करके भी लिखें</span><button class="btn small" id="th-sugg">✨ सुझाव</button></div>
      <div class="th-chips" id="th-chips">${(T.sugg?.options || []).map((o, i) => `<button class="chip" data-sg="${i}">${esc(o).replace(/\*([^*]+)\*/g, "<b>$1</b>").replace(/\n/g, " / ")}</button>`).join("") || `<span class="small muted">“सुझाव” दबाएँ</span>`}</div>
      <div class="th-row2">${field("Font", `<select data-k="font" ${dis}><option value="">template (${esc(tt.font || "")})</option>${TPLS.fonts.map((f) => `<option ${s.font === f ? "selected" : ""} style="font-family:${FONT_CSS[f] || f}">${f}</option>`).join("")}</select>`)}
        ${field("Style preset", `<select data-k="style" ${dis}><option value="">template (${esc(TPLS.styles[tt.style] || "")})</option>${Object.entries(TPLS.styles).map(([k, v]) => `<option value="${k}" ${s.style === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>`)}</div>
      <div class="thx-align">${[["left", "⯇ बाएँ"], ["center", "≡ बीच"], ["right", "दाएँ ⯈"]].map(([k, l]) => `<button class="btn small ${eff("align", tt.align || "left") === k ? "on" : ""}" data-align="${k}" ${dis}>${l}</button>`).join("")}</div>
      ${range("text_scale", "आकार", 0.5, 1.5, 0.05, s.text_scale || 1, (v) => (+v).toFixed(2) + "×")}
      ${field("अक्षर का रंग", swatches("color", s.color || ""))}
      <label class="chk small"><input type="checkbox" id="thx-grad" ${eff("fill2") ? "checked" : ""} ${dis}> Gradient भराव (ऊपर → नीचे)</label>${eff("fill2") ? swatches("fill2", eff("fill2")) : ""}
      ${field("Highlight रंग (*शब्द*)", swatches("hl", s.hl || ""))}
      <label class="chk small"><input type="checkbox" data-k="hl_box" ${eff("hl_box") ? "checked" : ""} ${dis}> highlight शब्द के पीछे box</label>
      ${field("दूसरा highlight (_शब्द_)", swatches("hl2", s.hl2 || ""))}
      <h4>Outline · shadow</h4>
      ${range("stroke_w", "Outline मोटाई", 0, 0.2, 0.005, eff("stroke_w", 0), (v) => Math.round(v * 100) + "%")}
      ${field("Outline रंग", swatches("stroke", s.stroke || ""))}
      ${range("stroke2_w", "दूसरी (बाहरी) outline", 0, 0.15, 0.005, eff("stroke2_w", 0), (v) => Math.round(v * 100) + "%")}
      ${eff("stroke2_w", 0) > 0 ? field("बाहरी outline रंग", swatches("stroke2", eff("stroke2", ""))) : ""}
      ${selectBox("shadow", "Shadow / effect", Object.entries(TPLS.shadows || {}), s.shadow, `style जैसा (${esc((TPLS.shadows || {})[sd.shadow] || sd.shadow || "")})`)}
      ${["soft", "hard", "long"].includes(eff("shadow")) ? field("Shadow रंग", swatches("shadow_color", s.shadow_color || "")) : ""}
      ${eff("shadow") === "glow" ? field("Glow रंग", swatches("glow", s.glow || "")) : ""}
      <h4>Spacing · ribbon</h4>
      ${range("spacing", "अक्षरों में दूरी", -0.05, 0.3, 0.01, eff("spacing", 0), (v) => (+v).toFixed(2) + "em")}
      ${range("line_h", "लाइनों में दूरी", 0.6, 1.8, 0.05, eff("line_h", 1), (v) => (+v).toFixed(2) + "×")}
      ${range("skew", "तिरछा (italic)", -20, 20, 1, eff("skew", 0), (v) => v + "°")}
      <label class="chk small"><input type="checkbox" id="thx-banner" ${eff("banner") ? "checked" : ""} ${dis}> पीछे ribbon / banner</label>${eff("banner") ? swatches("banner", eff("banner") === "accent" ? (s.accent || tp.accent) : eff("banner")) : ""}
      ${field("Accent (तीर, badge, glow, border)", swatches("accent", s.accent || tp.accent))}
      <label class="chk small"><input type="checkbox" data-k="upper" ${s.upper ? "checked" : ""} ${dis}> English CAPITAL letters</label>
      ${["color", "hl", "accent", "font", "style", ...TEXT_STYLE_KEYS].some((k) => s[k] !== undefined && s[k] !== "") ? `<button class="btn quiet small" id="th-reset-text">↺ template का text style</button>` : ""}`;
  } else if (T.panel === "layout") {
    html = `<p class="small muted">Layout चुनें — हर चीज़ बाद में canvas पर खींचकर बदल सकते हैं। हर layout 16:9 और 9:16 दोनों में बनता है।</p>
      <div class="th-tpls">${TPLS.templates.map((t) => tplCard(t)).join("")}</div>
      <label class="chk small" style="margin-top:.6rem"><input type="checkbox" data-k="flip" ${s.flip ? "checked" : ""} ${dis}> ⇆ उल्टा करें (चेहरा दूसरी तरफ़)</label>
      ${tp.labels?.length ? field("Labels", `<div class="th-row2">${tp.labels.map((l, i) => `<input data-label="${i}" value="${esc((s.labels || [])[i] || l.text)}" ${dis}>`).join("")}</div>`) : ""}
      ${tp.bg?.type === "split" ? field("दूसरा frame (पहले / before)", `<div class="th-scrub"><input type="range" id="th-t2" min="0" max="${Math.max(0.1, T.ov.duration || 0).toFixed(2)}" step="0.05" value="${s.t2 ?? (T.frames[1]?.t || 0)}"><b class="small" id="th-t2l">${fmtT(s.t2 ?? (T.frames[1]?.t || 0))}</b></div>`) : ""}
      ${hasLayout() ? `<button class="btn small" id="thx-reset-all">↺ सारी जगहें layout जैसी करें</button>` : ""}`;
  } else if (T.panel === "bg") {
    const bg = s.bg || {}; const imgs = T.lib.filter((x) => ["image", "frame", "broll"].includes(x.kind) && (x.mime || "").startsWith("image/"));
    html = `${field("Background", `<select id="th-bgtype" ${dis}>${Object.entries(TPLS.bg_types).map(([k, v]) => `<option value="${k}" ${(bg.type || "") === k ? "selected" : ""}>${esc(v)}${k === "" ? ` (${esc(tp.bg?.type || "")})` : ""}</option>`).join("")}</select>`)}
      ${["solid", "gradient"].includes(bg.type) ? field("रंग", swatches("bg.color", bg.color || "#111827")) : ""}
      ${bg.type === "gradient" ? field("दूसरा रंग", swatches("bg.color2", bg.color2 || "#2C5364")) + range("bg.angle", "कोण", 0, 180, 5, bg.angle ?? 90, (v) => v + "°") : ""}
      ${bg.type === "blur" ? range("bg.blur", "धुँधलापन", 4, 60, 2, bg.blur ?? 22) + range("bg.dim", "अंधेरा", 0, 0.85, 0.05, bg.dim ?? 0.4, (v) => Math.round(v * 100) + "%") : ""}
      ${bg.type === "image" ? `<div class="th-libgrid">${imgs.slice(0, 60).map((x) => `<button class="${bg.image_id === x.id ? "on" : ""}" data-bgimg="${x.id}" title="${esc(x.name)}"><img src="${x.url}" loading="lazy" alt="" draggable="false"></button>`).join("") || `<p class="small muted">Library में image upload करें।</p>`}</div>` : ""}
      <div class="row"><label class="btn small">⬆ अपनी image<input type="file" accept="image/png,image/jpeg,image/webp" id="thx-bgup" hidden></label><button class="btn small" id="thx-aibg">✨ AI background prompt</button></div>
      <div id="thx-aiprompt"></div>
      ${selectBox("overlay", "रोशनी / texture", Object.entries(TPLS.overlays || {}).filter(([k]) => k), s.overlay ?? "", `template जैसा${tp.overlay ? ` (${esc(TPLS.overlays?.[tp.overlay] || tp.overlay)})` : ""}`)}
      ${selectBox("grade", "Colour grade", Object.entries(TPLS.grades || {}), s.grade, `template जैसा${tp.grade ? ` (${esc(TPLS.grades?.[tp.grade] || tp.grade)})` : ""}`)}
      ${range("vignette", "किनारों पर अंधेरा (vignette)", 0, 1, 0.05, s.vignette ?? tp.vignette ?? 0, (v) => Math.round(v * 100) + "%")}
      <p class="small muted">cutout बंद हो तो solid / gradient की जगह पूरा frame लगता है, ताकि चेहरा दिखे।</p>`;
  } else if (T.panel === "person") {
    const pst = s.person_stroke !== undefined ? s.person_stroke : (tp.person?.stroke || ""); const pgl = s.person_glow !== undefined ? s.person_glow : (tp.person?.glow || "");
    const adj = { ...(tp.person?.adj || {}), ...(s.person_adj || {}) };
    html = tp.person === null ? `<p class="muted small">इस layout में अलग person नहीं है (पूरे frames)।</p>` : `
      <label class="chk"><input type="checkbox" data-k="cutout" ${s.cutout !== false ? "checked" : ""} ${dis}> <b>Person cutout</b> — background हटाकर सिर्फ़ आप</label>
      <p class="small muted">${T.ov.has_alpha ? "इस project का cutout (alpha) तैयार है ✓" : "cutout इसी frame पर RVM से बनता है (पहली बार कुछ सेकंड)। Editor → Body effects से पूरा cutout पहले बना लें तो और साफ़।"} Canvas पर चेहरे को खींचें / कोने से बड़ा करें।</p>
      ${range("person_scale", "चेहरे का आकार", 0.6, 1.6, 0.05, s.person_scale || 1, (v) => (+v).toFixed(2) + "×")}
      <label class="chk small"><input type="checkbox" id="th-pst" ${pst ? "checked" : ""} ${dis}> Outline (sticker look)</label>${pst ? swatches("person_stroke", pst === "accent" ? (s.accent || tp.accent) : pst) + range("person_stroke_w", "outline मोटाई", 2, 40, 1, s.person_stroke_w ?? tp.person?.stroke_w ?? 16, (v) => v + "px") : ""}
      <label class="chk small"><input type="checkbox" id="th-pgl" ${pgl ? "checked" : ""} ${dis}> Glow</label>${pgl ? swatches("person_glow", pgl === "accent" ? (s.accent || tp.accent) : pgl) + range("person_glow_w", "glow फैलाव", 6, 70, 2, s.person_glow_w ?? tp.person?.glow_w ?? 26, (v) => v + "px") : ""}
      <label class="chk small"><input type="checkbox" data-k="person_shadow" ${(s.person_shadow ?? tp.person?.shadow) ? "checked" : ""} ${dis}> Drop shadow</label>
      <h4>चेहरा / subject सुधारें</h4>
      ${[["bright", "रोशनी"], ["contrast", "contrast"], ["sat", "रंग (saturation)"], ["sharp", "sharpness"]].map(([k, l]) => range(`person_adj.${k}`, l, k === "sharp" ? 0.5 : 0.6, k === "sharp" ? 2.5 : 1.6, 0.02, adj[k] ?? 1, (v) => (+v).toFixed(2) + "×")).join("")}
      <div class="row"><button class="btn small" data-adjp="pop">✨ Pop</button><button class="btn small" data-adjp="bright">☀ चेहरा चमकाएँ</button><button class="btn small quiet" data-adjp="reset">↺ reset</button></div>`;
  } else if (T.panel === "layers") {
    html = layersPanel();
  } else {
    html = elementsPanel();
  }
  el.innerHTML = html;
  bindPanel(el);
}

function elementsPanel() {
  const { esc } = T.ctx; const s = T.s; const dis = T.canEdit ? "" : "disabled";
  const stk = T.lib.filter((x) => x.kind === "sticker" && /(shape|emoji|arrow|social)/.test(x.tags || ""));
  const mine = T.lib.filter((x) => ["sticker", "image", "logo"].includes(x.kind) && !/(shape|emoji|arrow|social)/.test(x.tags || "")).slice(0, 30);
  const st = selSticker();
  const selHtml = st ? `<div class="thx-selprops"><b class="small">चुना हुआ: ${esc(selLayer()?.name || "")}</b>
      ${st.shape || st.txt != null ? field("रंग", swatches("@color", st.color || "")) : ""}
      ${st.txt != null && !isEmoji(st.txt) ? field("पीछे पट्टी", swatches("@bg", st.bg || "", { none: true })) + field("Font", `<select id="thx-stfont">${TPLS.fonts.map((f) => `<option ${(st.font || "Mukta") === f ? "selected" : ""}>${f}</option>`).join("")}</select>`) : ""}
      ${["rect", "burst", "circle"].includes(st.shape) && st.shape !== "circle" ? `<label class="chk small"><input type="checkbox" id="thx-stfill" ${st.fill ? "checked" : ""}> भरा हुआ (fill)</label>` : ""}</div>` : "";
  return `${selHtml}
    <p class="small muted">खींचकर canvas पर छोड़ें (या क्लिक = बीच में)। अपनी PNG / JPG फ़ाइल सीधे canvas पर भी छोड़ सकते हैं।</p>
    <h4>Text badges</h4><div class="thx-items">${BADGES.map((b, i) => `<button class="thx-badge" data-drag="badge:${i}" style="--bg:${b.bg || "transparent"};--fg:${b.color};font-family:${FONT_CSS[b.font || "Mukta"]}">${esc(b.txt)}</button>`).join("")}</div>
    ${TPLS.emoji ? `<h4>Emoji</h4><div class="thx-items emoji">${EMOJI.map((e) => `<button data-drag="emoji:${e}">${e}</button>`).join("")}</div>` : ""}
    <h4>Shapes</h4><div class="thx-items">${Object.entries(TPLS.shapes).map(([k, v]) => `<button class="btn small" data-drag="shape:${k}">${esc(v)}</button>`).join("")}</div>
    <h4>Stickers <span class="small muted">(library)</span></h4>
    <div class="th-libgrid small">${stk.slice(0, 80).map((x) => `<button data-drag="lib:${x.id}" title="${esc(x.name)}"><img src="${x.url}" loading="lazy" alt="" draggable="false"></button>`).join("") || `<span class="small muted">library लोड हो रही है…</span>`}</div>
    ${mine.length ? `<h4>आपकी images</h4><div class="th-libgrid small">${mine.map((x) => `<button data-drag="lib:${x.id}" title="${esc(x.name)}"><img src="${x.url}" loading="lazy" alt="" draggable="false"></button>`).join("")}</div>` : ""}
    <label class="btn small">⬆ image / PNG जोड़ें<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" id="thx-up" multiple hidden></label>
    <h4>Number badge</h4>${field("", `<input data-k="badge" value="${esc(s.badge || "")}" placeholder="जैसे 3 (खाली = text का पहला नंबर)" ${dis}>`)}
    <p class="small muted">Badge “Number badge” / “Challenge” layout में दिखता है।</p>
    <h4>Brand logo</h4><label class="chk small"><input type="checkbox" data-k="logo" ${s.logo ? "checked" : ""} ${dis} ${T.ov.brand_logo ? "" : "disabled"}> logo ${T.ov.brand_logo ? "(canvas पर खींचकर जगह बदलें)" : "<span class='muted'>(Channels & Brand में logo चुनें)</span>"}</label>
    ${s.logo ? field("शुरुआती कोना", `<select data-k="logo_pos">${[["tr", "ऊपर दाएँ"], ["tl", "ऊपर बाएँ"], ["br", "नीचे दाएँ"], ["bl", "नीचे बाएँ"]].map(([k, l]) => `<option value="${k}" ${(s.logo_pos || "tr") === k ? "selected" : ""}>${l}</option>`).join("")}</select>`) : ""}`;
}

function layersPanel() {
  const { esc } = T.ctx; const v = T.view;
  if (!v) return `<p class="small muted">preview बन रहा है…</p>`;
  const rows = [...v.layers].reverse().filter((l) => l.id !== "border");
  const icon = { text: "T", textsticker: "T", person: "👤", sticker: "★", shape: "➜", label: "🏷", badge: "#", logo: "©", fx: "◐", emoji: "☺" };
  return `<p class="small muted">ऊपर वाली layer सबसे आगे। क्लिक = चुनें · ↑↓ = आगे / पीछे · 👁 = छुपाएँ।</p>
    <div class="thx-layerlist">${rows.map((l) => `<div class="thx-li ${T.sel === l.id ? "on" : ""} ${l.locked ? "locked" : ""}" data-li="${esc(l.id)}">
      <span class="ico">${icon[l.kind] || "▢"}</span><span class="nm">${esc(l.name)}</span>
      ${l.locked ? `<span class="small muted">effect</span>` : `<button class="btn quiet small" data-lz="${esc(l.id)}:1" title="आगे">↑</button><button class="btn quiet small" data-lz="${esc(l.id)}:-1" title="पीछे">↓</button>${l.uid ? "" : `<button class="btn quiet small" data-lhide="${esc(l.id)}" title="छुपाएँ">👁</button>`}`}</div>`).join("")}
      ${(v.hidden || []).map((h) => `<div class="thx-li hidden"><span class="ico">⦸</span><span class="nm">${esc(h.name)}</span><button class="btn quiet small" data-lshow="${esc(h.id)}">दिखाएँ</button></div>`).join("")}
      <div class="thx-li locked"><span class="ico">▦</span><span class="nm">Background</span><button class="btn quiet small" data-goto="bg">बदलें</button></div></div>`;
}

function tplCard(t) {
  const v = T.s.size === "vertical"; const tt = v ? { ...t, ...(t.vertical || {}), person: t.person ? { ...t.person, ...(t.vertical?.person || {}) } : null, text: { ...t.text, ...(t.vertical?.text || {}) } } : t;
  const acc = t.accent || "#FFD400"; const col = (c) => (c === "accent" ? acc : c);
  const bg = t.bg || {}; const fr = T.frameUrls[(T.frames[0] || {}).t];
  const bgCss = bg.type === "gradient" ? `linear-gradient(${(bg.angle ?? 90) + 90}deg, ${bg.color}, ${bg.color2})` : bg.type === "solid" ? bg.color : fr ? `center/cover url(${fr})` : "#3b4a5e";
  const [x0, y0, x1, y1] = tt.text?.box || [0.05, 0.1, 0.5, 0.9];
  const p = tt.person;
  return `<button class="th-tpl ${T.s.template === t.id ? "on" : ""}" data-tpl="${t.id}" title="${T.ctx.esc(t.desc || "")}">
    <div class="th-tplv ${v ? "v" : ""}" style="background:${bgCss}">${bg.type === "blur" ? `<i class="blurl"></i>` : ""}${bg.type === "split" ? `<i class="split" style="--a:${acc}"></i>` : ""}
      ${t.overlay === "rays" ? `<i class="rays" style="--a:${acc}"></i>` : t.overlay === "spotlight" ? `<i class="spot"></i>` : ""}
      ${p ? `<i class="face" style="left:${p.x * 100}%;top:${p.face_y * 100}%;width:${p.face_h * (v ? 56 : 100) * 0.62}%;${p.stroke ? `box-shadow:0 0 0 2px ${col(p.stroke)}${p.glow ? `,0 0 10px 3px ${col(p.glow)}` : ""}` : p.glow ? `box-shadow:0 0 10px 3px ${col(p.glow)}` : ""}"></i>` : ""}
      <i class="tbox ${t.text?.style || ""}" style="left:${x0 * 100}%;top:${y0 * 100}%;width:${(x1 - x0) * 100}%;height:${(y1 - y0) * 100}%;--tc:${col(t.text?.color || "#fff")};--hc:${col(t.text?.hl || acc)};--bc:${col(t.text?.box_color || t.text?.banner || acc)};align-items:${{ left: "flex-start", right: "flex-end", center: "center" }[t.text?.align || "left"]};justify-content:center;${t.text_behind ? "z-index:0" : ""}"><b></b><b class="h"></b></i>
      ${t.badge ? `<i class="badge" style="left:${(tt.badge || t.badge).x * 100}%;top:${(tt.badge || t.badge).y * 100}%;background:${acc}"></i>` : ""}
      ${(t.shapes || []).length ? `<i class="arrow" style="color:${col(t.shapes[0].color || "accent")}">➜</i>` : ""}
      ${t.border ? `<i class="border" style="border-color:${col(t.border.color)}"></i>` : ""}</div>
    <span>${T.ctx.esc(t.label)}</span></button>`;
}

function setPath(obj, path, val) { const ks = path.split("."); let o = obj; for (const k of ks.slice(0, -1)) o = o[k] = o[k] && typeof o[k] === "object" ? o[k] : {}; o[ks.at(-1)] = val; }

function bindPanel(el) {
  const s = T.s;
  $$("[data-k]", el).forEach((i) => {
    const ev = i.type === "range" ? "input" : i.tagName === "TEXTAREA" || i.type === "text" || (i.tagName === "INPUT" && !i.type.match(/checkbox|color/)) ? "input" : "change";
    i.addEventListener(ev, () => {
      const k = i.dataset.k; let v = i.type === "checkbox" ? i.checked : i.type === "range" ? +i.value : i.value;
      if (k.startsWith("@")) { const st = selSticker(); if (st) { st[k.slice(1)] = v; refresh(); } return; }
      if (k === "flip") mirrorPlacement();
      setPath(s, k, v);
      if (i.type === "range") { const b = i.closest(".th-f")?.querySelector("label b"); if (b) b.textContent = fmtFor(k, v); }
      if (i.type === "color") { i.closest(".th-sw")?.querySelectorAll("button").forEach((b) => b.classList.remove("on")); }
      if (["logo", "flip", "cutout", "shadow", "stroke2_w", "style"].includes(k) || (k === "stroke2_w")) renderPanel();
      refresh();
    });
  });
  $$("[data-sw]", el).forEach((b) => (b.onclick = () => {
    const k = b.dataset.sw; const c = b.dataset.c;
    if (k.startsWith("@")) { const st = selSticker(); if (st) { st[k.slice(1)] = c; renderPanel(); refresh(0); } return; }
    setPath(s, k, c); b.parentElement.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); const ci = b.parentElement.querySelector("input[type=color]"); if (ci && c) ci.value = c; refresh();
  }));
  const tx = $("#th-text", el); if (tx) tx.oninput = () => { s.text = tx.value.split("\n").slice(0, 3).join("\n"); refresh(); };
  const sg = $("#th-sugg", el); if (sg) sg.onclick = () => suggest(false);
  $$("[data-sg]", el).forEach((b) => (b.onclick = () => { s.text = T.sugg.options[+b.dataset.sg]; renderPanel(); refresh(0); }));
  $$("[data-align]", el).forEach((b) => (b.onclick = () => { s.align = b.dataset.align; renderPanel(); refresh(0); }));
  const gr = $("#thx-grad", el); if (gr) gr.onchange = () => { s.fill2 = gr.checked ? "#FFD400" : ""; renderPanel(); refresh(0); };
  const bn = $("#thx-banner", el); if (bn) bn.onchange = () => { s.banner = bn.checked ? (s.accent || tplOf(s.template).accent || "#E50914") : ""; renderPanel(); refresh(0); };
  const rt = $("#th-reset-text", el); if (rt) rt.onclick = () => { for (const k of ["color", "hl", "accent", "font", "style", "text_scale", ...TEXT_STYLE_KEYS]) delete s[k]; renderPanel(); refresh(0); };
  $$("[data-tpl]", el).forEach((b) => (b.onclick = () => {
    s.template = b.dataset.tpl; for (const k of ["labels", "person_stroke", "person_glow", "accent", "layout", "overlay", "vignette", "grade", "style", ...TEXT_STYLE_KEYS]) delete s[k];
    select(null); renderPanel(); refresh(0);
  }));
  $$("[data-label]", el).forEach((i) => (i.oninput = () => { const tp = tplOf(s.template); s.labels = (tp.labels || []).map((l, j) => (j === +i.dataset.label ? i.value : (s.labels || [])[j] || l.text)); refresh(); }));
  const t2 = $("#th-t2", el); if (t2) { t2.oninput = () => { $("#th-t2l", el).textContent = fmtT(+t2.value); }; t2.onchange = () => { s.t2 = +t2.value; refresh(0); }; }
  const bt = $("#th-bgtype", el); if (bt) bt.onchange = () => { s.bg = bt.value ? { ...(s.bg || {}), type: bt.value } : {}; renderPanel(); refresh(0); };
  $$("[data-bgimg]", el).forEach((b) => (b.onclick = () => { s.bg = { ...(s.bg || {}), type: "image", image_id: b.dataset.bgimg }; renderPanel(); refresh(0); }));
  const bu = $("#thx-bgup", el); if (bu) bu.onchange = async () => { const f = bu.files[0]; if (!f) return; try { const it = await uploadLib(f, "image"); s.bg = { ...(s.bg || {}), type: "image", image_id: it.id }; loadLib(); renderPanel(); refresh(0); } catch (e) { T.ctx.toast(e.message); } };
  const ai = $("#thx-aibg", el); if (ai) ai.onclick = () => aiPrompt();
  const pst = $("#th-pst", el); if (pst) pst.onchange = () => { s.person_stroke = pst.checked ? "#FFFFFF" : ""; renderPanel(); refresh(0); };
  const pgl = $("#th-pgl", el); if (pgl) pgl.onchange = () => { s.person_glow = pgl.checked ? (s.accent || tplOf(s.template).accent) : ""; renderPanel(); refresh(0); };
  $$("[data-adjp]", el).forEach((b) => (b.onclick = () => { const k = b.dataset.adjp; s.person_adj = k === "reset" ? undefined : k === "pop" ? { sat: 1.18, contrast: 1.12, sharp: 1.5, bright: 1.03 } : { ...(s.person_adj || {}), bright: 1.14, contrast: 1.05 }; if (!s.person_adj) delete s.person_adj; renderPanel(); refresh(0); }));
  const ra = $("#thx-reset-all", el); if (ra) ra.onclick = () => { if (s.layout) delete s.layout[sizeKey()]; renderPanel(); refresh(0); };
  // elements: pointer-drag onto the canvas (mouse + touch), click = add in the middle
  $$("[data-drag]", el).forEach((b) => bindDragSource(b));
  const up = $("#thx-up", el); if (up) up.onchange = async () => { for (const f of up.files) await addFile(f, 0.5, 0.5); };
  const sf = $("#thx-stfont", el); if (sf) sf.onchange = () => { const st = selSticker(); if (st) { st.font = sf.value; refresh(0); } };
  const sfl = $("#thx-stfill", el); if (sfl) sfl.onchange = () => { const st = selSticker(); if (st) { st.fill = sfl.checked; refresh(0); } };
  // layers panel
  $$("[data-li]", el).forEach((r) => (r.onclick = (e) => { if (e.target.closest("button")) return; const l = layerById(r.dataset.li); if (l && !l.locked) select(l.id); }));
  $$("[data-lz]", el).forEach((b) => (b.onclick = () => { const [id, d] = b.dataset.lz.split(/:(?=-?1$)/); zorder(id, +d); }));
  $$("[data-lhide]", el).forEach((b) => (b.onclick = () => { setOv(b.dataset.lhide, { hidden: true }); if (T.sel === b.dataset.lhide) select(null); refresh(0); }));
  $$("[data-lshow]", el).forEach((b) => (b.onclick = () => { const o = ovOf(b.dataset.lshow); delete o.hidden; refresh(0); }));
  $$("[data-goto]", el).forEach((b) => (b.onclick = () => openPanel(b.dataset.goto)));
}

function aiPrompt() {
  const title = T.p.title || ""; const v = T.s.size === "vertical";
  const p = `YouTube thumbnail background, ${v ? "9:16 vertical" : "16:9"}, cinematic, dramatic lighting, rich colours, shallow depth of field, empty space on the ${(tplOf(T.s.template).person?.x ?? 0.7) > 0.5 ? "left" : "right"} side for big text, no text, no letters, no people, no watermark. Theme: ${title}`;
  const el = $("#thx-aiprompt", T.root); if (!el) return;
  el.innerHTML = `<div class="thx-ai"><p class="small muted">ये prompt Grok / ChatGPT / Gemini में डालें, बनी image ऊपर “⬆ अपनी image” से जोड़ें:</p><textarea rows="4" readonly>${T.ctx.esc(p)}</textarea><button class="btn small" id="thx-aicopy">📋 copy</button></div>`;
  $("#thx-aicopy", el).onclick = async () => { try { await navigator.clipboard.writeText(p); T.ctx.toast("prompt copy हुआ"); } catch { $("textarea", el).select(); } };
}

// ---------- frames ----------
async function loadFrames(refreshIt) {
  const box = $("#th-frames", T.root); if (!box) return;
  if (refreshIt || !T.frames.length) {
    box.innerHTML = `<div class="small muted"><span class="spin sm"></span> best frames ढूँढे जा रहे हैं (~20 frames जाँच रहे)…</div>`;
    try { const r = await T.ctx.api("GET", `/projects/${T.pid}/thumbnails/frames${refreshIt ? "?refresh=1" : ""}`); if (!T) return; T.frames = r.frames || []; }
    catch (e) { box.innerHTML = `<div class="small muted">${T.ctx.esc(e.message)}</div>`; return; }
    if (!T.s.t && T.frames[0]) { T.s.t = T.frames[0].t; refresh(0); }
  }
  box.innerHTML = T.frames.map((f, i) => `<button class="th-fr" data-t="${f.t}" title="score ${f.score}${f.face ? " · चेहरा ✓" : ""}${f.eyes >= 2 ? " · आँखें खुली" : ""}"><img alt="">${i === 0 ? `<em>best</em>` : ""}<span>${fmtT(f.t)}${f.face ? " · 🙂" : ""}</span></button>`).join("");
  $$(".th-fr", box).forEach((b) => (b.onclick = () => { T.s.t = +b.dataset.t; const r = $("#th-t", T.root); r.value = T.s.t; $("#th-tl", T.root).textContent = fmtT(T.s.t); markFrames(); refresh(0); }));
  markFrames();
  for (const f of T.frames) {
    if (!T) return;
    if (!T.frameUrls[f.t]) { try { const { blob } = await authBlob(`/projects/${T.pid}/thumbnails/frame?t=${f.t}&w=320`); if (!T) return; T.frameUrls[f.t] = URL.createObjectURL(blob); } catch { continue; } }
    const img = $(`.th-fr[data-t="${f.t}"] img`, T.root); if (img) img.src = T.frameUrls[f.t];
  }
  if (T && T.panel === "layout") renderPanel();
}
function markFrames() { $$(".th-fr", T.root).forEach((b) => b.classList.toggle("on", Math.abs(+b.dataset.t - (T.s.t || 0)) < 0.03)); }

// ---------- history ----------
function record() {
  const j = JSON.stringify(T.s); if (j === T.hist[T.hi]) return;
  T.hist = T.hist.slice(0, T.hi + 1); T.hist.push(j); if (T.hist.length > 120) T.hist.shift(); T.hi = T.hist.length - 1; renderBar();
}
function undo(d) {
  record();
  const n = T.hi + d; if (n < 0 || n >= T.hist.length) return;
  T.hi = n; T.s = JSON.parse(T.hist[n]); T.pend = null;
  const r = $("#th-t", T.root); if (r) { r.value = T.s.t || 0; $("#th-tl", T.root).textContent = fmtT(T.s.t); }
  $$("[data-size]", T.root).forEach((x) => x.classList.toggle("on", x.dataset.size === (T.s.size || "yt"))); $(".th-canvas", T.root).classList.toggle("vertical", T.s.size === "vertical");
  renderPanel(); renderBar(); refresh(0);
}

// ---------- preview (layered) ----------
function refresh(delay = 380) {
  if (!T || !T.ov?.has_video) return;
  clearTimeout(T.timer);
  T.timer = setTimeout(async () => {
    if (!T) return;
    record();
    T.abort?.abort(); const ac = (T.abort = new AbortController());
    $("#th-busy", T.root).hidden = false;
    const sent = JSON.stringify(T.s);
    try {
      let r = await postJSON(`/projects/${T.pid}/thumbnails/layers`, { settings: T.s, have: Object.keys(T.sprites) }, ac.signal);
      if (!T || ac !== T.abort) return;
      if (JSON.stringify(T.s) !== sent) return; // changed meanwhile — the next (already scheduled) render wins
      if ([r.base, ...r.layers].some((l) => !l.src && !T.sprites[l.hash])) r = await postJSON(`/projects/${T.pid}/thumbnails/layers`, { settings: T.s, have: [] }, ac.signal);
      if (!T || ac !== T.abort) return;
      const keep = {};
      for (const l of [r.base, ...r.layers]) { keep[l.hash] = T.sprites[l.hash] || { src: l.src }; if (l.src) keep[l.hash] = { src: l.src }; }
      T.sprites = keep;
      T.view = r; T.pend = null;
      T.lint = r.warnings || []; T.info = r.info || {};
      if (!T.s.t && T.info.t) T.s.t = T.info.t;
      if (T.sel && T.sel !== "bg" && !layerById(T.sel)) T.sel = null;
      paint(); renderLint(); renderBar();
      if (T.panel === "layers") renderPanel();
    } catch (e) { if (e.name !== "AbortError" && T) { $("#th-lint", T.root).innerHTML = `<div class="note err">${T.ctx.esc(e.message)}</div>`; } }
    if (T && ac === T.abort) $("#th-busy", T.root).hidden = true;
  }, delay);
}
function pct(v) { return (v * 100).toFixed(4) + "%"; }
function paint() {
  const box = $("#thx-layers", T.root); if (!box) return;
  const v = T.view;
  if (!v) { box.innerHTML = ""; drawSel(); return; }
  box.innerHTML = `<img class="thx-base" src="${T.sprites[v.base.hash]?.src || ""}" alt="" draggable="false">` +
    v.layers.map((l) => `<img class="thx-spr ${l.locked ? "locked" : ""}" data-id="${T.ctx.esc(l.id)}" src="${T.sprites[l.hash]?.src || ""}" alt="" draggable="false" style="left:${pct(l.box[0])};top:${pct(l.box[1])};width:${pct(l.box[2])};height:${pct(l.box[3])}">`).join("");
  if (T.editing) { const sp = sprEl(T.editing.id); if (sp) sp.style.visibility = "hidden"; }
  drawSel();
}
function renderLint() {
  const el = $("#th-lint", T.root); if (!el) return; const { esc } = T.ctx; const i = T.info || {};
  const ok = !T.lint.some((w) => w.level === "warn");
  el.innerHTML = `<div class="th-lintrow ${ok ? "ok" : ""}"><b>${ok ? "✓ अच्छा दिख रहा है" : "⚠ सुधार"}</b>
    <span class="small muted">${i.words ? `${i.words} शब्द · ` : ""}${i.font_px ? `अक्षर ${i.font_px}px · ` : ""}${i.contrast ? `contrast ${i.contrast}:1 · ` : ""}${i.cutout ? "cutout ✓" : "पूरा frame"}</span></div>
    ${T.lint.map((w) => `<div class="th-warn ${w.level}">${w.level === "warn" ? "⚠" : "ℹ"} ${esc(w.msg)}</div>`).join("")}`;
}

// ---------- layer model helpers ----------
const sizeKey = () => (T.s.size === "vertical" ? "vertical" : "yt");
function layerById(id) { return T.view?.layers.find((l) => l.id === id) || null; }
function selLayer() { return T.sel && T.sel !== "bg" ? layerById(T.sel) : null; }
function stickerOf(l) { return l?.uid ? (T.s.stickers || []).find((st) => st.uid === l.uid) || null : null; }
function selSticker() { return stickerOf(selLayer()); }
function sprEl(id) { return $$(".thx-spr", T.root).find((x) => x.dataset.id === id) || null; }
function ovOf(id) { T.s.layout = T.s.layout && typeof T.s.layout === "object" ? T.s.layout : {}; const L = (T.s.layout[sizeKey()] = T.s.layout[sizeKey()] || {}); return (L[id] = L[id] || {}); }
function setOv(id, patch) { Object.assign(ovOf(id), patch); }
function hasLayout() { const L = T.s.layout?.[sizeKey()]; return !!L && Object.keys(L).length > 0; }
const isEmoji = (t) => /^\p{Extended_Pictographic}/u.test(t || "");
const uid = () => Math.random().toString(36).slice(2, 9);
function mirrorPlacement() {
  for (const L of Object.values(T.s.layout || {})) for (const [k, o] of Object.entries(L)) if (k !== "_order" && o && typeof o === "object") { if (o.x != null) o.x = 1 - o.x; if (o.rot != null) o.rot = -o.rot; }
  for (const st of T.s.stickers || []) { if (st.x != null) st.x = 1 - st.x; if (st.rot) st.rot = -st.rot; }
}

// commit a move / scale / rotate of layer l: d = {dx, dy, k, dr} (fractions of the canvas, scale factor, degrees)
function commit(l, d) {
  const k = d.k || 1;
  const [cx, cy] = l.frame; let [ax, ay] = l.anchor;
  if (k !== 1) { ax = cx + (ax - cx) * k; ay = cy + (ay - cy) * k; }
  ax += d.dx || 0; ay += d.dy || 0;
  const r4 = (v) => Math.round(v * 10000) / 10000;
  const rot = Math.round(((l.frame[4] || 0) + (d.dr || 0)) * 10) / 10;
  const st = stickerOf(l);
  if (st) {
    st.x = r4(ax); st.y = r4(ay);
    if (k !== 1) { if (st.txt != null) st.size = r4((st.size || 0.08) * k); else st.w = r4((st.w || 0.15) * k); }
    if (d.dr) st.rot = rot;
  } else {
    const patch = { x: r4(ax), y: r4(ay) };
    if (k !== 1) patch.s = r4((l.s || 1) * k);
    if (d.dr) patch.rot = rot;
    setOv(l.id, patch);
  }
}
function zorder(id, d) {
  const ids = T.view.layers.filter((l) => l.id !== "border").map((l) => l.id);
  const i = ids.indexOf(id); if (i < 0) return;
  ids.splice(i, 1);
  const j = d === 2 ? ids.length : d === -2 ? 0 : Math.max(0, Math.min(ids.length, i + d));
  ids.splice(j, 0, id);
  ovOf("_order"); T.s.layout[sizeKey()]._order = ids;
  refresh(0);
}
function removeLayer(l) {
  if (!l || l.locked) return;
  const st = stickerOf(l);
  if (st) T.s.stickers = T.s.stickers.filter((x) => x !== st);
  else if (l.id === "text") T.s.text = "";
  else if (l.id === "logo") T.s.logo = false;
  else setOv(l.id, { hidden: true });
  select(null); renderPanel(); refresh(0);
}
function duplicate(l) {
  const st = stickerOf(l); if (!st) return T.ctx.toast("सिर्फ़ stickers / text badges की copy बनती है");
  if ((T.s.stickers || []).length >= (TPLS.max_stickers || 12)) return T.ctx.toast(`ज़्यादा से ज़्यादा ${TPLS.max_stickers || 12} elements`);
  const c = { ...JSON.parse(JSON.stringify(st)), uid: uid(), x: Math.min(0.95, (st.x ?? 0.5) + 0.03), y: Math.min(0.95, (st.y ?? 0.5) + 0.03) };
  T.s.stickers.push(c); T.sel = "s:" + c.uid; refresh(0);
}
function resetLayer(l) {
  const st = stickerOf(l);
  if (st) { st.rot = 0; } else if (T.s.layout?.[sizeKey()]) delete T.s.layout[sizeKey()][l.id];
  refresh(0);
}
function addSticker(st, fx, fy) {
  if ((T.s.stickers || []).length >= (TPLS.max_stickers || 12)) { T.ctx.toast(`ज़्यादा से ज़्यादा ${TPLS.max_stickers || 12} elements`); return; }
  const it = { uid: uid(), x: Math.round(fx * 1000) / 1000, y: Math.round(fy * 1000) / 1000, rot: 0, ...st };
  (T.s.stickers = T.s.stickers || []).push(it);
  T.sel = "s:" + it.uid; renderBar(); renderPanel(); refresh(0);
}
function addFromToken(tok, fx, fy) {
  const [kind, ...rest] = tok.split(":"); const val = rest.join(":");
  if (kind === "lib") return addSticker({ id: val, w: 0.16 }, fx, fy);
  if (kind === "shape") return addSticker({ shape: val, w: val === "arrow" || val === "curve" ? 0.2 : 0.15 }, fx, fy);
  if (kind === "emoji") return addSticker({ txt: val, size: 0.16 }, fx, fy);
  if (kind === "badge") { const b = BADGES[+val]; return addSticker({ txt: b.txt, size: b.bg ? 0.065 : 0.09, bg: b.bg, color: b.color, font: b.font || "Mukta" }, fx, fy); }
}
async function uploadLib(f, kind) {
  const r = await fetch(`/api/library?kind=${kind}&filename=${encodeURIComponent(f.name || "image.png")}&channel=&tags=thumbnail`, { method: "PUT", headers: { authorization: "Bearer " + T.ctx.S.token, "content-type": "application/octet-stream" }, body: f });
  const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.error || r.statusText); return d;
}
async function addFile(f, fx, fy) {
  if (!/^image\/(png|jpe?g|webp|gif)$/.test(f.type)) return T.ctx.toast(`${f.name}: सिर्फ़ PNG / JPG / WEBP image`);
  const kind = /jpe?g/.test(f.type) ? "image" : "sticker";
  try { T.ctx.toast(`${f.name} upload हो रहा…`); const it = await uploadLib(f, kind); if (!T) return; T.lib = [it, ...T.lib]; addSticker({ id: it.id, w: kind === "image" ? 0.3 : 0.18 }, fx, fy); }
  catch (e) { T.ctx.toast(e.message); }
}

// ---------- selection UI ----------
function select(id) {
  if (T.editing) finishEdit(true);
  T.sel = id; drawSel(); renderBar();
  if (id === "bg") openPanel("bg");
  else if (T.panel === "layers" || (T.panel === "extras")) renderPanel();
}
function frameNow(l) {
  const f = [...l.frame]; const p = T.drag && T.drag.id === l.id ? T.drag : T.pend && T.pend.id === l.id ? T.pend : null;
  if (p) { const k = p.k || 1; f[0] += p.dx || 0; f[1] += p.dy || 0; f[2] *= k; f[3] *= k; f[4] += p.dr || 0; }
  return f;
}
function drawSel() {
  const el = $("#thx-sel", T?.root); if (!el) return;
  const l = selLayer();
  if (!l || T.editing) { el.hidden = true; return; }
  const [cx, cy, w, h, rot] = frameNow(l);
  el.hidden = false;
  Object.assign(el.style, { left: pct(cx - w / 2), top: pct(cy - h / 2), width: pct(w), height: pct(h), transform: `rotate(${rot}deg)` });
  el.classList.toggle("ro", !T.canEdit);
}
function liveSprite(id, p) {
  const sp = sprEl(id); if (!sp) return; const r = stageRect();
  sp.style.transform = p ? `translate(${(p.dx || 0) * r.width}px, ${(p.dy || 0) * r.height}px) rotate(${p.dr || 0}deg) scale(${p.k || 1})` : "";
}
function renderBar() {
  const el = $("#thx-bar", T?.root); if (!el) return; const { esc } = T.ctx;
  const l = selLayer(); const st = stickerOf(l);
  const canUndo = T.hi > 0, canRedo = T.hi < T.hist.length - 1;
  el.innerHTML = `<button class="btn small quiet" data-act="undo" ${canUndo ? "" : "disabled"} title="Undo (Ctrl+Z)">↶</button><button class="btn small quiet" data-act="redo" ${canRedo ? "" : "disabled"} title="Redo (Ctrl+Shift+Z)">↷</button><span class="sep"></span>` +
    (l ? `<b class="small nm">${esc(l.name)}</b>
      ${l.edit && T.canEdit ? `<button class="btn small" data-act="edit" title="text लिखें (double-click)">✎ लिखें</button>` : ""}
      ${l.kind === "text" ? `<button class="btn small quiet" data-act="style">Aa style</button>` : ""}${l.kind === "person" ? `<button class="btn small quiet" data-act="person">✨ सुधारें</button>` : ""}
      <button class="btn small quiet" data-act="fwd" title="आगे ( ] )">⬆ आगे</button><button class="btn small quiet" data-act="back" title="पीछे ( [ )">⬇ पीछे</button>
      ${st ? `<button class="btn small quiet" data-act="dup" title="copy (Ctrl+D)">⧉</button>` : ""}
      <button class="btn small quiet" data-act="reset" title="जगह / घुमाव reset">↺</button>
      <button class="btn small quiet danger" data-act="del" title="हटाएँ (Delete)">🗑</button>`
      : `<span class="small muted">${T.sel === "bg" ? "Background चुना — दाएँ panel में बदलें" : "canvas पर किसी चीज़ को क्लिक करें"}</span>`);
  $$("[data-act]", el).forEach((b) => (b.onclick = () => {
    const a = b.dataset.act; const L = selLayer();
    if (a === "undo") return undo(-1); if (a === "redo") return undo(1);
    if (!L || !T.canEdit) return;
    if (a === "edit") startEdit(L); if (a === "style") openPanel("text"); if (a === "person") openPanel("person");
    if (a === "fwd") zorder(L.id, 1); if (a === "back") zorder(L.id, -1);
    if (a === "dup") duplicate(L); if (a === "reset") resetLayer(L); if (a === "del") removeLayer(L);
  }));
}

// ---------- pointer interaction on the stage ----------
function stageRect() { return $("#thx-stage", T.root).getBoundingClientRect(); }
function toFrac(e) { const r = stageRect(); return [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height]; }
function inFrame(l, fx, fy, padPx = 0) {
  const r = stageRect(); const [cx, cy, w, h, rot] = frameNow(l);
  const px = (fx - cx) * r.width, py = (fy - cy) * r.height; const a = (-rot * Math.PI) / 180;
  const lx = px * Math.cos(a) - py * Math.sin(a), ly = px * Math.sin(a) + py * Math.cos(a);
  return Math.abs(lx) <= (w * r.width) / 2 + padPx && Math.abs(ly) <= (h * r.height) / 2 + padPx;
}
function maskOf(l) {
  const sp = T.sprites[l.hash]; if (!sp) return null;
  if (sp.mask) return sp.mask;
  if (!sp.img) { sp.img = new Image(); sp.img.onload = () => { sp.ready = true; }; sp.img.src = sp.src; return null; }
  if (!sp.ready && !sp.img.complete) return null;
  const iw = sp.img.naturalWidth, ih = sp.img.naturalHeight; if (!iw) return null;
  const sc = Math.min(1, 200 / Math.max(iw, ih)); const cw = Math.max(1, Math.round(iw * sc)), ch = Math.max(1, Math.round(ih * sc));
  const c = document.createElement("canvas"); c.width = cw; c.height = ch; const g = c.getContext("2d", { willReadFrequently: true }); g.drawImage(sp.img, 0, 0, cw, ch);
  const d = g.getImageData(0, 0, cw, ch).data; const a = new Uint8Array(cw * ch); for (let i = 0; i < a.length; i++) a[i] = d[i * 4 + 3];
  return (sp.mask = { w: cw, h: ch, a });
}
function hitLayer(fx, fy) {
  const v = T.view; if (!v) return null;
  for (const l of [...v.layers].reverse()) {
    if (l.locked) continue;
    const [bx, by, bw, bh] = l.box; if (fx < bx || fy < by || fx > bx + bw || fy > by + bh) continue;
    const m = maskOf(l);
    if (!m) return l; // not decoded yet: the box is good enough
    const ix = Math.floor(((fx - bx) / bw) * m.w), iy = Math.floor(((fy - by) / bh) * m.h);
    let hit = false;
    for (let oy = -1; oy <= 1 && !hit; oy++) for (let ox = -1; ox <= 1 && !hit; ox++) { const x = ix + ox, y = iy + oy; if (x >= 0 && y >= 0 && x < m.w && y < m.h && m.a[y * m.w + x] > 24) hit = true; }
    if (hit) return l;
  }
  return null;
}
function snapMove(l, dx, dy, alt) {
  const guides = []; if (alt) return { dx, dy, guides };
  const r = stageRect(); const tx = SNAP_PX / r.width, ty = SNAP_PX / r.height;
  const [bx, by, bw, bh] = l.box;
  const xs = [0, 0.5, 1], ys = [0, 0.5, 1];
  for (const o of T.view.layers) { if (o.id === l.id || o.locked) continue; const [ox, oy, ow, oh] = o.box; xs.push(ox, ox + ow / 2, ox + ow); ys.push(oy, oy + oh / 2, oy + oh); }
  const best = (pts, tgts, thr) => { let m = null; for (const p of pts) for (const t of tgts) { const d = t - p; if (Math.abs(d) <= thr && (!m || Math.abs(d) < Math.abs(m.d))) m = { d, t }; } return m; };
  const sx = best([bx + dx, bx + dx + bw / 2, bx + dx + bw], xs, tx); if (sx) { dx += sx.d; guides.push({ x: sx.t }); }
  const sy = best([by + dy, by + dy + bh / 2, by + dy + bh], ys, ty); if (sy) { dy += sy.d; guides.push({ y: sy.t }); }
  return { dx, dy, guides };
}
function showGuides(gs) {
  const el = $("#thx-guides", T.root); if (!el) return;
  el.innerHTML = (gs || []).map((g) => (g.x != null ? `<i class="gx" style="left:${pct(g.x)}"></i>` : `<i class="gy" style="top:${pct(g.y)}"></i>`)).join("");
}

function bindStage() {
  const st = $("#thx-stage", T.root);
  st.addEventListener("pointerdown", onDown);
  st.addEventListener("pointermove", onMove);
  st.addEventListener("pointerup", onUp);
  st.addEventListener("pointercancel", onUp);
  st.addEventListener("dblclick", (e) => { if (!T.canEdit) return; const [fx, fy] = toFrac(e); const l = hitLayer(fx, fy) || (selLayer() && inFrame(selLayer(), fx, fy) ? selLayer() : null); if (l?.edit) { select(l.id); startEdit(l); } });
  st.addEventListener("pointerleave", () => { const h = $("#thx-hover", T.root); if (h) h.hidden = true; });
  // OS files dropped on the canvas
  st.addEventListener("dragover", (e) => { if (!T.canEdit || ![...(e.dataTransfer?.types || [])].includes("Files")) return; e.preventDefault(); $("#thx-drop", T.root).hidden = false; });
  st.addEventListener("dragleave", () => { $("#thx-drop", T.root).hidden = true; });
  st.addEventListener("drop", async (e) => {
    $("#thx-drop", T.root).hidden = true; if (!T.canEdit) return; e.preventDefault();
    const [fx, fy] = toFrac(e); const files = [...(e.dataTransfer?.files || [])];
    for (const [i, f] of files.entries()) await addFile(f, fx + i * 0.03, fy + i * 0.03);
  });
}
function onDown(e) {
  if (!T.view || T.editing && e.target.closest(".thx-edit")) return;
  if (T.editing) finishEdit(true);
  if (e.button !== undefined && e.button !== 0) return;
  const st = $("#thx-stage", T.root); st.focus({ preventScroll: true });
  $("#thx-hover", T.root).hidden = true;
  const [fx, fy] = toFrac(e);
  const h = e.target.closest("[data-h]")?.dataset.h;
  let l = selLayer();
  if (h && l && T.canEdit) { startDrag(e, l, h === "rot" ? "rot" : "scale", fx, fy); return; }
  const hit = hitLayer(fx, fy);
  l = hit || (l && inFrame(l, fx, fy) ? l : null);
  if (!l) { select("bg"); return; }
  if (T.sel !== l.id) select(l.id);
  if (T.canEdit) startDrag(e, l, "move", fx, fy);
}
function startDrag(e, l, mode, fx, fy) {
  e.preventDefault();
  $("#thx-stage", T.root).setPointerCapture(e.pointerId);
  const r = stageRect(); const [cx, cy] = l.frame;
  T.drag = { id: l.id, mode, fx, fy, dx: 0, dy: 0, k: 1, dr: 0, moved: false, pid: e.pointerId,
    r0: Math.hypot((fx - cx) * r.width, (fy - cy) * r.height) || 1, a0: Math.atan2((fy - cy) * r.height, (fx - cx) * r.width) };
  if (T.pend && T.pend.id === l.id) { T.drag.base = { ...T.pend }; } else T.pend = null;
}
function onMove(e) {
  const d = T.drag;
  if (!d) { hoverAt(e); return; }
  if (e.pointerId !== d.pid) return;
  const l = layerById(d.id); if (!l) return;
  const [fx, fy] = toFrac(e); const r = stageRect(); const b = d.base || {};
  const [cx0, cy0] = l.frame; const cx = cx0 + (b.dx || 0), cy = cy0 + (b.dy || 0);
  if (!d.moved && Math.hypot((fx - d.fx) * r.width, (fy - d.fy) * r.height) < 3) return;
  d.moved = true;
  if (d.mode === "move") {
    const sn = snapMove(l, (b.dx || 0) + fx - d.fx, (b.dy || 0) + fy - d.fy, e.altKey);
    d.dx = sn.dx; d.dy = sn.dy; d.k = b.k || 1; d.dr = b.dr || 0; showGuides(sn.guides);
  } else if (d.mode === "scale") {
    const rr = Math.hypot((fx - cx) * r.width, (fy - cy) * r.height);
    const minK = 14 / Math.max(1, Math.max(l.frame[2] * r.width, l.frame[3] * r.height));
    d.k = Math.max(minK, Math.min(8, (b.k || 1) * (rr / d.r0))); d.dx = b.dx || 0; d.dy = b.dy || 0; d.dr = b.dr || 0;
  } else {
    let a = (b.dr || 0) + ((Math.atan2((fy - cy) * r.height, (fx - cx) * r.width) - d.a0) * 180) / Math.PI;
    const total = (l.frame[4] || 0) + a; const step = e.shiftKey ? 15 : 45; const near = Math.round(total / step) * step;
    if (e.shiftKey || Math.abs(near - total) < 4) a = near - (l.frame[4] || 0);
    d.dr = Math.round(a * 10) / 10; d.dx = b.dx || 0; d.dy = b.dy || 0; d.k = b.k || 1;
  }
  liveSprite(l.id, d); drawSel();
}
function onUp(e) {
  const d = T.drag; if (!d || e.pointerId !== d.pid) return;
  T.drag = null; showGuides([]);
  if (!d.moved) { drawSel(); return; }
  const l = layerById(d.id); if (!l) return;
  T.pend = { id: l.id, dx: d.dx, dy: d.dy, k: d.k, dr: d.dr };
  commit(l, T.pend); drawSel(); renderBar(); refresh(0);
}
function hoverAt(e) {
  const hv = $("#thx-hover", T.root); if (!hv || e.pointerType !== "mouse" || !T.view) return;
  const [fx, fy] = toFrac(e); const l = hitLayer(fx, fy);
  const st = $("#thx-stage", T.root);
  if (!l || l.id === T.sel) { hv.hidden = true; st.style.cursor = l ? "move" : "default"; return; }
  st.style.cursor = "pointer";
  const [cx, cy, w, h, rot] = l.frame; hv.hidden = false;
  Object.assign(hv.style, { left: pct(cx - w / 2), top: pct(cy - h / 2), width: pct(w), height: pct(h), transform: `rotate(${rot}deg)` });
}

// keyboard: arrows nudge, Delete, Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y, Ctrl+D, [ ], Esc, Enter
function onKey(e) {
  if (!T || !$("#thx-stage", T.root)) return;
  const tg = e.target; if (tg && (tg.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(tg.tagName))) return;
  if (!T.root.contains(document.activeElement) && document.activeElement !== document.body) return;
  const mod = e.ctrlKey || e.metaKey; const key = e.key;
  if (mod && (key === "z" || key === "Z")) { e.preventDefault(); undo(e.shiftKey ? 1 : -1); return; }
  if (mod && (key === "y" || key === "Y")) { e.preventDefault(); undo(1); return; }
  const l = selLayer(); if (!l || !T.canEdit) { if (key === "Escape") select(null); return; }
  if (key === "Escape") { select(null); return; }
  if (key === "Delete" || key === "Backspace") { e.preventDefault(); removeLayer(l); return; }
  if (mod && (key === "d" || key === "D")) { e.preventDefault(); duplicate(l); return; }
  if (key === "Enter" && l.edit) { e.preventDefault(); startEdit(l); return; }
  if (key === "]" || key === "[") { e.preventDefault(); zorder(l.id, (key === "]" ? 1 : -1) * (e.shiftKey ? 2 : 1)); return; }
  const dirs = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
  if (dirs[key]) {
    e.preventDefault(); const step = e.shiftKey ? 10 : 1;
    const p = T.pend && T.pend.id === l.id ? T.pend : (T.pend = { id: l.id, dx: 0, dy: 0, k: 1, dr: 0 });
    p.dx += (dirs[key][0] * step) / T.view.w; p.dy += (dirs[key][1] * step) / T.view.h;
    commit(l, p); liveSprite(l.id, p); drawSel(); refresh(300);
  }
}

// ---------- pointer drag from the elements panel (mouse + touch) ----------
function bindDragSource(b) {
  b.addEventListener("pointerdown", (e) => {
    if (!T.canEdit || (e.button !== undefined && e.button !== 0)) return;
    const pd = (T.pdrag = { tok: b.dataset.drag, x: e.clientX, y: e.clientY, pid: e.pointerId, active: false, src: b, ghost: null, touch: e.pointerType === "touch", t0: Date.now() });
    if (pd.touch) pd.timer = setTimeout(() => { if (T?.pdrag === pd) beginGhost(pd, e.clientX, e.clientY); }, 260);
  });
  b.addEventListener("touchmove", (e) => { if (T?.pdrag?.active) e.preventDefault(); }, { passive: false });
  b.addEventListener("pointermove", (e) => {
    const pd = T?.pdrag; if (!pd || pd.pid !== e.pointerId) return;
    if (!pd.active) { if (pd.touch) { if (Math.hypot(e.clientX - pd.x, e.clientY - pd.y) > 8) { clearTimeout(pd.timer); T.pdrag = null; } return; } if (Math.hypot(e.clientX - pd.x, e.clientY - pd.y) < 6) return; beginGhost(pd, e.clientX, e.clientY); }
    moveGhost(pd, e.clientX, e.clientY);
  });
  b.addEventListener("pointerup", (e) => endPanelDrag(e));
  b.addEventListener("pointercancel", () => { const pd = T?.pdrag; if (pd) { clearTimeout(pd.timer); pd.ghost?.remove(); T.pdrag = null; $("#thx-drop", T.root).hidden = true; } });
  b.addEventListener("dragstart", (e) => e.preventDefault());
}
function beginGhost(pd, x, y) {
  pd.active = true; try { pd.src.setPointerCapture(pd.pid); } catch {}
  const g = pd.src.cloneNode(true); g.classList.add("thx-ghost"); g.removeAttribute("data-drag"); document.body.appendChild(g); pd.ghost = g; moveGhost(pd, x, y);
}
function moveGhost(pd, x, y) {
  if (!pd.ghost) return; pd.ghost.style.transform = `translate(${x - 24}px, ${y - 24}px)`;
  const r = stageRect(); const over = x >= r.left && x <= r.right && y >= r.top && y <= r.bottom; $("#thx-drop", T.root).hidden = !over;
}
function endPanelDrag(e) {
  const pd = T?.pdrag; if (!pd || pd.pid !== e.pointerId) return;
  clearTimeout(pd.timer); T.pdrag = null; pd.ghost?.remove(); $("#thx-drop", T.root).hidden = true;
  if (!pd.active) { addFromToken(pd.tok, 0.5 + (Math.random() - 0.5) * 0.1, 0.5 + (Math.random() - 0.5) * 0.1); return; }
  const r = stageRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) return;
  addFromToken(pd.tok, (e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height);
}

// ---------- inline text editing ----------
function toHtml(t) { const { esc } = T.ctx; return esc(t).replace(/\*([^*\n]+)\*/g, "<b>$1</b>").replace(/(^|[\s])_([^_\s][^_\n]*)_(?=$|[\s])/g, "$1<i>$2</i>").replace(/\n/g, "<br>"); }
const ZW = /\u200b/g;
function fromHtml(el) {
  let out = "";
  const walk = (n, wrap) => {
    for (const c of n.childNodes) {
      if (c.nodeType === 3) out += c.textContent.replace(/\u00a0/g, " ").replace(ZW, "");
      else if (c.nodeName === "BR") out += "\n";
      else if (/^(B|STRONG)$/.test(c.nodeName)) { const t = c.textContent.replace(ZW, "").trim(); if (t) out += "*" + t + "*"; }
      else if (/^(I|EM)$/.test(c.nodeName)) { const t = c.textContent.replace(ZW, "").trim(); if (t) out += "_" + t + "_"; }
      else if (/^(DIV|P)$/.test(c.nodeName)) { if (out && !out.endsWith("\n")) out += "\n"; walk(c, wrap); }
      else walk(c, wrap);
    }
  };
  walk(el);
  return out.replace(/[ \t]+/g, " ").split("\n").map((x) => x.trim()).filter((x, i, a) => x || i < a.length - 1).slice(0, 3).join("\n").trim();
}
function startEdit(l) {
  if (!l?.edit || !T.canEdit) return;
  if (T.editing) finishEdit(true);
  const ed = l.edit; const r = stageRect(); const [cx, cy, , , rot] = l.frame;
  const box = document.createElement("div"); box.className = "thx-edit"; box.contentEditable = "true"; box.spellcheck = false;
  const px = (ed.px || 0.1) * r.height;
  Object.assign(box.style, { left: pct(cx), top: pct(cy), transform: `translate(-50%, -50%) rotate(${rot}deg)`, fontFamily: FONT_CSS[ed.font] || "Mukta", fontWeight: FONT_W[ed.font] || 800,
    fontSize: px + "px", color: ed.color || "#fff", textAlign: ed.align || "left", background: ed.bg || "" });
  box.style.setProperty("--hl", ed.hl || "#FFD400");
  if (ed.bg) box.style.webkitTextStroke = "0";
  box.innerHTML = l.id === "text" ? toHtml(ed.value || "") : T.ctx.esc(ed.value || "");
  $("#thx-stage", T.root).appendChild(box);
  T.editing = { id: l.id, el: box, layer: l };
  const sp = sprEl(l.id); if (sp) sp.style.visibility = "hidden"; drawSel(); renderBar();
  box.focus(); const rg = document.createRange(); rg.selectNodeContents(box); const sel = getSelection(); sel.removeAllRanges(); sel.addRange(rg);
  box.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Escape") { e.preventDefault(); finishEdit(false); }
    else if (e.key === "Enter" && (e.ctrlKey || e.metaKey || l.id !== "text")) { e.preventDefault(); finishEdit(true); }
    else if (e.key === "Enter") { e.preventDefault(); document.execCommand("insertLineBreak"); }
    else if ((e.ctrlKey || e.metaKey) && (e.key === "b" || e.key === "B")) { e.preventDefault(); if (l.id === "text") toggleHl(box); }
  });
  box.addEventListener("paste", (e) => { e.preventDefault(); document.execCommand("insertText", false, (e.clipboardData?.getData("text/plain") || "").slice(0, 160)); });
  box.addEventListener("blur", () => setTimeout(() => { if (T?.editing?.el === box) finishEdit(true); }, 0));
}
// Ctrl+B = highlight (*word*). The text is already heavy, so the browser's own "bold" command would un-bold it.
function toggleHl(box) {
  const sel = getSelection(); if (!sel.rangeCount) return;
  const rg = sel.getRangeAt(0); if (!box.contains(rg.commonAncestorContainer)) return;
  const inB = (n) => { while (n && n !== box) { if (n.nodeName === "B") return n; n = n.parentNode; } return null; };
  const b = inB(rg.startContainer);
  if (rg.collapsed) {
    if (b) { // leave the highlight: caret after it
      const after = document.createTextNode("\u200b"); b.after(after); const r = document.createRange(); r.setStart(after, 1); r.collapse(true); sel.removeAllRanges(); sel.addRange(r);
    } else {
      const nb = document.createElement("b"); nb.textContent = "\u200b"; rg.insertNode(nb); const r = document.createRange(); r.setStart(nb.firstChild, 1); r.collapse(true); sel.removeAllRanges(); sel.addRange(r);
    }
    return;
  }
  if (b && b.contains(rg.endContainer)) { b.replaceWith(...b.childNodes); return; }
  const nb = document.createElement("b"); nb.appendChild(rg.extractContents()); rg.insertNode(nb);
  const r = document.createRange(); r.setStartAfter(nb); r.collapse(true); sel.removeAllRanges(); sel.addRange(r);
}
function finishEdit(save) {
  const ed = T.editing; if (!ed) return; T.editing = null;
  const val = ed.layer.id === "text" ? fromHtml(ed.el) : ed.el.innerText.replace(/\s+/g, " ").trim();
  ed.el.remove();
  const sp = sprEl(ed.id); if (sp) sp.style.visibility = "";
  if (save && val !== (ed.layer.edit.value || "")) {
    const l = ed.layer; const st = stickerOf(l);
    if (l.id === "text") T.s.text = val;
    else if (st) { if (!val) T.s.stickers = T.s.stickers.filter((x) => x !== st); else st.txt = val; }
    else if (l.kind === "label") { const tp = tplOf(T.s.template); const i = l.edit.index; T.s.labels = (tp.labels || []).map((x, j) => (j === i ? val || x.text : (T.s.labels || [])[j] || x.text)); }
    renderPanel(); refresh(0);
  }
  drawSel(); renderBar();
}

// ---------- text suggestions ----------
async function suggest(quiet) {
  const b = $("#th-sugg", T.root); if (b) { b.disabled = true; b.textContent = "सोच रहा…"; }
  try { T.sugg = await T.ctx.api("POST", `/projects/${T.pid}/thumbnails/text`, {}); if (!T) return;
    if (quiet && !T.s.text && T.sugg.options?.length) { T.s.text = T.sugg.options[0]; T.hist[T.hi] = JSON.stringify(T.s); refresh(0); }
  } catch (e) { if (!quiet) T.ctx.toast(e.message); }
  if (T && T.panel === "text") renderPanel();
}

// ---------- saved ----------
function renderSaved() {
  const el = $("#th-saved", T.root); if (!el) return; const { esc } = T.ctx;
  const list = T.ov.saved.filter((a) => a.label === (T.s.size === "vertical" ? "vertical" : "yt"));
  el.innerHTML = list.length ? list.map((a) => `<div class="th-sv ${a.selected ? "sel" : ""} ${a.label}">
      <img src="${a.url}" loading="lazy" alt="">${a.selected ? `<em>★ चुना हुआ</em>` : ""}
      <div class="th-svb"><span class="small" title="${esc(a.meta?.text || "")}">${esc(tplOf(a.meta?.template).label)}${a.meta?.source === "autopilot" ? " · ✈" : a.meta?.source === "variants" ? " · A/B" : ""}</span>
      <span class="row">${T.canEdit && !a.selected ? `<button class="btn small" data-svsel="${a.id}" title="publish के लिए चुनें">★</button>` : ""}<button class="btn quiet small" data-svedit="${a.id}" title="इसे edit करें">✎</button><a class="btn quiet small" href="${a.url}&download=1" title="download">⬇</a>${T.canEdit ? `<button class="btn quiet small danger" data-svdel="${a.id}" title="हटाएँ">✕</button>` : ""}</span></div>
      ${(a.meta?.warnings || []).some((w) => w.level === "warn") ? `<i class="warnb" title="${esc(a.meta.warnings.filter((w) => w.level === "warn").map((w) => w.msg).join("\n"))}">⚠</i>` : ""}</div>`).join("")
    : `<p class="small muted">अभी कुछ save नहीं हुआ। “Save + चुनें” या “3 variants बनाएँ” — A/B test के लिए 2–3 रखें, YouTube Studio के “Test & compare” में डालें।</p>`;
  $$("[data-svsel]", el).forEach((b) => (b.onclick = async () => { await T.ctx.api("POST", `/projects/${T.pid}/thumbnails/${b.dataset.svsel}/select`, {}); await reloadSaved(); T.ctx.toast("★ publish पर यही thumbnail जाएगा"); }));
  $$("[data-svedit]", el).forEach((b) => (b.onclick = () => { const a = T.ov.saved.find((x) => x.id === b.dataset.svedit); if (!a?.meta?.settings) return; T.s = JSON.parse(JSON.stringify(a.meta.settings)); const r = $("#th-t", T.root); r.value = T.s.t || 0; $("#th-tl", T.root).textContent = fmtT(T.s.t); select(null); markFrames(); renderPanel(); refresh(0); T.ctx.toast("settings लोड हुईं — बदलें और फिर save करें"); }));
  $$("[data-svdel]", el).forEach((b) => (b.onclick = async () => { if (!confirm("यह thumbnail हटाएँ?")) return; await T.ctx.api("DELETE", `/projects/${T.pid}/thumbnails/${b.dataset.svdel}`); await reloadSaved(); }));
}
async function reloadSaved() { const ov = await T.ctx.api("GET", `/projects/${T.pid}/thumbnails`); if (!T) return; T.ov = { ...T.ov, saved: ov.saved, selected: ov.selected }; renderSaved(); }

async function save() {
  if (T.editing) finishEdit(true);
  const b = $("#th-save", T.root); b.disabled = true; const old = b.textContent; b.textContent = "save हो रहा…";
  try { await T.ctx.api("POST", `/projects/${T.pid}/thumbnails`, { settings: T.s, select: true }); await reloadSaved(); T.ctx.toast("save हुआ ★ — publish पर यही जाएगा"); }
  catch (e) { T.ctx.toast(e.message); }
  if (T) { b.disabled = false; b.textContent = old; }
}
async function variants() {
  const b = $("#th-var", T.root); b.disabled = true; const old = b.textContent; b.textContent = "3 variants बन रहे… (~10s)";
  try { const r = await T.ctx.api("POST", `/projects/${T.pid}/thumbnails/variants`, { n: 3, size: T.s.size || "yt", base: T.s.text ? T.s : null }); if (!T) return; T.ov.saved = r.saved; renderSaved(); T.ctx.toast(`${r.made.length} variants बने — नीचे देखें, ★ से चुनें`); $("#th-saved", T.root)?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }
  catch (e) { T.ctx.toast(e.message); }
  if (T) { b.disabled = false; b.textContent = old; }
}
async function download() {
  const b = $("#th-dl", T.root); b.disabled = true;
  try {
    const { blob } = await authBlob(`/projects/${T.pid}/thumbnails/preview`, { settings: T.s });
    const u = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = u; a.download = `thumbnail-${T.s.size || "yt"}.jpg`; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(u), 4000);
  } catch (e) { T.ctx.toast(e.message); }
  if (T) b.disabled = false;
}
