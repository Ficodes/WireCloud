"""Exercise the real browser/OAuth flow independently of MCP or Keycloak."""
import asyncio
import re
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from wirecloud import settings
from wirecloud.commons.auth import routes, utils as auth_utils
from wirecloud.oauth2provider import service as delegated, routes as oauth_routes
from wirecloud.oauth2provider.pages import page_headers
from wirecloud.oauth2provider.plugins import OAuth2ProviderPlugin
from wirecloud.commons.auth.crud import create_token, create_user_db, invalidate_token, invalidate_tokens_by_idm_session
from wirecloud.commons.auth.schemas import UserCreate
from wirecloud.commons.auth.utils import hash_password
from wirecloud.database import get_session

AUDIENCE = "http://localhost/mcp"
SCOPES = {"wirecloud:read": "Read accessible data", "wirecloud:workspace:write": "Edit workspaces"}


@pytest.fixture
async def oauth_app(monkeypatch, db_session):
    # Authorization state and rate-limit buckets must not leak between tests.
    for collection in ("oauth_attempts", "oauth_clients", "oauth_codes", "oauth_tokens", "oauth_grants", "login_attempts"):
        await db_session.client[collection].delete_many({})
    app = FastAPI()
    OAuth2ProviderPlugin(app)
    app.include_router(routes.base_router)
    delegated.register_resource(app, delegated.OAuthResource(AUDIENCE, SCOPES, "Test resource", ("wirecloud:read",)))

    async def session():
        yield db_session

    app.dependency_overrides[get_session] = session
    monkeypatch.setattr(settings, "OAUTH2_PUBLIC_URL", "http://localhost", raising=False)
    monkeypatch.setattr(settings, "OID_CONNECT_ENABLED", False)
    monkeypatch.setattr(settings, "OAUTH2_DYNAMIC_REGISTRATION", True, raising=False)
    monkeypatch.setattr(settings, "JWT_KEY", "delegated-tests-signing-key-at-least-32-characters")
    return app


@pytest.fixture
async def oauth_client(oauth_app):
    async with AsyncClient(transport=ASGITransport(app=oauth_app), base_url="http://localhost") as client:
        yield client


async def login_user(db, client, idm_session=None):
    name = "oauth-" + delegated.random_token()
    user = await create_user_db(db, UserCreate(username=name, password=hash_password("password"), email="a@example.com",
        first_name="", last_name="", is_superuser=False, is_staff=False, is_active=True, idm_data={}))
    expiration = delegated.now() + timedelta(hours=1)
    session_id = await create_token(db, expiration, user.id, idm_session)
    token = jwt.encode({"sub": str(user.id), "iss": "Wirecloud", "jti": str(session_id), "exp": expiration,
        "iat": delegated.now(), "csrf_required": True}, settings.JWT_KEY, algorithm="HS256")
    client.cookies.set("token", token)
    return user, session_id


async def authorize_client(client, scope="wirecloud:read", approve=True):
    registered = await client.post("/oauth2/register", json={"client_name": "Test AI", "redirect_uris": ["http://127.0.0.1:9000/callback"]})
    assert registered.status_code == 201, registered.text
    client_id = registered.json()["client_id"]
    verifier = delegated.random_token()
    params = {"client_id": client_id, "redirect_uri": "http://127.0.0.1:9000/callback", "response_type": "code",
        "code_challenge": delegated.pkce(verifier), "code_challenge_method": "S256", "resource": AUDIENCE,
        "scope": scope, "state": "client-state"}
    authorization = await client.get("/oauth2/authorize", params=params)
    assert authorization.status_code == 302, authorization.text
    consent_url = authorization.headers["location"]
    form = {key: values[0] for key, values in parse_qs(urlsplit(consent_url).query).items()}
    consent = await client.get(consent_url)
    if approve:
        assert consent.status_code == 200, consent.text
        assert "Test AI" in consent.text
        assert consent.headers["x-frame-options"] == "DENY"
    form["decision"] = "approve" if approve else "deny"
    result = await client.post("/oauth2/consent", data=form)
    assert result.status_code == 302, result.text
    callback = {key: value[0] for key, value in parse_qs(urlsplit(result.headers["location"]).query).items()}
    return client_id, verifier, callback, form


