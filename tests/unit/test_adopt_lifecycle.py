"""`yf adopt` (spec B, day 0) and the 48h city-change review lock (spec H).

The point of these tests is data integrity, not happy-path output:
* a bought account arrives with a profile that must NOT be filled by adopt;
* a blank home_city must be rejected here, because the DB check would only fire later;
* dry-run must fail exactly the rows the real run would fail (unknown metro);
* one inbox is one account, even inside the same file;
* a city change locks reviews for 48h in the ONE place the review path also reads.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import delete

from cli import main
from core.adopt import adopt_accounts, read_adopt_file
from core.lifecycle import city_change_locked, city_lock_until, review_block_reason
from db.models import Account, Metro, Profile, ProxyPool
from db.session import session_scope
from tests.fakes import FakeGPM

pytestmark = pytest.mark.usefixtures("db_ready")

HEADER = "email,password,supplier,home_city,metro,proxy,profile_id"
PROXY = "gate.example.com:8000:user:pass"


@pytest.fixture()
def metro():
    name = f"Testville, TS {uuid.uuid4().hex[:6]}"
    with session_scope() as session:
        row = Metro(name=name, state="TS")
        session.add(row)
        session.flush()
        metro_id = row.id
    yield name, metro_id
    with session_scope() as session:
        session.execute(delete(Metro).where(Metro.id == metro_id))


@pytest.fixture()
def adopted_ids():
    created: list[uuid.UUID] = []
    yield created
    if not created:
        return
    with session_scope() as session:
        profiles = [
            profile_id
            for (profile_id,) in session.query(Account.profile_id).filter(Account.id.in_(created)).all()
            if profile_id
        ]
        session.execute(delete(Account).where(Account.id.in_(created)))
        if profiles:
            session.execute(delete(Profile).where(Profile.id.in_(profiles)))
    with session_scope() as session:
        session.execute(delete(ProxyPool).where(ProxyPool.source_file == "adopt"))


def _write(tmp_path, *rows: str):
    path = tmp_path / "adopt.csv"
    path.write_text("\n".join((HEADER, *rows)) + "\n", encoding="utf-8")
    return path


def _row(metro: str, *, email: str | None = None, home_city: str = "Old Town, TS", profile_id: str = "") -> str:
    return (
        f"{email or f'a{uuid.uuid4().hex[:8]}@example.com'},Sup3rSecret!,supplier-a,"
        f'"{home_city}","{metro}",{PROXY},{profile_id}'
    )


def test_dry_run_writes_nothing_and_does_not_touch_gpm(tmp_path, metro):
    name, _ = metro
    path = _write(tmp_path, _row(name))
    gpm = FakeGPM()

    payload = adopt_accounts(path, gpm=gpm, dry_run=True)

    assert payload["valid"] == 1
    assert payload["dry_run"] is True
    assert payload["accounts"][0]["metro_known"] is True
    assert gpm.create_calls == []
    with session_scope() as session:
        assert session.query(Account).filter(Account.email == payload["accounts"][0]["email"]).count() == 0


def test_dry_run_rejects_unknown_metro_like_the_real_run(tmp_path):
    path = _write(tmp_path, _row("Nowhere, ZZ"))
    payload = adopt_accounts(path, gpm=FakeGPM(), dry_run=True)
    assert payload["valid"] == 0
    assert payload["errors"][0]["error"] == "unknown_metro:Nowhere, ZZ"


def test_blank_home_city_is_rejected_before_the_database_check(tmp_path, metro):
    name, _ = metro
    path = _write(tmp_path, _row(name, home_city="   "))
    report = read_adopt_file(path)
    assert [row["error"] for row in report.errors] == ["missing_home_city"]


def test_duplicate_email_inside_one_file_is_skipped(tmp_path, metro):
    name, _ = metro
    email = f"dup{uuid.uuid4().hex[:8]}@example.com"
    path = _write(tmp_path, _row(name, email=email), _row(name, email=email.upper()))
    report = read_adopt_file(path)
    assert len(report.rows) == 1
    assert report.duplicates == 1


def test_adopt_links_an_empty_profile_and_keeps_lifecycle_defaults(tmp_path, metro, adopted_ids):
    name, metro_id = metro
    path = _write(tmp_path, _row(name, home_city="  Old Town, TS  "))
    gpm = FakeGPM()

    payload = adopt_accounts(path, gpm=gpm, dry_run=False)
    assert payload["adopted"] == 1
    assert payload["accounts"][0]["profile_created"] is True

    account_id = uuid.UUID(payload["accounts"][0]["account"])
    adopted_ids.append(account_id)
    with session_scope() as session:
        account = session.get(Account, account_id)
        assert account is not None
        # profile is linked but empty: adopt never fills the profile fields (spec B).
        assert account.profile_id is not None
        profile = session.get(Profile, account.profile_id)
        assert profile.fingerprint_json == {"adopted": True, "profile_untouched": True}
        assert account.home_city == "Old Town, TS"
        assert account.city == "Old Town, TS"
        assert account.metro_id == metro_id
        assert account.supplier == "supplier-a"
        assert account.use_count == 0 and account.tier is None
        assert account.adopted_at is not None
        assert account.proxy_pool_id is not None

    assert len(gpm.create_calls) == 1
    assert gpm.create_calls[0]["raw_proxy"] == PROXY


def test_existing_gpm_profile_id_is_linked_without_creating_one(tmp_path, metro, adopted_ids):
    name, _ = metro
    path = _write(tmp_path, _row(name, profile_id=f"profile-{uuid.uuid4().hex[:8]}"))
    gpm = FakeGPM()

    payload = adopt_accounts(path, gpm=gpm, dry_run=False)
    assert payload["adopted"] == 1
    adopted_ids.append(uuid.UUID(payload["accounts"][0]["account"]))
    assert payload["accounts"][0]["profile_created"] is False
    assert gpm.create_calls == []


def test_cli_adopt_dry_run(capsys, tmp_path, metro):
    name, _ = metro
    path = _write(tmp_path, _row(name))
    code = main(["adopt", "--file", str(path), "--dry-run"])
    assert code == 0
    assert '"dry_run": true' in capsys.readouterr().out


def test_cli_account_show_still_has_its_uuid_import(capsys, make_account):
    account = make_account()
    code = main(["account", "show", "--account", str(account.id)])
    assert code == 0
    assert str(account.id) in capsys.readouterr().out


# ------------------------------------------------------------------ 48h locale lock


def _account(**kwargs):
    base = {
        "city_changed_at": None,
        "tier": None,
        "blacklisted": False,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_no_city_change_means_no_lock():
    assert city_lock_until(_account()) is None
    assert city_change_locked(_account()) is False
    assert review_block_reason(_account()) is None


def test_review_is_locked_inside_48h_and_free_after():
    now = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
    inside = _account(city_changed_at=now - timedelta(hours=47))
    outside = _account(city_changed_at=now - timedelta(hours=49))

    assert city_change_locked(inside, now=now) is True
    reason = review_block_reason(inside, now=now)
    assert reason.startswith("city_change_lock_until:")
    assert city_change_locked(outside, now=now) is False
    assert review_block_reason(outside, now=now) is None


def test_naive_timestamp_is_treated_as_utc():
    now = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
    assert city_change_locked(_account(city_changed_at=now.replace(tzinfo=None) - timedelta(hours=1)), now=now)


def test_blacklist_and_loai_block_even_without_a_city_change():
    assert review_block_reason(_account(blacklisted=True)) == "blacklisted"
    assert review_block_reason(_account(tier="Loại")) == "tier_loai"
