# -*- coding: utf-8 -*-

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from wirecloud.platform.core import plugins as core_plugins
from wirecloud.platform.plugins import URLTemplate


@pytest.fixture(autouse=True)
def _patch_gettext(monkeypatch):
    monkeypatch.setattr(core_plugins, "_", lambda text: text)


def _request(path="/workspace/wirecloud/home", query="", root_path=""):
    req = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "server": ("wirecloud.example.org", 443),
            "path": path,
            "root_path": root_path,
            "query_string": query.encode("utf-8"),
            "headers": [(b"host", b"wirecloud.example.org"), (b"user-agent", b"Mozilla/5.0")],
        }
    )
    req.state.lang = "en"
    return req


class _AnyPatterns(dict):
    def __missing__(self, key):
        value = URLTemplate(urlpattern=f"/{key}", defaults={})
        self[key] = value
        return value


def _base_patterns():
    patterns = _AnyPatterns()
    patterns["wirecloud|proxy"] = URLTemplate(urlpattern="/cdp/{protocol}/{domain}/{path:path}", defaults={})
    patterns["login"] = URLTemplate(urlpattern="/login", defaults={})
    patterns["wirecloud.login"] = URLTemplate(urlpattern="/api/auth/login", defaults={})
    patterns["logout"] = URLTemplate(urlpattern="/api/auth/logout", defaults={})
    patterns["wirecloud.token_refresh"] = URLTemplate(urlpattern="/api/auth/refresh", defaults={})
    return patterns


async def test_get_version_hash_uses_active_features(monkeypatch):
    monkeypatch.setattr(core_plugins, "get_active_features_info", lambda: {"a": "1", "b": "2"})
    first = core_plugins.get_version_hash()
    second = core_plugins.get_version_hash()
    assert first == second
    assert len(first) == 40


async def test_populate_component_paths(monkeypatch, db_session):
    async def _exists(*_args, **_kwargs):
        return object()

    monkeypatch.setattr(core_plugins, "get_catalogue_resource", _exists)
    assert await core_plugins.populate_component(db_session, object(), "v", "n", "1.0", "/tmp/x.wgt") is False

    called = {}

    async def _missing(*_args, **_kwargs):
        return None

    async def _install(db, wgt, executor_user, users):
        called["db"] = db
        called["wgt"] = wgt
        called["executor_user"] = executor_user
        called["users"] = users

    monkeypatch.setattr(core_plugins, "get_catalogue_resource", _missing)
    monkeypatch.setattr(core_plugins, "WgtFile", lambda path: f"WGT:{path}")
    monkeypatch.setattr(core_plugins, "install_component", _install)
    ok = await core_plugins.populate_component(db_session, "wirecloud-user", "v", "n", "1.0", "/tmp/new.wgt")
    assert ok is True
    assert called["wgt"] == "WGT:/tmp/new.wgt"
    assert called["users"] == ["wirecloud-user"]


def test_core_plugin_init_and_market_constants():
    app = FastAPI()
    plugin = core_plugins.WirecloudCorePlugin(app)
    assert plugin.app is app
    paths = {route.path for route in app.routes}
    assert "/" in paths
    assert "/api/context/" in paths
    assert "/workspace/{owner}/{name}" in paths
    assert "/showcase/media/{vendor}/{name}/{version}/{file_path:path}" in paths

    plugin_no_app = core_plugins.WirecloudCorePlugin(None)
    assert plugin_no_app.get_market_classes()["wirecloud"].__name__ == "WirecloudCatalogueManager"
    constants = plugin_no_app.get_constants()
    assert "AVAILABLE_LANGUAGES" in constants
    assert isinstance(constants["AVAILABLE_LANGUAGES"], list)


