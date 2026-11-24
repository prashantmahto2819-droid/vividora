# Vividora — Admin guide: keys, switches, where each job runs

यह फ़ाइल `server/vividora/adminguide.py` से बनती है (dashboard → Settings → API & Keys → 📖 Guide में यही दिखता है)।
दाम अंदाज़े हैं; असली bill हर service की अपनी site पर देखें। कोई भी cloud service तभी पैसा लेती है जब कोई काम उसे बुलाए।

## 1. कौन सा काम कहाँ चलता है

### Transcript (बोली हुई बात → शब्द)

| कहाँ | क्या चाहिए | कौन सा switch / कहाँ चुनें | दाम |
|---|---|---|---|
| यह server (Whisper) | — | Transcript कहाँ बने = यह server | मुफ़्त |
| fal.ai Whisper | fal.ai key | Transcript कहाँ बने = fal.ai या Auto | ~$0.006 / मिनट |
| RunPod (अपना endpoint) | RunPod key + Whisper endpoint ID | Transcript कहाँ बने = RunPod | GPU के सेकंड (~$0.0004 / s) |
| SRT / VTT फ़ाइल | — | upload पर “मेरे पास SRT है”, या Captions tab → SRT से transcript | मुफ़्त |

### AI voice-over (text → आवाज़)

| कहाँ | क्या चाहिए | कौन सा switch / कहाँ चुनें | दाम |
|---|---|---|---|
| यह server (Kokoro / Parler / VoiceStudio) | — | voice list में चुनें | मुफ़्त (धीमा) |
| fal.ai — Chatterbox हिन्दी, Kokoro, “मेरी अपनी आवाज़” | fal.ai key | voice list में “(fal.ai)” वाली आवाज़ | ~$0.02–0.025 / 1000 अक्षर |
| RunPod — MiniMax HD, Chatterbox Turbo (English) | RunPod key | voice list में “(RunPod)” वाली आवाज़ | $0.05 / 1000 अक्षर · $0.001 / audio सेकंड |
| ElevenLabs | ElevenLabs key | voice list में ElevenLabs वाली आवाज़ | ~$0.20 / 1000 अक्षर |

### Background music

| कहाँ | क्या चाहिए | कौन सा switch / कहाँ चुनें | दाम |
|---|---|---|---|
| Library / Jamendo | Jamendo client id (खोज के लिए) | Sound tab → music | मुफ़्त |
| AI से नया music (fal.ai) | fal.ai key | Sound tab → “AI से नया music बनाओ” | ~$0.02 / मिनट |

### AI video clip

| कहाँ | क्या चाहिए | कौन सा switch / कहाँ चुनें | दाम |
|---|---|---|---|
| fal.ai (तस्वीर को हिलाना) | fal.ai key | AI video clips कहाँ बनें = Auto / fal.ai | ~$0.03 / सेकंड (अंदाज़ा) |
| RunPod p-video | RunPod key | AI video clips कहाँ बनें = RunPod | $0.02 / सेकंड (720p) |

### AI तस्वीर

| कहाँ | क्या चाहिए | कौन सा switch / कहाँ चुनें | दाम |
|---|---|---|---|
| Cloudflare Workers AI | Cloudflare Account ID + token | — | रोज़ की मुफ़्त सीमा |
| मुफ़्त सार्वजनिक service | — | — | मुफ़्त (धीमी) |

### लिखना / सोचना (title, description, script, clips को देखना)

| कहाँ | क्या चाहिए | कौन सा switch / कहाँ चुनें | दाम |
|---|---|---|---|
| Google Gemini | Gemini key | — | मुफ़्त सीमा के अंदर |
| Claude | Anthropic key | Gemini न हो तब | paid |
| बिना AI | — | — | मुफ़्त (सादे नियम) |

### चुप्पी / filler काटना (auto-cut)

| कहाँ | क्या चाहिए | कौन सा switch / कहाँ चुनें | दाम |
|---|---|---|---|
| यह server — आवाज़ की ऊँचाई | — | चुप्पी कैसे पहचानें = आवाज़ की ऊँचाई से | मुफ़्त |
| यह server — Silero | — | चुप्पी कैसे पहचानें = Silero | मुफ़्त |

### Supporting clips को सही जगह लगाना

