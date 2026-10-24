// Scenes / Storyboard — environments (classroom, clinic, shop…), characters placed by drag, dialogue
// lines per scene → "Explainer बनाओ" renders voices + lip-synced characters into a normal project.
let ctx = null;
let D = null;          // envs, props, clips, expressions, presets
let CH = null;         // characters (library + custom)
const SB = { title: "", preset: "yt-long", language: "hi", theme_id: "", scenes: [] };
const ST = { cur: 0, id: null, saved: [], busy: false, drag: null };

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const EXPR = { neutral: "सामान्य", happy: "खुश", sad: "उदास", angry: "गुस्सा", surprised: "हैरान", thinking: "सोच" };

const css = `
.sb-wrap{display:grid;grid-template-columns:230px minmax(0,1fr);gap:1rem}
@media(max-width:900px){.sb-wrap{grid-template-columns:1fr}}
.sb-list{display:flex;flex-direction:column;gap:.4rem}
.sb-item{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:.5rem .6rem;cursor:pointer;display:flex;gap:.4rem;align-items:center}
.sb-item.on{border-color:var(--amber)}.sb-item b{font-size:.82rem}.sb-item small{color:var(--muted);font-size:.7rem}
.sb-stage{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:.8rem}
.sb-prev{position:relative;background:#000;border-radius:10px;overflow:hidden;touch-action:none}
.sb-prev svg{display:block;width:100%;height:auto}
.sb-prev.tall{max-width:360px;margin:0 auto}
.sb-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.5rem;margin:.6rem 0}
.sb-row label{font-size:.72rem;color:var(--muted);display:flex;flex-direction:column;gap:.15rem}
.sb-row select,.sb-row input{background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:.35rem .4rem;font-size:.82rem;color:var(--text);min-width:0}
.sb-chars{display:flex;flex-wrap:wrap;gap:.4rem}
.sb-ch{display:flex;align-items:center;gap:.4rem;background:var(--bg);border:1px solid var(--line);border-radius:999px;padding:.2rem .6rem .2rem .3rem;font-size:.8rem}
.sb-ch img{width:26px;height:52px;object-fit:contain;border-radius:6px;background:#1f2632}
.sb-lines{list-style:none;margin:.4rem 0;padding:0;display:flex;flex-direction:column;gap:.4rem}
.sb-line{display:grid;grid-template-columns:120px minmax(0,1fr) 92px 100px auto;gap:.4rem;align-items:center}
@media(max-width:700px){.sb-line{grid-template-columns:1fr 1fr;}.sb-line textarea{grid-column:1/-1}}
.sb-line textarea,.sb-line select{background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:.35rem .45rem;font-size:.85rem;color:var(--text);min-width:0;font-family:inherit}
.sb-line textarea{resize:vertical;min-height:38px}
.sb-pick{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:50;display:flex;align-items:center;justify-content:center;padding:1rem}
.sb-pick>div{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:1rem;width:min(900px,100%);max-height:88vh;overflow:auto}
.sb-pgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(96px,1fr));gap:.5rem}
.sb-pgrid button{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:.3rem;cursor:pointer;color:var(--text);display:flex;flex-direction:column;align-items:center;gap:.2rem;min-width:0}
.sb-pgrid img{width:100%;aspect-ratio:1/2;object-fit:contain;background:#1f2632;border-radius:8px}.sb-pgrid b{font-size:.7rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
`;

export function view() {
  return `<div class="pghead"><div><h1>Scenes / Storyboard</h1><p class="muted">Scene चुनें, characters को खींचकर जगह दें, हर line लिखें कि कौन क्या बोलेगा — फिर «Explainer बनाओ»: आवाज़, lip-sync, captions सब अपने-आप; बाकी editing editor में।</p></div>
    <div class="row"><a class="btn" href="#/characters">👤 Characters</a><button class="btn" id="sb-open">📂 saved</button><button class="btn" id="sb-save">💾 save</button><button class="btn primary" id="sb-build">🎬 Explainer बनाओ</button></div></div>
    <div class="sb-row" style="margin-top:0"><label>Title<input id="sb-title" placeholder="जैसे: दाँतों की सफ़ाई"></label><label>Format<select id="sb-preset"><option value="yt-long">16:9 YouTube</option><option value="yt-short">9:16 Short</option><option value="ig-reel">9:16 Reel</option></select></label>
      <label>भाषा<select id="sb-lang"><option value="hi">हिंदी</option><option value="en">English</option></select></label><label>Theme<select id="sb-theme"><option value="">(कोई नहीं)</option></select></label>
      <label><input type="checkbox" id="sb-auto" style="width:auto"> बनते ही render भी कर दो</label></div>
    <div class="sb-wrap"><div><div class="sb-list" id="sb-list"></div><button class="btn small" id="sb-add" style="margin-top:.5rem;width:100%;justify-content:center">+ Scene</button></div><div class="sb-stage" id="sb-stage"></div></div>`;
}

