# Creates the NON-SECRET Postgres role + database the test suite uses, so the suite
# never needs the real (rotated) credentials and never depends on repo/.env existing.
#
# Idempotent: safe to re-run. Reads the postgres superuser password from repo/.env
# (never prints it) and NEVER writes to .env.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_test_db.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_test_db.ps1 -SkipSchema
#
# After this, tests/conftest.py points YF_DATABASE_URL at this DB by default:
#   postgresql+psycopg://yf_test:yf_test@127.0.0.1:5433/yelp_factory_test
param(
    [string]$EnvFile = (Join-Path $PSScriptRoot "..\.env"),
    [string]$Psql = (Join-Path $PSScriptRoot "..\data\pg\pgsql\bin\psql.exe"),
    [string]$DbHost = "127.0.0.1",
    [int]$Port = 5433,
    [string]$SuperUser = "postgres",
    [string]$TestDb = "yelp_factory_test",
    [string]$TestUser = "yf_test",
    [string]$TestPassword = "yf_test",
    [switch]$SkipSchema
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Psql)) { throw "psql not found at $Psql (pass -Psql <path>)" }
if (-not (Test-Path $EnvFile)) { throw ".env not found at $EnvFile (superuser password source)" }

$url = (Select-String -Path $EnvFile -Pattern '^YF_DATABASE_URL=(.+)$' | Select-Object -First 1).Matches[0].Groups[1].Value.Trim()
if (-not $url) { throw "YF_DATABASE_URL not found in .env" }
$m = [regex]::Match($url, '^[^:]+://([^:]+):([^@]+)@')
if (-not $m.Success) { throw "cannot parse credentials out of YF_DATABASE_URL" }
$env:PGPASSWORD = [uri]::UnescapeDataString($m.Groups[2].Value)

function Invoke-Psql {
    param([string]$Sql)
    $out = & $Psql -h $DbHost -p $Port -U $SuperUser -d postgres -v ON_ERROR_STOP=1 -tAc $Sql 2>&1
    if ($LASTEXITCODE -ne 0) { throw "psql failed: $out" }
    return ($out | Out-String).Trim()
}

$roleExists = (Invoke-Psql -Sql "SELECT 1 FROM pg_roles WHERE rolname = '$TestUser'")
if ($roleExists -eq "1") {
    Invoke-Psql -Sql "ALTER ROLE $TestUser WITH LOGIN PASSWORD '$TestPassword'" | Out-Null
    Write-Output "role $TestUser exists -> password reset to the non-secret test value"
} else {
    Invoke-Psql -Sql "CREATE ROLE $TestUser WITH LOGIN PASSWORD '$TestPassword'" | Out-Null
    Write-Output "role $TestUser created (LOGIN, non-secret password)"
}

$dbExists = (Invoke-Psql -Sql "SELECT 1 FROM pg_database WHERE datname = '$TestDb'")
if ($dbExists -eq "1") {
    Write-Output "database $TestDb exists"
} else {
    Invoke-Psql -Sql "CREATE DATABASE $TestDb OWNER $TestUser" | Out-Null
    Write-Output "database $TestDb created (owner $TestUser)"
}

$testUrl = "postgresql+psycopg://{0}:{1}@{2}:{3}/{4}" -f $TestUser, $TestPassword, $DbHost, $Port, $TestDb
Write-Output "test database url: $testUrl"

if (-not $SkipSchema) {
    $venvPy = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
    $py = if (Test-Path $venvPy) { $venvPy } else { "python" }
    Push-Location (Join-Path $PSScriptRoot "..")
    try {
        $saved = $env:YF_DATABASE_URL
        $savedPath = $env:PYTHONPATH
        $env:YF_DATABASE_URL = $testUrl
        if (-not $savedPath) { $env:PYTHONPATH = "src" }
        & $py -m cli db-init
        if ($LASTEXITCODE -ne 0) { throw "db-init failed for $TestDb" }
    } finally {
        if ($null -eq $saved) { Remove-Item Env:\YF_DATABASE_URL -ErrorAction SilentlyContinue } else { $env:YF_DATABASE_URL = $saved }
        if ($null -eq $savedPath) { Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue } else { $env:PYTHONPATH = $savedPath }
        Pop-Location
    }
}

Write-Output "done: the test suite now defaults to $TestDb (non-secret credentials, no .env required)"
