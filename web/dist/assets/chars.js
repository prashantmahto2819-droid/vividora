// Character Studio — 200 built-in characters, a customiser (age, skin, hair, outfit, props…), pose
// clips with lip-sync preview, and "Scene में भेजें". Everything is drawn by the server
// (engine/chars/rig.py) so the preview here is exactly what the render makes.
let ctx = null;
let D = null;          // {library, custom, options, clips, voices}
const ST = { cat: "", q: "", sel: null, params: null, expr: "neutral", clip: "talk", svgUrl: "", busy: false, say: "" };

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const css = `
.ch-wrap{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:1rem}
@media(max-width:900px){.ch-wrap{grid-template-columns:1fr}}
.ch-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:.6rem}
.ch-card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:.4rem;cursor:pointer;text-align:center;display:flex;flex-direction:column;align-items:center;gap:.2rem;min-width:0}
.ch-card.on{border-color:var(--amber);box-shadow:0 0 0 1px var(--amber)}
.ch-card img{width:100%;aspect-ratio:1/2;object-fit:contain;background:linear-gradient(#1f2632,#171c25);border-radius:8px}
.ch-card b{font-size:.78rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.ch-card small{font-size:.68rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.ch-side{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:.8rem;position:sticky;top:.5rem;max-height:calc(100dvh - 1rem);overflow:auto}
.ch-prev{display:flex;gap:.6rem;align-items:flex-start}
.ch-prev img,.ch-prev video{width:150px;aspect-ratio:1/2;object-fit:contain;background:repeating-conic-gradient(#1b2130 0 25%,#222a38 0 50%) 50%/16px 16px;border-radius:10px}
.ch-opts{display:grid;grid-template-columns:1fr 1fr;gap:.4rem .6rem}
.ch-opts label{font-size:.72rem;color:var(--muted);display:flex;flex-direction:column;gap:.15rem}
.ch-opts select,.ch-opts input{background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:.3rem .4rem;font-size:.8rem;color:var(--text);min-width:0}
.ch-sw{display:flex;flex-wrap:wrap;gap:.3rem}.ch-sw i{width:22px;height:22px;border-radius:50%;border:2px solid transparent;cursor:pointer;display:inline-block}.ch-sw i.on{border-color:#fff}
.ch-chips{display:flex;flex-wrap:wrap;gap:.3rem}.ch-chips button{background:rgba(255,255,255,.06);border:1px solid var(--line);color:var(--text);border-radius:999px;padding:.15rem .6rem;font-size:.72rem;cursor:pointer}.ch-chips button.on{background:var(--amber);color:#111;border-color:var(--amber)}
.ch-sheet{width:100%;border-radius:8px;background:#121722;margin-top:.4rem}
`;

export function view() {
  return `<div class="pghead"><div><h1>Characters</h1><p class="muted">200 तैयार पात्र — डॉक्टर, दुकानदार, शिक्षक, जिम ट्रेनर, त्योहार के कपड़े… किसी को चुनकर रंग-रूप बदलें, बोलते हुए देखें, फिर Scene में भेजें।</p></div>
    <div class="row"><a class="btn" href="#/scenes">🎬 Scenes / Storyboard</a></div></div>
    <div class="ch-wrap"><div id="ch-left"><p class="small muted">लोड हो रहा है…</p></div><div class="ch-side" id="ch-side"><p class="small muted">बाएँ से कोई character चुनें।</p></div></div>`;
}

export function bind(c) {
  ctx = c;
  if (!$("#ch-css")) { const st = document.createElement("style"); st.id = "ch-css"; st.textContent = css; document.head.appendChild(st); }
  load();
}

async function load() {
  try { D = await ctx.api("GET", "/chars"); } catch (e) { $("#ch-left").innerHTML = `<div class="note err">${esc(e.message)}</div>`; return; }
  const want = (location.hash.match(/char=([a-z0-9]+)/) || [])[1];
  renderLeft();
  if (want) pick(want);
}

function all() { return [...(D.custom || []), ...(D.library || [])]; }

