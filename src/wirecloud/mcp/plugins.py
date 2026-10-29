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

from typing import Callable, Optional
from urllib.parse import urlsplit

from fastapi import FastAPI

from wirecloud import settings
from wirecloud.mcp.validators import validate_mcp_settings
from wirecloud.oauth2provider import OAuthResource, register_resource
from wirecloud.platform.plugins import ImproperlyConfigured, WirecloudPlugin


class WirecloudMCPPlugin(WirecloudPlugin):
    features = {"MCP": "1.0.0"}

    def __init__(self, app: Optional[FastAPI]) -> None:
        super().__init__(app)
        self.server = None
        if app is None:
            return

        # Builds and ordinary installations must not import the optional SDK.
        try:
            from wirecloud.mcp.server import create_server
            from wirecloud.mcp.routes import create_router
            from wirecloud.mcp.middleware import MCPCORSMiddleware
            from wirecloud.mcp.tools import SCOPES
        except ImportError as exc:
            raise ImproperlyConfigured("Install wirecloud[mcp] to enable the MCP plugin") from exc

        audience = settings.MCP_PUBLIC_URL.rstrip("/")
        parsed = urlsplit(audience)
        origins = [f"{parsed.scheme}://{parsed.netloc}", *getattr(settings, "MCP_ALLOWED_ORIGINS", [])]

        register_resource(app, OAuthResource(audience, SCOPES, "WireCloud MCP", tuple(SCOPES)))
        self.server = create_server()
        app.state.mcp_server = self.server
        app.state.mcp_audience = audience
        app.add_middleware(MCPCORSMiddleware, origins=origins)
        app.include_router(create_router(app, self.server, audience, origins), tags=["MCP"])

    def get_config_validators(self) -> tuple[Callable, ...]:
        return (validate_mcp_settings,)
