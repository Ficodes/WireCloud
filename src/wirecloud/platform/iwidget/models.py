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

from pydantic import BaseModel, Field, model_serializer
from typing import Any, Optional

from wirecloud.catalogue.crud import get_catalogue_resource_by_id
from wirecloud.commons.auth.schemas import User
from wirecloud.database import Id, DBSession


class WidgetLayout(BaseModel):
    x: Optional[int] = Field(default=None, ge=0)   # None => auto position (GridStack autoPosition)
    y: Optional[int] = Field(default=None, ge=0)
    w: int = Field(default=1, ge=1)
    h: int = Field(default=1, ge=1)
    minimized: bool = False
    titlevisible: bool = True
    fulldragboard: bool = False
    visible: bool = True


class WidgetPermissionsConfig(BaseModel):
    close: Optional[bool] = None
    configure: Optional[bool] = None
    move: Optional[bool] = None
    rename: Optional[bool] = None
    resize: Optional[bool] = None
    minimize: Optional[bool] = None
    upgrade: Optional[bool] = None

    def filtered_dict(self):
        return {k: v for k, v in self.model_dump().items() if v is not None}


class WidgetPermissions(BaseModel):
    editor: Optional[WidgetPermissionsConfig] = None
    viewer: Optional[WidgetPermissionsConfig] = {}

    @model_serializer()
    def serialize(self):
        return {
            "editor": self.editor.filtered_dict() if self.editor else {},
            "viewer": self.viewer.filtered_dict() if self.viewer else {}
        }



class WidgetVariables(BaseModel):
    users: dict[str, Any] = {}


class WidgetInstance(BaseModel):
    id: str
    resource: Id = None
    widget_uri: str = ''
    title: str = ''
    layouts: dict[str, WidgetLayout] = {}   # key = screen size id as a decimal string, e.g. "0"
    read_only: bool = False
    variables: dict[str, WidgetVariables] = {}
    permissions: WidgetPermissions = WidgetPermissions()

    async def set_variable_value(self, db: DBSession, var_name: str, value: Any, user: User):
        resource = await get_catalogue_resource_by_id(db, self.resource)
        if resource is None:
            raise ValueError('Widget not found')

        iwidget_info = resource.get_processed_info(translate=False, process_variables=True)

        vardef = iwidget_info.variables.all[var_name]
        if vardef.secure:
            from wirecloud.platform.workspace.utils import encrypt_value
            value = encrypt_value(value)
        elif vardef.type == 'boolean':
            if isinstance(value, str):
                value = value.strip().lower() == 'true'
            else:
                value = bool(value)
        elif vardef.type == 'number':
            value = float(value)

        current_value = self.variables.get(var_name)
        if isinstance(current_value, WidgetVariables):
            current_value.users = {str(user.id): value}
        elif isinstance(current_value, dict) and "users" in current_value:
            current_value["users"] = {str(user.id): value}
        else:
            self.variables[var_name] = WidgetVariables(users={str(user.id): value})
