// Vividora editor — professional engine features (contract: docs/editor-schema.md).
// Overlay-clip inspector (speed / ramps / trim / colour / effects / blend / mask / keyframes / own audio),
// keyframes UX, 🔥 Trending, Pro tools (morph cut, stabilise, denoise, sharpen, face refine, Speed Warp,
// colour wheels / curves / HSL / colour match, main-video mask), markers + scene detection, music fit,
// text-based editing, autopilot progress, and the live-preview side of all of it.
// editor.js owns the state (E) and calls in here; host() hands over the editor's helpers.

let H = null;
export function host(h) { H = h; }
const E = () => H.E;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const esc = (s) => E().ctx.esc(String(s ?? ""));
const PP = () => E().ctx.S.presets?.pro || {};
const r3 = (v) => Math.round(v * 1000) / 1000;
const uid = () => Math.random().toString(36).slice(2, 10);
const LS = (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } };
const LSset = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } };

// ====================================================================== keyframes (same maths as engine/keyframes.py)
export const EASES = ["linear", "in", "out", "inout", "hold"];
function easeF(u, e) { return e === "in" ? u ** 3 : e === "out" ? 1 - (1 - u) ** 3 : e === "inout" ? u * u * (3 - 2 * u) : e === "hold" ? (u >= 1 ? 1 : 0) : u; }
export function norm(pts) {
  if (typeof pts === "number") return [{ t: 0, v: pts, ease: "linear" }];
  if (!Array.isArray(pts)) return [];
  return pts.filter((p) => p && isFinite(+p.t) && isFinite(+p.v)).map((p) => ({ t: Math.max(0, +p.t), v: +p.v, ease: EASES.includes(p.ease) ? p.ease : "linear" })).sort((a, b) => a.t - b.t);
}
export function sample(pts, t, def) {
  const p = norm(pts); if (!p.length) return def;
  if (t <= p[0].t) return p[0].v; const L = p[p.length - 1]; if (t >= L.t) return L.v;
  for (let i = 0; i < p.length - 1; i++) { const a = p[i], b = p[i + 1]; if (t >= a.t && t <= b.t) { const u = (t - a.t) / Math.max(1e-4, b.t - a.t); return a.v + (b.v - a.v) * easeF(u, a.ease); } }
  return L.v;
}
const animated = (pts) => { const p = norm(pts); return p.length >= 2 && p.some((x) => Math.abs(x.v - p[0].v) > 1e-9); };
const hasKf = (kf, p) => Array.isArray(kf?.[p]) && kf[p].length > 0;
const FR = () => 1 / (E().p.meta?.fps || 30);
function keyAt(arr, t) { return (arr || []).findIndex((k) => Math.abs(k.t - t) < FR() * 0.6); }
function putKey(kf, p, t, v) {
  const arr = (kf[p] = Array.isArray(kf[p]) ? kf[p] : []); const i = keyAt(arr, t);
  if (i >= 0) arr[i].v = r3(v);
  else { const prev = norm(arr).filter((k) => k.t < t).pop(); arr.push({ t: r3(Math.max(0, t)), v: r3(v), ease: prev?.ease || "inout" }); arr.sort((a, b) => a.t - b.t); }
}

// ---------------------------------------------------------------- owners: things with keyframeable params
// owner = { id, kf() → the kf map (created), t0 → owner start on the output timeline, len, get(p) static value,
//           set(p, v) static write, spec: {p: [label, min, max, step]} }
const OWN = new Map();
function lt(o) { return H.outOf(E().t) - (o.t0 || 0); }
export function val(o, p) { const kf = o.kfMap(); return hasKf(kf, p) ? sample(kf[p], lt(o), o.get(p)) : o.get(p); }
export function setVal(o, p, v) {
  const kf = o.kfMap();
  if (hasKf(kf, p) || o.kfOnly?.includes(p)) { putKey(o.kf(), p, clamp(lt(o), 0, o.len ?? 1e9), v); return true; }   // auto-key
  o.set(p, v); return false;
}
function toggleKey(o, p) {
  const kf = o.kf(); const t = clamp(lt(o), 0, o.len ?? 1e9); const arr = kf[p] || []; const i = keyAt(arr, t);
  if (i >= 0) { arr.splice(i, 1); if (!arr.length) delete kf[p]; }
  else { const v = val(o, p); putKey(kf, p, t, v); }
  o.clean?.();
}
function regOwner(o) { OWN.set(o.id, o); return o; }

function clipBase(b) {   // base centre (fractions) of an overlay clip's box (engine compose.base_box)
  const fit = b.fit || "cover";
  if (fit === "free") return { x: +(b.x ?? 0.5), y: +(b.y ?? 0.5) };
  if (fit === "pip") { const fb = E().frameBox || { w: 1080, h: 1920, scale: 1 }; const W = fb.w, Hh = fb.h; const bw = 0.42 * W, bh = W < Hh ? 0.42 * Hh * 9 / 16 : 0.42 * Hh; const m = 24 * (fb.scale || 1); const pos = b.pos || "tr";
    return { x: (["tl", "bl"].includes(pos) ? m + bw / 2 : W - m - bw / 2) / W, y: (["tl", "tr"].includes(pos) ? m + bh / 2 : Hh - 0.28 * Hh - bh / 2) / Hh }; }
  return { x: 0.5, y: 0.5 };
}
export function clipOwner(b) {
  const free = (b.fit || "cover") === "free";
  return regOwner({ id: "clip:" + b._id, t0: +b.start, len: b.end - b.start, kfMap: () => b.kf || {}, kf: () => (b.kf = b.kf || {}),
    clean: () => { if (b.kf && !Object.keys(b.kf).length) delete b.kf; },
    kfOnly: free ? ["scale"] : ["x", "y", "scale", "rotation", "opacity"],
    get: (p) => p === "x" ? clipBase(b).x : p === "y" ? clipBase(b).y : p === "scale" ? 1 : p === "rotation" ? +(b.rotate || 0) : +(b.opacity ?? 1),
    set: (p, v) => { if (p === "x") b.x = r3(v); else if (p === "y") b.y = r3(v); else if (p === "rotation") b.rotate = +v.toFixed(1); else if (p === "opacity") b.opacity = r3(v); },
    spec: { x: ["← → X", -0.5, 1.5, 0.005], y: ["↑ ↓ Y", -0.5, 1.5, 0.005], scale: ["Zoom ×", 0.1, 4, 0.01], rotation: ["घुमाव °", -180, 180, 1], opacity: ["Opacity", 0, 1, 0.01] } });
}
export function maskOwner(id, getMask, t0, len) {
  return regOwner({ id, t0, len, kfMap: () => getMask()?.kf || {}, kf: () => { const m = getMask(); return (m.kf = m.kf || {}); },
    clean: () => { const m = getMask(); if (m?.kf && !Object.keys(m.kf).length) delete m.kf; },
    get: (p) => { const m = getMask() || {}; const d = (PP().masks?.params || []).find((x) => x.name === p); return +(m[p] ?? d?.default ?? 0); },
    set: (p, v) => { getMask()[p] = r3(v); },
    spec: Object.fromEntries((PP().masks?.params || []).map((x) => [x.name, [x.label, x.min, x.max, x.step]])) });
}
export function mainOwner() {
  const fx = E().rs.effects; const t = () => (fx.transform = fx.transform || {});
  return regOwner({ id: "main", t0: 0, len: H.outDur(), kfMap: () => fx.transform?.kf || {}, kf: () => (t().kf = t().kf || {}), clean: () => { if (t().kf && !Object.keys(t().kf).length) delete t().kf; },
    kfOnly: ["opacity"],
    get: (p) => p === "x" ? +(t().x || 0) : p === "y" ? +(t().y || 0) : p === "scale" ? +(t().scale || 1) : p === "rotation" ? +(t().angle || 0) : 1,
    set: (p, v) => { const T = t(); if (p === "x") T.x = r3(v); else if (p === "y") T.y = r3(v); else if (p === "scale") T.scale = r3(v); else if (p === "rotation") T.angle = +v.toFixed(1); },
    spec: { scale: ["size", 0.2, 2.5, 0.01], x: ["← →", -0.5, 0.5, 0.005], y: ["↑ ↓", -0.5, 0.5, 0.005], rotation: ["घुमाव °", -45, 45, 0.5], opacity: ["Opacity", 0, 1, 0.01] } });
}
export function paramOwner(id, holder, t0, len, def) {   // fx clip params / clip stack item params
  return regOwner({ id, t0, len, kfMap: () => holder.kf || {}, kf: () => (holder.kf = holder.kf || {}), clean: () => { if (holder.kf && !Object.keys(holder.kf).length) delete holder.kf; },
    get: (p) => +(holder.params?.[p] ?? (def.params || []).find((x) => x.name === p)?.default ?? 0),
    set: (p, v) => { holder.params = holder.params || {}; holder.params[p] = v; }, spec: {} });
}
// ◆ toggle + keyframeable slider (data-kp = owner|param → refreshed while the playhead moves)
export function kfBtn(o, p) {
  const kf = o.kfMap(); const on = hasKf(kf, p) && keyAt(kf[p], lt(o)) >= 0;
  return `<button class="kfb ${hasKf(kf, p) ? "has" : ""} ${on ? "on" : ""}" data-kfb="${o.id}|${p}" title="Keyframe ◆ — इस समय पर जोड़ें/हटाएँ (K)। keyframe होने पर बदलाव अपने-आप keyframe बनते हैं (auto-key)">◆</button>`;
}
export function kfSlider(o, p, dis, label) {
  const [l, mn, mx, st] = o.spec[p] || [p, 0, 1, 0.01]; const v = val(o, p); const lock = o.kfOnly?.includes(p) && !hasKf(o.kfMap(), p) && p === "opacity" && o.id === "main";
  return `<div class="ifield kfrow"><label>${esc(label || l)} <b data-kpv="${o.id}|${p}">${fmtV(v, st)}</b></label><span class="row" style="gap:.25rem">${kfBtn(o, p)}<input type="range" data-kp="${o.id}|${p}" min="${mn}" max="${mx}" step="${st}" value="${v}" ${dis} ${lock ? `disabled title="पहले ◆ से keyframe जोड़ें (fade in/out)"` : ""}></span></div>`;
}
const fmtV = (v, st) => (+v).toFixed(st >= 1 ? 0 : st >= 0.1 ? 1 : 2);
export function bindKf(root, after) {
  $$("[data-kfb]", root).forEach((b) => (b.onclick = (e) => { e.preventDefault(); if (!E().canEdit) return; const [id, p] = b.dataset.kfb.split("|"); const o = OWN.get(id); if (!o) return; toggleKey(o, p); H.touch(); after?.(); H.renderInspector(); }));
  $$("[data-kp]", root).forEach((el) => (el.oninput = () => { if (!E().canEdit) return; const [id, p] = el.dataset.kp.split("|"); const o = OWN.get(id); if (!o) return;
    setVal(o, p, +el.value); const b = $(`[data-kpv="${id}|${p}"]`, root); if (b) b.textContent = fmtV(+el.value, +el.step); H.touch(); after?.(); refreshKfUi(); }));
}
// playhead moved: keyframed sliders show the value at this moment, ◆ lights up on a key
export function refreshKfUi() {
  const ins = $("#inspector", E().root); if (!ins) return;
  for (const el of $$("[data-kp]", ins)) { const [id, p] = el.dataset.kp.split("|"); const o = OWN.get(id); if (!o || !hasKf(o.kfMap(), p) || document.activeElement === el) continue; const v = val(o, p); el.value = v; const b = $(`[data-kpv="${id}|${p}"]`, ins); if (b) b.textContent = fmtV(v, +el.step); }
  for (const b of $$("[data-kfb]", ins)) { const [id, p] = b.dataset.kfb.split("|"); const o = OWN.get(id); if (!o) continue; const kf = o.kfMap(); b.classList.toggle("has", hasKf(kf, p)); b.classList.toggle("on", hasKf(kf, p) && keyAt(kf[p], lt(o)) >= 0); }
}

