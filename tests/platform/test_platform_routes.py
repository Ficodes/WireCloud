# -*- coding: utf-8 -*-

import jinja2
import pytest
from fastapi.responses import RedirectResponse
from starlette.requests import Request

from wirecloud.commons.utils.http import NotFound
from wirecloud import main as main_module
from wirecloud.platform import routes


async def _noop_close():
    return None


main_module.close = _noop_close


def _request(path="/workspace/wirecloud/home", query=""):
    req = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "server": ("wirecloud.example.org", 443),
            "path": path,
            "query_string": query.encode("utf-8"),
            "headers": [(b"host", b"wirecloud.example.org"), (b"user-agent", b"Mozilla/5.0")],
        }
    )
    req.state.lang = "en"
    return req


class _FakeWorkspace:
    def __init__(self, public=True, can_access=True):
        self.public = public
        self.title = "Workspace title"
        self.description = "Workspace description"
        self._can_access = can_access

    async def is_accessible_by(self, _db, _user):
        return self._can_access


async def test_route_wrappers_use_app_client(app_client, monkeypatch):
    captured = {}

    async def _auto_select_workspace(db, request, user, mode):
        captured["root"] = (db, request.url.path, user, mode)
        return "root-ok"

    async def _render_workspace_view(db, request, user, owner, name):
        captured["workspace"] = (db, request.url.path, user, owner, name)
        return "workspace-ok"

    monkeypatch.setattr(routes, "auto_select_workspace", _auto_select_workspace)
    monkeypatch.setattr(routes, "render_workspace_view", _render_workspace_view)

    root = await app_client.get("/?mode=embedded")
    workspace = await app_client.get("/workspace/alice/main")

    assert root.status_code == 200
    assert root.text == "root-ok"
    assert workspace.status_code == 200
    assert workspace.text == "workspace-ok"
    assert captured["root"][1:] == ("/", None, "embedded")
    assert captured["workspace"][1:] == ("/workspace/alice/main", None, "alice", "main")


async def test_render_workspace_view_login_redirects_and_errors(monkeypatch, db_session):
    request = _request(query="x=1")
    monkeypatch.setattr(routes, "get_absolute_reverse_url", lambda *_args, **_kwargs: "https://wc/login")
    monkeypatch.setattr(routes.settings, "ALLOW_ANONYMOUS_ACCESS", False)
    monkeypatch.setattr(routes.settings, "OID_CONNECT_ENABLED", False)

    redirected = await routes.render_workspace_view(db_session, request, None, "wirecloud", "home")
    assert isinstance(redirected, RedirectResponse)
    assert "return_to=" in redirected.headers["location"]

    monkeypatch.setattr(routes.settings, "OID_CONNECT_ENABLED", True)
    redirected_oidc = await routes.render_workspace_view(db_session, request, None, "wirecloud", "home")
    assert "return_to=" in redirected_oidc.headers["location"]

    monkeypatch.setattr(routes, "get_absolute_reverse_url", lambda *_args, **_kwargs: "https://wc/login?x=1")
    redirected_oidc_with_query = await routes.render_workspace_view(db_session, request, None, "wirecloud", "home")
    assert "&return_to=" in redirected_oidc_with_query.headers["location"]

    monkeypatch.setattr(routes.settings, "ALLOW_ANONYMOUS_ACCESS", True)

    async def _none_workspace(*_args, **_kwargs):
        return None

    monkeypatch.setattr(routes, "get_workspace_by_username_and_name", _none_workspace)
    with pytest.raises(NotFound, match="Workspace not found"):
        await routes.render_workspace_view(db_session, request, object(), "wirecloud", "home")


