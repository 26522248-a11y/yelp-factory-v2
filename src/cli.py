"""``yf`` command line entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from core.config import get_settings
from obs.log import configure_logging, get_logger

log = get_logger("cli")


def _print(payload) -> None:
    print(json.dumps(payload, indent=2, default=str, ensure_ascii=False))


def _deps(settings):
    from adapters.captcha import build_chain
    from adapters.email import build_provider
    from adapters.gpm_mcp import HybridGPM
    from adapters.gpm_http import GPMHttpClient
    from core.orchestrator import SignupDeps
    from selector_registry.resolver import SelectorRegistry

    http = GPMHttpClient(base_url=settings.gpm.base_url, flavor=settings.gpm.flavor, timeout=settings.gpm.connect_timeout_s)
    gpm = HybridGPM(settings.gpm.mcp_url, settings.gpm.mcp_token, http)
    email_provider = build_provider(settings)
    captcha = build_chain(settings.captcha)
    registry = SelectorRegistry.from_yaml()
    sms_provider = None
    if settings.sms.api_key:
        from adapters.sms import HupSmsProvider, SmsActivateProvider

        if settings.sms.provider == "hup":
            sms_provider = HupSmsProvider(
                settings.sms.api_key,
                service_id=settings.sms.service_id,
                timeout_s=settings.sms.timeout_s,
            )
        else:
            sms_provider = SmsActivateProvider(settings.sms.api_key, country=settings.sms.country)
    return SignupDeps(
        settings=settings, gpm=gpm, registry=registry, email=email_provider, captcha=captcha, sms=sms_provider
    )


def cmd_avatar(args) -> int:
    import uuid as _uuid

    from sqlalchemy import select

    from core.orchestrator import upload_avatar
    from db.models import Account, AccountState
    from db.session import session_scope

    settings = get_settings()
    deps = _deps(settings)
    if getattr(args, "batch", None):
        from core.batches import batch_account_ids

        ids = batch_account_ids(args.batch)
    elif args.all or args.missing:
        statement = select(Account.id).where(
            Account.state.in_(
                (AccountState.ACTIVE.value, AccountState.WARMING.value, AccountState.ONBOARDED.value)
            )
        )
        if args.missing:
            statement = statement.where(Account.substate.is_distinct_from("avatar_uploaded"))
        with session_scope() as session:
            ids = list(session.scalars(statement.order_by(Account.created_at)))
    else:
        if not args.account:
            _print({"error": "account_required"})
            return 2
        ids = [_uuid.UUID(args.account)]

    async def run_all():
        semaphore = asyncio.Semaphore(max(1, args.concurrency))

        async def one(account_id):
            async with semaphore:
                try:
                    return await upload_avatar(account_id, deps, avatar_path=args.file)
                except Exception as exc:  # noqa: BLE001
                    return {"account": str(account_id), "ok": False, "error": str(exc)[:200]}

        return await asyncio.gather(*(one(account_id) for account_id in ids))

    results = list(asyncio.run(run_all())) if ids else []
    ok = sum(1 for item in results if item.get("ok"))
    _print({"count": len(results), "ok": ok, "results": results})
    return 0 if ok == len(results) else 1


def cmd_status(args) -> int:
    from core.batches import list_batches, status_snapshot

    snapshot = status_snapshot()
    print("accounts: " + " ".join(f"{key}={value}" for key, value in sorted(snapshot["states"].items())))
    print(
        f"warming : sessions_today={snapshot['sessions_today']} "
        f"actions_today={snapshot['actions_today']} "
        f"pending_tasks={snapshot['pending_tasks']} done_today={snapshot['done_today']}"
    )
    print(f"next_due: {snapshot['next_due'] or '-'}")
    rows = list_batches()
    if args.by_batch:
        for item in rows:
            phases = ", ".join(f"{key}:{value}" for key, value in (item["phases"] or {}).items()) or "-"
            trust = (
                f"{item['trust_min']}-{item['trust_max']}"
                if item["trust_min"] is not None
                else "-"
            )
            actions = ", ".join(f"{key}:{value}" for key, value in item["next_actions"].items()) or "-"
            print(
                f"{item['name']:<4} {item['accounts']:>3} acc  {item['status']:<8} "
                f"{phases:<26} sessions={item['sessions_today']:<3} actions={item['actions_today']:<4} "
                f"trust={trust:<7} next={actions}"
            )
    else:
        print(f"batches : {len(rows)}")
    return 0


def cmd_batch(args) -> int:
    import json

    from core import batches as store

    action = args.batch_action
    name = args.name or getattr(args, "name_opt", None)
    if action not in ("list", "backfill") and not name:
        print("batch name required")
        return 2
    try:
        if action == "create":
            print(json.dumps(store.create_batch(name, source=args.source, target_count=args.target, notes=args.notes), default=str))
        elif action == "list":
            for item in store.list_batches():
                phases = ", ".join(f"{key}:{value}" for key, value in (item["phases"] or {}).items()) or "-"
                print(
                    f"{item['name']:<4} {item['accounts']:>3} acc  {item['status']:<8} {phases:<26} "
                    f"sessions={item['sessions_today']} actions={item['actions_today']} "
                    f"next={item['next_actions']}"
                )
        elif action == "show":
            print(json.dumps(store.batch_summary(name), default=str, ensure_ascii=False, indent=2))
        elif action == "next":
            print(json.dumps(store.batch_next(name), default=str, ensure_ascii=False, indent=2))
        elif action == "backfill":
            print(json.dumps(store.backfill_legacy()))
        elif action == "pause":
            print(json.dumps(store.set_status(name, "paused")))
        elif action == "resume":
            print(json.dumps(store.set_status(name, "warming")))
        elif action == "close":
            print(json.dumps(store.set_status(name, "closed")))
        else:
            print(f"unknown action: {action}")
            return 2
    except ValueError as exc:
        print(str(exc))
        return 2
    return 0


def cmd_trust(args) -> int:
    import uuid as _uuid

    from core.trust import compute_trust, latest_trust, recompute_all, review_eligible

    if getattr(args, "recompute", False):
        if getattr(args, "all", False) or not args.account:
            from datetime import datetime

            from core.flags import get_flag, set_flag

            today = datetime.now().date().isoformat()
            marker = get_flag("trust_recompute", {})
            if marker.get("date") == today and not getattr(args, "force", False):
                _print({"skipped": "already_recomputed_today", "date": today})
                return 0
            result = recompute_all()
            set_flag("trust_recompute", {"date": today, "count": result.get("count", 0)})
            _print({"recompute": result})
            return 0
        from core.trust import record_trust

        account_id = _uuid.UUID(args.account)
        score = record_trust(account_id)
        _print({"account": str(account_id), "score": score, "components": compute_trust(account_id).as_dict()})
        return 0

    if not args.account:
        _print({"error": "account_required"})
        return 2
    account_id = _uuid.UUID(args.account)
    breakdown = compute_trust(account_id)
    ok, reason = review_eligible(account_id)
    _print(
        {
            "account": args.account,
            "derived": breakdown.score,
            "stored_latest": latest_trust(account_id),
            "components": breakdown.as_dict(),
            "review_eligible": ok,
            "review_reason": reason,
        }
    )
    return 0


def cmd_verify(args) -> int:
    import uuid as _uuid

    from core.orchestrator import probe_account, verify_login

    settings = get_settings()
    deps = _deps(settings)
    if args.all:
        from db.models import Account
        from db.session import session_scope

        with session_scope() as session:
            ids = [a.id for a in session.query(Account).order_by(Account.created_at).all()]
        results = {}
        for account_id in ids:
            try:
                if args.probe:
                    results[str(account_id)] = asyncio.run(probe_account(account_id, deps))
                else:
                    results[str(account_id)] = asyncio.run(verify_login(account_id, deps))
            except Exception as exc:  # noqa: BLE001
                results[str(account_id)] = {"exists": None, "reason": f"error: {str(exc)[:120]}"}
        _print(results)
        return 0
    if args.probe:
        result = asyncio.run(probe_account(_uuid.UUID(args.account), deps))
        _print(result)
        return 0 if result.get("exists") else 1
    result = asyncio.run(verify_login(_uuid.UUID(args.account), deps))
    _print(result)
    return 0 if result.get("ok") else 1


def cmd_login(args) -> int:
    """yf login: run the full LoginFlow (email + passwordless email link) per account."""
    import uuid as _uuid

    from core.orchestrator import login_account

    settings = get_settings()
    deps = _deps(settings)
    if getattr(args, "batch", None):
        from core.batches import batch_account_ids

        ids = batch_account_ids(args.batch)
    elif args.account:
        ids = [_uuid.UUID(args.account)]
    elif getattr(args, "all", False):
        from db.models import Account
        from db.session import session_scope

        with session_scope() as session:
            ids = [a.id for a in session.query(Account).order_by(Account.created_at).all()]
    else:
        _print({"error": "account_or_batch_required"})
        return 2
    results = [asyncio.run(login_account(account_id, deps)) for account_id in ids]
    _print({"count": len(results), "results": results})
    return 0 if all(r.get("ok") for r in results) else 1


def cmd_post_review(args) -> int:
    """yf post-review mark|list: manage the 'reviews done' flag (spec v3.0 section 5.1)."""
    import uuid as _uuid

    from core.post_review import list_marked, mark_reviews_done, unmark_reviews_done

    if args.post_action == "mark":
        _print(mark_reviews_done(_uuid.UUID(args.account)))
        return 0
    if args.post_action == "unmark":
        _print(unmark_reviews_done(_uuid.UUID(args.account)))
        return 0
    _print({"marked": list_marked()})
    return 0


def cmd_clients(args) -> int:
    from core.clients import import_clients, list_clients, list_metros

    if args.clients_action == "import":
        if not args.file:
            _print({"error": "--file required"})
            return 2
        _print(import_clients(args.file, dry_run=args.dry_run, probe=args.probe, create_metros=args.create_metros))
        return 0
    if args.clients_action == "metros":
        _print({"metros": list_metros()})
        return 0
    _print({"clients": list_clients(metro=args.metro, limit=args.limit)})
    return 0


def cmd_assign(args) -> int:
    from datetime import datetime

    from core.assignments import plan_assignments
    from core.flags import get_flag, set_flag
    from core.volume import effective_multiplier, is_lazy_week

    today = datetime.now().date().isoformat()
    marker = get_flag("assign", {})
    if not getattr(args, "force", False) and marker.get("date") == today:
        _print({"skipped": "already_planned_today", "date": today, "planned": marker.get("count", 0)})
        return 0
    created = plan_assignments(limit=args.limit)
    set_flag("assign", {"date": today, "count": len(created)})
    _print({"planned": len(created), "assignments": created, "volume": round(effective_multiplier(), 2), "lazy_week": is_lazy_week()})
    return 0


def cmd_review(args) -> int:
    from core.assignments import due_assignments
    from core.orchestrator import run_due_reviews

    settings = get_settings()
    deps = _deps(settings)
    if args.review_action == "due":
        _print(asyncio.run(run_due_reviews(deps, limit=args.limit)))
        return 0
    if args.review_action == "check":
        from datetime import datetime

        from core.flags import get_flag, set_flag
        from core.orchestrator import check_published_reviews

        today = datetime.now().date().isoformat()
        marker = get_flag("review_check", {})
        if marker.get("date") == today and not getattr(args, "force", False):
            _print({"skipped": "already_checked_today", "date": today})
            return 0
        result = asyncio.run(check_published_reviews(deps, hours=args.hours, limit=args.limit))
        set_flag("review_check", {"date": today, "count": result.get("count", 0)})
        _print(result)
        return 0
    _print({"due": due_assignments(limit=args.limit)})
    return 0


def cmd_volume(args) -> int:
    from datetime import datetime

    from core.flags import get_flag, set_flag
    from core.velocity import reviews_today
    from core.volume import effective_multiplier, filter_rate_7d, is_lazy_week

    # manual override (C4): pin a multiplier or pause/resume the whole system
    if getattr(args, "multiplier", None) is not None:
        set_flag("volume", {"multiplier": float(args.multiplier)})
        _print({"ok": True, "multiplier": args.multiplier})
        return 0
    if getattr(args, "pause", False):
        set_flag("volume", {"paused": True})
        _print({"ok": True, "paused": True})
        return 0
    if getattr(args, "resume", False):
        set_flag("volume", {})
        _print({"ok": True, "paused": False})
        return 0

    rate = filter_rate_7d()
    if rate > 0.40:
        # once per day, raise the system-wide filter alert (2026-11-09 policy)
        day = datetime.now().date().isoformat()
        marker = get_flag("filter_alert", {})
        if marker.get("date") != day:
            from core.alerts import notify as alert

            alert("filter_rate_high", detail={"rate_7d": round(rate, 3)})
            set_flag("filter_alert", {"date": day, "rate": round(rate, 3)})

    _print(
        {
            "multiplier": round(effective_multiplier(), 2),
            "lazy_week": is_lazy_week(),
            "filter_rate_7d": round(rate, 3),
            "reviews_today": reviews_today(),
            "flag": get_flag("volume", {}),
        }
    )
    return 0


def cmd_probe(args) -> int:
    from core.orchestrator import probe_stale_sessions

    settings = get_settings()
    deps = _deps(settings)
    _print(asyncio.run(probe_stale_sessions(deps, stale_days=args.stale_days, limit=args.limit)))
    return 0


def cmd_account(args) -> int:
    import uuid as _uuid

    from db.models import Account, Event
    from db.session import session_scope

    account_id = _uuid.UUID(args.account)
    with session_scope() as session:
        row = session.get(Account, account_id)
        if row is None:
            _print({"error": "account_missing"})
            return 2
        if args.account_action == "show":
            _print(
                {
                    "account": str(row.id),
                    "email": row.email,
                    "state": row.state,
                    "substate": row.substate,
                    "metro_id": str(row.metro_id) if row.metro_id else None,
                    "reviews_done": row.reviews_done,
                    "profile_complete": row.profile_complete,
                    "last_probe_at": row.last_probe_at.isoformat() if row.last_probe_at else None,
                }
            )
            return 0
        if args.account_action == "set-state":
            if not args.state:
                _print({"error": "--state required"})
                return 2
            old = row.state
            row.state = args.state
            row.substate = args.substate if args.substate is not None else row.substate
            session.add(Event(account_id=row.id, code="manual_set_state", msg=f"{old} -> {args.state}", ctx={"substate": args.substate}))
            _print({"ok": True, "account": str(row.id), "from": old, "to": args.state})
            return 0
        if args.account_action == "stop-profile":
            from core.orchestrator import load_account
            from db.models import Profile

            profile_row = session.query(Profile).filter(Profile.id == row.profile_id).one_or_none() if row.profile_id else None
            gpm_id = profile_row.gpm_profile_id if profile_row else None
            if not gpm_id:
                _print({"error": "no_gpm_profile"})
                return 2
            from core.config import get_settings
            from adapters.gpm_http import GPMHTTPAdapter

            settings = get_settings()
            gpm = GPMHTTPAdapter(settings)
            try:
                gpm.stop_profile(gpm_id)
                _print({"ok": True, "stopped": gpm_id})
            finally:
                try:
                    gpm.close()
                except Exception:  # noqa: BLE001
                    pass
            return 0
    _print({"error": "unknown_action"})
    return 2


def cmd_lock(args) -> int:
    import uuid as _uuid

    from sqlalchemy import delete, text

    from db.models import AccountLock
    from db.session import session_scope

    with session_scope() as session:
        if getattr(args, "all", False):
            removed = session.execute(delete(AccountLock)).rowcount or 0
            slots = session.execute(text("DELETE FROM browser_slots")).rowcount or 0
            _print({"ok": True, "locks_removed": removed, "slots_removed": slots})
            return 0
        if not args.account:
            _print({"error": "--account or --all required"})
            return 2
        removed = session.execute(delete(AccountLock).where(AccountLock.account_id == _uuid.UUID(args.account))).rowcount or 0
        _print({"ok": True, "locks_removed": removed})
        return 0


def cmd_proxy(args) -> int:
    import uuid as _uuid

    from core.flags import set_flag
    from db.models import Account, Event
    from db.session import session_scope

    account_id = _uuid.UUID(args.account)
    with session_scope() as session:
        row = session.get(Account, account_id)
        if row is None:
            _print({"error": "account_missing"})
            return 2
        row.state = "READY"
        row.substate = None
        session.add(Event(account_id=row.id, code="manual_proxy_healthy", msg="manual reset", ctx={}))
    set_flag(f"proxy_fail:{account_id}", {"count": 0})
    _print({"ok": True, "account": str(account_id), "state": "READY"})
    return 0


def cmd_clean_artifacts(args) -> int:
    import time
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[1] / "artifacts"
    cutoff = time.time() - args.days * 86400
    removed = 0
    for sub in ("login", "daily", "alerts", "post_review_state"):
        directory = root / sub
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
    _print({"ok": True, "removed": removed, "older_than_days": args.days})
    return 0


def cmd_pool_audit(args) -> int:
    from core.audit import pool_audit

    _print(pool_audit())
    return 0


def cmd_db_check(args) -> int:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        command.check(cfg)  # raises when models drifted away from migrations
        _print({"ok": True, "drift": None})
        return 0
    except Exception as exc:  # noqa: BLE001
        _print({"ok": False, "drift": str(exc)[:800]})
        return 1


def cmd_key_gen(args) -> int:
    """Print a fresh YF_MASTER_KEY to stdout.

    Deliberately does NOT read or write .env: the operator pastes the value. Printing to
    stdout (not a JSON envelope) so it can be piped straight into a secret manager.
    """
    from core.crypto import SecretBox, generate_master_key

    try:
        key = generate_master_key(args.bytes)
        SecretBox(key_b64=key)  # prove the value we print is usable by the real validator
    except (RuntimeError, ValueError) as exc:  # noqa: BLE001
        _print({"error": "key_gen_failed", "detail": str(exc)[:200]})
        return 1
    print(key)
    return 0


def cmd_schedule(args) -> int:
    from core.scheduler import bootstrap, run_due, scheduler_loop

    settings = get_settings()
    deps = _deps(settings)
    if getattr(args, "mode", "warm") == "post-review":
        from core.orchestrator import run_post_review_due

        if args.once:
            _print(asyncio.run(run_post_review_due(deps, limit=args.limit, max_seconds=args.minutes * 60)))
            return 0
        _print({"error": "post_review_schedule_requires_once"})
        return 2
    if args.once:
        _print(bootstrap())
        _print(asyncio.run(run_due(deps, limit=args.limit, max_seconds=args.minutes * 60)))
        return 0
    asyncio.run(scheduler_loop(deps, interval_s=args.interval, max_seconds=args.minutes * 60))
    return 0


def cmd_warm(args) -> int:
    import uuid as _uuid

    from core.batches import batch_account_ids
    from core.orchestrator import run_post_review_due, run_post_review_warm, run_warm

    settings = get_settings()
    deps = _deps(settings)
    mode = getattr(args, "mode", "warm") or "warm"
    if getattr(args, "batch", None):
        ids = batch_account_ids(args.batch)
    elif args.account:
        ids = [_uuid.UUID(args.account)]
    else:
        ids = []
    if mode == "post-review":
        if not ids:
            # all accounts flagged reviews_done that still owe a session today
            _print(asyncio.run(run_post_review_due(deps, limit=getattr(args, "limit", 20) or 20)))
            return 0
        results = [
            asyncio.run(run_post_review_warm(account_id, deps, max_seconds=(args.minutes * 60 if args.minutes else None)))
            for account_id in ids
        ]
    else:
        if not ids:
            _print({"error": "account_or_batch_required"})
            return 2
        results = [
            asyncio.run(run_warm(account_id, deps, sessions=args.sessions, max_seconds=args.minutes * 60))
            for account_id in ids
        ]
    _print({"count": len(results), "results": results})
    return 0


def cmd_profile(args) -> int:
    import uuid as _uuid

    from sqlalchemy import select

    from core.orchestrator import run_profile_completion
    from db.models import Account, AccountState
    from db.session import session_scope

    settings = get_settings()
    deps = _deps(settings)
    if getattr(args, "batch", None):
        from core.batches import batch_account_ids

        ids = batch_account_ids(args.batch)
    elif args.all:
        with session_scope() as session:
            ids = list(
                session.scalars(
                    select(Account.id)
                    .where(
                        Account.state.in_(
                            (AccountState.ACTIVE.value, AccountState.WARMING.value, AccountState.ONBOARDED.value)
                        ),
                        Account.substate.is_distinct_from("profile_completed"),
                    )
                    .order_by(Account.created_at)
                )
            )
    else:
        if not args.account:
            _print({"error": "account_or_batch_required"})
            return 2
        ids = [_uuid.UUID(args.account)]

    async def run_all():
        semaphore = asyncio.Semaphore(max(1, args.concurrency))

        async def one(account_id):
            async with semaphore:
                try:
                    return await run_profile_completion(account_id, deps)
                except Exception as exc:  # noqa: BLE001
                    return {"account": str(account_id), "error": str(exc)[:200]}

        return await asyncio.gather(*(one(account_id) for account_id in ids))

    results = list(asyncio.run(run_all())) if ids else []
    _print({"count": len(results), "results": results})
    return 0


def cmd_resume(args) -> int:
    import uuid as _uuid

    from core.orchestrator import resume_account

    settings = get_settings()
    deps = _deps(settings)
    state = asyncio.run(resume_account(_uuid.UUID(args.account), deps, raw_proxy=args.proxy))
    _print({"account": args.account, "state": state.value})
    return 0 if state == __import__("db.models", fromlist=["AccountState"]).AccountState.ACTIVE else 1


def cmd_import_emails(args) -> int:
    from core.importers import parse_emails, read_file
    from core.pool import import_emails
    from db.models import EmailPool
    from db.session import session_scope

    settings = get_settings()
    text = read_file(args.file)
    with session_scope() as session:
        existing = {row.mailbox_email for row in session.query(EmailPool).all()} | {row.alias for row in session.query(EmailPool).all()}
    report = parse_emails(
        text,
        default_client_id=args.client_id or settings.email.graph_client_id,
        default_domain=args.domain or settings.email.domains[0],
        existing=existing,
    )
    result = {"total": report.total, "valid": len(report.rows), "duplicates": report.duplicates, "invalid": len(report.errors)}
    if report.errors:
        result["errors"] = [{"line": e.line, "reason": e.reason, "row": e.raw} for e in report.errors]
    if args.dry_run:
        _print({**result, "dry_run": True})
        return 0
    if report.rows:
        result.update(import_emails(report.rows, source_file=str(args.file)))
    _print(result)
    return 0 if report.rows else 1


def cmd_import_proxies(args) -> int:
    from core.importers import parse_proxies, read_file
    from core.pool import import_proxies
    from db.models import ProxyPool
    from db.session import session_scope

    text = read_file(args.file)
    with session_scope() as session:
        existing = {row.raw for row in session.query(ProxyPool).all()}
    report = parse_proxies(text, existing=existing)
    result = {"total": report.total, "valid": len(report.rows), "duplicates": report.duplicates, "invalid": len(report.errors)}
    if report.errors:
        result["errors"] = [{"line": e.line, "reason": e.reason, "row": e.raw} for e in report.errors]
    if args.dry_run:
        _print({**result, "dry_run": True})
        return 0
    if report.rows:
        result.update(import_proxies(report.rows, source_file=str(args.file)))
    _print(result)
    return 0 if report.rows else 1


def cmd_pool(args) -> int:
    from core.pool import stats
    from db.models import EmailPool, ProxyPool
    from db.session import session_scope

    payload = stats()
    if args.list:
        with session_scope() as session:
            payload["email_rows"] = [
                {"alias": row.alias, "mailbox": row.mailbox_email, "status": row.status}
                for row in session.query(EmailPool).order_by(EmailPool.imported_at.desc()).limit(args.limit).all()
            ]
            payload["proxy_rows"] = [
                {
                    "raw": f"{row.host}:{row.port}:{row.username}:***",
                    "status": row.status,
                    "accounts": row.accounts_count,
                    "ip": row.ip,
                }
                for row in session.query(ProxyPool).order_by(ProxyPool.imported_at.desc()).limit(args.limit).all()
            ]
    _print(payload)
    return 0


def cmd_gpm_health(args) -> int:
    settings = get_settings()
    client = _deps(settings).gpm
    try:
        health = client.health()
        profiles = client.list_profiles()
        _print({"health": health, "profiles": len(profiles), "transport": client.last_transport})
        return 0
    finally:
        client.close()


def cmd_gpm_list(args) -> int:
    settings = get_settings()
    client = _deps(settings).gpm
    try:
        rows = [
            {"id": p.id, "name": p.name, "browser": p.browser_version, "proxy": bool(p.raw_proxy)}
            for p in client.list_profiles()
        ]
        _print(rows)
        return 0
    finally:
        client.close()


def cmd_signup(args) -> int:
    from core.orchestrator import create_account, run_batch
    from flows.geo import resolve_target_city

    settings = get_settings()
    city = args.city
    probe_result = None
    auto_city = not city or city.lower() == "auto"
    pool_proxy_source = args.source in ("pool_proxy", "pool_both")
    if auto_city:
        if pool_proxy_source:
            # Every account probes its own pool proxy right before it is created.
            city = settings.target.cities[0]
        else:
            # City is derived from the proxy IP, not typed by the operator.
            city, probe_result = asyncio.run(
                resolve_target_city(
                    settings.proxy.default_raw,
                    fallback=settings.target.cities[0],
                    country=settings.target.country,
                )
            )
    domain = args.domain or settings.email.domains[0]
    deps = _deps(settings)

    batch_id = None
    if getattr(args, "batch", None):
        from core.batches import create_batch, get_batch

        batch = get_batch(args.batch)
        if batch is None:
            create_batch(args.batch, source=args.source, target_count=args.count)
            batch = get_batch(args.batch)
        batch_id = batch.id

    account_ids = []
    try:
        for _ in range(args.count):
            account_ids.append(
                create_account(
                    city,
                    domain,
                    source=args.source,
                    max_per_proxy=args.max_per_proxy,
                    probe_city=auto_city and pool_proxy_source,
                    batch_id=batch_id,
                )
            )
    except RuntimeError as exc:
        _print({"error": str(exc), "created": [str(a) for a in account_ids]})
        return 2
    log.info("signup_batch_started", count=len(account_ids), city=city, dry_run=args.dry_run, source=args.source)
    if args.dry_run:
        _print({"created": [str(a) for a in account_ids], "dry_run": True})
        return 0
    results = asyncio.run(run_batch(account_ids, deps, concurrency=args.concurrency, proxy=args.proxy))
    ok = sum(1 for state in results.values() if state == "ACTIVE")
    _print({"results": results, "active": ok, "total": len(results)})
    return 0 if ok == len(results) else 1


def cmd_report(args) -> int:
    from core.report import build_report

    _print(build_report(args.since))
    return 0


def cmd_reap(args) -> int:
    from core.reaper import run_reaper

    settings = get_settings()
    gpm = _deps(settings).gpm
    report = run_reaper(gpm, artifacts_root=Path(settings.artifacts_dir), artifacts_days=settings.retention.artifacts_days)
    _print(report)
    return 0


def cmd_quarantine(args) -> int:
    from core.report import recent_events

    _print(recent_events(limit=args.limit, code=args.code))
    return 0


def cmd_db_init(args) -> int:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    from db.models import Base
    from db.session import get_engine

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    engine = get_engine()
    tables = set(inspect(engine).get_table_names())
    if not tables:
        # 0001_initial builds the schema from the live models, so later revisions would
        # try to re-add columns that already exist. On a brand-new database create the
        # current schema and stamp the head instead of replaying the broken chain.
        Base.metadata.create_all(bind=engine)
        command.stamp(cfg, "head")
        print("empty database -> schema created and stamped to head")
        return 0
    command.upgrade(cfg, "head")
    print("database upgraded to head")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    settings = get_settings()
    uvicorn.run("api.admin:app", host=settings.admin_host, port=args.port or settings.admin_port, log_level="info")
    return 0


def cmd_probe_profile(args) -> int:
    """Attach to an existing GPM profile and report what the browser shows."""

    async def run():
        from adapters.browser import attach

        settings = get_settings()
        client = _deps(settings).gpm
        started = client.start_profile(args.profile_id, window_size="1280,800")
        browser = await attach(started.cdp_url, timeout_s=settings.gpm.connect_timeout_s)
        page = browser.page
        await page.goto("https://www.yelp.com/?locale=en_US", wait_until="domcontentloaded", timeout=60_000)
        title = await page.title()
        url = page.url
        await browser.close()
        client.stop_profile(args.profile_id)
        _print({"cdp": started.cdp_url, "process_id": started.process_id, "title": title, "url": url})

    asyncio.run(run())
    return 0


def cmd_proxy_probe(args) -> int:
    from adapters.proxy_probe import ProxyTarget, probe

    settings = get_settings()
    raw = args.raw or settings.proxy.default_raw
    result = asyncio.run(probe(ProxyTarget(raw=raw, country=settings.target.country), timeout_s=settings.proxy.probe_timeout_s))
    from dataclasses import asdict

    _print(asdict(result))
    return 0 if result.ok else 1


def cmd_mail_probe(args) -> int:
    from adapters.email import build_provider

    settings = get_settings()
    provider = build_provider(settings)
    alias = args.alias or f"yfprobe{__import__('random').randint(1000, 9999)}@{settings.email.domains[0]}"
    ok = asyncio.run(provider.probe(alias))
    _print({"alias": alias, "delivered": ok})
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yf", description="Yelp account factory")
    parser.add_argument("--log-level", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("gpm-health", help="check GPM app + count profiles").set_defaults(func=cmd_gpm_health)
    sub.add_parser("gpm-list", help="list GPM profiles").set_defaults(func=cmd_gpm_list)

    import_emails = sub.add_parser("import-emails", help="import email|password|token|client_id|alias lines")
    import_emails.add_argument("--file", required=True)
    import_emails.add_argument("--client-id", default=None)
    import_emails.add_argument("--domain", default=None)
    import_emails.add_argument("--dry-run", action="store_true")
    import_emails.set_defaults(func=cmd_import_emails)

    import_proxies = sub.add_parser("import-proxies", help="import host:port:user:pass lines")
    import_proxies.add_argument("--file", required=True)
    import_proxies.add_argument("--dry-run", action="store_true")
    import_proxies.set_defaults(func=cmd_import_proxies)

    pool = sub.add_parser("pool", help="email/proxy pool statistics")
    pool.add_argument("--list", action="store_true")
    pool.add_argument("--limit", type=int, default=20)
    pool.set_defaults(func=cmd_pool)

    signup = sub.add_parser("signup", help="create accounts and run the signup flow")
    signup.add_argument("--count", type=int, default=1)
    signup.add_argument("--city", default=None, help="auto (default) = derive from proxy IP")
    signup.add_argument("--domain", default=None)
    signup.add_argument("--proxy", default=None)
    signup.add_argument("--concurrency", type=int, default=1)
    signup.add_argument("--source", choices=["auto", "pool_email", "pool_proxy", "pool_both"], default="auto")
    signup.add_argument("--batch", default=None, help="batch name (created if missing)")
    signup.add_argument("--max-per-proxy", type=int, default=2)
    signup.add_argument("--dry-run", action="store_true")
    signup.set_defaults(func=cmd_signup)

    resume = sub.add_parser("resume", help="resume a crashed account from its last checkpoint")
    resume.add_argument("--account", required=True)
    resume.add_argument("--proxy", default=None)
    resume.set_defaults(func=cmd_resume)

    warm = sub.add_parser("warm", help="run warming sessions for an ACTIVE account or batch")
    warm.add_argument("--account", default=None)
    warm.add_argument("--batch", default=None)
    warm.add_argument("--sessions", type=int, default=1)
    warm.add_argument("--minutes", type=int, default=None, help="cap session minutes (omit = random 25-90)")
    warm.add_argument("--limit", type=int, default=20, help="max accounts for the due-sweep")
    warm.add_argument("--mode", choices=["warm", "post-review"], default="warm", help="post-review: 1 session/day, ladder P0-P4, no review")
    warm.set_defaults(func=cmd_warm)

    status = sub.add_parser("status", help="compact factory status")
    status.add_argument("--by-batch", action="store_true")
    status.set_defaults(func=cmd_status)

    batch = sub.add_parser("batch", help="batch tracking")
    batch.add_argument("batch_action", choices=["create", "list", "show", "next", "backfill", "pause", "resume", "close"])
    batch.add_argument("name", nargs="?", default=None)
    batch.add_argument("--name", dest="name_opt", default=None)
    batch.add_argument("--source", default="auto")
    batch.add_argument("--target", type=int, default=0)
    batch.add_argument("--notes", default=None)
    batch.set_defaults(func=cmd_batch)

    profile = sub.add_parser("profile", help="fill every optional Yelp profile field")
    profile.add_argument("--account", default=None)
    profile.add_argument("--batch", default=None)
    profile.add_argument("--all", action="store_true")
    profile.add_argument("--concurrency", type=int, default=2)
    profile.set_defaults(func=cmd_profile)

    schedule = sub.add_parser("schedule", help="plan and run due warming sessions")
    schedule.add_argument("--once", action="store_true", help="single pass, then exit")
    schedule.add_argument("--interval", type=int, default=300, help="seconds between passes")
    schedule.add_argument("--limit", type=int, default=8)
    schedule.add_argument("--minutes", type=int, default=8)
    schedule.add_argument("--mode", choices=["warm", "post-review"], default="warm", help="post-review: daily maintenance sessions")
    schedule.set_defaults(func=cmd_schedule)

    avatar = sub.add_parser("avatar", help="upload the stored avatar to an account profile")
    avatar.add_argument("--account", default=None)
    avatar.add_argument("--batch", default=None)
    avatar.add_argument("--all", action="store_true")
    avatar.add_argument("--missing", action="store_true")
    avatar.add_argument("--file", default=None)
    avatar.add_argument("--concurrency", type=int, default=2)
    avatar.set_defaults(func=cmd_avatar)

    trust = sub.add_parser("trust", help="trust score (derived from real history) / recompute")
    trust.add_argument("--account", default=None)
    trust.add_argument("--recompute", action="store_true")
    trust.add_argument("--all", action="store_true")
    trust.add_argument("--force", action="store_true")
    trust.set_defaults(func=cmd_trust)

    verify = sub.add_parser("verify-login", help="prove an account really exists by logging in")
    verify.add_argument("--account", default=None)
    verify.add_argument("--all", action="store_true")
    verify.add_argument("--probe", action="store_true", help="use the signup page to test if the email exists")
    verify.set_defaults(func=cmd_verify)

    login = sub.add_parser("login", help="run the full LoginFlow (password + passwordless email link)")
    login.add_argument("--account", default=None)
    login.add_argument("--batch", default=None)
    login.add_argument("--all", action="store_true")
    login.set_defaults(func=cmd_login)

    post_review = sub.add_parser("post-review", help="manage the post-review warm mode flag")
    post_review.add_argument("post_action", choices=["mark", "unmark", "list"])
    post_review.add_argument("--account", default=None)
    post_review.set_defaults(func=cmd_post_review)

    clients = sub.add_parser("clients", help="client pool + metros (businesses to review)")
    clients.add_argument("clients_action", choices=["import", "list", "metros"])
    clients.add_argument("--file", default=None)
    clients.add_argument("--metro", default=None)
    clients.add_argument("--limit", type=int, default=100)
    clients.add_argument("--dry-run", action="store_true")
    clients.add_argument("--probe", action="store_true", help="HTTP-check each yelp_biz_id (404 = invalid)")
    clients.add_argument("--create-metros", action="store_true", help="allow metros missing from the table")
    clients.set_defaults(func=cmd_clients)

    assign = sub.add_parser("assign", help="plan review assignments for due clients")
    assign.add_argument("--limit", type=int, default=None)
    assign.add_argument("--force", action="store_true", help="ignore the once-per-day guard")
    assign.set_defaults(func=cmd_assign)

    review = sub.add_parser("review", help="due review list / post due reviews / 72h filter check")
    review.add_argument("review_action", choices=["due", "post", "check"], nargs="?", default="due")
    review.add_argument("--limit", type=int, default=5)
    review.add_argument("--hours", type=int, default=72)
    review.add_argument("--force", action="store_true")
    review.set_defaults(func=cmd_review)

    volume = sub.add_parser("volume", help="volume governor status / set")
    volume.add_argument("--multiplier", type=float, default=None)
    volume.add_argument("--pause", action="store_true")
    volume.add_argument("--resume", action="store_true")
    volume.set_defaults(func=cmd_volume)

    probe = sub.add_parser("probe", help="light session probe for stale accounts (~3 days)")
    probe.add_argument("--stale-days", type=int, default=3)
    probe.add_argument("--limit", type=int, default=10)
    probe.set_defaults(func=cmd_probe)

    sub.add_parser("pool-audit", help="metro/ASN/proxy binding + derived trust audit").set_defaults(func=cmd_pool_audit)
    sub.add_parser("db-check", help="verify the DB schema matches alembic head (drift detection)").set_defaults(func=cmd_db_check)

    key_gen = sub.add_parser("key-gen", help="print a fresh YF_MASTER_KEY (does not touch .env)")
    key_gen.add_argument("--bytes", type=int, default=32, choices=[16, 24, 32], help="key size in bytes (default 32)")
    key_gen.set_defaults(func=cmd_key_gen)

    account = sub.add_parser("account", help="manual account state operations")
    account.add_argument("account_action", choices=["show", "set-state", "stop-profile"])
    account.add_argument("--account", required=True)
    account.add_argument("--state", default=None, help="READY/ACTIVE/COOLDOWN/NEEDS_MANUAL/...")
    account.add_argument("--substate", default=None)
    account.set_defaults(func=cmd_account)

    lock = sub.add_parser("lock", help="clear stuck account locks / browser slots")
    lock.add_argument("--account", default=None)
    lock.add_argument("--all", action="store_true")
    lock.set_defaults(func=cmd_lock)

    proxy = sub.add_parser("proxy", help="proxy health operations")
    proxy.add_argument("proxy_action", choices=["mark-healthy"])
    proxy.add_argument("--account", required=True)
    proxy.set_defaults(func=cmd_proxy)

    clean = sub.add_parser("clean-artifacts", help="delete screenshots/logs older than N days")
    clean.add_argument("--days", type=int, default=30)
    clean.set_defaults(func=cmd_clean_artifacts)

    report = sub.add_parser("report", help="aggregate numbers for a time window")
    report.add_argument("--since", default="24h")
    report.set_defaults(func=cmd_report)

    sub.add_parser("reap", help="clean locks, stuck runs, orphan profiles, old artifacts").set_defaults(func=cmd_reap)

    quarantine = sub.add_parser("quarantine", help="recent quarantine events")
    quarantine.add_argument("--limit", type=int, default=50)
    quarantine.add_argument("--code", default=None)
    quarantine.set_defaults(func=cmd_quarantine)

    sub.add_parser("db-init", help="run alembic migrations").set_defaults(func=cmd_db_init)

    serve = sub.add_parser("serve", help="run the admin API")
    serve.add_argument("--port", type=int, default=None)
    serve.set_defaults(func=cmd_serve)

    probe = sub.add_parser("probe-profile", help="attach CDP to a GPM profile and print the page title")
    probe.add_argument("--profile-id", required=True)
    probe.set_defaults(func=cmd_probe_profile)

    proxy = sub.add_parser("proxy-probe", help="check a proxy geo/latency")
    proxy.add_argument("--raw", default=None)
    proxy.set_defaults(func=cmd_proxy_probe)

    mail = sub.add_parser("mail-probe", help="prove an email alias is routable")
    mail.add_argument("--alias", default=None)
    mail.set_defaults(func=cmd_mail_probe)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(args.log_level or settings.log_level, json_output=True)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
