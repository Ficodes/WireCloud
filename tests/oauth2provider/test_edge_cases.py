"""Protocol failures and browser boundaries beyond the happy-path flow."""
import asyncio
import base64
import json
import socket
from contextlib import asynccontextmanager
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit, urlencode
from unittest.mock import AsyncMock

import httpx
import pytest

from oauth2provider.test_oauth import (
    oauth_app, oauth_client, login_user, authorize_client, exchange, AUDIENCE,
)
from wirecloud import settings
from wirecloud.oauth2provider import service


def metadata_transport(monkeypatch, document, addresses=("93.184.216.34",), status=200):
    response = httpx.Response(status, content=document,
        request=httpx.Request("GET", "https://client.example/client.json"))
    requests = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        @asynccontextmanager
        async def stream(self, *args, **kwargs):
            requests.append((args, kwargs))
            yield response

    monkeypatch.setattr(service.httpx, "AsyncClient", Client)
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", AsyncMock(return_value=[
        (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
        for address in addresses]))
    return requests


@pytest.mark.parametrize("document", [b"null", b"[]", b'"string"', b"42", b"{", b"x" * 65537])
async def test_bad_metadata_documents_are_protocol_errors(monkeypatch, document):
    metadata_transport(monkeypatch, document)
    with pytest.raises(service.OAuthError) as error:
        await service.metadata_client("https://client.example/client.json")
    assert error.value.status_code == 400
    assert error.value.detail["error"] == "invalid_client"


@pytest.mark.parametrize("addresses", [("127.0.0.1",), ("10.0.0.1",), ("::1",),
    ("169.254.169.254",), ("93.184.216.34", "192.168.1.1")])
async def test_metadata_cannot_fetch_private_or_mixed_dns_addresses(monkeypatch, addresses):
    requests = metadata_transport(monkeypatch, b"{}", addresses)
    with pytest.raises(service.OAuthError):
        await service.metadata_client("https://client.example/client.json")
    assert requests == []


async def test_metadata_redirects_are_not_followed(monkeypatch):
    requests = metadata_transport(monkeypatch, b"", status=302)
    with pytest.raises(service.OAuthError):
        await service.metadata_client("https://client.example/client.json")
    assert len(requests) == 1


async def test_disabling_registration_preserves_existing_clients(oauth_client, db_session, monkeypatch):
    await login_user(db_session, oauth_client)
    client_id, verifier, callback, _ = await authorize_client(oauth_client)
    monkeypatch.setattr(settings, "OAUTH2_DYNAMIC_REGISTRATION", False)
    discovery = (await oauth_client.get("/.well-known/oauth-authorization-server/oauth2")).json()
    assert "registration_endpoint" not in discovery
    assert (await oauth_client.post("/oauth2/register", json={"redirect_uris": ["https://app.example/callback"]})).status_code == 404
    assert (await exchange(oauth_client, client_id, verifier, callback["code"])).status_code == 200


async def test_registration_request_limit_and_invalid_shapes(oauth_client, db_session):
    for document in (None, [], {"redirect_uris": []}, {"redirect_uris": ["http://external.example/callback"]}):
        result = await oauth_client.post("/oauth2/register", content=json.dumps(document),
            headers={"Content-Type": "application/json"})
        assert result.status_code == 400
    oversized = await oauth_client.post("/oauth2/register", content=b" " * 65537)
    assert oversized.status_code == 400
    # Start a clean observed-IP bucket after exercising malformed requests.
    await db_session.client.oauth_attempts.delete_many({"_id": {"$regex": "^registration:"}})
    for _ in range(60):
        assert (await oauth_client.post("/oauth2/register", json={"redirect_uris": ["https://app.example/callback"]})).status_code == 201
    assert (await oauth_client.post("/oauth2/register", json={"redirect_uris": ["https://app.example/callback"]})).status_code == 429


