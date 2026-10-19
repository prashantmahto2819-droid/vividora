// Vividora dashboard — plain JS, no build step. Served by the API from web/dist.

const S = { token: null, user: null, ws: null, projects: [], project: null, presets: null,
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
function parseRoute() { const p = location.hash.replace(/^#/, "") || "/"; const [, kind, id] = p.match(/^\/(projects|users|status|new)?\/?([^/]*)/) || []; return { kind: kind || "home", id }; }
function go(path) { location.hash = path; }
window.addEventListener("hashchange", () => { S.route = parseRoute(); load().then(render); });

// ---------- data ----------
async function load() {
  if (!S.token) return;
  if (!S.presets) S.presets = await api("GET", "/presets").catch(() => null);
  S.projects = await api("GET", "/projects");
  if (S.route.kind === "projects" && S.route.id) {
    S.project = await api("GET", "/projects/" + S.route.id).catch(() => null);
  } else S.project = null;
  if (S.route.kind === "status") { S.status = await api("GET", "/status"); S.activity = await api("GET", "/activity"); }
  if (S.route.kind === "users") S.users = await api("GET", "/users").catch(() => []);
  schedulePoll();
}
function schedulePoll() {
  clearTimeout(S.poll);
  const busy = S.project && ["preparing", "transcribing", "cutting", "rendering"].includes(S.project.status);
  const anyBusy = S.projects.some((p) => ["preparing", "transcribing", "cutting", "rendering"].includes(p.status));
  if (busy || anyBusy || S.route.kind === "status") S.poll = setTimeout(() => load().then(renderSoft), busy ? 2500 : 6000);
}
function renderSoft() { if (document.activeElement && ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) { schedulePoll(); return; } render(); }

// ---------- views ----------
function render() {
  const app = $("#app");
  if (!S.token) { app.innerHTML = loginView(); bindLogin(); return; }
  const r = S.route;
  const detail = r.kind === "projects" && r.id;
  app.innerHTML = `<div class="shell">
    <aside class="rail ${detail || r.kind !== "home" ? "hidden-mobile" : ""}">
      <div class="rail-head"><a class="brand" href="#/"><i></i>Vividora</a>
        ${S.user.role !== "viewer" ? `<a class="btn primary" href="#/new">+ नया</a>` : ""}</div>
      <div class="rail-list">${S.projects.length ? S.projects.map(projRow).join("") : `<p class="muted" style="padding:1rem">अभी कोई project नहीं। "+ नया" से पहली recording डालें।</p>`}</div>
      <div class="rail-foot"><span>${esc(S.user.name)} <span class="muted">· ${S.user.role}</span></span>
        <span class="row" style="gap:.1rem"><a class="btn quiet small" href="#/status">status</a>${S.user.role === "admin" ? `<a class="btn quiet small" href="#/users">users</a>` : ""}<button class="btn quiet small" id="logout">बाहर</button></span></div>
    </aside>
    <main class="main">${r.kind === "new" ? newView() : r.kind === "users" ? usersView() : r.kind === "status" ? statusView() : detail ? (S.project ? projectView(S.project) : `<p>project नहीं मिला।</p>`) : homeView()}</main>
  </div>`;
  $("#logout").onclick = logout;
  if (r.kind === "new") bindNew(); if (r.kind === "users") bindUsers();
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
  return `<h1>नमस्ते, ${esc(S.user.name.split(" ")[0])}</h1>
    <p class="muted">${review.length ? `${review.length} वीडियो आपकी जाँच का इंतज़ार कर रहे हैं।` : working.length ? `${working.length} वीडियो पर काम चल रहा है।` : "सब शांत है। नई recording डालें।"}</p>
    ${review.length ? `<div class="section"><h2>जाँच के लिए</h2>${review.map(projRow).join("")}</div>` : ""}
    ${working.length ? `<div class="section"><h2>चल रहा है</h2>${working.map(projRow).join("")}</div>` : ""}
    <div class="section"><h2>कैसे काम करता है</h2>
      <ol class="muted"><li>recording upload करें (फ़ोन से भी)</li><li>Vividora आवाज़ साफ़ करता है, transcript बनाता है, चुप्पी और गलत take ढूँढता है</li><li>आप कट जाँचें, caption style और platform चुनें, render करें</li><li>वीडियो देखकर मंज़ूरी दें, फिर download या publish</li></ol></div>`;
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
  return `<h1>नई recording</h1><p class="muted">पहले नाम दें, फिर फ़ाइल चुनें। upload बीच में टूटे तो वहीं से आगे बढ़ता है।</p>
    <form id="new"><div class="field"><label>वीडियो का नाम</label><input name="title" required placeholder="जैसे: 4 बजे उठने वाला लड़का"></div>
    <div class="field"><label>भाषा</label><select name="language"><option value="auto">अपने-आप पहचानें (हिंदी / English / Hinglish)</option><option value="hi">हिंदी</option><option value="en">English</option></select></div>
    <div class="drop" id="drop"><input type="file" id="file" accept="video/*,audio/*,.mkv,.mts" hidden><b>फ़ाइल यहाँ छोड़ें या चुनें</b><br><span class="muted small">mp4, mov, mkv, webm · 20 GB तक</span><div id="fname" class="small" style="margin-top:.5rem"></div></div>
    <div id="up-progress"></div>
    <div class="actionbar"><a class="btn" href="#/">रद्द</a><button class="btn primary" id="start" disabled>upload शुरू करें</button></div></form>`;
}
function bindNew() {
  const drop = $("#drop"), file = $("#file"); let chosen = null;
  drop.onclick = () => file.click();
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); chosen = e.dataTransfer.files[0]; pick(); };
  file.onchange = () => { chosen = file.files[0]; pick(); };
  function pick() { if (!chosen) return; $("#fname").textContent = `${chosen.name} · ${gb(chosen.size)}`; $("#start").disabled = false; }
  $("#new").onsubmit = async (e) => {
    e.preventDefault(); if (!chosen) return;
    const f = e.target; $("#start").disabled = true;
    try {
      const p = await api("POST", "/projects", { title: f.title.value, language: f.language.value });
      await uploadFile(p.id, chosen, (done, total) => { $("#up-progress").innerHTML = `<p class="small muted">${gb(done)} / ${gb(total)}</p><div class="progress"><i style="width:${(done / total * 100).toFixed(1)}%"></i></div>`; });
      toast("upload पूरा — जाँच शुरू"); go("/projects/" + p.id);
    } catch (err) { $("#up-progress").innerHTML = `<div class="note err">${esc(err.message)} — दोबारा कोशिश करें, upload वहीं से चलेगा।</div>`; $("#start").disabled = false; }
  };
}
async function uploadFile(pid, file, onProgress) {
  const up = await api("POST", `/projects/${pid}/uploads`, { filename: file.name, size: file.size });
  let off = up.received; const chunk = up.chunk;
  while (off < file.size) {
    const part = file.slice(off, Math.min(file.size, off + chunk));
    let r;
    try { r = await api("PUT", `/projects/${pid}/uploads/${up.upload_id}/chunk`, null, { data: part, offset: off }); }
    catch (err) { if (err.received != null) { off = err.received; continue; } throw err; }
    off = r.received; onProgress(off, file.size);
  }
  return api("POST", `/projects/${pid}/uploads/${up.upload_id}/finish`);
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
    <div class="section"><h2>disk</h2>${Object.entries(st.disk).map(([k, d]) => `<p>${k}: ${gb(d.used)} / ${gb(d.total)} <span class="muted">(${gb(d.free)} खाली)</span></p><div class="progress"><i style="width:${(d.used / d.total * 100).toFixed(0)}%"></i></div>`).join("")}</div>
    <div class="section"><h2>हाल की गतिविधि</h2><table>${(S.activity || []).slice(0, 40).map((a) => `<tr><td class="small muted">${new Date(a.created_at).toLocaleString("hi-IN")}</td><td class="small">${esc(a.user_name || "system")}</td><td class="small">${esc(a.action)} ${esc(a.detail?.title || a.detail?.email || a.detail?.file || (a.detail?.presets || []).join(",") || "")}</td></tr>`).join("")}</table></div>`;
}

// ---------- boot ----------
(async function boot() {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  S.token = localStorage.getItem("vividora_token");
  if (S.token) { try { const me = await api("GET", "/auth/me"); S.user = me.user; S.ws = me.workspace; await load(); } catch { S.token = null; } }
  render();
})();
