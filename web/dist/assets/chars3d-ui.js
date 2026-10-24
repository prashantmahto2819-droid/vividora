// 3D Studio — Characters page (#/characters3d): pick one of 60 profiles, customise, animate, write lines → lip-synced
// transparent clip in the library. Live preview runs in the browser (three.js); the final render runs on the worker.
import { buildShot, visemeTrack, OUTFITS, HAIR, SKIN, PROPS, EXPRESSIONS } from "./chars3d.js";

export const CSS = `
.c3d{display:grid;grid-template-columns:260px minmax(0,1fr) 330px;gap:1rem;min-height:70vh}
.c3d.sb{grid-template-columns:minmax(0,1fr) 380px}
.c3d-list{max-height:78vh;overflow:auto;display:grid;grid-template-columns:1fr 1fr;gap:.4rem;align-content:start}
.c3d-prof{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:.3rem;cursor:pointer;text-align:center;font-size:.72rem;min-width:0}
.c3d-prof.on{border-color:var(--amber);box-shadow:0 0 0 1px var(--amber)}
.c3d-prof img{width:100%;aspect-ratio:3/4;object-fit:contain;background:radial-gradient(#2a3140,#161b25);border-radius:6px;display:block}
.c3d-prof span{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:.2rem}
.c3d-stage{background:#0f1319;border:1px solid var(--line);border-radius:12px;position:relative;min-height:420px;display:flex;align-items:center;justify-content:center;overflow:hidden}
.c3d-stage canvas{max-width:100%;max-height:70vh;cursor:grab;touch-action:none}
.c3d-side{max-height:78vh;overflow:auto;padding-right:.2rem}
.c3d-side .field{margin-bottom:.55rem}.c3d-side label{font-size:.78rem}
.c3d-row{display:flex;gap:.4rem;flex-wrap:wrap}.c3d-row .field{flex:1;min-width:110px}
.c3d-sw{display:inline-block;width:22px;height:22px;border-radius:50%;border:2px solid transparent;cursor:pointer;margin:2px}.c3d-sw.on{border-color:#fff}
.c3d-jobs{list-style:none;margin:0;padding:0}.c3d-jobs li{display:flex;gap:.5rem;align-items:center;padding:.35rem 0;border-bottom:1px solid var(--line);font-size:.8rem;flex-wrap:wrap}
.c3d-jobs .progress{height:4px;background:var(--line);border-radius:2px;overflow:hidden;flex:1;min-width:60px}.c3d-jobs .progress i{display:block;height:100%;background:var(--amber)}
.c3d-cat{margin:.4rem 0 .2rem;font-size:.7rem;color:var(--muted);grid-column:1/-1;text-transform:uppercase;letter-spacing:.05em}
.c3d-lines textarea{width:100%;min-height:90px;font-size:.85rem}
.sb-scene{border:1px solid var(--line);border-radius:10px;padding:.6rem;margin-bottom:.6rem;background:var(--panel)}
.sb-scene .c3d-row .field{min-width:130px}
.sb-char{display:flex;gap:.4rem;align-items:center;flex-wrap:wrap;margin:.2rem 0}
.sb-lines textarea{width:100%;min-height:70px;font-size:.85rem}
@media (max-width:1100px){.c3d{grid-template-columns:200px minmax(0,1fr)}.c3d.sb{grid-template-columns:minmax(0,1fr)}.c3d-side{grid-column:1/-1;max-height:none}}
@media (max-width:700px){.c3d,.c3d.sb{grid-template-columns:1fr}.c3d-list{grid-template-columns:repeat(3,1fr);max-height:28vh}.c3d-stage{min-height:300px}.c3d-stage canvas{max-height:46vh}}
`;
let U = null;

export function injectCss() { if (!document.getElementById("c3d-css")) { const st = document.createElement("style"); st.id = "c3d-css"; st.textContent = CSS; document.head.appendChild(st); } }
export const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
export const hex = (n) => "#" + (n >>> 0).toString(16).padStart(6, "0").slice(-6);

