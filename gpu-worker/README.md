# Vividora GPU worker (Windows)

Runs on the PC with the NVIDIA GPU. It only transcribes (Hindi speech → words
with timestamps) and sends the result to the Vividora server in the Ubuntu VM.

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

The dashboard's status page shows the worker as online once it has checked in.
If the PC is off, transcribe jobs wait in the queue; the CPU worker can take
them instead if you set `TRANSCRIBE_LOCAL=1` in the server `.env` (slow).