async def exchange(client, client_id, verifier, code, **changes):
    data = {"client_id": client_id, "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
        "redirect_uri": "http://127.0.0.1:9000/callback", "resource": AUDIENCE, **changes}
    return await client.post("/oauth2/token", data=data)


async def test_discovery_and_browser_consent(oauth_client, db_session):
    user, session = await login_user(db_session, oauth_client)
    metadata = await oauth_client.get("/.well-known/oauth-protected-resource/mcp")
    assert metadata.json()["resource"] == AUDIENCE
    server = await oauth_client.get("/.well-known/oauth-authorization-server/oauth2")
    assert server.json()["issuer"] == "http://localhost/oauth2"
    client_id, verifier, callback, form = await authorize_client(oauth_client)
    assert callback["state"] == "client-state"
    response = await exchange(oauth_client, client_id, verifier, callback["code"])
    assert response.status_code == 200, response.text
    tokens = response.json()
    assert response.headers["cache-control"] == "no-store"
    principal = await delegated.verify_access_token(db_session, tokens["access_token"], AUDIENCE)
    assert principal.user.id == user.id
    assert principal.session_id == str(session)
    assert await delegated.verify_access_token(db_session, tokens["access_token"], "http://other/mcp") is None
    assert (await exchange(oauth_client, client_id, verifier, callback["code"])).status_code == 400
    assert (await oauth_client.post("/oauth2/consent", data=form)).status_code == 400
    record = await db_session.client.oauth_tokens.find_one({"_id": delegated.digest(tokens["access_token"])})
    assert "token" not in record


@pytest.mark.parametrize("callback", [
    "http://127.0.0.1:51389/callback",
    "https://client.example:8443/oauth/callback?session=example",
])
@pytest.mark.parametrize("decision", ["approve", "deny"])
async def test_consent_csp_allows_only_the_validated_callback(oauth_client, db_session, callback, decision):
    await login_user(db_session, oauth_client)
    registration = await oauth_client.post("/oauth2/register", json={"redirect_uris": [callback]})
    authorization = await oauth_client.get("/oauth2/authorize", params={
        "client_id": registration.json()["client_id"], "redirect_uri": callback, "resource": AUDIENCE,
        "response_type": "code", "code_challenge_method": "S256", "code_challenge": delegated.pkce("x" * 43)})
    consent = await oauth_client.get(authorization.headers["location"])
    assert consent.status_code == 200
    origin = urlsplit(callback)
    assert consent.headers["content-security-policy"] == page_headers(callback)["Content-Security-Policy"]
    assert f"form-action 'self' {origin.scheme}://{origin.netloc};" in consent.headers["content-security-policy"]
    assert "style-src 'self';" in consent.headers["content-security-policy"]
    assert "script-src 'self';" in consent.headers["content-security-policy"]
    assert "script-src-attr 'none';" in consent.headers["content-security-policy"]
    form = {key: values[0] for key, values in parse_qs(urlsplit(authorization.headers["location"]).query).items()}
    result = await oauth_client.post(authorization.headers["location"], data={**form, "decision": decision})
    assert result.status_code == 302
    destination = urlsplit(result.headers["location"])
    assert (destination.scheme, destination.netloc, destination.path) == (origin.scheme, origin.netloc, origin.path)
    assert ("code" if decision == "approve" else "error") in parse_qs(destination.query)
    connections = await oauth_client.get("/oauth2/connections")
    assert "form-action 'self';" in connections.headers["content-security-policy"]