export function bind(c) {
  ctx = c;
  if (!$("#sb-css")) { const st = document.createElement("style"); st.id = "sb-css"; st.textContent = css; document.head.appendChild(st); }
  $("#sb-title").oninput = (e) => (SB.title = e.target.value);
  $("#sb-preset").onchange = (e) => { SB.preset = e.target.value; renderStage(); };
  $("#sb-lang").onchange = (e) => (SB.language = e.target.value);
  $("#sb-theme").onchange = (e) => (SB.theme_id = e.target.value);
  $("#sb-add").onclick = () => { addScene(); };
  $("#sb-save").onclick = save;
  $("#sb-open").onclick = openSaved;
  $("#sb-build").onclick = build;
  load();
}

async function load() {
  try {
    [D, CH] = await Promise.all([ctx.api("GET", "/scenes/envs"), ctx.api("GET", "/chars")]);
    ctx.api("GET", "/presets/themes").then((t) => { const s = $("#sb-theme"); if (s) s.innerHTML += (t.themes || t || []).map((x) => `<option value="${esc(x.id)}">${esc(x.label || x.name)}</option>`).join(""); }).catch(() => {});
  } catch (e) { $("#sb-stage").innerHTML = `<div class="note err">${esc(e.message)}</div>`; return; }
  try { const d = JSON.parse(localStorage.getItem("vividora_sb_draft") || "null"); if (d && d.scenes?.length) Object.assign(SB, d); } catch {}
  let added = [];
  try { added = JSON.parse(localStorage.getItem("vividora_sb_add") || "[]"); localStorage.removeItem("vividora_sb_add"); } catch {}
  if (!SB.scenes.length) addScene(false);
  for (const a of added) SB.scenes[ST.cur].chars.push(placeChar(SB.scenes[ST.cur], a));
  $("#sb-title").value = SB.title; $("#sb-preset").value = SB.preset; $("#sb-lang").value = SB.language;
  renderList(); renderStage();
}

function draft() { try { localStorage.setItem("vividora_sb_draft", JSON.stringify(SB)); } catch {} }

function addScene(rerender = true) {
  SB.scenes.push({ env: "studio", framing: "wide", light: "day", title: "", hold: 0.6, chars: [], lines: [] });
  ST.cur = SB.scenes.length - 1;
  if (rerender) { renderList(); renderStage(); }
}

function allChars() { return [...(CH.custom || []), ...(CH.library || [])]; }
function placeChar(sc, a) {
  const env = D.envs.find((e) => e.id === sc.env) || D.envs[0];
  const slot = env.slots[sc.chars.length % env.slots.length];
  const prof = a.profile ? allChars().find((x) => x.id === a.profile) : null;
  return { profile: a.profile || null, params: a.params || prof?.params, name: a.name || prof?.name || "पात्र", x: slot[0], y: slot[1], s: slot[2], flip: sc.chars.length % 2 === 1, base: "idle", voice: "", expr: "neutral" };
}

function renderList() {
  $("#sb-list").innerHTML = SB.scenes.map((sc, i) => `<div class="sb-item ${i === ST.cur ? "on" : ""}" data-i="${i}"><span>${i + 1}.</span><div style="min-width:0"><b>${esc((D.envs.find((e) => e.id === sc.env) || {}).label || sc.env)}</b><br><small>${sc.chars.length} पात्र · ${sc.lines.length} lines</small></div></div>`).join("");
  $$(".sb-item").forEach((el) => (el.onclick = () => { ST.cur = +el.dataset.i; renderList(); renderStage(); }));
}

