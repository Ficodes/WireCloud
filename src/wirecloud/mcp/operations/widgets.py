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

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from wirecloud.database import Id
from wirecloud.mcp import schemas
from wirecloud.platform.iwidget import routes
from wirecloud.platform.iwidget.schemas import WidgetInstanceDataCreate, WidgetInstanceDataUpdate

if TYPE_CHECKING:
    from wirecloud.mcp.adapter import WireCloudAdapter


async def add_widget(adapter: WireCloudAdapter, args: schemas.AddWidget) -> dict[str, Any]:
    await adapter.resource(args.resource)
    return await adapter.call(
        routes.create_widget_instance_collection,
        workspace_id=Id(args.workspace_id),
        tab_id=args.tab_id,
        iwidget=WidgetInstanceDataCreate(title=args.title, widget=args.resource, layouts=args.layouts),
    )


async def update_widget(adapter: WireCloudAdapter, args: schemas.UpdateWidget) -> dict[str, Any]:
    if args.resource:
        await adapter.resource(args.resource)
    return await adapter.call(
        routes.update_widget_instance_entry,
        workspace_id=Id(args.workspace_id),
        tab_id=args.tab_id,
        iwidget_id=args.widget_id,
        iwidget_data=WidgetInstanceDataUpdate(
            title=args.title,
            widget=args.resource,
            tab=args.destination_tab_id,
            layouts=args.layouts,
        ),
    )


async def remove_widget(adapter: WireCloudAdapter, args: schemas.Widget) -> dict[str, Any]:
    return await adapter.call(
        routes.delete_widget_instance_entry,
        workspace_id=Id(args.workspace_id),
        tab_id=args.tab_id,
        iwidget_id=args.widget_id,
    )


async def set_widget_variables(adapter: WireCloudAdapter, args: schemas.WidgetVariables) -> dict[str, Any]:
    workspace = await adapter.workspace(args.workspace_id)
    forced = workspace.forced_values.widget.get(args.widget_id, {})
    if any(key in forced for key in args.values):
        raise HTTPException(403, "Forced widget values cannot be changed")

    operation = (
        routes.update_widget_instance_preferences
        if args.kind == "preferences"
        else routes.update_widget_instance_properties
    )
    return await adapter.call(
        operation,
        workspace_id=Id(args.workspace_id),
        tab_id=args.tab_id,
        iwidget_id=args.widget_id,
        new_values=args.values,
    )