def test_consent_csp_callback_cannot_inject_directives_or_wildcards():
    policy = page_headers("https://*.example;script-src=evil/callback")["Content-Security-Policy"]
    assert "form-action 'self' https://%2A.example%3Bscript-src%3Devil;" in policy
    assert "script-src=" not in policy


async def test_pkce_callback_resource_and_scope_validation(oauth_client, db_session):
    await login_user(db_session, oauth_client)
    client_id, verifier, callback, _ = await authorize_client(oauth_client)
    assert (await exchange(oauth_client, client_id, "x" * 43, callback["code"])).status_code == 400
    assert (await exchange(oauth_client, client_id, verifier, callback["code"], redirect_uri="https://evil.example/callback")).status_code == 400
    assert (await exchange(oauth_client, client_id, verifier, callback["code"], resource="https://evil.example/mcp")).status_code == 400
    assert (await exchange(oauth_client, client_id, verifier, callback["code"])).status_code == 200
    invalid = await oauth_client.get("/oauth2/authorize", params={"client_id": client_id, "resource": AUDIENCE,
        "redirect_uri": "https://evil.example/callback"})
    assert invalid.status_code == 400 and "location" not in invalid.headers
    assert (await oauth_client.post("/oauth2/register", json={"redirect_uris": ["javascript:alert(1)"]})).status_code == 400


async def test_denial_browser_binding_and_anonymous_redirect(oauth_client, oauth_app, db_session):
    await login_user(db_session, oauth_client)
    client_id, _, callback, form = await authorize_client(oauth_client, approve=False)
    assert callback["error"] == "access_denied" and "code" not in callback
    _, _, _, form = await authorize_client(oauth_client)
    async with AsyncClient(transport=ASGITransport(app=oauth_app), base_url="http://localhost") as other:
        forged = await other.post("/oauth2/consent", data=form)
        assert forged.status_code == 400
        r = await other.get("/oauth2/connections")
        assert r.status_code == 302 and "/auth/login?" in r.headers["location"]


@pytest.mark.parametrize("termination", ["logout", "provider_logout", "inactive", "permission_change", "expired"])
async def test_live_identity_and_session_checks(oauth_client, db_session, termination):
    user, session_id = await login_user(db_session, oauth_client, idm_session="external-" + delegated.random_token())
    client_id, verifier, callback, _ = await authorize_client(oauth_client)
    tokens = (await exchange(oauth_client, client_id, verifier, callback["code"])).json()
    if termination == "logout":
        assert (await oauth_client.get("/logout")).status_code == 302
    elif termination == "provider_logout":
        session = await db_session.client.tokens.find_one({"_id": session_id})
        await invalidate_tokens_by_idm_session(db_session, session["idm_session"])
    elif termination == "inactive":
        await db_session.client.users.update_one({"_id": user.id}, {"$set": {"is_active": False}})
    elif termination == "expired":
        await db_session.client.tokens.update_one({"_id": session_id}, {"$set": {"expiration": delegated.now() - timedelta(seconds=1)}})
    else:
        await db_session.client.users.update_one({"_id": user.id}, {"$set": {"user_permissions": []}})
    principal = await delegated.verify_access_token(db_session, tokens["access_token"], AUDIENCE)
    if termination == "permission_change":
        assert principal is not None and not principal.user.has_perm("WORKSPACE.CREATE")
    else:
        assert principal is None


async def test_refresh_rotation_reuse_and_scope_narrowing(oauth_client, db_session):
    await login_user(db_session, oauth_client)
    client_id, verifier, callback, _ = await authorize_client(oauth_client, scope="wirecloud:read wirecloud:workspace:write")
    tokens = (await exchange(oauth_client, client_id, verifier, callback["code"])).json()
    form = {"client_id": client_id, "grant_type": "refresh_token", "resource": AUDIENCE,
        "refresh_token": tokens["refresh_token"], "scope": "wirecloud:read"}
    refreshed = await oauth_client.post("/oauth2/token", data=form)
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["scope"] == "wirecloud:read"
    assert (await oauth_client.post("/oauth2/token", data=form)).status_code == 400
    assert await delegated.verify_access_token(db_session, refreshed.json()["access_token"], AUDIENCE) is None


