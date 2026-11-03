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

from types import SimpleNamespace

import pytest

from wirecloud.keycloak import plugins
from wirecloud.commons.auth.schemas import UserAll
from wirecloud.database import Id
from bson import ObjectId
from datetime import datetime, timezone
from datetime import timedelta


async def test_context_aware_oidc_validates_nonce_audience_and_userinfo_subject(monkeypatch):
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client_id, issuer = "wirecloud-test", "https://identity.example/realm"
    monkeypatch.setattr(plugins.settings, "OID_CONNECT_CLIENT_ID", client_id)
    monkeypatch.setattr(plugins.settings, "OID_CONNECT_DATA", {"token_endpoint": issuer + "/token", "userinfo_endpoint": issuer + "/userinfo",
        "issuer": issuer, "keys": {"test-key": key.public_key()}, "scopes": ["openid"]}, raising=False)
    nonce = "expected-nonce"
    claims = {"sub": "external-subject", "iss": issuer, "aud": client_id, "nonce": nonce,
              "iat": datetime.now(timezone.utc), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}
    captured = []
    async def provider_request(endpoint, data=None, **kwargs):
        captured.append(data)
        return {"scope": "openid", "access_token": "access", "refresh_token": "refresh",
                "id_token": jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})}
    monkeypatch.setattr(plugins, "make_oidc_provider_request", provider_request)
    plugin = plugins.WirecloudKeycloakPlugin(None)
    exchange = plugin.get_idm_get_token_functions()["keycloak"]
    context = {"nonce": nonce, "code_verifier": "pkce-verifier"}
    tokens = await exchange("code", None, "https://wc/oidc/callback", login_context=context)
    assert captured[0]["code_verifier"] == "pkce-verifier"
    claims["nonce"] = "wrong"
    with pytest.raises(ValueError, match="nonce"):
        await exchange("code", None, "https://wc/oidc/callback", login_context=context)
    claims["nonce"] = nonce
    claims["aud"] = "different-client"
    with pytest.raises(jwt.InvalidAudienceError):
        await exchange("code", None, "https://wc/oidc/callback", login_context=context)
    async def wrong_user(*args, **kwargs):
        return {"preferred_username": "alice", "sub": "another-subject"}
    monkeypatch.setattr(plugins, "make_oidc_provider_request", wrong_user)
    with pytest.raises(ValueError, match="subject"):
        await plugin.get_idm_get_user_functions()["keycloak"](tokens)


@pytest.fixture(autouse=True)
def _patch_gettext(monkeypatch):
    monkeypatch.setattr(plugins, "_", lambda text: text)


class _FakeFastAPI:
    def __init__(self):
        self.calls = []

    def include_router(self, *args, **kwargs):
        self.calls.append((args, kwargs))


class _FakeResponse:
    def __init__(self, status=200, data=None, json_error=False):
        self.status = status
        self._data = data or {}
        self._json_error = json_error

    async def json(self):
        if self._json_error:
            raise ValueError("bad json")
        return self._data


class _FakeSession:
    def __init__(self, response=None, get_error=False):
        self.response = response
        self.get_error = get_error
        self.closed = False
        self.captured = {}

    async def get(self, *args, **kwargs):
        self.captured["args"] = args
        self.captured["kwargs"] = kwargs
        if self.get_error:
            raise RuntimeError("boom")
        return self.response

    async def close(self):
        self.closed = True


def _set_common_settings(monkeypatch):
    monkeypatch.setattr(plugins.settings, "OID_CONNECT_PLUGIN", "keycloak")
    monkeypatch.setattr(plugins.settings, "OID_CONNECT_ENABLED", True)
    monkeypatch.setattr(plugins.settings, "OID_CONNECT_CLIENT_ID", "wc-client")
    monkeypatch.setattr(plugins.settings, "OID_CONNECT_CLIENT_SECRET", None)
    monkeypatch.setattr(plugins.settings, "WIRECLOUD_HTTPS_VERIFY", True)


