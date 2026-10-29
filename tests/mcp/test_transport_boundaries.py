"""Transport lifecycle, configuration, and safe translation of tool failures."""
import builtins
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

if sys.version_info < (3, 11):
    pytest.skip("MCP requires Python 3.11+", allow_module_level=True)
pytest.importorskip("mcp")

from fastapi import FastAPI
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from oauth2provider.test_oauth import oauth_app, oauth_client, AUDIENCE
from test_mcp import mcp_setup, token_for_client, package
from wirecloud import settings
from wirecloud.database import get_session
from wirecloud.mcp import middleware, validators
from wirecloud.mcp.plugins import WirecloudMCPPlugin
from wirecloud.mcp.context import MCPCallContext, call_context
from wirecloud.mcp.handlers import make_handler
from wirecloud.mcp.middleware import MCPAuthenticationMiddleware, MCPCORSMiddleware
from wirecloud.mcp.schemas import Install
from wirecloud.mcp.server import WireCloudMCPServer
from wirecloud.mcp.tools import TOOL_MAP
from wirecloud.platform.plugins import ImproperlyConfigured


@pytest.mark.parametrize("url", ["/mcp", "https://wc.example/api", "https://user:pass@wc.example/mcp",
    "https://wc.example/mcp?query=1", "http://remote.example/mcp"])
def test_mcp_configuration_rejects_non_public_or_unsafe_endpoints(url):
    with pytest.raises(ImproperlyConfigured):
        validators.validate_mcp_settings(SimpleNamespace(MCP_PUBLIC_URL=url))


def test_mcp_configuration_checks_python_and_exposes_validator(monkeypatch):
    validate, = WirecloudMCPPlugin(None).get_config_validators()
    validate(SimpleNamespace(MCP_PUBLIC_URL="https://wc.example/mcp"))
    monkeypatch.setattr(validators.sys, "version_info", (3, 10))
    with pytest.raises(ImproperlyConfigured, match="Python 3.11"):
        validate(SimpleNamespace(MCP_PUBLIC_URL="http://localhost/mcp"))


async def test_mcp_settings_are_validated_only_through_the_standard_hook(oauth_app, monkeypatch):
    from wirecloud import settings_validator
    from wirecloud.mcp import plugins

    oauth_app.state.oauth2_resources.clear()
    monkeypatch.setattr(settings, "MCP_PUBLIC_URL", AUDIENCE, raising=False)
    validate = Mock(wraps=validators.validate_mcp_settings)
    monkeypatch.setattr(plugins, "validate_mcp_settings", validate)

    plugin = WirecloudMCPPlugin(oauth_app)
    validate.assert_not_called()

    monkeypatch.setattr(settings_validator, "_validate_and_set_defaults", lambda: None)
    monkeypatch.setattr(settings_validator, "get_config_validators", plugin.get_config_validators)
    await settings_validator.validate_settings()
    validate.assert_called_once_with(settings, False)

    monkeypatch.setattr(settings, "MCP_PUBLIC_URL", "http://remote.example/mcp")
    with pytest.raises(ImproperlyConfigured, match="requires HTTPS"):
        await settings_validator.validate_settings()


def test_missing_sdk_is_an_actionable_configuration_error(oauth_app, monkeypatch):
    original = builtins.__import__
    def importing(name, *args, **kwargs):
        if name == "wirecloud.mcp.server":
            raise ImportError("SDK unavailable")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(settings, "MCP_PUBLIC_URL", AUDIENCE, raising=False)
    monkeypatch.setattr(builtins, "__import__", importing)
    with pytest.raises(ImproperlyConfigured, match="Install wirecloud"):
        WirecloudMCPPlugin(oauth_app)


async def test_plugin_lifecycle_creates_shared_worker_indexes(oauth_app, db_session, monkeypatch):
    oauth_app.state.oauth2_resources.clear()
    monkeypatch.setattr(settings, "MCP_PUBLIC_URL", AUDIENCE, raising=False)
    plugin = WirecloudMCPPlugin(oauth_app)
    async with oauth_app.router.lifespan_context(oauth_app):
        for collection in ("mcp_uploads", "mcp_upload_chunks"):
            indexes = await db_session.client[collection].index_information()
            assert indexes["expires_at_1"]["expireAfterSeconds"] == 0
        indexes = await db_session.client.mcp_upload_chunks.index_information()
        assert indexes["upload_id_1_index_1"]["unique"]
    assert WirecloudMCPPlugin(None).server is None


async def test_sdk_reports_unknown_tools_and_preserves_extension_tools():
    server = WireCloudMCPServer("extensions")
    @server.tool(structured_output=True)
    def extension_healthcheck() -> dict[str, bool]:
        return {"healthy": True}
    tools = await server.list_tools()
    assert [tool.name for tool in tools] == ["extension_healthcheck"]
    result = await server.call_tool("extension_healthcheck", {}, None)
    assert result.structured_content == {"healthy": True}
    with pytest.raises(ToolError, match="Unknown tool"):
        await server.call_tool("unknown_tool", {}, None)


def validation_error():
    try:
        Install.model_validate({})
    except ValidationError as exc:
        return exc
    raise AssertionError("Install must require a single package source")


