// Vividora dashboard — plain JS, no build step. Served by the API from web/dist.
import * as ED from "./editor.js";
import * as REC from "./record.js";
import * as TH from "./thumbs.js";
import * as VO from "./voice.js";

const S = { token: null, user: null, ws: null, projects: [], project: null, presets: null, channels: [], channel: localStorage.getItem("vividora_channel") || "",
            route: parseRoute(), poll: null, upload: null, playhead: 0, status: null, users: null, activity: null,
            sel: new Set(), pview: lsGet("vividora_pview") || "grid", pq: "", pch: "", overview: null, pubs: null, calOff: 0, pubTab: "queue" };
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (t) => { t = Math.max(0, t || 0); const m = Math.floor(t / 60), s = (t % 60); return `${m}:${s < 10 ? "0" : ""}${s.toFixed(1)}`; };
const fmtDur = (t) => { t = Math.round(t || 0); const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60; return `${h ? h + ":" + String(m).padStart(2, "0") : m}:${String(s).padStart(2, "0")}`; };
const gb = (b) => b >= 1024 ** 3 ? (b / 1024 ** 3).toFixed(1) + " GB" : (b / 1024 ** 2).toFixed(0) + " MB";
function lsGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, v); } catch {} }
function relTime(iso) {
  if (!iso) return ""; const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return "अभी"; if (d < 3600) return `${Math.floor(d / 60)} मिनट पहले`; if (d < 86400) return `${Math.floor(d / 3600)} घंटे पहले`;
  if (d < 86400 * 7) return `${Math.floor(d / 86400)} दिन पहले`; return new Date(iso).toLocaleDateString("hi-IN", { day: "numeric", month: "short" });
}
const STATUS = {
  uploading: ["Upload अधूरा", ""], preparing: ["जाँच हो रही है", "working"], transcribing: ["Transcript बन रहा है", "working"],
  cutting: ["कट ढूँढे जा रहे हैं", "working"], review_cuts: ["कट जाँचें", "review"], rendering: ["Render हो रहा है", "working"],
  review_output: ["मंज़ूरी बाकी", "review"], approved: ["मंज़ूर", "approved"], failed: ["रुक गया", "failed"],
};
const WORKING = ["preparing", "transcribing", "cutting", "rendering"];
const JOBK = { prepare: "जाँच और preview", transcribe: "Transcript", autocut: "कट ढूँढना", render: "Render", shorts_plan: "Shorts ढूँढना", publish: "Publish", montage: "Montage", montage_plan: "Beat plan", matte: "Cutout" };

