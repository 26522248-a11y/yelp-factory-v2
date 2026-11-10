"""The 4 metrics that were declared in obs/metrics.py but never set (/metrics reported 0).

Each test asserts the *wiring* (the sample actually moves), not the exporter itself.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

pytestmark = pytest.mark.usefixtures("db_ready")


class _StubMailbox:
    """Minimal EmailProvider stand-in: run_signup only needs a non-None fallback."""

    async def wait_for_message(self, *_args, **_kwargs):  # pragma: no cover - never called
        raise AssertionError("stub mailbox must not be called")


class _Recorder:
    def __init__(self) -> None:
        self.observed: list[float] = []
        self.set_values: list[float] = []

    def observe(self, value: float) -> None:
        self.observed.append(value)

    def set(self, value: float) -> None:
        self.set_values.append(value)


# ------------------------------------------------------------------ signup_duration_seconds


def test_run_signup_observes_duration(monkeypatch, settings, make_account):
    import core.orchestrator as orch

    account = make_account()
    recorder = _Recorder()
    monkeypatch.setattr(orch, "signup_duration_seconds", recorder)

    # No stages -> the machine returns immediately; we only care that the histogram is fed.
    class _EmptyFlow:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def stages(self):
            return []

    monkeypatch.setattr(orch, "SignupFlow", _EmptyFlow)
    # provider_for_account() raises when the account has no pool email and no fallback, so the
    # test passes a stub mailbox (never called: the stubbed flow has no stages).
    deps = orch.SignupDeps(settings=settings, gpm=None, registry=None, email=_StubMailbox(), captcha=None)

    asyncio.run(orch.run_signup(account.id, deps))

    assert len(recorder.observed) == 1, recorder.observed
    assert recorder.observed[0] >= 0.0


def test_run_signup_does_not_observe_duration_on_missing_account(monkeypatch, settings):
    """A missing account row is quarantined, not raised: the current run does not count."""
    import core.orchestrator as orch

    recorder = _Recorder()
    monkeypatch.setattr(orch, "signup_duration_seconds", recorder)
    deps = orch.SignupDeps(settings=settings, gpm=None, registry=None, email=_StubMailbox(), captcha=None)

    # run_signup() catches the KeyError, quarantines the account and returns DEAD instead of
    # propagating -- that is the shipped behaviour, so the test asserts on the return value.
    result = asyncio.run(orch.run_signup(uuid.uuid4(), deps))

    assert result in (orch.AccountState.DEAD, orch.AccountState.QUARANTINED)
    assert recorder.observed == []


# ------------------------------------------------------------------ proxy_health_ratio


def test_proxy_health_gauge_tracks_non_dead_share(make_account):
    """Healthy = status != dead (available/used/reserved all still usable)."""
    from sqlalchemy import func, select

    from core.crypto import SecretBox
    from core.pool import refresh_proxy_health_gauge
    from db.models import ProxyPool
    from db.session import session_scope
    from obs.metrics import proxy_health_ratio

    box = SecretBox()
    created: list[uuid.UUID] = []
    with session_scope() as session:
        for status, raw in (("available", "1.2.3.4:8080:u:p"), ("dead", "5.6.7.8:8080:u:p")):
            row = ProxyPool(
                raw=raw,
                host=raw.split(":")[0],
                port=8080,
                username="u",
                password_enc=box.encrypt("p"),
                status=status,
                source_file="test_metrics_wiring",
            )
            session.add(row)
            session.flush()
            created.append(row.id)

    try:
        with session_scope() as session:
            total = session.scalar(select(func.count()).select_from(ProxyPool)) or 0
            dead = session.scalar(
                select(func.count()).select_from(ProxyPool).where(ProxyPool.status == "dead")
            ) or 0
        ratio = refresh_proxy_health_gauge()
        assert ratio is not None and total > 0
        assert ratio == pytest.approx((total - dead) / total)
        assert proxy_health_ratio._value.get() == pytest.approx((total - dead) / total)
    finally:
        with session_scope() as session:
            session.query(ProxyPool).filter(ProxyPool.id.in_(created)).delete(synchronize_session=False)


def test_proxy_health_gauge_keeps_last_value_when_pool_empty(monkeypatch):
    """An empty table must not publish a fake 0.0 health ratio."""
    import core.pool as pool_mod
    from obs.metrics import proxy_health_ratio

    class _EmptySession:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def scalar(self, *_args, **_kwargs):
            return 0

    class _SessionScope:
        def __enter__(self):
            return _EmptySession()

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(pool_mod, "session_scope", lambda: _SessionScope())
    proxy_health_ratio.set(0.75)

    assert pool_mod.refresh_proxy_health_gauge() is None
    assert proxy_health_ratio._value.get() == pytest.approx(0.75)


# ------------------------------------------------------------------ queue_depth


def test_build_report_sets_queue_depth_gauge(make_account):
    from core.checkpoints import close_run, open_run
    from core.report import build_report
    from db.models import RunState
    from obs.metrics import queue_depth

    account = make_account()
    run_id = open_run(account.id, kind="signup")
    close_run(run_id, RunState.PENDING)

    report = build_report("24h")

    assert report["queue_depth"] >= 1
    assert queue_depth._value.get() == float(report["queue_depth"])


# ------------------------------------------------------------------ active_profiles


def test_metrics_endpoint_sets_active_profiles(monkeypatch):
    from fastapi.testclient import TestClient

    import api.admin as admin_mod

    recorder = _Recorder()
    monkeypatch.setattr(admin_mod, "active_profiles", recorder)

    response = TestClient(admin_mod.create_app()).get("/metrics")

    assert response.status_code == 200
    assert recorder.set_values, "active_profiles.set() must run on /metrics"
    assert recorder.set_values[0] == 0


def test_metrics_endpoint_refreshes_proxy_health(monkeypatch):
    """The gauge must be recomputed on scrape, not only when someone calls pool.py."""
    from fastapi.testclient import TestClient

    import core.pool as pool_mod
    from api.admin import create_app

    calls: list[int] = []

    def _fake_refresh():
        calls.append(1)
        return 0.5

    monkeypatch.setattr(pool_mod, "refresh_proxy_health_gauge", _fake_refresh)

    assert TestClient(create_app()).get("/metrics").status_code == 200
    assert calls, "/metrics must refresh proxy_health_ratio"


def test_metrics_endpoint_survives_gauge_refresh_failure(monkeypatch):
    """A broken DB must not turn /metrics into a 500 (dashboards would go blind)."""
    from fastapi.testclient import TestClient

    import core.pool as pool_mod
    from api.admin import create_app

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(pool_mod, "refresh_proxy_health_gauge", _boom)

    response = TestClient(create_app()).get("/metrics")
    assert response.status_code == 200
    assert "# TYPE proxy_health_ratio" in response.text


def test_metrics_endpoint_exports_all_wired_metric_names():
    from fastapi.testclient import TestClient

    from api.admin import create_app

    body = TestClient(create_app()).get("/metrics").text

    for name in (
        "signup_duration_seconds",
        "active_profiles",
        "proxy_health_ratio",
        "queue_depth",
        "signup_blocked_total",
        "captcha_detected_total",
    ):
        assert f"# TYPE {name}" in body or f"# HELP {name}" in body, name


def test_metrics_module_is_importable_without_side_effects():
    import obs.metrics as metrics

    # Every metric that used to be declared-but-never-set must be a real client object with
    # the API the wiring calls (observe for the histogram, set for the 3 gauges).
    assert hasattr(metrics.signup_duration_seconds, "observe")
    for gauge in (metrics.active_profiles, metrics.proxy_health_ratio, metrics.queue_depth):
        assert hasattr(gauge, "set")
        assert hasattr(gauge, "labels")
