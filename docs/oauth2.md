# OAuth client connections

`wirecloud.oauth2provider` is an optional OAuth 2.0 authorization server for plugins
that offer user-authorized connections to external clients. The [MCP plugin](mcp.md)
is one consumer. Other plugins can register their own resource URLs and scopes
without depending on MCP or its SDK.

WireCloud core continues to own user login, sessions, and identity-provider hooks.
OAuth clients sign in through WireCloud, including Keycloak or another configured
provider. Existing widget authentication and APIs use their existing mechanisms.
Enabling OAuth does not add bearer authentication to all WireCloud routes.

## Enable the module

Add `wirecloud.oauth2provider` to `INSTALLED_APPS`, retaining the core applications,
and enable each plugin offering a resource. Configure the public WireCloud base URL:

```python
OAUTH2_PUBLIC_URL = 'https://wirecloud.example.org'
AUTH_PUBLIC_URL = 'https://wirecloud.example.org'
OAUTH2_DYNAMIC_REGISTRATION = True
OAUTH2_CLIENTS = []
```

`OAUTH2_PUBLIC_URL` identifies the authorization server's public deployment base;
its issuer is that base plus `/oauth2`. `AUTH_PUBLIC_URL` tells core login which
public base to use for identity-provider callbacks. Local sign-in uses the
website's normal `/login` form on the visited origin. These settings
may be omitted when the request origin and ASGI `root_path` already identify the
external deployment correctly. Include any deployment prefix in both values.
HTTPS is required for registered resources, except for loopback development.

Docker equivalents are `WIRECLOUD_OAUTH2_PUBLIC_URL`, `WIRECLOUD_AUTH_PUBLIC_URL`,
and `WIRECLOUD_OAUTH2_DYNAMIC_REGISTRATION`. Add `wirecloud.oauth2provider` to
`WIRECLOUD_INSTALLED_APPS`. The module needs no extra Python dependency. Include it
in the build-time installed-app list and run `npm run build:js` (or the full
`npm run build`) to generate its OAuth page bundles. Restart WireCloud after enabling
the module. Startup creates idempotent indexes for its OAuth collections; core login
owns the browser login-attempt collection. Existing users and workspaces require no
data migration.

### Reverse proxies and deployment prefixes

Use the external HTTPS addresses seen by clients. Preserve request paths and the
`Authorization` header at the reverse proxy. For an installation under a URL prefix,
include that prefix in the public URLs and set ASGI `root_path` correctly.

Clients discover OAuth metadata through origin-level well-known URLs. For example,
an installation at `https://wirecloud.example.org/platform`, with a plugin resource
at `/platform/api/example`, needs these paths forwarded to WireCloud:

* `/.well-known/oauth-authorization-server/platform/oauth2`
* `/.well-known/oauth-protected-resource/platform/api/example`

For an MCP resource at `/platform/mcp`, the second path is
`/.well-known/oauth-protected-resource/platform/mcp`. Routing only requests under
`/platform` is insufficient for discovery.

### Local testing

For the local development server, configure:

```python
OAUTH2_PUBLIC_URL = 'http://localhost:8000'
AUTH_PUBLIC_URL = 'http://localhost:8000'
OAUTH2_DYNAMIC_REGISTRATION = True
OAUTH2_CLIENTS = []
```

