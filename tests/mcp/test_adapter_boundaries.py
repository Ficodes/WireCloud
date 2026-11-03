"""Authoring failures must preserve ownership, values, wiring, and credentials."""
import base64
import io
import json
import sys
import zipfile
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

if sys.version_info < (3, 11):
    pytest.skip("MCP requires Python 3.11+", allow_module_level=True)
pytest.importorskip("mcp")

from fastapi import HTTPException
from pydantic import ValidationError
from starlette.background import BackgroundTask
from starlette.responses import Response, StreamingResponse

from oauth2provider.test_oauth import oauth_app, oauth_client
from test_mcp import mcp_setup, token_for_client, adapter, package
from wirecloud.catalogue.crud import get_catalogue_resource
from wirecloud.database import DBSession, Id
from wirecloud.mcp.utils import redact
from wirecloud.mcp.operations import preferences, wiring
from wirecloud.mcp import packages
from wirecloud.mcp.schemas import Install, WiringPlacement
from wirecloud.platform.wiring.schemas import WiringConnectionEndpoint
from wirecloud.platform.workspace.crud import get_workspace_by_id


def repack(content, changes=None, files=None, remove=()):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as original, zipfile.ZipFile(output, "w") as archive:
        for name in original.namelist():
            if name in remove:
                continue
            data = original.read(name)
            if name == "config.xml":
                descriptor = json.loads(data)
                descriptor.update(changes or {})
                data = json.dumps(descriptor).encode()
            archive.writestr(name, data)
        for name, data in (files or {}).items():
            archive.writestr(name, data)
    return output.getvalue()


@pytest.fixture
async def scene(mcp_setup, oauth_client, db_session):
    app, _ = mcp_setup
    principal, _, _ = await token_for_client(oauth_client, db_session)
    api = adapter(db_session, principal, app)
    async def install(content):
        return (await api.execute("install_resource", {"package_base64": base64.b64encode(content).decode()}))["resource"]
    widget_resource = await install(package())
    operator_resource = await install(package("operator"))
    workspace_id = (await api.execute("create_workspace", {"title": "Boundary checks", "allow_renaming": True}))["id"]
    workspace = await get_workspace_by_id(db_session, Id(workspace_id))
    tab_id = next(iter(workspace.tabs))
    widget_id = (await api.execute("add_widget", {"workspace_id": workspace_id, "tab_id": tab_id,
        "resource": widget_resource, "title": "Widget"}))["result"]["id"]
    operator_id = (await api.execute("add_operator", {"workspace_id": workspace_id,
        "resource": operator_resource}))["result"]["operator_id"]
    return SimpleNamespace(api=api, principal=principal, workspace_id=workspace_id, tab_id=tab_id,
        widget_id=widget_id, operator_id=operator_id, widget_resource=widget_resource,
        operator_resource=operator_resource, install=install)


def assert_http(status, detail=""):
    """Assert the public error contract, including its useful explanation."""
    return pytest.raises(HTTPException, match=rf"{status}.*{detail}")


async def test_invalid_and_missing_workspaces_and_timestamps(scene):
    with assert_http(422, "Invalid workspace ID"):
        await scene.api.workspace("not-an-id")
    with assert_http(404, "Workspace not found"):
        await scene.api.workspace(str(Id()))
    with assert_http(422, "Invalid modification timestamp"):
        await scene.api.execute("update_workspace", {"workspace_id": scene.workspace_id,
            "title": "Must not change", "expected_last_modified": "not-a-date"})
    with assert_http(404, "Unknown tool"):
        await scene.api.execute("undefined_operation", {})


async def test_shared_workspace_editor_cannot_delete_owner_workspace(scene, db_session):
    await db_session.client.workspaces.update_one({"_id": Id(scene.workspace_id)}, {"$set": {
        "creator": Id(), "users": [{"id": scene.principal.user.id, "accesslevel": 2}]}})
    with assert_http(403, "Only owned workspaces"):
        await scene.api.execute("delete_workspace", {"workspace_id": scene.workspace_id})
    assert await get_workspace_by_id(db_session, Id(scene.workspace_id)) is not None


