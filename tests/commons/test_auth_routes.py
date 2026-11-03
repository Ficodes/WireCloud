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

from datetime import datetime, timezone
from types import SimpleNamespace
import sys

import pytest
from bson import ObjectId
from fastapi.responses import Response
from httpx import ASGITransport, AsyncClient

from wirecloud import settings
from wirecloud.commons.auth import routes, utils
from wirecloud.commons.auth.models import Group
from wirecloud.commons.auth.schemas import Permission, Session, UserAll, UserTokenType, UserWithPassword
from wirecloud.database import Id
from wirecloud.main import app


class _CallRecorder:
    def __init__(self):
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))


async def _noop(*_args, **_kwargs):
    return None


async def _oid(*_args, **_kwargs):
    return Id(str(ObjectId()))


def _user_with_password(username="alice", active=True):
    return UserWithPassword(
        id=Id(str(ObjectId())),
        username=username,
        password="hash",
        email=f"{username}@example.com",
        first_name="A",
        last_name="B",
        is_superuser=False,
        is_staff=False,
        is_active=active,
        date_joined=datetime.now(timezone.utc),
        last_login=None,
        idm_data={"keycloak": {"idm_token": "r1"}},
    )


def _user_all(username="alice", active=True, perms=None):
    return UserAll(
        id=Id(str(ObjectId())),
        username=username,
        email=f"{username}@example.com",
        first_name="First",
        last_name="Last",
        is_superuser=False,
        is_staff=False,
        is_active=active,
        date_joined=datetime.now(timezone.utc),
        last_login=None,
        idm_data={"keycloak": {"idm_token": "r1"}},
        groups=[],
        permissions=perms or [],
    )


def _admin_user():
    user = _user_all("admin", perms=[])
    user.is_superuser = True
    return user


def _set_auth_user(user):
    async def _dep():
        return user

    app.dependency_overrides[utils.get_user_csrf] = _dep


def _common_patches(monkeypatch):
    monkeypatch.setattr(routes, "_", lambda text: text)
    monkeypatch.setattr(routes, "build_error_response", lambda _r, status, _msg: Response(status_code=status))
    # These tests exercise identity provisioning after the browser state check.
    # Real state validation and replay rejection are covered in oauth2provider/test_oauth.py.
    async def _validated_login(*_args):
        return {}
    monkeypatch.setattr(routes, "consume_login_attempt", _validated_login)


