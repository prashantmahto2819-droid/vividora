// Vividora dashboard — plain JS, no build step. Served by the API from web/dist.
import * as ED from "./editor.js";
import * as REC from "./record.js";

const S = { token: null, user: null, ws: null, projects: [], project: null, presets: null, channels: [], channel: localStorage.getItem("vividora_channel") || "",
            route: parseRoute(), poll: null, upload: null, playhead: 0, status: null, users: null, activity: null };
const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (t) => { t = Math.max(0, t || 0); const m = Math.floor(t / 60), s = (t % 60); return `${m}:${s < 10 ? "0" : ""}${s.toFixed(1)}`; };
const gb = (b) => b >= 1024 ** 3 ? (b / 1024 ** 3).toFixed(1) + " GB" : (b / 1024 ** 2).toFixed(0) + " MB";
const STATUS = {
  uploading: ["upload बाकी", ""], preparing: ["जाँच हो रही है", "working"], transcribing: ["transcript बन रहा है", "working"],
  cutting: ["कट ढूँढे जा रहे हैं", "working"], review_cuts: ["कट जाँचें", "review"], rendering: ["render हो रहा है", "working"],
  review_output: ["मंज़ूरी बाकी", "review"], approved: ["मंज़ूर", "approved"], failed: ["रुक गया", "failed"],
};

// ---------- api ----------
async function api(method, path, body, raw) {
  const h = {};
  if (S.token) h.authorization = "Bearer " + S.token;
  if (raw) h["content-type"] = "application/octet-stream"; else if (body) h["content-type"] = "application/json";
  if (raw && raw.offset != null) h["x-offset"] = raw.offset;
  const r = await fetch("/api" + path, { method, headers: h, body: raw ? raw.data : body ? JSON.stringify(body) : undefined });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { if (r.status === 401 && S.token) { logout(); } throw Object.assign(new Error(data.error || r.statusText), data); }
  return data;
}
function logout() { S.token = null; S.user = null; localStorage.removeItem("vividora_token"); go("/"); render(); }
function toast(msg, ms = 2600) { const t = document.createElement("div"); t.className = "toast"; t.textContent = msg; document.body.appendChild(t); setTimeout(() => t.remove(), ms); }

