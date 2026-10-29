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

from typing import TYPE_CHECKING, Any, Union

from fastapi import HTTPException

from wirecloud.database import Id
from wirecloud.mcp import schemas
from wirecloud.mcp.utils import safe_preferences
from wirecloud.platform.preferences import routes

if TYPE_CHECKING:
    from wirecloud.mcp.adapter import WireCloudAdapter

READ_OPERATIONS = {
    "platform": routes.get_platform_preferences,
    "workspace": routes.get_workspace_preferences,
    "tab": routes.get_tab_preferences,
}
WRITE_OPERATIONS = {
    "platform": routes.create_platform_preferences,
    "workspace": routes.create_workspace_preferences,
    "tab": routes.create_tab_preferences,
}


def target_arguments(args: schemas.Preferences) -> dict[str, Union[Id, str]]:
    if (args.target != "platform" and not args.workspace_id) or (args.target == "tab" and not args.tab_id):
        raise HTTPException(422, "Workspace and tab IDs are required for this preference target")

    identifiers = {}
    if args.target != "platform":
        identifiers["workspace_id"] = Id(args.workspace_id)
    if args.target == "tab":
        identifiers["tab_id"] = args.tab_id
    return identifiers


async def get_preferences(adapter: WireCloudAdapter, args: schemas.Preferences) -> dict[str, Any]:
    return await adapter.call(READ_OPERATIONS[args.target], **target_arguments(args))


async def update_preferences(adapter: WireCloudAdapter, args: schemas.UpdatePreferences) -> dict[str, Any]:
    identifiers = target_arguments(args)
    safe_preferences(args.values)
    return await adapter.call(WRITE_OPERATIONS[args.target], preferences=args.values, **identifiers)
