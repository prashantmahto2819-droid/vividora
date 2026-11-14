# Platform API — Vividora ke models dusre platform (AI App Builder) se chalana

Vividora ke self-hosted models (VoiceStudio/Indic Parler TTS, TripoSR image→3D) ab **API key** se HTTP par chal sakte hain.
Key sirf neeche likhe endpoints chala sakti hai; login, billing, library, users ya keys par nahi.

## Key banana (VM par, ek baar)
```
cd ~/vividora            # jahan docker-compose.yml hai
docker compose exec api python -m vividora.apikey_cli "AI App Builder" tts,3d
```
Key `vvk_…` ek baar dikhti hai — copy karke builder ke env me `VIVIDORA_API_KEY` me daalein.
(Ya admin login karke `POST /api/keys {"name":"…","scopes":["tts","3d"]}`; `GET /api/keys` list, `DELETE /api/keys/{id}` revoke.)

## Endpoints (header: `Authorization: Bearer vvk_…`)
| scope | method + path | kaam |
|---|---|---|
| tts | `POST /api/voiceover` `{text, voice?, lang?, speed?, name?}` → `202 {job_id}` | text → awaaz (async) |
| tts | `GET /api/voiceover/{job_id}` → `{status, item{url}, error}` | status; done par `item.url` se wav download |
| tts | `GET /api/voicestudio/{health,models,voices}` | models / voices ki list |
| 3d | `POST /api/triposr/generate` multipart `file` → `202 {job_id}` | image → 3D GLB (async, CPU par 1–3 min) |
| 3d | `GET /api/triposr/job/{job_id}` → `{status, item{url}}` | status; done par `item.url` se .glb download |

`item.url` ek signed link hai (6 ghante chalta hai), usse bina key ke file mil jaati hai.
Key par rate limit 60 request/minute; ek workspace me ek samay me ek hi TTS aur ek hi 3D job chalta hai (429 aaye to ruke).

## Internet par kholna
Builder agar doosri machine/cloud par hai to Vividora ko Cloudflare Tunnel se expose karein (docs/cloudflare-tunnel.md) aur
`VIVIDORA_URL=https://<aapka-tunnel-domain>` rakhein. Key leak ho jaye to `DELETE /api/keys/{id}` se turant band.
