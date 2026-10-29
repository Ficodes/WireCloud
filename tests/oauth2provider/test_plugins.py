"""A non-MCP plugin can offer scoped connections using the shared OAuth server."""
from urllib.parse import parse_qs, urlsplit
from datetime import timedelta

import pytest
from fastapi import Request

from oauth2provider.test_oauth import oauth_app, oauth_client, login_user, AUDIENCE
from wirecloud import settings
from wirecloud.database import DBDep
from wirecloud.oauth2provider import OAuthResource, register_resource, require_access
from wirecloud.oauth2provider import service
from wirecloud.platform.plugins import ImproperlyConfigured

EXAMPLE = "http://localhost/api/example"


async def authorize_example(client, scope=None):
    registration = await client.post("/oauth2/register", json={"client_name": "Example desktop client",
        "redirect_uris": ["http://127.0.0.1:9000/callback"]})
    client_id = registration.json()["client_id"]
    verifier = service.random_token()
    params = {"client_id": client_id, "redirect_uri": "http://127.0.0.1:9000/callback", "response_type": "code",
        "code_challenge": service.pkce(verifier), "code_challenge_method": "S256", "resource": EXAMPLE}
    if scope is not None:
        params["scope"] = scope
    start = await client.get("/oauth2/authorize", params=params)
    assert start.status_code == 302, start.text
    form = {key: values[0] for key, values in parse_qs(urlsplit(start.headers["location"]).query).items()}
    consent = await client.get(start.headers["location"])
    assert "Example desktop client" in consent.text and "Read example data" in consent.text
    approved = await client.post("/oauth2/consent", data={**form, "decision": "approve"})
    code = parse_qs(urlsplit(approved.headers["location"]).query)["code"][0]
    tokens = await client.post("/oauth2/token", data={"grant_type": "authorization_code", "client_id": client_id,
        "redirect_uri": params["redirect_uri"], "resource": EXAMPLE, "code_verifier": verifier, "code": code})
    assert tokens.status_code == 200, tokens.text
    return tokens.json()["access_token"]


async def test_independent_plugin_connection_and_audience_scope_isolation(oauth_app, oauth_client, db_session):
    register_resource(oauth_app, OAuthResource(EXAMPLE, {"example:read": "Read example data", "example:write": "Edit example data"},
        "Example service", ("example:read",)))

    @oauth_app.get("/api/example")
    async def read(request: Request, db: DBDep):
        principal = await require_access(request, db, EXAMPLE, ("example:read",))
        return {"username": principal.user.username}

    @oauth_app.post("/api/example")
    async def write(request: Request, db: DBDep):
        await require_access(request, db, EXAMPLE, ("example:write",))
        return {"updated": True}

    user, _ = await login_user(db_session, oauth_client)
    # Browser cookies are not credentials for a plugin's bearer-only endpoint.
    missing = await oauth_client.get("/api/example")
    assert missing.status_code == 401
    assert '/.well-known/oauth-protected-resource/api/example' in missing.headers["www-authenticate"]
    access = await authorize_example(oauth_client)
    headers = {"Authorization": "Bearer " + access}
    assert (await oauth_client.get("/api/example", headers=headers)).json() == {"username": user.username}
    denied = await oauth_client.post("/api/example", headers=headers)
    assert denied.status_code == 403 and 'scope="example:write"' in denied.headers["www-authenticate"]
    assert await service.verify_access_token(db_session, access, AUDIENCE) is None
    # Reuse existing browser authentication without changing its JWT/widget behaviour.
    assert (await oauth_client.get("/oauth2/connections")).status_code == 200
    metadata = await oauth_client.get("/.well-known/oauth-protected-resource/api/example")
    assert metadata.json()["resource"] == EXAMPLE
    assert metadata.json()["scopes_supported"] == ["example:read", "example:write"]
    assert (await oauth_client.get("/.well-known/oauth-protected-resource/example")).status_code == 404
    write_access = await authorize_example(oauth_client, "example:read example:write")
    assert (await oauth_client.post("/api/example", headers={"Authorization": "Bearer " + write_access})).status_code == 200