@pytest.fixture()
async def app_http_client(db_session):
    from wirecloud.database import get_session

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def test_oidc_login_error_paths_http(app_http_client, monkeypatch):
    _common_patches(monkeypatch)

    monkeypatch.setattr(settings, "OID_CONNECT_ENABLED", False)
    assert (await app_http_client.get("/oidc/callback", params={"code": "abc"})).status_code == 400

    monkeypatch.setattr(settings, "OID_CONNECT_ENABLED", True)
    monkeypatch.setattr(settings, "OID_CONNECT_PLUGIN", "keycloak")
    monkeypatch.setattr(routes, "get_idm_get_token_functions", lambda: {})
    assert (await app_http_client.get("/oidc/callback", params={"code": "abc"})).status_code == 500

    monkeypatch.setattr(routes, "get_idm_get_token_functions", lambda: {"keycloak": lambda **_k: {}})
    monkeypatch.setattr(routes, "get_idm_get_user_functions", lambda: {})
    assert (await app_http_client.get("/oidc/callback", params={"code": "abc"})).status_code == 500

    async def _boom(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(routes, "get_idm_get_token_functions", lambda: {"keycloak": _boom})
    monkeypatch.setattr(routes, "get_idm_get_user_functions", lambda: {"keycloak": lambda **_k: {"preferred_username": "a"}})
    monkeypatch.setattr(routes, "get_absolute_reverse_url", lambda *_args, **_kwargs: "http://cb")
    assert (await app_http_client.get("/oidc/callback", params={"code": "abc"})).status_code == 502


async def test_oidc_login_success_branches_http(app_http_client, monkeypatch):
    _common_patches(monkeypatch)
    monkeypatch.setattr(settings, "OID_CONNECT_ENABLED", True)
    monkeypatch.setattr(settings, "OID_CONNECT_PLUGIN", "keycloak")
    monkeypatch.setattr(settings, "OID_CONNECT_FULLY_SYNC_GROUPS", True)

    monkeypatch.setattr(routes, "get_absolute_reverse_url", lambda *_args, **_kwargs: "http://cb")
    monkeypatch.setattr(routes, "get_redirect_response", lambda _r: Response(status_code=302))
    monkeypatch.setattr(routes, "commit", _noop)

    created = _CallRecorder()
    updated = _CallRecorder()
    group_created = _CallRecorder()
    grouped = _CallRecorder()
    removed_groups = _CallRecorder()

    monkeypatch.setattr(routes, "create_user_db", created)
    monkeypatch.setattr(routes, "update_user", updated)
    monkeypatch.setattr(routes, "create_group_if_not_exists", group_created)
    monkeypatch.setattr(routes, "add_user_to_groups_by_codename", grouped)
    monkeypatch.setattr(routes, "remove_user_from_all_groups", removed_groups)
    monkeypatch.setattr(routes, "set_login_date_for_user", _noop)
    monkeypatch.setattr(routes, "create_token", _oid)

    token_data = {"refresh_token": "r1", "session_state": "s1"}
    user_data = {
        "preferred_username": "oidcuser",
        "given_name": "OIDC",
        "family_name": "User",
        "email": "oidc@example.com",
        "sub": "sub-id",
        "wirecloud": {"groups": ["dev", "ops"]},
    }

    async def _token_async(**_kwargs):
        return token_data

    async def _user_async(**_kwargs):
        return user_data

    monkeypatch.setattr(routes, "get_idm_get_token_functions", lambda: {"keycloak": _token_async})
    monkeypatch.setattr(routes, "get_idm_get_user_functions", lambda: {"keycloak": _user_async})

    created_user = _user_all("oidcuser")
    calls = {"n": 0}

    async def _get_user(_db, _username):
        calls["n"] += 1
        return None if calls["n"] == 1 else created_user

    monkeypatch.setattr(routes, "get_user_by_username", _get_user)

    assert (await app_http_client.get("/oidc/callback", params={"code": "abc"})).status_code == 302
    assert len(created.calls) == 1
    assert len(group_created.calls) == 2
    assert len(grouped.calls) == 1
    assert len(removed_groups.calls) == 1

    existing = _user_all("oidcuser")

    async def _get_existing(_db, _username):
        return existing

    monkeypatch.setattr(routes, "get_idm_get_token_functions", lambda: {"keycloak": (lambda **_k: token_data)})
    monkeypatch.setattr(routes, "get_idm_get_user_functions", lambda: {"keycloak": (lambda **_k: user_data)})
    monkeypatch.setattr(routes, "get_user_by_username", _get_existing)
    assert (await app_http_client.get("/oidc/callback", params={"code": "def"})).status_code == 302
    assert len(updated.calls) == 1

    monkeypatch.setattr(settings, "OID_CONNECT_FULLY_SYNC_GROUPS", False)
    monkeypatch.setattr(routes, "get_idm_get_token_functions", lambda: {"keycloak": (lambda **_k: {"session_state": "s1"})})
    monkeypatch.setattr(routes, "get_idm_get_user_functions", lambda: {"keycloak": (lambda **_k: {"preferred_username": "u1", "wirecloud": {"groups": [1, 2]}})})
    assert (await app_http_client.get("/oidc/callback", params={"code": "third"})).status_code == 302

    # Cover branch where only `sub` is present (no refresh token or session state)
    monkeypatch.setattr(routes, "get_idm_get_token_functions", lambda: {"keycloak": (lambda **_k: {})})
    monkeypatch.setattr(routes, "get_idm_get_user_functions", lambda: {"keycloak": (lambda **_k: {"preferred_username": "u1", "sub": "sub-only"})})
    assert (await app_http_client.get("/oidc/callback", params={"code": "fourth"})).status_code == 302


async def test_oidc_login_rejects_inactive_user_http(app_http_client, monkeypatch):
    _common_patches(monkeypatch)
    monkeypatch.setattr(settings, "OID_CONNECT_ENABLED", True)
    monkeypatch.setattr(settings, "OID_CONNECT_PLUGIN", "keycloak")
    monkeypatch.setattr(routes, "get_absolute_reverse_url", lambda *_args, **_kwargs: "http://cb")
    monkeypatch.setattr(routes, "get_idm_get_token_functions", lambda: {"keycloak": (lambda **_k: {})})
    monkeypatch.setattr(routes, "get_idm_get_user_functions", lambda: {"keycloak": (lambda **_k: {"preferred_username": "x"})})

    async def _inactive(_db, _username):
        return _user_all("x", active=False)

    monkeypatch.setattr(routes, "get_user_by_username", _inactive)
    assert (await app_http_client.get("/oidc/callback", params={"code": "abc"})).status_code == 401


async def test_api_login_and_login_http(app_http_client, monkeypatch):
    _common_patches(monkeypatch)
    monkeypatch.setattr(routes, "build_validation_error_response", lambda _r: Response(status_code=422))
    monkeypatch.setattr(routes, "get_redirect_response", lambda _r: Response(status_code=302))
    monkeypatch.setattr(routes, "render_wirecloud", lambda *_a, **_k: Response(status_code=200))
    monkeypatch.setattr(routes, "commit", _noop)
    monkeypatch.setattr(routes, "set_login_date_for_user", _noop)
    monkeypatch.setattr(routes, "create_token", _oid)
    monkeypatch.setattr(routes, "remove_user_idm_data", _noop)

    async def _none_user(_db, _username):
        return None

    monkeypatch.setattr(routes, "get_user_with_password", _none_user)
    monkeypatch.setattr(routes, "check_password", lambda *_a, **_k: False)

    json_headers = {"content-type": "application/json", "accept": "application/json"}
    assert (await app_http_client.post("/api/auth/login", content="not-json", headers=json_headers)).status_code == 422
    assert (await app_http_client.post("/login", content="not-json", headers={"content-type": "application/json"})).status_code == 422

    assert (await app_http_client.post("/api/auth/login", data={"username": "x", "password": "y"}, headers={"accept": "application/json"})).status_code == 401
    assert (await app_http_client.post("/login", data={"username": "x", "password": "y"})).status_code == 200

    good_user = _user_with_password("good")

    async def _good_user(_db, _username):
        return good_user

    monkeypatch.setattr(routes, "get_user_with_password", _good_user)
    monkeypatch.setattr(routes, "check_password", lambda *_a, **_k: True)

    response = await app_http_client.post("/api/auth/login", json={"username": "good", "password": "ok"}, headers={"accept": "application/json"})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == UserTokenType.bearer

    assert (await app_http_client.post("/login", json={"username": "good", "password": "ok"})).status_code == 302

    monkeypatch.setattr(settings, "OID_CONNECT_PLUGIN", None)
    assert (await app_http_client.post("/login", json={"username": "good", "password": "ok"})).status_code == 302


async def test_login_page_and_logout_http(app_http_client, monkeypatch):
    _common_patches(monkeypatch)
    monkeypatch.setattr(routes, "render_wirecloud", lambda *_a, **_k: Response(status_code=200))
    assert (await app_http_client.get("/login")).status_code == 200

    monkeypatch.setattr(routes, "get_redirect_response", lambda _r: Response(status_code=302))
    monkeypatch.setattr(routes, "commit", _noop)

    async def _none_session():
        return None

    async def _none_user():
        return None

    app.dependency_overrides[utils.get_session_no_csrf] = _none_session
    app.dependency_overrides[utils.get_user_no_csrf] = _none_user
    assert (await app_http_client.get("/logout")).status_code == 401

    invalidated = _CallRecorder()
    monkeypatch.setattr(routes, "invalidate_token", invalidated)

    user = _user_all("logout")
    session = Session(id=Id(str(ObjectId())), requires_csrf=True, token_data={})

    async def _session_dep():
        return session

    async def _user_dep():
        return user

    app.dependency_overrides[utils.get_session_no_csrf] = _session_dep
    app.dependency_overrides[utils.get_user_no_csrf] = _user_dep

    monkeypatch.setattr(settings, "OID_CONNECT_ENABLED", False)
    assert (await app_http_client.get("/logout")).status_code == 302
    assert len(invalidated.calls) == 1

    monkeypatch.setattr(settings, "OID_CONNECT_ENABLED", True)
    monkeypatch.setattr(settings, "OID_CONNECT_PLUGIN", "keycloak")
    user.idm_data = {"keycloak": {"idm_token": "r1"}}

    async def _backchannel_async(**_kwargs):
        return None

    def _backchannel_sync(**_kwargs):
        raise RuntimeError("ignore")

    monkeypatch.setattr(routes, "get_idm_backchannel_logout_functions", lambda: {"keycloak": _backchannel_async})
    assert (await app_http_client.get("/logout")).status_code == 302

    monkeypatch.setattr(routes, "get_idm_backchannel_logout_functions", lambda: {"keycloak": _backchannel_sync})
    assert (await app_http_client.get("/logout")).status_code == 302


async def test_token_refresh_http(app_http_client, monkeypatch):
    _common_patches(monkeypatch)
    monkeypatch.setattr(routes, "commit", _noop)
    monkeypatch.setattr(routes, "set_token_expiration", _noop)

    user = _user_all("refresh")
    session = SimpleNamespace(id=Id(str(ObjectId())), oidc_token="exists", requires_csrf=True, token_data={"real_user": {"id": "x"}})

    async def _none_session():
        return None

    async def _user_dep():
        return user

    app.dependency_overrides[utils.get_session_csrf] = _none_session
    app.dependency_overrides[utils.get_user_csrf] = _user_dep
    assert (await app_http_client.get("/api/auth/refresh")).status_code == 401

    async def _session_dep():
        return session

    app.dependency_overrides[utils.get_session_csrf] = _session_dep

    monkeypatch.setattr(settings, "OID_CONNECT_ENABLED", True)
    monkeypatch.setattr(settings, "OID_CONNECT_PLUGIN", "keycloak")
    monkeypatch.setattr(routes, "get_idm_get_token_functions", lambda: {})
    assert (await app_http_client.get("/api/auth/refresh")).status_code == 500

    async def _boom(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(routes, "get_idm_get_token_functions", lambda: {"keycloak": _boom})
    assert (await app_http_client.get("/api/auth/refresh")).status_code == 502

    async def _token_async(**_kwargs):
        return {"refresh_token": "new-refresh"}

    updated = _CallRecorder()
    monkeypatch.setattr(routes, "update_user", updated)
    monkeypatch.setattr(routes, "get_idm_get_token_functions", lambda: {"keycloak": _token_async})

    assert (await app_http_client.get("/api/auth/refresh")).status_code == 200
    assert len(updated.calls) == 1

    monkeypatch.setattr(settings, "OID_CONNECT_ENABLED", False)
    session_no_csrf = SimpleNamespace(id=Id(str(ObjectId())), oidc_token="exists", requires_csrf=False, token_data={})

    async def _session_dep_no_csrf():
        return session_no_csrf

    app.dependency_overrides[utils.get_session_csrf] = _session_dep_no_csrf
    assert (await app_http_client.get("/api/auth/refresh")).status_code == 200

    # Cover sync token provider branch
    monkeypatch.setattr(settings, "OID_CONNECT_ENABLED", True)
    session_sync = SimpleNamespace(id=Id(str(ObjectId())), oidc_token="exists", requires_csrf=True, token_data={})

    async def _session_dep_sync():
        return session_sync

    app.dependency_overrides[utils.get_session_csrf] = _session_dep_sync
    user.idm_data["keycloak"] = {"idm_token": "refresh-sync"}
    monkeypatch.setattr(routes, "get_idm_get_token_functions", lambda: {"keycloak": (lambda **_k: {"refresh_token": "sync-refresh"})})
    assert (await app_http_client.get("/api/auth/refresh")).status_code == 200

    # Cover path where provider entry is None (route currently raises TypeError -> handled as 500)
    user.idm_data["keycloak"] = None
    assert (await app_http_client.get("/api/auth/refresh")).status_code == 500


async def test_switch_user_http(app_http_client, monkeypatch):
    _common_patches(monkeypatch)
    monkeypatch.setattr(routes, "commit", _noop)
    monkeypatch.setattr(routes, "create_token", _oid)

    async def _idm_session(*_args, **_kwargs):
        return "sess"

    monkeypatch.setattr(routes, "get_token_idm_session", _idm_session)

    session = Session(id=Id(str(ObjectId())), requires_csrf=True, token_data={})

    async def _none_user():
        return None

    app.dependency_overrides[utils.get_real_user_csrf] = _none_user
    app.dependency_overrides[utils.get_user_csrf] = _none_user
    async def _session_override():
        return session

    app.dependency_overrides[utils.get_session_csrf] = _session_override

    assert (await app_http_client.post("/api/admin/switchuser", json={"username": "target"})).status_code == 401

    real = _user_all("real", perms=[])
    actual = _user_all("actual")

    async def _real_user():
        return real

    async def _actual_user():
        return actual

    async def _session_dep():
        return session

    app.dependency_overrides[utils.get_real_user_csrf] = _real_user
    app.dependency_overrides[utils.get_user_csrf] = _actual_user
    app.dependency_overrides[utils.get_session_csrf] = _session_dep

    assert (await app_http_client.post("/api/admin/switchuser", json={"username": "target"})).status_code == 403

    real.permissions = [Permission(codename="SWITCH_USER")]

    async def _none_target(*_a, **_k):
        return None

    monkeypatch.setattr(routes, "get_user_with_all_info_by_username", _none_target)
    assert (await app_http_client.post("/api/admin/switchuser", json={"username": "target"})).status_code == 404

    async def _inactive_target(*_a, **_k):
        return _user_all("target", active=False)

    monkeypatch.setattr(routes, "get_user_with_all_info_by_username", _inactive_target)
    assert (await app_http_client.post("/api/admin/switchuser", json={"username": "target"})).status_code == 404

    async def _same_target(*_a, **_k):
        return actual

    monkeypatch.setattr(routes, "get_user_with_all_info_by_username", _same_target)
    assert (await app_http_client.post("/api/admin/switchuser", json={"username": "target"})).status_code == 204

    target = _user_all("target")

    async def _target(*_a, **_k):
        return target

    monkeypatch.setattr(routes, "get_user_with_all_info_by_username", _target)
    monkeypatch.setattr(routes, "resolve_url_name", lambda *_a, **_k: ("wirecloud.workspace_view", {"owner": "o", "name": "w"}))

    class _Workspace:
        async def is_accessible_by(self, _db, _user):
            return False

    async def _workspace(*_a, **_k):
        return _Workspace()

    monkeypatch.setattr(routes, "get_workspace_by_username_and_name", _workspace)

    blocked = await app_http_client.post("/api/admin/switchuser", json={"username": "target"}, headers={"Referer": "http://testserver/workspace/o/w"})
    assert blocked.status_code == 204
    assert "Location" not in blocked.headers

    monkeypatch.setattr(routes, "resolve_url_name", lambda *_a, **_k: None)
    ok = await app_http_client.post("/api/admin/switchuser", json={"username": "target"}, headers={"Referer": "http://testserver/some/path"})
    assert ok.status_code == 204
    assert ok.headers.get("Location") == "/some/path"

    other_host = await app_http_client.post("/api/admin/switchuser", json={"username": "target"}, headers={"Referer": "http://otherserver/some/path"})
    assert other_host.status_code == 204
    assert "Location" not in other_host.headers

    monkeypatch.setattr(routes, "resolve_url_name", lambda *_a, **_k: ("wirecloud.workspace_view", {"owner": "o", "name": "w"}))

    class _WorkspaceAllowed:
        async def is_accessible_by(self, _db, _user):
            return True

    async def _workspace_allowed(*_a, **_k):
        return _WorkspaceAllowed()

    monkeypatch.setattr(routes, "get_workspace_by_username_and_name", _workspace_allowed)
    allowed = await app_http_client.post("/api/admin/switchuser", json={"username": "target"}, headers={"Referer": "http://testserver/workspace/o/w"})
    assert allowed.status_code == 204
    assert allowed.headers.get("Location") == "/workspace/o/w"

    session_no_csrf = Session(id=Id(str(ObjectId())), requires_csrf=False, token_data={})

    async def _session_dep_no_csrf():
        return session_no_csrf

    app.dependency_overrides[utils.get_session_csrf] = _session_dep_no_csrf

    async def _real_target(*_a, **_k):
        return real

    monkeypatch.setattr(routes, "get_user_with_all_info_by_username", _real_target)
    resp_real = await app_http_client.post("/api/admin/switchuser", json={"username": real.username})
    assert resp_real.status_code == 204


async def test_admin_user_group_organization_crud_endpoints_http(app_http_client, monkeypatch):
    admin = _admin_user()

    async def _admin_dep():
        return admin

    app.dependency_overrides[utils.get_user_csrf] = _admin_dep

    monkeypatch.setattr(routes, "hash_password", lambda _password: "hashed-password")

    user_indexed = _CallRecorder()
    monkeypatch.setattr(routes, "add_user_to_index", user_indexed)

    created_user = _user_with_password("new-user")

    async def _none_user_by_username(_db, _username):
        return None

    async def _create_user_db(_db, _user_data):
        return created_user

    monkeypatch.setattr(routes, "get_user_by_username", _none_user_by_username)
    monkeypatch.setattr(routes, "create_user_db", _create_user_db)

    response = await app_http_client.post("/api/admin/users", json={
        "username": "new-user",
        "password": "secret",
        "first_name": "New",
        "last_name": "User",
        "email": "new-user@example.com",
        "is_superuser": False,
        "is_staff": False,
        "is_active": True,
        "idm_data": {}
    })
    assert response.status_code == 201
    assert len(user_indexed.calls) == 1

    existing_user = _user_all("existing-user", perms=[Permission(codename="USER.VIEW")])

    async def _get_user_with_all_info_by_username(_db, _username, **_kwargs):
        return existing_user

    monkeypatch.setattr(routes, "get_user_with_all_info_by_username", _get_user_with_all_info_by_username)
    response = await app_http_client.get("/api/admin/users/existing-user")
    assert response.status_code == 200
    assert response.json()["username"] == "existing-user"

    updated_user = _user_all("existing-user")
    update_user_calls = _CallRecorder()

    async def _get_user_for_update(_db, _username, **_kwargs):
        return updated_user

    monkeypatch.setattr(routes, "get_user_with_all_info_by_username", _get_user_for_update)
    monkeypatch.setattr(routes, "get_user_by_username", _none_user_by_username)
    monkeypatch.setattr(routes, "update_user_with_all_info", update_user_calls)

    response = await app_http_client.put("/api/admin/users/existing-user", json={
        "username": "renamed-user",
        "email": "renamed@example.com",
        "first_name": "Renamed",
        "last_name": "User",
        "is_staff": True,
        "is_active": True,
        "is_superuser": False,
        "permissions": ["USER.EDIT"]
    })
    assert response.status_code == 204
    assert len(update_user_calls.calls) == 1
    assert updated_user.username == "renamed-user"

    delete_user_calls = _CallRecorder()

    async def _get_user_for_delete(_db, _username):
        return _user_all("renamed-user")

    monkeypatch.setattr(routes, "get_user_by_username", _get_user_for_delete)
    monkeypatch.setattr(routes, "delete_user", delete_user_calls)
    response = await app_http_client.delete("/api/admin/users/renamed-user")
    assert response.status_code == 204
    assert len(delete_user_calls.calls) == 1

    group_id = Id(str(ObjectId()))
    user_id_1 = Id(str(ObjectId()))
    user_id_2 = Id(str(ObjectId()))
    user_id_3 = Id(str(ObjectId()))
    created_group = Group(_id=group_id, name="dev", codename="dev", path=[group_id])
    group_indexed = _CallRecorder()
    group_added_to_users = _CallRecorder()

    async def _none_group_by_name(_db, _name):
        return None

    async def _existing_user_by_id(_db, _user_id):
        return _user_all("member")

    async def _create_group_db(_db, _group_data):
        return created_group

    monkeypatch.setattr(routes, "get_group_by_name", _none_group_by_name)
    monkeypatch.setattr(routes, "get_user_by_id", _existing_user_by_id)
    monkeypatch.setattr(routes, "create_group_db", _create_group_db)
    monkeypatch.setattr(routes, "add_group_to_users", group_added_to_users)
    monkeypatch.setattr(routes, "add_group_to_index", group_indexed)

    response = await app_http_client.post("/api/admin/groups", json={
        "name": "dev",
        "codename": "dev",
        "users": [str(user_id_1)]
    })
    assert response.status_code == 201
    assert len(group_added_to_users.calls) == 1
    assert len(group_indexed.calls) == 1

    get_group = Group(_id=Id(str(ObjectId())), name="dev", codename="dev", path=[group_id], users=[user_id_1])
    get_group.group_permissions = [Permission(codename="GROUP.VIEW")]

    async def _get_group_for_get(_db, _group_name):
        return get_group

    monkeypatch.setattr(routes, "get_group_by_name", _get_group_for_get)
    response = await app_http_client.get("/api/admin/groups/dev")
    assert response.status_code == 200
    assert response.json()["name"] == "dev"

    update_group_calls = _CallRecorder()
    update_group_add_users_calls = _CallRecorder()
    update_group_remove_users_calls = _CallRecorder()
    original_group = Group(_id=Id(str(ObjectId())), name="dev", codename="dev", path=[group_id], users=[user_id_1, user_id_2])

    async def _get_group_for_update(_db, _group_name):
        if _group_name == "dev":
            return original_group
        return None

    monkeypatch.setattr(routes, "get_group_by_name", _get_group_for_update)
    monkeypatch.setattr(routes, "add_group_to_users", update_group_add_users_calls)
    monkeypatch.setattr(routes, "remove_group_to_users", update_group_remove_users_calls)
    monkeypatch.setattr(routes, "update_group", update_group_calls)

    response = await app_http_client.put("/api/admin/groups/dev", json={
        "name": "dev-renamed",
        "codename": "dev-renamed",
        "permissions": ["GROUP.EDIT"],
        "users": [str(user_id_2), str(user_id_3)]
    })
    assert response.status_code == 204
    assert len(update_group_add_users_calls.calls) == 1
    assert len(update_group_remove_users_calls.calls) == 1
    assert len(update_group_calls.calls) == 1

    delete_group_calls = _CallRecorder()

    async def _get_group_for_delete(_db, _group_name):
        return Group(_id=Id(str(ObjectId())), name="to-delete", codename="to-delete", path=[Id(str(ObjectId()))])

    monkeypatch.setattr(routes, "get_group_by_name", _get_group_for_delete)
    monkeypatch.setattr(routes, "delete_group", delete_group_calls)
    response = await app_http_client.delete("/api/admin/groups/to-delete")
    assert response.status_code == 204
    assert len(delete_group_calls.calls) == 1

    org_id = Id(str(ObjectId()))
    created_org = Group(_id=org_id, name="acme", codename="acme", path=[org_id], is_organization=True)
    create_org_calls = _CallRecorder()
    org_indexed = _CallRecorder()

    async def _create_org_db(_db, _org_data):
        return created_org

    monkeypatch.setattr(routes, "get_group_by_name", _none_group_by_name)
    monkeypatch.setattr(routes, "create_organization_db", _create_org_db)
    monkeypatch.setattr(routes, "add_group_to_users", create_org_calls)
    monkeypatch.setattr(routes, "add_group_to_index", org_indexed)

    response = await app_http_client.post("/api/admin/organizations", json={
        "name": "acme",
        "codename": "acme",
        "users": [str(user_id_1)]
    })
    assert response.status_code == 201
    assert len(create_org_calls.calls) == 1
    assert len(org_indexed.calls) == 1

    org_child = Group(
        _id=Id(str(ObjectId())),
        name="team-a",
        codename="team-a",
        path=[org_id, Id(str(ObjectId()))],
        is_organization=True,
        users=[user_id_1]
    )

    async def _get_org_root(_db, _org_name):
        return created_org

    async def _get_org_groups(_db, _org):
        return [created_org, org_child]

    monkeypatch.setattr(routes, "get_group_by_name", _get_org_root)
    monkeypatch.setattr(routes, "get_all_organization_groups", _get_org_groups)
    response = await app_http_client.get("/api/admin/organizations/acme")
    assert response.status_code == 200
    assert len(response.json()) == 2

    update_path_calls = _CallRecorder()
    update_org_group_calls = _CallRecorder()
    child_group = Group(
        _id=Id(str(ObjectId())),
        name="team-a",
        codename="team-a",
        path=[org_id, Id(str(ObjectId()))],
        is_organization=True
    )

    async def _get_child_group(_db, _group_name):
        return child_group

    monkeypatch.setattr(routes, "get_group_by_name", _get_child_group)
    monkeypatch.setattr(routes, "update_path_for_descendants", update_path_calls)
    monkeypatch.setattr(routes, "update_group", update_org_group_calls)
    response = await app_http_client.put("/api/admin/organizations/groups/team-a", json={"parent_name": ""})
    assert response.status_code == 204
    assert len(update_path_calls.calls) == 1
    assert len(update_org_group_calls.calls) == 1

    delete_org_calls = _CallRecorder()

    async def _get_org_for_delete(_db, _org_name):
        return created_org

    monkeypatch.setattr(routes, "get_group_by_name", _get_org_for_delete)
    monkeypatch.setattr(routes, "delete_organization", delete_org_calls)
    response = await app_http_client.delete("/api/admin/organizations/acme")
    assert response.status_code == 204
    assert len(delete_org_calls.calls) == 1


async def test_admin_user_endpoints_all_if_branches_http(app_http_client, monkeypatch):
    _common_patches(monkeypatch)
    monkeypatch.setattr(routes, "hash_password", lambda _password: "hashed-password")

    # create_user: permission denied
    _set_auth_user(_user_all("op", perms=[]))
    response = await app_http_client.post("/api/admin/users", json={
        "username": "u1",
        "password": "secret",
        "first_name": "U",
        "last_name": "One",
        "email": "u1@example.com",
        "is_superuser": False,
        "is_staff": False,
        "is_active": True,
        "idm_data": {}
    })
    assert response.status_code == 403

    # create_user: empty username
    _set_auth_user(_user_all("op", perms=[Permission(codename="USER.CREATE")]))
    response = await app_http_client.post("/api/admin/users", json={
        "username": "",
        "password": "secret",
        "first_name": "U",
        "last_name": "Empty",
        "email": "uempty@example.com",
        "is_superuser": False,
        "is_staff": False,
        "is_active": True,
        "idm_data": {}
    })
    assert response.status_code == 422

    # create_user: direct unit branch for empty username -> 400 in handler body
    unit_user_data = SimpleNamespace(
        username="",
        password="secret",
        first_name="U",
        last_name="Empty",
        email="uempty@example.com",
        is_superuser=False,
        is_staff=False,
        is_active=True,
        idm_data={}
    )

    handler = routes.create_user
    while hasattr(handler, "__wrapped__"):
        handler = handler.__wrapped__

    unit_response = await handler(db=None, request=None, user=_admin_user(), user_data=unit_user_data)
    assert unit_response.status_code == 400

    # create_user: conflict
    async def _existing_user(_db, _username):
        return _user_all("already")

    monkeypatch.setattr(routes, "get_user_by_username", _existing_user)
    response = await app_http_client.post("/api/admin/users", json={
        "username": "already",
        "password": "secret",
        "first_name": "A",
        "last_name": "Exists",
        "email": "already@example.com",
        "is_superuser": False,
        "is_staff": False,
        "is_active": True,
        "idm_data": {}
    })
    assert response.status_code == 409

    # create_user: success
    index_calls = _CallRecorder()

    async def _none_user(_db, _username, **_kwargs):
        return None

    async def _create_user_db(_db, _user_data):
        return _user_with_password("created")

    monkeypatch.setattr(routes, "get_user_by_username", _none_user)
    monkeypatch.setattr(routes, "create_user_db", _create_user_db)
    monkeypatch.setattr(routes, "add_user_to_index", index_calls)

    response = await app_http_client.post("/api/admin/users", json={
        "username": "created",
        "password": "secret",
        "first_name": "C",
        "last_name": "User",
        "email": "created@example.com",
        "is_superuser": False,
        "is_staff": False,
        "is_active": True,
        "idm_data": {}
    })
    assert response.status_code == 201
    assert len(index_calls.calls) == 1

    # get_user_entry: permission denied
    _set_auth_user(_user_all("op", perms=[]))
    response = await app_http_client.get("/api/admin/users/target")
    assert response.status_code == 403

    # get_user_entry: not found
    _set_auth_user(_user_all("op", perms=[Permission(codename="USER.VIEW")]))
    monkeypatch.setattr(routes, "get_user_with_all_info_by_username", _none_user)
    response = await app_http_client.get("/api/admin/users/target")
    assert response.status_code == 404

    # get_user_entry: success
    async def _user_for_get(_db, _username, **_kwargs):
        return _user_all("target", perms=[Permission(codename="USER.VIEW")])

    monkeypatch.setattr(routes, "get_user_with_all_info_by_username", _user_for_get)
    response = await app_http_client.get("/api/admin/users/target")
    assert response.status_code == 200
    assert response.json()["username"] == "target"

    # update_user_entry: permission denied
    _set_auth_user(_user_all("op", perms=[]))
    response = await app_http_client.put("/api/admin/users/target", json={
        "username": "target",
        "email": "target@example.com",
        "first_name": "T",
        "last_name": "User",
        "is_staff": False,
        "is_active": True,
        "is_superuser": False,
        "permissions": []
    })
    assert response.status_code == 403

    _set_auth_user(_user_all("op", perms=[Permission(codename="USER.EDIT")]))

    # update_user_entry: not found
    monkeypatch.setattr(routes, "get_user_with_all_info_by_username", _none_user)
    response = await app_http_client.put("/api/admin/users/target", json={
        "username": "target",
        "email": "target@example.com",
        "first_name": "T",
        "last_name": "User",
        "is_staff": False,
        "is_active": True,
        "is_superuser": False,
        "permissions": []
    })
    assert response.status_code == 404

    # update_user_entry: empty username
    editable = _user_all("target")

    async def _editable_user(_db, _username, **_kwargs):
        return editable

    monkeypatch.setattr(routes, "get_user_with_all_info_by_username", _editable_user)
    response = await app_http_client.put("/api/admin/users/target", json={
        "username": "",
        "email": "target@example.com",
        "first_name": "T",
        "last_name": "User",
        "is_staff": False,
        "is_active": True,
        "is_superuser": False,
        "permissions": []
    })
    assert response.status_code == 400

    # update_user_entry: username conflict
    async def _user_exists(_db, _username):
        return _user_all("occupied")

    monkeypatch.setattr(routes, "get_user_by_username", _user_exists)
    response = await app_http_client.put("/api/admin/users/target", json={
        "username": "occupied",
        "email": "target@example.com",
        "first_name": "T",
        "last_name": "User",
        "is_staff": False,
        "is_active": True,
        "is_superuser": False,
        "permissions": []
    })
    assert response.status_code == 409

    # update_user_entry: success with permissions=None
    updated_calls = _CallRecorder()
    monkeypatch.setattr(routes, "get_user_by_username", _none_user)
    monkeypatch.setattr(routes, "update_user_with_all_info", updated_calls)
    response = await app_http_client.put("/api/admin/users/target", json={
        "username": "target",
        "email": "target2@example.com",
        "first_name": "Target",
        "last_name": "Two",
        "is_staff": True,
        "is_active": False,
        "is_superuser": False,
        "permissions": None
    })
    assert response.status_code == 204

    # update_user_entry: success with rename + permissions
    response = await app_http_client.put("/api/admin/users/target", json={
        "username": "target-renamed",
        "email": "target3@example.com",
        "first_name": "Target",
        "last_name": "Three",
        "is_staff": True,
        "is_active": True,
        "is_superuser": False,
        "permissions": ["USER.EDIT"]
    })
    assert response.status_code == 204
    assert len(updated_calls.calls) == 2

    # delete_user_entry: permission denied
    _set_auth_user(_user_all("op", perms=[]))
    response = await app_http_client.delete("/api/admin/users/target")
    assert response.status_code == 403

    _set_auth_user(_user_all("op", perms=[Permission(codename="USER.DELETE")]))
    monkeypatch.setattr(routes, "get_user_by_username", _none_user)
    response = await app_http_client.delete("/api/admin/users/target")
    assert response.status_code == 404

    deleted_calls = _CallRecorder()

    async def _deletable(_db, _username):
        return _user_all("target")

    monkeypatch.setattr(routes, "get_user_by_username", _deletable)
    monkeypatch.setattr(routes, "delete_user", deleted_calls)
    response = await app_http_client.delete("/api/admin/users/target")
    assert response.status_code == 204
    assert len(deleted_calls.calls) == 1


async def test_admin_group_endpoints_all_if_branches_http(app_http_client, monkeypatch):
    _common_patches(monkeypatch)

    gid = Id(str(ObjectId()))
    u1 = Id(str(ObjectId()))
    u2 = Id(str(ObjectId()))
    u3 = Id(str(ObjectId()))

    # create_group: permission denied
    _set_auth_user(_user_all("op", perms=[]))
    response = await app_http_client.post("/api/admin/groups", json={"name": "dev", "codename": "dev", "users": []})
    assert response.status_code == 403

    _set_auth_user(_user_all("op", perms=[Permission(codename="GROUP.CREATE")]))

    # create_group: empty fields
    response = await app_http_client.post("/api/admin/groups", json={"name": "", "codename": "dev", "users": []})
    assert response.status_code == 400

    # create_group: conflict
    async def _group_exists(_db, _name):
        return Group(_id=gid, name="dev", codename="dev", path=[gid])

    monkeypatch.setattr(routes, "get_group_by_name", _group_exists)
    response = await app_http_client.post("/api/admin/groups", json={"name": "dev", "codename": "dev", "users": []})
    assert response.status_code == 409

    # create_group: user does not exist
    async def _group_missing(_db, _name):
        return None

    async def _user_missing(_db, _uid):
        return None

    monkeypatch.setattr(routes, "get_group_by_name", _group_missing)
    monkeypatch.setattr(routes, "get_user_by_id", _user_missing)
    response = await app_http_client.post("/api/admin/groups", json={"name": "dev", "codename": "dev", "users": [str(u1)]})
    assert response.status_code == 404

    # create_group: success without users (len == 0)
    add_users_calls = _CallRecorder()
    add_index_calls = _CallRecorder()

    async def _user_ok(_db, _uid):
        return _user_all("member")

    async def _create_group_db(_db, _group_data):
        return Group(_id=gid, name="dev", codename="dev", path=[gid])

    monkeypatch.setattr(routes, "get_user_by_id", _user_ok)
    monkeypatch.setattr(routes, "create_group_db", _create_group_db)
    monkeypatch.setattr(routes, "add_group_to_users", add_users_calls)
    monkeypatch.setattr(routes, "add_group_to_index", add_index_calls)
    response = await app_http_client.post("/api/admin/groups", json={"name": "dev", "codename": "dev", "users": []})
    assert response.status_code == 201
    assert len(add_users_calls.calls) == 0

    # create_group: success with users (len > 0)
    response = await app_http_client.post("/api/admin/groups", json={"name": "dev2", "codename": "dev2", "users": [str(u1)]})
    assert response.status_code == 201
    assert len(add_users_calls.calls) == 1
    assert len(add_index_calls.calls) == 2

    # get_group_entry: permission denied
    _set_auth_user(_user_all("op", perms=[]))
    response = await app_http_client.get("/api/admin/groups/dev")
    assert response.status_code == 403

    _set_auth_user(_user_all("op", perms=[Permission(codename="GROUP.VIEW")]))

    # get_group_entry: not found
    monkeypatch.setattr(routes, "get_group_by_name", _group_missing)
    response = await app_http_client.get("/api/admin/groups/dev")
    assert response.status_code == 404

    # get_group_entry: success
    group_for_get = Group(_id=gid, name="dev", codename="dev", path=[gid], users=[u1])
    group_for_get.group_permissions = [Permission(codename="GROUP.VIEW")]

    async def _group_for_get(_db, _name):
        return group_for_get

    monkeypatch.setattr(routes, "get_group_by_name", _group_for_get)
    response = await app_http_client.get("/api/admin/groups/dev")
    assert response.status_code == 200
    assert response.json()["name"] == "dev"

    # update_group_entry: permission denied
    _set_auth_user(_user_all("op", perms=[]))
    response = await app_http_client.put("/api/admin/groups/dev", json={"name": "dev", "codename": "dev", "permissions": None, "users": []})
    assert response.status_code == 403

    _set_auth_user(_user_all("op", perms=[Permission(codename="GROUP.EDIT")]))

    # update_group_entry: empty fields
    response = await app_http_client.put("/api/admin/groups/dev", json={"name": "", "codename": "dev", "permissions": None, "users": []})
    assert response.status_code == 400

    # update_group_entry: not found
    monkeypatch.setattr(routes, "get_group_by_name", _group_missing)
    response = await app_http_client.put("/api/admin/groups/dev", json={"name": "dev", "codename": "dev", "permissions": None, "users": []})
    assert response.status_code == 404

    # update_group_entry: rename conflict
    editable_group = Group(_id=gid, name="dev", codename="dev", path=[gid], users=[u1, u2])

    async def _group_for_update(_db, _name):
        if _name == "dev":
            return editable_group
        return Group(_id=Id(str(ObjectId())), name=_name, codename=_name, path=[Id(str(ObjectId()))])

    monkeypatch.setattr(routes, "get_group_by_name", _group_for_update)
    response = await app_http_client.put("/api/admin/groups/dev", json={
        "name": "taken",
        "codename": "taken",
        "permissions": None,
        "users": [str(u1), str(u2)]
    })
    assert response.status_code == 409

    # update_group_entry: success with no rename / no permissions / no user changes
    async def _group_for_update_same(_db, _name):
        return editable_group if _name == "dev" else None

    update_calls = _CallRecorder()
    add_users_update_calls = _CallRecorder()
    rm_users_update_calls = _CallRecorder()
    monkeypatch.setattr(routes, "get_group_by_name", _group_for_update_same)
    monkeypatch.setattr(routes, "update_group", update_calls)
    monkeypatch.setattr(routes, "add_group_to_users", add_users_update_calls)
    monkeypatch.setattr(routes, "remove_group_to_users", rm_users_update_calls)
    response = await app_http_client.put("/api/admin/groups/dev", json={
        "name": "dev",
        "codename": "dev",
        "permissions": None,
        "users": [str(u1), str(u2)]
    })
    assert response.status_code == 204
    assert len(add_users_update_calls.calls) == 0
    assert len(rm_users_update_calls.calls) == 0

    # update_group_entry: success with rename + permissions + users add/remove
    response = await app_http_client.put("/api/admin/groups/dev", json={
        "name": "dev-new",
        "codename": "dev-new",
        "permissions": ["GROUP.EDIT"],
        "users": [str(u2), str(u3)]
    })
    assert response.status_code == 204
    assert len(add_users_update_calls.calls) == 1
    assert len(rm_users_update_calls.calls) == 1
    assert len(update_calls.calls) == 2

    # delete_group_entry: permission denied
    _set_auth_user(_user_all("op", perms=[]))
    response = await app_http_client.delete("/api/admin/groups/dev")
    assert response.status_code == 403

    _set_auth_user(_user_all("op", perms=[Permission(codename="GROUP.DELETE")]))

    # delete_group_entry: not found
    monkeypatch.setattr(routes, "get_group_by_name", _group_missing)
    response = await app_http_client.delete("/api/admin/groups/dev")
    assert response.status_code == 404

    # delete_group_entry: root organization cannot be deleted
    root_org = Group(_id=gid, name="org", codename="org", path=[gid], is_organization=True)

    async def _root_org(_db, _name):
        return root_org

    monkeypatch.setattr(routes, "get_group_by_name", _root_org)
    response = await app_http_client.delete("/api/admin/groups/org")
    assert response.status_code == 400

    # delete_group_entry: success
    deletable_group = Group(_id=gid, name="dev", codename="dev", path=[Id(str(ObjectId())), gid], is_organization=False)
    delete_calls = _CallRecorder()

    async def _deletable_group(_db, _name):
        return deletable_group

    monkeypatch.setattr(routes, "get_group_by_name", _deletable_group)
    monkeypatch.setattr(routes, "delete_group", delete_calls)
    response = await app_http_client.delete("/api/admin/groups/dev")
    assert response.status_code == 204
    assert len(delete_calls.calls) == 1


async def test_admin_organization_endpoints_all_if_branches_http(app_http_client, monkeypatch):
    _common_patches(monkeypatch)

    org_id = Id(str(ObjectId()))
    child_id = Id(str(ObjectId()))
    parent_id = Id(str(ObjectId()))
    u1 = Id(str(ObjectId()))
    u2 = Id(str(ObjectId()))

    # create_organization: permission denied
    _set_auth_user(_user_all("op", perms=[]))
    response = await app_http_client.post("/api/admin/organizations", json={"name": "org", "codename": "org", "users": []})
    assert response.status_code == 403

    _set_auth_user(_user_all("op", perms=[Permission(codename="ORGANIZATION.CREATE")]))

    # create_organization: empty fields
    response = await app_http_client.post("/api/admin/organizations", json={"name": "", "codename": "org", "users": []})
    assert response.status_code == 400

    # create_organization: conflict
    async def _org_exists(_db, _name):
        return Group(_id=org_id, name="org", codename="org", path=[org_id], is_organization=True)

    monkeypatch.setattr(routes, "get_group_by_name", _org_exists)
    response = await app_http_client.post("/api/admin/organizations", json={"name": "org", "codename": "org", "users": []})
    assert response.status_code == 409

    # create_organization: success without users and with users
    async def _org_missing(_db, _name):
        return None

    async def _create_org(_db, _org_data):
        return Group(_id=org_id, name="org", codename="org", path=[org_id], is_organization=True)

    add_users_calls = _CallRecorder()
    add_index_calls = _CallRecorder()
    monkeypatch.setattr(routes, "get_group_by_name", _org_missing)
    monkeypatch.setattr(routes, "create_organization_db", _create_org)
    monkeypatch.setattr(routes, "add_group_to_users", add_users_calls)
    monkeypatch.setattr(routes, "add_group_to_index", add_index_calls)

    response = await app_http_client.post("/api/admin/organizations", json={"name": "org", "codename": "org", "users": []})
    assert response.status_code == 201
    assert len(add_users_calls.calls) == 0

    response = await app_http_client.post("/api/admin/organizations", json={"name": "org2", "codename": "org2", "users": [str(u1)]})
    assert response.status_code == 201
    assert len(add_users_calls.calls) == 1
    assert len(add_index_calls.calls) == 2

    # get_organization_entry: permission denied
    _set_auth_user(_user_all("op", perms=[]))
    response = await app_http_client.get("/api/admin/organizations/org")
    assert response.status_code == 403

    _set_auth_user(_user_all("op", perms=[Permission(codename="ORGANIZATION.VIEW")]))

    # get_organization_entry: not found (None)
    monkeypatch.setattr(routes, "get_group_by_name", _org_missing)
    response = await app_http_client.get("/api/admin/organizations/org")
    assert response.status_code == 404

    # get_organization_entry: not found (not org or not root)
    not_root_org = Group(_id=org_id, name="org", codename="org", path=[parent_id, org_id], is_organization=True)

    async def _not_root(_db, _name):
        return not_root_org

    monkeypatch.setattr(routes, "get_group_by_name", _not_root)
    response = await app_http_client.get("/api/admin/organizations/org")
    assert response.status_code == 404

    # get_organization_entry: success
    root_org = Group(_id=org_id, name="org", codename="org", path=[org_id], is_organization=True, users=[u1])
    child_org = Group(_id=child_id, name="team", codename="team", path=[org_id, child_id], is_organization=True, users=[u2])

    async def _root(_db, _name):
        return root_org

    async def _org_groups(_db, _org):
        return [root_org, child_org]

    monkeypatch.setattr(routes, "get_group_by_name", _root)
    monkeypatch.setattr(routes, "get_all_organization_groups", _org_groups)
    response = await app_http_client.get("/api/admin/organizations/org")
    assert response.status_code == 200
    assert len(response.json()) == 2

    # update_organization_group_entry: permission denied
    _set_auth_user(_user_all("op", perms=[]))
    response = await app_http_client.put("/api/admin/organizations/groups/team", json={"parent_name": ""})
    assert response.status_code == 403

    _set_auth_user(_user_all("op", perms=[Permission(codename="ORGANIZATION.EDIT")]))

    # update_organization_group_entry: child not found
    monkeypatch.setattr(routes, "get_group_by_name", _org_missing)
    response = await app_http_client.put("/api/admin/organizations/groups/team", json={"parent_name": ""})
    assert response.status_code == 404

    # update_organization_group_entry: detach branch (parent_name == "")
    detach_child = Group(_id=child_id, name="team", codename="team", path=[org_id, child_id], is_organization=True)
    detach_calls = _CallRecorder()
    update_calls = _CallRecorder()

    async def _detach_child(_db, _name):
        return detach_child

    monkeypatch.setattr(routes, "get_group_by_name", _detach_child)
    monkeypatch.setattr(routes, "update_path_for_descendants", detach_calls)
    monkeypatch.setattr(routes, "update_group", update_calls)
    response = await app_http_client.put("/api/admin/organizations/groups/team", json={"parent_name": ""})
    assert response.status_code == 204
    assert len(detach_calls.calls) == 1

    # update_organization_group_entry: parent missing
    async def _child_then_missing_parent(_db, name):
        if name == "team":
            return detach_child
        return None

    monkeypatch.setattr(routes, "get_group_by_name", _child_then_missing_parent)
    response = await app_http_client.put("/api/admin/organizations/groups/team", json={"parent_name": "missing"})
    assert response.status_code == 404

    # update_organization_group_entry: parent is not organization
    non_org_parent = Group(_id=parent_id, name="parent", codename="parent", path=[parent_id], is_organization=False)

    async def _child_then_non_org(_db, name):
        if name == "team":
            return detach_child
        return non_org_parent

    monkeypatch.setattr(routes, "get_group_by_name", _child_then_non_org)
    response = await app_http_client.put("/api/admin/organizations/groups/team", json={"parent_name": "parent"})
    assert response.status_code == 400

    # update_organization_group_entry: cycle detected
    cyclic_parent = Group(_id=parent_id, name="parent", codename="parent", path=[org_id, child_id, parent_id], is_organization=True)

    async def _child_then_cycle(_db, name):
        if name == "team":
            return detach_child
        return cyclic_parent

    monkeypatch.setattr(routes, "get_group_by_name", _child_then_cycle)
    response = await app_http_client.put("/api/admin/organizations/groups/team", json={"parent_name": "parent"})
    assert response.status_code == 400

    # update_organization_group_entry: success with parent organization
    valid_parent = Group(_id=parent_id, name="parent", codename="parent", path=[org_id, parent_id], is_organization=True)

    async def _child_then_parent(_db, name):
        if name == "team":
            return detach_child
        return valid_parent

    monkeypatch.setattr(routes, "get_group_by_name", _child_then_parent)
    response = await app_http_client.put("/api/admin/organizations/groups/team", json={"parent_name": "parent"})
    assert response.status_code == 204
    assert len(update_calls.calls) >= 2

    # delete_organization_entry: permission denied
    _set_auth_user(_user_all("op", perms=[]))
    response = await app_http_client.delete("/api/admin/organizations/org")
    assert response.status_code == 403

    _set_auth_user(_user_all("op", perms=[Permission(codename="ORGANIZATION.DELETE")]))

    # delete_organization_entry: not found
    monkeypatch.setattr(routes, "get_group_by_name", _org_missing)
    response = await app_http_client.delete("/api/admin/organizations/org")
    assert response.status_code == 404

    # delete_organization_entry: invalid organization root
    not_root = Group(_id=org_id, name="org", codename="org", path=[parent_id, org_id], is_organization=True)

    async def _invalid_root(_db, _name):
        return not_root

    monkeypatch.setattr(routes, "get_group_by_name", _invalid_root)
    response = await app_http_client.delete("/api/admin/organizations/org")
    assert response.status_code == 400

    # delete_organization_entry: success
    delete_calls = _CallRecorder()
    monkeypatch.setattr(routes, "get_group_by_name", _root)
    monkeypatch.setattr(routes, "delete_organization", delete_calls)
    response = await app_http_client.delete("/api/admin/organizations/org")
    assert response.status_code == 204
    assert len(delete_calls.calls) == 1
