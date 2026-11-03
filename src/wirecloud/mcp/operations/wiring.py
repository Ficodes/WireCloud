# -*- coding: utf-8 -*-
# Copyright (c) 2026 Future Internet Consulting and Development Solutions S.L.

# This file is part of Wirecloud.

# Wirecloud is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Wirecloud is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with Wirecloud.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, Sequence

import jsonpatch
from fastapi import HTTPException

from wirecloud.catalogue.crud import get_catalogue_resource, get_catalogue_resource_by_id
from wirecloud.database import Id
from wirecloud.mcp.layout import component_nodes, placement_patches
from wirecloud.mcp import schemas
from wirecloud.platform.wiring import routes
from wirecloud.platform.wiring.schemas import Wiring, WiringConnectionEndpoint, WiringEntryPatch
from wirecloud.platform.workspace.models import Workspace, WorkspaceWiringOperator
from wirecloud.platform.workspace import routes as workspace_routes
from wirecloud.platform.workspace.utils import is_owner_or_has_permission

if TYPE_CHECKING:
    from wirecloud.catalogue.schemas import CatalogueResource
    from wirecloud.mcp.adapter import WireCloudAdapter


async def get_wiring(adapter: WireCloudAdapter, args: schemas.Workspace) -> dict[str, Any]:
    data = await adapter.call(workspace_routes.get_workspace_entry_with_id, workspace_id=Id(args.workspace_id))
    workspace = await adapter.workspace(args.workspace_id)
    return {"wiring": data.get("wiring", {}), "modification_timestamp": adapter.timestamp(workspace)}


async def add_operator(adapter: WireCloudAdapter, args: schemas.AddOperator) -> dict[str, Any]:
    workspace = await adapter.workspace(args.workspace_id)
    resource = await adapter.resource(args.resource)
    if resource.resource_type() != "operator":
        raise HTTPException(422, "An operator resource is required")
    validate_operator_preferences(resource, args.preferences)

    operator_id = str(max((int(key) for key in workspace.wiring_status.operators), default=-1) + 1)
    patches = [
        {
            "op": "add",
            "path": "/operators/" + operator_id,
            "value": {
                "id": operator_id,
                "name": args.resource,
                "preferences": {key: {"value": value} for key, value in args.preferences.items()},
                "properties": {},
            },
        }
    ]
    await add_missing_positions(adapter, workspace, patches)
    result = await apply_patches(adapter, workspace, patches)
    return {"operator_id": operator_id, "result": result}


async def update_operator(adapter: WireCloudAdapter, args: schemas.UpdateOperator) -> dict[str, Any]:
    workspace = await adapter.workspace(args.workspace_id)
    operator = get_operator(workspace, args.operator_id)
    resource = await adapter.resource(operator.name)
    validate_operator_preferences(resource, args.preferences)

    # Patch only supplied values: never round-trip masked secrets.
    patches = []
    for key, value in args.preferences.items():
        escaped = key.replace("~", "~0").replace("/", "~1")
        patches.append(
            {
                "op": "add",
                "path": f"/operators/{args.operator_id}/preferences/{escaped}",
                "value": {"value": value},
            }
        )
    return await apply_patches(adapter, workspace, patches)


async def remove_operator(adapter: WireCloudAdapter, args: schemas.Operator) -> dict[str, Any]:
    workspace = await adapter.workspace(args.workspace_id)
    get_operator(workspace, args.operator_id)
    if not is_owner_or_has_permission(adapter.user, workspace, "WORKSPACE.OPERATOR.DELETE"):
        raise HTTPException(403, "Operator deletion permission is required")

    patches = [{"op": "remove", "path": "/operators/" + args.operator_id}]
    patches.extend(operator_visual_removals(workspace.wiring_status, args.operator_id))
    connection_patches = operator_connection_removals(workspace.wiring_status, args.operator_id)
    if connection_patches and not is_owner_or_has_permission(adapter.user, workspace, "WORKSPACE.WIRING.DELETE"):
        raise HTTPException(403, "Connection deletion permission is required")
    patches.extend(connection_patches)
    return await apply_patches(adapter, workspace, patches)


async def connect_components(adapter: WireCloudAdapter, args: schemas.Connect) -> dict[str, Any]:
    workspace = await adapter.workspace(args.workspace_id)
    await validate_connection(adapter, workspace, args.source, args.target)
    patches = [
        {
            "op": "add",
            "path": "/connections/-",
            "value": {
                "source": args.source.model_dump(mode="json"),
                "target": args.target.model_dump(mode="json"),
                "readonly": False,
            },
        }
    ]
    await add_missing_positions(adapter, workspace, patches)
    return await apply_patches(adapter, workspace, patches)


async def disconnect_components(adapter: WireCloudAdapter, args: schemas.Disconnect) -> dict[str, Any]:
    workspace = await adapter.workspace(args.workspace_id)
    if not is_owner_or_has_permission(adapter.user, workspace, "WORKSPACE.WIRING.DELETE"):
        raise HTTPException(403, "Connection deletion permission is required")
    if args.connection_index >= len(workspace.wiring_status.connections):
        raise HTTPException(404, "Connection not found")
    patches = [{"op": "remove", "path": "/connections/" + str(args.connection_index)}]
    return await apply_patches(adapter, workspace, patches)