def test_resource_registration_rejects_duplicates_invalid_defaults_and_disabled_provider(oauth_app, monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="already registered"):
        register_resource(oauth_app, OAuthResource(AUDIENCE, {"read": "Read"}, "Duplicate"))
    with pytest.raises(ImproperlyConfigured, match="valid scopes"):
        register_resource(oauth_app, OAuthResource(EXAMPLE, {"read": "Read"}, "Example", ("unknown",)))
    monkeypatch.setattr(settings, "INSTALLED_APPS", ["wirecloud.commons", "wirecloud.platform"])
    with pytest.raises(ImproperlyConfigured, match="Enable wirecloud.oauth2provider"):
        register_resource(oauth_app, OAuthResource(EXAMPLE, {"read": "Read"}, "Example"))


def test_commons_does_not_mount_optional_oauth_routes():
    from fastapi import FastAPI
    from wirecloud.commons.plugins import WirecloudCommonsPlugin
    app = FastAPI()
    WirecloudCommonsPlugin(app)
    assert "/auth/login" in {route.path for route in app.routes}
    assert not any(route.path.startswith("/oauth2/") for route in app.routes)


@pytest.mark.parametrize("prefix", ["", "/wirecloud", "/wirecloud/"])
def test_user_menu_endpoint_respects_deployment_prefix_and_platform_views(prefix):
    from wirecloud.oauth2provider.plugins import OAuth2ProviderPlugin
    plugin = OAuth2ProviderPlugin(None)
    request = Request({"type": "http", "root_path": prefix})
    for view in ("classic", "smartphone"):
        endpoints = plugin.get_ajax_endpoints(view, request)
        assert len(endpoints) == 1
        assert endpoints[0].id == "OAUTH2_CONNECTIONS"
        assert endpoints[0].url == prefix.rstrip("/") + "/oauth2/connections"
    assert plugin.get_ajax_endpoints("widget", request) == ()


async def test_consent_escapes_client_content_and_uses_theme_assets(oauth_client, db_session):
    await login_user(db_session, oauth_client)
    oauth_client.cookies.set("wc_oauth_browser", "preview-browser")
    attempt = {"_id": service.digest("preview-handle"), "browser": service.digest(oauth_client.cookies["wc_oauth_browser"]),
        "csrf": service.digest("preview-csrf"), "expires_at": service.now() + timedelta(minutes=5),
        "client_id": "client-id", "client_name": '<img src=x onerror="alert(1)">', "redirect_uri": "http://127.0.0.1:9000/callback",
        "audience": AUDIENCE, "scopes": ["wirecloud:read"]}
    await db_session.client.oauth_attempts.insert_one(attempt)
    response = await oauth_client.get("/oauth2/consent", params={"request_id": "preview-handle", "csrf": "preview-csrf"})
    assert response.status_code == 200
    assert '&lt;img src=x onerror=' in response.text
    assert '<img src=x' not in response.text
    assert 'css/oauth2provider.css?' in response.text
    assert 'images/logos/header.png?' in response.text
    from lxml import html
    scripts = html.fromstring(response.text).xpath("//script")
    assert scripts and all(script.get("src", "").startswith("/static/js/") and not script.text for script in scripts)
    assert all("defer" in script.attrib for script in scripts)
    assert len(scripts) == 1
    assert scripts[0].get("src") == "/static/js/cache.js?themeactive=defaulttheme&view=oauth2"
    assert "unsafe-inline" not in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"


async def test_child_theme_inherits_oauth_pages(oauth_client, db_session, monkeypatch):
    from wirecloud.commons.utils import theme
    monkeypatch.setattr(settings, "AVAILABLE_THEMES", ["defaulttheme", "fiwaretheme"])
    monkeypatch.setattr(theme, "AVAILABLE_THEMES", settings.AVAILABLE_THEMES)
    monkeypatch.setattr(theme, "JINJA2_TEMPLATES", {})
    monkeypatch.setattr(theme, "THEME_TRANSLATIONS", {})
    theme._generate_jinja2_templates()
    theme._generate_theme_translations()
    await login_user(db_session, oauth_client)
    response = await oauth_client.get("/oauth2/connections?themeactive=fiwaretheme")
    assert response.status_code == 200
    assert 'themeactive=fiwaretheme' in response.text
    assert 'No connected applications' in response.text
    from lxml import html
    assert html.fromstring(response.text).xpath("//script/@src") == [
        "/static/js/cache.js?themeactive=fiwaretheme&view=oauth2"]
    assert theme.get_theme_static_path("fiwaretheme", "css/oauth2provider.css").endswith("defaulttheme/static/css/oauth2provider.css")
