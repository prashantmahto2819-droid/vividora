# Vividora — Editor feature research & open-source implementation map (Oct 2026)

Scope: what CapCut, Filmora, Vozo, Descript, OpusClip, Submagic, Captions, VEED, InVideo AI, Canva, Runway and DaVinci Resolve offer in their current (2025–2026) versions, deduplicated into one feature inventory, then mapped to open-source routes that run on a Linux CPU server (Xeon E5-2696 v4, 64 GB) with an optional AMD RX 580 (no CUDA).

Method: ~45 web searches/fetches, preferring vendor help centers and 2025–2026 sources. Marketing pages and third-party reviews are cited where the vendor page was unreachable. Anything I could not confirm is tagged **[unverified]**. Prices change often; treat all prices as "as of Oct 2026, verify before quoting".

---

## 1. Per-app inventories

### 1.1 CapCut (desktop + mobile + web)

Sources: [CapCut Desktop AI page](https://www.capcut.com/tools/desktop-ai-power), [Auto Cut help](https://www.capcut.com/help/how-to-use-auto-cut), [AI effects guide](https://www.capcut.com/resource/ai-effect), [caption templates](https://www.capcut.com/resource/caption-template), [speed curve](https://www.capcut.com/tools/speed-ramp), [effects download page](https://www.capcut.com/resource/capcut-effects-download), [LitCommerce cheat sheet (PDF, Mar 2026)](https://litcommerce.com/wp-content/uploads/2026/03/CapCut-ToolCheat-Sheet.pdf), [Miracamp AutoCut guide](https://www.miracamp.com/learn/capcut/the-ultimate-guide-to-autocut), [Miracamp text guide](https://www.miracamp.com/learn/capcut/how-to-add-text), [Vidpros Pro vs Free (May 2026)](https://vidpros.com/capcut-pro-vs-free/), [NemoVideo review](https://www.nemovideo.com/blog/capcut-ai-video-features), [Finchley mobile effects](https://www.finchley.co.uk/finchley-learning/capcut-creativity-must-try-effects-for-video-editing-on-your-mobile-device), [BeverlyBoy transitions](https://beverlyboy.com/film-technology/top-5-must-try-transitions-in-capcut-for-pro-level-edits/).

**Auto / AI features (CapCut's names)**
- **Auto Cut** (desktop: AI button → AI Tools → Auto Cut; mobile: Templates → "AI Creation"/"Smart Editing"). Modes: **Beat Sync** (music-driven), **Speech Pause Detection** (vlogs/interviews), **AI Script Mode** (text instruction e.g. "make a 30-second energetic highlight reel"). Optional sensitivity, minimum clip duration, transition style "if available". Not supported on CapCut Web. ([help](https://www.capcut.com/help/how-to-use-auto-cut))
- **AutoCut / AI clips** (long video → shorts): highlight detection via voice + scene detection, auto subtitles, suggested template styles (cinematic, vlog, gaming, podcast), clip duration control; third-party review says clips often end a beat early/late. ([Miracamp](https://www.miracamp.com/learn/capcut/the-ultimate-guide-to-autocut), [NemoVideo](https://www.nemovideo.com/blog/capcut-ai-video-features))
- **AI Auto-Edit** — free plan: 5 uses/month ([Vidpros](https://vidpros.com/capcut-pro-vs-free/)).
- **Auto Captions** (Text → Auto Captions → spoken language). Free: up to 10 min/video; "Style captions with AI" picks a style; non-speech cues labelled; video must be < 20 min on web tool. Caption template families named on the web page: **Glow, Trending, Aesthetic, Multiline** ([caption-template](https://www.capcut.com/resource/caption-template)). Popular per-word highlight styles users call "Hormozi/Karaoke/Bounce" exist in the app library **[unverified exact names]**.
- **Remove Filler Words** (pauses, repeats, ums) — desktop. ([desktop page](https://www.capcut.com/tools/desktop-ai-power))
- **Auto Reframe** — Original / 9:16 / 1:1 / 16:9, subject-aware.
- **Auto Cutout / Remove Background** (Cutout → Remove Background → Auto remove); limited monthly credits on free, unlimited on Pro; also **Chroma key** and **Custom cutout** (brush) **[custom cutout unverified on current build]**.
- **Smart Search** (find clips by object/speech/person/environment).
- **Script to Video** = **AI Writer** + **Smart Generation** (subtitles + voiceover + music).
- **Text to Speech**, **Custom voices**, **Enhance voice**, **Reduce noise**, **Isolate Voice / Remove Vocals**, **Voice changer** [voice changer name unverified].
- **Selfie enhancement / Retouch** (face: skin smoothing, brightness, skin tone, teeth, makeup; body: Legs, Body, Waist, Head free; Straight shoulders, Wide shoulders, Arms Pro) ([TutsPlus](https://photography.tutsplus.com/tutorials/a-complete-guide-to-body-effects-in-capcut--cms-108858)).
- **AI stylize** (Auto Velocity; anime/watercolor/comic/3D-cartoon/sketch/painting styles), **AI Effects Generator** (free: 3 custom effects/month), **AI upscaling**, **AI relight**, **color matching**, **Scene Detection**, **Auto Beat** (sync effects/transitions to music beat), **One-click rough cut**, **AI Presenter**, **AI Image/Audio generation** (Pro).
- **Stabilization**, **Remove flicker** [flicker unverified], **Motion/Camera tracking** (Video → Camera Tracking → Face), **Sticker tracking**.
- Eye-contact correction: **not found** in CapCut sources I checked **[unverified absence]**.

**Effects (categories & representative names)**
- Panels: **Video effects** (applies to whole frame) vs **Body effects** (person-segmented, tracked automatically) vs **AI stylize**. ([ai-effect](https://www.capcut.com/resource/ai-effect))
- Video-effect library groups: **Classic, Party, Motion, Light**; themed: **Cinematic, Film, Glitch, Neon, Distortion, Mood, Soft aesthetic, Superpowers, Hallucination, Role**; web categories: **Trending, Opening & Closing, Lens, Light, Retro, Star**. ([effects-download](https://www.capcut.com/resource/capcut-effects-download))
- Body effects groups: **Stroke, Portrait, Mood, Funny Faces**; examples: glowing outlines, particle bursts, velocity lines, motion trails, body outlines, dynamic shadows, afterimage/ghost trail [afterimage name unverified].
- Trending effect names seen in 2026 cheat sheet: **Blur, Fade In, Rolling Film, 3D Zoom Pro, Shaky Dolly, Movie Look, Motion Tracking, Film Grain, Light Leaks**; overlays: bokeh, film grain, animated textures, sparkles, confetti.
- Filters: categories **Nature, Retro, Party** (mobile); desktop lists retro, life, movie, scenery; intensity slider; LUT import on desktop; color wheels, skin-tone protection (desktop Color Grading).
- Transitions: categories **Basic, Camera, Retro** (mobile); commonly used names **Smooth Zoom (Pull In/Out), Warp Slide, Glitch, Spin (3D), Cinematic Fade/Dissolve, Mix, Blur, Flash, Mirror, Swipe** [individual names partly from tutorials; exact list changes by build].
- Text: **Text Templates** (animated), **Bubbles/Text bubbles**, text effects (stroke, shadow, glow, gradient, background box with padding/opacity), **Animation → In / Out / Loop** (In: Fade In, Zoom, Pop-up, Typewriter, Bounce Left, Wave In, Blur Right, Showing Up, Dissolve Down; Out: Fade Out, Slide Out, Glitch, Dissolve; Loop: Wave, Bounce, Shake), speed/duration slider; custom .ttf/.otf fonts; desktop **Keyframe animation** for text.
- Speed: **Normal** (0.1×–10×) and **Curve** with presets **Montage, Hero, Bullet, Jump Cut, Flash In/Out [flash unverified]** + **Custom** (drag points, "Add Point"), optical-flow smoothing option [unverified name].
- **Mask** shapes: Linear, Mirror, Circle, Rectangle, Heart, Star + feather/invert [list from tutorials, not vendor page]; **Keyframes** on Position, Scale, Rotation, Opacity (and mask/filters); **Blending modes** (Normal, Screen, Multiply, Overlay, Lighten, Darken…) [list unverified]; **Chroma key**; **Mosaic/blur** (Effects → "Mosaic", "Pixelate", face-tracking blur via body effects) [unverified]; **Freeze frame**, **Reverse**, **Split screen** (via Templates), **Compound clip**, **Group/Ungroup**.
- Stickers: built-in library + GIPHY search inside the app; **Add Image as Sticker**.

**Workflow UI**
- Top panels: **Format(Media), Filters, Effects, Text, Audio, Templates, Upload, My space** (web); desktop: Media / Audio / Text / Stickers / Effects / Transitions / Filters / Adjustment / Templates, right-side inspector with Video/Audio/Speed/Animation/Tracking/Mask tabs; multi-track timeline with main track + overlay tracks; **Main Track Magnet**, **Auto Snapping**, **Linkage Switch** (ripple link), markers (coloured), **In/Out points**, shuttle (JKL), **Compound clip**, **Group**, keyframe panel, **Delete Left/Right** (ripple delete). Keyboard shortcut list in cheat sheet.
- Templates marketplace (CapCut Templates / Pippit); brand kit & team space on CapCut for Business [unverified detail]; cloud "My space" projects (100 GB Pro); export: resolution, bitrate, codec, MP4/MOV, 24/30/60 fps, HDR (Pro), 4K60 (Pro), direct share to TikTok/YouTube/IG.

**Pricing / limits (Oct 2026, [Vidpros](https://vidpros.com/capcut-pro-vs-free/))**
- Free: 1080p export, no watermark on standard exports; watermark appears when Pro-tagged templates/effects/AI tools are used; Auto-captions 10 min/video; AI Auto-Edit 5/mo; limited BG-removal credits; personal-use licence only.
- Pro: 4K60, HDR, unlimited captions/BG removal, upscaling, motion tracking, 100 GB cloud, commercial licence; regional pricing (India ~40–50% cheaper); 3-day trial; extra AI credit packs $4.99–19.99; exact monthly price not stated in source [verify on capcut.com/pricing].

### 1.2 Filmora (V15, 2026)

Sources: [What's new (official)](https://filmora.wondershare.com/whats-new-in-filmora-video-editor.html), [Smart Short Clips guide](https://filmora.wondershare.de/guide/smart-short-clips.html), [Macworld sponsored V15 piece](https://www.macworld.com/article/3016776/wondershare-filmora-v15-smarter-editing-powered-by-ai-and-built-for-real-creators.html).

**Auto / AI**
- **AI Mate** (formerly AI Copilot): AIGC / Action / Guide / Auto modes — natural-language commands executed as edits.
- **Smart Cutout / AI Smart Cutout** (subject isolation, BG removal, **adds outlines**; V15 improved edges) — the only mainstream NLE that advertises "outline after cutout" as a feature.
- **Smart Short Clips**: input YouTube link/file; options: source language, duration, template "designs", aspect ratio, **Intelligent BGM Generation**, "main theme" keywords for relevant animations, Enhance Voice; outputs several clips **each with a rating**, auto thumbnails, TTS voiceover, auto split-screen layouts, direct publish with schedule.
- **Smart Scene Cut**, **AI Media Analysis** (labels/scores clips), **Silence Detection**, **Auto Beat Sync**, **Dynamic Caption** (styled auto-captions w/ templates), **Smart Text Correction**, **AI Speech to Text**, **AI Text-Based Editing**, **AI Face Mosaic** (detect+track+blur faces), **AI Eye Contact**, **AI Video Translation** + **Translation-Lip Sync**, **AI Text to Speech**, **AI Voice Cloning**, **AI Music Generator**, **AI Sound Effect Generator**, **AI Audio Enhancer / Denoise / Vocal Remover / Voice Changer**, **AI Object Remover** (video, tracked), **AI Video Enhancer**, **AI Frame Interpolation**, **AI Relight**, **AI Night View**, **AI Color Palette**, **AI Skin Tone Protection**, **Auto Color**, **AI Thumbnail Creator**, **AI Copywriting** (titles/descriptions), **AI Script/Idea/Text/Image to Video**, **AI Extend** (prompted clip extension), **AIGC Transitions**, **AI Sticker**, **AI Effects** (generative grain/dust), **Photo to Talking Video**, integrations with Sora 2 / Veo 3.1 / Seedance 2.0 / Nano Banana Pro / GPT Image 2.
**Effects & editing**
- **Mask** (multi-mask), **Draw Mask** (pen/Bezier), **Color Mask**, **Track Matte**, **Keyframe** + **Keyframe Graph Editor** (velocity curves), **Keyframe Path Curve**, **Keyframe Motion Blur**, **Anchor Point**, **Camera Tracking**, **Planar Tracking**, Mocha plugin, **Corner Pin**, **Adjustment Layer**, **Compound Clip**, **Multi-Camera**, **Speed Ramping** presets (Montage, Hero moment, Bullet time, Jumper, Flash in, Flash out) [names from Filmora speed-ramp docs, not re-verified this session], **Super Slow Motion (optical flow)**, **Flicker Removal**, **Video Denoise**, **Lens Correction**, **Motion Blur**, **Advanced Mosaic** (9 mosaic types), **Split Screen Template**, **Multi Frame Effect**, **Audio Ducking**, **Loudness Normalization** (LUFS), **Audio Gain** batch, **Audio Stretch**, **Audio Stickers**, **Audio Transitions**.
- Text: **Text Animation (In/Out/Loop)**, **Text Bezier Path Animation**, **Curved Text**, **Glow Text**, **Bubble Text Presets**, **Custom Text Texture**, **3D Titles**, **Audio-Driven Text Effects**, **Animated Charts**, **Logo Reveal**, **Subtitle Track**, **Auto-Fill Text Gaps**.
- Colour: HDR colour wheels (6 zones), RGB curves, HSL eyedropper, **3D LUTs** w/ intensity, pro scopes.
- Asset packs via Filmstock (e.g. Movie Atmosphere, Retro DV), Boris FX / NewBlueFX plugins.
**Workflow UI**: dual timelines, source/timeline monitors, subprojects, magnetic timeline, 5 workspace layouts, Shortcut Key Manager, **Pen Tool** (draw motion paths), Video Review & Collaboration (time-coded notes), Filmora Cloud (100 GB on Premium), export batch presets, XML export, chapter progress bar, social scheduling ("Marketing Data Analysis").
**Pricing**: Premium ~$79.99/yr ($6.67/mo) incl. 2,000 AI credits + 100 GB cloud (sponsored source); free trial exports carry a watermark [watermark from general knowledge, unverified in these sources].

### 1.3 Vozo AI

Sources: [pricing](https://www.vozo.ai/pricing), [tools/points rules](https://www.vozo.ai/docs/common/tools-points-rules.md).
- Tools (point cost): **Translate & Dub** (3 pts/min; +1/min to erase burnt-in subs), **Translate Subtitles** (free for subscribers, limited time), **Visual Translate** (on-screen text translation, 10 pts/min), **Lip Sync** (5 + 5/min; variants 5/min), **Talking Photo**, **Voice Studio** (TTS/clone, 29 languages, 3 pts/min), **Long Video to Shorts / Shorts Generator** (1 pt per 3 min, English only), **Face Swap**. Also marketed: AI video "rewriting/redubbing" (change what you said), **AI Video Editor** with talking-video retake [unverified], eye contact **not listed** on pricing page **[unverified]**.
- Plans: Free $0 (20 pts, 3 projects, 20-min max), Creator $29/mo (150 pts, watermark removed, API), Studio $99/mo (600 pts, 3 seats, bulk upload, glossary/brand governance), XL/XXL, Enterprise. Up to 4K; Shorts Generator 2 h max.

### 1.4 Descript

Sources: [Underlord primer](https://www.descript.com/blog/article/underlord-ai-video-editor-primer), [transcription page](https://www.descript.com/transcription-update), [Chase Jarvis workflow](https://chasejarvis.com/blog/descript-underlord-ai/), [Vidpros review 2026](https://vidpros.com/descript-review/).
- **Underlord** (AI co-editor, works on the transcript; prompt-driven; prompts can be saved as templates). Named actions: **Identify Speakers / Speaker Detective, Remove Retakes** (keeps last complete take), **Remove Filler Words** ("Ignore" rather than delete so it's reversible), **Shorten Word Gaps** (threshold e.g. 0.7 s → ~0.2–0.3 s), **Edit for Clarity**, **Studio Sound** (intensity 55–85% recommended), **Eye Contact**, **Green Screen**, **Add captions**, **Apply a layout** (e.g. "Berlin Carrot"), **Add a title card**, **Chapter markers**, **Add B-roll** (stock or generated), **Add zooms**, **Create Clips** (social clips with templates), **Automatic Multicam**, **AI Speech / Overdub** (voice clone, dubbing 15 credits/min), **Regenerate** (fix a word), **Translation**.
- Workflow: text-based editing (delete words = cut video), **Scenes** (slash-command scene breaks), **Layouts/Templates**, brand templates, cloud collaboration/comments, publish to YouTube etc.
- Languages: transcription in 22 languages — **Hindi is NOT listed** ([source](https://www.descript.com/transcription-update)). Important for a Hindi creator.
- Pricing (2026): Free 1 h transcription + watermark; Hobbyist $12–16/mo (10 h); Creator $24 (30 h); Business $40–50 (40 h). AI features consume credits since the Sept-2025 billing change; media minutes count the full upload.

### 1.5 OpusClip

Sources: [home](https://www.opus.pro/home), [pricing](https://opus.pro/pricing?via=46f5e2).
- **ClipAnything** (multimodal clipping: visual + audio + sentiment cues; works on low-dialogue video; prompt "clip the moment where…"), **AI curation** (rearranges highlights from different parts into one short, ends with CTA), **Virality Score** (0–100 per clip), **AI Reframe** (speaker/moving-object aware; "ReframeAnything" is marketing name), **AI animated captions** (20+ languages, emoji + keyword highlighter; "viral caption templates"; custom fonts on Pro), **AI B-roll** (stock or AI-generated), **Filler & silence removal**, **Speech enhancement**, **Brand template** (fonts, colours, logo, intro/outro), **Social post scheduler / auto post** (YouTube, TikTok, IG, FB, LinkedIn, X), **Team workspace**, **XML export to Premiere/Resolve**, multi-aspect (9:16/1:1/16:9), input from 10+ sources.
- Pricing: Free 60 credits/mo, watermark, 1080p, no editing, exports expire 3 days; Starter $15/mo (150 credits); Pro $29/mo list ($14.50 annual promo; 3,600 credits/yr); Business custom. Credits ≈ minutes of source video (not stated on page) [unverified].

### 1.6 Submagic

Sources: [UC Strategies review 2026](https://ucstrategies.com/news/submagic-review-2026-pricing-features-is-it-worth-it-for-creators/), [Submagic blog/nav](https://www.submagic.co/blog/make-captions-like-ali-abdaal).
- Captions: 98.9% claimed accuracy, 50 caption languages, auto-emojis, keyword highlighting; creator-style templates named **Hormozi (Alex Hormozi), Beast (MrBeast), Ali (Ali Abdaal), Devin (Devin Jatho), Iman (Iman Gadzhi)** plus others (Karaoke, Tracy… [unverified]).
- **AI Auto Edit** (one-click): **Magic B-roll** (stock/GIF/images from transcript), **Auto-Zoom** (punch-ins on key moments), **Smart transitions**, **Sound effects** on transitions/B-roll, **Images & GIFs**, **Background music**, **Trimming/silence removal**, audio cleaning, **AI Eye Contact**, **Magic Clips** (long → shorts), **Auto Description**, **AI Video Translator** (100+ languages), **AI Actors Studio**, **Publishing** scheduler, API (Business).
- Pricing: Free 3 videos/mo, 90-s limit, watermark; Starter $12–19/mo (15 videos, 1080p); Pro $39 (40 videos, Storyblocks, eye contact); Business $69 (100 videos, 4K60, API).

### 1.7 Captions (by Mirage)

Source: [eesel review 2026](https://www.eesel.ai/blog/captions-ai).
- **AI Edit** (chat/command editing, e.g. "add B-roll of a city at night"), **AI Eye Contact**, **AI Denoise**, **AI Dubbing & Lipdub** (28+ languages), **Auto Captions** (100+ languages), **Caption styling** (100+ templates on paid), **AI Twin / AI Actors / AI Creator**, **AI Voice Clone**, **Text-to-Video**, trends/zooms/SFX [unverified names].
- Pricing: Free (1 caption template, no AI credits); Max $24.99/mo (500 credits); Frontier $69.99–279.99; Enterprise. Reviews mention lag/export crashes.

### 1.8 VEED

Source: [Dupple review (Jul 2026)](https://dupple.com/reviews/veed).
- **Auto Subtitles** (125+ languages, style presets: font/colour/animation), **Subtitle translation** (Pro), **AI Dubbing**, **AI Avatars** (5 min/mo Pro), **Magic Cut** (filler words + dead air, Pro), **Eye Contact** (Pro), **Clean Audio** (Pro), **Text to Video**, **AI Clips** (Pro), **Auto-resize**, one-click presets (transitions, filters, animations), **Brand Kit**, **Collaboration** (timestamped comments, shared drafts), stock media, screen/cam recorder, background remover [not on source page; VEED does have "Remove Background" tool — unverified here].
- Pricing: Free 720p + watermark + 10-min cap; Lite $9/mo (1080p, no watermark); Pro $24/mo; Business (4K).

### 1.9 InVideo AI

Source: [Creatify review 2026](https://creatify.ai/review/invideo-ai).
- **Script/prompt to video** (script + scenes + stock + voiceover + captions in one go), **iStock + Storyblocks** stock, 200+ generative models (Veo 3.1, Kling 3.0, Seedance 2.0, Nano Banana Pro, Sora 2 — Sora 2 API ends 24 Sep 2026), **voice clone** + 30+ stock voices/50+ languages, **edit by text command** + manual editor (InVideo Studio), vertical export for Shorts/Reels, avatars.
- Pricing: Free (~10 AI min/week, watermark); Plus $20 (75 credits, 100 stock assets); Max $100; Generative $200; Elite $1,000. Credits don't roll over.

### 1.10 Canva Video

Source: [Canva AI video editor page](https://www.canva.com/video-editor/ai/).
- **Magic Video** (clips + prompt → auto edit/transitions/music), **Capture Video Highlights**, **Video Background Remover** (one click), **AI Voice Generator**, **Image to Video** (~5 s), **Video Generator**, AI video effect templates (**Elevator Edit, Light Prism, Street Art**), templates, 25,000+ licensed tracks, text effects, animations (element/text/page), transitions, **Video hooks**, in-app recording, real-time collaboration, **Brand Kit** (Pro), multi-device, direct publish. Captions exist in Canva ("Captions" from the Magic Studio) but not on this page [unverified].
- Pricing: free tier with limited AI uses + small Canva logo on Pro elements; Pro removes watermark, unlocks resize + Brand Kit.

### 1.11 Runway (background/removal only)

Source: [fast.io review 2026](https://www.fast.io/resources/runway-ai-review-2026.md).
- Relevant tools: **Green Screen** (AI rotoscoping/background removal — not in this source; long-standing Runway tool [unverified current state]), **Video Inpainting** (remove objects/logos/bystanders, swap backgrounds), **Motion Brush 3.0**, **Act-One**, **Runway Agent**.
- Pricing: Free 125 one-time credits; Standard $12/mo (625 credits); Pro $28; Max $76; API $0.01/credit. Watermark policy not stated in source.

### 1.12 DaVinci Resolve 20 (concepts only)

Source: [ProVideoCoalition on Resolve 20](https://www.provideocoalition.com/davinci-resolve-20-released/).
- **Magic Mask v2** (AI person/object mask with paint-brush refinement), **Keyframe editor** (curve view + timeline drawer), **AI Animated Subtitles** (word highlight/animation), **AI IntelliScript** (timeline from script), **AI Multicam SmartSwitch**, **AI Dialogue Matcher**, **AI VoiceConvert**, **Chroma Warper**, nodes-based colour, LUTs, power windows (shapes + tracked), speed-ramp retime curves with optical flow. Free vs Studio split not in source.

---

## 2. Deduplicated feature inventory (what Vividora should expose)

Legend: ★ = in ≥5 of the apps above (table-stakes), ◆ = differentiator for a talking-head Hindi creator.

### 2.1 Auto / AI
| Feature | Apps that have it | Notes |
|---|---|---|
| ★ Auto captions, word-level, styled templates | CapCut, Filmora (Dynamic Caption), Descript, Opus, Submagic, Captions, VEED, Resolve 20 | Template families: Glow/Trending/Aesthetic/Multiline (CapCut), Hormozi/Beast/Ali/Devin/Iman (Submagic), emoji + keyword highlight (Opus) |
| ★ Silence / dead-air removal | CapCut Auto Cut (speech pause), Filmora Silence Detection, Descript Shorten Word Gaps, Opus, Submagic, VEED Magic Cut, Canva (no) | Exposed knobs: threshold, min gap, padding/margin, target gap length |
| ★ Filler-word removal | CapCut, Descript, Opus, VEED | needs transcript with word timestamps; Hindi fillers: "मतलब", "तो", "अं", "हम्म", "ना" |
| ★ Retake removal | Descript (Remove Retakes: keep last complete take) | transcript similarity of adjacent sentences |
| ★ Long video → Shorts with score | CapCut AI clips, Filmora Smart Short Clips (rating), Opus (Virality Score), Submagic Magic Clips, Vozo Shorts Generator, VEED AI Clips, Descript Create Clips, Canva Highlights | LLM over transcript; "hook/emotion/quotable/practical value" signals |
| ★ Auto reframe 9:16 / 1:1 / 16:9 | CapCut, Opus AI Reframe, VEED Auto-resize, Filmora 360 reframing, Canva resize | speaker/face tracking |
| ★ Background removal (video) | CapCut Auto Cutout, Filmora Smart Cutout, Canva Video BG Remover, Runway Green Screen, VEED | Filmora adds outline; CapCut Body effects do stroke/glow on the cutout |
| ◆ Cutout outline / stroke / glow / afterimage ("effects on person") | CapCut Body effects (Stroke, Portrait, Mood), Filmora Smart Cutout outline | |
| ★ Auto zoom / punch-ins | Submagic Auto-Zoom, Descript Add zooms, Captions | keyframe scale on emphasis words |
| ★ AI B-roll (stock/GIF/generated) | Submagic Magic B-roll, Opus AI B-roll, Descript Add B-roll, Captions AI Edit, InVideo | keyword → Pexels/Pixabay/Giphy |
| ★ Auto music + beat sync | CapCut Auto Beat / Beat Sync, Filmora Auto Beat Sync + Intelligent BGM, Submagic BGM, Canva Magic Video | |
| ★ Sound effects on cuts/B-roll | Submagic, Captions, Filmora Audio Stickers | |
| ★ Eye contact | Descript, Filmora, Submagic (Pro), Captions, VEED (Pro), Vozo [unverified] | no mature open-source model (see §3.11) |
| ★ TTS / voice clone | CapCut, Filmora, Descript Overdub, Captions, InVideo, Vozo Voice Studio, Canva | |
| ★ Dubbing + lip-sync | Vozo, Filmora, Captions Lipdub, VEED, Descript | |
| ★ Script-to-video | CapCut, Filmora, InVideo, VEED, Descript | low priority (user records himself) |
| ★ Noise reduction / voice enhance / loudness normalise | CapCut, Filmora (LUFS), Descript Studio Sound, Opus, Submagic, VEED Clean Audio | |
| ◆ Titles/descriptions/hashtags, auto description | Filmora AI Copywriting, Submagic Auto Description, Opus | |
| ◆ Hook generation / title card | Descript title card, Canva Video hooks, Opus hooks | |
| ★ Chat/prompt-driven editing | CapCut AI Script Mode, Filmora AI Mate, Descript Underlord, Captions AI Edit, InVideo, Runway Agent | Vividora: "edit recipe" JSON generated by Gemini |
| Face mosaic/blur tracked | Filmora AI Face Mosaic, CapCut | |
| Object removal | Filmora, Runway Inpainting, CapCut | out of scope v1 |
| Retouch / beauty | CapCut, Filmora | optional |
| Upscale / denoise / frame interpolation | CapCut, Filmora | optional (Real-ESRGAN, RIFE — GPU-heavy) |

### 2.2 Effects, motion, compositing
- **Effect taxonomy** to copy: *Video effects* (full-frame: Glitch, Retro/VHS, Film grain, Light leak, Bokeh, Lens flare, Shake, Blur/Fade in-out, Rolling Film, 3D Zoom, Shaky Dolly, Movie Look, Neon, Distortion, Mood, Soft aesthetic, Opening & Closing) vs *Body effects* (on person: Stroke/outline, Glow, Neon, Afterimage/ghost trail, Velocity lines, Particles, Dynamic shadow, Portrait relight) vs *AI stylize* (anime/comic/sketch — GPU, skip).
- **Transitions**: Dissolve/Fade, Mix, Smooth Zoom (Pull in/out), Warp Slide, Spin 3D, Glitch, Flash, Blur, Mirror, Swipe/Slide, Wipe; audio transitions.
- **Text**: templates, In/Out/Loop animations (Typewriter, Fade, Pop-up, Zoom, Bounce, Wave, Shake, Glitch, Dissolve, Blur), stroke/shadow/glow/gradient/background box, bubbles, curved text, path animation, karaoke highlight.
- **Speed**: constant 0.1–10×, curve presets Montage / Hero / Bullet / Jump Cut / Flash In / Flash Out + custom points, optical-flow option; Reverse; Freeze frame.
- **Masks**: Linear, Mirror, Circle, Rectangle, Heart, Star, pen/Bezier (Filmora Draw Mask, Resolve power windows), feather, invert, keyframable, Track Matte.
- **Keyframes**: Position, Scale, Rotation, Opacity, mask, filter params; graph editor with velocity curves (Filmora, Resolve 20).
- **Blending modes**, **Chroma key**, **Mosaic/Pixelate** (shape + tracked), **Stabilization**, **Flicker removal**, **Split screen / collage templates**, **Multi-frame**, **Adjustment layer**, **Compound clip**, **Stickers + GIF search**, **Frames/borders overlays**, **Filters + LUT import with intensity**, **Color wheels/curves/HSL**, **Skin-tone protection**.

### 2.3 Workflow UI (common denominator)
- Left asset panels (Media / Audio / Text / Stickers / Effects / Transitions / Filters / Templates), centre preview with on-canvas handles, right inspector with tabs (Basic, Speed, Animation, Mask, Tracking, Audio), bottom multi-track timeline (main track + overlays + text + audio), **snapping toggle**, **main-track magnet** (auto ripple close gaps), **linkage switch** (ripple edits on linked tracks), **ripple delete left/right**, multi-select/group/compound, markers, in/out points, JKL shuttle, keyframe lane, undo history.
- Templates marketplace (CapCut/Pippit, Canva, Filmstock), **Brand kit** (fonts/colours/logo/intro-outro: Opus, VEED, Canva, Submagic), **project versioning / cloud autosave** (CapCut My space, Filmora Cloud, Descript), **collaboration/comments** (VEED, Canva, Filmora Review, Descript), **export presets** (platform presets, 1080p/4K, bitrate/codec, XML/EDL to Premiere/Resolve: Opus, Filmora, auto-editor), direct publish + scheduler (Opus, Submagic, Filmora, Canva).

### 2.4 Pricing/watermark pattern (for product positioning)
Every competitor gates: watermark on free, 1080p vs 4K, AI minutes/credits per month, number of videos per month, caption minutes, brand templates count. Typical creator tier: $12–29/mo. Vividora's pitch: zero subscription, only Gemini/ElevenLabs API cost where used.

---

## 3. Open-source implementation map (Linux CPU server; optional RX 580)

Hardware reality check: Xeon E5-2696 v4 = 22 cores/44 threads, AVX2 (no AVX-512), 64 GB RAM. RX 580 is **gfx803 (Polaris)**, dropped from official ROCm; an unofficial Docker image (ROCm 6.1.2 + PyTorch 2.4, kernel 6.12/6.13 segfault, ~80 GB disk) exists ([woodrex83/ROCm-For-RX580](https://github.com/woodrex83/ROCm-For-RX580)). Practical advice: **design for CPU (ONNX Runtime + OpenVINO) and treat the GPU as optional** via **Vulkan (ncnn)** or that ROCm image; do not block the roadmap on it. ONNX Runtime's ROCm EP targets newer cards ([docs](https://onnxruntime.ai/docs/execution-providers/ROCm-ExecutionProvider.html)).

All CPU timings below are either cited or **my estimates [est.]** extrapolated from cited numbers; benchmark on the Z440 before committing.

### 3.1 Background removal / matting (video)
| Route | Repo / model | License | CPU speed (720p) | Notes |
|---|---|---|---|---|
| **Robust Video Matting (RVM)** mobilenetv3 | [PeterL1n/RobustVideoMatting](https://github.com/PeterL1n/RobustVideoMatting) (ONNX fp32/fp16, TorchScript, OpenVINO OMZ) | **GPL-3.0** (code+weights re-released GPL) | Repo gives GPU only (HD 104–172 fps). CPU: no official numbers; with `downsample_ratio=0.25–0.375` and ORT 44 threads expect ~8–20 fps [est.] | Temporal (recurrent) → no flicker, no trimap needed, ideal for talking head. GPL: fine for self-hosted service; if you ever distribute Vividora binaries, isolate RVM in a separate process/service. OpenVINO has an OMZ port ([docs](https://docs.openvino.ai/2024/omz_models_model_robust_video_matting_mobilenetv3.html)) — likely fastest CPU path. |
| **MediaPipe SelfieSegmenter** (256² / 144×256 landscape) | [MediaPipe Image Segmenter](https://developers.google.com/edge/mediapipe/solutions/vision/image_segmenter) | Apache-2.0 (code), model cards permissive | 33 ms/frame on Pixel 6 CPU → ~10–15 ms on Xeon [est.] (60+ fps) | Binary mask only (no soft alpha), hair edges weak. Use as the **fast preview / draft** path and for "is a person present" detection. **SelfieMulticlass** (hair, face skin, body skin, clothes) 218 ms Pixel-6 CPU → useful for hair-only / clothes-only effects. |
| **BiRefNet** (via `rembg`) | [ZhengPeng7/BiRefNet](https://github.com/ZhengPeng7/BiRefNet) | MIT | Swin-T 1024² ONNX: **4.3 s/frame on M1 Max CPU** ([dev.to](https://dev.to/kiarina/removing-a-portrait-background-with-birefnet-onnx-on-cpu-gbj)) → too slow for video; BiRefNet-lite / 512 px maybe ~1 s | Use for **thumbnails, stills, sticker cutouts** only. `rembg` also ships u2net / isnet-general (CPU ~0.3–1 s/frame [est.]). |
| MODNet | [ZHKKKe/MODNet](https://github.com/ZHKKKe/MODNet) | CC BY-NC-SA 4.0 (model) | fast (ONNX 512px ~50–100 ms [est.]) | **Non-commercial** licence → avoid if Vividora is ever sold. |
| BackgroundMattingV2 | [PeterL1n/BackgroundMattingV2](https://github.com/PeterL1n/BackgroundMattingV2) | MIT | GPU-oriented | Needs a clean background plate (user steps out of frame) — great quality if the creator records a 2-s empty-room shot. CPU slow [unverified]. |
| MatAnyone (2025) | [pq-yang/MatAnyone](https://github.com/pq-yang/MatAnyone) | check repo (paper CVPR 2025; licence not confirmed) [unverified] | GPU only in practice (P100, OOM on >8 s clips per [LearnOpenCV](https://learnopencv.com/matanyone-for-better-video-matting/)) | Needs first-frame mask (SAM2). Best quality; not CPU-viable. |

Recommendation: RVM-mobilenetv3 via ONNX Runtime/OpenVINO for final renders, MediaPipe for previews, BiRefNet for stills. Cache alpha as a grayscale `.mkv` (ffv1/gray) per source clip so every effect reuses it.

### 3.2 Outline / stroke / glow / afterimage after matting (CapCut "Body effects")
Pure ffmpeg/OpenCV on the cached alpha — no ML:
- **Stroke**: dilate alpha (`cv2.dilate` with elliptical kernel r px, or ffmpeg `dilation` filter ×N) → `stroke = dilated − alpha` → colourise → composite under subject. ffmpeg: `[alpha]dilation=...,format=gray[dil]; [dil][alpha]blend=all_mode=subtract[ring]; color=c=#FF2D55[ring_col]; [ring_col][ring]alphamerge; overlay`.
- **Glow**: `gblur=sigma=12` on dilated alpha, screen-blend coloured layer (`blend=all_mode=screen`), optionally animate sigma with `enable`/`sendcmd` or `geq` expressions on `t`.
- **Neon double-stroke**: two rings at r=4 and r=10 with different colours.
- **Afterimage / ghost trail**: keep N delayed copies of (subject×alpha) via `tmix` or `lagfun` (`lagfun=decay=0.95` on the RGBA subject layer) then overlay original on top.
- **Velocity lines / particles**: generate with Pillow/NumPy procedurally along motion vectors from `ffmpeg -vf mestimate` or dense optical flow (`cv2.calcOpticalFlowFarneback`, ~15 ms/frame at 720p [est.]).
- **Relight/"Portrait"**: multiply background by 0.4 and add vignette; subject unchanged.
- Performance: dilation/blur in OpenCV at 720p ≈ 1–3 ms/frame; the alpha pass (RVM) dominates.

### 3.3 Face / person tracking, auto-zoom, auto-reframe, face blur
- **Face detection**: MediaPipe Face Detector / Face Landmarker (Apache-2.0, ~5–10 ms/frame CPU [est.]), or **YOLOv8-face** (AGPL-3.0 — contaminating; prefer **YOLOX / RT-DETR under Apache** or [InsightFace SCRFD](https://github.com/deepinsight/insightface) (code MIT, models non-commercial research — check)).
- **Auto-reframe**: Google **AutoFlip** (MediaPipe graph, Apache-2.0, [blog](https://research.google/blog/autoflip-an-open-source-framework-for-intelligent-video-reframing/)) — shot detection + face/object saliency + camera-path smoothing (stationary / panning / tracking modes). Simpler: track face centre, smooth with a 1-Euro / Kalman filter, clamp crop-window velocity, cut on scene change; this is what [AI-Youtube-Shorts-Generator](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator) (MIT) does with OpenCV.
- **Auto-zoom (Submagic-style)**: punch-in 1.0→1.15 on emphasised words (loud RMS or LLM-marked) with easeOutCubic over 12 frames; implement as keyframed `scale`+`crop` via ffmpeg `zoompan` or `scale=…:eval=frame` with expressions on `n`.
- **Face mosaic**: track → `boxblur`/`pixelize` inside a per-frame mask (`maskedmerge`).
- **Motion tracking for stickers/text**: CSRT/KCF trackers in OpenCV (BSD) are enough for talking heads.

### 3.4 Stabilization, flicker, denoise
- **vid.stab** two-pass (`vidstabdetect` → `vidstabtransform`, GPL in ffmpeg build) — ~2–4× real-time at 1080p on this Xeon [est.]; `deshake` single-pass faster but worse. Flicker: ffmpeg `deflicker`. Denoise: `hqdn3d` (fast) / `nlmeans` (slow). Note: use a GPL-enabled ffmpeg build (Ubuntu's is).

### 3.5 Speed ramp / curves, reverse, freeze
- Constant speed: `setpts=PTS/2`, audio `atempo` (chain for >2×) or `rubberband` filter for pitch-preserving.
- **Curve presets** (Montage/Hero/Bullet/Jump Cut/Flash): represent curve as piecewise-linear speed(t), integrate to get source time → `setpts` cannot take arbitrary functions easily, so **resample via frame map**: compute for each output frame the source frame index (Python), write a `select`/concat list or use `ffmpeg -vf "setpts='…expr…'"` with `if()` expressions for 2–3 segments. For smooth slow-mo use `minterpolate=fps=60:mi_mode=mci` — very slow on CPU (~1–3 fps at 1080p [est.]); limit to ≤3 s segments. RIFE (MIT, ncnn-Vulkan build runs on RX 580) is the faster alternative for interpolation.
- Reverse: `reverse,areverse` (memory heavy; split to ≤10 s). Freeze: `select`/`loop` or `tpad=stop_mode=clone`.

### 3.6 Masks, keyframes, blending, chroma key, split-screen (ffmpeg)
- Shapes: generate mask frames with Pillow/NumPy (Linear, Mirror, Circle, Rect, Heart, Star, feather via Gaussian) → `maskedmerge`; or `geq` with expressions (circle: `lum='if(lt(pow(X-cx,2)+pow(Y-cy,2),r*r),255,0)'`, animate cx/cy/r with `t`).
- Keyframes: Position/Scale/Rotation/Opacity → `overlay=x='…':y='…'` + `scale=eval=frame` + `rotate='…'` + `colorchannelmixer=aa='…'`, expressions in `t`; ease curves precomputed in Python and emitted as `if(between(t,a,b), lerp…)` chains, or via `sendcmd`. For many layers prefer compositing in Python (OpenCV/NumPy) and piping raw frames to ffmpeg — simpler than giant filtergraphs.
- Blending: `blend=all_mode=screen|multiply|overlay|lighten|darken|…`. Chroma key: `chromakey`/`colorkey` + `despill`. Split screen/collage: `xstack`/`hstack`/`vstack` layouts.
- Transitions: ffmpeg **xfade** (~50 built-ins: fade, wipeleft, slideup, circlecrop, dissolve, pixelize, radial, hblur, zoomin, squeezeh, …; [source](https://ffmpeg.org/doxygen/trunk/vf__xfade_8c.html)) + **gl-transitions** (MIT, ~70 GLSL incl. GlitchMemories, Swirl, DoomScreen; run via `moderngl`/ffmpeg `gltransition` patch). **cut-fx** (MIT, [PyPI](https://pypi.org/project/cut-fx/)) wraps 559 named transitions over ffmpeg/procedural/shader backends — worth evaluating as the transition engine (needs ffmpeg ≥6; shader backend needs OpenGL 3.3 — RX 580 fine with Mesa).

### 3.7 Animated captions and text
- **libass / ASS** is the cheapest route: word-level timing from Whisper → ASS events with `\k` karaoke, `\t(…)` transforms, `\move`, `\fad`, `\fscx\fscy` (pop/bounce), `\bord`+`\shad`+`\blur` (stroke/glow), `\1c` highlight colour swaps per word (Hormozi style), `\an` positioning, Devanagari via Noto Sans Devanagari / Mukta / Hind (OFL). Burn with `subtitles=` filter (CPU cost negligible). Limits: no per-glyph physics, no emoji colour fonts (libass has limited colour-emoji support; render emoji as PNG overlays instead).
- For richer templates: **Remotion** (React → video). Licence: free for individuals and teams ≤3 people incl. commercial; company licence $25/dev/mo or $0.01/render otherwise ([FAQ](https://www.remotion.dev/docs/license-pricing-compliance/faq)). Headless Chrome rendering is CPU-OK (~5–15 fps at 1080p [est.]). Alternative fully-open: Pillow/Skia-python frame renderers, or `web-overlay`-style HTML/CSS → Chromium (used by cut-fx).
- Caption presets to ship (names after apps): **Karaoke highlight, Boxed word (Hormozi), Bounce/pop per word, Typewriter, Glow, Multiline aesthetic, Beast (big yellow+black stroke), Minimal lower-third**.

### 3.8 Transcription (Hindi) — word timestamps
- **faster-whisper** (CTranslate2, MIT) `large-v3` int8 on CPU ≈ 3× real-time on M5 Pro; `small` int8 batch-8 ≈ 15× RT on i7-12700K ([comparison](https://www.promptquorum.com/power-local-llm/local-whisper-stt-comparison-2026)) → on the 22-core Xeon expect large-v3 ≈ 2–4× RT, medium ≈ 6–8× RT [est.]. Whisper vanilla Hindi WER is poor (large-v2 21.5% FLEURS) while Collabora fine-tunes reach **5.3% (large-v2) / 6.1% (medium) / 7.2% (small)** on FLEURS ([Collabora](https://collabora.com/news-and-blog/news-and-events/breaking-language-barriers-20-moving-closer-production-ready-hindi-asr.html); models `collabora/whisper-*-hindi`, model licence not stated [unverified]). Use **whisperX**/CTC forced alignment for word timestamps (wav2vec2 Hindi models exist; alignment quality for Devanagari needs testing).
- **AI4Bharat IndicConformer** (Hindi, MIT/CC-BY per AI4Bharat; GGUF ports exist) — strong Hindi, but word timestamps need CTC alignment. **Vaani Whisper-large-v3-Hindi** fine-tune also exists ([arXiv 2606.09335](https://arxiv.org/pdf/2606.09335) compares both; no WERs in text).
- Hinglish (code-mixed) output in Devanagari vs Latin script matters for captions — expose a "script" setting; normalise with `indic-nlp-library`.
- Paid fallback: Gemini 2.5 Flash audio transcription with timestamps (cheap) — can also produce the edit plan in the same call.

### 3.9 Silence / filler / retake removal
- **auto-editor** ([wyattblue/auto-editor](https://github.com/wyattblue/auto-editor), **Unlicense**): `--edit audio:threshold=0.04` or `-19dB`, `--margin 0.2s` (or `0.3s,1.5s` asymmetric), motion detection, `--when:2 speed:1.5`, exports to Premiere/Resolve/FCP/Shotcut/Kdenlive/clip-sequence. Best base for the "Speech Pause Detection" mode.
- **unsilence** (MIT) — speeds silent parts 6× instead of cutting; nice "fast-forward pauses" option.
- Filler words: regex over Whisper word list (Hindi/Hinglish list above + "um/uh/like/you know"), cut with 60–80 ms crossfade on audio (`acrossfade`) and optional 3% punch-in to hide the jump cut (CapCut/Descript do a jump cut; Submagic hides with zoom).
- Retakes: sentence embeddings (e.g. `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, Apache) — adjacent sentences with cosine > 0.8 → keep last.

### 3.10 Highlights / Shorts / titles (LLM)
- Open pattern ([AI-Youtube-Shorts-Generator](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator), MIT): classify content type → chunk transcript 20 min with 60 s overlap → score 0–100 on **hook, emotional peak, opinion, revelation, conflict, quotable line, story peak, practical value** → dedupe >50% overlap → top-N → face-tracked 9:16 crop. Other repos: FunClip (Alibaba, MIT, ASR+LLM clipping), ClipsAI (MIT).
- Use Gemini Flash (cheap) with a Hindi motivational rubric: *hook in first 3 s, one idea per short, 25–55 s, end on a line that loops*. Also generate 3 titles, description, 10 hashtags, pinned comment, thumbnail text per platform.

### 3.11 Eye contact — honest status
- No mature open-source model. Options: (a) **NVIDIA Maxine Eye Contact** — NDA/early access, CUDA-only, no good on RX 580 ([forum thread](https://forum.manjaro.org/t/gaze-redirecton-on-pre-recorded-videos/166567)); (b) **Sieve Eye Contact API** (paid, closed) explains the method: eye-patch crop via landmarks → gaze-redirection net → blend, off during blinks ([Sieve](https://sievedata.com/blog/eye-contact-correction-gaze-correction-api)); (c) **LivePortrait** (KwaiVGI, MIT code; InsightFace deps non-commercial) exposes eye-direction controls and could be driven per-frame but is GPU-bound and risks warping; (d) research code (GazeGAN, STED) is non-commercial. **Recommendation: skip in v1; instead coach the creator to read from a teleprompter near the lens, and offer "Eye contact (paid API)" as an optional Sieve step later.**

### 3.12 TTS (Hindi) and voice
| Model | Licence | Hindi | CPU |
|---|---|---|---|
| **Indic Parler-TTS** (AI4Bharat) | Apache-2.0, 0.9B params, 69 voices (Hindi: Rohit, Divya, Aman, Rani), prompt-controlled style ([HF](https://huggingface.co/ai4bharat/indic-parler-tts)) | yes | slow on CPU (~5–10× slower than real-time [est.]) but fine for batch |
| **Piper** | MIT; `hi_IN` voice exists (community quality) [voice quality unverified] | yes | real-time+ on 1 core |
| **Kokoro-82M** | Apache-2.0, 82M; v1.0 lists 8 languages — Hindi reportedly `lang_code='h'` [unverified on model card] ([HF](https://huggingface.co/hexgrad/Kokoro-82M)) | likely | fast on CPU |
| Chatterbox (Resemble) | MIT, 23+ languages (Hindi inclusion [unverified]) | ? | GPU preferred |
| Coqui XTTS-v2 | **Coqui Public Model License — non-commercial**; Hindi added in later versions [unverified] | partial | GPU preferred |
| Paid: Gemini TTS, ElevenLabs (Hindi good), Sarvam Bulbul (Indian voices) | per-char | yes | n/a |

### 3.13 Dubbing / translation
- Hindi↔English: **IndicTrans2** distilled 200M (MIT, [HF](https://huggingface.co/ai4bharat/indictrans2-indic-en-dist-200M); CTranslate2 port possible, CPU fast). **NLLB-200** is **CC-BY-NC-4.0 and "not released for production"** ([model card](https://huggingface.co/facebook/nllb-200-distilled-600M/blob/main/README.md)) → avoid for a product. Pipeline: Whisper → IndicTrans2 → TTS → `rubberband` time-stretch to segment lengths → mix. Lip-sync (Wav2Lip, non-commercial; MuseTalk MIT, GPU) — skip on CPU.

### 3.14 Beat detection / music sync
- **librosa** `beat_track` (ISC) — good enough for 4/4 pop; **madmom** (BSD, RNN downbeats, unmaintained but works); **Beat This!** (CPJKU, MIT, 2024 SOTA, PyTorch; CPU inference OK for a 3-min track [est.]). Use onset strength envelope for "cut on drum hits"; map beat grid → clip boundaries / transition triggers / text pops.
- Music sources with clear licences: YouTube Audio Library (free for YouTube; some require attribution), Pixabay Music (Pixabay Content License, no attribution), Free Music Archive (per-track CC), Incompetech (CC BY). Avoid Epidemic/Artlist unless subscribed.

### 3.15 AI B-roll sources & legal
- **Pexels API**: 200 req/h, 20k/mo; attribution to Pexels + photographer required in-app; **new API keys paused as of Oct 2026** ([help](https://help.pexels.com/hc/en-us/articles/900005852323), [comparison](https://blog.laozhang.ai/en/posts/free-image-api.md)) — if you have no key already, rely on Pixabay.
- **Pixabay API**: 100 req/min, videos supported, cache 24 h, download to own server (no permanent hotlink), show source in search UI; Pixabay Content License (no attribution, no standalone resale).
- **Unsplash**: photos only, hotlink rule + download endpoint, 50 req/h demo.
- **GIPHY API**: "Powered By GIPHY" mark required, beta key 100 calls/h, **no caching/proxying of media without approval**, no mixing with other providers in one grid ([docs](https://developers.giphy.com/docs/api)) — burning GIFs into exported videos is not addressed by the API docs; treat as **legally grey for a product** (OK for personal use; Tenor API is the alternative, similar terms [unverified]).
- Generated B-roll: Gemini image models / Flux (schnell Apache-2.0, dev non-commercial) — Flux on CPU is minutes/image; use API.

### 3.16 Stickers, emoji, frames, overlays, LUTs
- Emoji sets: **Noto Color Emoji** (Apache-2.0; Google also ships **Noto Animated Emoji** as Lottie/GIF/WebP under CC-BY-4.0 [licence unverified]), **Twemoji** (CC-BY-4.0, needs credit), **OpenMoji** (CC-BY-SA-4.0 — share-alike, avoid in commercial templates), Fluent Emoji (MIT) ([licence list](https://funemojis.lovable.app/licensing)).
- Frames/borders/overlays: generate procedurally (rounded-rect borders, film sprocket, VHS lines, grain via `noise=alls=20:allf=t+u`, light leaks via animated gradients) — avoids licence risk; CC0 sources: Pixabay/Pexels overlay videos ("light leak", "film burn", "dust"), Kenney.nl (CC0 game UI), Mixkit (free licence).
- LUTs: free packs (RocketStock 35, Ground Control 30, Color Grading Central samples, SmallHD Movie Look, Frank Glencairn K-Tone, PremiumBeat Wanderlust — "no resell/redistribute") listed at [PremiumBeat](https://www.premiumbeat.com/blog/29-free-luts-for-video/); most lack explicit licences, so **ship your own** `.cube` LUTs generated in Python (teal-orange, Kodak-ish, bleach-bypass, VHS) and let users import theirs. Apply with ffmpeg `lut3d=file.cube:interp=tetrahedral` + `blend` for intensity.
- Fonts: Google Fonts OFL (Hindi: Mukta, Hind, Poppins Devanagari, Noto Sans Devanagari, Baloo 2, Yatra One, Tiro Devanagari Hindi).

### 3.17 Engine/orchestration
- Keep ffmpeg as the renderer (filter_complex generated from a JSON "edit recipe"); Python workers (Celery/RQ) for ML passes (alpha, transcript, face track) that write cache artifacts; final render is one ffmpeg call or a NumPy frame pipeline piped to ffmpeg for heavy compositing. MLT/OpenShot/Kdenlive engines are alternatives but add GPL + complexity. Encode: `libx264 -preset medium -crf 18` for YouTube masters (1080p ~1–2× RT on this Xeon), `-preset veryfast` for previews; the RX 580 can encode via VAAPI (`h264_vaapi`) on Linux — a cheap, real win for preview renders.

---

## 4. Autopilot pipeline — what the best apps automate, and which knobs they expose

### 4.1 Observed automation per app
| Stage | CapCut | Filmora Smart Short Clips | Descript Underlord | OpusClip | Submagic Auto Edit |
|---|---|---|---|---|---|
| Ingest | file/URL/cloud | YouTube link/file/cloud, source language | file, identify speakers | 10+ sources | file |
| Rough cut | Auto Cut: Beat Sync / Speech Pause / AI Script mode; sensitivity, min clip length, transition style | duration target, theme keywords | Remove Retakes → Remove Filler → Shorten Word Gaps (threshold) → Studio Sound % | silence/filler toggle | silence removal, audio clean |
| Captions | auto, style by AI, template pick | Dynamic Caption template + font | Add captions, layout, title card | template w/ emoji + keyword highlight, 20+ langs | creator templates, emojis, highlight |
| Visual interest | Auto Beat effects, template styles | split-screen layouts, stickers, TTS | Add zooms, Add B-roll (stock/generated), layouts | AI B-roll, reframe | Auto-Zoom, Magic B-roll, transitions, SFX, GIFs, music |
| Shorts | AI clips w/ duration | multiple clips **with rating** | Create Clips | Virality Score, curation, CTA ending | Magic Clips |
| Metadata | — | AI Copywriting, thumbnail | chapter markers | — | Auto Description |
| Publish | share to TikTok/YT/IG | direct + scheduled (YT/Vimeo/TikTok) | publish | scheduler, 6 platforms | scheduler |
| Approval | manual timeline refine | select clip → export | review in transcript | editor per clip | editor |

### 4.2 Decision rules the apps expose (to copy into Vividora settings)
- Silence: threshold (dB or 0–1), min silence length, margin before/after cut (auto-editor default 0.2 s), target gap (Descript 0.7 s → 0.3 s), "speed up instead of cut" (unsilence 6×).
- Filler words: on/off, custom word list, "ignore vs delete".
- Retakes: keep last complete take.
- Studio sound / denoise intensity (55–85%).
- Captions: template, max 2 lines (CapCut advice), words per line / chars per line, highlight colour, emoji on/off, language/script, auto-style by AI.
- Auto Cut modes: beat-sync vs speech-pause vs script-prompt; min clip duration; transition style.
- Shorts: clip count, duration range, aspect ratio(s), brand template, CTA at end, score threshold, "clip the moment where…" prompt.
- B-roll: source (stock / GIF / generated), density (per N seconds), only on nouns/keywords.
- Zoom: intensity, frequency.
- Reframe: 9:16 / 1:1 / 16:9, speaker tracking vs static.
- Loudness target (LUFS per platform: YouTube −14, Reels/TikTok ~−14 to −16 [common practice, unverified per-platform spec]).
- Publish: per-platform title/description/hashtags, schedule time, auto-post on/off, 3-day export expiry (Opus free).

### 4.3 Proposed Vividora autopilot (CPU-feasible)
1. Upload → probe (ffprobe), proxy 720p, loudness analyse (`ebur128`).
2. Transcribe (faster-whisper Hindi fine-tune, word timestamps; optional Gemini) → store words/segments.
3. Rough cut: auto-editor-style silence map + filler/retake rules → EDL v1.
4. Style plan via Gemini Flash (JSON): hook title, caption template, zoom points, B-roll keywords with timestamps, SFX cues, music mood, chapter marks, shorts candidates with scores + titles/descriptions per platform.
5. ML passes (parallel workers): RVM alpha (if any body effect or BG swap requested), face track (always, for reframe/zoom), beat grid for music.
6. Render long-form 16:9 + N shorts 9:16 with ffmpeg/ASS; VAAPI preview renders.
7. Dashboard approval: per-asset accept/edit/regenerate (the "style memory" stores accepted knobs as defaults).
8. Publish via YouTube Data API / Meta Graph API with schedule; log performance for feedback.

CPU budget (10-min 1080p30 talking head, 22-core Xeon, rough): transcription 3–5 min; alpha matting (RVM, 720p proxy) 15–35 min [est.]; face track 3–5 min; render 1080p x264 8–15 min; shorts 2–3 min each. Total ≈ 40–70 min fully automatic without GPU; without body effects ≈ 20–30 min.

---

## 5. Things I could not verify (please check before relying on them)
- Exact current CapCut Pro price (regional), exact names of CapCut mask list, blending modes, "Flash in/out" speed preset, mobile caption template names (Hormozi-style), Voice changer / Remove flicker names, absence of eye-contact tool.
- Filmora speed-ramp preset names and free-version watermark behaviour (from memory of older docs).
- Vozo eye-contact / "AI video editor" retake feature; Vozo Studio XL/XXL prices (page showed $0 — page bug).
- Opus credit-to-minute conversion.
- Kokoro Hindi support; Chatterbox Hindi; XTTS Hindi; Piper hi_IN voice quality; Collabora Whisper-Hindi model licence; MatAnyone licence; Noto Animated Emoji licence; Tenor API terms.
- All "[est.]" CPU timings — run `bench/` scripts on the Z440 (RVM ONNX at 720p with 0.25/0.375 ratios, faster-whisper medium/large int8, vidstab, x264 presets, VAAPI) before finalising the autopilot SLA.
- Platform loudness targets per Instagram/Facebook.

## 6. Source index (primary ones)
CapCut: https://www.capcut.com/tools/desktop-ai-power · https://www.capcut.com/help/how-to-use-auto-cut · https://www.capcut.com/resource/ai-effect · https://www.capcut.com/resource/caption-template · https://www.capcut.com/tools/speed-ramp · https://www.capcut.com/resource/capcut-effects-download · https://litcommerce.com/wp-content/uploads/2026/03/CapCut-ToolCheat-Sheet.pdf · https://vidpros.com/capcut-pro-vs-free/ · https://www.miracamp.com/learn/capcut/the-ultimate-guide-to-autocut · https://www.miracamp.com/learn/capcut/how-to-add-text · https://www.nemovideo.com/blog/capcut-ai-video-features · https://photography.tutsplus.com/tutorials/a-complete-guide-to-body-effects-in-capcut--cms-108858
Filmora: https://filmora.wondershare.com/whats-new-in-filmora-video-editor.html · https://filmora.wondershare.de/guide/smart-short-clips.html · https://www.macworld.com/article/3016776/wondershare-filmora-v15-smarter-editing-powered-by-ai-and-built-for-real-creators.html
Vozo: https://www.vozo.ai/pricing · https://www.vozo.ai/docs/common/tools-points-rules.md
Descript: https://www.descript.com/blog/article/underlord-ai-video-editor-primer · https://www.descript.com/transcription-update · https://chasejarvis.com/blog/descript-underlord-ai/ · https://vidpros.com/descript-review/
OpusClip: https://www.opus.pro/home · https://opus.pro/pricing
Submagic: https://ucstrategies.com/news/submagic-review-2026-pricing-features-is-it-worth-it-for-creators/ · https://www.submagic.co/blog/make-captions-like-ali-abdaal
Captions: https://www.eesel.ai/blog/captions-ai · VEED: https://dupple.com/reviews/veed · InVideo: https://creatify.ai/review/invideo-ai · Canva: https://www.canva.com/video-editor/ai/ · Runway: https://www.fast.io/resources/runway-ai-review-2026.md · Resolve 20: https://www.provideocoalition.com/davinci-resolve-20-released/
Open source: https://github.com/PeterL1n/RobustVideoMatting · https://developers.google.com/edge/mediapipe/solutions/vision/image_segmenter · https://dev.to/kiarina/removing-a-portrait-background-with-birefnet-onnx-on-cpu-gbj · https://learnopencv.com/matanyone-for-better-video-matting/ · https://github.com/wyattblue/auto-editor · https://github.com/lagmoellertim/unsilence · https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator · https://pypi.org/project/cut-fx/ · https://www.remotion.dev/docs/license-pricing-compliance/faq · https://huggingface.co/ai4bharat/indic-parler-tts · https://huggingface.co/hexgrad/Kokoro-82M · https://huggingface.co/ai4bharat/indictrans2-indic-en-dist-200M · https://huggingface.co/facebook/nllb-200-distilled-600M/blob/main/README.md · https://collabora.com/news-and-blog/news-and-events/breaking-language-barriers-20-moving-closer-production-ready-hindi-asr.html · https://www.promptquorum.com/power-local-llm/local-whisper-stt-comparison-2026 · https://sievedata.com/blog/eye-contact-correction-gaze-correction-api · https://forum.manjaro.org/t/gaze-redirecton-on-pre-recorded-videos/166567 · https://github.com/woodrex83/ROCm-For-RX580 · https://help.pexels.com/hc/en-us/articles/900005852323 · https://blog.laozhang.ai/en/posts/free-image-api.md · https://developers.giphy.com/docs/api · https://www.premiumbeat.com/blog/29-free-luts-for-video/ · https://funemojis.lovable.app/licensing · https://gittrend.io/repo/CPJKU/beat_this
