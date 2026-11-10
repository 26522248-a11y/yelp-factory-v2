<#
  schema_fingerprint.ps1 - in "van tay" schema cua mot DB (tables + index + constraint)
  de so sanh hai con DB ma khong phu thuoc vao alembic/db-check.

  Vi sao can: Alembic autogenerate chi so "basic changes in indexes and explicitly-named
  unique constraints" (alembic issue #428), nen index bieu thuc nhu
  lower(mailbox_email) va partial index nhu uq_runs_one_running_per_account la diem mu.
  => db-check ok:true KHONG chung minh duoc schema dung. Phai so sanh truc tiep.

  Cach dung (sau khi viet lai 0001 thanh op.create_table tuong minh):
    powershell -File scripts\schema_fingerprint.ps1 -DbName yelp_factory
    powershell -File scripts\schema_fingerprint.ps1 -DbName yf_chain_probe -CompareTo yelp_factory
  Ky vong: "DIFF: 0" va cung fingerprint.

  Tham so mac dinh khop Postgres portable cua repo (data/pg/pgsql, port 5433).
  Credentials duoc doc tu repo\.env (YF_DATABASE_URL) - KHONG hardcode password o day,
  vi password da rotate trong .env nen default cu se fail authentication.
  Password khong bao gio duoc in ra.
#>
param(
  [string]$DbName = "yelp_factory",
  [string]$CompareTo = "",
  [string]$DbHost = "",
  [int]$Port = 0,
  [string]$User = "",
  [string]$Password = "",
  [string]$EnvFile = "",
  [string]$PgBin = "",
  # Mac dinh bo qua bang/index/constraint cua alembic_version, vi DB vua install
  # (create_all, chua stamp) khong co chung va khong phai la "schema lech".
  [bool]$IgnoreAlembicVersion = $true
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($PgBin)) {
  $PgBin = Join-Path $projectRoot "data\pg\pgsql\bin"
}
$psql = Join-Path $PgBin "psql.exe"
if (-not (Test-Path $psql)) { throw "Khong thay psql.exe tai $psql (dung -PgBin de chi duong dan)" }

if ([string]::IsNullOrWhiteSpace($EnvFile)) { $EnvFile = Join-Path $projectRoot ".env" }

function Read-DbUrlFromEnv {
  param([string]$Path)
  if (-not (Test-Path $Path)) {
    throw ".env not found at $Path - cannot read the DB credentials (fingerprint must not guess them)"
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
  }
}

$creds = $null
if ([string]::IsNullOrWhiteSpace($User) -or [string]::IsNullOrWhiteSpace($Password)) {
  $creds = Read-DbUrlFromEnv -Path $EnvFile
}
if ([string]::IsNullOrWhiteSpace($DbHost)) { $DbHost = if ($creds) { $creds.Host } else { "127.0.0.1" } }
if ($Port -le 0) { $Port = if ($creds) { $creds.Port } else { 5433 } }
if ([string]::IsNullOrWhiteSpace($User)) { $User = $creds.User }
if ([string]::IsNullOrWhiteSpace($Password)) { $Password = $creds.Password }

$env:PGPASSWORD = $Password

function Invoke-PsqlLines {
  param([string]$Database, [string]$Sql)
  $raw = & $psql -h $DbHost -p $Port -U $User -d $Database -tA -F "|" -c $Sql 2>&1
  if ($LASTEXITCODE -ne 0) { throw ("psql that bai tren DB " + $Database + ": " + ($raw -join " ")) }
  return @($raw | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ -ne "" })
}

function Get-SchemaLines {
  param([string]$Database, [bool]$IgnoreAlembic = $false)

  $qTables = @"
select 'TABLE  ' || table_name
from information_schema.tables
where table_schema = 'public' and table_type = 'BASE TABLE'
"@

  # indexdef duoc chuan hoa khoang trang de so sanh on dinh giua 2 DB
  $qIndexes = @"
select 'INDEX  ' || indexname || ' :: ' || regexp_replace(indexdef, '\s+', ' ', 'g')
from pg_indexes
where schemaname = 'public'
"@

  $qConstraints = @"
select 'CONSTR ' || conrelid::regclass::text || ' :: ' || conname || ' :: ' || pg_get_constraintdef(oid)
from pg_constraint
where connamespace = 'public'::regnamespace and contype in ('u','c','f','p')
"@

  if ($IgnoreAlembic) {
    # alembic_version la metadata cua alembic, khong phai schema nghiep vu
    $qTables += "`n  and table_name <> 'alembic_version'"
    $qIndexes += "`n  and indexname not like '%alembic_version%'"
    $qConstraints += "`n  and conrelid::regclass::text <> 'alembic_version'"
  }

  $lines = @()
  $lines += Invoke-PsqlLines -Database $Database -Sql ($qTables + "`norder by table_name")
  $lines += Invoke-PsqlLines -Database $Database -Sql ($qIndexes + "`norder by indexname")
  $lines += Invoke-PsqlLines -Database $Database -Sql ($qConstraints + "`norder by conrelid::regclass::text, conname")
  return @($lines | Sort-Object -CaseSensitive)
}

function Get-Fingerprint {
  param([string[]]$Lines)
  $text = ($Lines -join "`n")
  $sha = [System.Security.Cryptography.SHA256]::Create()
  $hash = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($text))
  return (($hash | ForEach-Object { $_.ToString("x2") }) -join "")
}

$linesA = Get-SchemaLines -Database $DbName -IgnoreAlembic $IgnoreAlembicVersion
$fpA = Get-Fingerprint -Lines $linesA
$countsA = @{
  Tables      = @($linesA | Where-Object { $_ -like "TABLE*" }).Count
  Indexes     = @($linesA | Where-Object { $_ -like "INDEX*" }).Count
  Constraints = @($linesA | Where-Object { $_ -like "CONSTR*" }).Count
}

Write-Output ("DB        : " + $DbName + " (" + $DbHost + ":" + $Port + ")")
Write-Output ("Tables    : " + $countsA.Tables)
Write-Output ("Indexes   : " + $countsA.Indexes)
Write-Output ("Constraints: " + $countsA.Constraints)
Write-Output ("Fingerprint: " + $fpA)
Write-Output "--- schema lines ---"
$linesA | ForEach-Object { Write-Output $_ }

if (-not [string]::IsNullOrWhiteSpace($CompareTo)) {
  $linesB = Get-SchemaLines -Database $CompareTo -IgnoreAlembic $IgnoreAlembicVersion
  $fpB = Get-Fingerprint -Lines $linesB
  $onlyA = @($linesA | Where-Object { $linesB -notcontains $_ })
  $onlyB = @($linesB | Where-Object { $linesA -notcontains $_ })
  $diff = $onlyA.Count + $onlyB.Count

  Write-Output ""
  Write-Output ("--- so sanh voi " + $CompareTo + " (fingerprint " + $fpB + ") ---")
  Write-Output ("DIFF: " + $diff)
  if ($diff -eq 0) {
    Write-Output "KET LUAN: hai DB cung schema (tables + index + constraint khop 100%)."
  } else {
    Write-Output ("Chi co o " + $DbName + ":")
    $onlyA | ForEach-Object { Write-Output ("  - " + $_) }
    Write-Output ("Chi co o " + $CompareTo + ":")
    $onlyB | ForEach-Object { Write-Output ("  + " + $_) }
    Write-Output "KET LUAN: schema LECH - khong duoc tin vao replay chain / install moi."
  }
}

Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
