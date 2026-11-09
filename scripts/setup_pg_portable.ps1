<#
.SYNOPSIS
  Dung Postgres 16 portable cho may QA/dev theo DUNG duong dan chuan cua repo:
    binaries : <repo>\data\pg\pgsql
    cluster  : <repo>\data\pgdata
    port     : 5433
  Idempotent: chay lai duoc, khong pha cluster da co.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_pg_portable.ps1
#>
[CmdletBinding()]
param(
  [string]$Root = "",
  [int]$Port = 5433,
  [string]$DbName = "yelp_factory",
  [string]$DbUser = "postgres",
  [string]$DbPassword = "postgres",
  [string]$PgVersion = "16.6-1",
  [switch]$SkipEnv
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Root)) {
  $scriptDir = ""
  if ($PSScriptRoot) { $scriptDir = $PSScriptRoot }
  elseif ($MyInvocation.MyCommand.Definition) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition }
  $Root = Split-Path -Parent $scriptDir
}
$Root = (Resolve-Path $Root).Path

$dataRoot = Join-Path $Root "data"
New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null
$LogFile = Join-Path $dataRoot "setup_pg.log"

function Log([string]$m) {
  $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m
  Write-Output $line
  try { Add-Content -Path $LogFile -Value $line -Encoding UTF8 } catch {}
}

$pgRoot   = Join-Path $dataRoot "pg"
$binDir   = Join-Path $pgRoot "pgsql"
$dataDir  = Join-Path $dataRoot "pgdata"
$zipName  = "postgresql-$PgVersion-windows-x64-binaries.zip"
$zipPath  = Join-Path $pgRoot $zipName
$zipUrl   = "https://get.enterprisedb.com/postgresql/$zipName"

Log "=== setup_pg_portable: repo=$Root port=$Port db=$DbName ==="

# ---------------------------------------------------------------- 1. download
New-Item -ItemType Directory -Force -Path $pgRoot | Out-Null
if (Test-Path (Join-Path $binDir "bin\pg_ctl.exe")) {
  Log "Binaries da co tai $binDir - bo qua download."
} else {
  if (-not (Test-Path $zipPath) -or (Get-Item $zipPath).Length -lt 50MB) {
    Log "Download binaries: $zipUrl"
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
      $req = [System.Net.HttpWebRequest]::Create($zipUrl)
      $req.UserAgent = "Mozilla/5.0"
      $req.Timeout = 120000
      $resp = $req.GetResponse()
      $rs = $resp.GetResponseStream()
      $fs = [System.IO.File]::Open($zipPath, "Create", "Write", "None")
      $buf = New-Object byte[] 1048576
      $tot = 0; $next = 25MB
      while (($n = $rs.Read($buf, 0, $buf.Length)) -gt 0) {
        $fs.Write($buf, 0, $n); $tot += $n
        if ($tot -ge $next) { Log ("  da tai {0} MB ({1:N1} MB/s)" -f [math]::Round($tot/1MB), ($tot/1MB/[math]::Max($sw.Elapsed.TotalSeconds,0.1))); $next += 25MB }
      }
      $fs.Close(); $rs.Close(); $resp.Close()
      Log ("Download xong: {0} MB trong {1:N0}s" -f [math]::Round($tot/1MB), $sw.Elapsed.TotalSeconds)
    } catch {
      Log "DOWNLOAD FAIL: $($_.Exception.Message)"
      throw
    }
  } else {
    Log "Zip da ton tai: $zipPath"
  }

  # ------------------------------------------------------------ 2. extract
  Log "Giai nen vao $binDir ..."
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $extractDir = Join-Path $pgRoot "_extract"
  if (Test-Path $extractDir) { Remove-Item -Recurse -Force $extractDir }
  [System.IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $extractDir)
  $src = Join-Path $extractDir "pgsql"
  if (-not (Test-Path $src)) { $src = (Get-ChildItem $extractDir -Directory | Select-Object -First 1).FullName }
  if (Test-Path $binDir) { Remove-Item -Recurse -Force $binDir }
  Move-Item $src $binDir
  Remove-Item -Recurse -Force $extractDir
  Log "Binaries san sang: $binDir"
}

