// Vividora — live person cutout in the editor preview.
//
// The worker makes a grayscale alpha video per clip (engine/matting.py, Robust Video Matting).
// Here the picture <video> and its alpha <video> are kept on the same clock and composited on
// a <canvas> every frame: background (blur / dark / colour / gradient / image / looping video,
// zoom, extra blur, dark, tint) → drop shadow → glow → stroke → clones → the person, with the
// person's size / position / mirror, entrance animation and blink — the same order and
// parameters as effects.body_chain in the render. "सिर्फ़ इंसान" overlays (B-roll cutouts)
// use the same pipeline with a transparent background.
//
// WebGL (one mask-prep pass, quarter-resolution separable blurs, one composite pass) with a
// canvas-2D fallback (CSS-filter blur + SVG luminance→alpha + canvas shadows; no stroke).

const VS = `attribute vec2 p; uniform float uFlip; varying vec2 v;
void main(){ v = vec2((p.x+1.0)*0.5, uFlip > 0.5 ? (1.0-p.y)*0.5 : (p.y+1.0)*0.5); gl_Position = vec4(p,0.0,1.0); }`;

// alpha video → refined mask (R). Limited-range video is already expanded by the browser.
// erode ("किनारा अंदर") = min over 8 taps on a ring of radius uShrink; feather ("नरम") is a separate
// small blur of this result (see blur()), so the pass stays at 9 texture reads per pixel.
const FS_MASK = `precision mediump float; varying vec2 v; uniform sampler2D tA; uniform vec2 uPx; uniform float uShrink;
float a(vec2 q){ return texture2D(tA, q).r; }
void main(){ float m = a(v);
  if (uShrink >= 0.25) { vec2 r = uPx*uShrink;
    m = min(m, a(v+vec2(r.x,0.))); m = min(m, a(v-vec2(r.x,0.))); m = min(m, a(v+vec2(0.,r.y))); m = min(m, a(v-vec2(0.,r.y)));
    vec2 d = r*0.7071; m = min(m, a(v+d)); m = min(m, a(v-d)); m = min(m, a(v+vec2(d.x,-d.y))); m = min(m, a(v+vec2(-d.x,d.y))); }
  m = m < 0.024 ? 0.0 : m; gl_FragColor = vec4(m, m, m, 1.0); }`;

// separable gaussian (13 taps), on a small texture; uDir = step in uv
const FS_BLUR = `precision mediump float; varying vec2 v; uniform sampler2D t; uniform vec2 uDir;
void main(){ vec4 c = texture2D(t, v) * 0.1596;
  c += (texture2D(t, v+uDir) + texture2D(t, v-uDir)) * 0.1478;
  c += (texture2D(t, v+uDir*2.0) + texture2D(t, v-uDir*2.0)) * 0.1172;
  c += (texture2D(t, v+uDir*3.0) + texture2D(t, v-uDir*3.0)) * 0.0798;
  c += (texture2D(t, v+uDir*4.0) + texture2D(t, v-uDir*4.0)) * 0.0466;
  c += (texture2D(t, v+uDir*5.0) + texture2D(t, v-uDir*5.0)) * 0.0234;
  c += (texture2D(t, v+uDir*6.0) + texture2D(t, v-uDir*6.0)) * 0.0101;
  gl_FragColor = c / 0.9294; }`;

