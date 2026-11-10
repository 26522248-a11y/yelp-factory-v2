"""Typed settings loaded from config.yaml + .env (pydantic-settings)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config.yaml"
DEFAULT_ENV = ROOT / ".env"


class GPMConfig(BaseModel):
    flavor: Literal["global-v1", "gpm-v3"] = "global-v1"
    base_url: str = "http://127.0.0.1:9495"
    mcp_url: str = "http://127.0.0.1:9495/mcp"
    mcp_token: str = ""
    license_key: str = ""
    data_dir: str = ""
    read_only: bool = False
    connect_timeout_s: float = 20.0
    start_timeout_s: float = 60.0
    # Browser build must exist inside GPM; empty = ask the API for the newest one.
    browser_version: str = ""
    os_type: int = 1  # 1 = Windows
    browser_type: int = 1  # 1 = Chrome


class ConcurrencyConfig(BaseModel):
    workers: int = 8
    max_profiles: int = 8
    ram_guard_pct: float = 85.0


class TargetConfig(BaseModel):
    country: str = "US"
    cities: list[str] = Field(default_factory=lambda: ["Austin, TX"])
    zip_pool_file: str = "data/zips_us.json"


class ProxyConfig(BaseModel):
    kind: str = "residential"
    sticky_minutes: int = 45
    probe_timeout_s: float = 8.0
    max_fail_streak: int = 2
    default_raw: str = ""
    # Fail when a real page needs more than this to load (E-11).
    slow_page_p95_s: float = 25.0


class EmailConfig(BaseModel):
    provider: Literal["ms_graph", "imap", "fake", "fakemailo"] = "ms_graph"
    domains: list[str] = Field(default_factory=lambda: ["fviainboxes.com"])
    poll_timeout_s: int = 180
    resend_wait_s: int = 60
    graph_client_id: str = ""
    graph_refresh_token: str = ""
    graph_tenant: str = "consumers"
    imap_host: str = "outlook.office365.com"
    blocked_domain_hours: int = 24
    # fakemailo (partner-authorized-emails) — read channel used when Graph/IMAP is suspended.
    fakemailo_url: str = "https://fakemailo.com/partner-authorized-emails"
    fakemailo_service: str = "Yelp"


class LoginConfig(BaseModel):
    """Login flow (real-world 2026-11-08: password submit -> passwordless email link)."""

    login_url: str = "https://www.yelp.com/login?locale=en_US"
    submit_poll_s: int = 20
    link_timeout_s: int = 120
    max_password_attempts: int = 3
    bad_credentials_retries: int = 1  # one retry before giving up (3 fails invites captcha)
    max_resend: int = 2
    min_gap_s: int = 90
    jitter_s: int = 45
    # Dedicated GPM profile used only to read fakemailo; mobile proxies cannot reach it (E-67).
    mail_reader_profile_id: str = ""
    verify_owner: bool = True


class SMSConfig(BaseModel):
    provider: str = "hup"
    api_key: str = ""
    # HupSMS service id (84 = Hotmail/Microsoft on Server 1; pick the target app's id).
    service_id: int = 84
    country: str = "US"
    max_price: float = 0.35
    timeout_s: int = 180


class CaptchaConfig(BaseModel):
    providers: list[str] = Field(default_factory=lambda: ["capsolver", "2captcha"])
    capsolver_key: str = ""
    two_captcha_key: str = ""
    timeout_s: int = 90
    human_in_loop: bool = True
    poll_interval_s: float = 3.0


class WarmingConfig(BaseModel):
    enabled: bool = True
    max_sessions_per_day: int = 3
    phase_days: dict[str, int] = Field(
        default_factory=lambda: {"P0": 2, "P1": 3, "P2": 5, "P3": 10, "P4": 10}
    )


class PostReviewConfig(BaseModel):
    """Post-review warm mode: one session per day, ladder P0->P4, no review actions."""

    enabled: bool = True
    sessions_per_day: int = 1
    session_minutes_min: int = 25  # random session length per day (2026-11-09)
    session_minutes_max: int = 88  # must not exceed hard_stop (C2: 89-90 were dead values)
    max_minutes: int = 88
    hard_stop_minutes: int = 88
    window_start: str = "08:00"
    window_end: str = "20:00"
    schedule_jitter_minutes: int = 40  # daily start is never the same minute (signature breaker)
    rest_between_actions_s: tuple[int, int] = (10, 45)
    page_dwell_s: tuple[int, int] = (8, 25)
    idle_probability: float = 0.25  # real people stare at the screen
    idle_s: tuple[int, int] = (3, 15)
    abandon_probability: float = 0.12  # sometimes leave a page early / go back
    new_tab_probability: float = 0.2  # open a listing in a second tab
    filter_probability: float = 0.35  # use sort/filter on results like a human
    upload_photos_per_session: int = 1  # P1b: profile completeness matters for trust
    early_session_photos: int = 3  # first three sessions upload 2-3 photos each
    fill_profile_first_session: bool = True  # avatar + bio + city on the first run
    geo_center: tuple[float, float] = (40.7128, -74.0060)  # fallback check-in anchor
    # per-borough anchors so the four accounts do not check in at one point (C1)
    geo_by_city: dict[str, tuple[float, float]] = Field(
        default_factory=lambda: {
            "manhattan": (40.7580, -73.9855),
            "brooklyn": (40.6782, -73.9442),
            "queens": (40.7282, -73.7949),
            "bronx": (40.8448, -73.8648),
        }
    )
    max_concurrent: int = 2  # hard cap on simultaneously-open profiles
    penalty_days_on_429: int = 3
    reviews: bool = False  # locked off in post-review mode (spec 5.4)


class RetentionConfig(BaseModel):
    artifacts_days: int = 7


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="YF_",
        env_nested_delimiter="__",
        env_file=str(DEFAULT_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/yelp_factory"
    master_key: str = ""
    admin_token: str = ""
    admin_host: str = "127.0.0.1"
    admin_port: int = 8787
    artifacts_dir: str = "artifacts"
    log_level: str = "INFO"
    human_time_scale: float = 1.0  # 0.0 collapses sleeps in tests; 1.0 keeps production cadence
    fingerprint_salt: str = "yf-fingerprint-v1"

    @field_validator("human_time_scale", mode="before")
    @classmethod
    def _validate_human_time_scale(cls, v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 1.0

    gpm: GPMConfig = Field(default_factory=GPMConfig)
    concurrency: ConcurrencyConfig = Field(default_factory=ConcurrencyConfig)
    target: TargetConfig = Field(default_factory=TargetConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    sms: SMSConfig = Field(default_factory=SMSConfig)
    captcha: CaptchaConfig = Field(default_factory=CaptchaConfig)
    warming: WarmingConfig = Field(default_factory=WarmingConfig)
    login: LoginConfig = Field(default_factory=LoginConfig)
    post_review: PostReviewConfig = Field(default_factory=PostReviewConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _yaml_defaults(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _env_secrets() -> dict[str, Any]:
    """Secrets never live in YAML; they come from .env / Credential Manager."""
    mapping = {
        "YF_MASTER_KEY": "master_key",
        "YF_ADMIN_TOKEN": "admin_token",
        "YF_DATABASE_URL": "database_url",
    }
    out: dict[str, Any] = {}
    for env_name, field in mapping.items():
        if (value := os.environ.get(env_name)):
            out[field] = value
    return out


def load_settings(config_path: str | Path | None = None, env_file: str | Path | None = None) -> Settings:
    raw = _yaml_defaults(Path(config_path) if config_path else DEFAULT_CONFIG)
    # pydantic-settings reads nested env vars on top of these initial values.
    settings = Settings(**raw, _env_file=str(env_file or DEFAULT_ENV))
    for field, value in _env_secrets().items():
        setattr(settings, field, value)
    # Sync the env var used by human.timing so code that imports before conftest still respects scale.
    os.environ.setdefault("YF_HUMAN_TIME_SCALE", str(settings.human_time_scale))
    if settings.gpm.mcp_token:
        os.environ.setdefault("YF_GPM__MCP_TOKEN", settings.gpm.mcp_token)
    return settings


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None
