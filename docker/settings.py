# -*- coding: utf-8 -*-

import os
from aiocache import caches


def _env_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _env_csv(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_languages(name: str, default: list[tuple[str, str]]) -> list[tuple[str, str]]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default

    result: list[tuple[str, str]] = []
    for entry in value.split(","):
        item = entry.strip()
        if not item:
            continue
        if ":" in item:
            code, label = item.split(":", 1)
            result.append((code.strip(), label.strip() or code.strip()))
        else:
            result.append((item, item))
    return result or default


DEBUG = _env_bool("WIRECLOUD_DEBUG", False)
MCP_PUBLIC_URL = _env_str("WIRECLOUD_MCP_PUBLIC_URL", "")
AUTH_PUBLIC_URL = _env_str("WIRECLOUD_AUTH_PUBLIC_URL", "")
MCP_ALLOWED_ORIGINS = _env_csv("WIRECLOUD_MCP_ALLOWED_ORIGINS", [])
OAUTH2_PUBLIC_URL = _env_str("WIRECLOUD_OAUTH2_PUBLIC_URL", "")
OAUTH2_DYNAMIC_REGISTRATION = _env_bool("WIRECLOUD_OAUTH2_DYNAMIC_REGISTRATION", True)

BASEDIR = _env_str("WIRECLOUD_BASEDIR", "/var/lib/wirecloud")
ALLOW_ANONYMOUS_ACCESS = _env_bool("WIRECLOUD_ALLOW_ANONYMOUS_ACCESS", True)

INSTALLED_APPS = tuple(_env_csv("WIRECLOUD_INSTALLED_APPS", [
    "wirecloud.commons",
    "wirecloud.platform",
    "wirecloud.catalogue",
    "wirecloud.proxy",
    "wirecloud.fiware",
    "wirecloud.keycloak",
]))

DATABASE = {
    "DRIVER": _env_str("WIRECLOUD_DB_DRIVER", "mongodb"),
    "NAME": _env_str("WIRECLOUD_DB_NAME", "wirecloud"),
    "HOST": _env_str("WIRECLOUD_DB_HOST", "mongodb"),
    "PORT": _env_str("WIRECLOUD_DB_PORT", "27017"),
    "USER": _env_str("WIRECLOUD_DB_USER", ""),
    "PASSWORD": _env_str("WIRECLOUD_DB_PASSWORD", ""),
    "USE_TRANSACTIONS": _env_bool("WIRECLOUD_DB_USE_TRANSACTIONS", True),
}

ELASTICSEARCH = {
    "HOST": _env_str("WIRECLOUD_ES_HOST", "elasticsearch"),
    "PORT": _env_int("WIRECLOUD_ES_PORT", 9200),
    "USER": _env_str("WIRECLOUD_ES_USER", ""),
    "PASSWORD": _env_str("WIRECLOUD_ES_PASSWORD", ""),
    "SECURE": _env_bool("WIRECLOUD_ES_SECURE", False),
}

LANGUAGES = tuple(_env_languages("WIRECLOUD_LANGUAGES", [
    ("en", "English"),
    ("es", "Spanish"),
    ("pt", "Portuguese"),
]))

DEFAULT_LANGUAGE = _env_str("WIRECLOUD_DEFAULT_LANGUAGE", LANGUAGES[0][0])

JWT_KEY = _env_str("WIRECLOUD_JWT_KEY", "change-this-jwt-key-in-production-123456")
SECRET_KEY = _env_str("WIRECLOUD_SECRET_KEY", "change-this-secret-key-in-production-123456")
SESSION_AGE = _env_int("WIRECLOUD_SESSION_AGE", 60 * 60 * 24 * 14)

OID_CONNECT_ENABLED = _env_bool("WIRECLOUD_OIDC_ENABLED", False)
OID_CONNECT_DISCOVERY_URL = _env_str("WIRECLOUD_OIDC_DISCOVERY_URL", "")
OID_CONNECT_CLIENT_ID = _env_str("WIRECLOUD_OIDC_CLIENT_ID", "")
OID_CONNECT_CLIENT_SECRET = _env_str("WIRECLOUD_OIDC_CLIENT_SECRET", "")
OID_CONNECT_FULLY_SYNC_GROUPS = _env_bool("WIRECLOUD_OIDC_FULLY_SYNC_GROUPS", False)
OID_CONNECT_BACKCHANNEL_LOGOUT = _env_bool("WIRECLOUD_OIDC_BACKCHANNEL_LOGOUT", False)
OID_CONNECT_PLUGIN = _env_str("WIRECLOUD_OIDC_PLUGIN", "keycloak")

CATALOGUE_MEDIA_ROOT = _env_str("WIRECLOUD_CATALOGUE_MEDIA_ROOT", os.path.join(BASEDIR, "catalogue", "media"))
CACHE_DIR = _env_str("WIRECLOUD_CACHE_DIR", os.path.join(BASEDIR, "cache"))
WIDGET_DEPLOYMENT_DIR = _env_str("WIRECLOUD_WIDGET_DEPLOYMENT_DIR", os.path.join(BASEDIR, "deployment", "widgets"))

WIRECLOUD_HTTPS_VERIFY = _env_bool("WIRECLOUD_HTTPS_VERIFY", True)

AVAILABLE_THEMES = _env_csv("WIRECLOUD_AVAILABLE_THEMES", ["defaulttheme"])
THEME_ACTIVE = _env_str("WIRECLOUD_THEME_ACTIVE", AVAILABLE_THEMES[0])

PROXY_WS_MAX_MSG_SIZE = _env_int("WIRECLOUD_PROXY_WS_MAX_MSG_SIZE", 4 * 1024 * 1024)

PROXY_WHITELIST_ENABLED = _env_bool("WIRECLOUD_PROXY_WHITELIST_ENABLED", False)
PROXY_WHITELIST = _env_csv("WIRECLOUD_PROXY_WHITELIST", [])
PROXY_BLACKLIST_ENABLED = _env_bool("WIRECLOUD_PROXY_BLACKLIST_ENABLED", False)
PROXY_BLACKLIST = _env_csv("WIRECLOUD_PROXY_BLACKLIST", [])

caches.set_config({
    "default": {
        "cache": "aiocache.SimpleMemoryCache",
        "ttl": _env_int("WIRECLOUD_CACHE_TTL", 3600),
    }
})
cache = caches.get("default")
