# Task entry point: spawn the daily worker in the background and exit immediately.
# The scheduler therefore never blocks on a 25-90 minute warm session and several
# workers can coexist; the <=2 profile cap is enforced in the database (browser_slots
# + account_locks), not by the scheduler (2026-11-09).
$root = Split-Path -Parent $PSScriptRoot
Start-Process -FilePath "powershell.exe" `
    -ArgumentList @("-ExecutionPolicy", "Bypass", "-File", "`"$root\scripts\run_daily_pool.ps1`"") `
    -WindowStyle Hidden
exit 0