async def layout_wiring(adapter: WireCloudAdapter, args: schemas.LayoutWiring) -> dict[str, Any]:
    workspace = await adapter.workspace(args.workspace_id, edit=True)
    if not is_owner_or_has_permission(adapter.user, workspace, "WORKSPACE.WIRING.EDIT"):
        raise HTTPException(403, "Insufficient wiring permissions")

    patches = await wiring_layout_patches(
        adapter,
        workspace,
        workspace.wiring_status,
        moves=args.positions,
        preserve_existing=args.preserve_existing,
    )
    if patches:
        await apply_patches(adapter, workspace, patches)
    return {"positioned": len(patches)}


async def apply_patches(
    adapter: WireCloudAdapter, workspace: Workspace, patches: list[dict[str, Any]]
) -> dict[str, Any]:
    return await adapter.call(
        routes.patch_wiring_entry,
        workspace_id=workspace.id,
        req=[WiringEntryPatch(**patch) for patch in patches],
        content_type="application/json-patch+json",
    )


async def add_missing_positions(
    adapter: WireCloudAdapter, workspace: Workspace, patches: list[dict[str, Any]]
) -> None:
    current = workspace.wiring_status
    proposed = type(current).model_validate(jsonpatch.apply_patch(current.model_dump(), patches))
    patches.extend(await wiring_layout_patches(adapter, workspace, proposed))


def get_operator(workspace: Workspace, operator_id: str) -> WorkspaceWiringOperator:
    if operator_id not in workspace.wiring_status.operators:
        raise HTTPException(404, "Operator not found")
    return workspace.wiring_status.operators[operator_id]


def operator_visual_removals(status: Wiring, operator_id: str) -> list[dict[str, Any]]:
    patches = []
    descriptions = [("/visualdescription", status.visualdescription)] + [
        (f"/visualdescription/behaviours/{index}", behaviour)
        for index, behaviour in enumerate(status.visualdescription.behaviours)
    ]
    for path, description in descriptions:
        if operator_id in description.components.operator:
            patches.append({"op": "remove", "path": path + "/components/operator/" + operator_id})
        prefix = f"operator/{operator_id}/"
        for index in range(len(description.connections) - 1, -1, -1):
            connection = description.connections[index]
            if connection.sourcename.startswith(prefix) or connection.targetname.startswith(prefix):
                patches.append({"op": "remove", "path": path + "/connections/" + str(index)})
    return patches


def operator_connection_removals(status: Wiring, operator_id: str) -> list[dict[str, Any]]:
    patches = []
    for index in range(len(status.connections) - 1, -1, -1):
        connection = status.connections[index]
        if any(
            endpoint.type.value == "operator" and endpoint.id == operator_id
            for endpoint in (connection.source, connection.target)
        ):
            patches.append({"op": "remove", "path": "/connections/" + str(index)})
    return patches


async def wiring_layout_patches(
    adapter: WireCloudAdapter,
    workspace: Workspace,
    status: Wiring,
    moves: Sequence[schemas.WiringPlacement] = (),
    preserve_existing: bool = True,
) -> list[dict[str, Any]]:
    widgets = {widget.id: widget for tab in workspace.tabs.values() for widget in tab.widgets.values()}
    valid_nodes = {("widget", key) for key in widgets} | {("operator", key) for key in status.operators}
    nodes = component_nodes(status, valid_nodes, moves)
    heights, resources = {}, {}
    for kind, key in sorted(nodes):
        identifier = widgets[key].resource if kind == "widget" else status.operators[key].name
        cache_key = (kind, str(identifier))
        if cache_key not in resources:
            resources[cache_key] = (
                await get_catalogue_resource_by_id(adapter.db, identifier)
                if kind == "widget"
                else await get_catalogue_resource(adapter.db, *identifier.split("/"))
            )
        resource = resources[cache_key]
        if resource is not None:
            endpoints = resource.description.wiring
            heights[(kind, key)] = max(240, 110 + 35 * max(len(endpoints.inputs), len(endpoints.outputs)))
    return placement_patches(status, nodes, heights, moves, preserve_existing)


async def validate_connection(
    adapter: WireCloudAdapter, workspace: Workspace, source: WiringConnectionEndpoint, target: WiringConnectionEndpoint
) -> None:
    definitions = []
    for endpoint, direction in ((source, "outputs"), (target, "inputs")):
        if endpoint.type.value == "operator":
            operator = workspace.wiring_status.operators.get(endpoint.id)
            if operator is None:
                raise HTTPException(404, "Operator endpoint not found")
            resource = await adapter.resource(operator.name)
        else:
            widget = next(
                (
                    widget
                    for tab in workspace.tabs.values()
                    for widget in tab.widgets.values()
                    if widget.id == endpoint.id
                ),
                None,
            )
            if widget is None:
                raise HTTPException(404, "Widget endpoint not found")
            resource = await get_catalogue_resource_by_id(adapter.db, widget.resource)
            if resource is None or not resource.is_available_for(adapter.user):
                raise HTTPException(404, "Endpoint resource not available")

        definition = next(
            (value for value in getattr(resource.description.wiring, direction) if value.name == endpoint.endpoint),
            None,
        )
        if definition is None:
            raise HTTPException(422, "Unknown component endpoint: " + endpoint.endpoint)
        definitions.append(definition)
    if definitions[0].type != definitions[1].type:
        raise HTTPException(422, "Wiring endpoint types are incompatible")


def validate_operator_preferences(resource: CatalogueResource, values: Mapping[str, Any]) -> None:
    definitions = {preference.name: preference for preference in resource.description.preferences}
    for name in values:
        if name not in definitions:
            raise HTTPException(422, "Unknown operator preference: " + name)
        if definitions[name].readonly or getattr(definitions[name], "hidden", False):
            raise HTTPException(403, "Read-only and hidden preferences cannot be changed")
