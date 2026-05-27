$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root "bot.pid"

if (Test-Path $PidFile) {
    $oldPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($oldPid) {
        $process = Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $process.Id -Force
            Write-Host "Stopped PID $($process.Id)"
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

$listeners = netstat -ano | Select-String ':8080' | Where-Object { $_.ToString() -match 'LISTENING\s+(\d+)$' }
foreach ($line in $listeners) {
    if ($line.ToString() -match 'LISTENING\s+(\d+)$') {
        $targetPid = [int]$Matches[1]
        $process = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
        if ($process -and $process.ProcessName -like "python*") {
            Stop-Process -Id $targetPid -Force
            Write-Host "Stopped listener PID $targetPid"
        }
    }
}

Write-Host "Vozduhan stopped."
