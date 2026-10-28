// "मेरे 3D models (.glb)" — imported / photo-made 3D characters: import, preview (turntable), download, rename, delete.
// Shared by Characters, 3D Studio and Image → 3D pages.

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const CSS = `.m3-head{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;justify-content:space-between;margin-bottom:.5rem}
.m3-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:.6rem}
.m3-card{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:.6rem;display:flex;flex-direction:column;gap:.35rem;min-width:0}
.m3-card b{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.m3-btns{display:flex;gap:.3rem;flex-wrap:wrap}
.m3-modal{position:fixed;inset:0;z-index:200;background:rgba(0,0,0,.75);display:flex;align-items:center;justify-content:center;padding:1rem}
.m3-box{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:.8rem;width:min(720px,100%)}
.m3-box canvas{width:100%;height:min(62vh,520px);display:block;border-radius:10px;background:linear-gradient(#1f2632,#141922);touch-action:none;cursor:grab}`;
function css() { if (!document.getElementById("m3-css")) { const s = document.createElement("style"); s.id = "m3-css"; s.textContent = CSS; document.head.appendChild(s); } }

export async function viewModel(item) {
  css();
  const THREE = await import("./three.module.min.js"); const { GLTFLoader } = await import("./gltf-loader.js"); // three.js only loads when a model is opened
  const modal = document.createElement("div"); modal.className = "m3-modal";
  modal.innerHTML = `<div class="m3-box"><div class="m3-head"><b>🧊 ${esc(item.name)}</b><span><a class="btn small" href="${item.url}" download="${esc(item.name)}.glb">⬇ .glb</a> <button class="btn small quiet" id="m3-x">✕ बंद</button></span></div><canvas></canvas><p class="small muted" id="m3-st">लोड हो रहा है… · खींचकर घुमाएँ · scroll से zoom</p></div>`;
  document.body.appendChild(modal);
  const canvas = modal.querySelector("canvas"), st = modal.querySelector("#m3-st");
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene(), cam = new THREE.PerspectiveCamera(35, 1, 0.01, 100);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x445066, 1.6)); const dl = new THREE.DirectionalLight(0xffffff, 2.2); dl.position.set(2, 3, 4); scene.add(dl);
  const pivot = new THREE.Group(); scene.add(pivot);
  let raf = 0, dist = 3, drag = null, auto = true, dead = false;
  const size = () => { const w = canvas.clientWidth, h = canvas.clientHeight; renderer.setSize(w, h, false); cam.aspect = w / h; cam.updateProjectionMatrix(); };
  const loop = () => { if (dead) return; size(); if (auto) pivot.rotation.y += 0.008; cam.position.set(0, 0, dist); cam.lookAt(0, 0, 0); renderer.render(scene, cam); raf = requestAnimationFrame(loop); };
  canvas.onpointerdown = (e) => { drag = [e.clientX, e.clientY]; auto = false; canvas.setPointerCapture(e.pointerId); };
  canvas.onpointermove = (e) => { if (!drag) return; pivot.rotation.y += (e.clientX - drag[0]) * 0.01; pivot.rotation.x = Math.max(-1.2, Math.min(1.2, pivot.rotation.x + (e.clientY - drag[1]) * 0.01)); drag = [e.clientX, e.clientY]; };
  canvas.onpointerup = () => { drag = null; };
  canvas.onwheel = (e) => { e.preventDefault(); dist = Math.max(0.8, Math.min(12, dist * (1 + e.deltaY * 0.001))); };
  const close = () => { dead = true; cancelAnimationFrame(raf); renderer.dispose(); modal.remove(); };
  modal.querySelector("#m3-x").onclick = close; modal.onclick = (e) => { if (e.target === modal) close(); };
  new GLTFLoader().load(item.url, (g) => {
    const box = new THREE.Box3().setFromObject(g.scene), c = box.getCenter(new THREE.Vector3()), sz = box.getSize(new THREE.Vector3());
    const k = 1.6 / Math.max(sz.x, sz.y, sz.z, 1e-6); g.scene.scale.setScalar(k); g.scene.position.sub(c.multiplyScalar(k)); pivot.add(g.scene);
    dist = 3.4; st.textContent = "खींचकर घुमाएँ · scroll से zoom"; loop();
  }, undefined, (e) => { st.textContent = "model खुल नहीं पाया: " + (e?.message || e); st.style.color = "#ff6b5e"; });
}

