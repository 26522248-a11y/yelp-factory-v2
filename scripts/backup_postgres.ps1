# Daily logical backup of the pool database (keep the last 14 dumps).
# Binaries come from the portable Postgres inside the repo: data/pg/pgsql (see scripts/setup_pg_portable.ps1).
#
# Connection params are read from repo\.env (YF_DATABASE_URL) by default - the same
# pattern scripts\setup_test_db.ps1 uses. The password is NEVER printed or written.
# Do NOT hardcode the postgres password in here: it is rotated in .env, so a hardcoded
# default starts failing authentication silently and the nightly backup stops running.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\backup_postgres.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\backup_postgres.ps1 -BackupDir D:\pgbackup
param(
    [string]$BackupDir = "C:\pgbackup",
    [string]$EnvFile = (Join-Path $PSScriptRoot "..\.env"),
    # Explicit overrides win over .env; leave empty/0 to take the value from .env.
    [string]$DbHost = "",
    [int]$DbPort = 0,
    [string]$DbUser = "",
    [string]$DbPassword = "",
    [string]$DbName = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pgDump = Join-Path $projectRoot "data\pg\pgsql\bin\pg_dump.exe"
if (-not (Test-Path $pgDump)) {
    Write-Error "pg_dump not found at $pgDump - run scripts\setup_pg_portable.ps1 first"
    exit 1
}

function Read-DbUrlFromEnv {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        throw ".env not found at $Path - cannot read the DB credentials (backup must not guess them)"
    }
    $line = (Select-String -Path $Path -Pattern '^YF_DATABASE_URL=(.+)$' | Select-Object -First 1)
    if (-not $line) { throw "YF_DATABASE_URL not found in $Path" }
    $url = $line.Matches[0].Groups[1].Value.Trim()
    $m = [regex]::Match($url, '^[^:]+://([^:@/]+):([^@]+)@([^:/]+):(\d+)/([^?]+)')
    if (-not $m.Success) { throw "cannot parse connection params out of YF_DATABASE_URL" }
    return @{
        User     = [uri]::UnescapeDataString($m.Groups[1].Value)
        Password = [uri]::UnescapeDataString($m.Groups[2].Value)
        Host     = $m.Groups[3].Value
        Port     = [int]$m.Groups[4].Value
        Name     = $m.Groups[5].Value
    }
}

$creds = $null
if ([string]::IsNullOrWhiteSpace($DbUser) -or [string]::IsNullOrWhiteSpace($DbPassword) -or [string]::IsNullOrWhiteSpace($DbName)) {
    $creds = Read-DbUrlFromEnv -Path $EnvFile
}
if ([string]::IsNullOrWhiteSpace($DbHost)) { $DbHost = if ($creds) { $creds.Host } else { "127.0.0.1" } }
if ($DbPort -le 0) { $DbPort = if ($creds) { $creds.Port } else { 5433 } }
if ([string]::IsNullOrWhiteSpace($DbUser)) { $DbUser = $creds.User }
if ([string]::IsNullOrWhiteSpace($DbPassword)) { $DbPassword = $creds.Password }
if ([string]::IsNullOrWhiteSpace($DbName)) { $DbName = $creds.Name }

$ts = Get-Date -Format "yyyyMMdd_HHmm"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$target = Join-Path $BackupDir "yelp_factory_$ts.dump"
$log = Join-Path $BackupDir "backup_log.txt"
$env:PGPASSWORD = $DbPassword

& $pgDump -h $DbHost -p $DbPort -U $DbUser -Fc -f $target $DbName
$dumpExit = $LASTEXITCODE
Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue

if ($dumpExit -ne 0) {
    # Loud + recorded: a failing auth used to leave no trace at all.
    "FAILED $ts db=$DbName host=$DbHost`:$DbPort user=$DbUser exit=$dumpExit" | Out-File $log -Append -Encoding UTF8
    Write-Error "pg_dump failed (exit $dumpExit) - recorded in $log"
    exit 1
}
"OK $ts $target $((Get-Item $target).Length) bytes" | Out-File $log -Append -Encoding UTF8

# The dump holds password_enc; the master key (YF_MASTER_KEY) lives in .env and must NOT sit next to the dump.
# Only KEY NAMES are recorded here - copy .env yourself to a separate, off-machine location.
$envFile = Join-Path $projectRoot ".env"
if (Test-Path $envFile) {
    $reminder = @(
        "# yf backup $ts"
        "# .env cua ban LUU RIENG - khong cung thu muc dump, khong cung o dia C:"
        "# Cac key can backup:"
    )
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^([A-Za-z_][A-Za-z0-9_]*)=') { $reminder += "#   $($Matches[1])" }
    }
    $reminder += "# Luu o noi khac: encrypted volume / off-machine / secret manager."
    $reminder | Out-File (Join-Path $BackupDir "env_keys_$ts.txt") -Encoding UTF8
}

Get-ChildItem $BackupDir -Filter "yelp_factory_*.dump" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 14 | Remove-Item -Force
Get-ChildItem $BackupDir -Filter "env_keys_*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 14 | Remove-Item -Force
exit 0
