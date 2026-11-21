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
  return `<div class="pghead"><div><h1>🔌 API & Integrations</h1><p class="muted">अपने दूसरे software (n8n, Zapier, Make, अपनी app, script) से Vividora चलाएँ — Image→3D, Text→Voice, 3D character video। Key सिर्फ़ आपके workspace तक सीमित है।</p></div></div>
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
  </div></div>`;
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
  loadList();
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
    <button class="btn primary" id="dc-plan">✨ Scenes बनाओ</button>
    <div class="field" style="margin-top:.8rem"><label>या अपनी script (खाली लाइन = नया scene)</label><textarea id="dc-script" rows="5" placeholder="पहला scene…\n\nदूसरा scene…"></textarea></div>
    <button class="btn" id="dc-plan2">📝 Script से scenes</button>
  </div><div class="tl-box">
    <h3 style="margin:0 0 .4rem">2. Scenes जाँचें और बदलें</h3>
    <div id="dc-scenes"><p class="small muted">पहले ऊपर से scenes बनाएँ।</p></div>
    <div id="dc-opts" hidden>
      <div class="tl-row"><div class="field"><label>आवाज़</label><select id="dc-voice"></select></div>
        <div class="field"><label>Shape</label><select id="dc-or"><option value="landscape">Landscape 16:9 (YouTube)</option><option value="portrait">Portrait 9:16 (Reels/Shorts)</option><option value="square">Square 1:1</option></select></div></div>
      <p class="small muted">तस्वीरें: पहले आपकी Library (नाम/tags से मिलान), फिर Pixabay (अगर PIXABAY_API_KEY है), नहीं तो title card। Captions अभी नहीं हैं।</p>
      <button class="btn primary" id="dc-build">🎬 Documentary बनाओ</button>
    </div>
    <div id="dc-status"></div>
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
      <b>Scene ${i + 1}</b> <button class="btn small quiet" data-del="${i}" style="float:right">🗑</button>
      <textarea data-n="${i}" rows="3" style="width:100%">${esc(s.narration)}</textarea>
      <input data-v="${i}" value="${esc(s.visual || "")}" placeholder="तस्वीर के English keywords (जैसे aerial himalaya mountains)" style="width:100%;margin-top:.3rem">
    </div>`).join("");
    box.querySelectorAll("[data-n]").forEach((t) => (t.oninput = () => (docState.scenes[+t.dataset.n].narration = t.value)));
    box.querySelectorAll("[data-v]").forEach((t) => (t.oninput = () => (docState.scenes[+t.dataset.v].visual = t.value)));
    box.querySelectorAll("[data-del]").forEach((b) => (b.onclick = () => { docState.scenes.splice(+b.dataset.del, 1); draw(); }));
    const ti = $("#dc-title"); if (ti) ti.oninput = () => (docState.title = ti.value);
  };
  ctx.api("GET", "/v1/voices").then((r) => {
    const sel = $("#dc-voice"); if (!sel) return;
    const safe = (v) => v.engine === "kokoro" || v.engine === "parler";
    sel.innerHTML = r.voices.map((v) => `<option value="${esc(v.id)}">${esc(v.name || v.id)}${safe(v) ? "" : v.engine === "voicestudio" ? " ⚠ सिर्फ़ निजी इस्तेमाल" : ""}</option>`).join("");
    const pref = r.voices.find((v) => safe(v) && v.lang === "hi") || r.voices.find(safe); if (pref) sel.value = pref.id;
  }).catch(() => {});
  const plan = async (body, btn) => {
    btn.disabled = true; st("scenes बन रहे हैं… (AI 20–60 सेकंड ले सकता है)");
    try { const r = await ctx.api("POST", "/documentary/plan", body); docState = { title: r.title, scenes: r.scenes, job: null }; draw(); st(`${r.scenes.length} scenes तैयार — जाँचकर नीचे से बनाएँ`); }
    catch (e) { st(esc(e.message), true); } finally { btn.disabled = false; }
  };
  $("#dc-plan").onclick = (e) => { const t = $("#dc-topic").value.trim(); if (t.length < 3) { ctx.toast("पहले topic लिखें"); return; } plan({ topic: t, minutes: +$("#dc-min").value, language: $("#dc-lang").value }, e.target); };
  $("#dc-plan2").onclick = (e) => { const t = $("#dc-script").value.trim(); if (!t) { ctx.toast("पहले script लिखें"); return; } plan({ script: t }, e.target); };
  const poll = async (id) => {
    try {
      const j = await ctx.api("GET", "/documentary/" + id);
      if (j.status === "running") { st(`⏳ ${j.progress || 0}% — ${esc(j.message || "")}`); setTimeout(() => poll(id), 2500); return; }
      $("#dc-build").disabled = false;
      if (j.status === "done") { st(`✅ तैयार! <a href="#/library">Library</a> में "${esc(j.item?.name || "")}" देखें।${(j.credits || []).length ? "<br>Credits (description में डालें):<br>" + j.credits.map(esc).join("<br>") : ""}${(j.warnings || []).length ? "<br>⚠ " + j.warnings.map(esc).join("<br>⚠ ") : ""}`); }
      else st("❌ " + esc(j.error || "नहीं बन पाया"), true);
    } catch (e) { st(esc(e.message), true); $("#dc-build").disabled = false; }
  };
  $("#dc-build").onclick = async (e) => {
    const b = e.target; b.disabled = true; st("शुरू हो रहा है…");
    try {
      const r = await ctx.api("POST", "/documentary/build", { title: docState.title, scenes: docState.scenes, voice: $("#dc-voice").value, orientation: $("#dc-or").value, lang: $("#dc-lang").value === "en" ? "en" : "hi" });
      docState.job = r.job_id; poll(r.job_id);
    } catch (er) { st(esc(er.message), true); b.disabled = false; }
  };
  draw();
}