// ---------------------------------------------------------------- keyframe maps of a selected thing (timeline ◆, list, ease)
function kfMaps(sel) {
  const fx = E().rs.effects; const it = H.selItem(); if (!it) return [];
  if (sel.type === "broll") { const out = [["", it.kf]]; if (it.mask?.kf) out.push(["mask.", it.mask.kf]); if (it.crop?.kf) out.push(["crop.", it.crop.kf]); (it.stack || []).forEach((s, i) => s.kf && out.push([`fx${i + 1}.`, s.kf])); return out.filter((x) => x[1]); }
  if (sel.type === "fxclip") return it.kf ? [["", it.kf]] : [];
  if (sel.type === "video" || sel.type === "seg") { const out = []; if (fx.transform?.kf) out.push(["", fx.transform.kf]); if (fx.pro?.mask?.kf) out.push(["mask.", fx.pro.mask.kf]); return out; }
  return [];
}
function kfTimes(sel) { const ts = []; for (const [, m] of kfMaps(sel)) for (const arr of Object.values(m)) for (const k of arr || []) if (!ts.some((x) => Math.abs(x - k.t) < 1e-3)) ts.push(+k.t); return ts.sort((a, b) => a - b); }
const selT0 = (sel, it) => (sel.type === "broll" || sel.type === "fxclip" ? +it.start : 0);
// ◆ on the selected clip in the timeline: click = jump, drag = retime (all params keyed at that moment move together)
export function tlDiamonds(sel, X) {
  const it = H.selItem(); if (!sel || !it) return "";
  const t0 = selT0(sel, it); const ts = kfTimes(sel); if (!ts.length) return "";
  const lane = sel.type === "broll" ? `broll:${it.track || 0}` : sel.type === "fxclip" ? `fx:${it.track || 0}` : "video";
  return ts.map((t) => `<i class="kfd ${E().kfSel != null && Math.abs(E().kfSel - t) < 1e-3 ? "on" : ""}" data-kfd="${t}" data-lane="${lane}" style="left:${X(H.srcOf(t0 + t))}px" title="◆ ${t.toFixed(2)}s — क्लिक = वहाँ जाएँ, खींचें = समय बदलें"></i>`).join("");
}
export function bindDiamonds(body) {
  for (const d of $$(".kfd", body)) {
    const lane = $(`.tl-track[data-track="${d.dataset.lane}"]`, body); if (lane && d.parentElement !== lane) lane.appendChild(d);
    d.onpointerdown = (e) => {
      if (e.button > 0) return; e.preventDefault(); e.stopPropagation(); const sel = E().sel; const it = H.selItem(); if (!it) return;
      const t0v = +d.dataset.kfd; const st = selT0(sel, it); const len = sel.type === "broll" || sel.type === "fxclip" ? it.end - it.start : H.outDur();
      let cur = t0v; const x0 = e.clientX;
      H.track(e, (ev) => { const out = H.outOf(clamp(H.srcOf(st + t0v) + (ev.clientX - x0) / E().pps, 0, E().dur)); const nt = clamp(out - st, 0, len);
        for (const [, m] of kfMaps(sel)) for (const arr of Object.values(m)) { for (const k of arr || []) if (Math.abs(k.t - cur) < 1e-3) k.t = r3(nt); arr?.sort((a, b) => a.t - b.t); }
        cur = r3(nt); E().kfSel = cur; d.style.left = (H.srcOf(st + cur) * E().pps).toFixed(1) + "px"; H.renderOverlay(); },
      (moved) => { if (moved) { H.touch(); H.renderInspector(); } else { E().kfSel = t0v; H.seek(H.srcOf(st + t0v) + 0.001); H.renderInspector(); H.renderTimeline(); } }, 2);
    };
  }
}
// Keyframes section: every key, its params and the ease to the next one
export function kfListHtml(sel, dis) {
  const maps = kfMaps(sel); const ts = kfTimes(sel); const eases = PP().keyframe_eases || {};
  if (!ts.length) return `<p class="small muted">कोई keyframe नहीं। किसी property के ◆ से जोड़ें — फिर playhead आगे ले जाकर value बदलें, नया keyframe अपने-आप बनेगा। <b>K</b> = position/zoom/घुमाव/opacity एक साथ।</p>`;
  return `<ul class="plist kflist">${ts.map((t) => { const ps = []; let ease = null;
    for (const [pre, m] of maps) for (const [p, arr] of Object.entries(m)) { const k = (arr || []).find((x) => Math.abs(x.t - t) < 1e-3); if (k) { ps.push(pre + p); ease = ease || k.ease; } }
    const on = E().kfSel != null && Math.abs(E().kfSel - t) < 1e-3;
    return `<li class="${on ? "sel" : ""}"><button class="ibtn kfgo" data-kfgo="${t}" title="यहाँ जाएँ">◆</button><span class="small grow"><b>${t.toFixed(2)}s</b> <span class="muted">${esc(ps.join(", "))}</span></span>
      <select class="small" data-kfease="${t}" title="इस keyframe से अगले तक की चाल" ${dis}>${Object.entries(eases).map(([k, l]) => `<option value="${k}" ${ease === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select><button class="ibtn" data-kfdel="${t}" title="यह keyframe हटाएँ" ${dis}>✕</button></li>`; }).join("")}</ul>`;
}
export function bindKfList(root) {
  const sel = E().sel; const it = H.selItem(); if (!sel || !it) return; const st = selT0(sel, it);
  $$("[data-kfgo]", root).forEach((b) => (b.onclick = () => { E().kfSel = +b.dataset.kfgo; H.seek(H.srcOf(st + +b.dataset.kfgo) + 0.001); H.renderInspector(); H.renderTimeline(); }));
  $$("[data-kfease]", root).forEach((s) => (s.onchange = () => { const t = +s.dataset.kfease; for (const [, m] of kfMaps(sel)) for (const arr of Object.values(m)) for (const k of arr || []) if (Math.abs(k.t - t) < 1e-3) k.ease = s.value; H.touch(); }));
  $$("[data-kfdel]", root).forEach((b) => (b.onclick = () => { const t = +b.dataset.kfdel; for (const [, m] of kfMaps(sel)) for (const [p, arr] of Object.entries(m)) { m[p] = (arr || []).filter((k) => Math.abs(k.t - t) >= 1e-3); if (!m[p].length) delete m[p]; } H.touch(); H.renderInspector(); }));
}
// K: key every transform property of the selected overlay / main video at the playhead
export function keyAll() {
  const sel = E().sel; const it = H.selItem(); if (!sel || !it || !E().canEdit) return false;
  const o = sel.type === "broll" ? clipOwner(it) : sel.type === "video" || sel.type === "seg" ? mainOwner() : null; if (!o) return false;
  const ps = ["x", "y", "scale", "rotation", "opacity"].filter((p) => !(o.id === "main" && p === "opacity"));
  const kf = o.kf(); const t = clamp(lt(o), 0, o.len ?? 1e9); const allOn = ps.every((p) => hasKf(kf, p) && keyAt(kf[p], t) >= 0);
  for (const p of ps) { if (allOn) { const i = keyAt(kf[p], t); kf[p].splice(i, 1); if (!kf[p].length) delete kf[p]; } else if (!(hasKf(kf, p) && keyAt(kf[p], t) >= 0)) putKey(kf, p, t, val(o, p)); }
  o.clean?.(); H.touch(); H.renderInspector(); E().ctx.toast(allOn ? "◆ keyframes हटाए" : `◆ ${t.toFixed(2)}s पर keyframe — playhead आगे करके बदलें`); return true;
}
// Alt+←/→: previous / next keyframe of the selection
export function jumpKey(dir) {
  const sel = E().sel; const it = H.selItem(); if (!sel || !it) return false; const ts = kfTimes(sel); if (!ts.length) return false;
  const st = selT0(sel, it); const now = H.outOf(E().t) - st; const t = dir > 0 ? ts.find((x) => x > now + 1e-3) : [...ts].reverse().find((x) => x < now - 1e-3);
  if (t == null) return true; E().kfSel = t; H.seek(H.srcOf(st + t) + 0.001); H.renderInspector(); H.renderTimeline(); return true;
}

// ====================================================================== speed (overlay clips)
export function rampOf(b) { const p = norm(b.speed_ramp).map((k) => ({ ...k, v: clamp(k.v, 0.25, 4) })); return p.length >= 2 ? p : null; }
const spd = (b) => clamp(+(b.speed || 1), 0.25, 4);
// clip-local output seconds → source seconds after trim_in (engine compose.ramp_pieces, 0.1 s pieces)
export function srcOffset(b, t) {
  const r = rampOf(b); if (!r) return t * spd(b);
  let s = 0, out = 0; const step = 0.05;
  for (let n = 0; n < 4000 && out < t; n++) { const v = clamp(sample(r, s + step / 2), 0.25, 4); if (out + step / v >= t) { s += (t - out) * v; break; } s += step; out += step / v; }
  return s;
}
export function speedAt(b, t) { const r = rampOf(b); return r ? clamp(sample(r, srcOffset(b, t)), 0.25, 4) : spd(b); }
function naturalLen(b, span) { const r = rampOf(b); if (!r) return span / spd(b); let out = 0; const step = 0.05; for (let s = 0; s < span; s += step) out += Math.min(step, span - s) / clamp(sample(r, s + step / 2), 0.25, 4); return out; }
function srcAvail(b) { const it = H.libItem(b.id); const d = +(it?.meta?.duration || 0); const ti = +(b.trim_in || 0); if (b.trim_out != null && b.trim_out !== "") return Math.max(0.05, +b.trim_out - ti); return d ? Math.max(0.05, d - ti) : Math.max(1, (b.end - b.start) * spd(b)); }
const RAMPS = { montage: ["Montage", [[0, 1], [0.2, 3], [0.4, 0.5], [0.6, 0.5], [0.8, 3], [1, 1]]], hero: ["Hero", [[0, 1], [0.35, 1], [0.45, 0.3], [0.65, 0.3], [0.75, 1], [1, 1]]],
  bullet: ["Bullet", [[0, 2], [0.3, 2], [0.4, 0.25], [0.7, 0.25], [0.8, 2], [1, 2]]], jump: ["Jump cut", [[0, 0.5], [0.5, 0.5], [0.55, 3], [1, 3]]],
  flashin: ["Flash in", [[0, 3], [0.6, 1], [1, 1]]], flashout: ["Flash out", [[0, 1], [0.4, 1], [1, 3]]] };

// ====================================================================== live preview of overlay clips
function effKf(b, W, Hh) {   // keyframes the engine will use (legacy `to` move → keyframes, like compose._kf)
  const kf = { ...(b.kf || {}) }; const to = b.to;
  if (to && (b.fit || "cover") === "free") { const d = b.end - b.start; const x0 = +(b.x ?? 0.5), y0 = +(b.y ?? 0.5), s0 = +(b.scale ?? 0.4);
    if (!kf.x && to.x != null) kf.x = [{ t: 0, v: x0 }, { t: d, v: +to.x }]; if (!kf.y && to.y != null) kf.y = [{ t: 0, v: y0 }, { t: d, v: +to.y }]; if (!kf.scale && to.scale != null) kf.scale = [{ t: 0, v: 1 }, { t: d, v: +to.scale / s0 }]; }
  return kf;
}
// geometry of an overlay clip box in preview pixels at output time ot (engine compose.base_box + keyframes)
export function clipGeom(b, ot, fb) {
  const W = fb.w, Hh = fb.h; const it = H.libItem(b.id); const aw = +(it?.meta?.width || 0), ah = +(it?.meta?.height || 0); const ar = aw && ah ? aw / ah : null;
  const fit = b.fit || "cover"; let bw, bh, cx, cy;
  const base = clipBase(b);
  if (fit === "pip") { bw = 0.42 * W; bh = W < Hh ? 0.42 * Hh * 9 / 16 : 0.42 * Hh; }
  else if (fit === "free") { bw = W * clamp(+(b.scale ?? 0.4), 0.02, 4); bh = ar ? bw / ar : null; }
  else if (fit === "contain" && ar) { const k = Math.min(W / aw, Hh / ah); bw = aw * k; bh = ah * k; }
  else { bw = W; bh = Hh; }
  cx = base.x * W; cy = base.y * Hh;
  const t = ot - b.start; const kf = effKf(b, W, Hh);
  if (hasKf(kf, "x")) cx = sample(kf.x, t) * W; if (hasKf(kf, "y")) cy = sample(kf.y, t) * Hh;
  const sm = hasKf(kf, "scale") ? clamp(sample(kf.scale, t), 0.01, 10) : 1;
  const rot = hasKf(kf, "rotation") ? sample(kf.rotation, t) : +(b.rotate || 0);
  let op = hasKf(kf, "opacity") ? sample(kf.opacity, t) : +(b.opacity ?? 1);
  const dur = b.end - b.start;
  if (fit === "cover" && b.fade !== false) { const fd = Math.min(0.25, dur / 4); op *= clamp(Math.min(t / fd, (dur - t) / fd), 0, 1); }
  op *= trFactor(b, ot);
  return { cx, cy, w: bw * sm, h: bh == null ? null : bh * sm, rot, op: clamp(op, 0, 1), fit };
}
// ---- transitions between overlay clips on one track (render: engine/compose.apply_transitions; preview: opacity only)
export const TRANSITIONS = { none: "कोई नहीं", crossfade: "Crossfade", dip: "Dip (काला)", slide_left: "Slide ←", slide_right: "Slide →", slide_up: "Slide ↑", slide_down: "Slide ↓", zoom: "Zoom in", wipe: "Wipe →" };
export function trPrev(b) {
  const ed = E(); let best = null;
  for (const o of ed.rs.effects.broll) { if (o === b || (o.track || 0) !== (b.track || 0)) continue; if (+o.start < +b.start && +o.end >= +b.start - 0.02 && (!best || +o.end > +best.end)) best = o; }
  return best;
}
export function trWindow(b) {
  const tr = b.tr; if (!tr || !tr.kind || tr.kind === "none") return null;
  const prev = trPrev(b); if (!prev) return { prev: null, overlap: 0, wd: 0, want: +tr.dur || 0.5 };
  const overlap = Math.max(0, +prev.end - +b.start); const want = clamp(+tr.dur || 0.5, 0.1, 5);
  return { prev, overlap, wd: Math.min(want, overlap), want };
}
// opacity factor at output time ot: this clip fading in, or the next clip's transition fading this one out
function trFactor(b, ot) {
  let f = 1; const w = trWindow(b);
  if (w && w.prev && w.wd >= 0.08) { const t = ot - b.start; const [a, c] = b.tr.kind === "dip" ? [w.wd / 2, w.wd] : [0, w.wd]; if (t < c) f *= clamp((t - a) / Math.max(0.01, c - a), 0, 1); }
  for (const n of E().rs.effects.broll) { if (n === b || !n.tr || n.tr.kind === "none" || (n.track || 0) !== (b.track || 0)) continue; const wn = trWindow(n); if (!wn || wn.prev !== b || wn.wd < 0.08) continue;
    const end = n.tr.kind === "dip" ? +n.start + wn.wd / 2 : +n.start + wn.wd; if (ot >= +n.start && ot < end) f *= clamp(1 - (ot - n.start) / Math.max(0.01, end - n.start), 0, 1); else if (ot >= end) f = 0; }
  return f;
}
const CSS_BLEND = { normal: "", screen: "screen", multiply: "multiply", overlay: "overlay", softlight: "soft-light", hardlight: "hard-light", add: "plus-lighter", lighten: "lighten", darken: "darken", difference: "difference", exclusion: "exclusion", colordodge: "color-dodge", colorburn: "color-burn" };
const KEY_BLEND = { screen: "screen", black: "screen", white: "multiply" };
// per frame: move / scale / rotate / fade / mask / blend every visible overlay, keep its <video> on the clip's own clock
export function overlayFrame(ot) {
  const ed = E(); const fb = ed.frameBox; if (!fb) return; const v = $("#pv", ed.root); const playing = v && !v.paused && !v.ended; const rate = v?.playbackRate || 1; const fps = ed.p.meta?.fps || 30;
  for (const el of $$("#ovl-media .ov-broll", ed.root)) {
    const b = ed.rs.effects.broll.find((x) => x._id === el.dataset.bid); if (!b) continue;
    const g = clipGeom(b, ot, fb); const t = ot - b.start;
    const st = el.style; st.left = g.cx.toFixed(1) + "px"; st.top = g.cy.toFixed(1) + "px"; st.width = g.w.toFixed(1) + "px"; st.height = g.h == null ? "auto" : g.h.toFixed(1) + "px";
    st.transform = `translate(-50%,-50%) rotate(${g.rot.toFixed(2)}deg)`; st.opacity = g.op.toFixed(3);
    st.mixBlendMode = CSS_BLEND[b.blend_mode] || KEY_BLEND[b.blend] || "";
    const mk = maskCss(b, t, g); if (st.webkitMaskImage !== mk) { st.webkitMaskImage = mk; st.maskImage = mk; st.webkitMaskSize = st.maskSize = "100% 100%"; st.webkitMaskRepeat = st.maskRepeat = "no-repeat"; }
    const med = el.querySelector("video,img"); if (med) { const f = clipFilter(b, t); if (med._f !== f) { med._f = f; med.style.filter = f; } }
    const vid = el.querySelector("video");
    if (vid) {
      const src = +(b.trim_in || 0) + srcOffset(b, Math.max(0, t)); const end = b.trim_out != null && b.trim_out !== "" ? +b.trim_out : vid.duration || Infinity;
      el.style.visibility = src > end + 0.05 ? "hidden" : "";
      vid.muted = !(+b.volume > 0) || !playing; if (+b.volume > 0) vid.volume = clamp(+b.volume, 0, 1);
      H.follow(vid, Math.min(src, end - 0.001), playing, rate * speedAt(b, Math.max(0, t)), fps);
    }
  }
}
// what the clip's picture looks like (catalog grade / preset, effect stack css, wheels+curves as an SVG filter)
function clipFilter(b, t) {
  const g = b.grade && Object.keys(b.grade).length ? b.grade : b.grade_preset ? H.scaledGrade(b.grade_preset, 1) : null;
  return [g ? H.gradeCss(g) : "", H.stackCss(b.stack || []), colorFilter(b.color, "c" + b._id)].filter(Boolean).join(" ");
}
// ---------------------------------------------------------------- masks → a soft alpha image (canvas) used as CSS mask-image
const MASK_CACHE = new Map();
function maskNow(m, t) { const o = { ...m }; for (const [k, arr] of Object.entries(m.kf || {})) if (hasKf(m.kf, k)) o[k] = sample(arr, t); return o; }
function maskCss(b, t, g) {
  const m = b.mask && b.mask.enabled !== false && b.mask.shape ? maskNow(b.mask, t) : null; const c = b.crop && (+b.crop.w < 0.999 || +b.crop.h < 0.999 || +b.crop.x > 0 || +b.crop.y > 0 || b.crop.kf) ? maskNow(b.crop, t) : null;
  if (!m && !c) return "";
  const lw = Math.max(8, g.w), lh = Math.max(8, g.h ?? g.w * 0.5625);
  return maskImage(m, c, lw, lh);
}
export function maskImage(m, c, lw, lh) {
  const k = 160 / Math.max(lw, lh); const W = Math.max(4, Math.round(lw * k)), Hh = Math.max(4, Math.round(lh * k));
  const key = JSON.stringify([m, c, W, Hh]); if (MASK_CACHE.has(key)) return MASK_CACHE.get(key);
  const cv = document.createElement("canvas"); cv.width = W; cv.height = Hh; const x = cv.getContext("2d");
  x.fillStyle = "#fff";
  if (m) {
    const fe = clamp(+(m.feather ?? 0.02), 0, 0.5) * Math.min(W, Hh); x.save(); if (fe > 0.3) x.filter = `blur(${(fe / 2.5).toFixed(1)}px)`;
    const cx = +(m.x ?? 0.5) * W, cy = +(m.y ?? 0.5) * Hh, w = +(m.w ?? 0.6) * W, h = +(m.h ?? 0.6) * Hh; const rot = (+(m.rotation || 0)) * Math.PI / 180;
    x.translate(cx, cy); x.rotate(rot); x.beginPath();
    const sh = m.shape;
    if (sh === "circle") x.arc(0, 0, w / 2, 0, Math.PI * 2);
    else if (sh === "ellipse") x.ellipse(0, 0, w / 2, h / 2, 0, 0, Math.PI * 2);
    else if (sh === "rect") { const rr = clamp(+(m.roundness || 0), 0, 1) * Math.min(w, h) / 2; x.roundRect ? x.roundRect(-w / 2, -h / 2, w, h, rr) : x.rect(-w / 2, -h / 2, w, h); }
    else if (sh === "heart") { // engine masks.py sdHeart: tip (0,0), lobes r √2/4 at (±.25,.75); ±0.6036 ↔ w/2, 0.5518 ↔ h/2
      const A = w / 2 / 0.6036, B = h / 2 / 0.5518; const P = (hx, hy) => [hx * A, (0.5518 - hy) * B]; const pts = [[0, 0], [0.5, 0.5]];
      for (let i = 1; i <= 40; i++) { const a = (-45 + i * 180 / 40) * Math.PI / 180; pts.push([0.25 + Math.SQRT2 / 4 * Math.cos(a), 0.75 + Math.SQRT2 / 4 * Math.sin(a)]); }
      const all = [...pts, ...pts.slice(1).reverse().map(([a, b]) => [-a, b])]; all.forEach(([a, b], i) => { const [px, py] = P(a, b); i ? x.lineTo(px, py) : x.moveTo(px, py); }); x.closePath(); }
    else if (sh === "star") { const n = clamp(+(m.points || 5), 3, 12), inn = clamp(+(m.inner || 0.4), 0.1, 0.9); for (let i = 0; i < n * 2; i++) { const a = -Math.PI / 2 + i * Math.PI / n; const rx = (i % 2 ? inn : 1) * w / 2, ry = (i % 2 ? inn : 1) * h / 2; i ? x.lineTo(Math.cos(a) * rx, Math.sin(a) * ry) : x.moveTo(Math.cos(a) * rx, Math.sin(a) * ry); } x.closePath(); }
    else if (sh === "linear") x.rect(-4 * W, -4 * Hh, 4 * W, 8 * Hh);
    else if (sh === "mirror") x.rect(-4 * W, -h / 2, 8 * W, h);
    else if (sh === "polygon" && (m.pts || []).length >= 3) { const pts = m.pts; const mx = pts.reduce((a, q) => a + +q[0], 0) / pts.length, my = pts.reduce((a, q) => a + +q[1], 0) / pts.length; const sw = +(m.w ?? 0.6) / 0.6, shh = +(m.h ?? 0.6) / 0.6;
      pts.forEach((q, i) => { const px = ((+q[0] - mx) * sw + mx - 0.5) * W, py = ((+q[1] - my) * shh + my - 0.5) * Hh; i ? x.lineTo(px, py) : x.moveTo(px, py); }); x.closePath(); }
    x.fill(); x.restore();
    if (m.invert) { x.globalCompositeOperation = "xor"; x.fillRect(0, 0, W, Hh); x.globalCompositeOperation = "source-over"; }
  } else x.fillRect(0, 0, W, Hh);
  if (c) { x.globalCompositeOperation = "destination-in"; x.fillRect(+(c.x || 0) * W, +(c.y || 0) * Hh, +(c.w ?? 1) * W, +(c.h ?? 1) * Hh); x.globalCompositeOperation = "source-over"; }
  const url = `url(${cv.toDataURL()})`; if (MASK_CACHE.size > 300) MASK_CACHE.clear(); MASK_CACHE.set(key, url); return url;
}

// ====================================================================== colour (wheels + curves exactly as engine/colorpro.py; HSL/match only in render)
function pchip(pts) {
  let xs = pts.map((p) => +p[0]), ys = pts.map((p) => +p[1]);
  if (xs[0] > 0) { xs = [0, ...xs]; ys = [ys[0], ...ys]; } if (xs[xs.length - 1] < 1) { xs = [...xs, 1]; ys = [...ys, ys[ys.length - 1]]; }
  const n = xs.length; const h = xs.slice(1).map((x, i) => Math.max(1e-6, x - xs[i])); const d = h.map((hh, i) => (ys[i + 1] - ys[i]) / hh);
  const m = ys.map(() => 0); for (let i = 1; i < n - 1; i++) m[i] = d[i - 1] * d[i] > 0 ? 2 / (1 / d[i - 1] + 1 / d[i]) : 0; m[0] = d[0]; m[n - 1] = d[n - 2];
  return (x) => { let i = 0; while (i < n - 2 && x > xs[i + 1]) i++; const t = (x - xs[i]) / h[i];
    return (2 * t ** 3 - 3 * t * t + 1) * ys[i] + (t ** 3 - 2 * t * t + t) * h[i] * m[i] + (-2 * t ** 3 + 3 * t * t) * ys[i + 1] + (t ** 3 - t * t) * h[i] * m[i + 1]; };
}
function colorTables(c) {
  const wh = c.wheels || {}; const cv = c.curves || {}; const amt = clamp(+(c.amount ?? 1), 0, 1);
  const mf = cv.master?.length >= 2 ? pchip([...cv.master].sort((a, b) => a[0] - b[0])) : null;
  return ["r", "g", "b"].map((ch) => { const val2 = (k) => +(wh[k]?.[ch] || 0) + +(wh[k]?.y || 0); const cf = cv[ch]?.length >= 2 ? pchip([...cv[ch]].sort((a, b) => a[0] - b[0])) : null;
    const out = []; for (let i = 0; i < 33; i++) { const x0 = i / 32; let x = x0;
      const lift = val2("lift") * 0.25, gain = 1 + val2("gain") * 0.5, gamma = Math.max(0.2, 1 + val2("gamma") * 0.6);
      x = gain * (x + lift * (1 - x)); x = Math.pow(Math.max(0, x), 1 / gamma); x += val2("offset") * 0.25;
      if (mf) x = mf(clamp(x, 0, 1)); if (cf) x = cf(clamp(x, 0, 1));
      out.push(clamp(x0 + (x - x0) * amt, 0, 1).toFixed(4)); } return out.join(" "); });
}
const neutralColor = (c) => !c || c.enabled === false || (!Object.values(c.wheels || {}).some((w) => Object.values(w || {}).some((v) => Math.abs(+v) > 1e-4)) && !Object.values(c.curves || {}).some((p) => (p || []).some(([a, b]) => Math.abs(a - b) > 1e-4)));
export function colorFilter(c, id) {
  const ed = E(); if (!c || neutralColor(c)) return "";
  let svg = $("#vv-colsvg", ed.root); if (!svg) { svg = document.createElementNS("http://www.w3.org/2000/svg", "svg"); svg.id = "vv-colsvg"; svg.setAttribute("width", "0"); svg.setAttribute("height", "0"); svg.style.position = "absolute"; ed.root.appendChild(svg); }
  const fid = "vvc-" + String(id).replace(/[^\w-]/g, ""); const [tr, tg, tb] = colorTables(c); const key = tr + tg + tb;
  let f = svg.querySelector("#" + fid);
  if (!f || f._k !== key) { if (!f) { f = document.createElementNS("http://www.w3.org/2000/svg", "filter"); f.id = fid; f.setAttribute("color-interpolation-filters", "sRGB"); svg.appendChild(f); }
    f.innerHTML = `<feComponentTransfer><feFuncR type="table" tableValues="${tr}"/><feFuncG type="table" tableValues="${tg}"/><feFuncB type="table" tableValues="${tb}"/></feComponentTransfer>`; f._k = key; }
  return `url(#${fid})`;
}
const renderOnlyColor = (c) => !!(c && ((c.hsl || []).length || c.match));