@pytest.mark.parametrize("exception,status,detail", [
    (validation_error(), 422, "Supply exactly one"),
    (ValueError("Invalid value"), 422, "Invalid value"),
    (TypeError("Invalid type"), 422, "Invalid type"),
    (OSError("private/storage/path"), 500, "Component storage is unavailable"),
])
async def test_tool_failures_have_structured_safe_errors(monkeypatch, exception, status, detail):
    from wirecloud.mcp.adapter import WireCloudAdapter
    monkeypatch.setattr(WireCloudAdapter, "execute", AsyncMock(side_effect=exception))
    context = call_context.set(MCPCallContext(None, SimpleNamespace(user=None), None))
    try:
        with pytest.raises(ToolError) as error:
            await make_handler(TOOL_MAP["get_session_info"])()
    finally:
        call_context.reset(context)
    payload = json.loads(str(error.value))
    assert payload["status"] == status and detail in str(payload["error"])
    assert "private/storage/path" not in str(error.value)


@pytest.mark.parametrize("kind,status", [("not_found", 404), ("permission", 403)])
async def test_operation_errors_are_translated_for_sdk_clients(monkeypatch, kind, status):
    from wirecloud.commons.utils.http import NotFound, PermissionDenied
    from wirecloud.mcp.adapter import WireCloudAdapter
    exception = NotFound("missing") if kind == "not_found" else PermissionDenied("forbidden")
    monkeypatch.setattr(WireCloudAdapter, "execute", AsyncMock(side_effect=exception))
    context = call_context.set(MCPCallContext(None, SimpleNamespace(user=None), None))
    try:
        with pytest.raises(ToolError) as error:
            await make_handler(TOOL_MAP["get_session_info"])()
    finally:
        call_context.reset(context)
    assert json.loads(str(error.value))["status"] == status


async def test_upload_requires_live_install_permission_and_enforces_stream_limit(mcp_setup, oauth_client, db_session, monkeypatch):
    principal, token, _ = await token_for_client(oauth_client, db_session)
    headers = {"Authorization": "Bearer " + token}
    await db_session.client.users.update_one({"_id": principal.user.id}, {"$set": {"user_permissions": []}})
    assert (await oauth_client.post("/mcp/uploads", headers=headers, content=package())).status_code == 403
    await db_session.client.users.update_one({"_id": principal.user.id}, {"$set": {"is_superuser": True}})
    from wirecloud.mcp import packages
    monkeypatch.setattr(packages, "PACKAGE_LIMIT", 10)
    assert (await oauth_client.post("/mcp/uploads", headers=headers, content=b"x" * 11)).status_code == 413


def scope(method="POST", kind="http"):
    return {"type": kind, "method": method, "path": "/mcp", "headers": [(b"authorization", b"Bearer access")]}


async def test_asgi_streaming_replay_disconnect_get_and_context_cleanup(monkeypatch, db_session):
    app = FastAPI()
    async def sessions():
        yield db_session
    app.dependency_overrides[get_session] = sessions
    principal = SimpleNamespace(scopes=frozenset())
    monkeypatch.setattr(middleware, "verify_access_token", AsyncMock(return_value=principal))
    receive = AsyncMock(side_effect=[{"type": "http.request", "body": b"{", "more_body": True},
        {"type": "http.request", "body": b"}", "more_body": False}, {"type": "http.disconnect"}])
    send = AsyncMock()
    async def inner(asgi_scope, recv, send):
        assert call_context.get().principal is principal
        assert (await recv())["body"] == b"{}"
        assert (await recv())["type"] == "http.disconnect"
        raise RuntimeError("transport stopped")
    transport = MCPAuthenticationMiddleware(inner, app, AUDIENCE)
    with pytest.raises(RuntimeError, match="transport stopped"):
        await transport(scope(), receive, send)
    with pytest.raises(LookupError):
        call_context.get()
    # A disconnected caller must not run the SDK with a partial request.
    transport.app = AsyncMock()
    await transport(scope(), AsyncMock(return_value={"type": "http.disconnect"}), send)
    transport.app.assert_not_awaited()
    # GET/SSE and non-HTTP lifecycle events are forwarded without reading a body.
    for asgi_scope in (scope("GET"), scope(kind="lifespan")):
        no_body = AsyncMock(side_effect=AssertionError("unexpected body read"))
        await transport(asgi_scope, no_body, send)
    assert transport.app.await_count == 2


async def test_cors_does_not_intercept_websockets_or_other_prefixed_routes():
    inner = AsyncMock()
    cors = MCPCORSMiddleware(inner, ["http://localhost"])
    for asgi_scope in ({"type": "websocket", "path": "/mcp"},
            {"type": "http", "path": "/other", "root_path": "/platform"}):
        await cors(asgi_scope, AsyncMock(), AsyncMock())
    assert inner.await_count == 2


@pytest.mark.parametrize("parameters", [None, [], {"name": []}, {}, {"name": "unknown_tool"}])
def test_scope_inspection_leaves_invalid_tool_requests_to_the_sdk(parameters):
    principal = SimpleNamespace(scopes=frozenset())
    body = json.dumps({"method": "tools/call", "params": parameters})
    assert middleware.scope_challenge(body, principal, AUDIENCE) is None
