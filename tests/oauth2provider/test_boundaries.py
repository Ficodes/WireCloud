"""OAuth protocol boundaries, provider compatibility, and deployment settings."""
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock

import pytest
from fastapi import Request

from oauth2provider.test_oauth import (
    oauth_app, oauth_client, login_user, authorize_client, exchange, AUDIENCE,
)
from oauth2provider.test_edge_cases import metadata_transport
from wirecloud import settings
from wirecloud.commons.auth import routes as auth_routes
from wirecloud.oauth2provider import require_access, service
from wirecloud.oauth2provider.plugins import OAuth2ProviderPlugin
from wirecloud.platform.plugins import ImproperlyConfigured, URLTemplate


async def pending_consent(client, **changes):
    registration = (await client.post("/oauth2/register", json={
        "redirect_uris": ["https://client.example/callback"]})).json()
    params = {"client_id": registration["client_id"], "resource": AUDIENCE,
        "redirect_uri": "https://client.example/callback", "response_type": "code",
        "code_challenge_method": "S256", "code_challenge": service.pkce("v" * 43), **changes}
    response = await client.get("/oauth2/authorize", params=params)
    return response


@pytest.mark.parametrize("changes", [
    {"response_type": "token"}, {"code_challenge_method": "plain"}, {"code_challenge": "short"},
    {"scope": "unknown"}, {"scope": ""}, {"state": "x" * 2049},
])
async def test_authorization_rejects_unsupported_flow_and_scopes(oauth_client, changes):
    response = await pending_consent(oauth_client, **changes)
    assert response.status_code == 400 and "location" not in response.headers


async def test_consent_requires_the_same_signed_in_session_on_redisplay_and_submission(oauth_client, db_session):
    await login_user(db_session, oauth_client)
    start = await pending_consent(oauth_client)
    form = {key: values[0] for key, values in parse_qs(urlsplit(start.headers["location"]).query).items()}
    assert (await oauth_client.get(start.headers["location"])).status_code == 200
    await login_user(db_session, oauth_client)
    redisplay = await oauth_client.get(start.headers["location"])
    assert redisplay.status_code == 400 and "session changed" in redisplay.text
    browser = oauth_client.cookies["wc_oauth_browser"]
    oauth_client.cookies.clear()
    # Keep the authorization browser cookie while removing the login cookie.
    oauth_client.cookies.set("wc_oauth_browser", browser)
    denied = await oauth_client.post("/oauth2/consent", data={**form, "decision": "approve"})
    assert denied.status_code == 401
    assert await db_session.client.oauth_codes.count_documents({}) == 0


async def test_impersonated_sessions_cannot_authorize_or_manage_connections(oauth_client, db_session, monkeypatch):
    from wirecloud.oauth2provider import routes
    user, session = await login_user(db_session, oauth_client)
    async def impersonated(*args, **kwargs):
        return {"real_user": str(user.id), "jti": str(session)}
    monkeypatch.setattr(routes, "get_token_contents", impersonated)
    monkeypatch.setattr(routes, "get_user", AsyncMock(return_value=user))
    response = await oauth_client.get("/oauth2/connections")
    assert response.status_code == 403 and "impersonation" in response.text


async def test_discovery_and_registration_require_an_enabled_resource(oauth_app, oauth_client):
    oauth_app.state.oauth2_resources.clear()
    for path in ("/.well-known/oauth-authorization-server", "/.well-known/oauth-protected-resource"):
        assert (await oauth_client.get(path)).status_code == 404
    assert (await oauth_client.post("/oauth2/register", json={"redirect_uris": ["https://client.example/cb"]})).status_code == 404


async def test_unsupported_grant_and_bad_basic_auth_are_protocol_errors(oauth_client):
    registered = (await oauth_client.post("/oauth2/register", json={"redirect_uris": ["https://client.example/cb"]})).json()
    response = await oauth_client.post("/oauth2/token", data={"client_id": registered["client_id"],
        "resource": AUDIENCE, "grant_type": "password"})
    assert response.status_code == 400 and response.json()["error"] == "unsupported_grant_type"
    for credentials in ("not base64", "YWJj", "/w=="):
        response = await oauth_client.post("/oauth2/token", headers={"Authorization": "Basic " + credentials})
        assert response.status_code == 401 and response.json()["error"] == "invalid_client"


@pytest.mark.parametrize("uri", ["https://example.com:0/cb", "https://example.com:65536/cb", "https://[bad/cb",
    "https://example.com/has space", "https://example.com/back\\slash", "https://example.com/" + "x" * 2049])
def test_malformed_redirect_ports_and_hosts_are_rejected(uri):
    assert not service.valid_redirect(uri)


def test_loopback_port_flexibility_still_validates_the_requested_uri():
    assert not service.redirect_matches("http://127.0.0.1/cb", "http://127.0.0.1:0/cb")


