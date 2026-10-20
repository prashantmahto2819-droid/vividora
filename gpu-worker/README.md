# Vividora GPU worker (Windows)

Runs on the PC with the NVIDIA GPU. It transcribes (Hindi speech → words
with timestamps), optionally makes AI voice-overs (see below), and sends the
results to the Vividora server in the Ubuntu VM.

## Setup (once)

1. Install the latest NVIDIA driver and Python 3.11 (tick "Add to PATH").
2. Clone this repo on Windows (or copy the `gpu-worker` + `server` folders).
3. In PowerShell:
   ```powershell
   cd vividora\gpu-worker
   Set-ExecutionPolicy -Scope Process Bypass
   .\install.ps1
   ```
4. Edit `gpu-worker.env`: `API_URL` = the VM's address (e.g. `http://192.168.1.50:8000`),
   `WORKER_TOKEN` = the same value as in the server `.env`.
5. `.\run.ps1` — the first run downloads the Whisper model (~3 GB).

## AI voice-over / dubbing (optional)

The editor's Audio tab → “🗣 AI voice-over / dubbing” makes `dub` jobs: a new AI
voice for your own transcript, a Hindi↔English dub, or a voice-over from a typed
script. This worker picks them up (set `DUB=0` in `gpu-worker.env` to stop that).
Models — both commercial-use OK (Apache-2.0):

* Hindi + Indian English: `ai4bharat/indic-parler-tts` (~3.5 GB download on first use)
* English (lighter): `hexgrad/Kokoro-82M`

Install once, in PowerShell inside `vividora\gpu-worker` (after `install.ps1`):

```powershell
winget install Gyan.FFmpeg          # ffmpeg on PATH (open a NEW PowerShell afterwards)
.\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu121
.\.venv\Scripts\python.exe -m pip install -r requirements-tts.txt
.\install.ps1                        # again, so lib\vividora_tts.py is copied
```

`git` must be installed (`winget install Git.Git`) because parler-tts installs from GitHub.
If the first dub fails with a 401/“gated” error from Hugging Face, open
https://huggingface.co/ai4bharat/indic-parler-tts while logged in, accept the terms, then run
`.\.venv\Scripts\huggingface-cli.exe login` once. Models are stored in `gpu-worker\models\tts`.

VRAM: Parler runs in float16 (~2 GB) next to Whisper. On a small card set
`PARLER_DTYPE=float32` only if you see garbled audio. Without these packages a dub
job fails with a Hindi message that says exactly what to install. The CPU worker
can also make voice-overs with `TTS_LOCAL=1` (same packages, very slow).

The dashboard's status page shows the worker as online once it has checked in.
If the PC is off, transcribe jobs wait in the queue; the CPU worker can take
them instead if you set `TRANSCRIBE_LOCAL=1` in the server `.env` (slow).
