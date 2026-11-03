# -*- coding: utf-8 -*-

from fastapi import FastAPI

from wirecloud.commons import plugins


def test_wirecloud_commons_plugin_init_with_none():
    plugin = plugins.WirecloudCommonsPlugin(None)
    assert plugin.app is None


def test_wirecloud_commons_plugin_registers_routes_and_handlers():
    app = FastAPI()
    plugin = plugins.WirecloudCommonsPlugin(app)

    assert plugin.app is app
    route_paths = {route.path for route in app.routes}
    assert "/api/auth/login" in route_paths
    assert "/api/i18n/js_catalogue" in route_paths
    assert "/api/search" in route_paths

    assert plugins.ErrorResponse in app.exception_handlers
    assert app.exception_handlers[plugins.HTTPException] is plugins.http_exception_handler
    assert plugins.PermissionDenied in app.exception_handlers
    assert plugins.NotFound in app.exception_handlers
    assert plugins.RequestValidationError in app.exception_handlers
    assert ValueError in app.exception_handlers
    assert Exception in app.exception_handlers


def test_wirecloud_commons_plugin_urls_openapi_and_commands(monkeypatch):
    monkeypatch.setattr(plugins, "get_urlpatterns", lambda: {"x": "y"})
    monkeypatch.setattr(plugins, "setup_commands", lambda subparsers: {"cmd": subparsers})
    plugin = plugins.WirecloudCommonsPlugin(None)

    assert plugin.get_urls() == {"x": "y"}
    assert "UserLogin" in plugin.get_openapi_extra_schemas()
    assert plugin.get_management_commands("sub") == {"cmd": "sub"}

