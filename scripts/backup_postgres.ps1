# Daily logical backup of the pool database (keep the last 14 dumps).
$ts = Get-Date -Format "yyyyMMdd_HHmm"
$dir = "C:\pgbackup"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$target = Join-Path $dir "yelp_factory_$ts.dump"
& "C:\pg16\bin\pg_dump.exe" -h 127.0.0.1 -p 5433 -U postgres -Fc -f $target yelp_factory
if ($LASTEXITCODE -ne 0) {
    Write-Error "pg_dump failed with exit code $LASTEXITCODE"
    exit 1
}
# The dump contains password_enc; the master key lives in .env and must be stored
# somewhere else too (C6). Keep a dated copy next to the dumps as a reminder.
$envFile = Join-Path (Split-Path -Parent $PSScriptRoot) ".env"
if (Test-Path $envFile) {
    Copy-Item $envFile (Join-Path $dir "env_$ts.bak") -Force
}
Get-ChildItem $dir -Filter "yelp_factory_*.dump" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 14 |
    Remove-Item -Force
Get-ChildItem $dir -Filter "env_*.bak" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 14 |
    Remove-Item -Force
exit 0
