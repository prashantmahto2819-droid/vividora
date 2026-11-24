// Tutorials: one short lesson per page of Vividora and per tab of the editor.
// Used three ways: the ⓘ button (top corner of every page → the lesson of THAT page), the "सीखें" page (#/help — all
// lessons, searchable), and the first-login tour. Plain text on purpose: it loads instantly and works offline.
// A lesson: { t: title, w: what it is for (one line), s: [steps], tip?: [tips], go?: hash to open }

export const LESSONS = {
  // ───────── pages ─────────
  home: { t: "Home", w: "आज क्या करना है — एक नज़र में।", go: "#/",
    s: ["ऊपर के बड़े बटन से सीधे Record, Upload, Montage या Thumbnail शुरू करें।", "“जाँच बाकी” वाले projects सबसे ऊपर दिखते हैं — उन्हें खोलकर कट देखें और मंज़ूरी दें।", "बाएँ menu (phone पर ☰) से हर हिस्से में जाएँ। जिस page पर हों, ऊपर कोने का ⓘ उसी page का तरीका बताता है।"],
    tip: ["कोई काम पीछे चल रहा हो (render, transcript) तो Projects में ⏳ दिखता है — page खुला रखना ज़रूरी नहीं।"] },
  projects: { t: "Projects", w: "आपकी सारी वीडियो — बनती हुई और तैयार।", go: "#/projects",
    s: ["किसी project पर click करें → editor खुलता है।", "Status पढ़ें: “कट जाँचें” = आपकी बारी; “render हो रहा है” = इंतज़ार; “तैयार” = download / publish।", "⋯ menu से नाम बदलें, copy बनाएँ या हटाएँ।"],
    tip: ["हटाया हुआ project वापस नहीं आता — पहले तैयार वीडियो download कर लें।"] },
  record: { t: "Record (camera + teleprompter)", w: "Browser से ही वीडियो record करें — script सामने चलती रहती है।", go: "#/record",
    s: ["Camera और mic की अनुमति दें (browser पूछेगा)।", "Script चिपकाएँ → teleprompter में दिखेगी; speed और अक्षर का size ठीक करें।", "“Mic boost” Auto पर रखें — phone पर धीमी आवाज़ अपने-आप ऊँची होती है। ऊपर का level हरा रहना चाहिए।", "🔴 Record दबाएँ, बोलें, ⏹ रोकें। गलती हो तो वही line दोबारा बोल दें — Vividora पुराना वाला काट देता है।", "“Upload करके edit करें” → project बनता है और Autopilot काम शुरू कर देता है।"],
    tip: ["Phone को सीधा (9:16) या आड़ा (16:9) पहले तय कर लें — बीच में मत घुमाएँ।", "शांत कमरा + चेहरे पर सामने से रोशनी = आधी editing बच जाती है।"] },
  new: { t: "Upload", w: "पहले से बनी recording या clips डालें।", go: "#/new",
    s: ["फ़ाइल चुनें (या खींचकर छोड़ें)। कई clips एक साथ भी दे सकते हैं।", "Transcript चुनें: “बनाएँ” (captions और text-edit के लिए), “छोड़ें” (सिर्फ़ visual edit), या “मेरे पास SRT है” (कहीं और edit हुई वीडियो + उसकी subtitle फ़ाइल — तुरंत, बिना खर्च)।", "Autopilot चालू रखें तो कट, captions, music और thumbnail अपने-आप बनते हैं; बंद रखें तो सब कुछ आप खुद करेंगे।", "“शुरू करें” → upload टूट जाए तो वहीं से आगे चलता है।"],
    tip: ["लंबी recording (8 मिनट से ऊपर) का transcript cloud पर तेज़ बनता है — Settings → API & Keys → Guide देखें।"] },
  edit: { t: "Timeline Editor (सीधा edit)", w: "वीडियो डालें और बिना Autopilot के खुद edit करें।", go: "#/new?quick=1",
    s: ["वीडियो चुनें → सीधे editor खुलता है।", "नीचे timeline है, बीच में preview, बाएँ tabs (कट, Text, Effects…)।", "Editor के अंदर हर tab का अपना ⓘ तरीका है — tab बदलकर ⓘ दबाएँ।"] },
  montage: { t: "Montage (clips + गाना = reel)", w: "बिना बोले वाली clips को गाने की beat पर काटकर reel बनाना।", go: "#/new?type=montage",
    s: ["Clips चुनें (5–20 अच्छी रहती हैं) और एक गाना (Library से या upload)।", "लंबाई, format (9:16 / 16:9) और theme चुनें → “बनाओ”।", "बनने के बाद editor खुलता है: हर कट एक block है — खींचकर जगह बदलें, किनारे से छोटा-बड़ा करें, clip बदलें, effect / speed चुनें।", "Text डालना हो तो Montage tab में लिखें; preview पर खींचकर जगह और size बदलें।", "अपनी आवाज़ में कुछ बोलना हो (शायरी, बात): Audio tab → “अपनी आवाज़ में बोलें” — recording upload करें, mic से record करें, या script लिखकर AI आवाज़ बनाएँ।", "Export → नया reel बनता है।"],
    tip: ["आवाज़ चुनने पर music उसके नीचे अपने-आप धीमा हो जाता है।", "“आवाज़ कब शुरू हो” से तय करें कि बोलना किस सेकंड से शुरू हो।"] },
  "yt-shorts": { t: "YT → Shorts", w: "YouTube की लंबी वीडियो से Shorts / Reels निकालना।", go: "#/yt-shorts",
    s: ["अपनी वीडियो का link चिपकाएँ।", "Vividora उसे उतारकर सबसे अच्छे हिस्से सुझाता है।", "जो चाहिए वे चुनें → 9:16 में captions के साथ बनते हैं।"],
    tip: ["सिर्फ़ अपनी या इजाज़त वाली वीडियो इस्तेमाल करें।"] },
  documentary: { t: "Auto Documentary", w: "एक विषय लिखें — script, आवाज़, visuals और music के साथ पूरी वीडियो।", go: "#/documentary",
    s: ["विषय या पूरी script लिखें।", "आवाज़, भाषा, आकार (आड़ा / खड़ा) और music चुनें।", "“Plan” में हर scene की line और तस्वीर देखें, बदलें।", "“बनाओ” → कुछ मिनट में वीडियो; फिर चाहें तो editor में खोलकर और सुधारें।"] },
  compress: { t: "Compress", w: "वीडियो का size छोटा करना (WhatsApp / mail के लिए)।", go: "#/compress", s: ["वीडियो डालें → कितना छोटा चाहिए चुनें → download।"] },
  thumbs: { t: "Thumbnails", w: "YouTube thumbnail — सबसे अच्छा frame, बड़ा text, कई layout।", go: "#/thumbs",
    s: ["Project चुनें (या अपनी photo डालें)।", "Vividora अच्छे frames सुझाता है — एक चुनें।", "Text लिखें, layout और रंग बदलें; “cutout” से आप पीछे के रंग से अलग दिखते हैं।", "A/B के लिए 2–3 variant बनाकर download करें।"] },
  templates: { t: "Templates", w: "तैयार design — text, रंग और अंदाज़ एक click में।", go: "#/templates", s: ["अपने काम के हिसाब से template चुनें।", "“इस्तेमाल करें” → नया project उसी अंदाज़ में शुरू होता है।"] },
  voicestudio: { t: "Voice Studio (TTS)", w: "Text लिखें → आवाज़ की फ़ाइल।", go: "#/voicestudio",
    s: ["Text लिखें, model / आवाज़ और speed चुनें।", "“बनाओ” → सुनें → Library में रखें या download करें।"],
    tip: ["यह page आपके अपने server वाली VoiceStudio आवाज़ों का है (निजी इस्तेमाल)। fal.ai / RunPod की आवाज़ें और “मेरी अपनी आवाज़” editor के AI voice-over में मिलती हैं।"] },
  characters: { t: "Characters (2D)", w: "Animated पात्र जो आपकी script बोलते हैं।", go: "#/characters", s: ["पात्र चुनें या नया बनाएँ (रंग, कपड़े, चेहरा)।", "Scenes में इसे बात करवाएँ।"] },
  scenes: { t: "Scenes", w: "पात्रों से छोटी कहानी / explainer वीडियो।", go: "#/scenes", s: ["Script लिखें: `नाम: बात` हर line पर।", "हर पात्र की आवाज़ चुनें → “बनाओ”।"] },
  characters3d: { t: "3D Studio", w: "3D पात्र और दृश्य।", go: "#/characters3d", s: ["पात्र और animation चुनें, lines लिखें।", "Camera और background तय करें → render।"] },
  image3d: { t: "Image → 3D", w: "एक photo से 3D model (.glb)।", go: "#/image3d", s: ["साफ़ background वाली photo डालें → model बनता है → download या 3D Studio में इस्तेमाल।"] },
  plan: { t: "Plan", w: "Ideas → script → record की योजना।", go: "#/plan", s: ["Idea जोड़ें (या Trends से लें)।", "“Script बनाओ” → AI पहला draft लिखता है; उसे अपने शब्दों में ठीक करें।", "“Record” → वही script teleprompter में खुलती है।"] },
  trends: { t: "Trends", w: "आज क्या चल रहा है — आपके विषय में।", go: "#/trends", s: ["अपना विषय / पसंदीदा channels चुनें।", "कोई trend पसंद आए → “Idea बनाओ” → Plan में चला जाता है।"] },
  analytics: { t: "Analytics", w: "कौन सी वीडियो क्यों चली।", go: "#/analytics", s: ["Channel जोड़ा हो तो views, रुकने का समय और सबसे अच्छे hooks दिखते हैं।", "“सीख” वाले card पढ़ें — अगली वीडियो में वही दोहराएँ।"] },
  dashboard: { t: "Dashboard", w: "सारे आँकड़े: projects, render, जगह।", go: "#/dashboard", s: ["यहाँ सिर्फ़ देखना है — कुछ अटका हो तो यहीं दिखता है।"] },
  copilot: { t: "Copilot", w: "Vividora से सवाल पूछें / काम करवाएँ।", go: "#/copilot", s: ["लिखें क्या चाहिए (“पिछली वीडियो का title सुझाओ”)।", "जवाब के नीचे के बटन से सीधे वह काम करें।"] },
  publish: { t: "Publish", w: "YouTube / Instagram / Facebook पर डालना — आपकी मंज़ूरी के बाद ही।", go: "#/publish",
    s: ["पहले Channels & Brand में platform जोड़ें।", "तैयार वीडियो चुनें, title / description / hashtags देखें (AI सुझाव बदल सकते हैं)।", "अभी डालें या समय तय करें।"],
    tip: ["Auto-upload बंद है: कोई भी वीडियो आपके “हाँ” के बिना नहीं जाती।"] },
  library: { t: "Library", w: "आपकी सारी सामग्री: music, sounds, clips, photos, stickers, logo, fonts, LUT।", go: "#/library",
    s: ["ऊपर से प्रकार चुनें (Music, Sounds, Clips…)।", "“Upload” से अपनी फ़ाइलें जोड़ें — वे हर project में मिलेंगी।", "खोज में नाम, tag, या (Gemini ने देखा हो तो) “क्या दिख रहा है” लिखें — जैसे “पहाड़”।", "Music पर mood / BPM के tag अपने-आप लगते हैं; गलत हों तो बदल दें।"],
    tip: ["अपनी आवाज़ का नमूना नाम `myvoice` से रखें — “मेरी अपनी आवाज़” वही इस्तेमाल करती है।", "Starter सामग्री licence-safe है; अपनी डाली चीज़ों की ज़िम्मेदारी आपकी है।"] },
  settings: { t: "Channels & Brand", w: "हर channel की पहचान: logo, रंग, font, caption का अंदाज़।", go: "#/settings",
    s: ["Channel बनाएँ / चुनें।", "Brand kit भरें: logo, रंग, font, caption style, grade।", "नया project बनते ही यह सब अपने-आप लग जाता है।", "नीचे YouTube / Instagram जोड़ें।"] },
  account: { t: "Account & Security", w: "नाम, password, 2-step login।", go: "#/account", s: ["Password बदलें।", "2FA चालू करें: authenticator app से QR scan करें।"] },
  api: { t: "API & Keys", w: "बाहर की services की keys, खर्च, और हर switch का मतलब।", go: "#/api",
    s: ["“🔑 keys जोड़ें”: key चिपकाएँ → Save → तुरंत चालू। हर line के नीचे “ℹ️ इससे क्या होगा”।", "“💰 खर्च”: इस महीने कितना लगा, किस पर; सीमा यहीं से।", "“📖 Guide”: कौन सा काम कहाँ चलता है, हर switch से क्या बदलता है, जाँचने का क्रम।", "“🔌 Vividora की API”: अपने दूसरे software से Vividora चलाने की key।"],
    tip: ["पहले खर्च-सीमा लगाएँ, फिर keys डालें।"] },
  users: { t: "Users", w: "Team के लोग और उनकी अनुमति।", go: "#/users", s: ["“Invite” से link भेजें।", "Role: viewer (सिर्फ़ देखना), editor (बनाना), admin (सब कुछ)।"] },
  status: { t: "Status", w: "Server ठीक चल रहा है या नहीं।", go: "#/status", s: ["Workers हरे = काम हो रहा है। लाल हो तो server पर `docker compose ps` देखें।"] },
  help: { t: "सीखें (Help)", w: "सारे तरीके एक जगह।", go: "#/help", s: ["नीचे खोजें या कोई विषय खोलें।", "किसी भी page पर ऊपर कोने का ⓘ उसी page का तरीका खोलता है।"] },

  // ───────── editor ─────────
  editor: { t: "Editor — बुनियाद", w: "एक screen पर सब: preview, timeline, tabs।",
    s: ["बीच में preview: जो यहाँ दिखता है वही बनेगा। ऊपर 9:16 / 16:9 / 1:1 बदलें।", "नीचे timeline: V1 = आपकी वीडियो, ऊपर Text / Effect / Overlay की पट्टियाँ, नीचे Audio।", "किसी भी चीज़ पर click करें → दाईं ओर उसकी settings। खींचें = जगह बदलें, किनारा खींचें = लंबाई।", "Space = चलाएँ / रोकें · S = काटें · Del = हटाएँ · Ctrl+Z = वापस · Ctrl+C / V = copy / paste।", "बदलाव अपने-आप सेव होते हैं (ऊपर “सेव ✓”)।", "Export → format चुनें → “बनाओ”।"],
    tip: ["Phone पर timeline को दो उँगलियों से zoom करें।", "कुछ बिगड़ जाए तो Ctrl+Z कई बार दबा सकते हैं।"] },
  "tab:cuts": { t: "कट (Cuts)", w: "चुप्पी, अं-आं और दोबारा बोली lines हटाना।",
    s: ["ऊपर “सफ़ाई का हिसाब”: कितना हटा और किस वजह से; एक वजह पूरी बंद / चालू कर सकते हैं।", "हर कट की line पर ▶ से सुनें; गलत कट हो तो उसका switch बंद करें।", "खुद काटना हो: timeline पर I और O से हिस्सा चुनें → X।", "Text से काटना: Captions tab में शब्द चुनकर हटाएँ।"],
    tip: ["शोर वाली recording में कट ठीक न लगें तो API & Keys में “चुप्पी कैसे पहचानें” = Silero आज़माएँ।"] },
  "tab:media": { t: "Media", w: "अपनी clips और photos वीडियो पर लगाना।", s: ["Clip को timeline पर खींचें या “+” दबाएँ।", "लगी हुई clip चुनें → पूरी screen / छोटी खिड़की / आज़ाद (खींचकर)।", "Photo पर “Ken Burns” से धीमा zoom / pan; “frame” से border, गोल कोने, shadow।"] },
  "tab:audio": { t: "Audio", w: "Music, sound effects, आवाज़ साफ़ करना, AI voice-over।",
    s: ["Music: Library से “लगाएँ”; volume और “बोलते समय धीमा” चुनें। पसंद का न मिले तो “AI से नया music”।", "Voice: “studio” preset आवाज़ साफ़ करता है; “बदलाव सुनें” से पहले सुन लें।", "Sound effect: timeline पर छोड़ें; volume की रेखा पर बिंदु जोड़कर धीमा-तेज़ करें।", "AI voice-over: script लिखें → आवाज़ चुनें (“मेरी अपनी आवाज़” के लिए नमूना upload करें) → “बनाएँ” → “इसे इस्तेमाल करें”।"] },
  "tab:studio3d": { t: "3D & Voice", w: "झटपट voice-over और 3D पात्र।", s: ["Text लिखें → आवाज़ चुनें → “आवाज़ बनाओ और timeline में लगाओ”।", "3D पात्र चुनकर उससे line बुलवाएँ।"] },
  "tab:text": { t: "Text", w: "Title और लिखावट।", s: ["Style चुनें → text लिखें → timeline पर आ जाता है।", "Preview पर खींचें = जगह, कोना खींचें = size।", "Animation (आना / जाना) और रंग दाईं ओर से।"] },
  "tab:stickers": { t: "Stickers", w: "Emoji, GIF, तीर, subscribe बटन।", s: ["Sticker चुनें → preview पर खींचकर रखें।", "Animation चुनें (pop, bounce, float…)।"] },
  "tab:effects": { t: "Effects", w: "Zoom, glitch, blur, shake…", s: ["“पूरे video पर” या “सिर्फ़ इस हिस्से पर” चुनें।", "हिस्से वाला effect timeline की FX पट्टी पर clip बनकर आता है — खींचें, काटें।", "“Close-up (पास से)”: किसी हिस्से में चेहरे पर zoom — कितना पास और कहाँ, खुद तय करें।"] },
  "tab:transitions": { t: "Transitions", w: "एक कट से दूसरे में जाने का अंदाज़।", s: ["Default चुनें (सब कटों पर) या किसी एक कट पर अलग।", "कम इस्तेमाल करें — हर कट पर चमक थका देती है।"] },
  "tab:color": { t: "Filters / रंग", w: "वीडियो का look।", s: ["Preset चुनें, फिर “strength” से हल्का करें।", "अपना LUT हो तो Library में डालकर यहाँ चुनें।"] },
  "tab:pro": { t: "Pro", w: "Stabilize, denoise, sharpen, speed, mask।", s: ["हिलती वीडियो: Stabilize। कम रोशनी: Denoise।", "Final में ही चालू करें — render धीमा होता है।"] },
  "tab:captions": { t: "Captions", w: "बोले हुए शब्द screen पर।",
    s: ["Style चुनें (karaoke, pop, line…), size और जगह बदलें।", "गलत शब्द: list में सीधे ठीक करें; एक line दोबारा सुनवानी हो तो “🔁”।", "“📄 SRT से transcript”: दूसरे software की subtitle फ़ाइल यहीं डालें।", "Podcast में speaker जाँच के बाद हर line पर बोलने वाले का नाम दिखता है।"] },
  "tab:body": { t: "Cutout", w: "आपको background से अलग करना।", s: ["“Cutout बनाएँ” (एक बार, कुछ मिनट)।", "फिर background बदलें: blur, रंग, photo, वीडियो; या आपके चारों ओर outline / glow।"] },
  "tab:overlay": { t: "Overlay", w: "Logo, frame, watermark।", s: ["Logo चुनें → कोना और size।", "Brand kit में logo हो तो अपने-आप लगा रहता है।"] },
  "tab:shorts": { t: "Shorts", w: "लंबी वीडियो से छोटे clips।", s: ["“Shorts ढूँढो” → सबसे अच्छे हिस्से title के साथ।", "जो चाहिए चुनें, शुरू / अंत ठीक करें → “बनाओ”।", "Podcast में speaker जाँच हो चुकी हो तो खिड़की बोलने वाले पर रहती है।"] },
  "tab:ai": { t: "AI Studio", w: "Podcast के औज़ार और आवाज़ से visuals।",
    s: ["Supporting clips: बात से जुड़ी clips / photos डालें → “सही जगह ढूँढो” → देखकर “लगाओ”।", "बोलने वाले पर कैमरा: “जाँचो” → हर shot देखें / बदलें → “timeline पर लगाओ”। दूसरा कैमरा हो तो उसकी फ़ाइल चुनें।", "आवाज़ से visuals: हर line के लिए stock / AI तस्वीर के सुझाव।"],
    tip: ["Speaker close-up लगाने के बाद कट बदलें तो “दोबारा बैठाओ” दबाएँ।"] },
  "tab:refs": { t: "Refs", w: "किसी वीडियो का अंदाज़ देखकर सीखना।", s: ["Reference का link / फ़ाइल दें → उसका pace, text का अंदाज़, music का mood नोट होता है।"] },
  "tab:montage": { t: "Montage tab", w: "Beat पर कटा reel — plan बदलना।", s: ["Look, pace, effects का स्तर चुनें → “दोबारा plan बनाओ”।", "Text यहाँ लिखें; preview पर खींचकर रखें।", "अपनी आवाज़: Audio tab → “अपनी आवाज़ में बोलें”।"] },
};

