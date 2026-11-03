# Use WireCloud through MCP

The optional `wirecloud.mcp` plugin lets an MCP client create and edit dashboards
on behalf of a signed-in WireCloud user. It uses the shared
[OAuth client connections module](oauth2.md) for authorization and the same user
and current permissions as other WireCloud operations.

## Enable the plugin

MCP installations require Python 3.11 or newer. Install the optional dependencies
in the environment running WireCloud. For a published GitHub release, select its
standalone MCP wheel; it includes the application and declares the tested MCP
dependencies as mandatory:

```bash
python -m pip install './wirecloud-2.0.0+mcp-py3-none-any.whl'
```

See [release wheels](installation.md#install-from-a-release-wheel) for both
variants. When installing from source instead, use the MCP extra and constraints:

```bash
python -m pip install -c constraints-mcp.txt '.[mcp]'
```

The constraints file records the tested SDK, FastAPI, Starlette, and SSE dependency
versions. Install the plugin before building a deployment image. Installations
without MCP keep WireCloud's existing Python requirement and need no MCP SDK.

Enable and configure the [OAuth module](oauth2.md#enable-the-module), then append
`wirecloud.mcp` to `INSTALLED_APPS`, retaining the core applications and
`wirecloud.oauth2provider`. Set the public MCP resource URL:

```python
MCP_PUBLIC_URL = 'https://wirecloud.example.org/mcp'
```

Use the external HTTPS address seen by the client. HTTP is accepted only for
loopback development, for example `http://localhost:8000/mcp`. Preserve request
paths and the `Authorization` header at the reverse proxy. `MCP_PUBLIC_URL` is also
the resource audience used by the client during authorization and token exchange.
For deployments under a URL prefix, include it in this URL and follow the
[OAuth proxy and discovery configuration](oauth2.md#reverse-proxies-and-deployment-prefixes).

Restart WireCloud after enabling the plugin. Startup creates idempotent MongoDB
indexes for its temporary upload collection. The OAuth module owns authorization
records and their indexes.

### Local testing

The development settings in `src/settings.py` enable MCP at
`http://localhost:8000/mcp`. See [OAuth local testing](oauth2.md#local-testing) for
login and client registration settings.

Use the Python 3.11 environment alongside `venv/` from the repository root:

```bash
source venv-mcp/bin/activate
python -m uvicorn wirecloud.main:app --host localhost --port 8000 --reload
```

Keep the configured MongoDB and Elasticsearch services running. Database settings
that enable transactions require a MongoDB replica set. Connect the MCP client to
`http://localhost:8000/mcp`.

### Docker

Published releases provide an image with the MCP dependencies under the `-mcp`
tag suffix, for example `2.0.0-mcp`; stable releases also update `latest-mcp`.
See [published images](installation.md#use-a-published-docker-image) for repository
selection and use with Compose.

To build the image from source with the optional dependencies installed:

```bash
docker compose -f docker/docker-compose.yml build --build-arg WIRECLOUD_INSTALL_MCP=true
docker compose -f docker/docker-compose.yml up -d
```

The build argument installs the SDK with the tested constraints. Configure:

```text
WIRECLOUD_INSTALLED_APPS=wirecloud.commons,wirecloud.platform,wirecloud.catalogue,wirecloud.proxy,wirecloud.fiware,wirecloud.keycloak,wirecloud.oauth2provider,wirecloud.mcp
WIRECLOUD_MCP_PUBLIC_URL=https://wirecloud.example.org/mcp
```

Configure the shared [OAuth module settings](oauth2.md#enable-the-module) as well.
The MCP plugin has no frontend bundle, so enabling it adds no JavaScript build step.

## Connect a client

Configure a remote Streamable HTTP MCP server with URL:

```text
https://wirecloud.example.org/mcp
```

For example, clients accepting a JSON server map typically use:

```json
{
  "mcpServers": {
    "wirecloud": {
      "type": "http",
      "url": "https://wirecloud.example.org/mcp"
    }
  }
}
```

For Codex, the equivalent server entry is:

```toml
[mcp_servers.wirecloud]
url = "https://wirecloud.example.org/mcp"
```

Use the client's OAuth login/connect action to complete the
[WireCloud authorization flow](oauth2.md#client-flow-and-endpoints).
Supported ways to identify the application, including dynamic registration, are
described in [client registration](oauth2.md#client-registration).

Client configuration formats vary. Clients must support remote HTTP and browser
OAuth with PKCE; a local stdio-only client needs its own HTTP bridge.

### Scopes and permissions

| Scope | Access |
| --- | --- |
| `wirecloud:read` | Inspect accessible content and export workspaces |
| `wirecloud:workspace:write` | Create, clone, import, and edit workspaces and their contents |
| `wirecloud:workspace:delete` | Delete owned workspaces and remove permitted workspace contents |
| `wirecloud:component:install` | Install finished packages for the current user |
| `wirecloud:component:uninstall` | Uninstall personal component installations |

A scope does not grant a WireCloud permission. Permissions and user activation
are checked on every request. Existing shared workspaces can be edited when the
user has permission. Workspace deletion is restricted to owned workspaces.
Sharing, publishing, account administration, impersonation, and permission
management have no MCP tools.

The initial authorization challenge requests all MCP scopes. Authorization
requests that omit `scope` also default to all MCP scopes. Clients can explicitly
request a smaller set. Calling an operation outside the granted scopes returns
an HTTP OAuth scope challenge, allowing compatible clients to request additional
consent. To change an existing connection, open **User menu → App connections**,
select its permissions, and choose **Save permissions**. This also expands an
existing read-only connection without reconnecting and takes effect immediately.

See [session lifetime and revocation](oauth2.md#session-lifetime-and-revocation)
for token expiry, logout behavior, and managing app connections.

### Browser clients

For a browser client on another origin, add its exact origin to
`MCP_ALLOWED_ORIGINS` (Docker: `WIRECLOUD_MCP_ALLOWED_ORIGINS`) to allow requests to
the MCP transport and upload endpoint.

## What you can do

Once connected, ask your assistant to work with the dashboards and components
available to your WireCloud account. For example:

* List your workspaces or explain how an existing dashboard is wired.
* Create a dashboard, clone an existing workspace, or organize its tabs and widgets.
* Change component settings, connect widgets and operators, or arrange the wiring editor.
* Install a finished component package or import an installed mashup template.
* Export a workspace as a mashup descriptor.

New and cloned workspaces and component installations are private to your account.
Exports do not publish a workspace. Secure and hidden values are redacted from
responses and exports.

The server detects concurrent edits and can reject a change if the workspace has
changed since the assistant read it. If this happens, ask the assistant to review
the current workspace before trying again.

### Component packages

The MCP server installs finished WGT packages. Developing a new widget or operator
requires an external development environment; the server does not accept source
trees or run builds. See [component development](components.md) for the package
format and development API.

Packages can come from an HTTP(S) URL or be sent through the client. Inline
packages are limited to 2 MiB; URL downloads and binary uploads are limited to
100 MiB. Binary uploads require explicit client support. Temporary uploads expire
after 15 minutes and can be used once by the same user and connection.

URL downloads follow WireCloud's configured proxy policy, which determines whether
internal services are reachable. MCP credentials and WireCloud session cookies
are never forwarded to the download destination. Remote dependencies require
separate installation; bundled mashup dependencies can be installed with the import.

Existing immutable component versions are reused when the package bytes match.
Installing different content under the same immutable version requires a new
version number. Development versions follow WireCloud's user-specific replacement
rules.

### Wiring layout

The server automatically places new operators and connected components in the
wiring editor while preserving existing positions. You can also ask the assistant
to rearrange the whole wiring graph or move selected components. Wiring editor
positions are separate from widget positions on the dashboard. Automatic placement
uses dimensions estimated for the default theme, so custom themes or unusually
large components may need adjustment.

## Further information

The server supplies its tool descriptions, argument schemas, and authoring
instructions directly to MCP clients. You do not need to copy this guide into the
assistant's conversation to use the server.

For integration tests and contributor setup, see
[OAuth and MCP development](development.md#oauth-and-mcp-integration).