const FS_COMP = `precision mediump float; varying vec2 v;
uniform sampler2D tVid, tMask, tBg, tBgBlur, tShadow, tGlow, tStroke;
uniform int uMode; uniform float uOverlay;
uniform vec3 uC1, uC2, uTint, uStrokeC, uGlowC; uniform float uTintAmt, uDim, uZoom, uBgBright, uBgSat, uGradT;
uniform vec2 uBgScale, uBgOff; uniform float uBgContain, uBgBlurOn;
uniform float uScale, uFlipX; uniform vec2 uMove; uniform vec2 uAnimOff; uniform float uAnimK, uVisible;
uniform float uShadowOn, uShadowOp; uniform vec2 uShadowOff; uniform float uGlowOn, uGlowK, uStrokeOn; uniform int uClones; uniform float uCloneStep;
vec2 pv(vec2 q){ q = 0.5 + (q - 0.5 - uAnimOff) / uAnimK; q = (q - 0.5 - uMove) / uScale + 0.5; if (uFlipX > 0.5) q.x = 1.0 - q.x; return q; }
float inside(vec2 q){ return step(0.0, q.x) * step(0.0, q.y) * step(q.x, 1.0) * step(q.y, 1.0); }
float mk(sampler2D t, vec2 q){ return texture2D(t, q).r * inside(q); }
vec3 sat(vec3 c, float s){ float l = dot(c, vec3(0.299, 0.587, 0.114)); return mix(vec3(l), c, s); }
vec3 bgSample(vec2 q){
  vec2 b = (q - 0.5) / (1.0 + uZoom) + 0.5;
  if (uMode == 0) return texture2D(tVid, b).rgb;
  if (uMode == 1) return texture2D(tBgBlur, b).rgb;
  if (uMode == 2) return texture2D(tVid, b).rgb;
  if (uMode == 3) return uC1;
  if (uMode == 4) { float k = clamp(dot(b - 0.5, vec2(0.7071)) * 0.7071 + 0.5 + 0.08 * sin(uGradT), 0.0, 1.0); return mix(uC1, uC2, k); }
  vec2 s = (b - 0.5) / uBgScale + 0.5 + uBgOff;
  if (uBgContain > 0.5) { if (inside(s) < 0.5) return texture2D(tBgBlur, b).rgb; return uBgBlurOn > 0.5 ? texture2D(tBgBlur, b).rgb : texture2D(tBg, s).rgb; }
  return uBgBlurOn > 0.5 ? texture2D(tBgBlur, b).rgb : texture2D(tBg, s).rgb;
}
void main(){
  vec2 q = pv(v); float m = mk(tMask, q) * uVisible;
  if (uOverlay > 0.5) { vec3 c = texture2D(tVid, q).rgb; gl_FragColor = vec4(c * m, m); return; }
  vec3 col = bgSample(v);
  col = sat(col + uBgBright, uBgSat);
  col = mix(col, uTint, uTintAmt);
  if (uVisible > 0.5) {
    if (uShadowOn > 0.5) { float s = mk(tShadow, pv(v - uShadowOff)) * uShadowOp; col = mix(col, vec3(0.0), s); }
    if (uGlowOn > 0.5) { float g = clamp(mk(tGlow, q) * uGlowK, 0.0, 1.0); col = mix(col, uGlowC, g); }
    if (uStrokeOn > 0.5) { float d = step(0.094, mk(tStroke, q)); float ring = clamp(d - mk(tMask, q), 0.0, 1.0); col = mix(col, uStrokeC, ring); }
    for (int i = 0; i < 4; i++) { if (i >= uClones) break;
      float off = uCloneStep * float(i + 1) * (mod(float(i), 2.0) > 0.5 ? -1.0 : 1.0);
      vec2 cq = pv(v - vec2(off, 0.0)); float cm = mk(tMask, cq) * 0.45; col = mix(col, texture2D(tVid, cq).rgb, cm); }
  }
  col = mix(col, texture2D(tVid, q).rgb, m);
  gl_FragColor = vec4(col, 1.0);
}`;

const MODES = { none: 0, blur: 1, dim: 2, flat: 3, gradient: 4, image: 5, video: 6 };
const hex = (h, d = "#000000") => { const s = String(h || d).replace("#", "").padEnd(6, "0"); return [0, 2, 4].map((i) => parseInt(s.slice(i, i + 2), 16) / 255); };
const ready = (el) => !!el && (el.tagName === "IMG" ? el.complete && el.naturalWidth > 0 : el.readyState >= 2 && el.videoWidth > 0);

