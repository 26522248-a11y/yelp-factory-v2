"""Read-only secret scan over the whole git history.

Usage:
    python scripts/scan_secret_history.py [--repo .] [--out report.md]

For every blob reachable from any ref it looks for *credential-shaped* strings and
classifies each hit as:
  REAL      - value looks like a live credential (long, high entropy, not a placeholder)
  PLACEHOLDER - `<PWD>`, `xxx`, `...`, `SUB-XX...` etc. used in docs
  FIXTURE   - synthetic value from tests (repeated chars / known redaction fixtures)

It never prints a full secret: only the first 6 chars, so the report itself is safe
to commit. It does not touch the index, the working tree or any remote.
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

TEXT_EXT = {
    ".py", ".yaml", ".yml", ".json", ".ps1", ".bat", ".cmd", ".md", ".txt",
    ".csv", ".ini", ".toml", ".env", ".example", ".cfg", ".conf", ".sql",
}

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "db-url-password",
        re.compile(r"postgresql\+?(?:psycopg|asyncpg)?://[A-Za-z0-9_.-]+:([^@\s\"'<>]+)@"),
    ),
    ("master-key", re.compile(r"YF_MASTER_KEY=([A-Za-z0-9+/=_-]{8,})")),
    ("admin-token", re.compile(r"YF_ADMIN_TOKEN=([A-Za-z0-9_\-]{8,})")),
    ("gpm-license", re.compile(r"YF_GPM__LICENSE_KEY=([A-Za-z0-9_\-]{8,})")),
    ("gpm-mcp-token", re.compile(r"YF_GPM__MCP_TOKEN=([A-Za-z0-9_\-.]{8,})")),
    ("captcha-key", re.compile(r"YF_CAPTCHA__[A-Z_]+=([A-Za-z0-9_\-]{8,})")),
    (
        "graph-refresh-token",
        re.compile(r"YF_EMAIL__GRAPH_REFRESH_TOKEN=([A-Za-z0-9_.\-]{20,})"),
    ),
    ("proxy-raw", re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3}:\d{2,5}:[A-Za-z0-9_.-]{1,32}:[^\s\"'`,]{4,})")),
    ("mailbox-password", re.compile(r"(?m)^[^\s|@]{2,64}@[A-Za-z0-9.-]+\|([^|]{6,64})\|[A-Za-z0-9_.\-]{20,}")),
    ("ms-refresh-token", re.compile(r"\b(M\.C[0-9]{3}_[A-Za-z0-9_.\-]{20,})")),
    ("bearer-token", re.compile(r"(?i)bearer\s+([A-Za-z0-9_\-.]{20,})")),
]

PLACEHOLDER_HINTS = (
    "<", ">", "...", "xxx", "XXXX", "SUB-XX", "postgres:postgres",
    "your-", "YOUR_", "changeme", "CHANGE_ME", "placeholder", "PWD", "TOKEN",
)

# Known synthetic values used by the redaction/import unit tests.
FIXTURE_HINTS = (
    "M.C524_BAY.",
    "PteNqaaFuP",
    "VjJAGiuOkX",
    "CAP-13DD600012FAB8F5E2591D4DF6A3397947BF8D1A89ED5399FB041917D5321E60",
    "Hunter2!",
    "abcdef123456",
)


def sh(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = Counter(s)
    return -sum((c / len(s)) * math.log2(c / len(s)) for c in counts.values())


def classify(secret: str) -> str:
    if any(h in secret for h in FIXTURE_HINTS):
        return "FIXTURE"
    if any(h in secret for h in PLACEHOLDER_HINTS):
        return "PLACEHOLDER"
    if len(secret) < 12 or entropy(secret) < 2.6:
        return "PLACEHOLDER"
    if re.fullmatch(r"x{6,}|0{6,}|1{6,}|\*+", secret):
        return "FIXTURE"
    return "REAL"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--out", default="data/secret_scan_report.md")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    revs = sh("git", "-C", str(repo), "rev-list", "--all").split()
    if not revs:
        print("no commits", file=sys.stderr)
        return 2

    findings: dict[str, dict] = {}
    scanned_blobs = 0
    for rev in revs:
        for path in sh("git", "-C", str(repo), "ls-tree", "-r", "--name-only", rev).splitlines():
            if Path(path).suffix.lower() not in TEXT_EXT and Path(path).name not in {".env", ".env.example"}:
                continue
            blob = subprocess.run(
                ["git", "-C", str(repo), "show", f"{rev}:{path}"],
                capture_output=True,
            ).stdout
            scanned_blobs += 1
            try:
                text = blob.decode("utf-8")
            except UnicodeDecodeError:
                continue
            for label, pattern in PATTERNS:
                for match in pattern.finditer(text):
                    secret = match.group(1)
                    key = (label, secret)
                    entry = findings.setdefault(
                        key,
                        {"kind": classify(secret), "files": set(), "commits": set(), "sample": secret[:6]},
                    )
                    entry["files"].add(path)
                    entry["commits"].add(rev[:7])

    real = {k: v for k, v in findings.items() if v["kind"] == "REAL"}
    lines = [
        "# Secret scan — toàn bộ git history",
        "",
        f"- refs/commits quét: **{len(revs)}**",
        f"- blob text đã quét: **{scanned_blobs}**",
        f"- chuỗi credential-shaped: **{len(findings)}** (REAL {len(real)}, "
        f"PLACEHOLDER {sum(1 for v in findings.values() if v['kind'] == 'PLACEHOLDER')}, "
        f"FIXTURE {sum(1 for v in findings.values() if v['kind'] == 'FIXTURE')})",
        "",
    ]
    if real:
        lines += ["## REAL (cần rotate)", "", "| loại | 6 ký tự đầu | file | commits |", "|---|---|---|---|"]
        for (label, _), v in sorted(real.items()):
            lines.append(
                f"| {label} | `{v['sample']}…` | {', '.join(sorted(v['files'])[:3])} | "
                f"{len(v['commits'])} commit |"
            )
    else:
        lines.append("## REAL\n\nKhông tìm thấy credential thật nào trong history.")
    lines += ["", "## REAL nhưng chỉ nằm ngoài git (không purge history được)", ""]
    lines += [
        "- `.env` (gitignored, không có trong bất kỳ commit nào)",
        "- `C:\\pgbackup\\*.dump` + `env_keys_*.txt` (dump DB + backup key)",
        "- `data/accounts_export/*` nếu tồn tại",
    ]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report: {out}")
    print(f"REAL={len(real)} total={len(findings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
