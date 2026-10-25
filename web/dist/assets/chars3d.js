// Vividora 3D Studio — procedural rigged characters, animation clips, lip-sync, environments.
// Everything is built from primitives at runtime (no model downloads): a real skeleton (17 bones) with a
// skinned body, a head with morph targets (8 visemes + 5 expressions), outfits/hair/props, 8 scenes.
// Used by the studio pages (chars3d.js UI below, scenes3d.js) and by the headless renderer (3d.html).
import * as THREE from "./three.module.min.js";

export { THREE };

// ---------------------------------------------------------------- catalogue
export const VISEMES = ["sil", "aa", "ee", "oh", "oo", "mm", "ff", "ss"];
export const EXPRESSIONS = ["smile", "sad", "angry", "surprised", "think"];
export const ANIMATIONS = ["idle", "walk", "run", "sit", "talk1", "talk2", "talk3", "wave", "point", "type", "nod", "laugh", "dance", "teach"];
export const HAIR = ["short", "bun", "long", "bald", "curly", "ponytail"];
export const SKIN = { fair: 0xf1c9a5, wheat: 0xd9a06f, tan: 0xb97a4a, brown: 0x8d5a34, dark: 0x5a3a22 };
export const OUTFITS = {
  tshirt: { label: "T-shirt + jeans", torso: 0x3b82f6, sleeves: 0x3b82f6, legs: 0x1e3a8a, shoes: 0x222222, extras: [] },
  kurta: { label: "Kurta", torso: 0xf5e6c8, sleeves: 0xf5e6c8, legs: 0xf5e6c8, shoes: 0x6b4423, extras: ["kurta"] },
  saree: { label: "Saree", torso: 0xc2185b, sleeves: 0xc2185b, legs: 0xc2185b, shoes: 0x6b4423, extras: ["saree"] },
  suit: { label: "Suit + tie", torso: 0x1f2937, sleeves: 0x1f2937, legs: 0x1f2937, shoes: 0x111111, extras: ["tie"] },
  shirt: { label: "Formal shirt", torso: 0xe5e7eb, sleeves: 0xe5e7eb, legs: 0x374151, shoes: 0x222222, extras: [] },
  doctor: { label: "Doctor coat", torso: 0x93c5fd, sleeves: 0xffffff, legs: 0x374151, shoes: 0x222222, extras: ["coat", "stethoscope"] },
  nurse: { label: "Nurse", torso: 0x60a5fa, sleeves: 0x60a5fa, legs: 0x60a5fa, shoes: 0xffffff, extras: ["cap"] },
  labcoat: { label: "Lab coat", torso: 0xffffff, sleeves: 0xffffff, legs: 0x374151, shoes: 0x222222, extras: ["coat"] },
  apron: { label: "Shop apron", torso: 0xf3f4f6, sleeves: 0xf3f4f6, legs: 0x1f2937, shoes: 0x222222, extras: ["apron"] },
  chef: { label: "Chef", torso: 0xffffff, sleeves: 0xffffff, legs: 0x222222, shoes: 0x222222, extras: ["apron", "chefhat"] },
  police: { label: "Police", torso: 0xa8894e, sleeves: 0xa8894e, legs: 0xa8894e, shoes: 0x111111, extras: ["policecap"] },
  helmet: { label: "Site helmet + vest", torso: 0xf97316, sleeves: 0x6b7280, legs: 0x374151, shoes: 0x111111, extras: ["helmet", "vest"] },
  delivery: { label: "Delivery", torso: 0xf59e0b, sleeves: 0xf59e0b, legs: 0x111111, shoes: 0x111111, extras: ["helmet", "bag"] },
  gym: { label: "Gym vest", torso: 0x111827, sleeves: null, legs: 0x374151, shoes: 0xef4444, extras: [] },
  salon: { label: "Salon", torso: 0x111111, sleeves: 0x111111, legs: 0x111111, shoes: 0x111111, extras: ["apron"] },
  turban: { label: "Punjabi (turban)", torso: 0x1d4ed8, sleeves: 0x1d4ed8, legs: 0xf5f5f4, shoes: 0x6b4423, extras: ["turban", "kurta"] },
  garba: { label: "Garba (chaniya choli)", torso: 0xdc2626, sleeves: 0xf59e0b, legs: 0x16a34a, shoes: 0x6b4423, extras: ["skirt", "dupatta"] },
  lohri: { label: "Lohri (phulkari)", torso: 0xea580c, sleeves: 0xfacc15, legs: 0x7c2d12, shoes: 0x6b4423, extras: ["dupatta"] },
  southindian: { label: "South Indian (veshti)", torso: 0xffffff, sleeves: 0xffffff, legs: 0xfef3c7, shoes: 0x6b4423, extras: ["angavastram"] },
  school: { label: "School uniform", torso: 0xffffff, sleeves: 0xffffff, legs: 0x1e3a8a, shoes: 0x111111, extras: ["tie"] },
  mechanic: { label: "Mechanic overalls", torso: 0x1e40af, sleeves: 0x1e40af, legs: 0x1e40af, shoes: 0x111111, extras: [] },
  driver: { label: "Driver", torso: 0xe5e7eb, sleeves: 0xe5e7eb, legs: 0x374151, shoes: 0x111111, extras: ["policecap"] },
};
export const PROPS = ["stethoscope", "phone", "laptop", "bag", "book", "mic", "pointer", "glasses", "hat"];
export const SCENES = ["classroom", "office", "clinic", "home", "shop", "gym", "park", "stage"];
export const LIGHTING = ["day", "evening", "night"];
export const CAMERAS = { wide: { pos: [0, 1.6, 5.2], target: [0, 1.0, 0], fov: 40 }, medium: { pos: [0, 1.45, 3.0], target: [0, 1.2, 0], fov: 38 },
  closeup: { pos: [0, 1.55, 1.3], target: [0, 1.5, 0], fov: 34 }, twoshot: { pos: [0, 1.5, 4.2], target: [0, 1.1, 0], fov: 42 },
  low: { pos: [0.8, 0.9, 3.6], target: [0, 1.1, 0], fov: 40 }, high: { pos: [-1.2, 2.6, 4.0], target: [0, 1.0, 0], fov: 40 } };

export const DEFAULT_SPEC = { height: 1.72, build: 1.0, age: "adult", gender: "m", skin: "wheat", hair: "short", hairColor: 0x1a1a1a,
  outfit: "tshirt", colors: {}, props: [], beard: false, expression: "smile", expressionAmount: 0.35 };

// ---------------------------------------------------------------- small geometry helpers
function capsule(r, len, seg = 10) { return new THREE.CapsuleGeometry(r, Math.max(0.001, len - 2 * r), 4, seg); }
function tf(geom, m) { geom.applyMatrix4(m); return geom; }
function mat(color, opts = {}) { return new THREE.MeshStandardMaterial({ color, roughness: 0.75, metalness: 0.02, ...opts }); }
function skinMat(color) { return new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.01, envMapIntensity: 0.6 }); }

/** Merge non-indexed geometries into one BufferGeometry with skinIndex/skinWeight + a material group per part. */
function mergeSkinned(parts) {
  const pos = [], nor = [], si = [], sw = [], groups = []; let start = 0;
  for (const p of parts) {
    const g = p.geom.index ? p.geom.toNonIndexed() : p.geom;
    const pa = g.getAttribute("position"), na = g.getAttribute("normal");
    const n = pa.count;
    for (let i = 0; i < n; i++) {
      pos.push(pa.getX(i), pa.getY(i), pa.getZ(i)); nor.push(na.getX(i), na.getY(i), na.getZ(i));
      const w = p.weight ? p.weight(pa.getX(i), pa.getY(i), pa.getZ(i)) : null;
      if (w) { si.push(w[0], w[1], 0, 0); sw.push(w[2], 1 - w[2], 0, 0); } else { si.push(p.bone, 0, 0, 0); sw.push(1, 0, 0, 0); }
    }
    groups.push({ start, count: n, materialIndex: p.mat }); start += n;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3));
  geo.setAttribute("skinIndex", new THREE.Uint16BufferAttribute(si, 4));
  geo.setAttribute("skinWeight", new THREE.Float32BufferAttribute(sw, 4));
  for (const g of groups) geo.addGroup(g.start, g.count, g.materialIndex);
  return geo;
}

// ---------------------------------------------------------------- the rig
export const BONES = ["Hips", "Spine", "Chest", "Neck", "Head", "ShoulderL", "UpperArmL", "LowerArmL", "HandL", "ShoulderR", "UpperArmR",
  "LowerArmR", "HandR", "UpperLegL", "LowerLegL", "FootL", "UpperLegR", "LowerLegR", "FootR"];

