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

from contextvars import ContextVar
from dataclasses import dataclass

from fastapi import Request

from wirecloud.database import DBSession
from wirecloud.oauth2provider import OAuthPrincipal


@dataclass(frozen=True)
class MCPCallContext:
    db: DBSession
    principal: OAuthPrincipal
    request: Request


call_context: ContextVar[MCPCallContext] = ContextVar("wirecloud_mcp_call")
