"""Failure alerts: file artefacts + optional webhook (never let a dead login go silent)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from obs.log import get_logger

log = get_logger("alerts")

ALERT_DIR = Path("artifacts") / "alerts"


def notify(kind: str, *, account: str = "", detail: dict | None = None, severity: str = "error") -> dict:
    """Persist an alert and POST it to the configured webhook, best effort only."""
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "kind": kind,
        "account": account,
        "detail": detail or {},
    }
    try:
        ALERT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        tag = "".join(c if c.isalnum() else "_" for c in account)[:32] or "global"
        path = ALERT_DIR / f"alert_{stamp}_{tag}_{kind}.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        log.warning("alert_written", kind=kind, account=account, path=str(path))
    except OSError:
        log.warning("alert_write_failed", kind=kind)

    webhook = os.environ.get("YF_ALERT_WEBHOOK", "")
    if webhook:
        try:
            import httpx

            httpx.post(webhook, json=payload, timeout=10)
        except Exception as exc:  # noqa: BLE001
            log.warning("alert_webhook_failed", error=str(exc)[:150])

    telegram_token = os.environ.get("YF_TELEGRAM_BOT_TOKEN", "")
    telegram_chat = os.environ.get("YF_TELEGRAM_CHAT_ID", "")
    if telegram_token and telegram_chat:
        try:
            import httpx

            text = f"[{payload['severity']}] {kind}\naccount: {account or '-'}\ndetail: {json.dumps(payload['detail'])[:500]}"
            httpx.post(
                f"https://api.telegram.org/bot{telegram_token}/sendMessage",
                json={"chat_id": telegram_chat, "text": text[:4000]},
                timeout=10,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("alert_telegram_failed", error=str(exc)[:150])

    discord = os.environ.get("YF_DISCORD_WEBHOOK", "")
    if discord:
        try:
            import httpx

            text = f"**[{payload['severity']}] {kind}**\naccount: {account or '-'}\ndetail: {json.dumps(payload['detail'])[:800]}"
            httpx.post(discord, json={"content": text[:1900]}, timeout=10)
        except Exception as exc:  # noqa: BLE001
            log.warning("alert_discord_failed", error=str(exc)[:150])
    return payload
