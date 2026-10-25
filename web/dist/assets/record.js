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
  // WebM first: Chrome's MP4 muxer hands out data only when the take stops (with our audio settings), so nothing could be
  // saved locally while recording. WebM delivers every second → the safety copy is always current. iOS has only MP4.
  const c = ["video/webm;codecs=h264,opus", "video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm",
             "video/mp4;codecs=avc1.640028,mp4a.40.2", "video/mp4;codecs=avc1,mp4a.40.2", "video/mp4"];
  return c.find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m)) || "";
}

// ---- local safety copy: every recorded second goes into IndexedDB as it arrives, so a dead page, a lost
// network or a phone that locks mid-upload never loses the take. Deleted only after the server confirms the upload.
const DB = {
  name: "vividora_rec", _db: null,
  open() {
    if (this._db) return Promise.resolve(this._db);
    return new Promise((res, rej) => {
      if (!window.indexedDB) return rej(new Error("no indexedDB"));
      const r = indexedDB.open(this.name, 1);
      r.onupgradeneeded = () => { const d = r.result; d.createObjectStore("drafts", { keyPath: "id" }); d.createObjectStore("chunks", { keyPath: ["draft", "seq"] }); };
      r.onsuccess = () => { this._db = r.result; res(this._db); }; r.onerror = () => rej(r.error || new Error("indexedDB बंद है")); r.onblocked = () => rej(new Error("indexedDB blocked"));
    });
  },
  tx(store, mode, fn) { return this.open().then((d) => new Promise((res, rej) => { const t = d.transaction(store, mode); const q = fn(t.objectStore(store)); t.oncomplete = () => res(q && q.result); t.onerror = () => rej(t.error); t.onabort = () => rej(t.error || new Error("abort")); })); },
  putDraft(d) { return this.tx("drafts", "readwrite", (s) => s.put(d)); },
  putChunk(draft, seq, blob) { return this.tx("chunks", "readwrite", (s) => s.put({ draft, seq, blob })); },
  drafts() { return this.tx("drafts", "readonly", (s) => s.getAll()).then((x) => x || []); },
  chunks(draft) { return this.tx("chunks", "readonly", (s) => s.getAll(IDBKeyRange.bound([draft, 0], [draft, 1e9]))).then((x) => (x || []).sort((a, b) => a.seq - b.seq).map((c) => c.blob)); },
  async drop(draft) { await this.tx("drafts", "readwrite", (s) => s.delete(draft)); await this.tx("chunks", "readwrite", (s) => { let c = s.openCursor(IDBKeyRange.bound([draft, 0], [draft, 1e9])); c.onsuccess = () => { const k = c.result; if (k) { k.delete(); k.continue(); } }; return null; }); },
};
async function storageFree() { try { const e = await navigator.storage?.estimate?.(); return e && e.quota ? { free: e.quota - (e.usage || 0), quota: e.quota, usage: e.usage || 0 } : null; } catch { return null; }
}
const ago = (t) => { const m = Math.round((Date.now() - t) / 60000); return m < 1 ? "अभी" : m < 60 ? `${m} मिनट पहले` : m < 1440 ? `${Math.round(m / 60)} घंटे पहले` : `${Math.round(m / 1440)} दिन पहले`; };
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

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
      <div class="rec-hud"><span id="rec-time">0:00</span><span id="rec-q" class="small"></span><span id="rec-local" class="small" title="recording इसी phone/PC में भी save होती रहती है"></span></div>
      <div class="rec-recover" id="rec-recover" hidden></div>
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
      <textarea id="tp-src" rows="8" placeholder="यहाँ script लिखें या Plan से चुनें… हिस्से [HOOK] [SETUP] [STORY] [TURN] [LESSON] [CTA] से अलग करें">${esc(R.tp.text)}</textarea>
      <div class="row"><button class="btn small" id="tp-save" title="Plan में idea की तरह सेव">💾 सेव</button><button class="btn small quiet" id="tp-apply">लागू</button><button class="btn small quiet" id="tp-secs" title="हर हिस्से को अलग से दोबारा लिखवाएँ">✦ हिस्से</button></div>
      <div id="tp-sections" class="tp-sections" hidden></div>
      <label>अक्षर <input type="range" id="tp-size" min="16" max="72" value="${R.tp.size}"></label>
      <label>speed <input type="range" id="tp-speed" min="5" max="120" value="${R.tp.speed}"></label>
      <label>पारदर्शिता <input type="range" id="tp-op" min="0.3" max="1" step="0.05" value="${R.tp.opacity}"></label>
      <label class="chk"><input type="checkbox" id="tp-mirror" ${R.tp.mirror ? "checked" : ""}> mirror text (teleprompter glass)</label>
      <p class="small muted">window को drag करें, कोने से size बदलें, ⛶ से full screen। Space = scroll चालू/बंद (recording के दौरान भी)।</p>
    </div>
    <div class="rec-review" id="rec-review" hidden>
      <video id="rec-out" controls playsinline></video>
      <div class="row" style="margin-top:.5rem"><input id="rec-title" placeholder="वीडियो का नाम" style="flex:1"><label class="chk small"><input type="checkbox" id="rec-ap" checked> ✈ autopilot</label><button class="btn primary" id="rec-upload">Upload → auto edit</button><button class="btn quiet" id="rec-discard">हटाएँ</button></div>
      <div id="rec-prog"></div>
    </div>
  </div>`;
  bind();
  start();
  loadScripts();
  checkRecovery();
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
  const applyTp = () => { txt.style.fontSize = R.tp.size + "px"; txt.style.transform = R.tp.mirror ? "scaleX(-1)" : ""; tp.style.opacity = R.tp.opacity; txt.innerHTML = tpHtml(R.tp.text) + `<p style="height:60vh"></p>`; savePrefs(); if (!$("#tp-sections", R.root).hidden) renderSections(); };
  R.applyTp = applyTp;
  applyTp();
  $("#tp-secs", R.root).onclick = () => { const b = $("#tp-sections", R.root); b.hidden = !b.hidden; if (!b.hidden) { R.tp.text = $("#tp-src", R.root).value; renderSections(); } };
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
  let scrollAcc = 0, scrollLast = 0;
  const scroll = (ts) => { if (!R || !R.tp.playing) return;
    if (!scrollLast) scrollLast = ts;
    const dt = Math.min(ts - scrollLast, 200); // cap delta to avoid jumps after tab-switch
    scrollLast = ts;
    scrollAcc += R.tp.speed * (dt / 1000); // speed = px per second, time-based for consistent speed across refresh rates
    if (scrollAcc >= 1) { const px = Math.floor(scrollAcc); txt.scrollTop += px; scrollAcc -= px; }
    R.tpRaf = requestAnimationFrame(scroll); };
  const togglePlay = () => {
    if (tp.style.display === "none") tp.style.display = ""; // ensure teleprompter is visible before scrolling
    R.tp.playing = !R.tp.playing; $("#tp-play", R.root).textContent = R.tp.playing ? "⏸" : "▶";
    if (R.tp.playing) { scrollAcc = 0; scrollLast = 0; R.tpRaf = requestAnimationFrame(scroll); } else cancelAnimationFrame(R.tpRaf); };
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
  $("#rec-discard", R.root).onclick = () => { if (R.draft) { DB.drop(R.draft.id).catch(() => {}); R.draft = null; } R.blob = null; $("#rec-review", R.root).hidden = true; $("#rec-stage", R.root).hidden = false; $("#rec-main", R.root).classList.remove("busy"); start(); };
  $("#rec-upload", R.root).onclick = upload;
  document.addEventListener("keydown", onKey);
}
// ---- script sections: [HOOK] … [CTA] markers → labelled blocks on the prompter, each redoable on its own ----
const SEC_LABEL = { HOOK: "Hook — पहले 2 सेकंड", SETUP: "Setup", STORY: "Story", TURN: "Turn — वो पल", LESSON: "Lesson — सीख", POINTS: "मुख्य बातें", MAIN: "मुख्य बात", CTA: "CTA", CLOSING: "Closing" };
const SEC_RE = /^[ \t]*\[([A-Za-z][A-Za-z \/-]*?)(?:[ \t]*[—\-–:].*?)?\][ \t]*$/gm;
function parseSections(text) {
  text = text || ""; const hits = [...text.matchAll(SEC_RE)];
  if (!hits.length) return text.trim() ? [{ key: "MAIN", label: SEC_LABEL.MAIN, text: text.trim() }] : [];
  const out = []; const lead = text.slice(0, hits[0].index).trim(); if (lead) out.push({ key: "MAIN", label: SEC_LABEL.MAIN, text: lead });
  hits.forEach((h, n) => { const key = h[1].split(/\s/)[0].toUpperCase().replace(/[^A-Z]/g, "") || "MAIN"; const end = n + 1 < hits.length ? hits[n + 1].index : text.length; out.push({ key, label: SEC_LABEL[key] || key, text: text.slice(h.index + h[0].length, end).trim() }); });
  return out;
}
function joinSections(secs) { return secs.filter((s) => s.text.trim() || s.key === "HOOK").map((s) => `[${s.key}]\n${s.text.trim()}`).join("\n\n"); }
function tpHtml(text) {
  const { esc } = R.ctx; const secs = parseSections(text);
  if (!secs.length) return `<p class="muted">script Plan से चुनें या लिखें…</p>`;
  return secs.map((s) => `<section class="tp-sec" data-key="${s.key}"><h5>${esc(s.label)}</h5>${s.text.split("\n").filter((l) => l.trim()).map((l) => `<p>${esc(l)}</p>`).join("")}</section>`).join("");
}
function renderSections() {
  const { esc } = R.ctx; const box = $("#tp-sections", R.root); const secs = parseSections($("#tp-src", R.root).value);
  const can = !!R.scriptIdea;
  box.innerHTML = (can ? "" : `<p class="small muted">हर हिस्से को AI से दोबारा लिखवाने के लिए पहले 💾 सेव करें (Plan में idea बनती है)।</p>`) +
    (secs.length ? secs.map((s) => `<div class="tp-secrow" data-key="${s.key}"><div class="row between"><b class="small">${esc(s.label)}</b><span class="small muted">${s.text.split(/\s+/).filter(Boolean).length} शब्द</span></div>
      <div class="row tp-secbtns"><button class="btn small" data-mode="rewrite" ${can ? "" : "disabled"}>✦ दोबारा लिखो</button><button class="btn small" data-mode="improve" ${can ? "" : "disabled"}>✦ बेहतर करो</button><button class="btn small" data-mode="shorten" ${can ? "" : "disabled"}>✦ छोटा करो</button>${s.key === "HOOK" ? `<button class="btn small primary" data-hooks="1" ${can ? "" : "disabled"}>3 विकल्प</button>` : ""}</div>
      <div class="tp-alts" id="alts-${s.key}"></div></div>`).join("") : `<p class="small muted">script में [HOOK] [SETUP] … [CTA] जैसे markers डालें, तो हर हिस्सा अलग दिखेगा।</p>`);
  $$("[data-mode]", box).forEach((b) => (b.onclick = () => redoSection(b.closest(".tp-secrow").dataset.key, b.dataset.mode, b)));
  $$("[data-hooks]", box).forEach((b) => (b.onclick = () => hookOptions(b)));
}
async function redoSection(key, mode, btn) {
  const { api, toast } = R.ctx; if (!R.scriptIdea) return;
  const script = $("#tp-src", R.root).value; btn.disabled = true; const old = btn.textContent; btn.textContent = "… लिख रहा";
  try { const r = await api("POST", `/ideas/${R.scriptIdea.id}/script/section`, { key, mode, script, language: R.language });
    $("#tp-src", R.root).value = r.script; R.tp.text = r.script; R.applyTp(); renderSections(); toast(`${SEC_LABEL[key] || key} बदला — बाकी वैसा ही`); }
  catch (e) { toast(e.message); btn.disabled = false; btn.textContent = old; }
}
async function hookOptions(btn) {
  const { api, toast, esc } = R.ctx; if (!R.scriptIdea) return; btn.disabled = true; const box = $("#alts-HOOK", R.root); box.innerHTML = `<p class="small muted">hooks सोच रहा…</p>`;
  try { const r = await api("POST", `/ideas/${R.scriptIdea.id}/script/hooks`, { language: R.language });
    box.innerHTML = r.hooks.map((h) => `<div class="tp-alt"><span>${esc(h)}</span><div class="row"><button class="btn small primary" data-pick>यह चुनो</button><button class="btn small quiet" data-strong>और दमदार बनाओ</button></div></div>`).join("") + (r.source === "aipack" ? `<p class="small muted">video के transcript से लिए गए hooks — कोई नया AI credit नहीं लगा</p>` : "");
    $$("[data-pick]", box).forEach((b) => (b.onclick = () => setSection("HOOK", b.closest(".tp-alt").querySelector("span").textContent)));
    $$("[data-strong]", box).forEach((b) => (b.onclick = async () => { await setSection("HOOK", b.closest(".tp-alt").querySelector("span").textContent); redoSection("HOOK", "improve", b); }));
  } catch (e) { box.innerHTML = ""; toast(e.message); } finally { btn.disabled = false; }
}
async function setSection(key, text) {
  const { api, toast } = R.ctx; const script = $("#tp-src", R.root).value;
  try { const r = await api("POST", `/ideas/${R.scriptIdea.id}/script/section`, { key, text, script }); $("#tp-src", R.root).value = r.script; R.tp.text = r.script; R.applyTp(); renderSections(); toast("hook बदला"); }
  catch (e) { toast(e.message); }
}

// ---- recovery of a take that never reached the server ----
async function checkRecovery() {
  const { esc } = R.ctx; const box = $("#rec-recover", R.root); if (!box) return;
  let drafts = []; try { drafts = (await DB.drafts()).filter((d) => d.size > 0); } catch { return; }
  if (!drafts.length) { box.hidden = true; return; }
  const d = drafts.sort((a, b) => b.started - a.started)[0];
  box.hidden = false;
  box.innerHTML = `<b>पिछली recording मिली</b> — ${(d.size / 1024 / 1024).toFixed(1)} MB · ${mmss(d.seconds || 0)} · ${ago(d.started)}${d.title ? ` · ${esc(d.title)}` : ""}${d.uploading ? " · upload अधूरा था" : ""}<div class="row" style="margin-top:.4rem"><button class="btn small primary" id="rc-up">upload करें</button><button class="btn small quiet" id="rc-del">हटाएँ</button></div>`;
  $("#rc-del", box).onclick = async () => { if (!confirm("यह recording हमेशा के लिए हटेगी?")) return; await DB.drop(d.id).catch(() => {}); checkRecovery(); };
  $("#rc-up", box).onclick = async () => { try { const parts = await DB.chunks(d.id); if (!parts.length) throw new Error("chunks नहीं मिले"); R.blob = new Blob(parts, { type: d.mime || "video/webm" }); R.draft = d; box.hidden = true; review(); if (d.title) $("#rec-title", R.root).value = d.title; } catch (e) { R.ctx.toast("recording पढ़ नहीं पाया: " + e.message); } };
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
async function begin() {
  if (!R.stream) return;
  const m = mime(); R.chunks = [];
  const opts = { mimeType: m || undefined, videoBitsPerSecond: 24_000_000, audioBitsPerSecond: 192_000 };
  try { R.rec = new MediaRecorder(R.stream, opts); } catch { R.rec = new MediaRecorder(R.stream); }
  // local safety copy
  const local = $("#rec-local", R.root); const id = "d" + Date.now().toString(36); let seq = 0, size = 0, okWrites = 0;
  R.draft = { id, started: Date.now(), mime: R.rec.mimeType || m || "video/webm", size: 0, seconds: 0, title: R.scriptIdea?.title || "" };
  R.localOk = null;
  const fr = await storageFree();
  const need = 3 * 1024 * 1024 * 600; // ~24 Mbps × 10 min
  if (fr && fr.free < 2 * need) R.ctx.toast(`इस device में सिर्फ़ ${(fr.free / 1024 / 1024).toFixed(0)} MB जगह बची है — लंबी recording local save नहीं हो पाएगी`, 5000);
  try { await DB.putDraft(R.draft); } catch (e) { R.localOk = false; local.textContent = "⚠ local save नहीं"; local.title = "इस browser/mode में recording device पर save नहीं हो पा रही (private mode? storage बंद?) — upload पूरा होने तक page बंद न करें"; }
  R.rec.ondataavailable = (e) => { if (!e.data.size) return; R.chunks.push(e.data); const n = seq++;
    if (R.localOk === false) return;
    DB.putChunk(id, n, e.data).then(() => { okWrites++; size += e.data.size; R.draft.size = size; R.draft.seconds = (Date.now() - R.t0) / 1000; DB.putDraft(R.draft).catch(() => {});
      if (R.localOk !== true) { R.localOk = true; local.textContent = "💾 local save चालू"; local.title = "हर सेकंड इसी device में भी save हो रहा है — page बंद/refresh होने पर भी recording बची रहेगी"; } })
      .catch((err) => { if (R.localOk !== false) { R.localOk = false; local.textContent = "⚠ local save रुकी"; local.title = "device पर जगह नहीं या storage बंद: " + (err?.message || ""); } }); };
  R.rec.onstop = () => { R.blob = new Blob(R.chunks, { type: R.rec.mimeType || m || "video/webm" });
    if (R.localOk !== true && R.localOk !== false && R.blob.size) {  // nothing came live (MP4 muxer): save the whole take now
      DB.putChunk(id, 0, R.blob).then(() => { R.localOk = true; R.draft.size = R.blob.size; R.draft.seconds = (Date.now() - R.t0) / 1000; return DB.putDraft(R.draft); })
        .then(() => { const n = $("#rec-prog", R.root); if (n && /save नहीं/.test(n.textContent)) n.querySelector("p").textContent = n.querySelector("p").textContent.replace(/⚠.*$/, "💾 device पर save है — upload बाद में भी कर सकते हैं"); })
        .catch(() => { R.localOk = false; }); }
    review(); };
  R.rec.start(1000); R.state = "rec"; R.t0 = Date.now();
  // iOS/MP4: some muxers hand out nothing until stop — say so instead of pretending the live copy exists
  setTimeout(() => { if (R && R.rec && R.state !== "idle" && R.localOk === null) { try { R.rec.requestData(); } catch {} setTimeout(() => { if (R && R.state !== "idle" && R.localOk === null) { local.textContent = "⚠ live save नहीं (इस browser का " + (R.draft.mime.includes("mp4") ? "MP4" : "format") + ")"; local.title = "यह browser recording के बीच data नहीं देता — stop दबाने पर पूरी recording device पर save होगी; तब तक page बंद न करें"; } }, 2000); } }, 4000);
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
  const saved = R.localOk === true || (R.draft && R.draft.size > 0 && R.localOk !== false);
  $("#rec-prog", R.root).innerHTML = `<p class="small muted">${(R.blob.size / 1024 / 1024).toFixed(1)} MB · ${R.blob.type} · ${saved ? "💾 device पर save है — upload बाद में भी कर सकते हैं" : "⚠ device पर save नहीं हो पाई — upload पूरा होने तक यह page खुला रखें"}</p>`;
}
async function upload() {
  const { api, toast, go, uploadFile, uploadControl, uploadProgressHtml } = R.ctx; const btn = $("#rec-upload", R.root); btn.disabled = true;
  const ext = R.blob.type.includes("mp4") ? "mp4" : "webm";
  const stamp = R.draft?.started || Date.now();
  const file = new File([R.blob], `recording_${stamp}.${ext}`, { type: R.blob.type }); // same name + size on retry → the server resumes
  const title = $("#rec-title", R.root).value.trim() || "Recording";
  const ctl = uploadControl ? uploadControl() : null;
  try {
    let pid = R.draft?.project_id;
    if (!pid) { const p = await api("POST", "/projects", { title, language: R.language, autopilot: $("#rec-ap", R.root)?.checked !== false, channel_id: R.ctx.S.channel }); pid = p.id;
      if (R.scriptIdea) api("PATCH", `/ideas/${R.scriptIdea.id}`, { project_id: p.id, status: "recorded" }).catch(() => {}); }
    if (R.draft) { R.draft.project_id = pid; R.draft.title = title; R.draft.uploading = true; DB.putDraft(R.draft).catch(() => {}); }
    await uploadFile(pid, file, (d, t, info) => { const box = $("#rec-prog", R.root); box.innerHTML = uploadProgressHtml ? uploadProgressHtml("upload", d, t, info, ctl) : `<p class="small muted">upload ${(d / t * 100).toFixed(0)}%</p>`;
      const pb = $("#up-pause", box); if (pb) pb.onclick = () => { ctl.paused ? ctl.resume() : ctl.pause(); pb.textContent = ctl.paused ? "▶ जारी रखें" : "⏸ रोकें"; }; }, { ctl });
    if (R.draft) await DB.drop(R.draft.id).catch(() => {});  // the server has it — only now the local copy goes
    toast("upload पूरा — auto edit शुरू"); R.blob = null; R.draft = null; go("/projects/" + pid);
  } catch (e) { toast(e.message + (R.draft ? " — recording device पर safe है, फिर से upload दबाएँ" : "")); btn.disabled = false; }
}
