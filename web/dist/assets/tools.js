// AI Tools — Voice Studio (text → speech, self-hosted VoiceStudio) and Image → 3D (.glb, self-hosted TripoSR).
let ctx = null;
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function ensureCss() {
  if ($("#tl-css")) return;
  const st = document.createElement("style"); st.id = "tl-css";
  st.textContent = `.tl-wrap{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1rem}@media(max-width:900px){.tl-wrap{grid-template-columns:1fr}}
.tl-box{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:1rem}
.gd-tab{width:100%;border-collapse:collapse;font-size:.8rem;min-width:560px}.gd-tab th,.gd-tab td{text-align:left;padding:.35rem .5rem;border-bottom:1px solid var(--line);vertical-align:top}.gd-tab th{opacity:.65;font-weight:600}
.pk-help{margin:.1rem 0 .45rem}.pk-help summary{cursor:pointer;opacity:.85}
.pk-row{padding:.6rem 0;border-top:1px solid var(--line)}.pk-row:first-of-type{border-top:0;padding-top:0}
.pk-head{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap}.pk-head .grow{flex:1}.pk-edit select{flex:1;min-width:180px}.pk-chip{font-size:.72rem;padding:.08rem .5rem;border-radius:99px;border:1px solid var(--line);color:var(--muted)}
.pk-chip.ok{border-color:rgba(70,200,120,.5);color:#46c878}.pk-chip code{font-size:.72rem}
.pk-edit{display:flex;gap:.4rem;flex-wrap:wrap}.pk-edit input{flex:1;min-width:180px}
#api-tabs{display:inline-flex;border:1px solid var(--line);border-radius:10px;overflow:hidden;max-width:100%}#api-tabs button{background:none;border:0;color:var(--muted);padding:.55rem .9rem;cursor:pointer;font:inherit}
#api-tabs button.on{background:var(--amber);color:#111;font-weight:600}@media(max-width:560px){#api-tabs{display:flex}#api-tabs button{flex:1;padding:.5rem .4rem;font-size:.85rem}}
.tl-box textarea{width:100%;min-height:9rem;resize:vertical}
.tl-row{display:flex;gap:.6rem;flex-wrap:wrap;align-items:flex-end;margin:.6rem 0}.tl-row .field{flex:1;min-width:140px}
.tl-st{font-size:.85rem;margin-top:.5rem}.tl-st.err{color:#ff6b5e}
.tl-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:.6rem;margin-top:.6rem}
.tl-item{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:.6rem;display:flex;flex-direction:column;gap:.35rem;min-width:0}
.tl-item b{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tl-prev{max-width:100%;max-height:220px;border-radius:8px;display:block;margin:.4rem 0}
.tl-crop{position:relative;display:inline-block;max-width:100%;touch-action:none;cursor:crosshair;background:repeating-conic-gradient(#2a3140 0 25%,#1c222d 0 50%) 0 0/16px 16px;border-radius:8px;overflow:hidden}.tl-crop canvas{display:block;max-width:100%}.tl-crop i{position:absolute;border:2px solid #ffb020;background:rgba(255,176,32,.12);pointer-events:none}`;
  document.head.appendChild(st);
}

