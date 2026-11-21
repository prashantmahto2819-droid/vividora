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
- AI जो facts लिखे उन्हें **publish से पहले ख़ुद जाँचें**; script में वही नाम/तारीख़ें रखें जिन पर भरोसा हो।
- तस्वीरें Pixabay/आपकी Library से हैं — AI-generated या aerial footage अपने-आप नहीं बनती (अगला phase: GPU image/video model)।
- एक workspace में एक साथ एक ही documentary बनती है; ज़्यादा से ज़्यादा 24 scenes, 9000 अक्षर।

## API
```
POST /api/v1/documentary/plan   {"topic":"हिमालय कैसे बना","minutes":3,"language":"hi"}   (या {"script":"…"})
POST /api/v1/documentary/build  {"title":"…","scenes":[{"narration":"…","visual":"aerial himalaya"}],"voice":"hi_kokoro_alpha","orientation":"landscape"}  → 202 {job_id}
GET  /api/v1/jobs/{job_id}      → status, file (डाउनलोड: GET /api/v1/files/{id})
```