function renderStage() {
  const sc = SB.scenes[ST.cur]; if (!sc) return;
  const tall = SB.preset !== "yt-long";
  const st = $("#sb-stage");
  st.innerHTML = `<div class="sb-prev ${tall ? "tall" : ""}" id="sb-prev"><p class="small muted" style="padding:2rem;text-align:center">preview…</p></div>
    <div class="sb-row">
      <label>जगह<select data-s="env">${D.envs.map((e) => `<option value="${e.id}" ${sc.env === e.id ? "selected" : ""}>${esc(e.label)}</option>`).join("")}</select></label>
      <label>Camera<select data-s="framing">${D.framing.map((f) => `<option value="${f}" ${sc.framing === f ? "selected" : ""}>${{ wide: "दूर (wide)", medium: "बीच (medium)", close: "पास (close)" }[f] || f}</option>`).join("")}</select></label>
      <label>रोशनी<select data-s="light">${D.light.map((f) => `<option value="${f}" ${sc.light === f ? "selected" : ""}>${{ day: "दिन", evening: "शाम", night: "रात", warm: "गर्म", cool: "ठंडी" }[f] || f}</option>`).join("")}</select></label>
      <label>Title (ऊपर)<input data-s="title" value="${esc(sc.title || "")}" placeholder="वैकल्पिक"></label>
      <label>आख़िर में रुकें (s)<input data-s="hold" type="number" min="0" max="10" step=".1" value="${sc.hold ?? 0.6}"></label></div>
    <div class="row between"><b class="small">पात्र (preview में खींचकर रखें)</b><div class="row"><button class="btn small" id="sb-addch">+ पात्र</button>${SB.scenes.length > 1 ? `<button class="btn small danger" id="sb-delscene">scene हटाएँ</button>` : ""}</div></div>
    <div class="sb-chars" id="sb-chars">${sc.chars.map((ch, i) => `<span class="sb-ch"><img data-src="${ch.profile ? `/chars/${ch.profile}/preview.png?w=52&h=104` : ""}" alt=""><b>${esc(ch.name)}</b>
        <select data-chb="${i}" title="हरकत">${D.clips.map((c) => `<option value="${c.id}" ${ch.base === c.id ? "selected" : ""}>${esc(c.label)}</option>`).join("")}</select>
        <select data-chv="${i}" title="आवाज़"><option value="">आवाज़: auto</option>${(CH.voices || []).map((v) => `<option value="${v.id}" ${ch.voice === v.id ? "selected" : ""}>${esc(v.label)}</option>`).join("")}</select>
        <button class="btn small quiet" data-chflip="${i}" title="पलटें">⇄</button><button class="btn small quiet" data-chdel="${i}">✕</button></span>`).join("") || `<span class="small muted">अभी कोई पात्र नहीं — «+ पात्र» दबाएँ</span>`}</div>
    <div class="row between" style="margin-top:.8rem"><b class="small">Dialogue (कौन क्या बोले)</b><button class="btn small" id="sb-addline">+ line</button></div>
    <ul class="sb-lines" id="sb-lines">${sc.lines.map((ln, i) => `<li class="sb-line">
        <select data-lc="${i}">${sc.chars.map((ch, k) => `<option value="${k}" ${ln.char === k ? "selected" : ""}>${esc(ch.name)}</option>`).join("") || `<option value="0">(पात्र जोड़ें)</option>`}</select>
        <textarea data-lt="${i}" placeholder="यहाँ लिखें…">${esc(ln.text)}</textarea>
        <select data-le="${i}">${Object.entries(EXPR).map(([k, l]) => `<option value="${k}" ${(ln.expr || "neutral") === k ? "selected" : ""}>${l}</option>`).join("")}</select>
        <select data-lg="${i}">${D.clips.map((c) => `<option value="${c.id}" ${(ln.gesture || "talk") === c.id ? "selected" : ""}>${esc(c.label)}</option>`).join("")}</select>
        <span><button class="btn small quiet" data-lup="${i}" title="ऊपर">↑</button><button class="btn small quiet" data-ldel="${i}">✕</button></span></li>`).join("")}</ul>
    <p class="small muted">अनुमानित लंबाई: ${estimate(sc).toFixed(1)} s (पूरा video ≈ ${SB.scenes.reduce((a, s) => a + estimate(s), 0).toFixed(0)} s)</p>`;
  st.querySelectorAll("[data-s]").forEach((i) => (i.onchange = () => { const k = i.dataset.s; sc[k] = k === "hold" ? +i.value : i.value; if (k === "env") { const env = D.envs.find((e) => e.id === sc.env); sc.props = null; sc.chars.forEach((ch, n) => { const sl = env.slots[n % env.slots.length]; ch.x = sl[0]; ch.y = sl[1]; ch.s = sl[2]; }); } draft(); renderList(); renderStage(); }));
  $("#sb-addch").onclick = pickChar;
  if ($("#sb-delscene")) $("#sb-delscene").onclick = () => { SB.scenes.splice(ST.cur, 1); ST.cur = Math.max(0, ST.cur - 1); draft(); renderList(); renderStage(); };
  st.querySelectorAll("[data-chdel]").forEach((b) => (b.onclick = () => { sc.chars.splice(+b.dataset.chdel, 1); sc.lines.forEach((l) => (l.char = Math.min(l.char, Math.max(0, sc.chars.length - 1)))); draft(); renderList(); renderStage(); }));
  st.querySelectorAll("[data-chflip]").forEach((b) => (b.onclick = () => { const ch = sc.chars[+b.dataset.chflip]; ch.flip = !ch.flip; draft(); preview(); }));
  st.querySelectorAll("[data-chb]").forEach((s) => (s.onchange = () => { sc.chars[+s.dataset.chb].base = s.value; draft(); }));
  st.querySelectorAll("[data-chv]").forEach((s) => (s.onchange = () => { sc.chars[+s.dataset.chv].voice = s.value; draft(); }));
  $("#sb-addline").onclick = () => { sc.lines.push({ char: 0, text: "", expr: "neutral", gesture: "talk" }); draft(); renderStage(); $$("[data-lt]").pop()?.focus(); };
  st.querySelectorAll("[data-lt]").forEach((t) => (t.oninput = () => { sc.lines[+t.dataset.lt].text = t.value; draft(); }));
  st.querySelectorAll("[data-lc]").forEach((s) => (s.onchange = () => { sc.lines[+s.dataset.lc].char = +s.value; draft(); }));
  st.querySelectorAll("[data-le]").forEach((s) => (s.onchange = () => { sc.lines[+s.dataset.le].expr = s.value; draft(); }));
  st.querySelectorAll("[data-lg]").forEach((s) => (s.onchange = () => { sc.lines[+s.dataset.lg].gesture = s.value; draft(); }));
  st.querySelectorAll("[data-ldel]").forEach((b) => (b.onclick = () => { sc.lines.splice(+b.dataset.ldel, 1); draft(); renderStage(); }));
  st.querySelectorAll("[data-lup]").forEach((b) => (b.onclick = () => { const i = +b.dataset.lup; if (i > 0) { [sc.lines[i - 1], sc.lines[i]] = [sc.lines[i], sc.lines[i - 1]]; draft(); renderStage(); } }));
  st.querySelectorAll("img[data-src]").forEach((im) => { if (im.dataset.src) authImg(im.dataset.src).then((u) => (im.src = u)).catch(() => {}); });
  preview();
}