def test_config_validator_defaults_and_errors(tmp_path):
    plugin = core_plugins.WirecloudCorePlugin(None)
    validate = plugin.get_config_validators()[0]

    settings = SimpleNamespace(BASEDIR=str(tmp_path))
    validate(settings, False)
    assert settings.WIDGET_DEPLOYMENT_DIR.endswith("deployment/widgets")
    assert settings.AVAILABLE_THEMES == ["defaulttheme"]
    assert settings.THEME_ACTIVE == "defaulttheme"

    bad_widget_dir = SimpleNamespace(
        BASEDIR=str(tmp_path),
        WIDGET_DEPLOYMENT_DIR=123,
        AVAILABLE_THEMES=["defaulttheme"],
        THEME_ACTIVE="defaulttheme",
    )
    with pytest.raises(ValueError, match="WIDGET_DEPLOYMENT_DIR must be a string"):
        validate(bad_widget_dir, False)

    bad_cache_type = SimpleNamespace(
        BASEDIR=str(tmp_path),
        WIDGET_DEPLOYMENT_DIR=str(tmp_path / "widgets"),
        CACHE_DIR=123,
        AVAILABLE_THEMES=["defaulttheme"],
        THEME_ACTIVE="defaulttheme",
    )
    with pytest.raises(ValueError, match="CACHE_DIR must be a string"):
        validate(bad_cache_type, False)

    bad_theme_list = SimpleNamespace(
        BASEDIR=str(tmp_path),
        WIDGET_DEPLOYMENT_DIR=str(tmp_path / "widgets"),
        AVAILABLE_THEMES="x",
        THEME_ACTIVE="defaulttheme",
    )
    with pytest.raises(ValueError, match="AVAILABLE_THEMES must be a list"):
        validate(bad_theme_list, False)

    empty_themes = SimpleNamespace(
        BASEDIR=str(tmp_path),
        WIDGET_DEPLOYMENT_DIR=str(tmp_path / "widgets"),
        AVAILABLE_THEMES=[],
        THEME_ACTIVE="defaulttheme",
    )
    with pytest.raises(ValueError, match="must contain at least one theme"):
        validate(empty_themes, False)

    bad_active_type = SimpleNamespace(
        BASEDIR=str(tmp_path),
        WIDGET_DEPLOYMENT_DIR=str(tmp_path / "widgets"),
        AVAILABLE_THEMES=["defaulttheme"],
        THEME_ACTIVE=1,
    )
    with pytest.raises(ValueError, match="THEME_ACTIVE must be a string"):
        validate(bad_active_type, False)

    active_not_in_themes = SimpleNamespace(
        BASEDIR=str(tmp_path),
        WIDGET_DEPLOYMENT_DIR=str(tmp_path / "widgets"),
        AVAILABLE_THEMES=["defaulttheme"],
        THEME_ACTIVE="other",
    )
    with pytest.raises(ValueError, match="is not in AVAILABLE_THEMES"):
        validate(active_not_in_themes, False)

    cache_create_ok = SimpleNamespace(
        BASEDIR=str(tmp_path),
        WIDGET_DEPLOYMENT_DIR=str(tmp_path / "widgets-ok"),
        CACHE_DIR=str(tmp_path / "cache-ok"),
        AVAILABLE_THEMES=["defaulttheme"],
        THEME_ACTIVE="defaulttheme",
    )
    validate(cache_create_ok, False)
    assert (tmp_path / "cache-ok").exists()

    cache_exists = SimpleNamespace(
        BASEDIR=str(tmp_path),
        WIDGET_DEPLOYMENT_DIR=str(tmp_path / "widgets-ok-2"),
        CACHE_DIR=str(tmp_path / "cache-already"),
        AVAILABLE_THEMES=["defaulttheme"],
        THEME_ACTIVE="defaulttheme",
    )
    (tmp_path / "cache-already").mkdir(parents=True, exist_ok=True)
    validate(cache_exists, False)


