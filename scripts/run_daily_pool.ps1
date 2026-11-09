# Daily DB-driven operation:
#   1. plan review assignments (metro / trust / velocity / volume gates)
#   2. run post-review warm sessions for due accounts (max 2 profiles at a time)
#   3. post today's due reviews, then re-check reviews older than 72h
$root = Split-Path -Parent $PSScriptRoot
$yf = Join-Path $root ".venv\Scripts\yf.exe"
$logDir = Join-Path $root "artifacts\daily"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmm"
$log = Join-Path $logDir "daily_$stamp.log"

function Run-Yf([string[]]$argv) {
    $line = "> yf " + ($argv -join " ")
    Add-Content -Path $log -Value $line
    & $yf @argv *>> $log
}

# Random start jitter (0-40 min) so the daily run never starts at the same minute.
$jitter = Get-Random -Minimum 0 -Maximum 2400
Add-Content -Path $log -Value ("jitter_s=" + $jitter)
Start-Sleep -Seconds $jitter

Run-Yf @("trust", "--recompute", "--all")
Run-Yf @("assign")
for ($i = 0; $i -lt 2; $i++) {
    Run-Yf @("warm", "--mode", "post-review")
    Start-Sleep -Seconds (Get-Random -Minimum 60 -Maximum 300)
}
Run-Yf @("probe", "--stale-days", "3", "--limit", "4")
Run-Yf @("review", "post", "--limit", "3")
Run-Yf @("review", "check", "--hours", "72", "--limit", "5")
Run-Yf @("volume")
Run-Yf @("clean-artifacts", "--days", "30")
exit $LASTEXITCODE
