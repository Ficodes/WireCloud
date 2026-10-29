# Configuration

WireCloud loads a Python module named `settings`. The Docker image adds `/app/docker` to `PYTHONPATH`, so the environment-driven `docker/settings.py` module is loaded automatically.

For containers, configure the variables below in `docker/.env` or through your deployment platform. Boolean values accept `1`, `true`, `yes`, or `on` without regard to case.

## Core settings

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `WIRECLOUD_DEBUG` | `false` | Include additional error details. Keep false in production. |
| `WIRECLOUD_BASEDIR` | `/var/lib/wirecloud` | Base persistent data directory. It must exist. |
| `WIRECLOUD_ALLOW_ANONYMOUS_ACCESS` | `true` | Allow unauthenticated visitors to open public workspaces. |
| `WIRECLOUD_INSTALLED_APPS` | core app list | Comma-separated Python modules that provide WireCloud plugins. |
| `WIRECLOUD_DEFAULT_LANGUAGE` | `en` | Fallback language code. It must be present in `WIRECLOUD_LANGUAGES`. |
| `WIRECLOUD_LANGUAGES` | `en:English,es:Spanish,pt:Portuguese` | Comma-separated `code:label` entries. |
| `WIRECLOUD_AVAILABLE_THEMES` | `defaulttheme` | Comma-separated theme names. Bundled themes: `defaulttheme`, `industrytheme` (light and dark color schemes), `fiwaretheme`, `fiwarelabtheme` and `fiwarelabdarktheme`. |
| `WIRECLOUD_THEME_ACTIVE` | `defaulttheme` | Default theme; it must be in the available theme list. |

The default installed apps are `wirecloud.commons`, `wirecloud.platform`, `wirecloud.catalogue`, `wirecloud.proxy`, `wirecloud.fiware`, and `wirecloud.keycloak`. The commons and catalogue apps are required. Enabling the platform app also requires the proxy app.

## Security and sessions

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `WIRECLOUD_JWT_KEY` | insecure placeholder | Signs authentication and CSRF tokens. Use a unique secret of at least 32 characters. |
| `WIRECLOUD_SECRET_KEY` | insecure placeholder | General application secret. Use a different unique value of at least 32 characters. |
| `WIRECLOUD_SESSION_AGE` | `1209600` | Session lifetime in seconds (14 days by default). |
| `WIRECLOUD_HTTPS_VERIFY` | `true` | Verify TLS certificates for outbound HTTPS calls. |

Changing `WIRECLOUD_JWT_KEY` invalidates existing login and CSRF tokens. Never commit production secrets to the repository or bake them into an image.

For an HTTPS deployment, the application also needs the Python setting
`WIRECLOUD_HTTPS = True` so session cookies receive the `Secure` attribute. The
current environment-driven Docker settings do not map a `WIRECLOUD_HTTPS`
variable; provide this value through a custom `settings.py` (for example, in a
derived image) when deploying the supplied container behind HTTPS.

## MongoDB

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `WIRECLOUD_DB_DRIVER` | `mongodb` | Runtime database driver. The current application data layer uses MongoDB. |
| `WIRECLOUD_DB_NAME` | `wirecloud` | MongoDB database name. |
| `WIRECLOUD_DB_HOST` | `mongodb` | MongoDB hostname. |
| `WIRECLOUD_DB_PORT` | `27017` | MongoDB port. |
| `WIRECLOUD_DB_USER` | empty | Optional MongoDB username. |
| `WIRECLOUD_DB_PASSWORD` | empty | Optional MongoDB password. |
| `WIRECLOUD_DB_USE_TRANSACTIONS` | `true` | Attempt MongoDB transactions. |

Standalone MongoDB deployments do not support transactions. WireCloud detects the corresponding server error and continues without transactions. Use a replica set when transactional behavior is required.

The `mysql` and `postgresql` names accepted by parts of settings validation are for migration-related compatibility; the WireCloud runtime database implementation builds a MongoDB connection.