async def test_tab_reordering_requires_permission_and_an_exact_permutation(scene, monkeypatch):
    with assert_http(422, "every tab ID exactly once"):
        await scene.api.execute("reorder_tabs", {"workspace_id": scene.workspace_id, "tab_ids": []})
    with assert_http(422, "every tab ID exactly once"):
        await scene.api.execute("reorder_tabs", {"workspace_id": scene.workspace_id, "tab_ids": ["missing"]})
    monkeypatch.setattr("wirecloud.mcp.operations.workspaces.is_owner_or_has_permission", lambda *args: False)
    with assert_http(403, "tab permissions"):
        await scene.api.execute("reorder_tabs", {"workspace_id": scene.workspace_id, "tab_ids": [scene.tab_id]})


async def test_widget_resource_update_properties_and_forced_value_protection(scene, db_session):
    result = await scene.api.execute("update_widget", {"workspace_id": scene.workspace_id,
        "tab_id": scene.tab_id, "widget_id": scene.widget_id, "resource": scene.widget_resource})
    assert result["modification_timestamp"]
    await scene.api.execute("set_widget_variables", {"workspace_id": scene.workspace_id,
        "tab_id": scene.tab_id, "widget_id": scene.widget_id, "kind": "properties", "values": {}})
    await db_session.client.workspaces.update_one({"_id": Id(scene.workspace_id)}, {"$set": {
        f"forced_values.widget.{scene.widget_id}.message": {"value": "fixed", "hidden": True}}})
    with assert_http(403, "Forced widget values"):
        await scene.api.execute("set_widget_variables", {"workspace_id": scene.workspace_id,
            "tab_id": scene.tab_id, "widget_id": scene.widget_id, "values": {"message": "override"}})


@pytest.mark.parametrize("args", [{"target": "workspace"}, {"target": "tab"},
    {"target": "tab", "workspace_id": "unused"}])
async def test_preference_targets_require_parent_identifiers(scene, args):
    # Validate the operation's target contract before trying to resolve IDs.
    from wirecloud.mcp.schemas import Preferences
    with assert_http(422, "Workspace and tab IDs"):
        await preferences.get_preferences(scene.api, Preferences(**args))


async def test_missing_and_private_resources_cannot_be_inspected_or_installed(scene, db_session):
    with assert_http(404, "Resource not available"):
        await scene.api.execute("get_resource", {"resource": "test/missing/1.0.0"})
    resource = await get_catalogue_resource(db_session, *scene.widget_resource.split("/"))
    await db_session.client.catalogue_resources.update_one({"_id": resource.id}, {"$set": {"users": [], "groups": [], "public": False}})
    with assert_http(404, "Resource not available"):
        await scene.api.execute("get_resource", {"resource": scene.widget_resource})
    scene.principal.user.permissions = []
    with assert_http(403, "install permission"):
        await scene.api.execute("install_resource", {"package_base64": base64.b64encode(package()).decode()})
    with assert_http(403, "uninstall permission"):
        await scene.api.execute("uninstall_resource", {"resource": scene.operator_resource})


async def test_operator_type_existence_and_preference_permissions(scene):
    with assert_http(422, "operator resource"):
        await scene.api.execute("add_operator", {"workspace_id": scene.workspace_id, "resource": scene.widget_resource})
    with assert_http(404, "Operator not found"):
        await scene.api.execute("update_operator", {"workspace_id": scene.workspace_id, "operator_id": "999"})
    with assert_http(422, "Unknown operator preference"):
        await scene.api.execute("update_operator", {"workspace_id": scene.workspace_id,
            "operator_id": scene.operator_id, "preferences": {"missing": "value"}})
    resource = SimpleNamespace(description=SimpleNamespace(preferences=[
        SimpleNamespace(name="locked", readonly=True), SimpleNamespace(name="hidden", readonly=False, hidden=True)]))
    for name in ("locked", "hidden"):
        with assert_http(403, "Read-only and hidden"):
            wiring.validate_operator_preferences(resource, {name: "new"})


