// Vividora recorder — camera + teleprompter in the browser (phone or PC).
// Records with MediaRecorder at the best quality the device offers, then uploads
// straight into a new project so the usual pipeline (clean → transcript → cuts) runs.
//
// Camera access needs HTTPS (or localhost): use the Cloudflare Tunnel URL on the phone.

let R = null;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const RES = [["auto", "सबसे ऊँची (auto)"], ["3840x2160", "4K · 2160p"], ["2560x1440", "1440p"], ["1920x1080", "1080p"], ["1280x720", "720p"]];
const FPS = [["auto", "auto"], ["24", "24"], ["30", "30"], ["60", "60"]];

function mime() {
  const c = ["video/mp4;codecs=avc1.640028,mp4a.40.2", "video/mp4;codecs=avc1,mp4a.40.2", "video/mp4", "video/webm;codecs=h264,opus", "video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"];
  return c.find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m)) || "";
}

export function mount(root, ctx) {
  const { esc } = ctx;
  let prefs = {}; try { prefs = JSON.parse(localStorage.getItem("vividora_rec") || "{}"); } catch {}
  R = { ctx, root, stream: null, rec: null, chunks: [], t0: 0, timer: null, state: "idle", devices: { cams: [], mics: [] },
    facing: prefs.facing || "user", camId: prefs.camId || "", micId: prefs.micId || "", res: prefs.res || "auto", fps: prefs.fps || "auto", mirror: prefs.mirror !== false,
    tp: { on: true, size: prefs.tpSize || 30, speed: prefs.tpSpeed || 40, opacity: prefs.tpOpacity ?? 0.75, mirror: !!prefs.tpMirror, x: prefs.tpX ?? 20, y: prefs.tpY ?? 56, w: prefs.tpW ?? 360, h: prefs.tpH ?? 220, full: false, playing: false, text: prefs.tpText || "" },
    scriptIdea: null, blob: null, language: prefs.language || "auto" };
  root.innerHTML = `<div class="rec">
    <header class="rec-top"><a class="ibtn" href="#/" title="वापस">←</a><b>Record</b><span class="small muted" id="rec-info"></span><span class="grow"></span>
      <button class="btn small quiet" id="rec-settings-btn">⚙ settings</button><button class="btn small quiet" id="rec-tp-btn">📜 teleprompter</button></header>
    <div class="rec-stage" id="rec-stage">
      <video id="rec-pv" autoplay playsinline muted></video>
      <div class="rec-err" id="rec-err" hidden></div>
      <div class="tp" id="tp" style="left:${R.tp.x}px;top:${R.tp.y}px;width:${R.tp.w}px;height:${R.tp.h}px;opacity:${R.tp.opacity}">
        <div class="tp-bar" id="tp-bar"><span class="small">📜 script</span><span class="grow"></span>
          <button class="ibtn" id="tp-play" title="scroll चलाएँ (space)">▶</button><button class="ibtn" id="tp-full" title="full screen">⛶</button><button class="ibtn" id="tp-edit" title="edit">✎</button><button class="ibtn" id="tp-close">✕</button></div>
        <div class="tp-text" id="tp-text"></div><i class="tp-resize" id="tp-resize"></i>
      </div>
      <div class="rec-meter"><i id="rec-level"></i></div>
      <div class="rec-hud"><span id="rec-time">0:00</span><span id="rec-q" class="small"></span></div>
      <div class="rec-count" id="rec-count" hidden>3</div>
    </div>
    <div class="rec-controls">
      <button class="ibtn" id="rec-flip" title="camera बदलें">🔄</button>
      <button class="rec-btn" id="rec-main" title="record"><i></i></button>
      <button class="ibtn" id="rec-pause" title="pause" disabled>⏸</button>
    </div>
    <div class="rec-panel" id="rec-settings" hidden>
      <h3>Settings</h3>
      <label>Camera <select id="s-cam"></select></label>
      <label>Mic <select id="s-mic"></select></label>
      <label>Resolution <select id="s-res">${RES.map(([v, l]) => `<option value="${v}" ${R.res === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label>FPS <select id="s-fps">${FPS.map(([v, l]) => `<option value="${v}" ${R.fps === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label class="chk"><input type="checkbox" id="s-mirror" ${R.mirror ? "checked" : ""}> preview mirror (recording सीधी रहती है)</label>
      <label>भाषा <select id="s-lang"><option value="auto" ${R.language === "auto" ? "selected" : ""}>auto</option><option value="hi" ${R.language === "hi" ? "selected" : ""}>हिंदी</option><option value="en" ${R.language === "en" ? "selected" : ""}>English</option></select></label>
      <p class="small muted" id="s-caps"></p>
      <p class="small muted">format: <code>${esc(mime() || "MediaRecorder नहीं")}</code></p>
      <button class="btn small" id="s-apply">लागू करें</button>
    </div>
    <div class="rec-panel" id="rec-tp" hidden>
      <h3>Teleprompter</h3>
      <label>Script <select id="tp-pick"><option value="">— अपना text —</option></select></label>
      <textarea id="tp-src" rows="8" placeholder="यहाँ script लिखें या Plan से चुनें…">${esc(R.tp.text)}</textarea>
      <div class="row"><button class="btn small" id="tp-save" title="Plan में idea की तरह सेव">💾 सेव</button><button class="btn small quiet" id="tp-apply">लागू</button></div>
      <label>अक्षर <input type="range" id="tp-size" min="16" max="72" value="${R.tp.size}"></label>
      <label>speed <input type="range" id="tp-speed" min="5" max="120" value="${R.tp.speed}"></label>
      <label>पारदर्शिता <input type="range" id="tp-op" min="0.3" max="1" step="0.05" value="${R.tp.opacity}"></label>
      <label class="chk"><input type="checkbox" id="tp-mirror" ${R.tp.mirror ? "checked" : ""}> mirror text (teleprompter glass)</label>
      <p class="small muted">window को drag करें, कोने से size बदलें, ⛶ से full screen। Space = scroll चालू/बंद (recording के दौरान भी)।</p>
    </div>
    <div class="rec-review" id="rec-review" hidden>
      <video id="rec-out" controls playsinline></video>
      <div class="row" style="margin-top:.5rem"><input id="rec-title" placeholder="वीडियो का नाम" style="flex:1"><button class="btn primary" id="rec-upload">Upload → auto edit</button><button class="btn quiet" id="rec-discard">हटाएँ</button></div>
      <div id="rec-prog"></div>
    </div>
  </div>`;
  bind();
  start();
  loadScripts();
}
export function unmount() { if (!R) return; stop(); document.removeEventListener("keydown", onKey); clearInterval(R.timer); cancelAnimationFrame(R.raf); R = null; }

function savePrefs() { try { localStorage.setItem("vividora_rec", JSON.stringify({ facing: R.facing, camId: R.camId, micId: R.micId, res: R.res, fps: R.fps, mirror: R.mirror, language: R.language, tpSize: R.tp.size, tpSpeed: R.tp.speed, tpOpacity: R.tp.opacity, tpMirror: R.tp.mirror, tpX: R.tp.x, tpY: R.tp.y, tpW: R.tp.w, tpH: R.tp.h, tpText: R.tp.text })); } catch {} }

async function start() {
  stop();
  const err = $("#rec-err", R.root); err.hidden = true;
  if (!navigator.mediaDevices?.getUserMedia) { err.hidden = false; err.textContent = "camera सिर्फ़ HTTPS (या localhost) पर चलता है — Cloudflare Tunnel वाला पता खोलें।"; return; }
  const [w, h] = R.res === "auto" ? [3840, 2160] : R.res.split("x").map(Number);
  const video = { width: { ideal: w }, height: { ideal: h }, frameRate: R.fps === "auto" ? { ideal: 60 } : { ideal: +R.fps } };
  if (R.camId) video.deviceId = { exact: R.camId }; else video.facingMode = R.facing;
  const audio = { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1, sampleRate: 48000 };
  if (R.micId) audio.deviceId = { exact: R.micId };
  try { R.stream = await navigator.mediaDevices.getUserMedia({ video, audio }); }
  catch (e) { try { R.stream = await navigator.mediaDevices.getUserMedia({ video: R.camId ? { deviceId: { exact: R.camId } } : { facingMode: R.facing }, audio: true }); } catch (e2) { err.hidden = false; err.textContent = "camera नहीं मिला: " + e2.message; return; } }
  const v = $("#rec-pv", R.root); v.srcObject = R.stream; v.style.transform = R.mirror && R.facing === "user" ? "scaleX(-1)" : "";
  const tr = R.stream.getVideoTracks()[0]; const st = tr.getSettings();
  $("#rec-q", R.root).textContent = `${st.width}×${st.height} · ${Math.round(st.frameRate || 0)} fps`;
  $("#rec-info", R.root).textContent = tr.label || "";
  const caps = tr.getCapabilities ? tr.getCapabilities() : null;
  if (caps) $("#s-caps", R.root).textContent = `यह camera दे सकता है: ${caps.width?.max || "?"}×${caps.height?.max || "?"} तक, ${caps.frameRate?.max || "?"} fps तक${caps.facingMode ? " · " + caps.facingMode.join("/") : ""}`;
  // level meter
  try { const ac = new (window.AudioContext || window.webkitAudioContext)(); const src = ac.createMediaStreamSource(R.stream); const an = ac.createAnalyser(); an.fftSize = 512; src.connect(an); const buf = new Uint8Array(an.frequencyBinCount);
    const tick = () => { if (!R) return; an.getByteTimeDomainData(buf); let s = 0; for (const x of buf) s += (x - 128) ** 2; const lvl = Math.min(1, Math.sqrt(s / buf.length) / 40); $("#rec-level", R.root).style.width = (lvl * 100) + "%"; R.raf = requestAnimationFrame(tick); }; tick(); R.ac = ac; } catch {}
  await listDevices();
}
function stop() { if (R?.stream) { R.stream.getTracks().forEach((t) => t.stop()); R.stream = null; } if (R?.ac) { R.ac.close().catch(() => {}); R.ac = null; } }
async function listDevices() {
  const ds = await navigator.mediaDevices.enumerateDevices().catch(() => []);
  R.devices.cams = ds.filter((d) => d.kind === "videoinput"); R.devices.mics = ds.filter((d) => d.kind === "audioinput");
  $("#s-cam", R.root).innerHTML = `<option value="">auto (${R.facing === "user" ? "front" : "back"})</option>` + R.devices.cams.map((d, i) => `<option value="${d.deviceId}" ${R.camId === d.deviceId ? "selected" : ""}>${d.label || "camera " + (i + 1)}</option>`).join("");
  $("#s-mic", R.root).innerHTML = `<option value="">auto</option>` + R.devices.mics.map((d, i) => `<option value="${d.deviceId}" ${R.micId === d.deviceId ? "selected" : ""}>${d.label || "mic " + (i + 1)}</option>`).join("");
}

function bind() {
  const { toast } = R.ctx;
  $("#rec-settings-btn", R.root).onclick = () => { const p = $("#rec-settings", R.root); p.hidden = !p.hidden; $("#rec-tp", R.root).hidden = true; };
  $("#rec-tp-btn", R.root).onclick = () => { const p = $("#rec-tp", R.root); p.hidden = !p.hidden; $("#rec-settings", R.root).hidden = true; $("#tp", R.root).style.display = ""; };
  $("#s-apply", R.root).onclick = () => { R.camId = $("#s-cam", R.root).value; R.micId = $("#s-mic", R.root).value; R.res = $("#s-res", R.root).value; R.fps = $("#s-fps", R.root).value; R.mirror = $("#s-mirror", R.root).checked; R.language = $("#s-lang", R.root).value; savePrefs(); start(); $("#rec-settings", R.root).hidden = true; };
  $("#rec-flip", R.root).onclick = () => { R.facing = R.facing === "user" ? "environment" : "user"; R.camId = ""; savePrefs(); start(); };
  $("#rec-main", R.root).onclick = () => (R.state === "idle" ? countdown() : finish());
  $("#rec-pause", R.root).onclick = () => { if (!R.rec) return; if (R.rec.state === "recording") { R.rec.pause(); R.state = "paused"; $("#rec-pause", R.root).textContent = "▶"; } else { R.rec.resume(); R.state = "rec"; $("#rec-pause", R.root).textContent = "⏸"; } };
  // teleprompter
  const tp = $("#tp", R.root), bar = $("#tp-bar", R.root), txt = $("#tp-text", R.root);
  const applyTp = () => { txt.style.fontSize = R.tp.size + "px"; txt.style.transform = R.tp.mirror ? "scaleX(-1)" : ""; tp.style.opacity = R.tp.opacity; txt.innerHTML = (R.tp.text || "script Plan से चुनें या लिखें…").split("\n").map((l) => `<p>${R.ctx.esc(l)}</p>`).join("") + `<p style="height:60vh"></p>`; savePrefs(); };
  applyTp();
  bar.onmousedown = bar.ontouchstart = (e) => { if (e.target.closest("button")) return; e.preventDefault(); const p = e.touches ? e.touches[0] : e; const x0 = p.clientX - R.tp.x, y0 = p.clientY - R.tp.y;
    const mv = (ev) => { const q = ev.touches ? ev.touches[0] : ev; R.tp.x = Math.max(0, q.clientX - x0); R.tp.y = Math.max(0, q.clientY - y0); tp.style.left = R.tp.x + "px"; tp.style.top = R.tp.y + "px"; };
    const up = () => { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); document.removeEventListener("touchmove", mv); document.removeEventListener("touchend", up); savePrefs(); };
    document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up); document.addEventListener("touchmove", mv, { passive: false }); document.addEventListener("touchend", up); };
  const rz = $("#tp-resize", R.root);
  rz.onmousedown = rz.ontouchstart = (e) => { e.preventDefault(); const p = e.touches ? e.touches[0] : e; const w0 = R.tp.w - p.clientX, h0 = R.tp.h - p.clientY;
    const mv = (ev) => { const q = ev.touches ? ev.touches[0] : ev; R.tp.w = Math.max(200, w0 + q.clientX); R.tp.h = Math.max(100, h0 + q.clientY); tp.style.width = R.tp.w + "px"; tp.style.height = R.tp.h + "px"; };
    const up = () => { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); document.removeEventListener("touchmove", mv); document.removeEventListener("touchend", up); savePrefs(); };
    document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up); document.addEventListener("touchmove", mv, { passive: false }); document.addEventListener("touchend", up); };
  $("#tp-close", R.root).onclick = () => (tp.style.display = "none");
  $("#tp-full", R.root).onclick = () => { R.tp.full = !R.tp.full; tp.classList.toggle("full", R.tp.full); };
  $("#tp-edit", R.root).onclick = () => { $("#rec-tp", R.root).hidden = false; $("#tp-src", R.root).focus(); };
  const scroll = () => { if (!R || !R.tp.playing) return; txt.scrollTop += R.tp.speed / 60; R.tpRaf = requestAnimationFrame(scroll); };
  const togglePlay = () => { R.tp.playing = !R.tp.playing; $("#tp-play", R.root).textContent = R.tp.playing ? "⏸" : "▶"; if (R.tp.playing) scroll(); else cancelAnimationFrame(R.tpRaf); };
  $("#tp-play", R.root).onclick = togglePlay; R.togglePlay = togglePlay;
  txt.onwheel = () => { }; // manual scroll allowed
  $("#tp-size", R.root).oninput = (e) => { R.tp.size = +e.target.value; applyTp(); };
  $("#tp-speed", R.root).oninput = (e) => { R.tp.speed = +e.target.value; savePrefs(); };
  $("#tp-op", R.root).oninput = (e) => { R.tp.opacity = +e.target.value; applyTp(); };
  $("#tp-mirror", R.root).onchange = (e) => { R.tp.mirror = e.target.checked; applyTp(); };
  $("#tp-apply", R.root).onclick = () => { R.tp.text = $("#tp-src", R.root).value; applyTp(); txt.scrollTop = 0; $("#rec-tp", R.root).hidden = true; };
  $("#tp-pick", R.root).onchange = (e) => { const i = (R.ideas || []).find((x) => x.id === e.target.value); if (i) { R.scriptIdea = i; $("#tp-src", R.root).value = i.script || i.outline || i.title; R.tp.text = $("#tp-src", R.root).value; applyTp(); txt.scrollTop = 0; } else R.scriptIdea = null; };
  $("#tp-save", R.root).onclick = async () => { const text = $("#tp-src", R.root).value.trim(); if (!text) return; const title = prompt("script का नाम", R.scriptIdea?.title || text.split("\n")[0].slice(0, 60)); if (!title) return;
    try { if (R.scriptIdea) await R.ctx.api("PATCH", `/ideas/${R.scriptIdea.id}`, { script: text, title }); else { const i = await R.ctx.api("POST", "/ideas", { title, script: text, format: "short" }); await R.ctx.api("PATCH", `/ideas/${i.id}`, { status: "approved" }); R.scriptIdea = i; } toast("script सेव"); loadScripts(); } catch (e) { toast(e.message); } };
  // review
  $("#rec-discard", R.root).onclick = () => { R.blob = null; $("#rec-review", R.root).hidden = true; $("#rec-stage", R.root).hidden = false; $("#rec-main", R.root).classList.remove("busy"); start(); };
  $("#rec-upload", R.root).onclick = upload;
  document.addEventListener("keydown", onKey);
}
function onKey(e) { if (!R || e.target.closest("input,textarea,select")) return; if (e.code === "Space") { e.preventDefault(); R.togglePlay(); } else if (e.key === "r" || e.key === "R") { R.state === "idle" ? countdown() : finish(); } }
async function loadScripts() {
  try { R.ideas = (await R.ctx.api("GET", "/ideas")).filter((i) => i.script || i.outline); } catch { R.ideas = []; }
  const sel = $("#tp-pick", R.root); if (!sel) return;
  sel.innerHTML = `<option value="">— अपना text —</option>` + R.ideas.map((i) => `<option value="${i.id}" ${R.scriptIdea?.id === i.id ? "selected" : ""}>${R.ctx.esc(i.title)}${i.script ? "" : " (outline)"}</option>`).join("");
}
function countdown() {
  const c = $("#rec-count", R.root); let n = 3; c.hidden = false; c.textContent = n;
  const iv = setInterval(() => { n--; if (n <= 0) { clearInterval(iv); c.hidden = true; begin(); } else c.textContent = n; }, 1000);
}
function begin() {
  if (!R.stream) return;
  const m = mime(); R.chunks = [];
  const opts = { mimeType: m || undefined, videoBitsPerSecond: 24_000_000, audioBitsPerSecond: 192_000 };
  try { R.rec = new MediaRecorder(R.stream, opts); } catch { R.rec = new MediaRecorder(R.stream); }
  R.rec.ondataavailable = (e) => { if (e.data.size) R.chunks.push(e.data); };
  R.rec.onstop = () => { R.blob = new Blob(R.chunks, { type: R.rec.mimeType || m || "video/webm" }); review(); };
  R.rec.start(1000); R.state = "rec"; R.t0 = Date.now();
  $("#rec-main", R.root).classList.add("busy"); $("#rec-pause", R.root).disabled = false;
  R.timer = setInterval(() => { const s = Math.floor((Date.now() - R.t0) / 1000); $("#rec-time", R.root).textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; }, 500);
  if (R.tp.text && !R.tp.playing) R.togglePlay();
}
function finish() { if (!R.rec) return; clearInterval(R.timer); if (R.tp.playing) R.togglePlay(); R.rec.stop(); R.state = "idle"; $("#rec-pause", R.root).disabled = true; $("#rec-pause", R.root).textContent = "⏸"; }
function review() {
  stop();
  $("#rec-stage", R.root).hidden = true; const rv = $("#rec-review", R.root); rv.hidden = false;
  const out = $("#rec-out", R.root); out.src = URL.createObjectURL(R.blob);
  $("#rec-title", R.root).value = R.scriptIdea?.title || `Recording ${new Date().toLocaleString("hi-IN")}`;
  $("#rec-prog", R.root).innerHTML = `<p class="small muted">${(R.blob.size / 1024 / 1024).toFixed(1)} MB · ${R.blob.type}</p>`;
}
async function upload() {
  const { api, toast, go, uploadFile } = R.ctx; const btn = $("#rec-upload", R.root); btn.disabled = true;
  const ext = R.blob.type.includes("mp4") ? "mp4" : "webm";
  const file = new File([R.blob], `recording_${Date.now()}.${ext}`, { type: R.blob.type });
  try {
    const p = await api("POST", "/projects", { title: $("#rec-title", R.root).value.trim() || "Recording", language: R.language });
    if (R.scriptIdea) api("PATCH", `/ideas/${R.scriptIdea.id}`, { project_id: p.id, status: "recorded" }).catch(() => {});
    await uploadFile(p.id, file, (d, t) => { $("#rec-prog", R.root).innerHTML = `<p class="small muted">upload ${(d / t * 100).toFixed(0)}%</p><div class="progress"><i style="width:${(d / t * 100).toFixed(0)}%"></i></div>`; });
    toast("upload पूरा — auto edit शुरू"); R.blob = null; go("/projects/" + p.id);
  } catch (e) { toast(e.message); btn.disabled = false; }
}
