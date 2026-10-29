"""Export widget properties through the same MCP operations used by clients."""
import base64
import io
import json
import sys
import zipfile

import pytest

if sys.version_info < (3, 11):
    pytest.skip("MCP requires Python 3.11+", allow_module_level=True)
pytest.importorskip("mcp")

from oauth2provider.test_oauth import oauth_app, oauth_client
from test_mcp import adapter, mcp_setup, package, token_for_client
from wirecloud.database import Id
from wirecloud.platform.workspace.crud import get_workspace_by_id


@pytest.mark.parametrize("markdown", ["# Informe\n\nTemperatura: **22 °C**", ""])
async def test_export_preserves_widget_properties_and_omits_secure_values(
    mcp_setup, oauth_client, db_session, markdown
):
    app, _ = mcp_setup
    principal, _, _ = await token_for_client(oauth_client, db_session)
    api = adapter(db_session, principal, app)
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(package())) as original, zipfile.ZipFile(output, "w") as archive:
        for name in original.namelist():
            content = original.read(name)
            if name == "config.xml":
                descriptor = json.loads(content)
                descriptor["properties"] = [
                    {"name": "initialMarkdownValue", "type": "text", "default": ""},
                    {"name": "private_note", "type": "text", "secure": True, "default": ""},
                ]
                content = json.dumps(descriptor).encode()
            archive.writestr(name, content)
    resource = await api.execute("install_resource", {"package_base64": base64.b64encode(output.getvalue()).decode()})
    workspace_id = (await api.execute("create_workspace", {"title": "Markdown export", "allow_renaming": True}))["id"]
    workspace = await get_workspace_by_id(db_session, Id(workspace_id))
    tab_id = next(iter(workspace.tabs))
    widget_id = (await api.execute("add_widget", {
        "workspace_id": workspace_id, "tab_id": tab_id, "resource": resource["resource"], "title": "Markdown"
    }))["result"]["id"]
    await api.execute("set_widget_variables", {
        "workspace_id": workspace_id, "tab_id": tab_id, "widget_id": widget_id,
        "kind": "properties", "values": {"initialMarkdownValue": markdown, "private_note": "never-export-private-note"},
    })

    exported = await api.execute("export_workspace", {"workspace_id": workspace_id})

    properties = exported["descriptor"]["tabs"][0]["resources"][0]["properties"]
    assert properties == {"initialMarkdownValue": {"readonly": False, "value": markdown}}
    assert "never-export-private-note" not in json.dumps(exported)
