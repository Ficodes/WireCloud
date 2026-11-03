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

from pydantic import BaseModel
from typing import Any, Optional, Union
from enum import Enum


class SelectEntry(BaseModel):
    value: str
    label: str


class PreferenceKey(BaseModel):
    name: str
    label: str
    type: str
    hidden: bool = False
    description: str = ''
    initialEntries: Optional[list[SelectEntry]] = None
    defaultValue: Any = None
    inheritByDefault: bool = False


class TabPreferenceKey(PreferenceKey):
    inheritable: bool = True
    inheritByDefault: bool = True


class PlatformPreferenceCreateValue(BaseModel):
    value: str


class PlatformPreferenceCreate(BaseModel):
    preferences: dict[str, Union[str, PlatformPreferenceCreateValue]]


class WorkspacePreference(BaseModel):
    inherit: bool = False
    value: Optional[str] = None


class WorkspacePreferenceWithName(WorkspacePreference):
    name: str

TabPreference = WorkspacePreference


class ShareListEnum(Enum):
    user = 'user'
    group = 'group'
    organization = 'organization'


class ShareListPreference(BaseModel, use_enum_values=True):
    type: ShareListEnum = ShareListEnum.user
    name: str
    value: Optional[str] = None