def endpoint(kind, identifier, name):
    return WiringConnectionEndpoint(type=kind, id=identifier, endpoint=name)


async def test_connections_validate_component_existence_endpoint_names_and_types(scene, db_session, monkeypatch):
    workspace = await scene.api.workspace(scene.workspace_id)
    source = endpoint("operator", scene.operator_id, "output")
    target = endpoint("widget", scene.widget_id, "input")
    for bad, detail in [(endpoint("operator", "999", "output"), "Operator endpoint not found"),
            (endpoint("widget", "999", "output"), "Widget endpoint not found"),
            (endpoint("operator", scene.operator_id, "missing"), "Unknown component endpoint")]:
        with assert_http(404 if bad.id == "999" else 422, detail):
            await wiring.validate_connection(scene.api, workspace, bad, target)
    resource = await get_catalogue_resource(db_session, *scene.widget_resource.split("/"))
    await db_session.client.catalogue_resources.update_one({"_id": resource.id}, {"$set": {"description.wiring.inputs.0.type": "number"}})
    with assert_http(422, "incompatible"):
        await wiring.validate_connection(scene.api, workspace, source, target)
    await db_session.client.catalogue_resources.delete_one({"_id": resource.id})
    with assert_http(404, "Endpoint resource not available"):
        await wiring.validate_connection(scene.api, workspace, source, target)
    with assert_http(422, "missing components"):
        await scene.api.execute("export_workspace", {"workspace_id": scene.workspace_id})


async def test_remove_operator_cleans_connections_and_behaviour_views_atomically(scene, db_session, monkeypatch):
    from wirecloud.mcp.operations import wiring as module
    source = {"type": "operator", "id": scene.operator_id, "endpoint": "output"}
    target = {"type": "widget", "id": scene.widget_id, "endpoint": "input"}
    await scene.api.execute("connect_components", {"workspace_id": scene.workspace_id, "source": source, "target": target})
    await scene.api.execute("add_operator", {"workspace_id": scene.workspace_id, "resource": scene.operator_resource})
    # Keep an unrelated connection and visual connection in every view.
    visual = [{"sourcename": f"operator/{scene.operator_id}/output", "targetname": f"widget/{scene.widget_id}/input"},
        {"sourcename": f"widget/{scene.widget_id}/output", "targetname": f"widget/{scene.widget_id}/input"}]
    await db_session.client.workspaces.update_one({"_id": Id(scene.workspace_id)}, {"$set": {
        "wiring_status.visualdescription.connections": visual,
        "wiring_status.visualdescription.behaviours": [{"title": "Saved view", "description": "Keep this view",
            "components": {}, "connections": visual}],
        "wiring_status.connections": [{"source": source, "target": target}, {"source": target, "target": target}]}})
    original_permission = module.is_owner_or_has_permission
    monkeypatch.setattr(module, "is_owner_or_has_permission", lambda *args: False)
    with assert_http(403, "Operator deletion permission"):
        await scene.api.execute("remove_operator", {"workspace_id": scene.workspace_id, "operator_id": scene.operator_id})
    with assert_http(403, "Connection deletion permission"):
        await scene.api.execute("disconnect_components", {"workspace_id": scene.workspace_id, "connection_index": 0})
    monkeypatch.setattr(module, "is_owner_or_has_permission", lambda user, ws, perm: perm != "WORKSPACE.WIRING.DELETE")
    with assert_http(403, "Connection deletion permission"):
        await scene.api.execute("remove_operator", {"workspace_id": scene.workspace_id, "operator_id": scene.operator_id})
    assert len((await scene.api.workspace(scene.workspace_id)).wiring_status.connections) == 2
    monkeypatch.setattr(module, "is_owner_or_has_permission", original_permission)
    with assert_http(404, "Connection not found"):
        await scene.api.execute("disconnect_components", {"workspace_id": scene.workspace_id, "connection_index": 99})
    await scene.api.execute("remove_operator", {"workspace_id": scene.workspace_id, "operator_id": scene.operator_id})
    status = (await scene.api.workspace(scene.workspace_id)).wiring_status
    assert scene.operator_id not in status.operators
    assert len(status.connections) == 1
    assert len(status.visualdescription.connections) == 1
    assert len(status.visualdescription.behaviours[0].connections) == 1
    assert status.visualdescription.behaviours[0].title == "Saved view"