def test_config_validator_directory_creation_failures(monkeypatch, tmp_path):
    plugin = core_plugins.WirecloudCorePlugin(None)
    validate = plugin.get_config_validators()[0]

    settings_widget_fail = SimpleNamespace(
        BASEDIR=str(tmp_path),
        WIDGET_DEPLOYMENT_DIR=str(tmp_path / "widgets-fail"),
        AVAILABLE_THEMES=["defaulttheme"],
        THEME_ACTIVE="defaulttheme",
    )

    def _makedirs_fail_widget(path, exist_ok=False):
        if "widgets-fail" in path:
            raise RuntimeError("boom-widget")

    monkeypatch.setattr(core_plugins.os, "makedirs", _makedirs_fail_widget)
    monkeypatch.setattr(core_plugins.os.path, "exists", lambda path: False if "widgets-fail" in path else True)
    with pytest.raises(ValueError, match="Failed to create WIDGET_DEPLOYMENT_DIR directory"):
        validate(settings_widget_fail, False)

    settings_cache_fail = SimpleNamespace(
        BASEDIR=str(tmp_path),
        WIDGET_DEPLOYMENT_DIR=str(tmp_path / "widgets-ok"),
        CACHE_DIR=str(tmp_path / "cache-fail"),
        AVAILABLE_THEMES=["defaulttheme"],
        THEME_ACTIVE="defaulttheme",
    )

    def _makedirs_fail_cache(path, exist_ok=False):
        if "cache-fail" in path:
            raise RuntimeError("boom-cache")

    monkeypatch.setattr(core_plugins.os, "makedirs", _makedirs_fail_cache)
    monkeypatch.setattr(
        core_plugins.os.path,
        "exists",
        lambda path: False if ("widgets-ok" in path or "cache-fail" in path) else True,
    )
    with pytest.raises(ValueError, match="Failed to create CACHE_DIR directory"):
        validate(settings_cache_fail, False)


async def test_platform_context_definitions_and_values(monkeypatch, db_session):
    plugin = core_plugins.WirecloudCorePlugin(None)
    definitions = plugin.get_platform_context_definitions()
    assert "username" in definitions
    assert "version_hash" in definitions

    monkeypatch.setattr(core_plugins, "get_current_view", lambda _request: "classic")
    monkeypatch.setattr(core_plugins, "get_current_theme", lambda _request: "wirecloud.defaulttheme")
    monkeypatch.setattr(core_plugins, "get_version_hash", lambda: "hash")
    monkeypatch.setattr(core_plugins, "get_user_groups", lambda _db, _user_id: _groups())

    async def _groups():
        return [SimpleNamespace(name="dev"), SimpleNamespace(name="ops")]

    user = SimpleNamespace(
        id="u1",
        username="alice",
        email="alice@example.org",
        is_staff=True,
        is_superuser=False,
        get_full_name=lambda: "Alice Doe",
    )
    session = SimpleNamespace(real_user="root")
    values = await plugin.get_platform_context_current_values(db_session, _request(), user, session)
    assert values["username"] == "alice"
    assert values["fullname"] == "Alice Doe"
    assert values["groups"] == ("dev", "ops")
    assert values["organizations"] == ()
    assert values["realuser"] == "root"
    assert values["mode"] == "classic"
    assert values["theme"] == "wirecloud.defaulttheme"
    assert values["version_hash"] == "hash"

    root = SimpleNamespace(id="root", name="Acme", is_organization=True, path=["root"])
    child = SimpleNamespace(id="child", name="Acme/dev", is_organization=True, path=["root", "child"])
    duplicate = SimpleNamespace(id="other", name="Acme/ops", is_organization=True, path=["root", "other"])
    orphan = SimpleNamespace(id="orphan", name="Missing/dev", is_organization=True, path=["missing", "orphan"])
    no_path = SimpleNamespace(id="empty", name="Empty", is_organization=True, path=[])
    regular = SimpleNamespace(id="regular", name="Regular", is_organization=False, path=["regular"])

    async def _organization_groups():
        return [regular, no_path, root, child, duplicate, orphan]

    async def _root_group(_db, group_id):
        return root if group_id == "root" else None

    monkeypatch.setattr(core_plugins, "get_user_groups", lambda *_args: _organization_groups())
    monkeypatch.setattr(core_plugins, "get_group_by_id", _root_group)
    organization_values = await plugin.get_platform_context_current_values(db_session, _request(), user, session)
    assert organization_values["organizations"] == ("Acme",)

    anon = await plugin.get_platform_context_current_values(db_session, None, None, None)
    assert anon["username"] == "anonymous"
    assert anon["isanonymous"] is True
    assert anon["groups"] == ()
    assert anon["organizations"] == ()
    assert anon["mode"] is None
    assert anon["theme"] is None


