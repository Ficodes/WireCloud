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

from typing import Annotated, Any, Optional

from pydantic import BaseModel, Field, StringConstraints

from wirecloud.platform.iwidget.models import WidgetPermissions, WidgetLayout, WidgetVariables

ScreenSizeKey = Annotated[str, StringConstraints(pattern=r'^\d+$')]


class WidgetLayoutUpdate(BaseModel):          # partial update, every field optional
    x: Optional[int] = Field(default=None, ge=0)
    y: Optional[int] = Field(default=None, ge=0)
    w: Optional[int] = Field(default=None, ge=1)
    h: Optional[int] = Field(default=None, ge=1)
    minimized: Optional[bool] = None
    titlevisible: Optional[bool] = None
    fulldragboard: Optional[bool] = None
    visible: Optional[bool] = None
    dock: Optional[str] = None
    dock_mode: Optional[str] = None
    dock_open: Optional[bool] = None


class WidgetInstanceDataCreate(BaseModel):
    title: str
    widget: str                                 # vendor/name/version
    layouts: dict[ScreenSizeKey, WidgetLayout] = {}
    read_only: bool = False
    permissions: WidgetPermissions = WidgetPermissions()
    variable_values: Optional[dict[str, WidgetVariables]] = None


class WidgetInstanceDataPreference(BaseModel):
    name: str
    secure: bool
    readonly: bool
    hidden: bool
    value: Any


WidgetInstanceDataProperty = WidgetInstanceDataPreference


class WidgetInstanceData(WidgetInstanceDataCreate):   # unchanged apart from removed fields
    id: str = ''
    preferences: dict[str, WidgetInstanceDataPreference] = {}
    properties: dict[str, WidgetInstanceDataProperty] = {}


class WidgetInstanceDataUpdate(BaseModel):
    id: Optional[str] = None
    tab: Optional[str] = None
    title: Optional[str] = None
    widget: Optional[str] = None
    move: Optional[bool] = None                 # viewer "move" permission toggle (unchanged behaviour)
    layouts: Optional[dict[ScreenSizeKey, Optional[WidgetLayoutUpdate]]] = None