/** Live preview: one renderer, rebuilt on spec change; drag = orbit, wheel = zoom. */
export function livePreview(container, { width = 640, height = 720 } = {}) {
  const canvas = document.createElement("canvas"); canvas.width = width; canvas.height = height; container.appendChild(canvas);
  const P = { canvas, shot: null, raf: 0, t0: performance.now(), az: 0, el: 0.15, dist: null, drag: null, paused: false };
  const loop = () => {
    P.raf = requestAnimationFrame(loop);
    if (!P.shot || P.paused) return;
    const t = (performance.now() - P.t0) / 1000;
    P.shot.update(t);
    const cam = P.shot.camera, tg = cam.userData.target;
    if (P.dist == null) P.dist = cam.position.distanceTo(tg);
    cam.position.set(tg.x + Math.sin(P.az) * Math.cos(P.el) * P.dist, tg.y + Math.sin(P.el) * P.dist, tg.z + Math.cos(P.az) * Math.cos(P.el) * P.dist); cam.lookAt(tg);
    P.shot.render();
  };
  canvas.addEventListener("pointerdown", (e) => { P.drag = { x: e.clientX, y: e.clientY, az: P.az, el: P.el }; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener("pointermove", (e) => { if (!P.drag) return; P.az = P.drag.az - (e.clientX - P.drag.x) * 0.01; P.el = Math.max(-0.6, Math.min(1.2, P.drag.el + (e.clientY - P.drag.y) * 0.006)); });
  canvas.addEventListener("pointerup", () => (P.drag = null));
  canvas.addEventListener("wheel", (e) => { e.preventDefault(); P.dist = Math.max(0.8, Math.min(12, (P.dist || 3) * (e.deltaY > 0 ? 1.08 : 0.92))); }, { passive: false });
  P.set = (spec) => { try { P.shot?.renderer.dispose(); } catch {} P.shot = buildShot({ ...spec, width, height }, canvas); P.t0 = performance.now(); P.dist = null; P.az = 0; P.el = 0.15; };
  P.destroy = () => { cancelAnimationFrame(P.raf); try { P.shot?.renderer.dispose(); } catch {} canvas.remove(); };
  loop();
  return P;
}

export function jobsList(ul, jobs, api, onChange) {
  ul.innerHTML = jobs.length ? jobs.map((j) => `<li><span style="min-width:70px">${j.kind === "char3d" ? "🧍" : "🎬"} ${esc(j.payload?.name || j.payload?.title || "")}</span>${j.status === "running" || j.status === "queued" ? `<div class="progress"><i style="width:${j.progress || 0}%"></i></div><span class="muted">${esc(j.message || (j.status === "queued" ? "कतार में" : j.status))}</span><button class="btn small quiet" data-cancel="${j.id}">✕</button>` : j.status === "done" ? (j.item ? `<a class="btn small" href="${j.item.url}" target="_blank" rel="noopener">▶ देखें</a><span class="muted small">library में · ${Number(j.result?.duration || 0).toFixed(1)}s</span>` : j.project_id ? `<a class="btn small primary" href="#/projects/${j.project_id}">project खोलें →</a>` : "✓") : `<span class="muted">${esc(String(j.error || j.status).slice(0, 90))}</span>`}</li>`).join("") : `<li class="muted">अभी कोई 3D job नहीं</li>`;
  ul.querySelectorAll("[data-cancel]").forEach((b) => (b.onclick = async () => { await api("POST", `/chars3d/jobs/${b.dataset.cancel}/cancel`).catch(() => {}); onChange(); }));
}

export async function mountStudio(root, ctx) {
  injectCss();
  const { api, toast } = ctx;
  const cat = await api("GET", "/chars3d");
  U = { cat, prof: cat.profiles[0], spec: { ...cat.profiles[0].spec }, anim: "idle", expr: "smile", camera: "medium", lines: "", voice: "", seconds: 5, scene: "", lighting: "day", jobs: [], timer: 0 };
  root.innerHTML = `<div class="pghead"><div><h1>3D Studio — Characters</h1><p class="muted">60 तैयार 3D characters: पहनावा, रंग, props, हाव-भाव बदलें, lines लिखें — बोलता हुआ character (lip-sync) library में आता है, फिर editor में किसी भी video पर रखें।</p></div>
    <a class="btn quiet" href="#/scenes3d">🎬 3D Scenes & explainer →</a></div>
    <div class="c3d"><div class="c3d-list" id="c3d-list"></div>
      <div><div class="c3d-stage" id="c3d-stage"></div><p class="small muted" style="margin-top:.4rem">खींचकर घुमाएँ · scroll से zoom · preview browser में चलता है, render server पर</p></div>
      <div class="c3d-side" id="c3d-side"></div></div>`;
  const list = root.querySelector("#c3d-list");
  const cats = {};
  for (const p of cat.profiles) (cats[p.category] ||= []).push(p);
  list.innerHTML = Object.entries(cats).map(([c, ps]) => `<div class="c3d-cat">${esc(cat.categories[c] || c)}</div>` + ps.map((p) => `<div class="c3d-prof ${p.id === U.prof.id ? "on" : ""}" data-p="${p.id}"><img loading="lazy" src="/api/chars3d/preview/${p.id}.png?t=${encodeURIComponent(ctx.S.token)}" alt=""><span>${esc(p.name)}</span></div>`).join("")).join("");
  U.pv = livePreview(root.querySelector("#c3d-stage"), { width: 560, height: 630 });
  const shotSpec = () => ({ transparent: false, background: 0x1e2430, characters: [{ spec: U.spec, animation: U.anim, expression: U.expr, expressionAmount: 0.6, talk: [], visemes: U._demoVis || [] }],
    camera: { preset: U.camera }, ...(U.scene ? { scene: { name: U.scene, lighting: U.lighting } } : {}), fps: 25, duration: 10 });
  const refresh = () => U.pv.set(shotSpec());
  list.onclick = (e) => { const el = e.target.closest("[data-p]"); if (!el) return; U.prof = cat.profiles.find((p) => p.id === el.dataset.p); U.spec = { ...U.prof.spec }; list.querySelectorAll(".c3d-prof").forEach((x) => x.classList.toggle("on", x === el)); side(); refresh(); };
  const jobs = async () => { try { U.jobs = (await api("GET", "/chars3d/jobs")).jobs || []; } catch {} const ul = root.querySelector("#c-jobs"); if (ul) jobsList(ul, U.jobs, api, jobs); clearTimeout(U.timer); if (U.jobs.some((j) => ["queued", "running"].includes(j.status))) U.timer = setTimeout(jobs, 3000); };
  const side = () => {
    const s = U.spec; const sideEl = root.querySelector("#c3d-side");
    const opt = (arr, cur, lab = (x) => x.label ?? x) => arr.map((a) => `<option value="${esc(a.id ?? a)}" ${(a.id ?? a) === cur ? "selected" : ""}>${esc(lab(a))}</option>`).join("");
    sideEl.innerHTML = `<div class="card"><div class="card-h"><h2>${esc(U.prof.name)}</h2><span class="small muted">${esc(cat.categories[U.prof.category] || "")}</span></div>
      <div class="c3d-row"><div class="field"><label>पहनावा</label><select id="c-outfit">${opt(Object.keys(OUTFITS), s.outfit, (k) => OUTFITS[k].label)}</select></div>
        <div class="field"><label>बाल</label><select id="c-hair">${opt(HAIR, s.hair, (x) => x)}</select></div></div>
      <div class="c3d-row"><div class="field"><label>उम्र</label><select id="c-age">${opt(["child", "teen", "adult", "old"], s.age || "adult", (a) => ({ child: "बच्चा", teen: "किशोर", adult: "वयस्क", old: "बुज़ुर्ग" })[a])}</select></div>
        <div class="field"><label>त्वचा</label><div>${Object.entries(SKIN).map(([k, v]) => `<i class="c3d-sw ${s.skin === k ? "on" : ""}" data-skin="${k}" style="background:${hex(v)}"></i>`).join("")}</div></div></div>
      <div class="c3d-row"><div class="field"><label>कद <b id="c-hv">${(s.height || 1.72).toFixed(2)} m</b></label><input type="range" id="c-height" min="1.4" max="2.0" step="0.01" value="${s.height || 1.72}"></div>
        <div class="field"><label>शरीर <b id="c-bv">${(s.build || 1).toFixed(2)}</b></label><input type="range" id="c-build" min="0.7" max="1.5" step="0.05" value="${s.build || 1}"></div></div>
      <div class="c3d-row"><div class="field"><label>कपड़ों का रंग</label><input type="color" id="c-col" value="${hex(s.colors?.torso ?? OUTFITS[s.outfit]?.torso ?? 0x3b82f6)}"></div>
        <div class="field"><label>बालों का रंग</label><input type="color" id="c-hcol" value="${hex(s.hairColor ?? 0x1a1a1a)}"></div>
        <div class="field"><label>दाढ़ी</label><label class="chk"><input type="checkbox" id="c-beard" ${s.beard ? "checked" : ""}> हाँ</label></div></div>
      <div class="field"><label>Props</label><div class="choices">${PROPS.map((p) => `<label class="chip ${(s.props || []).includes(p) ? "on" : ""}"><input type="checkbox" data-prop="${p}" ${(s.props || []).includes(p) ? "checked" : ""}>${p}</label>`).join("")}</div></div>
      </div>
      <div class="card"><div class="card-h"><h2>Animation और हाव-भाव</h2></div>
      <div class="c3d-row"><div class="field"><label>Animation</label><select id="c-anim">${opt(cat.animations, U.anim)}</select></div>
        <div class="field"><label>चेहरा</label><select id="c-expr">${opt(EXPRESSIONS, U.expr, (e) => ({ smile: "मुस्कान", sad: "उदास", angry: "गुस्सा", surprised: "हैरान", think: "सोच" })[e])}</select></div></div>
      <div class="c3d-row"><div class="field"><label>Camera</label><select id="c-cam">${opt(cat.cameras, U.camera, (x) => x)}</select></div>
        <div class="field"><label>Scene (खाली = transparent)</label><select id="c-scene"><option value="">— transparent (overlay) —</option>${opt(cat.scenes, U.scene)}</select></div></div>
      <div class="c3d-row"><div class="field"><label>रोशनी</label><select id="c-light">${opt(cat.lighting, U.lighting, (x) => x)}</select></div>
        <div class="field"><label>लंबाई (बिना lines)</label><input type="number" id="c-sec" min="1" max="120" value="${U.seconds}"></div></div>
      <button class="btn small" id="c-demo">🗣 lip-sync demo देखें</button></div>
      <div class="card c3d-lines"><div class="card-h"><h2>क्या बोले (lip-sync)</h2><span class="small muted">एक line = एक वाक्य</span></div>
      <textarea id="c-lines" placeholder="नमस्ते, मैं डॉक्टर मीरा हूँ।&#10;आज हम सेहत की बात करेंगे।">${esc(U.lines)}</textarea>
      <div class="field" style="margin-top:.4rem"><label>आवाज़</label><select id="c-voice"><option value="">character के हिसाब से</option>${(cat.voices || []).map((v) => `<option value="${v.id}" ${U.voice === v.id ? "selected" : ""}>${esc(v.label)}</option>`).join("")}</select></div>
      <button class="btn primary" id="c-render" style="width:100%;justify-content:center">🎞 Render → Library</button>
      <p class="small muted" style="margin-top:.4rem">Transparent webm बनता है (alpha) — editor के Media / Overlay में "3D ·" नाम से मिलेगा; बोली गई lines की आवाज़ clip में रहती है।</p></div>
      <div class="card"><div class="card-h"><h2>3D jobs</h2><button class="btn small quiet" id="c-jobs-r">↻</button></div><ul class="c3d-jobs" id="c-jobs"></ul></div>`;
    const on = (id, ev, fn) => { const el = sideEl.querySelector(id); if (el) el[ev] = fn; };
    on("#c-outfit", "onchange", (e) => { U.spec.outfit = e.target.value; if (U.spec.colors) { delete U.spec.colors.torso; delete U.spec.colors.sleeves; } side(); refresh(); });
    on("#c-hair", "onchange", (e) => { U.spec.hair = e.target.value; refresh(); });
    on("#c-age", "onchange", (e) => { U.spec.age = e.target.value; refresh(); });
    sideEl.querySelectorAll("[data-skin]").forEach((i) => (i.onclick = () => { U.spec.skin = i.dataset.skin; sideEl.querySelectorAll("[data-skin]").forEach((x) => x.classList.toggle("on", x === i)); refresh(); }));
    on("#c-height", "oninput", (e) => { U.spec.height = +e.target.value; sideEl.querySelector("#c-hv").textContent = U.spec.height.toFixed(2) + " m"; });
    on("#c-height", "onchange", refresh); on("#c-build", "onchange", refresh);
    on("#c-build", "oninput", (e) => { U.spec.build = +e.target.value; sideEl.querySelector("#c-bv").textContent = U.spec.build.toFixed(2); });
    on("#c-col", "onchange", (e) => { const v = parseInt(e.target.value.slice(1), 16); U.spec.colors = { ...(U.spec.colors || {}), torso: v, sleeves: v }; refresh(); });
    on("#c-hcol", "onchange", (e) => { U.spec.hairColor = parseInt(e.target.value.slice(1), 16); refresh(); });
    on("#c-beard", "onchange", (e) => { U.spec.beard = e.target.checked; refresh(); });
    sideEl.querySelectorAll("[data-prop]").forEach((i) => (i.onchange = () => { const set = new Set(U.spec.props || []); if (i.checked) set.add(i.dataset.prop); else set.delete(i.dataset.prop); U.spec.props = [...set]; i.closest(".chip").classList.toggle("on", i.checked); refresh(); }));
    on("#c-anim", "onchange", (e) => { U.anim = e.target.value; refresh(); });
    on("#c-expr", "onchange", (e) => { U.expr = e.target.value; refresh(); });
    on("#c-cam", "onchange", (e) => { U.camera = e.target.value; refresh(); });
    on("#c-scene", "onchange", (e) => { U.scene = e.target.value; refresh(); });
    on("#c-light", "onchange", (e) => { U.lighting = e.target.value; refresh(); });
    on("#c-sec", "onchange", (e) => { U.seconds = +e.target.value || 5; });
    on("#c-lines", "oninput", (e) => { U.lines = e.target.value; });
    on("#c-voice", "onchange", (e) => { U.voice = e.target.value; });
    on("#c-demo", "onclick", () => { const txt = (U.lines || "नमस्ते दोस्तों, आज हम सेहत की बात करेंगे").split("\n").join(" "); const words = txt.split(/\s+/).filter(Boolean); const per = 0.38;
      U._demoVis = visemeTrack(words.map((w, i) => ({ w, start: i * per, end: i * per + per * 0.85 }))); const sp = shotSpec(); sp.characters[0].talk = [[0, words.length * per]]; sp.characters[0].visemes = U._demoVis; U.pv.set(sp); setTimeout(() => { if (U) U._demoVis = null; }, words.length * per * 1000); });
    on("#c-render", "onclick", async () => {
      const lines = U.lines.split("\n").map((t) => t.trim()).filter(Boolean).map((text) => ({ text, voice: U.voice || null }));
      const btn = sideEl.querySelector("#c-render"); btn.disabled = true;
      try { await api("POST", "/chars3d/render", { profile: U.prof.id, spec: U.spec, animation: U.anim, expression: U.expr, camera: U.camera, lines, seconds: U.seconds, scene: U.scene || null, lighting: U.lighting, name: U.prof.name, width: U.scene ? 1280 : 720, height: U.scene ? 720 : 1080 }); toast("3D render queue में — नीचे progress"); jobs(); } catch (e) { toast(e.message); } finally { btn.disabled = false; }
    });
    on("#c-jobs-r", "onclick", jobs);
    const ul = sideEl.querySelector("#c-jobs"); if (ul) jobsList(ul, U.jobs, api, jobs);
  };
  side(); refresh(); jobs();
}

export function unmountStudio() { if (!U) return; clearTimeout(U.timer); U.pv?.destroy(); U = null; }