def _sample_user(idm_data):
    return UserAll(
        id=Id(str(ObjectId())),
        username="u",
        email="u@example.com",
        first_name="First",
        last_name="Last",
        is_superuser=False,
        is_staff=False,
        is_active=True,
        date_joined=datetime.now(timezone.utc),
        last_login=None,
        idm_data=idm_data,
        groups=[],
        permissions=[],
    )


async def test_plugin_init_and_simple_accessors(monkeypatch):
    plugins.IDM_SUPPORT_ENABLED = False
    plugin = plugins.WirecloudKeycloakPlugin(None)
    assert plugin.get_proxy_processors() == ()

    app = _FakeFastAPI()
    plugins.WirecloudKeycloakPlugin(app)
    assert len(app.calls) == 1

    monkeypatch.setattr(plugins.settings, "OID_CONNECT_PLUGIN", "not-keycloak")
    assert plugin.get_ajax_endpoints("classic", None) == ()
    assert plugin.get_platform_context_definitions() == {}

    plugins.IDM_SUPPORT_ENABLED = True
    monkeypatch.setattr(plugins.settings, "OID_CONNECT_PLUGIN", "keycloak")
    monkeypatch.setattr(plugins.settings, "OID_CONNECT_DATA", {"check_session_iframe": "https://kc/iframe"}, raising=False)
    assert plugin.get_proxy_processors() == ("wirecloud.keycloak.proxy.KeycloakTokenProcessor",)
    endpoints = plugin.get_ajax_endpoints("classic", None)
    assert len(endpoints) == 1
    assert endpoints[0].id == "KEYCLOAK_LOGIN_STATUS_IFRAME"

    defs = plugin.get_platform_context_definitions()
    assert "fiware_token_available" in defs
    assert "keycloak_client_id" in defs
    assert "keycloak_session" in defs


async def test_platform_context_current_values(monkeypatch):
    plugin = plugins.WirecloudKeycloakPlugin(None)
    plugins.IDM_SUPPORT_ENABLED = False
    monkeypatch.setattr(plugins.settings, "OID_CONNECT_PLUGIN", "keycloak")
    assert await plugin.get_platform_context_current_values(None, None, None, None) == {}

    plugins.IDM_SUPPORT_ENABLED = True
    monkeypatch.setattr(plugins.settings, "OID_CONNECT_CLIENT_ID", "wc-client")
    values = await plugin.get_platform_context_current_values(None, None, _sample_user({}), None)
    assert values["fiware_token_available"] is False
    assert values["keycloak_session"] is None

    user = _sample_user({"keycloak": {"idm_session": "sid"}})
    values = await plugin.get_platform_context_current_values(None, None, user, None)
    assert values["fiware_token_available"] is True
    assert values["keycloak_client_id"] == "wc-client"
    assert values["keycloak_session"] == "sid"


async def test_get_authorization_url_function(monkeypatch):
    plugin = plugins.WirecloudKeycloakPlugin(None)
    monkeypatch.setattr(
        plugins.settings,
        "OID_CONNECT_DATA",
        {"authorization_endpoint": "https://kc/auth?existing=1", "scopes": ["openid", "profile"]},
        raising=False,
    )
    monkeypatch.setattr(plugins.settings, "OID_CONNECT_CLIENT_ID", "client-a")

    fn = plugin.get_idm_get_authorization_url_functions()["keycloak"]
    url_template = fn()
    assert "existing=1" in url_template.urlpattern
    assert "client_id=client-a" in url_template.urlpattern
    assert "response_type=code" in url_template.urlpattern
    assert "scope=openid%20profile" in url_template.urlpattern

    monkeypatch.setattr(
        plugins.settings,
        "OID_CONNECT_DATA",
        {"authorization_endpoint": "https://kc/auth", "scopes": ["openid"]},
        raising=False,
    )
    url_template2 = fn()
    assert "?" in url_template2.urlpattern
    assert "scope=openid" in url_template2.urlpattern


