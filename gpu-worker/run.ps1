# Start the GPU worker in this window (Ctrl+C to stop).
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
& "$here\.venv\Scripts\python.exe" "$here\gpu_worker.py"
