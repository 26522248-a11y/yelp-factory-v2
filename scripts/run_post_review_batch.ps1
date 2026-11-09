# Post-review warm sessions for every managed account - at most 2 profiles at a time.
# Registered in Task Scheduler (YelpFactoryPostReviewDaily, 09:00 daily).
# Each account runs at most once per day (guard inside post_review_session.py).

$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$runner = Join-Path $root "scripts\post_review_session.py"
$logDir = Join-Path $root "artifacts\post_review_state"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# Mail-reader profile for fakemailo (E-67): the residential profile can reach it,
# mobile profiles cannot. Used only when a session is lost and login is needed.
$mailProfile = "4c2b5b3c-8c63-4445-80f7-901709433f4c"

$accounts = @(
    @{ id = "4c2b5b3c-8c63-4445-80f7-901709433f4c"; email = "benita198617nellie966cyjpvk@outlook.com";     password = "c8DeborahueA63tk";  uid = "tu5rZ7CTBpe6oTZNowzWsg"; city = "Manhattan, NY" },
    @{ id = "bf35df54-afa8-4fc7-a3ee-6cac8541266e"; email = "patricialopezsteven924ebtsthxq@outlook.com"; password = "r3LauraoiU34vk";    uid = "KEdVZKG-MSXbRTxvuvabjA"; city = "Brooklyn, NY" },
    @{ id = "618de509-6ad4-41bb-9f27-112ba77959e1"; email = "cassie199115heidi722w0cz2w@outlook.com";     password = "a1SharonoaU92ee";  uid = "IfPWol9uBd4CsEZfACGjBg"; city = "Queens, NY" },
    @{ id = "7b6aae75-9d7c-4f5b-95dd-fb70d984bb51"; email = "helenwrightrichard712ulzr4o34@outlook.com";  password = "h0ElizabethoaU65td"; uid = "anfLEXysAQlqZKfZcH321w"; city = "Bronx, NY" }
)

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
        $argList = @(
            "`"$runner`"", "--profile-id", "`"$($a.id)`"",
            "--email", "`"$($a.email)`"", "--password", "`"$($a.password)`"",
            "--user-id", "`"$($a.uid)`"", "--city", "`"$($a.city)`"",
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
