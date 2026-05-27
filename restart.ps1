$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

& (Join-Path $Root "stop.ps1")
Start-Sleep -Seconds 1
& (Join-Path $Root "start.ps1")
