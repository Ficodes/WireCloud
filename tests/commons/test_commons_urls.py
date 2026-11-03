# -*- coding: utf-8 -*-

from wirecloud.commons import urls


def test_get_urlpatterns_default_and_oidc(monkeypatch):
    original_login = urls.patterns["login"]
    try:
        monkeypatch.setattr(urls.settings, "OID_CONNECT_ENABLED", False)
        monkeypatch.setattr(urls.settings, "OID_CONNECT_PLUGIN", "")
        plain = urls.get_urlpatterns()
        assert plain["login"].urlpattern == "/login"
        assert plain["wirecloud.begin_login"].urlpattern == "/auth/login"

        monkeypatch.setattr(urls.settings, "OID_CONNECT_ENABLED", True)
        monkeypatch.setattr(urls.settings, "OID_CONNECT_PLUGIN", "keycloak")
        updated = urls.get_urlpatterns()
        assert updated["login"].urlpattern == "/auth/login"

        monkeypatch.setattr(urls.settings, "OID_CONNECT_PLUGIN", "missing")
        unchanged = urls.get_urlpatterns()
        assert unchanged["login"].urlpattern == "/auth/login"
    finally:
        urls.patterns["login"] = original_login
