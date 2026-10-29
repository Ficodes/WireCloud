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

from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from wirecloud.mcp import docs
from wirecloud.platform.iwidget.models import WidgetLayout
from wirecloud.platform.iwidget.schemas import WidgetLayoutUpdate
from wirecloud.platform.wiring.schemas import WiringConnectionEndpoint


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Empty(Arguments):
    pass


class Page(Arguments):
    query: str = Field(default="", max_length=200, description=docs.query_description)
    offset: int = Field(default=0, ge=0, description=docs.offset_description)
    limit: int = Field(default=20, ge=1, le=100, description=docs.limit_description)


class Workspace(Arguments):
    workspace_id: str = Field(description=docs.workspace_id_description)


class Edit(Workspace):
    expected_last_modified: Optional[str] = Field(default=None, description=docs.expected_last_modified_description)


class CreateWorkspace(Arguments):
    name: str = Field(default="", description=docs.create_workspace_name_description)
    title: str = Field(default="", description=docs.title_description)
    preferences: dict[str, str] = Field(default_factory=dict, description=docs.preferences_description)
    allow_renaming: bool = Field(default=False, description=docs.allow_renaming_description)


class CloneWorkspace(CreateWorkspace):
    source_workspace_id: str = Field(description=docs.source_workspace_id_description)


class UpdateWorkspace(Edit):
    name: str = Field(default="", description=docs.name_description)
    title: str = Field(default="", description=docs.title_description)
    description: str = Field(default="", description=docs.description_description)
    longdescription: str = Field(default="", description=docs.longdescription_description)


class CreateTab(Edit):
    name: str = Field(default="", description=docs.name_description)
    title: str = Field(default="", description=docs.title_description)


class Tab(Edit):
    tab_id: str = Field(description=docs.tab_id_description)


class UpdateTab(Tab):
    name: str = Field(default="", description=docs.name_description)
    title: str = Field(default="", description=docs.title_description)
    visible: Optional[bool] = Field(default=None, description=docs.visible_description)


class ReorderTabs(Edit):
    tab_ids: list[str] = Field(description=docs.tab_ids_description)


class AddWidget(Tab):
    resource: str = Field(pattern=r"^[^/]+/[^/]+/[^/]+$", description=docs.resource_description)
    title: str = Field(description=docs.title_description)
    layouts: dict[str, WidgetLayout] = Field(default_factory=dict, description=docs.layouts_description)


class Widget(Tab):
    widget_id: str = Field(description=docs.widget_id_description)


class UpdateWidget(Widget):
    title: Optional[str] = Field(default=None, description=docs.update_widget_title_description)
    resource: Optional[str] = Field(
        default=None, pattern=r"^[^/]+/[^/]+/[^/]+$", description=docs.update_widget_resource_description
    )
    destination_tab_id: Optional[str] = Field(default=None, description=docs.destination_tab_id_description)
    layouts: Optional[dict[str, WidgetLayoutUpdate]] = Field(
        default=None, description=docs.update_widget_layouts_description
    )


class WidgetVariables(Widget):
    values: dict[str, Any] = Field(description=docs.widget_variables_values_description)
    kind: Literal["preferences", "properties"] = Field(default="preferences", description=docs.kind_description)


class Preferences(Arguments):
    target: Literal["platform", "workspace", "tab"] = Field(description=docs.target_description)
    workspace_id: Optional[str] = Field(default=None, description=docs.preferences_workspace_id_description)
    tab_id: Optional[str] = Field(default=None, description=docs.preferences_tab_id_description)


class UpdatePreferences(Preferences):
    values: dict[str, str] = Field(description=docs.update_preferences_values_description)
    expected_last_modified: Optional[str] = Field(default=None, description=docs.expected_last_modified_description)


class Resource(Arguments):
    resource: str = Field(pattern=r"^[^/]+/[^/]+/[^/]+$", description=docs.resource_description)


class Install(Arguments):
    url: Optional[str] = Field(default=None, description=docs.url_description)
    package_base64: Optional[str] = Field(default=None, description=docs.install_package_base64_description)
    upload_id: Optional[str] = Field(default=None, description=docs.upload_id_description)
    install_embedded_resources: bool = Field(default=False, description=docs.install_embedded_resources_description)

    @model_validator(mode="after")
    def single_source(self) -> Install:
        if sum(value is not None for value in (self.url, self.package_base64, self.upload_id)) != 1:
            raise ValueError("Supply exactly one of url, package_base64, or upload_id")
        return self


class ValidatePackage(Arguments):
    package_base64: str = Field(description=docs.package_base64_description)


class AddOperator(Edit):
    resource: str = Field(pattern=r"^[^/]+/[^/]+/[^/]+$", description=docs.resource_description)
    preferences: dict[str, Any] = Field(default_factory=dict, description=docs.add_operator_preferences_description)


class Operator(Edit):
    operator_id: str = Field(pattern=r"^\d+$", description=docs.operator_id_description)


class UpdateOperator(Operator):
    preferences: dict[str, Any] = Field(default_factory=dict, description=docs.update_operator_preferences_description)


class Connect(Edit):
    source: WiringConnectionEndpoint = Field(description=docs.source_description)
    target: WiringConnectionEndpoint = Field(description=docs.connect_target_description)


class Disconnect(Edit):
    connection_index: int = Field(ge=0, description=docs.connection_index_description)


class WiringPlacement(Arguments):
    type: Literal["widget", "operator"] = Field(description=docs.type_description)
    id: str = Field(min_length=1, description=docs.id_description)
    x: int = Field(ge=20, strict=True, description=docs.x_description)
    y: int = Field(ge=10, strict=True, description=docs.y_description)


class LayoutWiring(Edit):
    preserve_existing: bool = Field(default=True, description=docs.preserve_existing_description)
    positions: list[WiringPlacement] = Field(
        default_factory=list, max_length=500, description=docs.positions_description
    )


class ImportMashup(CreateWorkspace):
    mashup: str = Field(pattern=r"^[^/]+/[^/]+/[^/]+$", description=docs.mashup_description)


class MergeMashup(Edit):
    mashup: str = Field(pattern=r"^[^/]+/[^/]+/[^/]+$", description=docs.mashup_description)


class ExportWorkspace(Workspace):
    vendor: str = Field(default="export", description=docs.vendor_description)
    name: str = Field(default="workspace", description=docs.export_workspace_name_description)
    version: str = Field(default="1.0.0", description=docs.version_description)
