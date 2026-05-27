$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$LogDir = Join-Path $Root "logs"
$OutLog = Join-Path $LogDir "bot.out.log"
$ErrLog = Join-Path $LogDir "bot.err.log"
$PidFile = Join-Path $Root "bot.pid"

New-Item -ItemType Directory -Force $LogDir | Out-Null

if (-not (Test-Path $Python)) {
    throw "Virtualenv not found: $Python. Run: python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
}

$existing = $null
if (Test-Path $PidFile) {
    $oldPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($oldPid) {
        $existing = Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
    }
}

if ($existing) {
    Write-Host "Vozduhan already running: PID $($existing.Id)"
    exit 0
}

$process = Start-Process `
    -FilePath $Python `
    -ArgumentList "-u", "main.py" `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

Set-Content -Path $PidFile -Value $process.Id
Start-Sleep -Seconds 2

if ($process.HasExited) {
    Write-Host "Vozduhan failed to start. stderr:"
    Get-Content $ErrLog -Tail 80 -ErrorAction SilentlyContinue
    exit 1
}

Write-Host "Vozduhan started: PID $($process.Id)"
Write-Host "Panel: http://127.0.0.1:8080/"
Write-Host "Logs: $OutLog / $ErrLog"