/** Build a character. Returns { group, bones, skeleton, body, head, mouth, eyes, mixer, setViseme, setExpression, blink, dims }. */
export function buildCharacter(input = {}) {
  const spec = { ...DEFAULT_SPEC, ...input, colors: { ...(input.colors || {}) } };
  const age = spec.age;                      // child | teen | adult | old
  const H = spec.height * (age === "child" ? 0.68 : age === "teen" ? 0.9 : 1);
  const B = spec.build;                      // 0.7 slim … 1.4 heavy
  const headR = age === "child" ? 0.13 : 0.11;
  const s = H / 1.72;                        // body unit scale
  const d = { hipY: 0.94 * s, spine: 0.12 * s, chest: 0.27 * s, neck: 0.2 * s, head: 0.09 * s, shoulderX: 0.19 * s * Math.sqrt(B),
    upperArm: 0.27 * s, lowerArm: 0.25 * s, hand: 0.09 * s, upperLeg: 0.42 * s, lowerLeg: 0.41 * s, foot: 0.2 * s,
    hipX: 0.1 * s, torsoR: 0.16 * s * Math.sqrt(B), armR: 0.045 * s * Math.sqrt(B), legR: 0.065 * s * Math.sqrt(B), headR: headR * s };
  // bones ---------------------------------------------------------
  const bone = (name, x, y, z, parent) => { const b = new THREE.Bone(); b.name = name; b.position.set(x, y, z); if (parent) parent.add(b); return b; };
  const Hips = bone("Hips", 0, d.hipY, 0, null);
  const Spine = bone("Spine", 0, d.spine, 0, Hips), Chest = bone("Chest", 0, d.chest, 0, Spine), Neck = bone("Neck", 0, d.neck, 0, Chest), Head = bone("Head", 0, d.head, 0, Neck);
  const ShL = bone("ShoulderL", -d.shoulderX, d.neck * 0.55, 0, Chest), UAL = bone("UpperArmL", -0.02 * s, 0, 0, ShL), LAL = bone("LowerArmL", 0, -d.upperArm, 0, UAL), HL = bone("HandL", 0, -d.lowerArm, 0, LAL);
  const ShR = bone("ShoulderR", d.shoulderX, d.neck * 0.55, 0, Chest), UAR = bone("UpperArmR", 0.02 * s, 0, 0, ShR), LAR = bone("LowerArmR", 0, -d.upperArm, 0, UAR), HR = bone("HandR", 0, -d.lowerArm, 0, LAR);
  const ULL = bone("UpperLegL", -d.hipX, -0.03 * s, 0, Hips), LLL = bone("LowerLegL", 0, -d.upperLeg, 0, ULL), FL = bone("FootL", 0, -d.lowerLeg, 0, LLL);
  const ULR = bone("UpperLegR", d.hipX, -0.03 * s, 0, Hips), LLR = bone("LowerLegR", 0, -d.upperLeg, 0, ULR), FR = bone("FootR", 0, -d.lowerLeg, 0, LLR);
  const list = [Hips, Spine, Chest, Neck, Head, ShL, UAL, LAL, HL, ShR, UAR, LAR, HR, ULL, LLL, FL, ULR, LLR, FR];
  const bones = Object.fromEntries(list.map((b) => [b.name, b]));
  const idx = Object.fromEntries(list.map((b, i) => [b.name, i]));
  if (age === "old") { Spine.rotation.x = 0.12; Neck.rotation.x = 0.1; }
  Hips.updateMatrixWorld(true);
  const skeleton = new THREE.Skeleton(list);
  // materials --------------------------------------------------------
  const skin = SKIN[spec.skin] ?? SKIN.wheat;
  const o = OUTFITS[spec.outfit] || OUTFITS.tshirt;
  const col = (k, def) => (spec.colors[k] != null ? spec.colors[k] : def);
  const mats = [skinMat(skin), mat(col("torso", o.torso), { roughness: 0.7 }), mat(o.sleeves == null ? skin : col("sleeves", o.sleeves), { roughness: 0.7 }), mat(col("legs", o.legs), { roughness: 0.75 }), mat(col("shoes", o.shoes), { roughness: 0.5, metalness: 0.1 })];
  const M = { skin: 0, torso: 1, sleeves: 2, legs: 3, shoes: 4 };
  // body parts (geometry in bone space → world bind space) -------------
  const parts = [];
  const along = (b, r, len, matIdx, extra = 0) => {  // a capsule hanging down the bone (0 … -len)
    const g = capsule(r, len + extra); g.translate(0, -len / 2 - r * 0.45, 0); parts.push({ geom: tf(g, b.matrixWorld), bone: idx[b.name], mat: matIdx });
  };
  const longTop = o.extras.includes("kurta") || o.extras.includes("coat");
  // torso: hips→chest, blended between Spine and Chest by height
  { const g = capsule(d.torsoR, d.spine + d.chest + d.neck * 0.9 + (longTop ? 0.18 * s : 0.04 * s)); g.scale(1, 1, 0.62);
    g.translate(0, (d.spine + d.chest) / 2 + (longTop ? -0.08 * s : 0), 0);
    const y0 = d.hipY + d.spine, y1 = d.hipY + d.spine + d.chest; const ib = idx.Spine, ic = idx.Chest;
    parts.push({ geom: tf(g, Hips.matrixWorld), bone: ib, mat: M.torso, weight: (x, y) => { const t = Math.min(1, Math.max(0, (y - y0) / (y1 - y0))); return [ic, ib, t]; } }); }
  // pelvis / shorts
  { const g = new THREE.SphereGeometry(d.torsoR * 0.95, 14, 10); g.scale(1.1, 0.75, 0.65); g.translate(0, -0.02 * s, 0); parts.push({ geom: tf(g, Hips.matrixWorld), bone: idx.Hips, mat: M.legs }); }
  along(UAL, d.armR, d.upperArm, M.sleeves, 0.02); along(UAR, d.armR, d.upperArm, M.sleeves, 0.02);
  along(LAL, d.armR * 0.85, d.lowerArm, M.skin, 0.02); along(LAR, d.armR * 0.85, d.lowerArm, M.skin, 0.02);
  { for (const b of [HL, HR]) { const g = new THREE.SphereGeometry(d.armR * 1.1, 10, 8); g.scale(0.8, 1.3, 0.5); g.translate(0, -d.hand * 0.6, 0); parts.push({ geom: tf(g, b.matrixWorld), bone: idx[b.name], mat: M.skin }); } }
  const skirt = o.extras.includes("saree") || o.extras.includes("skirt") || o.extras.includes("angavastram");
  along(ULL, d.legR, d.upperLeg, M.legs, 0.04); along(ULR, d.legR, d.upperLeg, M.legs, 0.04);
  along(LLL, d.legR * 0.85, d.lowerLeg, M.legs); along(LLR, d.legR * 0.85, d.lowerLeg, M.legs);
  { for (const b of [FL, FR]) { const g = new THREE.BoxGeometry(d.legR * 1.6, d.legR * 0.9, d.foot); g.translate(0, -d.legR * 0.2, d.foot * 0.3); parts.push({ geom: tf(g, b.matrixWorld), bone: idx[b.name], mat: M.shoes }); } }
  // neck
  { const g = capsule(d.torsoR * 0.32, d.neck + d.head); g.translate(0, (d.neck + d.head) / 2, 0); parts.push({ geom: tf(g, Neck.matrixWorld), bone: idx.Neck, mat: M.skin }); }
  if (skirt) { const g = new THREE.CylinderGeometry(d.torsoR * 1.05, d.torsoR * 2.3, d.upperLeg + d.lowerLeg * 0.9, 18, 1, true); g.translate(0, -(d.upperLeg + d.lowerLeg * 0.9) / 2 + 0.02 * s, 0);
    parts.push({ geom: tf(g, Hips.matrixWorld), bone: idx.Hips, mat: M.legs }); }
  const body = new THREE.SkinnedMesh(mergeSkinned(parts), mats);
  body.castShadow = true; body.frustumCulled = false;
  const group = new THREE.Group(); group.name = "character";
  group.add(Hips); body.add(Hips); // skeleton root under the mesh (three convention) — bones remain world-posed via Hips position
  body.bind(skeleton);
  group.add(body);
  // head with morph targets ---------------------------------------------
  const hg = new THREE.SphereGeometry(d.headR, 28, 22); hg.scale(0.92, 1.05, 0.95); hg.translate(0, d.headR * 0.85, 0);
  const base = hg.getAttribute("position"); const nv = base.count;
  const R = d.headR;
  const morphs = {};
  const disp = (fn) => { const a = new Float32Array(nv * 3); for (let i = 0; i < nv; i++) { const x = base.getX(i), y = base.getY(i) - R * 0.85, z = base.getZ(i); const dd = fn(x / R, y / R, z / R); a[i * 3] = base.getX(i) + dd[0] * R; a[i * 3 + 1] = base.getY(i) + dd[1] * R; a[i * 3 + 2] = base.getZ(i) + dd[2] * R; } return new THREE.Float32BufferAttribute(a, 3); };
  const front = (z) => Math.max(0, z);                                   // facing +z
  const mouthW = (x, y, z) => front(z) * Math.exp(-((x * x) / 0.12 + ((y + 0.45) ** 2) / 0.05));  // around the mouth
  const jaw = (x, y, z) => front(z) * (y < -0.25 ? Math.min(1, (-0.25 - y) / 0.4) : 0);
  morphs.sil = disp(() => [0, 0, 0]);
  morphs.aa = disp((x, y, z) => [0, -0.22 * jaw(x, y, z), 0.02 * mouthW(x, y, z)]);
  morphs.ee = disp((x, y, z) => [0.16 * Math.sign(x) * mouthW(x, y, z), -0.04 * jaw(x, y, z), 0]);
  morphs.oh = disp((x, y, z) => [-0.1 * Math.sign(x) * mouthW(x, y, z), -0.16 * jaw(x, y, z), 0.08 * mouthW(x, y, z)]);
  morphs.oo = disp((x, y, z) => [-0.14 * Math.sign(x) * mouthW(x, y, z), -0.05 * jaw(x, y, z), 0.14 * mouthW(x, y, z)]);
  morphs.mm = disp((x, y, z) => [0, 0, -0.04 * mouthW(x, y, z)]);
  morphs.ff = disp((x, y, z) => [0, -0.06 * jaw(x, y, z), -0.06 * mouthW(x, y, z) * (y < -0.45 ? 1 : 0.2)]);
  morphs.ss = disp((x, y, z) => [0.08 * Math.sign(x) * mouthW(x, y, z), -0.03 * jaw(x, y, z), 0]);
  const corner = (x, y, z) => front(z) * Math.exp(-(((Math.abs(x) - 0.42) ** 2) / 0.03 + ((y + 0.42) ** 2) / 0.03));
  const brow = (x, y, z) => front(z) * Math.exp(-((x * x) / 0.25 + ((y - 0.25) ** 2) / 0.02));
  const cheek = (x, y, z) => front(z) * Math.exp(-(((Math.abs(x) - 0.5) ** 2) / 0.05 + ((y + 0.05) ** 2) / 0.05));
  morphs.smile = disp((x, y, z) => [0.05 * Math.sign(x) * corner(x, y, z), 0.12 * corner(x, y, z) + 0.03 * cheek(x, y, z), 0.04 * cheek(x, y, z)]);
  morphs.sad = disp((x, y, z) => [0, -0.12 * corner(x, y, z) + 0.04 * brow(x, y, z) * (Math.abs(x) < 0.25 ? 1 : 0), 0]);
  morphs.angry = disp((x, y, z) => [0, -0.08 * brow(x, y, z), 0.03 * brow(x, y, z)]);
  morphs.surprised = disp((x, y, z) => [0, 0.08 * brow(x, y, z) - 0.22 * jaw(x, y, z), 0.06 * mouthW(x, y, z)]);
  morphs.think = disp((x, y, z) => [0, 0.1 * brow(x, y, z) * (x > 0 ? 1 : 0) - 0.02 * corner(x, y, z), 0]);
  hg.morphAttributes.position = [];
  const names = [...VISEMES, ...EXPRESSIONS];
  for (const n of names) hg.morphAttributes.position.push(morphs[n]);
  const headGeom = tf(hg, Head.matrixWorld);   // bind-space positions
  for (const a of headGeom.morphAttributes.position) a.applyMatrix4(Head.matrixWorld);
  // skin weights for the head: all Head bone
  { const n = headGeom.getAttribute("position").count; const si = new Uint16Array(n * 4), sw = new Float32Array(n * 4); for (let i = 0; i < n; i++) { si[i * 4] = idx.Head; sw[i * 4] = 1; }
    headGeom.setAttribute("skinIndex", new THREE.BufferAttribute(si, 4)); headGeom.setAttribute("skinWeight", new THREE.BufferAttribute(sw, 4)); }
  const head = new THREE.SkinnedMesh(headGeom, skinMat(skin)); head.frustumCulled = false; head.castShadow = true;
  head.morphTargetDictionary = Object.fromEntries(names.map((n, i) => [n, i]));
  head.morphTargetInfluences = new Array(names.length).fill(0);
  head.bind(skeleton); group.add(head);
  // face features (parented to the Head bone) --------------------------
  const face = new THREE.Group(); Head.add(face);
  const eyeY = R * 0.95, eyeZ = R * 0.78, eyeX = R * 0.34;
  const eyes = [];
  for (const sx of [-1, 1]) {
    const w = new THREE.Mesh(new THREE.SphereGeometry(R * 0.165, 12, 10), mat(0xffffff, { roughness: 0.3, emissive: 0xffffff, emissiveIntensity: 0.15 })); w.position.set(sx * eyeX, eyeY, eyeZ); w.scale.set(1, 1, 0.5); face.add(w);
    const p = new THREE.Mesh(new THREE.SphereGeometry(R * 0.085, 10, 8), mat(0x1b1b1b, { roughness: 0.1, metalness: 0.15 })); p.position.set(sx * eyeX, eyeY, eyeZ + R * 0.06); face.add(p);
    const br = new THREE.Mesh(new THREE.BoxGeometry(R * 0.32, R * 0.05, R * 0.06), mat(spec.hairColor)); br.position.set(sx * eyeX, eyeY + R * 0.22, eyeZ + R * 0.02); br.rotation.z = sx * -0.15; face.add(br);
    eyes.push({ white: w, pupil: p, brow: br, sx });
  }
  const nose = new THREE.Mesh(new THREE.ConeGeometry(R * 0.08, R * 0.22, 8), skinMat(skin)); nose.rotation.x = Math.PI / 2; nose.position.set(0, R * 0.78, R * 0.92); face.add(nose);
  for (const sx of [-1, 1]) { const e = new THREE.Mesh(new THREE.SphereGeometry(R * 0.11, 8, 8), skinMat(skin)); e.position.set(sx * R * 0.9, R * 0.85, 0); e.scale.set(0.5, 1, 0.7); face.add(e); }
  const mouth = new THREE.Mesh(new THREE.SphereGeometry(R * 0.16, 14, 10), mat(0x6b1a1a, { roughness: 0.3, emissive: 0x3a0808, emissiveIntensity: 0.15 })); mouth.position.set(0, R * 0.5, R * 0.86); mouth.scale.set(1.3, 0.25, 0.4); face.add(mouth);
  const lips = new THREE.Mesh(new THREE.TorusGeometry(R * 0.17, R * 0.035, 6, 16), mat(0xa0453c, { roughness: 0.45, metalness: 0.05 })); lips.position.copy(mouth.position); lips.scale.set(1.2, 0.5, 0.4); face.add(lips);
  if (spec.beard) { const bg = new THREE.SphereGeometry(R * 1.0, 16, 12, 0, Math.PI * 2, Math.PI * 0.5, Math.PI * 0.45); bg.scale(0.95, 1.0, 0.98); const bd = new THREE.Mesh(bg, mat(spec.hairColor)); bd.position.set(0, R * 0.88, 0); face.add(bd); }
  // hair ---------------------------------------------------------------
  const hm = mat(spec.hairColor, { roughness: 0.65, metalness: 0.08 });
  // hair caps leave the face free: the sphere segment covers the top/back, the front edge sits above the brows
  const cap = (phi = 0.42, sc = 1.05) => { const g = new THREE.SphereGeometry(R * sc, 20, 14, Math.PI * 0.75, Math.PI * 1.5, 0, Math.PI * phi); const g2 = new THREE.SphereGeometry(R * sc, 20, 14, Math.PI * 0.25, Math.PI * 0.5, 0, Math.PI * 0.3); const m = new THREE.Group(); m.add(new THREE.Mesh(g, hm), new THREE.Mesh(g2, hm)); m.position.set(0, R * 0.9, -R * 0.03); m.scale.set(0.96, 1.05, 0.98); return m; };
  const hairStyle = spec.hair;
  if (hairStyle === "short") face.add(cap(0.5));
  else if (hairStyle === "bun") { face.add(cap(0.55)); const b = new THREE.Mesh(new THREE.SphereGeometry(R * 0.4, 12, 10), hm); b.position.set(0, R * 1.6, -R * 0.75); face.add(b); }
  else if (hairStyle === "long") { face.add(cap(0.6)); const l = new THREE.Mesh(new THREE.BoxGeometry(R * 1.7, R * 2.2, R * 0.5), hm); l.position.set(0, R * 0.2, -R * 0.8); face.add(l); }
  else if (hairStyle === "curly") { face.add(cap(0.5, 1.08)); for (let i = 0; i < 14; i++) { const a = (i / 14) * Math.PI * 2; const c = new THREE.Mesh(new THREE.SphereGeometry(R * 0.28, 8, 6), hm); c.position.set(Math.cos(a) * R * 0.95, R * 1.35 + Math.sin(a * 2) * R * 0.15, Math.sin(a) * R * 0.95 - R * 0.05); face.add(c); } }
  else if (hairStyle === "ponytail") { face.add(cap(0.55)); const t = new THREE.Mesh(new THREE.CylinderGeometry(R * 0.18, R * 0.08, R * 1.6, 8), hm); t.position.set(0, R * 0.5, -R * 1.0); t.rotation.x = 0.35; face.add(t); }
  // headwear / extras ----------------------------------------------------
  const extras = new Set(o.extras);
  for (const p of spec.props || []) extras.add(p);
  const addHead = (m, y, z = 0) => { m.position.set(0, R * y, R * z); face.add(m); return m; };
  if (extras.has("turban")) { const t = new THREE.Mesh(new THREE.SphereGeometry(R * 1.22, 18, 12, 0, Math.PI * 2, 0, Math.PI * 0.5), mat(col("turban", 0xdc2626))); t.scale.set(1, 0.95, 1); addHead(t, 1.05, -0.05); const k = new THREE.Mesh(new THREE.SphereGeometry(R * 0.35, 10, 8), mat(col("turban", 0xdc2626))); k.position.set(R * 0.9, R * 1.75, 0); face.add(k); }
  if (extras.has("helmet")) { const h = new THREE.Mesh(new THREE.SphereGeometry(R * 1.2, 18, 12, 0, Math.PI * 2, 0, Math.PI * 0.55), mat(col("helmet", 0xfacc15), { roughness: 0.4 })); addHead(h, 0.9, 0); const brim = new THREE.Mesh(new THREE.CylinderGeometry(R * 1.3, R * 1.3, R * 0.08, 20), mat(col("helmet", 0xfacc15))); addHead(brim, 1.1, 0.1); }
  if (extras.has("chefhat")) { const c = new THREE.Mesh(new THREE.CylinderGeometry(R * 0.9, R * 0.8, R * 1.3, 16), mat(0xffffff)); addHead(c, 2.3, 0); const b = new THREE.Mesh(new THREE.SphereGeometry(R * 1.0, 14, 10), mat(0xffffff)); addHead(b, 3.0, 0); }
  if (extras.has("policecap") || extras.has("hat")) { const c = new THREE.Mesh(new THREE.CylinderGeometry(R * 1.0, R * 1.05, R * 0.45, 18), mat(extras.has("hat") ? 0x3f2a14 : 0x1f2a44)); addHead(c, 1.75, 0); const v = new THREE.Mesh(new THREE.BoxGeometry(R * 1.6, R * 0.08, R * 0.8), mat(0x111111)); addHead(v, 1.55, 1.0); }
  if (extras.has("cap")) { const c = new THREE.Mesh(new THREE.BoxGeometry(R * 1.3, R * 0.35, R * 1.0), mat(0xffffff)); addHead(c, 1.9, -0.1); }
  if (extras.has("glasses")) { for (const sx of [-1, 1]) { const r = new THREE.Mesh(new THREE.TorusGeometry(R * 0.2, R * 0.03, 6, 14), mat(0x222222)); r.position.set(sx * eyeX, eyeY, eyeZ + R * 0.1); face.add(r); } const br = new THREE.Mesh(new THREE.BoxGeometry(R * 0.3, R * 0.03, R * 0.03), mat(0x222222)); br.position.set(0, eyeY, eyeZ + R * 0.1); face.add(br); }
  // outfit extras on the body ---------------------------------------------
  const chestW = new THREE.Group(); Chest.add(chestW);
  if (extras.has("tie")) { const t = new THREE.Mesh(new THREE.BoxGeometry(d.torsoR * 0.3, d.chest * 1.5, 0.01), mat(col("tie", 0xb91c1c))); t.position.set(0, d.chest * 0.1, d.torsoR * 0.62); chestW.add(t); }
  if (extras.has("coat")) { const g = new THREE.CylinderGeometry(d.torsoR * 1.12, d.torsoR * 1.25, d.chest + d.spine + 0.3 * s, 20, 1, true, Math.PI * 0.12, Math.PI * 1.76); g.scale(1, 1, 0.68); const c = new THREE.Mesh(g, mat(0xffffff, { side: THREE.DoubleSide })); c.position.set(0, -0.12 * s, 0); chestW.add(c); }
  if (extras.has("vest")) { const g = new THREE.CylinderGeometry(d.torsoR * 1.1, d.torsoR * 1.12, d.chest * 1.4, 20, 1, true); g.scale(1, 1, 0.68); const v = new THREE.Mesh(g, mat(0xf97316, { side: THREE.DoubleSide, emissive: 0x7c2d12, emissiveIntensity: 0.2 })); v.position.set(0, 0, 0); chestW.add(v); const st = new THREE.Mesh(new THREE.BoxGeometry(d.torsoR * 2.3, 0.03, 0.01), mat(0xcbd5e1)); st.position.set(0, 0, d.torsoR * 0.7); chestW.add(st); }
  if (extras.has("apron")) { const a = new THREE.Mesh(new THREE.BoxGeometry(d.torsoR * 1.6, d.chest + d.spine + d.upperLeg * 0.7, 0.012), mat(col("apron", 0xf5f5f4))); a.position.set(0, -(d.upperLeg * 0.35), d.torsoR * 0.66); chestW.add(a); const strap = new THREE.Mesh(new THREE.BoxGeometry(d.torsoR * 0.4, d.chest * 0.8, 0.012), mat(col("apron", 0xf5f5f4))); strap.position.set(0, d.chest * 0.7, d.torsoR * 0.66); chestW.add(strap); }
  if (extras.has("saree") || extras.has("dupatta") || extras.has("angavastram")) {
    const cc = col("drape", extras.has("saree") ? 0xfacc15 : extras.has("angavastram") ? 0xdc2626 : 0xf59e0b);
    const g = new THREE.BoxGeometry(d.torsoR * 0.7, (d.chest + d.spine) * 1.9, 0.015); const dr = new THREE.Mesh(g, mat(cc, { side: THREE.DoubleSide }));
    dr.position.set(d.torsoR * 0.35, -d.spine, d.torsoR * 0.66); dr.rotation.z = -0.55; chestW.add(dr);
    if (extras.has("saree")) { const back = new THREE.Mesh(new THREE.BoxGeometry(d.torsoR * 0.8, (d.chest + d.spine) * 1.4, 0.015), mat(cc, { side: THREE.DoubleSide })); back.position.set(-d.torsoR * 0.5, -d.spine * 0.2, -d.torsoR * 0.6); back.rotation.z = 0.3; chestW.add(back); }
  }
  if (extras.has("stethoscope")) { const t = new THREE.Mesh(new THREE.TorusGeometry(d.torsoR * 0.75, 0.008, 6, 24, Math.PI * 1.2), mat(0x222222)); t.position.set(0, d.chest * 0.75, d.torsoR * 0.4); t.rotation.set(0.5, 0, Math.PI * 0.9); chestW.add(t); const disc = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.01, 12), mat(0x9ca3af, { metalness: 0.6, roughness: 0.3 })); disc.position.set(d.torsoR * 0.3, -d.chest * 0.3, d.torsoR * 0.68); disc.rotation.x = Math.PI / 2; chestW.add(disc); }
  if (extras.has("bag")) { const bgm = new THREE.Mesh(new THREE.BoxGeometry(0.22 * s, 0.2 * s, 0.1 * s), mat(col("bag", 0x7c2d12))); bgm.position.set(d.torsoR * 1.3, -d.spine, 0); Hips.add(bgm); }
  const inHand = (b, m, dz = 0) => { m.position.set(0, -d.hand * 0.9, 0.04 * s + dz); b.add(m); };
  if (extras.has("phone")) inHand(HR, new THREE.Mesh(new THREE.BoxGeometry(0.07 * s, 0.14 * s, 0.01), mat(0x111111, { roughness: 0.3 })));
  if (extras.has("book")) inHand(HL, new THREE.Mesh(new THREE.BoxGeometry(0.16 * s, 0.22 * s, 0.03), mat(0x1d4ed8)));
  if (extras.has("mic")) { const m = new THREE.Group(); const h = new THREE.Mesh(new THREE.CylinderGeometry(0.014, 0.018, 0.18 * s, 8), mat(0x111111)); const t = new THREE.Mesh(new THREE.SphereGeometry(0.035, 10, 8), mat(0x6b7280, { metalness: 0.5 })); t.position.y = 0.1 * s; m.add(h, t); m.rotation.x = -0.6; inHand(HR, m); }
  if (extras.has("pointer")) { const p = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.6 * s, 6), mat(0x4b5563)); p.rotation.x = -1.2; inHand(HR, p, 0.2 * s); }
  if (extras.has("laptop")) { const l = new THREE.Group(); const b1 = new THREE.Mesh(new THREE.BoxGeometry(0.32 * s, 0.015, 0.22 * s), mat(0x374151)); const b2 = new THREE.Mesh(new THREE.BoxGeometry(0.32 * s, 0.2 * s, 0.012), mat(0x111827)); b2.position.set(0, 0.1 * s, -0.11 * s); b2.rotation.x = -0.2; const scr = new THREE.Mesh(new THREE.PlaneGeometry(0.29 * s, 0.17 * s), mat(0x60a5fa, { emissive: 0x1d4ed8, emissiveIntensity: 0.5 })); scr.position.set(0, 0.1 * s, -0.103 * s); scr.rotation.x = -0.2; l.add(b1, b2, scr); l.position.set(0, -0.02 * s, 0.3 * s); Hips.add(l); }
  // mixer + helpers --------------------------------------------------------
  const mixer = new THREE.AnimationMixer(group);
  const state = { viseme: new Array(VISEMES.length).fill(0), expr: Object.fromEntries(EXPRESSIONS.map((e) => [e, 0])), blink: 0 };
  const applyFace = () => {
    const inf = head.morphTargetInfluences, dict = head.morphTargetDictionary;
    for (let i = 0; i < VISEMES.length; i++) inf[dict[VISEMES[i]]] = state.viseme[i];
    for (const e of EXPRESSIONS) inf[dict[e]] = state.expr[e];
    const open = state.viseme[1] * 1 + state.viseme[3] * 0.8 + state.viseme[2] * 0.25 + state.viseme[4] * 0.45 + state.expr.surprised * 0.9;
    const wide = 1 + state.viseme[2] * 0.6 + state.expr.smile * 0.35 - state.viseme[4] * 0.4 - state.viseme[3] * 0.2;
    mouth.scale.set(1.3 * wide, 0.25 + 1.6 * Math.min(1, open), 0.4 + 0.4 * open);
    lips.scale.set(1.2 * wide, 0.5 + 1.2 * Math.min(1, open), 0.4);
    lips.position.y = mouth.position.y - R * 0.05 * open;
    for (const e of eyes) {
      e.white.scale.y = Math.max(0.08, 1 - state.blink) * (1 + state.expr.surprised * 0.3);
      e.pupil.scale.y = Math.max(0.08, 1 - state.blink);
      e.brow.position.y = eyeY + R * 0.22 + R * (0.1 * state.expr.surprised + (e.sx > 0 ? 0.12 * state.expr.think : 0) - 0.08 * state.expr.angry - 0.03 * state.expr.sad);
      e.brow.rotation.z = e.sx * (-0.15 + 0.35 * state.expr.angry - 0.25 * state.expr.sad);
    }
  };
  const setViseme = (weights) => { for (let i = 0; i < VISEMES.length; i++) state.viseme[i] = weights[i] || 0; applyFace(); };
  const setExpression = (name, amount = 1) => { for (const e of EXPRESSIONS) state.expr[e] = e === name ? amount : 0; applyFace(); };
  const blink = (v) => { state.blink = v; applyFace(); };
  setExpression(spec.expression, spec.expressionAmount);
  return { group, bones, skeleton, body, head, mouth, eyes, mixer, setViseme, setExpression, blink, dims: d, spec, state };
}

