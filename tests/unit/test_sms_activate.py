from __future__ import annotations

import httpx
import pytest

from adapters.sms import SmsActivateProvider

pytestmark = pytest.mark.asyncio

BASE = "https://5totp.example/stubs/handler_api.php"


def provider(handler) -> SmsActivateProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SmsActivateProvider("test_key", country="187", base_url=BASE, service_code="ot", client=client)


async def test_balance_uses_custom_handler_api():
    def handler(request):
        assert str(request.url).startswith(BASE)
        assert request.url.params["action"] == "getBalance"
        return httpx.Response(200, text="ACCESS_BALANCE:6.4323")

    assert await provider(handler).balance() == 6.4323


async def test_acquire_uses_configured_service_and_numeric_country():
    def handler(request):
        assert request.url.params["service"] == "ot"
        assert request.url.params["country"] == "187"
        return httpx.Response(200, text="ACCESS_NUMBER:abc123:15551234567")

    session = await provider(handler).acquire()
    assert session.provider_id == "abc123"
    assert session.phone_e164 == "+15551234567"
