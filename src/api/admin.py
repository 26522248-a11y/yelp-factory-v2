"""Minimal admin API. Binds 127.0.0.1 and requires a bearer token (section 14)."""

from __future__ import annotations

import importlib.metadata
import socket
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text

from api.schemas import HealthResponse, NodeHeartbeatRequest, PoolImportRequest, ReportResponse, SignupRequest
from core.config import get_settings
from core.governor import Governor
from core.report import build_report, recent_events
from db.session import session_scope
from obs.log import get_logger
from obs.metrics import active_profiles

log = get_logger("api.admin")

# Bump when the console-facing JSON shape changes in a breaking way.
CONTRACT_VERSION = 1


def _app_version() -> str:
    try:
        return importlib.metadata.version("yelp-factory")
    except importlib.metadata.PackageNotFoundError:  # running from a source tree
        return "0.1.0"


def _auth(request: Request) -> None:
    expected = get_settings().admin_token
    if not expected:
        raise HTTPException(status_code=503, detail="admin token not configured")
    header = request.headers.get("authorization", "")
    if header != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="unauthorized")


def create_app() -> FastAPI:
    app = FastAPI(title="Yelp Factory Admin", version="0.1.0", docs_url=None, redoc_url=None)
    governor = Governor(
        max_profiles=get_settings().concurrency.max_profiles,
        ram_guard_pct=get_settings().concurrency.ram_guard_pct,
        workers=get_settings().concurrency.workers,
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        ok_db = True
        schema_revision: str | None = None
        try:
            with session_scope() as session:
                schema_revision = session.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one_or_none()
        except Exception:  # noqa: BLE001
            ok_db = False
        return HealthResponse(
            status="ok" if ok_db else "degraded",
            db=ok_db,
            active_profiles=governor.active,
            version=_app_version(),
            contract_version=CONTRACT_VERSION,
            schema_revision=str(schema_revision) if schema_revision else None,
            host=socket.gethostname(),
        )

    @app.get("/report", response_model=ReportResponse, dependencies=[Depends(_auth)])
    def report(since: str = "24h") -> ReportResponse:
        return ReportResponse(**build_report(since))

    @app.get("/events", dependencies=[Depends(_auth)])
    def events(limit: int = 100, code: str | None = None):
        return recent_events(limit=limit, code=code)

    @app.post("/signup", dependencies=[Depends(_auth)])
    def signup(payload: SignupRequest):
        # Actual execution is done by workers; this only records intent.
        log.info("signup_requested", count=payload.count, city=payload.city, dry_run=payload.dry_run)
        return {"accepted": payload.count, "city": payload.city, "dry_run": payload.dry_run}

    @app.get("/metrics")
    def metrics():
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        # active_profiles was imported but never set (permanent 0 on the dashboard).
        active_profiles.set(governor.active)
        # Same story for proxy_health_ratio: recompute on scrape. Best effort -- a DB
        # hiccup must not turn /metrics into a 500, the last sample is better than nothing.
        try:
            from core.pool import refresh_proxy_health_gauge

            refresh_proxy_health_gauge()
        except Exception as exc:  # noqa: BLE001
            log.warning("proxy_health_gauge_refresh_failed", error=str(exc)[:150])
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # ------------------------------------------------------------------ accounts
    # Read-only projections for the operator console (yfcp/docs/engine-contract.md).

    @app.get("/api/accounts", dependencies=[Depends(_auth)])
    def accounts(
        state: str | None = None,
        city: str | None = None,
        batch_id: str | None = None,
        q: str | None = None,
        blacklisted: str | None = None,
        mode: str | None = None,
        sort: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ):
        from api.accounts_api import list_accounts, parse_filters

        try:
            filters = parse_filters(
                state=state,
                city=city,
                batch_id=batch_id,
                q=q,
                blacklisted=blacklisted,
                mode=mode,
                sort=sort,
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        with session_scope() as session:
            return list_accounts(session, filters)

    @app.get("/api/accounts/{account_id}", dependencies=[Depends(_auth)])
    def account_detail(account_id: str):
        from api.accounts_api import get_account

        try:
            uid = uuid.UUID(account_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="account_id must be a UUID") from exc
        with session_scope() as session:
            payload = get_account(session, uid)
        if payload is None:
            raise HTTPException(status_code=404, detail="account not found")
        return payload

    # ------------------------------------------------------------------ nodes
    # Deployment registry: consoles/workers heartbeat; the Nodes screen reads this.

    @app.get("/api/nodes", dependencies=[Depends(_auth)])
    def nodes():
        from api.nodes_api import list_nodes

        with session_scope() as session:
            return list_nodes(session)

    @app.post("/api/nodes/heartbeat", dependencies=[Depends(_auth)])
    def node_heartbeat(payload: NodeHeartbeatRequest):
        from api.nodes_api import upsert_node

        with session_scope() as session:
            return upsert_node(session, payload.model_dump())

    # ------------------------------------------------------------------ pools (spec v1.1)

    @app.get("/api/pool", dependencies=[Depends(_auth)])
    def pool_stats():
        from core.pool import stats

        return stats()

    @app.post("/api/pool/import", dependencies=[Depends(_auth)])
    def pool_import(payload: PoolImportRequest):
        from core.importers import parse_emails, parse_proxies
        from core.pool import import_emails, import_proxies
        from db.models import EmailPool, ProxyPool
        from db.session import session_scope

        settings = get_settings()
        with session_scope() as session:
            if payload.kind == "emails":
                existing = {row.mailbox_email for row in session.query(EmailPool).all()} | {
                    row.alias for row in session.query(EmailPool).all()
                }
            elif payload.kind == "proxies":
                existing = {row.raw for row in session.query(ProxyPool).all()}
            else:
                raise HTTPException(status_code=400, detail="kind must be emails|proxies")

        if payload.kind == "emails":
            report = parse_emails(
                payload.text,
                default_client_id=settings.email.graph_client_id,
                default_domain=settings.email.domains[0],
                existing=existing,
            )
            if not payload.dry_run and report.rows:
                import_emails(report.rows, source_file="api")
        else:
            report = parse_proxies(payload.text, existing=existing)
            if not payload.dry_run and report.rows:
                import_proxies(report.rows, source_file="api")

        return {
            "kind": payload.kind,
            "total": report.total,
            "valid": len(report.rows),
            "duplicates": report.duplicates,
            "invalid": len(report.errors),
            "errors": [
                {"line": error.line, "reason": error.reason, "row": error.raw} for error in report.errors
            ],
            "dry_run": payload.dry_run,
        }

    return app


app = create_app()