async def test_connection_revocation_is_csrf_and_user_protected(oauth_client, db_session):
    await login_user(db_session, oauth_client)
    client_id, verifier, callback, _ = await authorize_client(oauth_client)
    tokens = (await exchange(oauth_client, client_id, verifier, callback["code"])).json()
    principal = await delegated.verify_access_token(db_session, tokens["access_token"], AUDIENCE)
    forged = await oauth_client.post("/oauth2/connections", data={"grant_id": principal.grant_id, "csrf": "wrong"})
    assert forged.status_code == 403
    page = await oauth_client.get("/oauth2/connections")
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
    assert (await oauth_client.post("/oauth2/connections", data={"grant_id": principal.grant_id, "csrf": csrf})).status_code == 303
    assert await delegated.verify_access_token(db_session, tokens["access_token"], AUDIENCE) is None


async def test_modal_connections_json_is_user_scoped_and_csrf_protected(oauth_client, oauth_app, db_session):
    headers = {"Accept": "application/json"}
    assert (await oauth_client.get("/oauth2/connections", headers=headers)).status_code == 401
    await login_user(db_session, oauth_client)
    client_id, verifier, callback, _ = await authorize_client(oauth_client)
    tokens = (await exchange(oauth_client, client_id, verifier, callback["code"])).json()
    principal = await delegated.verify_access_token(db_session, tokens["access_token"], AUDIENCE)
    grant = await db_session.client.oauth_grants.find_one({"_id": principal.grant_id})
    await db_session.client.oauth_grants.insert_one({**grant, "_id": "another-users-grant", "user_id": "another-user"})
    page = await oauth_client.get("/oauth2/connections", headers=headers)
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store" and page.headers["vary"] == "Accept"
    data = page.json()
    assert data["connections"] == [{"id": principal.grant_id, "client_name": "Test AI", "client_id": client_id,
        "resource_name": "Test resource", "permissions": ["Read accessible data"], "scope_options": [
            {"scope": "wirecloud:read", "description": "Read accessible data", "selected": True},
            {"scope": "wirecloud:workspace:write", "description": "Edit workspaces", "selected": False},
        ]}]
    # Possessing a delegated access token cannot manage browser connections.
    async with AsyncClient(transport=ASGITransport(app=oauth_app), base_url="http://localhost") as other:
        assert (await other.get("/oauth2/connections", headers={**headers,
            "Authorization": "Bearer " + tokens["access_token"]})).status_code == 401
        assert (await other.post("/oauth2/connections", headers=headers,
            data={"csrf": data["csrf"], "grant_id": principal.grant_id})).status_code == 401
    assert (await oauth_client.post("/oauth2/connections", headers=headers,
        data={"csrf": "forged", "grant_id": principal.grant_id})).status_code == 403
    # Even a valid browser form cannot revoke another user's connection.
    assert (await oauth_client.post("/oauth2/connections", headers=headers,
        data={"csrf": data["csrf"], "grant_id": "another-users-grant"})).status_code == 200
    assert not (await db_session.client.oauth_grants.find_one({"_id": "another-users-grant"}))["revoked"]
    data = (await oauth_client.get("/oauth2/connections", headers=headers)).json()
    revoked = await oauth_client.post("/oauth2/connections", headers=headers,
        data={"csrf": data["csrf"], "grant_id": principal.grant_id})
    assert revoked.status_code == 200 and revoked.json() == {"revoked": True}
    assert "location" not in revoked.headers and revoked.headers["cache-control"] == "no-store"
    assert await delegated.verify_access_token(db_session, tokens["access_token"], AUDIENCE) is None
    assert (await oauth_client.get("/oauth2/connections", headers=headers)).json()["connections"] == []
    assert (await oauth_client.post("/oauth2/connections", headers=headers,
        data={"csrf": data["csrf"], "grant_id": principal.grant_id})).status_code == 403


