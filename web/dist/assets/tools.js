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
.tl-prev{max-width:100%;max-height:220px;border-radius:8px;display:block;margin:.4rem 0}`;
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
      const blob = await blobPost("/voicestudio/synthesise", { text, language: $("#vs-lang").value, model: $("#vs-model").value || undefined, voice: $("#vs-voice").value || undefined, speed: +$("#vs-speed").value });
      const url = URL.createObjectURL(blob);
      $("#vs-out").innerHTML = `<audio controls src="${url}" style="width:100%"></audio><p><a class="btn small" href="${url}" download="voice-${Date.now()}.wav">⬇ WAV download</a></p><p class="small muted">इसे timeline में लगाने के लिए Library → Voice में upload करें।</p>`;
      st("तैयार ✓");
    } catch (e) { st(e.message, true); } finally { btn.disabled = false; }
  };
}

// ---------------------------------------------------------------- Image → 3D (.glb)
export function glbView() {
  return `<div class="pghead"><div><h1>🧊 Image → 3D (.glb)</h1><p class="muted">एक photo या character की तस्वीर दें → 3D model (.glb) बनता है। साफ़ background वाली, सामने से ली तस्वीर सबसे अच्छी रहती है। CPU पर 1–3 मिनट लगते हैं।</p></div><div class="row"><a class="btn" href="#/characters3d">3D Studio</a></div></div>
  <div class="tl-wrap"><div class="tl-box">
    <div class="drop" id="g3-drop"><input type="file" id="g3-file" accept="image/*" hidden><b>तस्वीर यहाँ छोड़ें या click करें</b><br><span class="muted small">PNG / JPG, 10 MB तक</span><div id="g3-name" class="small"></div></div>
    <img id="g3-prev" class="tl-prev" hidden alt="">
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
  const pick = (f) => { if (!f) return; file = f; $("#g3-name").textContent = f.name; $("#g3-go").disabled = false; if (!$("#g3-title").value) $("#g3-title").value = f.name.replace(/\.[^.]+$/, ""); const p = $("#g3-prev"); p.src = URL.createObjectURL(f); p.hidden = false; };
  drop.onclick = () => inp.click(); inp.onchange = () => pick(inp.files[0]);
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); }; drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); pick(e.dataTransfer.files[0]); };
  let panel = null; const list = () => panel?.refresh();
  import("./models3d.js").then((M) => M.mountModels($("#g3-models"), ctx)).then((p) => { panel = p; }).catch(() => {});
  ctx.api("GET", "/triposr/health").then((h) => { if (h.status !== "ok") st("⚠ TripoSR service बंद है (port 8090) — server पर `systemctl status triposr` देखें", true); }).catch(() => {});
  $("#g3-go").onclick = async () => {
    if (!file) return; const btn = $("#g3-go"); btn.disabled = true; st("भेज रहे हैं…");
    try {
      const fd = new FormData(); fd.append("file", file); fd.append("name", $("#g3-title").value.trim() || file.name);
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
