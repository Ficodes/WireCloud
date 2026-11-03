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

import json
from typing import Any, Iterable

from fastapi import HTTPException, Request

from wirecloud.mcp.schemas import Page

BLOCKED_PREFERENCES = {"public", "sharelist", "requireauth", "searchable", "permissions", "owner", "creator"}
PRIVATE_FIELDS = {"password", "idm_data", "token_data", "csrf_token", "variable_values", "forced_values"}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        secret = value.get("secure") is True or value.get("hidden") is True
        blocked = PRIVATE_FIELDS
        if secret:
            blocked = blocked | {"value", "default", "users", "defaultValue"}

        result = {key: redact(item) for key, item in value.items() if key not in blocked}
        if secret:
            result["has_value"] = bool(value.get("value"))
        if result.get("value") == "********":
            result.pop("value")
            result["has_value"] = True
        return result

    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def safe_preferences(values: dict[str, str]) -> dict[str, str]:
    if set(values) & BLOCKED_PREFERENCES:
        raise HTTPException(403, "Sharing, authentication, and publishing settings are unavailable through MCP")
    return values


def operation_request(original: Request, body: Any = None, content_type: str = "application/json") -> Request:
    """Call core operations without forwarding the client's cookies or bearer token."""
    scope = dict(original.scope)
    scope["headers"] = [
        (b"accept", b"application/json"),
        (b"content-type", content_type.encode()),
        (b"user-agent", b"WireCloud-MCP/1.0"),
    ]
    scope["query_string"] = b""
    scope["state"] = {"lang": getattr(original.state, "lang", "en")}
    request = Request(scope)
    request._body = json.dumps(body or {}).encode()
    return request


def paginate(items: Iterable[dict[str, Any]], args: Page) -> dict[str, Any]:
    filtered = [item for item in items if args.query.casefold() in json.dumps(item).casefold()]
    end = args.offset + args.limit
    return {
        "items": filtered[args.offset : end],
        "total": len(filtered),
        "next_offset": end if end < len(filtered) else None,
    }