function estimate(sc) { const t = sc.lines.reduce((a, l) => a + Math.max(0.5, l.text.length / 14) + 0.35, 0); return Math.max(2, t) + (+sc.hold || 0); }

const blobCache = new Map();
async function authImg(path) {
  if (blobCache.has(path)) return blobCache.get(path);
  const r = await fetch("/api" + path, { headers: { authorization: "Bearer " + ctx.S.token } });
  if (!r.ok) throw new Error("image");
  const u = URL.createObjectURL(await r.blob()); blobCache.set(path, u); return u;
}

let pvTimer = null;
function preview() {
  clearTimeout(pvTimer);
  pvTimer = setTimeout(async () => {
    const sc = SB.scenes[ST.cur]; const box = $("#sb-prev"); if (!sc || !box) return;
    const tall = SB.preset !== "yt-long";
    try {
      const r = await fetch("/api/scenes/render", { method: "POST", headers: { authorization: "Bearer " + ctx.S.token, "content-type": "application/json" },
        body: JSON.stringify({ scene: { ...sc, chars: sc.chars.map((c) => ({ ...c, pose: { viseme: "rest", expr: c.expr || "neutral" } })) }, w: tall ? 540 : 960, h: tall ? 960 : 540 }) });
      if (!r.ok) { const d = await r.json().catch(() => ({})); box.innerHTML = `<div class="note err">${esc(d.error || "preview नहीं बना")}</div>`; return; }
      box.innerHTML = await r.text();
      bindDrag(box.querySelector("svg"), sc);
    } catch (e) { box.innerHTML = `<div class="note err">${esc(e.message)}</div>`; }
  }, 150);
}