# ------------------------------------------------------------ 3. initdb
$initdb = Join-Path $binDir "bin\initdb.exe"
if (-not (Test-Path (Join-Path $dataDir "PG_VERSION"))) {
  New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
  $pwFile = Join-Path $env:TEMP "yf_pg_pw.txt"
  Set-Content -Path $pwFile -Value $DbPassword -NoNewline -Encoding ASCII
  $attempts = @(
    @{ args = @("-E","UTF8","--locale=C");        tag = "UTF8 + locale=C" },
    @{ args = @("-E","UTF8");                      tag = "UTF8 + locale mac dinh" },
    @{ args = @("--no-locale","-E","UTF8");        tag = "UTF8 + no-locale" },
    @{ args = @();                                tag = "mac dinh (SQL_ASCII)" }
  )
  $ok = $false
  foreach ($a in $attempts) {
    Log "initdb: thu cach [$($a.tag)]"
    $out = & $initdb @("-D", $dataDir, "-U", $DbUser, "--pwfile=$pwFile", "--auth-local=trust", "--auth-host=scram-sha-256") @($a.args) 2>&1
    if ($LASTEXITCODE -eq 0) {
      Log "initdb OK voi cach [$($a.tag)]"
      ($out | Select-Object -Last 6) | ForEach-Object { Log "  $_" }
      $ok = $true
      break
    } else {
      Log "initdb that bai voi [$($a.tag)] (exit=$LASTEXITCODE)"
      ($out | Select-Object -Last 4) | ForEach-Object { Log "  $_" }
    }
  }
  Remove-Item $pwFile -Force -ErrorAction SilentlyContinue
  if (-not $ok) { Log "initdb that bai het cac cach."; exit 2 }
} else {
  Log "Cluster da co tai $dataDir - giu nguyen."
}

# ------------------------------------------------------------ 4. config
$conf = Join-Path $dataDir "postgresql.conf"
$marker = "# --- yf portable pg ---"
$confText = Get-Content $conf -Raw
if ($confText -notmatch [regex]::Escape($marker)) {
  Add-Content -Path $conf -Encoding UTF8 -Value @"

$marker
port = $Port
listen_addresses = '127.0.0.1'
max_connections = 100
timezone = 'UTC'
log_timezone = 'UTC'
datestyle = 'iso, mdy'
"@
  Log "Da ghi config Postgres vao $conf (port=$Port, listen=127.0.0.1)."
} else {
  Log "postgresql.conf da duoc config san (port=$Port)."
}
$hba = Join-Path $dataDir "pg_hba.conf"
if (-not (Select-String -Path $hba -Pattern "127.0.0.1/32" -Quiet)) {
  Add-Content -Path $hba -Encoding UTF8 -Value "host    all             all             127.0.0.1/32            scram-sha-256`nhost    all             all             ::1/128                 scram-sha-256"
  Log "Da them rule host cho pg_hba.conf."
}

# ------------------------------------------------------------ 5. start
# Luu y: dung Start-Process, KHONG pipe stdout cua pg_ctl.
#  - Server postgres.exe giu write-end cua pipe -> pipeline PowerShell khong bao gio thay EOF -> treo.
#  - ArgumentList co duong dan chua space -> phai quote tay.
$pgCtl = Join-Path $binDir "bin\pg_ctl.exe"
$pgLog = Join-Path $dataRoot "pg.log"
$ctlOut = Join-Path $dataRoot "pg_ctl.out"
$ctlErr = Join-Path $dataRoot "pg_ctl.err"
$qData = '"' + $dataDir + '"'
$qLog  = '"' + $pgLog + '"'
$qOut  = '"' + $ctlOut + '"'
$qErr  = '"' + $ctlErr + '"'

