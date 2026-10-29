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


# Shared response formats
oauth_error_schema = {
    "type": "object",
    "required": ["error", "error_description"],
    "properties": {
        "error": {"type": "string", "description": "OAuth error code"},
        "error_description": {"type": "string", "description": "Explanation of the rejected request"},
    },
}
http_error_schema = {
    "type": "object",
    "required": ["detail"],
    "properties": {"detail": {"type": "string", "description": "Explanation of the HTTP error"}},
}
oauth_bad_request_response_description = "Invalid authorization request, grant, resource, scopes, or client metadata"
oauth_bad_request_response_example = {"error": "invalid_request", "error_description": "Invalid authorization request"}
invalid_client_response_description = "Unknown client or invalid client authentication"
invalid_client_response_example = {"error": "invalid_client", "error_description": "Invalid client authentication"}
browser_auth_required_response_description = "A signed-in WireCloud browser session is required"
browser_auth_required_response_example = {"detail": "Unauthorized"}
browser_permission_denied_response_description = "Invalid browser CSRF token or an impersonated session"
browser_permission_denied_response_example = {"detail": "Invalid CSRF token"}
not_found_response_description = "The resource, connection, or optional endpoint is unavailable"
not_found_response_example = {"detail": "Not Found"}
no_store_headers = {
    "Cache-Control": {"description": "Sensitive responses must not be cached", "schema": {"type": "string"}, "example": "no-store"},
}
redirect_headers = {
    "Location": {"description": "Destination of the browser redirect", "schema": {"type": "string"}},
}
client_auth_parameter = {
    "name": "Authorization", "in": "header", "required": False,
    "description": "HTTP Basic credentials for clients registered with client_secret_basic. Otherwise send client_id and, for client_secret_post, client_secret in the form. Public clients use client_id without a secret.",
    "schema": {"type": "string"}, "example": "Basic Y2xpZW50LWlkOmNsaWVudC1zZWNyZXQ=",
}
browser_session_parameter = {
    "name": "token", "in": "cookie", "required": False,
    "description": "WireCloud login session cookie. Bearer tokens do not authenticate browser consent or connection management. Impersonated sessions are rejected.",
    "schema": {"type": "string"},
}
browser_binding_parameter = {
    "name": "wc_oauth_browser", "in": "cookie", "required": True,
    "description": "HTTP-only browser-binding cookie set when beginning authorization or listing app connections",
    "schema": {"type": "string"},
}
authenticated_browser_parameters = [{**browser_session_parameter, "required": True}, browser_binding_parameter]
accept_parameter = {
    "name": "Accept", "in": "header", "required": False,
    "description": "Include application/json for the modal/API response; otherwise receive the standalone HTML page or a browser redirect",
    "schema": {"type": "string"}, "example": "application/json",
}

# GET /.well-known/oauth-authorization-server[/oauth2|/{issuer_path}]
authorization_metadata_summary = "Get OAuth authorization server metadata"
authorization_metadata_description = "Discover the issuer, supported grants, PKCE method, client authentication methods, scopes, and protocol endpoints. Available when at least one OAuth resource is registered. The registration endpoint is included only when dynamic registration is enabled."
authorization_metadata_response_description = "OAuth authorization server discovery document"
authorization_metadata_response_example = {
    "issuer": "https://wirecloud.example.org/oauth2",
    "authorization_endpoint": "https://wirecloud.example.org/oauth2/authorize",
    "token_endpoint": "https://wirecloud.example.org/oauth2/token",
    "revocation_endpoint": "https://wirecloud.example.org/oauth2/revoke",
    "registration_endpoint": "https://wirecloud.example.org/oauth2/register",
    "response_types_supported": ["code"],
    "grant_types_supported": ["authorization_code", "refresh_token"],
    "code_challenge_methods_supported": ["S256"],
    "client_id_metadata_document_supported": True,
    "authorization_response_iss_parameter_supported": True,
    "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
    "scopes_supported": ["wirecloud:read", "wirecloud:workspace:write"],
}
authorization_metadata_path_parameters = [{
    "name": "issuer_path", "in": "path", "required": True,
    "description": "Issuer path, including the deployment prefix and oauth2 suffix when applicable",
    "schema": {"type": "string"}, "example": "platform/oauth2",
}]

# GET /.well-known/oauth-protected-resource[/{resource_path}]
resource_metadata_summary = "Get OAuth protected resource metadata"
resource_metadata_description = "Discover an exact registered resource's audience, authorization server, scopes, and bearer-token method. Without a resource path, the document is available only when one resource is registered."
resource_metadata_response_description = "OAuth protected resource discovery document"
resource_metadata_response_example = {
    "resource": "https://wirecloud.example.org/mcp",
    "resource_name": "WireCloud MCP",
    "authorization_servers": ["https://wirecloud.example.org/oauth2"],
    "scopes_supported": ["wirecloud:read", "wirecloud:workspace:write"],
    "bearer_methods_supported": ["header"],
}
resource_metadata_path_description = "Path of the registered resource, including a deployment prefix if present; omit on the base endpoint when only one resource is registered"

