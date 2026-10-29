"""Real SDK/HTTP integration and authoring tests (optional Python 3.11 extra)."""
import base64
import io
import json
import sys
import zipfile
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest

if sys.version_info < (3, 11):
    pytest.skip("MCP requires Python 3.11+", allow_module_level=True)
pytest.importorskip("mcp")

from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from oauth2provider.test_oauth import oauth_app, oauth_client, authorize_client, exchange, login_user, AUDIENCE
from wirecloud import settings
from wirecloud.oauth2provider import service as delegated
from wirecloud.commons.auth.crud import invalidate_token
from wirecloud.commons.utils.wgt import WgtDeployer
from wirecloud.mcp.adapter import WireCloudAdapter
from wirecloud.mcp.utils import redact
from wirecloud.mcp.packages import validate_package, decode_package, store_upload, consume_upload
from wirecloud.mcp.plugins import WirecloudMCPPlugin
from wirecloud.mcp.tools import SCOPES
from wirecloud.platform.workspace.crud import get_workspace_by_id
from wirecloud.database import DBSession, Id


def package(kind="widget", version="1.0.0", unsafe_path=None):
    descriptor = {"type": kind, "vendor": "test", "name": "mcp-" + kind, "version": version,
        "title": "Test component", "description": "MCP test", "email": "test@example.com", "macversion": 2,
        "preferences": [{"name": "message", "type": "text", "label": "Message", "default": "hello"},
                        {"name": "api_key", "type": "text", "label": "Key", "secure": True, "default": ""}],
        "wiring": {"inputs": [{"name": "input", "type": "text", "label": "Input"}],
                   "outputs": [{"name": "output", "type": "text", "label": "Output"}]}}
    if kind == "widget":
        descriptor.update(contents={"src": "index.html"}, widget_width="4", widget_height="3")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("config.xml", json.dumps(descriptor))
        archive.writestr("index.html", "<!doctype html><html><head><title>Test</title></head><body>Test</body></html>")
        if unsafe_path:
            archive.writestr(unsafe_path, "bad")
    return output.getvalue()


@pytest.fixture
async def mcp_setup(oauth_app, monkeypatch, db_session, tmp_path):
    oauth_app.state.oauth2_resources.pop(AUDIENCE)
    existing_workspaces = [item["_id"] async for item in db_session.client.workspaces.find({}, {"_id": 1})]
    monkeypatch.setattr(settings, "MCP_PUBLIC_URL", AUDIENCE, raising=False)
    monkeypatch.setattr(settings, "SECRET_KEY", "0123456789abcdef0123456789abcdef")
    await db_session.client.catalogue_resources.delete_many({"vendor": "test"})
    from wirecloud.platform.workspace import utils as workspace_utils
    monkeypatch.setattr(workspace_utils, "SECRET_KEY", "0123456789abcdef0123456789abcdef")
    from wirecloud.commons import search
    from wirecloud.catalogue import utils as catalogue_utils
    from wirecloud.platform.widget import utils as widget_utils
    monkeypatch.setattr(search, "es_client", AsyncMock())
    monkeypatch.setattr(catalogue_utils, "wgt_deployer", WgtDeployer(str(tmp_path / "catalogue")))
    from wirecloud.platform.workspace import routes as workspace_routes
    monkeypatch.setattr(workspace_routes, "wgt_deployer", catalogue_utils.wgt_deployer)
    monkeypatch.setattr(widget_utils, "wgt_deployer", WgtDeployer(str(tmp_path / "widgets")))
    plugin = WirecloudMCPPlugin(oauth_app)
    from asgi_lifespan import LifespanManager
    try:
        async with LifespanManager(oauth_app):
            yield oauth_app, plugin
    finally:
        await db_session.client.workspaces.delete_many({"_id": {"$nin": existing_workspaces}})


async def token_for_client(client, db, scopes=None):
    user, session_id = await login_user(db, client)
    client_id, verifier, callback, _ = await authorize_client(client, scope=" ".join(scopes or SCOPES))
    response = await exchange(client, client_id, verifier, callback["code"])
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    principal = await delegated.verify_access_token(db, token, AUDIENCE)
    return principal, token, session_id


def adapter(db, principal, app):
    request = Request({"type": "http", "http_version": "1.1", "scheme": "http", "server": ("localhost", 80),
        "client": ("127.0.0.1", 1234), "method": "POST", "path": "/mcp", "root_path": "", "query_string": b"",
        "headers": [(b"host", b"localhost")], "app": app})
    request.state.lang = "en"
    return WireCloudAdapter(db, principal, request)


