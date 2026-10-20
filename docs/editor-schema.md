# Vividora editor ↔ render engine schema (pro features)

This is the contract between the editor UI (`web/dist/assets/editor.js`) and the render engine
(`server/vividora/engine/*`). Everything below is **optional and off by default**: a project
that does not use a field renders exactly as before, at the same cost.

* All settings live in the project's render settings: `project.settings.render`
  (PATCH `/api/projects/{id}` with `{"settings": {"render": {...}}}`, or the body of
  POST `/api/projects/{id}/render`). The usual shape is `render.effects.<field>`.
* Times are **seconds**. Unless said otherwise, item times (`start`, `end`, markers `t`) are on
  the **output timeline** (after cuts and speed ranges) — the same clock the editor timeline,
  titles, overlays and effect clips already use.
* **Keyframe times are relative to the owner**: an overlay clip's keyframe `t = 0` is the clip's
  `start`; an effect clip's `t = 0` is its `start`; the main-video transform uses the output
  timeline.
* Everything the UI needs to *list* (trending effects, mask shapes, blend modes, eases, tool
  params, ranges, defaults) comes from **`GET /api/presets` → `pro`** (also
  `GET /api/pro/catalog`). Do not hard-code lists in the UI.
* Render-time cost per feature is listed so the UI can warn ("slow") where it matters.
  "1×" = a plain render of the same length.

Contents

