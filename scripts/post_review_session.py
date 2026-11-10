"""Run one post-review warm session for a single account without the factory DB.

The session walks the P0->P4 ladder through the factory's PostReviewWarmRunner
(no review actions), restores the login first when the session died, keeps a tiny
per-account state file (once per day, resume block, metro history), takes a lock so
two runs can never overlap, and raises alert files on failures.

Usage:
    python scripts/post_review_session.py \
        --profile-id <gpm-profile> --email a@outlook.com \
        --user-id tu5r... --city "Brooklyn, NY" --minutes 120

The password is never passed on the command line: it is decrypted from
accounts.password_enc using YF_MASTER_KEY. --password stays available for a
throwaway account that is not in the DB yet.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from adapters.browser import attach, is_logged_in  # noqa: E402
from core.alerts import notify as alert  # noqa: E402
from core.config import load_settings  # noqa: E402
from core.post_review import record_metro_visit, within_window  # noqa: E402
from flows.login_flow import LoginFlow  # noqa: E402
from flows.post_review_warm import PostReviewWarmRunner  # noqa: E402
from selector_registry.resolver import SelectorRegistry  # noqa: E402

STATE_DIR = ROOT / "artifacts" / "post_review_state"
LOCK_STALE_HOURS = 5  # longer than any session (120 min) + login overhead


def _tag(email: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in email)[:40]


def _start_profile(settings, profile_id: str) -> int | None:
    """Start the GPM profile and return its remote debugging port."""
    import httpx

    base = settings.gpm.base_url.rstrip("/")
    try:
        response = httpx.get(
            f"{base}/api/v1/profiles/start/{profile_id}",
            params={"skip_proxy_check": "true", "window_size": "1280,800"},
            timeout=settings.gpm.start_timeout_s,
        )
        data = response.json().get("data") or {}
        return int(data.get("remote_debugging_port") or 0) or None
    except Exception:  # noqa: BLE001
        return None


def _state_path(email: str) -> Path:
    return STATE_DIR / f"{_tag(email)}.json"


def _load_state(email: str) -> dict:
    path = _state_path(email)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save_state(email: str, state: dict) -> None:
    path = _state_path(email)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------------------
# per-account lock: scheduled + manual runs must never produce two sessions (2026-11-09)
# --------------------------------------------------------------------------------------


def _pid_alive(pid: int) -> bool:
    try:
        import psutil

        return psutil.pid_exists(pid)
    except Exception:  # noqa: BLE001
        return False


def _acquire_lock(email: str) -> Path | None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{_tag(email)}.lock"
    now = datetime.now(timezone.utc)
    if path.exists():
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            info = {}
        started = info.get("started_utc", "")
        pid = int(info.get("pid") or 0)
        fresh = False
        try:
            fresh = (now - datetime.fromisoformat(started)).total_seconds() < LOCK_STALE_HOURS * 3600
        except ValueError:
            fresh = False
        if fresh and (pid == 0 or _pid_alive(pid)):
            print(json.dumps({"status": "LOCKED", "lock": str(path), "pid": pid}))
            return None
        path.unlink(missing_ok=True)  # stale lock
    path.write_text(json.dumps({"pid": os.getpid(), "started_utc": now.isoformat()}), encoding="utf-8")
    return path


def _release_lock(path: Path | None) -> None:
    if path is not None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _password_from_db(email: str) -> str | None:
    """Decrypt accounts.password_enc for this email; None when the account is absent."""
    try:
        from core.crypto import SecretBox
        from db.models import Account
        from db.session import session_scope

        with session_scope() as session:
            row = session.query(Account).filter(Account.email == email).one_or_none()
            if row is None or row.password_enc is None:
                return None
            return SecretBox().decrypt(row.password_enc)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": "password_decrypt_failed", "detail": str(exc)[:200]}))
        return None


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-id", default=None, help="GPM profile id; the script starts/stops it via the GPM API")
    parser.add_argument("--port", type=int, default=None, help="attach to an already-running GPM browser")
    parser.add_argument("--mail-profile-id", default=None, help="mail-reader GPM profile for fakemailo (E-67)")
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--password",
        default=None,
        help="omit to decrypt password_enc for --email from the DB (YF_MASTER_KEY)",
    )
    parser.add_argument("--user-id", default=None)
    parser.add_argument("--city", default=None, help="account metro, e.g. 'Brooklyn, NY'")
    parser.add_argument("--minutes", type=int, default=None, help="cap session minutes (omit = random 25-90)")
    parser.add_argument("--force", action="store_true", help="ignore the once-per-day guard")
    parser.add_argument("--ignore-window", action="store_true", help="manual runs: ignore the daily window")
    args = parser.parse_args()

    settings = load_settings()
    password = args.password
    if password is None:
        password = _password_from_db(args.email)
        if password is None:
            print(json.dumps({"error": "password_not_found", "email": args.email,
                              "hint": "pass --password or seed the account first"}))
            return 2

    if not args.ignore_window and not within_window(start=settings.post_review.window_start, end=settings.post_review.window_end):
        print(json.dumps({"status": "SKIPPED", "reason": "outside_window"}))
        return 0

    state = _load_state(args.email)
    today = date.today().isoformat()
    if not args.force and state.get("last_run_date") == today:
        print(json.dumps({"status": "SKIPPED_TODAY", "last_run_date": state["last_run_date"]}))
        return 0

    lock = _acquire_lock(args.email)
    if lock is None:
        return 3

    try:
        port = args.port
        if port is None:
            if not args.profile_id:
                print(json.dumps({"error": "need --profile-id or --port"}))
                return 2
            port = _start_profile(settings, args.profile_id)
            if port is None:
                alert("gpm_start_failed", account=args.email, detail={"profile_id": args.profile_id})
                print(json.dumps({"error": "gpm_start_failed", "hint": "is GPMLogin Global running?"}))
                return 1

        browser = await attach(f"http://127.0.0.1:{port}", timeout_s=settings.gpm.connect_timeout_s)
        # Global hard cap: never more than max_concurrent open profiles (same DB slots
        # the scheduler uses), so a manual fallback run cannot exceed 2 either.
        from core.lock import acquire_slot, release_slot

        slot = acquire_slot(f"script-{_tag(args.email)[:16]}", settings.post_review.max_concurrent, purpose="warm")
        if slot is None:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001
                pass
            if args.profile_id and args.port is None:
                import httpx

                try:
                    httpx.get(f"{settings.gpm.base_url.rstrip('/')}/api/v1/profiles/stop/{args.profile_id}", timeout=15)
                except Exception:  # noqa: BLE001
                    pass
            print(json.dumps({"status": "SLOTS_FULL", "max_concurrent": settings.post_review.max_concurrent}))
            return 5
        try:
            page = browser.page
            # A freshly started profile sits on a blank tab; the session check needs a
            # real Yelp page before is_logged_in can see the account markers.
            try:
                await page.goto("https://www.yelp.com/?locale=en_US", wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(3000)
            except Exception:  # noqa: BLE001
                pass
            logged_in = await is_logged_in(page)
            if not logged_in:
                print(json.dumps({"info": "session lost -> running LoginFlow"}))
                from adapters.email_fakemailo import FakemailoMailbox

                mail_browser = None
                mail_page = page
                if args.mail_profile_id and args.mail_profile_id != args.profile_id:
                    # E-67: mobile proxies cannot reach fakemailo - read the link through a
                    # dedicated (residential) profile in a NEW TAB so its own session is not disturbed.
                    mail_port = _start_profile(settings, args.mail_profile_id)
                    if mail_port:
                        mail_browser = await attach(f"http://127.0.0.1:{mail_port}", timeout_s=settings.gpm.connect_timeout_s)
                        mail_page = await mail_browser.context.new_page()

                async def reader_page():
                    return mail_page

                mail = FakemailoMailbox(
                    url=settings.email.fakemailo_url,
                    service=settings.email.fakemailo_service,
                    page_factory=reader_page,
                )
                flow = LoginFlow(registry=SelectorRegistry.from_yaml(), settings=settings, email_provider=mail)
                try:
                    result = await flow.run(page, email=args.email, password=password, user_id=args.user_id)
                    print(json.dumps({"login": result.to_json()}))
                    login_ok = result.ok
                except Exception as exc:  # noqa: BLE001
                    print(json.dumps({"login_error": str(exc)[:300]}))
                    login_ok = False
                    result = None
                if mail_browser is not None:
                    try:
                        await mail_browser.close()  # disconnect only; the reader profile keeps its data
                    except Exception:  # noqa: BLE001
                        pass
                if not login_ok:
                    detail = result.to_json() if result is not None else {"error": "login_exception"}
                    alert("login_failed", account=args.email, detail=detail)
                    return 1

            resumed = state.get("in_progress")
            if resumed and state.get("in_progress_ts"):
                print(json.dumps({"info": "crash_recovered", "phase": resumed}))
                state["resume"] = state.get("resume") or resumed
            state.pop("in_progress", None)

            def remember_block(phase: str) -> None:
                # heartbeat so a crash mid-block is recoverable (not just block ends)
                state["in_progress"] = phase
                state["in_progress_ts"] = datetime.now(timezone.utc).isoformat()
                _save_state(args.email, state)

            runner = PostReviewWarmRunner(registry=SelectorRegistry.from_yaml(), settings=settings)
            outcome = await runner.run_session(
                page,
                account_id=None,
                max_seconds=(args.minutes * 60 if args.minutes else None),
                resume_phase=state.get("resume"),
                city=args.city,
                user_id=args.user_id,
                fill_profile=not state.get("profile_filled", False),
                on_block=remember_block,
            )
            state["last_run_date"] = today
            state["resume"] = outcome.get("resume_phase")
            state["last_outcome"] = {k: v for k, v in outcome.items() if k != "actions"}
            state["last_action_count"] = len(outcome.get("actions", []))
            if "profile_filled" in outcome.get("actions", []):
                state["profile_filled"] = True
            if args.city:
                record_metro_visit(state, args.city, today=today)
            state.pop("in_progress", None)
            _save_state(args.email, state)
            print(json.dumps({"status": "COMPLETED", **outcome}, default=str))
            return 0
        finally:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001
                pass
            if args.profile_id and args.port is None:
                try:
                    import httpx

                    httpx.get(
                        f"{settings.gpm.base_url.rstrip('/')}/api/v1/profiles/stop/{args.profile_id}",
                        timeout=15,
                    )
                except Exception:  # noqa: BLE001
                    pass
    except Exception as exc:  # noqa: BLE001
        alert("session_crashed", account=args.email, detail={"error": str(exc)[:400]})
        raise
    finally:
        _release_lock(lock)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
