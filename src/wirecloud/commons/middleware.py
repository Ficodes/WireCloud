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

from fastapi import Request, FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.datastructures import Headers, QueryParams
from starlette.requests import cookie_parser

from typing import Optional
from wirecloud import settings

DEFAULT_LANGUAGE = getattr(settings, "DEFAULT_LANGUAGE", "en")
AVAILABLE_LANGUAGES = [lang[0] for lang in settings.LANGUAGES]


def get_language_from_req_data(accept_lang_header: Optional[str], lang_param: Optional[str], cookie: Optional[str]) -> str:
    if accept_lang_header is None:
        browser_language = DEFAULT_LANGUAGE
    else:
        # Parse the header and get a list of languages sorted by priority
        languages = []
        for lang in accept_lang_header.split(","):
            parts = lang.strip().split(";")
            lang = parts[0].strip()
            quality = 1.0
            if len(parts) == 2:
                if parts[1].strip().startswith("q="):
                    try:
                        quality = float(parts[1].strip()[2:])
                    except ValueError:
                        pass
            if lang in AVAILABLE_LANGUAGES:
                languages.append((lang, quality))

        # Sort the languages by quality
        languages.sort(key=lambda x: x[1], reverse=True)

        language = None
        for lang, _ in languages:
            if lang in AVAILABLE_LANGUAGES:
                language = lang
                break

        browser_language = language if language is not None else DEFAULT_LANGUAGE

    if lang_param in AVAILABLE_LANGUAGES:
        language = lang_param
    elif cookie in AVAILABLE_LANGUAGES:
        language = cookie
    else:
        language = browser_language

    return language


class LocaleMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # Get the language from the request
        accept_lang_header = request.headers.get("Accept-Language")
        request.state.lang = get_language_from_req_data(accept_lang_header, request.query_params.get("lang"), request.cookies.get("lang"))

        # Call the next middleware
        response = await call_next(request)

        # Add a Content-Language header to the response
        response.headers["Content-Language"] = request.state.lang

        return response


class LocaleWSMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "websocket":
            return await self.app(scope, receive, send)

        headers = Headers(scope=scope)
        query_params = QueryParams(scope["query_string"])
        cookies: dict[str, str] = {}
        cookie_header = headers.get("cookie")

        if cookie_header:
            cookies = cookie_parser(cookie_header)

        language = get_language_from_req_data(headers.get("accept-language"), query_params.get("lang"), cookies.get("lang"))
        scope.setdefault("state", {})["lang"] = language

        await self.app(scope, receive, send)
        return None


class ContentTypeUTF8Middleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if "Content-Type" not in response.headers:
            return response

        if "charset" in response.headers["Content-Type"]:
            return response

        response.headers["Content-Type"] += "; charset=utf-8"

        return response


def install_all_middlewares(app: FastAPI) -> None:
    app.add_middleware(LocaleMiddleware)
    app.add_middleware(LocaleWSMiddleware)
    app.add_middleware(GZipMiddleware)
    app.add_middleware(ContentTypeUTF8Middleware)