async def test_provider_neutral_login_continuation(oauth_client, db_session, monkeypatch):
    from wirecloud.platform.plugins import URLTemplate
    monkeypatch.setattr(settings, "OID_CONNECT_ENABLED", True)
    monkeypatch.setattr(settings, "OID_CONNECT_PLUGIN", "future-provider")
    monkeypatch.setattr(routes, "get_idm_get_authorization_url_functions",
        lambda: {"future-provider": lambda: URLTemplate(urlpattern="https://identity.example/authorize?client_id=wc", defaults={})})
    async def exchange_provider(code, refresh_token, redirect_uri, login_context=None):
        return {}
    monkeypatch.setattr(routes, "get_idm_get_token_functions", lambda: {"future-provider": exchange_provider})
    response = await oauth_client.get("/auth/login", params={"return_to": "/oauth2/connections"})
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["state"][0].startswith("wc.") and query["code_challenge_method"] == ["S256"]
    from starlette.requests import Request
    scope = {"type": "http", "headers": [(b"cookie", ("wc_login_browser=" + oauth_client.cookies["wc_login_browser"]).encode())],
        "query_string": ("state=" + query["state"][0]).encode()}
    request = Request(scope)
    context = await auth_utils.consume_login_attempt(request, db_session)
    assert request.state.login_return_to == "/oauth2/connections"
    assert delegated.pkce(context["code_verifier"]) == query["code_challenge"][0]
    with pytest.raises(Exception, match="Invalid or expired login state"):
        await auth_utils.consume_login_attempt(request, db_session)
    assert (await oauth_client.get("/auth/login", params={"return_to": "//evil.example"})).status_code == 400


async def test_oidc_callback_rejects_missing_state(oauth_client, monkeypatch):
    monkeypatch.setattr(settings, "OID_CONNECT_ENABLED", True)
    monkeypatch.setattr(settings, "OID_CONNECT_PLUGIN", "future-provider")
    monkeypatch.setattr(routes, "get_idm_get_token_functions", lambda: {"future-provider": lambda **kwargs: {}})
    monkeypatch.setattr(routes, "get_idm_get_user_functions", lambda: {"future-provider": lambda **kwargs: {}})
    assert (await oauth_client.get("/oidc/callback", params={"code": "forged"})).status_code == 400


async def test_atomic_code_redemption(oauth_client, db_session):
    await login_user(db_session, oauth_client)
    client_id, verifier, callback, _ = await authorize_client(oauth_client)
    responses = await asyncio.gather(*(exchange(oauth_client, client_id, verifier, callback["code"]) for _ in range(2)))
    assert sorted(response.status_code for response in responses) == [200, 400]


