// Timeline sound in the editor: while the preview plays, every audio item — background music,
// SFX / music clips on the A2+ lanes, the AI voice-over track and overlay clips that have their own
// sound — plays in sync with the playhead through one Web Audio graph, with the same volume, fade,
// duck, lane mute/solo/volume rules the render applies. Nothing here touches the render; it only
// makes the preview sound like the export will.
//
// Timeline items are timed on the OUTPUT timeline (cuts removed); the <video> runs on the source
// timeline — H.outOf() converts. Clips are plain <audio> elements (streamed, seekable) wired through
// a GainNode each, so a 5-minute song does not have to be decoded into memory first.
let E = null, H = null;          // editor state + helpers from editor.js
let ctx = null, master = null;   // AudioContext (created on the first play — autoplay policy)
let nodes = new Map();           // key → {el, gain, src, spec}
let specs = new Map();           // key → spec (what should exist)
let duckLevel = 1;               // smoothed duck factor for music

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

function lanes() { return (H.fx().track_audio && typeof H.fx().track_audio === "object") ? H.fx().track_audio : {}; }
// final gain of a lane after volume, mute and solo (solo on any lane mutes the others) — mirrors engine/effects.py track_gain
export function laneGain(lane) {
  const ta = lanes(); const solo = Object.entries(ta).filter(([, v]) => v && v.solo).map(([k]) => k);
  const cfg = ta[lane] || {};
  if (cfg.mute || (solo.length && !solo.includes(lane))) return 0;
  if (lane !== "audio" && (H.fx().hidden_tracks || []).includes(lane)) return 0;  // A2+ lanes: the 🔇 button
  const v = cfg.vol == null ? 1 : +cfg.vol; return Number.isFinite(v) ? clamp(v, 0, 2) : 1;
}

// what the timeline says should be heard: [{key, url, start, end (output s), trim, vol, fadeIn, fadeOut, loop, rate, lane, duck}]
function collect() {
  const fx = H.fx(); const out = new Map(); const dur = H.outDur();
  if (fx.music?.id) { const it = H.libItem(fx.music.id); if (it?.url) {
    const f = Math.min(+fx.music.fade || 0, dur / 3);
    out.set("music", { key: "music", url: it.url, start: 0, end: dur, trim: 0, vol: fx.music.volume ?? 0.18, fadeIn: f, fadeOut: f, loop: true, rate: 1, lane: "audio", duck: fx.music.duck !== false ? (fx.music.duck_amount ?? 0.6) : 0 }); } }
  for (const s of fx.sfx || []) { const it = H.libItem(s.id); if (!it?.url) continue;
    const len = s.dur || Math.min(it.meta?.duration || 0.6, 600);
    out.set("sfx:" + s._id, { key: "sfx:" + s._id, url: it.url, start: +s.at || 0, end: (+s.at || 0) + len, trim: +s.trim || 0, vol: s.volume ?? 0.8, fadeIn: +s.fade_in || 0, fadeOut: +s.fade_out || 0, loop: false, rate: 1, lane: `audio:${s.track || 0}`, duck: 0 }); }
  for (const b of fx.broll || []) { if (!(+b.volume > 0)) continue; const it = H.libItem(b.id); if (!it?.url || it.kind === "image") continue;
    out.set("broll:" + b._id, { key: "broll:" + b._id, url: it.url, start: +b.start, end: +b.end, trim: +b.trim_in || 0, vol: +b.volume, fadeIn: 0, fadeOut: 0, loop: false, rate: +b.speed > 0 ? +b.speed : 1, lane: `broll:${b.track || 0}`, duck: 0, overlay: true }); }
  const vt = fx.voice_track; if (vt && vt !== "original") { const a = (E.p.assets || []).find((x) => x.id === vt); if (a?.url)
    out.set("dub", { key: "dub", url: a.url, start: 0, end: dur, trim: 0, vol: 1, fadeIn: 0, fadeOut: 0, loop: false, rate: 1, lane: "audio", duck: 0 }); }
  return out;
}

function ensure(spec) {
  let n = nodes.get(spec.key);
  if (n && n.spec.url !== spec.url) { dispose(spec.key); n = null; }
  if (!n) {
    const el = new Audio(); el.preload = "auto"; el.crossOrigin = "anonymous"; el.src = spec.url; el.loop = !!spec.loop;
    const gain = ctx.createGain(); gain.gain.value = 0;
    const src = ctx.createMediaElementSource(el); src.connect(gain); gain.connect(master);
    n = { el, gain, src, spec }; nodes.set(spec.key, n);
  }
  n.spec = spec; n.el.loop = !!spec.loop; return n;
}
function dispose(key) { const n = nodes.get(key); if (!n) return; try { n.el.pause(); n.el.src = ""; n.src.disconnect(); n.gain.disconnect(); } catch (e) { /* gone */ } nodes.delete(key); }

