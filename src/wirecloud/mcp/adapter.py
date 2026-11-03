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

from datetime import datetime, timezone
import logging
from typing import Any, Awaitable, Callable

from bson.errors import InvalidId
from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder

from wirecloud.catalogue.crud import get_catalogue_resource
from wirecloud.catalogue.schemas import CatalogueResource
from wirecloud.commons.utils.operations import invoke_operation
from wirecloud.database import DBSession, Id, commit, rollback
from wirecloud.mcp.schemas import Arguments
from wirecloud.mcp.tools import TOOL_MAP
from wirecloud.mcp.utils import operation_request, redact
from wirecloud.oauth2provider import OAuthPrincipal
from wirecloud.platform.workspace.concurrency import write_preconditions
from wirecloud.platform.workspace.crud import get_workspace_by_id
from wirecloud.platform.workspace.models import Workspace

logger = logging.getLogger(__name__)
CREATES_WORKSPACE = {"create_workspace", "clone_workspace", "import_mashup"}


class WireCloudAdapter:
    def __init__(self, db: DBSession, principal: OAuthPrincipal, request: Request) -> None:
        self.db = db
        self.principal = principal
        self.request = request
        self.user = principal.user

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        tool = TOOL_MAP.get(name)
        if tool is None:
            raise HTTPException(404, "Unknown tool")

        self.principal.require(*tool.scopes)
        args = tool.model.model_validate(arguments)
        conditions = await self.write_conditions(args)
        context = write_preconditions.set(conditions)
        try:
            result = await tool.operation(self, args)
            result = await self.include_timestamp(name, args, conditions, result)
            result = redact(jsonable_encoder(result))
            await commit(self.db)
            self.audit(name, args, "success")
            return result
        except Exception:
            await rollback(self.db)
            self.audit(name, args, "failure")
            raise
        finally:
            write_preconditions.reset(context)

    async def workspace(self, workspace_id: str, edit: bool = False) -> Workspace:
        try:
            workspace = await get_workspace_by_id(self.db, Id(workspace_id))
        except (InvalidId, ValueError, TypeError) as exc:
            raise HTTPException(422, "Invalid workspace ID") from exc
        if workspace is None:
            raise HTTPException(404, "Workspace not found")

        allowed = (
            await workspace.is_editable_by(self.db, self.user)
            if edit
            else await workspace.is_accessible_by(self.db, self.user)
        )
        if not allowed:
            raise HTTPException(403, "Insufficient workspace permissions")
        return workspace

    async def resource(self, identifier: str) -> CatalogueResource:
        resource = await get_catalogue_resource(self.db, *identifier.split("/"))
        if resource is None or not resource.is_available_for(self.user):
            raise HTTPException(404, "Resource not available")
        return resource

    async def call(
        self,
        operation: Callable[..., Awaitable[Any]],
        body: Any = None,
        content_type: str = "application/json",
        **kwargs: Any,
    ) -> Any:
        request = operation_request(self.request, body, content_type)
        return await invoke_operation(operation, self.db, self.user, request, **kwargs)

    async def write_conditions(self, args: Arguments) -> dict[str, datetime]:
        workspace_id = getattr(args, "workspace_id", None)
        if not workspace_id:
            return {}

        workspace = await self.workspace(workspace_id)
        if not hasattr(args, "expected_last_modified"):
            return {}

        expected = args.expected_last_modified
        if expected:
            try:
                timestamp = datetime.fromisoformat(expected.replace("Z", "+00:00"))
            except ValueError as exc:
                raise HTTPException(422, "Invalid modification timestamp") from exc
            if timestamp != workspace.last_modified.replace(tzinfo=timezone.utc):
                raise HTTPException(409, "Workspace changed; read it again before editing")
        return {str(workspace.id): workspace.last_modified}

    async def include_timestamp(
        self, name: str, args: Arguments, conditions: dict[str, datetime], result: Any
    ) -> Any:
        if name in CREATES_WORKSPACE and result.get("id"):
            workspace = await self.workspace(result["id"])
            result["modification_timestamp"] = self.timestamp(workspace)
        if conditions and name != "delete_workspace":
            workspace = await self.workspace(getattr(args, "workspace_id"))
            return {"result": result, "modification_timestamp": self.timestamp(workspace)}
        return result

    @staticmethod
    def timestamp(workspace: Workspace) -> str:
        return workspace.last_modified.replace(tzinfo=timezone.utc).isoformat()

    def audit(self, name: str, args: Arguments, outcome: str) -> None:
        logger.info(
            "MCP operation",
            extra={
                "wirecloud_user": str(self.user.id),
                "oauth_client": self.principal.client_id,
                "oauth_grant": self.principal.grant_id,
                "operation": name,
                "target": getattr(args, "workspace_id", getattr(args, "resource", None)),
                "outcome": outcome,
            },
        )
