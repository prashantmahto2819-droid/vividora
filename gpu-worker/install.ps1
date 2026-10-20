# Vividora GPU worker - one-time setup on the Windows PC with the NVIDIA GPU.
# Run in PowerShell (as Administrator for the auto-start task):
#   Set-ExecutionPolicy -Scope Process Bypass; .\install.ps1
# ASCII only: Windows PowerShell 5 misreads UTF-8 files without a BOM.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

Write-Host "== Vividora GPU worker setup ==" -ForegroundColor Cyan

# 1. Python (skip the Microsoft Store stub in WindowsApps)
$py = $null
foreach ($cand in @("python", "python3", "py")) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notlike "*WindowsApps*") { $py = $cmd.Source; break }
}
if (-not $py) {
    Write-Host "Python not found. Install Python 3.11 from python.org (tick 'Add python.exe to PATH')," -ForegroundColor Red
    Write-Host "turn off Settings > Apps > App execution aliases > python.exe, then open a NEW PowerShell." -ForegroundColor Red
    exit 1
}
Write-Host "Python: $py"
& $py --version

# 2. NVIDIA driver check
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
} else {
    Write-Host "nvidia-smi not found - install/update the NVIDIA driver from nvidia.com" -ForegroundColor Yellow
}

# 3. Virtual environment + packages
if (-not (Test-Path ".venv")) { & $py -m venv .venv }
$venvPy = Join-Path $here ".venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r requirements.txt

# 4. Shared code from the server package (client + transcriber)
New-Item -ItemType Directory -Force -Path lib | Out-Null
Copy-Item ..\server\vividora\worker\client.py lib\vividora_client.py -Force
Copy-Item ..\server\vividora\worker\transcribe.py lib\vividora_transcribe.py -Force
# AI voice-over / dubbing engine (packages: requirements-tts.txt, see README)
Copy-Item ..\server\vividora\engine\tts.py lib\vividora_tts.py -Force
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "ffmpeg not found - AI voice-over (dub) jobs need it: winget install Gyan.FFmpeg" -ForegroundColor Yellow
}
$shim = @(
    "import json, subprocess",
    "def probe(p):",
    "    o = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(p)],capture_output=True,text=True)",
    "    return {'duration': float(json.loads(o.stdout)['format']['duration'])}",
    "def silences(p): return []"
)
Set-Content -Path lib\ffmpeg_shim.py -Value $shim -Encoding UTF8
$t = Get-Content lib\vividora_transcribe.py -Raw -Encoding UTF8
$t = $t.Replace("from ..engine import ffmpeg", "import ffmpeg_shim as ffmpeg")
Set-Content -Path lib\vividora_transcribe.py -Value $t -Encoding UTF8

# 5. Config
if (-not (Test-Path "gpu-worker.env")) {
    Copy-Item gpu-worker.env.example gpu-worker.env
    Write-Host "Created gpu-worker.env - open it in Notepad and set API_URL and WORKER_TOKEN." -ForegroundColor Yellow
}

# 6. Auto-start at logon (needs an Administrator PowerShell)
$ans = Read-Host "Start the worker automatically at Windows logon? (y/n)"
if ($ans -eq "y") {
    try {
        $action = New-ScheduledTaskAction -Execute (Join-Path $here ".venv\Scripts\pythonw.exe") -Argument ('"' + (Join-Path $here "gpu_worker.py") + '"') -WorkingDirectory $here
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        $settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
        Register-ScheduledTask -TaskName "Vividora GPU Worker" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
        Write-Host "Task Scheduler: 'Vividora GPU Worker' registered." -ForegroundColor Green
    } catch {
        Write-Host "Could not register the task (run PowerShell as Administrator to enable auto-start)." -ForegroundColor Yellow
    }
}
Write-Host "Setup done. Start now with: .\run.ps1" -ForegroundColor Green
