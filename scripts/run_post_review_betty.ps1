# Daily post-review warm session - single account (Betty M. / Resi US).
# Registered in Task Scheduler to run once per day (see docs/USER_GUIDE.md).
#
# Credentials live OUTSIDE git: data/post_review_accounts.json (data/ is gitignored).
# Schema: docs/seed_accounts.example.json. The password is decrypted from the DB by
# post_review_session.py (YF_MASTER_KEY) - it is never passed on the command line.
#
# Usage: .\scripts\run_post_review_betty.ps1 [-AccountIndex 0]

param(
    [int]$AccountIndex = 0,
    [string]$AccountsFile = (Join-Path (Split-Path -Parent $PSScriptRoot) "data\post_review_accounts.json")
)

$root = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path $AccountsFile)) {
    Write-Error "missing $AccountsFile - copy docs/seed_accounts.example.json there and fill in real values (never commit it)"
    exit 2
}

$accounts = @(Get-Content -Raw $AccountsFile | ConvertFrom-Json).accounts
if ($accounts.Count -le $AccountIndex) {
    Write-Error "$AccountsFile has no account at index $AccountIndex"
    exit 2
}
$account = $accounts[$AccountIndex]

& "$root\.venv\Scripts\python.exe" "$root\scripts\post_review_session.py" `
    --profile-id "$($account.gpm)" `
    --email "$($account.email)" `
    --user-id "$($account.user_id)" `
    --city "$($account.city)" `
    --minutes 60
exit $LASTEXITCODE
