from __future__ import annotations

import json

import httpx
import pytest

from adapters.base import GPMError, GPMSchemaDrift, ProfileDTO
from adapters.gpm_http import GPMHttpClient
from adapters.gpm_mcp import HybridGPM, MCPClient

pytestmark = pytest.mark.asyncio


def http_client(handler) -> GPMHttpClient:
    return GPMHttpClient(base_url="http://127.0.0.1:9495", transport=httpx.MockTransport(handler))


def profiles_payload(profiles: list[dict]) -> dict:
    return {"success": True, "data": {"total": len(profiles), "data": profiles}, "message": "OK", "sender": "GPMLoginGlobal"}


async def test_hybrid_list_profiles_keeps_http_fallback_dtos():
    """Fallback already returns ProfileDTO; it must not be re-parsed into an empty list."""
    def handler(request):
        if request.url.path == "/api/v1/profiles":
            return httpx.Response(200, json=profiles_payload([{"id": "p1", "name": "yf-1"}, {"id": "p2", "name": "yf-2"}]))
        raise AssertionError(f"unexpected request {request.url}")

    gpm = HybridGPM(mcp_url="", http_client=http_client(handler))
    profiles = gpm.list_profiles()

    assert [p.id for p in profiles] == ["p1", "p2"]
    assert all(isinstance(p, ProfileDTO) for p in profiles)
    assert gpm.last_transport == "http"


async def test_hybrid_list_profiles_converts_mcp_dicts():
    """A successful MCP call returns raw dicts and still needs DTO conversion."""
    def handler(request):
        raise AssertionError("HTTP fallback must not be used")

    gpm = HybridGPM(mcp_url="http://mcp.local/mcp", http_client=http_client(handler))
    gpm._mcp = FakeMCP([{"id": "m1", "name": "yf-mcp"}])  # noqa: SLF001 - explicit injection

    profiles = gpm.list_profiles()

    assert [p.id for p in profiles] == ["m1"]
    assert gpm.last_transport == "mcp"


async def test_hybrid_list_profiles_rejects_non_list_payload():
    gpm = HybridGPM(mcp_url="", http_client=http_client(lambda request: httpx.Response(200, json=profiles_payload([]))))
    gpm._call = lambda *args, **kwargs: "not-a-profile-list"  # noqa: SLF001

    with pytest.raises(GPMSchemaDrift):
        gpm.list_profiles()


async def test_mcp_rpc_error_string_keeps_message():
    """GPM may answer `error` as a plain string; it must not become AttributeError."""
    client = MCPClient("http://mcp.local/mcp")
    client._post = lambda payload: {"jsonrpc": "2.0", "id": 1, "error": "Unauthorized"}  # noqa: SLF001

    with pytest.raises(GPMError) as excinfo:
        client._rpc("tools/list")  # noqa: SLF001

    assert "Unauthorized" in str(excinfo.value)


async def test_mcp_rpc_error_dict_keeps_message():
    client = MCPClient("http://mcp.local/mcp")
    client._post = lambda payload: {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "bad tool"}}  # noqa: SLF001

    with pytest.raises(GPMError) as excinfo:
        client._rpc("tools/call")  # noqa: SLF001

    assert "bad tool" in str(excinfo.value)


class FakeMCP:
    def __init__(self, result):
        self.result = result

    def call_tool(self, name, arguments):
        return self.result

    def list_tools(self):
        return []

    def close(self):
        pass