async function blobPost(path, body) {
  const r = await fetch("/api" + path, { method: "POST", headers: { authorization: "Bearer " + ctx.S.token, "content-type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.error || r.statusText); }
  return r.blob();
}

// ---------------------------------------------------------------- Voice Studio (TTS)
export function voiceView() {
  return `<div class="pghead"><div><h1>🎙 Voice Studio</h1><p class="muted">Text लिखें → AI आवाज़ बनाएँ (हिंदी, English और 600+ भाषाएँ)। अपने server पर चलता है — कोई credit नहीं लगता।</p></div></div>
  <div class="tl-wrap"><div class="tl-box">
    <div class="field"><label>Text (max 5000 अक्षर)</label><textarea id="vs-text" maxlength="5000" placeholder="यहाँ वह लिखें जो बुलवाना है…"></textarea></div>
    <div class="tl-row">
      <div class="field"><label>भाषा</label><select id="vs-lang"><option value="hi">हिंदी</option><option value="en">English</option><option value="mr">मराठी</option><option value="bn">বাংলা</option><option value="ta">தமிழ்</option><option value="te">తెలుగు</option><option value="gu">ગુજરાતી</option><option value="pa">ਪੰਜਾਬੀ</option><option value="ur">اردو</option></select></div>
      <div class="field"><label>Model</label><select id="vs-model"><option value="">Default</option></select></div>
      <div class="field"><label>Voice</label><select id="vs-voice"><option value="">Default</option></select></div>
      <div class="field"><label>Speed <span id="vs-sp-l" class="small muted">1.0×</span></label><input type="range" id="vs-speed" min="0.6" max="1.6" step="0.05" value="1"></div>
    </div>
    <button class="btn primary" id="vs-go">🔊 आवाज़ बनाएँ</button>
    <div class="tl-st" id="vs-st"></div>
  </div><div class="tl-box"><h3 style="margin:0 0 .4rem">नतीजा</h3><div id="vs-out"><p class="small muted">बनी हुई आवाज़ यहाँ सुनें और download करें।</p></div></div></div>`;
}
export function voiceBind(c) {
  ctx = c; ensureCss();
  const st = (m, err) => { const e = $("#vs-st"); if (e) { e.textContent = m || ""; e.classList.toggle("err", !!err); } };
  const opt = (x) => typeof x === "string" ? [x, x] : [x.id ?? x.name ?? x.value, x.name ?? x.label ?? x.id ?? x.value];
  const fill = (sel, list) => { $(sel).innerHTML = `<option value="">Default</option>` + (list || []).map((x) => { const [v, l] = opt(x); return v ? `<option value="${esc(v)}">${esc(l)}</option>` : ""; }).join(""); };
  ctx.api("GET", "/voicestudio/health").then((h) => { if (h.status !== "ok") st("⚠ VoiceStudio service बंद है (port 3900) — server पर `systemctl status voicestudio` देखें", true); }).catch(() => st("⚠ VoiceStudio से संपर्क नहीं हो पाया", true));
  ctx.api("GET", "/voicestudio/models").then((r) => fill("#vs-model", r.models)).catch(() => {});
  const loadVoices = () => ctx.api("GET", "/voicestudio/voices" + ($("#vs-model").value ? "?model=" + encodeURIComponent($("#vs-model").value) : "")).then((r) => fill("#vs-voice", r.voices)).catch(() => {});
  loadVoices(); $("#vs-model").onchange = loadVoices;
  $("#vs-speed").oninput = (e) => { $("#vs-sp-l").textContent = (+e.target.value).toFixed(2).replace(/0$/, "") + "×"; };
  $("#vs-go").onclick = async () => {
    const text = $("#vs-text").value.trim(); if (!text) return st("पहले text लिखें", true);
    const btn = $("#vs-go"); btn.disabled = true; st("आवाज़ बन रही है… (CPU पर लंबे text में 1–2 मिनट लग सकते हैं)");
    try {
      const r0 = await ctx.api("POST", "/voiceover", { text, lang: $("#vs-lang").value, vs_model: $("#vs-model").value || undefined, vs_voice: $("#vs-voice").value || undefined, speed: +$("#vs-speed").value, voice: "vs_multi" });
      let item = null;
      for (let i = 0; i < 400 && !item; i++) {
        if (!$("#vs-st")) return; // left the page
        const s2 = await ctx.api("GET", "/voiceover/" + r0.job_id);
        if (s2.status === "failed") throw new Error(s2.error || "आवाज़ नहीं बन पाई");
        if (s2.status === "done") { item = s2.item; break; }
        st(`आवाज़ बन रही है… ${s2.seconds}s (लंबे text में 1–2 मिनट लगते हैं, page खुला रखें)`); await sleep(2500);
      }
      if (!item) throw new Error("बहुत देर लग रही है — बाद में Library → Voice-over में देखें");
      $("#vs-out").innerHTML = `<audio controls src="${esc(item.url)}" style="width:100%"></audio><p><a class="btn small" href="${esc(item.url)}" download="${esc(item.name)}.wav">⬇ WAV download</a></p><p class="small muted">✓ Library → Voice-over में save है। Editor के «3D &amp; Voice» tab से सीधे timeline पर लग सकती है।</p>`;
      st("तैयार ✓");
    } catch (e) { st(e.message, true); } finally { btn.disabled = false; }
  };
}

// ---------------------------------------------------------------- Image → 3D (.glb)
export function glbView() {
  return `<div class="pghead"><div><h1>🧊 Image → 3D (.glb)</h1><p class="muted">एक photo या character की तस्वीर दें → 3D model (.glb) बनता है। साफ़ background वाली, सामने से ली तस्वीर सबसे अच्छी रहती है। CPU पर 1–3 मिनट लगते हैं।</p></div><div class="row"><a class="btn" href="#/characters3d">3D Studio</a></div></div>
  <div class="tl-wrap"><div class="tl-box">
    <div class="drop" id="g3-drop"><input type="file" id="g3-file" accept="image/*" hidden><b>तस्वीर यहाँ छोड़ें या click करें</b><br><span class="muted small">PNG / JPG, 10 MB तक</span><div id="g3-name" class="small"></div></div>
    <div id="g3-cropbox" hidden><p class="small muted" style="margin:.4rem 0">⚠ सिर्फ़ <b>एक</b> character/object चाहिए। कई poses वाली sheet हो तो उंगली/माउस से <b>एक character पर box खींचें</b>।</p>
      <div class="tl-crop" id="g3-crop"><canvas id="g3-cv"></canvas><i id="g3-sel" hidden></i></div>
      <label class="chk" style="display:flex;gap:.4rem;align-items:center;margin:.4rem 0"><input type="checkbox" id="g3-bg"> सादा background मैं ख़ुद हटाऊँ (सिर्फ़ एक-रंग के background पर; वरना बंद रखें — server का AI हटाएगा)</label></div>
    <div class="field"><label>Model का नाम</label><input id="g3-title" placeholder="जैसे: Sunil character"></div>
    <button class="btn primary" id="g3-go" disabled>🧊 3D बनाएँ</button>
    <div class="tl-st" id="g3-st"></div>
  </div><div class="tl-box" id="g3-models"></div></div>`;
}
export function glbBind(c) {
  ctx = c; ensureCss();
  let file = null;
  const st = (m, err) => { const e = $("#g3-st"); if (e) { e.textContent = m || ""; e.classList.toggle("err", !!err); } };
  const drop = $("#g3-drop"), inp = $("#g3-file");
  let img = null, sel = null; const cv = () => $("#g3-cv");
  const draw = () => { const c = cv(); if (!c || !img) return; const W = Math.min(520, img.naturalWidth), k = W / img.naturalWidth; c.width = W; c.height = Math.round(img.naturalHeight * k); c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    const el = $("#g3-sel"); if (sel) { Object.assign(el.style, { left: sel.x + "px", top: sel.y + "px", width: sel.w + "px", height: sel.h + "px" }); el.hidden = false; } else el.hidden = true; };
  const pick = (f) => { if (!f) return; file = f; sel = null; $("#g3-name").textContent = f.name; $("#g3-go").disabled = false; if (!$("#g3-title").value) $("#g3-title").value = f.name.replace(/\.[^.]+$/, "");
    const im = new Image(); im.onload = () => { img = im; $("#g3-cropbox").hidden = false; draw(); if (im.naturalWidth / im.naturalHeight > 1.5) st("⚠ तस्वीर चौड़ी है — शायद कई character/angle हैं। एक पर box खींचें, वरना 3D ख़राब बनेगा।", true); else st(""); }; im.onerror = () => st("यह तस्वीर खुल नहीं पाई", true); im.src = URL.createObjectURL(f); };
  { const box = $("#g3-crop"); let d0 = null;
    box.onpointerdown = (e) => { const r = cv().getBoundingClientRect(); d0 = { x: e.clientX - r.left, y: e.clientY - r.top }; sel = null; box.setPointerCapture(e.pointerId); };
    box.onpointermove = (e) => { if (!d0) return; const r = cv().getBoundingClientRect(); const x = Math.max(0, Math.min(r.width, e.clientX - r.left)), y = Math.max(0, Math.min(r.height, e.clientY - r.top)); sel = { x: Math.min(d0.x, x), y: Math.min(d0.y, y), w: Math.abs(x - d0.x), h: Math.abs(y - d0.y) }; draw(); };
    box.onpointerup = () => { d0 = null; if (sel && (sel.w < 20 || sel.h < 20)) { sel = null; draw(); } }; }
  // crop → (optional) remove a plain background by flood-filling from the edges → centred on a transparent square
  const prepared = () => new Promise((res, rej) => {
    const c = cv(), k = img.naturalWidth / c.width; const r = sel ? { x: sel.x * k, y: sel.y * k, w: sel.w * k, h: sel.h * k } : { x: 0, y: 0, w: img.naturalWidth, h: img.naturalHeight };
    const sc = Math.min(1, 1024 / Math.max(r.w, r.h)); const w = Math.max(8, Math.round(r.w * sc)), h = Math.max(8, Math.round(r.h * sc));
    const a = document.createElement("canvas"); a.width = w; a.height = h; const g = a.getContext("2d", { willReadFrequently: true }); g.drawImage(img, r.x, r.y, r.w, r.h, 0, 0, w, h);
    if ($("#g3-bg").checked) {
      const D = g.getImageData(0, 0, w, h), px = D.data; const at = (x, y) => (y * w + x) * 4;
      const corners = [at(0, 0), at(w - 1, 0), at(0, h - 1), at(w - 1, h - 1)]; const bgc = [0, 1, 2].map((i) => corners.reduce((s2, o) => s2 + px[o + i], 0) / 4);
      const near = (o) => px[o + 3] < 10 || (Math.abs(px[o] - bgc[0]) + Math.abs(px[o + 1] - bgc[1]) + Math.abs(px[o + 2] - bgc[2])) < 60;
      const seen = new Uint8Array(w * h), q = []; const push = (x, y) => { const i = y * w + x; if (!seen[i] && near(i * 4)) { seen[i] = 1; q.push(i); } };
      for (let x = 0; x < w; x++) { push(x, 0); push(x, h - 1); } for (let y = 0; y < h; y++) { push(0, y); push(w - 1, y); }
      while (q.length) { const i = q.pop(), x = i % w, y = (i / w) | 0; px[i * 4 + 3] = 0; if (x > 0) push(x - 1, y); if (x < w - 1) push(x + 1, y); if (y > 0) push(x, y - 1); if (y < h - 1) push(x, y + 1); }
      let left = 0; for (let i = 0; i < w * h; i++) if (px[i * 4 + 3]) left++; if (left < w * h * 0.04) return rej(new Error("background हटाने पर कुछ नहीं बचा — «background हटाएँ» बंद करके देखें"));
      g.putImageData(D, 0, 0);
    }
    if (!$("#g3-bg").checked) return a.toBlob((b) => (b ? res(b) : rej(new Error("तस्वीर तैयार नहीं हुई"))), "image/png"); // opaque crop → the server's AI removes the background
    const S = Math.round(Math.max(w, h) * 1.2), o = document.createElement("canvas"); o.width = o.height = S; o.getContext("2d").drawImage(a, (S - w) / 2, (S - h) / 2);
    o.toBlob((b) => (b ? res(b) : rej(new Error("तस्वीर तैयार नहीं हुई"))), "image/png");
  });
  drop.onclick = () => inp.click(); inp.onchange = () => pick(inp.files[0]);
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); }; drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); pick(e.dataTransfer.files[0]); };
  let panel = null; const list = () => panel?.refresh();
  import("./models3d.js").then((M) => M.mountModels($("#g3-models"), ctx)).then((p) => { panel = p; }).catch(() => {});
  ctx.api("GET", "/triposr/health").then((h) => { if (h.status !== "ok") st("⚠ TripoSR service बंद है (port 8090) — server पर `systemctl status triposr` देखें", true); }).catch(() => {});
  $("#g3-go").onclick = async () => {
    if (!file) return; const btn = $("#g3-go"); btn.disabled = true; st("भेज रहे हैं…");
    try {
      const blob = await prepared();
      const fd = new FormData(); fd.append("file", blob, "object.png"); fd.append("name", $("#g3-title").value.trim() || file.name);
      const r = await fetch("/api/triposr/generate", { method: "POST", headers: { authorization: "Bearer " + ctx.S.token }, body: fd });
      const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.error || r.statusText);
      for (let i = 0; i < 400; i++) {
        if (!$("#g3-st")) return; // left the page
        const s = await ctx.api("GET", "/triposr/job/" + d.job_id);
        if (s.status === "done") { st("तैयार ✓ — नीचे list में download करें"); list(); break; }
        if (s.status === "failed") throw new Error(s.error || "3D नहीं बन पाया");
        st(`3D बन रहा है… ${s.seconds}s (1–3 मिनट लगते हैं, page खुला रखें)`); await sleep(3000);
      }
    } catch (e) { st(e.message, true); } finally { const b = $("#g3-go"); if (b) b.disabled = false; }
  };
}