## Elasticsearch

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `WIRECLOUD_ES_HOST` | `elasticsearch` | Elasticsearch hostname. |
| `WIRECLOUD_ES_PORT` | `9200` | Elasticsearch port. |
| `WIRECLOUD_ES_USER` | empty | Optional basic-auth username. |
| `WIRECLOUD_ES_PASSWORD` | empty | Optional basic-auth password. |
| `WIRECLOUD_ES_SECURE` | `false` | Use HTTPS to connect to Elasticsearch. |

Search indexes are derived data. After restoring MongoDB or performing a migration, run `python -m manage rebuildsearchindexes`.

## Persistent paths and cache

| Environment variable | Default under `WIRECLOUD_BASEDIR` | Purpose |
| --- | --- | --- |
| `WIRECLOUD_CATALOGUE_MEDIA_ROOT` | `catalogue/media` | Uploaded component packages and catalogue media. |
| `WIRECLOUD_WIDGET_DEPLOYMENT_DIR` | `deployment/widgets` | Extracted widget assets served to browsers. |
| `WIRECLOUD_CACHE_DIR` | `cache` | On-disk application cache files. |
| `WIRECLOUD_CACHE_TTL` | `3600` | In-memory cache lifetime in seconds. |

Back up the catalogue media and deployment directories with MongoDB. The in-memory cache and Elasticsearch indexes can be rebuilt.

## Proxy controls

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `WIRECLOUD_PROXY_WS_MAX_MSG_SIZE` | `4194304` | Maximum proxied WebSocket message size in bytes. |
| `WIRECLOUD_PROXY_WHITELIST_ENABLED` | `false` | Allow proxy destinations only when listed. |
| `WIRECLOUD_PROXY_WHITELIST` | empty | Comma-separated allowed entries. |
| `WIRECLOUD_PROXY_BLACKLIST_ENABLED` | `false` | Block listed proxy destinations. |
| `WIRECLOUD_PROXY_BLACKLIST` | empty | Comma-separated blocked entries. |

The proxy exists so components can reach services that would otherwise be blocked by browser cross-origin rules. Treat it as an outbound network boundary. An enabled but empty allowlist blocks all destinations.

## OpenID Connect and Keycloak

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `WIRECLOUD_OIDC_ENABLED` | `false` | Enable OpenID Connect login. |
| `WIRECLOUD_OIDC_DISCOVERY_URL` | empty | Provider discovery document URL. |
| `WIRECLOUD_OIDC_CLIENT_ID` | empty | OIDC client identifier. |
| `WIRECLOUD_OIDC_CLIENT_SECRET` | empty | OIDC client secret. |
| `WIRECLOUD_OIDC_PLUGIN` | `keycloak` | Installed plugin implementing the provider integration. |
| `WIRECLOUD_OIDC_FULLY_SYNC_GROUPS` | `false` | Replace local group membership with groups supplied at OIDC login. |
| `WIRECLOUD_OIDC_BACKCHANNEL_LOGOUT` | `false` | Notify the provider when a WireCloud session ends. This is separate from provider-initiated logout. |

When OIDC is enabled, the client ID, client secret, plugin, and provider metadata are required. For Keycloak, configure the callback URL as:

```text
https://wirecloud.example.com/oidc/callback
```

The discovery document is fetched and validated during application startup. Keep `WIRECLOUD_HTTPS_VERIFY=true`; fix the provider's certificate chain instead of disabling verification in production.

Keycloak is optional but recommended for shared and production deployments. The
[Keycloak installation procedure](installation.md#optional-but-recommended-keycloak-single-sign-on)
covers the confidential client, exact redirect URI, required scopes, UserInfo
claims, optional group mapper, both logout directions, and verification steps.
Be especially careful with `WIRECLOUD_OIDC_FULLY_SYNC_GROUPS=true`: it makes the
identity provider authoritative and discards local group membership at each
OIDC login before applying the supplied groups.

## Python settings modules

Non-container deployments can define equivalent uppercase values directly in a `settings.py` module. Dictionary settings such as `DATABASE` and `ELASTICSEARCH` and sequence settings such as `LANGUAGES` are validated at startup. Review `docker/settings.py` for the complete environment mapping. Settings that are not mapped there, such as `WIRECLOUD_HTTPS`, must be supplied by a custom Python settings module.