async def test_transport_authentication_and_real_sdk_client(mcp_setup, oauth_client, db_session):
    app, plugin = mcp_setup
    unauthorized = await oauth_client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert unauthorized.status_code == 401
    assert "resource_metadata=" in unauthorized.headers["www-authenticate"]
    principal, token, session_id = await token_for_client(oauth_client, db_session)
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), headers={"Authorization": "Bearer " + token}) as http:
        async with Client(streamable_http_client(AUDIENCE, http_client=http)) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            assert "create_workspace" in names and "install_resource" in names and "layout_wiring" in names
            assert not any("admin" in name or "publish" in name or "share" in name for name in names)
            result = await client.call_tool("get_session_info", {})
            assert not result.is_error, result
            assert result.structured_content["user"]["id"] == str(principal.user.id)
    await invalidate_token(db_session, Id(session_id))
    assert (await oauth_client.post("/mcp", headers={"Authorization": "Bearer " + token}, json={})).status_code == 401


@pytest.mark.parametrize("requested_scope", [None, "wirecloud:read"])
async def test_connection_defaults_to_all_scopes_and_honors_explicit_scopes(
    mcp_setup: tuple[FastAPI, WirecloudMCPPlugin],
    oauth_client: AsyncClient,
    db_session: DBSession,
    requested_scope: Optional[str],
) -> None:
    challenge = await oauth_client.post("/mcp", json={})
    assert challenge.status_code == 401
    assert f'scope="{" ".join(SCOPES)}"' in challenge.headers["www-authenticate"]

    await login_user(db_session, oauth_client)
    registration = await oauth_client.post("/oauth2/register", json={
        "redirect_uris": ["http://127.0.0.1:9000/callback"],
    })
    assert registration.status_code == 201
    client_id = registration.json()["client_id"]
    verifier = delegated.random_token()
    params = {
        "client_id": client_id,
        "resource": AUDIENCE,
        "redirect_uri": "http://127.0.0.1:9000/callback",
        "response_type": "code",
        "code_challenge_method": "S256",
        "code_challenge": delegated.pkce(verifier),
    }
    if requested_scope is not None:
        params["scope"] = requested_scope
    start = await oauth_client.get("/oauth2/authorize", params=params)
    assert start.status_code == 302
    assert (await oauth_client.get(start.headers["location"])).status_code == 200
    form = {key: values[0] for key, values in parse_qs(urlsplit(start.headers["location"]).query).items()}
    approval = await oauth_client.post("/oauth2/consent", data={**form, "decision": "approve"})
    assert approval.status_code == 302
    code = parse_qs(urlsplit(approval.headers["location"]).query)["code"][0]
    response = await exchange(oauth_client, client_id, verifier, code)
    assert response.status_code == 200
    tokens = response.json()
    expected_scopes = set(requested_scope.split()) if requested_scope is not None else set(SCOPES)
    assert set(tokens["scope"].split()) == expected_scopes
    principal = await delegated.verify_access_token(db_session, tokens["access_token"], AUDIENCE)
    assert principal is not None
    assert principal.scopes == expected_scopes