async def test_render_workspace_view_permissions_and_success(monkeypatch, db_session):
    request = _request()
    monkeypatch.setattr(routes, "get_absolute_reverse_url", lambda *_args, **_kwargs: "https://wc/login")
    monkeypatch.setattr(routes.settings, "ALLOW_ANONYMOUS_ACCESS", True)
    monkeypatch.setattr(routes.settings, "OID_CONNECT_ENABLED", False)

    async def _private_ws(*_args, **_kwargs):
        return _FakeWorkspace(public=False, can_access=True)

    monkeypatch.setattr(routes, "get_workspace_by_username_and_name", _private_ws)
    anon_private = await routes.render_workspace_view(db_session, request, None, "wirecloud", "home")
    assert isinstance(anon_private, RedirectResponse)

    async def _forbidden_ws(*_args, **_kwargs):
        return _FakeWorkspace(public=True, can_access=False)

    captured = {}

    def _error_response(_request, status, message):
        captured["status"] = status
        captured["message"] = message
        return {"status": status, "message": message}

    monkeypatch.setattr(routes, "get_workspace_by_username_and_name", _forbidden_ws)
    monkeypatch.setattr(routes, "build_error_response", _error_response)
    denied = await routes.render_workspace_view(db_session, request, object(), "wirecloud", "home")
    assert denied["status"] == 403
    assert "permission" in captured["message"].lower()

    async def _allowed_ws(*_args, **_kwargs):
        return _FakeWorkspace(public=True, can_access=True)

    monkeypatch.setattr(routes, "get_workspace_by_username_and_name", _allowed_ws)
    monkeypatch.setattr(routes, "render_wirecloud", lambda _request, **kwargs: {"title": kwargs["title"], "description": kwargs["description"]})
    rendered = await routes.render_workspace_view(db_session, request, object(), "wirecloud", "home")
    assert rendered["title"] == "Workspace title"


async def test_auto_select_workspace_paths(monkeypatch, db_session):
    request = _request(path="/", query="themeactive=wirecloud.defaulttheme")
    monkeypatch.setattr(routes, "get_absolute_reverse_url", lambda *_args, **_kwargs: "https://wc/workspace/wirecloud/home")

    logged = await routes.auto_select_workspace(db_session, request, object(), mode="embedded")
    assert isinstance(logged, RedirectResponse)
    assert "mode=embedded" in logged.headers["location"]
    assert "themeactive=wirecloud.defaulttheme" in logged.headers["location"]

    logged_without_params = await routes.auto_select_workspace(db_session, _request(path="/"), object(), mode=None)
    assert logged_without_params.headers["location"] == "https://wc/workspace/wirecloud/home"

    async def _render_workspace_view(_db, _request, _user, owner, workspace):
        return {"owner": owner, "workspace": workspace}

    monkeypatch.setattr(routes, "render_workspace_view", _render_workspace_view)
    anon = await routes.auto_select_workspace(db_session, request, None, mode=None)
    assert anon == {"owner": "wirecloud", "workspace": "landing"}


def test_serve_static_cache_and_default(monkeypatch):
    monkeypatch.setattr(routes, "get_theme_static_path", lambda theme, path: f"/themes/{theme}/{path}")

    css = routes.serve_static("css/cache.css", themeactive="wirecloud.defaulttheme", view="classic", context="platform")
    assert "wirecloud.defaulttheme_classic_platform.css" in str(css.path)

    js = routes.serve_static("js/cache.js", themeactive="wirecloud.defaulttheme", view="smartphone", context="platform")
    assert "main-wirecloud.defaulttheme-smartphone.js" in str(js.path)

    image = routes.serve_static("img/logo.png", themeactive="wirecloud.defaulttheme")
    assert str(image.path).endswith("/themes/wirecloud.defaulttheme/img/logo.png")

    def _raise_not_found(_theme, path):
        raise NotFound(path)

    monkeypatch.setattr(routes, "get_theme_static_path", _raise_not_found)
    with pytest.raises(NotFound, match="compile CSS"):
        routes.serve_static("css/cache.css")
    with pytest.raises(NotFound, match="compile JS"):
        routes.serve_static("js/cache.js")