// ---------------------------------------------------------------- animation clips (procedural keyframes)
const deg = (a) => (a * Math.PI) / 180;
const POSE_BONES = ["Spine", "Chest", "Neck", "Head", "UpperArmL", "LowerArmL", "HandL", "UpperArmR", "LowerArmR", "HandR", "UpperLegL", "LowerLegL", "FootL", "UpperLegR", "LowerLegR", "FootR"];
/** pose(t) → { Bone: [rx, ry, rz] in degrees, hips: [dx, dy, dz] } ; t in 0..1 of the loop */
const POSES = {
  idle: (t) => { const b = Math.sin(t * Math.PI * 2); return { Spine: [1.5 * b, 0, 0], Chest: [1.2 * b, 0, 0], Head: [-1 * b, 2 * Math.sin(t * Math.PI * 4), 0], UpperArmL: [3, 0, 7 + 1.5 * b], UpperArmR: [3, 0, -7 - 1.5 * b], LowerArmL: [-8, 0, 0], LowerArmR: [-8, 0, 0], hips: [0, 0.006 * b, 0] }; },
  walk: (t) => { const a = Math.sin(t * Math.PI * 2), c = Math.cos(t * Math.PI * 2); return { Spine: [3, 4 * a, 0], Chest: [2, -3 * a, 0], Head: [-2, 0, 0], UpperLegL: [35 * a, 0, 0], LowerLegL: [-Math.max(0, 40 * -c) - 5, 0, 0], FootL: [8 * a, 0, 0], UpperLegR: [-35 * a, 0, 0], LowerLegR: [-Math.max(0, 40 * c) - 5, 0, 0], FootR: [-8 * a, 0, 0], UpperArmL: [-28 * a, 0, 8], LowerArmL: [-25, 0, 0], UpperArmR: [28 * a, 0, -8], LowerArmR: [-25, 0, 0], hips: [0, 0.02 * Math.abs(Math.sin(t * Math.PI * 2 * 1)) , 0] }; },
  run: (t) => { const a = Math.sin(t * Math.PI * 2), c = Math.cos(t * Math.PI * 2); return { Spine: [12, 6 * a, 0], Chest: [6, -4 * a, 0], Head: [-6, 0, 0], UpperLegL: [55 * a, 0, 0], LowerLegL: [-Math.max(0, 80 * -c) - 10, 0, 0], FootL: [12 * a, 0, 0], UpperLegR: [-55 * a, 0, 0], LowerLegR: [-Math.max(0, 80 * c) - 10, 0, 0], FootR: [-12 * a, 0, 0], UpperArmL: [-50 * a, 0, 12], LowerArmL: [-85, 0, 0], UpperArmR: [50 * a, 0, -12], LowerArmR: [-85, 0, 0], hips: [0, 0.05 * Math.abs(a), 0] }; },
  sit: (t) => { const b = Math.sin(t * Math.PI * 2); return { Spine: [4 + b, 0, 0], Chest: [2, 0, 0], Head: [-3, 3 * b, 0], UpperLegL: [-85, -6, 0], LowerLegL: [85, 0, 0], FootL: [0, 0, 0], UpperLegR: [-85, 6, 0], LowerLegR: [85, 0, 0], FootR: [0, 0, 0], UpperArmL: [-25, 0, 10], LowerArmL: [-55 + 2 * b, 0, 0], UpperArmR: [-25, 0, -10], LowerArmR: [-55 - 2 * b, 0, 0], hips: [0, -0.42, 0.05] }; },
  talk1: (t) => { const a = Math.sin(t * Math.PI * 2), b = Math.sin(t * Math.PI * 4 + 1); return { Spine: [2, 2 * a, 0], Head: [-2 + 3 * b, 4 * a, 2 * a], UpperArmL: [-20 - 10 * a, 10, 25], LowerArmL: [-70 - 15 * b, 0, -20], HandL: [0, 0, 10 * b], UpperArmR: [-35 + 12 * a, -15, -30], LowerArmR: [-80 + 15 * a, 0, 25], HandR: [0, 0, -12 * a], hips: [0, 0.004 * a, 0] }; },
  talk2: (t) => { const a = Math.sin(t * Math.PI * 2), b = Math.cos(t * Math.PI * 2); return { Spine: [3, 0, 2 * a], Chest: [0, 3 * a, 0], Head: [-3, -5 * a, 0], UpperArmL: [-10, 0, 10], LowerArmL: [-30, 0, 0], UpperArmR: [-55 + 15 * b, -20 - 20 * a, -25], LowerArmR: [-60 - 25 * a, 0, 30], HandR: [20 * a, 0, -10], hips: [0, 0, 0] }; },
  talk3: (t) => { const a = Math.sin(t * Math.PI * 2); return { Spine: [2, 0, 0], Head: [-2, 6 * a, -2 * a], UpperArmL: [-40 - 10 * a, 15, 35], LowerArmL: [-85, 0, -30], HandL: [0, 0, 15 * a], UpperArmR: [-40 + 10 * a, -15, -35], LowerArmR: [-85, 0, 30], HandR: [0, 0, -15 * a], hips: [0, 0, 0] }; },
  wave: (t) => { const a = Math.sin(t * Math.PI * 4); return { Head: [-3, 4, 4 * a], Spine: [2, 0, 0], UpperArmL: [3, 0, 8], LowerArmL: [-10, 0, 0], UpperArmR: [-30, 0, -140], LowerArmR: [-95, 0, 15 * a], HandR: [0, 0, 25 * a], hips: [0, 0, 0] }; },
  point: (t) => { const a = Math.sin(t * Math.PI * 2); return { Spine: [3, -6, 0], Head: [-4, -12, 0], UpperArmL: [3, 0, 8], LowerArmL: [-10, 0, 0], UpperArmR: [-95 + 3 * a, -20, -15], LowerArmR: [-8, 0, 0], HandR: [0, 0, 0], hips: [0, 0, 0] }; },
  type: (t) => { const a = Math.sin(t * Math.PI * 8), b = Math.cos(t * Math.PI * 6); return { Spine: [12, 0, 0], Chest: [4, 0, 0], Head: [10, 2 * b, 0], UpperLegL: [-85, -6, 0], LowerLegL: [85, 0, 0], UpperLegR: [-85, 6, 0], LowerLegR: [85, 0, 0], UpperArmL: [-40, 15, 15], LowerArmL: [-75 + 4 * a, 0, -25], HandL: [10 * a, 0, 0], UpperArmR: [-40, -15, -15], LowerArmR: [-75 - 4 * b, 0, 25], HandR: [-10 * b, 0, 0], hips: [0, -0.42, 0.05] }; },
  nod: (t) => { const a = Math.sin(t * Math.PI * 4); return { Head: [-6 + 12 * a, 0, 0], Neck: [4 * a, 0, 0], Spine: [2, 0, 0], UpperArmL: [3, 0, 8], UpperArmR: [3, 0, -8], LowerArmL: [-10, 0, 0], LowerArmR: [-10, 0, 0], hips: [0, 0, 0] }; },
  laugh: (t) => { const a = Math.sin(t * Math.PI * 6), b = Math.sin(t * Math.PI * 2); return { Spine: [-6 + 4 * a, 0, 0], Chest: [-4 + 3 * a, 0, 0], Head: [-18 + 3 * a, 0, 4 * b], UpperArmL: [-25, 10, 20], LowerArmL: [-80, 0, -30], UpperArmR: [-25, -10, -20], LowerArmR: [-80, 0, 30], hips: [0, 0.01 * a, 0] }; },
  dance: (t) => { const a = Math.sin(t * Math.PI * 2), b = Math.cos(t * Math.PI * 2), c = Math.sin(t * Math.PI * 4); return { Spine: [4, 10 * a, 6 * b], Chest: [0, -8 * a, 0], Head: [-4, 10 * b, -6 * b], UpperArmL: [-60 - 30 * a, 20, 60 + 20 * c], LowerArmL: [-90, 0, -20 * a], UpperArmR: [-60 + 30 * a, -20, -60 - 20 * c], LowerArmR: [-90, 0, 20 * a], UpperLegL: [-10 + 10 * a, 0, 8], LowerLegL: [12, 0, 0], UpperLegR: [-10 - 10 * a, 0, -8], LowerLegR: [12, 0, 0], hips: [0.04 * a, 0.03 * Math.abs(c), 0] }; },
  teach: (t) => { const a = Math.sin(t * Math.PI * 2), b = Math.sin(t * Math.PI * 2 + 2); return { Spine: [2, 8 * a, 0], Head: [-3, 15 * a, 0], UpperArmL: [-15, 0, 12], LowerArmL: [-70, 0, -10], HandL: [0, 0, 5 * b], UpperArmR: [-70 + 10 * b, -35 - 25 * a, -20], LowerArmR: [-15, 0, 0], HandR: [0, 0, -10 * a], hips: [0, 0, 0] }; },
};
export const ANIM_DURATION = { idle: 3.2, walk: 1.1, run: 0.7, sit: 3.0, talk1: 2.4, talk2: 2.8, talk3: 2.2, wave: 1.4, point: 2.0, type: 1.6, nod: 1.2, laugh: 1.0, dance: 1.6, teach: 3.0 };
export const SEATED = new Set(["sit", "type"]);