async def test_packages_workspace_widgets_wiring_export_and_logout(mcp_setup, oauth_client, db_session):
    app, _ = mcp_setup
    principal, token, session_id = await token_for_client(oauth_client, db_session)
    api = adapter(db_session, principal, app)
    widget = await api.execute("install_resource", {"package_base64": base64.b64encode(package()).decode()})
    assert widget["resource"] == "test/mcp-widget/1.0.0"
    operator = await api.execute("install_resource", {"package_base64": base64.b64encode(package("operator")).decode()})
    assert operator["resource"] == "test/mcp-operator/1.0.0"
    created = await api.execute("create_workspace", {"name": "mcp-" + delegated.random_token(), "title": "Dashboard"})
    workspace_id = created["id"]
    workspace = await get_workspace_by_id(db_session, Id(workspace_id))
    tab_id = next(iter(workspace.tabs))
    added = await api.execute("add_widget", {"workspace_id": workspace_id, "tab_id": tab_id,
        "resource": widget["resource"], "title": "Widget", "layouts": {"0": {"x": 0, "y": 0, "w": 4, "h": 3}}})
    widget_id = added["result"]["id"]
    await api.execute("set_widget_variables", {"workspace_id": workspace_id, "tab_id": tab_id,
        "widget_id": widget_id, "values": {"message": "hello world", "api_key": "never-export-this-secret"}})
    added_operator = await api.execute("add_operator", {"workspace_id": workspace_id,
        "resource": operator["resource"], "preferences": {"message": "process", "api_key": "operator-secret"}})
    operator_id = added_operator["result"]["operator_id"]
    workspace = await get_workspace_by_id(db_session, Id(workspace_id))
    operator_position = workspace.wiring_status.visualdescription.components.operator[operator_id].position
    assert operator_position.x >= 20 and operator_position.y >= 10
    await api.execute("connect_components", {"workspace_id": workspace_id,
        "source": {"type": "widget", "id": widget_id, "endpoint": "output"},
        "target": {"type": "operator", "id": operator_id, "endpoint": "input"}})
    workspace = await get_workspace_by_id(db_session, Id(workspace_id))
    visual = workspace.wiring_status.visualdescription.components
    assert visual.operator[operator_id].position == operator_position
    assert visual.widget[widget_id].position.x < operator_position.x
    inspected = await api.execute("get_workspace", {"workspace_id": workspace_id})
    assert "never-export-this-secret" not in json.dumps(inspected)
    assert "operator-secret" not in json.dumps(inspected)
    before = await get_workspace_by_id(db_session, Id(workspace_id))
    stamp = inspected["modification_timestamp"]
    moved = await api.execute("layout_wiring", {"workspace_id": workspace_id, "expected_last_modified": stamp,
        "positions": [{"type": "widget", "id": widget_id, "x": 100, "y": 200},
                      {"type": "operator", "id": operator_id, "x": 800, "y": 400}]})
    assert moved["result"]["positioned"] == 2
    current = await get_workspace_by_id(db_session, Id(workspace_id))
    assert current.wiring_status.visualdescription.components.widget[widget_id].position.x == 100
    assert current.wiring_status.visualdescription.components.operator[operator_id].position.x == 800
    assert current.tabs == before.tabs
    assert current.wiring_status.operators == before.wiring_status.operators
    assert current.wiring_status.connections == before.wiring_status.connections
    with pytest.raises(HTTPException) as stale:
        await api.execute("layout_wiring", {"workspace_id": workspace_id, "expected_last_modified": stamp})
    assert stale.value.status_code == 409
    with pytest.raises(HTTPException) as missing:
        await api.execute("layout_wiring", {"workspace_id": workspace_id, "positions": [
            {"type": "widget", "id": widget_id, "x": 500, "y": 500},
            {"type": "operator", "id": "9999", "x": 900, "y": 900}]})
    assert missing.value.status_code == 404
    assert (await get_workspace_by_id(db_session, Id(workspace_id))).wiring_status == current.wiring_status
    arranged = await api.execute("layout_wiring", {"workspace_id": workspace_id, "preserve_existing": False})
    assert arranged["result"]["positioned"] == 2
    repeated = await api.execute("layout_wiring", {"workspace_id": workspace_id})
    assert repeated["result"]["positioned"] == 0
    exported = await api.execute("export_workspace", {"workspace_id": workspace_id})
    assert exported["descriptor"]["type"] == "mashup"
    assert "never-export-this-secret" not in json.dumps(exported)
    assert "operator-secret" not in json.dumps(exported)
    await api.execute("disconnect_components", {"workspace_id": workspace_id, "connection_index": 0})
    await api.execute("remove_operator", {"workspace_id": workspace_id, "operator_id": operator_id})
    current = await get_workspace_by_id(db_session, Id(workspace_id))
    assert operator_id not in current.wiring_status.visualdescription.components.operator
    await api.execute("delete_workspace", {"workspace_id": workspace_id})
    assert await get_workspace_by_id(db_session, Id(workspace_id)) is None
    await invalidate_token(db_session, Id(session_id))
    assert await delegated.verify_access_token(db_session, token, AUDIENCE) is None


async def test_scopes_sharing_and_stale_edit_rejection(mcp_setup, oauth_client, db_session):
    app, _ = mcp_setup
    principal, _, _ = await token_for_client(oauth_client, db_session)
    api = adapter(db_session, principal, app)
    created = await api.execute("create_workspace", {"title": "Concurrency test", "allow_renaming": True})
    workspace_id = created["id"]
    inspected = await api.execute("get_workspace", {"workspace_id": workspace_id})
    stamp = inspected["modification_timestamp"]
    await api.execute("update_workspace", {"workspace_id": workspace_id, "title": "Changed", "expected_last_modified": stamp})
    with pytest.raises(HTTPException) as conflict:
        await api.execute("update_workspace", {"workspace_id": workspace_id, "title": "Stale", "expected_last_modified": stamp})
    assert conflict.value.status_code == 409
    with pytest.raises(HTTPException) as blocked:
        await api.execute("update_preferences", {"target": "workspace", "workspace_id": workspace_id, "values": {"public": "true"}})
    assert blocked.value.status_code == 403
    principal.scopes = frozenset({"wirecloud:read"})
    with pytest.raises(HTTPException) as no_scope:
        await api.execute("delete_workspace", {"workspace_id": workspace_id})
    assert no_scope.value.status_code == 403
    with pytest.raises(HTTPException) as no_layout_scope:
        await api.execute("layout_wiring", {"workspace_id": workspace_id})
    assert no_layout_scope.value.status_code == 403
    with pytest.raises(HTTPException) as unknown:
        await api.execute("create_admin_user", {})
    assert unknown.value.status_code == 404


