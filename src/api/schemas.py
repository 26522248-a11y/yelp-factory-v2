"""Admin API schemas (localhost only, bearer token)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    gpm_transport: str | None = None
    db: bool = False
    active_profiles: int = 0
    # Multi-machine handshake: the console refuses/warns on a contract mismatch.
    version: str = ""
    contract_version: int = 0
    schema_revision: str | None = None
    host: str | None = None


class SignupRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=500)
    city: str | None = None
    dry_run: bool = False


class ReportResponse(BaseModel):
    since: str
    accounts: dict[str, int]
    runs: dict[str, int]
    signups_ok: int
    signups_failed: int
    quarantine: dict[str, int]
    queue_depth: int


class QuarantineEntry(BaseModel):
    account_id: str
    code: str
    created_at: str
    evidence: dict[str, Any] = {}


class PoolImportRequest(BaseModel):
    kind: str
    text: str
    dry_run: bool = False


class NodeHeartbeatRequest(BaseModel):
    node_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    hostname: str = Field(default="", max_length=200)
    role: str = Field(default="console", pattern="^(console|worker|engine)$")
    version: str | None = Field(default=None, max_length=64)
    capacity: int = Field(default=0, ge=0, le=256)
    meta: dict[str, Any] = Field(default_factory=dict)