function renderLeft() {
  const cats = D.options.categories;
  const list = all().filter((p) => (!ST.cat || p.category === ST.cat || (ST.cat === "custom" && p.custom)) && (!ST.q || (p.label + " " + (p.profession || "")).toLowerCase().includes(ST.q.toLowerCase())));
  $("#ch-left").innerHTML = `<div class="row" style="margin-bottom:.6rem"><input id="ch-q" placeholder="खोजें: डॉक्टर, साड़ी, बच्चा…" value="${esc(ST.q)}" style="flex:1;min-width:160px;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:.45rem .6rem">
      <div class="ch-chips"><button data-cat="" class="${ST.cat ? "" : "on"}">सब</button>${D.custom?.length ? `<button data-cat="custom" class="${ST.cat === "custom" ? "on" : ""}">मेरे (${D.custom.length})</button>` : ""}${Object.entries(cats).map(([k, v]) => `<button data-cat="${k}" class="${ST.cat === k ? "on" : ""}">${esc(v)}</button>`).join("")}</div></div>
    <div class="ch-grid">${list.map((p) => `<div class="ch-card ${ST.sel === p.id ? "on" : ""}" data-id="${p.id}"><img loading="lazy" data-src="/chars/${p.id}/preview.png?w=120&h=240&expr=happy" alt=""><b>${esc(p.name)}</b><small>${esc(p.profession || p.label)}</small></div>`).join("")}</div>
    <p class="small muted" style="margin-top:.5rem">${list.length} characters</p>`;
  $("#ch-q").oninput = (e) => { ST.q = e.target.value; renderLeft(); };
  $$("[data-cat]").forEach((b) => (b.onclick = () => { ST.cat = b.dataset.cat; renderLeft(); }));
  $$(".ch-card").forEach((el) => (el.onclick = () => pick(el.dataset.id)));
  lazy();
}

const blobCache = new Map();
async function authImg(path) {
  if (blobCache.has(path)) return blobCache.get(path);
  const r = await fetch("/api" + path, { headers: { authorization: "Bearer " + ctx.S.token } });
  if (!r.ok) throw new Error("image");
  const u = URL.createObjectURL(await r.blob());
  blobCache.set(path, u);
  return u;
}
function lazy() {
  const io = new IntersectionObserver((es) => { es.forEach((en) => { if (en.isIntersecting) { const im = en.target; io.unobserve(im); authImg(im.dataset.src).then((u) => (im.src = u)).catch(() => {}); } }); }, { rootMargin: "300px" });
  $$("img[data-src]").forEach((im) => io.observe(im));
}

function pick(id) {
  const p = all().find((x) => x.id === id);
  if (!p) return;
  ST.sel = id; ST.params = { ...p.params }; ST.base = p;
  $$(".ch-card").forEach((el) => el.classList.toggle("on", el.dataset.id === id));
  renderSide();
}