async def test_wiring_layout_requires_edit_permission_even_for_noop(mcp_setup, oauth_client, db_session, monkeypatch):
    app, _ = mcp_setup
    principal, _, _ = await token_for_client(oauth_client, db_session)
    api = adapter(db_session, principal, app)
    created = await api.execute("create_workspace", {"title": "Layout permissions", "allow_renaming": True})
    from wirecloud.mcp.operations import wiring as module
    monkeypatch.setattr(module, "is_owner_or_has_permission", lambda *args: False)
    with pytest.raises(HTTPException) as blocked:
        await api.execute("layout_wiring", {"workspace_id": created["id"]})
    assert blocked.value.status_code == 403


async def test_upload_binding_expiry_and_install(mcp_setup, oauth_client, db_session):
    app, _ = mcp_setup
    principal, token, _ = await token_for_client(oauth_client, db_session)
    uploaded = await oauth_client.post("/mcp/uploads", content=package(), headers={"Authorization": "Bearer " + token})
    assert uploaded.status_code == 201, uploaded.text
    handle = uploaded.json()["upload_id"]
    other = delegated.OAuthPrincipal(principal.user, principal.client_id, "other-grant", principal.session_id, AUDIENCE, principal.scopes)
    with pytest.raises(HTTPException) as denied:
        await consume_upload(db_session, other, handle)
    assert denied.value.status_code == 404
    result = await adapter(db_session, principal, app).execute("install_resource", {"upload_id": handle})
    assert result["resource"] == "test/mcp-widget/1.0.0"
    with pytest.raises(HTTPException):
        await consume_upload(db_session, principal, handle)


@pytest.mark.parametrize("path", ["../escape", "/absolute", "foo/../../escape", "..\\escape", "C:/escape"])
def test_archive_path_validation(path):
    with pytest.raises(HTTPException) as error:
        validate_package(package(unsafe_path=path))
    assert error.value.status_code == 422


def test_invalid_packages_and_secret_redaction():
    with pytest.raises(HTTPException):
        validate_package(b"not-a-zip")
    with pytest.raises(HTTPException):
        decode_package("not base64!")
    redacted = redact({"preferences": {"secret": {"secure": True, "value": "secret", "default": "secret"},
        "hidden": {"hidden": True, "value": "hidden"}}, "idm_data": {"token": "idp"}})
    assert redacted == {"preferences": {"secret": {"secure": True, "has_value": True}, "hidden": {"hidden": True, "has_value": True}}}


async def test_url_import_uses_proxy_policy_and_user_without_bearer(mcp_setup, oauth_client, db_session, monkeypatch):
    app, _ = mcp_setup
    principal, _, _ = await token_for_client(oauth_client, db_session)
    from wirecloud.proxy.routes import WIRECLOUD_PROXY
    from fastapi import Response
    seen = []
    async def download(request, url, method, context, db, user=None):
        seen.append((request, url, user))
        return Response(package())
    monkeypatch.setattr(WIRECLOUD_PROXY, "do_request", download)
    result = await adapter(db_session, principal, app).execute("install_resource", {"url": "http://internal-marketplace/component.wgt"})
    assert result["resource"] == "test/mcp-widget/1.0.0"
    assert seen[0][1] == "http://internal-marketplace/component.wgt"
    assert seen[0][2].id == principal.user.id
    assert "authorization" not in seen[0][0].headers and "cookie" not in seen[0][0].headers


async def test_immutable_resource_reuse_and_conflict(mcp_setup, oauth_client, db_session):
    app, _ = mcp_setup
    principal, _, _ = await token_for_client(oauth_client, db_session)
    api = adapter(db_session, principal, app)
    content = package()
    payload = {"package_base64": base64.b64encode(content).decode()}
    assert not (await api.execute("install_resource", payload))["reused_existing"]
    assert (await api.execute("install_resource", payload))["reused_existing"]
    changed = io.BytesIO(content)
    with zipfile.ZipFile(changed, "a") as archive:
        archive.writestr("new-file.txt", "different immutable contents")
    with pytest.raises(HTTPException) as conflict:
        await api.execute("install_resource", {"package_base64": base64.b64encode(changed.getvalue()).decode()})
    assert conflict.value.status_code == 409