// ---------------------------------------------------------------- WebGL compositor
function glCompositor(canvas, overlay) {
  const gl = canvas.getContext("webgl", { premultipliedAlpha: true, alpha: !!overlay, antialias: false, preserveDrawingBuffer: true });
  if (!gl) return null;
  const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
  const prog = (fs) => { const p = gl.createProgram(); gl.attachShader(p, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, fs)); gl.bindAttribLocation(p, 0, "p"); gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p)); const u = {}; const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
    for (let i = 0; i < n; i++) { const info = gl.getActiveUniform(p, i); u[info.name.replace(/\[0\]$/, "")] = gl.getUniformLocation(p, info.name); } return { p, u }; };
  let P;
  try { P = { mask: prog(FS_MASK), blur: prog(FS_BLUR), comp: prog(FS_COMP) }; } catch (e) { console.warn("cutout webgl", e); return null; }
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  const tex = () => { const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
    for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([0, 0, 0, 255])); return t; };
  const T = { vid: tex(), alpha: tex(), bg: tex() };
  const fbos = {};
  const fbo = (name, w, h) => { let f = fbos[name]; if (f && f.w === w && f.h === h) return f; if (!f) { f = { t: tex(), fb: gl.createFramebuffer() }; fbos[name] = f; }
    gl.bindTexture(gl.TEXTURE_2D, f.t); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    gl.bindFramebuffer(gl.FRAMEBUFFER, f.fb); gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, f.t, 0); f.w = w; f.h = h; return f; };
  const upload = (t, el) => { gl.bindTexture(gl.TEXTURE_2D, t); gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false); gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    try { gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, el); return true; } catch { return false; } };
  const run = (pr, target, w, h, setup) => { gl.useProgram(pr.p); gl.bindFramebuffer(gl.FRAMEBUFFER, target ? target.fb : null); gl.viewport(0, 0, w, h);
    gl.uniform1f(pr.u.uFlip, target ? 0 : 1); setup(pr.u); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4); };
  const bind = (unit, t, loc) => { gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, t); if (loc) gl.uniform1i(loc, unit); };
  // blur src texture (any size) into a small texture, sigma in FULL-RES px
  const blur = (name, srcT, W, H, sigma) => {
    // work on a smaller copy so that sigma ≈ 2.5 texels there; taps ≈ 1.1 texel apart → smooth, no blocks
    const div = Math.max(1, Math.min(8, Math.round(sigma / 2.5))); const w = Math.max(8, Math.round(W / div)), h = Math.max(8, Math.round(H / div));
    const a = fbo(name + "A", w, h), b = fbo(name + "B", w, h); const step = Math.max(0.5, (sigma / div) / 2.2);
    run(P.blur, a, w, h, (u) => { bind(0, srcT, u.t); gl.uniform2f(u.uDir, step / w, 0); });
    run(P.blur, b, w, h, (u) => { bind(0, a.t, u.t); gl.uniform2f(u.uDir, 0, step / h); });
    return b.t;
  };
  return {
    kind: "webgl",
    draw(s) {
      const W = canvas.width, H = canvas.height; if (!W || !H) return false;
      if (!ready(s.vid) || !ready(s.alpha)) return false;
      upload(T.vid, s.vid); upload(T.alpha, s.alpha);
      const k720 = Math.min(W, H) / 720; const sz = (px) => Math.max(0, px) * k720;
      const mk0 = fbo("mask", W, H);
      run(P.mask, mk0, W, H, (u) => { bind(0, T.alpha, u.tA); gl.uniform2f(u.uPx, 1 / W, 1 / H); gl.uniform1f(u.uShrink, sz(s.edge?.shrink || 0)); });
      const fe = sz(s.edge?.feather || 0);
      const mk = { t: fe >= 0.3 ? blur("fe", mk0.t, W, H, fe) : mk0.t };
      const b = s.bg || {}; let mode = overlay ? 0 : (MODES[b.mode] ?? 1);
      let bgBlur = T.vid, bgOn = 0, contain = 0, scale = [1, 1];
      if (!overlay) {
        if ((mode === 5 || mode === 6) && !(ready(b.el) && upload(T.bg, b.el))) mode = 3;
        if (mode === 1) bgBlur = blur("bgv", T.vid, W, H, b.blur ?? 18);
        if (mode === 5 || mode === 6) {
          const iw = b.el.naturalWidth || b.el.videoWidth, ih = b.el.naturalHeight || b.el.videoHeight; const ar = (iw / ih) / (W / H);
          contain = b.fit === "contain" ? 1 : 0;
          scale = contain ? (ar > 1 ? [1, 1 / ar] : [ar, 1]) : (ar > 1 ? [ar, 1] : [1, 1 / ar]);
          if (contain || (b.blur2 || 0) > 0) { bgBlur = blur("bgi", T.bg, W, H, contain && !(b.blur2 > 0) ? 30 : b.blur2); bgOn = (b.blur2 || 0) > 0 ? 1 : 0; }
        } else if ((b.blur2 || 0) > 0 && mode !== 1) { bgBlur = blur("bgv", T.vid, W, H, b.blur2); if (mode === 0 || mode === 2) mode = 1; }
      }
      const tSh = s.shadow?.on ? blur("sh", mk.t, W, H, s.shadow.blur ?? 18) : mk.t;
      const tGl = s.glow?.on ? blur("gl", mk.t, W, H, (s.glow.size ?? 24) * 0.6) : mk.t;
      const tSt = s.stroke?.on ? blur("st", mk.t, W, H, (s.stroke.width ?? 8) * 0.5) : mk.t;
      if (overlay) { gl.clearColor(0, 0, 0, 0); gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.clear(gl.COLOR_BUFFER_BIT); }
      run(P.comp, null, W, H, (u) => {
        bind(0, T.vid, u.tVid); bind(1, mk.t, u.tMask); bind(2, T.bg, u.tBg); bind(3, bgBlur, u.tBgBlur); bind(4, tSh, u.tShadow); bind(5, tGl, u.tGlow); bind(6, tSt, u.tStroke);
        gl.uniform1i(u.uMode, mode); gl.uniform1f(u.uOverlay, overlay ? 1 : 0);
        gl.uniform3fv(u.uC1, hex(b.color, "#111111")); gl.uniform3fv(u.uC2, hex(b.color2, "#f2b33d")); gl.uniform3fv(u.uTint, hex(b.tint, "#f2b33d"));
        gl.uniform1f(u.uTintAmt, overlay ? 0 : Math.min(0.9, b.tintAmt || 0)); gl.uniform1f(u.uZoom, overlay ? 0 : (b.zoomNow || 0)); gl.uniform1f(u.uGradT, (s.t || 0) * 0.6);
        const dim = Math.min(0.9, b.dim || 0); const base = mode === 1 ? -0.04 : mode === 2 ? -0.35 : 0; const bsat = mode === 2 ? 0.6 : 1;
        gl.uniform1f(u.uBgBright, overlay ? 0 : base - 0.5 * dim); gl.uniform1f(u.uBgSat, overlay ? 1 : bsat * (1 - 0.4 * dim));
        gl.uniform2f(u.uBgScale, scale[0], scale[1]); gl.uniform2f(u.uBgOff, 0, 0); gl.uniform1f(u.uBgContain, contain); gl.uniform1f(u.uBgBlurOn, bgOn);
        const p = s.person || {}; gl.uniform1f(u.uScale, Math.max(0.3, Math.min(2, p.scale || 1))); gl.uniform1f(u.uFlipX, p.flip ? 1 : 0); gl.uniform2f(u.uMove, p.x || 0, p.y || 0);
        const an = s.anim || {}; gl.uniform2f(u.uAnimOff, an.dx || 0, an.dy || 0); gl.uniform1f(u.uAnimK, an.k || 1); gl.uniform1f(u.uVisible, an.hidden ? 0 : 1);
        gl.uniform1f(u.uShadowOn, s.shadow?.on ? 1 : 0); gl.uniform1f(u.uShadowOp, Math.min(1, s.shadow?.opacity ?? 0.55)); const so = s.shadow?.offset ?? 0.012; gl.uniform2f(u.uShadowOff, so, so * W / H);
        gl.uniform1f(u.uGlowOn, s.glow?.on ? 1 : 0); gl.uniform1f(u.uGlowK, s.glow?.strength ?? 1.6); gl.uniform3fv(u.uGlowC, hex(s.glow?.color, "#f2b33d"));
        gl.uniform1f(u.uStrokeOn, s.stroke?.on ? 1 : 0); gl.uniform3fv(u.uStrokeC, hex(s.stroke?.color, "#ffffff"));
        gl.uniform1i(u.uClones, Math.min(4, s.clones || 0)); gl.uniform1f(u.uCloneStep, 0.22);
      });
      return true;
    },
    destroy() { try { gl.getExtension("WEBGL_lose_context")?.loseContext(); } catch {} },
  };
}