def test_workspace_preferences_templates_extensions_and_openapi(monkeypatch):
    plugin = core_plugins.WirecloudCorePlugin(None)
    workspace_ctx = plugin.get_workspace_context_definitions()
    assert "title" in workspace_ctx
    assert "params" in workspace_ctx
    platform_prefs = plugin.get_platform_preferences()
    assert [pref.name for pref in platform_prefs] == ["allow_external_token_use", "external_token_domain_whitelist"]

    workspace_prefs = plugin.get_workspace_preferences()
    assert any(pref.name == "public" for pref in workspace_prefs)
    tab_prefs = plugin.get_tab_preferences()
    assert all(pref.name != "public" for pref in tab_prefs)
    assert all(pref.inheritable for pref in tab_prefs)

    # The old 'initiallayout'/'baselayout' preferences and the 'layout' input field type are gone
    assert all(pref.name not in ("initiallayout", "baselayout") for pref in workspace_prefs)
    assert all(pref.type != "layout" for pref in workspace_prefs)

    prefs_by_name = {pref.name: pref for pref in workspace_prefs}
    sharelist_pref = prefs_by_name["sharelist"]
    assert sharelist_pref.type == "text"
    assert sharelist_pref.hidden is True

    screen_sizes_pref = prefs_by_name["screenSizes"]
    assert screen_sizes_pref.type == "screenSizes"
    assert screen_sizes_pref.defaultValue == [
        {"id": 0, "name": "Phone", "moreOrEqual": 0, "lessOrEqual": 767, "columns": 1},
        {"id": 1, "name": "Tablet", "moreOrEqual": 768, "lessOrEqual": 1199, "columns": 6},
        {"id": 2, "name": "Desktop", "moreOrEqual": 1200, "lessOrEqual": -1, "columns": 12},
    ]

    cellheight_pref = prefs_by_name["cellheight"]
    assert cellheight_pref.type == "number"
    assert cellheight_pref.defaultValue == 40

    margin_pref = prefs_by_name["margin"]
    assert margin_pref.type == "number"
    assert margin_pref.defaultValue == 5

    # Tab preferences mirror the workspace ones (minus 'public') and stay inheritable
    tab_prefs_by_name = {pref.name: pref for pref in tab_prefs}
    assert tab_prefs_by_name["screenSizes"].defaultValue == screen_sizes_pref.defaultValue
    assert tab_prefs_by_name["cellheight"].defaultValue == 40
    assert tab_prefs_by_name["margin"].defaultValue == 5

    assert len(plugin.get_templates("classic")) > 0
    assert len(plugin.get_templates("smartphone")) > 0
    assert plugin.get_templates("embedded") == []

    assert plugin.get_widget_api_extensions("classic", []) == ["js/WirecloudAPI/StyledElements.js"]
    assert plugin.get_widget_api_extensions("classic", ["DashboardManagement", "ComponentManagement"]) == [
        "js/WirecloudAPI/StyledElements.js",
        "js/WirecloudAPI/DashboardManagementAPI.js",
        "js/WirecloudAPI/ComponentManagementAPI.js",
    ]
    assert plugin.get_operator_api_extensions("classic", []) == []
    assert plugin.get_operator_api_extensions("classic", ["DashboardManagement", "ComponentManagement"]) == [
        "js/WirecloudAPI/DashboardManagementAPI.js",
        "js/WirecloudAPI/ComponentManagementAPI.js",
    ]
    assert plugin.get_proxy_processors() == ("wirecloud.proxy.processors.SecureDataProcessor",)

    monkeypatch.setattr(core_plugins.ResourceCreateData, "model_json_schema", classmethod(lambda cls: {"a": 1}))
    monkeypatch.setattr(core_plugins.ResourceCreateFormData, "model_json_schema", classmethod(lambda cls: {"b": 2}))
    assert plugin.get_openapi_extra_schemas() == {"ResourceCreateData": {"a": 1}, "ResourceCreateFormData": {"b": 2}}


def test_get_management_commands_delegates(monkeypatch):
    plugin = core_plugins.WirecloudCorePlugin(None)
    monkeypatch.setattr(core_plugins, "setup_commands", lambda subparsers: {"x": subparsers})
    assert plugin.get_management_commands("sp") == {"x": "sp"}


