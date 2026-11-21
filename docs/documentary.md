# Auto Documentary

**Topic (या अपनी script) → scenes → narration → तस्वीरें → sound → पूरा MP4** (Library में, kind "B-roll", tags `documentary`).
Dashboard → **Auto Documentary** (`#/documentary`), या API `/api/v1/documentary/plan` + `/build`, या Claude से MCP tool `vividora_documentary_*`।

## कैसे चलता है
1. **Scenes:** Topic दें तो AI (`GEMINI_API_KEY` या `ANTHROPIC_API_KEY`, `.env` में) हर scene की narration + तस्वीर के English keywords बनाता है। Key न हो तो **अपनी script** दें — खाली लाइन = नया scene।
2. आप scenes **जाँचकर बदल** सकते हैं (text, keywords, हटाना)।
3. **Build:** हर scene की आवाज़ बनती है; scene की लंबाई = आवाज़ + 0.45 s (कम से कम 2.8 s)। तस्वीर:
   1. आपकी Library की image/B-roll जिसके नाम/tags keywords से मिलें,
   2. नहीं तो **Pixabay** video (अगर `PIXABAY_API_KEY` है; free key: https://pixabay.com/api/docs/),
   3. नहीं तो एक सादा **title card** — scene कभी खाली नहीं रहता।
   फिर Ken-Burns zoom (image) / loop-crop (video), हर scene change पर हल्की whoosh, वैकल्पिक music (आवाज़ के नीचे दबकर), loudness -16 LUFS।
4. नतीजा Library में। साथ में **YouTube description** मिलती है: chapters (0:00 से, हर chapter ≥10 s — scenes जुड़कर), footage credits, और "AI voice" का नोट — copy करके सीधे डालें।
5. हर scene के लिए आप Library से **ख़ुद तस्वीर चुन** सकते हैं (dropdown); बाकी scenes अपने-आप भरते हैं। Pixabay पर video न मिले तो photo लगती है।

## आवाज़ और licence
- Default आवाज़ **commercial-safe** engine की चुनी जाती है (Kokoro / Parler)। Voice Studio (OmniVoice) की आवाज़ पर ⚠ दिखता है — वह **सिर्फ़ निजी/non-commercial** है, public/monetised वीडियो में न लगाएँ।
- Kokoro Hindi (`hi_kokoro_alpha`, `hi_kokoro_omega`) जुड़ गई हैं — हल्का CPU model, quality सुनकर तय करें।

## मुफ़्त AI अपनी मशीन पर (Ollama) — वैकल्पिक
`.env` में Gemini/Claude key की जगह अपना model चला सकते हैं (free, offline): `OLLAMA_URL=http://host.docker.internal:11434` और `OLLAMA_MODEL=qwen2.5:7b`।
`LLM_PROVIDER=ollama` से इसे ज़बरदस्ती चुनें (वरना Gemini → Claude → Ollama क्रम है)।
⚠ CPU पर 7B model धीमा है (एक script में कई मिनट) और **हिंदी की गुणवत्ता Gemini से कमज़ोर** — पहले English/Hinglish में आज़माएँ।
Setup (VM पर):
1. `curl -fsSL https://ollama.com/install.sh | sh`
2. `ollama pull qwen2.5:7b`
3. Docker से पहुँचने के लिए: `sudo systemctl edit ollama` → नीचे दो लाइनें डालें → save:
   ```
   [Service]
   Environment="OLLAMA_HOST=0.0.0.0:11434"
   ```
   फिर `sudo systemctl restart ollama` (यह port सिर्फ़ आपके LAN में खुलता है; router से बाहर forward न करें)।
4. `.env` में ऊपर की दो लाइनें, फिर `docker compose --profile tunnel up -d`।
5. जाँच: `curl http://127.0.0.1:11434/api/tags`

## अभी की सीमाएँ (Phase 1)
- Scene-by-scene timeline editing UI नहीं — वीडियो सीधा MP4 बनता है (Captions burned-in आते हैं; बंद करने का checkbox है)।
- Topic से plan करते समय Wikipedia के intro extracts prompt में जाते हैं और AI को कहा जाता है कि संख्या/तारीख़/नाम सिर्फ़ उन्हीं से लें; इस्तेमाल हुए pages YouTube description में "Sources (Wikipedia, CC BY-SA 4.0)" बनकर जुड़ते हैं। बंद करने के लिए `"ground": false` या UI का checkbox।
- Build के बाद एक **thumbnail** (फ़िल्म का frame + title) Library में image (`documentary,thumbnail`) की तरह सेव होता है।
- UI में हर scene के नीचे दिखता है कि Library से कौन-सी तस्वीर मिलेगी (`POST /documentary/preview`)।
- **AI तस्वीरें (GPU API):** Library में match न मिले तो scene की `visual` से FLUX.1-schnell image बनती है (पहले Cloudflare Workers AI, फिर Hugging Face; `AI_IMAGE_PROVIDER` से चुनें)। GPU इस server पर नहीं, API पर चलता है। description में "AI-generated image — synthetic" लिखा आता है; YouTube पर realistic AI तस्वीरों के लिए upload के समय **altered/synthetic content** वाला विकल्प ख़ुद चुनें। बंद: `"ai_images": false`।
- AI जो facts लिखे उन्हें **publish से पहले ख़ुद जाँचें**; script में वही नाम/तारीख़ें रखें जिन पर भरोसा हो।
- तस्वीरें: Library → AI image → Pixabay → title card। AI *video* clips वैकल्पिक हैं (नीचे देखें); बाक़ी तस्वीरों में Ken-Burns zoom लगता है।
- एक workspace में एक साथ एक ही documentary बनती है; ज़्यादा से ज़्यादा 24 scenes, 9000 अक्षर।

## API
```
POST /api/v1/documentary/plan   {"topic":"हिमालय कैसे बना","minutes":3,"language":"hi","ground":true}   (या {"script":"…"}) → {title, scenes, sources}
POST /api/v1/documentary/build  {"title":"…","scenes":[{"narration":"…","visual":"aerial himalaya"}],"voice":"hi_kokoro_alpha","orientation":"landscape"}  → 202 {job_id}
GET  /api/v1/jobs/{job_id}      → status, file (डाउनलोड: GET /api/v1/files/{id})
```


## Studio extras
- **Timeline editing:** हर scene ▲▼ से ऊपर/नीचे, ⧉ से copy, 🗑 से हटाना; "कम से कम इतने सेकंड" (`hold`, 0–30) से scene लंबा रखें; Music की आवाज़ का slider (`music_volume`)। काम अधूरा हो तो **💾 Draft** सेव करें और बाद में 📂 से खोलें (`/documentary/drafts`)।
- **Shorts/Reels:** "✂ Shorts निकालो" scenes में से 20–58 सेकंड के सबसे अच्छे लगातार हिस्से चुनता है (hook/सवाल/संख्या वाले पहले); चुने हुए हिस्से 9:16 में captions के साथ एक-एक करके बनते हैं, titles में `#Shorts`। API: `POST /api/v1/documentary/shorts {scenes, count, build, pick}`।
- **Series:** topic → AI episodes की list → आप नाम बदलें → "पूरी series बनाओ": हर episode की scenes AI लिखता है (बाक़ी episodes के नाम देकर, ताकि दोहराव न हो), एक के बाद एक बनती हैं, description में पूरी series की list आती है। API: `POST /api/v1/documentary/series` (`build:false` outline, `build:true` + `episodes[]`)। Batch का नतीजा `/v1/jobs/{id}` के `items[]` में।
- **YouTube private draft:** फ़िल्म बनने पर "⬆ Private draft के रूप में upload" — आपके connected channel पर **हमेशा private** (public नहीं होता), title/description/thumbnail के साथ; AI तस्वीरें लगी हों तो YouTube का "synthetic content" flag अपने-आप लगता है। देखकर publish आप YouTube Studio में ख़ुद करें। `PUBLISH_DRY_RUN=1` हो तो असल upload नहीं होता।
- सीमाएँ: एक workspace में एक समय एक ही job/batch; Shorts हर बार नए सिरे से (TTS + तस्वीरें) बनते हैं, इसलिए ज़्यादा Shorts = ज़्यादा समय।

## AI video clips (वैकल्पिक, पैसे वाले)
हर scene में "🎥 AI video बनाओ" टिक करने पर उसकी तस्वीर (Library/AI/stock) fal.ai के image-to-video model से 1–3 मिनट में छोटे clip में बदलती है। `.env` में `FAL_KEY` चाहिए (https://fal.ai/dashboard/keys); model `AI_VIDEO_MODEL` से बदलें; एक film में अधिकतम `AI_VIDEO_MAX` (default 4) clips, ताकि बिल सीमित रहे। fail हो तो तस्वीर पर Ken-Burns लगता है और warning दिखती है। description में "AI video — synthetic" जुड़ता है और YouTube का synthetic flag लगता है। **ध्यान:** यह real fal.ai API पर test नहीं हुआ (नक़ली server से जाँचा) — पहले 1 scene से आज़माएँ और fal dashboard में model id/कीमत देख लें।

**कोई भी fal model:** `AI_VIDEO_MODEL` के साथ ज़रूरत हो तो `AI_VIDEO_IMAGE_FIELD`, `AI_VIDEO_PROMPT_FIELD` (ख़ाली = prompt नहीं भेजना), `AI_VIDEO_EXTRA_JSON` (जैसे `{"duration":"5"}`) सेट करें — code बदलने की ज़रूरत नहीं (output `video.url` से पढ़ा जाता है; fal का नियम)। `AI_VIDEO_PRICE_PER_SEC` और `AI_VIDEO_SECONDS` डालने पर scenes के नीचे "इस film में N AI clip ≈ $x" का अंदाज़ा दिखता है।

## Instagram
- **Reel post:** फ़िल्म/Short बनने पर "📸 Instagram Reel" — connected Instagram (Dashboard → Connections → Meta) पर post होता है। YouTube की तरह private draft **नहीं** है: Instagram API draft नहीं देती, इसलिए यह तुरंत live होता है और टिक (`confirm:true`) ज़रूरी है। Instagram वीडियो आपके `PUBLIC_URL` से 48 घंटे के signed link (`/publib/…`) से उठाता है, इसलिए `.env` में `PUBLIC_URL=https://studio.vividbrandify.com` ज़रूरी है। 9:16 (Shorts वाला) सबसे अच्छा। `PUBLISH_DRY_RUN=1` में कुछ नहीं जाता।
- **Analysis:** "4. Instagram analysis" पिछली 12 posts के views / reach / saves / shares / watch time और saves-per-reach दिखाता है (Meta Graph API insights; account Business/Creator + Page से जुड़ा होना चाहिए)। असली Meta API पर test नहीं हुआ — नक़ली server से जाँचा; Meta के metric नाम बदलते हैं (2025 में plays → views), इसलिए code दोनों आज़माता है।