// ---------------------------------------------------------------- canvas-2D fallback
let svgReady = false;
function lumaFilter() {
  if (svgReady) return; svgReady = true;
  const d = document.createElement("div"); d.style.cssText = "position:absolute;width:0;height:0;overflow:hidden";
  d.innerHTML = `<svg width="0" height="0"><filter id="vv-l2a" color-interpolation-filters="sRGB"><feColorMatrix type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  1 0 0 0 0"/></filter></svg>`;
  document.body.appendChild(d);
}
function c2dCompositor(canvas, overlay) {
  const ctx = canvas.getContext("2d"); if (!ctx) return null; lumaFilter();
  const off = document.createElement("canvas"), oc = off.getContext("2d");
  const mask = document.createElement("canvas"), mc = mask.getContext("2d");
  const cover = (el, W, H, contain) => { const iw = el.naturalWidth || el.videoWidth, ih = el.naturalHeight || el.videoHeight; const k = contain ? Math.min(W / iw, H / ih) : Math.max(W / iw, H / ih); return [(W - iw * k) / 2, (H - ih * k) / 2, iw * k, ih * k]; };
  return {
    kind: "2d",
    draw(s) {
      const W = canvas.width, H = canvas.height; if (!W || !H || !ready(s.vid) || !ready(s.alpha)) return false;
      const k720 = Math.min(W, H) / 720;
      for (const c of [off, mask]) if (c.width !== W || c.height !== H) { c.width = W; c.height = H; }
      // person = picture × (alpha video as luminance → alpha)
      mc.globalCompositeOperation = "copy"; mc.filter = `url(#vv-l2a)${s.edge?.feather ? ` blur(${(s.edge.feather * k720).toFixed(1)}px)` : ""}`; mc.drawImage(s.alpha, 0, 0, W, H); mc.filter = "none";
      oc.globalCompositeOperation = "copy"; oc.drawImage(s.vid, 0, 0, W, H); oc.globalCompositeOperation = "destination-in"; oc.drawImage(mask, 0, 0);
      const b = s.bg || {}; const p = s.person || {}; const an = s.anim || {};
      ctx.save(); ctx.globalCompositeOperation = "source-over";
      if (overlay) ctx.clearRect(0, 0, W, H);
      else {
        const z = 1 + (b.zoomNow || 0); ctx.save(); ctx.translate(W / 2, H / 2); ctx.scale(z, z); ctx.translate(-W / 2, -H / 2);
        const dim = Math.min(0.9, b.dim || 0);
        const f = [b.mode === "blur" ? `blur(${((b.blur ?? 18) * k720).toFixed(1)}px) brightness(.96)` : "", b.mode === "dim" ? "brightness(.65) saturate(.6)" : "", b.blur2 ? `blur(${(b.blur2 * k720).toFixed(1)}px)` : "", dim ? `brightness(${1 - 0.5 * dim}) saturate(${1 - 0.4 * dim})` : ""].filter(Boolean).join(" ");
        ctx.filter = f || "none";
        if (b.mode === "flat") { ctx.fillStyle = b.color || "#111111"; ctx.fillRect(0, 0, W, H); }
        else if (b.mode === "gradient") { const g = ctx.createLinearGradient(0, 0, W, H); g.addColorStop(0, b.color || "#1b1f3a"); g.addColorStop(1, b.color2 || "#f2b33d"); ctx.fillStyle = g; ctx.fillRect(0, 0, W, H); }
        else if ((b.mode === "image" || b.mode === "video") && ready(b.el)) { ctx.drawImage(b.el, ...cover(b.el, W, H, b.fit === "contain")); }
        else ctx.drawImage(s.vid, 0, 0, W, H);
        ctx.restore(); ctx.filter = "none";
        if (b.tintAmt) { ctx.globalAlpha = Math.min(0.9, b.tintAmt); ctx.fillStyle = b.tint || "#f2b33d"; ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1; }
      }
      if (!an.hidden) {
        ctx.translate(W / 2 + (an.dx || 0) * W, H / 2 + (an.dy || 0) * H); ctx.scale(an.k || 1, an.k || 1);
        const sc = Math.max(0.3, Math.min(2, p.scale || 1)); ctx.translate((p.x || 0) * W, (p.y || 0) * H); ctx.scale(sc * (p.flip ? -1 : 1), sc); ctx.translate(-W / 2, -H / 2);
        if (s.shadow?.on && !overlay) { ctx.shadowColor = `rgba(0,0,0,${s.shadow.opacity ?? 0.55})`; ctx.shadowBlur = (s.shadow.blur ?? 18) * k720; ctx.shadowOffsetX = ctx.shadowOffsetY = (s.shadow.offset ?? 0.012) * W; ctx.drawImage(off, 0, 0); ctx.shadowColor = "transparent"; }
        if (s.glow?.on && !overlay) { ctx.shadowColor = s.glow.color || "#f2b33d"; ctx.shadowBlur = (s.glow.size ?? 24) * k720; ctx.shadowOffsetX = ctx.shadowOffsetY = 0; ctx.drawImage(off, 0, 0); ctx.drawImage(off, 0, 0); ctx.shadowColor = "transparent"; }
        for (let i = 0; i < Math.min(4, s.clones || 0) && !overlay; i++) { ctx.globalAlpha = 0.45; ctx.drawImage(off, W * 0.22 * (i + 1) * (i % 2 ? -1 : 1) * (p.flip ? -1 : 1), 0); ctx.globalAlpha = 1; }
        ctx.drawImage(off, 0, 0);
      }
      ctx.restore();
      return true;
    },
    destroy() {},
  };
}

