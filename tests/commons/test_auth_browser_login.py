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


from datetime import timedelta
from typing import Any, AsyncIterator, Awaitable, Callable
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
import jwt
from asgi_lifespan import LifespanManager
from fastapi import FastAPI, Request, Response
from httpx import ASGITransport, AsyncClient
from lxml import html

from wirecloud import settings
from wirecloud.commons import search, urls
from wirecloud.commons.auth import crud, routes, tokens
from wirecloud.commons.auth.models import DBUser, DBLoginAttempt
from wirecloud.commons.auth.schemas import UserCreate
from wirecloud.commons.auth.utils import hash_password
from wirecloud.database import DBSession, Id, get_session
from wirecloud.platform.plugins import URLTemplate


@pytest.fixture
async def browser_client(
    db_session: DBSession, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(routes.base_router)
    app.include_router(routes.router, prefix="/api/auth")
    prefix = getattr(request, "param", "")
    monkeypatch.setattr(settings, "OID_CONNECT_ENABLED", False)
    monkeypatch.setattr(settings, "AUTH_PUBLIC_URL", "http://localhost:8000", raising=False)
    monkeypatch.setattr(settings, "JWT_KEY", "browser-login-regression-signing-key-at-least-32-bytes")
    monkeypatch.setattr(search, "es_client", AsyncMock())
    await db_session.client.login_attempts.delete_many({})

    @app.middleware("http")
    async def language_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request.state.lang = "en"
        return await call_next(request)

    async def session() -> AsyncIterator[DBSession]:
        yield db_session

    app.dependency_overrides[get_session] = session
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, root_path=prefix), base_url="http://127.0.0.1:8000"
        ) as client:
            yield client


@pytest.fixture
async def website_user(db_session: DBSession) -> DBUser:
    return await crud.create_user_db(db_session, UserCreate(
        username="website-" + tokens.random_token(), password=hash_password("password"),
        email="website@example.com", first_name="", last_name="",
        is_superuser=False, is_staff=False, is_active=True, idm_data={},
    ))