async def test_another_worker_can_validate_existing_tokens(mcp_setup, oauth_client, db_session):
    app, _ = mcp_setup
    _, token, _ = await token_for_client(oauth_client, db_session)
    from fastapi import FastAPI
    from wirecloud.database import get_session
    second = FastAPI()
    async def session():
        yield db_session
    second.dependency_overrides[get_session] = session
    plugin = WirecloudMCPPlugin(second)
    async with second.router.lifespan_context(second):
        async with AsyncClient(transport=ASGITransport(app=second), base_url="http://localhost") as client:
            response = await client.post("/mcp", headers={"Authorization": "Bearer " + token,
                "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2026-07-28", "MCP-Method": "tools/list"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientCapabilities": {}}}})
    assert response.status_code == 200, response.text
    assert any(tool["name"] == "create_workspace" for tool in response.json()["result"]["tools"])


async def test_personal_uninstall_preserves_other_users_and_search(mcp_setup, oauth_client, db_session):
    app, _ = mcp_setup
    first, _, _ = await token_for_client(oauth_client, db_session)
    api = adapter(db_session, first, app)
    payload = {"package_base64": base64.b64encode(package()).decode()}
    resource = (await api.execute("install_resource", payload))["resource"]
    second, _, _ = await token_for_client(oauth_client, db_session)
    await adapter(db_session, second, app).execute("install_resource", payload)
    await api.execute("uninstall_resource", {"resource": resource})
    from wirecloud.catalogue.crud import get_catalogue_resource
    remaining = await get_catalogue_resource(db_session, *resource.split("/"))
    assert remaining is not None
    assert str(second.user.id) in remaining.users and str(first.user.id) not in remaining.users
    from wirecloud.commons import search
    assert search.es_client.delete.await_count == 0


async def test_read_only_connection_receives_oauth_scope_challenge(mcp_setup, oauth_client, db_session):
    _, token, _ = await token_for_client(oauth_client, db_session, scopes=["wirecloud:read"])
    response = await oauth_client.post("/mcp", headers={"Authorization": "Bearer " + token},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "create_workspace", "arguments": {"title": "Dashboard"}}})
    assert response.status_code == 403
    assert 'error="insufficient_scope"' in response.headers["www-authenticate"]
    assert 'scope="wirecloud:workspace:write"' in response.headers["www-authenticate"]


async def test_connection_permissions_can_change_without_replacing_the_client_token(
    mcp_setup: tuple[FastAPI, WirecloudMCPPlugin], oauth_client: AsyncClient, db_session: DBSession
) -> None:
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    app, _ = mcp_setup
    principal, token, _ = await token_for_client(oauth_client, db_session, scopes=["wirecloud:read"])
    headers = {"Authorization": "Bearer " + token}
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "create_workspace", "arguments": {"title": "Updated connection permissions"},
    }}
    assert (await oauth_client.post("/mcp", headers=headers, json=payload)).status_code == 403
    for scopes in ("wirecloud:read wirecloud:workspace:write", "wirecloud:read"):
        form = (await oauth_client.get("/oauth2/connections", headers={"Accept": "application/json"})).json()
        response = await oauth_client.post("/oauth2/connections", headers={"Accept": "application/json"}, data={
            "csrf": form["csrf"], "grant_id": principal.grant_id, "action": "update_permissions", "scope": scopes,
        })
        assert response.status_code == 200
        if scopes == "wirecloud:read":
            assert (await oauth_client.post("/mcp", headers=headers, json=payload)).status_code == 403
        else:
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), headers=headers) as http:
                async with Client(streamable_http_client(AUDIENCE, http_client=http)) as client:
                    created = await client.call_tool("create_workspace", {"title": "Updated connection permissions"})
                    assert not created.is_error, created
                    assert created.structured_content["id"]