/** Build an AnimationClip for a rig. Hips get a position track (bob / seat offset), the pose bones quaternion tracks. */
export function makeClip(name, rig, { fps = 12, travel = 0 } = {}) {
  const pose = POSES[name] || POSES.idle;
  const dur = ANIM_DURATION[name] || 2;
  const n = Math.max(2, Math.round(dur * fps)) + 1;
  const times = Array.from({ length: n }, (_, i) => (i / (n - 1)) * dur);
  const tracks = [];
  const q = new THREE.Quaternion(), e = new THREE.Euler();
  for (const b of POSE_BONES) {
    const vals = [];
    const base = rig.bones[b].rotation; // bind rotation (old age stoop etc.)
    for (let i = 0; i < n; i++) {
      const p = pose(i / (n - 1));
      const r = p[b] || [0, 0, 0];
      e.set(base.x + deg(r[0]), base.y + deg(r[1]), base.z + deg(r[2]));
      q.setFromEuler(e); vals.push(q.x, q.y, q.z, q.w);
    }
    tracks.push(new THREE.QuaternionKeyframeTrack(`${rig.bones[b].name}.quaternion`, times, vals));
  }
  const hp = rig.bones.Hips.position, pv = [];
  for (let i = 0; i < n; i++) { const p = pose(i / (n - 1)); const h = p.hips || [0, 0, 0]; pv.push(hp.x + h[0] * rig.dims.hipY, hp.y + h[1] * rig.dims.hipY, hp.z + h[2] * rig.dims.hipY + travel * times[i]); }
  tracks.push(new THREE.VectorKeyframeTrack("Hips.position", times, pv));
  return new THREE.AnimationClip(name, dur, tracks);
}

