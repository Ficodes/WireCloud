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
from typing import Collection, Optional, Sequence

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from wirecloud.database import get_session
from wirecloud.mcp.context import MCPCallContext, call_context
from wirecloud.mcp.tools import SCOPES, TOOL_MAP
from wirecloud.oauth2provider import OAuthPrincipal, bearer_token, resource_metadata_url, verify_access_token

REQUEST_BODY_LIMIT = 4 * 1024 * 1024


class MCPCORSMiddleware:
    """Apply the same origin policy to MCP calls and binary package uploads."""

    def __init__(self, app: ASGIApp, origins: Sequence[str]) -> None:
        self.app = app
        self.cors = CORSMiddleware(
            app,
            allow_origins=origins,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["*"],
            expose_headers=["WWW-Authenticate", "Mcp-Session-Id"],
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        prefix = scope.get("root_path", "").rstrip("/")
        if prefix and path.startswith(prefix + "/"):
            path = path[len(prefix) :]

        if scope["type"] == "http" and path in ("/mcp", "/mcp/uploads"):
            return await self.cors(scope, receive, send)
        return await self.app(scope, receive, send)


class MCPAuthenticationMiddleware:
    """Authenticate before invoking the SDK and hold identity for the whole call."""

    def __init__(self, app: ASGIApp, application: FastAPI, audience: str) -> None:
        self.app = app
        self.application = application
        self.audience = audience

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request = Request(scope, receive=receive)
        provider = self.application.dependency_overrides.get(get_session, get_session)
        async for db in provider():
            token = bearer_token(request)
            principal = await verify_access_token(db, token, self.audience) if token else None
            if principal is None:
                response = authorization_error(self.audience, "invalid_token", tuple(SCOPES))
                return await response(scope, receive, send)

            if scope["method"] == "POST":
                try:
                    body = await read_request_body(receive)
                except HTTPException:
                    response = JSONResponse({"error": "request_too_large"}, status_code=413)
                    return await response(scope, receive, send)
                if body is None:
                    return  # The caller disconnected before sending the body.

                # OAuth clients need HTTP challenges to request additional consent.
                response = scope_challenge(body, principal, self.audience)
                if response is not None:
                    return await response(scope, receive, send)
                receive = ReplayBody(body, receive)

            context = call_context.set(MCPCallContext(db, principal, request))
            try:
                await self.app(scope, receive, send)
            finally:
                call_context.reset(context)


async def read_request_body(receive: Receive) -> Optional[bytes]:
    """Read a bounded ASGI body; leave malformed JSON for the SDK to report."""
    body = bytearray()
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return None
        body.extend(message.get("body", b""))
        if len(body) > REQUEST_BODY_LIMIT:
            raise HTTPException(413)
        if not message.get("more_body", False):
            return bytes(body)


class ReplayBody:
    """Let the SDK read the inspected body, then forward later ASGI messages."""

    def __init__(self, body: bytes, receive: Receive) -> None:
        self.body = body
        self.receive = receive
        self.sent = False

    async def __call__(self) -> Message:
        if not self.sent:
            self.sent = True
            return {"type": "http.request", "body": self.body, "more_body": False}
        return await self.receive()


def scope_challenge(body: bytes, principal: OAuthPrincipal, audience: str) -> Optional[JSONResponse]:
    try:
        message = json.loads(body)
    except ValueError:
        return None
    if not isinstance(message, dict) or message.get("method") != "tools/call":
        return None

    parameters = message.get("params", {})
    if not isinstance(parameters, dict) or not isinstance(parameters.get("name"), str):
        return None
    tool = TOOL_MAP.get(parameters["name"])
    if tool is None or set(tool.scopes).issubset(principal.scopes):
        return None
    return authorization_error(audience, "insufficient_scope", tool.scopes)


def authorization_error(audience: str, error: str, scopes: Collection[str]) -> JSONResponse:
    challenge = f'Bearer resource_metadata="{resource_metadata_url(audience)}", ' f'scope="{" ".join(scopes)}"'
    payload = {"error": error}
    status = 401
    if error == "insufficient_scope":
        challenge += ', error="insufficient_scope"'
        payload["required_scopes"] = list(scopes)
        status = 403
    return JSONResponse(
        payload,
        status_code=status,
        headers={"WWW-Authenticate": challenge, "Cache-Control": "no-store"},
    )