function sel(key, table, label, pairs = false) {
  const v = ST.params[key];
  const opts = Array.isArray(table) ? table.map((k) => [k, k]) : Object.entries(table).map(([k, o]) => [k, typeof o === "string" ? o : o.label]);
  return `<label>${label}<select data-p="${key}">${opts.map(([k, l]) => `<option value="${k}" ${k === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>`;
}

function renderSide() {
  const o = D.options, p = ST.params, base = ST.base;
  const side = $("#ch-side");
  side.innerHTML = `<div class="row between"><h3 style="margin:0">${esc(base.name)}</h3><span class="small muted">${esc(base.profession || "")}</span></div>
    <div class="ch-prev" style="margin:.5rem 0"><img id="ch-img" alt=""><div style="flex:1;min-width:0">
      <label class="small muted">भाव</label><div class="ch-chips" id="ch-expr">${o.expressions.map((e) => `<button data-expr="${e}" class="${ST.expr === e ? "on" : ""}">${{ neutral: "सामान्य", happy: "खुश", sad: "उदास", angry: "गुस्सा", surprised: "हैरान", thinking: "सोच" }[e] || e}</button>`).join("")}</div>
      <label class="small muted" style="margin-top:.4rem;display:block">Animation</label><select id="ch-clip" style="width:100%">${D.clips.map((c) => `<option value="${c.id}" ${ST.clip === c.id ? "selected" : ""}>${esc(c.label)}</option>`).join("")}</select>
      <input id="ch-say" placeholder="बोलकर दिखाओ: नमस्ते दोस्तों…" value="${esc(ST.say)}" style="width:100%;margin-top:.4rem;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:.3rem .4rem;font-size:.8rem">
      <button class="btn small" id="ch-play" style="margin-top:.4rem;width:100%;justify-content:center">▶ चलाकर देखें</button>
      <video id="ch-vid" hidden autoplay loop muted playsinline style="width:100%;margin-top:.4rem"></video></div></div>
    <img class="ch-sheet" id="ch-sheet" alt="">
    <details open style="margin-top:.6rem"><summary class="small" style="cursor:pointer;font-weight:600">रंग-रूप बदलें</summary>
    <div class="ch-opts" style="margin-top:.5rem">
      ${sel("age", o.ages, "उम्र")}${sel("gender", o.genders, "पुरुष / महिला")}${sel("body", o.bodies, "शरीर")}${sel("hair", o.hair, "बाल")}
      ${sel("hair_color", o.hair_colors, "बालों का रंग")}${sel("facial", o.facial, "दाढ़ी-मूँछ")}${sel("outfit", o.outfits, "पोशाक")}${sel("prop", o.props, "हाथ में")}${sel("hat", o.hats, "सिर पर")}
      <label>कपड़े का रंग<input type="color" data-p="top" value="${esc(p.top || "#3B82C4")}"></label>
      <label>जूते<input type="color" data-p="shoes" value="${esc(p.shoes || "#2B2B2B")}"></label>
    </div>
    <label class="small muted" style="display:block;margin-top:.5rem">त्वचा</label><div class="ch-sw">${o.skin.map((s) => `<i style="background:${s}" data-skin="${s}" class="${p.skin === s ? "on" : ""}"></i>`).join("")}</div>
    <label class="small muted" style="display:block;margin-top:.5rem">सामान</label><div class="ch-chips">${Object.entries(o.accessories).map(([k, l]) => `<button data-acc="${k}" class="${(p.accessories || []).includes(k) ? "on" : ""}">${esc(l)}</button>`).join("")}</div>
    </details>
    <div class="row" style="margin-top:.8rem"><input id="ch-name" value="${esc(p.name || base.name)}" placeholder="नाम" style="flex:1;min-width:120px;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:.4rem .5rem">
      <button class="btn small" id="ch-save">💾 मेरा character बनाएँ</button>${base.custom ? `<button class="btn small danger" id="ch-del">हटाएँ</button>` : ""}</div>
    <div class="row" style="margin-top:.5rem"><button class="btn primary small" id="ch-scene">🎬 Scene में भेजें</button><span class="small muted">आवाज़ सुझाव: ${esc(voiceFor(p))}</span></div>`;
  side.querySelectorAll("[data-p]").forEach((i) => (i.onchange = () => { ST.params[i.dataset.p] = i.value; preview(); }));
  side.querySelectorAll("[data-skin]").forEach((i) => (i.onclick = () => { ST.params.skin = i.dataset.skin; side.querySelectorAll("[data-skin]").forEach((x) => x.classList.toggle("on", x === i)); preview(); }));
  side.querySelectorAll("[data-acc]").forEach((b) => (b.onclick = () => { const a = new Set(ST.params.accessories || []); a.has(b.dataset.acc) ? a.delete(b.dataset.acc) : a.add(b.dataset.acc); ST.params.accessories = [...a]; b.classList.toggle("on"); preview(); }));
  side.querySelectorAll("[data-expr]").forEach((b) => (b.onclick = () => { ST.expr = b.dataset.expr; side.querySelectorAll("[data-expr]").forEach((x) => x.classList.toggle("on", x === b)); preview(); }));
  $("#ch-clip").onchange = (e) => { ST.clip = e.target.value; sheet(); };
  $("#ch-say").oninput = (e) => (ST.say = e.target.value);
  $("#ch-play").onclick = playClip;
  $("#ch-save").onclick = save;
  if ($("#ch-del")) $("#ch-del").onclick = del;
  $("#ch-scene").onclick = () => { try { const d = JSON.parse(localStorage.getItem("vividora_sb_add") || "[]"); d.push({ profile: ST.base.custom || unchanged() ? ST.sel : null, params: ST.params, name: $("#ch-name").value || ST.base.name }); localStorage.setItem("vividora_sb_add", JSON.stringify(d.slice(-6))); } catch {} ctx.go("/scenes"); };
  preview(); sheet();
}

function unchanged() { return JSON.stringify(ST.params) === JSON.stringify(ST.base.params); }

function voiceFor(p) {
  const v = D.voices || [];
  const g = p.gender === "f" ? "f" : "m";
  const want = g === "f" ? (p.age === "child" || p.age === "young" ? "hi_divya_energetic" : "hi_divya_soft") : (p.age === "young" ? "hi_rohit_energetic" : p.age === "elderly" ? "hi_aman_story" : "hi_rohit_deep");
  return (v.find((x) => x.id === want) || {}).label || want;
}

let pvTimer = null;
function preview() {
  clearTimeout(pvTimer);
  pvTimer = setTimeout(async () => {
    try {
      const r = await fetch("/api/chars/render", { method: "POST", headers: { authorization: "Bearer " + ctx.S.token, "content-type": "application/json" },
        body: JSON.stringify({ params: ST.params, pose: { expr: ST.expr, viseme: ST.expr === "surprised" ? "OO" : "rest" }, w: 300, h: 600 }) });
      if (!r.ok) { const d = await r.json().catch(() => ({})); return ctx.toast(d.error || "preview नहीं बना"); }
      const u = URL.createObjectURL(await r.blob());
      if (ST.svgUrl) URL.revokeObjectURL(ST.svgUrl);
      ST.svgUrl = u; const im = $("#ch-img"); if (im) im.src = u;
    } catch (e) { ctx.toast(e.message); }
  }, 120);
}

async function sheet() {
  const im = $("#ch-sheet"); if (!im) return;
  if (!unchanged() && !ST.base.custom) { im.hidden = true; return; }
  im.hidden = false;
  try { im.src = await authImg(`/chars/${ST.sel}/sheet.png?clip=${ST.clip}`); } catch { im.hidden = true; }
}

async function playClip() {
  const v = $("#ch-vid"), b = $("#ch-play");
  let id = ST.sel;
  if (!unchanged() && !ST.base.custom) { ctx.toast("पहले «मेरा character बनाएँ» दबाएँ, फिर animation चलेगी"); return; }
  b.disabled = true; b.textContent = "बन रहा है…";
  try {
    const q = `clip=${ST.clip}&dur=3&expr=${ST.expr}${ST.say ? "&say=" + encodeURIComponent(ST.say) : ""}`;
    v.src = await authImg(`/chars/${id}/clip.webm?${q}`); v.hidden = false; $("#ch-img").hidden = true;
  } catch (e) { ctx.toast("clip नहीं बना"); }
  b.disabled = false; b.textContent = "▶ चलाकर देखें";
}

async function save() {
  const name = $("#ch-name").value.trim() || ST.base.name;
  try {
    const r = await ctx.api("POST", "/chars", { id: ST.base.custom ? ST.sel : undefined, name, params: { ...ST.params, name }, base: ST.base.custom ? ST.base.base : ST.sel, profession: ST.base.profession, category: ST.base.category });
    ctx.toast("save हो गया — अब Scene में इस्तेमाल करें");
    D = await ctx.api("GET", "/chars"); ST.cat = ""; renderLeft(); pick(r.id);
  } catch (e) { ctx.toast(e.message); }
}

async function del() {
  if (!confirm("यह character हटाएँ?")) return;
  try { await ctx.api("DELETE", `/chars/${ST.sel}`); D = await ctx.api("GET", "/chars"); ST.sel = null; renderLeft(); $("#ch-side").innerHTML = `<p class="small muted">हट गया।</p>`; } catch (e) { ctx.toast(e.message); }
}
