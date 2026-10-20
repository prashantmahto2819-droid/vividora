// 🎤 Voice / typed commands — floating button on every screen.
// Speech is recognised in the browser (Web Speech API, hi-IN, free — no server credit);
// the text goes to POST /api/command, which never publishes on its own.
let ctx = null;
let rec = null;

const css = `
.vo-fab{position:fixed;right:16px;bottom:84px;z-index:60;width:52px;height:52px;border-radius:50%;border:0;background:var(--accent,#F2B33D);color:#111;font-size:22px;box-shadow:0 6px 20px rgba(0,0,0,.35);cursor:pointer}
.vo-fab.live{animation:vo-pulse 1s infinite;background:#ff3b30;color:#fff}
@keyframes vo-pulse{0%{box-shadow:0 0 0 0 rgba(255,59,48,.6)}100%{box-shadow:0 0 0 18px rgba(255,59,48,0)}}
.vo-box{position:fixed;right:16px;bottom:146px;z-index:60;width:min(360px,calc(100vw - 32px));background:var(--panel,#1b1b1f);color:var(--text,#eee);border:1px solid var(--line,#333);border-radius:14px;padding:12px;box-shadow:0 10px 30px rgba(0,0,0,.4);font-size:.9rem}
.vo-box[hidden]{display:none}
.vo-box form{display:flex;gap:6px;margin-top:8px}.vo-box input{flex:1;min-width:0}
.vo-out{white-space:pre-wrap;max-height:40vh;overflow:auto}
.vo-heard{opacity:.7;font-style:italic;margin-bottom:6px}
@media (min-width:900px){.vo-fab{bottom:20px}.vo-box{bottom:82px}}
body.ed-mode .vo-fab{bottom:12px;top:auto;right:12px;width:40px;height:40px;font-size:18px}
body.ed-mode .vo-box{bottom:60px;top:auto}
`;

function projectId() {
  const m = location.hash.match(/^#\/projects\/([^/?]+)/);
  return m ? m[1] : null;
}

function show(html) {
  const b = document.getElementById("vo-box");
  b.hidden = false;
  b.querySelector(".vo-out").innerHTML = html;
}

function esc(s) { return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]); }

async function send(text) {
  text = (text || "").trim();
  if (!text) return;
  show(`<div class="vo-heard">“${esc(text)}”</div>…`);
  try {
    const r = await ctx.api("POST", "/command", { text, project_id: projectId() });
    show(`<div class="vo-heard">“${esc(text)}”</div>${esc(r.reply || "हो गया")}`);
    if (r.changed) ctx.reload?.(r);
    if (r.navigate) location.hash = r.navigate;
  } catch (e) {
    show(`<div class="vo-heard">“${esc(text)}”</div>⚠ ${esc(e.message)}`);
  }
}

function listen() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const fab = document.getElementById("vo-fab");
  if (!SR) { show("इस browser में बोलकर command नहीं चलता — नीचे लिखें (Chrome में बोल सकते हैं)।"); document.querySelector("#vo-box input").focus(); return; }
  if (rec) { rec.stop(); return; }
  rec = new SR();
  rec.lang = "hi-IN";
  rec.interimResults = true;
  rec.maxAlternatives = 1;
  let final = "";
  rec.onresult = (e) => {
    let t = "";
    for (const r of e.results) { t += r[0].transcript; if (r.isFinal) final = t; }
    show(`<div class="vo-heard">🎤 ${esc(t)}</div>`);
  };
  rec.onerror = (e) => show(e.error === "not-allowed" ? "Mic की permission दें (address bar में 🔒 → Microphone → Allow)।" : "सुनाई नहीं दिया — फिर से दबाएँ या लिखें।");
  rec.onend = () => { fab.classList.remove("live"); rec = null; if (final) send(final); };
  fab.classList.add("live");
  show("🎤 बोलिए… जैसे “इसके 3 शॉर्ट्स बना दो” या “music हटाओ”");
  rec.start();
}

export function mount(c) {
  ctx = c;
  if (document.getElementById("vo-fab")) return;
  const st = document.createElement("style");
  st.textContent = css;
  document.head.appendChild(st);
  const fab = document.createElement("button");
  fab.id = "vo-fab"; fab.className = "vo-fab"; fab.title = "बोलकर command दें (hold नहीं, बस tap)"; fab.textContent = "🎤";
  fab.onclick = listen;
  const box = document.createElement("div");
  box.id = "vo-box"; box.className = "vo-box"; box.hidden = true;
  box.innerHTML = `<div class="row between"><b class="small">Voice / command</b><button class="ibtn" id="vo-x" aria-label="बंद">✕</button></div>
    <div class="vo-out small"></div>
    <form id="vo-form"><input placeholder="या लिखें: help, status, 3 shorts बनाओ…" maxlength="300"><button class="btn small primary">भेजें</button></form>`;
  document.body.append(fab, box);
  box.querySelector("#vo-x").onclick = () => (box.hidden = true);
  box.querySelector("#vo-form").onsubmit = (e) => { e.preventDefault(); const i = box.querySelector("input"); send(i.value); i.value = ""; };
}

export function unmount() {
  document.getElementById("vo-fab")?.remove();
  document.getElementById("vo-box")?.remove();
}
