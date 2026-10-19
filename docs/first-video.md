# कल का पहला वीडियो — Vividora से (checklist)

## 0. Server update (एक बार, ~10 मिनट)
```bash
cd /srv/studio/app
git pull
docker compose up -d --build          # नए packages: onnxruntime (cutout), opencv, rclone
docker compose logs -f api | grep -i starter   # "starter pack: 248 items added" दिखे
```
Browser में Ctrl+Shift+R (पुराना cache हटेगा)।

## 1. Channel set करें (2 मिनट)
Dashboard → नीचे **channels** →
- Main channel का नाम `@theprashantmahto`, niche: `Hindi motivation, success stories, self-improvement`, भाषा हिंदी, keywords।
- **Brand kit**: caption style (Hormozi / Karaoke), font, रंग, color grade (Natural Skin), CTA line, hashtags → सेव।
- दूसरे channels (जैसे Tukur Tukoor) "+ नया channel" से — हर channel का अपना brand kit/connections।
- Logo: Library → upload → kind `logo` → फिर brand kit में चुनें।

## 2. Recording
**Phone से (सबसे आसान):** phone के browser में Tunnel वाला पता (https://…) → ऊपर ⏺ **Record**
- ⚙ settings: back/front camera, resolution "सबसे ऊँची", 30 fps
- 📜 teleprompter: Plan से script चुनें या लिखें, अक्षर/speed सेट करें, window खींचकर lens के पास रखें
- 🔴 → 3-2-1 → बोलें (Space = teleprompter चलाएँ/रोकें) → ■ → preview → **✈ autopilot ✓** → Upload
(Phone पर camera सिर्फ़ HTTPS पर चलता है — Tunnel नहीं है तो phone के camera app से record करके "+ नया" से upload करें, वो भी ठीक है।)

**Phone camera app / दूसरी app से:** record करें → dashboard → **+ नया** → files चुनें (कई clips एक साथ चुनें तो क्रम से जुड़ेंगी) → ✈ Autopilot ✓ → upload.

## 3. Autopilot क्या करेगा (10-min video ≈ 20–40 min, CPU)
आवाज़ साफ़ → transcript (Hindi/English/Hinglish auto) → चुप्पी/अं-आं/retake कट → hook card → captions (brand style) → zoom (slow push / punch) → color grade → mood वाली background music (बोलते समय धीमी) → logo → Subscribe popup + pop SFX → Like/Sub/Bell popup → YouTube long + 3 Shorts (face tracking के साथ) → AI titles/description/tags।

## 4. Review (5–10 मिनट)
Project खोलें → editor:
- **कट** tab: कोई ज़रूरी हिस्सा कट गया हो तो checkbox हटाएँ
- **Caption** tab: गलत सुने शब्द list में सीधे सुधारें
- **Effects / Body / Color / Media(stickers) / Audio** — जो चाहिए बदलें; 🎞 Preview frame से असली frame देखें
- Export → "दोबारा render" (बदलाव किए हों तो)

## 5. Approve & publish
Export → videos देखें → **मंज़ूरी दें** → (Channels में YouTube/IG/FB जुड़े हों तो) **✈ सब publish करें** — title बदलना हो तो वहीं।
WhatsApp जुड़ा हो तो "ok XXXX" reply से भी मंज़ूरी।

## अगर कुछ अटके
- status page: worker online है? queue में job?
- "transcript बन रहा है" पर रुका → `docker compose logs worker`
- cutout (Body effects) पहली बार ~15 MB model download करता है (internet चाहिए)
