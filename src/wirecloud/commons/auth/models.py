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

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any

from wirecloud.commons.auth.schemas import Permission
from wirecloud.database import Id


class DBPlatformPreference(BaseModel):
    name: str
    value: str = ""


class DBLoginAttempt(BaseModel, populate_by_name=True):
    id: str = Field(alias="_id")
    state: str
    nonce: str
    code_verifier: str
    return_to: str
    browser: str
    expires_at: datetime


class Group(BaseModel, populate_by_name=True):
    id: Id = Field(alias="_id")
    name: str
    codename: str

    is_organization: bool = False
    path: list[Id] = []

    group_permissions: list[Permission] = []
    users: list[Id] = []

    @property
    def parent(self) -> Optional[Id]:
        if len(self.path) < 2:
            return None
        return self.path[-2]


class DBUser(BaseModel, populate_by_name=True):
    id: Id = Field(alias="_id")
    password: Optional[str]
    last_login: Optional[datetime]
    is_superuser: bool
    username: str
    first_name: str
    last_name: str
    email: str
    is_staff: bool
    is_active: bool
    date_joined: datetime
    idm_data: dict[str, dict[str, Optional[Any]]] = {}

    user_permissions: list[Permission] = []
    groups: list[Id] = []
    preferences: list[DBPlatformPreference] = []
