# Vividora API — दूसरे software से जोड़ना

n8n, Zapier, Make, अपनी app या script से Vividora के 3 काम चलाइए: **Image → 3D (.glb)**, **Text → Voice**, **3D character talking video**.

- Dashboard → **API & Integrations** (`#/api`) में key बनाइए (`vk_…`). Key सिर्फ़ एक बार दिखती है।
- Live docs: `https://<आपका-domain>/api/v1/docs` · OpenAPI: `/api/v1/openapi.json` (Postman / n8n / Swagger में import)
- Auth: `Authorization: Bearer vk_…` **या** header `X-API-Key: vk_…`
- Limit: 120 requests/min per key. एक समय में 1 image→3D और 1 voice job (CPU server).

## Keys
| | |
|---|---|
| Role `editor` | बना सकती है (voice, 3D, video) + देख/download |
| Role `viewer` | सिर्फ़ देख/download |
| Key बनाना/हटाना | सिर्फ़ dashboard login से (key से नहीं) |
| Key leak | Dashboard → API & Integrations → 🗑 हटाएँ (तुरंत बंद) |

## Endpoints (`/api/v1`)
| Method | Path | काम |
|---|---|---|
| GET | `/me` | key जाँचें (user, role, workspace) |
| GET | `/voices` | इस्तेमाल हो सकने वाली voices |
| POST | `/text-to-speech` | JSON `{text, voice?, lang?, speed?, name?, callback_url?}` → `202 {job_id}` |
| POST | `/image-to-3d` | multipart `file`, `name?`, `callback_url?` → `202 {job_id}` (1–3 मिनट) |
| GET / POST | `/models3d` | 3D models की list / तैयार `.glb` upload (multipart `file`, `name`) |
| POST | `/character-video` | JSON `{glb \| profile, lines:[{text,voice?}], animation?, camera?, seconds?, width?, height?, scene?, lighting?}` → `202 {job_id}` |
| POST | `/auto-sfx` | JSON `{project_id \| (effects + duration), cut_times?, density?: low/normal/high, level?: 0.3–1.5}` → `200 {sfx:[…], added}` — timeline (title / B-roll / sticker / cut) देखकर whoosh, pop, tick अपने-आप; सेव नहीं करता, editor `effects.sfx` में डालना आपके हाथ में |
| POST | `/documentary/plan` | `{topic, minutes?, language?}` या `{script}` → `{title, scenes[]}` (topic के लिए GEMINI/ANTHROPIC key) — देखें [documentary.md](documentary.md) |
| POST | `/documentary/build` | `{scenes[], title?, voice?, lang?, orientation?, music_id?, stock?, callback_url?}` → `202 {job_id}` — narrated MP4 Library में |
| GET | `/jobs/{job_id}` | `status`: `queued/running/done/failed` (+ `file` जब done) |
| GET | `/files/{file_id}` | नतीजा download (key चाहिए, link expire नहीं होता) |

## Flow (हर लंबे काम में एक जैसा)
1. POST → `{ "job_id": "…" }`
2. हर 3–5 सेकंड `GET /jobs/{job_id}` → `done` होने पर `file.download` (जैसे `/api/v1/files/abc…`)
3. `GET /files/{id}` से फ़ाइल लें (`.wav`, `.glb`, `.webm`)

`callback_url` (text-to-speech और image-to-3d) देने पर काम खत्म होते ही Vividora आपके URL पर POST करता है:
`{"event":"job.finished","job_id","kind","status","item_id","error"}`. असली details के लिए `GET /jobs/{id}` करें (इसी से पता चलता है call असली थी)। Private/local address (127.x, 192.168.x, 10.x…) मना है।

## Examples
### curl
```bash
KEY=vk_xxx; BASE=https://studio.vividbrandify.com
curl -X POST $BASE/api/v1/text-to-speech -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"text":"नमस्ते दोस्तों","lang":"hi"}'
curl $BASE/api/v1/jobs/JOB_ID -H "Authorization: Bearer $KEY"
curl -o voice.wav $BASE/api/v1/files/FILE_ID -H "Authorization: Bearer $KEY"
curl -X POST $BASE/api/v1/image-to-3d -H "Authorization: Bearer $KEY" -F file=@object.png -F name=chair
```

