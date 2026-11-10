"""Configured machine clients retain WireCloud's live user permission checks."""
from datetime import timedelta
from typing import Any

import pytest
from fastapi import Request
from httpx import BasicAuth

from test_oauth import oauth_app, oauth_client, login_user, AUDIENCE
from wirecloud import settings
from wirecloud.commons.auth.crud import invalidate_token
from wirecloud.oauth2provider import require_access, service
from wirecloud.oauth2provider.validators import validate_oauth_settings


@pytest.fixture
async def machine_client(oauth_client, db_session, monkeypatch):
    user, session = await login_user(db_session, oauth_client)
    oauth_client.cookies.clear()
    client: dict[str, Any] = {
        "client_id": "automation", "client_name": "Automation",
        "grant_types": ["client_credentials"], "token_endpoint_auth_method": "client_secret_basic",
        "client_secret": "test-machine-secret", "service_user": user.username,
        "resource_scopes": {AUDIENCE: ["wirecloud:read", "wirecloud:workspace:write"]},
    }
    monkeypatch.setitem(vars(settings), "OAUTH2_CLIENTS", [client])
    return client, user, session


async def issue(client, config, **changes):
    data = {"grant_type": "client_credentials", "resource": AUDIENCE, **changes}
    if config["token_endpoint_auth_method"] == "client_secret_basic":
        return await client.post("/oauth2/token", data=data,
                                 auth=BasicAuth(config["client_id"], config["client_secret"]))
    return await client.post("/oauth2/token", data={
        "client_id": config["client_id"], "client_secret": config["client_secret"], **data,
    })


@pytest.mark.parametrize("method", ["client_secret_basic", "client_secret_post"])
async def test_machine_tokens_without_browser_session(oauth_client, oauth_app, db_session, machine_client, method):
    config, user, session = machine_client
    config["token_endpoint_auth_method"] = method
    await invalidate_token(db_session, session)
    response = await issue(oauth_client, config)
    assert response.status_code == 200, response.text
    tokens = response.json()
    assert set(tokens) == {"access_token", "token_type", "scope", "expires_in"}
    assert tokens["token_type"] == "Bearer" and 0 < tokens["expires_in"] <= 900
    assert tokens["scope"] == "wirecloud:read wirecloud:workspace:write"
    assert response.headers["cache-control"] == "no-store" and response.headers["pragma"] == "no-cache"
    token = tokens["access_token"]
    principal = await service.verify_access_token(db_session, token, AUDIENCE)
    assert principal.user.id == user.id and principal.session_id is None
    assert not principal.user.has_perm("EXAMPLE.VIEW")
    assert await service.verify_access_token(db_session, token, "http://localhost/other") is None
    record = await db_session.client.oauth_tokens.find_one({"_id": service.digest(token)})
    assert record["kind"] == "access" and "token" not in record
    assert await db_session.client.oauth_tokens.count_documents({"kind": "refresh"}) == 0
    request = Request({"type": "http", "app": oauth_app, "headers": [
        (b"authorization", ("Bearer " + token).encode()),
    ]})
    assert (await require_access(request, db_session, AUDIENCE, ("wirecloud:read",))).user.id == user.id
    metadata = (await oauth_client.get("/.well-known/oauth-authorization-server/oauth2")).json()
    assert "client_credentials" in metadata["grant_types_supported"]


@pytest.mark.parametrize(("changes", "error"), [
    ({"scope": ""}, "invalid_scope"), ({"scope": "unknown"}, "invalid_scope"),
    ({"resource": "http://localhost/unknown"}, "invalid_target"),
    ({"grant_type": "refresh_token", "refresh_token": "anything"}, "unauthorized_client"),
    ({"grant_type": "authorization_code"}, "unauthorized_client"),
])
async def test_machine_token_request_boundaries(oauth_client, db_session, machine_client, changes, error):
    config, _, _ = machine_client
    response = await issue(oauth_client, config, **changes)
    assert response.status_code == 400 and response.json()["error"] == error
    assert await db_session.client.oauth_tokens.count_documents({}) == 0