// which lesson belongs to the place the user is in right now
export function lessonKey(route, hash, edTab) {
  const k = route?.kind || "home";
  if (k === "projects" && route.id) return edTab && LESSONS["tab:" + edTab] ? "tab:" + edTab : "editor";
  if (k === "new") return /type=montage/.test(hash || "") ? "montage" : /quick=1/.test(hash || "") ? "edit" : "new";
  return LESSONS[k] ? k : "help";
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export function lessonHtml(key, { link = true } = {}) {
  const L = LESSONS[key]; if (!L) return "";
  return `<h3 style="margin:0 0 .2rem">${esc(L.t)}</h3><p class="small muted" style="margin:0 0 .6rem">${esc(L.w)}</p>
    <ol class="lrn-steps">${L.s.map((x) => `<li>${esc(x).replace(/`([^`]+)`/g, "<code>$1</code>")}</li>`).join("")}</ol>
    ${L.tip ? `<div class="lrn-tip">${L.tip.map((x) => `<p>💡 ${esc(x).replace(/`([^`]+)`/g, "<code>$1</code>")}</p>`).join("")}</div>` : ""}
    ${link && L.go ? `<p style="margin:.7rem 0 0"><a class="btn small" href="${L.go}" data-lrn-go>यह page खोलें →</a></p>` : ""}`;
}
// the drawer opened by the ⓘ button
export function openLesson(key) {
  closeLesson();
  const d = document.createElement("div"); d.id = "lrn-drawer";
  const isTab = key.startsWith("tab:") || key === "editor";
  d.innerHTML = `<div class="lrn-scrim" data-lrn-x></div><aside class="lrn-panel" role="dialog" aria-label="तरीका">
    <div class="lrn-head"><b>ⓘ यह कैसे इस्तेमाल करें</b><button class="ibtn" data-lrn-x aria-label="बंद करें">✕</button></div>
    <div class="lrn-body">${lessonHtml(key, { link: false })}${isTab && key !== "editor" ? `<hr class="lrn-hr">${lessonHtml("editor", { link: false })}` : ""}
      <p style="margin:1rem 0 0"><a href="#/help" data-lrn-x>📚 सारे तरीके देखें</a></p></div></aside>`;
  document.body.appendChild(d);
  d.querySelectorAll("[data-lrn-x]").forEach((b) => b.addEventListener("click", () => closeLesson()));
  d._esc = (e) => { if (e.key === "Escape") closeLesson(); }; document.addEventListener("keydown", d._esc);
}
export function closeLesson() { const d = document.getElementById("lrn-drawer"); if (d) { document.removeEventListener("keydown", d._esc); d.remove(); } }
// the "सीखें" page: every lesson, grouped, with a search box
const GROUPS = [["शुरुआत", ["home", "projects", "editor"]], ["वीडियो बनाना", ["record", "new", "edit", "montage", "yt-shorts", "documentary", "compress"]],
  ["Editor के tabs", ["tab:cuts", "tab:captions", "tab:audio", "tab:text", "tab:media", "tab:effects", "tab:transitions", "tab:color", "tab:stickers", "tab:overlay", "tab:body", "tab:shorts", "tab:ai", "tab:pro", "tab:studio3d", "tab:refs", "tab:montage"]],
  ["Design · आवाज़ · 3D", ["thumbs", "templates", "voicestudio", "characters", "scenes", "characters3d", "image3d"]],
  ["Channel बढ़ाना", ["plan", "trends", "analytics", "dashboard", "copilot", "publish"]], ["Library और Settings", ["library", "settings", "account", "api", "users", "status"]]];
