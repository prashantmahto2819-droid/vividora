// 3D Studio — Scenes & explainer page (#/scenes3d): 8 procedural environments, lighting, camera, characters in
// slots, a storyboard of scenes with dialogue → "3D explainer बनाओ" renders one video and opens it as a project.
import { buildShot } from "./chars3d.js";
import { injectCss, livePreview, jobsList, esc } from "./chars3d-ui.js";

let V = null;
const CAM_LABEL = { wide: "wide", medium: "medium", closeup: "close-up", twoshot: "two-shot", low: "low angle", high: "high angle" };

function newScene(cat, i) {
  return { scene: cat.scenes[i % cat.scenes.length].id, lighting: "day", camera: "", orbit: 0, push: 0, hold: 0,
           characters: [{ profile: cat.profiles[0].id, slot: 0, animation: "", expression: "smile" }], lines: "" };
}

export async function mountScenes(root, ctx) {
  injectCss();
  const { api, toast } = ctx;
  const cat = await api("GET", "/chars3d");
  V = { cat, title: "", format: "16:9", cur: 0, scenes: [newScene(cat, 1)], jobs: [], timer: 0, autopilot: false };
  root.innerHTML = `<div class="pghead"><div><h1>3D Studio — Scenes & explainer</h1><p class="muted">Classroom, office, clinic, घर, दुकान, gym, park, stage — characters को जगह दें, हर scene की lines लिखें; पूरा 3D explainer video (आवाज़ + lip-sync + captions) एक project बन जाता है।</p></div>
    <a class="btn quiet" href="#/characters3d">🧍 Characters →</a></div>
    <div class="c3d sb"><div><div class="c3d-stage" id="s3-stage"></div><p class="small muted" style="margin-top:.4rem">खींचकर घुमाएँ · scroll से zoom · यह चुने हुए scene का preview है</p>
      <div class="card" style="margin-top:.8rem"><div class="card-h"><h2>3D jobs</h2><button class="btn small quiet" id="s3-jobs-r">↻</button></div><ul class="c3d-jobs" id="s3-jobs"></ul></div></div>
      <div class="c3d-side" id="s3-side"></div></div>`;
  V.pv = livePreview(root.querySelector("#s3-stage"), { width: 800, height: 450 });
  const shotSpec = (sc) => ({ transparent: false, scene: { name: sc.scene, lighting: sc.lighting }, camera: { preset: sc.camera || (sc.characters.length > 1 ? "twoshot" : "medium") },
    characters: sc.characters.map((c, i) => { const p = cat.profiles.find((x) => x.id === c.profile) || cat.profiles[0]; return { spec: p.spec, slot: c.slot ?? i, ...(c.animation ? { animation: c.animation } : {}), expression: c.expression || "smile", expressionAmount: 0.5, talk: [], visemes: [] }; }), fps: 25, duration: 10 });
  const refresh = () => V.pv.set(shotSpec(V.scenes[V.cur]));
  const jobs = async () => { try { V.jobs = (await api("GET", "/chars3d/jobs")).jobs || []; } catch {} const ul = root.querySelector("#s3-jobs"); if (ul) jobsList(ul, V.jobs, api, jobs); clearTimeout(V.timer); if (V.jobs.some((j) => ["queued", "running"].includes(j.status))) V.timer = setTimeout(jobs, 3000); };
  root.querySelector("#s3-jobs-r").onclick = jobs;
  const side = () => {
    const el = root.querySelector("#s3-side"); const sc = V.scenes[V.cur];
    const opt = (arr, cur, lab = (x) => x.label ?? x) => arr.map((a) => `<option value="${esc(a.id ?? a)}" ${(a.id ?? a) === cur ? "selected" : ""}>${esc(lab(a))}</option>`).join("");
    el.innerHTML = `<div class="card"><div class="card-h"><h2>Explainer</h2></div>
      <div class="field"><label>Video का नाम</label><input id="s3-title" value="${esc(V.title)}" placeholder="जैसे: Clinic में पहला दिन"></div>
      <div class="c3d-row"><div class="field"><label>Format</label><select id="s3-fmt"><option value="16:9" ${V.format === "16:9" ? "selected" : ""}>16:9 YouTube</option><option value="9:16" ${V.format === "9:16" ? "selected" : ""}>9:16 Reel / Short</option></select></div>
        <div class="field"><label>बाद में</label><label class="chk"><input type="checkbox" id="s3-ap" ${V.autopilot ? "checked" : ""}> Autopilot चलाए</label></div></div></div>
      <div class="card"><div class="card-h"><h2>Scenes (${V.scenes.length})</h2><button class="btn small" id="s3-add">+ scene</button></div>
      <div class="choices" style="margin-bottom:.5rem">${V.scenes.map((s, i) => `<button class="chip ${i === V.cur ? "on" : ""}" data-go="${i}">${i + 1}. ${esc((cat.scenes.find((x) => x.id === s.scene) || {}).label || s.scene)}</button>`).join("")}</div>
      <div class="sb-scene">
        <div class="c3d-row"><div class="field"><label>जगह</label><select id="s3-scene">${opt(cat.scenes, sc.scene)}</select></div>
          <div class="field"><label>रोशनी</label><select id="s3-light">${opt(cat.lighting, sc.lighting, (x) => x)}</select></div></div>
        <div class="c3d-row"><div class="field"><label>Camera</label><select id="s3-cam"><option value="">auto</option>${opt(cat.cameras, sc.camera, (x) => CAM_LABEL[x] || x)}</select></div>
          <div class="field"><label>Camera घूमे (orbit)</label><input type="range" id="s3-orbit" min="-1" max="1" step="0.1" value="${sc.orbit}"></div>
          <div class="field"><label>Push-in</label><input type="range" id="s3-push" min="0" max="2" step="0.1" value="${sc.push}"></div></div>
        <div class="field"><label>Characters (जगह = slot)</label>
          ${sc.characters.map((c, i) => `<div class="sb-char"><b class="small">${i + 1}</b><select data-cp="${i}">${opt(cat.profiles, c.profile, (p) => p.name)}</select>
            <select data-cs="${i}">${[0, 1, 2, 3].map((n) => `<option value="${n}" ${c.slot === n ? "selected" : ""}>जगह ${n + 1}</option>`).join("")}</select>
            <select data-ca="${i}"><option value="">auto</option>${opt(cat.animations, c.animation)}</select>
            <select data-ce="${i}">${opt(cat.expressions, c.expression || "smile", (x) => x)}</select><button class="btn small quiet" data-cx="${i}">✕</button></div>`).join("")}
          ${sc.characters.length < 4 ? `<button class="btn small" id="s3-addc">+ character</button>` : ""}</div>
        <div class="field sb-lines"><label>Lines — "1: " से बोलने वाला (character नंबर), एक line = एक वाक्य</label><textarea id="s3-lines" placeholder="1: नमस्ते, clinic में आपका स्वागत है।&#10;2: धन्यवाद डॉक्टर, मुझे सिरदर्द रहता है।">${esc(sc.lines)}</textarea></div>
        <div class="c3d-row"><div class="field"><label>कम से कम सेकंड (बिना lines)</label><input type="number" id="s3-hold" min="0" max="60" value="${sc.hold}"></div>
          <div class="field" style="align-self:end">${V.scenes.length > 1 ? `<button class="btn small quiet" id="s3-del">scene हटाएँ</button>` : ""}</div></div>
      </div>
      <button class="btn primary" id="s3-go" style="width:100%;justify-content:center">🎬 3D explainer बनाओ</button>
      <p class="small muted" style="margin-top:.4rem">हर scene की आवाज़ AI voice से बनती है (characters के gender से), lip-sync अपने-आप; तैयार video नया project बनता है — captions script से, बिना transcription।</p></div>`;
    const on = (id, ev, fn) => { const x = el.querySelector(id); if (x) x[ev] = fn; };
    on("#s3-title", "oninput", (e) => (V.title = e.target.value)); on("#s3-fmt", "onchange", (e) => (V.format = e.target.value)); on("#s3-ap", "onchange", (e) => (V.autopilot = e.target.checked));
    on("#s3-add", "onclick", () => { V.scenes.push(newScene(cat, V.scenes.length)); V.cur = V.scenes.length - 1; side(); refresh(); });
    el.querySelectorAll("[data-go]").forEach((b) => (b.onclick = () => { V.cur = +b.dataset.go; side(); refresh(); }));
    on("#s3-scene", "onchange", (e) => { sc.scene = e.target.value; side(); refresh(); }); on("#s3-light", "onchange", (e) => { sc.lighting = e.target.value; refresh(); });
    on("#s3-cam", "onchange", (e) => { sc.camera = e.target.value; refresh(); }); on("#s3-orbit", "onchange", (e) => (sc.orbit = +e.target.value)); on("#s3-push", "onchange", (e) => (sc.push = +e.target.value));
    el.querySelectorAll("[data-cp]").forEach((s) => (s.onchange = () => { sc.characters[+s.dataset.cp].profile = s.value; refresh(); }));
    el.querySelectorAll("[data-cs]").forEach((s) => (s.onchange = () => { sc.characters[+s.dataset.cs].slot = +s.value; refresh(); }));
    el.querySelectorAll("[data-ca]").forEach((s) => (s.onchange = () => { sc.characters[+s.dataset.ca].animation = s.value; refresh(); }));
    el.querySelectorAll("[data-ce]").forEach((s) => (s.onchange = () => { sc.characters[+s.dataset.ce].expression = s.value; refresh(); }));
    el.querySelectorAll("[data-cx]").forEach((b) => (b.onclick = () => { sc.characters.splice(+b.dataset.cx, 1); side(); refresh(); }));
    on("#s3-addc", "onclick", () => { sc.characters.push({ profile: cat.profiles[(sc.characters.length * 7) % cat.profiles.length].id, slot: sc.characters.length, animation: "", expression: "smile" }); side(); refresh(); });
    on("#s3-lines", "oninput", (e) => (sc.lines = e.target.value)); on("#s3-hold", "onchange", (e) => (sc.hold = +e.target.value || 0));
    on("#s3-del", "onclick", () => { V.scenes.splice(V.cur, 1); V.cur = Math.max(0, V.cur - 1); side(); refresh(); });
    on("#s3-go", "onclick", async () => {
      if (!V.title.trim()) return toast("video का नाम लिखें");
      const scenes = V.scenes.map((s) => ({ scene: s.scene, lighting: s.lighting, camera: s.camera || null, orbit: s.orbit, push: s.push, hold: s.hold,
        characters: s.characters.map((c) => ({ profile: c.profile, slot: c.slot, animation: c.animation || null, expression: c.expression })),
        lines: s.lines.split("\n").map((t) => t.trim()).filter(Boolean).map((t) => { const m = t.match(/^(\d+)\s*[:：\-]\s*(.+)$/); return m ? { speaker: +m[1] - 1, text: m[2] } : { speaker: 0, text: t }; }) }));
      const btn = el.querySelector("#s3-go"); btn.disabled = true;
      try { await api("POST", "/chars3d/storyboard", { title: V.title, format: V.format, scenes, autopilot: V.autopilot, channel_id: ctx.S.channel }); toast("3D explainer बन रहा है — नीचे progress; तैयार होने पर project खुलेगा"); jobs(); } catch (e) { toast(e.message); } finally { btn.disabled = false; }
    });
  };
  side(); refresh(); jobs();
}

export function unmountScenes() { if (!V) return; clearTimeout(V.timer); V.pv?.destroy(); V = null; }
