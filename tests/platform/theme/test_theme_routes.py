# -*- coding: utf-8 -*-

from types import SimpleNamespace

import jinja2

from wirecloud import main as main_module
from wirecloud.platform.theme import routes


async def _noop_close():
    return None


main_module.close = _noop_close


async def test_get_theme_info_success(app_client, monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_available_themes",
        lambda _lang: [
            {"value": "othertheme", "label": "Other"},
            {"value": "defaulttheme", "label": "Default"},
        ],
    )
    monkeypatch.setattr(routes, "get_templates", lambda _view: ["wirecloud/head", "wirecloud/body"])

    class _Templates:
        def TemplateResponse(self, request, name, context):
            return SimpleNamespace(body=f"<{name}>".encode("utf-8"))

    monkeypatch.setattr(routes, "get_jinja2_templates", lambda _theme: _Templates())
    monkeypatch.setattr(routes, "get_translation", lambda *_args, **_kwargs: "translated")
    monkeypatch.setattr(routes, "get_static_path", lambda *_args, **_kwargs: "/static/path")
    monkeypatch.setattr(routes, "get_url_from_view", lambda *_args, **_kwargs: "/view/url")
    monkeypatch.setattr(routes, "get_theme_config", lambda _theme: {"color_schemes": ["light", "dark"]})

    response = await app_client.get("/api/theme/defaulttheme?view=classic", headers={"accept": "application/json"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["config"] == {"color_schemes": ["light", "dark"]}
    assert payload["name"] == "defaulttheme"
    assert payload["label"] == "Default"
    assert payload["templates"]["wirecloud/head"] == "<wirecloud/head.html>"
    assert payload["templates"]["wirecloud/body"] == "<wirecloud/body.html>"
    expected_cache = "no-store" if routes.settings.DEBUG else "public, max-age=31536000, immutable"
    assert response.headers["cache-control"] == expected_cache


async def test_get_theme_info_theme_not_found_with_empty_theme_list(app_client, monkeypatch):
    monkeypatch.setattr(routes, "get_available_themes", lambda _lang: [])

    response = await app_client.get("/api/theme/missing?view=classic", headers={"accept": "application/json"})
    assert response.status_code == 404


async def test_get_theme_info_template_not_found(app_client, monkeypatch):
    monkeypatch.setattr(routes, "get_available_themes", lambda _lang: [{"value": "defaulttheme", "label": "Default"}])
    monkeypatch.setattr(routes, "get_templates", lambda _view: ["wirecloud/head"])

    class _Templates:
        def TemplateResponse(self, request, name, context):
            raise jinja2.exceptions.TemplateNotFound(name)

    monkeypatch.setattr(routes, "get_jinja2_templates", lambda _theme: _Templates())

    response = await app_client.get("/api/theme/defaulttheme?view=classic", headers={"accept": "application/json"})
    assert response.status_code == 404