# POST /oauth2/register
register_summary = "Register an OAuth client"
register_description = "Dynamically register a client with explicit HTTPS or loopback callback URLs. Metadata is limited to 64 KiB and 20 redirect URIs. Registration is limited to 60 requests per observed client IP per hour. This registers an application; a user must still sign in and approve its access. Confidential clients receive a secret once, while only its hash is stored."
register_response_description = "Registered client metadata and, for a confidential client, its new secret"
register_request_schema = {
    "type": "object", "required": ["redirect_uris"],
    "properties": {
        "client_name": {"type": "string", "description": "Application name displayed on consent and app connections", "default": "Application", "maxLength": 150},
        "redirect_uris": {"type": "array", "minItems": 1, "maxItems": 20, "items": {"type": "string", "format": "uri"}, "description": "Explicit HTTPS or loopback callbacks; fragments and embedded credentials are rejected"},
        "token_endpoint_auth_method": {"type": "string", "enum": ["none", "client_secret_post", "client_secret_basic"], "default": "none", "description": "Client authentication method for token exchange and revocation"},
    },
}
register_request_example = {
    "client_name": "Dashboard assistant", "redirect_uris": ["http://127.0.0.1:9000/callback"],
    "token_endpoint_auth_method": "none",
}
register_response_example = {
    **register_request_example, "client_id": "registered-client-id",
    "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
}
register_response_schema = {
    "type": "object", "required": ["client_id", "client_name", "redirect_uris", "token_endpoint_auth_method", "grant_types", "response_types"],
    "properties": {
        **register_request_schema["properties"],
        "client_id": {"type": "string", "description": "Generated client identifier"},
        "grant_types": {"type": "array", "items": {"type": "string"}},
        "response_types": {"type": "array", "items": {"type": "string"}},
        "client_secret": {"type": "string", "description": "Returned only when registering a confidential client"},
        "client_secret_expires_at": {"type": "integer", "description": "Zero indicates a non-expiring client secret"},
    },
}
register_rate_limit_response_description = "Registration rate limit exceeded"
register_rate_limit_response_example = {"detail": "Too many registrations"}
register_request_body = {"required": True, "content": {"application/json": {
    "schema": register_request_schema, "example": register_request_example,
}}}

# GET /oauth2/authorize
authorize_summary = "Begin OAuth authorization"
authorize_description = "Validate the registered or metadata-document client, resource audience, callback, requested scopes, and S256 PKCE challenge. Create a browser-bound authorization attempt and redirect to consent. An omitted scope uses the resource's defaults. Invalid callbacks are rejected without redirecting."
authorize_response_description = "Redirect to browser consent and set the browser-binding cookie"
authorize_parameters = [
    {"name": "client_id", "in": "query", "required": True, "description": "Registered, configured, or HTTPS metadata-document client identifier", "schema": {"type": "string"}},
    {"name": "resource", "in": "query", "required": True, "description": "Exact registered resource audience", "schema": {"type": "string", "format": "uri"}},
    {"name": "redirect_uri", "in": "query", "required": True, "description": "Registered callback URI. Literal loopback callbacks may choose an ephemeral port.", "schema": {"type": "string", "format": "uri"}},
    {"name": "response_type", "in": "query", "required": True, "description": "Authorization Code is the supported response type", "schema": {"type": "string", "enum": ["code"]}},
    {"name": "code_challenge_method", "in": "query", "required": True, "description": "Required PKCE challenge method", "schema": {"type": "string", "enum": ["S256"]}},
    {"name": "code_challenge", "in": "query", "required": True, "description": "Base64url-encoded SHA-256 digest of the PKCE verifier, without padding", "schema": {"type": "string", "pattern": "^[A-Za-z0-9_-]{43}$"}},
    {"name": "scope", "in": "query", "required": False, "description": "Space-separated resource scopes; defaults to the resource's configured default scopes", "schema": {"type": "string"}},
    {"name": "state", "in": "query", "required": False, "description": "Client state returned unchanged in the callback", "schema": {"type": "string", "maxLength": 2048}},
]

# GET /oauth2/consent
consent_summary = "Display OAuth consent"
consent_description = "Show the application, callback, resource, and requested permissions. Browser cookies authenticate the user; bearer tokens are ignored. Anonymous users are redirected to the normal WireCloud login flow. The displayed consent is bound to the current user and login session."
consent_response_description = "HTML consent page"
consent_request_id_description = "Opaque authorization attempt handle returned by /oauth2/authorize"
consent_csrf_description = "Browser-bound consent CSRF value returned by /oauth2/authorize"
consent_login_redirect_response_description = "Redirect to WireCloud sign-in, retaining the pending consent"
consent_parameters = [browser_session_parameter, browser_binding_parameter]