$running = $false
if (Test-Path $pgCtl) {
  $st = Start-Process -FilePath $pgCtl -ArgumentList @("-D", $qData, "status") -NoNewWindow -Wait -PassThru -RedirectStandardOutput $ctlOut -RedirectStandardError $ctlErr -ErrorAction SilentlyContinue
  if ($st -and $st.ExitCode -eq 0) { $running = $true }
}
if ($running) {
  Log "Postgres da chay tren cluster $dataDir - bo qua start."
} else {
  Log "Start Postgres (port=$Port) ..."
  $p = Start-Process -FilePath $pgCtl -ArgumentList @("-D", $qData, "-l", $qLog, "-o", ('"-p ' + $Port + '"'), "-w", "-t", "60", "start") -NoNewWindow -Wait -PassThru -RedirectStandardOutput $ctlOut -RedirectStandardError $ctlErr
  if ($p.ExitCode -ne 0) {
    Log "pg_ctl start that bai (exit=$($p.ExitCode)). Output:"
    if (Test-Path $ctlOut) { Get-Content $ctlOut -Tail 20 | ForEach-Object { Log "  $_" } }
    if (Test-Path $ctlErr) { Get-Content $ctlErr -Tail 20 | ForEach-Object { Log "  $_" } }
    exit 3
  }
  Log "Postgres da start (port=$Port)."
}

# ------------------------------------------------------------ 6. create db
$psql = Join-Path $binDir "bin\psql.exe"
$env:PGPASSWORD = $DbPassword
$exists = (& $psql -h 127.0.0.1 -p $Port -U $DbUser -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DbName'" 2>$null | Out-String).Trim()
if ($exists -eq "1") {
  Log "Database $DbName da co."
} else {
  & $psql -h 127.0.0.1 -p $Port -U $DbUser -d postgres -c "CREATE DATABASE `"$DbName`"" 2>&1 | ForEach-Object { Log "  $_" }
  Log "Da tao database $DbName."
}

# ------------------------------------------------------------ 7. .env
if (-not $SkipEnv) {
  $envPath = Join-Path $Root ".env"
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  $existing = ""
  if (Test-Path $envPath) { $existing = [System.IO.File]::ReadAllText($envPath) }
  if ($existing.Length -gt 0 -and $existing[0] -eq [char]0xFEFF) { $existing = $existing.Substring(1) }
  $add = @()
  if ($existing -notmatch "(?m)^YF_DATABASE_URL=") {
    $b = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create(); $rng.GetBytes($b)
    $key = [Convert]::ToBase64String($b)
    $url = "postgresql+psycopg://$DbUser`:$DbPassword@127.0.0.1`:$Port/$DbName"
    $add += ""
    $add += "# --- yf QA local db (setup_pg_portable.ps1) ---"
    $add += "YF_DATABASE_URL=$url"
    $add += "YF_MASTER_KEY=$key"
  }
  if ($existing -notmatch "(?m)^YF_ADMIN_TOKEN=") {
    $t = New-Object byte[] 32
    $rng2 = [System.Security.Cryptography.RandomNumberGenerator]::Create(); $rng2.GetBytes($t)
    $tok = [Convert]::ToBase64String($t).Replace("+", "-").Replace("/", "_").TrimEnd("=")
    $add += "YF_ADMIN_TOKEN=$tok"
  }
  if ($add.Count -gt 0) {
    $text = $existing.TrimEnd("`r", "`n") + "`r`n" + ($add -join "`r`n") + "`r`n"
    [System.IO.File]::WriteAllText($envPath, $text, $utf8NoBom)
    Log ("Da them vao .env: " + (($add | Where-Object { $_ -match "^YF_" }) -join ", "))
    Log ".env: KHONG BOM, KHONG commit len git."
  } else {
    Log ".env da co YF_DATABASE_URL + YF_ADMIN_TOKEN - giu nguyen."
  }
}
# ------------------------------------------------------------ 8. verify
$ver = (& $psql -h 127.0.0.1 -p $Port -U $DbUser -d $DbName -tAc "select version()" 2>&1 | Out-String).Trim()
Log "VERIFY: $ver"
Log "Binaries : $binDir"
Log "Data dir : $dataDir"
Log "DSN      : postgresql+psycopg://$DbUser`:***@127.0.0.1`:$Port/$DbName"
Log "=== setup_pg_portable DONE ==="