async def test_machine_resource_and_scope_allowlist(oauth_client, oauth_app, db_session, machine_client):
    config, _, _ = machine_client
    other = "http://localhost/other"
    service.register_resource(oauth_app, service.OAuthResource(other, {"other:read": "Read"}, "Other"))
    response = await issue(oauth_client, config, resource=other)
    assert response.status_code == 400 and response.json()["error"] == "invalid_target"
    config["resource_scopes"][AUDIENCE] = ["wirecloud:read"]
    response = await issue(oauth_client, config, scope="wirecloud:workspace:write")
    assert response.status_code == 400 and response.json()["error"] == "invalid_scope"
    config["resource_scopes"][AUDIENCE] = ["unregistered:scope"]
    response = await issue(oauth_client, config)
    assert response.status_code == 400 and response.json()["error"] == "invalid_scope"


@pytest.mark.parametrize("change", ["missing", "wrong", "method", "mixed", "conflicting_id"])
async def test_machine_authentication(oauth_client, machine_client, change):
    config, _, _ = machine_client
    data = {"grant_type": "client_credentials", "resource": AUDIENCE}
    auth = BasicAuth(config["client_id"], config["client_secret"])
    if change == "missing":
        auth = None
        data["client_id"] = config["client_id"]
    elif change == "wrong":
        auth = BasicAuth(config["client_id"], "wrong")
    elif change == "method":
        auth = None
        data.update(client_id=config["client_id"], client_secret=config["client_secret"])
    elif change == "mixed":
        data["client_secret"] = config["client_secret"]
    else:
        data["client_id"] = "another-client"
    response = await oauth_client.post("/oauth2/token", data=data, auth=auth)
    assert response.status_code == 401 and response.json()["error"] == "invalid_client"
    if auth:
        assert response.headers["www-authenticate"].startswith("Basic ")


async def test_public_registration_cannot_provision_machine_access(oauth_client):
    response = await oauth_client.post("/oauth2/register", json={
        "redirect_uris": ["https://client.example/cb"], "grant_types": ["client_credentials"],
        "token_endpoint_auth_method": "client_secret_post", "service_user": "admin",
        "resource_scopes": {AUDIENCE: ["wirecloud:read"]},
    })
    assert response.status_code == 400 and response.json()["error"] == "invalid_client_metadata"
    for method in ("none", "client_secret_post"):
        registered = (await oauth_client.post("/oauth2/register", json={
            "redirect_uris": ["https://client.example/cb"], "token_endpoint_auth_method": method,
        })).json()
        response = await oauth_client.post("/oauth2/token", data={
            "client_id": registered["client_id"], "client_secret": registered.get("client_secret", ""),
            "grant_type": "client_credentials", "resource": AUDIENCE,
        })
        assert response.status_code == 400 and response.json()["error"] == "unauthorized_client"


@pytest.mark.parametrize("change", ["removed", "secret", "binding", "inactive", "deleted", "expired", "renamed"])
async def test_machine_tokens_follow_live_policy(oauth_client, db_session, machine_client, monkeypatch, change):
    config, user, _ = machine_client
    token = (await issue(oauth_client, config)).json()["access_token"]
    if change == "removed":
        monkeypatch.setitem(vars(settings), "OAUTH2_CLIENTS", [])
    elif change == "secret":
        config["client_secret"] = "rotated-secret"
    elif change == "binding":
        config["service_user"] = "another-account"
    elif change == "inactive":
        await db_session.client.users.update_one({"_id": user.id}, {"$set": {"is_active": False}})
    elif change == "deleted":
        await db_session.client.users.delete_one({"_id": user.id})
    elif change == "renamed":
        await db_session.client.users.update_one({"_id": user.id}, {"$set": {"username": "renamed"}})
    else:
        await db_session.client.oauth_tokens.update_one({"_id": service.digest(token)}, {
            "$set": {"expires_at": service.now() - timedelta(seconds=1)},
        })
    assert await service.verify_access_token(db_session, token, AUDIENCE) is None


async def test_machine_scope_narrowing_is_preserved(oauth_client, db_session, machine_client):
    config, _, _ = machine_client
    token = (await issue(oauth_client, config, scope="wirecloud:read")).json()["access_token"]
    principal = await service.verify_access_token(db_session, token, AUDIENCE)
    assert principal.scopes == {"wirecloud:read"}
    config["resource_scopes"][AUDIENCE] = ["wirecloud:workspace:write"]
    assert await service.verify_access_token(db_session, token, AUDIENCE) is None


