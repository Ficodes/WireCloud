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

from __future__ import annotations

import hmac
import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, AsyncIterator, Optional
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import Field

from wirecloud import settings
from wirecloud.commons.auth.crud import get_token_expiration
from wirecloud.commons.auth.schemas import UserAll
from wirecloud.commons.auth.utils import Token, get_token_contents, get_user
from wirecloud.database import DBDep, DBSession, Id, commit, get_session
from wirecloud.oauth2provider import crud, docs, service as auth
from wirecloud.oauth2provider.pages import render_page


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    provider = app.dependency_overrides.get(get_session, get_session)
    async for db in provider():
        await crud.ensure_indexes(db)
        await commit(db)
    yield


router = APIRouter(lifespan=lifespan)
metadata_router = APIRouter()


async def oauth_error_handler(request: Request, exc: auth.OAuthError) -> JSONResponse:
    return JSONResponse(exc.detail, exc.status_code, headers={"Cache-Control": "no-store"})


async def browser_identity(request: Request, db: DBSession) -> tuple[Optional[UserAll], Token]:
    # A browser consent is never authenticated by a bearer token or URL argument.
    token = await get_token_contents(request.cookies.get("token", ""), request, db, csrf=False)
    user = await get_user(db, token, False)
    if token and "real_user" in token:
        raise HTTPException(403, "End impersonation before connecting an application")
    return user, token


@metadata_router.get(
    "/.well-known/oauth-authorization-server",
    summary=docs.authorization_metadata_summary,
    description=docs.authorization_metadata_description,
    response_description=docs.authorization_metadata_response_description,
    responses={
        200: {
            "description": docs.authorization_metadata_response_description,
            "content": {"application/json": {"example": docs.authorization_metadata_response_example}},
        },
        404: {
            "description": docs.not_found_response_description,
            "content": {
                "application/json": {"schema": docs.http_error_schema, "example": docs.not_found_response_example},
            },
        },
    },
)
@metadata_router.get(
    "/.well-known/oauth-authorization-server/oauth2",
    summary=docs.authorization_metadata_summary,
    description=docs.authorization_metadata_description,
    response_description=docs.authorization_metadata_response_description,
    responses={
        200: {
            "description": docs.authorization_metadata_response_description,
            "content": {"application/json": {"example": docs.authorization_metadata_response_example}},
        },
        404: {
            "description": docs.not_found_response_description,
            "content": {
                "application/json": {"schema": docs.http_error_schema, "example": docs.not_found_response_example},
            },
        },
    },
)
@metadata_router.get(
    "/.well-known/oauth-authorization-server/{issuer_path:path}",
    summary=docs.authorization_metadata_summary,
    description=docs.authorization_metadata_description,
    response_description=docs.authorization_metadata_response_description,
    responses={
        200: {
            "description": docs.authorization_metadata_response_description,
            "content": {"application/json": {"example": docs.authorization_metadata_response_example}},
        },
        404: {
            "description": docs.not_found_response_description,
            "content": {
                "application/json": {"schema": docs.http_error_schema, "example": docs.not_found_response_example},
            },
        },
    },
    openapi_extra={"parameters": docs.authorization_metadata_path_parameters},
)
async def authorization_metadata(request: Request) -> dict[str, Any]:
    resources = getattr(request.app.state, "oauth2_resources", {})
    if not resources:
        raise HTTPException(404)
    issuer = auth.public_base(request) + "/oauth2"
    result = {
        "issuer": issuer,
        "authorization_endpoint": issuer + "/authorize",
        "token_endpoint": issuer + "/token",
        "revocation_endpoint": issuer + "/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "client_id_metadata_document_supported": True,
        "authorization_response_iss_parameter_supported": True,
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
        "scopes_supported": sorted({s for r in resources.values() for s in r.scopes}),
    }
    if getattr(settings, "OAUTH2_DYNAMIC_REGISTRATION", True):
        result["registration_endpoint"] = issuer + "/register"
    return result