function bindDrag(svg, sc) {
  if (!svg) return;
  const vb = svg.viewBox.baseVal;
  svg.querySelectorAll("[data-char]").forEach((g) => {
    g.addEventListener("pointerdown", (e) => {
      e.preventDefault(); g.setPointerCapture(e.pointerId);
      const i = +g.dataset.char; const ch = sc.chars[i]; const r = svg.getBoundingClientRect();
      const sx = vb.width / r.width, sy = vb.height / r.height; const x0 = ch.x, y0 = ch.y, px = e.clientX, py = e.clientY;
      const wide = (sc.framing || "wide") === "wide";
      const move = (ev) => {
        if (wide) { ch.x = Math.min(1, Math.max(0, x0 + (ev.clientX - px) * sx / 1920)); ch.y = Math.min(1.05, Math.max(0.6, y0 + (ev.clientY - py) * sy / 1080));
          g.setAttribute("transform", g.getAttribute("transform").replace(/translate\([^)]*\)/, `translate(${(ch.x * 1920 - 200 * cs(ch)).toFixed(1)},${(ch.y * 1080 - 760 * cs(ch)).toFixed(1)})`)); }
        else { ch.x = Math.min(1, Math.max(0, x0 + (ev.clientX - px) / r.width)); ch.y = Math.min(1.0, Math.max(0.6, y0 + (ev.clientY - py) / r.height * 0.4));
          g.setAttribute("transform", g.getAttribute("transform").replace(/translate\(([^,]+),([^)]+)\)/, (m, a, b) => `translate(${(+a + (ev.clientX - (move.lx ?? px)) * sx).toFixed(1)},${(+b + (ev.clientY - (move.ly ?? py)) * sy).toFixed(1)})`)); move.lx = ev.clientX; move.ly = ev.clientY; }
      };
      const up = () => { g.removeEventListener("pointermove", move); g.removeEventListener("pointerup", up); draft(); preview(); };
      g.addEventListener("pointermove", move); g.addEventListener("pointerup", up);
    });
    g.addEventListener("wheel", (e) => { e.preventDefault(); const ch = sc.chars[+g.dataset.char]; ch.s = Math.min(1.8, Math.max(0.4, (ch.s || 1) * (e.deltaY < 0 ? 1.06 : 0.94))); draft(); preview(); }, { passive: false });
  });
}
function cs(ch) { return (ch.s || 1) * (0.55 + 0.45 * ch.y) * (1080 / 800) * 0.70; }

function pickChar() {
  const sc = SB.scenes[ST.cur];
  const m = document.createElement("div"); m.className = "sb-pick";
  const list = allChars();
  m.innerHTML = `<div><div class="row between"><h3 style="margin:0">पात्र चुनें</h3><input id="sb-pq" placeholder="खोजें…" style="flex:1;max-width:260px;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:.4rem .6rem"><button class="btn small" id="sb-px">✕</button></div>
    <div class="sb-pgrid" id="sb-pg" style="margin-top:.6rem"></div></div>`;
  document.body.appendChild(m);
  const draw = (q) => { const l = list.filter((p) => !q || (p.label + " " + (p.profession || "")).toLowerCase().includes(q.toLowerCase())).slice(0, 80);
    $("#sb-pg", m).innerHTML = l.map((p) => `<button data-id="${p.id}"><img data-src="/chars/${p.id}/preview.png?w=96&h=192&expr=happy" alt=""><b>${esc(p.name)}</b><small style="font-size:.62rem;color:var(--muted);white-space:nowrap;overflow:hidden;max-width:100%">${esc(p.profession || "")}</small></button>`).join("");
    $$("button[data-id]", m).forEach((b) => (b.onclick = () => { const p = list.find((x) => x.id === b.dataset.id); sc.chars.push(placeChar(sc, { profile: p.id, params: p.params, name: p.name })); if (!sc.lines.length) sc.lines.push({ char: sc.chars.length - 1, text: "", expr: "neutral", gesture: "talk" }); m.remove(); draft(); renderList(); renderStage(); }));
    $$("img[data-src]", m).forEach((im) => authImg(im.dataset.src).then((u) => (im.src = u)).catch(() => {})); };
  draw(""); $("#sb-pq", m).oninput = (e) => draw(e.target.value); $("#sb-px", m).onclick = () => m.remove();
}

