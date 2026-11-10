# Post-review warm sessions for every managed account - at most 2 profiles at a time.
# Registered in Task Scheduler (YelpFactoryPostReviewDaily, 09:00 daily).
# Each account runs at most once per day (guard inside post_review_session.py).
#
# Credentials live OUTSIDE git: data/post_review_accounts.json (data/ is gitignored).
# Schema: docs/seed_accounts.example.json. Override with YF_POST_REVIEW_ACCOUNTS.
# Passwords are decrypted from the DB by post_review_session.py, so this file only
# carries ids/labels - see docs/RUNBOOK.md "post-review batch".

param(
    [string]$AccountsFile = (Join-Path (Split-Path -Parent $PSScriptRoot) "data\post_review_accounts.json")
)

$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$runner = Join-Path $root "scripts\post_review_session.py"
$logDir = Join-Path $root "artifacts\post_review_state"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not (Test-Path $AccountsFile)) {
    Write-Error "missing $AccountsFile - copy docs/seed_accounts.example.json there and fill in real values (never commit it)"
    exit 2
}

# Mail-reader profile for fakemailo (E-67): the residential profile can reach it,
# mobile profiles cannot. Used only when a session is lost and login is needed.
$mailProfile = if ($env:YF_LOGIN__MAIL_READER_PROFILE_ID) { $env:YF_LOGIN__MAIL_READER_PROFILE_ID } else {
    Write-Error "YF_LOGIN__MAIL_READER_PROFILE_ID not set (see .env)"
    exit 2
}

$accounts = @(Get-Content -Raw $AccountsFile | ConvertFrom-Json).accounts
if (-not $accounts -or $accounts.Count -eq 0) {
    Write-Error "$AccountsFile has no accounts"
    exit 2
}

$maxParallel = 2   # LUON <= 2 profile cung luc

$queue = [System.Collections.Queue]::new()
foreach ($a in $accounts) { $queue.Enqueue($a) }
$running = @()

while ($queue.Count -gt 0 -or $running.Count -gt 0) {
    while ($running.Count -lt $maxParallel -and $queue.Count -gt 0) {
        $a = $queue.Dequeue()
        # per-account start jitter: never two accounts at exactly the same second
        Start-Sleep -Seconds (Get-Random -Minimum 0 -Maximum 600)
        $tag = ($a.email -replace '[^a-zA-Z0-9]', '_').Substring(0, 24)
        $stamp = Get-Date -Format "yyyyMMdd_HHmm"
        $out = Join-Path $logDir "run_${tag}_${stamp}.log"
        $err = "$out.err"
        # No password on the command line: post_review_session.py decrypts
        # password_enc from the DB using YF_MASTER_KEY.
        $argList = @(
            "`"$runner`"", "--profile-id", "`"$($a.gpm)`"",
            "--email", "`"$($a.email)`"",
            "--user-id", "`"$($a.user_id)`"", "--city", "`"$($a.city)`"",
            "--mail-profile-id", "`"$mailProfile`""
        )
        $p = Start-Process -FilePath $py -ArgumentList $argList -PassThru -NoNewWindow `
            -RedirectStandardOutput $out -RedirectStandardError $err
        $running += $p
        Write-Output "started $($a.email) (pid $($p.Id))"
        Start-Sleep -Seconds 5
    }
    Start-Sleep -Seconds 20
    $running = @($running | Where-Object { -not $_.HasExited })
}

Write-Output "batch done: $($accounts.Count) accounts, max $maxParallel parallel"
exit 0
