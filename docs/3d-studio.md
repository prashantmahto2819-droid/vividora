# 3D Studio — characters, scenes, lip-sync, explainers

सब कुछ procedural है: कोई model download नहीं, three.js (MIT, `web/dist/assets/three.module.min.js`) browser में
primitives से rigged character बनाता है। Preview browser में चलता है, final render worker पर headless Chromium
(software GL) frame-by-frame बनाकर ffmpeg से encode होता है।

| हिस्सा | कहाँ |
|---|---|
| Rig, animations, lip-sync, scenes (JS) | `web/dist/assets/chars3d.js` |
| Characters page `#/characters3d` | `web/dist/assets/chars3d-ui.js` |
| Scenes & explainer page `#/scenes3d` | `web/dist/assets/scenes3d.js` |
| Headless render page | `web/dist/assets/3d.html` (`setup3d(spec)` → `frame3d(i)`) |
| Server engine (TTS, visemes, Chromium driver, encode, storyboard) | `server/vividora/engine/chars3d/` |
| 60+ profiles | `server/vividora/engine/chars3d/profiles.py` |
| API | `server/vividora/api/chars3d_api.py` (`/api/chars3d…`) |
| Worker jobs | `char3d`, `storyboard3d` in `worker/cpu.py` |

## Rig
19 bones (Hips→Spine→Chest→Neck→Head, shoulders→upper/lower arm→hand, upper/lower leg→foot), one skinned body
mesh (blended weights at the spine/chest) + a head mesh with **13 morph targets**: 8 visemes
(`sil aa ee oh oo mm ff ss`) + 5 expressions (`smile sad angry surprised think`). Parametric: height, build,
age (child/teen/adult/old), skin tone, 6 hairstyles, 22 outfits (coat, apron, helmet+vest, turban, saree, kurta,
garba, lohri, veshti, uniforms…), props (stethoscope, phone, laptop, bag, book, mic, pointer, glasses, hat).

## Animation
14 procedural clips (`makeClip`): idle, walk, run, sit, talk1–3, wave, point, type, nod, laugh, dance, teach —
quaternion tracks per bone + a hips position track, looped and cross-faded by the mixer. While a character
speaks, a talk clip plays; otherwise its idle/seated clip.

## Lip-sync
TTS (engine/tts: Indic-Parler / Kokoro; `VIVIDORA_TTS=fake` for tests) → per-word timing (`tts.word_times`) →
grapheme→viseme table (Devanagari + Latin) → events every 40 ms, weighted by the audio RMS envelope → morph
targets + mouth mesh. Blinks and idle head noise are added automatically.

## Scenes
8 environments built from primitives (classroom, office, clinic, home, shop, gym, park, stage), 3 lighting
rigs (day / evening / night), 6 camera presets + orbit / push-in, 3–4 character slots per scene.

## Outputs
- **Character clip**: transparent VP9 webm (`yuva420p`, with the spoken audio) → library B-roll "3D · name".
  Place it on any overlay track; `effects.alpha_decoder` makes ffmpeg keep the alpha (libvpx decoder).
- **Explainer**: scenes × characters × lines → one H.264 mp4 → a new project whose transcript is the script
  (captions without Whisper; `meta.transcript_preset` is consumed by `service.after_job(prepare)`).

## Production
The Docker image installs `playwright` + Chromium (`server/Dockerfile`); the worker opens
`CHARS3D_PAGE_URL` (default `http://api:8000/assets/3d.html`). Software rendering: ~1–2 frames/s at 720p on a
Xeon core — a 15 s two-character scene takes ~5 minutes. Tests: `python3 tests/test_chars3d_units.py`.