def test_get_ajax_endpoints_paths(monkeypatch):
    plugin = core_plugins.WirecloudCorePlugin(None)
    request = _request(path="/workspace/wirecloud/home", query="mode=classic", root_path="/prefix")
    monkeypatch.setattr(core_plugins, "get_plugin_urls", _base_patterns)

    def _build_url_template(urltemplate, kwargs=None, prefix=None):
        kwargs = kwargs or []
        suffix = ",".join(kwargs)
        return f"{prefix or ''}{urltemplate.urlpattern}|{suffix}"

    monkeypatch.setattr(core_plugins, "build_url_template", _build_url_template)
    monkeypatch.setattr(core_plugins, "get_absolute_reverse_url", lambda *_args, **_kwargs: "https://wc/oidc/callback")
    monkeypatch.setattr(core_plugins.settings, "OID_CONNECT_ENABLED", False)

    endpoints = plugin.get_ajax_endpoints("classic", request)
    endpoint_ids = {e.id for e in endpoints}
    assert "PROXY" in endpoint_ids
    assert "WORKSPACE_VIEW" in endpoint_ids
    assert "LOGIN_VIEW" in endpoint_ids
    login_view = next(e for e in endpoints if e.id == "LOGIN_VIEW")
    assert login_view.url.startswith("/prefix")

    monkeypatch.setattr(core_plugins.settings, "OID_CONNECT_ENABLED", True)
    oidc_endpoints = plugin.get_ajax_endpoints("classic", request)
    oidc_login = next(e for e in oidc_endpoints if e.id == "LOGIN_VIEW")
    assert "redirect_uri=" in oidc_login.url
    assert "state=" in oidc_login.url

    patterns_with_query = _base_patterns()
    patterns_with_query["login"] = URLTemplate(urlpattern="/login?x=1", defaults={})
    monkeypatch.setattr(core_plugins, "get_plugin_urls", lambda: patterns_with_query)
    oidc_endpoints_q = plugin.get_ajax_endpoints("classic", request)
    oidc_login_q = next(e for e in oidc_endpoints_q if e.id == "LOGIN_VIEW")
    assert "&redirect_uri=" in oidc_login_q.url


def test_get_ajax_endpoints_missing_proxy_raises(monkeypatch):
    plugin = core_plugins.WirecloudCorePlugin(None)
    patterns = _base_patterns()
    del patterns["wirecloud|proxy"]
    monkeypatch.setattr(core_plugins, "get_plugin_urls", lambda: patterns)
    with pytest.raises(ValueError, match="Missing proxy url pattern"):
        plugin.get_ajax_endpoints("classic", _request())


async def test_populate_orchestrates_components_and_workspaces(monkeypatch, db_session):
    plugin = core_plugins.WirecloudCorePlugin(None)
    calls = {"components": [], "workspaces": [], "creates": []}

    async def _populate_component(_db, _user, vendor, name, version, wgt_path):
        calls["components"].append((vendor, name, version, wgt_path))
        return name in ("workspace-browser", "markdown-editor")

    async def _workspace_lookup(_db, owner, name):
        calls["workspaces"].append((owner, name))
        if name in ("home", "landing"):
            return None
        return object()

    async def _create_workspace(_db, _source, _user, wgt, searchable, public):
        calls["creates"].append((wgt, searchable, public))

    monkeypatch.setattr(core_plugins, "populate_component", _populate_component)
    monkeypatch.setattr(core_plugins, "get_workspace_by_username_and_name", _workspace_lookup)
    monkeypatch.setattr(core_plugins, "create_workspace", _create_workspace)
    monkeypatch.setattr(core_plugins, "WgtFile", lambda path: f"WGT:{path}")

    updated = await plugin.populate(db_session, object())
    assert updated is True
    assert len(calls["components"]) == 3
    assert ("wirecloud", "home") in calls["workspaces"]
    assert ("wirecloud", "landing") in calls["workspaces"]
    assert len(calls["creates"]) == 2

    async def _workspace_exists(_db, owner, name):
        return object()

    monkeypatch.setattr(core_plugins, "populate_component", lambda *_args, **_kwargs: _false())
    monkeypatch.setattr(core_plugins, "get_workspace_by_username_and_name", _workspace_exists)

    async def _false():
        return False

    updated2 = await plugin.populate(db_session, object())
    assert updated2 is False