// ---------------------------------------------------------------- API & Integrations (API keys for other software)
let apiNewKey = null;
export function apiView() {
  const base = location.origin;
  const k = apiNewKey || "YOUR_API_KEY";
  const cu = `curl -X POST ${base}/api/v1/text-to-speech \\\n  -H "Authorization: Bearer ${k}" -H "Content-Type: application/json" \\\n  -d '{"text":"नमस्ते दोस्तों","lang":"hi"}'`;
  const tab = /out|vividora/.test(location.hash.split("?")[1] || "") ? "out" : "in";
  return `<div class="pghead"><div><h1>🔌 API & Keys</h1><p class="muted">दो अलग चीज़ें हैं: <b>बाहर की services की keys</b> (Gemini, Pixabay, fal… — जिन्हें Vividora इस्तेमाल करता है) और <b>Vividora की अपनी API key</b> (जिससे आपका दूसरा software Vividora को चलाता है)।</p></div></div>
  <div class="seg" id="api-tabs" style="margin-bottom:1rem"><button data-apitab="in" class="${tab === "in" ? "on" : ""}">🔑 Services की keys जोड़ें</button><button data-apitab="spend">💰 खर्च</button><button data-apitab="guide">📖 Guide — कौन सा switch क्या करता है</button><button data-apitab="out" class="${tab === "out" ? "on" : ""}">🔌 Vividora की API दें</button></div>
  <div id="api-spend" hidden><div id="sp-box"><p class="small muted">लोड हो रहा है…</p></div></div>
  <div id="api-guide" hidden><div id="gd-box"><p class="small muted">लोड हो रहा है…</p></div></div>
  <div id="api-in" ${tab === "in" ? "" : "hidden"}><div id="pk-list"><p class="small muted">लोड हो रहा है…</p></div></div>
  <div id="api-out" ${tab === "out" ? "" : "hidden"}><p class="muted small" style="margin:0 0 .8rem">अपने दूसरे software (n8n, Zapier, Make, अपनी app, script) से Vividora चलाएँ — Image→3D, Text→Voice, 3D character video, documentary। Key सिर्फ़ आपके workspace तक सीमित है।</p>
  <div class="tl-wrap"><div class="tl-box">
    <h3 style="margin:0 0 .4rem">नई API key</h3>
    <div class="tl-row"><div class="field"><label>नाम (जैसे n8n, my-app)</label><input id="ak-name" maxlength="60" placeholder="n8n"></div>
      <div class="field"><label>अनुमति</label><select id="ak-role"><option value="editor">editor — बना भी सकती है</option><option value="viewer">viewer — सिर्फ़ देख/download</option></select></div></div>
    <button class="btn primary" id="ak-go">🔑 Key बनाएँ</button>
    <div id="ak-new"></div>
    <h3 style="margin:1rem 0 .4rem">आपकी keys</h3><div id="ak-list"><p class="small muted">लोड हो रहा है…</p></div>
  </div><div class="tl-box">
    <h3 style="margin:0 0 .4rem">इस्तेमाल कैसे करें</h3>
    <p class="small">Base URL: <code>${esc(base)}/api/v1</code></p>
    <p class="small">हर request में header: <code>Authorization: Bearer vk_…</code></p>
    <pre id="ak-curl" style="white-space:pre-wrap;word-break:break-all;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:.6rem;font-size:.78rem">${esc(cu)}</pre>
    <button class="btn small quiet" id="ak-copycurl">📋 Example copy</button>
    <p class="small" style="margin-top:.8rem">काम में 1–3 मिनट लग सकते हैं: response में <code>job_id</code> मिलता है → <code>GET /v1/jobs/{job_id}</code> से देखें → <code>done</code> होने पर <code>file.download</code> से फ़ाइल लें। या <code>callback_url</code> दें, तो खत्म होते ही आपके URL पर खबर आएगी।</p>
    <p class="small"><a href="/api/v1/docs" target="_blank" rel="noopener">📖 पूरा API docs</a> · <a href="/api/v1/openapi.json" target="_blank" rel="noopener">openapi.json</a> (Postman / n8n में import करें)</p>
    <p class="small muted">⚠ Key password जैसी है — किसी को दिखाएँ नहीं, screenshot में न आने दें। लीक हो जाए तो यहीं से हटा दें।</p>
  </div></div></div>`;
}
// 💰 this month's paid-service spending (server: spend.py + engine/meter.py)
async function spendLoad() {
  const box = $("#sp-box"); if (!box) return; let s; try { s = await ctx.api("GET", "/spend"); } catch (e) { box.innerHTML = `<p class="small err">${esc(e.message)}</p>`; return; }
  const usd = (v) => "$" + (+v || 0).toFixed(+v >= 10 ? 2 : 3); const pct = s.cap ? Math.min(100, s.total / s.cap * 100) : 0; const over = s.cap != null && s.left <= 0;
  box.innerHTML = `<div class="tl-box" style="margin-bottom:.8rem"><h3 style="margin:0 0 .4rem">इस महीने (${esc(s.period)})</h3>
      <p style="font-size:1.6rem;margin:.2rem 0"><b>${usd(s.total)}</b> <span class="small muted">${s.cap == null ? "· कोई सीमा नहीं लगाई" : `/ ${usd(s.cap)} की सीमा`}</span></p>
      ${s.cap != null ? `<div class="progress" style="height:8px"><i style="width:${pct.toFixed(1)}%;${over ? "background:var(--rose)" : ""}"></i></div><p class="small ${over ? "err" : "muted"}" style="margin:.4rem 0 0">${over ? "⛔ सीमा पूरी — सारे paid काम रुके हैं: cloud transcript, fal.ai / RunPod / ElevenLabs की आवाज़ें, AI music, AI video। मुफ़्त काम (यह server, SRT, Cloudflare images) चलते रहेंगे।" : `बचा: <b>${usd(s.left)}</b>`}</p>` : `<p class="small muted">सीमा लगाने के लिए “Services की keys” tab → सबसे ऊपर <b>महीने की खर्च-सीमा</b>।</p>`}
      <p class="small muted" style="margin-top:.5rem">ये <b>अंदाज़े</b> हैं (हर काम × नीचे की दर) — असली bill fal.ai / RunPod / ElevenLabs की site पर देखें। कोई भी cloud service तभी चलती है जब कोई काम उसे बुलाए; बीच में कुछ चालू नहीं रहता।</p></div>
    ${s.by_service ? `<div class="tl-wrap"><div class="tl-box"><h3 style="margin:0 0 .4rem">किस पर कितना</h3>${s.by_service.length ? s.by_service.map((x) => `<div class="pk-row"><div class="pk-head"><b>${esc(x.label)}</b><span class="grow"></span><b>${usd(x.usd)}</b></div><p class="small muted" style="margin:.1rem 0 0">${x.calls} बार · ${x.units} ${esc(x.unit)}</p></div>`).join("") : `<p class="small muted">इस महीने अभी कोई paid काम नहीं हुआ।</p>`}
        <h3 style="margin:1rem 0 .4rem">दरें (अंदाज़ा)</h3>${s.prices.map((p) => `<p class="small" style="margin:.15rem 0">${esc(p.label)}: <b>${usd(p.usd)}</b> / ${esc(p.unit)} <span class="muted">· ${esc(p.env)}</span></p>`).join("")}
        <p class="small muted">दर बदलनी हो तो server की <code>.env</code> में ऊपर लिखा नाम डालें (जैसे <code>PRICE_FAL_WHISPER_MIN=0.004</code>)।</p>
        ${s.months.length > 1 ? `<h3 style="margin:1rem 0 .4rem">पिछले महीने</h3>${s.months.map((m) => `<p class="small" style="margin:.15rem 0">${esc(m.period)}: <b>${usd(m.usd)}</b></p>`).join("")}` : ""}</div>
      <div class="tl-box"><h3 style="margin:0 0 .4rem">हाल के काम</h3>${s.recent.length ? s.recent.map((r) => `<div class="pk-row"><div class="pk-head"><span class="small">${esc(r.label)}</span><span class="grow"></span><b class="small">${usd(r.usd)}</b></div><p class="small muted" style="margin:.1rem 0 0">${esc(new Date(r.ts).toLocaleString())} · ${esc(r.what || "")}</p></div>`).join("") : `<p class="small muted">अभी कुछ नहीं।</p>`}</div></div>` : ""}`;
}
// 📖 the admin guide (server: adminguide.py — the same text as docs/admin-guide.md)
async function guideLoad() {
  const box = $("#gd-box"); if (!box || box.dataset.done) return; let g; try { g = await ctx.api("GET", "/providers/guide"); } catch (e) { box.innerHTML = `<p class="small err">${esc(e.message)}</p>`; return; }
  box.dataset.done = "1"; let grp = "";
  box.innerHTML = `<div class="note" style="margin-bottom:.8rem">यह पूरा हिसाब है: <b>कौन सा काम कहाँ चलता है</b>, <b>हर key / switch से क्या बदलता है</b>, और <b>पहली बार कैसे जाँचें</b>। दाम अंदाज़े हैं — असली bill हर service की अपनी site पर। कोई भी cloud service तभी पैसा लेती है जब कोई काम उसे बुलाए; बीच में कुछ चालू नहीं रहता। यही guide फ़ाइल में भी है: <code>docs/admin-guide.md</code>।</div>
    <div class="tl-box" style="margin-bottom:.8rem"><h3 style="margin:0 0 .5rem">1 · कौन सा काम कहाँ चलता है</h3>${g.tasks.map((t) => `<h4 style="margin:.9rem 0 .3rem">${esc(t.task)}</h4><div style="overflow-x:auto"><table class="gd-tab"><thead><tr><th>कहाँ</th><th>क्या चाहिए</th><th>कौन सा switch / कहाँ चुनें</th><th>दाम</th></tr></thead><tbody>${t.options.map((o) => `<tr><td><b>${esc(o.where)}</b></td><td>${esc(o.need)}</td><td>${esc(o.switch)}</td><td>${esc(o.cost)}</td></tr>`).join("")}</tbody></table></div>`).join("")}</div>
    <div class="tl-box" style="margin-bottom:.8rem"><h3 style="margin:0 0 .5rem">2 · हर key और switch — क्या करने से क्या होगा</h3>${g.rows.map((r) => `${r.group !== grp ? ((grp = r.group), `<h4 style="margin:1rem 0 .3rem;opacity:.75">${esc(r.group)}</h4>`) : ""}<div class="pk-row"><div class="pk-head"><b>${esc(r.label)}</b><span class="pk-chip">${r.kind === "switch" ? "switch" : r.kind === "number" ? "संख्या" : "key"}</span><span class="small muted">${esc(r.env)}</span></div>${r.states.map((h) => `<p class="small" style="margin:.2rem 0"><b>${esc(h.state)}:</b> ${esc(h.effect)}</p>`).join("")}</div>`).join("")}</div>
    <div class="tl-box" style="margin-bottom:.8rem"><h3 style="margin:0 0 .3rem">3 · Server की <code>.env</code> फ़ाइल वाले switch</h3><p class="small muted">ये dashboard में नहीं हैं — server पर <code>/srv/studio/vividora/.env</code> में line जोड़कर <code>docker compose --profile tunnel up -d --build</code> चलाना होता है।</p>${g.server.map((x) => `<div class="pk-row"><div class="pk-head"><code>${esc(x.name)}</code></div><p class="small" style="margin:.2rem 0">${esc(x.does)}</p><p class="small muted" style="margin:.1rem 0">${esc(x.note)}</p></div>`).join("")}</div>
    <div class="tl-box"><h3 style="margin:0 0 .5rem">4 · पहली बार जाँचने का क्रम</h3><ol style="margin:0;padding-left:1.2rem">${g.checklist.map((c) => `<li class="small" style="margin:.3rem 0">${esc(c)}</li>`).join("")}</ol></div>`;
}
// outside-service keys (server: provkeys.py) — saved encrypted, used at once, no server restart
async function provLoad() {
  const box = $("#pk-list"); if (!box) return;
  let r; try { r = await ctx.api("GET", "/providers"); } catch (e) { box.innerHTML = `<p class="small err">${esc(e.message)}</p>`; return; }
  const can = r.can_edit; const groups = Object.keys(r.groups);
  const n = r.providers.filter((x) => x.set).length;
  box.innerHTML = `<div class="note ${can ? "" : "warn"}" style="margin-bottom:.8rem">${can ? `यहाँ key चिपकाकर <b>Save</b> दबाएँ — तुरंत काम करने लगती है, server restart या <code>.env</code> खोलने की ज़रूरत नहीं। Key database में <b>encrypt</b> होकर रहती है और दोबारा पूरी कभी नहीं दिखती (सिर्फ़ आख़िरी 4 अक्षर)। <code>.env</code> में पहले से रखी key भी चलती रहती है; यहाँ डाली key उससे ऊपर मानी जाती है।` : `ये keys सिर्फ़ server के मालिक (admin) बदल सकते हैं। नीचे दिखता है कि कौन-सी service चालू है।`} <b>${n}/${r.providers.length}</b> चालू।</div>`
    + groups.map((g) => { const rows = r.providers.filter((x) => x.group === g); if (!rows.length) return "";
      return `<div class="tl-box" style="margin-bottom:.8rem"><h3 style="margin:0 0 .5rem">${esc(r.groups[g])}</h3>${rows.map((x) => `<div class="pk-row" data-pk="${esc(x.env)}">
        <div class="pk-head"><b>${esc(x.label)}</b> ${x.set ? `<span class="pk-chip ok">✓ ${x.choices || x.number ? "set" : "चालू"}${x.shown ? ` · <code>${esc(x.choices ? (x.choices[x.shown] || x.shown).split(" — ")[0] : x.shown)}</code>` : ""}${x.source === "env" ? " · .env से" : x.source === "dashboard" ? " · यहाँ से" : ""}</span>` : `<span class="pk-chip">${x.choices ? "default: यह server" : x.number ? "खाली" : "नहीं डाली"}</span>`}
          ${x.link ? `<a class="small" href="${esc(x.link)}" target="_blank" rel="noopener">key कहाँ मिलेगी ↗</a>` : ""}</div>
        <p class="small muted" style="margin:.15rem 0 .4rem">${esc(x.use)} <span style="opacity:.6">· ${esc(x.env)}</span></p>
        ${(x.help || []).length ? `<details class="pk-help"><summary class="small">ℹ️ इससे क्या होगा</summary>${x.help.map((h) => `<p class="small" style="margin:.2rem 0"><b>${esc(h.state)}:</b> ${esc(h.effect)}</p>`).join("")}</details>` : ""}
        ${can ? `<div class="pk-edit">${x.choices ? `<select>${Object.entries(x.choices).map(([k, l]) => `<option value="${esc(k)}" ${(x.shown || "local") === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`
          : `<input type="${x.secret ? "password" : x.number ? "number" : "text"}" ${x.number ? `min="${x.number[0]}" max="${x.number[1]}" step="any"` : ""} autocomplete="off" spellcheck="false" placeholder="${esc(x.placeholder || (x.number ? "" : x.set ? "नई key चिपकाएँ (बदलने के लिए)" : "key यहाँ चिपकाएँ"))}" value="${x.number && x.shown ? esc(x.shown) : ""}">`}<button class="btn small primary" data-pksave>Save</button>${x.source === "dashboard" ? `<button class="btn small quiet" data-pkdel title="यहाँ डाली key हटाएँ (.env वाली, अगर है, वापस चलने लगेगी)">हटाएँ</button>` : ""}</div>` : ""}
      </div>`).join("")}</div>`; }).join("");
  if (!can) return;
  box.querySelectorAll("[data-pk]").forEach((row) => { const env = row.dataset.pk; const inp = row.querySelector("input,select"); const sv = row.querySelector("[data-pksave]"); const dl = row.querySelector("[data-pkdel]");
    const save = async () => { const v = inp.value.trim(); if (!v) return ctx.toast("पहले value लिखें / चुनें"); sv.disabled = true;
      try { await ctx.api("PUT", "/providers/" + env, { value: v }); ctx.toast("✅ Save हो गई — अब से इस्तेमाल होगी"); await provLoad(); } catch (e) { ctx.toast(e.message); sv.disabled = false; } };
    sv.onclick = save; inp.onkeydown = (e) => { if (e.key === "Enter") save(); };
    if (dl) dl.onclick = async () => { if (dl.dataset.sure !== "1") { dl.dataset.sure = "1"; dl.textContent = "पक्का? (दोबारा दबाएँ)"; return; } try { await ctx.api("DELETE", "/providers/" + env); ctx.toast("हटा दी"); await provLoad(); } catch (e) { ctx.toast(e.message); } }; });
}
export function apiBind(c) {
  ctx = c; ensureCss();
  const fmt = (t) => t ? new Date(t).toLocaleString() : "अभी तक नहीं";
  const copy = async (txt, msg) => { try { await navigator.clipboard.writeText(txt); ctx.toast(msg || "Copy हो गया"); } catch { ctx.toast("Copy नहीं हुआ — खुद select करके copy करें"); } };
  const loadList = async () => {
    const box = $("#ak-list"); if (!box) return;
    try {
      const r = await ctx.api("GET", "/keys");
      box.innerHTML = r.keys.length ? r.keys.map((k) => `<div class="tl-item" style="margin-bottom:.4rem"><b>${esc(k.name)}</b><span class="small muted"><code>${esc(k.prefix)}…</code> · ${esc(k.role)} · आख़िरी इस्तेमाल: ${esc(fmt(k.last_used_at))}</span><button class="btn small quiet" data-rev="${esc(k.id)}">🗑 हटाएँ</button></div>`).join("") : `<p class="small muted">अभी कोई key नहीं।</p>`;
      box.querySelectorAll("[data-rev]").forEach((b) => (b.onclick = async () => {
        if (b.dataset.sure !== "1") { b.dataset.sure = "1"; b.textContent = "पक्का हटाएँ? (दोबारा दबाएँ)"; return; }
        try { await ctx.api("DELETE", "/keys/" + b.dataset.rev); ctx.toast("Key हट गई"); loadList(); } catch (e) { ctx.toast(e.message); }
      }));
    } catch (e) { box.innerHTML = `<p class="small err">${esc(e.message)}</p>`; }
  };
  loadList(); provLoad();
  document.querySelectorAll("[data-apitab]").forEach((b) => (b.onclick = () => { const t = b.dataset.apitab; document.querySelectorAll("[data-apitab]").forEach((x) => x.classList.toggle("on", x === b)); $("#api-in").hidden = t !== "in"; $("#api-out").hidden = t !== "out"; $("#api-spend").hidden = t !== "spend"; $("#api-guide").hidden = t !== "guide"; if (t === "spend") spendLoad(); if (t === "guide") guideLoad(); }));
  const cc = $("#ak-copycurl"); if (cc) cc.onclick = () => copy($("#ak-curl").textContent, "Example copy हो गया");
  const go = $("#ak-go");
  if (go) go.onclick = async () => {
    const name = $("#ak-name").value.trim();
    if (!name) { ctx.toast("पहले key का नाम लिखें"); return; }
    go.disabled = true;
    try {
      const r = await ctx.api("POST", "/keys", { name, role: $("#ak-role").value });
      apiNewKey = r.key;
      $("#ak-new").innerHTML = `<div class="tl-item" style="margin-top:.6rem;border-color:#ffb020"><b>✅ आपकी key — अभी copy कर लें, दोबारा नहीं दिखेगी</b><code id="ak-key" style="word-break:break-all;user-select:all">${esc(r.key)}</code><button class="btn small" id="ak-copy">📋 Key copy करें</button></div>`;
      $("#ak-copy").onclick = () => copy(r.key, "Key copy हो गई");
      $("#ak-curl").textContent = `curl -X POST ${location.origin}/api/v1/text-to-speech \\\n  -H "Authorization: Bearer ${r.key}" -H "Content-Type: application/json" \\\n  -d '{"text":"नमस्ते दोस्तों","lang":"hi"}'`;
      $("#ak-name").value = ""; loadList();
    } catch (e) { ctx.toast(e.message); } finally { go.disabled = false; }
  };
}

// ---------------------------------------------------------------- Auto Documentary
let docState = { title: "", scenes: [], job: null };
export function docView() {
  return `<div class="pghead"><div><h1>🎬 Auto Documentary</h1><p class="muted">Topic या अपनी script दें → scenes → narration + तस्वीरें + sound → पूरा वीडियो (Library में)</p></div></div>
  <div class="tl-wrap"><div class="tl-box">
    <h3 style="margin:0 0 .4rem">1. Topic या script</h3>
    <div class="field"><label>Topic (AI scenes बनाएगा — .env में GEMINI_API_KEY / ANTHROPIC_API_KEY चाहिए)</label><input id="dc-topic" maxlength="300" placeholder="जैसे: हिमालय कैसे बना"></div>
    <div class="tl-row"><div class="field"><label>कितने मिनट</label><select id="dc-min"><option>2</option><option selected>3</option><option>5</option><option>8</option></select></div>
      <div class="field"><label>भाषा</label><select id="dc-lang"><option value="hi">हिन्दी</option><option value="en">English</option><option value="hinglish">Hinglish</option></select></div></div>
    <div class="field"><label><input type="checkbox" id="dc-ground" checked> Wikipedia से facts लेकर लिखो (नाम/तारीख़ें सही रहें; sources description में जुड़ेंगे)</label></div>
    <button class="btn primary" id="dc-plan">✨ Scenes बनाओ</button>
    <div class="field" style="margin-top:.8rem"><label>या अपनी script (खाली लाइन = नया scene)</label><textarea id="dc-script" rows="5" placeholder="पहला scene…\n\nदूसरा scene…"></textarea></div>
    <button class="btn" id="dc-plan2">📝 Script से scenes</button>
  </div><div class="tl-box">
    <h3 style="margin:0 0 .4rem">2. Scenes जाँचें और बदलें</h3>
    <div id="dc-scenes"><p class="small muted">पहले ऊपर से scenes बनाएँ।</p></div>
    <div id="dc-opts" hidden>
      <div class="tl-row"><div class="field"><label>आवाज़</label><select id="dc-voice"></select></div>
        <div class="field"><label>Shape</label><select id="dc-or"><option value="landscape">Landscape 16:9 (YouTube)</option><option value="portrait">Portrait 9:16 (Reels/Shorts)</option><option value="square">Square 1:1</option></select></div></div>
      <div class="tl-row"><div class="field"><label>Background music (वैकल्पिक)</label><select id="dc-music"><option value="">— कोई नहीं —</option><option value="auto">🎲 Auto — script के mood से (सिर्फ़ safe tracks)</option></select></div>
        <div class="field"><label><input type="checkbox" id="dc-cap" checked> Captions (नीचे लिखा हुआ text)</label></div></div>
      <div class="field"><label>Music की आवाज़ <input type="range" id="dc-mvol" min="0.04" max="0.4" step="0.02" value="0.14" style="vertical-align:middle"> <span class="small muted">(आवाज़ के नीचे अपने-आप दबती है)</span></label></div>
      <div class="field"><label><input type="checkbox" id="dc-ai" checked> AI से तस्वीरें बनाओ (Library में match न मिले तो) <span class="muted" id="dc-aiinfo"></span></label> <span class="small muted" id="dc-vinfo"></span></div>
      <p class="small muted">तस्वीरें: पहले आपकी Library (नाम/tags से मिलान), फिर AI-generated (GPU API), फिर Pixabay (अगर PIXABAY_API_KEY है), नहीं तो title card।</p>
      <button class="btn primary" id="dc-build">🎬 Documentary बनाओ</button>
      <div class="tl-row" style="margin-top:.6rem"><div class="field"><label>Draft (बाद में जारी रखने के लिए)</label><select id="dc-drafts"><option value="">— सेव किए हुए —</option></select></div>
        <div style="display:flex;gap:.3rem;align-items:flex-end;flex-wrap:wrap"><button class="btn small" id="dc-dsave">💾 सेव</button><button class="btn small" id="dc-dload">📂 खोलें</button><button class="btn small quiet" id="dc-ddel">🗑</button></div></div>
      <div class="tl-row" style="margin-top:.4rem"><button class="btn small" id="dc-shorts-plan">✂ Shorts/Reels निकालो</button></div>
      <div id="dc-shorts"></div>
    </div>
    <div id="dc-status"></div>
    <div id="dc-yt"></div>
    <div id="dc-ig"></div>
  </div><div class="tl-box">
    <h3 style="margin:0 0 .4rem">3. Series (कई episodes एक साथ)</h3>
    <div class="field"><label>Series का topic (AI key चाहिए)</label><input id="sr-topic" maxlength="200" placeholder="जैसे: हिमालय की पूरी कहानी"></div>
    <div class="tl-row"><div class="field"><label>Episodes</label><select id="sr-n"><option>3</option><option selected>4</option><option>5</option><option>6</option><option>8</option></select></div></div>
    <button class="btn" id="sr-plan">📺 Episodes की list बनाओ</button>
    <div id="sr-eps"></div>
    <div id="sr-status"></div>
  </div><div class="tl-box">
    <h3 style="margin:0 0 .4rem">4. Instagram analysis</h3>
    <p class="small muted">आपके connected Instagram account की पिछली 12 posts: views, reach, saves, shares, औसत watch time — और क्या बेहतर चला।</p>
    <div class="tl-row"><div class="field"><label>Account</label><select id="ia-conn"><option value="">— connection नहीं मिला —</option></select></div></div>
    <button class="btn" id="ia-go">📊 Analyse करो</button>
    <div id="ia-out"></div>
  </div></div>`;
}
export function docBind(c) {
  ctx = c; ensureCss();
  const st = (h, err) => { const b = $("#dc-status"); if (b) b.innerHTML = `<p class="small ${err ? "err" : ""}" style="margin-top:.6rem">${h}</p>`; };
  const draw = () => {
    const box = $("#dc-scenes"); if (!box) return;
    if (!docState.scenes.length) { box.innerHTML = `<p class="small muted">पहले ऊपर से scenes बनाएँ।</p>`; $("#dc-opts").hidden = true; return; }
    $("#dc-opts").hidden = false;
    box.innerHTML = `<div class="field"><label>Title</label><input id="dc-title" value="${esc(docState.title)}" maxlength="100"></div>` + docState.scenes.map((s, i) => `<div class="tl-item" style="display:block;margin-bottom:.5rem">
      <b>Scene ${i + 1}</b> <span style="float:right"><button class="btn small quiet" data-up="${i}" title="ऊपर">▲</button> <button class="btn small quiet" data-dn="${i}" title="नीचे">▼</button> <button class="btn small quiet" data-dup="${i}" title="copy">⧉</button> <button class="btn small quiet" data-del="${i}">🗑</button></span>
      <textarea data-n="${i}" rows="3" style="width:100%">${esc(s.narration)}</textarea>
      <label class="small muted" style="display:block;margin-top:.3rem">कम से कम इतने सेकंड दिखाएँ (0 = आवाज़ जितना) <input data-h="${i}" type="number" min="0" max="30" step="0.5" value="${s.hold || 0}" style="width:5rem"></label>
      <label class="small" style="display:block;margin-top:.3rem" title="हर clip पर fal.ai का पैसा लगता है"><input type="checkbox" data-mo="${i}" ${s.motion ? "checked" : ""}> 🎥 इस scene की तस्वीर को AI video बनाओ (पैसे वाला, वैकल्पिक)</label>
      <input data-v="${i}" value="${esc(s.visual || "")}" placeholder="तस्वीर के English keywords (जैसे aerial himalaya mountains)" style="width:100%;margin-top:.3rem">
      <select data-l="${i}" style="width:100%;margin-top:.3rem"><option value="">तस्वीर: अपने-आप (Library → Pixabay → title card)</option>${(docState.lib || []).map((m) => `<option value="${esc(m.id)}" ${s.library_id === m.id ? "selected" : ""}>${m.kind === "image" ? "🖼" : "🎞"} ${esc(m.name)}</option>`).join("")}</select>${!s.library_id && docState.pv && docState.pv[i] ? `<div class="small muted">${docState.pv[i].library_id ? "✓ Library से मिलेगी: " + esc(docState.pv[i].name) : "Library में match नहीं — Pixabay या title card"}</div>` : ""}
    </div>`).join("");
    box.querySelectorAll("[data-n]").forEach((t) => (t.oninput = () => (docState.scenes[+t.dataset.n].narration = t.value)));
    box.querySelectorAll("[data-v]").forEach((t) => (t.oninput = () => (docState.scenes[+t.dataset.v].visual = t.value)));
    box.querySelectorAll("[data-l]").forEach((t) => (t.onchange = () => { const sc = docState.scenes[+t.dataset.l]; if (t.value) sc.library_id = t.value; else delete sc.library_id; }));
    const mv = (a, b) => { const sc = docState.scenes; if (b < 0 || b >= sc.length) return; [sc[a], sc[b]] = [sc[b], sc[a]]; if (docState.pv) docState.pv = null; draw(); };
    box.querySelectorAll("[data-up]").forEach((b) => (b.onclick = () => mv(+b.dataset.up, +b.dataset.up - 1)));
    box.querySelectorAll("[data-dn]").forEach((b) => (b.onclick = () => mv(+b.dataset.dn, +b.dataset.dn + 1)));
    box.querySelectorAll("[data-dup]").forEach((b) => (b.onclick = () => { docState.scenes.splice(+b.dataset.dup + 1, 0, { ...docState.scenes[+b.dataset.dup] }); docState.pv = null; draw(); }));
    box.querySelectorAll("[data-mo]").forEach((t) => (t.onchange = () => { if (t.checked) docState.scenes[+t.dataset.mo].motion = true; else delete docState.scenes[+t.dataset.mo].motion; preview(); }));
    box.querySelectorAll("[data-h]").forEach((t) => (t.oninput = () => { const v = Math.max(0, Math.min(30, +t.value || 0)); if (v) docState.scenes[+t.dataset.h].hold = v; else delete docState.scenes[+t.dataset.h].hold; }));
    box.querySelectorAll("[data-del]").forEach((b) => (b.onclick = () => { docState.scenes.splice(+b.dataset.del, 1); draw(); }));
    const ti = $("#dc-title"); if (ti) ti.oninput = () => (docState.title = ti.value);
  };
  ctx.api("GET", "/v1/voices").then((r) => {
    const sel = $("#dc-voice"); if (!sel) return;
    const safe = (v) => v.engine === "kokoro" || v.engine === "parler";
    sel.innerHTML = r.voices.map((v) => `<option value="${esc(v.id)}">${esc(v.name || v.id)}${safe(v) ? "" : v.engine === "voicestudio" ? " ⚠ सिर्फ़ निजी इस्तेमाल" : ""}</option>`).join("");
    const pref = r.voices.find((v) => safe(v) && v.lang === "hi") || r.voices.find(safe); if (pref) sel.value = pref.id;
  }).catch(() => {});
  ctx.api("GET", "/library?kind=music").then((r) => { const sel = $("#dc-music"); if (!sel) return; const items = Array.isArray(r) ? r : (r.items || []);
    sel.innerHTML += items.slice(0, 60).map((m) => `<option value="${esc(m.id)}">${/non-commercial|-nc\b/i.test((m.license || "") + " " + (m.tags || "")) ? "⚠ NC · " : ""}${esc(m.name)}</option>`).join(""); }).catch(() => {});
  Promise.all(["image", "broll"].map((k) => ctx.api("GET", "/library?kind=" + k).catch(() => []))).then((rs) => {
    docState.lib = rs.flatMap((r) => (Array.isArray(r) ? r : (r.items || []))).filter((m) => !(m.meta && m.meta.alpha)).slice(0, 150); if (docState.scenes.length) draw(); });
  const preview = async () => {
    try {
      const r = await ctx.api("POST", "/documentary/preview", { scenes: docState.scenes });
      docState.pv = r.matches; draw();
      const vi = $("#dc-vinfo"); if (vi) vi.textContent = r.video_provider ? `(AI video: ${r.video_provider} चालू)` : "(AI video बंद — .env में FAL_KEY डालें)";
      if (vi && r.video_clips) vi.textContent += ` · इस film में ${r.video_clips} AI clip${r.video_estimate_usd != null ? ` ≈ $${r.video_estimate_usd}` : " (कीमत जानने के लिए .env में AI_VIDEO_PRICE_PER_SEC डालें)"}`;
      const inf = $("#dc-aiinfo"); if (inf) inf.textContent = r.ai_provider ? `(${r.ai_provider} GPU)` : "— .env में CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN या HF_TOKEN डालें";
    } catch { /* preview is optional */ }
  };
  const plan = async (body, btn) => {
    btn.disabled = true; st("scenes बन रहे हैं… (AI 20–60 सेकंड ले सकता है)");
    try { const r = await ctx.api("POST", "/documentary/plan", body); docState = { title: r.title, scenes: r.scenes, sources: r.sources || [], job: null }; draw(); st(`${r.scenes.length} scenes तैयार${(r.sources || []).length ? ` (Wikipedia: ${r.sources.map((x) => esc(x.title)).join(", ")})` : ""} — जाँचकर नीचे से बनाएँ`); preview(); }
    catch (e) { st(esc(e.message), true); } finally { btn.disabled = false; }
  };
  $("#dc-plan").onclick = (e) => { const t = $("#dc-topic").value.trim(); if (t.length < 3) { ctx.toast("पहले topic लिखें"); return; } plan({ topic: t, minutes: +$("#dc-min").value, language: $("#dc-lang").value, ground: $("#dc-ground").checked }, e.target); };
  $("#dc-plan2").onclick = (e) => { const t = $("#dc-script").value.trim(); if (!t) { ctx.toast("पहले script लिखें"); return; } plan({ script: t }, e.target); };
  const opts = () => ({ voice: $("#dc-voice").value, orientation: $("#dc-or").value, lang: $("#dc-lang").value === "en" ? "en" : "hi", music_id: $("#dc-music").value || undefined,
    music_volume: +$("#dc-mvol").value, captions: $("#dc-cap").checked, ai_images: $("#dc-ai").checked });
  const loadDrafts = () => ctx.api("GET", "/documentary/drafts").then((r) => { const sel = $("#dc-drafts"); if (!sel) return;
    sel.innerHTML = `<option value="">— सेव किए हुए —</option>` + r.drafts.map((d) => `<option value="${esc(d.id)}">${esc(d.name)} (${d.scenes} scenes)</option>`).join(""); }).catch(() => {});
  loadDrafts();
  $("#dc-dsave").onclick = async () => {
    try { const r = await ctx.api("POST", "/documentary/drafts", { id: $("#dc-drafts").value || undefined, title: docState.title, scenes: docState.scenes, sources: docState.sources || [], ...opts() });
      await loadDrafts(); $("#dc-drafts").value = r.id; ctx.toast("Draft सेव हो गया"); } catch (e) { ctx.toast(e.message); }
  };
  $("#dc-dload").onclick = async () => {
    const id = $("#dc-drafts").value; if (!id) { ctx.toast("पहले draft चुनें"); return; }
    try { const d = await ctx.api("GET", "/documentary/drafts/" + id); docState = { ...docState, title: d.title, scenes: d.scenes, sources: (d.options || {}).sources || [], pv: null }; draw();
      const o = d.options || {}; if (o.orientation) $("#dc-or").value = o.orientation; if (o.music_volume) $("#dc-mvol").value = o.music_volume; if (o.captions !== undefined) $("#dc-cap").checked = o.captions;
      if (o.ai_images !== undefined) $("#dc-ai").checked = o.ai_images; if (o.voice) $("#dc-voice").value = o.voice; ctx.toast("Draft खुल गया"); preview(); } catch (e) { ctx.toast(e.message); }
  };
  $("#dc-ddel").onclick = async () => { const id = $("#dc-drafts").value; if (!id) return; if (!confirm("यह draft हटाएँ?")) return; await ctx.api("DELETE", "/documentary/drafts/" + id).catch(() => {}); loadDrafts(); };
  const batchHtml = (j) => `<ul class="small" style="padding-left:1.1rem">${(j.items || []).map((r) => `<li>${r.status === "done" ? "✅" : r.status === "failed" ? "❌" : r.status === "running" ? "⏳" : "·"} ${esc(r.title)}${r.error ? " — " + esc(r.error) : ""}</li>`).join("")}</ul>`;
  const pollBatch = async (id, out) => {
    try {
      const j = await ctx.api("GET", "/documentary/" + id);
      if (j.status === "running") { out(`⏳ ${j.progress || 0}% — ${esc(j.message || "")}${batchHtml(j)}`); setTimeout(() => pollBatch(id, out), 3000); return; }
      out(`${j.status === "done" ? "✅ " + esc(j.message || "तैयार") + " — <a href=\"#/library\">Library</a> में देखें" : "❌ " + esc(j.error || "नहीं बन पाया")}${batchHtml(j)}`);
      $("#dc-build") && ($("#dc-build").disabled = false);
    } catch (e) { out(esc(e.message), true); }
  };
  $("#dc-shorts-plan").onclick = async (e) => {
    const box = $("#dc-shorts"); if (!docState.scenes.length) { ctx.toast("पहले scenes बनाएँ"); return; }
    e.target.disabled = true; box.innerHTML = `<p class="small muted">देख रहा हूँ…</p>`;
    try {
      const r = await ctx.api("POST", "/documentary/shorts", { title: docState.title, scenes: docState.scenes, count: 4 });
      box.innerHTML = `<p class="small muted">इन हिस्सों से Shorts (9:16, captions के साथ) बनेंगे — जो चाहिए चुनें:</p>` + r.shorts.map((c, k) =>
        `<label class="small" style="display:block"><input type="checkbox" data-sp="${k}" checked> ${esc(c.title)} — scenes ${c.indices[0] + 1}–${c.indices[c.indices.length - 1] + 1}, ≈${Math.round(c.seconds)} सेकंड</label>`).join("") +
        `<button class="btn primary small" id="dc-shorts-go" style="margin-top:.4rem">✂ चुने हुए Shorts बनाओ</button><div id="dc-shorts-st"></div>`;
      $("#dc-shorts-go").onclick = async (ev) => {
        const pick = [...box.querySelectorAll("[data-sp]")].filter((x) => x.checked).map((x) => +x.dataset.sp); if (!pick.length) { ctx.toast("कम से कम एक चुनें"); return; }
        ev.target.disabled = true; const o = (h, er) => ($("#dc-shorts-st").innerHTML = `<p class="small ${er ? "err" : ""}">${h}</p>`);
        try { const b = await ctx.api("POST", "/documentary/shorts", { title: docState.title, scenes: docState.scenes, count: 4, build: true, pick, ...opts() }); pollBatch(b.job_id, o); }
        catch (er) { o(esc(er.message), true); ev.target.disabled = false; }
      };
    } catch (er) { box.innerHTML = `<p class="small err">${esc(er.message)}</p>`; } finally { e.target.disabled = false; }
  };
  $("#sr-plan").onclick = async (e) => {
    const t = $("#sr-topic").value.trim(); if (t.length < 3) { ctx.toast("पहले series का topic लिखें"); return; }
    e.target.disabled = true; $("#sr-status").innerHTML = `<p class="small muted">episodes सोच रहा हूँ…</p>`;
    try {
      const r = await ctx.api("POST", "/documentary/series", { topic: t, episodes: +$("#sr-n").value, language: $("#dc-lang").value });
      docState.series = r; $("#sr-status").innerHTML = "";
      $("#sr-eps").innerHTML = `<div class="field"><label>Series का नाम</label><input id="sr-name" value="${esc(r.series)}"></div>` + r.episodes.map((x, k) =>
        `<div class="tl-item" style="display:block;margin:.3rem 0"><b>Ep ${k + 1}</b> <input data-et="${k}" value="${esc(x.title)}" style="width:70%"><br><span class="small muted">${esc(x.summary)}</span></div>`).join("") +
        `<p class="small muted">हर episode की scenes AI लिखेगा (ऊपर की भाषा/आवाज़/shape वाली settings के साथ) और बारी-बारी बनाएगा — हर episode में कई मिनट लग सकते हैं।</p><button class="btn primary" id="sr-go">📺 पूरी series बनाओ</button>`;
      $("#sr-eps").querySelectorAll("[data-et]").forEach((i) => (i.oninput = () => (r.episodes[+i.dataset.et].title = i.value)));
      $("#sr-go").onclick = async (ev) => {
        ev.target.disabled = true; const o = (h, er) => ($("#sr-status").innerHTML = `<p class="small ${er ? "err" : ""}">${h}</p>`);
        try { const b = await ctx.api("POST", "/documentary/series", { build: true, series: $("#sr-name").value, episodes: r.episodes, language: $("#dc-lang").value, minutes: +$("#dc-min").value, ground: $("#dc-ground").checked, ...opts() }); pollBatch(b.job_id, o); }
        catch (er) { o(esc(er.message), true); ev.target.disabled = false; }
      };
    } catch (er) { $("#sr-status").innerHTML = `<p class="small err">${esc(er.message)}</p>`; } finally { e.target.disabled = false; }
  };
  const igBox = (j, ig) => {
    const box = $("#dc-ig"); if (!box) return;
    if (!ig.length) { box.innerHTML = ""; return; }
    const cap = `${docState.title || (j.item && j.item.name) || ""}\n\n#documentary #facts${j.ai_used ? "\n(AI-generated visuals)" : ""}`;
    box.innerHTML = `<div class="tl-item" style="display:block;margin-top:.6rem"><b>📸 Instagram Reel</b> <span class="small muted">(Instagram में private draft नहीं होता — यह <b>तुरंत live</b> होता है; 9:16 Short सबसे अच्छा)</span>
      <select id="ig-conn" style="width:100%;margin:.3rem 0">${ig.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join("")}</select>
      <textarea id="ig-cap" rows="4" style="width:100%" maxlength="2200">${esc(cap)}</textarea>
      <label class="small" style="display:block"><input type="checkbox" id="ig-ok"> मैं समझता हूँ कि यह Instagram पर अभी live हो जाएगा</label>
      <button class="btn small primary" id="ig-go">📸 Reel के रूप में post करें</button><div id="ig-st" class="small" style="margin-top:.3rem"></div></div>`;
    $("#ig-go").onclick = async (ev) => {
      if (!$("#ig-ok").checked) { ctx.toast("पहले टिक करें कि यह live होगा"); return; }
      ev.target.disabled = true; const o = (h, er) => ($("#ig-st").innerHTML = `<span class="${er ? "err" : ""}">${h}</span>`);
      try {
        const b = await ctx.api("POST", "/documentary/instagram", { library_id: j.item.id, connection_id: $("#ig-conn").value, caption: $("#ig-cap").value, confirm: true });
        if ((b.warnings || []).length) o("⚠ " + b.warnings.map(esc).join("<br>⚠ "));
        const tick = async () => { const u = await ctx.api("GET", "/documentary/" + b.job_id);
          if (u.status === "running") { o(`⏳ ${u.progress || 0}% ${esc(u.message || "")}`); setTimeout(tick, 4000); return; }
          o(u.status === "done" ? `✅ ${esc(u.message || "")} ${u.url && u.url.startsWith("http") ? `<a href="${esc(u.url)}" target="_blank" rel="noopener">${esc(u.url)}</a>` : ""}` : "❌ " + esc(u.error || "नहीं हुआ"), u.status !== "done");
          ev.target.disabled = false; };
        tick();
      } catch (er) { o(esc(er.message), true); ev.target.disabled = false; }
    };
  };
  const ytBox = async (j) => {
    const box = $("#dc-yt"); if (!box || !j.item) return;
    const r = await ctx.api("GET", "/connections").catch(() => ({ connections: [] }));
    const yt = (r.connections || []).filter((c) => c.platform === "youtube");
    igBox(j, (r.connections || []).filter((c) => c.platform === "instagram"));
    if (!yt.length) { box.innerHTML = `<p class="small muted">YouTube पर भेजने के लिए पहले Dashboard → Connections में channel जोड़ें।</p>`; return; }
    box.innerHTML = `<div class="tl-item" style="display:block;margin-top:.6rem"><b>▶ YouTube पर private draft</b> <span class="small muted">(public नहीं होता — YouTube Studio में देखकर आप ख़ुद publish करें)</span>
      <select id="yt-conn" style="width:100%;margin:.3rem 0">${yt.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join("")}</select>
      <button class="btn small primary" id="yt-go">⬆ Private draft के रूप में upload</button><div id="yt-st" class="small" style="margin-top:.3rem"></div></div>`;
    $("#yt-go").onclick = async (ev) => {
      ev.target.disabled = true; const o = (h, er) => ($("#yt-st").innerHTML = `<span class="${er ? "err" : ""}">${h}</span>`);
      try {
        const b = await ctx.api("POST", "/documentary/youtube", { library_id: j.item.id, connection_id: $("#yt-conn").value, title: docState.title || j.item.name,
          description: ($("#dc-desc") || {}).value || j.description || "", thumbnail_id: j.thumbnail && j.thumbnail.id, synthetic: !!j.ai_used, language: $("#dc-lang").value === "en" ? "en" : "hi" });
        const tick = async () => { const u = await ctx.api("GET", "/documentary/" + b.job_id);
          if (u.status === "running") { o(`⏳ ${u.progress || 0}% ${esc(u.message || "")}`); setTimeout(tick, 3000); return; }
          o(u.status === "done" ? `✅ ${esc(u.message || "तैयार")} ${u.url && u.url.startsWith("http") ? `<a href="${esc(u.url)}" target="_blank" rel="noopener">${esc(u.url)}</a>` : ""}${(u.warnings || []).length ? "<br>⚠ " + u.warnings.map(esc).join("<br>⚠ ") : ""}` : "❌ " + esc(u.error || "नहीं हुआ"), u.status !== "done");
          ev.target.disabled = false; };
        tick();
      } catch (er) { o(esc(er.message), true); ev.target.disabled = false; }
    };
  };
  ctx.api("GET", "/connections").then((r) => { const ig = (r.connections || []).filter((c) => c.platform === "instagram"); const sel = $("#ia-conn"); if (sel && ig.length) sel.innerHTML = ig.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join(""); }).catch(() => {});
  $("#ia-go").onclick = async (e) => {
    const id = $("#ia-conn").value; if (!id) { ctx.toast("पहले Dashboard → Connections में Instagram (Meta) जोड़ें"); return; }
    e.target.disabled = true; $("#ia-out").innerHTML = `<p class="small muted">Instagram से data आ रहा है…</p>`;
    try {
      const r = await ctx.api("GET", "/documentary/instagram/insights?connection_id=" + encodeURIComponent(id));
      const pct = (x) => (x == null ? "–" : (x * 100).toFixed(1) + "%");
      $("#ia-out").innerHTML = (r.tips.length ? `<ul class="small" style="padding-left:1.1rem">${r.tips.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : "") +
        `<div style="overflow-x:auto"><table class="small" style="border-collapse:collapse;width:100%"><tr><th align="left">Post</th><th>Views</th><th>Reach</th><th>Saves</th><th>Shares</th><th>Likes</th><th>Watch s</th><th>Save%</th></tr>` +
        r.reels.map((x) => `<tr><td><a href="${esc(x.permalink || "#")}" target="_blank" rel="noopener">${esc(x.caption || x.id)}</a></td><td align="right">${x.views}</td><td align="right">${x.reach}</td><td align="right">${x.saves}</td><td align="right">${x.shares}</td><td align="right">${x.likes}</td><td align="right">${x.avg_watch_s || "–"}</td><td align="right">${pct(x.save_rate)}</td></tr>`).join("") + `</table></div>`;
    } catch (er) { $("#ia-out").innerHTML = `<p class="small err">${esc(er.message)}</p>`; } finally { e.target.disabled = false; }
  };
  const poll = async (id) => {
    try {
      const j = await ctx.api("GET", "/documentary/" + id);
      if (j.status === "running") { st(`⏳ ${j.progress || 0}% — ${esc(j.message || "")}`); setTimeout(() => poll(id), 2500); return; }
      $("#dc-build").disabled = false;
      if (j.status === "done") { st(`✅ तैयार! <a href="#/library">Library</a> में "${esc(j.item?.name || "")}" देखें।${j.thumbnail ? ` Thumbnail भी बना है: "${esc(j.thumbnail.name || "")}".` : ""}${j.description ? `<br><b>YouTube description (chapters + credits):</b><textarea id="dc-desc" rows="8" style="width:100%" readonly>${esc(j.description)}</textarea><button class="btn small quiet" id="dc-copy">📋 Copy</button>` : ""}${(j.warnings || []).length ? "<br>⚠ " + j.warnings.map(esc).join("<br>⚠ ") : ""}`); }
      else st("❌ " + esc(j.error || "नहीं बन पाया"), true);
      if (j.status === "done") ytBox(j);
      const cp = $("#dc-copy"); if (cp) cp.onclick = async () => { try { await navigator.clipboard.writeText($("#dc-desc").value); ctx.toast("Copy हो गया"); } catch { $("#dc-desc").select(); ctx.toast("Ctrl+C दबाएँ"); } };
    } catch (e) { st(esc(e.message), true); $("#dc-build").disabled = false; }
  };
  $("#dc-build").onclick = async (e) => {
    const b = e.target; b.disabled = true; st("शुरू हो रहा है…");
    try {
      const r = await ctx.api("POST", "/documentary/build", { title: docState.title, scenes: docState.scenes, ...opts(), sources: docState.sources || [] });
      docState.job = r.job_id; poll(r.job_id);
    } catch (er) { st(esc(er.message), true); b.disabled = false; }
  };
  draw();
}