| कहाँ | क्या चाहिए | कौन सा switch / कहाँ चुनें | दाम |
|---|---|---|---|
| Gemini (clip खोलकर देखता है) | Gemini key | — | मुफ़्त सीमा के अंदर |
| यह server — OpenCLIP | server WITH_OPENCLIP=1 से बना हो | Clips को तस्वीर देखकर मिलाना = चालू | मुफ़्त |
| सिर्फ़ शब्द / नाम | — | — | मुफ़्त |

### Podcast: बोलने वाले पर कैमरा, render, captions, effects

| कहाँ | क्या चाहिए | कौन सा switch / कहाँ चुनें | दाम |
|---|---|---|---|
| यह server | — | — | मुफ़्त |

## 2. हर key और switch — क्या करने से क्या होगा

### Site

**Site का पता (PUBLIC_URL)** — key · `PUBLIC_URL`

- **भरा हो:** share links, webhook और social login के लिंक इसी पते से बनते हैं (जैसे https://studio.vividbrandify.com)
- **खाली हो:** लिंक में server का अंदरूनी पता आ सकता है — बाहर से नहीं खुलेंगे; Settings में चेतावनी दिखती है

### AI (लिखना / सोचना)

**Google Gemini** — key · `GEMINI_API_KEY`

- **डाली हो:** AI title / description / hashtags, script, Shorts के title, transcript की spelling सुधार, supporting clips को “खोलकर देखना”, visuals के सुझाव — सब चालू
- **न हो:** ये सब सादे नियमों से चलते हैं (कम समझदार); कोई काम रुकता नहीं

**Anthropic (Claude)** — key · `ANTHROPIC_API_KEY`

- **डाली हो:** Gemini न हो तो वही काम Claude से (paid)। दोनों हों तो Gemini पहले
- **न हो:** कुछ नहीं बदलता

### AI image · video · voice

**Cloudflare Account ID** — key · `CLOUDFLARE_ACCOUNT_ID`

- **token के साथ डाली हो:** AI तस्वीरें Cloudflare Workers AI से (रोज़ की मुफ़्त सीमा के अंदर)
- **न हो:** AI तस्वीरें मुफ़्त सार्वजनिक service से (धीमी, कभी-कभी fail)

**Cloudflare API token (Workers AI)** — key · `CLOUDFLARE_API_TOKEN`

- **Account ID के साथ डाली हो:** ऊपर जैसा — दोनों साथ चाहिए
- **न हो:** ऊपर जैसा

**fal.ai** — key · `FAL_KEY`

- **डाली हो:** चार चीज़ें खुलती हैं: (1) तेज़ cloud transcript — अगर नीचे “Transcript कहाँ बने” fal.ai / Auto पर हो, (2) fal.ai की आवाज़ें voice list में — Chatterbox, Kokoro, “मेरी अपनी आवाज़”, (3) AI से background music (Sound tab), (4) AI video clips। हर एक सिर्फ़ इस्तेमाल पर पैसा लेता है
- **न हो:** ये चारों दिखते / चलते नहीं; बाकी सब पहले जैसा

**ElevenLabs** — key · `ELEVENLABS_API_KEY`

- **डाली हो:** ElevenLabs की आवाज़ें voice list में (महँगी, ~$0.20 / 1000 अक्षर)
- **न हो:** वे आवाज़ें list में नहीं दिखतीं

### Stock video · photo · music · sound

**Pixabay** — key · `PIXABAY_API_KEY`

- **डाली हो:** “आवाज़ से visuals” और Library में stock video / photo खोज
- **न हो:** stock खोज बंद; अपनी clips और AI तस्वीरें चलती हैं

**Jamendo (client id)** — key · `JAMENDO_CLIENT_ID`

- **डाली हो:** Library → music में Jamendo के गाने खोजकर जोड़ना
- **न हो:** वह खोज बंद

**Freesound** — key · `FREESOUND_API_KEY`

- **डाली हो:** sound effects की खोज (Freesound)
- **न हो:** वह खोज बंद; starter sounds रहते हैं

**Tenor (GIF / sticker)** — key · `TENOR_API_KEY`

- **डाली हो:** GIF / sticker की खोज
- **न हो:** वह खोज बंद

### YouTube · Instagram · TikTok

**YouTube Data API key** — key · `YT_API_KEY`

- **डाली हो:** YouTube trends, दूसरे channels के आँकड़े, ideas
- **न हो:** ये आँकड़े नहीं आते

**Google OAuth client ID** — key · `YT_CLIENT_ID`

- **secret के साथ डाली हो:** YouTube channel जोड़ना और वहाँ upload / schedule (auto-upload आपने बंद रखा है — हर upload आपकी मंज़ूरी से)
- **न हो:** YouTube जोड़ने का बटन काम नहीं करता

**Google OAuth client secret** — key · `YT_CLIENT_SECRET`

- **client ID के साथ:** ऊपर जैसा — दोनों साथ चाहिए
- **न हो:** ऊपर जैसा

**Meta app ID** — key · `META_APP_ID`

- **secret के साथ डाली हो:** Instagram / Facebook page जोड़ना और post करना
- **न हो:** वे जुड़ते नहीं

**Meta app secret** — key · `META_APP_SECRET`

- **app ID के साथ:** ऊपर जैसा
- **न हो:** ऊपर जैसा

**TikTok client key** — key · `TIKTOK_CLIENT_KEY`

- **secret के साथ डाली हो:** TikTok जोड़ना
- **न हो:** नहीं जुड़ता

**TikTok client secret** — key · `TIKTOK_CLIENT_SECRET`

- **client key के साथ:** ऊपर जैसा
- **न हो:** ऊपर जैसा

### कहाँ चलाएँ · खर्च

**Transcript कहाँ बने** — switch · `TRANSCRIBE_ENGINE`

- **यह server (Z440):** transcript यहीं Whisper से — मुफ़्त, पर CPU पर धीमा (लंबी recording में कई मिनट)
- **fal.ai Whisper:** हर transcript fal.ai पर — तेज़, ~$0.006 / मिनट (अंदाज़ा)। FAL_KEY चाहिए; fal fail हो तो यहीं बनता है
- **RunPod serverless:** आपके अपने RunPod Whisper endpoint पर। RunPod key + endpoint ID चाहिए; fail हो तो यहीं बनता है
- **Auto:** छोटी recording यहीं (मुफ़्त), “Auto: कितने मिनट” से लंबी cloud पर। रोज़ के काम के लिए सबसे अच्छा
- **SRT दी हो:** यह switch लागू ही नहीं होता — transcript फ़ाइल से बनता है, कोई खर्च नहीं

**Auto: कितने मिनट से लंबी recording cloud पर जाए** — संख्या · `TRANSCRIBE_AUTO_MIN`

- **जैसे 8:** 8 मिनट तक की recording यहीं, उससे लंबी cloud पर (सिर्फ़ Auto में)
- **खाली:** 8 मिनट माना जाता है

**महीने की खर्च-सीमा (USD)** — संख्या · `SPEND_CAP_USD`

- **जैसे 5:** महीने में $5 का अंदाज़न खर्च होते ही सारे paid काम रुक जाते हैं (cloud transcript, fal / RunPod / ElevenLabs की आवाज़ें, AI music, AI video)। मुफ़्त काम चलते रहते हैं
- **0:** सारे paid काम बंद
- **खाली:** कोई सीमा नहीं — सलाह नहीं

**RunPod API key** — key · `RUNPOD_API_KEY`

- **डाली हो:** RunPod की आवाज़ें voice list में (MiniMax HD, Chatterbox Turbo), AI video के लिए RunPod चुन सकते हैं, और अपना Whisper endpoint इस्तेमाल हो सकता है
- **न हो:** RunPod की कोई चीज़ नहीं दिखती / चलती

**AI video clips कहाँ बनें** — switch · `AI_VIDEO_PROVIDER`

- **Auto:** fal.ai की key हो तो fal.ai, नहीं तो RunPod
- **fal.ai:** AI तस्वीर बनती है, फिर fal.ai उसे हिलाकर clip बनाता है
- **RunPod p-video:** बात के वर्णन से सीधा clip (~$0.02 / सेकंड, 720p)। चुनी हुई service की key न हो तो AI video बंद रहता है — चुपचाप दूसरी पर नहीं जाता

**चुप्पी कैसे पहचानें (auto-cut)** — switch · `SILENCE_ENGINE`

- **आवाज़ की ऊँचाई से:** पहले जैसा: जो हिस्सा धीमा है वह चुप्पी। शांत कमरे में ठीक; पंखे / traffic / music में चुप्पी छूट जाती है
- **Silero:** इंसानी आवाज़ पहचानकर: शोर में भी चुप्पी कटती है, धीमे शब्द नहीं कटते। नई upload और “transcript दोबारा बनाएँ” पर लागू। model न चले तो अपने-आप पहले वाला तरीका

**शब्दों का सटीक समय (WhisperX)** — switch · `WORD_ALIGN`

- **बंद:** शब्दों का समय Whisper का अपना (कभी-कभी 0.1–0.3 s आगे-पीछे)
- **WhisperX:** हर शब्द आवाज़ से दोबारा मिलाया जाता है — karaoke captions और text से कट ज़्यादा सटीक। तभी चलता है जब server WITH_WHISPERX=1 से बना हो (docs/whisperx.md); नहीं तो कुछ नहीं बदलता

**Clips को तस्वीर देखकर मिलाना (OpenCLIP, इसी server पर)** — switch · `CLIP_MATCH`

- **बंद:** supporting clips: आपका लिखा समय → Gemini → बोले गए शब्द → नाम का क्रम
- **चालू:** शब्दों के बाद एक कदम और: इसी server पर clip को देखकर सबसे मिलती line पर लगाना (बाहर कुछ नहीं जाता)। तभी चलता है जब server WITH_OPENCLIP=1 से बना हो (docs/openclip.md)

**RunPod Whisper endpoint ID** — key · `RUNPOD_WHISPER_ENDPOINT`

- **भरा हो:** “Transcript कहाँ बने” में RunPod चुनने पर यही endpoint इस्तेमाल होता है (RunPod → Serverless → Faster Whisper, Min workers = 0)
- **खाली:** RunPod transcript नहीं चल सकता

## 3. Server की फ़ाइल `.env` वाले switch (dashboard में नहीं)

बदलने के बाद: `cd /srv/studio/vividora && docker compose --profile tunnel up -d --build`

| line | क्या करता है | ध्यान दें |
|---|---|---|
| `TRANSCRIBE_LOCAL=1` | यह server खुद transcript बना सकता है (default चालू) | 0 करने पर transcript सिर्फ़ cloud या GPU worker से बनेगा |
| `TTS_LOCAL=1` | यह server खुद AI आवाज़ (Kokoro / Parler) बना सकता है — CPU पर धीमा | खाली हो तो local आवाज़ें GPU worker का इंतज़ार करती हैं; cloud आवाज़ें (fal / RunPod / ElevenLabs) फिर भी चलती हैं |
| `WITH_WHISPERX=1` | image में WhisperX install होता है (+2 GB) — तभी “शब्दों का सटीक समय” काम करता है | docs/whisperx.md; गड़बड़ी पर यह line हटाकर दोबारा build |
| `WITH_OPENCLIP=1` | image में OpenCLIP install होता है (+2 GB, model +1.5 GB) — तभी “Clips को तस्वीर देखकर मिलाना” काम करता है | docs/openclip.md |
| `PRICE_…` | खर्च के अंदाज़े की दरें (जैसे PRICE_FAL_WHISPER_MIN=0.004) | असली bill से मिलाकर ठीक करें; नाम 💰 खर्च tab में लिखे हैं |

## 4. पहली बार जाँचने का क्रम

1. PUBLIC_URL भरें → Settings की चेतावनी हटनी चाहिए।
2. खर्च-सीमा $5 रखें (पहले यही — फिर कोई key डालें)।
3. Gemini key डालें → किसी project में AI title बनवाकर देखें।
4. fal.ai key डालें → voice list में “(fal.ai)” आवाज़ें दिखें; एक line की voice-over बनाएँ; 💰 खर्च में entry आए।
5. “Transcript कहाँ बने” = Auto → 1 छोटी और 1 लंबी (8 मिनट से ऊपर) recording upload करें; लंबी वाली का खर्च दिखे।
6. SRT के साथ एक वीडियो upload करें → कोई transcribe काम न बने, captions तुरंत आएँ।
7. Sound tab → “AI से नया music” 20 सेकंड का बनाएँ।
8. Silero चालू करें → शोर वाली recording upload करें → Cuts tab देखें; पसंद न आए तो वापस।
9. RunPod key (ज़रूरत हो तब) → “(RunPod)” आवाज़ से एक हिन्दी line सुनें।
10. WhisperX / OpenCLIP सबसे आख़िर में, एक-एक करके (docs/whisperx.md, docs/openclip.md)।