async def test_all_authoring_tools_through_the_official_sdk(mcp_setup, oauth_client, db_session):
    """Use the real transport, schemas, permission checks, and persistence for all tools."""
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    from wirecloud.mcp.tools import TOOL_MAP

    app, _ = mcp_setup
    _, token, _ = await token_for_client(oauth_client, db_session)
    called = set()
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), headers={"Authorization": "Bearer " + token}) as http:
        async with Client(streamable_http_client(AUDIENCE, http_client=http)) as client:
            advertised = (await client.list_tools()).tools
            assert all(tool.input_schema.get("additionalProperties") is False for tool in advertised)
            async def call(tool_name, **arguments):
                result = await client.call_tool(tool_name, arguments)
                assert not result.is_error, (tool_name, result)
                called.add(tool_name)
                return result.structured_content

            assert (await call("get_session_info"))["user"]["id"]
            widget_bytes = package()
            encoded = base64.b64encode(widget_bytes).decode()
            assert (await call("validate_resource_package", package_base64=encoded))["valid"]
            widget_resource = (await call("install_resource", package_base64=encoded))["resource"]
            operator_resource = (await call("install_resource", package_base64=base64.b64encode(package("operator")).decode()))["resource"]
            assert (await call("list_resources", query="mcp-widget"))["total"] >= 1
            assert (await call("get_resource", resource=widget_resource))["title"] == "Test component"
            assert (await call("get_resource_documentation", resource=widget_resource))["title"] == "Test component"

            workspace_id = (await call("create_workspace", title="SDK dashboard", allow_renaming=True))["id"]
            inspected = await call("get_workspace", workspace_id=workspace_id)
            original_tab = inspected["workspace"]["tabs"][0]["id"]
            assert (await call("list_workspaces", query="SDK dashboard"))["total"] >= 1
            await call("update_workspace", workspace_id=workspace_id, title="SDK dashboard updated", description="Retain description")
            await call("update_workspace", workspace_id=workspace_id, title="SDK dashboard final")
            assert (await call("get_workspace", workspace_id=workspace_id))["workspace"]["description"] == "Retain description"
            second_tab = (await call("create_tab", workspace_id=workspace_id, title="Data", name="sdk-data"))["result"]["id"]
            await call("update_tab", workspace_id=workspace_id, tab_id=second_tab, title="Updated data", name="sdk-data-updated", visible=True)
            await call("reorder_tabs", workspace_id=workspace_id, tab_ids=[second_tab, original_tab])
            assert (await call("get_workspace", workspace_id=workspace_id))["workspace"]["tabs"][0]["id"] == second_tab

            for target, ids in [("platform", {}), ("workspace", {"workspace_id": workspace_id}),
                    ("tab", {"workspace_id": workspace_id, "tab_id": second_tab})]:
                await call("update_preferences", target=target, values={"sdkPreference": "value"}, **ids)
                values = await call("get_preferences", target=target, **ids)
                assert values["sdkPreference"]["value"] == "value"

            added = await call("add_widget", workspace_id=workspace_id, tab_id=original_tab,
                resource=widget_resource, title="SDK widget", layouts={"0": {"x": 0, "y": 0, "w": 4, "h": 3}})
            widget_id = added["result"]["id"]
            await call("update_widget", workspace_id=workspace_id, tab_id=original_tab, widget_id=widget_id,
                title="Moved widget", destination_tab_id=second_tab, layouts={"0": {"x": 1, "y": 2}})
            moved = await call("get_workspace", workspace_id=workspace_id)
            moved_tab = next(tab for tab in moved["workspace"]["tabs"] if tab["id"] == second_tab)
            widget_id = moved_tab["widgets"][0]["id"]
            assert moved_tab["widgets"][0]["title"] == "Moved widget"
            await call("set_widget_variables", workspace_id=workspace_id, tab_id=second_tab, widget_id=widget_id,
                values={"message": "SDK input", "api_key": "sdk-widget-secret"})
            added = await call("add_operator", workspace_id=workspace_id, resource=operator_resource,
                preferences={"message": "SDK operator", "api_key": "sdk-operator-secret"})
            operator_id = added["result"]["operator_id"]
            await call("update_operator", workspace_id=workspace_id, operator_id=operator_id, preferences={"message": "Updated operator"})
            await call("connect_components", workspace_id=workspace_id,
                source={"type": "widget", "id": widget_id, "endpoint": "output"},
                target={"type": "operator", "id": operator_id, "endpoint": "input"})
            await call("layout_wiring", workspace_id=workspace_id, preserve_existing=False)
            inspected = await call("get_wiring", workspace_id=workspace_id)
            assert len(inspected["wiring"]["connections"]) == 1
            assert "sdk-widget-secret" not in json.dumps(inspected)
            assert "sdk-operator-secret" not in json.dumps(inspected)

            exported = await call("export_workspace", workspace_id=workspace_id, vendor="test", name="sdk-mashup")
            assert "sdk-widget-secret" not in json.dumps(exported)
            assert "sdk-operator-secret" not in json.dumps(exported)
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                archive.writestr("config.xml", json.dumps(exported["descriptor"]))
            mashup = (await call("install_resource", package_base64=base64.b64encode(output.getvalue()).decode()))["resource"]
            imported = (await call("import_mashup", mashup=mashup, title="Imported SDK dashboard", allow_renaming=True))["id"]
            imported_data = await call("get_workspace", workspace_id=imported)
            assert "sdk-widget-secret" not in json.dumps(imported_data)
            assert "sdk-operator-secret" not in json.dumps(imported_data)
            cloned = (await call("clone_workspace", source_workspace_id=workspace_id, title="Cloned SDK dashboard", allow_renaming=True))["id"]
            await call("merge_mashup", workspace_id=cloned, mashup=mashup)
            assert len((await get_workspace_by_id(db_session, Id(cloned))).tabs) > 2

            await call("disconnect_components", workspace_id=workspace_id, connection_index=0)
            await call("remove_operator", workspace_id=workspace_id, operator_id=operator_id)
            await call("remove_widget", workspace_id=workspace_id, tab_id=second_tab, widget_id=widget_id)
            await call("delete_tab", workspace_id=workspace_id, tab_id=second_tab)
            for identifier in (workspace_id, imported, cloned):
                await call("delete_workspace", workspace_id=identifier)
                assert await get_workspace_by_id(db_session, Id(identifier)) is None
            for resource in (mashup, widget_resource, operator_resource):
                await call("uninstall_resource", resource=resource)
    assert called == set(TOOL_MAP), "Every advertised tool must be exercised over the transport"