1. [Keyframes](#1-keyframes)
2. [Overlay clips (`effects.broll[]`) — pro compositing](#2-overlay-clips-effectsbroll--pro-compositing)
3. [Masks and crop](#3-masks-and-crop)
4. [Blend modes](#4-blend-modes)
5. [Speed, ramps, Speed Warp](#5-speed-ramps-speed-warp)
6. [Effect clips (`effects.fxclips[]`) and the 🔥 Trending pack](#6-effect-clips-effectsfxclips-and-the--trending-pack)
7. [Main video: transform keyframes](#7-main-video-transform-keyframes)
8. [Main video pro tools (`effects.pro`)](#8-main-video-pro-tools-effectspro)
9. [Colour (wheels, curves, HSL, colour match)](#9-colour-wheels-curves-hsl-colour-match)
10. [Morph cut (smooth jump cuts)](#10-morph-cut-smooth-jump-cuts)
11. [Music remix (`effects.music.fit`)](#11-music-remix-effectsmusicfit)
12. [Markers / chapters (`render.markers`)](#12-markers--chapters-rendermarkers)
13. [Text-based editing API](#13-text-based-editing-api)
14. [Scene detection API](#14-scene-detection-api)
15. [Catalogs in `/api/presets`](#15-catalogs-in-apipresets)
16. [Preview in the browser](#16-preview-in-the-browser)
17. [Cost table](#17-cost-table)

---

## 1. Keyframes

```jsonc
// one animatable parameter
[{"t": 0.0, "v": 0.2, "ease": "inout"}, {"t": 1.5, "v": 0.8, "ease": "linear"}, {"t": 3, "v": 0.8}]
```

| field | meaning |
|---|---|
| `t` | seconds from the owner's start (clip start / effect-clip start / output timeline for the main video) |
| `v` | value (units of the parameter) |
| `ease` | curve **from this keyframe to the next**: `linear` · `in` (cubic, slow start) · `out` (cubic, slow end) · `inout` (smoothstep) · `hold` (jump at the next keyframe) |

* Before the first keyframe the first value holds; after the last, the last value holds.
* A parameter can also be a plain number (constant).
* Max 120 keyframes per parameter; duplicates at the same `t` keep the last one.
* Eases list: `presets.pro.keyframe_eases`.
* Engine: `engine/keyframes.py` — per-frame expressions (`expr`), `sendcmd` scripts (opacity),
  or stepped chunks for arbitrary filter params (`stepped`, 1/8 s steps, max 64 chunks).

Where keyframes are accepted:

| owner | field | params |
|---|---|---|
| overlay clip | `kf` | `x`, `y`, `scale`, `rotation`, `opacity` |
| overlay clip | `mask.kf` | `x`, `y`, `w`, `h`, `rotation`, `feather`, `roundness` |
| overlay clip | `crop.kf` | `x`, `y`, `w`, `h` |
| overlay clip / global stack item | `stack[i].kf` | any numeric param of that catalog effect |
| effect clip | `kf` | any numeric param of the effect (`params` names) |
| main video | `effects.transform.kf` | `x`, `y`, `scale`, `rotation`, `opacity` |
| main video | `effects.pro.mask.kf` | as `mask.kf` |

---

## 2. Overlay clips (`effects.broll[]`) — pro compositing

Existing overlay items keep working unchanged. An item is rendered by the new compositor
(`engine/compose.py`) as soon as it uses **any** of: `trim_in > 0`, `trim_out`, `speed ≠ 1`,
`speed_ramp`, `speed_warp ≠ off`, `volume > 0`, `color`, `grade`, `grade_preset`, `stack`, `mask`,
`crop`, `blend_mode ≠ normal`, `kf`.

```jsonc
{
  // existing fields
  "id": "<library id>", "start": 4.0, "end": 9.0, "track": 1,
  "fit": "free",            // cover | contain (new) | pip | free
  "x": 0.5, "y": 0.5,       // free: centre, fraction of the frame
  "scale": 0.4,             // free: width as fraction of frame width
  "rotate": 0, "opacity": 1, "blend": "normal", "key_sim": 0.25,   // `blend` = keying (green/black/white…), unchanged
  "fade": true,             // cover: 0.25 s alpha fade in/out (default true)

  // NEW
  "trim_in": 2.5,           // seconds into the source clip
  "trim_out": 11.0,         // optional end in the source
  "speed": 1.0,             // 0.25 … 4 (constant)
  "speed_ramp": [ {"t": 0, "v": 0.5, "ease": "inout"}, {"t": 2, "v": 2.0} ],   // curve speed, t = SOURCE seconds after trim_in
  "speed_warp": "off",      // off | fast | balanced | best   (smooth slow motion when speed < 0.75)
  "volume": 0,              // 0 = muted (default, as before) … 2 — the clip's own sound, pitch kept (atempo)
  "color": { … },           // §9
  "grade_preset": "teal_orange", "grade": { "contrast": 0.1 },   // catalog grade (presets.catalog.grade_*)
  "stack": [ {"id": "vignette", "params": {"angle": 0.7}}, {"id": "blur", "params": {"sigma": 2}, "kf": {"sigma": [{"t":0,"v":0},{"t":2,"v":12}]}} ],
  "mask": { … },            // §3
  "crop": {"x": 0.1, "y": 0, "w": 0.8, "h": 1},   // §3
  "blend_mode": "screen",   // §4
  "kf": {                   // §1 — t relative to `start`
    "x": [{"t": 0, "v": 0.2}, {"t": 4, "v": 0.8, "ease": "out"}],
    "y": [...],
    "scale": [{"t": 0, "v": 1, "ease": "inout"}, {"t": 5, "v": 2}],    // MULTIPLIER of the base size (1 = as laid out)
    "rotation": [{"t": 0, "v": 0}, {"t": 5, "v": 90}],                  // degrees, clockwise
    "opacity": [{"t": 0, "v": 0}, {"t": 0.4, "v": 1}]                   // 0 … 1
  }
}
```

Geometry rules (pro path):

* The **base box** comes from `fit`: `cover` = fills the frame (cropped), `contain` = whole clip
  inside the frame, `pip` = the existing corner box (`pos`), `free` = `scale` × frame width,
  height from the clip's aspect.
* `kf.x` / `kf.y` move the **centre** (fractions of the frame; default = the base box centre).
* `kf.scale` multiplies the base box; `kf.rotation` rotates around the centre (the clip is never
  cut off by rotation).
* The legacy one-step move `to: {x, y, scale}` on `free` items is converted to keyframes.
* Order inside a clip: trim → speed → frame/fit → Speed Warp → keying (`blend`) → colour (§9) →
  grade → effect stack → mask × crop × alpha → opacity → fades → rotation → scale → position →
  blend mode.
* If the clip ends before `end`, it disappears (as before).
* When a Short / preview frame starts inside a pro clip, the engine advances `trim_in`, the speed
  ramp and all clip-relative keyframes so the visible part is unchanged (effect clips' `kf` too).
* The clip's own audio (when `volume > 0`) is mixed with the voice/music/SFX; it needs the main
  video to have a sound track (every normal project has one).

Duration helper: with a ramp the clip's natural length is
`Σ piece_len / speed` (see `compose.out_duration(item, source_seconds)`); a UI can compute it as
`∫ ds / v(s)` over the used source span, numerically (0.1 s steps, the engine does the same).

---

## 3. Masks and crop

```jsonc
"mask": {
  "shape": "circle",     // circle | ellipse | rect | heart | star | linear | mirror   (presets.pro.masks.shapes)
  "x": 0.5, "y": 0.5,    // centre, fraction of the LAYER (the clip box; the frame for the main video)
  "w": 0.6, "h": 0.6,    // size, fraction of layer width / height (circle uses w → radius = w/2 of the layer width)
  "rotation": 0,         // degrees. linear: the wipe edge direction (0 = vertical edge, left side visible); mirror: band angle
  "roundness": 0,        // rect: corner radius 0 … 1 (1 = pill)
  "points": 5, "inner": 0.4,   // star
  "feather": 0.02,       // soft edge, fraction of the layer's shorter side (0 … 0.5)
  "invert": false,
  "kf": {"w": [{"t": 0, "v": 0.2}, {"t": 1, "v": 0.6, "ease": "out"}]},
  "enabled": true
}
```

* `linear` = split/wipe: everything on one side of a line through (x, y) is visible.
  Animate `x` (or `rotation`) for a wipe.
* `mirror` = a band of height `h` through (x, y), rotated by `rotation`.
* Main video mask: `effects.pro.mask` with the same fields **plus** `"bg": "black" | "blur" | "#rrggbb"`
  (what shows outside the mask).
* Crop (overlay clips): `"crop": {"x": 0.1, "y": 0.0, "w": 0.8, "h": 1.0, "kf": {"x": [...]}}` —
  top-left based fractions of the clip; animated crop is drawn as a hard rectangular mask.
  (The main video keeps its existing `transform.crop`.)
* Engine: `engine/masks.py`; a still mask is one PNG, an animated mask a small lossless grey video
  (≤ 640 px, scaled up). Masks multiply with the clip's own alpha (PNG stickers, green screen).

---

## 4. Blend modes

`blend_mode` on an overlay clip: `normal` · `screen` · `multiply` · `overlay` · `softlight` ·
`hardlight` · `add` · `subtract` · `lighten` · `darken` · `difference` · `exclusion` ·
`colordodge` · `colorburn` (list + labels: `presets.pro.blend_modes`).

* Computed in RGB (gbrp) on the clip's time range only; the clip's alpha × opacity mixes the
  blended result over the picture, so masks / opacity / keyframes all work with every mode.
* `overlay` / `hardlight` follow the Photoshop/CapCut definitions (base = the picture under the clip).
* `subtract` = picture − clip.
* Not the same as the old `blend` field (keying: `screen` lumakey, green/blue/black/white) — both can be used together.
* CSS preview: `mix-blend-mode` has the same names (`soft-light`, `hard-light`, `color-dodge`,
  `color-burn`; `add` ≈ `plus-lighter`; `subtract` has no CSS equivalent).

---

## 5. Speed, ramps, Speed Warp

Overlay clips: `speed`, `speed_ramp`, `speed_warp` (see §2).

* `speed_ramp` keyframes are on the **source** clock (seconds after `trim_in`), `v` = speed
  0.25 … 4. Presets like CapCut's "Montage / Hero / Bullet" are just keyframe lists the UI can offer.
* Audio follows the same speed piece-wise with `atempo` (pitch preserved, ≤ 24 pieces).
* `speed_warp` (only acts where speed < 0.75):
  * `fast` — frame blending (+5 %)
  * `balanced` — motion-compensated interpolation at ½ resolution (~1–2 fps of slowed footage)
  * `best` — full-resolution optical flow (`minterpolate mci aobmc vsbmc`, ~0.3–1 fps) — use for short clips

Main video: speed ranges stay in `edl.speed` (`[{start, end, rate}]`, source time) as before;
Speed Warp for them is `effects.pro.speed_warp` (same values).

---

## 6. Effect clips (`effects.fxclips[]`) and the 🔥 Trending pack

Unchanged shape, two additions:

```jsonc
{"kind": "effect", "id": "tr_glitch", "params": {"amount": 0.7, "rate": 5}, "start": 3.0, "end": 4.2, "track": 0,
 "kf": {"amount": [{"t": 0, "v": 0.2}, {"t": 1.2, "v": 1}]}}      // NEW: animate any numeric param
```

* Inside an effect clip time runs 0 … `end − start`, and every trending effect animates over that
  length (`DUR`) — e.g. a film burn swells and fades across the clip, letterbox bars slide in and
  out, the 3D zoom pushes in for the clip's duration.
* `kf` on params is stepped every 1/8 s (max 64 steps per clip).
* The same effects can go in `effects.stack` (whole video, DUR = video length) or an overlay
  clip's `stack`.

Trending effects (`presets.pro.trending`, also in `presets.catalog.effects` with `cat: "trending"`).
Every entry: `id`, `label` (Hindi · English), `params` (name, label, min, max, default, step;
`type: "color"` for colours), `cost` (1 cheap … 3 heavy), `anim: "duration"`, `tags`, `preview`/`css`.

| id | what | key params | cost |
|---|---|---|---|
| `tr_beat_shake` | shake hits on every beat | bpm, amount %, decay | 1 |
| `tr_camera_shake` | smooth hand-held shake (+ tilt) | amount %, speed, rotate ° | 1 |
| `tr_glitch` | slice displacement + RGB tear + noise + smear (datamosh look) | amount, rate | 2 |
| `tr_rgb_split` | true per-channel RGB split, waving | amount px, speed Hz | 2 |
| `tr_chroma_pulse` | chromatic split + zoom bump on the beat | amount px, bpm, zoom | 2 |
| `tr_zoom_blur` | radial zoom blur (burst = peaks mid-clip) | amount, burst 0/1 | 2 |
| `tr_radial_blur` | spin blur | angle °, burst | 2 |
| `tr_motion_blur` | frame-blend motion blur | frames | 1 |
| `tr_light_leak` | moving generated light leak (screen) | amount, speed, pattern | 2 |
| `tr_film_burn` | burn flare that swells and fades over the clip | amount, speed, pattern | 2 |
| `tr_vhs` | chroma bleed, noise, scanlines, rolling tracking bar | amount | 2 |
| `tr_old_film` | sepia, grain, flicker, scratches, gate weave | amount | 1 |
| `tr_freeze` | freeze the first frame of the clip (+ zoom-in, flash) | zoom, flash | 1 |
| `tr_flash` | white flash in + optional strobe | amount, rate Hz, decay | 1 |
| `tr_zoom_3d` | push-in with sharp centre / slower blurred edges (parallax look) | amount | 2 |
| `tr_spotlight` | moving spotlight vignette | size, move, speed | 1 |
| `tr_duotone` | two-colour gradient map | shadow, highlight (colours), contrast | 1 |
| `tr_lens_flare` | generated anamorphic flare travelling across | amount, from X, to X, Y, colour | 2 |
| `tr_pixelate` | pixel reveal / dissolve / static | size, mode (0 reveal, 1 dissolve, 2 static) | 1 |
| `tr_kaleido` | 4-way mirror, drifting (+ spin) | speed, spin | 2 |
| `tr_bw_pop` | B&W with one colour kept (+ ramp from colour) | colour, similarity, ramp s | 1 |
| `tr_slow_shutter` | ghost trails | frames, trail | 1 |
| `tr_neon` | edge glow with cycling hue | glow, hue speed, dim | 3 |
| `tr_retro_tv` | CRT bulge, scanlines, flicker | amount | 2 |
| `tr_letterbox` | cinematic bars slide in (and out) | bar %, anim s, out 0/1 | 1 |

All are plain ffmpeg filters (no stock footage); each was rendered on 9:16 (1080×1920) and
16:9 (1920×1080) in `server/tests/test_pro_render.py`.

---

## 7. Main video: transform keyframes

```jsonc
"transform": {
  "crop": {"x": 0, "y": 0, "w": 1, "h": 1}, "rotate": 0, "flip_h": false, "angle": 0,   // unchanged
  "scale": 1, "x": 0, "y": 0, "bg": "blur", "bg_color": "#000000",                       // unchanged
  "kf": {                                       // NEW — output timeline
    "x": [{"t": 0, "v": 0}, {"t": 6, "v": 0.2}],          // OFFSET as a fraction of the frame (like transform.x), 0 = centred
    "y": [...],
    "scale": [{"t": 0, "v": 1}, {"t": 3, "v": 1.3, "ease": "inout"}],   // 1 = full frame (absolute, like transform.scale)
    "rotation": [{"t": 0, "v": 0}, {"t": 6, "v": 10}],    // degrees
    "opacity": [{"t": 0, "v": 1}, {"t": 6, "v": 0}]       // fades the picture over `bg`
  }
}
```

Note the main video's `x`/`y` are **offsets** (as the existing transform), while overlay clips
use **centres**. When `kf` has no real animation the old static transform is used.

---

## 8. Main video pro tools (`effects.pro`)

`DEFAULT_EFFECTS.pro = {}`; defaults for the UI: `presets.pro.defaults`; params/labels/costs:
`presets.pro.tools`; whether real vidstab is available: `presets.pro.capabilities.stabilize`
(`"vidstab"` | `"deshake"` | `"none"`).

```jsonc
"pro": {
  "stabilize":   {"enabled": true, "strength": 0.5, "zoom": 0},            // zoom % (0 = automatic crop-zoom)
  "denoise":     {"enabled": true, "method": "hqdn3d", "strength": 0.4},   // hqdn3d (fast) | nlmeans (slow, best)
  "sharpen":     {"enabled": true, "method": "cas", "amount": 0.4},        // cas | unsharp
  "face_refine": {"enabled": true, "strength": 0.5, "brighten": 0.3, "eyes": 0.3},
  "speed_warp":  "balanced",                                                // for edl.speed ranges < 0.75×
  "color":       { … },                                                     // §9
  "morph_cut":   {"enabled": true, "all": false, "frames": 8, "mode": "flow"},   // §10
  "mask":        { …, "bg": "blur" }                                        // §3
}
```

* **Stabilise**: two-pass `vidstabdetect`/`vidstabtransform` when the ffmpeg build has it
  (Debian/Ubuntu builds do), else single-pass `deshake` + a small crop-zoom. Runs on the source
  before the cuts (frame order matters). Skipped for the 1-frame preview (`/frame`).
* **Denoise** runs right after framing (before zoom/look/grade); **sharpen** after the grade/stack.
* **Face refine**: finds the face (OpenCV Haar when available, otherwise a skin-colour finder)
  every 0.5 s, builds a soft face-ellipse mask, multiplies it by a skin-colour mask (so eyes,
  brows, lips, teeth, hair stay sharp), smooths only that with an edge-preserving bilateral filter,
  brightens a touch, and adds local contrast to the non-skin parts of the face (eye pop).
  `strength` 0.5 is natural; 1.0 is strong. If no face is found it does nothing
  (`render meta.pro` notes `face_refine:no-face`).
* The render result's `files[0].meta.pro` lists what ran, e.g. `["stabilize:vidstab", "face_refine"]`.

---

## 9. Colour (wheels, curves, HSL, colour match)

Same object on the main video (`effects.pro.color`) and on overlay clips (`color`):

```jsonc
"color": {
  "wheels": {                                   // each -1 … 1; y = master (all channels)
    "lift":   {"r": 0, "g": 0, "b": 0.05, "y": 0},
    "gamma":  {"r": 0, "g": 0, "b": 0, "y": 0.1},     // + = brighter mid-tones
    "gain":   {"r": 0.1, "g": 0, "b": 0, "y": 0},
    "offset": {"r": 0, "g": 0, "b": 0, "y": 0}
  },
  "curves": {                                   // points [x, y] in 0 … 1, monotone cubic
    "master": [[0, 0], [0.25, 0.2], [0.75, 0.82], [1, 1]],
    "r": [[0, 0], [0.5, 0.55], [1, 1]], "g": [...], "b": [...]
  },
  "hsl": [                                      // secondaries, up to 8
    {"hue": 210, "range": 60, "softness": 20, "sat": -0.6, "lum": 0.0, "hue_shift": 0}
  ],
  "match": {"src": {"mean": [L,a,b], "std": [L,a,b]}, "ref": {...}, "amount": 1.0},   // from the API below
  "amount": 1.0                                 // overall mix 0 … 1
}
```

* `hsl.hue` = centre hue in degrees (0 red, 30 orange/skin, 60 yellow, 120 green, 210 blue, 300 magenta);
  `range` = full width in degrees; `softness` = fall-off in degrees; `sat` / `lum` −1 … 1; `hue_shift` ±180°.
  Near-grey pixels are never touched.
* Order: match → wheels → curves → HSL → `amount`. Baked into one 33³ LUT per clip (`lut3d`), so
  the whole colour block costs one cheap filter. Wheels/curves neutral = no filter.

**Colour match API** — POST `/api/projects/{id}/color/match`

```jsonc
// request
{"clip": {"kind": "library", "id": "<lib id>", "t": 2.0},     // the clip to correct ("kind": "project" = the recording)
 "ref":  {"kind": "project", "t": 31.5},                       // the look to copy (another clip or a frame of the recording)
 "amount": 1.0, "keep_luma": false}
// response
{"color": {"match": {"src": {...}, "ref": {...}, "amount": 1.0}}, "hint": "…"}
```

Put the returned `match` into that clip's `color.match` (or `effects.pro.color.match`).

---

## 10. Morph cut (smooth jump cuts)

* Global: `effects.pro.morph_cut = {"enabled": true, "all": true, "frames": 8, "mode": "flow"}`.
* Per cut: on an EDL cut `{"id": "c3", "start": …, "end": …, "morph": true}`. A cut with
  `morph: true` is morphed even when `all` is false (or `morph_cut` is not enabled — `frames` /
  `mode` still come from `morph_cut` when present); `morph: false` excludes a cut from `all`.
* `frames` (4 … 16, even) = total frames replaced around the cut (half each side);
  `mode`: `flow` = optical-flow morph (minterpolate mci) from the last good frame before to the
  first good frame after the cut, `blend` = cross-dissolve of those two frames.
* Audio and duration are unchanged (the morph replaces frames, it does not overlap the clips).
  Works best for talking heads where the head moves a little between takes. Cuts that use an
  `x_…` (xfade) transition are skipped.

---

## 11. Music remix (`effects.music.fit`)

```jsonc
"music": {"id": "<library music>", "volume": 0.18, "duck": true, "fit": true}
```

With `fit: true` the song is re-cut at bar starts so it **ends like the song ends** exactly at the
video's length (longer song: intro + jump + real ending; shorter: a middle phrase is looped),
joined with short equal-power crossfades; the last error is absorbed by a ≤ ±4 % tempo change
(pitch kept). Plan preview:

POST `/api/projects/{id}/music/fit` `{"music_id": "<lib id>", "target": 47.5}` (`target` omitted =
current output length) →

```jsonc
{"plan": {"bpm": 117.5, "duration": 182.3, "target": 47.5, "pieces": [[0, 21.4], [150.2, 182.3]],
          "crossfade": 0.12, "tempo": 1.0081, "length": 47.88, "output_length": 47.5, "end_trim": null}}
```

Cost: one beat analysis (~1–2 s per song minute) + one audio pass, cached per render.

---

## 12. Markers / chapters (`render.markers`)

```jsonc
"markers": [
  {"id": "m1", "t": 0,   "label": "शुरुआत",  "kind": "chapter", "color": "#F2B33D"},
  {"id": "m2", "t": 95,  "label": "Setup",   "kind": "chapter"},
  {"id": "m3", "t": 140, "label": "fix audio", "kind": "todo"}
]
```

* `t` on the output timeline. `kind`: `chapter` | `note` | `todo` (`presets.pro.markers`).
* No effect on the picture. When there are `chapter` markers, YouTube chapters in the
  description come from them (`engine/metadata.chapters`) instead of the automatic ones; YouTube
  rules are enforced (first at 00:00 — an "Intro" is added if needed —, ≥ 3 chapters, ≥ 10 s apart).
* Scene detection (§14) returns ready-made `note` markers.

---

## 13. Text-based editing API

GET `/api/projects/{id}/textcut` →
`{"words": [{"i": 0, "w": "नमस्ते", "start": 0.2, "end": 0.6, "removed": false}, …]}`
(`i` = index the other calls use; `start`/`end` are source seconds; `removed` = mostly cut away → strike through).

POST `/api/projects/{id}/textcut`

```jsonc
{
  "delete": [12, 13, 14, [31.2, 33.0]],   // word indexes and/or [start, end] source ranges
  "restore": [40],                        // bring words back (cuts over them are trimmed / switched off)
  "keep_text": "…",                       // alternative: the full text to keep; words not in it are deleted
  "fillers": true,                        // remove every filler word (अं, उम, um, uh, …)
  "silences_over": 0.8,                   // remove pauses between words longer than this (s); also leading/trailing silence
  "keep_pause": 0.12,                     // breathing room left on each side of a removed gap (default 0.12)
  "dry_run": false,                       // true = only return the result
  "note": "text edit"                     // history label
}
```

Response: `{"edl": {…full new EDL…}, "added": 4, "changed": 1, "removed_words": [3, 12, 13, 14]}`.

* New cuts carry `"source": "text"`, `id` `t1`, `t2` … and `reason` `text` | `filler` | `silence`.
* Existing cuts (manual or automatic) are never moved: a new cut only covers what is not yet cut.
* Deleting a word also removes the pause around it (leaving `keep_pause` on each side), like Descript.
* The EDL is saved (with a history entry) unless `dry_run`. Stats are recomputed (`stats.final_seconds`).
* Items timed on the output timeline (titles, overlays, effect clips, markers) are **not** shifted
  automatically; the UI should move items that sit after a deleted range if it wants ripple behaviour.

---

## 14. Scene detection API

POST `/api/projects/{id}/scenes`

```jsonc
{"source": {"kind": "project"} /* or {"kind": "library", "id": "…"} */, "threshold": 0.3, "start": 0, "end": null, "min_gap": 0.6}
```

→ `{"scenes": [{"t": 12.4, "score": 0.61}, …], "markers": [{"t": 12.4, "label": "Scene 2", "kind": "note"}, …]}`

Times are **source** seconds of that file (use for overlay `trim_in` / auto-split, or map through
the cuts for markers). Runs on the 720p proxy at 320 px: ~20–60× realtime.

---

## 15. Catalogs in `/api/presets`

`GET /api/presets` now has `pro`:

```jsonc
"pro": {
  "trending":   [ {id, label, cat: "trending", params, cost, anim, tags, preview, css}, … 25 ],
  "masks":      {"shapes": {...}, "params": [...], "animatable": [...], "bg": [...]},
  "blend_modes": {"normal": "Normal", …},
  "keyframe_eases": {"linear": "Linear", …},
  "keyframe_params": {"clip": {x: {min,max}, …}, "main_transform": {...}, "mask": [...], "crop": [...], "effect_params": "…"},
  "speed": {"min": 0.25, "max": 4, "warp": {"off": …, "fast": …, "balanced": …, "best": …}},
  "tools": {stabilize, denoise, sharpen, face_refine, speed_warp, morph_cut, color, mask — labels, params, costs},
  "color": {"wheels": [...], "channels": [...], "range": [-1, 1], "curves": [...], "hsl_item": {...}},
  "markers": {"chapter": …, "note": …, "todo": …},
  "defaults": { …effects.pro defaults… },
  "capabilities": {"stabilize": "vidstab"}
}
```

`presets.catalog` also gains category `trending` (first) and the 25 effects;
`presets.render_defaults` gains `markers: []` and `effects.pro: {}`.

---

## 16. Preview in the browser

What the editor can show live without the server:

* keyframes: CSS transforms per frame (`translate`, `scale`, `rotate`, `opacity`), same eases
  (cubic in/out, smoothstep in-out, hold);
* masks: `clip-path` (circle/ellipse/inset round/polygon for the star) or a canvas `mask-image`;
* blend modes: `mix-blend-mode` (see §4); speed: `video.playbackRate`;
* colour/grade: existing `grade_css` approximations; trending effects with `preview: "css"` have a `css` string.

Everything else (trending effects, stabilise, denoise, face refine, morph, LUT colour) →
POST `/api/projects/{id}/frame` (one rendered JPEG with the sent settings).

---

## 17. Cost table

Measured on the CPU worker class machine (2 cores, ultrafast preset); "+x %" relative to a plain render.

| feature | cost |
|---|---|
| everything off | 0 (no filter added) |
| overlay pro clip, normal blend | ≈ legacy overlay; + per-frame scale/rotate when animated (+5–10 % for that range) |
| overlay blend mode | one RGB blend over the clip's range only (+10–20 % for that range at 1080p) |
| mask still / animated | PNG: ~0; animated: numpy mask video ≈ 3 ms/frame at ≤ 640 px |
| keyframed effect params | the effect's own cost (stepped chunks) |
| speed / ramp | ~0; audio atempo ~0 |
| Speed Warp | fast +5 %; balanced ~1–2 fps of slowed footage; best ~0.3–1 fps |
| trending effects | cost 1: < 5 %; cost 2: 10–40 % for the clip's range; cost 3 (`tr_neon`): ~2× for the range |
| stabilise | +1 decode pass of the source (detect) + ~10 % |
| denoise | hqdn3d +5 %; nlmeans +150–300 % |
| sharpen | +3–5 % |
| face refine | face scan at 2 fps (fast) + small mask video + ~15 % |
| colour (any) | one lut3d +3 % |
| morph cut | < 0.2 s per cut |
| music fit | ~1–2 s per song minute (once) |
| scene detection (API) | 20–60× realtime on the proxy |

Nothing is encoded twice: every feature is part of the single render filter graph (the only
extra passes are analysis-only: vidstab detect, face scan, beat analysis).

---

## Tests

* `cd server && python3 tests/test_pro_render.py --out /tmp/pro_tests` — renders a short sample per
  feature (generated test media: testsrc2 / mandelbrot / a face picture / a beat track), checks
  ffmpeg success + frame-level numbers (keyframe positions, mask pixels, blend inequalities, speed
  mapping, stabilisation motion, denoise error, skin smoothness, colour-match distance, morph jump
  size, music length, scene times, text-cut EDL) and writes contact sheets to `/tmp/pro_tests/sheets`.
  `--only name1,name2`, `--list`.
* `cd server && python3 tests/test_pro_api.py --media /tmp/pro_tests/media` — boots the API on a temp
  data dir and exercises every new endpoint.