@metadata_router.get(
    "/.well-known/oauth-protected-resource",
    summary=docs.resource_metadata_summary,
    description=docs.resource_metadata_description,
    response_description=docs.resource_metadata_response_description,
    responses={
        200: {
            "description": docs.resource_metadata_response_description,
            "content": {"application/json": {"example": docs.resource_metadata_response_example}},
        },
        404: {
            "description": docs.not_found_response_description,
            "content": {
                "application/json": {"schema": docs.http_error_schema, "example": docs.not_found_response_example},
            },
        },
    },
)
@metadata_router.get(
    "/.well-known/oauth-protected-resource/{resource_path:path}",
    summary=docs.resource_metadata_summary,
    description=docs.resource_metadata_description,
    response_description=docs.resource_metadata_response_description,
    responses={
        200: {
            "description": docs.resource_metadata_response_description,
            "content": {"application/json": {"example": docs.resource_metadata_response_example}},
        },
        404: {
            "description": docs.not_found_response_description,
            "content": {
                "application/json": {"schema": docs.http_error_schema, "example": docs.not_found_response_example},
            },
        },
    },
)
async def resource_metadata(
    request: Request,
    resource_path: Annotated[str, Field(description=docs.resource_metadata_path_description)] = "",
) -> dict[str, Any]:
    for resource in getattr(request.app.state, "oauth2_resources", {}).values():
        if urlsplit(resource.audience).path.rstrip("/") == "/" + resource_path.strip("/") or (
            not resource_path and len(getattr(request.app.state, "oauth2_resources", {})) == 1
        ):
            return {
                "resource": resource.audience,
                "resource_name": resource.name,
                "authorization_servers": [auth.public_base(request) + "/oauth2"],
                "scopes_supported": list(resource.scopes),
                "bearer_methods_supported": ["header"],
            }
    raise HTTPException(404)


@router.post(
    "/register",
    summary=docs.register_summary,
    description=docs.register_description,
    status_code=201,
    response_class=JSONResponse,
    response_description=docs.register_response_description,
    responses={
        201: {
            "description": docs.register_response_description,
            "headers": docs.no_store_headers,
            "content": {
                "application/json": {"schema": docs.register_response_schema, "example": docs.register_response_example},
            },
        },
        400: {
            "description": docs.oauth_bad_request_response_description,
            "content": {
                "application/json": {"schema": docs.oauth_error_schema, "example": docs.oauth_bad_request_response_example},
            },
        },
        404: {
            "description": docs.not_found_response_description,
            "content": {
                "application/json": {"schema": docs.http_error_schema, "example": docs.not_found_response_example},
            },
        },
        429: {
            "description": docs.register_rate_limit_response_description,
            "content": {
                "application/json": {"schema": docs.http_error_schema, "example": docs.register_rate_limit_response_example},
            },
        },
    },
    openapi_extra={"requestBody": docs.register_request_body},
)
async def register(request: Request, db: DBDep) -> JSONResponse:
    if not getattr(request.app.state, "oauth2_resources", {}) or not getattr(
        settings, "OAUTH2_DYNAMIC_REGISTRATION", True
    ):
        raise HTTPException(404)
    bucket = "registration:" + auth.digest(request.client.host) + ":" + auth.now().strftime("%Y%m%d%H")
    count = await crud.increment_registration_attempts(db, bucket, auth.now() + timedelta(hours=1))
    await commit(db)
    if count >= 60:
        raise HTTPException(429, "Too many registrations")
    try:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 65536:
                auth.oauth_error("invalid_client_metadata", "Metadata too large")
        data = json.loads(body)
        client = auth.validate_client(data)
    except (ValueError, AttributeError, TypeError):
        auth.oauth_error("invalid_client_metadata", "Invalid metadata")
    client["client_id"] = auth.random_token()
    response = dict(client)
    if client["token_endpoint_auth_method"] != "none":
        secret = auth.random_token()
        client["secret_hash"] = auth.digest(secret)
        response.update(client_secret=secret, client_secret_expires_at=0)
    await crud.create_client(db, client)
    await commit(db)
    return JSONResponse(response, 201, headers={"Cache-Control": "no-store"})