async def test_live_permissions_private_workspaces_and_closed_inputs_over_sdk(mcp_setup, oauth_client, db_session):
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    app, _ = mcp_setup
    owner, owner_token, _ = await token_for_client(oauth_client, db_session)
    workspace = await adapter(db_session, owner, app).execute("create_workspace", {"title": "Private workspace", "allow_renaming": True})
    _, other_token, _ = await token_for_client(oauth_client, db_session)
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), headers={"Authorization": "Bearer " + other_token}) as http:
        async with Client(streamable_http_client(AUDIENCE, http_client=http)) as client:
            for tool, args in [("get_workspace", {"workspace_id": workspace["id"]}),
                    ("update_workspace", {"workspace_id": workspace["id"], "title": "Not allowed"}),
                    ("delete_workspace", {"workspace_id": workspace["id"]}),
                    ("clone_workspace", {"source_workspace_id": workspace["id"], "title": "Not allowed"})]:
                result = await client.call_tool(tool, args)
                assert result.is_error, (tool, result)
            result = await client.call_tool("create_workspace", {"title": "Injected owner", "owner": str(owner.user.id)})
            assert result.is_error
    await db_session.client.users.update_one({"_id": owner.user.id}, {"$set": {"user_permissions": []}})
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), headers={"Authorization": "Bearer " + owner_token}) as http:
        async with Client(streamable_http_client(AUDIENCE, http_client=http)) as client:
            result = await client.call_tool("create_workspace", {"title": "Permission revoked"})
            assert result.is_error and "403" in str(result)


@pytest.mark.parametrize("prefix", ["", "/platform"])
async def test_upload_cors_and_oauth_challenges(mcp_setup, oauth_app, db_session, monkeypatch, prefix):
    app, _ = mcp_setup
    if prefix:
        # The public audience need not change to exercise routing behind a proxy.
        monkeypatch.setattr(app, "root_path", prefix)
    async with AsyncClient(transport=ASGITransport(app=app, root_path=prefix), base_url="http://localhost") as client:
        preflight = await client.options(prefix + "/mcp/uploads", headers={"Origin": "http://localhost",
            "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization,content-type"})
        assert preflight.status_code == 200, preflight.text
        assert preflight.headers["access-control-allow-origin"] == "http://localhost"
        anonymous = await client.post(prefix + "/mcp/uploads", content=package())
        assert anonymous.status_code == 401 and "resource_metadata=" in anonymous.headers["www-authenticate"]
        _, token, _ = await token_for_client(client, db_session, scopes=["wirecloud:read"])
        denied = await client.post(prefix + "/mcp/uploads", content=package(), headers={"Authorization": "Bearer " + token})
        assert denied.status_code == 403
        assert 'scope="wirecloud:component:install"' in denied.headers["www-authenticate"]
        rejected = await client.options(prefix + "/mcp/uploads", headers={"Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST"})
        assert "access-control-allow-origin" not in rejected.headers


async def test_transport_rejects_bad_origins_hosts_cookies_and_large_bodies(mcp_setup, oauth_client, db_session):
    _, token, _ = await token_for_client(oauth_client, db_session)
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json, text/event-stream"}
    assert (await oauth_client.post("/mcp", json=payload)).status_code == 401
    assert (await oauth_client.post("/mcp", json=payload, headers={**headers, "Origin": "https://evil.example"})).status_code == 403
    assert (await oauth_client.post("/mcp", json=payload, headers={**headers, "Host": "evil.example"})).status_code == 421
    assert (await oauth_client.post("/mcp", content=b" " * (4 * 1024 * 1024 + 1), headers=headers)).status_code == 413
    for invalid in (b"null", b"[]", b"42", b"not-json"):
        result = await oauth_client.post("/mcp", content=invalid, headers={**headers, "Content-Type": "application/json"})
        assert result.status_code < 500 and "error" in result.text.lower()


async def test_expired_and_incomplete_uploads_cannot_be_installed(mcp_setup, oauth_client, db_session):
    from datetime import timedelta
    app, _ = mcp_setup
    principal, _, _ = await token_for_client(oauth_client, db_session)
    expired = await store_upload(db_session, principal, package())
    await db_session.client.mcp_uploads.update_one({"_id": delegated.digest(expired["upload_id"])},
        {"$set": {"expires_at": delegated.now() - timedelta(seconds=1)}})
    with pytest.raises(HTTPException) as error:
        await consume_upload(db_session, principal, expired["upload_id"])
    assert error.value.status_code == 404
    incomplete = await store_upload(db_session, principal, package())
    await db_session.client.mcp_upload_chunks.delete_many({"upload_id": delegated.digest(incomplete["upload_id"])})
    with pytest.raises(HTTPException) as error:
        await adapter(db_session, principal, app).execute("install_resource", {"upload_id": incomplete["upload_id"]})
    assert error.value.status_code == 422