async def test_complete_authorization_through_a_new_provider(oauth_client, db_session, monkeypatch):
    from wirecloud.platform.plugins import URLTemplate
    import wirecloud.platform.plugins as plugins
    monkeypatch.setattr(settings, "OID_CONNECT_ENABLED", True)
    monkeypatch.setattr(settings, "OID_CONNECT_PLUGIN", "another-provider")
    monkeypatch.setattr(settings, "OID_CONNECT_FULLY_SYNC_GROUPS", False)
    username = "future-" + delegated.random_token()
    contexts = []
    async def provider_token(code, refresh_token, redirect_uri, login_context):
        contexts.append(login_context)
        return {"refresh_token": "upstream-token", "session_state": "provider-session-" + username}
    async def provider_user(token_data):
        return {"preferred_username": username, "sub": "external-user", "email": "future@example.com"}
    token_hooks = {"another-provider": provider_token}
    monkeypatch.setattr(routes, "get_idm_get_authorization_url_functions",
        lambda: {"another-provider": lambda: URLTemplate(urlpattern="https://another.example/authorize", defaults={})})
    monkeypatch.setattr(plugins, "get_idm_get_token_functions", lambda: token_hooks)
    monkeypatch.setattr(routes, "get_idm_get_token_functions", lambda: token_hooks)
    monkeypatch.setattr(routes, "get_idm_get_user_functions", lambda: {"another-provider": provider_user})
    registration = (await oauth_client.post("/oauth2/register", json={"redirect_uris": ["http://127.0.0.1:9000/callback"]})).json()
    verifier = delegated.random_token()
    auth_response = await oauth_client.get("/oauth2/authorize", params={"client_id": registration["client_id"],
        "redirect_uri": "http://127.0.0.1:9000/callback", "resource": AUDIENCE, "scope": "wirecloud:read",
        "response_type": "code", "code_challenge_method": "S256", "code_challenge": delegated.pkce(verifier)})
    consent_url = auth_response.headers["location"]
    needs_login = await oauth_client.get(consent_url)
    assert "/auth/login?" in needs_login.headers["location"]
    upstream = await oauth_client.get(needs_login.headers["location"])
    state = parse_qs(urlsplit(upstream.headers["location"]).query)["state"][0]
    callback = await oauth_client.get("/oidc/callback", params={"code": "provider-code", "state": state})
    assert callback.status_code == 302, callback.text
    consent_page = await oauth_client.get(callback.headers["location"])
    assert username in consent_page.text
    form = {key: values[0] for key, values in parse_qs(urlsplit(consent_url).query).items()}
    approved = await oauth_client.post("/oauth2/consent", data={**form, "decision": "approve"})
    code = parse_qs(urlsplit(approved.headers["location"]).query)["code"][0]
    response = await exchange(oauth_client, registration["client_id"], verifier, code)
    assert response.status_code == 200, response.text
    principal = await delegated.verify_access_token(db_session, response.json()["access_token"], AUDIENCE)
    assert principal.user.username == username and len(contexts) == 1


async def test_local_login_continuation(oauth_client, db_session, monkeypatch):
    user, _ = await login_user(db_session, oauth_client)
    oauth_client.cookies.clear()
    start = await oauth_client.get("/auth/login", params={"return_to": "/oauth2/connections"})
    assert "/login?return_to=" in start.headers["location"]
    from wirecloud.commons import search
    from unittest.mock import AsyncMock
    monkeypatch.setattr(search, "es_client", AsyncMock())
    login = await oauth_client.post(start.headers["location"], json={"username": user.username, "password": "password"})
    assert login.status_code == 302, login.text
    assert login.headers["location"] == "/oauth2/connections"
    repeated = await oauth_client.post(start.headers["location"], json={"username": user.username, "password": "password"})
    assert repeated.status_code == 302 and repeated.headers["location"] == "/oauth2/connections"
    assert await db_session.client.login_attempts.count_documents({}) == 0