async def test_machine_permissions_are_live(oauth_client, db_session, machine_client):
    config, user, _ = machine_client
    token = (await issue(oauth_client, config)).json()["access_token"]
    await db_session.client.users.update_one({"_id": user.id}, {
        "$set": {"user_permissions": [{"codename": "EXAMPLE.VIEW"}]},
    })
    principal = await service.verify_access_token(db_session, token, AUDIENCE)
    assert principal.user.has_perm("EXAMPLE.VIEW")
    await db_session.client.users.update_one({"_id": user.id}, {"$set": {"user_permissions": []}})
    principal = await service.verify_access_token(db_session, token, AUDIENCE)
    assert not principal.user.has_perm("EXAMPLE.VIEW")


@pytest.mark.parametrize("available", [False, True])
async def test_machine_account_must_exist_and_be_active(oauth_client, db_session, machine_client, available):
    config, user, _ = machine_client
    if available:
        await db_session.client.users.update_one({"_id": user.id}, {"$set": {"is_active": False}})
    else:
        config["service_user"] = "missing-service-account"
    response = await issue(oauth_client, config)
    assert response.status_code == 400 and response.json()["error"] == "unauthorized_client"
    assert await db_session.client.oauth_tokens.count_documents({}) == 0


async def test_machine_scope_reduction_and_client_owned_revocation(oauth_client, db_session, machine_client):
    config, _, _ = machine_client
    token = (await issue(oauth_client, config)).json()["access_token"]
    config["resource_scopes"][AUDIENCE] = ["wirecloud:read"]
    principal = await service.verify_access_token(db_session, token, AUDIENCE)
    assert principal.scopes == {"wirecloud:read"}
    other = {**config, "client_id": "another-client"}
    config_list = getattr(settings, "OAUTH2_CLIENTS")
    config_list.append(other)
    response = await oauth_client.post("/oauth2/revoke", data={"token": token},
        auth=BasicAuth(other["client_id"], other["client_secret"]))
    assert response.status_code == 200
    assert await service.verify_access_token(db_session, token, AUDIENCE) is not None
    response = await oauth_client.post("/oauth2/revoke", data={"token": token},
        auth=BasicAuth(config["client_id"], config["client_secret"]))
    assert response.status_code == 200
    assert await service.verify_access_token(db_session, token, AUDIENCE) is None


def test_machine_openapi_contract(oauth_app):
    from fastapi.openapi.models import OpenAPI

    schema = oauth_app.openapi()
    OpenAPI.model_validate(schema)
    token = schema["paths"]["/oauth2/token"]["post"]
    form = token["requestBody"]["content"]["application/x-www-form-urlencoded"]
    assert "client_credentials" in form["schema"]["properties"]["grant_type"]["enum"]
    assert form["examples"]["client_credentials"]["value"]["grant_type"] == "client_credentials"
    response = token["responses"]["200"]["content"]["application/json"]["schema"]
    assert "access_token" in response["required"] and "refresh_token" not in response["required"]


async def test_machine_grants_cannot_be_edited_in_browser(oauth_client, db_session, machine_client):
    from wirecloud.oauth2provider import crud

    config, user, _ = machine_client
    token = (await issue(oauth_client, config)).json()["access_token"]
    principal = await service.verify_access_token(db_session, token, AUDIENCE)
    assert await crud.get_grants_for_user(db_session, str(user.id), service.now()) == []
    assert not await crud.update_grant_scopes(db_session, principal.grant_id, str(user.id),
                                             ["wirecloud:read"], service.now())
    await crud.revoke_grant(db_session, principal.grant_id, user_id=str(user.id))
    assert await service.verify_access_token(db_session, token, AUDIENCE) is not None
    response = await oauth_client.get("/oauth2/authorize", params={"client_id": config["client_id"], "resource": AUDIENCE})
    assert response.status_code == 400 and response.json()["error"] == "unauthorized_client"


@pytest.mark.parametrize("changes", [
    {"token_endpoint_auth_method": "none"}, {"client_secret": ""}, {"service_user": ""},
    {"resource_scopes": {}}, {"resource_scopes": {AUDIENCE: []}},
    {"resource_scopes": {AUDIENCE: ["has space"]}}, {"resource_scopes": {AUDIENCE: "read"}},
    {"grant_types": ["authorization_code", "client_credentials"]},
])
def test_invalid_machine_configuration(machine_client, changes):
    config, _, _ = machine_client
    configured = type("Config", (), {"OAUTH2_CLIENTS": [{**config, **changes}]})()
    with pytest.raises(service.OAuthError):
        validate_oauth_settings(configured)
