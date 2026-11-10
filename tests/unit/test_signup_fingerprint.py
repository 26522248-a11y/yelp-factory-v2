"""Hook tests for fingerprint matrix v2 batch 1 in signup/orchestrator/cli."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from adapters.base import BrowserAttachError, ProfileDTO
from core.config import Settings
from core.fingerprint_matrix import WINDOW_SIZES, for_account, window_size_for_profile
from core.orchestrator import SignupDeps, _start_profile_safely
from core.state_machine import StageContext
from db.models import AccountState
from db.session import session_scope as real_session_scope
from flows.signup import SignupFlow
from tests.fakes import FakeBrowser, FakeGPM


@pytest.fixture
def settings():
    return Settings()


async def test_enter_provisioning_uses_fp1_and_persists_matrix(settings):
    flow = SignupFlow(settings=settings, gpm=FakeGPM(), registry=None, email_provider=None)
    account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    ctx = StageContext(
        account_id=account_id,
        run_id=uuid.uuid4(),
        state=AccountState.NEW,
        data={
            "persona": type(
                "Persona",
                (),
                {
                    "city": "Austin, TX",
                    "first_name": "A",
                    "last_name": "B",
                    "email_alias": "a@x.com",
                    "password": "x",
                    "zip": "78701",
                },
            ),
        },
    )

    probe_result = MagicMock(ok=True, ip="1.2.3.4", city="Austin, TX", latency_ms=100, error=None, asn="AS1")
    created_profile = ProfileDTO(id="p123", name="test", raw_proxy="proxy://x")

    captured = {}

    def fake_ensure_profile(gpm, *, operation_id, name, create_kwargs):
        captured["operation_id"] = operation_id
        captured["create_kwargs"] = create_kwargs
        return created_profile, False

    session = MagicMock()
    session.get.return_value = None
    session.query.return_value.filter_by.return_value.one_or_none.return_value = None

    with (
        patch("flows.signup.probe", return_value=probe_result),
        patch("flows.signup.ensure_profile", side_effect=fake_ensure_profile),
        patch("flows.signup.persist_account_state"),
        patch(
            "db.session.session_scope",
            return_value=MagicMock(__enter__=lambda s: session, __exit__=lambda *a: False),
        ),
    ):
        ctx.data["raw_proxy"] = "http://proxy:8080"
        result = await flow._enter_provisioning(ctx)

    assert result == {"profile_id": "p123"}
    assert ":fp1" in captured["operation_id"]
    assert captured["create_kwargs"]["os_type"] == 1
    assert captured["create_kwargs"]["browser_type"] in (1, 2)
    assert "browser_version" in captured["create_kwargs"]

    # _persist_profile wrote the 4 matrix fields into the DB row.
    add_call = session.add.call_args[0][0]
    fp = add_call.fingerprint_json
    assert fp["os_type"] == 1
    assert fp["browser_type"] == captured["create_kwargs"]["browser_type"]
    assert fp["window_size"] in WINDOW_SIZES
    assert fp["browser_version"] == captured["create_kwargs"]["browser_version"]


async def test_enter_browser_up_uses_fingerprint_window_size(settings):
    flow = SignupFlow(settings=settings, gpm=FakeGPM(), registry=None, email_provider=None)
    account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    fp = for_account(account_id)
    ctx = StageContext(
        account_id=account_id,
        run_id=uuid.uuid4(),
        state=AccountState.PROXY_BOUND,
        data={"profile": ProfileDTO(id="p1", name="test", raw_proxy=""), "fingerprint": fp},
    )

    with patch("flows.signup.attach", return_value=FakeBrowser()):
        await flow._enter_browser_up(ctx)

    assert flow.gpm.started[0].raw["window_size"] == fp.window_size


async def test_enter_browser_up_restart_uses_same_window_size(settings):
    flow = SignupFlow(settings=settings, gpm=FakeGPM(), registry=None, email_provider=None)
    account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    fp = for_account(account_id)
    ctx = StageContext(
        account_id=account_id,
        run_id=uuid.uuid4(),
        state=AccountState.PROXY_BOUND,
        data={"profile": ProfileDTO(id="p1", name="test", raw_proxy=""), "fingerprint": fp},
    )

    with patch("flows.signup.attach", side_effect=[BrowserAttachError("fail"), FakeBrowser()]):
        await flow._enter_browser_up(ctx)

    assert len(flow.gpm.started) == 2
    assert flow.gpm.started[0].raw["window_size"] == fp.window_size
    assert flow.gpm.started[1].raw["window_size"] == fp.window_size


def test_window_size_for_profile_reads_db():
    row = MagicMock(fingerprint_json={"window_size": "1440,900"})
    session = MagicMock()
    session.query.return_value.filter_by.return_value.one_or_none.return_value = row

    with patch(
        "db.session.session_scope",
        return_value=MagicMock(__enter__=lambda s: session, __exit__=lambda *a: False),
    ):
        assert window_size_for_profile("p999") == "1440,900"


def test_start_profile_safely_explicit_window_size_overrides_db(settings):
    gpm = FakeGPM()
    deps = SignupDeps(settings=settings, gpm=gpm, registry=None, email=None, captcha=None)

    with patch("core.orchestrator.window_size_for_profile", return_value="1366,768"):
        _start_profile_safely(deps, "p1", window_size="1920,1080")

    assert gpm.started[0].raw["window_size"] == "1920,1080"


def test_start_profile_safely_defaults_to_db_window_size(settings):
    gpm = FakeGPM()
    deps = SignupDeps(settings=settings, gpm=gpm, registry=None, email=None, captcha=None)

    with patch("core.orchestrator.window_size_for_profile", return_value="1600,900"):
        _start_profile_safely(deps, "p1")

    assert gpm.started[0].raw["window_size"] == "1600,900"


def _mock_session_scope(session):
    class Ctx:
        def __enter__(self, *a):
            return session
        def __exit__(self, *a):
            return False
    return Ctx



async def test_enter_browser_up_falls_back_to_db_window_size(settings):
    """Resume path has no ctx fingerprint; read persisted window_size from DB."""
    flow = SignupFlow(settings=settings, gpm=FakeGPM(), registry=None, email_provider=None)
    from core.state_machine import StageContext
    from db.models import AccountState
    account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    ctx = StageContext(
        account_id=account_id,
        run_id=uuid.uuid4(),
        state=AccountState.PROXY_BOUND,
        data={
            "profile": ProfileDTO(id="p1", name="test", raw_proxy=""),
            # no "fingerprint" key -> should read DB
        },
    )
    from tests.fakes import FakeBrowser
    with patch("flows.signup.attach", return_value=FakeBrowser()):
        with patch("flows.signup.window_size_for_profile", return_value="1536,864"):
            result = await flow._enter_browser_up(ctx)
    assert flow.gpm.started[0].raw["window_size"] == "1536,864"


async def test_persist_profile_backfills_existing_row(settings):
    """A reused profile row gets the 4 matrix fields written if missing."""
    flow = SignupFlow(settings=settings, gpm=FakeGPM(), registry=None, email_provider=None)
    from core.state_machine import StageContext
    from db.models import AccountState
    from core.fingerprint_matrix import for_account
    account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    fp = for_account(account_id)
    ctx = StageContext(
        account_id=account_id,
        run_id=uuid.uuid4(),
        state=AccountState.NEW,
        data={},
    )
    existing = MagicMock()
    existing.fingerprint_json = {"browser": "119.0"}  # legacy row without matrix fields
    session = MagicMock()
    session.query.return_value.filter_by.return_value.one_or_none.return_value = existing
    with patch("db.session.session_scope", _mock_session_scope(session)):
        flow._persist_profile(ctx, ProfileDTO(id="p1", name="test"), "", fp, "120.0.1")
    assert existing.fingerprint_json["os_type"] == fp.os_type
    assert existing.fingerprint_json["browser_type"] == fp.browser_type
    assert existing.fingerprint_json["browser_version"] == "120.0.1"
    assert existing.fingerprint_json["window_size"] == fp.window_size


async def test_persist_profile_keeps_existing_window_size(settings):
    """Backfill must not overwrite an already-persisted matrix value."""
    flow = SignupFlow(settings=settings, gpm=FakeGPM(), registry=None, email_provider=None)
    from core.state_machine import StageContext
    from db.models import AccountState
    from core.fingerprint_matrix import for_account
    account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    fp = for_account(account_id)
    ctx = StageContext(account_id=account_id, run_id=uuid.uuid4(), state=AccountState.NEW, data={})
    existing = MagicMock()
    existing.fingerprint_json = {"window_size": "1600,900", "browser_version": "130.0"}
    session = MagicMock()
    session.query.return_value.filter_by.return_value.one_or_none.return_value = existing
    with patch("db.session.session_scope", _mock_session_scope(session)):
        flow._persist_profile(ctx, ProfileDTO(id="p1", name="test"), "", fp, "120.0.1")
    assert existing.fingerprint_json["window_size"] == "1600,900"
    assert existing.fingerprint_json["browser_version"] == "130.0"
    assert existing.fingerprint_json["os_type"] == fp.os_type


def test_browser_versions_parses_nested_browser_object():
    from adapters.gpm_http import GPMHttpClient
    client = object.__new__(GPMHttpClient)
    client._extract_browser_engine = GPMHttpClient._extract_browser_engine
    def fake_call(method, path):
        return [
            {"id": "1", "browser": {"name": "chrome", "version": "120.0.1"}},
            {"id": "2", "browser": {"name": "firefox", "version": "130.0.1"}, "engine": "firefox"},
        ]
    client._call = fake_call
    versions = client.browser_versions()
    assert versions["chromium"] == ["120.0.1"]
    assert versions["firefox"] == ["130.0.1"]


def test_resolve_browser_version_uses_fallback_when_browsers_empty():
    from adapters.gpm_http import GPMHttpClient
    client = object.__new__(GPMHttpClient)
    client.browser_versions = lambda: {}
    client.list_profiles = lambda: [ProfileDTO(id="p1", name="x", browser_version="119.0.2")]
    assert client.resolve_browser_version(engine="chromium") == "119.0.2"