export function playAnimation(rig, name, { fade = 0.3, speed = 1 } = {}) {
  const clip = makeClip(name, rig);
  const action = rig.mixer.clipAction(clip);
  action.setLoop(THREE.LoopRepeat, Infinity); action.timeScale = speed;
  if (rig._action && rig._action !== action) { action.reset().play(); rig._action.crossFadeTo(action, fade, false); } else action.play();
  rig._action = action; rig._anim = name;
  return action;
}

// ---------------------------------------------------------------- lip-sync
// grapheme → viseme for Devanagari + Latin. Index into VISEMES.
const DEV_V = { "अ": 1, "आ": 1, "ा": 1, "इ": 2, "ई": 2, "ि": 2, "ी": 2, "उ": 4, "ऊ": 4, "ु": 4, "ू": 4, "ए": 2, "ऐ": 2, "े": 2, "ै": 2, "ओ": 3, "औ": 3, "ो": 3, "ौ": 3, "ऋ": 2, "ृ": 2, "ं": 5, "ँ": 5 };
const DEV_C = { "प": 5, "फ": 6, "ब": 5, "भ": 5, "म": 5, "व": 6, "स": 7, "श": 7, "ष": 7, "ज": 7, "च": 7, "छ": 7, "झ": 7, "त": 7, "थ": 7, "द": 7, "ध": 7, "न": 7, "ट": 1, "ठ": 1, "ड": 1, "ढ": 1, "ण": 1, "क": 1, "ख": 1, "ग": 1, "घ": 1, "ह": 1, "ल": 7, "र": 1, "य": 2 };
const LAT = { a: 1, e: 2, i: 2, o: 3, u: 4, y: 2, p: 5, b: 5, m: 5, f: 6, v: 6, w: 4, s: 7, z: 7, t: 7, d: 7, n: 7, l: 7, c: 7, j: 7, k: 1, g: 1, h: 1, r: 1, q: 1, x: 7 };
export function visemesForWord(w) {
  const out = [];
  for (const ch of w.toLowerCase()) { const v = DEV_V[ch] ?? DEV_C[ch] ?? LAT[ch]; if (v != null) out.push(v); }
  return out.length ? out : [1];
}
/** words: [{w, start, end}] → events [[t, visemeIndex, weight]] sampled every `step` seconds. */
export function visemeTrack(words, { step = 0.04, energy = null } = {}) {
  const ev = [];
  for (const wd of words) {
    const vs = visemesForWord(wd.w); const span = Math.max(0.05, wd.end - wd.start); const per = span / vs.length;
    vs.forEach((v, i) => { const t0 = wd.start + i * per; for (let t = t0; t < t0 + per; t += step) ev.push([+t.toFixed(3), v, 1]); });
  }
  if (energy) for (const e of ev) { const k = Math.min(energy.length - 1, Math.max(0, Math.round(e[0] / energy.step))); e[2] = 0.35 + 0.65 * (energy[k] ?? 0.5); }
  return ev;
}
/** Smooth viseme weights at time t from an event list (the previous event decays into the next). */
export function visemeAt(events, t, hold = 0.06) {
  const w = new Array(VISEMES.length).fill(0);
  let lo = 0, hi = events.length - 1, k = -1;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (events[m][0] <= t) { k = m; lo = m + 1; } else hi = m - 1; }
  if (k < 0) return w;
  const [t0, v, a] = events[k];
  const nxt = events[k + 1];
  const gap = nxt ? nxt[0] - t0 : hold;
  if (t - t0 > gap + hold) return w;                      // silence after the last event
  const f = Math.min(1, (t - t0) / Math.max(0.02, gap * 0.6));
  w[v] = a * (1 - f * 0.25);
  if (k > 0) { const [, pv, pa] = events[k - 1]; if (pv !== v) w[pv] = Math.max(w[pv], pa * (1 - f) * 0.6); }
  w[0] = 0;
  return w;
}