# POST /oauth2/consent
approve_summary = "Approve or deny OAuth consent"
approve_description = "Consume the browser-bound consent attempt once. Approval creates a grant tied to the user's login session and a one-use authorization code valid for 60 seconds. Denial redirects with access_denied. The validated callback receives iss, the original client state if supplied, and either code or error."
approve_response_description = "Redirect to the validated client callback with an authorization code or access_denied"
approve_request_schema = {
    "type": "object", "required": ["request_id", "csrf"],
    "properties": {
        "request_id": {"type": "string", "description": consent_request_id_description},
        "csrf": {"type": "string", "description": consent_csrf_description},
        "decision": {"type": "string", "enum": ["approve", "deny"], "default": "deny", "description": "Only approve grants access; an omitted decision denies access"},
    },
}
approve_request_body = {"required": True, "content": {"application/x-www-form-urlencoded": {
    "schema": approve_request_schema, "example": {"request_id": "browser-attempt", "csrf": "consent-csrf", "decision": "approve"},
}}}

# POST /oauth2/token
token_endpoint_summary = "Exchange an authorization code or refresh token"
token_endpoint_description = "Issue opaque access and refresh tokens for an exact resource audience. Authorization codes are one-use and require the original callback and PKCE verifier. Refresh tokens rotate; reusing one revokes the connection. Tokens remain bound to the authorizing WireCloud session. Clients may narrow refresh scopes; only an explicit browser permission edit can expand the connection."
token_endpoint_response_description = "New access and refresh tokens"
token_client_properties = {
    "client_id": {"type": "string", "description": "Required for public and client_secret_post clients; HTTP Basic clients provide their ID in the header"},
    "client_secret": {"type": "string", "description": "Required only for client_secret_post clients"},
    "resource": {"type": "string", "format": "uri", "description": "Exact registered resource audience"},
}
token_endpoint_request_schema = {
    "type": "object",
    "required": ["grant_type", "resource"],
    "properties": {
        **token_client_properties,
        "grant_type": {"type": "string", "enum": ["authorization_code", "refresh_token"]},
        "code": {"type": "string", "description": "One-use authorization code; required for authorization_code"},
        "code_verifier": {"type": "string", "minLength": 43, "maxLength": 128, "pattern": "^[A-Za-z0-9._~-]+$", "description": "Original PKCE verifier; required for authorization_code"},
        "redirect_uri": {"type": "string", "format": "uri", "description": "Exact callback URI used during authorization; required for authorization_code"},
        "refresh_token": {"type": "string", "description": "Unconsumed refresh token; required for refresh_token"},
        "scope": {"type": "string", "description": "Optional space-separated subset of the current token's effective scopes when refreshing"},
    },
    "oneOf": [
        {"required": ["code", "code_verifier", "redirect_uri"],
         "properties": {"grant_type": {"enum": ["authorization_code"]}}},
        {"required": ["refresh_token"], "properties": {"grant_type": {"enum": ["refresh_token"]}}},
    ],
}
token_endpoint_request_examples = {
    "authorization_code": {"summary": "Exchange a PKCE authorization code", "value": {
        "grant_type": "authorization_code", "client_id": "registered-client-id", "code": "one-use-code",
        "code_verifier": "a" * 43, "redirect_uri": "http://127.0.0.1:9000/callback",
        "resource": "https://wirecloud.example.org/mcp",
    }},
    "refresh_token": {"summary": "Rotate a refresh token", "value": {
        "grant_type": "refresh_token", "client_id": "registered-client-id", "refresh_token": "opaque-refresh-token",
        "resource": "https://wirecloud.example.org/mcp", "scope": "wirecloud:read",
    }},
}
token_endpoint_request_body = {"required": True, "content": {"application/x-www-form-urlencoded": {
    "schema": token_endpoint_request_schema, "examples": token_endpoint_request_examples,
}}}
token_endpoint_response_example = {
    "access_token": "opaque-access-token", "refresh_token": "opaque-refresh-token",
    "token_type": "Bearer", "expires_in": 900, "scope": "wirecloud:read",
}
token_endpoint_response_schema = {
    "type": "object", "required": list(token_endpoint_response_example),
    "properties": {
        "access_token": {"type": "string"}, "refresh_token": {"type": "string"},
        "token_type": {"type": "string", "enum": ["Bearer"]},
        "expires_in": {"type": "integer", "minimum": 0, "description": "Access-token lifetime in seconds, bounded by the authorizing session"},
        "scope": {"type": "string", "description": "Granted space-separated scopes"},
    },
}

