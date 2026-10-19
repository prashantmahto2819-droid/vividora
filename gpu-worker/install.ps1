# Vividora GPU worker — one-time setup on the Windows PC with the NVIDIA GPU.
# Run in PowerShell:  Set-ExecutionPolicy -Scope Process Bypass; .\install.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

Write-Host "== Vividora GPU worker setup ==" -ForegroundColor Cyan

# 1. Python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Write-Host "Python नहीं मिला। python.org से Python 3.11 install करें (Add to PATH टिक करें)।" -ForegroundColor Red; exit 1 }
python --version

# 2. NVIDIA driver check
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($smi) { nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv } else { Write-Host "nvidia-smi नहीं मिला — NVIDIA driver install/update करें।" -ForegroundColor Yellow }

# 3. Virtual environment + packages
if (-not (Test-Path ".venv")) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 4. Shared code from the server package (client + transcriber)
New-Item -ItemType Directory -Force -Path lib | Out-Null
Copy-Item ..\server\vividora\worker\client.py lib\vividora_client.py -Force
Copy-Item ..\server\vividora\worker\transcribe.py lib\vividora_transcribe.py -Force
# the transcriber imports the engine only for the stub; give it a tiny shim
@"
import json, subprocess
def probe(p):
    o = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(p)],capture_output=True,text=True)
    return {'duration': float(json.loads(o.stdout)['format']['duration'])}
def silences(p): return []
"@ | Set-Content lib\ffmpeg_shim.py
(Get-Content lib\vividora_transcribe.py) -replace 'from \.\.engine import ffmpeg', 'import ffmpeg_shim as ffmpeg' | Set-Content lib\vividora_transcribe.py

# 5. Config
if (-not (Test-Path "gpu-worker.env")) { Copy-Item gpu-worker.env.example gpu-worker.env; Write-Host "gpu-worker.env बनाई — इसमें API_URL और WORKER_TOKEN भरें।" -ForegroundColor Yellow }

# 6. Auto-start at logon (optional)
$ans = Read-Host "Windows login पर worker अपने-आप शुरू हो? (y/n)"
if ($ans -eq "y") {
  $action = New-ScheduledTaskAction -Execute "$here\.venv\Scripts\pythonw.exe" -Argument "`"$here\gpu_worker.py`"" -WorkingDirectory $here
  $trigger = New-ScheduledTaskTrigger -AtLogOn
  $settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
  Register-ScheduledTask -TaskName "Vividora GPU Worker" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
  Write-Host "Task Scheduler में 'Vividora GPU Worker' जुड़ गया।" -ForegroundColor Green
}
Write-Host "Setup पूरा। अभी चलाने के लिए: .\run.ps1" -ForegroundColor Green
