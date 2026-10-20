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
हर कदम पिछले के पूरा होने के बाद ही शुरू होता है; project की line पर दिखता है कि कौन-सा कदम चल रहा है (जैसे “3/11 · कट ढूँढ रहे हैं”):

1. फ़ाइल जाँच + आवाज़ साफ़
2. transcript (Hindi/English/Hinglish auto)
3. चुप्पी/अं-आं/retake कट
4. edit plan — hook heading, captions (brand style), color, mood वाली music, emoji stickers, बड़ी lines, Subscribe/Follow popup (English, हर platform का अपना), zoom
5. platform नियम जाँच — जो अपने-आप ठीक हो सकता है वो ठीक: लंबा वीडियो Reel नहीं बनता (Shorts कटते हैं), hook कमज़ोर हो तो बेहतर hook, text/sticker safe zone में
6. मुख्य वीडियो render (+ quality check: शुरू के काले frames हटते हैं, loudness, captions)
7. Shorts चुने जाते हैं (लंबी video से; गिनती Settings → Autopilot में, 0 = कोई नहीं)
8. Shorts render — हर Short के अपने hook/stickers/popup
9. 3 thumbnails + 9:16 cover
10. title / description / tags — AI key हो तो **एक ही AI call** में सब, नहीं तो transcript से
11. publish plan + समय (channel के posting slots)

फिर status “✅ autopilot पूरा … code XXXX” और WhatsApp पर **एक** message। Publish कभी अपने-आप नहीं होता — मंज़ूरी (dashboard या WhatsApp पर `ok XXXX`) के बाद Publish आप दबाते हैं।
कोई कदम असफल हो तो line पर लिखा होता है क्या हुआ और क्या करें; ठीक करके **Autopilot फिर चलाएँ** (`POST /api/projects/{id}/autopilot/resume`) — वहीं से आगे चलता है।

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