@pytest.mark.parametrize("unavailable", ["missing", "private"])
async def test_workspace_read_preserves_unavailable_operators_without_exposing_values(
    scene: SimpleNamespace, db_session: DBSession, unavailable: str
) -> None:
    await scene.api.execute("update_operator", {
        "workspace_id": scene.workspace_id,
        "operator_id": scene.operator_id,
        "preferences": {"message": "Stored operator value"},
    })
    workspace = await scene.api.workspace(scene.workspace_id)
    stored_preferences = workspace.wiring_status.operators[scene.operator_id].preferences
    assert stored_preferences
    resource = await get_catalogue_resource(db_session, *scene.operator_resource.split("/"))
    if unavailable == "missing":
        await db_session.client.catalogue_resources.delete_one({"_id": resource.id})
    else:
        await db_session.client.catalogue_resources.update_one(
            {"_id": resource.id}, {"$set": {"users": [], "groups": [], "public": False}}
        )

    result = await scene.api.execute("get_workspace", {"workspace_id": scene.workspace_id})
    operator = result["workspace"]["wiring"]["operators"][scene.operator_id]
    assert operator["name"] == scene.operator_resource
    assert operator["preferences"] == {}
    assert operator["properties"] == {}
    assert result["workspace"]["tabs"][0]["widgets"][0]["id"] == scene.widget_id
    assert result["modification_timestamp"] == scene.api.timestamp(workspace)
    persisted = await scene.api.workspace(scene.workspace_id)
    assert persisted.wiring_status.operators[scene.operator_id].preferences == stored_preferences


async def test_layout_handles_repeated_and_missing_resource_descriptors(scene, db_session):
    # Shared descriptors are fetched once; missing descriptors still get a layout.
    await scene.api.execute("add_operator", {"workspace_id": scene.workspace_id, "resource": scene.operator_resource})
    workspace = await scene.api.workspace(scene.workspace_id)
    resource = await get_catalogue_resource(db_session, *scene.operator_resource.split("/"))
    await db_session.client.catalogue_resources.delete_one({"_id": resource.id})
    patches = await wiring.wiring_layout_patches(scene.api, workspace, workspace.wiring_status,
        moves=[WiringPlacement(type="operator", id=scene.operator_id, x=1000, y=500)])
    assert any(patch["value"] == {"x": 1000, "y": 500} for patch in patches)


@pytest.mark.parametrize("doc,files,expected", [
    ("docs/guide", {"docs/guide/index.md": "# Directory guide"}, "# Directory guide"),
    ("docs/guide.md", {"docs/guide.md": "x" * 65537}, "x" * 65536),
    ("docs/missing.md", {}, None),
], ids=["directory-index", "truncated-file", "missing-documentation"])
async def test_documentation_supports_directory_indexes_and_bounded_content(scene, doc, files, expected, db_session):
    # Imported legacy archives may use directory indexes or lose a document.
    # Install a valid resource, then represent those stored archive states.
    content = repack(package(version="2.0.0"), {"doc": doc}, {doc: "Guide"})
    identifier = await scene.install(content)
    resource = await get_catalogue_resource(db_session, *identifier.split("/"))
    from wirecloud.catalogue.utils import wgt_deployer
    stored = Path(wgt_deployer.get_base_dir(resource.vendor, resource.short_name, resource.version)) / resource.template_uri
    stored.write_bytes(repack(content, files=files, remove=[doc]))
    data = await scene.api.execute("get_resource_documentation", {"resource": identifier})
    if expected is None:
        assert "documentation" not in data
    else:
        assert data["documentation"] == expected
        assert data["truncated"] == (len(expected) == 65536)