# POST /oauth2/revoke
revoke_summary = "Revoke an OAuth connection"
revoke_description = "Authenticate the client and revoke the connection associated with its access or refresh token. This invalidates all tokens for that grant. Unknown tokens and tokens belonging to another client return an empty successful response."
revoke_response_description = "Revocation processed"
revoke_request_schema = {
    "type": "object", "required": ["token"],
    "properties": {
        "client_id": token_client_properties["client_id"],
        "client_secret": token_client_properties["client_secret"],
        "token": {"type": "string", "description": "Access or refresh token to revoke"},
    },
}
revoke_request_body = {"required": True, "content": {"application/x-www-form-urlencoded": {
    "schema": revoke_request_schema, "example": {"client_id": "registered-client-id", "token": "opaque-access-token"},
}}}
revoke_success_response_example = {}

# GET /oauth2/connections
connections_summary = "List the current user's app connections"
connections_description = "List unrevoked, unexpired connections owned by the signed-in browser user. By default return the standalone HTML page; Accept: application/json returns connection details, permission choices, and a one-use management CSRF token. Set the browser-binding cookie needed to save or revoke a connection. Bearer tokens cannot manage browser connections."
connections_response_description = "Standalone HTML page or JSON connection list and management CSRF token"
connections_response_example = {
    "connections": [{
        "id": "connection-id", "client_name": "Dashboard assistant", "client_id": "registered-client-id",
        "resource_name": "WireCloud MCP", "permissions": ["Read accessible workspaces"],
        "scope_options": [
            {"scope": "wirecloud:read", "description": "Read accessible workspaces", "selected": True},
            {"scope": "wirecloud:workspace:write", "description": "Edit workspaces", "selected": False},
        ],
    }],
    "csrf": "one-use-management-csrf",
}
connections_response_schema = {
    "type": "object", "required": ["connections", "csrf"],
    "properties": {
        "csrf": {"type": "string", "description": "One-use CSRF token bound to this browser and login session"},
        "connections": {"type": "array", "items": {
            "type": "object", "required": ["id", "client_name", "client_id", "resource_name", "permissions", "scope_options"],
            "properties": {
                "id": {"type": "string"}, "client_name": {"type": "string"}, "client_id": {"type": "string"},
                "resource_name": {"type": "string"}, "permissions": {"type": "array", "items": {"type": "string"}},
                "scope_options": {"type": "array", "description": "Available scopes; empty if the resource is no longer registered",
                    "items": {"type": "object", "required": ["scope", "description", "selected"], "properties": {
                        "scope": {"type": "string"}, "description": {"type": "string"}, "selected": {"type": "boolean"},
                    }}},
            },
        }},
    },
}
connections_login_redirect_response_description = "Anonymous HTML requests are redirected to WireCloud sign-in"

# POST /oauth2/connections
manage_connection_summary = "Change permissions or revoke an app connection"
manage_connection_description = "Manage a connection owned by the signed-in browser user. Submit the one-use CSRF value from GET /oauth2/connections with the same browser cookie and login session. update_permissions replaces the connection's scopes and immediately affects existing access and refresh tokens; at least one registered scope is required. The default revoke action removes the connection's access. Existing WireCloud user and object permissions still apply."
manage_connection_response_description = "Redirect to the connection list; JSON requests receive updated or revoked"
manage_connection_request_schema = {
    "type": "object", "required": ["grant_id", "csrf"],
    "properties": {
        "grant_id": {"type": "string", "description": "Connection ID from the connection list"},
        "csrf": {"type": "string", "description": "One-use browser- and session-bound management CSRF token"},
        "action": {"type": "string", "enum": ["revoke", "update_permissions"], "default": "revoke"},
        "scope": {"description": "Required for update_permissions: a space-separated list or repeated form values of registered scopes",
                  "oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}, "minItems": 1}]},
    },
}
manage_connection_request_body = {"required": True, "content": {"application/x-www-form-urlencoded": {
    "schema": manage_connection_request_schema, "examples": {
        "update_permissions": {"summary": "Save selected permissions", "value": {
            "grant_id": "connection-id", "csrf": "one-use-management-csrf", "action": "update_permissions",
            "scope": "wirecloud:read wirecloud:workspace:write",
        }},
        "revoke": {"summary": "Revoke a connection", "value": {
            "grant_id": "connection-id", "csrf": "one-use-management-csrf", "action": "revoke",
        }},
    },
}}}
manage_connection_success_response_description = "JSON confirmation of the requested action"
manage_connection_success_response_examples = {"updated": {"value": {"updated": True}}, "revoked": {"value": {"revoked": True}}}
manage_connection_redirect_response_description = "Redirect to the standalone connection list"
manage_connection_bad_request_response_description = "Unknown action, empty or invalid permissions, or an unavailable OAuth resource"
manage_connection_bad_request_response_example = {"detail": "Select at least one available permission"}