def test_invalid_client_auth_method_is_rejected():
    with pytest.raises(service.OAuthError, match="Unsupported client authentication"):
        service.validate_client({"redirect_uris": ["https://client.example/cb"], "token_endpoint_auth_method": "unknown"})


@pytest.mark.parametrize("url", ["http://client.example/client.json", "https://client.example:8443/client.json",
    "https://user:secret@client.example/client.json", "https://client.example/client.json#fragment"])
async def test_metadata_urls_must_be_public_https_without_credentials(url):
    with pytest.raises(service.OAuthError, match="Invalid client metadata URL"):
        await service.metadata_client(url)


async def test_metadata_uses_validated_ipv6_and_preserves_tls_name(monkeypatch):
    import json
    url = "https://client.example/client.json"
    requests = metadata_transport(monkeypatch, json.dumps({"client_id": url,
        "redirect_uris": ["https://client.example/cb"]}).encode(), addresses=("2606:4700:4700::1111",))
    client = await service.metadata_client(url)
    assert client["client_id"] == url
    args, kwargs = requests[0]
    assert args == ("GET", "https://[2606:4700:4700::1111]/client.json")
    assert kwargs["headers"]["Host"] == "client.example"
    assert kwargs["extensions"]["sni_hostname"] == "client.example"


async def test_configured_clients_skip_unrelated_entries_and_allow_public_clients(oauth_app, db_session, monkeypatch):
    monkeypatch.setattr(settings, "OAUTH2_CLIENTS", [
        {"client_id": "other"}, {"client_id": "public", "redirect_uris": ["https://client.example/cb"]}], raising=False)
    client = await service.get_client(db_session, "public")
    assert client["token_endpoint_auth_method"] == "none" and "secret_hash" not in client
    with pytest.raises(service.OAuthError, match="Unknown client"):
        await service.get_client(db_session, "missing")


async def test_token_exchange_rechecks_session_and_refresh_scope(oauth_client, db_session):
    user, session = await login_user(db_session, oauth_client)
    client_id, verifier, callback, _ = await authorize_client(oauth_client)
    # A correct code is unusable when its authorizing session has ended.
    await db_session.client.tokens.delete_one({"_id": session})
    response = await exchange(oauth_client, client_id, verifier, callback["code"])
    assert response.status_code == 400 and "session ended" in response.text
    await login_user(db_session, oauth_client)
    client_id, verifier, callback, _ = await authorize_client(oauth_client)
    tokens = (await exchange(oauth_client, client_id, verifier, callback["code"])).json()
    form = {"client_id": client_id, "resource": AUDIENCE, "grant_type": "refresh_token"}
    assert (await oauth_client.post("/oauth2/token", data={**form, "refresh_token": "missing"})).status_code == 400
    increased = await oauth_client.post("/oauth2/token", data={**form,
        "refresh_token": tokens["refresh_token"], "scope": "wirecloud:read wirecloud:workspace:write"})
    assert increased.status_code == 400 and increased.json()["error"] == "invalid_scope"
    other_id = (await oauth_client.post("/oauth2/register", json={"redirect_uris": ["https://other.example/cb"]})).json()["client_id"]
    wrong_client = await oauth_client.post("/oauth2/token", data={**form, "client_id": other_id,
        "refresh_token": tokens["refresh_token"]})
    assert wrong_client.status_code == 400 and "Invalid client or resource" in wrong_client.text
    # Failed scope/client requests must leave the valid refresh token usable.
    assert (await oauth_client.post("/oauth2/token", data={**form, "refresh_token": tokens["refresh_token"]})).status_code == 200


async def test_public_base_falls_back_to_login_configuration(oauth_app, monkeypatch):
    monkeypatch.setattr(settings, "OAUTH2_PUBLIC_URL", "")
    request = Request({"type": "http", "app": oauth_app, "scheme": "https", "server": ("wc.example", 443),
        "root_path": "/platform", "headers": [(b"host", b"wc.example")]})
    assert service.public_base(request) == "https://wc.example/platform"


async def test_plugin_endpoint_without_scope_and_misconfigured_scope(oauth_app, oauth_client, db_session):
    await login_user(db_session, oauth_client)
    client_id, verifier, callback, _ = await authorize_client(oauth_client)
    access = (await exchange(oauth_client, client_id, verifier, callback["code"])).json()["access_token"]
    request = Request({"type": "http", "app": oauth_app, "headers": [(b"authorization", ("Bearer " + access).encode())]})
    assert (await require_access(request, db_session, AUDIENCE)).client_id == client_id
    with pytest.raises(ValueError, match="not declared"):
        await require_access(request, db_session, AUDIENCE, ("unknown",))