function spec() { return { ...SB, title: SB.title || "Explainer", scenes: SB.scenes.map((s) => ({ ...s, lines: s.lines.filter((l) => l.text.trim()) })) }; }

async function save() {
  try { const r = await ctx.api("POST", "/storyboards", { id: ST.id, name: SB.title || "Storyboard", spec: spec() }); ST.id = r.id; ctx.toast("storyboard save हुआ"); } catch (e) { ctx.toast(e.message); }
}

async function openSaved() {
  try { ST.saved = await ctx.api("GET", "/storyboards"); } catch (e) { return ctx.toast(e.message); }
  const m = document.createElement("div"); m.className = "sb-pick";
  m.innerHTML = `<div><div class="row between"><h3 style="margin:0">Saved storyboards</h3><button class="btn small" id="sb-px">✕</button></div>
    <ul class="plist" style="list-style:none;padding:0;margin-top:.6rem">${ST.saved.map((s) => `<li class="row between" style="padding:.4rem 0;border-bottom:1px solid var(--line)"><span><b>${esc(s.name)}</b> <span class="small muted">${s.scenes} scenes${s.project_id ? ` · <a href="#/projects/${s.project_id}">project</a>` : ""}</span></span><span><button class="btn small" data-open="${s.id}">खोलें</button> <button class="btn small quiet" data-del="${s.id}">✕</button></span></li>`).join("") || "<li class='small muted'>कुछ save नहीं है</li>"}</ul></div>`;
  document.body.appendChild(m);
  $("#sb-px", m).onclick = () => m.remove();
  $$("[data-open]", m).forEach((b) => (b.onclick = () => { const s = ST.saved.find((x) => x.id === b.dataset.open); if (s?.spec) { Object.assign(SB, { title: s.spec.title || s.name, preset: s.spec.preset || "yt-long", language: s.spec.language || "hi", theme_id: s.spec.theme_id || "", scenes: s.spec.scenes || [] }); ST.id = s.id; ST.cur = 0; $("#sb-title").value = SB.title; $("#sb-preset").value = SB.preset; $("#sb-lang").value = SB.language; draft(); renderList(); renderStage(); } m.remove(); }));
  $$("[data-del]", m).forEach((b) => (b.onclick = async () => { await ctx.api("DELETE", `/storyboards/${b.dataset.del}`).catch(() => {}); m.remove(); openSaved(); }));
}

async function build() {
  const s = spec();
  if (!s.scenes.some((sc) => sc.lines.length)) return ctx.toast("कम से कम एक line लिखें");
  if (!s.scenes.every((sc) => sc.chars.length || !sc.lines.length)) return ctx.toast("जिस scene में lines हैं उसमें पात्र भी जोड़ें");
  const b = $("#sb-build"); b.disabled = true; b.textContent = "बन रहा है…";
  try {
    const r = await ctx.api("POST", "/storyboards/build", { storyboard: s, title: s.title, auto_render: $("#sb-auto").checked, storyboard_id: ST.id, channel_id: ctx.S.channel || undefined });
    ctx.toast("explainer बन रहा है — आवाज़ और characters तैयार होते ही editor में दिखेगा");
    localStorage.removeItem("vividora_sb_draft");
    ctx.go("/projects/" + r.project_id);
  } catch (e) { ctx.toast(e.message); b.disabled = false; b.textContent = "🎬 Explainer बनाओ"; }
}
