# Vividora — पूरा setup, update और रोज़ की देखभाल

Server: Ubuntu VM `yt-meta` (VMware, HPSERVER) · folder `/srv/studio/vividora` · site `https://studio.vividbrandify.com`

## 1. इसमें क्या-क्या है
| हिस्सा | कहाँ खुलता है | काम |
|---|---|---|
| Video editor + Projects | Home / Timeline Editor | Upload → auto-cut → captions → render (YouTube / Shorts / Reels) |
| 3D Studio | `#/characters3d`, `#/scenes3d` | बोलता 3D character (built-in या आपका `.glb`), lip-sync, scenes |
| Image → 3D | `#/image3d` | तस्वीर → `.glb` model (TripoSR, CPU पर 1–3 मिनट) |
| Voice Studio | `#/voicestudio` | Text → AI आवाज़ (VoiceStudio/OmniVoice, निजी इस्तेमाल) |
| Editor की "3D & Voice" tab | Timeline Editor के अंदर | 3D clip और voice-over सीधे timeline में |
| **API & Integrations** | `#/api` | दूसरे software के लिए API keys + `/api/v1` |
| Publish, Plan, Trends, Copilot, Library… | बाकी menu | पहले जैसे |

## 2. इस update में क्या नया है (API)
- API keys (`vk_…`): बनाओ / copy / हटाओ — dashboard से
- Public API `/api/v1`: text-to-speech · image-to-3d · character-video · models3d · jobs · files
- Webhook `callback_url`, OpenAPI (`/api/v1/openapi.json`) और docs (`/api/v1/docs`)
- Database में नई table अपने-आप बन जाती है (कुछ migrate नहीं करना)

## 3. Update कैसे करें (VM पर, PowerShell → `ssh prashant@<vm-ip>`)
```bash
cd /srv/studio/vividora
git pull
docker compose up -d --build api      # सिर्फ़ api बनता है; worker चलता रहता है
docker compose ps                     # api = healthy
```
फिर browser में `Ctrl+Shift+R` (hard refresh)। `worker` को तभी rebuild करें जब कोई video render न चल रहा हो।

## 4. API key बनाकर इस्तेमाल करना
1. Dashboard → बाएँ menu **API → API & Integrations**
2. नाम लिखें (जैसे `n8n`), अनुमति `editor` → **Key बनाएँ**
3. Key तुरंत 📋 copy करें (दोबारा नहीं दिखेगी)
4. अपने software में header डालें: `Authorization: Bearer vk_…`
5. Test: `curl https://studio.vividbrandify.com/api/v1/me -H "Authorization: Bearer vk_…"`
6. पूरे examples (curl / Python / JS / n8n / Zapier): `docs/api.md`
7. अगर Cloudflare Access लगा है तो `/api/v1/*` पर Bypass policy जोड़ें (`docs/api.md` देखें)

## 5. Reboot / बिजली जाने के बाद सब कुछ चालू करना
```bash
docker ps -a --format "table {{.Names}}\t{{.Status}}"
cd /srv/studio/vividora && docker compose up -d
sudo systemctl start triposr voicestudio voicestudio-proxy
systemctl is-active triposr voicestudio voicestudio-proxy      # तीनों active
curl -s http://127.0.0.1:8090/health                            # TripoSR ok
```
हमेशा के लिए अपने-आप चालू रहने के लिए (एक बार):
```bash
sudo systemctl enable triposr voicestudio voicestudio-proxy
docker update --restart unless-stopped $(docker ps -aq)
```

## 6. VM का IP न बदले
Router admin → DHCP / Address Reservation → VM का MAC (`ip link show ens33 | grep link/ether`) → एक fixed IP। Site (Cloudflare Tunnel) IP पर निर्भर नहीं, पर SSH, दूसरे worker और local links निर्भर हैं।

## 7. दिक्कत आए तो
| लक्षण | वजह / हल |
|---|---|
| Cloudflare **Error 1033** | `cloudflared` container बंद → `docker compose up -d`, `docker ps` में `vividora-cloudflared-1` Up देखें |
| Image→3D "TripoSR service band" | `sudo systemctl start triposr` (30–40 s रुकें) |
| Voice में 403 / "licence" | VoiceStudio में licence एक बार accept (हो चुका); service `voicestudio` active हो |
| UI पुराना दिख रहा | `Ctrl+Shift+R` या incognito |
| API `401` | key गलत/हटाई गई → नई बनाएँ |
| API `429` | एक काम पहले से चल रहा → job खत्म होने दें |

## 8. सुरक्षा याद रखें
- Password / token / API key screenshot या chat में न दिखाएँ
- VM का password बदलें: `passwd`
- Cloudflared token पहले leak हुआ था तो Zero Trust → Tunnels में rotate करें
- Voice Studio (OmniVoice) licence सिर्फ़ निजी/non-commercial; public SaaS के लिए commercial-safe TTS (जैसे Kokoro) लगाएँ
