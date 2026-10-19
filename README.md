# Vividora

AI video studio for creators who record their own videos. Upload a recording;
Vividora cleans the voice, writes a Hindi transcript with word timing, finds
silences / fillers / retakes, burns stylish captions, and renders a version
for YouTube, Shorts, Instagram Reels and Facebook Reels. Nothing is published
without your approval.

Runs on your own machine — no subscriptions. Phase 1 (this repo today):
**M0 Core** (login, users, projects, resumable upload, job queue) and
**M1 Studio** (prepare → transcribe → autocut → captions → render).

```
Windows PC (NVIDIA GPU)            Ubuntu VM (Docker)
┌──────────────────┐   transcribe   ┌───────────┐  ┌────────────┐
│ gpu-worker       │ ◄────────────► │  api      │◄─│  worker    │
│ faster-whisper   │                │  :8000    │  │ ffmpeg     │
└──────────────────┘                └───────────┘  └────────────┘
                                          ▲  dashboard (PWA) · phone / laptop
```

## Layout

| folder | what |
| --- | --- |
| `server/vividora/engine` | the editing engine: `prepare.py` (probe, voice clean, preview), `autocut.py` (EDL), `captions.py` (ASS/SRT, Devanagari), `render.py` (ffmpeg) |
| `server/vividora/api` | HTTP API (Starlette): auth, projects, uploads, worker endpoints |
| `server/vividora/worker` | CPU worker + shared HTTP client + transcriber |
| `server/presets` | platform presets (`platforms/*.json`) and caption styles (`captions/*.json`) — add a file, no code |
| `server/fonts` | Noto Sans Devanagari (OFL) |
| `gpu-worker` | the Windows worker (`install.ps1`, `run.ps1`) |
| `web/dist` | the dashboard — plain HTML/JS, no build step |
| `docker-compose.yml`, `.env.example` | the whole server stack |

## Run on the Ubuntu VM

```bash
git clone https://github.com/prashantmahto2819-droid/vividora /srv/studio/app
cd /srv/studio/app
cp .env.example .env            # set SECRET_KEY, WORKER_TOKEN, ADMIN_* , paths
docker compose up -d --build
```

Open `http://<vm-ip>:8000`, log in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`,
change the password (users page). Then set up `gpu-worker/` on the Windows PC
(see its README). The status page shows both workers.

## Run for development (no Docker)

```bash
cd server
pip install -r requirements.txt
DATA_ROOT=./data MEDIA_ROOT=./media WEB_DIST=../web/dist \
  python -m uvicorn vividora.app:app --reload
# second terminal: CPU worker, with a stub transcriber so no GPU is needed
API_URL=http://127.0.0.1:8000 TRANSCRIBE_LOCAL=1 WHISPER_MODEL=stub python -m vividora.worker.cpu
```

## How a project flows

`uploading → preparing → transcribing → cutting → review_cuts → rendering → review_output → approved`

- **prepare** (CPU): ffprobe, 720p preview, 16 kHz audio for ASR, voice cleanup (DeepFilterNet if `deep-filter` is installed, else ffmpeg filters).
- **transcribe** (GPU): faster-whisper `large-v3`, word timestamps, VAD.
- **autocut** (CPU): pauses longer than `max_pause`, isolated fillers (अं, उम…), repeated sentences (retakes). Every cut is a checkbox in the dashboard.
- **render** (CPU): frame-accurate select filter, crop/blur/pad per preset, libass captions (karaoke / pop / classic / boxed), loudness −14 LUFS, optional 3-second hook card, SRT sidecar for YouTube long.

## Roadmap (from the plan)

M2 effects library · M3 Shorts factory (face tracking) · M4 platform
publishing (YouTube / Instagram / Facebook APIs) · M5 planner & scripts ·
M6 trend radar · M7 analytics + style learning · M8 WhatsApp notifications ·
M9 asset library · M10 montage templates · M11 website.