// ---------------------------------------------------------------- scenes
function box(w, h, dp, color, x, y, z, opts) { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, dp), mat(color, opts)); m.position.set(x, y, z); m.castShadow = m.receiveShadow = true; return m; }
function cyl(rt, rb, h, color, x, y, z, seg = 14) { const m = new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, seg), mat(color)); m.position.set(x, y, z); m.castShadow = true; return m; }
function tree(x, z, hgt = 2.2) { const g = new THREE.Group(); g.add(cyl(0.08, 0.12, hgt * 0.45, 0x6b4423, 0, hgt * 0.22, 0)); const c = new THREE.Mesh(new THREE.SphereGeometry(hgt * 0.35, 12, 10), mat(0x2f8f3a)); c.position.y = hgt * 0.7; c.castShadow = true; g.add(c); g.position.set(x, 0, z); return g; }
function desk(x, z, color = 0x8b5a2b) { const g = new THREE.Group(); g.add(box(1.2, 0.05, 0.6, color, 0, 0.74, 0)); for (const [dx, dz] of [[-0.55, -0.25], [0.55, -0.25], [-0.55, 0.25], [0.55, 0.25]]) g.add(box(0.05, 0.72, 0.05, 0x4a2e14, dx, 0.36, dz)); g.position.set(x, 0, z); return g; }
function chair(x, z, ry = 0, color = 0x374151) { const g = new THREE.Group(); g.add(box(0.46, 0.05, 0.46, color, 0, 0.45, 0)); g.add(box(0.46, 0.5, 0.05, color, 0, 0.72, -0.2)); for (const [dx, dz] of [[-0.2, -0.2], [0.2, -0.2], [-0.2, 0.2], [0.2, 0.2]]) g.add(box(0.04, 0.44, 0.04, 0x1f2937, dx, 0.22, dz)); g.position.set(x, 0, z); g.rotation.y = ry; return g; }
function shelf(x, z, cols = [0xef4444, 0x3b82f6, 0xf59e0b, 0x10b981]) { const g = new THREE.Group(); g.add(box(1.6, 2.0, 0.4, 0x9a7b4f, 0, 1.0, 0)); for (let r = 0; r < 4; r++) for (let c = 0; c < 5; c++) g.add(box(0.22, 0.3, 0.2, cols[(r + c) % cols.length], -0.6 + c * 0.3, 0.3 + r * 0.45, 0.12)); g.position.set(x, 0, z); return g; }

