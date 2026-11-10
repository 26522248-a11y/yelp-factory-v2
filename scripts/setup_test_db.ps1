# Creates the NON-SECRET Postgres role + database the test suite uses, so the suite
# never needs the real (rotated) credentials and never depends on repo/.env existing.
#
# Idempotent: safe to re-run. Reads the postgres superuser password from the MAIN
# repo .env (never prints it) and NEVER writes to .env.
#
# Works inside a detached git worktree: psql/.env are auto-resolved from the main
# repo root (the worktree has no .env and no data/pg), so no parameters are needed.
# Explicit -Psql / -EnvFile always win when you pass them.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_test_db.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_test_db.ps1 -SkipSchema
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_test_db.ps1 -DryRun
#
# After this, tests/conftest.py points YF_DATABASE_URL at this DB by default:
#   postgresql+psycopg://yf_test:yf_test@127.0.0.1:5433/yelp_factory_test
param(
    [string]$EnvFile,
    [string]$Psql,
    [string]$DbHost = "127.0.0.1",
    [int]$Port = 5433,
    [string]$SuperUser = "postgres",
    [string]$TestDb = "yelp_factory_test",
    [string]$TestUser = "yf_test",
    [string]$TestPassword = "yf_test",
    [switch]$SkipSchema,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# --- resolve the MAIN repo root (worktree-safe) ---------------------------------
function Find-RepoRoot {
    param([string]$Start)

    $candidates = New-Object System.Collections.Generic.List[string]
    $dir = (Resolve-Path -LiteralPath $Start).Path
    while ($dir) {
        $candidates.Add($dir)
        $parent = Split-Path -Parent $dir
        if (-not $parent -or $parent -eq $dir) { break }
        $dir = $parent
    }

    # A worktree's .env + psql live in the main worktree: ask git for the common dir.
    try {
        $common = (& git -C $Start rev-parse --path-format=absolute --git-common-dir 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -eq 0 -and $common) {
            $candidates.Add((Split-Path -Parent $common.Trim()))
        }
    } catch {
        # git missing / not a repo: fall back to the walk-up chain only
    }

    foreach ($c in $candidates) {
        if ((Test-Path (Join-Path $c ".env")) -and (Test-Path (Join-Path $c "data\pg\pgsql\bin\psql.exe"))) {
            return $c
        }
    }
    return $null
}

$repoRoot = Find-RepoRoot -Start $PSScriptRoot
if (-not $repoRoot) { $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }

if (-not $Psql) { $Psql = Join-Path $repoRoot "data\pg\pgsql\bin\psql.exe" }
if (-not $EnvFile) { $EnvFile = Join-Path $repoRoot ".env" }

if ($DryRun) {
    Write-Output "repo root : $repoRoot"
    Write-Output "psql      : $Psql (exists: $(Test-Path $Psql))"
    Write-Output "env file  : $EnvFile (exists: $(Test-Path $EnvFile))"
    Write-Output "dry run: nothing was created or changed"
    return
}

if (-not (Test-Path $Psql)) { throw "psql not found at $Psql (pass -Psql <path>)" }
if (-not (Test-Path $EnvFile)) { throw ".env not found at $EnvFile (superuser password source; pass -EnvFile <path>)" }

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
Write-Output "repo root used: $repoRoot"

if (-not $SkipSchema) {
    $venvPy = Join-Path $repoRoot ".venv\Scripts\python.exe"
    $py = if (Test-Path $venvPy) { $venvPy } else { "python" }
    Push-Location $repoRoot
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