@router.get(
    "/authorize",
    summary=docs.authorize_summary,
    description=docs.authorize_description,
    status_code=302,
    response_class=RedirectResponse,
    response_description=docs.authorize_response_description,
    responses={
        302: {"description": docs.authorize_response_description, "headers": docs.redirect_headers},
        400: {
            "description": docs.oauth_bad_request_response_description,
            "content": {
                "application/json": {"schema": docs.oauth_error_schema, "example": docs.oauth_bad_request_response_example},
            },
        },
        401: {
            "description": docs.invalid_client_response_description,
            "content": {
                "application/json": {"schema": docs.oauth_error_schema, "example": docs.invalid_client_response_example},
            },
        },
    },
    openapi_extra={"parameters": docs.authorize_parameters},
)
async def authorize(request: Request, db: DBDep) -> RedirectResponse:
    q = request.query_params
    resource = auth.get_resource(request, q.get("resource", ""))
    client = await auth.get_client(db, q.get("client_id", ""))
    redirect = q.get("redirect_uri", "")
    if not any(auth.redirect_matches(registered, redirect) for registered in client["redirect_uris"]):
        auth.oauth_error(description="Unregistered redirect URI")
    if (
        q.get("response_type") != "code"
        or q.get("code_challenge_method") != "S256"
        or not re.fullmatch(r"[A-Za-z0-9_-]{43}", q.get("code_challenge", ""))
    ):
        auth.oauth_error(description="Authorization code with S256 PKCE is required")
    scopes = q.get("scope", " ".join(resource.default_scopes)).split()
    if not scopes or not set(scopes).issubset(resource.scopes) or len(q.get("state", "")) > 2048:
        auth.oauth_error("invalid_scope", "Unknown or empty scopes")
    handle, csrf = auth.random_token(), auth.random_token()
    browser = request.cookies.get("wc_oauth_browser") or auth.random_token()
    await crud.create_attempt(
        db,
        {
            "_id": auth.digest(handle),
            "client_id": client["client_id"],
            "client_name": client["client_name"],
            "redirect_uri": redirect,
            "audience": resource.audience,
            "scopes": scopes,
            "challenge": q["code_challenge"],
            "state": q.get("state"),
            "browser": auth.digest(browser),
            "csrf": auth.digest(csrf),
            "expires_at": auth.now() + timedelta(minutes=10),
        }
    )
    await commit(db)
    # CSRF is an unguessable form token, not an authorization code or credential.
    response = RedirectResponse(
        auth.public_base(request) + "/oauth2/consent?" + urlencode({"request_id": handle, "csrf": csrf}), 302
    )
    response.set_cookie(
        "wc_oauth_browser",
        browser,
        secure=auth.public_base(request).startswith("https:"),
        httponly=True,
        samesite="lax",
        max_age=600,
    )
    return response


async def attempt_for_browser(request: Request, db: DBSession, handle: str, csrf: str) -> dict[str, Any]:
    attempt = await crud.get_authorization_attempt(db, auth.digest(handle), auth.now())
    if (
        attempt is None
        or not hmac.compare_digest(attempt["browser"], auth.digest(request.cookies.get("wc_oauth_browser", "")))
        or not hmac.compare_digest(attempt["csrf"], auth.digest(csrf))
    ):
        auth.oauth_error(description="Expired or invalid browser authorization attempt")
    return attempt


@router.get(
    "/consent",
    summary=docs.consent_summary,
    description=docs.consent_description,
    response_class=HTMLResponse,
    response_description=docs.consent_response_description,
    responses={
        200: {"description": docs.consent_response_description, "headers": docs.no_store_headers},
        302: {"description": docs.consent_login_redirect_response_description, "headers": docs.redirect_headers},
        400: {
            "description": docs.oauth_bad_request_response_description,
            "content": {
                "application/json": {"schema": docs.oauth_error_schema, "example": docs.oauth_bad_request_response_example},
            },
        },
        403: {
            "description": docs.browser_permission_denied_response_description,
            "content": {
                "application/json": {"schema": docs.http_error_schema, "example": docs.browser_permission_denied_response_example},
            },
        },
    },
    openapi_extra={"parameters": docs.consent_parameters},
)
async def consent(
    request: Request, db: DBDep,
    request_id: str = Query(..., description=docs.consent_request_id_description),
    csrf: str = Query(..., description=docs.consent_csrf_description),
) -> Response:
    attempt = await attempt_for_browser(request, db, request_id, csrf)
    resource = auth.get_resource(request, attempt["audience"])
    user, token = await browser_identity(request, db)
    if user is None:
        target = request.url.path + "?" + urlencode({"request_id": request_id, "csrf": csrf})
        return RedirectResponse(auth.public_base(request) + "/auth/login?" + urlencode({"return_to": target}), 302)
    # Bind the displayed consent to this user and session, including when another
    # tab signs in to a different account before the form is submitted.
    bound = await crud.bind_authorization_attempt(db, attempt["_id"], str(user.id), token["jti"])
    if not bound:
        auth.oauth_error(description="Sign-in session changed; start authorization again")
    await commit(db)
    return render_page(
        request,
        "consent",
        {
            "user": user,
            "resource": resource,
            "attempt": attempt,
            "permissions": [resource.scopes[scope] for scope in attempt["scopes"]],
            "request_id": request_id,
            "csrf": csrf,
        },
        form_redirect_uri=attempt["redirect_uri"],
    )