async def test_get_token_function_paths(monkeypatch):
    plugin = plugins.WirecloudKeycloakPlugin(None)
    _set_common_settings(monkeypatch)
    monkeypatch.setattr(plugins.settings, "OID_CONNECT_DATA", {"token_endpoint": "https://kc/token", "scopes": ["openid", "profile"]}, raising=False)

    fn = plugin.get_idm_get_token_functions()["keycloak"]

    with pytest.raises(ValueError, match="Either code or refresh_token must be provided"):
        await fn(code=None, refresh_token=None, redirect_uri="http://cb")

    async def _request_ok(_endpoint, _data, **_kwargs):
        return {"scope": "openid profile", "access_token": "a", "refresh_token": "r"}

    monkeypatch.setattr(plugins, "make_oidc_provider_request", _request_ok)
    data = await fn(code="code", refresh_token=None, redirect_uri="http://cb")
    assert data["access_token"] == "a"

    monkeypatch.setattr(plugins.settings, "OID_CONNECT_CLIENT_SECRET", "secret")
    captured = {}

    async def _request_with_capture(_endpoint, data, **_kwargs):
        captured.update(data)
        return {"scope": "openid profile", "access_token": "a", "refresh_token": "r"}

    monkeypatch.setattr(plugins, "make_oidc_provider_request", _request_with_capture)
    await fn(code="code2", refresh_token=None, redirect_uri="http://cb2")
    assert captured["client_secret"] == "secret"

    async def _request_boom(*_args, **_kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(plugins, "make_oidc_provider_request", _request_boom)
    with pytest.raises(ValueError, match="Exception while requesting OIDC access token"):
        await fn(code="code", refresh_token=None, redirect_uri="http://cb")

    async def _missing_scope(*_args, **_kwargs):
        return {"scope": "openid", "access_token": "a", "refresh_token": "r"}

    monkeypatch.setattr(plugins, "make_oidc_provider_request", _missing_scope)
    with pytest.raises(ValueError, match="invalid scope"):
        await fn(code="code", refresh_token=None, redirect_uri="http://cb")

    async def _missing_tokens(*_args, **_kwargs):
        return {"scope": "openid profile"}

    monkeypatch.setattr(plugins, "make_oidc_provider_request", _missing_tokens)
    with pytest.raises(ValueError, match="missing access_token or refresh_token"):
        await fn(code="code", refresh_token=None, redirect_uri="http://cb")

    async def _refresh_ok(_endpoint, data, **_kwargs):
        assert data["grant_type"] == "refresh_token"
        return {"access_token": "na", "refresh_token": "nr"}

    monkeypatch.setattr(plugins, "make_oidc_provider_request", _refresh_ok)
    refresh_data = await fn(code=None, refresh_token="rr", redirect_uri=None)
    assert refresh_data["refresh_token"] == "nr"

    async def _refresh_missing(*_args, **_kwargs):
        return {"access_token": "na"}

    monkeypatch.setattr(plugins, "make_oidc_provider_request", _refresh_missing)
    with pytest.raises(ValueError, match="missing access_token or refresh_token"):
        await fn(code=None, refresh_token="rr", redirect_uri=None)

    monkeypatch.setattr(plugins.settings, "OID_CONNECT_CLIENT_SECRET", None)
    monkeypatch.setattr(plugins, "make_oidc_provider_request", _request_boom)
    with pytest.raises(ValueError, match="Exception while requesting OIDC access token"):
        await fn(code=None, refresh_token="rr", redirect_uri=None)


async def test_get_user_function_paths(monkeypatch):
    plugin = plugins.WirecloudKeycloakPlugin(None)
    monkeypatch.setattr(plugins.settings, "OID_CONNECT_DATA", {"userinfo_endpoint": "https://kc/userinfo"}, raising=False)
    fn = plugin.get_idm_get_user_functions()["keycloak"]

    with pytest.raises(ValueError, match="Access token must be provided"):
        await fn({})

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(plugins, "make_oidc_provider_request", _boom)
    with pytest.raises(ValueError, match="Exception while requesting OIDC access token"):
        await fn({"access_token": "a"})

    async def _no_preferred(*_args, **_kwargs):
        return {"sub": "1"}

    monkeypatch.setattr(plugins, "make_oidc_provider_request", _no_preferred)
    with pytest.raises(ValueError, match="missing preferred_username"):
        await fn({"access_token": "a"})

    async def _ok(*_args, **_kwargs):
        return {"preferred_username": "alice"}

    monkeypatch.setattr(plugins, "make_oidc_provider_request", _ok)
    assert (await fn({"access_token": "a"}))["preferred_username"] == "alice"


async def test_backchannel_logout_function_paths(monkeypatch):
    plugin = plugins.WirecloudKeycloakPlugin(None)
    fn = plugin.get_idm_backchannel_logout_functions()["keycloak"]

    with pytest.raises(ValueError, match="Access token must be provided"):
        await fn("")

    monkeypatch.setattr(plugins.settings, "OID_CONNECT_BACKCHANNEL_LOGOUT", False)
    await fn("refresh")

    monkeypatch.setattr(plugins.settings, "OID_CONNECT_BACKCHANNEL_LOGOUT", True)
    monkeypatch.setattr(plugins.settings, "OID_CONNECT_CLIENT_ID", "cid")
    monkeypatch.setattr(plugins.settings, "OID_CONNECT_CLIENT_SECRET", "sec")
    monkeypatch.setattr(plugins.settings, "OID_CONNECT_DATA", {"end_session_endpoint": "https://kc/logout"}, raising=False)
    captured = {}

    async def _ok(endpoint, data, **_kwargs):
        captured["endpoint"] = endpoint
        captured["data"] = data
        return None

    monkeypatch.setattr(plugins, "make_oidc_provider_request", _ok)
    await fn("refresh-1")
    assert captured["endpoint"] == "https://kc/logout"
    assert captured["data"]["client_secret"] == "sec"

    monkeypatch.setattr(plugins.settings, "OID_CONNECT_CLIENT_SECRET", None)
    captured2 = {}

    async def _ok_no_secret(endpoint, data, **_kwargs):
        captured2["endpoint"] = endpoint
        captured2["data"] = data
        return None

    monkeypatch.setattr(plugins, "make_oidc_provider_request", _ok_no_secret)
    await fn("refresh-1b")
    assert captured2["endpoint"] == "https://kc/logout"
    assert "client_secret" not in captured2["data"]

    logs = []
    monkeypatch.setattr(plugins.logger, "error", lambda msg: logs.append(msg))

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("logout failed")

    monkeypatch.setattr(plugins, "make_oidc_provider_request", _boom)
    await fn("refresh-2")
    assert logs


async def test_config_validator_non_keycloak_and_disabled(monkeypatch):
    plugin = plugins.WirecloudKeycloakPlugin(None)
    validator = plugin.get_config_validators()[0]
    plugins.IDM_SUPPORT_ENABLED = False

    cfg = SimpleNamespace(OID_CONNECT_PLUGIN="other", OID_CONNECT_ENABLED=True)
    await validator(cfg, offline=False)
    assert plugins.IDM_SUPPORT_ENABLED is False

    cfg2 = SimpleNamespace(OID_CONNECT_PLUGIN="keycloak", OID_CONNECT_ENABLED=False)
    await validator(cfg2, offline=False)
    assert plugins.IDM_SUPPORT_ENABLED is False


async def test_config_validator_discovery_transport_errors(monkeypatch):
    plugin = plugins.WirecloudKeycloakPlugin(None)
    validator = plugin.get_config_validators()[0]
    plugins.IDM_SUPPORT_ENABLED = False

    cfg = SimpleNamespace(
        OID_CONNECT_PLUGIN="keycloak",
        OID_CONNECT_ENABLED=True,
        OID_CONNECT_DISCOVERY_URL="https://kc/.well-known",
        WIRECLOUD_HTTPS_VERIFY=True,
    )

    bad_session = _FakeSession(get_error=True)
    monkeypatch.setattr(plugins.aiohttp, "ClientSession", lambda: bad_session)
    with pytest.raises(ValueError, match="OID_CONNECT_DISCOVERY_URL is not valid or reachable"):
        await validator(cfg, offline=False)
    assert bad_session.closed is True

    bad_status_session = _FakeSession(response=_FakeResponse(status=500, data={}))
    monkeypatch.setattr(plugins.aiohttp, "ClientSession", lambda: bad_status_session)
    with pytest.raises(ValueError, match="OID_CONNECT_DISCOVERY_URL is not valid or reachable"):
        await validator(cfg, offline=False)
    assert bad_status_session.closed is True

    bad_json_session = _FakeSession(response=_FakeResponse(status=200, data={}, json_error=True))
    monkeypatch.setattr(plugins.aiohttp, "ClientSession", lambda: bad_json_session)
    with pytest.raises(ValueError, match="OID_CONNECT_DISCOVERY_URL is not valid or reachable"):
        await validator(cfg, offline=False)
    assert bad_json_session.closed is True


@pytest.mark.parametrize(
    "missing_key,error",
    [
        ("issuer", "OID_CONNECT_DISCOVERY_URL does not contain issuer"),
        ("authorization_endpoint", "OID_CONNECT_DISCOVERY_URL does not contain authorization_endpoint"),
        ("token_endpoint", "OID_CONNECT_DISCOVERY_URL does not contain token_endpoint"),
        ("userinfo_endpoint", "OID_CONNECT_DISCOVERY_URL does not contain userinfo_endpoint"),
        ("end_session_endpoint", "OID_CONNECT_DISCOVERY_URL does not contain end_session_endpoint"),
        ("scopes_supported", "OID_CONNECT_DISCOVERY_URL does not contain scopes_supported"),
        ("response_types_supported", "OID_CONNECT_DISCOVERY_URL does not contain response_types_supported"),
        ("grant_types_supported", "OID_CONNECT_DISCOVERY_URL does not contain grant_types_supported"),
    ],
)
async def test_config_validator_discovery_required_keys(monkeypatch, missing_key, error):
    plugin = plugins.WirecloudKeycloakPlugin(None)
    validator = plugin.get_config_validators()[0]

    discovery = {
        "issuer": "https://kc",
        "authorization_endpoint": "https://kc/auth",
        "token_endpoint": "https://kc/token",
        "userinfo_endpoint": "https://kc/userinfo",
        "end_session_endpoint": "https://kc/logout",
        "scopes_supported": ["openid", "profile", "offline_access"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
    }
    del discovery[missing_key]

    session = _FakeSession(response=_FakeResponse(status=200, data=discovery))
    monkeypatch.setattr(plugins.aiohttp, "ClientSession", lambda: session)

    cfg = SimpleNamespace(
        OID_CONNECT_PLUGIN="keycloak",
        OID_CONNECT_ENABLED=True,
        OID_CONNECT_DISCOVERY_URL="https://kc/.well-known",
        WIRECLOUD_HTTPS_VERIFY=True,
    )

    with pytest.raises(ValueError, match=error):
        await validator(cfg, offline=False)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("scopes_supported", "no-list", "OID_CONNECT_DISCOVERY_URL scopes_supported is not a list"),
        ("response_types_supported", "no-list", "OID_CONNECT_DISCOVERY_URL response_types_supported is not a list"),
        ("grant_types_supported", "no-list", "OID_CONNECT_DISCOVERY_URL grant_types_supported is not a list"),
    ],
)
async def test_config_validator_discovery_type_checks(monkeypatch, field, value, error):
    plugin = plugins.WirecloudKeycloakPlugin(None)
    validator = plugin.get_config_validators()[0]

    discovery = {
        "issuer": "https://kc",
        "authorization_endpoint": "https://kc/auth",
        "token_endpoint": "https://kc/token",
        "userinfo_endpoint": "https://kc/userinfo",
        "end_session_endpoint": "https://kc/logout",
        "scopes_supported": ["openid", "profile", "offline_access"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
    }
    discovery[field] = value

    session = _FakeSession(response=_FakeResponse(status=200, data=discovery))
    monkeypatch.setattr(plugins.aiohttp, "ClientSession", lambda: session)

    cfg = SimpleNamespace(
        OID_CONNECT_PLUGIN="keycloak",
        OID_CONNECT_ENABLED=True,
        OID_CONNECT_DISCOVERY_URL="https://kc/.well-known",
        WIRECLOUD_HTTPS_VERIFY=True,
    )

    with pytest.raises(ValueError, match=error):
        await validator(cfg, offline=False)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("scopes_supported", ["profile", "offline_access"], "scopes_supported does not contain openid"),
        ("scopes_supported", ["openid", "offline_access"], "scopes_supported does not contain profile"),
        ("scopes_supported", ["openid", "profile"], "scopes_supported does not contain offline_access"),
        ("response_types_supported", ["token"], "response_types_supported does not contain code"),
        ("grant_types_supported", ["client_credentials"], "grant_types_supported does not contain authorization_code"),
    ],
)
async def test_config_validator_discovery_required_values(monkeypatch, field, value, error):
    plugin = plugins.WirecloudKeycloakPlugin(None)
    validator = plugin.get_config_validators()[0]

    discovery = {
        "issuer": "https://kc",
        "authorization_endpoint": "https://kc/auth",
        "token_endpoint": "https://kc/token",
        "userinfo_endpoint": "https://kc/userinfo",
        "end_session_endpoint": "https://kc/logout",
        "scopes_supported": ["openid", "profile", "offline_access"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
    }
    discovery[field] = value

    session = _FakeSession(response=_FakeResponse(status=200, data=discovery))
    monkeypatch.setattr(plugins.aiohttp, "ClientSession", lambda: session)

    cfg = SimpleNamespace(
        OID_CONNECT_PLUGIN="keycloak",
        OID_CONNECT_ENABLED=True,
        OID_CONNECT_DISCOVERY_URL="https://kc/.well-known",
        WIRECLOUD_HTTPS_VERIFY=True,
    )

    with pytest.raises(ValueError, match=error):
        await validator(cfg, offline=False)


async def test_config_validator_discovery_jwks_paths_and_success(monkeypatch):
    plugin = plugins.WirecloudKeycloakPlugin(None)
    validator = plugin.get_config_validators()[0]

    cfg = SimpleNamespace(
        OID_CONNECT_PLUGIN="keycloak",
        OID_CONNECT_ENABLED=True,
        OID_CONNECT_DISCOVERY_URL="https://kc/.well-known",
        WIRECLOUD_HTTPS_VERIFY=True,
    )

    discovery_no_jwks = {
        "issuer": "https://kc",
        "authorization_endpoint": "https://kc/auth",
        "token_endpoint": "https://kc/token",
        "userinfo_endpoint": "https://kc/userinfo",
        "end_session_endpoint": "https://kc/logout",
        "scopes_supported": ["openid", "profile", "offline_access"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
    }

    warnings = []
    monkeypatch.setattr(plugins.logger, "warning", lambda msg: warnings.append(msg))
    session = _FakeSession(response=_FakeResponse(status=200, data=discovery_no_jwks))
    monkeypatch.setattr(plugins.aiohttp, "ClientSession", lambda: session)
    monkeypatch.setattr(plugins, "make_oidc_provider_request", lambda *_a, **_k: {"keys": []})
    await validator(cfg, offline=False)
    assert warnings
    assert cfg.OID_CONNECT_DATA["keys"] == {}

    discovery_with_jwks = discovery_no_jwks | {"jwks_uri": "https://kc/jwks", "scopes_supported": ["openid", "profile", "offline_access", "email", "wirecloud"], "check_session_iframe": "https://kc/iframe"}

    session2 = _FakeSession(response=_FakeResponse(status=200, data=discovery_with_jwks))
    monkeypatch.setattr(plugins.aiohttp, "ClientSession", lambda: session2)

    async def _jwks_req(url, *_args, **_kwargs):
        assert url == "https://kc/jwks"
        return {"keys": [{"kid": "a"}, {"kid": "b"}]}

    monkeypatch.setattr(plugins, "make_oidc_provider_request", _jwks_req)
    monkeypatch.setattr(plugins, "format_jwks_key", lambda key_data: f"pem-{key_data['kid']}".encode("ascii"))

    await validator(cfg, offline=False)
    data = cfg.OID_CONNECT_DATA
    assert data["keys"]["a"] == b"pem-a"
    assert data["keys"]["b"] == b"pem-b"
    assert "email" in data["scopes"] and "wirecloud" in data["scopes"]
    assert data["check_session_iframe"] == "https://kc/iframe"

    session3 = _FakeSession(response=_FakeResponse(status=200, data=discovery_with_jwks))
    monkeypatch.setattr(plugins.aiohttp, "ClientSession", lambda: session3)

    async def _jwks_invalid(*_args, **_kwargs):
        return {"keys": [{"x": 1}, {"kid": "bad"}]}

    monkeypatch.setattr(plugins, "make_oidc_provider_request", _jwks_invalid)

    def _format_or_fail(key_data):
        if key_data["kid"] == "bad":
            raise ValueError("bad key")
        return b"ignored"

    monkeypatch.setattr(plugins, "format_jwks_key", _format_or_fail)
    await validator(cfg, offline=False)
    assert any("without kid" in w for w in warnings) or any("invalid key" in w for w in warnings)


async def test_config_validator_discovery_jwks_errors(monkeypatch):
    plugin = plugins.WirecloudKeycloakPlugin(None)
    validator = plugin.get_config_validators()[0]

    cfg = SimpleNamespace(
        OID_CONNECT_PLUGIN="keycloak",
        OID_CONNECT_ENABLED=True,
        OID_CONNECT_DISCOVERY_URL="https://kc/.well-known",
        WIRECLOUD_HTTPS_VERIFY=True,
    )

    discovery = {
        "issuer": "https://kc",
        "authorization_endpoint": "https://kc/auth",
        "token_endpoint": "https://kc/token",
        "userinfo_endpoint": "https://kc/userinfo",
        "end_session_endpoint": "https://kc/logout",
        "scopes_supported": ["openid", "profile", "offline_access"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "jwks_uri": "https://kc/jwks",
    }
    session = _FakeSession(response=_FakeResponse(status=200, data=discovery))
    monkeypatch.setattr(plugins.aiohttp, "ClientSession", lambda: session)

    async def _jwks_boom(*_args, **_kwargs):
        raise RuntimeError("nope")

    monkeypatch.setattr(plugins, "make_oidc_provider_request", _jwks_boom)
    with pytest.raises(ValueError, match="Exception while requesting OIDC jwks_uri"):
        await validator(cfg, offline=False)

    async def _jwks_no_keys(*_args, **_kwargs):
        return {"not_keys": []}

    monkeypatch.setattr(plugins, "make_oidc_provider_request", _jwks_no_keys)
    with pytest.raises(ValueError, match="OIDC provider jwks_uri does not contain keys"):
        await validator(cfg, offline=False)


@pytest.mark.parametrize(
    "data,error",
    [
        (None, "OID_CONNECT_DATA must be set if OID_CONNECT_DISCOVERY_URL is not set"),
        ({"x": 1}, "OID_CONNECT_DATA must contain issuer as a string"),
        ({"issuer": 1}, "OID_CONNECT_DATA must contain issuer as a string"),
        ({"issuer": "i"}, "OID_CONNECT_DATA must contain authorization_endpoint as a string"),
        ({"issuer": "i", "authorization_endpoint": 1}, "OID_CONNECT_DATA must contain authorization_endpoint as a string"),
        ({"issuer": "i", "authorization_endpoint": "a"}, "OID_CONNECT_DATA must contain token_endpoint as a string"),
        ({"issuer": "i", "authorization_endpoint": "a", "token_endpoint": 1}, "OID_CONNECT_DATA must contain token_endpoint as a string"),
        ({"issuer": "i", "authorization_endpoint": "a", "token_endpoint": "t"}, "OID_CONNECT_DATA must contain userinfo_endpoint as a string"),
        ({"issuer": "i", "authorization_endpoint": "a", "token_endpoint": "t", "userinfo_endpoint": 1}, "OID_CONNECT_DATA must contain userinfo_endpoint as a string"),
        ({"issuer": "i", "authorization_endpoint": "a", "token_endpoint": "t", "userinfo_endpoint": "u"}, "OID_CONNECT_DATA must contain scopes as a list"),
        ({"issuer": "i", "authorization_endpoint": "a", "token_endpoint": "t", "userinfo_endpoint": "u", "scopes": "x"}, "OID_CONNECT_DATA must contain scopes as a list"),
        ({"issuer": "i", "authorization_endpoint": "a", "token_endpoint": "t", "userinfo_endpoint": "u", "scopes": []}, "OID_CONNECT_DATA scopes must contain openid"),
        ({"issuer": "i", "authorization_endpoint": "a", "token_endpoint": "t", "userinfo_endpoint": "u", "scopes": ["openid"], "check_session_iframe": 1}, "OID_CONNECT_DATA check_session_iframe must be a string"),
    ],
)
async def test_config_validator_manual_data_validation(monkeypatch, data, error):
    plugin = plugins.WirecloudKeycloakPlugin(None)
    validator = plugin.get_config_validators()[0]

    cfg = SimpleNamespace(
        OID_CONNECT_PLUGIN="keycloak",
        OID_CONNECT_ENABLED=True,
        OID_CONNECT_DISCOVERY_URL=None,
        OID_CONNECT_DATA=data,
        OID_CONNECT_BACKCHANNEL_LOGOUT=False,
    )

    with pytest.raises(ValueError, match=error):
        await validator(cfg, offline=False)


async def test_config_validator_manual_data_backchannel_and_keys(monkeypatch):
    plugin = plugins.WirecloudKeycloakPlugin(None)
    validator = plugin.get_config_validators()[0]

    cfg = SimpleNamespace(
        OID_CONNECT_PLUGIN="keycloak",
        OID_CONNECT_ENABLED=True,
        OID_CONNECT_DISCOVERY_URL=None,
        OID_CONNECT_DATA={
            "issuer": "https://kc",
            "authorization_endpoint": "https://kc/auth",
            "token_endpoint": "https://kc/token",
            "userinfo_endpoint": "https://kc/user",
            "scopes": ["openid"],
        },
        OID_CONNECT_BACKCHANNEL_LOGOUT=True,
    )

    with pytest.raises(ValueError, match="OID_CONNECT_DATA must contain end_session_endpoint as a string"):
        await validator(cfg, offline=False)

    cfg.OID_CONNECT_BACKCHANNEL_LOGOUT = False
    warnings = []
    monkeypatch.setattr(plugins.logger, "warning", lambda msg: warnings.append(msg))

    await validator(cfg, offline=False)
    assert cfg.OID_CONNECT_DATA["keys"] == {}
    assert warnings

    cfg_ok = SimpleNamespace(
        OID_CONNECT_PLUGIN="keycloak",
        OID_CONNECT_ENABLED=True,
        OID_CONNECT_DISCOVERY_URL=None,
        OID_CONNECT_DATA={
            "issuer": "https://kc",
            "authorization_endpoint": "https://kc/auth",
            "token_endpoint": "https://kc/token",
            "userinfo_endpoint": "https://kc/user",
            "scopes": ["openid"],
            "keys": {"kid": b"pem"},
            "check_session_iframe": "https://kc/iframe",
        },
        OID_CONNECT_BACKCHANNEL_LOGOUT=False,
    )
    await validator(cfg_ok, offline=False)


async def test_config_validator_offline_shortcuts():
    plugin = plugins.WirecloudKeycloakPlugin(None)
    validator = plugin.get_config_validators()[0]

    cfg = SimpleNamespace(
        OID_CONNECT_PLUGIN="keycloak",
        OID_CONNECT_ENABLED=True,
        OID_CONNECT_DISCOVERY_URL="https://kc/.well-known",
        OID_CONNECT_DATA=None,
        OID_CONNECT_BACKCHANNEL_LOGOUT=False,
    )
    await validator(cfg, offline=True)