export function learnPageHtml() {
  return `<div class="lrn-search"><input id="lrn-q" type="search" placeholder="खोजें: जैसे “captions”, “आवाज़”, “SRT”, “montage”…" autocomplete="off"></div>
    ${GROUPS.map(([g, keys]) => `<section class="lrn-grp"><h2>${g}</h2><div class="lrn-list">${keys.filter((k) => LESSONS[k]).map((k) => `<details class="lrn-item" data-lrn="${k}" data-text="${esc((LESSONS[k].t + " " + LESSONS[k].w + " " + LESSONS[k].s.join(" ") + " " + (LESSONS[k].tip || []).join(" ")).toLowerCase())}"><summary><b>${esc(LESSONS[k].t)}</b><span class="small muted"> — ${esc(LESSONS[k].w)}</span></summary><div class="lrn-in">${lessonHtml(k)}</div></details>`).join("")}</div></section>`).join("")}
    <p class="small muted" id="lrn-none" hidden>कुछ नहीं मिला — दूसरा शब्द आज़माएँ।</p>`;
}
export function learnPageBind(root = document) {
  const q = root.querySelector("#lrn-q"); if (!q) return;
  q.oninput = () => { const v = q.value.trim().toLowerCase(); let n = 0;
    root.querySelectorAll(".lrn-item").forEach((el) => { const hit = !v || el.dataset.text.includes(v); el.hidden = !hit; if (hit) n++; if (v && hit) el.open = n <= 3; if (!v) el.open = false; });
    root.querySelectorAll(".lrn-grp").forEach((g) => { g.hidden = ![...g.querySelectorAll(".lrn-item")].some((el) => !el.hidden); });
    root.querySelector("#lrn-none").hidden = n > 0; };
  const want = (location.hash.split("?")[1] || "").match(/(?:^|&)t=([^&]+)/); if (want) { const el = root.querySelector(`.lrn-item[data-lrn="${decodeURIComponent(want[1])}"]`); if (el) { el.open = true; el.scrollIntoView({ block: "center" }); } }
}
export const LEARN_CSS = `.lrn-fab{position:fixed;top:.7rem;right:.8rem;z-index:60;width:34px;height:34px;border-radius:50%;border:1px solid var(--line);background:var(--panel);color:var(--text);font-weight:700;font-size:1rem;cursor:pointer;box-shadow:0 2px 10px #0005;display:flex;align-items:center;justify-content:center}
.lrn-fab:hover{border-color:var(--accent,#F2B33D);color:var(--accent,#F2B33D)}
@media(max-width:900px){.lrn-fab{top:60px;right:.6rem;width:30px;height:30px;opacity:.92}}
.lrn-fab.in-editor{top:auto;bottom:12px;right:60px;width:32px;height:32px}
.lrn-scrim{position:fixed;inset:0;background:#0008;z-index:200}
.lrn-panel{position:fixed;top:0;right:0;bottom:0;width:min(440px,100vw);background:var(--panel);border-left:1px solid var(--line);z-index:201;display:flex;flex-direction:column;box-shadow:-8px 0 30px #0007}
.lrn-head{display:flex;align-items:center;justify-content:space-between;padding:.8rem 1rem;border-bottom:1px solid var(--line)}
.lrn-body{padding:1rem;overflow-y:auto;padding-bottom:calc(1.5rem + env(safe-area-inset-bottom,0px))}
.lrn-steps{margin:0;padding-left:1.3rem}.lrn-steps li{margin:.45rem 0;line-height:1.5;font-size:.92rem}
.lrn-tip{margin-top:.7rem;padding:.55rem .7rem;border-radius:8px;background:var(--bg);border:1px solid var(--line)}.lrn-tip p{margin:.2rem 0;font-size:.85rem}
.lrn-hr{border:0;border-top:1px solid var(--line);margin:1.1rem 0}
.lrn-search input{width:100%;padding:.7rem .9rem;border-radius:10px;border:1px solid var(--line);background:var(--panel);color:var(--text);font-size:1rem}
.lrn-grp h2{font-size:1rem;margin:1.3rem 0 .5rem;opacity:.8}
.lrn-item{background:var(--panel);border:1px solid var(--line);border-radius:10px;margin-bottom:.4rem}
.lrn-item summary{padding:.65rem .9rem;cursor:pointer;list-style-position:inside}.lrn-in{padding:.2rem 1rem 1rem}`;
