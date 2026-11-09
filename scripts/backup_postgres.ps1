# Daily logical backup of the pool database (keep the last 14 dumps).
# Binaries come from the portable Postgres inside the repo: data/pg/pgsql (see scripts/setup_pg_portable.ps1).
param(
    [string]$BackupDir = "C:\pgbackup",
    [string]$DbHost = "127.0.0.1",
    [int]$DbPort = 5433,
    [string]$DbUser = "postgres",
    [string]$DbPassword = "postgres",
    [string]$DbName = "yelp_factory"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pgDump = Join-Path $projectRoot "data\pg\pgsql\bin\pg_dump.exe"
if (-not (Test-Path $pgDump)) {
    Write-Error "pg_dump not found at $pgDump - run scripts\setup_pg_portable.ps1 first"
    exit 1
}

$ts = Get-Date -Format "yyyyMMdd_HHmm"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$target = Join-Path $BackupDir "yelp_factory_$ts.dump"
$env:PGPASSWORD = $DbPassword

& $pgDump -h $DbHost -p $DbPort -U $DbUser -Fc -f $target $DbName
if ($LASTEXITCODE -ne 0) {
    Write-Error "pg_dump failed (exit $LASTEXITCODE)"
    exit 1
}

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