export function buildScene(name = "office", lighting = "day") {
  const scene = new THREE.Scene();
  const g = new THREE.Group(); scene.add(g);
  const floorCol = { classroom: 0xd6c7a8, office: 0x9ca3af, clinic: 0xe5f0f5, home: 0xb08968, shop: 0xd1d5db, gym: 0x374151, park: 0x4f9d43, stage: 0x2b2b2b }[name] ?? 0x9ca3af;
  const wallCol = { classroom: 0xf3e9c6, office: 0xe5e7eb, clinic: 0xffffff, home: 0xfde68a, shop: 0xfef3c7, gym: 0x1f2937, park: 0x9fd3ff, stage: 0x111111 }[name] ?? 0xe5e7eb;
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(30, 30), mat(floorCol, { roughness: 0.95 })); floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; g.add(floor);
  if (name !== "park") { const wall = box(16, 4.5, 0.1, wallCol, 0, 2.25, -3.2); wall.receiveShadow = true; g.add(wall); g.add(box(0.1, 4.5, 8, wallCol, -8, 2.25, 0.8)); g.add(box(0.1, 4.5, 8, wallCol, 8, 2.25, 0.8)); }
  const slots = [];  // where characters stand / sit: {pos:[x,z], ry, seated}
  if (name === "classroom") {
    g.add(box(4.2, 1.6, 0.06, 0x1f6b3a, 0, 1.9, -3.1)); g.add(box(4.4, 1.8, 0.04, 0x8b5a2b, 0, 1.9, -3.14)); g.add(box(4, 0.06, 0.12, 0x6b4423, 0, 1.05, -3.05));
    for (const [x, z] of [[-1.8, 0.4], [0, 0.4], [1.8, 0.4], [-1.8, 1.6], [0, 1.6], [1.8, 1.6]]) { g.add(desk(x, z)); g.add(chair(x, z + 0.55)); }
    g.add(desk(-2.6, -2.2, 0x6b4423)); g.add(box(0.5, 0.6, 0.35, 0xdddddd, -2.6, 1.06, -2.2));
    slots.push({ pos: [0.9, -2.3], ry: 0.2, seated: false }, { pos: [-1.8, 0.9], ry: 0, seated: true }, { pos: [0, 0.9], ry: 0, seated: true }, { pos: [1.8, 0.9], ry: 0, seated: true });
  } else if (name === "office") {
    g.add(desk(0, -1.4, 0xd1d5db)); g.add(box(0.5, 0.35, 0.03, 0x111827, 0, 1.0, -1.5)); g.add(box(0.46, 0.3, 0.01, 0x60a5fa, 0, 1.0, -1.48)); g.add(chair(0, -0.8, Math.PI, 0x111827));
    g.add(box(2.4, 1.6, 0.05, 0xbfdbfe, 3.5, 2.2, -3.15)); g.add(cyl(0.18, 0.14, 0.4, 0x8b5a2b, -3, 0.2, -2.4)); g.add(new THREE.Mesh(new THREE.SphereGeometry(0.45, 10, 8), mat(0x2f8f3a))).position.set(-3, 0.85, -2.4);
    g.add(shelf(5.5, -2.9, [0x1f2937, 0x9ca3af, 0x3b82f6, 0xe5e7eb]));
    slots.push({ pos: [0, -0.8], ry: Math.PI, seated: true }, { pos: [1.6, 0.4], ry: -0.3, seated: false }, { pos: [-1.6, 0.4], ry: 0.3, seated: false });
  } else if (name === "clinic") {
    g.add(box(2.0, 0.5, 0.9, 0xffffff, 2.4, 0.55, -1.6)); g.add(box(2.0, 0.08, 0.9, 0x93c5fd, 2.4, 0.84, -1.6)); g.add(box(0.1, 0.8, 0.9, 0x9ca3af, 3.4, 1.0, -1.6));
    g.add(box(1.2, 2.0, 0.4, 0xe5e7eb, -3.2, 1.0, -2.9)); g.add(box(0.5, 0.5, 0.05, 0xdc2626, -0.8, 2.6, -3.15)); g.add(box(0.14, 0.4, 0.06, 0xffffff, -0.8, 2.6, -3.1)); g.add(box(0.4, 0.14, 0.06, 0xffffff, -0.8, 2.6, -3.1));
    g.add(desk(-1.2, -1.6, 0xd1d5db)); g.add(chair(-1.2, -1.0, Math.PI, 0x1d4ed8)); g.add(chair(-1.2, -2.3, 0, 0x374151));
    slots.push({ pos: [-1.2, -1.0], ry: Math.PI, seated: true }, { pos: [-1.2, -2.3], ry: 0, seated: true }, { pos: [1.2, 0.2], ry: 0.2, seated: false });
  } else if (name === "home") {
    g.add(box(2.2, 0.5, 0.9, 0x7c3aed, 0, 0.3, -1.8)); g.add(box(2.2, 0.6, 0.25, 0x6d28d9, 0, 0.85, -2.2)); g.add(box(0.25, 0.5, 0.9, 0x6d28d9, -1.1, 0.55, -1.8)); g.add(box(0.25, 0.5, 0.9, 0x6d28d9, 1.1, 0.55, -1.8));
    g.add(box(1.0, 0.04, 0.6, 0x8b5a2b, 0, 0.4, -0.4)); for (const [dx, dz] of [[-0.45, -0.25], [0.45, -0.25], [-0.45, 0.25], [0.45, 0.25]]) g.add(box(0.04, 0.4, 0.04, 0x4a2e14, dx, 0.2, -0.4 + dz));
    g.add(cyl(0.02, 0.02, 1.4, 0x374151, 2.4, 0.7, -2.4)); g.add(cyl(0.22, 0.3, 0.3, 0xfde68a, 2.4, 1.5, -2.4)); g.add(box(1.6, 1.2, 0.05, 0xbfdbfe, -3.0, 2.2, -3.15)); g.add(box(1.8, 1.4, 0.08, 0x8b5a2b, -3.0, 2.2, -3.17));
    slots.push({ pos: [-0.5, -1.7], ry: 0, seated: true }, { pos: [0.5, -1.7], ry: 0, seated: true }, { pos: [2.6, 0.2], ry: -0.4, seated: false });
  } else if (name === "shop") {
    g.add(box(3.0, 0.9, 0.7, 0xa16207, 0, 0.45, -0.8)); g.add(box(3.1, 0.06, 0.8, 0xfde68a, 0, 0.93, -0.8));
    g.add(shelf(-2.6, -2.9)); g.add(shelf(0, -2.9, [0x10b981, 0xf59e0b, 0xef4444, 0x8b5cf6])); g.add(shelf(2.6, -2.9, [0x3b82f6, 0xfde047, 0xf97316, 0x14b8a6]));
    g.add(box(2.0, 0.5, 0.06, 0xdc2626, 0, 3.4, -3.1)); g.add(box(0.3, 0.3, 0.1, 0x111827, 0.9, 1.1, -0.8));
    slots.push({ pos: [0, -1.6], ry: 0, seated: false }, { pos: [-0.6, 0.6], ry: Math.PI, seated: false }, { pos: [0.9, 0.7], ry: Math.PI + 0.3, seated: false });
  } else if (name === "gym") {
    g.add(box(1.2, 2.2, 0.6, 0x111111, -3.0, 1.1, -2.6)); for (let i = 0; i < 4; i++) g.add(cyl(0.06, 0.06, 0.5, 0x9ca3af, -3.0, 0.3 + i * 0.5, -2.4, 10).rotateZ(Math.PI / 2));
    for (let i = 0; i < 3; i++) { const d = new THREE.Group(); d.add(cyl(0.015, 0.015, 0.3, 0x9ca3af, 0, 0, 0, 8).rotateZ(Math.PI / 2)); d.add(cyl(0.08, 0.08, 0.06, 0x111111, -0.14, 0, 0, 12).rotateZ(Math.PI / 2)); d.add(cyl(0.08, 0.08, 0.06, 0x111111, 0.14, 0, 0, 12).rotateZ(Math.PI / 2)); d.position.set(1.8 + i * 0.5, 0.08, -2.2); g.add(d); }
    g.add(box(1.8, 0.03, 0.7, 0x7c3aed, 1.2, 0.015, 0.6)); g.add(box(5, 2.0, 0.04, 0xcbd5e1, 0, 1.6, -3.15, { metalness: 0.4, roughness: 0.2 }));
    slots.push({ pos: [0, -0.6], ry: 0, seated: false }, { pos: [1.6, 0.8], ry: -0.4, seated: false }, { pos: [-1.6, 0.6], ry: 0.4, seated: false });
  } else if (name === "park") {
    floor.material.color.set(0x4f9d43); g.add(box(30, 0.02, 2.4, 0x3f3f46, 0, 0.011, -2.6)); for (let i = -14; i < 14; i += 2) g.add(box(0.9, 0.025, 0.12, 0xfde047, i, 0.02, -2.6));
    for (const [x, z] of [[-5, -4.5], [-2.5, -5.2], [3, -4.8], [6, -4.2], [-7, 2], [7, 2.5]]) g.add(tree(x, z, 2.2 + ((x * 7) % 3) * 0.3));
    g.add(box(1.4, 0.05, 0.4, 0x8b5a2b, 2.2, 0.45, 0.8)); g.add(box(1.4, 0.4, 0.05, 0x8b5a2b, 2.2, 0.72, 0.6)); g.add(box(0.05, 0.45, 0.4, 0x4a2e14, 1.55, 0.22, 0.8)); g.add(box(0.05, 0.45, 0.4, 0x4a2e14, 2.85, 0.22, 0.8));
    const sky = new THREE.Mesh(new THREE.SphereGeometry(40, 16, 10), new THREE.MeshBasicMaterial({ color: lighting === "night" ? 0x0b1026 : lighting === "evening" ? 0xf8b37a : 0x9fd3ff, side: THREE.BackSide })); scene.add(sky);
    slots.push({ pos: [-0.6, 0.4], ry: 0.2, seated: false }, { pos: [0.8, 0.5], ry: -0.2, seated: false }, { pos: [2.2, 0.8], ry: 0, seated: true });
  } else if (name === "stage") {
    g.add(box(8, 0.3, 4, 0x3f2a14, 0, 0.15, -0.5)); g.add(box(8, 3.2, 0.1, 0x7f1d1d, 0, 1.9, -2.6)); g.add(box(0.5, 1.1, 0.4, 0x1f2937, 0, 0.85, 0.6)); g.add(box(0.7, 0.05, 0.5, 0x374151, 0, 1.4, 0.6));
    for (const x of [-3, 0, 3]) { const sp = new THREE.SpotLight(0xffffff, lighting === "night" ? 60 : 25, 12, 0.5, 0.5, 1); sp.position.set(x, 4.2, 2.5); sp.target.position.set(x * 0.3, 1, -0.5); sp.castShadow = true; scene.add(sp, sp.target); g.add(cyl(0.12, 0.2, 0.3, 0x111111, x, 4.1, 2.5)); }
    slots.push({ pos: [0, 0.0], ry: 0, seated: false, lift: 0.3 }, { pos: [-2, -0.3], ry: 0.3, seated: false, lift: 0.3 }, { pos: [2, -0.3], ry: -0.3, seated: false, lift: 0.3 });
  }
  for (const s of slots) if (s.lift == null) s.lift = 0;
  if (name !== "park") { const r = new THREE.Mesh(new THREE.PlaneGeometry(16, 10), mat(0xf8fafc)); r.position.y = 4.5; r.rotation.x = Math.PI / 2; scene.add(r); }
  applyLighting(scene, lighting, name);
  scene.userData.slots = slots; scene.userData.name = name;
  return scene;
}

