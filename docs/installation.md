# Installation

WireCloud needs the application service, MongoDB, Elasticsearch, and writable persistent storage. The repository's Docker Compose stack is the reference deployment layout.

## Docker Compose

Use the complete procedure in [Getting started](getting-started.md). The supplied files provide:

- a multi-stage image build that compiles frontend assets and builds a Python wheel;
- a WireCloud container running Uvicorn on port 8000;
- MongoDB 7;
- Elasticsearch 8.13.4 in single-node mode; and
- named volumes for all persistent data.

For production, place a TLS-terminating reverse proxy or ingress in front of WireCloud, use externally managed secrets, apply resource limits, and replace the single-node data services with infrastructure matching your availability and backup requirements.

### Use a published Docker image

Each published release provides regular and MCP image variants, both supporting
`linux/amd64` and `linux/arm64`. Pin a release rather than relying on `latest` in
production:

```bash
docker pull ficodes/wirecloud:2.0.0
docker pull ficodes/wirecloud:2.0.0-mcp
```

The `-mcp` image includes the MCP SDK and its tested dependencies. Follow the
[MCP deployment settings](mcp.md#docker) to enable the OAuth and MCP plugins at
runtime. Stable releases also provide `latest` and `latest-mcp`, plus major/minor
aliases with the same suffix convention. Prereleases do not update those aliases.
The publishing repository can be overridden by CI's `DOCKER_IMAGE` variable;
check the release notes for its canonical location.

To use a published image with the supplied Compose stack, remove the `build`
block from the `wirecloud` service in `docker/docker-compose.yml` and set its
image explicitly:

```yaml
services:
  wirecloud:
    image: ficodes/wirecloud:2.0.0
```

Keep the environment, dependency services, ports, and volumes from the supplied
Compose file. Release images support `linux/amd64` and `linux/arm64`; runtime
configuration is supplied through the same environment variables documented in
[Configuration](configuration.md).

## Install from a release wheel

Published GitHub releases contain two standalone wheels:

| Wheel (example release) | Python | Dependencies |
| --- | --- | --- |
| `wirecloud-2.0.0-py3-none-any.whl` | 3.9+ | Regular WireCloud installation. |
| `wirecloud-2.0.0+mcp-py3-none-any.whl` | 3.11+ | WireCloud plus the MCP SDK and tested MCP dependency pins. |

Both are available in the `wirecloud-wheels` artifact on push and pull-request
workflow runs. Choose one wheel; each contains the complete application and
compiled frontend and translation catalogs, so installation needs Python but
does not need Node.js or npm.
The MCP wheel uses a `+mcp` local version label to distinguish the release asset
while retaining the same Python distribution name. Switching variants lets pip
replace the installed WireCloud distribution without overlapping packages.
The `+mcp` artifact is distributed through GitHub releases, rather than PyPI.

### Install from PyPI (planned)

WireCloud is not published on [PyPI](https://pypi.org/) yet. Once publication
starts, install the latest release directly from the Python package index:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install wirecloud
```

To deploy a specific release, pin its version:

```bash
python -m pip install "wirecloud==2.0.0"
```

The PyPI package will contain the same compiled frontend as the GitHub release
wheel. After installing it, create the `config/` and `data/` directories and
follow the configuration and startup instructions below.

### Install a wheel from GitHub

Create a small deployment project. Download a wheel from the release's
**Assets** section into `packages/`, or use the GitHub CLI:

```text
my-wirecloud/
├── .env
├── .venv/
├── config/
│   └── settings.py
├── data/
└── packages/
    └── wirecloud-2.0.0-py3-none-any.whl
```

```bash
mkdir -p my-wirecloud/packages
cd my-wirecloud
gh release download 2.0.0 --pattern '*.whl' --dir packages
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./packages/wirecloud-2.0.0-py3-none-any.whl
mkdir -p config data
```

For MCP, create the environment using Python 3.11 or newer and install the other
wheel instead:

```bash
python -m pip install './packages/wirecloud-2.0.0+mcp-py3-none-any.whl'
```

Pip installs its MCP dependencies automatically; no extra or constraints argument
is needed for this wheel. Enable the OAuth and MCP plugins and configure their
public URLs as described in [MCP setup](mcp.md#enable-the-plugin).

WireCloud imports a Python module named `settings`. Put the directory containing
the selected `settings.py` first on `PYTHONPATH`. For example, the following
`config/settings.py` configures a local MongoDB and Elasticsearch while keeping
the deployment state inside the project:

```python
import os
from pathlib import Path

from aiocache import caches


PROJECT_DIR = Path(__file__).resolve().parents[1]
BASEDIR = str(PROJECT_DIR / "data")

DEBUG = False
ALLOW_ANONYMOUS_ACCESS = False

INSTALLED_APPS = (
    "wirecloud.commons",
    "wirecloud.platform",
    "wirecloud.catalogue",
    "wirecloud.proxy",
    "wirecloud.fiware",
    "wirecloud.keycloak",
)

DATABASE = {
    "DRIVER": "mongodb",
    "NAME": "wirecloud",
    "HOST": "127.0.0.1",
    "PORT": "27017",
    "USER": "",
    "PASSWORD": "",
    "USE_TRANSACTIONS": False,
}

ELASTICSEARCH = {
    "HOST": "127.0.0.1",
    "PORT": 9200,
    "USER": "",
    "PASSWORD": "",
    "SECURE": False,
}

LANGUAGES = (("en", "English"), ("es", "Spanish"), ("pt", "Portuguese"))
DEFAULT_LANGUAGE = "en"

JWT_KEY = os.environ["WIRECLOUD_JWT_KEY"]
SECRET_KEY = os.environ["WIRECLOUD_SECRET_KEY"]
SESSION_AGE = 60 * 60 * 24 * 14

OID_CONNECT_ENABLED = False
WIRECLOUD_HTTPS_VERIFY = True

CACHE_DIR = str(PROJECT_DIR / "data" / "cache")
CATALOGUE_MEDIA_ROOT = str(PROJECT_DIR / "data" / "catalogue" / "media")
WIDGET_DEPLOYMENT_DIR = str(PROJECT_DIR / "data" / "deployment" / "widgets")

AVAILABLE_THEMES = ["defaulttheme"]
THEME_ACTIVE = "defaulttheme"

PROXY_WHITELIST_ENABLED = False
PROXY_WHITELIST = []
PROXY_BLACKLIST_ENABLED = False
PROXY_BLACKLIST = []

caches.set_config({
    "default": {
        "cache": "aiocache.SimpleMemoryCache",
        "ttl": 3600,
    }
})
cache = caches.get("default")
```

Store stable, unique values of at least 32 characters in `.env`; changing them
invalidates existing sessions. Do not commit this file:

```dotenv
WIRECLOUD_JWT_KEY=replace-with-a-stable-random-value-of-at-least-32-characters
WIRECLOUD_SECRET_KEY=replace-with-a-different-random-value-of-at-least-32-characters
```

Load the environment and select the configuration before using management
commands or starting the server:

```bash
set -a
. ./.env
set +a
export PYTHONPATH="$PWD/config"

python -m manage populate
python -m manage createsuperuser
uvicorn wirecloud.main:app --host 127.0.0.1 --port 8000
```

Keep `PYTHONPATH` set for every WireCloud command. To run a second instance with
a different configuration, point it at another directory containing its own
`settings.py`; the installed wheel can be shared, while database, search,
storage, secrets, and feature settings remain project-specific. See
[Configuration](configuration.md) for all available settings and production
guidance.

## Install from source

Source installations are useful for development and custom deployments. They require:

- Python 3.9 or newer;
- Node.js and npm;
- MongoDB;
- Elasticsearch; and
- build tools required by Python and Node dependencies.

Create a virtual environment and install the JavaScript dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
npm ci
```

Install WireCloud. The package build automatically compiles translations and
the frontend after `npm ci` has installed its toolchain:

```bash
python -m pip install .
```

Set `WIRECLOUD_SKIP_NPM_BUILD=1` only when the frontend artifacts were already
built and are present in the source tree.

Create a settings module named `settings.py` on the Python import path. The repository's `docker/settings.py` is the environment-driven production example; `src/settings.py` is intended for local development. Ensure that all configured storage directories exist and are writable.

Compiled translation catalogs (`.mo`) are generated during wheel builds,
including the wheel built by Docker. Source distributions contain the editable
`.po` catalogs. To compile translations in a source checkout, use the existing
management command:

```bash
python src/manage.py compiletranslations
```

Use `--language es` or `--language ja` to compile a single language. Recompile
after editing a `.po` file. Generated `.mo` files are ignored by Git.

Then initialize and run the instance:

```bash
python -m manage populate
python -m manage createsuperuser
python -m manage runserver --host 127.0.0.1 --port 8000
```

`manage runserver` is a development server. A production process can start the ASGI application directly:

```bash
uvicorn wirecloud.main:app --host 0.0.0.0 --port 8000
```

## Optional but recommended: Keycloak single sign-on

WireCloud can use its local accounts on their own, so Keycloak is not required.
For a shared or production instance, however, Keycloak is recommended: it
centralizes sign-in, multi-factor authentication, password policy, and account
lifecycle management. WireCloud still creates a local user record on the first
successful OpenID Connect (OIDC) login so that it can own workspaces, resources,
and permissions.

Keep at least one tested local WireCloud superuser as a break-glass account. An
identity-provider outage or a bad client configuration should not prevent all
administrative access.

### 1. Create the Keycloak client

In the Keycloak administration console:

1. Create or select the realm that will contain the WireCloud users.
2. Open **Clients**, create an **OpenID Connect** client, and use a stable client
   ID such as `wirecloud`.
3. Turn **Client authentication** on. This makes it a confidential, server-side
   client and provides the client secret that WireCloud requires.
4. Enable **Standard flow** (the authorization-code flow). Implicit flow,
   direct-access grants, and service-account roles are not needed for normal
   WireCloud login.
5. Add this exact **Valid redirect URI**, replacing the host with the public
   WireCloud URL:

   ```text
   https://wirecloud.example.com/oidc/callback
   ```

   Avoid a wildcard redirect URI in production. The scheme, host, port, and path
   must match the URL seen by the user's browser.
6. On the client's **Credentials** tab, copy the generated client secret into
   the deployment's secret store.

Leave Keycloak's built-in `profile` and `offline_access` client scopes available
to this client. WireCloud requests `openid profile offline_access`, uses the
UserInfo endpoint to create or update the user, and needs a refresh token for its
session and logout integration. It also requests `email` when the provider
advertises that scope.

The realm discovery URL normally has this form:

```text
https://sso.example.com/realms/example/.well-known/openid-configuration
```

For more detail about the client controls, see Keycloak's
[Server Administration Guide](https://www.keycloak.org/docs/latest/server_admin/#assembly-managing-clients_server_administration_guide).

### 2. Configure WireCloud

Set these variables in `docker/.env` or the equivalent secret/configuration
mechanism used by the deployment:

```dotenv
WIRECLOUD_OIDC_ENABLED=true
WIRECLOUD_OIDC_DISCOVERY_URL=https://sso.example.com/realms/example/.well-known/openid-configuration
WIRECLOUD_OIDC_CLIENT_ID=wirecloud
WIRECLOUD_OIDC_CLIENT_SECRET=replace-with-the-client-secret
WIRECLOUD_OIDC_PLUGIN=keycloak

# Optional features described below
WIRECLOUD_OIDC_FULLY_SYNC_GROUPS=false
WIRECLOUD_OIDC_BACKCHANNEL_LOGOUT=true
```

Do not commit the client secret. Restart WireCloud after changing these values.
At startup, WireCloud retrieves and validates the discovery document and the
provider's signing keys. Keep `WIRECLOUD_HTTPS_VERIFY=true` in production and fix
certificate trust problems at their source.

The reverse proxy must preserve the public host and HTTPS scheme in trusted
forwarding headers. Otherwise, WireCloud can generate an `http://` callback or
an internal hostname, which Keycloak correctly rejects as an invalid redirect
URI. Confirm in the browser's authorization request that `redirect_uri` is
exactly the URI registered above. Also set the Python setting
`WIRECLOUD_HTTPS = True` as described in the [production checklist](#production-checklist).

### 3. Optional group synchronization

By default, Keycloak authenticates the user but local WireCloud administrators
continue to manage WireCloud groups. To supply group membership from Keycloak:

1. Create an OIDC client scope named `wirecloud`.
2. Add a **Group Membership** protocol mapper to that client scope.
3. Set its token claim name to `wirecloud.groups`, turn **Full group path** off,
   and enable adding the claim to **UserInfo**.
4. Assign the `wirecloud` scope to the WireCloud client as an optional client
   scope. WireCloud requests it automatically when it appears in provider
   metadata.

Use Keycloak's client-scope evaluation tools to verify that the UserInfo result
for a test user contains this shape:

```json
{
  "wirecloud": {
    "groups": ["developers", "editors"]
  }
}
```

The UserInfo setting is essential: putting the claim only in an ID or access
token is not sufficient for this integration. Leave
`WIRECLOUD_OIDC_FULLY_SYNC_GROUPS=false` when Keycloak merely adds managed
groups. Set it to `true` only when Keycloak is the authoritative source for
*all* WireCloud group membership; on every OIDC login, WireCloud removes the
user's existing local group memberships before applying the supplied list.

### 4. Optional single sign-out

There are two complementary logout directions:

- `WIRECLOUD_OIDC_BACKCHANNEL_LOGOUT=true` makes WireCloud notify Keycloak's
  end-session endpoint when the user signs out of WireCloud.
- To make a logout initiated in Keycloak invalidate WireCloud sessions, set the
  client's **Backchannel logout URL** to:

  ```text
  https://wirecloud.example.com/oidc/k_logout
  ```

  Turn **Backchannel logout session required** on. Front-channel logout is not
  required for this integration.

Keycloak recommends back-channel logout over browser-dependent front-channel
logout. WireCloud validates incoming logout tokens against the discovery
document's issuer, client ID, and signing keys before invalidating sessions.

### 5. Verify the integration

1. Restart WireCloud and check its logs for discovery or signing-key errors.
2. In a private browser window, open WireCloud and confirm that sign-in redirects
   to the expected Keycloak realm.
3. Sign in as a test user and confirm that WireCloud creates the account with the
   expected username, name, email, and groups.
4. Sign out from WireCloud and verify the expected Keycloak sign-out behavior.
5. If Keycloak-initiated logout was configured, start a new session, end it from
   Keycloak, and confirm that WireCloud requires authentication again.

Common symptoms are usually narrow configuration errors:

| Symptom | Check |
| --- | --- |
| WireCloud fails during startup | The discovery URL is reachable from the container, its TLS chain is trusted, and it advertises authorization-code flow, UserInfo, end-session, JWKS, `openid`, `profile`, and `offline_access`. |
| Keycloak reports an invalid redirect URI | The registered URI exactly matches the public scheme, host, port, and `/oidc/callback` path; verify reverse-proxy forwarding headers. |
| Login reaches WireCloud but fails | The UserInfo response includes `preferred_username`, the user is active locally, and Keycloak returned a refresh token. |
| Login works but groups do not | The `wirecloud` scope is requested and the mapper adds `wirecloud.groups` to UserInfo, not only to a token. |
| Logout does not propagate | Configure the appropriate direction above; these are two separate settings. Check that Keycloak can reach WireCloud's public `/oidc/k_logout` endpoint. |

## Production checklist

- Set unique, random `JWT_KEY` and `SECRET_KEY` values of at least 32 characters.
- Terminate HTTPS at a trusted reverse proxy and set the Python setting `WIRECLOUD_HTTPS = True` so authentication cookies are marked secure.
- Set `DEBUG` to false.
- Decide explicitly whether anonymous access is allowed.
- Restrict the proxy with an allowlist or denylist appropriate to your network.
- Use MongoDB and Elasticsearch authentication when those services are reachable outside a private application network.
- Persist and back up MongoDB plus the catalogue media and widget deployment directories.
- Monitor the application, database, search service, storage space, and certificate expiry.
- Run the service as a non-root user with write access only to its data directories.
- If OIDC is enabled, retain a local break-glass administrator and test both
  login and logout propagation after Keycloak, proxy, or certificate changes.

## Service checks

After startup:

1. Open `/` and confirm that the landing page or login flow loads.
2. Open `/docs` and confirm that the OpenAPI UI is generated.
3. Sign in as an administrator.
4. Open **My Resources** and confirm that the bundled components exist.
5. Create a workspace, add a widget, and reload the page.
6. Search for a resource to verify Elasticsearch access.
7. If Keycloak is enabled, complete the [integration checks](#5-verify-the-integration).