// ---------- icons (stroke, 24 grid) ----------
const IC = {
  home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  rec: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4" fill="currentColor"/>',
  upload: '<path d="M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5"/><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
  music: '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/>',
  bulb: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"/>',
  trend: '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  send: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/><path d="m10 15 2 2 3-4"/>',
  lib: '<path d="M4 5a1 1 0 0 1 1-1h4l2 2h8a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z"/>',
  tv: '<rect x="2" y="6" width="20" height="14" rx="2"/><path d="m8 2 4 4 4-4"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>',
  pulse: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7M12 17h.01"/>',
  film: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>', plus: '<path d="M12 5v14M5 12h14"/>', out: '<path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l5-5-5-5M15 12H3"/>',
  dots: '<circle cx="5" cy="12" r="1.6" fill="currentColor"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/><circle cx="19" cy="12" r="1.6" fill="currentColor"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>', search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
};
const ic = (n, cls = "") => `<svg class="ic ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IC[n] || ""}</svg>`;

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
function parseRoute() {
  const full = location.hash.replace(/^#/, "") || "/"; const [p, qs] = full.split("?");
  const [, kind, id] = p.match(/^\/(projects|users|status|new|settings|plan|analytics|record|library|thumbs|publish|trends|help|account)?\/?([^/]*)/) || [];
  return { kind: kind || "home", id, q: new URLSearchParams(qs || "") };
}
function go(path) { location.hash = path; }
window.addEventListener("hashchange", () => { S.route = parseRoute(); document.body.classList.remove("nav-open"); closeMenu(); load().catch((e) => toast(e.message)).then(render); });

// ---------- data ----------
async function load() {
  if (!S.token) return;
  const r = S.route;
  if (!S.presets) S.presets = await api("GET", "/presets").catch(() => null);
  S.channels = await api("GET", "/channels").catch(() => []);
  if (!S.channels.find((c) => c.id === S.channel)) S.channel = S.channels[0]?.id || "";
  const allCh = r.kind === "projects" && !r.id && S.pch === "all";
  const chQ = S.channel && S.channels.length > 1 && !allCh ? `?channel=${S.pch && S.pch !== "all" && r.kind === "projects" ? S.pch : S.channel}` : "";
  S.projects = await api("GET", "/projects" + chQ);
  const ovQ = S.channels.length > 1 ? `?channel=${S.channel}` : "";
  if (r.kind === "home") { const [t, i, a, o] = await Promise.all([api("GET", "/trends").catch(() => ({ trends: [] })), api("GET", `/ideas?channel=${S.channel}`).catch(() => []), api("GET", `/analytics?channel=${S.channel}`).catch(() => ({ videos: [] })), api("GET", "/overview" + ovQ).catch(() => null)]); S.homeTrends = t.trends || []; S.ideas = i; S.analytics = a; S.overview = o; }
  if (r.kind === "projects" && r.id) {
    S.project = await api("GET", "/projects/" + r.id).catch(() => null);
  } else S.project = null;
  if (r.kind === "status") { S.status = await api("GET", "/status"); S.activity = await api("GET", "/activity"); }
  if (r.kind === "users" || (r.kind === "account" && S.user?.role === "admin")) S.users = await api("GET", "/users").catch(() => []);
  if (r.kind === "plan") { const [t, i, n, rf] = await Promise.all([api("GET", "/trends").catch(() => ({ trends: [], setup: {} })), api("GET", `/ideas?channel=${S.channel}`).catch(() => []), api("GET", "/notify").catch(() => ({})), api("GET", "/refs").catch(() => [])]); S.trends = t; S.ideas = i; S.notify = n; S.refs = rf; }
  if (r.kind === "trends") { S.trends = await api("GET", "/trends").catch(() => ({ trends: [], setup: {} })); S.radar = S.channel ? await api("GET", `/radar?channel=${S.channel}`).catch(() => null) : null; }
  if (r.kind === "publish") { const [o, p] = await Promise.all([api("GET", "/overview" + ovQ).catch(() => null), api("GET", "/publications" + ovQ).catch(() => [])]); S.overview = o; S.pubs = p; }
  if (r.kind === "library") S.lib = await api("GET", `/library?channel=${S.channel}`).catch(() => []);
  if (r.kind === "analytics") S.analytics = await api("GET", `/analytics?channel=${S.channel}`).catch(() => ({ videos: [], learn: {} }));
  if (r.kind === "settings") { S.conns = await api("GET", "/connections").catch(() => ({ connections: [], setup: {} })); S.brand = await api("GET", `/brand?channel=${S.channel}`).catch(() => ({})); S.lib = await api("GET", "/library").catch(() => []); const sc = S.channel ? await api("GET", `/schedule?channel=${S.channel}`).catch(() => null) : null; if (!sc || sc.channel_id !== S.sched?.channel_id) S.schedEdit = null; S.sched = sc; S.notify = await api("GET", "/notify").catch(() => null); }
  const ids = new Set(S.projects.map((p) => p.id)); for (const id of [...S.sel]) if (!ids.has(id)) S.sel.delete(id);
  schedulePoll();
}
function schedulePoll() {
  clearTimeout(S.poll);
  const busy = S.project && (WORKING.includes(S.project.status) || (S.project.jobs || []).some((j) => ["queued", "running"].includes(j.status)));
  const anyBusy = S.projects.some((p) => WORKING.includes(p.status)) || (S.route.kind === "home" && (S.overview?.jobs || []).length);
  if (busy || anyBusy || S.route.kind === "status") S.poll = setTimeout(() => load().then(renderSoft), busy ? 2500 : 6000);
}
function renderSoft() { if ((document.activeElement && ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) || $("#pmenu") || S.route.kind === "thumbs") { schedulePoll(); return; } render(); }

// ---------- shell: left nav, mobile top bar + tab bar ----------
const NAV = [
  [null, [["home", "#/", "home", "Home"], ["projects", "#/projects", "grid", "Projects"]]],
  ["बनाएँ", [["record", "#/record", "rec", "Record", 1], ["new", "#/new", "upload", "Upload", 1], ["montage", "#/new?type=montage", "music", "Montage", 1], ["thumbs", "#/thumbs", "image", "Thumbnails"]]],
  ["बढ़ाएँ", [["plan", "#/plan", "bulb", "Plan"], ["trends", "#/trends", "trend", "Trends"], ["analytics", "#/analytics", "chart", "Analytics"], ["publish", "#/publish", "send", "Publish"]]],
  ["Workspace", [["library", "#/library", "lib", "Library"], ["settings", "#/settings", "tv", "Channels & Brand"], ["account", "#/account", "gear", "Settings"], ["status", "#/status", "pulse", "Status"], ["help", "#/help", "help", "Help"]]],
];
function navActive(id) {
  const k = S.route.kind; const mont = /type=montage/.test(location.hash);
  if (id === "montage") return k === "new" && mont; if (id === "new") return k === "new" && !mont;
  if (id === "account") return k === "account" || k === "users"; return k === id;
}
function shellHTML(main, wide = false) {
  const canEdit = S.user.role !== "viewer";
  const review = S.projects.filter((p) => p.status === "review_cuts" || p.status === "review_output").length;
  const badges = { projects: review || "", publish: (S.overview?.upcoming || []).length || "" };
  const chn = S.channels.find((c) => c.id === S.channel);
  const initials = (S.user.name || "?").split(/\s+/).map((x) => x[0]).slice(0, 2).join("").toUpperCase();
  return `<div class="app2">
    <aside class="nav" id="nav" aria-label="मुख्य menu">
      <div class="nav-head"><a class="brand" href="#/"><i></i>Vividora</a></div>
      ${canEdit ? `<a class="btn primary nav-new" href="#/new">${ic("plus")} नया वीडियो</a>` : ""}
      ${S.channels.length ? `<div class="chsw"><span class="chdot" style="background:${esc(chn?.color || "#F2B33D")}"></span><select id="ch-switch" title="channel">${S.channels.map((c) => `<option value="${c.id}" ${c.id === S.channel ? "selected" : ""}>${esc(c.name)}${c.handle ? " · " + esc(c.handle) : ""}</option>`).join("")}</select></div>` : ""}
      <nav class="nav-list">${NAV.map(([sec, items]) => `${sec ? `<div class="nav-sec">${sec}</div>` : ""}${items.filter((it) => !it[4] || canEdit).map(([id, href, icon, label]) => `<a class="nav-item ${navActive(id) ? "on" : ""}" href="${href}">${ic(icon)}<span>${label}</span>${badges[id] ? `<em>${badges[id]}</em>` : ""}</a>`).join("")}`).join("")}
        ${S.user.role === "admin" ? `<a class="nav-item ${S.route.kind === "users" ? "on" : ""}" href="#/users">${ic("tv")}<span>Users</span></a>` : ""}</nav>
      <div class="nav-foot"><span class="avatar">${esc(initials)}</span><span class="nav-user"><b>${esc(S.user.name)}</b><span class="small muted">${S.user.role}</span></span><button class="ibtn" id="logout" title="Log out करें" aria-label="Log out करें">${ic("out")}</button></div>
    </aside>
    <div class="nav-scrim" id="nav-scrim"></div>
    <header class="topbar"><button class="ibtn" id="nav-open" aria-label="Menu खोलें">${ic("menu")}</button><a class="brand" href="#/"><i></i>Vividora</a>${canEdit ? `<a class="btn primary small" href="#/new">${ic("plus")} नया</a>` : "<span></span>"}</header>
    <main class="main ${wide ? "wide" : ""}">${main}</main>
    <nav class="tabbar">${[["home", "#/", "home", "Home"], ["projects", "#/projects", "grid", "Projects"], ["record", "#/record", "rec", "Record"], ["thumbs", "#/thumbs", "image", "Thumbnail"], ["more", "", "menu", "और"]].map(([id, href, icon, label]) => id === "more" ? `<button class="tab" id="tab-more">${ic(icon)}<span>${label}</span></button>` : `<a class="tab ${navActive(id) ? "on" : ""} ${id === "record" ? "tab-rec" : ""}" href="${href}">${ic(icon)}<span>${label}</span></a>`).join("")}</nav>
  </div>`;
}
function bindShell() {
  $("#logout").onclick = logout;
  const chs = $("#ch-switch"); if (chs) chs.onchange = () => { S.channel = chs.value; lsSet("vividora_channel", S.channel); load().then(render); };
  const open = () => document.body.classList.add("nav-open"); const close = () => document.body.classList.remove("nav-open");
  $("#nav-open").onclick = open; $("#tab-more").onclick = open; $("#nav-scrim").onclick = close;
}

// ---------- views ----------
const EDITOR_STATUS = ["review_cuts", "rendering", "review_output", "approved"];
function render() {
  const app = $("#app");
  closeMenu();
  if (!S.token) { ED.unmount(); TH.unmount(); VO.unmount(); app.dataset.mode = ""; app.innerHTML = loginView(); bindLogin(); return; }
  const r = S.route;
  if (S.user?.role !== "viewer") VO.mount({ api, toast, reload: () => { $("#app").dataset.mode = ""; load().then(render); } });
  document.body.classList.toggle("ed-mode", r.kind === "projects" && !!r.id);
  const detail = r.kind === "projects" && r.id;
  if (r.kind === "record") {
    if (app.dataset.mode !== "record") { ED.unmount(); TH.unmount(); app.dataset.mode = "record"; app.innerHTML = `<div id="recroot"></div>`; REC.mount($("#recroot"), { S, api, esc, toast, go, uploadFile }); }
    return;
  }
  if (app.dataset.mode === "record") REC.unmount();
  if (r.kind === "thumbs" && r.id) {
    const key = "thumbs:" + r.id;
    if (app.dataset.mode === key) return; // the studio keeps its own state; polling must not wipe it
    ED.unmount(); app.dataset.mode = key; app.innerHTML = shellHTML(`<div id="throot"></div>`, true); bindShell();
    TH.mount($("#throot"), r.id, { S, api, esc, toast, go });
    return;
  }
  if ((app.dataset.mode || "").startsWith("thumbs:")) TH.unmount();
  const edKey = S.project ? "editor:" + S.project.id : "";
  // a re-transcribe / re-cut of a project that is already open keeps the editor (it shows the progress and locks editing)
  const reworking = S.project && ["transcribing", "cutting"].includes(S.project.status) && S.project.edl && app.dataset.mode === edKey;
  if (detail && S.project && (EDITOR_STATUS.includes(S.project.status) || reworking) && S.presets) {
    const key = edKey;
    if (app.dataset.mode !== key) { app.dataset.mode = key; app.innerHTML = `<div id="edroot"></div>`; }
    ED.mount($("#edroot"), S.project, { S, api, esc, fmt, toast, load, render, go, stylePreview });
    const top = $(".ed-top-right");
    if (top && !$("#ed-thumb")) top.insertAdjacentHTML("afterbegin", `<a class="btn small ed-thumb" id="ed-thumb" href="#/thumbs/${S.project.id}" title="Thumbnail studio — YouTube thumbnail / Shorts cover">🖼<span> Thumbnail</span></a>`);
    return;
  }
  app.dataset.mode = "shell"; ED.unmount();
  const views = { new: newView, users: usersView, status: statusView, settings: settingsView, plan: planView, analytics: analyticsView, library: libraryView,
                  thumbs: thumbsPickView, publish: publishView, trends: trendsView, help: helpView, account: accountView };
  const main = detail ? (S.project ? projectView(S.project) : `<div class="empty"><p>यह project नहीं मिला — शायद हटा दिया गया है।</p><a class="btn" href="#/projects">सभी projects</a></div>`) : r.kind === "projects" ? projectsView() : (views[r.kind] || homeView)();
  app.innerHTML = shellHTML(main, ["home", "projects", "thumbs", "publish", "library", "help", "trends"].includes(r.kind) && !detail);
  bindShell();
  const binds = { new: bindNew, users: bindUsers, settings: bindSettings, plan: bindPlan, analytics: bindAnalytics, library: bindLibrary, home: bindHome,
                  publish: bindPublish, trends: bindTrends, account: bindAccount, thumbs: bindCards };
  if (detail) { if (S.project) bindProject(S.project); } else if (r.kind === "projects") bindProjects(); else (binds[r.kind] || (() => {}))();
}

// ---------- project cards, ⋯ menu, bulk actions ----------
function pcard(p, opts = {}) {
  const [label, cls] = STATUS[p.status] || [p.status, ""];
  const canEdit = S.user.role !== "viewer" && opts.select !== false;
  const ch = S.channels.length > 1 ? S.channels.find((c) => c.id === p.channel_id) : null;
  const href = opts.href ? opts.href(p) : `#/projects/${p.id}`;
  return `<div class="pc ${S.sel.has(p.id) ? "picked" : ""}" data-pid="${p.id}">
    <div class="pc-thumb"><a class="pc-link" href="${href}" aria-label="${esc(p.title)}"></a>
      ${p.thumb_url ? `<img src="${p.thumb_url}" alt="" loading="lazy">` : `<div class="ph">${ic(p.kind === "montage" ? "music" : "film")}</div>`}
      <span class="pc-status ${cls}">${label}</span>${p.meta?.duration ? `<span class="pc-dur">${fmtDur(p.meta.duration)}</span>` : ""}${p.settings?.autopilot ? `<span class="pc-ap">✈ Autopilot</span>` : ""}
      ${WORKING.includes(p.status) ? `<div class="pc-prog"><i class="indet"></i></div>` : ""}
      ${canEdit ? `<label class="pc-check" title="चुनें"><input type="checkbox" data-sel="${p.id}" ${S.sel.has(p.id) ? "checked" : ""}></label>` : ""}
      ${opts.hover !== false ? `<div class="pc-hover"><a class="btn small" href="#/projects/${p.id}">खोलें</a>${S.user.role !== "viewer" ? `<a class="btn small quiet" href="#/thumbs/${p.id}">Thumbnail</a>` : ""}</div>` : ""}</div>
    <div class="pc-body"><div class="pc-title"><a href="${href}" title="${esc(p.title)}">${esc(p.title)}</a>${opts.menu !== false ? `<button class="ibtn pc-more" data-menu="${p.id}" aria-label="और विकल्प">${ic("dots")}</button>` : ""}</div>
      <span class="small muted">${ch ? `<i class="dot" style="background:${esc(ch.color || "#F2B33D")}"></i>${esc(ch.name)} · ` : ""}${relTime(p.updated_at)}</span></div></div>`;
}
function prow(p) {
  const [label, cls] = STATUS[p.status] || [p.status, ""]; const canEdit = S.user.role !== "viewer";
  const ch = S.channels.find((c) => c.id === p.channel_id);
  return `<tr data-pid="${p.id}" class="${S.sel.has(p.id) ? "picked" : ""}">${canEdit ? `<td class="cbx"><input type="checkbox" data-sel="${p.id}" ${S.sel.has(p.id) ? "checked" : ""} aria-label="चुनें"></td>` : ""}
    <td class="th"><a href="#/projects/${p.id}">${p.thumb_url ? `<img src="${p.thumb_url}" alt="" loading="lazy">` : `<span class="ph">${ic("film")}</span>`}</a></td>
    <td class="tt"><a href="#/projects/${p.id}">${esc(p.title)}</a>${p.settings?.autopilot ? ` <span class="pill">✈</span>` : ""}<div class="small muted mob">${label} · ${relTime(p.updated_at)}</div></td>
    <td class="hide-m"><span class="status ${cls}">${label}</span></td><td class="hide-m small muted">${esc(ch?.name || "")}</td>
    <td class="hide-m small">${p.meta?.duration ? fmtDur(p.meta.duration) : "—"}</td><td class="hide-m small muted">${relTime(p.updated_at)}</td>
    <td><button class="ibtn pc-more" data-menu="${p.id}" aria-label="और विकल्प">${ic("dots")}</button></td></tr>`;
}
function closeMenu() { const m = document.getElementById("pmenu"); if (m) m.remove(); document.removeEventListener("click", menuOutside, true); }
function menuOutside(e) { if (!e.target.closest("#pmenu") && !e.target.closest("[data-menu]")) closeMenu(); }
function openMenu(id, btn) {
  const was = $("#pmenu")?.dataset.pid; closeMenu(); if (was === id) return;
  const p = S.projects.find((x) => x.id === id) || (S.project?.id === id ? S.project : null); if (!p) return;
  const canEdit = S.user.role !== "viewer";
  const items = [["open", "↗", "खोलें"], ...(canEdit ? [["rename", "✎", "नाम बदलें"], ["dup", "⧉", "कॉपी बनाएँ"], ["thumb", "🖼", "Thumbnail"]] : []),
    ["dl", "⬇", "Final video download करें"], ...(canEdit ? [["archive", "🗄", "Drive में archive करें"], ["-"], ["del", "🗑", "हटाएँ", "danger"]] : [])];
  const m = document.createElement("div"); m.className = "pmenu"; m.id = "pmenu"; m.dataset.pid = id; m.setAttribute("role", "menu");
  m.innerHTML = items.map(([a, i, l, c]) => a === "-" ? `<hr>` : `<button role="menuitem" data-act="${a}" class="${c || ""}"><i>${i}</i>${l}</button>`).join("");
  document.body.appendChild(m);
  const r = btn.getBoundingClientRect(); const mw = m.offsetWidth, mh = m.offsetHeight;
  m.style.left = Math.max(8, Math.min(r.right - mw, innerWidth - mw - 8)) + "px";
  m.style.top = (r.bottom + mh + 8 > innerHeight ? Math.max(8, r.top - mh - 4) : r.bottom + 4) + "px";
  m.onclick = (e) => { const b = e.target.closest("[data-act]"); if (!b) return; closeMenu(); projAction(b.dataset.act, p); };
  setTimeout(() => document.addEventListener("click", menuOutside, true));
}
async function deleteProject(p, after) {
  if (!confirm(`"${p.title}" और उसकी सारी फ़ाइलें server से हटाएँ?\n\nRecording, cutout, renders और thumbnails — सब हट जाएँगे। यह वापस नहीं होगा।`)) return false;
  const arc = p.meta?.archived_at ? confirm("Google Drive या archive में रखी copy भी हटाएँ?\n\nOK — हाँ, वह भी हटाएँ\nCancel — Drive वाली copy रहने दें") : false;
  try { await api("DELETE", `/projects/${p.id}${arc ? "?archive=1" : ""}`); } catch (e) { toast(e.message); return false; }
  S.sel.delete(p.id); toast("Project और उसकी फ़ाइलें हटा दी गईं"); if (after) after(); return true;
}
async function downloadFinal(p) {
  try {
    const full = await api("GET", `/projects/${p.id}`);
    const outs = full.assets.filter((a) => a.kind === "render");
    if (!outs.length) return toast("अभी कोई final video नहीं है — पहले render करें।");
    const a = outs.find((x) => x.label === "yt-long") || outs.find((x) => !String(x.label || "").startsWith("short-")) || outs[0];
    const l = document.createElement("a"); l.href = a.url + "&download=1"; l.download = ""; document.body.appendChild(l); l.click(); l.remove();
    if (outs.length > 1) toast(`इस project में ${outs.length} videos हैं — बाकी project खोलकर download करें।`);
  } catch (e) { toast(e.message); }
}
async function projAction(act, p) {
  if (act === "open") return go(`/projects/${p.id}`);
  if (act === "thumb") return go(`/thumbs/${p.id}`);
  if (act === "dl") return downloadFinal(p);
  if (act === "rename") { const t = prompt("नया नाम", p.title); if (!t || t.trim() === p.title) return; try { await api("PATCH", `/projects/${p.id}`, { title: t.trim() }); toast("नाम बदल दिया"); } catch (e) { toast(e.message); } return load().then(render); }
  if (act === "dup") { toast("कॉपी बन रही है…"); try { const n = await api("POST", `/projects/${p.id}/duplicate`, {}); toast(`“${n.title}” बन गया`); } catch (e) { toast(e.message); } return load().then(render); }
  if (act === "archive") {
    if (p.status !== "approved") return toast("सिर्फ़ मंज़ूर projects archive होते हैं — पहले मंज़ूरी दें।");
    if (!confirm("Raw recording और भारी फ़ाइलें archive (Google Drive) में भेजें? Final videos यहीं रहेंगी।")) return;
    try { const r = await api("POST", `/projects/${p.id}/archive`, {}); toast(`Archive हो गया${r.moved != null ? " — " + r.moved + " फ़ाइलें भेजी गईं" : ""}`); } catch (e) { toast(e.message); } return load().then(render);
  }
  if (act === "del") return deleteProject(p, () => { if (S.route.id === p.id) go("/projects"); else load().then(render); });
}
function bindCards(root = document) {
  $$("[data-menu]", root).forEach((b) => (b.onclick = (e) => { e.preventDefault(); e.stopPropagation(); openMenu(b.dataset.menu, b); }));
  $$("[data-sel]", root).forEach((cb) => (cb.onchange = () => { cb.checked ? S.sel.add(cb.dataset.sel) : S.sel.delete(cb.dataset.sel); cb.closest("[data-pid]")?.classList.toggle("picked", cb.checked); updateBulk(); }));
}
function updateBulk() {
  const bar = $("#bulk"); if (!bar) return; const n = S.sel.size;
  bar.hidden = !n; $("#bulk-n").textContent = n;
  const all = $("#sel-all"); if (all) { const vis = filteredProjects().map((p) => p.id); all.checked = vis.length > 0 && vis.every((id) => S.sel.has(id)); }
}
async function bulk(act) {
  const list = S.projects.filter((p) => S.sel.has(p.id)); if (!list.length) return;
  if (act === "del") {
    if (!confirm(`${list.length} projects और उनकी सारी फ़ाइलें हमेशा के लिए हटाएँ?`)) return;
    const anyArc = list.some((p) => p.meta?.archived_at);
    const arc = anyArc ? confirm("जिनकी Google Drive या archive में copy है, वह copy भी हटाएँ?\n\nOK — हाँ, वह भी हटाएँ\nCancel — Drive वाली copy रहने दें") : false;
    let ok = 0, fail = 0;
    for (const p of list) { try { await api("DELETE", `/projects/${p.id}${arc && p.meta?.archived_at ? "?archive=1" : ""}`); ok++; S.sel.delete(p.id); } catch { fail++; } }
    toast(`${ok} projects हटाए${fail ? ` — ${fail} नहीं हटे (मंज़ूर projects सिर्फ़ admin हटा सकता है)` : ""}`);
  } else if (act === "archive") {
    let ok = 0, skip = 0;
    for (const p of list) { if (p.status !== "approved") { skip++; continue; } try { await api("POST", `/projects/${p.id}/archive`, {}); ok++; } catch { skip++; } }
    toast(`${ok} projects archive हुए${skip ? ` — ${skip} छोड़े (सिर्फ़ मंज़ूर projects archive होते हैं)` : ""}`); S.sel.clear();
  }
  load().then(render);
}

// ---------- projects page ----------
const PFILTERS = [["all", "सब", () => true], ["review", "जाँच बाकी", (p) => ["review_cuts", "review_output"].includes(p.status)], ["working", "चल रहे", (p) => WORKING.includes(p.status)],
  ["approved", "मंज़ूर", (p) => p.status === "approved"], ["failed", "रुके", (p) => p.status === "failed"], ["draft", "Upload अधूरा", (p) => p.status === "uploading"]];
function filteredProjects() {
  const f = PFILTERS.find((x) => x[0] === (S.route.q.get("status") || "all")) || PFILTERS[0]; const q = (S.pq || "").toLowerCase().trim();
  return S.projects.filter((p) => f[2](p) && (!q || p.title.toLowerCase().includes(q)));
}
function projectsView() {
  const cur = S.route.q.get("status") || "all"; const list = filteredProjects(); const canEdit = S.user.role !== "viewer";
  const counts = Object.fromEntries(PFILTERS.map(([k, , fn]) => [k, S.projects.filter(fn).length]));
  return `<div class="pghead"><div><h1>Projects</h1><p class="muted small">${S.projects.length} projects${S.channels.length > 1 ? ` · ${S.pch === "all" ? "सभी channels" : esc(S.channels.find((c) => c.id === (S.pch || S.channel))?.name || "")}` : ""}</p></div>
      ${canEdit ? `<span class="row"><a class="btn" href="#/record">${ic("rec")} Record</a><a class="btn primary" href="#/new">${ic("upload")} Upload</a></span>` : ""}</div>
    <div class="ptools">
      <label class="search">${ic("search")}<input id="p-q" placeholder="नाम से खोजें…" value="${esc(S.pq)}"></label>
      ${S.channels.length > 1 ? `<select id="p-ch"><option value="" ${!S.pch ? "selected" : ""}>यह channel</option><option value="all" ${S.pch === "all" ? "selected" : ""}>सभी channels</option>${S.channels.map((c) => `<option value="${c.id}" ${S.pch === c.id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select>` : ""}
      <div class="seg" role="tablist" aria-label="दिखाने का तरीका"><button data-pv="grid" class="${S.pview === "grid" ? "on" : ""}" title="grid">${ic("grid")}</button><button data-pv="list" class="${S.pview === "list" ? "on" : ""}" title="list">${ic("list")}</button></div>
    </div>
    <div class="fchips">${PFILTERS.map(([k, l]) => `<a class="fchip ${cur === k ? "on" : ""}" href="#/projects${k === "all" ? "" : "?status=" + k}">${l}<i>${counts[k]}</i></a>`).join("")}</div>
    ${canEdit ? `<div class="bulk" id="bulk" ${S.sel.size ? "" : "hidden"}><label class="chk"><input type="checkbox" id="sel-all"> सभी चुनें</label><b><span id="bulk-n">${S.sel.size}</span> चुने</b><span class="grow"></span><button class="btn small" data-bulk="archive">Archive करें</button><button class="btn small danger" data-bulk="del">हटाएँ</button><button class="btn quiet small" id="bulk-x" title="चुनाव हटाएँ" aria-label="चुनाव हटाएँ">✕</button></div>` : ""}
    <div id="plist">${projList(list)}</div>`;
}
function projList(list) {
  if (!list.length) return `<div class="empty">${S.projects.length ? `<p>इस filter में कोई project नहीं।</p>` : `<p>अभी कोई project नहीं।</p><a class="btn primary" href="#/record">पहली recording करें</a>`}</div>`;
  if (S.pview === "list") return `<div class="tablewrap"><table class="ptable"><thead><tr>${S.user.role !== "viewer" ? "<th></th>" : ""}<th></th><th>नाम</th><th class="hide-m">Status</th><th class="hide-m">Channel</th><th class="hide-m">लंबाई</th><th class="hide-m">आख़िरी बदलाव</th><th></th></tr></thead><tbody>${list.map(prow).join("")}</tbody></table></div>`;
  return `<div class="pgrid2">${list.map((p) => pcard(p)).join("")}</div>`;
}
function bindProjects() {
  const redraw = () => { $("#plist").innerHTML = projList(filteredProjects()); bindCards($("#plist")); updateBulk(); };
  const q = $("#p-q"); q.oninput = () => { S.pq = q.value; redraw(); };
  const ch = $("#p-ch"); if (ch) ch.onchange = () => { S.pch = ch.value; S.sel.clear(); load().then(render); };
  $$("[data-pv]").forEach((b) => (b.onclick = () => { S.pview = b.dataset.pv; lsSet("vividora_pview", S.pview); $$("[data-pv]").forEach((x) => x.classList.toggle("on", x === b)); redraw(); }));
  $$("[data-bulk]").forEach((b) => (b.onclick = () => bulk(b.dataset.bulk)));
  const x = $("#bulk-x"); if (x) x.onclick = () => { S.sel.clear(); redraw(); };
  const all = $("#sel-all"); if (all) all.onchange = () => { for (const p of filteredProjects()) all.checked ? S.sel.add(p.id) : S.sel.delete(p.id); redraw(); };
  bindCards($("#plist")); updateBulk();
}

// ---------- home ----------
const TIPS = [
  "Thumbnail पर 2–4 शब्द काफ़ी हैं — title दोहराएँ नहीं, उत्सुकता जगाएँ।",
  "पहले 3 सेकंड में hook बोलें — Shorts में यही तय करता है कि लोग रुकेंगे या नहीं।",
  "2–3 thumbnail variants बनाकर YouTube Studio के “Test & compare” में डालें।",
  "Autopilot चालू रखें: cuts, captions, zoom, music और 3 thumbnails अपने-आप बनते हैं।",
  "Brand kit (Channels & Brand) में logo और रंग एक बार सेट करें — हर वीडियो और thumbnail में लगेगा।",
  "Recorder में teleprompter है — script Plan से सीधे आती है।",
];
function homeView() {
  const review = S.projects.filter((p) => p.status === "review_cuts" || p.status === "review_output");
  const working = S.projects.filter((p) => WORKING.includes(p.status));
  const approved = S.projects.filter((p) => p.status === "approved");
  const canEdit = S.user.role !== "viewer";
  const vids = (S.analytics?.videos || []); const views = vids.reduce((a, v) => a + (v.views || 0), 0);
  const ideas = (S.ideas || []).filter((i) => i.status === "approved").slice(0, 5);
  const trends = (S.homeTrends || []).slice(0, 6);
  const jobs = S.overview?.jobs || []; const upcoming = S.overview?.upcoming || [];
  const hour = new Date().getHours(); const greet = hour < 12 ? "सुप्रभात" : hour < 17 ? "नमस्ते" : "शुभ संध्या";
  const HS = homeSections();
  const sec = (title, link, body, cls = "") => `<section class="card ${cls}"><div class="card-h"><h2>${title}</h2>${link || ""}</div>${body}</section>`;
  const blocks = {
    review: review.length ? sec(`मंज़ूरी बाकी <em class="cnt">${review.length}</em>`, `<a class="small muted" href="#/projects?status=review">सब देखें</a>`, `<div class="pgrid2 compact">${review.slice(0, 6).map((p) => pcard(p, { select: false })).join("")}</div>`, "wide") : "",
    working: sec("चल रहे काम", `<a class="small muted" href="#/status">Status</a>`, jobs.length || working.length ? `<ul class="jobs">${jobs.length ? jobs.map((j) => `<li><a href="#/projects/${j.project_id}"><b>${esc(j.project_title)}</b><span class="small muted">${JOBK[j.kind] || j.kind} · ${j.status === "queued" ? "कतार में" : esc(j.message || "चल रहा है")}</span></a><div class="progress"><i ${j.status === "queued" ? 'class="indet"' : `style="width:${j.progress || 0}%"`}></i></div><span class="small">${j.status === "running" ? (j.progress || 0) + "%" : ""}</span></li>`).join("")
        : working.map((p) => `<li><a href="#/projects/${p.id}"><b>${esc(p.title)}</b><span class="small muted">${(STATUS[p.status] || [])[0]}</span></a><div class="progress"><i class="indet"></i></div><span></span></li>`).join("")}</ul>` : `<p class="small muted">अभी कुछ नहीं चल रहा।</p>`),
    upcoming: sec("आने वाले posts", `<a class="small muted" href="#/publish">Calendar</a>`, upcoming.length ? `<ul class="hlist">${upcoming.slice(0, 5).map((u) => `<li><span><span class="plat ${u.platform}">${PLAT[u.platform] || u.platform}</span> ${esc(u.title)}</span><span class="small muted">${u.when ? new Date(u.when).toLocaleString("hi-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : u.status === "running" ? "Upload हो रहा है" : "कतार में"}</span></li>`).join("")}</ul>` : `<p class="small muted">कोई post scheduled नहीं। मंज़ूर वीडियो खोलकर Publish करें।</p>`),
    recent: sec("हाल के projects", `<a class="small muted" href="#/projects">सभी projects</a>`, S.projects.length ? `<div class="pgrid2">${S.projects.slice(0, 8).map((p) => pcard(p)).join("")}</div>` : `<div class="empty"><p>अभी कोई project नहीं।</p><a class="btn primary" href="#/record">पहली recording करें</a></div>`, "wide"),
    published: vids.length ? sec("हाल में published", `<a class="small muted" href="#/analytics">Analytics</a>`, `<ul class="hlist">${vids.slice(0, 5).map((v) => `<li><a href="${v.url}" target="_blank" rel="noopener">${esc(v.title)}</a><span class="small muted">${v.platform} · ${(v.views || 0).toLocaleString("en-IN")} views</span></li>`).join("")}</ul>`) : "",
    storage: S.user.role === "admin" ? sec("Storage", `<a class="small muted" href="#/account">जगह खाली करें</a>`, `<div id="home-storage"><p class="small muted">जाँच हो रही है…</p></div>`) : "",
    ideas: sec("Record करने के लिए", `<a class="small muted" href="#/plan">Plan</a>`, ideas.length ? `<ul class="hlist">${ideas.map((i) => `<li><a href="#/record"><b>${esc(i.title)}</b></a>${i.script ? `<span class="pill">script ✓</span>` : ""}</li>`).join("")}</ul>` : `<p class="small muted">Plan में ideas बनाएँ और उन्हें “बनाना है” में रखें — वे यहाँ दिखेंगे।</p>`),
    trends: sec("आज trending", `<a class="small muted" href="#/trends">Radar</a>`, trends.length ? `<ul class="hlist">${trends.map((r) => `<li>${r.url ? `<a href="${r.url}" target="_blank" rel="noopener">${esc(r.title)}</a>` : esc(r.title)}<span class="small muted">${r.meta?.traffic ? r.meta.traffic + "+" : r.meta?.channel ? esc(r.meta.channel) : ""}</span></li>`).join("")}</ul>` : `<p class="small muted">Trends पेज पर “ताज़ा करें” दबाएँ।</p>`),
    tips: sec("आज की tip", "", `<p class="tip">💡 ${TIPS[new Date().getDate() % TIPS.length]}</p><a class="small muted" href="#/help">Help में और tips</a>`),
    library: sec("Library", `<a class="small muted" href="#/library">खोलें</a>`, `<div class="hlibq"><a href="#/library" class="qtile"><i>🎵</i><b>Music & SFX</b></a><a href="#/library" class="qtile"><i>📣</i><b>Popups</b></a><a href="#/library" class="qtile"><i>😀</i><b>Stickers</b></a><a href="#/library" class="qtile"><i>🖼</i><b>Frames</b></a></div>`),
  };
  const SIDE = ["working", "upcoming", "storage", "ideas", "trends", "tips", "library"];
  const order = HS.filter((x) => x.on).map((x) => x.id);
  const main = order.filter((id) => blocks[id] !== undefined && !SIDE.includes(id)).map((id) => blocks[id]).join("");
  const side = order.filter((id) => SIDE.includes(id)).map((id) => blocks[id]).join("");
  const counters = [["review", review.length, "मंज़ूरी बाकी", "#/projects?status=review"], ["working", working.length, "चल रहे", "#/projects?status=working"], ["approved", approved.length, "मंज़ूर", "#/projects?status=approved"],
    ["pub", vids.length, "Published", "#/publish"], ["views", views.toLocaleString("en-IN"), "Views", "#/analytics"]];
  return `<div class="home2">
    ${HS.find((x) => x.id === "hero")?.on ? `<div class="hero2"><div class="hero2-t"><p class="kicker">${greet}, ${esc(S.user.name.split(" ")[0])}</p><h1>${review.length ? `${review.length} वीडियो आपकी मंज़ूरी का इंतज़ार कर रहे हैं` : working.length ? `${working.length} वीडियो पर काम चल रहा है` : "आज क्या बनाएँ?"}</h1>
      <p class="muted">Record या upload करें — Vividora cuts, captions, zoom, music, Shorts, titles और thumbnails तैयार कर देगा। आपको बस मंज़ूरी देनी है।</p></div>
      <button class="btn small quiet hcust-btn" id="home-custom" title="Sections दिखाएँ या छुपाएँ">⚙ Customize</button>
      ${canEdit ? `<div class="qacts">${[["#/record", "rec", "Record", "Camera और teleprompter", "c1"], ["#/new", "upload", "Upload", "Recording या clips", "c2"], ["#/new?type=montage", "music", "Montage", "Music और clips", "c3"], ["#/plan", "bulb", "Plan", "Trends, ideas और script", "c4"], ["#/thumbs", "image", "Thumbnail", "ज़्यादा clicks वाले thumbnails", "c5"]].map(([h, i, b, s, c]) => `<a class="qact ${c}" href="${h}"><span class="qi">${ic(i)}</span><b>${b}</b><span>${s}</span></a>`).join("")}</div>` : ""}</div>` : `<div class="row between"><span></span><button class="btn small quiet" id="home-custom">⚙ Customize</button></div>`}
    <div id="home-cust" hidden class="box hcust"><b>Home के sections</b> <span class="small muted">— दिखाएँ या छुपाएँ, ↑↓ से क्रम बदलें। यह इसी browser में याद रहता है।</span><ul>${HS.map((x, i) => `<li><label class="chk"><input type="checkbox" data-hs="${x.id}" ${x.on ? "checked" : ""}> ${x.label}</label><span><button class="btn small quiet" data-hsu="${i}">↑</button><button class="btn small quiet" data-hsd="${i}">↓</button></span></li>`).join("")}</ul></div>
    ${HS.find((x) => x.id === "stats")?.on ? `<div class="stats2">${counters.map(([k, n, l, h]) => `<a class="stat ${k}" href="${h}"><b>${n}</b><span>${l}</span></a>`).join("")}</div>` : ""}
    <div class="hcols2"><div class="hmain">${main}</div><div class="hside2">${side}</div></div></div>`;
}
const HOME_DEFAULT = [["hero", "स्वागत और quick actions"], ["stats", "गिनती"], ["review", "मंज़ूरी बाकी"], ["working", "चल रहे काम"], ["recent", "हाल के projects"], ["upcoming", "आने वाले posts"], ["published", "हाल में published"], ["storage", "Storage (admin)"], ["ideas", "Record करने के लिए"], ["trends", "आज trending"], ["tips", "आज की tip"], ["library", "Library shortcuts"]];
function homeSections() {
  let saved = []; try { saved = JSON.parse(localStorage.getItem("vividora_home") || "[]"); } catch {}
  const known = new Map(HOME_DEFAULT.map(([id, label]) => [id, label]));
  const out = saved.filter((x) => known.has(x.id)).map((x) => ({ id: x.id, on: x.on !== false, label: known.get(x.id) }));
  for (const [id, label] of HOME_DEFAULT) if (!out.find((x) => x.id === id)) out.push({ id, on: true, label });
  return out;
}
function bindHome() {
  const save = (list) => { try { localStorage.setItem("vividora_home", JSON.stringify(list.map(({ id, on }) => ({ id, on })))); } catch {} render(); setTimeout(() => { const c = $("#home-cust"); if (c) c.hidden = false; }); };
  const b = $("#home-custom"); if (b) b.onclick = () => { const c = $("#home-cust"); c.hidden = !c.hidden; };
  document.querySelectorAll("[data-hs]").forEach((cb) => (cb.onchange = () => { const l = homeSections(); l.find((x) => x.id === cb.dataset.hs).on = cb.checked; save(l); }));
  document.querySelectorAll("[data-hsu]").forEach((x) => (x.onclick = () => { const l = homeSections(); const i = +x.dataset.hsu; if (i > 0) { [l[i - 1], l[i]] = [l[i], l[i - 1]]; save(l); } }));
  document.querySelectorAll("[data-hsd]").forEach((x) => (x.onclick = () => { const l = homeSections(); const i = +x.dataset.hsd; if (i < l.length - 1) { [l[i + 1], l[i]] = [l[i], l[i + 1]]; save(l); } }));
  bindCards();
  const hs = $("#home-storage");
  if (hs) {
    const paint = (d) => { const m = d.disk.media; const pct = Math.round(m.used / m.total * 100); hs.innerHTML = `<div class="stbar"><i style="width:${pct}%;background:${pct > 85 ? "#e5484d" : pct > 70 ? "#f2b33d" : "#46a758"}"></i></div><p class="small"><b>${fmtBytes(m.free)} खाली</b> · ${fmtBytes(m.used)} / ${fmtBytes(m.total)} (${pct}%)</p>${d.groups ? `<p class="small muted">recordings ${fmtBytes(d.groups.source || 0)} · videos ${fmtBytes(d.groups.render || 0)} · cache ${fmtBytes(d.groups.cache || 0)}</p>` : ""}`; };
    if (S.storageCache && Date.now() - S.storageCache.at < 120000) paint(S.storageCache.d);
    else api("GET", "/storage").then((d) => { S.storageCache = { at: Date.now(), d }; if (document.body.contains(hs)) paint(d); }).catch((e) => { hs.innerHTML = `<p class="small muted">${esc(e.message)}</p>`; });
  }
}
function loginView() {
  return `<div class="login"><form id="login"><div class="brand"><i></i>Vividora</div><p class="muted">आपका video studio — आगे बढ़ने के लिए login करें।</p>
    <div class="field"><label>Email</label><input name="email" type="email" autocomplete="username" required></div>
    <div class="field"><label>Password</label><input name="password" type="password" autocomplete="current-password" required></div>
    <div id="login-err"></div><button class="btn primary" style="width:100%;justify-content:center">Login करें</button></form></div>`;
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
  return `<div class="pghead"><div><h1>नया वीडियो</h1><p class="muted">पहले नाम दें, फिर फ़ाइल चुनें। Upload बीच में टूटे तो वहीं से फिर शुरू होता है।</p></div></div>${chn ? `<p class="small muted">Channel: <b style="color:${esc(chn.color || "#F2B33D")}">${esc(chn.name)}</b> — इसी channel का brand kit और connections लगेंगे। Channel बाएँ menu में ऊपर से बदलें।</p>` : ""}${idea ? `<div class="note">Idea: <b>${esc(idea.title)}</b> — upload के बाद यह “Record हो गया” में चला जाएगा।</div>` : ""}
    <div class="choices" style="margin-bottom:1rem"><label class="chip on"><input type="radio" name="ptype" value="talking_head" checked>Recording — मेरी आवाज़ वाला वीडियो</label><label class="chip"><input type="radio" name="ptype" value="montage">Montage — music और clips, बिना आवाज़</label></div>
    <form id="new"><div class="field"><label>वीडियो का नाम</label><input name="title" required placeholder="जैसे: 4 बजे उठने वाला लड़का" value="${idea ? esc(idea.title) : ""}"></div>
    <div class="field"><label>भाषा</label><select name="language"><option value="auto">अपने-आप पहचानें (हिंदी / English / Hinglish)</option><option value="hi">हिंदी</option><option value="en">English</option></select></div>
    <div class="drop" id="drop" data-upload="1"><input type="file" id="file" accept="video/*,audio/*,.mkv,.mts" multiple hidden><b>फ़ाइलें यहाँ खींचकर छोड़ें, या click करके चुनें</b><br><span class="muted small">MP4, MOV, MKV, WebM — 20 GB तक। कई clips चुनें तो वे क्रम से एक timeline पर जुड़ेंगी।</span><div id="fname" class="small" style="margin-top:.5rem"></div></div>
    <div id="mo-new" hidden>
      <div class="drop" id="mo-drop"><input type="file" id="mo-files" accept="video/*,image/*,.mov,.mkv" multiple hidden><b>Clips और photos यहाँ छोड़ें, या click करके चुनें</b><br><span class="muted small">छोटे-बड़े, किसी भी ratio के — best हिस्से अपने-आप चुने जाएँगे</span><div id="mo-fnames" class="small" style="margin-top:.5rem"></div></div>
      <div class="row" style="gap:1rem;flex-wrap:wrap;align-items:flex-end;margin-top:.75rem">
        <div class="field" style="flex:1;min-width:220px"><label>Song / music</label><label class="btn small" style="display:inline-flex">गाना चुनें (mp3, m4a, या reel का mp4)<input type="file" id="mo-song" accept="audio/*,video/mp4,.m4a,.mp3,.wav" hidden></label> <span id="mo-songname" class="small muted"></span>
          <select id="mo-libsong" style="margin-top:.4rem"><option value="">…या library का music</option></select></div>
        <div class="field"><label>Format</label><select id="mo-preset"><option value="ig-reel">9:16 Reel / Short</option><option value="yt-short">9:16 YouTube Short</option><option value="yt-long">16:9 YouTube</option></select></div>
        <div class="field"><label>लंबाई</label><select id="mo-len">${[10, 15, 20, 30, 45, 60].map((n) => `<option value="${n}" ${n === 30 ? "selected" : ""}>${n}s</option>`).join("")}</select></div>
      </div>
      <label class="chk" style="margin:.5rem 0;display:flex;gap:.5rem;align-items:center"><input type="checkbox" id="mo-auto" checked> <span><b>✨ Auto beat-edit तुरंत शुरू करें</b> — beat पर cut, effects, color, auto-crop। बाद में हर cut बदल सकते हैं।</span></label>
    </div>
    <label class="chk" id="ap-row" style="margin:.5rem 0;display:flex;gap:.5rem;align-items:center"><input type="checkbox" name="autopilot" checked> <span><b>✈ Autopilot</b> — upload के बाद पूरा edit अपने-आप होगा (cuts, captions, zoom, music, Shorts, titles)। आपको बस देखकर मंज़ूरी देनी है।</span></label>
    <div id="up-progress"></div>
    <div class="actionbar"><a class="btn quiet" href="#/">रद्द करें</a><button class="btn primary" id="start" disabled>Upload शुरू करें</button></div></form>`;
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
  const moBox = $("#mo-new"), moFiles = []; let moSong = null;
  document.querySelectorAll("input[name=ptype]").forEach((i) => (i.onchange = () => { ptype = i.value; document.querySelectorAll(".chip").forEach((c) => c.classList.toggle("on", c.contains(i))); const mont = ptype === "montage";
    drop.style.display = mont ? "none" : ""; moBox.hidden = !mont; $("#ap-row").style.display = mont ? "none" : "flex"; $("#start").textContent = mont ? "Montage बनाएँ" : "Upload शुरू करें"; $("#start").disabled = mont ? false : !chosen;
    if (mont && !moBox.dataset.lib) { moBox.dataset.lib = "1"; api("GET", "/library").then((lib) => { $("#mo-libsong").innerHTML += lib.filter((x) => x.kind === "music").map((x) => `<option value="${x.id}">${esc(x.name)}</option>`).join(""); }).catch(() => {}); } }));
  const moDrop = $("#mo-drop"), moIn = $("#mo-files");
  const moShow = () => { $("#mo-fnames").innerHTML = moFiles.length ? moFiles.map((f, n) => `${n + 1}. ${esc(f.name)} · ${gb(f.size)}`).join("<br>") : ""; };
  moDrop.onclick = (e) => { if (e.target === moIn) return; moIn.click(); };
  moDrop.ondragover = (e) => { e.preventDefault(); moDrop.classList.add("over"); }; moDrop.ondragleave = () => moDrop.classList.remove("over");
  moDrop.ondrop = (e) => { e.preventDefault(); moDrop.classList.remove("over"); moFiles.push(...[...e.dataTransfer.files].filter((f) => /^(video|image)\//.test(f.type) || /\.(mov|mkv|mp4|jpe?g|png|webp)$/i.test(f.name))); moShow(); };
  moIn.onchange = () => { moFiles.push(...moIn.files); moIn.value = ""; moShow(); };
  $("#mo-song").onchange = (e) => { moSong = e.target.files[0] || null; $("#mo-songname").textContent = moSong ? moSong.name : ""; };
  if (/type=montage/.test(location.hash)) { const r = document.querySelector('input[name=ptype][value=montage]'); if (r) { r.checked = true; r.onchange(); } }
  $("#new").onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target;
    if (ptype === "montage") {
      const auto = $("#mo-auto").checked; const libSong = $("#mo-libsong").value;
      if (auto && !moFiles.length) return toast("पहले clips/photos चुनें");
      if (auto && !moSong && !libSong) return toast("गाना चुनें (या library का music)");
      $("#start").disabled = true; const prog = $("#up-progress");
      try {
        const p = await api("POST", "/projects", { title: f.title.value, language: f.language.value, kind: "montage", channel_id: S.channel });
        const ids = [];
        for (let n = 0; n < moFiles.length; n++) { const fl = moFiles[n]; const kind = fl.type.startsWith("image/") || /\.(jpe?g|png|webp)$/i.test(fl.name) ? "image" : "broll";
          const d = await libPut(kind, fl, (pc) => { prog.innerHTML = `<p class="small muted">Clip ${n + 1}/${moFiles.length} upload — ${pc}%</p><div class="progress"><i style="width:${pc}%"></i></div>`; }); ids.push({ id: d.id, duration: d.meta?.duration }); }
        let music = libSong;
        if (moSong) { const d = await libPut("music", moSong, (pc) => { prog.innerHTML = `<p class="small muted">गाना upload — ${pc}%</p><div class="progress"><i style="width:${pc}%"></i></div>`; }); music = d.id; }
        if (auto) { await api("POST", `/projects/${p.id}/montage`, { mode: "auto", replan: true, auto_render: true, plan: null, clips: ids, music, preset: $("#mo-preset").value, max_seconds: +$("#mo-len").value, look: "auto", pace: "auto", effects_level: "auto", reframe: "smart", slowmo: true, texts: [] }); toast("Clips देखे जा रहे हैं → beat plan → video ⏳"); }
        go("/projects/" + p.id);
      } catch (err) { prog.innerHTML = `<div class="note err">${esc(err.message)}</div>`; $("#start").disabled = false; }
      return;
    }
    if (!chosen) return;
    $("#start").disabled = true;
    try {
      const p = await api("POST", "/projects", { title: f.title.value, language: f.language.value, autopilot: f.autopilot.checked, channel_id: S.channel });
      const ideaId = (location.hash.match(/idea=([0-9a-f]+)/) || [])[1]; if (ideaId) api("PATCH", `/ideas/${ideaId}`, { project_id: p.id, status: "recorded" }).catch(() => {});
      if (chosenAll.length > 1) {
        for (let i = 0; i < chosenAll.length; i++) { const f = chosenAll[i]; await uploadFile(p.id, f, (done, total) => { $("#up-progress").innerHTML = `<p class="small muted">Clip ${i + 1}/${chosenAll.length} — ${gb(done)} / ${gb(total)}</p><div class="progress"><i style="width:${(done / total * 100).toFixed(1)}%"></i></div>`; }, { clip: true, start: i === chosenAll.length - 1 }); }
      } else
      await uploadFile(p.id, chosen, (done, total) => { $("#up-progress").innerHTML = `<p class="small muted">${gb(done)} / ${gb(total)}</p><div class="progress"><i style="width:${(done / total * 100).toFixed(1)}%"></i></div>`; });
      toast("Upload पूरा हुआ — जाँच शुरू हो गई"); go("/projects/" + p.id);
    } catch (err) { $("#up-progress").innerHTML = `<div class="note err">${esc(err.message)} — फिर से कोशिश करें, upload वहीं से आगे चलेगा।</div>`; $("#start").disabled = false; }
  };
}
function libPut(kind, file, onPct) {
  // library upload with progress (fetch has no upload progress)
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("PUT", `/api/library?kind=${kind}&filename=${encodeURIComponent(file.name)}${S.channel ? "&channel=" + S.channel : ""}`);
    x.setRequestHeader("authorization", "Bearer " + S.token); x.setRequestHeader("content-type", "application/octet-stream");
    x.upload.onprogress = (e) => { if (e.lengthComputable) onPct(Math.round(e.loaded / e.total * 100)); };
    x.onload = () => { let d = {}; try { d = JSON.parse(x.responseText); } catch {} if (x.status < 300) resolve(d); else reject(new Error(d.error || `upload ${x.status}`)); };
    x.onerror = () => reject(new Error("network — upload टूट गया, फिर कोशिश करें"));
    x.send(file);
  });
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
  if (p.status === "uploading") body = `<div class="note">Upload पूरा नहीं हुआ। <a href="#/new">नया वीडियो</a> से फ़ाइल फिर से डालें।</div>`;
  else if (["preparing", "transcribing", "cutting"].includes(p.status)) body = workingView(p, job);
  else if (p.status === "failed") body = `<div class="note err"><b>रुक गया:</b> ${esc(p.status_note)}</div>${canEdit ? `<button class="btn" id="retry-cuts">कट दोबारा ढूँढें</button>` : ""}`;
  else body = reviewView(p, proxy, canEdit) + renderSection(p, canEdit) + outputsSection(p, canEdit);
  return `<div class="row between"><div><a class="btn quiet" href="#/projects" style="padding-left:0">← सभी projects</a><h1 id="title" ${canEdit ? 'contenteditable="true" spellcheck="false"' : ""}>${esc(p.title)}</h1>
      <span class="status ${cls}">${label}</span> <span class="muted small">${esc(p.status_note || "")}</span></div>
      ${canEdit ? `<span class="row"><a class="btn" href="#/thumbs/${p.id}">Thumbnail</a><button class="btn danger quiet" id="del">हटाएँ</button></span>` : ""}</div>
    ${p.meta.duration ? `<p class="muted small">${fmt(p.meta.duration)} · ${p.meta.width}×${p.meta.height} · ${p.meta.fps} fps · भाषा ${{hi:"हिंदी",en:"English",auto:"पहचान बाकी"}[p.language] || p.language} · आवाज़ ${p.meta.denoise === "deepfilternet" ? "DeepFilterNet से साफ़" : p.meta.denoise === "ffmpeg" ? "साफ़ की गई" : "जैसी थी"}</p>` : ""}
    ${body}`;
}
function workingView(p, job) {
  return `<div class="section"><h2>${(STATUS[p.status] || [])[0]}</h2>
    <div class="progress"><i style="width:${job ? job.progress : 0}%"></i></div>
    <p class="muted small" style="margin-top:.5rem">${esc(job ? (job.message || "") : "")}${p.status === "transcribing" ? " — इसके लिए GPU worker चाहिए (Status पेज देखें)" : ""}</p></div>`;
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
      : `<p class="muted">कोई कट नहीं सुझाया गया — recording पहले से साफ़ है।</p>`}
    ${canEdit ? `<div class="row" style="margin-top:.75rem"><button class="btn" id="save-cuts">कट सेव करें</button>
      <label class="small muted">रुकावट की सीमा <input type="number" id="max-pause" step="0.1" min="0.2" max="3" value="${edl.options?.max_pause ?? 0.55}" style="width:70px;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:.2rem .4rem"> s</label>
      <button class="btn quiet" id="recut">दोबारा ढूँढें</button></div>` : ""}
    ${words.length ? `<details style="margin-top:1rem"><summary class="muted">Transcript (${words.length} शब्द) — किसी शब्द पर click करके वहाँ जाएँ</summary>
      <p class="words" id="words">${words.map((w, i) => `<span data-i="${i}" data-s="${w.start}" data-e="${w.end}">${esc(w.w)}</span>`).join(" ")}</p></details>` : ""}
  </div>`;
}
function renderSection(p, canEdit) {
  if (!canEdit || !S.presets) return "";
  const d = p.render_defaults;
  return `<div class="section"><h2>Render</h2>
    <div class="field"><label>कहाँ के लिए</label><div class="choices">${S.presets.platforms.map((pl) => `<label class="chip ${d.presets.includes(pl.id) ? "on" : ""}"><input type="checkbox" name="preset" value="${pl.id}" ${d.presets.includes(pl.id) ? "checked" : ""}>${esc(pl.label)}</label>`).join("")}</div></div>
    <div class="field"><label>Caption style</label><div class="styles">${S.presets.caption_styles.map((cs) => stylePreview(cs, d.caption_style === cs.id)).join("")}</div></div>
    <details class="capopts" ${hasOverrides(d.captions) ? "open" : ""}><summary class="muted">Caption अपने हिसाब से बदलें — आकार, जगह, रंग, font</summary>
      <div class="row" style="margin-top:.6rem">
        <div class="field"><label>आकार</label><input type="range" id="cap-size" min="0.6" max="1.8" step="0.05" value="${d.captions?.size_scale ?? 1}"></div>
        <div class="field"><label>जगह</label><select id="cap-pos"><option value="">style जैसी</option><option value="bottom" ${d.captions?.position === "bottom" ? "selected" : ""}>नीचे</option><option value="center" ${d.captions?.position === "center" ? "selected" : ""}>बीच में</option><option value="top" ${d.captions?.position === "top" ? "selected" : ""}>ऊपर</option></select></div>
        <div class="field"><label>अक्षर का रंग</label><input type="color" id="cap-primary" value="${d.captions?.primary || "#ffffff"}"></div>
        <div class="field"><label>Highlight रंग</label><input type="color" id="cap-highlight" value="${d.captions?.highlight || "#ffd400"}"></div>
        <div class="field"><label>Font</label><select id="cap-font"><option value="">style जैसा</option>${(S.presets.fonts || []).map((f) => `<option ${d.captions?.font === f ? "selected" : ""}>${f}</option>`).join("")}</select></div>
        <label class="small muted" style="align-self:end;padding-bottom:1rem"><input type="checkbox" id="cap-usecolors" ${d.captions?.primary ? "checked" : ""}> ऊपर के रंग लागू करें</label>
      </div></details>
    <div class="row"><div class="field" style="flex:1;min-width:200px"><label>शुरुआत का hook (3 सेकंड; खाली छोड़ें तो नहीं लगेगा)</label><input id="hook" value="${esc(d.hook?.text || "")}" placeholder="4 बजे उठने वाला लड़का"></div>
      <div class="field"><label>9:16 में चेहरा कहाँ</label><select id="focus"><option value="0.5" ${d.focus_x == 0.5 ? "selected" : ""}>बीच</option><option value="0.25" ${d.focus_x == 0.25 ? "selected" : ""}>बाएँ</option><option value="0.75" ${d.focus_x == 0.75 ? "selected" : ""}>दाएँ</option></select></div></div>
    <div class="actionbar"><button class="btn primary" id="render" ${p.status === "rendering" ? "disabled" : ""}>${p.status === "rendering" ? "Render हो रहा है…" : "Render करें"}</button></div></div>`;
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
        <div class="row"><a class="btn small" href="${a.url}&download=1">Download</a>${srt ? `<a class="btn quiet small" href="${srt.url}&download=1">SRT</a>` : ""}</div></div>`; }).join("")}</div>
    ${p.status === "review_output" && S.user.role !== "admin" ? `<p class="muted small" style="margin-top:.75rem">मंज़ूरी admin देंगे।</p>` : ""}</div>`;
}

function bindProject(p) {
  const title = $("#title");
  if (title && title.isContentEditable) title.onblur = async () => { const t = title.textContent.trim(); if (t && t !== p.title) { await api("PATCH", `/projects/${p.id}`, { title: t }); toast("नाम बदल दिया"); load().then(render); } };
  const del = $("#del"); if (del) del.onclick = () => deleteProject(p, () => go("/projects"));
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
  const save = $("#save-cuts"); if (save) save.onclick = async () => { await api("PATCH", `/projects/${p.id}`, { edl: { cuts: p.edl.cuts } }); toast("कट सेव हो गए"); load().then(render); };
  const recut = $("#recut"); if (recut) recut.onclick = async () => { await api("POST", `/projects/${p.id}/recut`, { options: { max_pause: +$("#max-pause").value } }); load().then(render); };
  document.querySelectorAll(".stylecard input").forEach((i) => (i.onchange = () => { document.querySelectorAll(".stylecard").forEach((c) => c.classList.remove("on")); i.closest(".stylecard").classList.add("on"); }));
  document.querySelectorAll(".chip input").forEach((i) => (i.onchange = () => { if (i.type === "radio") i.closest(".choices").querySelectorAll(".chip").forEach((c) => c.classList.remove("on")); i.closest(".chip").classList.toggle("on", i.checked); }));
  const rb = $("#render"); if (rb) rb.onclick = async () => {
    const presets = [...document.querySelectorAll('input[name=preset]:checked')].map((i) => i.value);
    const caption_style = $('input[name=cstyle]:checked')?.value;
    const useColors = $("#cap-usecolors")?.checked;
    const captions = { size_scale: +($("#cap-size")?.value || 1), position: $("#cap-pos")?.value || "", font: $("#cap-font")?.value || "",
      primary: useColors ? $("#cap-primary").value : "", highlight: useColors ? $("#cap-highlight").value : "" };
    try { await api("POST", `/projects/${p.id}/render`, { presets, caption_style, captions, hook: { text: $("#hook").value.trim(), seconds: 3 }, focus_x: +$("#focus").value }); toast("Render शुरू हो गया"); load().then(render); }
    catch (err) { toast(err.message); }
  };
  const ap = $("#approve"); if (ap) ap.onclick = async () => { if (confirm("यह वीडियो मंज़ूर करें? इसके बाद download/publish किया जा सकेगा।")) { await api("POST", `/projects/${p.id}/approve`); toast("मंज़ूरी दे दी"); load().then(render); } };
}

// ---------- users / status ----------
function usersView() {
  return `<h1>Users</h1><p class="muted">Admin सब कुछ कर सकता है और आख़िरी मंज़ूरी देता है। Editor upload, कट और render कर सकता है। Viewer सिर्फ़ देख सकता है।</p>
    <div class="tablewrap"><table><tr><th>नाम</th><th>Email</th><th>Role</th><th>आख़िरी login</th><th></th></tr>${(S.users || []).map((u) => `<tr class="${u.active ? "" : "muted"}"><td>${esc(u.name)}</td><td>${esc(u.email)}</td>
      <td><select data-id="${u.id}" class="role" ${u.id === S.user.id ? "disabled" : ""}>${["admin", "editor", "viewer"].map((r) => `<option ${u.role === r ? "selected" : ""}>${r}</option>`).join("")}</select></td>
      <td class="small">${u.last_login_at ? new Date(u.last_login_at).toLocaleString("hi-IN") : "कभी नहीं"}</td>
      <td>${u.id !== S.user.id ? `<button class="btn quiet small toggle" data-id="${u.id}" data-active="${u.active}">${u.active ? "बंद करें" : "चालू करें"}</button>` : ""}</td></tr>`).join("")}</table></div>
    <div class="section"><h2>नया user</h2><form id="adduser" class="row">
      <div class="field"><label>नाम</label><input name="name" required></div><div class="field"><label>Email</label><input name="email" type="email" required></div>
      <div class="field"><label>Password (कम से कम 8 अक्षर)</label><input name="password" type="password" minlength="8" required></div>
      <div class="field"><label>Role</label><select name="role"><option>editor</option><option>viewer</option><option>admin</option></select></div>
      <button class="btn primary">User जोड़ें</button></form></div>
    <div class="section"><h2>अपना password</h2><form id="pw" class="row"><div class="field"><label>मौजूदा password</label><input name="current" type="password" required></div><div class="field"><label>नया password</label><input name="new" type="password" minlength="8" required></div><button class="btn">Password बदलें</button></form></div>`;
}
function bindUsers() {
  document.querySelectorAll(".role").forEach((s) => (s.onchange = () => api("PATCH", `/users/${s.dataset.id}`, { role: s.value }).then(() => toast("Role बदल दिया")).catch((e) => toast(e.message))));
  document.querySelectorAll(".toggle").forEach((b) => (b.onclick = () => api("PATCH", `/users/${b.dataset.id}`, { active: b.dataset.active !== "true" }).then(() => load().then(render))));
  $("#adduser").onsubmit = async (e) => { e.preventDefault(); const f = e.target; try { await api("POST", "/users", { name: f.name.value, email: f.email.value, password: f.password.value, role: f.role.value }); toast("User जोड़ दिया"); load().then(render); } catch (err) { toast(err.message); } };
  $("#pw").onsubmit = async (e) => { e.preventDefault(); const f = e.target; try { await api("POST", "/auth/password", { current: f.current.value, new: f.new.value }); toast("Password बदल दिया"); f.reset(); } catch (err) { toast(err.message); } };
}
function statusView() {
  const st = S.status || { workers: [], jobs: {}, disk: {} };
  const online = (w) => Date.now() - new Date(w.last_seen_at).getTime() < 90000;
  return `<h1>Status</h1>
    <div class="section"><h2>Workers</h2>${st.workers.length ? `<div class="tablewrap"><table><tr><th>नाम</th><th>काम</th><th>हालत</th><th>जानकारी</th></tr>${st.workers.map((w) => `<tr><td>${esc(w.name)}</td><td class="small">${w.kinds.join(", ")}</td><td><span class="status ${online(w) ? "approved" : "failed"}">${online(w) ? "online" : "offline · " + new Date(w.last_seen_at).toLocaleTimeString("hi-IN")}</span></td><td class="small muted">${esc(Object.entries(w.info || {}).map(([k, v]) => `${k}: ${v}`).join(" · "))}</td></tr>`).join("")}</table></div>` : `<p class="muted">अभी कोई worker नहीं जुड़ा है। Docker वाला worker और Windows PC का GPU worker चालू करें।</p>`}
      ${!st.workers.some((w) => w.kinds.includes("transcribe") && online(w)) ? `<div class="note">Transcript बनाने वाला worker online नहीं है — नए वीडियो “Transcript बन रहा है” पर रुके रहेंगे। Windows PC पर GPU worker चलाएँ।</div>` : ""}</div>
    <div class="section"><h2>Queue</h2><p>${Object.entries(st.jobs).map(([k, v]) => `${k}: <b>${v}</b>`).join(" · ") || "खाली"}</p></div>
    <div class="section"><h2>Archive</h2><p class="small muted">${st.archive?.backend ? `Backend: <b>${esc(st.archive.backend)}</b>${st.archive.remote ? ` · ${esc(st.archive.remote)}` : ""} · मंज़ूरी के ${st.archive.after_days} दिन बाद raw files अपने-आप archive` : ".env में ARCHIVE_RCLONE_REMOTE (Google Drive) या ARCHIVE_ROOT सेट करें — docs/google-drive.md"}</p></div>
    <div class="section"><h2>Disk</h2>${Object.entries(st.disk).map(([k, d]) => `<p>${k === "raw" ? `D: drive (originals) · ${d.active ? "✓ चालू" : "✗ बंद — share mount नहीं, files VM disk पर जा रही हैं"}` : k === "media" ? "VM disk (proxy, renders)" : k}: ${gb(d.used)} / ${gb(d.total)} <span class="muted">(${gb(d.free)} खाली)</span></p><div class="progress"><i style="width:${(d.used / d.total * 100).toFixed(0)}%"></i></div>`).join("")}</div>
    <div class="section"><h2>हाल की गतिविधि</h2><div class="tablewrap"><table>${(S.activity || []).slice(0, 40).map((a) => `<tr><td class="small muted">${new Date(a.created_at).toLocaleString("hi-IN")}</td><td class="small">${esc(a.user_name || "system")}</td><td class="small">${esc(a.action)} ${esc(a.detail?.title || a.detail?.email || a.detail?.file || (a.detail?.presets || []).join(",") || "")}</td></tr>`).join("")}</table></div></div>`;
}

// ---------- settings / connections ----------
const PLAT = { youtube: "YouTube", instagram: "Instagram", facebook: "Facebook" };
function settingsView() {
  const c = S.conns || { connections: [], setup: {} }; const st = c.setup || {}; const admin = S.user.role === "admin";
  const chn = S.channels.find((c) => c.id === S.channel);
  return `<div class="pghead"><div><h1>Channels & Brand</h1><p class="muted small">Channels, brand kit और YouTube, Instagram, Facebook connections</p></div></div>
    <div class="section" style="margin-top:0;border:0;padding-top:0"><div class="row between"><h2>आपके channels <em class="cnt">${S.channels.length}</em></h2>${admin ? `<button class="btn small" id="ch-add">+ नया channel</button>` : ""}</div>
      <div class="chgrid">${S.channels.map((c) => `<div class="chcard ${c.id === S.channel ? "on" : ""}" data-ch="${c.id}" style="--c:${esc(c.color || "#F2B33D")}"><b>${esc(c.name)}</b><span class="small muted">${[c.handle, c.niche || "niche तय नहीं", `${c.projects} projects`, (c.platforms || []).join(", ") || "कोई account नहीं जुड़ा"].filter(Boolean).map(esc).join(" · ")}</span></div>`).join("")}</div>
      ${chn && admin ? `<form id="ch-edit" class="row" style="align-items:flex-end;margin-top:.75rem"><input type="hidden" name="id" value="${chn.id}">
        <div class="field"><label>नाम</label><input name="name" value="${esc(chn.name)}" required></div><div class="field"><label>Handle</label><input name="handle" value="${esc(chn.handle || "")}" placeholder="@theprashantmahto"></div>
        <div class="field" style="flex:1;min-width:220px"><label>Niche — ideas, trends और titles इसी से बनते हैं</label><input name="niche" value="${esc(chn.niche || "")}" placeholder="Hindi motivation, success stories, self-improvement"></div>
        <div class="field"><label>भाषा</label><select name="language"><option value="hi" ${chn.language === "hi" ? "selected" : ""}>हिंदी</option><option value="en" ${chn.language === "en" ? "selected" : ""}>English</option><option value="auto" ${chn.language === "auto" ? "selected" : ""}>अपने-आप</option></select></div>
        <div class="field"><label>रंग</label><input type="color" name="color" value="${esc(chn.color || "#F2B33D")}"></div>
        <div class="field" style="flex:1;min-width:200px"><label>Trend keywords (comma से अलग करें)</label><input name="keywords" value="${esc((chn.keywords || []).join(", "))}" placeholder="motivation, success, hindi story"></div>
        <button class="btn primary">Channel सेव करें</button>${S.channels.length > 1 ? `<button type="button" class="btn quiet danger" id="ch-del">हटाएँ</button>` : ""}</form>` : ""}</div>
    <p class="muted">नीचे की settings (connections, brand kit) <b>${esc(chn?.name || "")}</b> channel की हैं। हर upload से पहले आपकी मंज़ूरी ज़रूरी है — connection सिर्फ़ रास्ता खोलता है।</p>
    ${st.dry_run ? `<div class="note">Test mode: PUBLISH_DRY_RUN चालू है, इसलिए कुछ भी असल में publish नहीं होगा।</div>` : ""}
    ${!st.public_url ? `<div class="note err">.env में <b>PUBLIC_URL</b> नहीं है (जैसे https://studio.yourdomain.com — Cloudflare Tunnel का पता)। बिना इसके Google/Meta login वापस नहीं आ सकता और Instagram/Facebook वीडियो नहीं ले पाएँगे।</div>` : ""}
    <div class="section"><div class="row between"><h2>जुड़े हुए accounts</h2>${admin ? `<span class="row"><button class="btn" id="c-yt" ${st.youtube ? "" : "disabled"} title="${st.youtube ? "" : ".env में YT_CLIENT_ID/YT_CLIENT_SECRET चाहिए"}">+ YouTube</button><button class="btn" id="c-meta" ${st.meta ? "" : "disabled"} title="${st.meta ? "" : ".env में META_APP_ID/META_APP_SECRET चाहिए"}">+ Instagram / Facebook</button></span>` : ""}</div>
      ${c.connections.length ? `<div class="tablewrap"><table><tr><th>Platform</th><th>नाम</th><th>Channel</th><th>कब जुड़ा</th><th></th></tr>${c.connections.map((x) => `<tr><td>${PLAT[x.platform] || x.platform}</td><td>${esc(x.name)}${x.meta?.subscribers ? ` <span class="muted small">· ${x.meta.subscribers} subs</span>` : ""}${x.meta?.page ? ` <span class="muted small">· page: ${esc(x.meta.page)}</span>` : ""}</td><td>${admin ? `<select class="c-move small" data-id="${x.id}">${S.channels.map((ch) => `<option value="${ch.id}" ${x.channel_id === ch.id ? "selected" : ""}>${esc(ch.name)}</option>`).join("")}</select>` : esc(S.channels.find((ch) => ch.id === x.channel_id)?.name || "")}</td><td class="small muted">${new Date(x.created_at).toLocaleDateString("hi-IN")}</td><td>${admin ? `<button class="btn quiet small danger c-del" data-id="${x.id}">हटाएँ</button>` : ""}</td></tr>`).join("")}</table></div>` : `<p class="muted">अभी कोई account नहीं जुड़ा। ऊपर के button से YouTube या Instagram / Facebook जोड़ें।</p>`}</div>
    ${S.user.role === "admin" ? `<p class="small muted">Storage और disk की सफ़ाई <a href="#/account">Settings</a> में है।</p>` : ""}
    <div class="section"><h2>Brand kit</h2><p class="muted small">हर नए project और autopilot में यही default लगेगा।</p>
      <form id="brand" class="row" style="align-items:flex-end">
        <div class="field"><label>Channel का नाम</label><input name="name" value="${esc(S.brand?.name || "")}" placeholder="@theprashantmahto"></div>
        <div class="field"><label>Logo (Library से)</label><select name="logo_id"><option value="">नहीं</option>${(S.lib || []).filter((x) => x.kind === "logo").map((x) => `<option value="${x.id}" ${S.brand?.logo_id === x.id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></div>
        <div class="field"><label>Caption style</label><select name="caption_style"><option value="">Default</option>${(S.presets?.caption_styles || []).map((c) => `<option value="${c.id}" ${S.brand?.caption_style === c.id ? "selected" : ""}>${esc(c.label)}</option>`).join("")}</select></div>
        <div class="field"><label>Font</label><select name="font"><option value="">style जैसा</option>${(S.presets?.fonts || []).map((f) => `<option ${S.brand?.font === f ? "selected" : ""}>${f}</option>`).join("")}</select></div>
        <div class="field"><label>अक्षर का रंग</label><input type="color" name="primary" value="${S.brand?.primary || "#ffffff"}"></div>
        <div class="field"><label>Highlight रंग</label><input type="color" name="highlight" value="${S.brand?.highlight || "#ffd400"}"></div>
        <div class="field"><label>Color grade</label><select name="grade_preset"><option value="">नहीं</option>${Object.entries(S.presets?.catalog?.grade_presets || {}).map(([k, v]) => `<option value="${k}" ${S.brand?.grade_preset === k ? "selected" : ""}>${esc(v.label)}</option>`).join("")}</select></div>
        <div class="field"><label>Logo किस कोने में</label><select name="watermark_pos">${[["tr", "ऊपर दाएँ"], ["tl", "ऊपर बाएँ"], ["br", "नीचे दाएँ"], ["bl", "नीचे बाएँ"]].map(([v, l]) => `<option value="${v}" ${(S.brand?.watermark_pos || "tr") === v ? "selected" : ""}>${l}</option>`).join("")}</select></div>
        <div class="field" style="flex:1;min-width:220px"><label>CTA line (description में जुड़ेगी)</label><input name="cta" value="${esc(S.brand?.cta || "")}" placeholder="ऐसी कहानियों के लिए follow करें"></div>
        <div class="field" style="flex:1;min-width:220px"><label>Hashtags</label><input name="hashtags" value="${esc(S.brand?.hashtags || "")}" placeholder="#motivation #hindi"></div>
        <div class="field" style="flex:1;min-width:220px"><label>शब्दावली (नाम/खास शब्द — transcript इन्हें सही लिखेगा)</label><input name="vocab_words" value="${esc(S.brand?.vocab_words || "")}" placeholder="Prashant Mahto, UPSC, सफलता, मोटिवेशन"></div>
        <div class="field"><label>आवाज़ सुधार</label><select name="voice_preset">${[["studio", "Studio"], ["soft", "Soft / warm"], ["podcast", "Podcast"], ["bright", "Clear / bright"], ["phone", "Phone mic fix"], ["clean", "हल्का"], ["off", "बंद"]].map(([k, l]) => `<option value="${k}" ${(S.brand?.voice_preset || "studio") === k ? "selected" : ""}>${l}</option>`).join("")}</select></div>
        ${S.user.role === "admin" ? `<button class="btn primary">Brand kit सेव करें</button>` : ""}</form></div>
    <div class="section"><div class="row between"><h2>WhatsApp (Vivid Relay)</h2>${S.user.role === "admin" ? `<button class="btn" id="wa-test" ${S.notify?.enabled ? "" : "disabled"}>Test message भेजें</button>` : ""}</div>
      <p class="small muted">${S.notify?.enabled ? `Alerts भेजना: चालू (नंबर …${esc(S.notify.to || "")})` : "Alerts भेजना: बंद — .env में NOTIFY_URL, NOTIFY_TOKEN और NOTIFY_TO डालें"}<br>${S.notify?.inbound ? "WhatsApp से commands: चालू" : "WhatsApp से commands: बंद — .env में NOTIFY_INBOUND_SECRET डालें"}</p></div>
    ${autopilotSection()}
    <div id="sched-wrap">${scheduleSection()}</div>
    <div class="section"><h2>एक बार का setup</h2>
      <details><summary><b>YouTube</b> (free, 10 मिनट)</summary><ol class="small muted"><li>console.cloud.google.com → नया project → "YouTube Data API v3" enable करें</li><li>OAuth consent screen → External → अपना Gmail test user में जोड़ें</li><li>Credentials → OAuth client ID → Web application → Authorized redirect URI: <code>${esc(st.public_url || "https://<PUBLIC_URL>")}/api/connect/youtube/callback</code></li><li>client id/secret को .env में <code>YT_CLIENT_ID</code> / <code>YT_CLIENT_SECRET</code> में डालें, <code>docker compose up -d</code>, फिर यहाँ "+ YouTube"</li></ol><p class="small muted">quota: ~6 upload/दिन (10,000 units, upload 1,600)।</p></details>
      <details><summary><b>Instagram / Facebook</b> (free, Business account चाहिए)</summary><ol class="small muted"><li>Instagram को Professional (Creator/Business) बनाएँ और एक Facebook Page से link करें</li><li>developers.facebook.com → Create App (Business) → products: Facebook Login for Business + Instagram Graph API</li><li>Facebook Login → Settings → Valid OAuth Redirect URIs: <code>${esc(st.public_url || "https://<PUBLIC_URL>")}/api/connect/meta/callback</code></li><li>App ID/Secret को .env में <code>META_APP_ID</code> / <code>META_APP_SECRET</code>; फिर "+ Instagram / Facebook"</li><li>Cloudflare Access में <code>/pub/*</code> path को bypass करें (Meta वहीं से वीडियो उठाता है)</li></ol><p class="small muted">limit: Instagram 100 post/24h, Facebook Reels ~30/24h।</p></details></div>`;
}
// ---------- autopilot switches + posting schedule (per channel) ----------
function autopilotSection() {
  const ap = S.presets?.autopilot; if (!ap) return "";
  const cur = { ...ap.defaults, ...(S.brand?.autopilot || {}) }; const admin = S.user.role === "admin";
  return `<div class="section"><h2>Autopilot क्या-क्या करे</h2><p class="muted small">Autopilot वाला हर नया वीडियो इन्हीं से edit होगा। Publish फिर भी आपकी मंज़ूरी से ही होगा।</p>
    <form id="ap-form" class="apgrid">${Object.entries(ap.labels).filter(([k]) => k !== "shorts").map(([k, l]) => `<label class="chk"><input type="checkbox" name="${k}" ${cur[k] ? "checked" : ""} ${admin ? "" : "disabled"}> ${esc(l)}</label>`).join("")}
      <label class="field" style="margin:0"><span class="small">${esc(ap.labels.shorts || "Shorts")}</span><select name="shorts" ${admin ? "" : "disabled"}>${[0, 1, 2, 3, 4, 5, 6, 8].map((n) => `<option ${+cur.shorts === n ? "selected" : ""}>${n}</option>`).join("")}</select></label>
      ${admin ? `<div><button class="btn primary">Autopilot सेव करें</button></div>` : ""}</form></div>`;
}
const LANES = [["youtube_long", "YouTube — लंबा वीडियो"], ["youtube_short", "YouTube Shorts"], ["instagram", "Instagram Reels"], ["facebook", "Facebook Reels"]];
const DAYH = { mon: "सो", tue: "मं", wed: "बु", thu: "गु", fri: "शु", sat: "श", sun: "र" };
function scheduleSection() {
  const d = S.sched; if (!d) return "";
  const sc = S.schedEdit || (S.schedEdit = JSON.parse(JSON.stringify(d.schedule))); const admin = S.user.role === "admin"; const dis = admin ? "" : "disabled";
  return `<div class="section"><div class="row between"><h2>Posting schedule</h2><label class="chk"><input type="checkbox" id="sc-auto" ${sc.auto ? "checked" : ""} ${dis}> तैयार वीडियो को अगले खाली slot में अपने-आप रखें</label></div>
    <p class="muted small">हर platform के लिए हफ़्ते के समय (${esc(sc.timezone || "Asia/Kolkata")})। मंज़ूरी देने पर वीडियो इन्हीं समय पर जाएगा — YouTube/Facebook खुद schedule करते हैं, Instagram हमारी queue से उसी समय।${d.suggested?.length ? ` <b>आपके पुराने videos के हिसाब से अच्छा समय: ${d.suggested.map((x) => x.time).join(", ")}</b>` : ""}</p>
    <div class="schgrid">${LANES.map(([k, l]) => `<div class="schlane"><div class="row between"><b>${l}</b><span class="small muted">रोज़ अधिकतम <input type="number" min="0" max="10" data-scmax="${k}" value="${sc.max_per_day?.[k] ?? 1}" style="width:3.2rem" ${dis}></span></div>
      ${(sc.slots?.[k] || []).map((sl, i) => `<div class="schslot"><input type="time" data-sctime="${k}:${i}" value="${esc(sl.time)}" ${dis}><span class="days">${(d.days || Object.keys(DAYH)).map((dy) => `<button type="button" class="dchip ${(sl.days || []).includes(dy) ? "on" : ""}" data-scday="${k}:${i}:${dy}" ${dis}>${DAYH[dy] || dy}</button>`).join("")}</span><button type="button" class="ibtn" data-scdel="${k}:${i}" title="हटाएँ" ${dis}>✕</button></div>`).join("") || `<p class="small muted">कोई समय तय नहीं — इस platform पर अपने-आप schedule नहीं होगा।</p>`}
      ${admin ? `<button type="button" class="btn quiet small" data-scadd="${k}">+ समय जोड़ें</button>` : ""}</div>`).join("")}</div>
    <div class="row" style="flex-wrap:wrap;gap:.75rem;margin-top:.5rem"><label class="small">दो Shorts के बीच <input type="number" id="sc-sgap" min="1" max="48" value="${sc.short_gap_hours}" style="width:3.5rem" ${dis}> घंटे</label>
      <label class="small">YouTube Short → Insta/FB <input type="number" id="sc-cgap" min="0" max="24" value="${sc.cross_gap_hours}" style="width:3.5rem" ${dis}> घंटे बाद</label>
      ${admin ? `<button class="btn primary" id="sc-save">Schedule सेव करें</button>${d.suggested?.length ? `<button class="btn quiet" id="sc-sugg">सुझाया समय लगाएँ</button>` : ""}<button class="btn quiet" id="sc-reset">Default पर लौटें</button>` : ""}</div></div>`;
}
function bindSchedule() {
  const sc = S.schedEdit; if (!sc) return;
  const redraw = () => { const el = $("#sched-wrap"); if (el) { el.innerHTML = scheduleSection(); bindSchedule(); } };
  $$("[data-sctime]").forEach((el) => (el.onchange = () => { const [k, i] = el.dataset.sctime.split(":"); sc.slots[k][+i].time = el.value; }));
  $$("[data-scday]").forEach((b) => (b.onclick = () => { const [k, i, dy] = b.dataset.scday.split(":"); const sl = sc.slots[k][+i]; sl.days = sl.days.includes(dy) ? sl.days.filter((x) => x !== dy) : [...sl.days, dy]; redraw(); }));
  $$("[data-scdel]").forEach((b) => (b.onclick = () => { const [k, i] = b.dataset.scdel.split(":"); sc.slots[k].splice(+i, 1); redraw(); }));
  $$("[data-scadd]").forEach((b) => (b.onclick = () => { const k = b.dataset.scadd; (sc.slots[k] = sc.slots[k] || []).push({ days: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], time: "19:00" }); redraw(); }));
  $$("[data-scmax]").forEach((el) => (el.onchange = () => { sc.max_per_day = { ...(sc.max_per_day || {}), [el.dataset.scmax]: +el.value }; }));
  const g = (id, f) => { const el = $(id); if (el) el.onchange = () => f(el); };
  g("#sc-auto", (el) => (sc.auto = el.checked)); g("#sc-sgap", (el) => (sc.short_gap_hours = +el.value)); g("#sc-cgap", (el) => (sc.cross_gap_hours = +el.value));
  const sv = $("#sc-save"); if (sv) sv.onclick = async () => { try { const r = await api("PUT", "/schedule", { channel_id: S.channel, schedule: sc }); S.sched.schedule = r.schedule; S.schedEdit = JSON.parse(JSON.stringify(r.schedule)); toast("Schedule सेव हो गया"); redraw(); } catch (e) { toast(e.message); } };
  const sg = $("#sc-sugg"); if (sg) sg.onclick = () => { S.sched.suggested.forEach((x, n) => { const lane = n === 0 ? "youtube_long" : "youtube_short"; sc.slots[lane] = [{ days: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], time: x.time }, ...(sc.slots[lane] || []).slice(1)]; }); redraw(); toast("सुझाया समय लग गया — अब “Schedule सेव करें” दबाएँ"); };
  const rs = $("#sc-reset"); if (rs) rs.onclick = () => { S.schedEdit = JSON.parse(JSON.stringify(S.sched.defaults)); redraw(); };
}
function bindSettings() {
  bindSchedule();
  const wt = $("#wa-test"); if (wt) wt.onclick = async () => { wt.disabled = true; wt.textContent = "भेज रहे हैं…"; try { await api("POST", "/notify/test"); toast("Test message भेज दिया — WhatsApp देखें"); } catch (e) { toast(e.message, 7000); } wt.disabled = false; wt.textContent = "Test message भेजें"; };
  const apf = $("#ap-form"); if (apf) apf.onsubmit = async (e) => { e.preventDefault(); const ap = {}; for (const el of apf.elements) if (el.name) ap[el.name] = el.type === "checkbox" ? el.checked : +el.value;
    try { await api("PUT", `/brand?channel=${S.channel}`, { autopilot: ap }); S.brand = { ...(S.brand || {}), autopilot: ap }; toast("Autopilot settings सेव हो गईं"); } catch (err) { toast(err.message); } };
  const stl = $("#st-load"); if (stl) stl.onclick = () => loadStorage();
  const bf = $("#brand"); if (bf) bf.onsubmit = async (e) => { e.preventDefault(); const f = e.target; const body = {}; for (const el of f.elements) if (el.name) body[el.name] = el.type === "color" ? (el.value === "#ffffff" && el.name === "primary" ? "" : el.value) : el.value; try { await api("PUT", `/brand?channel=${S.channel}`, body); toast("Brand kit सेव हो गया"); } catch (err) { toast(err.message); } };
  const start = async (pl) => { try { const r = await api("POST", `/connect/${pl}/start?channel=${S.channel}`); location.href = r.url; } catch (e) { toast(e.message); } };
  document.querySelectorAll(".c-move").forEach((sel) => (sel.onchange = async () => { await api("PATCH", `/connections/${sel.dataset.id}`, { channel_id: sel.value }); toast("Channel बदल दिया"); load().then(render); }));
  const add = $("#ch-add"); if (add) add.onclick = async () => { const name = prompt("नए channel का नाम"); if (!name) return; const niche = prompt("niche (जैसे: Hindi motivation, success stories)") || ""; const r = await api("POST", "/channels", { name, niche }); S.channel = r.id; localStorage.setItem("vividora_channel", r.id); load().then(render); };
  const ce = $("#ch-edit"); if (ce) ce.onsubmit = async (e) => { e.preventDefault(); const f = e.target; await api("PATCH", `/channels/${f.id.value}`, { name: f.name.value, handle: f.handle.value, niche: f.niche.value, language: f.language.value, color: f.color.value, keywords: f.keywords.value.split(",").map((x) => x.trim()).filter(Boolean) }); toast("Channel सेव हो गया"); load().then(render); };
  const cd = $("#ch-del"); if (cd) cd.onclick = async () => { if (!confirm("यह channel हटाएँ? इसके projects पहले channel में चले जाएँगे।")) return; await api("DELETE", `/channels/${S.channel}`); S.channel = ""; load().then(render); };
  document.querySelectorAll("[data-ch]").forEach((el) => (el.onclick = () => { S.channel = el.dataset.ch; localStorage.setItem("vividora_channel", S.channel); load().then(render); }));
  const yt = $("#c-yt"); if (yt) yt.onclick = () => start("youtube");
  const mt = $("#c-meta"); if (mt) mt.onclick = () => start("meta");
  document.querySelectorAll(".c-del").forEach((b) => (b.onclick = async () => { if (confirm("यह connection हटाएँ?")) { await api("DELETE", `/connections/${b.dataset.id}`); load().then(render); } }));
}

// ---------- plan: trends + ideas + scripts ----------
const ISTAT = { new: "नया", approved: "बनाना है", recorded: "Record हो गया", done: "पूरा" };
const FMT = { short: "Short / Reel", long: "लंबा वीडियो", montage: "Montage" };
function planView() {
  const t = S.trends || { trends: [], setup: {} }; const ideas = S.ideas || []; const st = t.setup || {}; const canEdit = S.user.role !== "viewer";
  const src = { google_trends: "Google Trends", yt_popular: "YouTube Top", yt_channel: "Channels" };
  const bySrc = {}; for (const r of t.trends) (bySrc[r.source] = bySrc[r.source] || []).push(r);
  const open = S.ideaOpen && ideas.find((i) => i.id === S.ideaOpen);
  return `<div class="pghead"><h1>Plan</h1><span class="small muted" title="${st.llm ? "" : "AI के लिए server की .env में GEMINI_API_KEY या ANTHROPIC_API_KEY डालें"}">${st.llm ? "AI चालू" : "AI बंद — ideas और script template से बनेंगे"}${S.notify?.enabled ? " · WhatsApp चालू" : ""}</span></div>
    <p class="muted">Trend देखें, idea चुनें, script लिखें और record करें — बाकी काम Vividora कर देगा।</p>
    <div class="plan">
      <div class="section" style="margin-top:0;border:0;padding-top:0"><div class="row between"><h2>Trend radar</h2>${canEdit ? `<button class="btn small" id="tr-refresh">ताज़ा करें</button>` : ""}</div>
        <p class="small muted">${t.fetched_at ? `आख़िरी बार: ${new Date(t.fetched_at).toLocaleString("hi-IN")}` : "अभी trends नहीं लाए गए"}${!st.yt_api_key ? " · YouTube Top के लिए .env में YT_API_KEY डालें" : ""}${!(st.watch_channels || []).length ? " · WATCH_CHANNELS=UC… से पसंदीदा channels देखें" : ""}</p>
        ${Object.keys(bySrc).length ? Object.entries(bySrc).map(([k, rows]) => `<h3 class="small muted" style="margin:.75rem 0 .3rem">${src[k] || k}</h3><ul class="trlist">${rows.slice(0, 15).map((r) => `<li>${r.url ? `<a href="${r.url}" target="_blank" rel="noopener">${esc(r.title)}</a>` : esc(r.title)}<span class="muted small">${r.meta?.traffic ? r.meta.traffic + "+" : r.meta?.views_per_day ? r.meta.views_per_day.toLocaleString("en-IN") + "/day" : r.meta?.views ? r.meta.views.toLocaleString("en-IN") : ""}${r.meta?.channel ? " · " + esc(r.meta.channel) : ""}</span></li>`).join("")}</ul>`).join("") : `<p class="muted small">“ताज़ा करें” दबाएँ — Google Trends बिना किसी key के आ जाते हैं।</p>`}</div>
      <div class="section" style="margin-top:0;border:0;padding-top:0"><div class="row between"><h2>Ideas</h2></div>
        ${canEdit ? `<form id="idea-gen" class="row" style="margin-bottom:.75rem"><input name="topic" placeholder="विषय (खाली छोड़ें तो trends से)" style="flex:1;min-width:160px"><select name="format">${Object.entries(FMT).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select><select name="count">${[4, 6, 8, 12].map((n) => `<option ${n === 6 ? "selected" : ""}>${n}</option>`).join("")}</select><button class="btn primary small">✨ Ideas बनाएँ</button></form>
        <form id="idea-add" class="row" style="margin-bottom:.75rem"><input name="title" placeholder="अपना idea लिखें…" style="flex:1;min-width:160px" required><button class="btn small">+ Idea जोड़ें</button></form>` : ""}
        ${["new", "approved", "recorded", "done"].map((stt) => { const list = ideas.filter((i) => i.status === stt); return list.length ? `<h3 class="small muted" style="margin:.75rem 0 .3rem">${ISTAT[stt]} · ${list.length}</h3><ul class="ideas">${list.map((i) => `<li class="${open && open.id === i.id ? "sel" : ""}" data-idea="${i.id}"><b>${esc(i.title)}</b><span class="small muted">${FMT[i.format] || i.format}${i.script ? " · script ✓" : ""}${i.source ? " · " + esc(i.source.slice(0, 40)) : ""}</span></li>`).join("")}</ul>` : ""; }).join("") || `<p class="muted small">अभी कोई idea नहीं — ऊपर से बनाएँ या अपना लिखें।</p>`}</div>
    </div>
    <div class="section"><div class="row between"><h2>Swipe file — references</h2></div><p class="small muted">जो trend audio, video या effect आपको बनाना है, उसका link और note यहाँ रखें। Project के अंदर Refs tab से भी जोड़ सकते हैं।</p>
      ${canEdit ? `<form id="ref-form" class="row" style="margin-bottom:.75rem"><select name="kind"><option value="audio">Audio</option><option value="video">Video</option><option value="effect">Effect</option><option value="caption">Caption</option><option value="hook">Hook</option><option value="other">अन्य</option></select><input name="url" placeholder="https://…" style="flex:1;min-width:160px"><input name="note" placeholder="Note: क्या बनाना है" style="flex:2;min-width:200px"><button class="btn small">+ Reference जोड़ें</button></form>` : ""}
      ${(S.refs || []).length ? `<ul class="trlist">${S.refs.map((r) => `<li><span>${{ audio: "🎵", video: "🎬", effect: "✨", caption: "💬", hook: "🪝" }[r.kind] || "📌"} ${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.url.replace(/^https?:\/\//, "").slice(0, 60))}</a>` : ""} ${r.note ? `<span class="muted">— ${esc(r.note)}</span>` : ""}${r.project_id ? ` <a class="small" href="#/projects/${r.project_id}">Project</a>` : ""}</span>${canEdit ? `<button class="btn quiet small ref-del" data-id="${r.id}" title="हटाएँ" aria-label="हटाएँ">✕</button>` : ""}</li>`).join("")}</ul>` : `<p class="muted small">अभी कोई reference नहीं।</p>`}</div>
    ${open ? ideaPanel(open, canEdit) : ""}`;
}
function ideaPanel(i, canEdit) {
  const m = i.meta || {};
  return `<div class="ed-modal idea-modal" id="idea-modal"><div class="modal idea-sheet" role="dialog" aria-modal="true" aria-label="Idea"><div class="row between idea-head"><h2 class="idea-title" ${canEdit ? 'contenteditable="true" spellcheck="false" id="idea-title" title="नाम बदलने के लिए click करें"' : ""}>${esc(i.title)}</h2><button class="ibtn" id="idea-close" title="बंद करें" aria-label="बंद करें">✕</button></div>
    <div class="row idea-meta"><select id="idea-status" ${canEdit ? "" : "disabled"}>${Object.entries(ISTAT).map(([k, v]) => `<option value="${k}" ${i.status === k ? "selected" : ""}>${v}</option>`).join("")}</select>
      <select id="idea-format" ${canEdit ? "" : "disabled"}>${Object.entries(FMT).map(([k, v]) => `<option value="${k}" ${i.format === k ? "selected" : ""}>${v}</option>`).join("")}</select>
      <input type="date" id="idea-due" value="${(i.due_at || "").slice(0, 10)}" title="कब तक बनाना है" ${canEdit ? "" : "disabled"}><span class="grow"></span>${canEdit ? `<button class="btn small quiet danger" id="idea-drop">Idea हटाएँ</button>` : ""}</div>
    <div class="field"><label for="idea-hook">Hook <span>— camera पर बोली जाने वाली पहली लाइन</span></label><textarea id="idea-hook" rows="2" ${canEdit ? "" : "disabled"}>${esc(i.hook || "")}</textarea></div>
    <div class="field"><label for="idea-angle">Angle <span>— कहानी किस नज़रिए से कहेंगे</span></label><input id="idea-angle" value="${esc(i.angle || "")}" ${canEdit ? "" : "disabled"}></div>
    <div class="field"><label for="idea-outline">Outline <span>— मुख्य बातें, क्रम से</span></label><textarea id="idea-outline" rows="4" ${canEdit ? "" : "disabled"}>${esc(i.outline || "")}</textarea></div>
    <div class="row between idea-scripthead"><label for="idea-scripttext">Script${m.script_source === "llm" ? ` <span class="pill ok">AI से लिखी</span>` : m.script_source ? ` <span class="pill warn" title="AI key नहीं थी, इसलिए यह खाका template से बना है">खाका (template)</span>` : ""}</label>${canEdit ? `<span class="row"><select id="script-secs" aria-label="Script की लंबाई"><option value="">लंबाई: अपने-आप</option><option value="30">30 सेकंड</option><option value="45">45 सेकंड</option><option value="60">1 मिनट</option><option value="180">3 मिनट</option><option value="480">8 मिनट</option></select><button class="btn small" id="idea-script">✨ Script लिखें</button></span>` : ""}</div>
    <textarea id="idea-scripttext" class="idea-script" rows="12" ${canEdit ? "" : "disabled"}>${esc(i.script || "")}</textarea>
    ${m.shotlist?.length ? `<p class="small muted" style="margin-top:.5rem"><b>Shots:</b> ${m.shotlist.map(esc).join(" · ")}</p>` : ""}${m.overlays?.length ? `<p class="small muted"><b>On-screen text:</b> ${m.overlays.map(esc).join(" · ")}</p>` : ""}${m.title_options?.length ? `<p class="small muted"><b>Title options:</b> ${m.title_options.map(esc).join(" / ")}</p>` : ""}
    <div class="row between idea-foot"><span class="small muted">Record करने के बाद यहीं से upload करें — वीडियो इस idea से जुड़ जाएगा।</span>${canEdit ? `<span class="row"><a class="btn small" href="#/new?idea=${i.id}">Recording upload करें</a><button class="btn primary small" id="idea-save">सेव करें</button></span>` : ""}</div></div></div>`;
}
function bindPlan() {
  const rf0 = $("#ref-form"); if (rf0) rf0.onsubmit = async (e) => { e.preventDefault(); const f = e.target; try { await api("POST", "/refs", { kind: f.kind.value, url: f.url.value.trim(), note: f.note.value.trim(), channel_id: S.channel }); load().then(render); } catch (err) { toast(err.message); } };
  document.querySelectorAll(".ref-del").forEach((b) => (b.onclick = async () => { await api("DELETE", `/refs/${b.dataset.id}`); load().then(render); }));
  const rf = $("#tr-refresh"); if (rf) rf.onclick = async () => { rf.disabled = true; rf.textContent = "ला रहे हैं…"; try { const r = await api("POST", "/trends/refresh"); toast(`${r.count} trends मिले`); } catch (e) { toast(e.message); } load().then(render); };
  const gen = $("#idea-gen"); if (gen) gen.onsubmit = async (e) => { e.preventDefault(); const f = e.target; const b = f.querySelector("button"); b.disabled = true; b.textContent = "Ideas बन रहे हैं…";
    try { await api("POST", "/ideas/generate", { topic: f.topic.value, format: f.format.value, count: +f.count.value, channel_id: S.channel }); toast("नए ideas जुड़ गए"); } catch (err) { toast(err.message); } load().then(render); };
  const add = $("#idea-add"); if (add) add.onsubmit = async (e) => { e.preventDefault(); const f = e.target; const r = await api("POST", "/ideas", { title: f.title.value, format: "short", channel_id: S.channel }); S.ideaOpen = r.id; load().then(render); };
  document.querySelectorAll("[data-idea]").forEach((li) => (li.onclick = () => { S.ideaOpen = li.dataset.idea; render(); }));
  const close = $("#idea-close"); if (close) close.onclick = () => { S.ideaOpen = null; render(); };
  const modal = $("#idea-modal"); if (modal) modal.onclick = (e) => { if (e.target === modal) { S.ideaOpen = null; render(); } };
  const id = S.ideaOpen; if (!id) return;
  const collect = () => ({ title: $("#idea-title")?.textContent.trim(), status: $("#idea-status").value, format: $("#idea-format").value, due_at: $("#idea-due").value || null, hook: $("#idea-hook").value, angle: $("#idea-angle").value, outline: $("#idea-outline").value, script: $("#idea-scripttext").value });
  const save = $("#idea-save"); if (save) save.onclick = async () => { await api("PATCH", `/ideas/${id}`, collect()); toast("Idea सेव हो गया"); load().then(render); };
  const drop = $("#idea-drop"); if (drop) drop.onclick = async () => { if (confirm("यह idea हटाएँ?")) { await api("PATCH", `/ideas/${id}`, { status: "dropped" }); S.ideaOpen = null; load().then(render); } };
  const sc = $("#idea-script"); if (sc) sc.onclick = async () => { sc.disabled = true; sc.textContent = "Script लिख रहे हैं…"; await api("PATCH", `/ideas/${id}`, collect()); try { const r = await api("POST", `/ideas/${id}/script`, { seconds: $("#script-secs").value || null }); toast(r.source === "llm" ? "Script तैयार है" : r.ai_error ? "AI से script नहीं बन पाई, इसलिए खाका (template) लगाया। वजह: " + r.ai_error : "AI key नहीं मिली, इसलिए script का खाका (template) बना है। पूरी AI script के लिए server की .env में GEMINI_API_KEY या ANTHROPIC_API_KEY जोड़ें।", r.source === "llm" ? 2600 : 9000); } catch (e) { toast(e.message); } load().then(render); };
  $("#idea-status").onchange = async () => { await api("PATCH", `/ideas/${id}`, { status: $("#idea-status").value }); load().then(render); };
}

// ---------- library ----------
const LIBCATS = [
  ["all", "सब", null], ["music", "Music", { kind: "music" }], ["sfx", "SFX", { kind: "sfx" }], ["popup", "Popups और CTA", { tag: "popup" }],
  ["emoji", "Emoji", { tag: "emoji" }], ["social", "Social icons", { tag: "social" }], ["shape", "Arrows और shapes", { tag: "shape" }],
  ["frame", "Frames", { kind: "frame" }], ["broll", "B-roll और backgrounds", { kind: "broll" }], ["image", "Images", { kind: "image" }],
  ["lut", "LUTs", { kind: "lut" }], ["logo", "Logos", { kind: "logo" }], ["mine", "मेरे uploads", { source: "upload" }],
];
const MOODS = ["motivational", "emotional", "lofi", "upbeat", "cinematic", "story", "energetic", "news"];
function libFilter(x) {
  const c = LIBCATS.find((k) => k[0] === (S.libCat || "all"))?.[2]; const q = (S.libQ || "").toLowerCase();
  if (c?.kind && x.kind !== c.kind) return false; if (c?.tag && !(`,${x.tags},`).includes(`,${c.tag},`)) return false; if (c?.source && x.source !== c.source) return false;
  if (S.libMood && !(x.tags || "").includes(S.libMood)) return false;
  return !q || x.name.toLowerCase().includes(q) || (x.tags || "").toLowerCase().includes(q);
}
function libCard(x) {
  const img = ["sticker", "image", "logo", "frame"].includes(x.kind); const vid = x.kind === "broll"; const aud = ["music", "sfx", "voice"].includes(x.kind);
  return `<div class="lcard" data-id="${x.id}">${img ? `<div class="lprev chk"><img src="${x.url}" loading="lazy" alt=""></div>` : vid ? `<div class="lprev"><video src="${x.url}#t=0.5" muted preload="metadata" loop></video></div>` : aud ? `<div class="lprev aud"><button class="btn small" data-play="${x.id}">▶</button><span class="small muted">${x.meta?.duration ? fmt(x.meta.duration) : ""}</span></div>` : `<div class="lprev aud">🎨 .cube</div>`}
    <div class="lbody"><b title="${esc(x.name)}">${esc(x.name)}</b><span class="small muted" title="${esc(x.license || "")}">${esc((x.tags || "").split(",").filter((t) => t && t !== "starter").slice(0, 3).join(" · "))}</span></div>
    ${S.user.role !== "viewer" ? `<button class="ibtn ldel" data-del="${x.id}" title="हटाएँ">✕</button>` : ""}</div>`;
}
function libraryView() {
  const all = S.lib || []; const items = all.filter(libFilter); const canEdit = S.user.role !== "viewer";
  const counts = Object.fromEntries(LIBCATS.map(([k, , c]) => [k, all.filter((x) => !c || ((!c.kind || x.kind === c.kind) && (!c.tag || (`,${x.tags},`).includes(`,${c.tag},`)) && (!c.source || x.source === c.source))).length]));
  return `<div class="pghead"><h1>Library</h1><span class="row">${S.user.role === "admin" ? `<button class="btn small quiet" id="lib-starter" title="Starter pack के जो items नहीं हैं, उन्हें फिर से जोड़ें">Starter pack फिर जोड़ें</button>` : ""}${canEdit ? `<label class="btn small primary">Upload करें<input type="file" id="lib-up" multiple hidden></label>` : ""}</span></div>
    <p class="muted small">हर project और Autopilot यहीं से music, SFX, stickers, frames और LUTs लेता है। सब free और licence-safe है — हर item पर उसका licence लिखा है। Starter pack Vividora का अपना है (CC0), साथ में Noto Emoji (Apache) और Simple Icons (CC0)।</p>
    <div class="libtabs"><button class="${S.libMode !== "web" ? "on" : ""}" data-lm="mine">मेरी library (${all.length})</button><button class="${S.libMode === "web" ? "on" : ""}" data-lm="web">Free online खोजें</button></div>
    ${S.libMode === "web" ? libWebView() : `<div class="libbar"><input id="lib-q" placeholder="खोजें — जैसे fire, subscribe, whoosh, frame" value="${esc(S.libQ || "")}">
      ${canEdit ? `<select id="lib-upkind" title="Upload किस category में हो">${["music", "sfx", "sticker", "image", "broll", "frame", "logo", "lut", "voice"].map((k) => `<option ${S.libUpKind === k ? "selected" : ""}>${k}</option>`).join("")}</select>` : ""}</div>
    <div class="libcats">${LIBCATS.map(([k, l]) => `<button class="${(S.libCat || "all") === k ? "on" : ""}" data-cat="${k}">${l} <i>${counts[k]}</i></button>`).join("")}</div>
    ${(S.libCat === "music") ? `<div class="libcats moods">${["", ...MOODS].map((m) => `<button class="${(S.libMood || "") === m ? "on" : ""}" data-mood="${m}">${m || "सभी moods"}</button>`).join("")}</div>` : ""}
    <div class="lgrid">${items.map(libCard).join("") || `<p class="muted">इस खोज से कुछ नहीं मिला।</p>`}</div>`}`;
}
function libWebView() {
  const r = S.libWeb || [];
  return `<div class="libbar"><select id="lw-src"><option value="openverse-audio" ${S.lwSrc === "openverse-audio" ? "selected" : ""}>Music / SFX — Openverse (CC, key नहीं चाहिए)</option><option value="openverse-image" ${S.lwSrc === "openverse-image" ? "selected" : ""}>Images — Openverse (CC, key नहीं चाहिए)</option><option value="pixabay-video" ${S.lwSrc === "pixabay-video" ? "selected" : ""}>B-roll videos — Pixabay (key चाहिए)</option><option value="pixabay-image" ${S.lwSrc === "pixabay-image" ? "selected" : ""}>Images / PNG — Pixabay (key चाहिए)</option><option value="jamendo" ${S.lwSrc === "jamendo" ? "selected" : ""}>Music — Jamendo (key चाहिए)</option></select>
    <input id="lw-q" placeholder="जैसे: motivational piano, sunrise, city timelapse" value="${esc(S.lwQ || "")}"><button class="btn primary small" id="lw-go">खोजें</button></div>
    <p class="small muted">सिर्फ़ commercial-safe licences दिखते हैं (CC0, CC-BY, CC-BY-SA, Pixabay licence)। CC-BY वाले items का credit description में देना ज़रूरी है — import के समय credit उसी item पर save हो जाता है। YouTube Audio Library का API नहीं है: वहाँ से download करके ऊपर “Upload करें” से डालें।</p>
    <div class="lgrid">${r.map((x, i) => `<div class="lcard">${x.kind === "image" ? `<div class="lprev chk"><img src="${esc(x.preview)}" loading="lazy" alt=""></div>` : x.kind === "broll" ? `<div class="lprev"><img src="${esc(x.preview)}" alt=""></div>` : `<div class="lprev aud"><button class="btn small" data-wplay="${i}">▶</button><span class="small muted">${x.duration ? fmt(x.duration) : ""}</span></div>`}
      <div class="lbody"><b title="${esc(x.title)}">${esc(x.title)}</b><span class="small muted">${esc(x.license)} · ${esc(x.creator || "")}</span></div>
      <select class="lw-kind small" data-i="${i}">${(x.kind === "music" ? ["music", "sfx"] : x.kind === "broll" ? ["broll"] : ["image", "sticker", "frame"]).map((k) => `<option>${k}</option>`).join("")}</select><button class="btn small" data-wimp="${i}">+ Library</button></div>`).join("") || `<p class="muted small">ऊपर source चुनें और खोजें।</p>`}</div>`;
}
let libAudio = null;
function bindLibrary() {
  document.querySelectorAll("[data-lm]").forEach((b) => (b.onclick = () => { S.libMode = b.dataset.lm; render(); }));
  document.querySelectorAll("[data-cat]").forEach((b) => (b.onclick = () => { S.libCat = b.dataset.cat; S.libMood = ""; render(); }));
  document.querySelectorAll("[data-mood]").forEach((b) => (b.onclick = () => { S.libMood = b.dataset.mood; render(); }));
  const q = $("#lib-q"); if (q) q.oninput = () => { S.libQ = q.value; const grid = document.querySelector(".lgrid"); grid.innerHTML = (S.lib || []).filter(libFilter).map(libCard).join("") || `<p class="muted">इस खोज से कुछ नहीं मिला।</p>`; bindLibCards(); };
  const uk = $("#lib-upkind"); if (uk) uk.onchange = () => (S.libUpKind = uk.value);
  const up = $("#lib-up"); if (up) up.onchange = async () => { const kind = $("#lib-upkind")?.value || "sticker"; for (const f of up.files) { try { const r = await fetch(`/api/library?kind=${kind}&filename=${encodeURIComponent(f.name)}&channel=`, { method: "PUT", headers: { authorization: "Bearer " + S.token, "content-type": "application/octet-stream" }, body: f }); const d = await r.json(); if (!r.ok) throw new Error(d.error); toast(`${f.name} जुड़ गया`); } catch (e) { toast(e.message); } } load().then(render); };
  const st = $("#lib-starter"); if (st) st.onclick = async () => { st.disabled = true; const r = await api("POST", "/library/starter"); toast(`${r.added} नए items जुड़े`); load().then(render); };
  const go = $("#lw-go"); if (go) { const run = async () => { S.lwSrc = $("#lw-src").value; S.lwQ = $("#lw-q").value; go.disabled = true; go.textContent = "खोज रहे हैं…"; try { S.libWeb = await api("GET", `/library/search?source=${S.lwSrc}&q=${encodeURIComponent(S.lwQ)}`); } catch (e) { toast(e.message); S.libWeb = []; } render(); }; go.onclick = run; $("#lw-q").onkeydown = (e) => { if (e.key === "Enter") run(); }; }
  document.querySelectorAll("[data-wplay]").forEach((b) => (b.onclick = () => { const x = S.libWeb[+b.dataset.wplay]; if (libAudio) { libAudio.pause(); if (libAudio.dataset.u === x.url) { libAudio = null; return; } } libAudio = new Audio(x.preview || x.url); libAudio.dataset.u = x.url; libAudio.play(); }));
  document.querySelectorAll("[data-wimp]").forEach((b) => (b.onclick = async () => { const i = +b.dataset.wimp; const x = S.libWeb[i]; const kind = document.querySelector(`.lw-kind[data-i="${i}"]`).value; b.disabled = true; b.textContent = "…"; try { await api("POST", "/library/import", { ...x, kind, channel_id: null }); b.textContent = "✓ जुड़ा"; } catch (e) { toast(e.message); b.disabled = false; b.textContent = "+ Library"; } }));
  bindLibCards();
}
function bindLibCards() {
  document.querySelectorAll("[data-play]").forEach((b) => (b.onclick = () => { const x = S.lib.find((y) => y.id === b.dataset.play); if (libAudio) { libAudio.pause(); if (libAudio.dataset.u === x.url) { libAudio = null; b.textContent = "▶"; return; } } libAudio = new Audio(x.url); libAudio.dataset.u = x.url; libAudio.play(); b.textContent = "⏸"; libAudio.onended = () => (b.textContent = "▶"); }));
  document.querySelectorAll(".lcard video").forEach((v) => { v.onmouseenter = () => v.play().catch(() => {}); v.onmouseleave = () => v.pause(); });
  document.querySelectorAll("[data-del]").forEach((b) => (b.onclick = async (e) => { e.stopPropagation(); if (!confirm("Library से हटाएँ?")) return; await api("DELETE", `/library/${b.dataset.del}`); S.lib = S.lib.filter((x) => x.id !== b.dataset.del); b.closest(".lcard").remove(); }));
}

// ---------- analytics ----------
function analyticsView() {
  const a = S.analytics || { videos: [], learn: {} }; const L = a.learn || {}; const canEdit = S.user.role !== "viewer";
  const n = (x) => (x || 0).toLocaleString("en-IN");
  const rec = L.recommend || {}; const recLabels = { caption_style: "caption style", hook: "hook", zoom: "auto zoom", look: "look", length: "लंबाई", music: "music", weekday: "दिन", hour: "समय" };
  // retention (YouTube Analytics): inline SVG curve + marker at the biggest drop
  const ret = a.videos.filter((v) => v.platform === "youtube" && v.yta);
  const pctf = (x, d = 0) => (x == null || x === "" ? "—" : (+x).toFixed(d) + "%");
  const curve = (y) => { const pts = (y.retention || []).filter((p) => p && p[1] != null); if (pts.length < 2) return `<span class="small muted">Curve अभी नहीं</span>`;
    const top = Math.max(1, Math.min(1.5, Math.max(...pts.map((p) => +p[1])))); const Y = (v) => (36 - Math.min(+v, top) / top * 32).toFixed(1);
    const line = pts.map((p) => `${(p[0] * 100).toFixed(1)},${Y(p[1])}`).join(" "); const d = y.drop;
    const near = d ? pts.reduce((b, p) => (Math.abs(p[0] - d.at) < Math.abs(b[0] - d.at) ? p : b), pts[0]) : null;
    return `<svg viewBox="0 0 100 40" preserveAspectRatio="none" width="180" height="44" role="img" aria-label="audience retention" style="display:block;overflow:visible"><line x1="0" x2="100" y1="${Y(Math.min(1, top))}" y2="${Y(Math.min(1, top))}" stroke="var(--line)" stroke-width=".6" vector-effect="non-scaling-stroke"/><polyline points="${line}" fill="none" stroke="var(--amber)" stroke-width="1.6" vector-effect="non-scaling-stroke"/>${near ? `<line x1="${(d.at * 100).toFixed(1)}" x2="${(d.at * 100).toFixed(1)}" y1="2" y2="38" stroke="var(--rose)" stroke-width="1" stroke-dasharray="2 2" vector-effect="non-scaling-stroke"/><circle cx="${(near[0] * 100).toFixed(1)}" cy="${Y(near[1])}" r="2.4" fill="var(--rose)"><title>${esc(d.hint || "")}</title></circle>` : ""}</svg>`; };
  const retSec = ret.length ? `<div class="section"><h2>Retention — लोग कहाँ छोड़ते हैं</h2><p class="small muted">YouTube Analytics से (हर 6 घंटे में अधिकतम एक बार, रोज़ अपने-आप)। लाल निशान = सबसे बड़ी गिरावट।</p>
    ${(L.notes || []).length ? `<div class="note">${L.notes.map((t) => `• ${esc(t)}`).join("<br>")}</div>` : ""}
    <div class="tablewrap"><table><tr><th>Video</th><th>औसत % देखा</th><th>औसत समय</th><th>CTR</th><th>retention</th></tr>${ret.map((v) => { const y = v.yta; const m = y.metrics || {}; const avd = m.averageViewDuration;
      return `<tr><td><a href="${v.url}" target="_blank" rel="noopener">${esc(v.title)}</a>${y.error ? `<br><span class="small err">${esc(y.error)}</span>` : ""}</td><td><b>${pctf(m.averageViewPercentage)}</b></td><td class="small">${avd != null ? `${Math.floor(avd / 60)}:${String(Math.round(avd % 60)).padStart(2, "0")}` : "—"}</td><td class="small">${m.impressionClickThroughRate != null ? pctf(m.impressionClickThroughRate, 1) : `<span class="muted" title="API ने CTR नहीं दिया — Studio में देखें">—</span>`}</td><td>${curve(y)}${y.drop ? `<div class="small">${esc(y.drop.hint)}</div>` : ""}</td></tr>`; }).join("")}</table></div></div>` : "";
  return `<div class="pghead"><div><h1>Analytics</h1><p class="muted">Published videos का हाल और उनसे सीख: कौन-सा style, hook और लंबाई ज़्यादा चलती है (index 1.0 = औसत)।</p></div>${canEdit ? `<button class="btn small" id="an-refresh">Stats ताज़ा करें</button>` : ""}</div>
    ${Object.keys(rec).length ? `<div class="note"><b>सीख:</b> ${Object.entries(rec).map(([k, v]) => `${recLabels[k] || k} → <b>${esc(v)}</b>`).join(" · ")}
      ${S.user.role === "admin" ? `<br><button class="btn small primary" id="an-apply" style="margin-top:.5rem">नए projects के लिए यही default बनाएँ</button>` : ""}
      ${a.defaults && Object.keys(a.defaults).length ? `<span class="small muted" style="margin-left:.5rem">अभी default: ${esc(JSON.stringify(a.defaults))}</span>` : ""}</div>` : `<p class="small muted">${L.note || "अभी सीखने के लिए data कम है।"}</p>`}
    ${Object.keys(L.dimensions || {}).length ? `<div class="section"><h2>क्या काम कर रहा है</h2><div class="dims">${Object.entries(L.dimensions).map(([k, d]) => `<div class="dim"><b>${esc(d.label)}</b>${Object.entries(d.groups).sort((x, y) => y[1].index - x[1].index).map(([g, v]) => `<div class="bar"><span>${esc(g)} <i class="muted">(${v.n})</i></span><div class="progress"><i style="width:${Math.min(100, v.index * 50).toFixed(0)}%"></i></div><b>${v.index.toFixed(2)}</b></div>`).join("")}</div>`).join("")}</div></div>` : ""}
    ${retSec}
    <div class="section"><h2>Published videos <em class="cnt">${a.videos.length}</em></h2>${a.videos.length ? `<div class="tablewrap"><table><tr><th>Video</th><th>Platform</th><th>Views</th><th>Likes</th><th>Comments</th><th>Style</th><th>Published</th></tr>${a.videos.map((v) => `<tr><td><a href="${v.url}" target="_blank" rel="noopener">${esc(v.title)}</a> <span class="small muted">${esc(v.label || "")}</span></td><td>${v.platform}</td><td>${n(v.views)}</td><td>${n(v.likes)}</td><td>${n(v.comments)}</td><td class="small">${esc(v.features?.caption_style || "")}${v.features?.hook === "yes" ? " · hook" : ""} · ${esc(v.features?.length || "")}</td><td class="small muted">${v.published_at ? new Date(v.published_at).toLocaleDateString("hi-IN") : ""}${v.fetched_at ? "" : " · stats बाकी"}</td></tr>`).join("")}</table></div>` : `<p class="muted">अभी कुछ publish नहीं हुआ। मंज़ूर वीडियो Publish पेज से डालें।</p>`}</div>`;
}
function bindAnalytics() {
  const r = $("#an-refresh"); if (r) r.onclick = async () => { r.disabled = true; r.textContent = "ला रहे हैं…"; try { const x = await api("POST", "/analytics/refresh"); toast(`${x.updated} videos के stats अपडेट हुए${(x.errors || []).length ? " — " + x.errors.join("; ") : ""}`); } catch (e) { toast(e.message); } load().then(render); };
  const ap = $("#an-apply"); if (ap) ap.onclick = async () => { const x = await api("POST", `/analytics/apply?channel=${S.channel}`); toast("नए projects के defaults बदल दिए"); load().then(render); };
}

// ---------- thumbnails: pick a project ----------
function thumbsPickView() {
  const list = S.projects.filter((p) => p.status !== "uploading");
  return `<div class="pghead"><div><h1>Thumbnails</h1><p class="muted small">किस वीडियो का thumbnail बनाएँ? Publish के समय ★ वाला thumbnail लगता है।</p></div></div>
    <div class="thfeat">${[["◎", "Best frame", "20 frames में से सबसे साफ़ — चेहरा और खुली आँखें"], ["✂", "Person cutout", "Background हटाकर border या glow"], ["अ", "हिंदी text", "सही shaping, *शब्द* लिखकर highlight"], ["AB", "A/B variants", "एक click में 3 अलग thumbnails"]].map(([i, b, s]) => `<div><i>${i}</i><b>${b}</b><span class="small muted">${s}</span></div>`).join("")}</div>
    ${list.length ? `<div class="pgrid2">${list.map((p) => pcard(p, { href: (x) => `#/thumbs/${x.id}`, select: false, hover: false })).join("")}</div>` : `<div class="empty"><p>Thumbnail बनाने के लिए पहले कोई वीडियो upload करें।</p><a class="btn primary" href="#/new">वीडियो upload करें</a></div>`}`;
}

// ---------- publish queue + calendar ----------
function publishView() {
  const pubs = S.pubs || []; const now = new Date().toISOString();
  const upcoming = pubs.filter((p) => ["queued", "running"].includes(p.status) || (p.when && p.when > now));
  const done = pubs.filter((p) => p.status === "done" && !(p.when && p.when > now)); const failed = pubs.filter((p) => p.status === "failed");
  const approved = S.projects.filter((p) => p.status === "approved");
  const tab = S.pubTab;
  const row = (u) => `<li class="pubi"><span class="plat ${u.platform}">${PLAT[u.platform] || u.platform}</span><span class="grow"><a href="#/projects/${u.project_id}"><b>${esc(u.title)}</b></a><span class="small muted">${esc(u.connection_name || "")}${u.privacy ? " · " + esc(u.privacy) : ""}${u.error && u.status === "failed" ? " · " + esc(u.error.slice(0, 120)) : ""}</span></span>
    <span class="small ${u.status === "failed" ? "err" : "muted"}">${u.when ? new Date(u.when).toLocaleString("hi-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : u.status === "done" ? "✓ " + relTime(u.finished_at) : u.status === "failed" ? "✕ असफल" : u.status === "running" ? "Upload हो रहा है…" : "कतार में"}</span>${u.url ? `<a class="btn quiet small" href="${esc(u.url)}" target="_blank" rel="noopener">↗</a>` : ""}</li>`;
  return `<div class="pghead"><div><h1>Publish</h1><p class="muted small">हर upload आपकी मंज़ूरी के बाद ही जाता है। YouTube पर ★ चुना हुआ thumbnail अपने-आप लगता है।</p></div></div>
    <div class="stats2 small4"><div class="stat"><b>${upcoming.length}</b><span>Scheduled या कतार में</span></div><div class="stat"><b>${done.length}</b><span>Published</span></div><div class="stat"><b>${failed.length}</b><span>असफल</span></div><a class="stat" href="#/projects?status=approved"><b>${approved.length}</b><span>मंज़ूर, publish बाकी</span></a></div>
    <div class="libtabs">${[["queue", `कतार (${upcoming.length})`], ["done", `Published (${done.length})`], ["failed", `असफल (${failed.length})`], ["cal", "Calendar"]].map(([k, l]) => `<button data-ptab="${k}" class="${tab === k ? "on" : ""}">${l}</button>`).join("")}</div>
    ${tab === "cal" ? calendarView(pubs) : `<ul class="publist">${(tab === "queue" ? upcoming : tab === "done" ? done : failed).map(row).join("") || `<li class="empty small">यहाँ अभी कुछ नहीं।${tab === "queue" && approved.length ? " नीचे मंज़ूर वीडियो खोलकर Publish करें।" : ""}</li>`}</ul>`}
    ${approved.length ? `<section class="card" style="margin-top:1rem"><div class="card-h"><h2>मंज़ूर — publish के लिए तैयार</h2></div><div class="pgrid2 compact">${approved.slice(0, 8).map((p) => pcard(p, { select: false })).join("")}</div></section>` : ""}`;
}
function calendarView(pubs) {
  const base = new Date(); base.setDate(1); base.setMonth(base.getMonth() + S.calOff);
  const y = base.getFullYear(), m = base.getMonth(); const first = (new Date(y, m, 1).getDay() + 6) % 7; const days = new Date(y, m + 1, 0).getDate();
  const byDay = {};
  for (const p of pubs) { const d = new Date(p.when || p.finished_at || p.created_at); if (d.getFullYear() === y && d.getMonth() === m) (byDay[d.getDate()] = byDay[d.getDate()] || []).push(p); }
  const today = new Date(); const cells = [];
  for (let i = 0; i < first; i++) cells.push(`<div class="cal-c off"></div>`);
  for (let d = 1; d <= days; d++) {
    const isT = today.getFullYear() === y && today.getMonth() === m && today.getDate() === d;
    cells.push(`<div class="cal-c ${isT ? "today" : ""}"><span class="cal-d">${d}</span>${(byDay[d] || []).slice(0, 3).map((p) => `<a class="cal-e ${p.platform} ${p.status}" href="#/projects/${p.project_id}" title="${esc(p.title)}">${esc(p.title)}</a>`).join("")}${(byDay[d] || []).length > 3 ? `<span class="small muted">+${byDay[d].length - 3}</span>` : ""}</div>`);
  }
  return `<div class="cal"><div class="row between"><button class="btn small quiet" data-cal="-1" title="पिछला महीना" aria-label="पिछला महीना">‹</button><b>${base.toLocaleDateString("hi-IN", { month: "long", year: "numeric" })}</b><button class="btn small quiet" data-cal="1" title="अगला महीना" aria-label="अगला महीना">›</button></div>
    <div class="cal-g">${["सोम", "मंगल", "बुध", "गुरु", "शुक्र", "शनि", "रवि"].map((d) => `<div class="cal-h">${d}</div>`).join("")}${cells.join("")}</div>
    <p class="small muted"><span class="plat youtube">YouTube</span> <span class="plat instagram">Instagram</span> <span class="plat facebook">Facebook</span> — scheduled समय, या publish होने का दिन</p></div>`;
}
function bindPublish() {
  $$("[data-ptab]").forEach((b) => (b.onclick = () => { S.pubTab = b.dataset.ptab; render(); }));
  $$("[data-cal]").forEach((b) => (b.onclick = () => { S.calOff += +b.dataset.cal; render(); }));
  bindCards();
}

// ---------- trends ----------
function trendsView() {
  const t = S.trends || { trends: [], setup: {} }; const st = t.setup || {}; const canEdit = S.user.role !== "viewer";
  const src = { google_trends: "Google Trends", yt_popular: "YouTube Top", yt_channel: "आपके देखे channels" };
  const bySrc = {}; for (const r of t.trends) (bySrc[r.source] = bySrc[r.source] || []).push(r);
  return `<div class="pghead"><div><h1>Trends</h1><p class="muted small">${t.fetched_at ? `आख़िरी बार: ${new Date(t.fetched_at).toLocaleString("hi-IN")}` : "अभी trends नहीं लाए गए"} — किसी trend पर “+ Idea” दबाएँ, वह Plan में जुड़ जाएगा।</p></div>${canEdit ? `<button class="btn primary" id="tr-refresh">ताज़ा करें</button>` : ""}</div>
    ${!st.yt_api_key ? `<div class="note small">YouTube Top के लिए .env में YT_API_KEY डालें। पसंदीदा channels देखने के लिए WATCH_CHANNELS=UC… सेट करें।</div>` : ""}
    ${radarSection(canEdit)}
    <div class="trcols">${Object.keys(bySrc).length ? Object.entries(bySrc).map(([k, rows]) => `<section class="card"><div class="card-h"><h2>${src[k] || esc(k)}</h2><span class="small muted">${rows.length}</span></div><ul class="trlist2">${rows.slice(0, 25).map((r) => `<li><span class="grow">${r.url ? `<a href="${r.url}" target="_blank" rel="noopener">${esc(r.title)}</a>` : esc(r.title)}<span class="small muted">${r.meta?.traffic ? r.meta.traffic + "+ searches" : r.meta?.views_per_day ? r.meta.views_per_day.toLocaleString("en-IN") + "/day" : r.meta?.views ? r.meta.views.toLocaleString("en-IN") + " views" : ""}${r.meta?.channel ? " · " + esc(r.meta.channel) : ""}</span></span>${canEdit ? `<button class="btn quiet small" data-tidea="${esc(r.title)}">+ Idea</button>` : ""}</li>`).join("")}</ul></section>`).join("") : `<div class="empty"><p>“ताज़ा करें” दबाएँ — Google Trends बिना किसी key के आ जाते हैं।</p></div>`}</div>`;
}
function radarSection(canEdit) {
  const R = S.radar; if (!R) return "";
  const st = R.settings || {}; const admin = S.user.role === "admin"; const dis = admin ? "" : "disabled";
  return `<section class="card radar"><div class="card-h"><h2>Daily radar — आपकी niche में क्या चल रहा है</h2><span class="small muted">${R.last ? "आख़िरी बार: " + relTime(R.last) : "अभी तक नहीं चला"}</span></div>
    <p class="small muted">हर दिन चुने समय पर: आपकी niche की search + पसंदीदा channels → जो वीडियो अपने channel के normal से ${st.outlier_x || 2}× ज़्यादा चल रहे हैं (outliers) → ${st.ideas || 5} ideas → WhatsApp पर छोटा digest। सिर्फ़ सुझाव — बनाना/डालना आपके हाथ में।</p>
    ${!R.has_yt_key ? `<div class="note small">Niche search के लिए .env में <b>YT_API_KEY</b> चाहिए (free, Google Cloud)। बिना key के सिर्फ़ Google Trends आएँगे।</div>` : ""}
    <details ${admin && !R.last ? "open" : ""}><summary class="small"><b>Radar settings</b></summary><form id="rd-form" class="row" style="align-items:flex-end;flex-wrap:wrap">
      <label class="chk"><input type="checkbox" name="daily" ${st.daily ? "checked" : ""} ${dis}> रोज़ चलाएँ</label>
      <div class="field"><label>किस समय</label><select name="hour" ${dis}>${Array.from({ length: 24 }, (_, h) => `<option value="${h}" ${+st.hour === h ? "selected" : ""}>${String(h).padStart(2, "0")}:00</option>`).join("")}</select></div>
      <div class="field"><label>Outlier मतलब normal से</label><select name="outlier_x" ${dis}>${[1.5, 2, 3, 5].map((x) => `<option value="${x}" ${+st.outlier_x === x ? "selected" : ""}>${x}×</option>`).join("")}</select></div>
      <div class="field"><label>Ideas</label><select name="ideas" ${dis}>${[3, 5, 8, 10].map((x) => `<option ${+st.ideas === x ? "selected" : ""}>${x}</option>`).join("")}</select></div>
      <div class="field" style="flex:1;min-width:240px"><label>Niche searches (हर line में एक search)</label><textarea name="queries" rows="3" ${dis}>${esc((st.queries || []).join("\n"))}</textarea></div>
      <div class="field" style="flex:1;min-width:240px"><label>नज़र रखने वाले channels (UC… id या @handle, हर line में एक)</label><textarea name="watch" rows="3" ${dis}>${esc((st.watch || []).join("\n"))}</textarea></div>
      ${admin ? `<button class="btn primary">Radar सेव करें</button>` : ""}</form></details>
    ${canEdit ? `<div class="row" style="gap:.5rem;margin:.5rem 0"><button class="btn" id="rd-run">Radar अभी चलाएँ</button><label class="chk small"><input type="checkbox" id="rd-send"> WhatsApp पर भी भेजें</label></div>` : ""}
    <ul class="trlist2">${(R.outliers || []).map((r) => `<li><span class="grow">${r.url ? `<a href="${r.url}" target="_blank" rel="noopener">${esc(r.title)}</a>` : esc(r.title)}<span class="small muted">${r.meta?.views_per_day ? (+r.meta.views_per_day).toLocaleString("en-IN") + "/दिन" : ""}${r.meta?.outlier_x ? ` · <b style="color:var(--amber)">${r.meta.outlier_x}×</b> normal से` : ""}${r.meta?.channel ? " · " + esc(r.meta.channel) : ""}</span></span>${canEdit ? `<button class="btn quiet small" data-tidea="${esc(r.title)}">+ Idea</button>` : ""}</li>`).join("") || `<li class="small muted">अभी कोई outlier नहीं — “Radar अभी चलाएँ” दबाएँ।</li>`}</ul></section>`;
}
function bindTrends() {
  const rdf = $("#rd-form"); if (rdf) rdf.onsubmit = async (e) => { e.preventDefault(); const f = rdf.elements; const lines = (v) => v.split("\n").map((x) => x.trim()).filter(Boolean);
    const body = { channel_id: S.channel, settings: { daily: f.daily.checked, hour: +f.hour.value, outlier_x: +f.outlier_x.value, ideas: +f.ideas.value, queries: lines(f.queries.value), watch: lines(f.watch.value) } };
    try { const r = await api("PUT", "/radar", body); S.radar.settings = r.settings; toast("Radar settings सेव हो गईं"); } catch (err) { toast(err.message); } };
  const rr = $("#rd-run"); if (rr) rr.onclick = async () => { rr.disabled = true; rr.textContent = "Radar चल रहा है… (1–2 मिनट)"; try { const r = await api("POST", "/radar/run", { channel_id: S.channel, send: $("#rd-send")?.checked }); toast(`${(r.outliers || []).length} outliers मिले, ${(r.ideas || []).length} ideas Plan में जुड़े`); } catch (e) { toast(e.message); } load().then(render); };
  const rf = $("#tr-refresh"); if (rf) rf.onclick = async () => { rf.disabled = true; rf.textContent = "ला रहे हैं…"; try { const r = await api("POST", "/trends/refresh"); toast(`${r.count} trends मिले`); } catch (e) { toast(e.message); } load().then(render); };
  $$("[data-tidea]").forEach((b) => (b.onclick = async () => { b.disabled = true; try { await api("POST", "/ideas", { title: b.dataset.tidea, format: "short", source: "trend", channel_id: S.channel }); b.textContent = "✓ Plan में"; toast("Idea जुड़ गया — Plan में उसकी script लिखें"); } catch (e) { toast(e.message); b.disabled = false; } }));
}

// ---------- help ----------
function helpView() {
  const mods = [["rec", "Record", "#/record", "Camera और teleprompter के साथ सीधे browser में record करें; upload अपने-आप होता है।"], ["upload", "Upload", "#/new", "एक या कई clips डालें — टूटे upload वहीं से आगे चलते हैं।"],
    ["music", "Montage", "#/new?type=montage", "बिना आवाज़ वाले clips और music से beat पर कटा reel।"], ["image", "Thumbnails", "#/thumbs", "Best frame, cutout, बड़ा हिंदी text, 13 layouts और A/B variants।"],
    ["film", "Editor", "#/projects", "कट, captions, text, B-roll, music, effects और Shorts — एक जगह।"], ["bulb", "Plan", "#/plan", "Trends से ideas, ideas से script, फिर record।"],
    ["trend", "Trends", "#/trends", "Google Trends, YouTube Top और आपके पसंदीदा channels।"], ["send", "Publish", "#/publish", "YouTube, Instagram और Facebook पर — मंज़ूरी के बाद, तय समय पर।"],
    ["chart", "Analytics", "#/analytics", "क्या चल रहा है — style, hook और लंबाई से सीख।"], ["lib", "Library", "#/library", "Music, SFX, stickers, frames और LUTs — सब licence-safe।"],
    ["tv", "Channels & Brand", "#/settings", "कई channels, brand kit और connections।"], ["gear", "Settings", "#/account", "Password, users और storage की सफ़ाई।"]];
  return `<div class="pghead"><div><h1>Help</h1><p class="muted small">Vividora के सारे modules — एक नज़र में।</p></div></div>
    <div class="helpgrid">${mods.map(([i, t, h, d]) => `<a class="hcard" href="${h}">${ic(i)}<b>${t}</b><span class="small muted">${d}</span></a>`).join("")}</div>
    <div class="hcols2"><section class="card"><div class="card-h"><h2>वीडियो कैसे बनता है</h2></div><ol class="steps"><li><b>Record / Upload</b> — Autopilot चालू रखें</li><li><b>जाँच</b> — preview, आवाज़ साफ़, चेहरा tracking</li><li><b>Transcript</b> — हिंदी शब्द-दर-शब्द timing</li><li><b>कट</b> — चुप्पी, अं-आं, दोबारा बोला हुआ</li><li><b>Render</b> — captions, zoom, music, Shorts + 3 thumbnails</li><li><b>मंज़ूरी</b> → <b>Publish</b> (★ thumbnail के साथ)</li></ol></section>
      <section class="card"><div class="card-h"><h2>Tips</h2></div><ul class="hlist">${TIPS.map((t) => `<li>${t}</li>`).join("")}</ul>
        <h3 class="small" style="margin-top:1rem">Editor shortcuts</h3><p class="small muted"><kbd>Space</kbd> play · <kbd>I</kbd> / <kbd>O</kbd> हिस्सा चुनें · <kbd>X</kbd> काटें · <kbd>Ctrl+Z</kbd> undo</p>
        <p class="small muted">Setup guides: <code>docs/first-video.md</code>, <code>docs/cloudflare-tunnel.md</code>, <code>docs/google-drive.md</code></p></section></div>`;
}

// ---------- settings (account, users, storage) ----------
function accountView() {
  const admin = S.user.role === "admin";
  return `<div class="pghead"><div><h1>Settings</h1><p class="muted small">आपका account, team और server की जगह।</p></div></div>
    <div class="setgrid">
      <section class="card"><div class="card-h"><h2>आपका account</h2></div><p><b>${esc(S.user.name)}</b> <span class="pill">${S.user.role}</span><br><span class="small muted">${esc(S.user.email || "")}</span></p>
        <form id="pw" class="row" style="align-items:flex-end"><div class="field"><label>मौजूदा password</label><input name="current" type="password" required autocomplete="current-password"></div><div class="field"><label>नया password</label><input name="new" type="password" minlength="8" required autocomplete="new-password"></div><button class="btn">बदलें</button></form>
        <button class="btn quiet danger" id="logout2">${ic("out")} बाहर निकलें</button></section>
      <section class="card"><div class="card-h"><h2>Workspace</h2></div><ul class="hlist">
        <li><a href="#/settings">Channels & Brand kit, YouTube / Instagram connections</a></li>${admin ? `<li><a href="#/users">Users और roles (${(S.users || []).length})</a></li>` : ""}<li><a href="#/status">Workers, queue और archive की स्थिति</a></li>
        <li><span>Home के sections</span><button class="btn small quiet" id="home-reset">Default पर लौटें</button></li></ul></section>
    </div>
    ${admin ? `<section class="card" id="storage"><div class="card-h"><h2>Storage</h2><button class="btn small" id="st-load">फिर जाँचें</button></div>
      <p class="muted small">server की disk कितनी भरी है, किस project ने कितनी जगह ली — और सुरक्षित तरीके से साफ़ करें। project हटाने पर उसकी सारी फ़ाइलें अपने-आप हट जाती हैं।</p><div id="st-body"></div></section>` : ""}`;
}
function bindAccount() {
  $("#pw").onsubmit = async (e) => { e.preventDefault(); const f = e.target; try { await api("POST", "/auth/password", { current: f.current.value, new: f.new.value }); toast("Password बदल दिया"); f.reset(); } catch (err) { toast(err.message); } };
  $("#logout2").onclick = logout;
  $("#home-reset").onclick = () => { try { localStorage.removeItem("vividora_home"); } catch {} toast("Home के sections default पर लौट आए"); };
  const stl = $("#st-load"); if (stl) { stl.onclick = () => loadStorage(); loadStorage(); }
}

// ---------- boot ----------
(async function boot() {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  S.token = localStorage.getItem("vividora_token");
  if (S.token) { try { const me = await api("GET", "/auth/me"); S.user = me.user; S.ws = me.workspace; await load(); } catch { S.token = null; } }
  render();
})();

function fmtBytes(n) { n = +n || 0; const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0; while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; } return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${u[i]}`; }
async function loadStorage() {
  const box = $("#st-body"); if (!box) return; box.innerHTML = `<p class="muted small">गिनती हो रही है…</p>`;
  let d; try { d = await api("GET", "/storage"); } catch (e) { box.innerHTML = `<p class="small">${esc(e.message)}</p>`; return; }
  const m = d.disk.media; const pct = Math.round(m.used / m.total * 100); const g = d.groups || {};
  const rows = (d.projects || []).slice(0, 25).map((p) => `<tr><td>${esc(p.title)}${p.published ? ` <span class="pill small">published</span>` : ""}</td><td class="muted small">${esc(p.status)}</td><td>${fmtBytes(p.total)}</td><td class="muted small">rec ${fmtBytes(p.source || 0)} · cache ${fmtBytes(p.cache || 0)} · video ${fmtBytes(p.render || 0)}</td><td><button class="btn small danger quiet" data-stdel="${p.id}" data-t="${esc(p.title)}">हटाएँ</button></td></tr>`).join("");
  box.innerHTML = `<div class="stbar"><i style="width:${pct}%;background:${pct > 85 ? "#e5484d" : pct > 70 ? "#f2b33d" : "#46a758"}"></i></div>
    <p class="small"><b>${fmtBytes(m.used)}</b> भरा / ${fmtBytes(m.total)} · <b>${fmtBytes(m.free)} खाली</b> (${pct}%)${d.disk.archive ? ` · archive drive: ${fmtBytes(d.disk.archive.free)} खाली` : ""}</p>
    <div class="ststats"><span>recordings ${fmtBytes(g.source || 0)}</span><span>cache ${fmtBytes(g.cache || 0)}</span><span>final videos ${fmtBytes(g.render || 0)}</span><span>library ${fmtBytes(d.library)}</span><span>बेकार फ़ाइलें ${fmtBytes(d.orphans.bytes)}</span><span>अधूरे upload ${fmtBytes(d.uploads.bytes)}</span></div>
    <h3 class="small">साफ़ करें</h3>
    <label class="chk small"><input type="checkbox" data-stw="orphans" checked> बेकार फ़ाइलें (किसी project/library में नहीं — हमेशा सुरक्षित) · ${fmtBytes(d.orphans.bytes)}</label>
    <label class="chk small"><input type="checkbox" data-stw="uploads" checked> अधूरे uploads (1 दिन से पुराने) · ${fmtBytes(d.uploads.bytes)}</label>
    <label class="chk small"><input type="checkbox" data-stw="cache"> पूरे हो चुके projects का cache (preview copy, speech audio, cutout) — editor में दोबारा बन सकता है</label>
    <label class="chk small"><input type="checkbox" data-stw="sources"> पूरे हो चुके projects की original recording (final videos रहेंगे) — सबसे ज़्यादा जगह</label>
    <label class="chk small"><input type="checkbox" data-stw="renders"> publish हो चुके projects की final videos (YouTube/IG पर हैं)</label>
    <div class="row"><label class="small">कितने दिन पुराने पूरे projects <input type="number" id="st-days" value="7" min="0" max="365" style="width:5rem"></label><button class="btn primary small" id="st-clean">साफ़ करें</button></div>
    <h3 class="small">सबसे बड़े projects</h3><div class="tablewrap"><table><tr><th>Project</th><th>Status</th><th>कुल</th><th></th><th></th></tr>${rows || `<tr><td colspan="5" class="muted small">कोई project नहीं</td></tr>`}</table></div>
    <p class="muted small">Docker की पुरानी images भी जगह लेती हैं — server पर कभी-कभी चलाएँ: <code>docker image prune -f</code></p>`;
  $("#st-clean").onclick = async () => { const what = $$("[data-stw]").filter((x) => x.checked).map((x) => x.dataset.stw); if (!what.length) return toast("साफ़ करने के लिए कम से कम एक चीज़ चुनें");
    if ((what.includes("sources") || what.includes("renders")) && !confirm("चुनी हुई फ़ाइलें हमेशा के लिए हटेंगी। आगे बढ़ें?")) return;
    const r = await api("POST", "/storage/clean", { what, days: +$("#st-days").value }); toast(`${fmtBytes(r.freed)} जगह खाली हुई`); loadStorage(); };
  $$("[data-stdel]").forEach((b) => (b.onclick = async () => { if (!confirm(`"${b.dataset.t}" और उसकी सारी फ़ाइलें हटाएँ?`)) return; await api("DELETE", `/projects/${b.dataset.stdel}`); toast("Project हटा दिया"); await load(); loadStorage(); }));
}