export function applyLighting(scene, lighting = "day", name = "") {
  const old = scene.children.filter((c) => c.isLight && !c.isSpotLight); for (const l of old) scene.remove(l);
  const cfg = { day: { sky: 0xdfefff, ground: 0x8a7a66, hemi: 1.1, sun: 0xfff2d8, sunI: 2.4, pos: [3, 6, 4], amb: 0.25 },
    evening: { sky: 0xffc38a, ground: 0x4a2e14, hemi: 0.8, sun: 0xff9a4a, sunI: 2.2, pos: [-5, 2.5, 3], amb: 0.2 },
    night: { sky: 0x1a2a55, ground: 0x0b0f1a, hemi: 0.5, sun: 0x9ab4ff, sunI: 0.9, pos: [2, 5, -2], amb: 0.15 } }[lighting] || {};
  const hemi = new THREE.HemisphereLight(cfg.sky, cfg.ground, cfg.hemi); scene.add(hemi);
  const sun = new THREE.DirectionalLight(cfg.sun, cfg.sunI); sun.position.set(...cfg.pos); sun.castShadow = true; sun.shadow.mapSize.set(1024, 1024);
  sun.shadow.camera.left = -6; sun.shadow.camera.right = 6; sun.shadow.camera.top = 6; sun.shadow.camera.bottom = -6; sun.shadow.camera.far = 30; sun.shadow.bias = -0.001; sun.shadow.normalBias = 0.02; scene.add(sun);
  const rim = new THREE.DirectionalLight(0xaaccff, 0.3); rim.position.set(-2, 3, -3); scene.add(rim);
  scene.add(new THREE.AmbientLight(0xffffff, cfg.amb));
  if (name === "stage" || name === "gym") { const fill = new THREE.PointLight(0xff8800, lighting === "night" ? 30 : 8, 10); fill.position.set(0, 3, 2); scene.add(fill); }
  scene.background = name === "park" ? null : new THREE.Color(lighting === "night" ? 0x0f172a : lighting === "evening" ? 0x3b2a1a : 0x1e2430);
}

/** Lights for a character-only (transparent) render. */
export function studioLights(scene) {
  scene.add(new THREE.HemisphereLight(0xffffff, 0x665544, 1.2));
  const key = new THREE.DirectionalLight(0xfff4e0, 2.2); key.position.set(2, 4, 3); key.castShadow = false; scene.add(key);
  const rim = new THREE.DirectionalLight(0x9ec5ff, 1.0); rim.position.set(-3, 3, -2); scene.add(rim);
}

export function makeCamera(preset = "medium", aspect = 1, over = {}) {
  const c = { ...(CAMERAS[preset] || CAMERAS.medium), ...over };
  const cam = new THREE.PerspectiveCamera(c.fov, aspect, 0.05, 100);
  cam.position.set(...c.pos); cam.lookAt(...c.target); cam.userData.target = new THREE.Vector3(...c.target);
  return cam;
}

/** Place a rig in a scene slot (or at pos/ry). */
export function placeRig(rig, { pos = [0, 0], ry = 0, lift = 0 } = {}) { rig.group.position.set(pos[0], lift, pos[1]); rig.group.rotation.y = ry; }

// ---------------------------------------------------------------- a complete "shot" (used by the renderer and the studio preview)
/** spec: { width, height, transparent, scene:{name,lighting}|null, camera:{preset,...}, characters:[{spec, animation, speed, slot|pos, ry, expression, expressionAmount, visemes, talk:[[s,e]], seated}] } */
export function buildShot(spec, canvas) {
  const W = spec.width || 1280, H = spec.height || 720;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: !!spec.transparent, preserveDrawingBuffer: true, premultipliedAlpha: false });
  renderer.setSize(W, H, false); renderer.setPixelRatio(1); renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.0;
  if (spec.transparent) renderer.setClearColor(0x000000, 0);
  let scene;
  if (spec.scene && spec.scene.name) scene = buildScene(spec.scene.name, spec.scene.lighting || "day");
  else { scene = new THREE.Scene(); studioLights(scene); if (!spec.transparent) scene.background = new THREE.Color(spec.background ?? 0x1e2430); }
  const slots = scene.userData.slots || [];
  const rigs = [];
  (spec.characters || []).forEach((c, i) => {
    const rig = buildCharacter(c.spec || c.profile || {});
    const slot = c.slot != null ? slots[c.slot % Math.max(1, slots.length)] : null;
    const seated = c.seated ?? (slot ? slot.seated : SEATED.has(c.animation));
    placeRig(rig, { pos: c.pos || (slot ? slot.pos : [i * 1.2 - ((spec.characters.length - 1) * 0.6), 0]), ry: c.ry ?? (slot ? slot.ry : 0), lift: slot ? slot.lift : 0 });
    const anim = c.animation || (seated ? "sit" : "idle");
    playAnimation(rig, anim, { speed: c.speed || 1 });
    rig.mixer.update(Math.random() * 2); // de-sync loops between characters
    if (c.expression) rig.setExpression(c.expression, c.expressionAmount ?? 0.6);
    rig._visemes = c.visemes || []; rig._talk = c.talk || []; rig._idleAnim = anim; rig._talkAnim = c.talkAnimation || ["talk1", "talk2", "talk3"][i % 3];
    rig._blinkNext = 1 + Math.random() * 3;
    scene.add(rig.group); rigs.push(rig);
  });
  const camera = makeCamera(spec.camera?.preset || (spec.characters?.length > 1 ? "twoshot" : "medium"), W / H, spec.camera || {});
  let tPrev = 0;
  const update = (t) => {
    const dt = Math.max(0, t - tPrev); tPrev = t;
    for (const rig of rigs) {
      const talking = rig._talk.some(([s, e]) => t >= s && t <= e);
      const want = talking ? rig._talkAnim : rig._idleAnim;
      if (rig._anim !== want && !(SEATED.has(rig._idleAnim) && talking)) playAnimation(rig, want, { fade: 0.4 });
      rig.mixer.update(dt);
      if (rig._visemes.length) rig.setViseme(visemeAt(rig._visemes, t));
      // blink
      if (t >= rig._blinkNext) { const ph = (t - rig._blinkNext) / 0.18; rig.blink(ph < 1 ? Math.sin(ph * Math.PI) : 0); if (ph >= 1) rig._blinkNext = t + 2 + Math.random() * 3.5; }
    }
    if (spec.camera?.orbit) { const a = (t / Math.max(1, spec.duration || 10)) * spec.camera.orbit; const tg = camera.userData.target; const r = Math.hypot(camera.position.x - tg.x, camera.position.z - tg.z); camera.position.x = tg.x + Math.sin(a) * r; camera.position.z = tg.z + Math.cos(a) * r; camera.lookAt(tg); }
    if (spec.camera?.push) { const tg = camera.userData.target; camera.position.lerp(new THREE.Vector3(tg.x, camera.position.y, tg.z), dt * 0.02 * spec.camera.push); camera.lookAt(tg); }
  };
  const render = () => renderer.render(scene, camera);
  return { renderer, scene, camera, rigs, update, render, W, H };
}