@pytest.mark.parametrize("configuration", [
    {"OAUTH2_PUBLIC_URL": "http://remote.example"},
    {"OAUTH2_PUBLIC_URL": "https://wc.example?query=1"},
    {"OAUTH2_DYNAMIC_REGISTRATION": "yes"},
])
def test_oauth_plugin_rejects_invalid_configuration(configuration):
    validate, = OAuth2ProviderPlugin(None).get_config_validators()
    with pytest.raises(ImproperlyConfigured):
        validate(SimpleNamespace(**configuration))


def test_oauth_plugin_validates_preconfigured_clients():
    validate, = OAuth2ProviderPlugin(None).get_config_validators()
    validate(SimpleNamespace(OAUTH2_PUBLIC_URL="https://wc.example", OAUTH2_CLIENTS=[
        {"redirect_uris": ["https://client.example/cb"]}]))
    with pytest.raises(service.OAuthError):
        validate(SimpleNamespace(OAUTH2_CLIENTS=[{"redirect_uris": []}]))


async def test_oidc_provider_missing_or_async_legacy_hooks(oauth_client, monkeypatch):
    monkeypatch.setattr(settings, "OID_CONNECT_ENABLED", True)
    monkeypatch.setattr(settings, "OID_CONNECT_PLUGIN", "legacy")
    monkeypatch.setattr(auth_routes, "get_idm_get_authorization_url_functions", lambda: {})
    assert (await oauth_client.get("/auth/login")).status_code == 503
    async def authorize():
        return URLTemplate(urlpattern="https://id.example/auth?client_id=wc", defaults={})
    monkeypatch.setattr(auth_routes, "get_idm_get_authorization_url_functions", lambda: {"legacy": authorize})
    monkeypatch.setattr(auth_routes, "get_idm_get_token_functions", lambda: {"legacy": lambda code: None})
    response = await oauth_client.get("/auth/login", params={"next": "/oauth2/connections", "prompt": "select_account"})
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["prompt"] == ["select_account"]
    assert "code_challenge" not in query


async def test_oauth_startup_creates_expiry_and_lookup_indexes(oauth_app, db_session):
    async with oauth_app.router.lifespan_context(oauth_app):
        for collection in ("oauth_attempts", "oauth_codes", "oauth_tokens"):
            indexes = await db_session.client[collection].index_information()
            assert indexes["expires_at_1"]["expireAfterSeconds"] == 0
        assert (await db_session.client.oauth_clients.index_information())["client_id_1"]["unique"]
        assert {"user_id_1", "session_id_1"} <= (await db_session.client.oauth_grants.index_information()).keys()


async def test_invalid_pkce_verifiers_do_not_consume_codes(oauth_client, db_session):
    await login_user(db_session, oauth_client)
    client_id, verifier, callback, _ = await authorize_client(oauth_client)
    for invalid in ("short", "x" * 129, "!" * 43):
        response = await exchange(oauth_client, client_id, invalid, callback["code"])
        assert response.status_code == 400 and "Invalid PKCE verifier" in response.text
    assert (await exchange(oauth_client, client_id, verifier, callback["code"])).status_code == 200


async def test_consent_rejects_a_session_removed_during_approval(oauth_client, db_session, monkeypatch):
    from wirecloud.oauth2provider import routes

    user, session = await login_user(db_session, oauth_client)
    start = await pending_consent(oauth_client)
    assert (await oauth_client.get(start.headers["location"])).status_code == 200
    form = {key: values[0] for key, values in parse_qs(urlsplit(start.headers["location"]).query).items()}
    browser_identity = routes.browser_identity

    async def identity_before_session_removal(request, db):
        identity = await browser_identity(request, db)
        await db.client.tokens.delete_one({"_id": session})
        return identity

    monkeypatch.setattr(routes, "browser_identity", identity_before_session_removal)
    response = await oauth_client.post("/oauth2/consent", data={**form, "decision": "approve"})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_grant"
    assert await db_session.client.oauth_grants.count_documents({"user_id": str(user.id)}) == 0
    assert await db_session.client.oauth_codes.count_documents({}) == 0


async def test_connections_omit_a_grant_that_expires_while_listing(oauth_client, oauth_app, db_session, monkeypatch):
    await login_user(db_session, oauth_client)
    await authorize_client(oauth_client)
    instant = service.now()
    await db_session.client.oauth_grants.update_many({}, {"$set": {"expires_at": instant + timedelta(seconds=1)}})
    calls = 0
    def clock():
        nonlocal calls
        calls += 1
        # Registration of the CSRF form and construction of the query happen
        # before the expiry; by the time a row is returned it has expired.
        return instant if calls <= 2 else instant + timedelta(seconds=2)
    monkeypatch.setattr(service, "now", clock)
    response = await oauth_client.get("/oauth2/connections", headers={"Accept": "application/json"})
    assert response.status_code == 200 and response.json()["connections"] == []