### Python
```python
import time, requests
BASE, H = "https://studio.vividbrandify.com/api/v1", {"Authorization": "Bearer vk_xxx"}
job = requests.post(f"{BASE}/text-to-speech", headers=H, json={"text": "Hello", "lang": "en"}).json()["job_id"]
while (j := requests.get(f"{BASE}/jobs/{job}", headers=H).json())["status"] == "running":
    time.sleep(4)
open("voice.wav", "wb").write(requests.get(f"{BASE}/files/{j['file']['id']}", headers=H).content)
```

### JavaScript (Node 18+)
```js
const BASE = "https://studio.vividbrandify.com/api/v1", H = { Authorization: "Bearer vk_xxx" };
const { job_id } = await (await fetch(`${BASE}/text-to-speech`, { method: "POST", headers: { ...H, "Content-Type": "application/json" }, body: JSON.stringify({ text: "Hello", lang: "en" }) })).json();
let j; do { await new Promise(r => setTimeout(r, 4000)); j = await (await fetch(`${BASE}/jobs/${job_id}`, { headers: H })).json(); } while (j.status === "running");
```

### n8n
1. **HTTP Request** node → Method `POST`, URL `…/api/v1/text-to-speech`, Authentication: *Generic → Header Auth* (Name `Authorization`, Value `Bearer vk_xxx`), Body JSON.
2. **Wait** node 10 s → **HTTP Request** `GET …/api/v1/jobs/{{$json.job_id}}` → **IF** `status = done` (नहीं तो Wait पर वापस)।
3. **HTTP Request** `GET …/api/v1/files/{{$json.file.id}}` → *Response Format: File*.
(या `callback_url` में n8n का **Webhook** node URL दें — पर वह public होना चाहिए।)

### Zapier / Make
*Webhooks by Zapier → Custom Request* (Zapier) / *HTTP → Make a request* (Make): वही URL, header `Authorization: Bearer vk_xxx`, JSON body।

## Errors
`401` key गलत/हटाई गई · `403` role कम · `422` input गलत · `429` एक काम पहले से चल रहा / बहुत requests · `503` TripoSR/VoiceStudio service बंद।

## Cloudflare Access लगा हो तो
अगर `studio…` पर Cloudflare Access (login wall) है, तो बाहर के software की request वहीं रुक जाएगी। Zero Trust → Access → Applications में एक **Bypass** policy जोड़ें (Everyone, path `/api/v1/*`) — वहाँ सुरक्षा Vividora की अपनी API key से होती है। (Docs page `/api/v1/docs` भी इसी path में है, चाहें तो उसे बंद रखें।)

## सुरक्षा
- Key सिर्फ़ SHA-256 hash के रूप में सेव होती है; दोबारा नहीं देखी जा सकती — खो जाए तो नई बनाएँ।
- हर key अपने workspace तक सीमित; दूसरी workspace का data नहीं दिखता।
- Key को code repo, screenshot या chat में न डालें।

## Sound effects (Auto SFX)
* Editor → inspector → **🔊 Auto SFX** (कम / सामान्य / ज़्यादा) — B-roll पर whoosh (तस्वीर से थोड़ा *पहले*), title/sticker पर pop (ठीक उसी frame), ज़्यादा density पर jump-cut पर हल्की tick। हर आवाज़ narration के नीचे अपने-आप दबती है (`duck`), अपने हाथ से रखी आवाज़ें नहीं छूती — दोबारा दबाने पर सिर्फ़ `asfx_` वाली बदलती हैं।
* Starter pack में अब 29 SFX हैं (`server/tools/make_sfx.py` से numpy में बने, CC0)। नए जोड़ने: Settings → Library → Starter pack फिर से।
* **Earshot / अपनी WAV files:** `MEDIA_ROOT/incoming/sfx/<tag>/file.wav` में डालें, फिर `POST /api/library/import-sfx-dir` (admin)। folder का नाम tag बन जाता है।
* **Openverse SFX:** Library → वेब खोज → "Sound effects — Openverse"। सिर्फ़ commercial-safe CC (CC0 / PDM / BY / BY-SA) दिखते हैं; credit/licence हर item में सेव रहता है (BY/BY-SA में video description में credit देना होगा)।

