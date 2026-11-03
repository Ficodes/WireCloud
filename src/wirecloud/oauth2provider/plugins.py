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

from fastapi import FastAPI, Request

from wirecloud.oauth2provider.middleware import AuthorizationCORSMiddleware
from wirecloud.oauth2provider.routes import metadata_router, oauth_error_handler, router
from wirecloud.oauth2provider.service import OAuthError
from wirecloud.oauth2provider.urls import patterns
from wirecloud.oauth2provider.validators import validate_oauth_settings
from wirecloud.platform.plugins import AjaxEndpoint, WirecloudPlugin


class OAuth2ProviderPlugin(WirecloudPlugin):
    features = {"OAuth2Provider": "1.0"}
    urls = patterns

    def __init__(self, app: Optional[FastAPI]) -> None:
        super().__init__(app)
        if app is None:
            return

        app.include_router(router, prefix="/oauth2", tags=["OAuth2"])
        app.include_router(metadata_router, tags=["OAuth2"])
        app.add_exception_handler(OAuthError, oauth_error_handler)
        app.add_middleware(AuthorizationCORSMiddleware)

    def get_ajax_endpoints(self, view: str, request: Request) -> tuple[AjaxEndpoint, ...]:
        if view not in ("classic", "smartphone"):
            return ()

        prefix = (request.scope.get("root_path") or "").rstrip("/")
        connections_url = prefix + self.urls["oauth2provider.connections"].urlpattern
        return (AjaxEndpoint(id="OAUTH2_CONNECTIONS", url=connections_url),)

    def get_config_validators(self) -> tuple[Callable, ...]:
        return (validate_oauth_settings,)