@pytest.mark.parametrize("browser_client", ["", "/wirecloud"], indirect=True)
async def test_normal_local_login_preserves_the_visited_origin_and_return_path_without_oidc_state(
    browser_client: AsyncClient, website_user: DBUser, db_session: DBSession,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = browser_client._transport.root_path
    target = prefix + "/workspace/alice/dashboard?mode=classic"
    assert urls.get_urlpatterns()["login"].urlpattern == "/login"
    start = await browser_client.get(prefix + "/auth/login", params={"return_to": target})
    assert start.status_code == 302
    destination = urlsplit(start.headers["location"])
    assert destination.hostname == "127.0.0.1" and destination.path == prefix + "/login"
    assert parse_qs(destination.query) == {"return_to": [target]}
    assert "wc_login_browser" not in browser_client.cookies
    assert await db_session.client.login_attempts.count_documents({}) == 0
    page = await browser_client.get(start.headers["location"])
    assert page.status_code == 200 and html.fromstring(page.text).xpath("//form[@method='post']")
    later = tokens.now() + timedelta(hours=1)
    monkeypatch.setattr(tokens, "now", lambda: later)
    for _ in range(2):
        response = await browser_client.post(start.headers["location"], data={
            "username": website_user.username, "password": "password",
        })
        assert response.status_code == 302 and response.headers["location"] == target
        assert "token" in response.cookies


@pytest.mark.parametrize("continuation", ["", "?continue=wc.deleted", "?continue=wc.expired"])
async def test_normal_login_accepts_credentials_with_no_pending_or_stale_continuation(
    browser_client: AsyncClient, website_user: DBUser, continuation: str, db_session: DBSession
) -> None:
    response = await browser_client.post("/login" + continuation, data={
        "username": website_user.username, "password": "password",
    })
    assert response.status_code == 302
    assert urlsplit(response.headers["location"]).path == "/"
    assert "token" in response.cookies
    assert await db_session.client.login_attempts.count_documents({}) == 0
    assert (await browser_client.get("/oauth2/connections")).status_code == 404


async def test_local_login_keeps_invalid_credentials_on_the_normal_form(
    browser_client: AsyncClient, website_user: DBUser
) -> None:
    response = await browser_client.post("/login?continue=wc.deleted", data={
        "username": website_user.username, "password": "wrong",
    })
    assert response.status_code == 200 and "didn't match" in response.text
    assert "token" not in response.cookies


@pytest.mark.parametrize("encoding", ["form", "json"])
async def test_api_login_keeps_its_token_contract_separate_from_browser_login(
    browser_client: AsyncClient, website_user: DBUser, db_session: DBSession, encoding: str
) -> None:
    credentials = {"username": website_user.username, "password": "password"}
    arguments = {"data" if encoding == "form" else "json": credentials}
    response = await browser_client.post("/api/auth/login", **arguments)
    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer" and "token" not in response.cookies
    claims = jwt.decode(payload["access_token"], settings.JWT_KEY, algorithms=["HS256"], issuer="Wirecloud")
    assert claims["sub"] == str(website_user.id) and claims["csrf_required"] is False
    stored = await db_session.client.tokens.find_one({"_id": Id(claims["jti"])})
    assert stored["valid"] and stored["user_id"] == website_user.id
    denied = await browser_client.post("/api/auth/login", data={**credentials, "password": "incorrect"})
    assert denied.status_code == 401 and "access_token" not in denied.text


@pytest.mark.parametrize("path", ["/api/auth/login", "/login"])
async def test_malformed_login_data_is_a_validation_error(browser_client: AsyncClient, path: str) -> None:
    response = await browser_client.post(path, content="invalid-json", headers={
        "Content-Type": "application/json", "Accept": "application/json",
    })
    assert response.status_code == 422 and "token" not in response.cookies


async def test_local_login_works_without_an_identity_provider_setting(
    browser_client: AsyncClient, website_user: DBUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "OID_CONNECT_PLUGIN", None)
    response = await browser_client.post("/login", data={"username": website_user.username, "password": "password"})
    assert response.status_code == 302 and "token" in response.cookies


@pytest.mark.parametrize("target", ["//evil.example", "https://evil.example", "/\\evil", "/\ninvalid"])
async def test_local_login_rejects_external_or_malformed_return_destinations_before_creating_a_session(
    browser_client: AsyncClient, website_user: DBUser, db_session: DBSession, target: str
) -> None:
    before = await db_session.client.tokens.count_documents({"user_id": website_user.id})
    response = await browser_client.post("/login", params={"return_to": target}, data={
        "username": website_user.username, "password": "password",
    })
    assert response.status_code == 400 and response.json()["detail"] == "Invalid login return destination"
    assert "token" not in response.cookies
    assert await db_session.client.tokens.count_documents({"user_id": website_user.id}) == before


@pytest.mark.parametrize("failure", ["expired", "wrong_browser"])
async def test_oidc_callbacks_still_require_a_live_browser_bound_attempt(
    browser_client: AsyncClient, db_session: DBSession, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    monkeypatch.setattr(settings, "OID_CONNECT_ENABLED", True)
    monkeypatch.setattr(settings, "OID_CONNECT_PLUGIN", "provider")
    contexts = []

    def authorization(login_context: dict[str, Any]) -> URLTemplate:
        contexts.append(login_context)
        return URLTemplate(urlpattern="https://identity.example/authorize?client_id=wc", defaults={})

    exchange = AsyncMock()
    monkeypatch.setattr(routes, "get_idm_get_authorization_url_functions", lambda: {"provider": authorization})
    monkeypatch.setattr(routes, "get_idm_get_token_functions", lambda: {"provider": exchange})
    monkeypatch.setattr(routes, "get_idm_get_user_functions", lambda: {"provider": AsyncMock()})
    assert urls.get_urlpatterns()["login"].urlpattern == "/auth/login"
    start = await browser_client.get("/auth/login", params={"return_to": "/workspace/alice/dashboard"})
    query = parse_qs(urlsplit(start.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    stored = await db_session.client.login_attempts.find_one({"_id": tokens.digest(query["state"][0])})
    attempt = DBLoginAttempt.model_validate(stored)
    assert attempt.return_to == "/workspace/alice/dashboard"
    assert attempt.nonce == query["nonce"][0] and contexts[0]["nonce"] == attempt.nonce
    if failure == "expired":
        await db_session.client.login_attempts.update_one(
            {"_id": attempt.id}, {"$set": {"expires_at": tokens.now() - timedelta(seconds=1)}}
        )
    else:
        browser_client.cookies.clear()
    response = await browser_client.get("/oidc/callback", params={"state": attempt.state, "code": "code"})
    assert response.status_code == 400 and response.json()["detail"] == "Invalid or expired login state"
    exchange.assert_not_awaited()
    indexes = await db_session.client.login_attempts.index_information()
    assert indexes["expires_at_1"]["expireAfterSeconds"] == 0
