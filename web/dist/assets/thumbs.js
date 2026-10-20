// Vividora — Thumbnail studio (no build step). Mounted by app.js on #/thumbs/<project id>.
// Server: /api/projects/<id>/thumbnails* (server/vividora/api/thumbnails.py)

let T = null;
let TPLS = null; // cached /thumbnails/templates

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const fmtT = (t) => { t = Math.max(0, +t || 0); const m = Math.floor(t / 60), s = t % 60; return `${m}:${s < 10 ? "0" : ""}${s.toFixed(1)}`; };
const COLORS = ["#FFD400", "#FF3B30", "#00E5FF", "#00E676", "#FF6A00", "#F2B33D", "#FFFFFF", "#E040FB"];
const FONT_CSS = { Mukta: "Mukta", "Baloo 2": "'Baloo 2'", Hind: "Hind", Poppins: "Poppins", "Noto Sans Devanagari": "'Noto Sans Devanagari'" };

async function authBlob(path, body) {
  const r = await fetch("/api" + path, { method: body ? "POST" : "GET", headers: { authorization: "Bearer " + T.ctx.S.token, ...(body ? { "content-type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined, signal: body ? T.abort?.signal : undefined });
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).error || m; } catch {} throw new Error(m); }
  return { blob: await r.blob(), headers: r.headers };
}

export async function mount(root, pid, ctx) {
  unmount();
  T = { root, pid, ctx, p: null, ov: null, frames: [], frameUrls: {}, lib: [], sugg: null, s: null, preview: null, lint: [], info: {}, timer: null, abort: null,
        canEdit: ctx.S.user.role !== "viewer", panel: localStorage.getItem("vividora_thpanel") || "text" };
  root.innerHTML = `<div class="th-loading"><div class="spin"></div><p class="muted">Thumbnail studio खुल रहा है…</p></div>`;
  try {
    const [p, ov, tp] = await Promise.all([ctx.api("GET", `/projects/${pid}`), ctx.api("GET", `/projects/${pid}/thumbnails`), TPLS ? Promise.resolve(TPLS) : ctx.api("GET", "/thumbnails/templates")]);
    if (!T || T.pid !== pid) return;
    TPLS = tp; T.p = p; T.ov = ov; T.frames = ov.frames || [];
  } catch (e) { root.innerHTML = `<div class="note err">${ctx.esc(e.message)}</div><a class="btn" href="#/thumbs">← वापस</a>`; return; }
  const sel = T.ov.saved.find((a) => a.selected && a.label === "yt") || T.ov.saved[0];
  T.s = sel?.meta?.settings ? JSON.parse(JSON.stringify(sel.meta.settings)) : { template: "face_right", size: "yt", t: T.frames[0]?.t || 0, text: "", cutout: true, logo: T.ov.brand_logo };
  shell();
  if (!T.ov.has_video) { $("#th-stage-msg", root).innerHTML = `<div class="note">इस project में अभी वीडियो नहीं है — upload / preview बनने के बाद thumbnail बनेगा।</div>`; return; }
  loadFrames(false);
  if (!T.s.text) suggest(true);
  ctx.api("GET", "/library").then((l) => { if (!T) return; T.lib = l; if (T.panel === "extras" || T.panel === "bg") renderPanel(); }).catch(() => {});
  refresh(0);
}

export function unmount() {
  if (!T) return;
  clearTimeout(T.timer); T.abort?.abort();
  Object.values(T.frameUrls).forEach((u) => URL.revokeObjectURL(u));
  if (T.preview) URL.revokeObjectURL(T.preview);
  T = null;
}

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
      <a class="btn quiet" id="th-dl" download="thumbnail.jpg" title="अभी का preview download करें">⬇</a>
    </div>
    <div class="th-grid">
      <section class="th-stage">
        <div id="th-stage-msg"></div>
        <div class="th-canvas ${s.size === "vertical" ? "vertical" : ""}"><img id="th-img" alt="thumbnail preview"><div class="th-busy" id="th-busy" hidden><div class="spin"></div></div></div>
        <div id="th-lint" class="th-lint"></div>
        <div class="th-block"><div class="row between"><h3>Frame चुनें</h3><span class="row"><span class="small muted">sharpness · चेहरा · आँखें · रोशनी से चुने गए</span><button class="btn quiet small" id="th-fr-refresh" title="दोबारा ढूँढें">⟳</button></span></div>
          <div class="th-frames" id="th-frames"><div class="small muted">best frames ढूँढे जा रहे हैं…</div></div>
          <div class="th-scrub"><span class="small muted">कोई भी समय</span><input type="range" id="th-t" min="0" max="${Math.max(0.1, T.ov.duration || 0).toFixed(2)}" step="0.05" value="${s.t || 0}"><b class="small" id="th-tl">${fmtT(s.t)}</b></div></div>
        <div class="th-block"><div class="row between"><h3>Saved · A/B candidates</h3><span class="small muted">★ = publish पर यही जाएगा</span></div><div class="th-saved" id="th-saved"></div></div>
      </section>
      <aside class="th-side">
        <nav class="th-tabs">${[["text", "Text"], ["layout", "Layout"], ["bg", "Background"], ["person", "Person"], ["extras", "Extras"]].map(([k, l]) => `<button data-panel="${k}" class="${T.panel === k ? "on" : ""}">${l}</button>`).join("")}</nav>
        <div id="th-panel" class="th-panel"></div>
      </aside>
    </div></div>`;
  $$("[data-size]", T.root).forEach((b) => (b.onclick = () => { T.s.size = b.dataset.size; $$("[data-size]", T.root).forEach((x) => x.classList.toggle("on", x === b)); $(".th-canvas", T.root).classList.toggle("vertical", T.s.size === "vertical"); renderPanel(); refresh(0); renderSaved(); }));
  $$("[data-panel]", T.root).forEach((b) => (b.onclick = () => { T.panel = b.dataset.panel; try { localStorage.setItem("vividora_thpanel", T.panel); } catch {} $$("[data-panel]", T.root).forEach((x) => x.classList.toggle("on", x === b)); renderPanel(); }));
  const tr = $("#th-t", T.root); tr.oninput = () => { $("#th-tl", T.root).textContent = fmtT(+tr.value); }; tr.onchange = () => { T.s.t = +tr.value; markFrames(); refresh(0); };
  $("#th-fr-refresh", T.root).onclick = () => loadFrames(true);
  const sv = $("#th-save", T.root); if (sv) sv.onclick = save;
  const vb = $("#th-var", T.root); if (vb) vb.onclick = variants;
  renderPanel(); renderSaved();
}

function field(label, html, cls = "") { return `<div class="th-f ${cls}"><label>${label}</label>${html}</div>`; }
function swatches(key, cur) { return `<div class="th-sw">${COLORS.map((c) => `<button style="--c:${c}" data-sw="${key}" data-c="${c}" class="${(cur || "").toUpperCase() === c ? "on" : ""}" title="${c}"></button>`).join("")}<input type="color" data-k="${key}" value="${cur && /^#[0-9a-f]{6}$/i.test(cur) ? cur : "#ffffff"}"></div>`; }
function tplOf(id) { return TPLS.templates.find((t) => t.id === id) || TPLS.templates[0]; }

function renderPanel() {
  const { esc } = T.ctx; const s = T.s; const el = $("#th-panel", T.root); if (!el) return;
  const tp = tplOf(s.template); const dis = T.canEdit ? "" : "disabled";
  let html = "";
  if (T.panel === "text") {
    html = `${field("Thumbnail text <span class='muted'>(2–5 शब्द · <b>*शब्द*</b> = highlight · Enter = नई लाइन)</span>", `<textarea id="th-text" rows="3" placeholder="3 *बड़ी* गलतियाँ" ${dis}>${esc(s.text || "")}</textarea>`)}
      <div class="row between"><span class="small muted">AI / title से सुझाव</span><button class="btn small" id="th-sugg">✨ सुझाव</button></div>
      <div class="th-chips" id="th-chips">${(T.sugg?.options || []).map((o, i) => `<button class="chip" data-sg="${i}">${esc(o).replace(/\*([^*]+)\*/g, "<b>$1</b>").replace(/\n/g, " / ")}</button>`).join("") || `<span class="small muted">“सुझाव” दबाएँ</span>`}</div>
      <div class="th-row2">${field("Font", `<select data-k="font" ${dis}><option value="">template (${esc(tp.text?.font || "")})</option>${TPLS.fonts.map((f) => `<option ${s.font === f ? "selected" : ""} style="font-family:${FONT_CSS[f] || f}">${f}</option>`).join("")}</select>`)}
        ${field("Style", `<select data-k="style" ${dis}><option value="">template (${esc(TPLS.styles[tp.text?.style] || "")})</option>${Object.entries(TPLS.styles).map(([k, v]) => `<option value="${k}" ${s.style === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>`)}</div>
      ${field(`आकार <b>${(+s.text_scale || 1).toFixed(2)}×</b>`, `<input type="range" data-k="text_scale" min="0.5" max="1.5" step="0.05" value="${s.text_scale || 1}" ${dis}>`)}
      ${field("अक्षर का रंग", swatches("color", s.color || ""))}
      ${field("Highlight रंग (*शब्द*)", swatches("hl", s.hl || ""))}
      ${field("Accent (तीर, badge, glow, border)", swatches("accent", s.accent || tp.accent))}
      <label class="chk small"><input type="checkbox" data-k="upper" ${s.upper ? "checked" : ""} ${dis}> English CAPITAL letters</label>
      ${s.color || s.hl || s.accent || s.font || s.style ? `<button class="btn quiet small" id="th-reset-text">↺ template के रंग/font</button>` : ""}`;
  } else if (T.panel === "layout") {
    html = `<p class="small muted">Layout चुनें — चेहरा, text और रंग की जगह। हर layout 16:9 और 9:16 दोनों में बनता है।</p>
      <div class="th-tpls">${TPLS.templates.map((t) => tplCard(t)).join("")}</div>
      <label class="chk small" style="margin-top:.6rem"><input type="checkbox" data-k="flip" ${s.flip ? "checked" : ""} ${dis}> ⇆ उल्टा करें (चेहरा दूसरी तरफ़)</label>
      ${tp.labels?.length ? field("Labels", `<div class="th-row2">${tp.labels.map((l, i) => `<input data-label="${i}" value="${esc((s.labels || [])[i] || l.text)}" ${dis}>`).join("")}</div>`) : ""}
      ${tp.bg?.type === "split" ? field("दूसरा frame (पहले / before)", `<div class="th-scrub"><input type="range" id="th-t2" min="0" max="${Math.max(0.1, T.ov.duration || 0).toFixed(2)}" step="0.05" value="${s.t2 ?? (T.frames[1]?.t || 0)}"><b class="small" id="th-t2l">${fmtT(s.t2 ?? (T.frames[1]?.t || 0))}</b></div>`) : ""}
      ${field("Grade", `<select data-k="grade" ${dis}><option value="">template जैसा</option><option value="pop" ${s.grade === "pop" ? "selected" : ""}>Pop (चटक)</option><option value="warm" ${s.grade === "warm" ? "selected" : ""}>Warm</option><option value="dark" ${s.grade === "dark" ? "selected" : ""}>Dark / moody</option><option value="none" ${s.grade === "none" ? "selected" : ""}>कुछ नहीं</option></select>`)}`;
  } else if (T.panel === "bg") {
    const bg = s.bg || {}; const imgs = T.lib.filter((x) => ["image", "frame", "broll"].includes(x.kind) && (x.mime || "").startsWith("image/"));
    html = `${field("Background", `<select id="th-bgtype" ${dis}>${Object.entries(TPLS.bg_types).map(([k, v]) => `<option value="${k}" ${(bg.type || "") === k ? "selected" : ""}>${esc(v)}${k === "" ? ` (${esc(tp.bg?.type || "")})` : ""}</option>`).join("")}</select>`)}
      ${["solid", "gradient"].includes(bg.type) ? field("रंग", swatches("bg.color", bg.color || "#111827")) : ""}
      ${bg.type === "gradient" ? field("दूसरा रंग", swatches("bg.color2", bg.color2 || "#2C5364")) + field(`कोण <b>${bg.angle ?? 90}°</b>`, `<input type="range" data-k="bg.angle" min="0" max="180" step="5" value="${bg.angle ?? 90}">`) : ""}
      ${bg.type === "blur" ? field(`धुँधलापन <b>${bg.blur ?? 22}</b>`, `<input type="range" data-k="bg.blur" min="4" max="60" step="2" value="${bg.blur ?? 22}">`) + field(`अंधेरा <b>${Math.round((bg.dim ?? 0.4) * 100)}%</b>`, `<input type="range" data-k="bg.dim" min="0" max="0.85" step="0.05" value="${bg.dim ?? 0.4}">`) : ""}
      ${bg.type === "image" ? `<div class="th-libgrid">${imgs.slice(0, 60).map((x) => `<button class="${bg.image_id === x.id ? "on" : ""}" data-bgimg="${x.id}" title="${esc(x.name)}"><img src="${x.url}" loading="lazy" alt=""></button>`).join("") || `<p class="small muted">Library में image upload करें (kind: image)।</p>`}</div>` : ""}
      <p class="small muted">cutout बंद हो तो solid / gradient की जगह पूरा frame लगता है, ताकि चेहरा दिखे।</p>`;
  } else if (T.panel === "person") {
    const pst = s.person_stroke !== undefined ? s.person_stroke : (tp.person?.stroke || ""); const pgl = s.person_glow !== undefined ? s.person_glow : (tp.person?.glow || "");
    html = tp.person === null ? `<p class="muted small">इस layout में अलग person नहीं है (पूरे frames)।</p>` : `
      <label class="chk"><input type="checkbox" data-k="cutout" ${s.cutout !== false ? "checked" : ""} ${dis}> <b>Person cutout</b> — background हटाकर सिर्फ़ आप</label>
      <p class="small muted">${T.ov.has_alpha ? "इस project का cutout (alpha) तैयार है ✓" : "cutout इसी frame पर RVM से बनता है (पहली बार कुछ सेकंड)। Editor → Body effects से पूरा cutout पहले बना लें तो और साफ़।"}</p>
      ${field(`चेहरे का आकार <b>${(+s.person_scale || 1).toFixed(2)}×</b>`, `<input type="range" data-k="person_scale" min="0.6" max="1.6" step="0.05" value="${s.person_scale || 1}" ${dis}>`)}
      <label class="chk small"><input type="checkbox" id="th-pst" ${pst ? "checked" : ""} ${dis}> सफ़ेद/रंगीन border (sticker look)</label>${pst ? swatches("person_stroke", pst === "accent" ? (s.accent || tp.accent) : pst) : ""}
      <label class="chk small"><input type="checkbox" id="th-pgl" ${pgl ? "checked" : ""} ${dis}> Glow</label>${pgl ? swatches("person_glow", pgl === "accent" ? (s.accent || tp.accent) : pgl) : ""}`;
  } else {
    const stk = T.lib.filter((x) => x.kind === "sticker" && /(shape|emoji|arrow|social)/.test(x.tags || ""));
    html = `${field("Number badge", `<input data-k="badge" value="${esc(s.badge || "")}" placeholder="जैसे 3 (खाली = text का पहला नंबर)" ${dis}>`)}
      <p class="small muted">Badge “Number badge” layout में दिखता है।</p>
      <h4>Shapes</h4><div class="row">${Object.entries(TPLS.shapes).map(([k, v]) => `<button class="btn small" data-addshape="${k}">+ ${esc(v)}</button>`).join("")}</div>
      <h4>Stickers · emoji <span class="small muted">(library)</span></h4>
      <div class="th-libgrid small">${stk.slice(0, 80).map((x) => `<button data-addstk="${x.id}" title="${esc(x.name)}"><img src="${x.url}" loading="lazy" alt=""></button>`).join("") || `<span class="small muted">library लोड हो रही है…</span>`}</div>
      ${(s.stickers || []).length ? `<h4>लगे हुए</h4>${s.stickers.map((st, i) => `<div class="th-stk"><b class="small">${st.shape ? esc(TPLS.shapes[st.shape] || st.shape) : esc((T.lib.find((x) => x.id === st.id) || {}).name || "sticker")}</b>
        <div class="th-row4">${[["x", 0, 1, 0.01, "←→"], ["y", 0, 1, 0.01, "↑↓"], ["w", 0.04, 0.6, 0.01, "size"], ["rot", -180, 180, 5, "घुमाएँ"]].map(([k, a, b, st2, l]) => `<label>${l}<input type="range" data-stk="${i}" data-sk="${k}" min="${a}" max="${b}" step="${st2}" value="${st[k] ?? (k === "w" ? 0.15 : k === "rot" ? 0 : 0.5)}"></label>`).join("")}</div>
        <button class="btn quiet small danger" data-delstk="${i}">✕ हटाएँ</button></div>`).join("")}` : ""}
      <h4>Brand logo</h4><label class="chk small"><input type="checkbox" data-k="logo" ${s.logo ? "checked" : ""} ${dis} ${T.ov.brand_logo ? "" : "disabled"}> कोने में logo ${T.ov.brand_logo ? "" : "<span class='muted'>(Channels & Brand में logo चुनें)</span>"}</label>
      ${s.logo ? field("कोना", `<select data-k="logo_pos">${[["tr", "ऊपर दाएँ"], ["tl", "ऊपर बाएँ"], ["br", "नीचे दाएँ"], ["bl", "नीचे बाएँ"]].map(([k, l]) => `<option value="${k}" ${(s.logo_pos || "tr") === k ? "selected" : ""}>${l}</option>`).join("")}</select>`) : ""}`;
  }
  el.innerHTML = html;
  bindPanel(el);
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
      ${p ? `<i class="face" style="left:${p.x * 100}%;top:${p.face_y * 100}%;width:${p.face_h * (v ? 56 : 100) * 0.62}%;${p.stroke ? `box-shadow:0 0 0 2px ${col(p.stroke)}${p.glow ? `,0 0 10px 3px ${col(p.glow)}` : ""}` : p.glow ? `box-shadow:0 0 10px 3px ${col(p.glow)}` : ""}"></i>` : ""}
      <i class="tbox ${t.text?.style || ""}" style="left:${x0 * 100}%;top:${y0 * 100}%;width:${(x1 - x0) * 100}%;height:${(y1 - y0) * 100}%;--tc:${col(t.text?.color || "#fff")};--hc:${col(t.text?.hl || acc)};--bc:${col(t.text?.box_color || acc)};align-items:${{ left: "flex-start", right: "flex-end", center: "center" }[t.text?.align || "left"]};justify-content:center"><b></b><b class="h"></b></i>
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
      setPath(s, k, v);
      if (i.type === "range") { const b = i.closest(".th-f")?.querySelector("label b"); if (b) b.textContent = k === "bg.dim" ? Math.round(v * 100) + "%" : k === "bg.angle" ? v + "°" : k.endsWith("scale") ? (+v).toFixed(2) + "×" : v; }
      if (i.type === "color") { i.closest(".th-sw")?.querySelectorAll("button").forEach((b) => b.classList.remove("on")); }
      if (["logo", "flip"].includes(k) || (k === "cutout")) renderPanel();
      refresh();
    });
  });
  $$("[data-sw]", el).forEach((b) => (b.onclick = () => { setPath(s, b.dataset.sw, b.dataset.c); b.parentElement.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); const ci = b.parentElement.querySelector("input[type=color]"); if (ci) ci.value = b.dataset.c; refresh(); }));
  const tx = $("#th-text", el); if (tx) tx.oninput = () => { s.text = tx.value.split("\n").slice(0, 3).join("\n"); refresh(); };
  const sg = $("#th-sugg", el); if (sg) sg.onclick = () => suggest(false);
  $$("[data-sg]", el).forEach((b) => (b.onclick = () => { s.text = T.sugg.options[+b.dataset.sg]; renderPanel(); refresh(0); }));
  const rt = $("#th-reset-text", el); if (rt) rt.onclick = () => { for (const k of ["color", "hl", "accent", "font", "style", "text_scale"]) delete s[k]; renderPanel(); refresh(0); };
  $$("[data-tpl]", el).forEach((b) => (b.onclick = () => { s.template = b.dataset.tpl; delete s.labels; delete s.person_stroke; delete s.person_glow; delete s.accent; renderPanel(); refresh(0); }));
  $$("[data-label]", el).forEach((i) => (i.oninput = () => { const tp = tplOf(s.template); s.labels = (tp.labels || []).map((l, j) => (j === +i.dataset.label ? i.value : (s.labels || [])[j] || l.text)); refresh(); }));
  const t2 = $("#th-t2", el); if (t2) { t2.oninput = () => { $("#th-t2l", el).textContent = fmtT(+t2.value); }; t2.onchange = () => { s.t2 = +t2.value; refresh(0); }; }
  const bt = $("#th-bgtype", el); if (bt) bt.onchange = () => { s.bg = bt.value ? { ...(s.bg || {}), type: bt.value } : {}; renderPanel(); refresh(0); };
  $$("[data-bgimg]", el).forEach((b) => (b.onclick = () => { s.bg = { ...(s.bg || {}), type: "image", image_id: b.dataset.bgimg }; renderPanel(); refresh(0); }));
  const pst = $("#th-pst", el); if (pst) pst.onchange = () => { s.person_stroke = pst.checked ? "#FFFFFF" : ""; renderPanel(); refresh(0); };
  const pgl = $("#th-pgl", el); if (pgl) pgl.onchange = () => { s.person_glow = pgl.checked ? (s.accent || tplOf(s.template).accent) : ""; renderPanel(); refresh(0); };
  $$("[data-addshape]", el).forEach((b) => (b.onclick = () => { (s.stickers = s.stickers || []).push({ shape: b.dataset.addshape, x: 0.5, y: 0.5, w: b.dataset.addshape === "arrow" ? 0.2 : 0.15, rot: 0 }); renderPanel(); refresh(0); }));
  $$("[data-addstk]", el).forEach((b) => (b.onclick = () => { if ((s.stickers || []).length >= 8) return T.ctx.toast("ज़्यादा से ज़्यादा 8"); (s.stickers = s.stickers || []).push({ id: b.dataset.addstk, x: 0.15, y: 0.2, w: 0.14, rot: 0 }); renderPanel(); refresh(0); }));
  $$("[data-stk]", el).forEach((i) => (i.oninput = () => { s.stickers[+i.dataset.stk][i.dataset.sk] = +i.value; refresh(); }));
  $$("[data-delstk]", el).forEach((b) => (b.onclick = () => { s.stickers.splice(+b.dataset.delstk, 1); renderPanel(); refresh(0); }));
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

// ---------- preview ----------
function refresh(delay = 380) {
  if (!T || !T.ov?.has_video) return;
  clearTimeout(T.timer);
  T.timer = setTimeout(async () => {
    if (!T) return;
    T.abort?.abort(); T.abort = new AbortController();
    $("#th-busy", T.root).hidden = false;
    try {
      const { blob, headers } = await authBlob(`/projects/${T.pid}/thumbnails/preview`, { settings: T.s });
      if (!T) return;
      if (T.preview) URL.revokeObjectURL(T.preview);
      T.preview = URL.createObjectURL(blob);
      $("#th-img", T.root).src = T.preview; $("#th-dl", T.root).href = T.preview;
      let lint = {}; try { lint = JSON.parse(headers.get("x-thumb-lint") || "{}"); } catch {}
      T.lint = lint.warnings || []; T.info = lint.info || {};
      if (!T.s.t && T.info.t) T.s.t = T.info.t;
      renderLint();
    } catch (e) { if (e.name !== "AbortError" && T) { $("#th-lint", T.root).innerHTML = `<div class="note err">${T.ctx.esc(e.message)}</div>`; } }
    if (T) $("#th-busy", T.root).hidden = true;
  }, delay);
}
function renderLint() {
  const el = $("#th-lint", T.root); if (!el) return; const { esc } = T.ctx; const i = T.info || {};
  const ok = !T.lint.some((w) => w.level === "warn");
  el.innerHTML = `<div class="th-lintrow ${ok ? "ok" : ""}"><b>${ok ? "✓ अच्छा दिख रहा है" : "⚠ सुधार"}</b>
    <span class="small muted">${i.words ? `${i.words} शब्द · ` : ""}${i.font_px ? `अक्षर ${i.font_px}px · ` : ""}${i.contrast ? `contrast ${i.contrast}:1 · ` : ""}${i.cutout ? "cutout ✓" : "पूरा frame"}</span></div>
    ${T.lint.map((w) => `<div class="th-warn ${w.level}">${w.level === "warn" ? "⚠" : "ℹ"} ${esc(w.msg)}</div>`).join("")}`;
}

async function suggest(quiet) {
  const b = $("#th-sugg", T.root); if (b) { b.disabled = true; b.textContent = "सोच रहा…"; }
  try { T.sugg = await T.ctx.api("POST", `/projects/${T.pid}/thumbnails/text`, {}); if (!T) return;
    if (quiet && !T.s.text && T.sugg.options?.length) { T.s.text = T.sugg.options[0]; refresh(0); }
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
  $$("[data-svedit]", el).forEach((b) => (b.onclick = () => { const a = T.ov.saved.find((x) => x.id === b.dataset.svedit); if (!a?.meta?.settings) return; T.s = JSON.parse(JSON.stringify(a.meta.settings)); const r = $("#th-t", T.root); r.value = T.s.t || 0; $("#th-tl", T.root).textContent = fmtT(T.s.t); markFrames(); renderPanel(); refresh(0); T.ctx.toast("settings लोड हुईं — बदलें और फिर save करें"); }));
  $$("[data-svdel]", el).forEach((b) => (b.onclick = async () => { if (!confirm("यह thumbnail हटाएँ?")) return; await T.ctx.api("DELETE", `/projects/${T.pid}/thumbnails/${b.dataset.svdel}`); await reloadSaved(); }));
}
async function reloadSaved() { const ov = await T.ctx.api("GET", `/projects/${T.pid}/thumbnails`); if (!T) return; T.ov = { ...T.ov, saved: ov.saved, selected: ov.selected }; renderSaved(); }

async function save() {
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