// ---------------------------------------------------------------- colour UI: wheels, curves, HSL, match (main video + overlay clips)
// colour holder: { id, get() → color object (created), reset(), clip?() → colour-match source of an overlay clip }
const COLS = new Map();
export function colReg(id, get, extra = {}) { COLS.set(id, { id, get, ...extra }); return id; }
const WHEEL_L = { lift: "Lift · shadows", gamma: "Gamma · mid", gain: "Gain · highlights", offset: "Offset · सब" };
function puckXY(w) { const s = 0.5; const r = +(w?.r || 0), g = +(w?.g || 0), b = +(w?.b || 0); return [(2 * r - g - b) / (3 * s), (g - b) / (Math.sqrt(3) * s)]; }
function rgbOfPuck(px, py) { const s = 0.5; return { r: r3(px * s), g: r3((-px / 2 + py * Math.sqrt(3) / 2) * s), b: r3((-px / 2 - py * Math.sqrt(3) / 2) * s) }; }
const CCOL = { master: "#e8e8e8", r: "#ff5a5a", g: "#4ade80", b: "#60a5fa" };
const cP = (x, y) => `${(8 + x * 184).toFixed(1)},${(192 - y * 184).toFixed(1)}`;
function curvePath(p) { const f = pchip([...p].sort((a, b) => a[0] - b[0])); return Array.from({ length: 65 }, (_, i) => cP(i / 64, clamp(f(i / 64), 0, 1))).join(" "); }
const cDots = (p, ch) => p.map((q, i) => `<circle cx="${8 + q[0] * 184}" cy="${192 - q[1] * 184}" r="5" data-cpt="${i}" style="fill:${CCOL[ch]}"/>`).join("");
export function colorHtml(id, dis) {
  const h = COLS.get(id); const c = h.get(); const wh = c.wheels || {}; const tab = E().curveCh || "master";
  const wheels = (PP().color?.wheels || ["lift", "gamma", "gain", "offset"]).map((k) => { const [px, py] = puckXY(wh[k]); const d = Math.hypot(px, py); const k2 = d > 1 ? 1 / d : 1;
    return `<div class="whl" data-whl="${id}|${k}"><span class="small">${WHEEL_L[k] || k}</span><div class="whd" title="puck खींचें = रंग · double-click = reset"><i class="pk" style="left:${50 + px * k2 * 50}%;top:${50 - py * k2 * 50}%"></i></div>
      <input type="range" data-wy="${id}|${k}" min="-1" max="1" step="0.01" value="${+(wh[k]?.y || 0)}" title="master (सब रंग) — ${k === "gamma" ? "+ = mid-tones रोशन" : k === "gain" ? "+ = highlights रोशन" : k === "lift" ? "+ = shadows ऊपर" : "पूरी रेंज"}" ${dis}></div>`; }).join("");
  const cv = (c.curves || {})[tab] || [[0, 0], [1, 1]];
  const hsl = c.hsl || [];
  return `<div class="colbox"><h5>Colour wheels</h5><div class="whgrid">${wheels}</div>
    <h5>Curves</h5><div class="seg" style="margin-bottom:.3rem">${["master", "r", "g", "b"].map((k) => `<button data-cch="${k}" class="${tab === k ? "on" : ""}">${{ master: "RGB", r: "R", g: "G", b: "B" }[k]}</button>`).join("")}</div>
    <svg class="curve" viewBox="0 0 200 200" data-curve="${id}"><title>क्लिक = point जोड़ें · खींचें · double-click = हटाएँ</title><rect x="8" y="8" width="184" height="184" class="cbg"/>${[0.25, 0.5, 0.75].map((g) => `<line x1="${8 + g * 184}" y1="8" x2="${8 + g * 184}" y2="192"/><line x1="8" y1="${8 + g * 184}" x2="192" y2="${8 + g * 184}"/>`).join("")}
      <line x1="8" y1="192" x2="192" y2="8" class="cdiag"/><polyline points="${curvePath(cv)}" style="stroke:${CCOL[tab]}" class="cline"/>${cDots(cv, tab)}</svg>
    <h5>HSL (एक रंग बदलें)</h5>
    ${hsl.map((s, i) => `<div class="hslrow"><div class="hue" data-hsl="${id}|${i}" title="कौन-सा रंग: पट्टी पर खींचें"><i style="left:${(s.hue / 360 * 100).toFixed(1)}%;width:${(s.range / 360 * 100).toFixed(1)}%"></i></div>
      <div class="irow">${hslR(id, i, "range", "चौड़ाई°", 5, 180, 1, s.range, dis)}${hslR(id, i, "softness", "नरम°", 0, 90, 1, s.softness, dis)}</div>
      <div class="irow">${hslR(id, i, "hue_shift", "रंग घुमाएँ°", -180, 180, 1, s.hue_shift, dis)}${hslR(id, i, "sat", "saturation", -1, 1, 0.01, s.sat, dis)}${hslR(id, i, "lum", "रोशनी", -1, 1, 0.01, s.lum, dis)}</div>
      <button class="btn small quiet" data-hsldel="${id}|${i}" ${dis}>✕ हटाएँ</button></div>`).join("")}
    ${hsl.length < 8 ? `<div class="irow"><button class="btn small quiet" data-hsladd="${id}|30" ${dis} title="त्वचा (skin) — orange रंग">+ skin</button><button class="btn small quiet" data-hsladd="${id}|210" ${dis} title="नीला आसमान">+ आसमान</button><button class="btn small quiet" data-hsladd="${id}|120" ${dis} title="हरा">+ हरियाली</button><button class="btn small quiet" data-hsladd="${id}|0" ${dis}>+ लाल</button></div>` : ""}
    ${matchHtml(id, c, dis)}
    <div class="irow">${H.field(`कुल असर <b>${Math.round((c.amount ?? 1) * 100)}%</b>`, `<input type="range" data-camt="${id}" min="0" max="1" step="0.05" value="${c.amount ?? 1}" ${dis}>`)}<button class="btn small quiet" data-creset="${id}" ${dis}>colour reset</button></div>
    ${renderOnlyColor(c) ? `<p class="small muted rhint">HSL / colour match preview में नहीं — <b>render में दिखेगा</b> (🎞 Preview frame)।</p>` : `<p class="small muted">wheels + curves preview में live — render जैसा ही।</p>`}</div>`;
}
const hslR = (id, i, k, l, mn, mx, st, v, dis) => H.field(`${l} <b>${(+v).toFixed(st < 1 ? 2 : 0)}</b>`, `<input type="range" data-hslp="${id}|${i}|${k}" min="${mn}" max="${mx}" step="${st}" value="${v}" ${dis}>`);
function matchHtml(id, c, dis) {
  const h = COLS.get(id); const lib = (E().lib || []).filter((x) => ["broll", "image"].includes(x.kind));
  return `<h5>Colour match</h5><p class="small muted">${h.clip ? "इस clip का रंग main video (playhead वाला frame) जैसा करें — या कोई और reference चुनें।" : "पूरे वीडियो का रंग किसी reference clip/image जैसा करें (या In mark वाले frame जैसा)।"}</p>
    <div class="irow"><select data-cmref="${id}" class="small" style="flex:1" ${dis}>${h.clip ? `<option value="project">Main video · playhead frame</option>` : `<option value="mark">Main video · In (I) mark वाला frame</option>`}${lib.map((x) => `<option value="lib:${x.id}">${esc(x.name.slice(0, 28))}</option>`).join("")}</select>
      <button class="btn small" data-cmgo="${id}" ${dis}>🎯 Match</button>${c.match ? `<button class="btn small quiet" data-cmclr="${id}" ${dis}>हटाएँ</button>` : ""}</div>
    ${c.match ? `<div class="irow">${H.field(`match असर <b>${Math.round((c.match.amount ?? 1) * 100)}%</b>`, `<input type="range" data-cmamt="${id}" min="0" max="1" step="0.05" value="${c.match.amount ?? 1}" ${dis}>`)}</div>` : ""}`;
}
export function bindColor(root, after) {
  const ed = E(); const done = (re) => { H.touch(); after?.(); if (re) H.rerender(); };
  for (const w of $$("[data-whl]", root)) {
    const [id, k] = w.dataset.whl.split("|"); const h = COLS.get(id); if (!h) continue; const disc = $(".whd", w);
    const setFrom = (ev) => { const r = disc.getBoundingClientRect(); let px = ((ev.clientX - r.left) / r.width - 0.5) * 2, py = -((ev.clientY - r.top) / r.height - 0.5) * 2; const d = Math.hypot(px, py); if (d > 1) { px /= d; py /= d; }
      if (Math.abs(px) < 0.05 && Math.abs(py) < 0.05) px = py = 0;
      const c = h.get(); c.wheels = c.wheels || {}; c.wheels[k] = { ...(c.wheels[k] || {}), ...rgbOfPuck(px, py) }; const pk = $(".pk", w); pk.style.left = 50 + px * 50 + "%"; pk.style.top = 50 - py * 50 + "%"; after?.(); };
    disc.onpointerdown = (e) => { if (!ed.canEdit || e.button > 0) return; e.preventDefault(); setFrom(e); H.track(e, (ev) => setFrom(ev), () => done(false), 0); };
    disc.ondblclick = () => { if (!ed.canEdit) return; const c = h.get(); if (c.wheels?.[k]) c.wheels[k] = { y: c.wheels[k].y || 0 }; done(true); };
  }
  $$("[data-wy]", root).forEach((el) => (el.oninput = () => { const [id, k] = el.dataset.wy.split("|"); const c = COLS.get(id).get(); c.wheels = c.wheels || {}; c.wheels[k] = { ...(c.wheels[k] || {}), y: +el.value }; H.touch(); after?.(); }));
  $$("[data-cch]", root).forEach((b) => (b.onclick = () => { ed.curveCh = b.dataset.cch; H.rerender(); }));
  for (const svg of $$("[data-curve]", root)) {
    const h = COLS.get(svg.dataset.curve); const ch = ed.curveCh || "master";
    const pts = () => { const c = h.get(); c.curves = c.curves || {}; if (!c.curves[ch]) c.curves[ch] = [[0, 0], [1, 1]]; return c.curves[ch]; };
    const redraw = (p) => { $(".cline", svg).setAttribute("points", curvePath(p)); $$("[data-cpt]", svg).forEach((c) => c.remove()); svg.insertAdjacentHTML("beforeend", cDots(p, ch)); };
    const at = (ev) => { const r = svg.getBoundingClientRect(); return [clamp(((ev.clientX - r.left) / r.width * 200 - 8) / 184, 0, 1), clamp((192 - (ev.clientY - r.top) / r.height * 200) / 184, 0, 1)]; };
    const drag = (e, i) => { const p = pts(); const n = p.length; H.track(e, (ev) => { const [x, y] = at(ev); const lo = i > 0 ? p[i - 1][0] + 0.01 : 0, hi = i < n - 1 ? p[i + 1][0] - 0.01 : 1;
      p[i] = [i === 0 ? p[0][0] : i === n - 1 ? p[n - 1][0] : r3(clamp(x, lo, hi)), r3(y)]; redraw(p); after?.(); }, () => done(false), 0); };
    svg.onpointerdown = (e) => { if (!ed.canEdit || e.button > 0) return; e.preventDefault(); const c = e.target.closest("[data-cpt]"); if (c) return drag(e, +c.dataset.cpt);
      const [x, y] = at(e); const p = pts(); if (p.length >= 16) return; let i = p.findIndex((q) => q[0] > x); if (i < 0) i = p.length; if (i === 0) i = 1; p.splice(i, 0, [r3(x), r3(y)]); redraw(p); drag(e, i); };
    svg.ondblclick = (e) => { const c = e.target.closest("[data-cpt]"); if (!c || !ed.canEdit) return; const p = pts(); const i = +c.dataset.cpt; if (i > 0 && i < p.length - 1) { p.splice(i, 1); done(true); } };
  }
  for (const hu of $$("[data-hsl]", root)) {
    const [id, i] = hu.dataset.hsl.split("|"); const h = COLS.get(id);
    hu.onpointerdown = (e) => { if (!ed.canEdit) return; e.preventDefault(); const set = (ev) => { const r = hu.getBoundingClientRect(); const s = h.get().hsl[+i]; s.hue = Math.round(clamp((ev.clientX - r.left) / r.width, 0, 1) * 360); $("i", hu).style.left = (s.hue / 360 * 100) + "%"; after?.(); }; set(e); H.track(e, set, () => done(false), 0); };
  }
  $$("[data-hslp]", root).forEach((el) => (el.oninput = () => { const [id, i, k] = el.dataset.hslp.split("|"); const s = COLS.get(id).get().hsl[+i]; s[k] = +el.value; const lb = el.closest(".ifield")?.querySelector("label b"); if (lb) lb.textContent = (+el.value).toFixed(+el.step < 1 ? 2 : 0); if (k === "range") el.closest(".hslrow").querySelector(".hue i").style.width = (s.range / 360 * 100) + "%"; H.touch(); after?.(); }));
  $$("[data-hsladd]", root).forEach((b) => (b.onclick = () => { const [id, hue] = b.dataset.hsladd.split("|"); const c = COLS.get(id).get(); c.hsl = c.hsl || []; c.hsl.push({ ...(PP().color?.hsl_item || {}), hue: +hue, range: 40, softness: 20, sat: hue === "30" ? -0.15 : 0.25, lum: 0, hue_shift: 0 }); done(true); }));
  $$("[data-hsldel]", root).forEach((b) => (b.onclick = () => { const [id, i] = b.dataset.hsldel.split("|"); const c = COLS.get(id).get(); c.hsl.splice(+i, 1); if (!c.hsl.length) delete c.hsl; done(true); }));
  $$("[data-camt]", root).forEach((el) => (el.oninput = () => { const c = COLS.get(el.dataset.camt).get(); c.amount = +el.value; const lb = el.closest(".ifield")?.querySelector("label b"); if (lb) lb.textContent = Math.round(c.amount * 100) + "%"; H.touch(); after?.(); }));
  $$("[data-creset]", root).forEach((b) => (b.onclick = () => { COLS.get(b.dataset.creset).reset(); done(true); }));
  $$("[data-cmamt]", root).forEach((el) => (el.oninput = () => { const c = COLS.get(el.dataset.cmamt).get(); if (c.match) c.match.amount = +el.value; const lb = el.closest(".ifield")?.querySelector("label b"); if (lb) lb.textContent = Math.round(+el.value * 100) + "%"; H.touch(); }));
  $$("[data-cmclr]", root).forEach((b) => (b.onclick = () => { delete COLS.get(b.dataset.cmclr).get().match; done(true); }));
  $$("[data-cmgo]", root).forEach((b) => (b.onclick = async () => {
    const h = COLS.get(b.dataset.cmgo); const refSel = $(`[data-cmref="${h.id}"]`, root).value; b.disabled = true; b.textContent = "मिला रहे…";
    try {
      if (refSel === "mark" && ed.markIn == null) ed.ctx.toast("In (I) mark नहीं लगा — playhead वाला frame लिया");
      const ref = refSel === "project" ? { kind: "project", t: +ed.t.toFixed(2) } : refSel === "mark" ? { kind: "project", t: +(ed.markIn ?? ed.t).toFixed(2) } : { kind: "library", id: refSel.slice(4), t: 1 };
      const clip = h.clip ? h.clip() : { kind: "project", t: +ed.t.toFixed(2) };
      await H.flush(); const r = await ed.ctx.api("POST", `/projects/${ed.pid}/color/match`, { clip, ref, amount: 1 });
      h.get().match = r.color.match; done(true); ed.ctx.toast("🎯 Colour match लगा — 🎞 Preview frame / render में देखें");
    } catch (err) { ed.ctx.toast(err.message); b.disabled = false; b.textContent = "🎯 Match"; }
  }));
}