export function compositor(canvas, { overlay = false, force2d = false } = {}) {
  return (!force2d && glCompositor(canvas, overlay)) || c2dCompositor(canvas, overlay);
}

// ---------------------------------------------------------------- clocks
// Keep a follower <video> on a target time: hard seek on a big jump (cut, skip, seek), otherwise
// nudge its playbackRate so it converges without visible stutter.
export function follow(el, target, playing, rate = 1, fps = 30) {
  if (!el || el.readyState < 1) return;
  const dur = el.duration || Infinity; if (target > dur) target = dur - 0.001;
  const d = target - el.currentTime;
  if (!playing) { if (!el.paused) el.pause(); if (Math.abs(d) > 0.5 / fps && !el.seeking) el.currentTime = Math.max(0, target); el.playbackRate = rate; return; }
  if (Math.abs(d) > 0.3) { if (!el.seeking) el.currentTime = Math.max(0, target + 0.03); el.playbackRate = rate; }
  else el.playbackRate = Math.max(0.0625, rate * (1 + Math.max(-0.25, Math.min(0.25, d * 2.5))));
  if (el.paused) el.play().catch(() => {});
}

// Body-effect settings (render JSON) + output time → compositor state (same formulas as effects.body_chain).
export function bodyState(b, ot, outDur, el) {
  const T = +b.anim_seconds || 0.9; const u = Math.min(1, Math.max(0, ot / T)); const e = 1 - u * u;
  const an = { dx: 0, dy: 0, k: 1, hidden: false };
  if (ot < T) {
    if (b.anim === "drop") an.dy = -e; else if (b.anim === "rise") an.dy = e; else if (b.anim === "slide") an.dx = -e;
    else if (b.anim === "pop") an.k = 0.6 + 0.5 * u;
  }
  if (b.anim === "blink") { const P = +b.blink_period || 0.4; an.hidden = (ot % P) >= P * 0.55; }
  return {
    bg: { mode: b.bg || "blur", blur: +b.bg_blur || 18, color: b.bg_color, color2: b.bg_color2, el, fit: b.bg_fit, blur2: +b.bg_blur2 || 0, dim: +b.bg_dim || 0,
      tint: b.bg_tint, tintAmt: +b.bg_tint_amt || 0, zoomNow: (+b.bg_zoom || 0) * Math.min(1, ot / Math.max(0.1, outDur)) },
    person: { scale: +b.subj_scale || 1, x: +b.subj_x || 0, y: +b.subj_y || 0, flip: !!b.flip },
    edge: { shrink: +b.edge_shrink || 0, feather: +b.edge_feather || 0 },
    stroke: { on: !!b.stroke, color: b.stroke_color, width: +b.stroke_width || 8 },
    glow: { on: !!b.glow, color: b.glow_color, size: +b.glow_size || 24, strength: +b.glow_strength || 1.6 },
    shadow: { on: !!b.shadow, opacity: b.shadow_opacity ?? 0.55, blur: +b.shadow_blur || 18, offset: b.shadow_offset ?? 0.012 },
    clones: +b.clones || 0, anim: an, t: ot,
  };
}