async def test_expired_code_and_scope_escalation(oauth_client, db_session):
    await login_user(db_session, oauth_client)
    client_id, verifier, callback, _ = await authorize_client(oauth_client)
    await db_session.client.oauth_codes.update_one({"_id": delegated.digest(callback["code"])},
        {"$set": {"expires_at": delegated.now() - timedelta(seconds=1)}})
    assert (await exchange(oauth_client, client_id, verifier, callback["code"])).status_code == 400
    client_id, verifier, callback, _ = await authorize_client(oauth_client)
    tokens = (await exchange(oauth_client, client_id, verifier, callback["code"])).json()
    escalated = await oauth_client.post("/oauth2/token", data={"client_id": client_id, "resource": AUDIENCE,
        "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "scope": "wirecloud:workspace:write"})
    assert escalated.status_code == 400 and escalated.json()["error"] == "invalid_scope"


async def test_confidential_client_requires_its_secret(oauth_client, db_session):
    registered = await oauth_client.post("/oauth2/register", json={"redirect_uris": ["https://client.example/callback"],
        "token_endpoint_auth_method": "client_secret_post"})
    client = registered.json()
    assert client.get("client_secret")
    record = await db_session.client.oauth_clients.find_one({"client_id": client["client_id"]})
    assert "client_secret" not in record and record["secret_hash"] == delegated.digest(client["client_secret"])
    rejected = await oauth_client.post("/oauth2/token", data={"client_id": client["client_id"], "grant_type": "authorization_code",
        "resource": AUDIENCE, "client_secret": "incorrect"})
    assert rejected.status_code == 401 and rejected.json()["error"] == "invalid_client"


def test_native_redirect_ports_and_remote_exact_matching():
    assert delegated.redirect_matches("http://127.0.0.1:9000/callback", "http://127.0.0.1:48563/callback")
    assert delegated.redirect_matches("http://[::1]:9000/callback", "http://[::1]:48563/callback")
    assert not delegated.redirect_matches("http://127.0.0.1:9000/callback", "http://127.0.0.1:48563/other")
    assert not delegated.redirect_matches("https://app.example/callback", "https://app.example:444/callback")
    assert not delegated.redirect_matches("https://app.example/callback", "https://other.example/callback")
    assert not delegated.valid_redirect("http://127.0.0.1:invalid/callback")


@pytest.mark.parametrize("address", ["93.184.216.34", "2606:4700::1111"])
async def test_metadata_client_authorization_with_pinned_tls(oauth_client, monkeypatch, address):
    """Exercise HTTPX/HTTPcore down to TLS without using the public network."""
    import json
    import socket
    from unittest.mock import AsyncMock

    import httpcore
    import httpx

    client_id = "https://client.example/oauth/client.json"
    document = json.dumps({"client_id": client_id, "client_name": "Test AI",
        "redirect_uris": ["http://127.0.0.1/callback"], "token_endpoint_auth_method": "none"}).encode()
    stream = AsyncMock(spec=httpcore.AsyncNetworkStream)
    stream.read.side_effect = [b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(document)).encode()
        + b"\r\nContent-Type: application/json\r\n\r\n" + document, b""]
    stream.get_extra_info.return_value = None

    async def start_tls(ssl_context, server_hostname, timeout):
        # Match the TLS backend's hostname contract, including certificate checks.
        assert isinstance(server_hostname, str)
        assert server_hostname == "client.example"
        assert ssl_context.check_hostname
        return stream

    stream.start_tls.side_effect = start_tls
    backend = AsyncMock(spec=httpcore.AsyncNetworkBackend)
    backend.connect_tcp.return_value = stream
    transport = httpx.AsyncHTTPTransport()
    transport._pool = httpcore.AsyncConnectionPool(network_backend=backend)
    client_class = httpx.AsyncClient
    monkeypatch.setattr(delegated.httpx, "AsyncClient", lambda **kwargs: client_class(transport=transport, **kwargs))
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    resolve = AsyncMock(return_value=[(family, socket.SOCK_STREAM, 6, "", (address, 443))])
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)

    response = await oauth_client.get("/oauth2/authorize", params={"client_id": client_id,
        "redirect_uri": "http://127.0.0.1:51389/callback", "resource": AUDIENCE, "scope": "wirecloud:read",
        "response_type": "code", "code_challenge_method": "S256", "code_challenge": delegated.pkce("x" * 43)})
    assert response.status_code == 302, response.text
    assert urlsplit(response.headers["location"]).path == "/oauth2/consent"
    resolve.assert_awaited_once_with("client.example", 443, type=socket.SOCK_STREAM)
    assert backend.connect_tcp.await_args.kwargs["host"] == address
    stream.start_tls.assert_awaited_once()
    request_bytes = b"".join(call.args[0] for call in stream.write.await_args_list)
    assert b"GET /oauth/client.json HTTP/1.1\r\n" in request_bytes
    assert b"Host: client.example\r\n" in request_bytes
