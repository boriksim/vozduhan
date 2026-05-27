$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$OutLog = Join-Path $Root "logs\bot.out.log"
$ErrLog = Join-Path $Root "logs\bot.err.log"

Write-Host "=== stderr ==="
Get-Content $ErrLog -Tail 80 -ErrorAction SilentlyContinue

Write-Host "=== stdout ==="
Get-Content $OutLog -Tail 80 -ErrorAction SilentlyContinue
