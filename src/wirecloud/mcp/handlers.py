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

import inspect
import json
from typing import Any, Awaitable, Callable

from fastapi import HTTPException
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from wirecloud.commons.utils.http import NotFound, PermissionDenied
from wirecloud.mcp.adapter import WireCloudAdapter
from wirecloud.mcp.context import call_context
from wirecloud.mcp.tools import Tool


def make_handler(spec: Tool) -> Callable[..., Awaitable[Any]]:
    """Expose the closed input model as a signature understood by the MCP SDK."""

    async def handler(**arguments: Any) -> Any:
        context = call_context.get()
        adapter = WireCloudAdapter(context.db, context.principal, context.request)

        try:
            return await adapter.execute(spec.name, arguments)
        except HTTPException as exc:
            raise tool_error(exc.status_code, exc.detail) from exc
        except ValidationError as exc:
            errors = exc.errors(include_input=False, include_context=False)
            raise tool_error(422, errors) from exc
        except NotFound as exc:
            raise tool_error(404, str(exc)) from exc
        except PermissionDenied as exc:
            raise tool_error(403, str(exc)) from exc
        except (ValueError, TypeError) as exc:
            raise tool_error(422, str(exc)) from exc
        except OSError as exc:
            raise tool_error(500, "Component storage is unavailable") from exc

    parameters = []
    annotations = {"return": dict[str, Any]}
    for name, field in spec.model.model_fields.items():
        default = inspect.Parameter.empty if field.is_required() else field.get_default(call_default_factory=True)
        parameters.append(
            inspect.Parameter(
                name,
                inspect.Parameter.KEYWORD_ONLY,
                annotation=field.annotation,
                default=default,
            )
        )
        annotations[name] = field.annotation

    handler.__name__ = spec.name
    handler.__annotations__ = annotations
    handler.__signature__ = inspect.Signature(parameters, return_annotation=dict[str, Any])
    return handler


def tool_error(status: int, detail: Any) -> ToolError:
    return ToolError(json.dumps({"status": status, "error": detail}))