The development settings in `src/settings.py` use local WireCloud accounts
(`OID_CONNECT_ENABLED = False`). To test Keycloak, enable OIDC and configure the
existing provider settings there. Other login providers use the same WireCloud
login entry point and [provider contract](#authentication-provider-contract).
Use `localhost` consistently instead of mixing it with `127.0.0.1`; browser cookies
and configured resource URLs depend on the hostname.

## Client registration

A client is the external application requesting a connection. Client registration
records its name, allowed callback URLs, and client authentication method so
WireCloud can validate subsequent authorization requests. It does not create a
WireCloud user, approve access, or issue access tokens. The user must still sign in
through WireCloud and explicitly approve the requested resource and scopes.

WireCloud supports three ways to identify clients:

| Method | How the client gets its identity |
| --- | --- |
| Dynamic registration | The client submits metadata to `/oauth2/register` and receives a generated `client_id`. |
| Configured clients | The deployment provides a fixed `client_id` and metadata in `OAUTH2_CLIENTS`. |
| HTTPS client metadata documents | The client uses its public metadata document URL as `client_id`; WireCloud fetches and validates that document. |

### Dynamic registration

`OAUTH2_DYNAMIC_REGISTRATION = True` is the default. This allows a compatible app to
connect without an administrator first adding that app to `OAUTH2_CLIENTS`:

1. The client discovers `registration_endpoint` in the authorization server metadata.
2. It sends its metadata to `POST /oauth2/register`, for example:

    ```json
    {
      "client_name": "Dashboard assistant",
      "redirect_uris": ["http://127.0.0.1:9000/callback"],
      "token_endpoint_auth_method": "none"
    }
    ```

3. WireCloud validates the metadata, stores the client, and returns HTTP 201 with
   its generated `client_id` and accepted metadata.
4. The client starts the [browser authorization flow](#client-flow-and-endpoints)
   using that ID. The user reviews the app and requested access before consenting.

The registration endpoint requires no browser login or existing client credential.
It accepts JSON bodies up to 64 KiB and at most 20 explicit HTTPS or loopback
callback URLs. Registration requests are rate limited to 60 per observed client IP
per hour; further requests receive HTTP 429. The observed IP depends on the trusted
proxy configuration used by the application server.

For a public client, `token_endpoint_auth_method` is `none`: possession of a client
ID is not authentication as a user. Confidential clients may request
`client_secret_post` or `client_secret_basic`; registration then also returns a
generated `client_secret`, whose hash is stored by WireCloud. All clients still
use Authorization Code with S256 PKCE and user consent.

Set `OAUTH2_DYNAMIC_REGISTRATION = False` (Docker:
`WIRECLOUD_OAUTH2_DYNAMIC_REGISTRATION=false`) to stop accepting new registrations.
The registration endpoint then returns HTTP 404 and is omitted from discovery.
Previously registered clients remain usable, and existing grants remain valid
until their normal expiry or revocation. Configured clients and HTTPS metadata
documents remain supported. This setting alone does not restrict connections to
the entries in `OAUTH2_CLIENTS`.

### Configured clients

To provision a client explicitly, add its metadata to the deployment configuration:

```python
OAUTH2_CLIENTS = [{
    'client_id': 'dashboard-assistant',
    'client_name': 'Dashboard assistant',
    'redirect_uris': ['https://assistant.example.org/oauth/callback'],
    'token_endpoint_auth_method': 'none',
}]
```

For a confidential client, use `client_secret_post` or `client_secret_basic` and
provide `client_secret` in server configuration. The client must use the same
authentication method during token exchange and revocation.

### HTTPS client metadata documents

A client can instead use an HTTPS URL, such as
`https://assistant.example.org/oauth/client.json`, as its `client_id`. WireCloud
retrieves the JSON document at that URL. The document must contain that exact
`client_id`, valid `redirect_uris`, and the public client authentication method
`none`. The name and callback information come from the document.

WireCloud only fetches public HTTPS metadata URLs on port 443, rejects redirects
and private network addresses, and limits the response to 64 KiB with a five-second
HTTP timeout. This mechanism does not call `/oauth2/register` and works even when
dynamic registration is disabled.

### Callback matching

Redirect URIs use exact matching, with the native-app ephemeral-port exception for
HTTP callbacks at the literal loopback addresses `127.0.0.1` and `::1`. The callback
host, path, and query still have to match; `localhost` does not get this exception.
Authorization codes remain bound to the complete callback selected in the
authorization request.

## Offer a resource from a plugin

Register each audience once while constructing the plugin. Give it a user-facing
name, capability descriptions for consent, and optional default scopes:

```python
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from wirecloud.database import DBDep
from wirecloud.oauth2provider import (
    OAuthPrincipal, OAuthResource, register_resource, require_access,
)
from wirecloud.platform.plugins import WirecloudPlugin

AUDIENCE = 'https://wirecloud.example.org/api/example'
router = APIRouter()


async def example_access(request: Request, db: DBDep):
    return await require_access(request, db, AUDIENCE, ('example:read',))


@router.get('/api/example')
async def example(principal: Annotated[OAuthPrincipal, Depends(example_access)]):
    if not principal.user.has_perm('EXAMPLE.VIEW'):
        raise HTTPException(403, 'Insufficient permissions')
    return {'username': principal.user.username}


class ExamplePlugin(WirecloudPlugin):
    def __init__(self, app):
        super().__init__(app)
        if app is None:
            return
        register_resource(app, OAuthResource(
            audience=AUDIENCE,
            name='Example service',
            scopes={'example:read': 'Read your example data'},
            default_scopes=('example:read',),
        ))
        app.include_router(router)
```

`require_access` accepts bearer tokens only. It validates the audience, required
scopes, live WireCloud session, active account, and current user identity. Missing
or invalid tokens return HTTP 401; missing scopes return HTTP 403. Both include an
OAuth challenge pointing at resource metadata. Plugins still enforce their normal
permissions and object access checks using `principal.user`. A scope does not grant
a WireCloud permission. Tokens for one resource cannot be used for another.

For custom transports, `verify_access_token(db, token, audience)` returns an
`OAuthPrincipal` or `None`; `bearer_token(request)` and
`resource_metadata_url(audience)` are also available. Custom transports must check
scopes explicitly and apply their usual authorization checks. Browser clients on
other origins also need a CORS policy on the plugin's resource endpoints.

## Client flow and endpoints

After identifying itself through one of the registration methods above, a client
uses Authorization Code with S256 PKCE and sends the resource's exact audience in
`resource` during authorization and token exchange. Discovery exposes:

* `/.well-known/oauth-authorization-server/oauth2`: server metadata.
* `/.well-known/oauth-protected-resource/<resource-path>`: metadata for an exact
  registered resource path, e.g. `/api/example` or `/mcp`.

| Endpoint | Purpose |
| --- | --- |
| `/oauth2/authorize` | Validate the client, callback, resource, scopes, and PKCE challenge, then start browser authorization. |
| `/oauth2/consent` | Show the requested access and let the signed-in user approve or deny it. |
| `/oauth2/token` | Exchange an authorization code or rotate a refresh token. |
| `/oauth2/register` | Register client metadata when dynamic registration is enabled. |
| `/oauth2/revoke` | Revoke a connection using one of its tokens and the client's authentication method. |
| `/oauth2/connections` | Let the signed-in user review and revoke their app connections. |

The client opens the authorization URL in a browser. WireCloud owns sign-in and
chooses the configured identity provider, including Keycloak when enabled. The user
reviews the client identity, callback address, and requested capabilities, then
approves or denies access. Resource plugins and external clients do not need
provider-specific settings.

Public OAuth protocol endpoints support CORS without browser credentials; login,
consent, and browser connection management retain their same-origin protections.
Each resource plugin configures CORS separately for its own endpoints.

### Session lifetime and revocation

Grants are bound to the client, selected resource, scopes, and authorizing WireCloud
session. Access tokens last at most 15 minutes. Refresh tokens rotate and cannot
outlive that session. Logout, session revocation or expiry, account deactivation,
and provider logout that invalidates the WireCloud session also end delegated
access. Reusing a consumed refresh token revokes its connection. User permissions
are checked by the resource plugin on every request.

Users manage their connections from **User menu → App connections** in the
desktop and mobile platform views. The menu opens a StyledElements modal within
the current workspace, listing each application's resource, permission checkboxes,
client ID, and a revocation action. Select the desired permissions and choose
**Save permissions** to expand or reduce access. Changes apply immediately to that
connection's existing access and refresh tokens; current WireCloud user permissions
still apply. Select at least one permission, or revoke the connection to remove
access entirely. Client-requested scope narrowing is retained until the user next
changes that connection's permissions. The direct URL remains available as a
standalone page at `/oauth2/connections`, with the same editing controls.

## Authentication provider contract

WireCloud's `/auth/login` entry point owns login continuation. Provider plugins
contribute the existing authorization-URL, token-exchange, user-info, and logout
hooks. Providers can accept the optional `login_context` argument on URL and
token hooks. It carries state, nonce, PKCE verifier, and the return destination.
OIDC attempts are stored as typed login records by the auth CRUD layer.
WireCloud binds state to the browser and consumes it once; providers validate
their own protocol tokens. The Keycloak plugin validates the ID token's
signature, issuer, audience, nonce, and subject binding, and submits PKCE.

The provider returns identity data using WireCloud's existing hook contract.
WireCloud maps that identity to a local user and session. Provider logout must
invalidate the corresponding WireCloud sessions using the existing token
invalidation helpers. The delegated verifier then rejects dependent grants.
Resource plugins use the resulting WireCloud identity and permissions.

Older hooks without `login_context` remain callable. Providers adopting PKCE
must implement the context-aware exchange and their protocol's token validation.
All browser OIDC callbacks require a WireCloud-generated state; integrations
must start login through `/auth/login`, rather than constructing provider URLs
or treating OAuth `state` as a return address. Local username/password sign-in
uses `/login` with a validated local `return_to` path and does not depend on an
expiring OIDC continuation or cookie. External clients still return to the
OAuth consent screen after signing in.

## Theme integration

Consent and connection management use these templates in the active theme:

* `wirecloud/oauth2provider/base.html`
* `wirecloud/oauth2provider/consent.html`
* `wirecloud/oauth2provider/connections.html`

The default theme supplies all three. Child themes inherit them and may override
templates, the `branding`, `styles`, `footer`, or `content` blocks, or
`static/css/oauth2provider.css`. Logo and favicon paths are resolved through the
theme's static-file inheritance. Strings use the existing translation system.

Pages use StyledElements `Panel`, `Button`, `Alert`, and `Container` components.
Their appearance comes from the active theme's existing StyledElements styles;
OAuth-specific CSS controls page layout and spacing. The module's `plugin.ts`
registers StyledElements and the page enhancer for the `oauth2` JavaScript view.
Webpack produces `main-<theme>-oauth2.js` for each theme, served through
`js/cache.js?view=oauth2`. The template loads this bundle with `defer`.
Development builds use external source maps to respect the pages' strict CSP.
The native forms also work if JavaScript is unavailable.

Pages escape client-controlled content. Their CSP permits same-origin scripts,
theme styles, fonts, and images, with inline scripts and event handlers blocked.
Consent and revocation keep native form submissions, including the selected
button value and hidden CSRF fields. Form destinations are restricted to WireCloud
and the validated callback origin for that consent attempt. Keep these restrictions
when creating theme overrides.

## Verification

The OAuth module tests cover discovery, client registration and metadata documents,
consent, PKCE/state replay, token rotation, browser CSRF and connection ownership,
session revocation, provider-neutral login, and resource audience/scope isolation.
They also check confidential clients, malformed metadata, private-address fetch
rejection, registration limits, CORS behind URL prefixes, and account changes
between displaying and submitting consent:

```bash
python -m pytest tests/oauth2provider
```

Tests use a mock MongoDB. Verify production identity-provider and reverse-proxy
settings in the deployment environment too. The MCP integration suite adds a
real HTTP OAuth flow through an authenticated SDK call and revocation. CI
publishes test and coverage reports for Python 3.11 and 3.13; see
[development](development.md#oauth-and-mcp-integration).
