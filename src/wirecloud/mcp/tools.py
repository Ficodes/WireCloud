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

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from wirecloud.mcp import docs, schemas
from wirecloud.mcp.operations import preferences, resources, widgets, wiring, workspaces

READ = "wirecloud:read"
WRITE = "wirecloud:workspace:write"
DELETE = "wirecloud:workspace:delete"
INSTALL = "wirecloud:component:install"
UNINSTALL = "wirecloud:component:uninstall"

SCOPES = {
    READ: docs.scope_read_description,
    WRITE: docs.scope_write_description,
    DELETE: docs.scope_delete_description,
    INSTALL: docs.scope_install_description,
    UNINSTALL: docs.scope_uninstall_description,
}


@dataclass(frozen=True)
class Tool:
    operation: Callable[..., Awaitable[Any]]
    model: type[schemas.Arguments]
    scopes: tuple[str, ...]
    description: str
    destructive: bool = False

    @property
    def name(self) -> str:
        return self.operation.__name__


TOOLS = [
    Tool(
        workspaces.get_session_info,
        schemas.Empty,
        (READ,),
        docs.get_session_info_description,
    ),
    Tool(
        workspaces.list_workspaces,
        schemas.Page,
        (READ,),
        docs.list_workspaces_description,
    ),
    Tool(
        workspaces.get_workspace,
        schemas.Workspace,
        (READ,),
        docs.get_workspace_description,
    ),
    Tool(
        workspaces.create_workspace,
        schemas.CreateWorkspace,
        (WRITE,),
        docs.create_workspace_description,
    ),
    Tool(
        workspaces.clone_workspace,
        schemas.CloneWorkspace,
        (WRITE,),
        docs.clone_workspace_description,
    ),
    Tool(
        workspaces.update_workspace,
        schemas.UpdateWorkspace,
        (WRITE,),
        docs.update_workspace_description,
    ),
    Tool(
        workspaces.delete_workspace,
        schemas.Edit,
        (WRITE, DELETE),
        docs.delete_workspace_description,
        destructive=True,
    ),
    Tool(
        workspaces.create_tab,
        schemas.CreateTab,
        (WRITE,),
        docs.create_tab_description,
    ),
    Tool(
        workspaces.update_tab,
        schemas.UpdateTab,
        (WRITE,),
        docs.update_tab_description,
    ),
    Tool(
        workspaces.reorder_tabs,
        schemas.ReorderTabs,
        (WRITE,),
        docs.reorder_tabs_description,
    ),
    Tool(
        workspaces.delete_tab,
        schemas.Tab,
        (WRITE, DELETE),
        docs.delete_tab_description,
        destructive=True,
    ),
    Tool(
        widgets.add_widget,
        schemas.AddWidget,
        (WRITE,),
        docs.add_widget_description,
    ),
    Tool(
        widgets.update_widget,
        schemas.UpdateWidget,
        (WRITE,),
        docs.update_widget_description,
    ),
    Tool(
        widgets.remove_widget,
        schemas.Widget,
        (WRITE, DELETE),
        docs.remove_widget_description,
        destructive=True,
    ),
    Tool(
        widgets.set_widget_variables,
        schemas.WidgetVariables,
        (WRITE,),
        docs.set_widget_variables_description,
    ),
    Tool(
        preferences.get_preferences,
        schemas.Preferences,
        (READ,),
        docs.get_preferences_description,
    ),
    Tool(
        preferences.update_preferences,
        schemas.UpdatePreferences,
        (WRITE,),
        docs.update_preferences_description,
    ),
    Tool(
        wiring.get_wiring,
        schemas.Workspace,
        (READ,),
        docs.get_wiring_description,
    ),
    Tool(
        wiring.add_operator,
        schemas.AddOperator,
        (WRITE,),
        docs.add_operator_description,
    ),
    Tool(
        wiring.update_operator,
        schemas.UpdateOperator,
        (WRITE,),
        docs.update_operator_description,
    ),
    Tool(
        wiring.remove_operator,
        schemas.Operator,
        (WRITE, DELETE),
        docs.remove_operator_description,
        destructive=True,
    ),
    Tool(
        wiring.connect_components,
        schemas.Connect,
        (WRITE,),
        docs.connect_components_description,
    ),
    Tool(
        wiring.disconnect_components,
        schemas.Disconnect,
        (WRITE, DELETE),
        docs.disconnect_components_description,
        destructive=True,
    ),
    Tool(
        wiring.layout_wiring,
        schemas.LayoutWiring,
        (WRITE,),
        docs.layout_wiring_description,
    ),
    Tool(
        resources.list_resources,
        schemas.Page,
        (READ,),
        docs.list_resources_description,
    ),
    Tool(
        resources.get_resource,
        schemas.Resource,
        (READ,),
        docs.get_resource_description,
    ),
    Tool(
        resources.get_resource_documentation,
        schemas.Resource,
        (READ,),
        docs.get_resource_documentation_description,
    ),
    Tool(
        resources.validate_resource_package,
        schemas.ValidatePackage,
        (INSTALL,),
        docs.validate_resource_package_description,
    ),
    Tool(
        resources.install_resource,
        schemas.Install,
        (INSTALL,),
        docs.install_resource_description,
    ),
    Tool(
        resources.uninstall_resource,
        schemas.Resource,
        (UNINSTALL,),
        docs.uninstall_resource_description,
        destructive=True,
    ),
    Tool(
        workspaces.import_mashup,
        schemas.ImportMashup,
        (WRITE,),
        docs.import_mashup_description,
    ),
    Tool(
        workspaces.merge_mashup,
        schemas.MergeMashup,
        (WRITE,),
        docs.merge_mashup_description,
    ),
    Tool(
        workspaces.export_workspace,
        schemas.ExportWorkspace,
        (READ,),
        docs.export_workspace_description,
    ),
]

TOOL_MAP = {tool.name: tool for tool in TOOLS}