// ---------- routing ----------
function parseRoute() { const p = location.hash.replace(/^#/, "") || "/"; const [, kind, id] = p.match(/^\/(projects|users|status|new|settings|plan|analytics|record)?\/?([^/]*)/) || []; return { kind: kind || "home", id }; }
function go(path) { location.hash = path; }
window.addEventListener("hashchange", () => { S.route = parseRoute(); load().then(render); });

// ---------- data ----------
async function load() {
  if (!S.token) return;
  if (!S.presets) S.presets = await api("GET", "/presets").catch(() => null);
  S.channels = await api("GET", "/channels").catch(() => []);
  if (!S.channels.find((c) => c.id === S.channel)) S.channel = S.channels[0]?.id || "";
  S.projects = await api("GET", "/projects" + (S.channel && S.channels.length > 1 ? `?channel=${S.channel}` : ""));
  if (S.route.kind === "home") { const [t, i, a] = await Promise.all([api("GET", "/trends").catch(() => ({ trends: [] })), api("GET", `/ideas?channel=${S.channel}`).catch(() => []), api("GET", `/analytics?channel=${S.channel}`).catch(() => ({ videos: [] }))]); S.homeTrends = t.trends || []; S.ideas = i; S.analytics = a; }
  if (S.route.kind === "projects" && S.route.id) {
    S.project = await api("GET", "/projects/" + S.route.id).catch(() => null);
  } else S.project = null;
  if (S.route.kind === "status") { S.status = await api("GET", "/status"); S.activity = await api("GET", "/activity"); }
  if (S.route.kind === "users") S.users = await api("GET", "/users").catch(() => []);
  if (S.route.kind === "plan") { const [t, i, n, r] = await Promise.all([api("GET", "/trends").catch(() => ({ trends: [], setup: {} })), api("GET", `/ideas?channel=${S.channel}`).catch(() => []), api("GET", "/notify").catch(() => ({})), api("GET", "/refs").catch(() => [])]); S.trends = t; S.ideas = i; S.notify = n; S.refs = r; }
  if (S.route.kind === "analytics") S.analytics = await api("GET", `/analytics?channel=${S.channel}`).catch(() => ({ videos: [], learn: {} }));
  if (S.route.kind === "settings") { S.conns = await api("GET", "/connections").catch(() => ({ connections: [], setup: {} })); S.brand = await api("GET", `/brand?channel=${S.channel}`).catch(() => ({})); S.lib = await api("GET", "/library").catch(() => []); }
  schedulePoll();
}
function schedulePoll() {
  clearTimeout(S.poll);
  const busy = S.project && (["preparing", "transcribing", "cutting", "rendering"].includes(S.project.status) || (S.project.jobs || []).some((j) => ["queued", "running"].includes(j.status)));
  const anyBusy = S.projects.some((p) => ["preparing", "transcribing", "cutting", "rendering"].includes(p.status));
  if (busy || anyBusy || S.route.kind === "status") S.poll = setTimeout(() => load().then(renderSoft), busy ? 2500 : 6000);
}
function renderSoft() { if (document.activeElement && ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) { schedulePoll(); return; } render(); }

// ---------- views ----------
const EDITOR_STATUS = ["review_cuts", "rendering", "review_output", "approved"];
function render() {
  const app = $("#app");
  if (!S.token) { ED.unmount(); app.innerHTML = loginView(); bindLogin(); return; }
  const r = S.route;
  const detail = r.kind === "projects" && r.id;
  if (r.kind === "record") {
    if (app.dataset.mode !== "record") { ED.unmount(); app.dataset.mode = "record"; app.innerHTML = `<div id="recroot"></div>`; REC.mount($("#recroot"), { S, api, esc, toast, go, uploadFile }); }
    return;
  }
  if (app.dataset.mode === "record") REC.unmount();
  if (detail && S.project && EDITOR_STATUS.includes(S.project.status) && S.presets) {
    const key = "editor:" + S.project.id;
    if (app.dataset.mode !== key) { app.dataset.mode = key; app.innerHTML = `<div id="edroot"></div>`; }
    ED.mount($("#edroot"), S.project, { S, api, esc, fmt, toast, load, render, go, stylePreview });
    return;
  }
  app.dataset.mode = "shell"; ED.unmount();
  app.innerHTML = `<div class="shell">
    <aside class="rail ${detail || r.kind !== "home" ? "hidden-mobile" : ""}">
      <div class="rail-head"><a class="brand" href="#/"><i></i>Vividora</a>
        ${S.user.role !== "viewer" ? `<span class="row" style="gap:.3rem"><a class="btn quiet" href="#/record" title="camera + teleprompter">⏺</a><a class="btn primary" href="#/new">+ नया</a></span>` : ""}</div>
      ${S.channels.length ? `<div class="chsw"><select id="ch-switch" title="channel">${S.channels.map((c) => `<option value="${c.id}" ${c.id === S.channel ? "selected" : ""}>${esc(c.name)}${c.handle ? " · " + esc(c.handle) : ""}</option>`).join("")}</select>${S.user.role === "admin" ? `<a class="ibtn" href="#/settings" title="channels manage">⚙</a>` : ""}</div>` : ""}
      <div class="rail-list">${S.projects.length ? S.projects.map(projRow).join("") : `<p class="muted" style="padding:1rem">अभी कोई project नहीं। "+ नया" से पहली recording डालें।</p>`}</div>
      <div class="rail-foot"><span>${esc(S.user.name)} <span class="muted">· ${S.user.role}</span></span>
        <span class="row" style="gap:.1rem"><a class="btn quiet small" href="#/plan">plan</a><a class="btn quiet small" href="#/analytics">analytics</a><a class="btn quiet small" href="#/status">status</a><a class="btn quiet small" href="#/settings">channels</a>${S.user.role === "admin" ? `<a class="btn quiet small" href="#/users">users</a>` : ""}<button class="btn quiet small" id="logout">बाहर</button></span></div>
    </aside>
    <main class="main ${r.kind === "home" ? "wide" : ""}">${r.kind === "new" ? newView() : r.kind === "users" ? usersView() : r.kind === "status" ? statusView() : r.kind === "settings" ? settingsView() : r.kind === "plan" ? planView() : r.kind === "analytics" ? analyticsView() : detail ? (S.project ? projectView(S.project) : `<p>project नहीं मिला।</p>`) : homeView()}</main>
  </div>`;
  $("#logout").onclick = logout;
  const chs = $("#ch-switch"); if (chs) chs.onchange = () => { S.channel = chs.value; localStorage.setItem("vividora_channel", S.channel); load().then(render); };
  if (r.kind === "new") bindNew(); if (r.kind === "users") bindUsers(); if (r.kind === "settings") bindSettings(); if (r.kind === "plan") bindPlan(); if (r.kind === "analytics") bindAnalytics();
  if (detail && S.project) bindProject(S.project);
}

function projRow(p) {
  const [label, cls] = STATUS[p.status] || [p.status, ""];
  return `<a class="proj ${S.project && S.project.id === p.id ? "active" : ""}" href="#/projects/${p.id}">
    ${p.thumb_url ? `<img src="${p.thumb_url}" alt="">` : `<div class="ph"></div>`}
    <div><b>${esc(p.title)}</b><span class="status ${cls}">${label}</span></div></a>`;
}

function homeView() {
  const review = S.projects.filter((p) => p.status === "review_cuts" || p.status === "review_output");
  const working = S.projects.filter((p) => ["preparing", "transcribing", "cutting", "rendering"].includes(p.status));
  const approved = S.projects.filter((p) => p.status === "approved");
  const canEdit = S.user.role !== "viewer";
  const vids = (S.analytics?.videos || []); const views = vids.reduce((a, v) => a + (v.views || 0), 0);
  const ideas = (S.ideas || []).filter((i) => i.status === "approved").slice(0, 4);
  const trends = (S.homeTrends || []).slice(0, 6);
  const hour = new Date().getHours(); const greet = hour < 12 ? "सुप्रभात" : hour < 17 ? "नमस्ते" : "शुभ संध्या";
  const card = (p) => { const [label, cls] = STATUS[p.status] || [p.status, ""]; return `<a class="pcard" href="#/projects/${p.id}">
      <div class="pthumb">${p.thumb_url ? `<img src="${p.thumb_url}" alt="">` : `<div class="ph">${p.kind === "montage" ? "🎵" : "🎬"}</div>`}<span class="status ${cls}">${label}</span>${p.settings?.autopilot ? `<span class="ap">✈ autopilot</span>` : ""}</div>
      <div class="pbody"><b>${esc(p.title)}</b><span class="small muted">${p.meta?.duration ? fmt(p.meta.duration) + " · " : ""}${new Date(p.updated_at).toLocaleDateString("hi-IN")}</span>${["preparing", "transcribing", "cutting", "rendering"].includes(p.status) ? `<div class="progress"><i class="indet"></i></div>` : ""}</div></a>`; };
  return `<div class="home">
    <div class="hhero"><div><p class="kicker">${greet}, ${esc(S.user.name.split(" ")[0])}</p><h1>${review.length ? `${review.length} वीडियो आपकी मंज़ूरी का इंतज़ार कर रहे हैं` : working.length ? `${working.length} वीडियो पर काम चल रहा है` : "आज क्या बनाएँ?"}</h1>
      <p class="muted">Record करें या upload — Vividora cuts, captions, zoom, music, Shorts और titles तैयार कर देगा। आप सिर्फ़ approve करें।</p></div>
      ${canEdit ? `<div class="hactions"><a class="hbtn" href="#/record"><i>⏺</i><b>Record</b><span>camera + teleprompter</span></a><a class="hbtn" href="#/new"><i>⬆</i><b>Upload</b><span>recording / clips</span></a><a class="hbtn" href="#/new?type=montage"><i>🎵</i><b>Montage</b><span>music + clips</span></a><a class="hbtn" href="#/plan"><i>✨</i><b>Plan</b><span>trends · ideas · script</span></a></div>` : ""}</div>
    <div class="hstats"><div><b>${review.length}</b><span>मंज़ूरी बाकी</span></div><div><b>${working.length}</b><span>चल रहे</span></div><div><b>${approved.length}</b><span>मंज़ूर</span></div><div><b>${vids.length}</b><span>published</span></div><div><b>${views.toLocaleString("en-IN")}</b><span>views</span></div></div>
    ${review.length ? `<div class="hsec"><div class="row between"><h2>जाँच के लिए</h2></div><div class="pgrid">${review.map(card).join("")}</div></div>` : ""}
    ${working.length ? `<div class="hsec"><h2>चल रहा है</h2><div class="pgrid">${working.map(card).join("")}</div></div>` : ""}
    <div class="hcols">
      <div class="hsec"><div class="row between"><h2>हाल के projects</h2><a class="small muted" href="#/new">+ नया</a></div>${S.projects.length ? `<div class="pgrid">${S.projects.slice(0, 8).map(card).join("")}</div>` : `<div class="empty"><p>अभी कोई project नहीं।</p><a class="btn primary" href="#/record">पहली recording करें</a></div>`}</div>
      <div class="hside"><div class="hsec"><div class="row between"><h2>Record करने के लिए</h2><a class="small muted" href="#/plan">सब</a></div>${ideas.length ? `<ul class="hlist">${ideas.map((i) => `<li><a href="#/record"><b>${esc(i.title)}</b>${i.script ? `<span class="tag manual">script ✓</span>` : ""}</a></li>`).join("")}</ul>` : `<p class="small muted">Plan में ideas बनाएँ → "बनाना है" में रखें, यहाँ दिखेंगे।</p>`}</div>
      <div class="hsec"><div class="row between"><h2>आज trending</h2><a class="small muted" href="#/plan">radar</a></div>${trends.length ? `<ul class="hlist">${trends.map((r) => `<li>${r.url ? `<a href="${r.url}" target="_blank" rel="noopener">${esc(r.title)}</a>` : esc(r.title)}<span class="small muted">${r.meta?.traffic ? r.meta.traffic + "+" : r.meta?.channel ? esc(r.meta.channel) : ""}</span></li>`).join("")}</ul>` : `<p class="small muted">Plan → "ताज़ा करें"</p>`}</div></div>
    </div></div>`;
}
function loginView() {
  return `<div class="login"><form id="login"><div class="brand"><i></i>Vividora</div><p class="muted">आपका video studio</p>
    <div class="field"><label>Email</label><input name="email" type="email" autocomplete="username" required></div>
    <div class="field"><label>Password</label><input name="password" type="password" autocomplete="current-password" required></div>
    <div id="login-err"></div><button class="btn primary" style="width:100%;justify-content:center">अंदर जाएँ</button></form></div>`;
}
function bindLogin() {
  $("#login").onsubmit = async (e) => {
    e.preventDefault(); const f = e.target;
    try { const r = await api("POST", "/auth/login", { email: f.email.value, password: f.password.value });
      S.token = r.token; S.user = r.user; S.ws = r.workspace; localStorage.setItem("vividora_token", r.token);
      await load(); render();
    } catch (err) { $("#login-err").innerHTML = `<div class="note err">${esc(err.message)}</div>`; }
  };
}

function newView() {
  const ideaId = (location.hash.match(/idea=([0-9a-f]+)/) || [])[1]; const idea = ideaId && (S.ideas || []).find((i) => i.id === ideaId);
  const chn = S.channels.find((c) => c.id === S.channel);
  return `<h1>नई recording</h1>${chn ? `<p class="small muted">channel: <b style="color:${esc(chn.color || "#F2B33D")}">${esc(chn.name)}</b> — brand kit, pattern और connections इसी के लगेंगे (बाएँ ऊपर से बदलें)</p>` : ""}${idea ? `<div class="note">idea: <b>${esc(idea.title)}</b> — upload के बाद यह "record हो गया" में चला जाएगा।</div>` : ""}<p class="muted">पहले नाम दें, फिर फ़ाइल चुनें। upload बीच में टूटे तो वहीं से आगे बढ़ता है।</p>
    <div class="choices" style="margin-bottom:1rem"><label class="chip on"><input type="radio" name="ptype" value="talking_head" checked>🎙️ Recording (मेरी आवाज़ वाला वीडियो)</label><label class="chip"><input type="radio" name="ptype" value="montage">🎵 Montage (music + clips, बिना voice)</label></div>
    <form id="new"><div class="field"><label>वीडियो का नाम</label><input name="title" required placeholder="जैसे: 4 बजे उठने वाला लड़का" value="${idea ? esc(idea.title) : ""}"></div>
    <div class="field"><label>भाषा</label><select name="language"><option value="auto">अपने-आप पहचानें (हिंदी / English / Hinglish)</option><option value="hi">हिंदी</option><option value="en">English</option></select></div>
    <div class="drop" id="drop" data-upload="1"><input type="file" id="file" accept="video/*,audio/*,.mkv,.mts" multiple hidden><b>फ़ाइल(ें) यहाँ छोड़ें या चुनें</b><br><span class="muted small">mp4, mov, mkv, webm · 20 GB तक · कई clips चुनें तो क्रम से एक timeline पर जुड़ेंगी</span><div id="fname" class="small" style="margin-top:.5rem"></div></div>
    <label class="chk" style="margin:.5rem 0;display:flex;gap:.5rem;align-items:center"><input type="checkbox" name="autopilot" checked> <span><b>✈ Autopilot</b> — upload के बाद पूरा edit अपने-आप (cuts, captions, zoom, music, Shorts, titles); आप सिर्फ़ देखकर approve करें</span></label>
    <div id="up-progress"></div>
    <div class="actionbar"><a class="btn" href="#/">रद्द</a><button class="btn primary" id="start" disabled>upload शुरू करें</button></div></form>`;
}
function bindNew() {
  const drop = $("#drop"), file = $("#file"); let chosen = null; let chosenAll = [];
  drop.onclick = () => file.click();
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); chosenAll = [...e.dataTransfer.files]; chosen = chosenAll[0]; pick(); };
  file.onchange = () => { chosenAll = [...file.files]; chosen = chosenAll[0]; pick(); };
  function pick() { if (!chosen) return; $("#fname").innerHTML = chosenAll.length > 1 ? chosenAll.map((f, i) => `${i + 1}. ${esc(f.name)} · ${gb(f.size)}`).join("<br>") : `${esc(chosen.name)} · ${gb(chosen.size)}`; $("#start").disabled = false; }
  let ptype = "talking_head";
  if (/type=montage/.test(location.hash)) { const r = document.querySelector('input[name=ptype][value=montage]'); if (r) { r.checked = true; r.dispatchEvent(new Event("change")); } }
  document.querySelectorAll("input[name=ptype]").forEach((i) => (i.onchange = () => { ptype = i.value; document.querySelectorAll(".chip").forEach((c) => c.classList.toggle("on", c.contains(i))); const mont = ptype === "montage"; drop.style.display = mont ? "none" : ""; $("#start").textContent = mont ? "montage project बनाएँ" : "upload शुरू करें"; $("#start").disabled = mont ? false : !chosen; }));
  $("#new").onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target;
    if (ptype === "montage") { $("#start").disabled = true; try { const p = await api("POST", "/projects", { title: f.title.value, language: f.language.value, kind: "montage", channel_id: S.channel }); go("/projects/" + p.id); } catch (err) { toast(err.message); $("#start").disabled = false; } return; }
    if (!chosen) return;
    $("#start").disabled = true;
    try {
      const p = await api("POST", "/projects", { title: f.title.value, language: f.language.value, autopilot: f.autopilot.checked, channel_id: S.channel });
      const ideaId = (location.hash.match(/idea=([0-9a-f]+)/) || [])[1]; if (ideaId) api("PATCH", `/ideas/${ideaId}`, { project_id: p.id, status: "recorded" }).catch(() => {});
      if (chosenAll.length > 1) {
        for (let i = 0; i < chosenAll.length; i++) { const f = chosenAll[i]; await uploadFile(p.id, f, (done, total) => { $("#up-progress").innerHTML = `<p class="small muted">clip ${i + 1}/${chosenAll.length} · ${gb(done)} / ${gb(total)}</p><div class="progress"><i style="width:${(done / total * 100).toFixed(1)}%"></i></div>`; }, { clip: true, start: i === chosenAll.length - 1 }); }
      } else
      await uploadFile(p.id, chosen, (done, total) => { $("#up-progress").innerHTML = `<p class="small muted">${gb(done)} / ${gb(total)}</p><div class="progress"><i style="width:${(done / total * 100).toFixed(1)}%"></i></div>`; });
      toast("upload पूरा — जाँच शुरू"); go("/projects/" + p.id);
    } catch (err) { $("#up-progress").innerHTML = `<div class="note err">${esc(err.message)} — दोबारा कोशिश करें, upload वहीं से चलेगा।</div>`; $("#start").disabled = false; }
  };
}
async function uploadFile(pid, file, onProgress, opts = {}) {
  const up = await api("POST", `/projects/${pid}/uploads`, { filename: file.name, size: file.size, clip: !!opts.clip });
  let off = up.received; const chunk = up.chunk;
  while (off < file.size) {
    const part = file.slice(off, Math.min(file.size, off + chunk));
    let r;
    try { r = await api("PUT", `/projects/${pid}/uploads/${up.upload_id}/chunk`, null, { data: part, offset: off }); }
    catch (err) { if (err.received != null) { off = err.received; continue; } throw err; }
    off = r.received; onProgress(off, file.size);
  }
  return api("POST", `/projects/${pid}/uploads/${up.upload_id}/finish`, { start: opts.start !== false });
}

function hasOverrides(c) { return c && (c.position || c.primary || c.font || (c.size_scale && c.size_scale != 1)); }
function stylePreview(cs, on) {
  const words = ["मेहनत", "कभी", "बेकार", "नहीं"];
  const hiIdx = cs.mode === "line" ? -1 : 2;
  const box = cs.box === "line" ? `background:${cs.box_color || "#000"}CC;padding:.15em .4em;border-radius:4px;` : "";
  const glow = cs.glow ? `text-shadow:0 0 6px ${cs.outline_color}, 0 0 12px ${cs.outline_color};` : "";
  const stroke = cs.outline ? `-webkit-text-stroke:${Math.max(0.5, cs.outline * 160)}px ${cs.outline_color || "#000"};paint-order:stroke fill;` : "";
  const size = Math.round(10 + (cs.size || 0.06) * 120);
  const n = Math.min(words.length, cs.max_words || 4);
  const txt = words.slice(0, n).map((w, i) => {
    const t = cs.uppercase ? w : w;
    if (i === hiIdx || (hiIdx >= n && i === n - 1)) {
      if (cs.box === "word") return `<span style="background:${cs.box_color};color:${cs.highlight};padding:0 .2em;border-radius:.2em;${stroke}">${t}</span>`;
      return `<span style="color:${cs.highlight};${cs.mode === "pop" ? "transform:scale(1.15);display:inline-block;" : ""}${stroke}">${t}</span>`;
    }
    return `<span style="${stroke}">${t}</span>`;
  }).join(" ");
  const pos = cs.position === "center" ? "center" : cs.position === "top" ? "flex-start" : "flex-end";
  return `<label class="stylecard ${on ? "on" : ""}" title="${esc(cs.description || "")}"><input type="radio" name="cstyle" value="${cs.id}" ${on ? "checked" : ""}>
    <div class="scr" style="justify-content:${pos}"><div style="font-family:'${cs.font}',var(--font);font-weight:${cs.bold === false ? 400 : 800};font-size:${size}px;color:${cs.primary};line-height:1.15;${box}${glow}text-align:center">${txt}</div></div>
    <b>${esc(cs.label)}</b></label>`;
}

// ---------- project ----------
function projectView(p) {
  const [label, cls] = STATUS[p.status] || [p.status, ""];
  const proxy = p.assets.find((a) => a.kind === "proxy");
  const job = p.jobs.find((j) => ["running", "queued"].includes(j.status));
  const canEdit = S.user.role !== "viewer";
  let body = "";
  if (p.status === "uploading") body = `<div class="note">upload पूरा नहीं हुआ। <a href="#/new">नई recording</a> से दोबारा डालें।</div>`;
  else if (["preparing", "transcribing", "cutting"].includes(p.status)) body = workingView(p, job);
  else if (p.status === "failed") body = `<div class="note err"><b>रुक गया:</b> ${esc(p.status_note)}</div>${canEdit ? `<button class="btn" id="retry-cuts">कट दोबारा ढूँढें</button>` : ""}`;
  else body = reviewView(p, proxy, canEdit) + renderSection(p, canEdit) + outputsSection(p, canEdit);
  return `<div class="row between"><div><a class="btn quiet" href="#/" style="padding-left:0">← सभी</a><h1 id="title" ${canEdit ? 'contenteditable="true" spellcheck="false"' : ""}>${esc(p.title)}</h1>
      <span class="status ${cls}">${label}</span> <span class="muted small">${esc(p.status_note || "")}</span></div>
      ${canEdit ? `<button class="btn danger quiet" id="del">हटाएँ</button>` : ""}</div>
    ${p.meta.duration ? `<p class="muted small">${fmt(p.meta.duration)} · ${p.meta.width}×${p.meta.height} · ${p.meta.fps} fps · भाषा ${{hi:"हिंदी",en:"English",auto:"पहचान बाकी"}[p.language] || p.language} · आवाज़ ${p.meta.denoise === "deepfilternet" ? "DeepFilterNet से साफ़" : p.meta.denoise === "ffmpeg" ? "साफ़ की गई" : "जैसी थी"}</p>` : ""}
    ${body}`;
}
function workingView(p, job) {
  return `<div class="section"><h2>${(STATUS[p.status] || [])[0]}</h2>
    <div class="progress"><i style="width:${job ? job.progress : 0}%"></i></div>
    <p class="muted small" style="margin-top:.5rem">${esc(job ? (job.message || "") : "")}${p.status === "transcribing" ? " · GPU worker चाहिए (status पेज देखें)" : ""}</p></div>`;
}
function reviewView(p, proxy, canEdit) {
  const edl = p.edl || { cuts: [], duration: p.meta.duration || 0, stats: {} };
  const dur = edl.duration || 1;
  const cuts = edl.cuts || [];
  const words = (p.transcript?.segments || []).flatMap((s) => s.words || []);
  return `<div class="section"><div class="row between"><h2>कट की जाँच</h2>
      <span class="muted small">${edl.stats.cuts || 0} कट · ${(edl.stats.removed_seconds || 0).toFixed(1)}s हटेंगे · अंतिम ${fmt(edl.stats.final_seconds ?? dur)}</span></div>
    ${proxy ? `<video class="preview" id="preview" src="${proxy.url}" controls playsinline preload="metadata"></video>` : ""}
    <div class="timeline"><div class="track" id="track">
      <div class="keep" style="left:0;width:100%"></div>
      ${cuts.map((c) => `<div class="cut ${c.enabled ? "" : "off"}" data-id="${c.id}" style="left:${(c.start / dur * 100).toFixed(2)}%;width:${Math.max(0.3, (c.end - c.start) / dur * 100).toFixed(2)}%" title="${c.reason} ${fmt(c.start)}–${fmt(c.end)}"></div>`).join("")}
      <div class="play" id="play" style="left:0"></div></div>
      <div class="ticks"><span>0:00</span><span>${fmt(dur / 2)}</span><span>${fmt(dur)}</span></div></div>
    ${cuts.length ? `<ul class="cutlist">${cuts.map((c) => `<li class="${c.enabled ? "" : "off"}" data-id="${c.id}">
        <label><input type="checkbox" class="cut-on" data-id="${c.id}" ${c.enabled ? "checked" : ""} ${canEdit ? "" : "disabled"}></label>
        <div><span class="reason ${c.reason}">${{ silence: "चुप्पी", filler: "अं-आं", retake: "दोबारा बोला" }[c.reason] || c.reason}</span> ${c.text ? `<span class="small muted">“${esc(c.text)}”</span>` : ""}</div>
        <button class="btn quiet small seek" data-t="${c.start}"><span class="t">${fmt(c.start)}</span> → ${fmt(c.end)}</button></li>`).join("")}</ul>`
      : `<p class="muted">कोई कट नहीं सुझाया गया।</p>`}
    ${canEdit ? `<div class="row" style="margin-top:.75rem"><button class="btn" id="save-cuts">कट सेव करें</button>
      <label class="small muted">रुकावट की सीमा <input type="number" id="max-pause" step="0.1" min="0.2" max="3" value="${edl.options?.max_pause ?? 0.55}" style="width:70px;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:.2rem .4rem"> s</label>
      <button class="btn quiet" id="recut">दोबारा ढूँढें</button></div>` : ""}
    ${words.length ? `<details style="margin-top:1rem"><summary class="muted">transcript (${words.length} शब्द) — शब्द पर क्लिक करके वहाँ जाएँ</summary>
      <p class="words" id="words">${words.map((w, i) => `<span data-i="${i}" data-s="${w.start}" data-e="${w.end}">${esc(w.w)}</span>`).join(" ")}</p></details>` : ""}
  </div>`;
}
function renderSection(p, canEdit) {
  if (!canEdit || !S.presets) return "";
  const d = p.render_defaults;
  return `<div class="section"><h2>render</h2>
    <div class="field"><label>कहाँ के लिए</label><div class="choices">${S.presets.platforms.map((pl) => `<label class="chip ${d.presets.includes(pl.id) ? "on" : ""}"><input type="checkbox" name="preset" value="${pl.id}" ${d.presets.includes(pl.id) ? "checked" : ""}>${esc(pl.label)}</label>`).join("")}</div></div>
    <div class="field"><label>caption style</label><div class="styles">${S.presets.caption_styles.map((cs) => stylePreview(cs, d.caption_style === cs.id)).join("")}</div></div>
    <details class="capopts" ${hasOverrides(d.captions) ? "open" : ""}><summary class="muted">caption को अपने हिसाब से बदलें (आकार, जगह, रंग, font)</summary>
      <div class="row" style="margin-top:.6rem">
        <div class="field"><label>आकार</label><input type="range" id="cap-size" min="0.6" max="1.8" step="0.05" value="${d.captions?.size_scale ?? 1}"></div>
        <div class="field"><label>जगह</label><select id="cap-pos"><option value="">style जैसी</option><option value="bottom" ${d.captions?.position === "bottom" ? "selected" : ""}>नीचे</option><option value="center" ${d.captions?.position === "center" ? "selected" : ""}>बीच में</option><option value="top" ${d.captions?.position === "top" ? "selected" : ""}>ऊपर</option></select></div>
        <div class="field"><label>अक्षर का रंग</label><input type="color" id="cap-primary" value="${d.captions?.primary || "#ffffff"}"></div>
        <div class="field"><label>highlight रंग</label><input type="color" id="cap-highlight" value="${d.captions?.highlight || "#ffd400"}"></div>
        <div class="field"><label>font</label><select id="cap-font"><option value="">style जैसा</option>${(S.presets.fonts || []).map((f) => `<option ${d.captions?.font === f ? "selected" : ""}>${f}</option>`).join("")}</select></div>
        <label class="small muted" style="align-self:end;padding-bottom:1rem"><input type="checkbox" id="cap-usecolors" ${d.captions?.primary ? "checked" : ""}> ऊपर के रंग लागू करें</label>
      </div></details>
    <div class="row"><div class="field" style="flex:1;min-width:200px"><label>शुरुआत का hook (3 सेकंड, खाली छोड़ें तो नहीं लगेगा)</label><input id="hook" value="${esc(d.hook?.text || "")}" placeholder="4 बजे उठने वाला लड़का"></div>
      <div class="field"><label>9:16 में चेहरा कहाँ</label><select id="focus"><option value="0.5" ${d.focus_x == 0.5 ? "selected" : ""}>बीच</option><option value="0.25" ${d.focus_x == 0.25 ? "selected" : ""}>बाएँ</option><option value="0.75" ${d.focus_x == 0.75 ? "selected" : ""}>दाएँ</option></select></div></div>
    <div class="actionbar"><button class="btn primary" id="render" ${p.status === "rendering" ? "disabled" : ""}>${p.status === "rendering" ? "render हो रहा है…" : "render करें"}</button></div></div>`;
}
function outputsSection(p, canEdit) {
  const outs = p.assets.filter((a) => a.kind === "render");
  if (!outs.length && p.status !== "rendering") return "";
  const job = p.jobs.find((j) => j.kind === "render" && ["running", "queued"].includes(j.status));
  return `<div class="section"><div class="row between"><h2>तैयार वीडियो</h2>
      ${p.status === "review_output" && S.user.role === "admin" ? `<button class="btn primary" id="approve">मंज़ूरी दें</button>` : p.status === "approved" ? `<span class="status approved">मंज़ूर</span>` : ""}</div>
    ${p.status === "rendering" ? `<div class="progress"><i style="width:${job ? job.progress : 0}%"></i></div><p class="muted small" style="margin-top:.4rem">${esc(job?.message || "")}</p>` : ""}
    <div class="outputs">${outs.map((a) => { const pl = S.presets?.platforms.find((x) => x.id === a.label); const srt = p.assets.find((s) => s.kind === "subtitle" && s.label === a.label);
      return `<div class="output ${a.meta.height > a.meta.width ? "vertical" : ""}"><video src="${a.url}" controls playsinline preload="metadata"></video>
        <div class="row between" style="margin-top:.4rem"><b>${esc(pl ? pl.label : a.label)}</b><span class="muted small">${fmt(a.meta.duration)} · ${gb(a.size)}</span></div>
        <div class="row"><a class="btn small" href="${a.url}&download=1">download</a>${srt ? `<a class="btn quiet small" href="${srt.url}&download=1">SRT</a>` : ""}</div></div>`; }).join("")}</div>
    ${p.status === "review_output" && S.user.role !== "admin" ? `<p class="muted small" style="margin-top:.75rem">मंज़ूरी admin देंगे।</p>` : ""}</div>`;
}

function bindProject(p) {
  const title = $("#title");
  if (title && title.isContentEditable) title.onblur = async () => { const t = title.textContent.trim(); if (t && t !== p.title) { await api("PATCH", `/projects/${p.id}`, { title: t }); toast("नाम बदला"); load().then(render); } };
  const del = $("#del"); if (del) del.onclick = async () => { if (confirm(`"${p.title}" और उसकी सारी फ़ाइलें हटाएँ?`)) { await api("DELETE", `/projects/${p.id}`); go("/"); } };
  const retry = $("#retry-cuts"); if (retry) retry.onclick = () => api("POST", `/projects/${p.id}/recut`, {}).then(() => load().then(render));
  const video = $("#preview"), track = $("#track"), play = $("#play");
  const dur = p.edl?.duration || p.meta.duration || 1;
  if (video && track) {
    video.ontimeupdate = () => { play.style.left = (video.currentTime / dur * 100) + "%"; const now = $("#words span.now"); if (now) now.classList.remove("now");
      const w = [...document.querySelectorAll("#words span")].find((s) => +s.dataset.s <= video.currentTime && +s.dataset.e >= video.currentTime); if (w) w.classList.add("now"); };
    track.onclick = (e) => { const r = track.getBoundingClientRect(); video.currentTime = (e.clientX - r.left) / r.width * dur; video.play(); };
    document.querySelectorAll(".seek").forEach((b) => (b.onclick = () => { video.currentTime = Math.max(0, +b.dataset.t - 0.6); video.play(); }));
    document.querySelectorAll("#words span").forEach((s) => (s.onclick = () => { video.currentTime = +s.dataset.s; video.play(); }));
  }
  document.querySelectorAll(".cut-on").forEach((cb) => (cb.onchange = () => {
    const id = cb.dataset.id; const c = p.edl.cuts.find((x) => x.id === id); c.enabled = cb.checked;
    $(`.track .cut[data-id="${id}"]`)?.classList.toggle("off", !cb.checked); $(`.cutlist li[data-id="${id}"]`)?.classList.toggle("off", !cb.checked);
    document.querySelectorAll("#words span").forEach((s) => { const mid = (+s.dataset.s + +s.dataset.e) / 2; s.classList.toggle("cut", p.edl.cuts.some((x) => x.enabled && x.start <= mid && mid <= x.end)); });
  }));
  const save = $("#save-cuts"); if (save) save.onclick = async () => { await api("PATCH", `/projects/${p.id}`, { edl: { cuts: p.edl.cuts } }); toast("कट सेव हुए"); load().then(render); };
  const recut = $("#recut"); if (recut) recut.onclick = async () => { await api("POST", `/projects/${p.id}/recut`, { options: { max_pause: +$("#max-pause").value } }); load().then(render); };
  document.querySelectorAll(".stylecard input").forEach((i) => (i.onchange = () => { document.querySelectorAll(".stylecard").forEach((c) => c.classList.remove("on")); i.closest(".stylecard").classList.add("on"); }));
  document.querySelectorAll(".chip input").forEach((i) => (i.onchange = () => { if (i.type === "radio") i.closest(".choices").querySelectorAll(".chip").forEach((c) => c.classList.remove("on")); i.closest(".chip").classList.toggle("on", i.checked); }));
  const rb = $("#render"); if (rb) rb.onclick = async () => {
    const presets = [...document.querySelectorAll('input[name=preset]:checked')].map((i) => i.value);
    const caption_style = $('input[name=cstyle]:checked')?.value;
    const useColors = $("#cap-usecolors")?.checked;
    const captions = { size_scale: +($("#cap-size")?.value || 1), position: $("#cap-pos")?.value || "", font: $("#cap-font")?.value || "",
      primary: useColors ? $("#cap-primary").value : "", highlight: useColors ? $("#cap-highlight").value : "" };
    try { await api("POST", `/projects/${p.id}/render`, { presets, caption_style, captions, hook: { text: $("#hook").value.trim(), seconds: 3 }, focus_x: +$("#focus").value }); toast("render शुरू"); load().then(render); }
    catch (err) { toast(err.message); }
  };
  const ap = $("#approve"); if (ap) ap.onclick = async () => { if (confirm("यह वीडियो मंज़ूर करें? इसके बाद download/publish किया जा सकेगा।")) { await api("POST", `/projects/${p.id}/approve`); toast("मंज़ूर"); load().then(render); } };
}

// ---------- users / status ----------
function usersView() {
  return `<h1>Users</h1><p class="muted">admin सब कर सकता है और आख़िरी मंज़ूरी देता है · editor upload, कट और render कर सकता है · viewer सिर्फ़ देख सकता है</p>
    <table><tr><th>नाम</th><th>email</th><th>role</th><th>आख़िरी login</th><th></th></tr>${(S.users || []).map((u) => `<tr class="${u.active ? "" : "muted"}"><td>${esc(u.name)}</td><td>${esc(u.email)}</td>
      <td><select data-id="${u.id}" class="role" ${u.id === S.user.id ? "disabled" : ""}>${["admin", "editor", "viewer"].map((r) => `<option ${u.role === r ? "selected" : ""}>${r}</option>`).join("")}</select></td>
      <td class="small">${u.last_login_at ? new Date(u.last_login_at).toLocaleString("hi-IN") : "कभी नहीं"}</td>
      <td>${u.id !== S.user.id ? `<button class="btn quiet small toggle" data-id="${u.id}" data-active="${u.active}">${u.active ? "बंद करें" : "चालू करें"}</button>` : ""}</td></tr>`).join("")}</table>
    <div class="section"><h2>नया user</h2><form id="adduser" class="row">
      <div class="field"><label>नाम</label><input name="name" required></div><div class="field"><label>email</label><input name="email" type="email" required></div>
      <div class="field"><label>password</label><input name="password" type="password" minlength="8" required></div>
      <div class="field"><label>role</label><select name="role"><option>editor</option><option>viewer</option><option>admin</option></select></div>
      <button class="btn primary">जोड़ें</button></form></div>
    <div class="section"><h2>अपना password</h2><form id="pw" class="row"><div class="field"><label>मौजूदा</label><input name="current" type="password" required></div><div class="field"><label>नया</label><input name="new" type="password" minlength="8" required></div><button class="btn">बदलें</button></form></div>`;
}
function bindUsers() {
  document.querySelectorAll(".role").forEach((s) => (s.onchange = () => api("PATCH", `/users/${s.dataset.id}`, { role: s.value }).then(() => toast("role बदला")).catch((e) => toast(e.message))));
  document.querySelectorAll(".toggle").forEach((b) => (b.onclick = () => api("PATCH", `/users/${b.dataset.id}`, { active: b.dataset.active !== "true" }).then(() => load().then(render))));
  $("#adduser").onsubmit = async (e) => { e.preventDefault(); const f = e.target; try { await api("POST", "/users", { name: f.name.value, email: f.email.value, password: f.password.value, role: f.role.value }); toast("user जुड़ा"); load().then(render); } catch (err) { toast(err.message); } };
  $("#pw").onsubmit = async (e) => { e.preventDefault(); const f = e.target; try { await api("POST", "/auth/password", { current: f.current.value, new: f.new.value }); toast("password बदला"); f.reset(); } catch (err) { toast(err.message); } };
}
function statusView() {
  const st = S.status || { workers: [], jobs: {}, disk: {} };
  const online = (w) => Date.now() - new Date(w.last_seen_at).getTime() < 90000;
  return `<h1>Status</h1>
    <div class="section"><h2>workers</h2>${st.workers.length ? `<table><tr><th>नाम</th><th>काम</th><th>हालत</th><th>जानकारी</th></tr>${st.workers.map((w) => `<tr><td>${esc(w.name)}</td><td class="small">${w.kinds.join(", ")}</td><td><span class="status ${online(w) ? "approved" : "failed"}">${online(w) ? "online" : "offline · " + new Date(w.last_seen_at).toLocaleTimeString("hi-IN")}</span></td><td class="small muted">${esc(Object.entries(w.info || {}).map(([k, v]) => `${k}: ${v}`).join(" · "))}</td></tr>`).join("")}</table>` : `<p class="muted">अभी कोई worker नहीं जुड़ा। Docker का worker और Windows का GPU worker चालू करें।</p>`}
      ${!st.workers.some((w) => w.kinds.includes("transcribe") && online(w)) ? `<div class="note">transcript बनाने वाला worker online नहीं है — नए वीडियो "transcript बन रहा है" पर रुकेंगे। Windows PC पर GPU worker चलाएँ।</div>` : ""}</div>
    <div class="section"><h2>queue</h2><p>${Object.entries(st.jobs).map(([k, v]) => `${k}: <b>${v}</b>`).join(" · ") || "खाली"}</p></div>
    <div class="section"><h2>archive</h2><p class="small muted">${st.archive?.backend ? `backend: <b>${esc(st.archive.backend)}</b>${st.archive.remote ? ` · ${esc(st.archive.remote)}` : ""} · मंज़ूरी के ${st.archive.after_days} दिन बाद raw files अपने-आप archive` : ".env में ARCHIVE_RCLONE_REMOTE (Google Drive) या ARCHIVE_ROOT सेट करें — docs/google-drive.md"}</p></div>
    <div class="section"><h2>disk</h2>${Object.entries(st.disk).map(([k, d]) => `<p>${k}: ${gb(d.used)} / ${gb(d.total)} <span class="muted">(${gb(d.free)} खाली)</span></p><div class="progress"><i style="width:${(d.used / d.total * 100).toFixed(0)}%"></i></div>`).join("")}</div>
    <div class="section"><h2>हाल की गतिविधि</h2><table>${(S.activity || []).slice(0, 40).map((a) => `<tr><td class="small muted">${new Date(a.created_at).toLocaleString("hi-IN")}</td><td class="small">${esc(a.user_name || "system")}</td><td class="small">${esc(a.action)} ${esc(a.detail?.title || a.detail?.email || a.detail?.file || (a.detail?.presets || []).join(",") || "")}</td></tr>`).join("")}</table></div>`;
}

// ---------- settings / connections ----------
const PLAT = { youtube: "YouTube", instagram: "Instagram", facebook: "Facebook" };
function settingsView() {
  const c = S.conns || { connections: [], setup: {} }; const st = c.setup || {}; const admin = S.user.role === "admin";
  const chn = S.channels.find((c) => c.id === S.channel);
  return `<h1>Channels</h1>
    <div class="section" style="margin-top:0;border:0;padding-top:0"><div class="row between"><h2>आपके channels · ${S.channels.length}</h2>${admin ? `<button class="btn small" id="ch-add">+ नया channel</button>` : ""}</div>
      <div class="chgrid">${S.channels.map((c) => `<div class="chcard ${c.id === S.channel ? "on" : ""}" data-ch="${c.id}" style="--c:${esc(c.color || "#F2B33D")}"><b>${esc(c.name)}</b><span class="small muted">${esc(c.handle || "")} · ${esc(c.niche || "niche नहीं")} · ${c.projects} projects · ${(c.platforms || []).join(", ") || "कोई connection नहीं"}</span></div>`).join("")}</div>
      ${chn && admin ? `<form id="ch-edit" class="row" style="align-items:flex-end;margin-top:.75rem"><input type="hidden" name="id" value="${chn.id}">
        <div class="field"><label>नाम</label><input name="name" value="${esc(chn.name)}" required></div><div class="field"><label>handle</label><input name="handle" value="${esc(chn.handle || "")}" placeholder="@theprashantmahto"></div>
        <div class="field" style="flex:1;min-width:220px"><label>niche (ideas/trends/titles इसी से)</label><input name="niche" value="${esc(chn.niche || "")}" placeholder="Hindi motivation, success stories, self-improvement"></div>
        <div class="field"><label>भाषा</label><select name="language"><option value="hi" ${chn.language === "hi" ? "selected" : ""}>हिंदी</option><option value="en" ${chn.language === "en" ? "selected" : ""}>English</option><option value="auto" ${chn.language === "auto" ? "selected" : ""}>auto</option></select></div>
        <div class="field"><label>रंग</label><input type="color" name="color" value="${esc(chn.color || "#F2B33D")}"></div>
        <div class="field" style="flex:1;min-width:200px"><label>trend keywords (comma)</label><input name="keywords" value="${esc((chn.keywords || []).join(", "))}" placeholder="motivation, success, hindi story"></div>
        <button class="btn primary">सेव</button>${S.channels.length > 1 ? `<button type="button" class="btn quiet danger" id="ch-del">हटाएँ</button>` : ""}</form>` : ""}</div>
    <p class="muted">नीचे की settings (connections, brand kit) <b>${esc(chn?.name || "")}</b> channel की हैं। हर upload से पहले आपकी मंज़ूरी ज़रूरी है — connection सिर्फ़ रास्ता खोलता है।</p>
    ${st.dry_run ? `<div class="note">PUBLISH_DRY_RUN चालू है — publish असली नहीं होगा (test mode)।</div>` : ""}
    ${!st.public_url ? `<div class="note err">.env में <b>PUBLIC_URL</b> नहीं है (जैसे https://studio.yourdomain.com — Cloudflare Tunnel का पता)। बिना इसके Google/Meta login वापस नहीं आ सकता और Instagram/Facebook वीडियो नहीं ले पाएँगे।</div>` : ""}
    <div class="section"><div class="row between"><h2>जुड़े हुए</h2>${admin ? `<span class="row"><button class="btn" id="c-yt" ${st.youtube ? "" : "disabled"} title="${st.youtube ? "" : ".env में YT_CLIENT_ID/YT_CLIENT_SECRET चाहिए"}">+ YouTube</button><button class="btn" id="c-meta" ${st.meta ? "" : "disabled"} title="${st.meta ? "" : ".env में META_APP_ID/META_APP_SECRET चाहिए"}">+ Instagram / Facebook</button></span>` : ""}</div>
      ${c.connections.length ? `<table><tr><th>platform</th><th>नाम</th><th>channel</th><th>जुड़ा</th><th></th></tr>${c.connections.map((x) => `<tr><td>${PLAT[x.platform] || x.platform}</td><td>${esc(x.name)}${x.meta?.subscribers ? ` <span class="muted small">· ${x.meta.subscribers} subs</span>` : ""}${x.meta?.page ? ` <span class="muted small">· page: ${esc(x.meta.page)}</span>` : ""}</td><td>${admin ? `<select class="c-move small" data-id="${x.id}">${S.channels.map((ch) => `<option value="${ch.id}" ${x.channel_id === ch.id ? "selected" : ""}>${esc(ch.name)}</option>`).join("")}</select>` : esc(S.channels.find((ch) => ch.id === x.channel_id)?.name || "")}</td><td class="small muted">${new Date(x.created_at).toLocaleDateString("hi-IN")}</td><td>${admin ? `<button class="btn quiet small danger c-del" data-id="${x.id}">हटाएँ</button>` : ""}</td></tr>`).join("")}</table>` : `<p class="muted">अभी कोई channel नहीं जुड़ा।</p>`}</div>
    <div class="section"><h2>Brand kit</h2><p class="muted small">हर नए project और autopilot में यही default लगेगा।</p>
      <form id="brand" class="row" style="align-items:flex-end">
        <div class="field"><label>channel का नाम</label><input name="name" value="${esc(S.brand?.name || "")}" placeholder="@theprashantmahto"></div>
        <div class="field"><label>logo (library)</label><select name="logo_id"><option value="">नहीं</option>${(S.lib || []).filter((x) => x.kind === "logo").map((x) => `<option value="${x.id}" ${S.brand?.logo_id === x.id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></div>
        <div class="field"><label>caption style</label><select name="caption_style"><option value="">default</option>${(S.presets?.caption_styles || []).map((c) => `<option value="${c.id}" ${S.brand?.caption_style === c.id ? "selected" : ""}>${esc(c.label)}</option>`).join("")}</select></div>
        <div class="field"><label>font</label><select name="font"><option value="">style जैसा</option>${(S.presets?.fonts || []).map((f) => `<option ${S.brand?.font === f ? "selected" : ""}>${f}</option>`).join("")}</select></div>
        <div class="field"><label>अक्षर रंग</label><input type="color" name="primary" value="${S.brand?.primary || "#ffffff"}"></div>
        <div class="field"><label>highlight</label><input type="color" name="highlight" value="${S.brand?.highlight || "#ffd400"}"></div>
        <div class="field"><label>color grade</label><select name="grade_preset"><option value="">नहीं</option>${Object.entries(S.presets?.catalog?.grade_presets || {}).map(([k, v]) => `<option value="${k}" ${S.brand?.grade_preset === k ? "selected" : ""}>${esc(v.label)}</option>`).join("")}</select></div>
        <div class="field"><label>logo कोना</label><select name="watermark_pos">${[["tr", "ऊपर दाएँ"], ["tl", "ऊपर बाएँ"], ["br", "नीचे दाएँ"], ["bl", "नीचे बाएँ"]].map(([v, l]) => `<option value="${v}" ${(S.brand?.watermark_pos || "tr") === v ? "selected" : ""}>${l}</option>`).join("")}</select></div>
        <div class="field" style="flex:1;min-width:220px"><label>CTA line (description में)</label><input name="cta" value="${esc(S.brand?.cta || "")}" placeholder="ऐसी कहानियों के लिए follow करें"></div>
        <div class="field" style="flex:1;min-width:220px"><label>hashtags</label><input name="hashtags" value="${esc(S.brand?.hashtags || "")}" placeholder="#motivation #hindi"></div>
        ${S.user.role === "admin" ? `<button class="btn primary">सेव</button>` : ""}</form></div>
    <div class="section"><h2>एक बार का setup</h2>
      <details><summary><b>YouTube</b> (free, 10 मिनट)</summary><ol class="small muted"><li>console.cloud.google.com → नया project → "YouTube Data API v3" enable करें</li><li>OAuth consent screen → External → अपना Gmail test user में जोड़ें</li><li>Credentials → OAuth client ID → Web application → Authorized redirect URI: <code>${esc(st.public_url || "https://<PUBLIC_URL>")}/api/connect/youtube/callback</code></li><li>client id/secret को .env में <code>YT_CLIENT_ID</code> / <code>YT_CLIENT_SECRET</code> में डालें, <code>docker compose up -d</code>, फिर यहाँ "+ YouTube"</li></ol><p class="small muted">quota: ~6 upload/दिन (10,000 units, upload 1,600)।</p></details>
      <details><summary><b>Instagram / Facebook</b> (free, Business account चाहिए)</summary><ol class="small muted"><li>Instagram को Professional (Creator/Business) बनाएँ और एक Facebook Page से link करें</li><li>developers.facebook.com → Create App (Business) → products: Facebook Login for Business + Instagram Graph API</li><li>Facebook Login → Settings → Valid OAuth Redirect URIs: <code>${esc(st.public_url || "https://<PUBLIC_URL>")}/api/connect/meta/callback</code></li><li>App ID/Secret को .env में <code>META_APP_ID</code> / <code>META_APP_SECRET</code>; फिर "+ Instagram / Facebook"</li><li>Cloudflare Access में <code>/pub/*</code> path को bypass करें (Meta वहीं से वीडियो उठाता है)</li></ol><p class="small muted">limit: Instagram 100 post/24h, Facebook Reels ~30/24h।</p></details></div>`;
}
function bindSettings() {
  const bf = $("#brand"); if (bf) bf.onsubmit = async (e) => { e.preventDefault(); const f = e.target; const body = {}; for (const el of f.elements) if (el.name) body[el.name] = el.type === "color" ? (el.value === "#ffffff" && el.name === "primary" ? "" : el.value) : el.value; try { await api("PUT", `/brand?channel=${S.channel}`, body); toast("brand kit सेव"); } catch (err) { toast(err.message); } };
  const start = async (pl) => { try { const r = await api("POST", `/connect/${pl}/start?channel=${S.channel}`); location.href = r.url; } catch (e) { toast(e.message); } };
  document.querySelectorAll(".c-move").forEach((sel) => (sel.onchange = async () => { await api("PATCH", `/connections/${sel.dataset.id}`, { channel_id: sel.value }); toast("channel बदला"); load().then(render); }));
  const add = $("#ch-add"); if (add) add.onclick = async () => { const name = prompt("नए channel का नाम"); if (!name) return; const niche = prompt("niche (जैसे: Hindi motivation, success stories)") || ""; const r = await api("POST", "/channels", { name, niche }); S.channel = r.id; localStorage.setItem("vividora_channel", r.id); load().then(render); };
  const ce = $("#ch-edit"); if (ce) ce.onsubmit = async (e) => { e.preventDefault(); const f = e.target; await api("PATCH", `/channels/${f.id.value}`, { name: f.name.value, handle: f.handle.value, niche: f.niche.value, language: f.language.value, color: f.color.value, keywords: f.keywords.value.split(",").map((x) => x.trim()).filter(Boolean) }); toast("channel सेव"); load().then(render); };
  const cd = $("#ch-del"); if (cd) cd.onclick = async () => { if (!confirm("यह channel हटाएँ? इसके projects पहले channel में चले जाएँगे।")) return; await api("DELETE", `/channels/${S.channel}`); S.channel = ""; load().then(render); };
  document.querySelectorAll("[data-ch]").forEach((el) => (el.onclick = () => { S.channel = el.dataset.ch; localStorage.setItem("vividora_channel", S.channel); load().then(render); }));
  const yt = $("#c-yt"); if (yt) yt.onclick = () => start("youtube");
  const mt = $("#c-meta"); if (mt) mt.onclick = () => start("meta");
  document.querySelectorAll(".c-del").forEach((b) => (b.onclick = async () => { if (confirm("यह connection हटाएँ?")) { await api("DELETE", `/connections/${b.dataset.id}`); load().then(render); } }));
}

// ---------- plan: trends + ideas + scripts ----------
const ISTAT = { new: "विचार", approved: "बनाना है", recorded: "record हो गया", done: "हो गया" };
const FMT = { short: "Short / Reel", long: "लंबा वीडियो", montage: "Montage" };
function planView() {
  const t = S.trends || { trends: [], setup: {} }; const ideas = S.ideas || []; const st = t.setup || {}; const canEdit = S.user.role !== "viewer";
  const src = { google_trends: "Google Trends", yt_popular: "YouTube Top", yt_channel: "Channels" };
  const bySrc = {}; for (const r of t.trends) (bySrc[r.source] = bySrc[r.source] || []).push(r);
  const open = S.ideaOpen && ideas.find((i) => i.id === S.ideaOpen);
  return `<div class="row between"><h1>Plan</h1><span class="small muted">${st.llm ? "AI: चालू" : "AI: key नहीं — offline सुझाव"}${S.notify?.enabled ? " · WhatsApp: चालू" : ""}</span></div>
    <p class="muted">आज क्या चल रहा है → इस channel के लिए ideas → script → record → Vividora बाकी करेगा।</p>
    <div class="plan">
      <div class="section" style="margin-top:0;border:0;padding-top:0"><div class="row between"><h2>Trend radar</h2>${canEdit ? `<button class="btn small" id="tr-refresh">ताज़ा करें</button>` : ""}</div>
        <p class="small muted">${t.fetched_at ? `आख़िरी: ${new Date(t.fetched_at).toLocaleString("hi-IN")}` : "अभी कुछ नहीं लिया"}${!st.yt_api_key ? " · YouTube Top के लिए .env में YT_API_KEY डालें" : ""}${!(st.watch_channels || []).length ? " · WATCH_CHANNELS=UC… से पसंदीदा channels देखें" : ""}</p>
        ${Object.keys(bySrc).length ? Object.entries(bySrc).map(([k, rows]) => `<h3 class="small muted" style="margin:.75rem 0 .3rem">${src[k] || k}</h3><ul class="trlist">${rows.slice(0, 15).map((r) => `<li>${r.url ? `<a href="${r.url}" target="_blank" rel="noopener">${esc(r.title)}</a>` : esc(r.title)}<span class="muted small">${r.meta?.traffic ? r.meta.traffic + "+" : r.meta?.views_per_day ? r.meta.views_per_day.toLocaleString("en-IN") + "/day" : r.meta?.views ? r.meta.views.toLocaleString("en-IN") : ""}${r.meta?.channel ? " · " + esc(r.meta.channel) : ""}</span></li>`).join("")}</ul>`).join("") : `<p class="muted small">“ताज़ा करें” दबाएँ — Google Trends बिना key के आता है।</p>`}</div>
      <div class="section" style="margin-top:0;border:0;padding-top:0"><div class="row between"><h2>Ideas</h2></div>
        ${canEdit ? `<form id="idea-gen" class="row" style="margin-bottom:.75rem"><input name="topic" placeholder="विषय (खाली = trends से)" style="flex:1;min-width:160px"><select name="format">${Object.entries(FMT).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select><select name="count">${[4, 6, 8, 12].map((n) => `<option ${n === 6 ? "selected" : ""}>${n}</option>`).join("")}</select><button class="btn primary small">✨ ideas बनाएँ</button></form>
        <form id="idea-add" class="row" style="margin-bottom:.75rem"><input name="title" placeholder="अपना idea लिखें…" style="flex:1;min-width:160px" required><button class="btn small">+ जोड़ें</button></form>` : ""}
        ${["new", "approved", "recorded", "done"].map((stt) => { const list = ideas.filter((i) => i.status === stt); return list.length ? `<h3 class="small muted" style="margin:.75rem 0 .3rem">${ISTAT[stt]} · ${list.length}</h3><ul class="ideas">${list.map((i) => `<li class="${open && open.id === i.id ? "sel" : ""}" data-idea="${i.id}"><b>${esc(i.title)}</b><span class="small muted">${FMT[i.format] || i.format}${i.script ? " · script ✓" : ""}${i.source ? " · " + esc(i.source.slice(0, 40)) : ""}</span></li>`).join("")}</ul>` : ""; }).join("") || `<p class="muted small">अभी कोई idea नहीं।</p>`}</div>
    </div>
    <div class="section"><div class="row between"><h2>Swipe file · references</h2></div><p class="small muted">trend audio / video / effect जो आपको बनाना है — link + note। (project के अंदर Refs tab से भी जुड़ते हैं)</p>
      ${canEdit ? `<form id="ref-form" class="row" style="margin-bottom:.75rem"><select name="kind"><option value="audio">🎵 audio</option><option value="video">🎬 video</option><option value="effect">✨ effect</option><option value="caption">💬 caption</option><option value="hook">🪝 hook</option><option value="other">📌 other</option></select><input name="url" placeholder="https://…" style="flex:1;min-width:160px"><input name="note" placeholder="note: क्या बनाना है" style="flex:2;min-width:200px"><button class="btn small">+ जोड़ें</button></form>` : ""}
      ${(S.refs || []).length ? `<ul class="trlist">${S.refs.map((r) => `<li><span>${{ audio: "🎵", video: "🎬", effect: "✨", caption: "💬", hook: "🪝" }[r.kind] || "📌"} ${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.url.replace(/^https?:\/\//, "").slice(0, 60))}</a>` : ""} ${r.note ? `<span class="muted">— ${esc(r.note)}</span>` : ""}${r.project_id ? ` <a class="small" href="#/projects/${r.project_id}">project</a>` : ""}</span>${canEdit ? `<button class="btn quiet small ref-del" data-id="${r.id}">✕</button>` : ""}</li>`).join("")}</ul>` : `<p class="muted small">अभी खाली।</p>`}</div>
    ${open ? ideaPanel(open, canEdit) : ""}`;
}
function ideaPanel(i, canEdit) {
  const m = i.meta || {};
  return `<div class="ed-modal" id="idea-modal"><div class="modal"><div class="row between"><h2 ${canEdit ? 'contenteditable="true" id="idea-title"' : ""}>${esc(i.title)}</h2><button class="ibtn" id="idea-close">✕</button></div>
    <div class="row" style="margin:.5rem 0 1rem"><select id="idea-status" ${canEdit ? "" : "disabled"}>${Object.entries(ISTAT).map(([k, v]) => `<option value="${k}" ${i.status === k ? "selected" : ""}>${v}</option>`).join("")}</select>
      <select id="idea-format" ${canEdit ? "" : "disabled"}>${Object.entries(FMT).map(([k, v]) => `<option value="${k}" ${i.format === k ? "selected" : ""}>${v}</option>`).join("")}</select>
      <input type="date" id="idea-due" value="${(i.due_at || "").slice(0, 10)}" ${canEdit ? "" : "disabled"}><span class="grow"></span>${canEdit ? `<button class="btn small quiet danger" id="idea-drop">हटाएँ</button>` : ""}</div>
    <div class="field"><label>Hook (camera पर पहली लाइन)</label><textarea id="idea-hook" rows="2" ${canEdit ? "" : "disabled"}>${esc(i.hook || "")}</textarea></div>
    <div class="field"><label>Angle</label><input id="idea-angle" value="${esc(i.angle || "")}" ${canEdit ? "" : "disabled"}></div>
    <div class="field"><label>Outline</label><textarea id="idea-outline" rows="4" ${canEdit ? "" : "disabled"}>${esc(i.outline || "")}</textarea></div>
    <div class="row between"><label class="small muted">Script${m.script_source ? ` (${m.script_source})` : ""}</label>${canEdit ? `<span class="row"><select id="script-secs"><option value="">लंबाई अपने-आप</option><option value="30">30s</option><option value="45">45s</option><option value="60">60s</option><option value="180">3 min</option><option value="480">8 min</option></select><button class="btn small" id="idea-script">✨ script लिखें</button></span>` : ""}</div>
    <textarea id="idea-scripttext" rows="12" style="width:100%;font-family:var(--font)" ${canEdit ? "" : "disabled"}>${esc(i.script || "")}</textarea>
    ${m.shotlist?.length ? `<p class="small muted" style="margin-top:.5rem"><b>Shots:</b> ${m.shotlist.map(esc).join(" · ")}</p>` : ""}${m.overlays?.length ? `<p class="small muted"><b>On-screen text:</b> ${m.overlays.map(esc).join(" · ")}</p>` : ""}${m.title_options?.length ? `<p class="small muted"><b>Title options:</b> ${m.title_options.map(esc).join(" / ")}</p>` : ""}
    <div class="row between" style="margin-top:1rem"><span class="small muted">record करने के बाद "+ नया" से upload करें — यह idea link हो जाएगा।</span>${canEdit ? `<span class="row"><a class="btn small" href="#/new?idea=${i.id}">record हो गया → upload</a><button class="btn primary small" id="idea-save">सेव</button></span>` : ""}</div></div></div>`;
}
function bindPlan() {
  const rf0 = $("#ref-form"); if (rf0) rf0.onsubmit = async (e) => { e.preventDefault(); const f = e.target; try { await api("POST", "/refs", { kind: f.kind.value, url: f.url.value.trim(), note: f.note.value.trim(), channel_id: S.channel }); load().then(render); } catch (err) { toast(err.message); } };
  document.querySelectorAll(".ref-del").forEach((b) => (b.onclick = async () => { await api("DELETE", `/refs/${b.dataset.id}`); load().then(render); }));
  const rf = $("#tr-refresh"); if (rf) rf.onclick = async () => { rf.disabled = true; rf.textContent = "ला रहा है…"; try { const r = await api("POST", "/trends/refresh"); toast(`${r.count} trends`); } catch (e) { toast(e.message); } load().then(render); };
  const gen = $("#idea-gen"); if (gen) gen.onsubmit = async (e) => { e.preventDefault(); const f = e.target; const b = f.querySelector("button"); b.disabled = true; b.textContent = "सोच रहा है…";
    try { await api("POST", "/ideas/generate", { topic: f.topic.value, format: f.format.value, count: +f.count.value, channel_id: S.channel }); toast("ideas आ गए"); } catch (err) { toast(err.message); } load().then(render); };
  const add = $("#idea-add"); if (add) add.onsubmit = async (e) => { e.preventDefault(); const f = e.target; const r = await api("POST", "/ideas", { title: f.title.value, format: "short", channel_id: S.channel }); S.ideaOpen = r.id; load().then(render); };
  document.querySelectorAll("[data-idea]").forEach((li) => (li.onclick = () => { S.ideaOpen = li.dataset.idea; render(); }));
  const close = $("#idea-close"); if (close) close.onclick = () => { S.ideaOpen = null; render(); };
  const modal = $("#idea-modal"); if (modal) modal.onclick = (e) => { if (e.target === modal) { S.ideaOpen = null; render(); } };
  const id = S.ideaOpen; if (!id) return;
  const collect = () => ({ title: $("#idea-title")?.textContent.trim(), status: $("#idea-status").value, format: $("#idea-format").value, due_at: $("#idea-due").value || null, hook: $("#idea-hook").value, angle: $("#idea-angle").value, outline: $("#idea-outline").value, script: $("#idea-scripttext").value });
  const save = $("#idea-save"); if (save) save.onclick = async () => { await api("PATCH", `/ideas/${id}`, collect()); toast("सेव"); load().then(render); };
  const drop = $("#idea-drop"); if (drop) drop.onclick = async () => { if (confirm("यह idea हटाएँ?")) { await api("PATCH", `/ideas/${id}`, { status: "dropped" }); S.ideaOpen = null; load().then(render); } };
  const sc = $("#idea-script"); if (sc) sc.onclick = async () => { sc.disabled = true; sc.textContent = "लिख रहा है…"; await api("PATCH", `/ideas/${id}`, collect()); try { const r = await api("POST", `/ideas/${id}/script`, { seconds: $("#script-secs").value || null }); toast(r.source === "llm" ? "script तैयार" : "template बना (AI key नहीं)"); } catch (e) { toast(e.message); } load().then(render); };
  $("#idea-status").onchange = async () => { await api("PATCH", `/ideas/${id}`, { status: $("#idea-status").value }); load().then(render); };
}

// ---------- analytics ----------
function analyticsView() {
  const a = S.analytics || { videos: [], learn: {} }; const L = a.learn || {}; const canEdit = S.user.role !== "viewer";
  const n = (x) => (x || 0).toLocaleString("en-IN");
  const rec = L.recommend || {}; const recLabels = { caption_style: "caption style", hook: "hook", zoom: "auto zoom", look: "look", length: "लंबाई", music: "music", weekday: "दिन", hour: "समय" };
  return `<div class="row between"><h1>Analytics</h1>${canEdit ? `<button class="btn small" id="an-refresh">stats ताज़ा करें</button>` : ""}</div>
    <p class="muted">published videos का हाल, और उससे सीख: कौन-सा style / hook / लंबाई ज़्यादा चलती है (index 1.0 = औसत)।</p>
    ${Object.keys(rec).length ? `<div class="note"><b>सीख:</b> ${Object.entries(rec).map(([k, v]) => `${recLabels[k] || k} → <b>${esc(v)}</b>`).join(" · ")}
      ${S.user.role === "admin" ? `<br><button class="btn small primary" id="an-apply" style="margin-top:.5rem">नए projects के लिए यही default बनाएँ</button>` : ""}
      ${a.defaults && Object.keys(a.defaults).length ? `<span class="small muted" style="margin-left:.5rem">अभी default: ${esc(JSON.stringify(a.defaults))}</span>` : ""}</div>` : `<p class="small muted">${L.note || "अभी सीखने के लिए data कम है।"}</p>`}
    ${Object.keys(L.dimensions || {}).length ? `<div class="section"><h2>क्या काम कर रहा है</h2><div class="dims">${Object.entries(L.dimensions).map(([k, d]) => `<div class="dim"><b>${esc(d.label)}</b>${Object.entries(d.groups).sort((x, y) => y[1].index - x[1].index).map(([g, v]) => `<div class="bar"><span>${esc(g)} <i class="muted">(${v.n})</i></span><div class="progress"><i style="width:${Math.min(100, v.index * 50).toFixed(0)}%"></i></div><b>${v.index.toFixed(2)}</b></div>`).join("")}</div>`).join("")}</div></div>` : ""}
    <div class="section"><h2>Published videos · ${a.videos.length}</h2>${a.videos.length ? `<table><tr><th>video</th><th>platform</th><th>views</th><th>likes</th><th>comments</th><th>style</th><th>published</th></tr>${a.videos.map((v) => `<tr><td><a href="${v.url}" target="_blank" rel="noopener">${esc(v.title)}</a> <span class="small muted">${esc(v.label || "")}</span></td><td>${v.platform}</td><td>${n(v.views)}</td><td>${n(v.likes)}</td><td>${n(v.comments)}</td><td class="small">${esc(v.features?.caption_style || "")}${v.features?.hook === "yes" ? " · hook" : ""} · ${esc(v.features?.length || "")}</td><td class="small muted">${v.published_at ? new Date(v.published_at).toLocaleDateString("hi-IN") : ""}${v.fetched_at ? "" : " · stats नहीं"}</td></tr>`).join("")}</table>` : `<p class="muted">अभी कुछ publish नहीं हुआ।</p>`}</div>`;
}
function bindAnalytics() {
  const r = $("#an-refresh"); if (r) r.onclick = async () => { r.disabled = true; r.textContent = "ला रहा है…"; try { const x = await api("POST", "/analytics/refresh"); toast(`${x.updated} videos · ${(x.errors || []).join("; ") || "ok"}`); } catch (e) { toast(e.message); } load().then(render); };
  const ap = $("#an-apply"); if (ap) ap.onclick = async () => { const x = await api("POST", `/analytics/apply?channel=${S.channel}`); toast("default बदले"); load().then(render); };
}

// ---------- boot ----------
(async function boot() {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  S.token = localStorage.getItem("vividora_token");
  if (S.token) { try { const me = await api("GET", "/auth/me"); S.user = me.user; S.ws = me.workspace; await load(); } catch { S.token = null; } }
  render();
})();
