# Daily post-review warm session - Betty M. (Resi US - sess 0486848620)
# Registered in Task Scheduler to run once per day (see docs/USER_GUIDE.md).
$root = Split-Path -Parent $PSScriptRoot
& "$root\.venv\Scripts\python.exe" "$root\scripts\post_review_session.py" `
    --profile-id "4c2b5b3c-8c63-4445-80f7-901709433f4c" `
    --email "benita198617nellie966cyjpvk@outlook.com" `
    --password "c8DeborahueA63tk" `
    --user-id "tu5rZ7CTBpe6oTZNowzWsg" `
    --minutes 60
exit $LASTEXITCODE