@router.post(
    "/consent",
    summary=docs.approve_summary,
    description=docs.approve_description,
    status_code=302,
    response_class=RedirectResponse,
    response_description=docs.approve_response_description,
    responses={
        302: {
            "description": docs.approve_response_description,
            "headers": {**docs.redirect_headers, **docs.no_store_headers},
        },
        400: {
            "description": docs.oauth_bad_request_response_description,
            "content": {
                "application/json": {"schema": docs.oauth_error_schema, "example": docs.oauth_bad_request_response_example},
            },
        },
        401: {
            "description": docs.browser_auth_required_response_description,
            "content": {
                "application/json": {"schema": docs.http_error_schema, "example": docs.browser_auth_required_response_example},
            },
        },
        403: {
            "description": docs.browser_permission_denied_response_description,
            "content": {
                "application/json": {"schema": docs.http_error_schema, "example": docs.browser_permission_denied_response_example},
            },
        },
    },
    openapi_extra={"parameters": docs.authenticated_browser_parameters, "requestBody": docs.approve_request_body},
)
async def approve(request: Request, db: DBDep) -> RedirectResponse:
    form = await request.form(max_files=0, max_fields=5)
    attempt = await attempt_for_browser(request, db, str(form.get("request_id", "")), str(form.get("csrf", "")))
    user, token = await browser_identity(request, db)
    if user is None:
        raise HTTPException(401, "Sign in before authorizing")
    consumed = await crud.consume_authorization_attempt(db, attempt["_id"], str(user.id), token["jti"])
    if consumed is None:
        auth.oauth_error(description="Authorization attempt already used or sign-in session changed")
    params = {"iss": auth.public_base(request) + "/oauth2"}
    if attempt.get("state") is not None:
        params["state"] = attempt["state"]
    if form.get("decision") != "approve":
        params["error"] = "access_denied"
    else:
        grant_id, code = auth.random_token(), auth.random_token()
        session_expiration = await get_token_expiration(db, Id(token["jti"]))
        if session_expiration is None:
            auth.oauth_error("invalid_grant", "Authorizing session ended")
        expiration = min(
            auth.utc(session_expiration),
            datetime.fromtimestamp(token["exp"], tz=timezone.utc),
        )
        await crud.create_grant(
            db,
            {
                "_id": grant_id,
                "client_id": attempt["client_id"],
                "client_name": attempt["client_name"],
                "user_id": str(user.id),
                "session_id": token["jti"],
                "audience": attempt["audience"],
                "scopes": attempt["scopes"],
                "revoked": False,
                "created_at": auth.now(),
                "expires_at": expiration,
            }
        )
        await crud.create_code(
            db,
            {
                "_id": auth.digest(code),
                "grant_id": grant_id,
                "client_id": attempt["client_id"],
                "audience": attempt["audience"],
                "redirect_uri": attempt["redirect_uri"],
                "challenge": attempt["challenge"],
                "expires_at": auth.now() + timedelta(seconds=60),
            }
        )
        params["code"] = code
    await commit(db)
    separator = "&" if "?" in attempt["redirect_uri"] else "?"
    return RedirectResponse(
        attempt["redirect_uri"] + separator + urlencode(params),
        302,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.post(
    "/token",
    summary=docs.token_endpoint_summary,
    description=docs.token_endpoint_description,
    response_class=JSONResponse,
    response_description=docs.token_endpoint_response_description,
    responses={
        200: {
            "description": docs.token_endpoint_response_description,
            "headers": docs.no_store_headers,
            "content": {
                "application/json": {
                    "schema": docs.token_endpoint_response_schema,
                    "example": docs.token_endpoint_response_example,
                },
            },
        },
        400: {
            "description": docs.oauth_bad_request_response_description,
            "content": {
                "application/json": {"schema": docs.oauth_error_schema, "example": docs.oauth_bad_request_response_example},
            },
        },
        401: {
            "description": docs.invalid_client_response_description,
            "content": {
                "application/json": {"schema": docs.oauth_error_schema, "example": docs.invalid_client_response_example},
            },
        },
    },
    openapi_extra={"parameters": [docs.client_auth_parameter], "requestBody": docs.token_endpoint_request_body},
)
async def token_endpoint(request: Request, db: DBDep) -> JSONResponse:
    form = await request.form(max_files=0, max_fields=12)
    client = await auth.authenticate_client(db, form, request.headers.get("authorization", ""))
    auth.get_resource(request, str(form.get("resource", "")))
    if form.get("grant_type") == "authorization_code":
        result = await auth.exchange_code(db, client, form)
    elif form.get("grant_type") == "refresh_token":
        result = await auth.exchange_refresh(db, client, form)
    else:
        auth.oauth_error("unsupported_grant_type", "Unsupported grant")
    await commit(db)
    return JSONResponse(result, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


@router.post(
    "/revoke",
    summary=docs.revoke_summary,
    description=docs.revoke_description,
    response_class=JSONResponse,
    response_description=docs.revoke_response_description,
    responses={
        200: {
            "description": docs.revoke_response_description,
            "headers": docs.no_store_headers,
            "content": {
                "application/json": {
                    "schema": {"type": "object", "maxProperties": 0},
                    "example": docs.revoke_success_response_example,
                },
            },
        },
        401: {
            "description": docs.invalid_client_response_description,
            "content": {
                "application/json": {"schema": docs.oauth_error_schema, "example": docs.invalid_client_response_example},
            },
        },
    },
    openapi_extra={"parameters": [docs.client_auth_parameter], "requestBody": docs.revoke_request_body},
)
async def revoke(request: Request, db: DBDep) -> JSONResponse:
    form = await request.form(max_files=0, max_fields=5)
    client = await auth.authenticate_client(db, form, request.headers.get("authorization", ""))
    record = await crud.get_token_by_id(db, auth.digest(str(form.get("token", ""))))
    if record:
        await crud.revoke_grant(db, record["grant_id"], client_id=client["client_id"])
    await commit(db)
    return JSONResponse({}, headers={"Cache-Control": "no-store"})


@router.get(
    "/connections",
    summary=docs.connections_summary,
    description=docs.connections_description,
    response_class=HTMLResponse,
    response_description=docs.connections_response_description,
    responses={
        200: {
            "description": docs.connections_response_description,
            "headers": docs.no_store_headers,
            "content": {
                "text/html": {"schema": {"type": "string"}},
                "application/json": {"schema": docs.connections_response_schema, "example": docs.connections_response_example},
            },
        },
        302: {
            "description": docs.connections_login_redirect_response_description,
            "headers": docs.redirect_headers,
        },
        401: {
            "description": docs.browser_auth_required_response_description,
            "content": {
                "application/json": {"schema": docs.http_error_schema, "example": docs.browser_auth_required_response_example},
            },
        },
        403: {
            "description": docs.browser_permission_denied_response_description,
            "content": {
                "application/json": {"schema": docs.http_error_schema, "example": docs.browser_permission_denied_response_example},
            },
        },
    },
    openapi_extra={"parameters": [docs.accept_parameter, docs.browser_session_parameter]},
)
async def connections(request: Request, db: DBDep) -> Response:
    user, token = await browser_identity(request, db)
    if user is None:
        if "application/json" in request.headers.get("accept", ""):
            raise HTTPException(401, "Sign in to manage app connections")
        return RedirectResponse(
            auth.public_base(request) + "/auth/login?" + urlencode({"return_to": request.url.path}), 302
        )
    csrf = auth.random_token()
    browser = request.cookies.get("wc_oauth_browser") or auth.random_token()
    await crud.create_attempt(
        db,
        {
            "_id": auth.digest(csrf),
            "browser": auth.digest(browser),
            "session_id": token["jti"],
            "expires_at": auth.now() + timedelta(minutes=10),
            "purpose": "connections",
        }
    )
    rows = []
    for grant in await crud.get_grants_for_user(db, str(user.id), auth.now()):
        resource = getattr(request.app.state, "oauth2_resources", {}).get(grant["audience"])
        if auth.utc(grant["expires_at"]) <= auth.now():
            continue
        rows.append(
            {
                "id": grant["_id"],
                "client_name": grant["client_name"],
                "client_id": grant["client_id"],
                "resource_name": resource.name if resource else grant["audience"],
                "permissions": [resource.scopes.get(scope, scope) if resource else scope for scope in grant["scopes"]],
                "scope_options": [
                    {"scope": scope, "description": description, "selected": scope in grant["scopes"]}
                    for scope, description in resource.scopes.items()
                ] if resource else [],
            }
        )
    await commit(db)
    if "application/json" in request.headers.get("accept", ""):
        response = JSONResponse({"connections": rows, "csrf": csrf}, headers={"Cache-Control": "no-store"})
    else:
        response = render_page(request, "connections", {"user": user, "connections": rows, "csrf": csrf})
    response.headers["Vary"] = "Accept"
    response.set_cookie(
        "wc_oauth_browser",
        browser,
        httponly=True,
        secure=auth.public_base(request).startswith("https:"),
        samesite="lax",
        max_age=600,
    )
    return response


@router.post(
    "/connections",
    summary=docs.manage_connection_summary,
    description=docs.manage_connection_description,
    status_code=303,
    response_class=Response,
    response_description=docs.manage_connection_response_description,
    responses={
        200: {
            "description": docs.manage_connection_success_response_description,
            "headers": docs.no_store_headers,
            "content": {
                "application/json": {
                    "schema": {
                        "oneOf": [
                            {
                                "type": "object", "required": ["updated"],
                                "properties": {"updated": {"type": "boolean", "enum": [True]}},
                            },
                            {
                                "type": "object", "required": ["revoked"],
                                "properties": {"revoked": {"type": "boolean", "enum": [True]}},
                            },
                        ],
                    },
                    "examples": docs.manage_connection_success_response_examples,
                },
            },
        },
        303: {
            "description": docs.manage_connection_redirect_response_description,
            "headers": docs.redirect_headers,
        },
        400: {
            "description": docs.manage_connection_bad_request_response_description,
            "content": {
                "application/json": {
                    "schema": {"oneOf": [docs.http_error_schema, docs.oauth_error_schema]},
                    "example": docs.manage_connection_bad_request_response_example,
                },
            },
        },
        401: {
            "description": docs.browser_auth_required_response_description,
            "content": {
                "application/json": {"schema": docs.http_error_schema, "example": docs.browser_auth_required_response_example},
            },
        },
        403: {
            "description": docs.browser_permission_denied_response_description,
            "content": {
                "application/json": {"schema": docs.http_error_schema, "example": docs.browser_permission_denied_response_example},
            },
        },
        404: {
            "description": docs.not_found_response_description,
            "content": {
                "application/json": {"schema": docs.http_error_schema, "example": docs.not_found_response_example},
            },
        },
    },
    openapi_extra={
        "parameters": [docs.accept_parameter, *docs.authenticated_browser_parameters],
        "requestBody": docs.manage_connection_request_body,
    },
)
async def manage_connection(request: Request, db: DBDep) -> Response:
    user, token = await browser_identity(request, db)
    if user is None:
        raise HTTPException(401)
    form = await request.form(max_files=0, max_fields=128)
    action = str(form.get("action", "revoke"))
    if action not in ("revoke", "update_permissions"):
        raise HTTPException(400, "Unknown connection action")
    valid = await crud.consume_connection_attempt(
        db,
        auth.digest(str(form.get("csrf", ""))),
        auth.digest(request.cookies.get("wc_oauth_browser", "")),
        token["jti"],
        auth.now(),
    )
    if valid is None:
        raise HTTPException(403, "Invalid CSRF token")
    grant_id = str(form.get("grant_id", ""))
    if action == "update_permissions":
        grant = await crud.get_unrevoked_grant(db, grant_id)
        if grant is None or grant["user_id"] != str(user.id) or auth.utc(grant["expires_at"]) <= auth.now():
            raise HTTPException(404, "Connection not found")
        resource = auth.get_resource(request, grant["audience"])
        scopes = {scope for value in form.getlist("scope") for scope in str(value).split()}
        if not scopes or not scopes.issubset(resource.scopes):
            raise HTTPException(400, "Select at least one available permission")
        updated = await crud.update_grant_scopes(
            db, grant_id, str(user.id), [scope for scope in resource.scopes if scope in scopes], auth.now()
        )
        if not updated:
            raise HTTPException(404, "Connection not found")
    else:
        await crud.revoke_grant(db, grant_id, user_id=str(user.id))
    await commit(db)
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse(
            {"updated": True} if action == "update_permissions" else {"revoked": True},
            headers={"Cache-Control": "no-store", "Vary": "Accept"},
        )
    return RedirectResponse(request.url.path, 303)