def test_linked_duplicate_and_oversized_packages_are_rejected(monkeypatch):
    import stat
    from wirecloud.mcp import packages
    linked = io.BytesIO(package())
    with zipfile.ZipFile(linked, "a") as archive:
        entry = zipfile.ZipInfo("link")
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(entry, "/etc/passwd")
    with pytest.raises(HTTPException):
        validate_package(linked.getvalue())
    duplicate = io.BytesIO(package())
    with zipfile.ZipFile(duplicate, "a") as archive, pytest.warns(UserWarning, match="Duplicate name"):
        archive.writestr("index.html", "duplicate")
    with pytest.raises(HTTPException):
        validate_package(duplicate.getvalue())
    monkeypatch.setattr(packages, "EXTRACTED_LIMIT", 10)
    with pytest.raises(HTTPException):
        validate_package(package())
    with pytest.raises(HTTPException) as error:
        decode_package("a" * (4 * ((packages.INLINE_LIMIT + 2) // 3) + 1))
    assert error.value.status_code == 413


async def test_oauth_discovery_and_sdk_over_tcp_with_a_deployment_prefix(oauth_app, db_session, monkeypatch):
    """Real Uvicorn/HTTP sockets, OAuth code exchange, and the official MCP client."""
    import asyncio
    import socket
    from urllib.parse import parse_qs, urlsplit
    import httpx2
    import uvicorn
    from fastapi import FastAPI
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    from wirecloud.database import get_session
    from wirecloud.oauth2provider.plugins import OAuth2ProviderPlugin

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    origin = f"http://127.0.0.1:{sock.getsockname()[1]}"
    base = origin + "/platform"
    audience = base + "/mcp"
    monkeypatch.setattr(settings, "MCP_PUBLIC_URL", audience, raising=False)
    monkeypatch.setattr(settings, "OAUTH2_PUBLIC_URL", base)
    app = FastAPI(root_path="/platform")
    OAuth2ProviderPlugin(app)

    async def session():
        yield db_session

    app.dependency_overrides[get_session] = session
    plugin = WirecloudMCPPlugin(app)
    server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_level="error", access_log=False))
    async with app.router.lifespan_context(app):
        task = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            for _ in range(100):
                if server.started:
                    break
                if task.done():
                    await task
                await asyncio.sleep(0.01)
            assert server.started
            async with AsyncClient(base_url=origin) as browser:
                missing = await browser.post("/platform/mcp", json={})
                assert missing.status_code == 401
                metadata_url = origin + "/.well-known/oauth-protected-resource/platform/mcp"
                assert metadata_url in missing.headers["www-authenticate"]
                metadata = (await browser.get(metadata_url)).json()
                assert metadata["resource"] == audience
                issuer = (await browser.get(origin + "/.well-known/oauth-authorization-server/platform/oauth2")).json()
                assert issuer["issuer"] == base + "/oauth2"
                preflight = await browser.options("/platform/mcp/uploads", headers={"Origin": origin,
                    "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization"})
                assert preflight.status_code == 200 and preflight.headers["access-control-allow-origin"] == origin

                user, _ = await login_user(db_session, browser)
                registered = (await browser.post(issuer["registration_endpoint"], json={"client_name": "TCP client",
                    "redirect_uris": ["http://127.0.0.1:9000/callback"]})).json()
                verifier = delegated.random_token()
                start = await browser.get(issuer["authorization_endpoint"], params={"client_id": registered["client_id"],
                    "resource": audience, "redirect_uri": "http://127.0.0.1:9000/callback", "scope": "wirecloud:read",
                    "response_type": "code", "code_challenge_method": "S256", "code_challenge": delegated.pkce(verifier),
                    "state": "tcp-state"})
                assert start.status_code == 302
                consent = await browser.get(start.headers["location"])
                assert consent.status_code == 200 and user.username in consent.text
                form = {key: values[0] for key, values in parse_qs(urlsplit(start.headers["location"]).query).items()}
                approved = await browser.post("/platform/oauth2/consent", data={**form, "decision": "approve"})
                callback = parse_qs(urlsplit(approved.headers["location"]).query)
                assert callback["state"] == ["tcp-state"]
                response = await browser.post(issuer["token_endpoint"], data={"grant_type": "authorization_code",
                    "code": callback["code"][0], "code_verifier": verifier, "client_id": registered["client_id"],
                    "resource": audience, "redirect_uri": "http://127.0.0.1:9000/callback"})
                assert response.status_code == 200, response.text
                tokens = response.json()
                async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + tokens["access_token"]}) as http:
                    async with Client(streamable_http_client(audience, http_client=http)) as client:
                        result = await client.call_tool("get_session_info", {})
                        assert not result.is_error and result.structured_content["user"]["id"] == str(user.id)
                        assert result.structured_content["connections_url"] == base + "/oauth2/connections"
                revoked = await browser.post(issuer["revocation_endpoint"], data={"client_id": registered["client_id"],
                    "token": tokens["refresh_token"]})
                assert revoked.status_code == 200
                assert (await browser.post("/platform/mcp", json={},
                    headers={"Authorization": "Bearer " + tokens["access_token"]})).status_code == 401
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, 5)
            sock.close()
