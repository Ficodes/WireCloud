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

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse, Response, RedirectResponse
from typing import Optional
from urllib.parse import quote_plus
import os
import jinja2

from wirecloud import settings
from wirecloud.commons.auth.schemas import UserAll
from wirecloud.commons.auth.utils import UserDepNoCSRF
from wirecloud.commons.templates.tags import get_wirecloud_bootstrap, get_translation, get_static_path, \
    get_url_from_view
from wirecloud.commons.utils.http import NotFound, get_absolute_reverse_url, build_error_response
from wirecloud.commons.utils.theme import get_theme_static_path, get_available_themes, get_jinja2_templates
from wirecloud.database import DBSession, DBDep
from wirecloud.platform import docs
from wirecloud import docs as root_docs
from wirecloud.platform.plugins import get_template_context
from wirecloud.platform.utils import get_current_view, get_current_theme
from wirecloud.platform.workspace.crud import get_workspace_by_username_and_name

router = APIRouter()


async def render_workspace_view(db: DBSession, request: Request, user: Optional[UserAll], owner: str, workspace: str) -> Response:
    login_url = get_absolute_reverse_url("login", request)
    login_url += ('&' if '?' in login_url else '?') + f"return_to={quote_plus(request.url.path + '?' + request.url.query)}"

    if settings.ALLOW_ANONYMOUS_ACCESS is False and user is None:
        return RedirectResponse(login_url)

    workspace_db = await get_workspace_by_username_and_name(db, owner, workspace)

    if workspace_db is None:
        raise NotFound("Workspace not found")

    if user is not None and not await workspace_db.is_accessible_by(db, user):
        return build_error_response(request, 403, "You do not have permission to access this workspace.")
    elif user is None and not workspace_db.public:
        return RedirectResponse(login_url)

    return render_wirecloud(request, title=workspace_db.title, description=workspace_db.description)


async def auto_select_workspace(db: DBSession, request: Request, user: Optional[UserAll], mode: Optional[str] = None) -> Response:
    if user is not None:
        url = get_absolute_reverse_url("wirecloud.workspace_view", request, owner="wirecloud", name="home")

        parameters = {}
        if mode:
            parameters['mode'] = mode

        if 'themeactive' in request.query_params:
            parameters['themeactive'] = request.query_params['themeactive']

        if len(parameters) > 0:
            url += "?" + "&".join([f"{k}={quote_plus(v)}" for k, v in parameters.items()])

        return RedirectResponse(url)
    else:
        return await render_workspace_view(db, request, user, "wirecloud", "landing")

@router.get(
    "/",
    response_class=HTMLResponse,
    summary=docs.get_root_page_summary,
    description=docs.get_root_page_description,
    response_description=docs.get_root_page_response_description,
    responses={
        404: root_docs.generate_not_found_response_openapi_description(
            docs.get_root_page_not_found_response_description),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.get_root_page_permission_denied_response_description, "You do not have permission to access this workspace.")
    }
)
async def render_root_page(db: DBDep, request: Request, user: UserDepNoCSRF):
    mode = request.query_params.get("mode", None)
    return await auto_select_workspace(db, request, user, mode)


@router.get(
    "/workspace/{owner}/{name}",
    response_class=HTMLResponse,
    summary=docs.get_workspace_view_summary,
    description=docs.get_workspace_view_description,
    response_description=docs.get_workspace_view_response_description,
    responses={
        404: root_docs.generate_not_found_response_openapi_description(
            docs.get_workspace_view_not_found_response_description),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.get_workspace_view_permission_denied_response_description, "You do not have permission to access this workspace.")
    }
)
async def render_workspace_page(db: DBDep, request: Request, user: UserDepNoCSRF, owner: str, name: str):
    return await render_workspace_view(db, request, user, owner, name)


@router.get(
    "/static/{path:path}",
    response_class=FileResponse,
    summary=docs.get_static_file_summary,
    description=docs.get_static_file_description,
    response_description=docs.get_static_file_response_description,
    responses={
        404: root_docs.generate_error_response_openapi_description(
            docs.get_static_file_not_found_response_description,
            "File not found"),
        422: root_docs.generate_validation_error_response_openapi_description(
            docs.get_static_file_validation_error_response_description)
    }
)
def serve_static(path: str, themeactive: str = settings.THEME_ACTIVE, view: str = "classic", context: str = "platform"):
    if path == "css/cache.css":
        try:
            return FileResponse(get_theme_static_path(themeactive, f"css/{themeactive}_{view}_{context}.css"))
        except NotFound:
            raise NotFound(f"File not found. If you're an admin, compile CSS by running npm run build:css.")
    elif path == "js/cache.js":
        try:
            return FileResponse(get_theme_static_path(themeactive, f"js/main-{themeactive}-{view}.js"))
        except NotFound:
            raise NotFound(f"File not found. If you're an admin, compile JS by running npm run build:js.")

    return FileResponse(get_theme_static_path(themeactive, path))


def render_wirecloud(request: Request, view: Optional[str] = None, page: Optional[str] = None, title: str = "", description: str = "", extra_context: dict = None):
    from wirecloud.platform.core.plugins import get_version_hash

    templates = get_jinja2_templates(get_current_theme(request))
    if view is None:
        view = get_current_view(request)

    context = get_template_context(request)

    context.update({
        "title": title,
        "description": description,
        "uri": request.url.scheme + "://" + request.url.netloc + request.url.path + "?" + request.url.query,
        "LANGUAGE_CODE": request.state.lang,
        'WIRECLOUD_VERSION_HASH': get_version_hash(),
        "THEME": get_current_theme(request),
        "VIEW_MODE": view,
        "LANG": request.state.lang,
        'environ': os.environ,
        'request': request,
        'request_path': request.url.path,

        "trans": lambda text, **kwargs: get_translation(get_current_theme(request), request.state.lang, text, **kwargs),
        "static": lambda path: get_static_path(get_current_theme(request), view, request, path),
        "url": lambda viewname, **kwargs: get_url_from_view(request, viewname, **kwargs)
    })

    context["wirecloud_bootstrap"] = lambda view_name, plain=False: get_wirecloud_bootstrap(context,
                                                                                            get_available_themes(request.state.lang),
                                                                                            view_name, plain)

    if extra_context:
        context.update(extra_context)

    try:
        path = f"wirecloud/views/{view}.html" if page is None else f"{page}.html"
        return templates.TemplateResponse(
            request=request, name=path, context=context,
        )
    except jinja2.exceptions.TemplateNotFound:
        if page is not None:
            raise NotFound(f"Template {page} not found")

        view = get_current_view(request, True)
        context["VIEW_MODE"] = view

        return templates.TemplateResponse(
            request=request, name=f"wirecloud/views/{view}.html", context=context,
        )