async def test_external_documentation_is_returned_as_a_link_without_fetching(scene):
    identifier = await scene.install(repack(package(version="2.0.0"), {"doc": "https://docs.example/guide"}))
    data = await scene.api.execute("get_resource_documentation", {"resource": identifier})
    assert data["doc"] == "https://docs.example/guide" and "documentation" not in data


@pytest.mark.parametrize("url", ["file:///tmp/resource.wgt", "http://user:secret@wc.example/a.wgt", "https://"])
async def test_package_urls_reject_local_files_credentials_and_missing_hosts(scene, url):
    with assert_http(422, r"HTTP\(S\) package URL"):
        await scene.api.execute("install_resource", {"url": url})


@pytest.mark.parametrize("response", [None, Response(status_code=404)])
async def test_failed_proxy_downloads_have_a_useful_error(scene, monkeypatch, response):
    monkeypatch.setattr("wirecloud.proxy.routes.WIRECLOUD_PROXY.do_request", AsyncMock(return_value=response))
    with assert_http(409, "configured proxy"):
        await scene.api.execute("install_resource", {"url": "https://packages.example/missing.wgt"})


@pytest.mark.parametrize("too_large", [False, True])
async def test_streamed_downloads_are_bounded_and_release_connections(scene, monkeypatch, too_large):
    cleanup = AsyncMock()
    content = package(version="2.0.0")
    async def chunks():
        yield content[:10]
        yield content[10:]
    response = StreamingResponse(chunks(), background=BackgroundTask(cleanup))
    monkeypatch.setattr("wirecloud.proxy.routes.WIRECLOUD_PROXY.do_request", AsyncMock(return_value=response))
    if too_large:
        monkeypatch.setattr(packages, "PACKAGE_LIMIT", 10)
        with assert_http(413, "Downloaded package"):
            await scene.api.execute("install_resource", {"url": "https://packages.example/component.wgt"})
    else:
        assert (await scene.api.execute("install_resource", {"url": "https://packages.example/component.wgt"}))["resource"].endswith("/2.0.0")
    cleanup.assert_awaited_once()


def mashup_package(child, src="inner.wgt", **changes):
    descriptor = {"type": "mashup", "vendor": "test", "name": "embedded-mashup", "version": "1.0.0",
        "title": "Embedded components", "description": "Test", "email": "test@example.com", "macversion": 2,
        "embedded": [{"vendor": "test", "name": "mcp-widget", "version": "2.0.0", "src": src}], **changes}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("config.xml", json.dumps(descriptor))
        archive.writestr(src, child)
    return output.getvalue()


async def test_embedded_packages_are_validated_and_installed_with_the_mashup(scene):
    content = mashup_package(package(version="2.0.0"))
    result = await scene.api.execute("install_resource", {"package_base64": base64.b64encode(content).decode(),
        "install_embedded_resources": True})
    assert result["resource"] == "test/embedded-mashup/1.0.0"
    assert (await scene.api.execute("get_resource", {"resource": "test/mcp-widget/2.0.0"}))["version"] == "2.0.0"


async def test_remote_embedded_dependencies_must_be_installed_explicitly(scene, monkeypatch):
    # Validate the adapter policy even if a custom descriptor parser exposes a remote dependency.
    original = packages.validate_package
    def remote(content):
        package, info = original(content)
        return package, SimpleNamespace(embedded=[SimpleNamespace(src="https://packages.example/dependency.wgt")])
    monkeypatch.setattr(packages, "validate_package", remote)
    with assert_http(422, "remote embedded dependencies explicitly"):
        await scene.api.execute("install_resource", {"package_base64": base64.b64encode(package()).decode(),
            "install_embedded_resources": True})


def test_masked_secrets_and_ambiguous_package_sources_are_rejected():
    assert redact({"value": "********"}) == {"has_value": True}
    for data in ({}, {"url": "https://wc.example/a.wgt", "upload_id": "handle"}):
        with pytest.raises(ValidationError, match="Supply exactly one"):
            Install.model_validate(data)
