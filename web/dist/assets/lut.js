// Approximate live preview of a .cube LUT on the editor preview: the video (or the cutout canvas) is drawn
// through a WebGL shader that samples the 3D LUT (packed into one 2D texture, trilinear between slices).
// Render uses ffmpeg lut3d (tetrahedral) — this is close, not identical; the "🎞 Preview frame" is exact.
const VS = `attribute vec2 p; varying vec2 v; void main(){ v = vec2(p.x, 1.0 - p.y); gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0); }`;
const FS = `precision mediump float; varying vec2 v; uniform sampler2D tV, tL; uniform float uN, uAmt;
vec3 lut(vec3 c){
  float n = uN; float z = c.b * (n - 1.0); float z0 = floor(z); float f = z - z0; float z1 = min(z0 + 1.0, n - 1.0);
  // slices side by side: texture is (n*n) x n ; x = r within slice, slice index = b, y = g
  vec2 uv0 = vec2((z0 + (c.r * (n - 1.0) + 0.5) / n) / n, (c.g * (n - 1.0) + 0.5) / n);
  vec2 uv1 = vec2((z1 + (c.r * (n - 1.0) + 0.5) / n) / n, (c.g * (n - 1.0) + 0.5) / n);
  return mix(texture2D(tL, uv0).rgb, texture2D(tL, uv1).rgb, f);
}
void main(){ vec3 c = texture2D(tV, v).rgb; gl_FragColor = vec4(mix(c, lut(clamp(c, 0.0, 1.0)), uAmt), 1.0); }`;

export function parseCube(text) {
  let n = 0; const vals = [];
  for (const raw of text.split(/\r?\n/)) {
    const t = raw.trim(); if (!t || t[0] === "#" || /^(TITLE|DOMAIN_)/.test(t)) continue;
    if (t.startsWith("LUT_3D_SIZE")) { n = parseInt(t.split(/\s+/)[1], 10); continue; }
    if (t.startsWith("LUT_1D_SIZE")) return null; // 1D LUTs are not previewed
    const p = t.split(/\s+/); if (p.length !== 3) continue;
    vals.push(+p[0], +p[1], +p[2]);
  }
  if (!n || vals.length !== n * n * n * 3) return null;
  // pack: width n*n (slice b, then r), height n (g); .cube order is r fastest, then g, then b
  const data = new Uint8Array(n * n * n * 4);
  for (let b = 0; b < n; b++) for (let g = 0; g < n; g++) for (let r = 0; r < n; r++) {
    const si = ((b * n + g) * n + r) * 3; const di = ((g * n * n) + b * n + r) * 4;
    data[di] = Math.max(0, Math.min(255, Math.round(vals[si] * 255))); data[di + 1] = Math.max(0, Math.min(255, Math.round(vals[si + 1] * 255)));
    data[di + 2] = Math.max(0, Math.min(255, Math.round(vals[si + 2] * 255))); data[di + 3] = 255;
  }
  return { n, data };
}

export function lutPreview(canvas) {
  const gl = canvas.getContext("webgl", { premultipliedAlpha: false, preserveDrawingBuffer: false });
  if (!gl) return null;
  const sh = (t, src) => { const s = gl.createShader(t); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
  const pr = gl.createProgram(); gl.attachShader(pr, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(pr);
  if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) return null;
  gl.useProgram(pr);
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]), gl.STATIC_DRAW);
  const ap = gl.getAttribLocation(pr, "p"); gl.enableVertexAttribArray(ap); gl.vertexAttribPointer(ap, 2, gl.FLOAT, false, 0, 0);
  const u = { tV: gl.getUniformLocation(pr, "tV"), tL: gl.getUniformLocation(pr, "tL"), uN: gl.getUniformLocation(pr, "uN"), uAmt: gl.getUniformLocation(pr, "uAmt") };
  const mk = () => { const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR); return t; };
  const tV = mk(), tL = mk(); let n = 0, key = "";
  return {
    kind: "webgl",
    setLut(id, cube) { if (key === id) return; key = id; n = cube.n; gl.bindTexture(gl.TEXTURE_2D, tL); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, n * n, n, 0, gl.RGBA, gl.UNSIGNED_BYTE, cube.data); },
    draw(src, amount) {
      if (!n) return false;
      try { gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, tV); gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, src); } catch { return false; }
      gl.uniform1i(u.tV, 0); gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, tL); gl.uniform1i(u.tL, 1);
      gl.uniform1f(u.uN, n); gl.uniform1f(u.uAmt, Math.max(0, Math.min(1, amount ?? 1)));
      gl.viewport(0, 0, canvas.width, canvas.height); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4); return true;
    },
    destroy() { try { gl.getExtension("WEBGL_lose_context")?.loseContext(); } catch {} },
  };
}