// ---------------------------------------------------------------- mask editor (overlay clip `mask` / main video `effects.pro.mask`)
const SHAPE_ICON = {
  circle: '<circle cx="12" cy="12" r="8"/>', ellipse: '<ellipse cx="12" cy="12" rx="9" ry="6"/>', rect: '<rect x="4" y="6" width="16" height="12" rx="3"/>',
  heart: '<path d="M12 20s-7-4.5-7-10a4 4 0 017-2.6A4 4 0 0119 10c0 5.5-7 10-7 10z"/>', star: '<path d="M12 3l2.6 5.6 6 .7-4.5 4.1 1.2 6L12 16.4 6.7 19.4l1.2-6L3.4 9.3l6-.7z"/>',
  linear: '<path d="M4 4h8v16H4z" fill="currentColor" stroke="none" opacity=".5"/><path d="M12 3v18"/>', polygon: '<path d="M5 9l7-5 8 6-3 9H7z" fill="currentColor" stroke="none" opacity=".5"/><path d="M5 9l7-5 8 6-3 9H7z"/>', mirror: '<path d="M3 9h18v6H3z" fill="currentColor" stroke="none" opacity=".5"/><path d="M3 9h18M3 15h18"/>',
};
export function maskHtml(oid, m, dis, opts = {}) {
  const shapes = PP().masks?.shapes || {}; const o = OWN.get(oid); const sh = m?.shape || "";
  const bgv = String(m?.bg || "black").startsWith("#") ? "color" : m?.bg || "black";
  return `<div class="shapes">${[["", "कोई mask नहीं", '<path d="M5 5l14 14M19 5L5 19"/>'], ...Object.entries(shapes).map(([k, l]) => [k, l, SHAPE_ICON[k] || ""])].map(([k, l, ic]) => `<button class="shp ${sh === k ? "on" : ""}" data-mshape="${oid}|${k}" title="${esc(l)}" ${dis}><svg viewBox="0 0 24 24">${ic}</svg></button>`).join("")}</div>
    ${sh ? `<div class="irow"><label class="chk small"><input type="checkbox" data-minv="${oid}" ${m.invert ? "checked" : ""} ${dis}> उल्टा (invert)</label><button class="btn small ${E().maskEdit ? "primary" : "quiet"}" data-medit="${oid}" title="preview पर mask: बीच से खींचें = जगह, कोने = size, ऊपर का गोला = घुमाव" ${dis}>✎ preview पर handles</button></div>
      ${opts.bg ? `<div class="irow">${H.field("mask के बाहर", `<select data-mbg="${oid}" class="small" ${dis}>${[["black", "काला"], ["blur", "blur"], ["color", "रंग"]].map(([v, l]) => `<option value="${v}" ${bgv === v ? "selected" : ""}>${l}</option>`).join("")}</select>`)}${bgv === "color" ? H.field("रंग", `<input type="color" data-mbgc="${oid}" value="${m.bg}" ${dis}>`) : ""}</div>` : ""}
      ${["feather", "x", "y", "w", ...(["circle", "linear"].includes(sh) ? [] : ["h"]), "rotation", ...(sh === "rect" ? ["roundness"] : [])].map((p) => kfSlider(o, p, dis)).join("")}
      ${sh === "polygon" ? `<div class="irow"><button class="btn small ${E().polyMode === "add" ? "primary" : "quiet"}" data-poly="${oid}|add" ${dis} title="preview पर click करके कोने जोड़ें">＋ कोने (click)</button><button class="btn small ${E().polyMode === "draw" ? "primary" : "quiet"}" data-poly="${oid}|draw" ${dis} title="preview पर उँगली/mouse से आकार खींचें">✍ freehand</button><button class="btn small quiet" data-poly="${oid}|clear" ${dis}>साफ़ करें</button><span class="small muted">${(m.pts || []).length} कोने${(m.pts || []).length < 3 ? " — कम से कम 3 चाहिए" : ""} · कोने खींचकर बदलें, double-click = हटाएँ</span></div>` : ""}
      ${sh === "star" ? `<div class="irow">${H.field(`कोने <b>${m.points || 5}</b>`, `<input type="range" data-mstar="${oid}|points" min="3" max="12" step="1" value="${m.points || 5}" ${dis}>`)}${H.field(`अंदर <b>${m.inner || 0.4}</b>`, `<input type="range" data-mstar="${oid}|inner" min="0.1" max="0.9" step="0.01" value="${m.inner || 0.4}" ${dis}>`)}</div>` : ""}` : ""}`;
}
export function bindMask(root, getMask, setMask, after) {
  $$("[data-mshape]", root).forEach((b) => (b.onclick = () => { const k = b.dataset.mshape.split("|")[1]; if (!k) { setMask(null); E().maskEdit = false; }
    else { const m = getMask() || {}; const d = Object.fromEntries((PP().masks?.params || []).filter((x) => x.name !== "points" && x.name !== "inner").map((x) => [x.name, x.default])); setMask({ ...d, ...m, shape: k, enabled: true, ...(k === "linear" ? { w: 1, h: 1 } : {}), ...(k === "polygon" ? { pts: m.pts || [], w: 0.6, h: 0.6, x: 0.5, y: 0.5, rotation: 0 } : {}) }); E().maskEdit = true; if (k === "polygon" && !(m.pts || []).length) E().polyMode = "add"; }
    H.touch(); after?.(); H.rerender(); H.renderOverlay(); }));
  $$("[data-minv]", root).forEach((el) => (el.onchange = () => { getMask().invert = el.checked; H.touch(); after?.(); }));
  $$("[data-medit]", root).forEach((b) => (b.onclick = () => { E().maskEdit = !E().maskEdit; H.rerender(); H.renderOverlay(); }));
  $$("[data-mbg]", root).forEach((el) => (el.onchange = () => { getMask().bg = el.value === "color" ? "#111111" : el.value; H.touch(); after?.(); H.rerender(); }));
  $$("[data-mbgc]", root).forEach((el) => (el.oninput = () => { getMask().bg = el.value; H.touch(); after?.(); }));
  $$("[data-poly]", root).forEach((b) => (b.onclick = () => { const k = b.dataset.poly.split("|")[1]; const ed = E(); const m = getMask(); if (!m) return;
    if (k === "clear") { m.pts = []; ed.polyMode = "add"; } else ed.polyMode = ed.polyMode === k ? "" : k; ed.maskEdit = true; H.touch(); after?.(); H.rerender(); H.renderOverlay(); }));
  $$("[data-mstar]", root).forEach((el) => (el.oninput = () => { const k = el.dataset.mstar.split("|")[1]; getMask()[k] = +el.value; const lb = el.closest(".ifield")?.querySelector("label b"); if (lb) lb.textContent = el.value; H.touch(); after?.(); }));
}

// ====================================================================== overlay clip inspector
const SECS = () => (E().secs = E().secs || LS("vividora_secs", { tf: true, speed: true }));
const sec = (k, title, body, badge = "") => `<details class="insp psec" data-sec="${k}" ${SECS()[k] ? "open" : ""}><summary>${title}${badge ? ` <span class="tag">${badge}</span>` : ""}</summary>${body}</details>`;
function bindSecs(root) { $$("details[data-sec]", root).forEach((d) => (d.ontoggle = () => { SECS()[d.dataset.sec] = d.open; LSset("vividora_secs", SECS()); })); }
const SPEEDS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4];
const FRM = '<rect x="1" y="1" width="16" height="22" rx="2" class="lf"/>';
const LAYOUT_IC = { full: FRM + '<rect x="1" y="1" width="16" height="22" rx="2" class="lc"/>', tl: FRM + '<rect x="2.5" y="2.5" width="7" height="7" rx="1" class="lc"/>', tr: FRM + '<rect x="8.5" y="2.5" width="7" height="7" rx="1" class="lc"/>',
  bl: FRM + '<rect x="2.5" y="12" width="7" height="7" rx="1" class="lc"/>', br: FRM + '<rect x="8.5" y="12" width="7" height="7" rx="1" class="lc"/>',
  s2: FRM + '<rect x="1" y="1" width="16" height="11" class="lc"/><rect x="1" y="12" width="16" height="11" class="lc2"/>', s3: FRM + '<rect x="1" y="1" width="16" height="7.3" class="lc"/><rect x="1" y="8.3" width="16" height="7.3" class="lc2"/><rect x="1" y="15.6" width="16" height="7.4" class="lc"/>' };