def test_render_wirecloud_context_and_fallback(monkeypatch):
    class _Templates:
        def TemplateResponse(self, request, name, context):
            if name == "wirecloud/views/classic.html":
                raise jinja2.exceptions.TemplateNotFound(name)
            return {"name": name, "context": context}

    request = _request(path="/workspace/wirecloud/home", query="a=1")

    monkeypatch.setattr(routes, "get_jinja2_templates", lambda _theme: _Templates())
    monkeypatch.setattr(routes, "get_current_theme", lambda _request: "wirecloud.defaulttheme")
    monkeypatch.setattr(routes, "get_current_view", lambda _request, ignore_query=False: "embedded" if ignore_query else "classic")
    monkeypatch.setattr(routes, "get_template_context", lambda _request: {"base": "value"})
    monkeypatch.setattr(routes, "get_translation", lambda *_args, **_kwargs: "translated")
    monkeypatch.setattr(routes, "get_static_path", lambda *_args, **_kwargs: "/static/x")
    monkeypatch.setattr(routes, "get_url_from_view", lambda *_args, **_kwargs: "/url/x")
    monkeypatch.setattr(routes, "get_wirecloud_bootstrap", lambda *_args, **_kwargs: "bootstrap")
    monkeypatch.setattr(routes, "get_available_themes", lambda _lang: ["wirecloud.defaulttheme"])
    monkeypatch.setattr("wirecloud.platform.core.plugins.get_version_hash", lambda: "vhash")

    rendered = routes.render_wirecloud(request, title="Title", description="Desc", extra_context={"extra": "x"})
    assert rendered["name"] == "wirecloud/views/embedded.html"
    assert rendered["context"]["title"] == "Title"
    assert rendered["context"]["description"] == "Desc"
    assert rendered["context"]["LANG"] == "en"
    assert rendered["context"]["WIRECLOUD_VERSION_HASH"] == "vhash"
    assert rendered["context"]["extra"] == "x"

    direct = routes.render_wirecloud(request, page="wirecloud/custom")
    assert direct["name"] == "wirecloud/custom.html"


def test_render_wirecloud_page_not_found(monkeypatch):
    class _Templates:
        def TemplateResponse(self, request, name, context):
            raise jinja2.exceptions.TemplateNotFound(name)

    request = _request(path="/workspace/wirecloud/home", query="a=1")
    monkeypatch.setattr(routes, "get_jinja2_templates", lambda _theme: _Templates())
    monkeypatch.setattr(routes, "get_current_theme", lambda _request: "wirecloud.defaulttheme")
    monkeypatch.setattr(routes, "get_current_view", lambda _request, ignore_query=False: "classic")
    monkeypatch.setattr(routes, "get_template_context", lambda _request: {})
    monkeypatch.setattr(routes, "get_translation", lambda *_args, **_kwargs: "translated")
    monkeypatch.setattr(routes, "get_static_path", lambda *_args, **_kwargs: "/static/x")
    monkeypatch.setattr(routes, "get_url_from_view", lambda *_args, **_kwargs: "/url/x")
    monkeypatch.setattr(routes, "get_wirecloud_bootstrap", lambda *_args, **_kwargs: "bootstrap")
    monkeypatch.setattr(routes, "get_available_themes", lambda _lang: ["wirecloud.defaulttheme"])
    monkeypatch.setattr("wirecloud.platform.core.plugins.get_version_hash", lambda: "vhash")

    with pytest.raises(NotFound, match="Template wirecloud/missing not found"):
        routes.render_wirecloud(request, page="wirecloud/missing")


def test_render_wirecloud_with_explicit_view(monkeypatch):
    class _Templates:
        def TemplateResponse(self, request, name, context):
            return {"name": name, "context": context}

    request = _request(path="/workspace/wirecloud/home", query="a=1")
    monkeypatch.setattr(routes, "get_jinja2_templates", lambda _theme: _Templates())
    monkeypatch.setattr(routes, "get_current_theme", lambda _request: "wirecloud.defaulttheme")
    monkeypatch.setattr(routes, "get_current_view", lambda _request, ignore_query=False: "should-not-be-used")
    monkeypatch.setattr(routes, "get_template_context", lambda _request: {})
    monkeypatch.setattr(routes, "get_translation", lambda *_args, **_kwargs: "translated")
    monkeypatch.setattr(routes, "get_static_path", lambda *_args, **_kwargs: "/static/x")
    monkeypatch.setattr(routes, "get_url_from_view", lambda *_args, **_kwargs: "/url/x")
    monkeypatch.setattr(routes, "get_wirecloud_bootstrap", lambda *_args, **_kwargs: "bootstrap")
    monkeypatch.setattr(routes, "get_available_themes", lambda _lang: ["wirecloud.defaulttheme"])
    monkeypatch.setattr("wirecloud.platform.core.plugins.get_version_hash", lambda: "vhash")
    rendered = routes.render_wirecloud(request, view="smartphone")
    assert rendered["name"] == "wirecloud/views/smartphone.html"
    assert rendered["context"]["VIEW_MODE"] == "smartphone"