@pytest.mark.parametrize("scheme", ["Basic", "basic", "BASIC"])
async def test_configured_confidential_client_can_authorize_refresh_and_revoke(oauth_client, db_session, monkeypatch, scheme):
    await login_user(db_session, oauth_client)
    client_id, secret = "configured:client", "private:secret"
    monkeypatch.setattr(settings, "OAUTH2_CLIENTS", [{"client_id": client_id, "client_name": "Configured client",
        "redirect_uris": ["https://app.example/callback"], "token_endpoint_auth_method": "client_secret_basic", "client_secret": secret}], raising=False)
    monkeypatch.setattr(settings, "OAUTH2_DYNAMIC_REGISTRATION", False)
    verifier = service.random_token()
    start = await oauth_client.get("/oauth2/authorize", params={"client_id": client_id,
        "redirect_uri": "https://app.example/callback", "resource": AUDIENCE, "scope": "wirecloud:read",
        "response_type": "code", "code_challenge_method": "S256", "code_challenge": service.pkce(verifier)})
    assert start.status_code == 302
    assert (await oauth_client.get(start.headers["location"])).status_code == 200
    form = {key: value[0] for key, value in parse_qs(urlsplit(start.headers["location"]).query).items()}
    consent = await oauth_client.post("/oauth2/consent", data={**form, "decision": "approve"})
    code = parse_qs(urlsplit(consent.headers["location"]).query)["code"][0]
    # RFC 6749 Basic credentials are individually form-encoded before base64.
    credentials = base64.b64encode((urlencode({"x": client_id})[2:] + ":" + urlencode({"x": secret})[2:]).encode()).decode()
    headers = {"Authorization": scheme + " " + credentials}
    token = await oauth_client.post("/oauth2/token", headers=headers, data={"grant_type": "authorization_code",
        "code": code, "code_verifier": verifier, "resource": AUDIENCE, "redirect_uri": "https://app.example/callback"})
    assert token.status_code == 200, token.text
    tokens = token.json()
    refreshed = await oauth_client.post("/oauth2/token", headers=headers, data={"grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"], "resource": AUDIENCE})
    assert refreshed.status_code == 200
    revoked = await oauth_client.post("/oauth2/revoke", headers=headers, data={"token": refreshed.json()["refresh_token"]})
    assert revoked.status_code == 200
    assert await service.verify_access_token(db_session, tokens["access_token"], AUDIENCE) is None
    assert await service.verify_access_token(db_session, refreshed.json()["access_token"], AUDIENCE) is None
    assert (await oauth_client.post("/oauth2/revoke", headers=headers, data={"token": "unknown"})).status_code == 200


@pytest.mark.parametrize("prefix", ["", "/platform"])
@pytest.mark.parametrize("endpoint", ["token", "register", "revoke"])
async def test_public_oauth_cors_with_deployment_prefix(oauth_app, prefix, endpoint):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=oauth_app, root_path=prefix),
            base_url="http://localhost") as client:
        headers = {"Origin": "https://client.example", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization"}
        response = await client.options(prefix + "/oauth2/" + endpoint, headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers["access-control-allow-origin"] == "*"
        assert "access-control-allow-credentials" not in response.headers
        # Interactive pages must not inherit public-protocol CORS.
        consent = await client.options(prefix + "/oauth2/consent", headers=headers)
        assert "access-control-allow-origin" not in consent.headers


async def test_consent_cannot_authorize_a_different_account_than_the_page(oauth_client, db_session):
    await login_user(db_session, oauth_client)
    # A fresh pending consent page, displayed before another tab changes account.
    registration = (await oauth_client.post("/oauth2/register", json={"redirect_uris": ["https://app.example/callback"]})).json()
    start = await oauth_client.get("/oauth2/authorize", params={"client_id": registration["client_id"],
        "redirect_uri": "https://app.example/callback", "resource": AUDIENCE, "scope": "wirecloud:read",
        "response_type": "code", "code_challenge_method": "S256", "code_challenge": service.pkce("x" * 43)})
    assert (await oauth_client.get(start.headers["location"])).status_code == 200
    form = {key: value[0] for key, value in parse_qs(urlsplit(start.headers["location"]).query).items()}
    await login_user(db_session, oauth_client)
    result = await oauth_client.post("/oauth2/consent", data={**form, "decision": "approve"})
    assert result.status_code in (400, 403), result.text
    assert "code=" not in result.headers.get("location", "")


async def test_expired_access_token_can_refresh_but_revoked_grant_cannot(oauth_client, db_session):
    await login_user(db_session, oauth_client)
    client_id, verifier, callback, _ = await authorize_client(oauth_client)
    tokens = (await exchange(oauth_client, client_id, verifier, callback["code"])).json()
    await db_session.client.oauth_tokens.update_one({"_id": service.digest(tokens["access_token"])},
        {"$set": {"expires_at": service.now() - timedelta(seconds=1)}})
    assert await service.verify_access_token(db_session, tokens["access_token"], AUDIENCE) is None
    response = await oauth_client.post("/oauth2/token", data={"client_id": client_id, "resource": AUDIENCE,
        "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    refreshed = response.json()
    assert await service.verify_access_token(db_session, refreshed["access_token"], AUDIENCE) is not None
    await oauth_client.post("/oauth2/revoke", data={"client_id": client_id, "token": refreshed["access_token"]})
    assert (await oauth_client.post("/oauth2/token", data={"client_id": client_id, "resource": AUDIENCE,
        "grant_type": "refresh_token", "refresh_token": refreshed["refresh_token"]})).status_code == 400