// The panel. el = container element, ctx = { S, api, toast }
export async function mountModels(el, ctx, opts = {}) {
  css();
  const { S, api, toast } = ctx;
  const canEdit = S.user?.role !== "viewer";
  const draw = async () => {
    let list = [];
    try { list = (await api("GET", "/triposr/models")).models || []; } catch (e) { el.querySelector(".m3-grid").innerHTML = `<p class="small muted">${esc(e.message)}</p>`; return; }
    el.querySelector(".m3-grid").innerHTML = list.length ? list.map((m) => `<div class="m3-card" data-id="${m.id}"><b title="${esc(m.name)}">🧊 ${esc(m.name)}</b><span class="small muted">${(m.size / 1048576).toFixed(1)} MB · ${new Date(m.created_at).toLocaleDateString("hi-IN")}</span>
      <div class="m3-btns"><button class="btn small" data-act="view">👁 देखें</button><a class="btn small quiet" href="${m.url}" download="${esc(m.name)}.glb">⬇</a>${canEdit ? `<button class="btn small quiet" data-act="ren" title="नाम बदलें">✏</button><button class="btn small danger" data-act="del">🗑 हटाएँ</button>` : ""}</div></div>`).join("")
      : `<p class="small muted">अभी कोई 3D model नहीं — «.glb import» से अपनी फ़ाइल डालें, या «फोटो से बनाएँ» से तस्वीर से बनाएँ।</p>`;
    el.querySelectorAll(".m3-card").forEach((card) => {
      const m = list.find((x) => x.id === card.dataset.id);
      card.querySelector('[data-act="view"]').onclick = () => viewModel(m);
      const ren = card.querySelector('[data-act="ren"]'); if (ren) ren.onclick = async () => { const n = prompt("नया नाम", m.name); if (!n || !n.trim()) return; try { await api("PATCH", `/library/${m.id}`, { name: n.trim() }); draw(); } catch (e) { toast(e.message); } };
      const del = card.querySelector('[data-act="del"]'); if (del) del.onclick = async () => { if (!confirm(`«${m.name}» हमेशा के लिए हटाएँ?`)) return; try { await api("DELETE", `/library/${m.id}`); toast("हटा दिया"); draw(); } catch (e) { toast(e.message); } };
    });
    opts.onChange?.(list);
  };
  el.innerHTML = `<div class="m3-head"><h2 style="margin:0;font-size:1.05rem">🧊 मेरे 3D models (.glb)</h2><span class="row" style="gap:.4rem">${canEdit ? `<label class="btn small" style="cursor:pointer">⬆ .glb import<input type="file" id="m3-file" accept=".glb,model/gltf-binary" hidden></label>` : ""}<a class="btn small quiet" href="#/image3d">🧊 फोटो से बनाएँ</a></span></div><div class="m3-grid"><p class="small muted">लोड हो रहा है…</p></div>`;
  const inp = el.querySelector("#m3-file");
  if (inp) inp.onchange = async () => {
    const f = inp.files[0]; inp.value = ""; if (!f) return;
    if (!/\.glb$/i.test(f.name)) return toast("सिर्फ़ .glb फ़ाइल");
    toast("import हो रहा है…");
    try {
      const fd = new FormData(); fd.append("file", f); fd.append("name", f.name.replace(/\.glb$/i, ""));
      const r = await fetch("/api/triposr/import", { method: "POST", headers: { authorization: "Bearer " + S.token }, body: fd });
      const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.error || r.statusText);
      toast("import हो गया ✓"); draw();
    } catch (e) { toast(e.message); }
  };
  await draw();
  return { refresh: draw };
}
