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

from typing import Any, Optional, Union

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import CallToolResult, InputRequiredResult, Tool, ToolAnnotations
from pydantic import ValidationError

from wirecloud.mcp import docs
from wirecloud.mcp.handlers import make_handler, tool_error
from wirecloud.mcp.tools import READ, TOOLS, TOOL_MAP

SERVER_INSTRUCTIONS = docs.server_instructions


def create_server() -> WireCloudMCPServer:
    server = WireCloudMCPServer("WireCloud", version="1.0.0", instructions=SERVER_INSTRUCTIONS)
    for tool in TOOLS:
        register = server.tool(
            name=tool.name,
            description=tool.description,
            structured_output=True,
            annotations=ToolAnnotations(
                readOnlyHint=tool.scopes == (READ,),
                destructiveHint=tool.destructive,
                openWorldHint=tool.name == "install_resource",
            ),
        )
        register(make_handler(tool))
    return server


class WireCloudMCPServer(MCPServer):
    """Validate original arguments before the SDK discards unknown fields."""

    async def list_tools(self) -> list[Tool]:
        tools = await super().list_tools()
        return [
            (
                tool.model_copy(update={"input_schema": TOOL_MAP[tool.name].model.model_json_schema()})
                if tool.name in TOOL_MAP
                else tool
            )
            for tool in tools
        ]

    async def call_tool(
        self, name: str, arguments: dict[str, Any], context: Optional[Context[Any, Any]]
    ) -> Union[CallToolResult, InputRequiredResult]:
        spec = TOOL_MAP.get(name)
        if spec is not None:
            try:
                spec.model.model_validate(arguments)
            except ValidationError as exc:
                errors = exc.errors(include_input=False, include_context=False)
                raise tool_error(422, errors) from exc
        return await super().call_tool(name, arguments, context)
