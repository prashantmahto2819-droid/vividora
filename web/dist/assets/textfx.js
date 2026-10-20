// Text preview — the browser twin of server/vividora/engine/textfx.py.
// Same keyframe tables (from /api/presets → textfx), same maths, drawn with CSS,
// so the editor shows what the render will burn in.
const REST = { x: 0, y: 0, sx: 1, sy: 1, rz: 0, rx: 0, ry: 0, a: 1, blur: 0, fax: 0, w: 0, cl: 0, cr: 1, ct: 0, cb: 1 };
const LEGACY = { none: ["none", "none", "none"], fade: ["fade", "fade", "none"], pop: ["pop", "fade", "none"], slide_up: ["slide_up", "fade", "none"],
  slide_left: ["slide_left", "fade", "none"], zoom_out: ["zoom_out", "fade", "none"], typewriter: ["typewriter", "fade", "none"],
  bounce: ["bounce_in", "fade", "none"], glow: ["fade", "fade", "glow"], shake: ["shake_in", "fade", "none"] };

export function ease(name, u) {
  u = Math.max(0, Math.min(1, u));
  if (name === "out") return 1 - (1 - u) ** 3;
  if (name === "in") return u ** 3;
  if (name === "inout") return u < 0.5 ? 4 * u ** 3 : 1 - (-2 * u + 2) ** 3 / 2;
  if (name === "back") { const c1 = 1.70158, c3 = 2.70158; return 1 + c3 * (u - 1) ** 3 + c1 * (u - 1) ** 2; }
  if (name === "step") return u < 1 ? 0 : 1;
  return u;
}
export function state(kf, p) {
  if (!kf || !kf.length) return { ...REST };
  const full = kf.map((k) => [+k[0], { ...REST, ...k[1] }, k[2] || "lin"]);
  if (p <= full[0][0]) return { ...full[0][1] };
  for (let i = 1; i < full.length; i++) {
    const [t0, a] = full[i - 1], [t1, b, e] = full[i];
    if (p <= t1) { const u = ease(e, (p - t0) / Math.max(1e-6, t1 - t0)); const o = {}; for (const k in REST) o[k] = a[k] + (b[k] - a[k]) * u; return o; }
  }
  return { ...full[full.length - 1][1] };
}
export function normalize(t) {
  const o = { ...t };
  if (!o.anim_in) { const [a, b, c] = LEGACY[o.anim || "fade"] || LEGACY.fade; o.anim_in = a; o.anim_out = b; o.anim_loop = c; }
  if (o.bg && !o.outline && !o.box) { o.outline = o.bg; o.outline_w = o.outline_w ?? 0.01; }
  return o;
}
export function graphemes(s) {
  try { return [...new Intl.Segmenter("hi", { granularity: "grapheme" }).segment(s)].map((x) => x.segment); } catch { return [...s]; }
}
function phaseTimes(t, P) {
  const raw = String(t.text || ""); const dur = Math.max(0.2, t.end - t.start);
  const ain = P.anim_in[t.anim_in] || P.anim_in.fade, aout = P.anim_out[t.anim_out] || P.anim_out.fade;
  const hasIn = !!(ain.kf?.length || ain.unit), hasOut = !!(aout.kf?.length || aout.unit);
  let inS = hasIn ? (t.in_ms ? t.in_ms / 1000 : ain.unit === "char" ? Math.min(1.6, 0.07 * graphemes(raw).length) : 0.45) : 0;
  let outS = hasOut ? (t.out_ms ? t.out_ms / 1000 : 0.35) : 0;
  if (inS + outS > dur * 0.9) { const k = dur * 0.9 / (inS + outS); inS *= k; outS *= k; }
  return { ain, aout, inS, outS, dur };
}
// → { s: state, unit: null | {anim, progress, entering} }
export function animAt(t0, P, now) {
  const t = normalize(t0); if (!P) return { s: { ...REST }, unit: null };
  const { ain, aout, inS, outS, dur } = phaseTimes(t, P); const rel = now - t.start;
  const loop = P.anim_loop[t.anim_loop] || P.anim_loop.none;
  if (inS && rel < inS) { const p = rel / inS; return ain.unit ? { s: { ...REST }, unit: { anim: ain, p, entering: true } } : { s: state(ain.kf, p), unit: null }; }
  if (outS && rel > dur - outS) { const p = (rel - (dur - outS)) / outS; return aout.unit ? { s: { ...REST }, unit: { anim: aout, p, entering: false } } : { s: state(aout.kf, p), unit: null }; }
  if (loop.kf?.length) {
    const mid = rel - inS; const span = dur - inS - outS;
    if (loop.span) return { s: state(loop.kf, mid / Math.max(0.01, span)), unit: null };
    const per = (t.loop_ms || loop.period || 1000) / 1000; return { s: state(loop.kf, (mid % per) / per), unit: null };
  }
  return { s: { ...REST }, unit: null };
}
const hex = (c) => { c = (c || "#ffffff").replace("#", ""); if (c.length === 3) c = [...c].map((x) => x + x).join(""); return [0, 2, 4].map((i) => parseInt(c.slice(i, i + 2), 16) || 0); };
const mixW = (c, w) => { const [r, g, b] = hex(c); const m = (v) => Math.round(v + (255 - v) * w); return `rgb(${m(r)},${m(g)},${m(b)})`; };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function cssFor(t, s, fb, base) {
  const tr = `translate(${(s.x * fb.w).toFixed(1)}px,${(s.y * fb.h).toFixed(1)}px) perspective(600px) rotateX(${s.rx}deg) rotateY(${s.ry}deg) rotate(${-(s.rz + (+t.rotate || 0))}deg) skewX(${(-Math.atan(s.fax) * 180 / Math.PI).toFixed(1)}deg) scale(${s.sx},${s.sy})`;
  const clip = (s.cl > 0 || s.cr < 1 || s.ct > 0 || s.cb < 1) ? `clip-path:inset(${(s.ct * 100).toFixed(1)}% ${((1 - s.cr) * 100).toFixed(1)}% ${((1 - s.cb) * 100).toFixed(1)}% ${(s.cl * 100).toFixed(1)}%);` : "";
  return `transform:${tr};opacity:${(s.a * (t.opacity ?? 1)).toFixed(3)};${s.blur > 0.05 ? `filter:blur(${(s.blur * base / 1080).toFixed(2)}px);` : ""}${clip}color:${mixW(t.color || "#ffffff", s.w)};`;
}
export function textStyle(t, base) {
  const size = (t.size || 0.075) * base; let css = `font-family:'${t.font || "Poppins"}',var(--font);font-size:${size.toFixed(1)}px;font-weight:${t.bold === false ? 500 : 800};`;
  if (t.italic) css += "font-style:italic;"; if (t.underline) css += "text-decoration:underline;";
  if (t.spacing) css += `letter-spacing:${(t.spacing * base).toFixed(1)}px;`;
  if (t.box) { const pad = (t.box_pad ?? 0.016) * base; const [r, g, b] = hex(t.box_color || "#000000"); css += `background:rgba(${r},${g},${b},${1 - (t.box_alpha || 0)});padding:${(pad * 0.5).toFixed(1)}px ${pad.toFixed(1)}px;-webkit-box-decoration-break:clone;box-decoration-break:clone;`; }
  else {
    if (t.outline && (t.outline_w ?? 0) > 0) css += `-webkit-text-stroke:${(t.outline_w * base * 2).toFixed(1)}px ${t.outline};paint-order:stroke fill;`;
    if (t.shadow) css += `text-shadow:${((t.shadow_d || 0) * base).toFixed(1)}px ${((t.shadow_d || 0) * base).toFixed(1)}px ${((t.shadow_d ? 0 : 0.012) * base).toFixed(1)}px ${t.shadow};`;
  }
  if (t.align === "left" || t.align === "right") css += `text-align:${t.align};`;
  return css;
}
export function anchorCss(t, fb) {
  const pos = t.pos || "top";
  const x = pos === "free" ? (t.x ?? 0.5) : 0.5; const y = pos === "free" ? (t.y ?? 0.5) : ({ top: 0.18, center: 0.5, bottom: 0.78 }[pos] ?? 0.18);
  return `left:${(x * 100).toFixed(2)}%;top:${(y * 100).toFixed(2)}%;`;
}
// Full HTML for one text item at output time `now`.
export function renderText(t0, P, now, fb, opts = {}) {
  const t = normalize(t0); const base = Math.min(fb.w, fb.h);
  const { s, unit } = animAt(t, P, now);
  const raw = String(t.text || "");
  let inner;
  if (unit) {
    const an = unit.anim; const lines = raw.split("|"); const parts = []; const units = [];
    lines.forEach((ln, li) => { if (li) parts.push("<br>"); const pieces = an.unit === "word" ? ln.split(" ").flatMap((w, i) => (i ? [" ", w] : [w])) : graphemes(ln);
      for (const pc of pieces) { if (!pc.trim()) parts.push(esc(pc)); else { units.push(parts.length); parts.push(pc); } } });
    const n = Math.max(1, units.length); const st = an.stagger ?? 0.7; const each = st < 1 ? 1 - st : 1 / n;
    const frm = { ...REST, ...(an.from || {}) }, to = { ...REST, ...(an.to || {}) };
    units.forEach((pi, k0) => {
      const k = an.reverse ? n - 1 - k0 : k0; const t0u = n > 1 ? k * (1 - each) / (n - 1) : 0;
      let u = (unit.p - t0u) / (an.step ? 1e-3 : each); u = Math.max(0, Math.min(1, u)); if (an.step) u = unit.p >= t0u ? 1 : 0;
      const A = unit.entering ? frm : REST, B = unit.entering ? REST : to; const v = {}; for (const key in REST) v[key] = A[key] + (B[key] - A[key]) * u;
      parts[pi] = `<span style="display:inline-block;white-space:pre;opacity:${v.a.toFixed(3)};transform:scale(${v.sx},${v.sy});${v.blur > 0.05 ? `filter:blur(${(v.blur * base / 1080).toFixed(1)}px);` : ""}color:${mixW(t.color || "#fff", v.w)}">${esc(parts[pi])}</span>`;
    });
    inner = parts.join("");
  } else inner = esc(raw).replace(/\|/g, "<br>");
  const sel = opts.selected ? " sel" : "";
  return `<div class="ov-title tfx${sel}" data-id="${t._id || ""}" style="position:absolute;${anchorCss(t, fb)}transform:translate(-50%,-50%);text-align:center;white-space:pre-wrap;max-width:94%;line-height:1.2;pointer-events:auto;cursor:move">
    <div style="${textStyle(t, base)}${cssFor(t, s, fb, base)}display:inline-block;transform-origin:50% 50%;">${inner}</div></div>`;
}
