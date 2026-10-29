# AI access through MCP

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

## Tools and authoring workflow

Start with `get_session_info`, `list_workspaces`, and `list_resources`.
`get_workspace` returns the workspace and its `modification_timestamp`. Supply
that value as `expected_last_modified` when editing to reject stale changes.
Mutations return updated timestamps. Tools also use conditional persistence to
detect a concurrent write during an operation.

| Area | Tools |
| --- | --- |
| Workspaces | `create_workspace`, `clone_workspace`, `update_workspace`, `delete_workspace` |
| Tabs | `create_tab`, `update_tab`, `reorder_tabs`, `delete_tab` |
| Widgets | `add_widget`, `update_widget`, `remove_widget`, `set_widget_variables` |
| Preferences | `get_preferences`, `update_preferences` |
| Wiring | `get_wiring`, `add_operator`, `update_operator`, `remove_operator`, `connect_components`, `disconnect_components`, `layout_wiring` |
| Resources | `get_resource`, `get_resource_documentation`, `validate_resource_package`, `install_resource`, `uninstall_resource` |
| Mashups | `import_mashup`, `merge_mashup`, `export_workspace` |

Use exact resource IDs (`vendor/name/version`) and returned workspace, tab,
widget, and operator IDs. Wiring checks that endpoints exist and have compatible
types. Omitted preferences preserve existing values. Secure and hidden values
are redacted from responses and exports. Component documentation is untrusted
content, and remote documentation references are not fetched automatically.

### Finished component packages

Build widgets and operators outside WireCloud following
[component packaging](components.md). The MCP server does not receive source
trees, run build commands, or execute component code.

`install_resource` accepts exactly one input:

* `url`: an HTTP(S) WGT URL fetched through WireCloud's configured proxy policy,
  including internal services when that policy allows them. MCP credentials and
  WireCloud session cookies are never forwarded to the destination.
* `package_base64`: base64 of the finished WGT, up to 2 MiB decoded.
* `upload_id`: a handle returned by an authenticated binary upload to
  `POST /mcp/uploads`, using the delegated bearer token. Uploads and downloads
  are limited to 100 MiB. Handles are single use, expire after 15 minutes, and
  are bound to the user and connection. Clients need explicit upload support
  for this path; inline packages and URLs require only MCP tools.

Installations are private to the current user. Existing immutable versions are
reused when their package bytes match; different bytes for an immutable version
return a conflict and require a new version. Development versions follow WireCloud's user-specific replacement
rules. `install_embedded_resources` explicitly installs packaged mashup
dependencies through the same validator and installer. Remote dependencies must
be installed explicitly. Archive paths, extraction size, nesting, descriptors,
and required contents are validated before installation.

Imports use an already installed mashup resource. Exports return a JSON mashup
descriptor and do not publish it.

### Wiring editor placement

MCP automatically places new operators and components without a saved position
when connecting them. Existing positions are preserved. Widgets appear in the
wiring editor when connected or explicitly positioned; their dashboard layout
is separate. Placement leaves space based on endpoint counts and avoids existing
components, so routine authoring needs no coordinate arguments or extra calls.

For a complete automatic arrangement after wiring, or to repair an existing
overlapping layout, call `layout_wiring` once:

```json
{"workspace_id": "...", "preserve_existing": false}
```

This places the graph from left to right, with deterministic handling of branches,
feedback loops, and disconnected components. Omit `preserve_existing` to fill only
missing positions. To move selected components, supply their positions together:

```json
{
  "workspace_id": "...",
  "positions": [
    {"type": "widget", "id": "0", "x": 20, "y": 10},
    {"type": "operator", "id": "0", "x": 440, "y": 10}
  ]
}
```

Coordinates are wiring editor pixels (minimum `x=20`, `y=10`). Explicit positions
take precedence over automatic placement. The tool returns the number of changed
component positions and the workspace timestamp; use `get_wiring` when coordinates
are needed. Layout changes require the workspace write scope and WireCloud wiring
edit permission, and support `expected_last_modified`. Connections, operator values,
endpoint ordering, collapsed state, dashboard layouts, and behaviour views are
preserved. Automatic dimensions are estimates for the default theme; explicit moves
remain available for custom themes or unusually large components.

## Maintenance and verification

The backend follows the same registration, router, URL, and validator conventions
as the bundled plugins. Runtime resources use [native router lifespans](plugins.md#runtime-resources).

| Module | Responsibility |
| --- | --- |
| `plugins.py` | Register the feature, OAuth resource, middleware, and router. |
| `routes.py` | Serve the SDK endpoint and binary uploads; start and stop runtime resources. |
| `middleware.py`, `context.py` | Authenticate requests, issue scope challenges, and carry request identity. |
| `server.py`, `handlers.py` | Bind the official SDK to closed schemas and translate operation errors. |
| `tools.py`, `schemas.py` | Declare the supported tools, their operation functions, and input models. |
| `adapter.py` | Enforce scopes, workspace access, concurrency, transactions, and audit logging. |
| `operations/` | Implement workspace, widget, preference, resource, and wiring actions. |
| `packages.py`, `layout.py`, `utils.py` | Validate and transfer packages, arrange wiring, and redact results. |
| `validators.py` | Check configuration without importing the optional SDK. |

The adapter and operation modules are the boundary with WireCloud internals.
They reuse authorized entrypoints, installers, serializers, cache invalidation,
and search indexing. The plugin interface is not independently versioned: pin
WireCloud and rerun tests when upgrading. Extracting MCP into a separate
distribution should retain that boundary and installed-app import path. Shared
OAuth code remains in WireCloud.

Run the existing test suite on the supported core interpreter. With the MCP
extra installed on Python 3.11+, the suite additionally exercises the official
SDK client and a complete authoring workflow:

```bash
python -m pytest tests
```

MCP tests use a mock MongoDB and mock search backend. They cover transport
authentication, packages, upload ownership, scopes, concurrent edits, redaction,
private workspace ownership, live permission changes, strict tool argument
validation, and all 33 authoring tools through the official SDK. A real HTTP
integration test also exercises OAuth discovery, consent, token exchange, an
SDK call, and revocation behind a deployment URL prefix. CI runs the full suite
with pinned MCP dependencies on Python 3.11 and 3.13; see
[development](development.md#oauth-and-mcp-integration) for commands and reports.
Shared authorization behavior is covered by the
[OAuth module tests](oauth2.md#verification).
