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

from datetime import datetime, timedelta
from typing import Collection

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from lxml import html

from oauth2provider.test_oauth import oauth_app, oauth_client, login_user, authorize_client, exchange, AUDIENCE
from wirecloud.database import DBSession
from wirecloud.oauth2provider import crud, service

READ = "wirecloud:read"
WRITE = "wirecloud:workspace:write"
HEADERS = {"Accept": "application/json"}


async def test_unknown_connection_action_does_not_consume_csrf_or_change_access(
    oauth_client: AsyncClient, db_session: DBSession, connection: dict[str, str]
) -> None:
    page = (await oauth_client.get("/oauth2/connections", headers=HEADERS)).json()
    form = {"csrf": page["csrf"], "grant_id": connection["grant_id"], "action": "unknown", "scope": WRITE}
    response = await oauth_client.post("/oauth2/connections", headers=HEADERS, data=form)
    assert response.status_code == 400 and response.json()["detail"] == "Unknown connection action"
    principal = await service.verify_access_token(db_session, connection["access_token"], AUDIENCE)
    assert principal.scopes == {READ}
    response = await oauth_client.post("/oauth2/connections", headers=HEADERS, data={**form, "action": "update_permissions"})
    assert response.status_code == 200


async def test_permission_edit_cannot_restore_a_connection_revoked_during_the_request(
    oauth_client: AsyncClient, db_session: DBSession, connection: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    update = crud.update_grant_scopes

    async def revoked_before_update(
        db: DBSession, grant_id: str, user_id: str, scopes: list[str], current_time: datetime
    ) -> bool:
        await crud.revoke_grant(db, grant_id)
        return await update(db, grant_id, user_id, scopes, current_time)

    monkeypatch.setattr(crud, "update_grant_scopes", revoked_before_update)
    response = await save_permissions(oauth_client, connection["grant_id"], [WRITE])
    assert response.status_code == 404
    grant = await db_session.client.oauth_grants.find_one({"_id": connection["grant_id"]})
    assert grant["revoked"] and grant["scopes"] == [READ]
    assert await service.verify_access_token(db_session, connection["access_token"], AUDIENCE) is None


@pytest.fixture
async def connection(oauth_client: AsyncClient, db_session: DBSession) -> dict[str, str]:
    await login_user(db_session, oauth_client)
    client_id, verifier, callback, _ = await authorize_client(oauth_client)
    tokens = (await exchange(oauth_client, client_id, verifier, callback["code"])).json()
    principal = await service.verify_access_token(db_session, tokens["access_token"], AUDIENCE)
    return {
        "client_id": client_id, "grant_id": principal.grant_id,
        "access_token": tokens["access_token"], "refresh_token": tokens["refresh_token"],
    }


async def save_permissions(client: AsyncClient, grant_id: str, scopes: Collection[str]) -> Response:
    page = (await client.get("/oauth2/connections", headers=HEADERS)).json()
    return await client.post("/oauth2/connections", headers=HEADERS, data={
        "csrf": page["csrf"], "grant_id": grant_id, "action": "update_permissions", "scope": " ".join(scopes),
    })


async def test_permission_edits_immediately_update_access_and_refresh_tokens(
    oauth_client: AsyncClient, db_session: DBSession, connection: dict[str, str]
) -> None:
    response = await save_permissions(oauth_client, connection["grant_id"], [READ, WRITE])
    assert response.status_code == 200 and response.json() == {"updated": True}
    assert response.headers["cache-control"] == "no-store" and response.headers["vary"] == "Accept"
    principal = await service.verify_access_token(db_session, connection["access_token"], AUDIENCE)
    assert principal.scopes == {READ, WRITE}

    refreshed = await oauth_client.post("/oauth2/token", data={
        "client_id": connection["client_id"], "grant_type": "refresh_token", "resource": AUDIENCE,
        "refresh_token": connection["refresh_token"],
    })
    assert refreshed.status_code == 200
    tokens = refreshed.json()
    assert set(tokens["scope"].split()) == {READ, WRITE}
    assert (await save_permissions(oauth_client, connection["grant_id"], [READ])).status_code == 200
    for access in (connection["access_token"], tokens["access_token"]):
        assert (await service.verify_access_token(db_session, access, AUDIENCE)).scopes == {READ}
    form = {
        "client_id": connection["client_id"], "grant_type": "refresh_token", "resource": AUDIENCE,
        "refresh_token": tokens["refresh_token"],
    }
    assert (await oauth_client.post("/oauth2/token", data={**form, "scope": WRITE})).status_code == 400
    narrowed = await oauth_client.post("/oauth2/token", data=form)
    assert narrowed.status_code == 200 and narrowed.json()["scope"] == READ


async def test_client_scope_narrowing_is_preserved_until_an_explicit_browser_edit(
    oauth_client: AsyncClient, db_session: DBSession, connection: dict[str, str]
) -> None:
    await save_permissions(oauth_client, connection["grant_id"], [READ, WRITE])
    response = await oauth_client.post("/oauth2/token", data={
        "client_id": connection["client_id"], "grant_type": "refresh_token", "resource": AUDIENCE,
        "refresh_token": connection["refresh_token"], "scope": READ,
    })
    assert response.status_code == 200
    tokens = response.json()
    assert (await service.verify_access_token(db_session, tokens["access_token"], AUDIENCE)).scopes == {READ}
    increased = await oauth_client.post("/oauth2/token", data={
        "client_id": connection["client_id"], "grant_type": "refresh_token", "resource": AUDIENCE,
        "refresh_token": tokens["refresh_token"], "scope": WRITE,
    })
    assert increased.status_code == 400
    assert (await save_permissions(oauth_client, connection["grant_id"], [WRITE])).status_code == 200
    assert (await service.verify_access_token(db_session, tokens["access_token"], AUDIENCE)).scopes == {WRITE}


@pytest.mark.parametrize("scope", ["", "unknown", READ + " unknown"])
async def test_permission_edits_reject_empty_or_unknown_scopes(
    oauth_client: AsyncClient, db_session: DBSession, connection: dict[str, str], scope: str
) -> None:
    response = await save_permissions(oauth_client, connection["grant_id"], scope.split())
    assert response.status_code == 400
    grant = await db_session.client.oauth_grants.find_one({"_id": connection["grant_id"]})
    assert grant["scopes"] == [READ] and grant.get("scope_version", 0) == 0


@pytest.mark.parametrize("state", ["other_user", "expired", "revoked", "missing"])
async def test_permission_edits_require_a_current_owned_connection(
    oauth_client: AsyncClient, db_session: DBSession, connection: dict[str, str], state: str
) -> None:
    changes = {
        "other_user": {"user_id": "other-user"},
        "expired": {"expires_at": service.now() - timedelta(seconds=1)},
        "revoked": {"revoked": True},
        "missing": {},
    }
    if state == "missing":
        await db_session.client.oauth_grants.delete_one({"_id": connection["grant_id"]})
    else:
        await db_session.client.oauth_grants.update_one(
            {"_id": connection["grant_id"]}, {"$set": changes[state]}
        )
    response = await save_permissions(oauth_client, connection["grant_id"], [READ, WRITE])
    assert response.status_code == 404
    grant = await db_session.client.oauth_grants.find_one({"_id": connection["grant_id"]})
    assert grant is None or grant["scopes"] == [READ]


async def test_permission_edits_require_browser_identity_and_one_time_csrf(
    oauth_app: FastAPI, oauth_client: AsyncClient, db_session: DBSession, connection: dict[str, str]
) -> None:
    page = (await oauth_client.get("/oauth2/connections", headers=HEADERS)).json()
    form = {"csrf": page["csrf"], "grant_id": connection["grant_id"], "action": "update_permissions", "scope": WRITE}
    async with AsyncClient(transport=ASGITransport(app=oauth_app), base_url="http://localhost") as other:
        response = await other.post("/oauth2/connections", headers={
            **HEADERS, "Authorization": "Bearer " + connection["access_token"],
        }, data=form)
        assert response.status_code == 401
        other.cookies.set("token", oauth_client.cookies["token"])
        assert (await other.post("/oauth2/connections", headers=HEADERS, data=form)).status_code == 403
    assert (await oauth_client.post("/oauth2/connections", headers=HEADERS, data={**form, "csrf": "wrong"})).status_code == 403
    assert (await oauth_client.post("/oauth2/connections", headers=HEADERS, data=form)).status_code == 200
    assert (await oauth_client.post("/oauth2/connections", headers=HEADERS, data=form)).status_code == 403


async def test_permission_edits_expired_csrf_and_other_connections_are_unchanged(
    oauth_client: AsyncClient, db_session: DBSession, connection: dict[str, str]
) -> None:
    grant = await db_session.client.oauth_grants.find_one({"_id": connection["grant_id"]})
    await db_session.client.oauth_grants.insert_one({**grant, "_id": "other-connection"})
    page = (await oauth_client.get("/oauth2/connections", headers=HEADERS)).json()
    await db_session.client.oauth_attempts.update_one(
        {"_id": service.digest(page["csrf"])}, {"$set": {"expires_at": service.now() - timedelta(seconds=1)}}
    )
    response = await oauth_client.post("/oauth2/connections", headers=HEADERS, data={
        "csrf": page["csrf"], "grant_id": connection["grant_id"], "action": "update_permissions", "scope": WRITE,
    })
    assert response.status_code == 403
    assert (await save_permissions(oauth_client, connection["grant_id"], [WRITE])).status_code == 200
    other = await db_session.client.oauth_grants.find_one({"_id": "other-connection"})
    assert other["scopes"] == [READ] and other.get("scope_version", 0) == 0


async def test_standalone_connections_form_lists_and_saves_permission_choices(
    oauth_client: AsyncClient, connection: dict[str, str]
) -> None:
    page = await oauth_client.get("/oauth2/connections")
    document = html.fromstring(page.text)
    form = document.xpath("//form[.//input[@name='grant_id']]")[0]
    options = form.xpath(".//input[@name='scope']")
    assert [option.get("value") for option in options] == [READ, WRITE]
    assert [option.get("value") for option in options if option.get("checked") is not None] == [READ]
    assert form.xpath(".//button[@name='action' and @value='update_permissions']")
    response = await oauth_client.post("/oauth2/connections", data={
        "csrf": form.xpath(".//input[@name='csrf']/@value")[0], "grant_id": connection["grant_id"],
        "action": "update_permissions", "scope": [READ, WRITE],
    })
    assert response.status_code == 303 and response.headers["location"] == "/oauth2/connections"
    saved = html.fromstring((await oauth_client.get(response.headers["location"])).text)
    assert saved.xpath("//input[@name='scope' and @checked]/@value") == [READ, WRITE]