## Keys of outside services — from the dashboard

`API & Keys → Services की keys जोड़ें` (`#/api`) sets the keys Vividora itself uses, without touching `.env` or
restarting: `PUBLIC_URL`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_API_TOKEN`,
`FAL_KEY`, `ELEVENLABS_API_KEY`, `PIXABAY_API_KEY`, `JAMENDO_CLIENT_ID`, `FREESOUND_API_KEY`, `TENOR_API_KEY`,
`YT_API_KEY`, `YT_CLIENT_ID` / `YT_CLIENT_SECRET`, `META_APP_ID` / `META_APP_SECRET`, `TIKTOK_CLIENT_KEY` /
`TIKTOK_CLIENT_SECRET`.

* Stored encrypted (Fernet from `SECRET_KEY`) in the `provider_keys` table; the API only ever returns “set / not set”
  and the last four characters. **Changing `SECRET_KEY` makes saved keys unreadable — enter them again.**
* A dashboard value wins over `.env`; “हटाएँ” brings the `.env` value back. Everything else in `.env` works as before.
* Only the admin of the server's first (operator) workspace, with a dashboard login, can change them
  (`GET /api/providers`, `PUT|DELETE /api/providers/{ENV}`); an API key (`vk_…`) never can.
* Workers receive the keys they use themselves (Gemini / Anthropic / Cloudflare / fal / ElevenLabs) with every job they
  claim, so the worker container needs no restart either.

The other half of the page, `Vividora की API दें`, creates `vk_…` keys for your own software (described above).

## Where the transcript is made, and the spending guard

`TRANSCRIBE_ENGINE` (dashboard: API & Keys → “कहाँ चलाएँ · खर्च”) — `local` (this server's faster-whisper), `fal`
(fal.ai Whisper), `runpod` (a RunPod **serverless** endpoint running the stock Faster Whisper worker), `auto` (recordings
longer than `TRANSCRIBE_AUTO_MIN` minutes go to the cloud). `engine/cloudasr.py` cuts the audio into ~7-minute MP3s, sends
them inline, joins the word times on one clock; the result has the local transcriber's shape, so vocabulary fixes, AI
polish, auto-cut and captions work unchanged. A missing key, or a cloud failure, falls back to this server when it can
transcribe itself (`TRANSCRIBE_LOCAL=1`). The CPU worker takes `transcribe` jobs itself whenever a cloud engine is on.

`engine/meter.py` counts every paid call (`fal_whisper`, `runpod_whisper`, `ai_video`, `ai_image`, `elevenlabs`) with an
estimated unit price; `spend.py` keeps the log (`spend_log`) and the month's total. `SPEND_CAP_USD` stops paid calls
when the month's estimate reaches it (`meter.SpendCap`). Workers get the remaining budget with each claimed job and
report what they spend (`POST /api/worker/spend`). `GET /api/spend` → totals (the log only for the operator admin).
Nothing is kept running anywhere: fal.ai bills per call, RunPod serverless per second of a job.

### Speaker switch (podcast camera)

`POST /api/projects/{id}/speakers/plan` `{style?: "mix"|"close"|"wide_long", zoom?: 0.6–1.6, min_turn?: 1–6, cam?: <library video id>, cam_offset?: seconds}`
→ `202 {job}`; `GET /api/visuals/jobs/{job}` → `{status, message, result: {shots, people, faces, turns, cam, main_close}}`.
Nothing is written to the project: the editor stores the plan in `effects.speaker` and places the clips (docs/editor-schema.md).