/** The timeline changed (touch / renderTimeline): refresh the wanted clip list. Cheap when nothing changed. */
export function rebuild() {
  if (!E || !H) return;
  specs = collect();
  if (!ctx) return;
  for (const k of [...nodes.keys()]) if (!specs.has(k)) dispose(k);
  for (const s of specs.values()) ensure(s);
  applyVideo();
}

/** First play: build the graph (needs a user gesture for the AudioContext). */
export function start() {
  if (!E || !H) return;
  if (!ctx) { const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return; ctx = new AC(); master = ctx.createGain(); master.connect(ctx.destination); }
  if (ctx.state === "suspended") ctx.resume().catch(() => {});
  rebuild();
}

/** Pause everything (the video paused / the editor closed / a library preview started). */
export function stop() { for (const n of nodes.values()) if (!n.el.paused) n.el.pause(); }

// Is somebody speaking at source time t? From the waveform peaks the server stored at upload.
function speaking(t) {
  const fx = H.fx(); if (fx.voice_track && fx.voice_track !== "original") return true;  // the AI voice talks all along
  const peaks = E.p.meta?.peaks; if (!peaks?.length || !E.dur) return false;
  const i = clamp(Math.floor(t / E.dur * peaks.length), 0, peaks.length - 1);
  return Math.max(peaks[i], peaks[i + 1] || 0, peaks[i - 1] || 0) > 14;
}

/** The main <video>'s own volume: lane A1 × voice volume × (muted under an AI voice-over). */
export function applyVideo() {
  const v = H.video(); if (!v) return; const fx = H.fx();
  let g = laneGain("audio") * clamp(+(H.voiceVolume?.() ?? 1), 0, 2.5);
  const vt = fx.voice_track; if (vt && vt !== "original") g *= fx.voice_track_mode === "both" ? clamp(+(fx.voice_track_under ?? 0.25), 0, 1) : 0;
  v.volume = clamp(g, 0, 1); v.muted = g <= 0.001;
}

/** Called every animation frame while playing, and on every seek, with the source time t. */
export function tick(t) {
  if (!ctx || !E || !H) return;
  const v = H.video(); const playing = v && !v.paused; const out = H.outOf(t); const now = ctx.currentTime;
  const talk = speaking(t); duckLevel += ((talk ? 1 : 0) - duckLevel) * (talk ? 0.35 : 0.06);  // fast attack, slow release
  for (const n of nodes.values()) {
    const s = n.spec; const local = out - s.start; const len = s.end - s.start;
    const active = playing && local >= 0 && local < len;
    if (!active) { if (!n.el.paused) n.el.pause(); n.gain.gain.setTargetAtTime(0, now, 0.02); continue; }
    const want = s.trim + local * s.rate; const have = n.el.currentTime;
    const expect = s.loop && n.el.duration > 0 ? want % n.el.duration : want;
    if (n.el.paused || Math.abs(have - expect) > 0.3) { try { n.el.currentTime = expect; } catch (e) { /* not seekable yet */ } }
    n.el.playbackRate = clamp(s.rate * (v.playbackRate || 1), 0.25, 4);
    if (n.el.paused) n.el.play().catch(() => {});
    let g = s.vol * laneGain(s.lane);
    if (s.fadeIn > 0 && local < s.fadeIn) g *= local / s.fadeIn;
    if (s.fadeOut > 0 && len - local < s.fadeOut) g *= Math.max(0, (len - local) / s.fadeOut);
    if (s.duck > 0) g *= 1 - clamp(s.duck, 0, 1) * 0.85 * duckLevel;
    n.gain.gain.setTargetAtTime(clamp(g, 0, 2), now, 0.03);
  }
}

export function mount(e, helpers) { E = e; H = helpers; nodes = new Map(); specs = new Map(); duckLevel = 0; rebuild(); window.__vmix = debug; }
export function unmount() { stop(); for (const k of [...nodes.keys()]) dispose(k); if (ctx) { ctx.close().catch(() => {}); ctx = null; master = null; } E = H = null; }

/** For tests and the console: what is wired right now. */
export function debug() {
  return { context: ctx ? ctx.state : null, wanted: [...specs.keys()], sources: [...nodes.values()].map((n) => ({ key: n.spec.key, lane: n.spec.lane, playing: !n.el.paused, t: +n.el.currentTime.toFixed(2), gain: +n.gain.gain.value.toFixed(3), laneGain: laneGain(n.spec.lane) })) };
}