export function brollInspector(it, dis) {
  const ed = E(); const item = H.libItem(it.id); const isVid = item?.kind === "broll"; const fit = it.fit || "cover";
  const o = clipOwner(it); const mo = maskOwner("mask:" + it._id, () => it.mask, +it.start, it.end - it.start);
  colReg("col:" + it._id, () => (it.color = it.color || {}), { reset: () => delete it.color, clip: () => ({ kind: "library", id: it.id, t: +((+it.trim_in || 0) + srcOffset(it, clamp(H.outOf(ed.t) - it.start, 0, it.end - it.start))).toFixed(2) }) });
  const ramp = rampOf(it); const len = it.end - it.start; const sp = spd(it);
  const badge = [ramp ? "⤳ curve" : sp !== 1 ? sp + "×" : "", it.mask?.shape ? "mask" : "", it.blend_mode && it.blend_mode !== "normal" ? it.blend_mode : "", +it.volume > 0 ? "🔊" : ""].filter(Boolean).join(" · ");
  const BM = PP().blend_modes || { normal: "Normal" };
  // --- basics
  let h = `<h3>${isVid ? "Video clip" : item?.kind === "image" ? "Image" : "Sticker / overlay"} ${badge ? `<span class="tag">${esc(badge)}</span>` : ""}</h3><p class="small muted">${esc(item?.name || "?")}${item?.meta?.duration ? ` · source ${H.fmt(item.meta.duration)}` : ""}${item?.meta?.width ? ` · ${item.meta.width}×${item.meta.height}` : ""}</p>
    <div class="irow">${H.field("शुरू", H.num("start", it.start, 0.1, 0))}${H.field("ख़त्म", H.num("end", it.end, 0.1, 0))}${H.field("track", H.num("track", it.track || 0, 1, 0, 9))}</div>
    <div class="irow">${H.field("कैसे", `<select data-k="fit" ${dis}>${[["cover", "पूरा frame (cover)"], ["contain", "पूरा दिखे (contain)"], ["pip", "छोटा box (PiP)"], ["free", "free (जगह/size/घुमाव)"]].map(([v, l]) => `<option value="${v}" ${fit === v ? "selected" : ""}>${l}</option>`).join("")}</select>`)}
      ${fit === "pip" ? H.field("कोना", `<select data-k="pos" ${dis}>${["tr", "tl", "br", "bl"].map((p) => `<option value="${p}" ${(it.pos || "tr") === p ? "selected" : ""}>${{ tr: "ऊपर दाएँ", tl: "ऊपर बाएँ", br: "नीचे दाएँ", bl: "नीचे बाएँ" }[p]}</option>`).join("")}</select>`) : ""}
      ${fit === "free" ? H.field(`size <b>${(+(it.scale ?? 0.4)).toFixed(2)}</b>`, `<input type="range" data-k="scale" min="0.03" max="2.5" step="0.01" value="${it.scale ?? 0.4}" ${dis}>`) : ""}</div>
    <div class="box" style="margin:6px 0;padding:8px 10px;border-left:3px solid var(--accent,#7c3aed)"><b class="small">🎬 Smart Layout (render में)</b>
      <div class="irow">${H.field("layout mode", `<select data-k="layout" ${dis}>${[["", "Default (fullscreen)"], ["behind", "🧑 Smart — इंसान सामने, B-roll पीछे"], ["pip", "📺 PiP — छोटी window"], ["split", "⬛⬜ Split screen"], ["overlay", "🌫 Semi-transparent overlay"]].map(([v, l]) => `<option value="${v}" ${(it.layout || "") === v ? "selected" : ""}>${l}</option>`).join("")}</select>`)}</div>
      ${(it.layout || "") === "behind" ? `<div class="irow">${H.field(`edge softness <b>${(+(it.edge_feather ?? 0)).toFixed(1)}</b>`, `<input type="range" data-pk="edge_feather" min="0" max="30" step="1" value="${it.edge_feather ?? 0}" ${dis}>`)}${H.field(`shrink <b>${(+(it.edge_shrink ?? 0)).toFixed(1)}</b>`, `<input type="range" data-pk="edge_shrink" min="0" max="20" step="1" value="${it.edge_shrink ?? 0}" ${dis}>`)}</div><p class="small muted">person matte (cutout) ज़रूरी — नहीं है तो auto बनेगा render में। edge feather = धुँधला किनारा।</p>` : ""}
      ${(it.layout || "") === "pip" ? `<div class="irow">${H.field("corner", `<select data-pk="pip_corner" ${dis}>${[["br", "नीचे दाएँ"], ["bl", "नीचे बाएँ"], ["tr", "ऊपर दाएँ"], ["tl", "ऊपर बाएँ"]].map(([v, l]) => `<option value="${v}" ${(it.pip_corner || "br") === v ? "selected" : ""}>${l}</option>`).join("")}</select>`)}${H.field(`size <b>${Math.round((+(it.pip_size ?? 0.28)) * 100)}%</b>`, `<input type="range" data-pk="pip_size" min="0.15" max="0.4" step="0.02" value="${it.pip_size ?? 0.28}" ${dis}>`)}</div>
        <div class="irow">${H.field(`radius <b>${+(it.pip_radius ?? 12)}</b>`, `<input type="range" data-pk="pip_radius" min="0" max="40" step="2" value="${it.pip_radius ?? 12}" ${dis}>`)}${H.field(`feather <b>${+(it.feather ?? 6)}</b>`, `<input type="range" data-pk="feather" min="0" max="24" step="2" value="${it.feather ?? 6}" ${dis}>`)}</div>` : ""}
      ${(it.layout || "") === "split" ? `<div class="irow">${H.field("ratio", `<select data-pk="split_ratio" ${dis}>${[["50_50", "50/50"], ["60_40", "60/40 (इंसान ज़्यादा)"], ["40_60", "40/60 (B-roll ज़्यादा)"]].map(([v, l]) => `<option value="${v}" ${(it.split_ratio || "50_50") === v ? "selected" : ""}>${l}</option>`).join("")}</select>`)}${H.field("side", `<select data-pk="split_side" ${dis}>${[["person_left", "इंसान बाएँ"], ["person_right", "इंसान दाएँ"]].map(([v, l]) => `<option value="${v}" ${(it.split_side || "person_left") === v ? "selected" : ""}>${l}</option>`).join("")}</select>`)}</div>
        ${H.field(`seam feather <b>${+(it.feather ?? 12)}</b>`, `<input type="range" data-pk="feather" min="0" max="40" step="2" value="${it.feather ?? 12}" ${dis}>`)}` : ""}
      ${(it.layout || "") === "overlay" ? `<div class="irow">${H.field(`opacity <b>${Math.round((+(it.opacity ?? 0.35)) * 100)}%</b>`, `<input type="range" data-pk="opacity" min="0.05" max="0.95" step="0.05" value="${it.opacity ?? 0.35}" ${dis}>`)}${H.field(`feather <b>${+(it.feather ?? 18)}</b>`, `<input type="range" data-pk="feather" min="0" max="40" step="2" value="${it.feather ?? 18}" ${dis}>`)}</div>` : ""}
    </div>
    <div class="layouts"><span class="small muted">Layout</span>${[["full", "पूरा frame", LAYOUT_IC.full], ["pip_tl", "PiP ऊपर बाएँ", LAYOUT_IC.tl], ["pip_tr", "PiP ऊपर दाएँ", LAYOUT_IC.tr], ["pip_bl", "PiP नीचे बाएँ", LAYOUT_IC.bl], ["pip_br", "PiP नीचे दाएँ", LAYOUT_IC.br], ["2up", "2-up split screen", LAYOUT_IC.s2], ["3up", "3-up split screen", LAYOUT_IC.s3]].map(([k, l, ic]) => `<button class="lyb" data-layout="${k}" title="${l}${k.endsWith("up") ? " — इसी समय के सारे overlay clips (दूसरे V tracks पर) एक साथ" : ""}" ${dis}><svg viewBox="0 0 18 24">${ic}</svg></button>`).join("")}</div>`;
  // --- transform (keyframeable)
  h += sec("tf", "Position · Zoom · घुमाव", `${["x", "y", "scale", "rotation"].map((p) => kfSlider(o, p, dis)).join("")}
    ${it.to ? `<p class="small muted">पुराना "अंत में यहाँ पहुँचे" move लगा है <button class="btn small quiet" data-act2="to2kf" ${dis}>keyframes में बदलें</button></p>` : ""}
    <p class="small muted">◆ = keyframe। preview पर खींचने/घुमाने से भी keyframe बनते हैं जब उस property पर keyframe हो। <b>K</b> = सब एक साथ।</p>
    ${fit === "free" ? H.field("animation (आना/जाना)", `<select data-k="anim" ${dis}>${(ed.ctx.S.presets?.sticker_anims || [{ id: "none", label: "none" }]).map((a) => `<option value="${a.id}" ${(it.anim || "none") === a.id ? "selected" : ""}>${esc(a.label)}</option>`).join("")}</select>`) : ""}`, hasKf(it.kf, "x") || hasKf(it.kf, "y") || hasKf(it.kf, "scale") || hasKf(it.kf, "rotation") ? "◆" : "");
  // --- speed
  if (isVid) {
    const avail = srcAvail(it); const nat = naturalLen(it, avail);
    h += sec("speed", "Speed", `<div class="chips spd">${SPEEDS.map((s) => `<button class="${!ramp && Math.abs(sp - s) < 1e-3 ? "on" : ""}" data-spd="${s}" ${dis}>${s}×</button>`).join("")}<input type="number" data-spdc min="0.25" max="4" step="0.05" value="${ramp ? "" : sp}" placeholder="custom" title="custom speed 0.25–4" ${dis}></div>
      <div class="seg" style="margin:.35rem 0"><button data-spmode="normal" class="${ramp ? "" : "on"}">Normal</button><button data-spmode="curve" class="${ramp ? "on" : ""}" ${dis}>⤳ Curve (ramp)</button></div>
      ${ramp ? `<div class="chips">${Object.entries(RAMPS).map(([k, [l]]) => `<button data-ramp="${k}" ${dis}>${l}</button>`).join("")}</div>${rampSvg(it, avail)}<p class="small muted">point खींचें · खाली जगह क्लिक = नया point · double-click = हटाएँ · ऊपर = तेज़, नीचे = slow-mo</p>` : ""}
      <p class="small muted">इस speed पर पूरी clip: <b>${H.fmt(nat)}</b> (timeline पर अभी ${H.fmt(len)})${Math.abs(nat - len) > 0.15 ? ` <button class="btn small quiet" data-act2="fitlen" ${dis}>लंबाई = पूरी clip</button>` : ""}</p>
      ${H.field("Speed Warp (smooth slow-mo)", `<select data-pk="speed_warp" ${dis}>${Object.entries(PP().speed?.warp || { off: "Off" }).map(([k, l]) => `<option value="${k}" ${(it.speed_warp || "off") === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`)}
      ${(it.speed_warp || "off") !== "off" ? `<p class="small muted rhint">सिर्फ़ 0.75× से धीमे हिस्सों पर · render धीमा (${it.speed_warp === "best" ? "~0.3–1 fps" : it.speed_warp === "balanced" ? "~1–2 fps" : "+5 %"}) · <b>render में दिखेगा</b></p>` : ""}`, ramp ? "curve" : sp !== 1 ? sp + "×" : "");
    // --- trim
    const sd = +(item?.meta?.duration || 0);
    h += sec("trim", "Trim (clip का कौन-सा हिस्सा)", `<div class="irow">${H.field(`शुरू से काटें <b>${(+(it.trim_in || 0)).toFixed(2)}s</b>`, `<input type="range" data-pk="trim_in" min="0" max="${Math.max(0.1, sd - 0.1).toFixed(2)}" step="0.05" value="${+(it.trim_in || 0)}" ${dis}>`)}</div>
      <div class="irow">${H.field(`अंत (source) <b>${it.trim_out != null && it.trim_out !== "" ? (+it.trim_out).toFixed(2) + "s" : "पूरा"}</b>`, `<input type="range" data-pk="trim_out" min="0.1" max="${Math.max(0.2, sd).toFixed(2)}" step="0.05" value="${it.trim_out != null && it.trim_out !== "" ? +it.trim_out : sd}" ${dis}>`)}</div>
      <p class="small muted">source ${H.fmt(sd)} में से ${H.fmt(avail)} इस्तेमाल · clip ख़त्म होते ही overlay हट जाता है।</p>`, +(it.trim_in || 0) > 0 || (it.trim_out != null && it.trim_out !== "") ? "✂" : "");
  }
  // --- colour (filter preset + intensity, then wheels / curves / HSL / match)
  const cat = ed.ctx.S.presets?.catalog || { grade_presets: {} }; const thumb = (ed.p.assets.find((a) => a.kind === "thumb") || {}).url;
  const gp = it.grade_preset || ""; const gs = it.grade_strength ?? 1;
  h += sec("color", "Colour", `<div class="chips">${[["", "सब"], ...Object.entries(cat.grade_cats || {})].map(([k, l]) => `<button class="${(ed.gCatClip || "") === k ? "on" : ""}" data-gcc="${k}">${esc(l)}</button>`).join("")}</div>
    <div class="looks mini">${[["", { label: "कोई नहीं" }], ...Object.entries(cat.grade_presets).filter(([, p]) => !ed.gCatClip || p.cat === ed.gCatClip)].map(([k, p]) => `<button class="look ${gp === k ? "on" : ""}" data-cgp="${k}" ${dis} title="${esc(p.label)}">${thumb ? `<img src="${thumb}" style="filter:${k ? H.gradeCss(p) : ""}" alt="" loading="lazy">` : `<i></i>`}<small>${esc(p.label)}</small></button>`).join("")}</div>
    ${gp ? H.field(`intensity <b>${Math.round(gs * 100)}%</b>`, `<input type="range" data-cgs min="0" max="1.5" step="0.05" value="${gs}" ${dis}>`) : ""}
    ${(() => { const luts = (ed.lib || []).filter((x) => x.kind === "lut"); if (!luts.length && !it.lut) return ""; const la = it.lut_amount ?? 1;
      return `<div class="irow">${H.field("LUT (सिर्फ़ इस clip पर)", `<select data-clut class="small" ${dis}><option value="">कोई नहीं</option>${luts.map((x) => `<option value="${x.id}" ${it.lut === x.id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select>`)}${it.lut ? H.field(`LUT कितना <b>${Math.round(la * 100)}%</b>`, `<input type="range" data-cla min="0" max="1" step="0.05" value="${la}" ${dis}>`) : ""}</div>${it.lut ? `<p class="small muted rhint">LUT preview में नहीं — <b>render / 🎞 Preview frame</b> में दिखेगी।</p>` : ""}`; })()}
    <details class="insp sub" data-sec="ccol" ${SECS().ccol ? "open" : ""}><summary>Wheels · Curves · HSL · Colour match</summary>${colorHtml("col:" + it._id, dis)}</details>`, gp || !neutralColor(it.color) || renderOnlyColor(it.color) ? "●" : "");
  // --- effects stack (per clip)
  const effs = cat.effects || []; const stack = it.stack || [];
  h += sec("fx", "Effects (सिर्फ़ इस clip पर)", `${stack.map((s, i) => { const d = H.fxDef(s.id); if (!d) return ""; const so = paramOwner(`stk:${it._id}:${i}`, s, +it.start, len, d); const pr = H.fxParams(d, s.params);
      return `<div class="stk"><div class="row between"><b class="small">${esc(d.label)}</b><span class="row" style="gap:0">${d.preview === "css" ? "" : `<span class="tag" title="preview में नहीं — Preview frame / render">render में</span>`}<button class="ibtn" data-stkdel="${i}" ${dis}>✕</button></span></div>
        ${(d.params || []).map((p) => p.type === "color" ? H.field(esc(p.label), `<input type="color" data-stkc="${i}|${p.name}" value="${pr[p.name]}" ${dis}>`) : (so.spec[p.name] = [p.label, p.min, p.max, p.step || 1], kfSlider(so, p.name, dis))).join("")}</div>`; }).join("")}
    ${stack.length < 8 ? `<div class="irow"><select data-stkadd class="small" style="flex:1" ${dis}><option value="">+ effect जोड़ें…</option>${Object.entries(cat.categories || {}).map(([ck, cl]) => `<optgroup label="${esc(cl)}">${effs.filter((e) => e.cat === ck).map((e) => `<option value="${e.id}">${esc(e.label)}</option>`).join("")}</optgroup>`).join("")}</select></div>` : ""}`, stack.length ? String(stack.length) : "");
  // --- blend + opacity
  h += sec("blend", "Blend mode · Opacity", `${H.field("blend mode", `<select data-pk="blend_mode" ${dis}>${Object.entries(BM).map(([k, l]) => `<option value="${k}" ${(it.blend_mode || "normal") === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`)}
    ${it.blend_mode === "subtract" ? `<p class="small muted rhint">Subtract का CSS preview नहीं — <b>render में दिखेगा</b></p>` : ""}
    ${kfSlider(o, "opacity", dis)}
    <div class="irow">${H.field("background हटाएँ (keying)", `<select data-k="blend" ${dis}>${Object.entries(ed.ctx.S.presets?.blends || { normal: "Normal" }).map(([k, l]) => `<option value="${k}" ${(it.blend || "normal") === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`)}${["green", "blue", "black", "white"].includes(it.blend) ? H.field("कितना हटे", `<input type="range" data-k="key_sim" min="0.05" max="0.6" step="0.01" value="${it.key_sim ?? 0.25}" ${dis}>`) : ""}</div>`, it.blend_mode && it.blend_mode !== "normal" ? BM[it.blend_mode] : "");
  // --- transition from the previous clip on this track
  { const w = trWindow(it); const prev = trPrev(it); const kind = it.tr?.kind || "none";
    const warn = kind !== "none" ? (!prev ? `<p class="small muted rhint">⚠ इसी track पर इससे पहले कोई clip नहीं जो इसे छूती/overlap करती हो — transition नहीं लगेगी।</p>` : w.wd < 0.08 ? `<p class="small muted rhint">⚠ handles कम हैं: clips overlap नहीं करतीं — पिछली clip को इसके ऊपर खींचकर ${w.want.toFixed(1)}s overlap दें।</p>` : w.wd < w.want - 0.02 ? `<p class="small muted">overlap सिर्फ़ ${w.overlap.toFixed(2)}s → transition ${w.wd.toFixed(2)}s की होगी।</p>` : `<p class="small muted">preview में opacity crossfade; slide/zoom/wipe render में (🎞 Preview frame)।</p>`) : "";
    h += sec("tr", "Transition (पिछली clip से)", `<div class="irow">${H.field("किस तरह", `<select data-trk class="small" ${dis}>${Object.entries(TRANSITIONS).map(([k, l]) => `<option value="${k}" ${kind === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`)}${kind !== "none" ? H.field(`समय <b>${(+it.tr?.dur || 0.5).toFixed(1)}s</b>`, `<input type="range" data-trd min="0.1" max="3" step="0.1" value="${+it.tr?.dur || 0.5}" ${dis}>`) : ""}</div>${warn}`, kind !== "none" ? TRANSITIONS[kind] : ""); }
  // --- mask (+ crop)
  const cr = it.crop || { x: 0, y: 0, w: 1, h: 1 };
  h += sec("mask", "Mask · Crop", maskHtml(mo.id, it.mask, dis) + `<details class="insp sub" data-sec="crop" ${SECS().crop ? "open" : ""}><summary>Crop (clip के किनारे काटें)</summary><div class="irow">${["x", "y", "w", "h"].map((k) => H.field(`${{ x: "बाएँ", y: "ऊपर", w: "चौड़ाई", h: "ऊँचाई" }[k]} <b>${(+(cr[k] ?? (k === "w" || k === "h" ? 1 : 0))).toFixed(2)}</b>`, `<input type="range" data-crop="${k}" min="${k === "w" || k === "h" ? 0.05 : 0}" max="${k === "w" || k === "h" ? 1 : 0.95}" step="0.01" value="${cr[k] ?? (k === "w" || k === "h" ? 1 : 0)}" ${dis}>`)).join("")}</div>${it.crop ? `<button class="btn small quiet" data-act2="cropreset" ${dis}>crop हटाएँ</button>` : ""}</details>`, it.mask?.shape ? (PP().masks?.shapes?.[it.mask.shape] || it.mask.shape).split(" ")[0] : "");
  // --- keyframes list
  h += sec("kf", "Keyframes", kfListHtml(ed.sel, dis), kfTimes(ed.sel).length ? String(kfTimes(ed.sel).length) : "");
  // --- own audio
  if (isVid) h += sec("aud", "Audio (clip की अपनी आवाज़)", `<div class="irow"><label class="chk small"><input type="checkbox" data-amute ${+it.volume > 0 ? "" : "checked"} ${dis}> 🔇 mute</label>${H.field(`volume <b>${Math.round((+it.volume || 0) * 100)}%</b>`, `<input type="range" data-pk="volume" min="0" max="2" step="0.05" value="${+it.volume || 0}" ${dis}>`)}</div><p class="small muted">voice/music के साथ mix · speed बदलने पर pitch वही रहती है।</p>`, +it.volume > 0 ? Math.round(+it.volume * 100) + "%" : "mute");
  // --- cutout, platforms, actions
  h += `${isVid ? H.brollCutoutBox(it, item, dis) : ""}
    <div class="ifield"><label>किस platform पर दिखे (कोई नहीं चुना = सब पर)</label><div class="irow">${["youtube", "instagram", "facebook", "tiktok"].map((pl) => `<label class="chk small"><input type="checkbox" data-plat="${pl}" ${(it.platforms || []).includes(pl) ? "checked" : ""} ${dis}> ${{ youtube: "YouTube", instagram: "Instagram", facebook: "Facebook", tiktok: "TikTok" }[pl]}</label>`).join("")}</div></div>
    ${previewHints(it)}
    <div class="irow"><button class="btn small" data-act="seek">यहाँ जाएँ</button><button class="btn small quiet" data-zorder="up" ${dis} title="ऊपर वाले V track पर — दूसरी clips के आगे दिखेगी">⬆ आगे लाएँ</button><button class="btn small quiet" data-zorder="down" ${dis || (+(it.track || 0) <= 0 ? "disabled" : "")} title="नीचे वाले V track पर — दूसरी clips के पीछे">⬇ पीछे भेजें</button><button class="btn small danger quiet" data-act="del" ${dis}>${H.ICON.trash} हटाएँ</button></div>`;
  return h;
}
function previewHints(it) {
  const r = [];
  if ((it.speed_warp || "off") !== "off") r.push("Speed Warp"); if (renderOnlyColor(it.color)) r.push("HSL/colour match");
  if ((it.stack || []).some((s) => H.fxDef(s.id)?.preview !== "css")) r.push("कुछ effects"); if (it.blend_mode === "subtract") r.push("subtract blend");
  return r.length ? `<p class="small muted rhint">ℹ ${esc(r.join(", "))} — preview में नहीं, <b>render में दिखेगा</b>। बिल्कुल final frame: "🎞 Preview frame"।</p>` : "";
}
function rampSvg(it, avail) {
  const r = rampOf(it) || []; const W = 270, Hh = 120, pd = 10; const X = (s) => pd + s / avail * (W - 2 * pd); const Y = (v) => pd + (1 - (Math.log2(clamp(v, 0.25, 4)) + 2) / 4) * (Hh - 2 * pd);
  const path = Array.from({ length: 81 }, (_, i) => { const s = i / 80 * avail; return `${X(s).toFixed(1)},${Y(sample(r, s)).toFixed(1)}`; }).join(" ");
  return `<svg class="ramp" viewBox="0 0 ${W} ${Hh}" data-ramp-svg data-avail="${avail}">${[0.25, 0.5, 1, 2, 4].map((v) => `<line x1="${pd}" x2="${W - pd}" y1="${Y(v)}" y2="${Y(v)}" class="${v === 1 ? "one" : ""}"/><text x="${W - pd - 2}" y="${Y(v) - 2}">${v}×</text>`).join("")}
    <polyline points="${path}" class="rline"/>${r.map((k, i) => `<circle cx="${X(k.t)}" cy="${Y(k.v)}" r="6" data-rpt="${i}"><title>${k.v.toFixed(2)}× @ ${k.t.toFixed(2)}s (source)</title></circle>`).join("")}</svg>`;
}
// quick multi-video layouts: PiP corners, 2-up / 3-up split screen of the overlay clips under this one
function applyLayout(it, kind) {
  const ed = E(); const fx = ed.rs.effects; const fb = ed.frameBox || { w: 1080, h: 1920 }; const W = fb.w, Hh = fb.h;
  const clean = (b) => { delete b.to; if (b.kf) { delete b.kf.x; delete b.kf.y; delete b.kf.scale; delete b.kf.rotation; if (!Object.keys(b.kf).length) delete b.kf; } if (b.mask?.layout) delete b.mask; b.rotate = 0; };
  if (kind === "full") { clean(it); it.fit = "cover"; return 1; }
  if (kind.startsWith("pip_")) { clean(it); it.fit = "pip"; it.pos = kind.slice(4); return 1; }
  const n = kind === "2up" ? 2 : 3; const vert = Hh > W;
  const group = [it, ...fx.broll.filter((b) => b !== it && b.start < it.end - 0.05 && b.end > it.start + 0.05 && H.libItem(b.id)?.kind !== "sticker").sort((a, b) => (a.track || 0) - (b.track || 0))].slice(0, n);
  const cells = Array.from({ length: n }, (_, i) => (vert ? { x: 0, y: i / n, w: 1, h: 1 / n } : { x: i / n, y: 0, w: 1 / n, h: 1 }));
  // fewer clips than cells: the main video keeps the first cell(s)
  const off = n - group.length;
  group.forEach((b, i) => {
    const c = cells[i + off]; const li = H.libItem(b.id); const ar = li?.meta?.width && li?.meta?.height ? li.meta.width / li.meta.height : 16 / 9;
    const cw = c.w * W, ch = c.h * Hh; const bw = Math.max(cw, ch * ar); const bh = bw / ar;
    clean(b); Object.assign(b, { fit: "free", x: r3(c.x + c.w / 2), y: r3(c.y + c.h / 2), scale: r3(bw / W), opacity: 1 });
    const mw = cw / bw, mh = ch / bh; if (mw < 0.995 || mh < 0.995) b.mask = { shape: "rect", x: 0.5, y: 0.5, w: r3(Math.min(1, mw)), h: r3(Math.min(1, mh)), rotation: 0, roundness: 0, feather: 0, enabled: true, layout: true };
  });
  return group.length;
}
export function bindBrollInspector(ins, it) {
  const ed = E(); const after = () => H.renderOverlay();
  bindSecs(ins); bindKf(ins, after); bindKfList(ins); bindColor(ins, after);
  bindMask(ins, () => it.mask, (m) => { if (m) it.mask = m; else delete it.mask; }, after);
  const re = () => { H.touch(); H.renderInspector(); after(); };
  $$("[data-layout]", ins).forEach((b) => (b.onclick = () => { if (!ed.canEdit) return; const n = applyLayout(it, b.dataset.layout); re(); if (b.dataset.layout.endsWith("up")) ed.ctx.toast(n < (b.dataset.layout === "2up" ? 2 : 3) ? `${n} overlay clip — बाकी हिस्से में main video रहेगा (और clips दूसरे V track पर इसी समय डालें)` : `${n} clips split-screen में`); }));
  $$("[data-spd]", ins).forEach((b) => (b.onclick = () => { if (!ed.canEdit) return; setSpeed(it, +b.dataset.spd); re(); }));
  const sc = $("[data-spdc]", ins); if (sc) sc.onchange = () => { const v = clamp(+sc.value || 1, 0.25, 4); setSpeed(it, v); re(); };
  $$("[data-spmode]", ins).forEach((b) => (b.onclick = () => { if (!ed.canEdit) return; if (b.dataset.spmode === "curve") { if (!rampOf(it)) applyRamp(it, "montage"); } else { delete it.speed_ramp; } re(); }));
  $$("[data-ramp]", ins).forEach((b) => (b.onclick = () => { applyRamp(it, b.dataset.ramp); re(); }));
  const svg = $("[data-ramp-svg]", ins); if (svg) bindRamp(svg, it);
  $$("[data-pk]", ins).forEach((el) => (el.oninput = el.onchange = () => { if (!ed.canEdit) return; const k = el.dataset.pk; const v = el.type === "range" || el.type === "number" ? +el.value : el.value;
    if (k === "trim_out") { const sd = +(H.libItem(it.id)?.meta?.duration || 0); if (sd && v >= sd - 0.06) delete it.trim_out; else it.trim_out = r3(Math.max(v, (+it.trim_in || 0) + 0.1)); }
    else if (k === "trim_in") it.trim_in = r3(Math.min(v, it.trim_out != null && it.trim_out !== "" ? +it.trim_out - 0.1 : v));
    else if (k === "volume") it.volume = v; else if (k === "speed_warp") { if (v === "off") delete it.speed_warp; else it.speed_warp = v; }
    else if (k === "blend_mode") { if (v === "normal") delete it.blend_mode; else it.blend_mode = v; }
    else it[k] = v;
    const lb = el.closest(".ifield")?.querySelector("label b"); if (lb && el.type === "range") lb.textContent = k === "volume" ? Math.round(v * 100) + "%" : k === "pip_size" || k === "opacity" ? Math.round(v * 100) + "%" : k === "edge_feather" || k === "edge_shrink" || k === "pip_radius" || k === "feather" ? String(Math.round(v)) : v.toFixed(2) + "s";
    H.touch(); after(); if (el.type !== "range" || el.tagName === "SELECT") H.renderInspector(); }));
  const am = $("[data-amute]", ins); if (am) am.onchange = () => { it.volume = am.checked ? 0 : 1; re(); };
  $$("[data-gcc]", ins).forEach((b) => (b.onclick = () => { ed.gCatClip = b.dataset.gcc; H.renderInspector(); }));
  $$("[data-cgp]", ins).forEach((b) => { b.onclick = () => { if (!ed.canEdit) return; const k = b.dataset.cgp; if (!k) { delete it.grade_preset; delete it.grade; delete it.grade_strength; } else { it.grade_preset = k; it.grade = H.scaledGrade(k, it.grade_strength ?? 1); } re(); };
    b.onmouseenter = () => { const m = $(`#ovl-media .ov-broll[data-bid="${it._id}"] video, #ovl-media .ov-broll[data-bid="${it._id}"] img`, ed.root); if (m) m.style.filter = b.dataset.cgp ? H.gradeCss(H.scaledGrade(b.dataset.cgp, 1)) : ""; };
    b.onmouseleave = () => { const m = $(`#ovl-media .ov-broll[data-bid="${it._id}"] video, #ovl-media .ov-broll[data-bid="${it._id}"] img`, ed.root); if (m) { m._f = null; after(); } }; });
  $$("[data-zorder]", ins).forEach((b) => (b.onclick = () => { if (!ed.canEdit) return; const fx = ed.rs.effects; const cur = +(it.track || 0); const nt = b.dataset.zorder === "up" ? cur + 1 : Math.max(0, cur - 1); if (nt === cur) return;
    fx.tracks = { ...(fx.tracks || {}) }; fx.tracks.broll = Math.max(fx.tracks.broll || 1, nt + 1, ...fx.broll.map((x) => (x.track || 0) + 1)); it.track = nt; H.touch(); H.renderTimeline(); H.renderOverlay(); H.renderInspector(); ed.ctx.toast(nt > cur ? `V${nt + 1} पर — अब आगे दिखेगी` : `V${nt + 1} पर — अब पीछे`); }));
  const trk = $("[data-trk]", ins); if (trk) trk.onchange = () => { if (trk.value === "none") delete it.tr; else it.tr = { ...(it.tr || {}), kind: trk.value, dur: +(it.tr?.dur || 0.5) }; re(); };
  const trd = $("[data-trd]", ins); if (trd) trd.oninput = () => { it.tr = { ...(it.tr || { kind: "crossfade" }), dur: +trd.value }; const lb = trd.closest(".ifield")?.querySelector("label b"); if (lb) lb.textContent = (+trd.value).toFixed(1) + "s"; H.touch(); after(); };
  const cl = $("[data-clut]", ins); if (cl) cl.onchange = () => { if (cl.value) it.lut = cl.value; else { delete it.lut; delete it.lut_amount; } re(); };
  const cla = $("[data-cla]", ins); if (cla) cla.oninput = () => { it.lut_amount = +cla.value; const lb = cla.closest(".ifield")?.querySelector("label b"); if (lb) lb.textContent = Math.round(it.lut_amount * 100) + "%"; H.touch(); };
  const gs = $("[data-cgs]", ins); if (gs) gs.oninput = () => { it.grade_strength = +gs.value; it.grade = H.scaledGrade(it.grade_preset, it.grade_strength); const lb = gs.closest(".ifield")?.querySelector("label b"); if (lb) lb.textContent = Math.round(it.grade_strength * 100) + "%"; H.touch(); after(); };
  const sa = $("[data-stkadd]", ins); if (sa) sa.onchange = () => { if (!sa.value) return; it.stack = it.stack || []; it.stack.push({ id: sa.value, params: {} }); SECS().fx = true; re(); };
  $$("[data-stkdel]", ins).forEach((b) => (b.onclick = () => { it.stack.splice(+b.dataset.stkdel, 1); if (!it.stack.length) delete it.stack; re(); }));
  $$("[data-stkc]", ins).forEach((el) => (el.oninput = () => { const [i, p] = el.dataset.stkc.split("|"); const s = it.stack[+i]; s.params = s.params || {}; s.params[p] = el.value; H.touch(); after(); }));
  $$("[data-crop]", ins).forEach((el) => (el.oninput = () => { const k = el.dataset.crop; it.crop = { x: 0, y: 0, w: 1, h: 1, ...(it.crop || {}) }; it.crop[k] = +el.value; it.crop.w = Math.min(it.crop.w, 1 - it.crop.x); it.crop.h = Math.min(it.crop.h, 1 - it.crop.y);
    const lb = el.closest(".ifield")?.querySelector("label b"); if (lb) lb.textContent = (+el.value).toFixed(2); H.touch(); after(); }));
  $$("[data-act2]", ins).forEach((b) => (b.onclick = () => { if (!ed.canEdit) return; const a = b.dataset.act2;
    if (a === "fitlen") { it.end = r3(Math.min(H.outDur(), it.start + naturalLen(it, srcAvail(it)))); }
    else if (a === "cropreset") delete it.crop;
    else if (a === "to2kf") { const k = effKf(it); it.kf = { ...(it.kf || {}), ...Object.fromEntries(["x", "y", "scale"].filter((p) => k[p]).map((p) => [p, k[p]])) }; delete it.to; }
    re(); }));
}
function setSpeed(it, s) {   // keep the same part of the source: the clip gets longer / shorter like CapCut
  const used = (it.end - it.start) * (rampOf(it) ? 1 : spd(it)); delete it.speed_ramp;
  if (Math.abs(s - 1) < 1e-3) delete it.speed; else it.speed = s;
  const len = Math.min(used / s, srcAvail(it) / s); it.end = r3(Math.min(H.outDur(), it.start + Math.max(0.2, len)));
}
function applyRamp(it, key) {
  const avail = Math.min(srcAvail(it), 30); const pts = RAMPS[key][1];
  it.speed_ramp = pts.map(([f, v], i) => ({ t: r3(f * avail), v, ease: i < pts.length - 1 ? "inout" : "linear" })); delete it.speed;
  it.end = r3(Math.min(H.outDur(), it.start + naturalLen(it, avail)));
}
function bindRamp(svg, it) {
  const ed = E(); const avail = +svg.dataset.avail; const W = 270, Hh = 120, pd = 10;
  const at = (ev) => { const r = svg.getBoundingClientRect(); const x = (ev.clientX - r.left) / r.width * W, y = (ev.clientY - r.top) / r.height * Hh;
    return [clamp((x - pd) / (W - 2 * pd), 0, 1) * avail, Math.pow(2, clamp((1 - (y - pd) / (Hh - 2 * pd)) * 4 - 2, -2, 2))]; };
  const redraw = () => { const n = document.createElement("div"); n.innerHTML = rampSvg(it, avail); const s2 = n.firstElementChild; svg.innerHTML = s2.innerHTML; };
  const drag = (e, i) => { H.track(e, (ev) => { const r = it.speed_ramp; const [s, v] = at(ev); const lo = i > 0 ? r[i - 1].t + 0.05 : 0, hi = i < r.length - 1 ? r[i + 1].t - 0.05 : avail;
    r[i].t = i === 0 ? 0 : r3(clamp(s, lo, hi)); r[i].v = r3(Math.abs(v - 1) < 0.06 ? 1 : v); redraw(); H.renderOverlay(); }, () => { it.end = r3(Math.min(H.outDur(), it.start + naturalLen(it, avail))); H.touch(); H.renderInspector(); }, 0); };
  svg.onpointerdown = (e) => { if (!ed.canEdit || e.button > 0) return; e.preventDefault(); const c = e.target.closest("[data-rpt]"); if (c) return drag(e, +c.dataset.rpt);
    const [s, v] = at(e); const r = it.speed_ramp; let i = r.findIndex((k) => k.t > s); if (i < 0) i = r.length; if (i === 0) i = 1; r.splice(i, 0, { t: r3(s), v: r3(v), ease: "inout" }); redraw(); drag(e, i); };
  svg.ondblclick = (e) => { const c = e.target.closest("[data-rpt]"); if (!c || !ed.canEdit) return; const r = it.speed_ramp; if (r.length > 2) { r.splice(+c.dataset.rpt, 1); it.end = r3(Math.min(H.outDur(), it.start + naturalLen(it, avail))); H.touch(); H.renderInspector(); } };
}
// effect clip (timeline FX track): params with ◆ (kf t = 0 at the clip start)
export function fxParamsHtml(it, d, dis) {
  const o = paramOwner("fxc:" + it._id, it, +it.start, it.end - it.start, d); const pr = H.fxParams(d, it.params);
  return (d.params || []).map((p) => p.type === "color" ? H.field(esc(p.label), `<input type="color" data-fxcp="${p.name}" value="${pr[p.name]}" ${dis}>`) : (o.spec[p.name] = [p.label, p.min, p.max, p.step || 1], kfSlider(o, p.name, dis))).join("")
    + (d.cat === "trending" ? `<p class="small muted">${d.cost >= 3 ? "⚠ भारी effect (render ~2× इस हिस्से पर) · " : ""}clip की लंबाई पर पूरा animation चलता है — किनारे खींचकर छोटा/बड़ा करें।</p>` : "")
    + (it.kf && Object.keys(it.kf).length ? `<h5>Keyframes</h5>${kfListHtml(E().sel, dis)}` : "");
}
export function bindFxParams(ins) { bindKf(ins, () => H.layoutFrame()); bindKfList(ins); }

// ====================================================================== main video: effective transform (keyframes) + blurred fill
export function mainTf() {
  const fx = E().rs.effects; const t = fx.transform || {}; const kf = t.kf || {}; if (!Object.keys(kf).length) return t;
  const ot = H.outOf(E().t); const o = { ...t };
  if (hasKf(kf, "x")) o.x = sample(kf.x, ot); if (hasKf(kf, "y")) o.y = sample(kf.y, ot); if (hasKf(kf, "scale")) o.scale = sample(kf.scale, ot);
  if (hasKf(kf, "rotation")) o.angle = sample(kf.rotation, ot); if (animated(kf.opacity)) o.opacity = sample(kf.opacity, ot);
  return o;
}
export const mainAnimated = () => { const kf = E().rs.effects.transform?.kf || {}; return Object.values(kf).some(animated) || !!E().rs.effects.pro?.mask?.kf; };
// what shows behind a shrunk / moved / letter-boxed main video: blur of the same frame (render: transform.bg)
export function bgFill(g, T) {
  const ed = E(); const cv = $("#pv-bg", ed.root); const v = $("#pv", ed.root); if (!cv || !v) return;
  const fb = ed.frameBox; const full = g && g.dw >= fb.w - 1 && g.dh >= fb.h - 1 && g.x0 <= 0.5 && g.y0 <= 0.5;
  const moved = T && ((+T.scale || 1) < 0.999 || Math.abs(+T.x || 0) > 1e-3 || Math.abs(+T.y || 0) > 1e-3 || (T.opacity ?? 1) < 0.999);
  const m = ed.rs.effects.pro?.mask; const masked = !!(m?.shape && m.enabled !== false);
  const bg = masked ? (String(m.bg || "black").startsWith("#") ? "color" : m.bg || "black") : T?.bg || "blur";
  const need = !!g && (!full || moved || masked);
  cv.hidden = !need; const fr = $("#frame", ed.root);
  fr.style.background = need && bg === "color" ? (masked ? m.bg : T.bg_color || "#000") : "";
  ed.bgBlur = need && bg === "blur";
  if (!ed.bgBlur) { cv.style.visibility = "hidden"; return; }
  cv.style.visibility = ""; cv.style.cssText = `left:0;top:0;width:${fb.w}px;height:${fb.h}px;position:absolute;filter:blur(${Math.max(6, fb.w / 40).toFixed(0)}px) ${ed.vf || ""};transform:scale(1.08)`;
  drawBg();
}
export function drawBg() {
  const ed = E(); if (!ed.bgBlur) return; const cv = $("#pv-bg", ed.root); const v = $("#pv", ed.root); if (!cv || !v || v.readyState < 2) return;
  const fb = ed.frameBox; const W = 72, Hh = Math.max(8, Math.round(72 * fb.h / fb.w)); if (cv.width !== W || cv.height !== Hh) { cv.width = W; cv.height = Hh; }
  const x = cv.getContext("2d"); const vw = v.videoWidth, vh = v.videoHeight; const k = Math.max(W / vw, Hh / vh);
  try { x.drawImage(v, (W - vw * k) / 2, (Hh - vh * k) / 2, vw * k, vh * k); } catch { /* not decodable yet */ }
}
// main video mask (effects.pro.mask): CSS mask on the picture, relative to the frame
export function mainMaskCss() {
  const m = E().rs.effects.pro?.mask; if (!m?.shape || m.enabled === false) return ""; const fb = E().frameBox;
  return maskImage(maskNow(m, H.outOf(E().t)), null, fb.w, fb.h);
}

// ====================================================================== on-canvas mask handles (move / resize / rotate)
// returns the handle box for the selected clip's mask (or the main video mask) in frame pixels
function maskLayer() {
  const ed = E(); const s = ed.sel; if (!ed.maskEdit || !s) return null; const fb = ed.frameBox;
  if (s.type === "broll") { const it = H.selItem(); if (!it?.mask?.shape) return null; const g = clipGeom(it, H.outOf(ed.t), fb); const el = $(`#ovl-media .ov-broll[data-bid="${it._id}"]`, ed.root);
    const h = g.h ?? el?.offsetHeight ?? g.w * 0.5625; return { m: it.mask, cx: g.cx, cy: g.cy, w: g.w, h, rot: g.rot, t: H.outOf(ed.t) - it.start, owner: OWN.get("mask:" + it._id) || maskOwner("mask:" + it._id, () => it.mask, +it.start, it.end - it.start) }; }
  if (s.type === "video" || s.type === "seg") { const m = ed.rs.effects.pro?.mask; if (!m?.shape) return null; return { m, cx: fb.w / 2, cy: fb.h / 2, w: fb.w, h: fb.h, rot: 0, t: H.outOf(ed.t), owner: OWN.get("mmask") || maskOwner("mmask", () => ed.rs.effects.pro.mask, 0, H.outDur()) }; }
  return null;
}
// polygon vertex (layer fraction) → frame px, honouring the mask's x/y translate, w/h scale and the layer rotation
function polyPx(L, m, q) {
  const pts = m.pts || []; const mx = pts.reduce((s_, v) => s_ + +v[0], 0) / (pts.length || 1), my = pts.reduce((s_, v) => s_ + +v[1], 0) / (pts.length || 1);
  const sw = +(m.w ?? 0.6) / 0.6, sh = +(m.h ?? 0.6) / 0.6; const fx = (+q[0] - mx) * sw + mx + (+(m.x ?? 0.5) - 0.5) - 0.5, fy = (+q[1] - my) * sh + my + (+(m.y ?? 0.5) - 0.5) - 0.5;
  const a = L.rot * Math.PI / 180; const lx = fx * L.w, ly = fy * L.h; return [L.cx + lx * Math.cos(a) - ly * Math.sin(a), L.cy + lx * Math.sin(a) + ly * Math.cos(a)];
}
function polyFrac(L, m, x, y) {   // frame px → vertex fraction as it should be STORED (undo translate / scale)
  const pts = m.pts || []; const mx = pts.reduce((s_, v) => s_ + +v[0], 0) / (pts.length || 1), my = pts.reduce((s_, v) => s_ + +v[1], 0) / (pts.length || 1);
  const sw = +(m.w ?? 0.6) / 0.6, sh = +(m.h ?? 0.6) / 0.6; const a = -L.rot * Math.PI / 180; const dx = x - L.cx, dy = y - L.cy;
  const fx = (dx * Math.cos(a) - dy * Math.sin(a)) / L.w + 0.5 - (+(m.x ?? 0.5) - 0.5), fy = (dx * Math.sin(a) + dy * Math.cos(a)) / L.h + 0.5 - (+(m.y ?? 0.5) - 0.5);
  return [r3(pts.length ? (fx - mx) / sw + mx : fx), r3(pts.length ? (fy - my) / sh + my : fy)];
}
// Ramer–Douglas–Peucker: a drawn stroke → a few vertices
function simplify(pts, eps) {
  if (pts.length < 3) return pts; const [a, b] = [pts[0], pts[pts.length - 1]]; let imax = 0, dmax = 0;
  for (let i = 1; i < pts.length - 1; i++) { const d = Math.abs((b[0] - a[0]) * (a[1] - pts[i][1]) - (a[0] - pts[i][0]) * (b[1] - a[1])) / (Math.hypot(b[0] - a[0], b[1] - a[1]) || 1); if (d > dmax) { dmax = d; imax = i; } }
  if (dmax <= eps) return [a, b]; const l = simplify(pts.slice(0, imax + 1), eps), r = simplify(pts.slice(imax), eps); return [...l.slice(0, -1), ...r];
}
export function maskHandlesHtml() {
  const L = maskLayer(); if (!L) return ""; const m = maskNow(L.m, L.t); const a = L.rot * Math.PI / 180;
  if (m.shape === "polygon") { const mode = E().polyMode || ""; const pts = L.m.pts || []; const px = pts.map((q) => polyPx(L, L.m, q));
    const fb = E().frameBox; return `<svg class="mpoly ${mode ? "mode-" + mode : ""}" width="${fb.w}" height="${fb.h}" viewBox="0 0 ${fb.w} ${fb.h}" data-polysvg title="${mode === "add" ? "click = कोना जोड़ें" : mode === "draw" ? "खींचकर आकार बनाएँ" : "कोने खींचें · double-click = हटाएँ"}">${px.length ? `<polygon points="${px.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" ")}" data-pmove/>` : ""}${px.map((p, i) => `<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="7" data-pv="${i}"/>`).join("")}<text x="${(px[0]?.[0] ?? 12).toFixed(1)}" y="${((px[0]?.[1] ?? 12) - 12).toFixed(1)}">mask · ${mode === "add" ? "click = कोना" : mode === "draw" ? "freehand" : pts.length + " कोने"}</text></svg>`; }
  const lx = (+(m.x ?? 0.5) - 0.5) * L.w, ly = (+(m.y ?? 0.5) - 0.5) * L.h; const cx = L.cx + lx * Math.cos(a) - ly * Math.sin(a), cy = L.cy + lx * Math.sin(a) + ly * Math.cos(a);
  const w = +(m.w ?? 0.6) * L.w, h = m.shape === "circle" ? w : m.shape === "linear" ? L.h * 1.2 : +(m.h ?? 0.6) * L.h; const r = L.rot + +(m.rotation || 0);
  return `<div class="mbox ${m.shape}" style="left:${(cx - w / 2).toFixed(1)}px;top:${(cy - h / 2).toFixed(1)}px;width:${w.toFixed(1)}px;height:${h.toFixed(1)}px;transform:rotate(${r}deg)" title="mask: खींचें = जगह · कोने = size · गोला = घुमाव">${m.shape === "linear" ? "" : ["nw", "ne", "se", "sw"].map((k) => `<i class="hh h-${k}" data-mh="${k}"></i>`).join("")}<i class="hrot" data-mh="rot"></i><span class="mtag">mask</span></div>`;
}
export function bindMaskHandles(L0) {
  const svg = $("svg.mpoly", L0);
  if (svg) {
    svg.onpointerdown = (e) => {
      if (e.button > 0 || !E().canEdit) return; e.preventDefault(); e.stopPropagation(); const ed = E(); const L = maskLayer(); if (!L) return; const m = L.m; m.pts = m.pts || [];
      const fr = $("#frame", ed.root).getBoundingClientRect(); const P = (ev) => [ev.clientX - fr.left, ev.clientY - fr.top]; const mode = ed.polyMode || ""; const vi = e.target.dataset.pv;
      if (vi != null && mode !== "draw") { // drag one vertex
        const i = +vi; H.track(e, (ev) => { const [x, y] = P(ev); m.pts[i] = polyFrac(L, m, x, y); H.renderOverlay(); H.renderHandles?.(); }, (moved) => { if (moved) { H.touch(); H.renderInspector(); } }, 2); return; }
      if (mode === "add") { const [x, y] = P(e); m.pts.push(polyFrac(L, m, x, y)); H.touch(); H.renderOverlay(); H.rerender(); return; }
      if (mode === "draw") { const raw = [P(e)]; H.track(e, (ev) => { raw.push(P(ev)); svg.dataset.n = raw.length; }, () => { const eps = Math.max(3, Math.min(L.w, L.h) * 0.012); const sp = simplify(raw, eps).slice(0, 120); if (sp.length >= 3) { m.pts = sp.map(([x, y]) => polyFrac(L, { ...m, pts: [] }, x, y)); ed.polyMode = ""; H.touch(); } H.renderOverlay(); H.rerender(); }, 1); return; }
      if (e.target.dataset.pmove != null) { // drag the whole shape = x/y (keyframable)
        const o = L.owner; const m0 = maskNow(m, L.t); const [x0, y0] = P(e); const a = L.rot * Math.PI / 180;
        H.track(e, (ev) => { const [x, y] = P(ev); const dx = x - x0, dy = y - y0; setVal(o, "x", r3(+(m0.x ?? 0.5) + (dx * Math.cos(a) + dy * Math.sin(a)) / L.w)); setVal(o, "y", r3(+(m0.y ?? 0.5) + (-dx * Math.sin(a) + dy * Math.cos(a)) / L.h)); H.renderOverlay(); if (o.id === "mmask") H.applyVideoCss(); refreshKfUi(); }, (moved) => { if (moved) { H.touch(); H.renderInspector(); } }, 2); }
    };
    svg.ondblclick = (e) => { const vi = e.target.dataset.pv; const L = maskLayer(); if (vi == null || !L || !E().canEdit) return; e.preventDefault(); if ((L.m.pts || []).length <= 3) { E().ctx.toast("कम से कम 3 कोने चाहिए"); return; } L.m.pts.splice(+vi, 1); H.touch(); H.renderOverlay(); H.rerender(); };
    return;
  }
  const box = $(".mbox", L0); if (!box) return;
  box.onpointerdown = (e) => {
    if (e.button > 0 || !E().canEdit) return; e.preventDefault(); e.stopPropagation(); const L = maskLayer(); if (!L) return; const mode = e.target.dataset.mh || "move";
    const fr = $("#frame", E().root).getBoundingClientRect(); const m0 = maskNow(L.m, L.t); const a = L.rot * Math.PI / 180; const o = L.owner;
    const toLayer = (dx, dy) => [(dx * Math.cos(a) + dy * Math.sin(a)) / L.w, (-dx * Math.sin(a) + dy * Math.cos(a)) / L.h];
    const lx = (+(m0.x ?? 0.5) - 0.5) * L.w, ly = (+(m0.y ?? 0.5) - 0.5) * L.h; const ccx = L.cx + lx * Math.cos(a) - ly * Math.sin(a), ccy = L.cy + lx * Math.sin(a) + ly * Math.cos(a);
    const x0 = e.clientX - fr.left, y0 = e.clientY - fr.top; const d0 = Math.hypot(x0 - ccx, y0 - ccy) || 1; const an0 = Math.atan2(y0 - ccy, x0 - ccx);
    H.track(e, (ev) => { const x = ev.clientX - fr.left, y = ev.clientY - fr.top;
      if (mode === "move") { const [dx, dy] = toLayer(x - x0, y - y0); setVal(o, "x", r3(+(m0.x ?? 0.5) + dx)); setVal(o, "y", r3(+(m0.y ?? 0.5) + dy)); }
      else if (mode === "rot") { let r = +(m0.rotation || 0) + (Math.atan2(y - ccy, x - ccx) - an0) * 180 / Math.PI; r = ((r + 540) % 360) - 180; for (const q of [-90, 0, 90]) if (Math.abs(r - q) < 3) r = q; setVal(o, "rotation", +r.toFixed(1)); }
      else { const k = Math.hypot(x - ccx, y - ccy) / d0; setVal(o, "w", r3(clamp(+(m0.w ?? 0.6) * k, 0.02, 3))); if (m0.shape !== "circle") setVal(o, "h", r3(clamp(+(m0.h ?? 0.6) * k, 0.02, 3))); }
      H.renderOverlay(); if (L.owner.id === "mmask") H.applyVideoCss(); refreshKfUi(); },
    (moved) => { if (moved) { H.touch(); H.renderInspector(); } }, 2);
  };
}
// ====================================================================== Pro tab (main video tools)
const proFx = () => { const fx = E().rs.effects; fx.pro = fx.pro && typeof fx.pro === "object" ? fx.pro : {}; return fx.pro; };
const toolOn = (k) => { const v = proFx()[k]; return !!(v && v.enabled); };
function toolParams(k, cur, dis) {
  const T = PP().tools?.[k] || {}; const D = PP().defaults?.[k] || {};
  return (T.params || []).map((p) => { const v = cur?.[p.name] ?? D[p.name] ?? p.default; return H.field(`${esc(p.label)} <b>${(+v).toFixed(p.step < 1 ? 2 : 0)}</b>`, `<input type="range" data-tp="${k}|${p.name}" min="${p.min}" max="${p.max}" step="${p.step}" value="${v}" ${dis}>`); }).join("");
}
const toolHead = (k, l, dis, title) => `<label class="chk" title="${esc(title || "")}"><input type="checkbox" data-ton="${k}" ${toolOn(k) ? "checked" : ""} ${dis}> <b>${l}</b></label>`;
const cost = (k) => PP().tools?.[k]?.cost ? `<span class="tag" title="render पर असर">⏱ ${esc(PP().tools[k].cost)}</span>` : "";
export function proPanel(dis) {
  const ed = E(); const pr = proFx(); const cap = PP().capabilities?.stabilize || "none";
  colReg("col:main", () => (proFx().color = proFx().color || {}), { reset: () => delete proFx().color });
  const mmo = maskOwner("mmask", () => proFx().mask, 0, H.outDur());
  const mc = pr.morph_cut || {}; const nCuts = ed.cuts.filter((c) => c.enabled !== false).length; const nMorph = ed.cuts.filter((c) => c.morph === true).length;
  const fr = pr.face_refine || {}; const dn = pr.denoise || {}; const sh = pr.sharpen || {}; const st = pr.stabilize || {};
  const mk = ed.rs.markers || []; const MK = PP().markers || { chapter: "Chapter", note: "Note", todo: "To-do" };
  return `<div class="ph"><h3>Pro tools</h3><span class="small muted">पूरे वीडियो पर · render quality</span></div>
    <p class="small muted">ये सब render में असली ffmpeg से लगते हैं। जो preview में live नहीं दिखता उसके लिए "🎞 Preview frame" दबाएँ।</p>
    ${sec("p_morph", "🌗 Morph cut (jump cut smooth)", `<div class="row between">${toolHead("morph_cut", "हर कट पर morph", dis, "talking head में सिर थोड़ा हिलने वाले jump cut को smooth करता है")}${cost("morph_cut")}</div>
      <div class="irow"><label class="chk small"><input type="checkbox" data-mc="all" ${mc.all ? "checked" : ""} ${dis}> सारे कट (${nCuts})</label>${H.field("तरीका", `<select data-mc="mode" class="small" ${dis}><option value="flow" ${mc.mode !== "blend" ? "selected" : ""}>Optical flow (बढ़िया)</option><option value="blend" ${mc.mode === "blend" ? "selected" : ""}>Blend (dissolve)</option></select>`)}</div>
      ${H.field(`frames <b>${mc.frames || 8}</b>`, `<input type="range" data-mc="frames" min="4" max="16" step="2" value="${mc.frames || 8}" ${dis}>`)}
      <p class="small muted">एक-एक कट पर: कट list (कट tab) में 🌗 या timeline पर कट चुनकर। अभी ${nMorph} कट पर अलग से चालू। xfade transition वाले कट छूट जाते हैं।</p>`, mc.enabled || nMorph ? (mc.all ? "सब" : nMorph || "on") : "")}
    ${sec("p_stab", "🎥 Stabilise (हिलना कम)", `<div class="row between">${toolHead("stabilize", "Stabilise", dis)}${cost("stabilize")}</div>${toolParams("stabilize", st, dis)}
      <p class="small muted">${cap === "vidstab" ? "vidstab (2-pass) उपलब्ध ✓" : cap === "deshake" ? "इस server पर सिर्फ़ deshake (हल्का) — vidstab नहीं" : "इस server पर stabilise उपलब्ध नहीं"} · zoom 0 = अपने-आप crop · <b>render में दिखेगा</b> (preview frame में नहीं)</p>`, toolOn("stabilize") ? "on" : "")}
    ${sec("p_clean", "✨ Denoise · Sharpen", `<div class="row between">${toolHead("denoise", "Noise हटाएँ (grain)", dis)}${cost("denoise")}</div>
      <div class="irow">${H.field("तरीका", `<select data-tm="denoise" class="small" ${dis}><option value="hqdn3d" ${dn.method !== "nlmeans" ? "selected" : ""}>तेज़ (hqdn3d)</option><option value="nlmeans" ${dn.method === "nlmeans" ? "selected" : ""}>बढ़िया, धीमा (nlmeans)</option></select>`)}</div>${toolParams("denoise", dn, dis)}
      <div class="row between" style="margin-top:.5rem">${toolHead("sharpen", "Sharpen", dis)}${cost("sharpen")}</div>
      <div class="irow">${H.field("तरीका", `<select data-tm="sharpen" class="small" ${dis}><option value="cas" ${sh.method !== "unsharp" ? "selected" : ""}>CAS (natural)</option><option value="unsharp" ${sh.method === "unsharp" ? "selected" : ""}>Unsharp</option></select>`)}</div>${toolParams("sharpen", sh, dis)}
      <p class="small muted rhint">preview में नहीं — <b>render / 🎞 Preview frame में दिखेगा</b></p>`, [toolOn("denoise") && "DN", toolOn("sharpen") && "SH"].filter(Boolean).join("+"))}
    ${sec("p_face", "🙂 Face refine (चेहरा निखारें)", `<div class="row between">${toolHead("face_refine", "Face refine", dis, "त्वचा smooth, आँखें/होंठ/बाल sharp रहते हैं")}${cost("face_refine")}</div>
      <div class="chips"><button data-face="natural" ${dis}>Natural</button><button data-face="soft" ${dis}>Soft glow</button><button data-face="strong" ${dis}>Strong</button></div>${toolParams("face_refine", fr, dis)}
      <p class="small muted">0.5 = natural (सुझाया)। चेहरा न मिले तो कुछ नहीं बदलता। <b>render / 🎞 Preview frame में दिखेगा</b></p>`, toolOn("face_refine") ? "on" : "")}
    ${sec("p_warp", "🐢 Speed Warp (main video slow-mo)", `${H.field("slow हिस्सों (speed < 0.75×) पर", `<select data-warp class="small" ${dis}>${Object.entries(PP().speed?.warp || {}).map(([k, l]) => `<option value="${k}" ${(pr.speed_warp || "off") === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`)}
      <p class="small muted">${(ed.speed || []).filter((s) => s.rate < 0.75).length} slow हिस्से (I/O → speed…)। ${cost("speed_warp")}</p>`, pr.speed_warp && pr.speed_warp !== "off" ? pr.speed_warp : "")}
    ${sec("p_color", "🎨 Colour (wheels · curves · HSL · match)", colorHtml("col:main", dis), !neutralColor(pr.color) || renderOnlyColor(pr.color) ? "●" : "")}
    ${sec("p_mask", "⬭ Mask (main video)", maskHtml("mmask", pr.mask, dis, { bg: true }), pr.mask?.shape || "")}
    ${sec("p_mark", "🚩 Markers · Chapters", `<div class="irow"><button class="btn small primary" data-mkadd="chapter" ${dis} title="playhead पर chapter (YouTube description में)">+ Chapter</button><button class="btn small" data-mkadd="note" ${dis} title="M">+ Marker (M)</button><button class="btn small quiet" data-mkadd="todo" ${dis}>+ To-do</button></div>
      <ul class="plist mklist">${[...mk].sort((a, b) => a.t - b.t).map((m) => `<li data-mkid="${m.id}"><button class="ibtn" data-mkgo="${m.id}" title="यहाँ जाएँ" style="color:${m.color || mkColor(m.kind)}">⚑</button><span class="small muted">${H.fmt(m.t)}</span>
        <input class="grow small" data-mklabel="${m.id}" value="${esc(m.label || "")}" placeholder="नाम" ${dis}><select class="small" data-mkkind="${m.id}" ${dis}>${Object.entries(MK).map(([k, l]) => `<option value="${k}" ${m.kind === k ? "selected" : ""}>${esc(l.split(" ")[0])}</option>`).join("")}</select><button class="ibtn" data-mkdel="${m.id}" ${dis}>✕</button></li>`).join("") || `<li class="small muted">कोई marker नहीं — <b>M</b> दबाएँ (playhead पर)</li>`}</ul>
      <p class="small muted">Chapter markers से YouTube description के chapters बनते हैं (पहला 0:00 पर, कम से कम 3, 10s दूर)।</p>`, mk.length ? String(mk.length) : "")}
    ${sec("p_scene", "🎬 Scenes ढूँढो", `<div class="irow">${H.field(`sensitivity <b>${ed.sceneTh ?? 0.3}</b>`, `<input type="range" data-scth min="0.1" max="0.6" step="0.05" value="${ed.sceneTh ?? 0.3}">`)}<button class="btn small primary" data-scgo ${dis}>🔍 scenes ढूँढो</button></div>
      ${ed.scenes ? `<p class="small">${ed.scenes.length} scene बदलाव मिले</p><ul class="plist">${ed.scenes.map((s, i) => `<li><span class="small grow">Scene ${i + 2} · ${H.fmt(H.outOf(s.t))} <span class="muted">score ${s.score}</span></span><button class="btn small quiet" data-scseek="${s.t}">देखें</button><button class="btn small quiet" data-scsplit="${s.t}" ${dis} title="main video को यहाँ दो हिस्सों में">✂</button></li>`).join("")}</ul>
        <div class="irow"><button class="btn small" data-scall="markers" ${dis}>सब → markers</button><button class="btn small quiet" data-scall="split" ${dis}>सब पर ✂ split</button></div>` : `<p class="small muted">recording में shot/scene बदलने की जगहें (720p proxy पर, ~20–60× realtime) → markers या split सुझाव।</p>`}`, ed.scenes ? String(ed.scenes.length) : "")}`;
}
const mkColor = (k) => ({ chapter: "#F2B33D", note: "#7cc4ff", todo: "#ff6b6b" }[k] || "#aaa");
export function addMarker(kind = "note") {
  const ed = E(); if (!ed.canEdit) return; ed.rs.markers = Array.isArray(ed.rs.markers) ? ed.rs.markers : [];
  const t0 = r3(H.outOf(ed.t)); const t = t0 < 0.15 ? 0 : t0; const near = ed.rs.markers.find((m) => Math.abs(m.t - t) < 0.05); if (near) { ed.ctx.toast("यहाँ पहले से marker है"); return; }
  const n = ed.rs.markers.filter((m) => m.kind === kind).length + 1;
  ed.rs.markers.push({ id: "m" + uid().slice(0, 6), t, label: kind === "chapter" ? (t < 0.5 ? "शुरुआत" : `Chapter ${n}`) : kind === "todo" ? "to-do" : `Marker ${n}`, kind, color: mkColor(kind) });
  H.touch(); H.renderTimeline(); if (ed.tab === "pro") H.renderPanel(); ed.ctx.toast(`⚑ ${H.fmt(t)} पर ${kind === "chapter" ? "chapter" : "marker"}`);
}
export function bindProPanel(panel) {
  const ed = E(); const pr = proFx(); const after = () => { H.layoutFrame(); H.renderOverlay(); };
  bindSecs(panel); bindKf(panel, after); bindColor(panel, after);
  bindMask(panel, () => proFx().mask, (m) => { if (m) proFx().mask = { bg: "blur", ...m }; else delete proFx().mask; }, after);
  const re = () => { H.touch(); H.rerender(); };
  $$("[data-ton]", panel).forEach((cb) => (cb.onchange = () => { const k = cb.dataset.ton; pr[k] = { ...(PP().defaults?.[k] || {}), ...(pr[k] || {}), enabled: cb.checked }; re(); }));
  $$("[data-tp]", panel).forEach((el) => (el.oninput = () => { const [k, p] = el.dataset.tp.split("|"); pr[k] = { ...(PP().defaults?.[k] || {}), ...(pr[k] || {}) }; pr[k][p] = +el.value; if (!pr[k].enabled) { pr[k].enabled = true; const cb = $(`[data-ton="${k}"]`, panel); if (cb) cb.checked = true; }
    const lb = el.closest(".ifield")?.querySelector("label b"); if (lb) lb.textContent = (+el.value).toFixed(+el.step < 1 ? 2 : 0); H.touch(); }));
  $$("[data-tm]", panel).forEach((el) => (el.onchange = () => { const k = el.dataset.tm; pr[k] = { ...(PP().defaults?.[k] || {}), ...(pr[k] || {}), method: el.value, enabled: true }; re(); }));
  $$("[data-face]", panel).forEach((b) => (b.onclick = () => { pr.face_refine = { ...(pr.face_refine || {}), enabled: true, ...{ natural: { strength: 0.5, brighten: 0.3, eyes: 0.3 }, soft: { strength: 0.7, brighten: 0.45, eyes: 0.2 }, strong: { strength: 1, brighten: 0.5, eyes: 0.5 } }[b.dataset.face] }; re(); }));
  $$("[data-mc]", panel).forEach((el) => (el.oninput = el.onchange = () => { const k = el.dataset.mc; pr.morph_cut = { ...(PP().defaults?.morph_cut || {}), ...(pr.morph_cut || {}) };
    pr.morph_cut[k] = el.type === "checkbox" ? el.checked : el.type === "range" ? +el.value : el.value; if (k === "all" && el.checked) pr.morph_cut.enabled = true;
    const lb = el.closest(".ifield")?.querySelector("label b"); if (lb) lb.textContent = el.value; H.touch(); if (el.type !== "range") { H.rerender(); H.renderTimeline(); } }));
  const w = $("[data-warp]", panel); if (w) w.onchange = () => { pr.speed_warp = w.value; re(); };
  // markers
  $$("[data-mkadd]", panel).forEach((b) => (b.onclick = () => addMarker(b.dataset.mkadd)));
  const mk = (id) => (ed.rs.markers || []).find((m) => m.id === id);
  $$("[data-mkgo]", panel).forEach((b) => (b.onclick = () => H.seek(H.srcOf(mk(b.dataset.mkgo).t) + 0.001)));
  $$("[data-mklabel]", panel).forEach((el) => (el.oninput = () => { mk(el.dataset.mklabel).label = el.value; H.touch(); }));
  $$("[data-mkkind]", panel).forEach((el) => (el.onchange = () => { const m = mk(el.dataset.mkkind); m.kind = el.value; m.color = mkColor(el.value); re(); H.renderTimeline(); }));
  $$("[data-mkdel]", panel).forEach((b) => (b.onclick = () => { ed.rs.markers = ed.rs.markers.filter((m) => m.id !== b.dataset.mkdel); re(); H.renderTimeline(); }));
  // scenes
  const th = $("[data-scth]", panel); if (th) th.oninput = () => { ed.sceneTh = +th.value; th.closest(".ifield").querySelector("label b").textContent = th.value; };
  const sg = $("[data-scgo]", panel); if (sg) sg.onclick = async () => { sg.disabled = true; sg.textContent = "ढूँढ रहे…";
    try { const r = await ed.ctx.api("POST", `/projects/${ed.pid}/scenes`, { source: { kind: "project" }, threshold: ed.sceneTh ?? 0.3 }); ed.scenes = (r.scenes || []).filter((s) => !H.cutAt(s.t)); SECS().p_scene = true; ed.ctx.toast(`${ed.scenes.length} scenes मिले`); }
    catch (e) { ed.ctx.toast(e.message); } H.rerender(); };
  $$("[data-scseek]", panel).forEach((b) => (b.onclick = () => H.seek(+b.dataset.scseek + 0.02)));
  const split = (t) => { if (H.cutAt(t) || ed.splits.some((x) => Math.abs(x - t) < 0.05)) return 0; ed.splits.push(r3(t)); return 1; };
  $$("[data-scsplit]", panel).forEach((b) => (b.onclick = () => { if (split(+b.dataset.scsplit)) { H.touch(); ed.ctx.toast("✂ split लगा"); } }));
  $$("[data-scall]", panel).forEach((b) => (b.onclick = () => { let n = 0;
    if (b.dataset.scall === "split") { for (const s of ed.scenes) n += split(s.t); }
    else { ed.rs.markers = Array.isArray(ed.rs.markers) ? ed.rs.markers : []; ed.scenes.forEach((s, i) => { const t = r3(H.outOf(s.t)); if (!ed.rs.markers.some((m) => Math.abs(m.t - t) < 0.3)) { ed.rs.markers.push({ id: "m" + uid().slice(0, 6), t, label: `Scene ${i + 2}`, kind: "note", color: mkColor("note") }); n++; } }); }
    H.touch(); H.renderTimeline(); H.rerender(); ed.ctx.toast(b.dataset.scall === "split" ? `${n} जगह ✂ split` : `${n} markers जुड़े`); }));
}
// markers on the timeline ruler: click = jump, drag = move, double-click = rename
export function tlMarkers(X) {
  return (E().rs.markers || []).map((m) => `<i class="tlmk mk-${m.kind}" data-tlmk="${m.id}" style="left:${X(H.srcOf(m.t))}px;--mk:${m.color || mkColor(m.kind)}" title="${esc(m.label || "")} · ${H.fmt(m.t)} — क्लिक = जाएँ · खींचें · double-click = नाम"><b>${esc((m.label || "").slice(0, 14))}</b></i>`).join("");
}
export function bindTlMarkers(body) {
  const ed = E();
  for (const el of $$("[data-tlmk]", body)) {
    const m = (ed.rs.markers || []).find((x) => x.id === el.dataset.tlmk); if (!m) continue;
    el.onpointerdown = (e) => { if (e.button > 0) return; e.preventDefault(); e.stopPropagation(); const x0 = e.clientX; const s0 = H.srcOf(m.t);
      H.track(e, (ev) => { if (!ed.canEdit) return; const s = clamp(s0 + (ev.clientX - x0) / ed.pps, 0, ed.dur); m.t = r3(H.outOf(s)); el.style.left = (H.srcOf(m.t) * ed.pps).toFixed(1) + "px"; },
        (moved) => { if (moved) { H.touch(); if (ed.tab === "pro") H.renderPanel(); } else H.seek(H.srcOf(m.t) + 0.001); }, 3); };
    el.ondblclick = () => { if (!ed.canEdit) return; const v = prompt("marker का नाम", m.label || ""); if (v != null) { m.label = v; H.touch(); H.renderTimeline(); if (ed.tab === "pro") H.renderPanel(); } };
  }
}

// ====================================================================== 🔥 Trending (Effects tab, first section)
export function trendingHtml(dis) {
  const ed = E(); const list = PP().trending || []; if (!list.length) return ""; const thumb = (ed.p.assets.find((a) => a.kind === "thumb") || {}).url;
  const seen = LS("vividora_tr_seen", []);
  return `<div class="trend"><div class="row between"><h4 style="margin:.2rem 0">🔥 Trending <span class="tag new">${list.length} नए</span></h4><span class="small muted">mouse रखें = झलक · क्लिक = playhead पर</span></div>
    <div class="fxgrid trgrid2">${list.map((e) => `<button class="fxcard tcard tr-${e.id}" data-fxadd="${e.id}" draggable="${ed.canEdit}" title="${esc(e.label)} · ${esc((e.tags || []).join(", "))} · क्लिक = playhead पर ${e.anim === "duration" ? "(clip की लंबाई पर animate)" : ""}" ${dis}>
      <span class="tprev">${thumb ? `<img src="${thumb}" alt="" loading="lazy">` : `<i></i>`}<em class="tfx"></em></span>${seen.includes(e.id) ? "" : `<b class="newb">नया</b>`}${e.cost >= 3 ? `<b class="heavy" title="भारी — render धीमा">⚡</b>` : ""}<span>${esc(e.label.split(" · ").pop())}</span><small>${esc(e.label.split(" · ")[0])}</small></button>`).join("")}</div></div>`;
}
export function markTrendSeen(id) { const s = LS("vividora_tr_seen", []); if (!s.includes(id)) { s.push(id); LSset("vividora_tr_seen", s); } }

// ====================================================================== music: fit the song to the video length (remix at bar starts)
export function musicFitHtml(dis) {
  const ed = E(); const m = ed.rs.effects.music; if (!m?.id) return ""; const pl = ed.mfit?.id === m.id ? ed.mfit.plan : null;
  return `<div class="box audioctl mfit"><div class="row between"><b>🎼 वीडियो की लंबाई में fit करें</b><label class="chk small"><input type="checkbox" data-mfit ${m.fit ? "checked" : ""} ${dis}> चालू</label></div>
    <p class="small muted">गाना bar पर काटकर ऐसे जोड़ा जाता है कि वीडियो के अंत पर गाने का असली अंत आए (लंबा गाना: intro + jump + ending · छोटा: बीच का हिस्सा loop)।</p>
    <div class="irow"><button class="btn small" data-mfplan ${dis}>📐 plan देखें</button><span class="small muted grow">video ${H.fmt(H.outDur())}</span></div>
    ${pl ? `<div class="mfbar" title="गाने के कौन-से हिस्से (bar पर कटे) जुड़ेंगे">${pl.pieces.map(([a, b]) => `<i style="left:${(a / pl.duration * 100).toFixed(2)}%;width:${((b - a) / pl.duration * 100).toFixed(2)}%"></i>`).join("")}</div>
      <p class="small">गाना ${H.fmt(pl.duration)} → <b>${H.fmt(pl.output_length ?? pl.length)}</b> · ${pl.bpm} BPM · ${pl.pieces.length} हिस्से · ${pl.tempo && Math.abs(pl.tempo - 1) > 0.002 ? `tempo ${((pl.tempo - 1) * 100).toFixed(1)}% · ` : ""}अंत bar पर ✓</p>` : ""}</div>`;
}
export function bindMusicFit(panel) {
  const ed = E(); const m = ed.rs.effects.music;
  const cb = $("[data-mfit]", panel); if (cb) cb.onchange = () => { m.fit = cb.checked; if (!m.fit) delete m.fit; H.touch(); if (cb.checked && !(ed.mfit?.id === m.id)) $("[data-mfplan]", panel)?.click(); };
  const b = $("[data-mfplan]", panel); if (b) b.onclick = async () => { b.disabled = true; b.textContent = "beat देख रहे…";
    try { await H.flush(); const r = await ed.ctx.api("POST", `/projects/${ed.pid}/music/fit`, { music_id: m.id, target: +H.outDur().toFixed(2) }); ed.mfit = { id: m.id, plan: r.plan }; }
    catch (e) { ed.ctx.toast(e.message); } H.renderPanel(); };
}

// ====================================================================== text-based editing (Captions → "Text से edit")
const FILL = new Set(["अं", "अंं", "उम", "उम्म", "हम्म", "अ", "आ", "um", "uh", "umm", "uhh", "hmm", "erm", "ah", "eh"]);
const fnorm = (w) => String(w || "").toLowerCase().replace(/[।॥,.!?;:"'""''()\[\]…\-]/g, "");
function keepsOf(cuts, dur) { const on = cuts.filter((c) => c.enabled !== false && c.end > c.start).sort((a, b) => a.start - b.start); const out = []; let t = 0;
  for (const c of on) { if (c.start > t) out.push([t, Math.min(c.start, dur)]); t = Math.max(t, c.end); } if (t < dur) out.push([t, dur]); return out; }
const outOfK = (src, K) => { let o = 0; for (const [a, b] of K) { if (src <= a) break; o += Math.min(src, b) - a; } return o; };
const srcOfK = (out, K) => { let o = 0; for (const [a, b] of K) { if (out <= o + (b - a)) return a + (out - o); o += b - a; } return K.length ? K[K.length - 1][1] : 0; };
function wordGone(w, K) { const d = Math.max(1e-3, w.end - w.start); let kept = 0; for (const [a, b] of K) kept += Math.max(0, Math.min(w.end, b) - Math.max(w.start, a)); return kept / d < 0.5; }
export function textDocHtml(dis) {
  const ed = E(); const K = H.keeps(); const rip = ed.ripple ?? LS("vividora_ripple", true); const gap = ed.silGap ?? 0.8;
  const segs = ed.tr.segments.filter((s) => (s.words || []).length);
  const nGone = ed.words.filter((w) => wordGone(w, K)).length; const nFill = ed.words.filter((w) => FILL.has(fnorm(w.w)) && !wordGone(w, K)).length;
  const tapMode = ed.tapCut ?? LS("vividora_tapcut", false);
  return `<div class="tedit"><div class="irow"><label class="chk small" title="text से कटा हिस्सा हटने पर बाद के titles / overlays / effects / markers उतना पीछे खिसकें"><input type="checkbox" data-ripple ${rip ? "checked" : ""}> Ripple</label>
      <label class="chk small ${tapMode ? "tap-on" : ""}" title="tap करें = शब्द कटे · फिर tap = वापस"><input type="checkbox" data-tapcut ${tapMode ? "checked" : ""}> ✂ Tap to cut</label>
      <button class="btn small" data-tfill ${dis} title="अं, उम, um, uh…">🧹 filler हटाएँ${nFill ? ` (${nFill})` : ""}</button></div>
    <div class="irow"><button class="btn small" data-tsil ${dis}>🤫 <span>${gap}</span> s से लंबी चुप्पी हटाएँ</button><input type="range" data-tgap min="0.3" max="3" step="0.1" value="${gap}" title="कितनी लंबी चुप्पी" style="flex:1"></div>
    <div class="irow"><button class="btn small quiet" data-tdel ${dis} title="Delete / Backspace">🗑 चुने शब्द हटाएँ</button><button class="btn small quiet" data-trest ${dis} title="कटे शब्द वापस">↺ वापस लाएँ</button><span class="small muted grow">${nGone} शब्द कटे</span></div>
    <p class="small muted">${tapMode ? `<b>✂ Tap mode ON</b> — हर शब्द पर tap करो = कट जाएगा · कटे शब्द पर tap = वापस · <b>Ctrl+Z</b> undo` : `शब्द चुनें (खींचकर) → <b>Delete</b>/<b>Backspace</b> = वीडियो से हटे · कटे (~~) शब्द चुनकर Delete या double-click = वापस · क्लिक = वहाँ जाएँ · <b>Ctrl+Z</b> undo`}</p>
    <div class="tdoc ${tapMode ? "tapmode" : ""}" tabindex="0" data-tdoc>${segs.map((s) => `<p>${(s.words || []).map((w) => `<span class="tw ${wordGone(w, K) ? "gone" : ""} ${FILL.has(fnorm(w.w)) ? "fill" : ""}" data-ws="${w.start}" data-we="${w.end}">${esc(w.w)}</span>`).join(" ")}</p>`).join("") || `<p class="small muted">transcript नहीं है</p>`}</div></div>`;
}
function selWords(doc) {
  const s = window.getSelection(); if (!s || s.isCollapsed || !s.rangeCount) return [];
  const r = s.getRangeAt(0); return $$(".tw", doc).filter((el) => r.intersectsNode(el)).map((el) => ({ start: +el.dataset.ws, end: +el.dataset.we, gone: el.classList.contains("gone") }));
}
async function textCut(ops, msg) {
  const ed = E(); if (!ed.canEdit) return; const before = JSON.parse(JSON.stringify(ed.cuts));
  try {
    await H.flush();
    const r = await ed.ctx.api("POST", `/projects/${ed.pid}/textcut`, { ...ops, dry_run: true, note: "text edit" });
    if (E() !== ed) return;
    ed.cuts = r.edl.cuts || []; const rip = ed.ripple ?? LS("vividora_ripple", true); let moved = 0;
    if (rip) moved = ripple(before, ed.cuts);
    H.touch(); H.renderPanel(); H.renderInspector(); H.renderOverlay();
    ed.ctx.toast(`${msg}${r.added ? ` · ${r.added} नए कट` : ""}${r.changed ? ` · ${r.changed} कट बदले` : ""}${moved ? ` · ${moved} items ripple से खिसके` : ""} (Ctrl+Z से वापस)`);
  } catch (e) { ed.ctx.toast(e.message); }
}
// ripple: items on the output timeline follow the source moment they were on (removed parts collapse)
export function ripple(oldCuts, newCuts) {
  const ed = E(); const fx = ed.rs.effects; const K0 = keepsOf(oldCuts, ed.dur), K1 = keepsOf(newCuts, ed.dur); let n = 0;
  const map = (t) => r3(outOfK(srcOfK(t, K0), K1));
  const shift = (o, a, b) => { const s = map(o[a]); const e = b ? map(o[b]) : null; if (Math.abs(s - o[a]) > 1e-3 || (b && Math.abs(e - o[b]) > 1e-3)) n++; o[a] = s; if (b) o[b] = Math.max(e, s + 0.2); };
  for (const k of ["titles", "broll", "fxclips"]) for (const x of fx[k] || []) shift(x, "start", "end");
  for (const x of fx.sfx || []) shift(x, "at");
  for (const m of ed.rs.markers || []) shift(m, "t");
  return n;
}
export function bindTextDoc(panel) {
  const ed = E(); const doc = $("[data-tdoc]", panel); if (!doc) return;
  const rp = $("[data-ripple]", panel); if (rp) rp.onchange = () => { ed.ripple = rp.checked; LSset("vividora_ripple", rp.checked); };
  const tc = $("[data-tapcut]", panel); if (tc) tc.onchange = () => { ed.tapCut = tc.checked; LSset("vividora_tapcut", tc.checked); H.renderPanel(); };
  const gp = $("[data-tgap]", panel); if (gp) gp.oninput = () => { ed.silGap = +gp.value; $("[data-tsil] span", panel).textContent = gp.value; };
  const fl = $("[data-tfill]", panel); if (fl) fl.onclick = () => textCut({ fillers: true }, "🧹 filler हटे");
  const sl = $("[data-tsil]", panel); if (sl) sl.onclick = () => textCut({ silences_over: ed.silGap ?? 0.8 }, `🤫 ${ed.silGap ?? 0.8}s से लंबी चुप्पी हटी`);
  const del = (restore) => { const ws = selWords(doc); if (!ws.length) return ed.ctx.toast("पहले शब्द चुनें (खींचकर)"); const rng = ws.map((w) => [w.start, w.end]);
    window.getSelection()?.removeAllRanges(); textCut(restore ? { restore: rng } : { delete: rng }, restore ? `↺ ${ws.length} शब्द वापस` : `✂ ${ws.length} शब्द हटे`); };
  const db = $("[data-tdel]", panel); if (db) db.onclick = () => del(false);
  const rb = $("[data-trest]", panel); if (rb) rb.onclick = () => del(true);
  const tapMode = ed.tapCut ?? LS("vividora_tapcut", false);
  doc.onclick = (e) => { const w = e.target.closest(".tw"); if (!w) return;
    if (tapMode) {
      // Tap-to-cut: single tap toggles cut/restore
      e.preventDefault(); window.getSelection()?.removeAllRanges();
      if (!ed.canEdit) return;
      const rng = [[+w.dataset.ws, +w.dataset.we]];
      if (w.classList.contains("gone")) { textCut({ restore: rng }, `↺ "${w.textContent}" वापस`); }
      else { textCut({ delete: rng }, `✂ "${w.textContent}" कटा`); }
    } else {
      // Normal mode: click = seek to that word
      if (!window.getSelection()?.isCollapsed) return; H.seek(+w.dataset.ws + 0.01);
    }
  };
  doc.ondblclick = (e) => { if (tapMode) return; const w = e.target.closest(".tw.gone"); if (!w) return; e.preventDefault(); window.getSelection()?.removeAllRanges(); textCut({ restore: [[+w.dataset.ws, +w.dataset.we]] }, `↺ "${w.textContent}" वापस`); };
  doc._del = del;
}
// keyboard inside the text document: Delete/Backspace cut (or restore when everything chosen is already cut)
export function onKey(e) {
  const ed = E(); const doc = $("#ed-panel [data-tdoc]", ed.root);
  if (doc && (e.key === "Delete" || e.key === "Backspace")) { const s = window.getSelection(); if (s && !s.isCollapsed && s.rangeCount && doc.contains(s.anchorNode)) { e.preventDefault(); const ws = selWords(doc); doc._del(ws.length && ws.every((w) => w.gone)); return true; } }
  return false;
}
export function textNow() {   // the word under the playhead lights up
  const ed = E(); const doc = $("#ed-panel [data-tdoc]", ed.root); if (!doc) return; const t = ed.t;
  const cur = $(".tw.now", doc); const el = $$(".tw", doc).find((x) => +x.dataset.ws <= t && t < +x.dataset.we); if (cur === el) return; cur?.classList.remove("now"); el?.classList.add("now");
}

// ====================================================================== autopilot progress (11 steps) + "फिर चलाएँ"
export function autopilotStrip() {
  const ed = E(); const st = ed.p.meta?.autopilot; if (!ed.p.settings?.autopilot || !st?.stage || ed.montage || !ed.apSteps) return "";
  const labels = ed.apSteps; const keys = labels.map((s) => s.key); const failed = st.failed && keys.includes(st.failed) ? st.failed : null;
  if (!failed && (!keys.includes(st.stage) || !["rendering", "transcribing", "cutting", "preparing", "uploaded", "review_cuts", "failed"].includes(ed.p.status))) return "";
  const total = labels.length || st.total || 11; const step = failed ? keys.indexOf(failed) + 1 : keys.indexOf(st.stage) + 1;
  return `<div class="apstrip ${failed ? "fail" : ""}"><div class="row between"><b class="small">✈ Autopilot · ${step}/${total}</b>${failed && ed.canEdit ? `<button class="btn small primary" data-apresume>↻ Autopilot फिर चलाएँ</button>` : ""}</div>
    <div class="apsteps">${Array.from({ length: total }, (_, i) => `<i class="${i + 1 < step ? "done" : i + 1 === step ? (failed ? "failed" : "cur") : ""}" title="${i + 1}. ${esc(labels[i]?.label || "")}"></i>`).join("")}</div>
    <div class="small muted">${esc(failed ? (ed.p.status_note || "").slice(0, 160) : st.label || labels[step - 1]?.label || "")}</div></div>`;
}
export function bindAutopilot(el) {
  const ed = E(); if (ed.p.settings?.autopilot && !ed.apSteps && !ed.apLoading) { ed.apLoading = true; ed.ctx.api("GET", `/projects/${ed.pid}/autopilot`).then((r) => { if (E() === ed) { ed.apSteps = r.steps || []; H.renderJobs(); } }).catch(() => {}); }
  const b = $("[data-apresume]", el); if (b) b.onclick = async () => { b.disabled = true; b.textContent = "शुरू हो रहा…";
    try { await H.flush(); const r = await ed.ctx.api("POST", `/projects/${ed.pid}/autopilot/resume`); ed.ctx.toast(`✈ Autopilot step ${r.step || ""} से फिर चला`); await ed.ctx.load(); } catch (e) { ed.ctx.toast(e.message); b.disabled = false; } };
}

// ====================================================================== shortcuts help (?)
export function shortcutsHtml() {
  const K = [["Space", "चलाएँ / रोकें"], ["← / →", "1 frame (Shift = 1 s)"], ["Home / End", "शुरू / अंत"], ["I / O", "हिस्सा चुनें (In / Out)"], ["X", "In–Out हटाएँ (कट)"], ["S / C", "playhead पर split"],
    ["Del / Backspace", "चुना item हटाएँ · Text से edit में: चुने शब्द काटें"], ["Ctrl+Z / Ctrl+Y", "undo / redo"], ["Ctrl+S", "सेव"], ["Ctrl+D", "duplicate"], ["F", "full screen"],
    ["J / K / L", "shuttle: J = पीछे, K = रोकें, L = आगे (speed बढ़ता है)"],
    ["M", "playhead पर marker (Shift+M = chapter)"], ["K", "चुने clip/main video पर ◆ keyframe (position, zoom, घुमाव, opacity)"], ["Alt+← / Alt+→", "पिछला / अगला keyframe"],
    ["G", "snap on/off (timeline items एक-दूसरे से चिपके)"],
    ["Esc", "selection हटाएँ"], ["?", "यह सूची"]];
  return `<div class="modal shortcuts"><div class="row between"><h2>⌨ Keyboard shortcuts</h2><button class="ibtn" data-scx>✕</button></div><table>${K.map(([k, l]) => `<tr><td>${k.split(" / ").map((x) => `<kbd>${esc(x)}</kbd>`).join(" / ")}</td><td>${esc(l)}</td></tr>`).join("")}</table></div>`;
}

