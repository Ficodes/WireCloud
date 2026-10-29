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

from typing import Any, Mapping, Optional
from urllib.parse import quote, urlencode, urlsplit

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import select_autoescape

from wirecloud import settings


def page_headers(form_redirect_uri: Optional[str] = None) -> dict[str, str]:
    form_actions = "'self'"
    if form_redirect_uri is not None:
        callback = urlsplit(form_redirect_uri)
        form_actions += " " + quote(f"{callback.scheme}://{callback.netloc}", safe=":/[]")
    return {
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'none'; script-src 'self'; script-src-attr 'none'; "
        "style-src 'self'; img-src 'self'; font-src 'self'; "
        f"form-action {form_actions}; frame-ancestors 'none'; base-uri 'none'",
    }


def render_page(
    request: Request, template: str, context: Mapping[str, Any], *, form_redirect_uri: Optional[str] = None
) -> HTMLResponse:
    from wirecloud.commons.templates.tags import get_translation
    from wirecloud.commons.utils.theme import get_jinja2_templates
    from wirecloud.platform.plugins import get_template_context
    from wirecloud.platform.utils import get_current_theme

    theme = get_current_theme(request)
    lang = getattr(request.state, "lang", settings.DEFAULT_LANGUAGE)
    root = request.scope.get("root_path", "").rstrip("/")

    def translate(text: str) -> str:
        return get_translation(theme, lang, text)

    def static_url(asset: str, view: str = "classic") -> str:
        return root + "/static/" + asset + "?" + urlencode({"themeactive": theme, "view": view})

    values = get_template_context(request)
    values.update(
        {
            "request": request,
            "LANGUAGE_CODE": lang,
            "THEME": theme,
            "home_url": root + "/",
            "trans": translate,
            "static": static_url,
        }
    )
    values.update(context)
    # Limit autoescaping changes to OAuth pages; existing widget/theme rendering is unaffected.
    environment = get_jinja2_templates(theme).env.overlay(autoescape=select_autoescape(["html", "xml"]))
    content = environment.get_template(f"wirecloud/oauth2provider/{template}.html").render(values)
    return HTMLResponse(content, headers=page_headers(form_redirect_uri))
