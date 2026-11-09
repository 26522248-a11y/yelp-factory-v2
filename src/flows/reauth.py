"""Re-authentication when the GPM profile lost its Yelp session (E-50)."""

from __future__ import annotations

from adapters.base import YFError
from core.backoff import RetryPolicy
from core.state_machine import Stage
from db.models import AccountState
from obs.log import get_logger

log = get_logger("flows.reauth")

LOGIN_URL = "https://www.yelp.com/login?locale=en_US"


class ReauthFlow:
    """Thin wrapper over LoginFlow so there is only one login code path (spec v3.0 §3)."""

    def __init__(self, *, gpm, registry, settings):
        self.gpm = gpm
        self.registry = registry
        self.settings = settings

    def stages(self) -> list[Stage]:
        return [
            Stage(AccountState.WARMING, self._enter_warm, retry=RetryPolicy(max_attempts=2)),
        ]

    async def _enter_warm(self, ctx):
        from flows.login_flow import LoginFlow

        browser = ctx.data.get("browser")
        if browser is None:
            raise YFError("reauth requires an attached browser", code="cdp_failed")
        persona = ctx.data["persona"]
        flow = LoginFlow(registry=self.registry, settings=self.settings, email_provider=ctx.data.get("email_provider"))
        result = await flow.run(
            browser.page,
            email=persona.email_alias,
            password=persona.password,
            user_id=getattr(persona, "yelp_user_id", None),
        )
        # Two failed reauths mean the account is gone, not that we should keep trying.
        if not result.ok:
            raise YFError("reauth failed", code="reauth_failed", meta=result.to_json())
        return {"reauth": True}
