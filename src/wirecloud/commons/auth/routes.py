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

from contextlib import asynccontextmanager
from typing import AsyncIterator, Literal, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Request, Query, Body, Path
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from datetime import datetime, timedelta, timezone
from pydantic import ValidationError
import jwt
import asyncio
import inspect
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

from wirecloud.commons.auth.models import DBLoginAttempt, Group
from wirecloud.commons.search import add_user_to_index, add_group_to_index
from wirecloud.database import Id
from wirecloud.commons.auth.schemas import UserLogin, UserToken, UserWithPassword, UserTokenType, User, UserCreate, \
    SwitchUserRequest, UserUpdate, Permission, GroupCreate, GroupUpdate, OrganizationCreate, OrganizationGroupData, \
    OrganizationGroupUpdate
from wirecloud.commons.auth.crud import get_user_with_password, set_login_date_for_user, get_user_by_username, \
    create_user_db, update_user, create_token, invalidate_token, add_user_to_groups_by_codename, \
    create_group_if_not_exists, remove_user_from_all_groups, set_token_expiration, remove_user_idm_data, \
    get_user_with_all_info_by_username, get_token_idm_session, update_user_with_all_info, delete_user, \
    get_group_by_name, get_user_by_id, create_group_db, add_group_to_users, remove_group_to_users, update_group, \
    delete_group, create_organization_db, get_all_organization_groups, update_path_for_descendants, delete_organization, \
    ensure_login_attempt_indexes, create_login_attempt
from wirecloud.commons.auth.utils import check_password, SessionDepNoCSRF, SessionDep, \
    UserDep, UserDepNoCSRF, RealUserDep, hash_password, accepts_context, consume_login_attempt, validate_login_return_to
from wirecloud.database import DBDep, commit, get_session
from wirecloud.commons.utils.http import build_error_response, build_validation_error_response, produces, consumes, \
    get_redirect_response, get_absolute_reverse_url, resolve_url_name, authentication_required
from wirecloud import settings
from wirecloud import docs as root_docs
from wirecloud.commons.auth import docs, tokens
from wirecloud.platform.plugins import get_idm_get_token_functions, get_idm_get_user_functions, \
    get_idm_backchannel_logout_functions, get_idm_get_authorization_url_functions
from wirecloud.platform.routes import render_wirecloud
from wirecloud.platform.workspace.crud import get_workspace_by_username_and_name
from wirecloud.translation import gettext as _


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    provider = app.dependency_overrides.get(get_session, get_session)
    async for db in provider():
        await ensure_login_attempt_indexes(db)
        await commit(db)
    yield


router = APIRouter()
base_router = APIRouter(lifespan=lifespan)
admin_router = APIRouter()


@base_router.get(
    "/auth/login",
    summary=docs.begin_login_summary,
    description=docs.begin_login_description,
    response_class=RedirectResponse,
    status_code=302,
    response_description=docs.begin_login_response_description,
    responses={
        302: {
            "headers": {
                "Location": {"description": docs.login_redirect_location_description, "schema": {"type": "string"}},
                "Set-Cookie": {"description": docs.begin_login_browser_cookie_description, "schema": {"type": "string"}},
            },
        },
        400: {
            "description": docs.begin_login_bad_request_response_description,
            "content": {"application/json": {
                "schema": docs.login_http_error_schema, "example": docs.begin_login_bad_request_response_example,
            }},
        },
        503: {
            "description": docs.begin_login_unavailable_response_description,
            "content": {"application/json": {
                "schema": docs.login_http_error_schema, "example": docs.begin_login_unavailable_response_example,
            }},
        },
    },
)
async def begin_login(
    request: Request,
    db: DBDep,
    return_to: str = Query("/", description=docs.begin_login_return_to_description),
    next_url: Optional[str] = Query(None, alias="next", description=docs.begin_login_next_description),
    prompt: Optional[Literal["login", "select_account", "consent", "none"]] = Query(
        None, description=docs.begin_login_prompt_description
    ),
) -> RedirectResponse:
    return_to = validate_login_return_to(next_url or return_to)
    if not settings.OID_CONNECT_ENABLED:
        destination = get_absolute_reverse_url("wirecloud.login_form", request)
        return RedirectResponse(destination + "?" + urlencode({"return_to": return_to}), 302)

    provider = getattr(settings, "OID_CONNECT_PLUGIN", "")
    functions = get_idm_get_authorization_url_functions()
    if provider not in functions:
        raise HTTPException(503, "Authentication provider is unavailable")

    state, browser = "wc." + tokens.random_token(), tokens.random_token()
    attempt = DBLoginAttempt(
        id=tokens.digest(state), state=state, nonce=tokens.random_token(), code_verifier=tokens.random_token(),
        return_to=return_to, browser=tokens.digest(browser), expires_at=tokens.now() + timedelta(minutes=10),
    )
    await create_login_attempt(db, attempt)
    await commit(db)
    context = attempt.model_dump(exclude={"id"})
    base = tokens.public_base(request)
    exchange = get_idm_get_token_functions().get(provider)
    context["pkce"] = exchange is not None and accepts_context(exchange)
    context["redirect_uri"] = base + "/oidc/callback"
    function = functions[provider]
    result = function(login_context=context) if accepts_context(function) else function()
    if inspect.isawaitable(result):
        result = await result
    parts = urlsplit(result.urlpattern)
    query = dict(parse_qsl(parts.query))
    query.update(state=state, nonce=attempt.nonce, redirect_uri=context["redirect_uri"])
    if prompt:
        query["prompt"] = prompt
    if context["pkce"]:
        query.update(code_challenge=tokens.pkce(attempt.code_verifier), code_challenge_method="S256")
    destination = urlunsplit(parts._replace(query=urlencode(query)))
    response = RedirectResponse(
        destination, 302, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    )
    response.set_cookie(
        "wc_login_browser", browser, httponly=True, secure=base.startswith("https:"), samesite="lax", max_age=600
    )
    return response


@base_router.get(
    "/oidc/callback",
    summary=docs.oidc_login_summary,
    description=docs.oidc_login_description,
    response_class=Response,
    status_code=302,
    response_description=docs.oidc_login_response_description,
    responses={
        302: {
            "headers": {
                "Location": {"description": docs.login_redirect_location_description, "schema": {"type": "string"}},
                "Set-Cookie": {"description": docs.login_session_cookie_description, "schema": {"type": "string"}},
            },
        },
        400: {
            "description": docs.oidc_login_bad_request_response_description,
            "content": {"application/json": {
                "schema": {"oneOf": [docs.login_http_error_schema, {"$ref": "#/components/schemas/HTTPError"}]},
                "examples": docs.oidc_login_bad_request_response_examples,
            }},
        },
        401: root_docs.generate_error_response_openapi_description(
            docs.oidc_login_unauthorized_response_description, "Invalid user"),
        500: root_docs.generate_error_response_openapi_description(
            docs.oidc_login_configuration_error_response_description,
            "OIDC provider is not configured correctly! Contact your administrator."),
        502: root_docs.generate_error_response_openapi_description(
            docs.oidc_login_provider_error_response_description, "Identity provider request failed"),
        422: root_docs.generate_validation_error_response_openapi_description(
            docs.oidc_login_validation_error_response_description)
    },
    openapi_extra={"parameters": [
        {"name": "state", "in": "query", "required": True,
         "description": docs.oidc_login_state_description, "schema": {"type": "string"}},
        {"name": "wc_login_browser", "in": "cookie", "required": True,
         "description": docs.oidc_login_browser_cookie_description, "schema": {"type": "string"}},
    ]},
)
async def oidc_login(request: Request, db: DBDep, code: str = Query(description=docs.oidc_login_code_description)):
    if not getattr(settings, "OID_CONNECT_ENABLED", False):
        return build_error_response(request, 400, _("OIDC provider is not enabled"))

    if not getattr(settings, "OID_CONNECT_PLUGIN", "") in get_idm_get_token_functions():
        return build_error_response(request, 500, _("OIDC provider is not configured correctly! Contact your administrator."))

    if not getattr(settings, "OID_CONNECT_PLUGIN", "") in get_idm_get_user_functions():
        return build_error_response(request, 500, _("OIDC provider is not configured correctly! Contact your administrator."))

    token_data_get_func = get_idm_get_token_functions()[getattr(settings, "OID_CONNECT_PLUGIN", "")]
    user_get_func = get_idm_get_user_functions()[getattr(settings, "OID_CONNECT_PLUGIN", "")]

    login_context = await consume_login_attempt(request, db)

    redirect_uri = get_absolute_reverse_url('oidc_login_callback', request)

    try:
        if asyncio.iscoroutinefunction(token_data_get_func):
            # If the function is a coroutine, we need to await it
            token_data = await token_data_get_func(code=code, refresh_token=None, redirect_uri=redirect_uri,
                **({"login_context": login_context} if accepts_context(token_data_get_func) else {}))
        else:
            # If the function is a regular function, we can call it directly
            token_data = token_data_get_func(code=code, refresh_token=None, redirect_uri=redirect_uri,
                **({"login_context": login_context} if accepts_context(token_data_get_func) else {}))

        if asyncio.iscoroutinefunction(user_get_func):
            # If the function is a coroutine, we need to await it
            user_data = await user_get_func(token_data=token_data)
        else:
            # If the function is a regular function, we can call it directly
            user_data = user_get_func(token_data=token_data)
    except Exception as e:
        return build_error_response(request, 502, str(e))

    username = user_data["preferred_username"]

    user: User = await get_user_by_username(db, username)
    if user is not None and not user.is_active:
        return build_error_response(request, 401, _("Invalid user"))

    idm_data = {}
    if "refresh_token" in token_data:
        idm_data = {f"{getattr(settings, 'OID_CONNECT_PLUGIN')}": {"idm_token": token_data["refresh_token"]}}
    if 'session_state' in token_data:
        if getattr(settings, 'OID_CONNECT_PLUGIN') not in idm_data:
            idm_data = {f"{getattr(settings, 'OID_CONNECT_PLUGIN')}": {}}
        idm_data[getattr(settings, 'OID_CONNECT_PLUGIN')]['idm_session'] = token_data['session_state']
    if 'sub' in user_data:
        if getattr(settings, 'OID_CONNECT_PLUGIN') not in idm_data:
            idm_data = {f"{getattr(settings, 'OID_CONNECT_PLUGIN')}": {}}
        idm_data[getattr(settings, 'OID_CONNECT_PLUGIN')]['idm_user'] = user_data['sub']

    if user is None:
        # Register user
        await create_user_db(db, UserCreate(
            username=username,
            password="x",
            first_name=user_data.get("given_name", ""),
            last_name=user_data.get("family_name", ""),
            email=user_data.get("email", ""),
            is_superuser=False,
            is_staff=False,
            is_active=True,
            idm_data=idm_data
        ))

        await commit(db)

        user = await get_user_by_username(db, username)
    else:
        user.email = user_data.get("email", user.email)
        user.first_name = user_data.get("given_name", user.first_name)
        user.last_name = user_data.get("family_name", user.last_name)
        user.idm_data = idm_data

        await update_user(db, user)

    if getattr(settings, "OID_CONNECT_FULLY_SYNC_GROUPS", False):
        await remove_user_from_all_groups(db, user.id)

    if 'wirecloud' in user_data and isinstance(user_data['wirecloud'], dict) and 'groups' in user_data['wirecloud']:
        # Check that groups are a list of strings
        if isinstance(user_data['wirecloud']['groups'], list) and all(isinstance(group, str) for group in user_data['wirecloud']['groups']):
            for group in user_data['wirecloud']['groups']:
                group_id = Id()
                await create_group_if_not_exists(db, Group(_id=group_id, name=group, codename=group, path=[group_id]))
            await add_user_to_groups_by_codename(db, user.id, user_data['wirecloud']['groups'])

    await set_login_date_for_user(db, user.id)

    duration = (hasattr(settings, 'SESSION_AGE') and settings.SESSION_AGE) or 14 * 24 * 60 * 60  # 2 weeks
    expiration = datetime.fromtimestamp(int(datetime.now(timezone.utc).timestamp() + duration), tz=timezone.utc)

    token_id = str(await create_token(db, expiration, user.id, token_data.get('session_state', None)))
    await commit(db)

    token_contents = {
        "sub": str(user.id),
        "iss": "Wirecloud",
        "jti": token_id,
        "exp": int(expiration.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "csrf_required": True
    }
    token = jwt.encode(token_contents, settings.JWT_KEY, algorithm="HS256")

    csrf_token_contents = {
        "sub": "csrf",
        "iss": "Wirecloud",
        "jti": token_id,
        "exp": int(expiration.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp())
    }
    csrf_token = jwt.encode(csrf_token_contents, settings.JWT_KEY, algorithm="HS256")

    response = get_redirect_response(request)
    response.set_cookie(key="token", value=token, httponly=True, secure=getattr(settings, "WIRECLOUD_HTTPS", False), samesite="strict", expires=expiration)
    response.set_cookie(key="csrf_token", value=csrf_token, httponly=False, secure=getattr(settings, "WIRECLOUD_HTTPS", False), samesite="strict", expires=expiration)
    response.set_cookie(key="token_expiration", value=str(int(expiration.timestamp())), httponly=False,
                        secure=getattr(settings, "WIRECLOUD_HTTPS", False), samesite="lax", expires=expiration)

    return response


@router.post(
    "/login",
    summary=docs.api_login_summary,
    description=docs.api_login_description,
    response_model=UserToken,
    response_description=docs.api_login_response_model_description,
    responses={
        200: {"content": {"application/json": {"example": docs.api_login_response_model_example}}},
        401: root_docs.generate_error_response_openapi_description(
            docs.api_login_unauthorized_response_description,
            "Invalid username or password"),
        406: root_docs.generate_not_acceptable_response_openapi_description(
            docs.api_login_not_acceptable_response_description,
            ["application/json", "application/x-www-form-urlencoded", "multipart/form-data"]),
        415: root_docs.generate_unsupported_media_type_response_openapi_description(
            docs.api_login_unsupported_media_type_response_description),
        422: root_docs.generate_validation_error_response_openapi_description(
            docs.api_login_validation_error_response_descrition)
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "description": docs.login_credentials_description,
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/UserLogin"},
                    "example": docs.login_credentials_example,
                },
                "application/x-www-form-urlencoded": {
                    "schema": {"$ref": "#/components/schemas/UserLogin"},
                    "example": docs.login_credentials_example,
                },
                "multipart/form-data": {"schema": {"$ref": "#/components/schemas/UserLogin"}},
            }
        }
    }
)
@produces(["application/json"])
@consumes(["application/json", "application/x-www-form-urlencoded", "multipart/form-data"])
async def api_login(request: Request, db: DBDep):
    try:
        if request.state.mimetype == "application/x-www-form-urlencoded" or request.state.mimetype == "multipart/form-data":
            login_data = UserLogin.model_validate(await request.form(max_files=0, max_fields=50))
        else:
            login_data = UserLogin.model_validate_json(await request.body())
    except (ValueError, ValidationError):
        return build_validation_error_response(request)

    user: UserWithPassword = await get_user_with_password(db, login_data.username)
    if user is None or not user.is_active or not check_password(login_data.password, user.password):
        return build_error_response(request, 401, _("Invalid username or password"))

    await set_login_date_for_user(db, user.id)

    duration = (hasattr(settings, 'SESSION_AGE') and settings.SESSION_AGE) or 14 * 24 * 60 * 60  # 2 weeks
    expiration = datetime.fromtimestamp(int(datetime.now(timezone.utc).timestamp() + duration), tz=timezone.utc)

    token_id = str(await create_token(db, expiration, user.id))
    await commit(db)

    token_contents = {
        "sub": str(user.id),
        "iss": "Wirecloud",
        "jti": token_id,
        "exp": int(expiration.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "csrf_required": False
    }
    token = jwt.encode(token_contents, settings.JWT_KEY, algorithm="HS256")
    return UserToken(access_token=token, token_type=UserTokenType.bearer)


@base_router.get(
    "/login",
    summary=docs.login_page_summary,
    description=docs.login_page_description,
    response_class=HTMLResponse,
    response_description=docs.login_page_response_description,
    openapi_extra={"parameters": [
        {"name": "return_to", "in": "query", "required": False,
         "description": docs.login_return_to_description, "schema": {"type": "string"}},
        {"name": "state", "in": "query", "required": False,
         "description": docs.login_state_description, "schema": {"type": "string"}},
    ]},
)
async def login_page(request: Request):
    return render_wirecloud(request, page="registration/login", title="Login", extra_context={"form": {"errors": False}})


@base_router.post(
    "/login",
    summary=docs.login_summary,
    description=docs.login_description,
    response_class=HTMLResponse,
    response_description=docs.login_response_description,
    responses={
        200: {"description": docs.login_invalid_credentials_response_description},
        302: {
            "description": docs.login_response_description,
            "headers": {
                "Location": {"description": docs.login_redirect_location_description, "schema": {"type": "string"}},
                "Set-Cookie": {"description": docs.login_session_cookie_description, "schema": {"type": "string"}},
            },
        },
        400: {
            "description": docs.login_bad_request_response_description,
            "content": {"application/json": {
                "schema": docs.login_http_error_schema, "example": docs.begin_login_bad_request_response_example,
            }},
        },
        415: root_docs.generate_unsupported_media_type_response_openapi_description(
            docs.login_unsupported_media_type_response_description),
        422: root_docs.generate_validation_error_response_openapi_description(
            docs.login_validation_error_response_description)
    },
    openapi_extra={
        "parameters": [
            {"name": "return_to", "in": "query", "required": False,
             "description": docs.login_return_to_description, "schema": {"type": "string"}},
            {"name": "state", "in": "query", "required": False,
             "description": docs.login_state_description, "schema": {"type": "string"}},
        ],
        "requestBody": {
            "required": True,
            "description": docs.login_credentials_description,
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/UserLogin"},
                    "example": docs.login_credentials_example,
                },
                "application/x-www-form-urlencoded": {
                    "schema": {"$ref": "#/components/schemas/UserLogin"},
                    "example": docs.login_credentials_example,
                },
                "multipart/form-data": {"schema": {"$ref": "#/components/schemas/UserLogin"}},
            }
        }
    }
)
@consumes(["application/json", "application/x-www-form-urlencoded", "multipart/form-data"])
async def login(request: Request, db: DBDep):
    if "return_to" in request.query_params:
        request.state.login_return_to = validate_login_return_to(request.query_params["return_to"])
    try:
        if request.state.mimetype == "application/x-www-form-urlencoded" or request.state.mimetype == "multipart/form-data":
            login_data = UserLogin.model_validate(await request.form(max_files=0, max_fields=50))
        else:
            login_data = UserLogin.model_validate_json(await request.body())
    except (ValueError, ValidationError):
        return build_validation_error_response(request)

    user: UserWithPassword = await get_user_with_password(db, login_data.username)
    if user is None or not user.is_active or not check_password(login_data.password, user.password):
        return render_wirecloud(request, page="registration/login", title="Login", extra_context={"form": {"errors": True}})

    await set_login_date_for_user(db, user.id)
    if getattr(settings, 'OID_CONNECT_PLUGIN', None) is not None:
        await remove_user_idm_data(db, user.id, getattr(settings, 'OID_CONNECT_PLUGIN'))

    duration = (hasattr(settings, 'SESSION_AGE') and settings.SESSION_AGE) or 14 * 24 * 60 * 60  # 2 weeks
    expiration = datetime.fromtimestamp(int(datetime.now(timezone.utc).timestamp() + duration), tz=timezone.utc)

    token_id = str(await create_token(db, expiration, user.id))
    await commit(db)

    token_contents = {
        "sub": str(user.id),
        "iss": "Wirecloud",
        "jti": token_id,
        "exp": int(expiration.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "csrf_required": True
    }

    token = jwt.encode(token_contents, settings.JWT_KEY, algorithm="HS256")

    csrf_token_contents = {
        "sub": "csrf",
        "iss": "Wirecloud",
        "jti": token_id,
        "exp": int(expiration.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp())
    }

    csrf_token = jwt.encode(csrf_token_contents, settings.JWT_KEY, algorithm="HS256")

    response = get_redirect_response(request)
    response.set_cookie(key="token", value=token, httponly=True, secure=getattr(settings, "WIRECLOUD_HTTPS", False), samesite="strict", expires=expiration)
    response.set_cookie(key="csrf_token", value=csrf_token, httponly=False, secure=getattr(settings, "WIRECLOUD_HTTPS", False), samesite="strict", expires=expiration)
    response.set_cookie(key="token_expiration", value=str(int(expiration.timestamp())), httponly=False,
                        secure=getattr(settings, "WIRECLOUD_HTTPS", False), samesite="lax", expires=expiration)

    return response


@base_router.get(
    "/logout",
    summary=docs.logout_summary,
    description=docs.logout_description,
    response_class=Response,
    status_code=302,
    response_description=docs.logout_response_description,
    responses={
        302: {"headers": {
            "Location": {"description": docs.login_redirect_location_description, "schema": {"type": "string"}},
            "Set-Cookie": {"description": docs.logout_cookie_description, "schema": {"type": "string"}},
        }},
        401: root_docs.generate_error_response_openapi_description(
            docs.logout_unauthorized_response_description, "You are not logged in"),
    },
    openapi_extra={"parameters": [
        {"name": "state", "in": "query", "required": False,
         "description": docs.login_state_description, "schema": {"type": "string"}},
    ]},
)
async def logout(request: Request, db: DBDep, session: SessionDepNoCSRF, user: UserDepNoCSRF):
    if not session:
        return build_error_response(request, 401, _("You are not logged in"))

    await invalidate_token(db, session.id)
    await commit(db)

    if getattr(settings, "OID_CONNECT_ENABLED", False) and \
            getattr(settings, "OID_CONNECT_PLUGIN", "") in get_idm_backchannel_logout_functions() and \
            user.idm_data[getattr(settings, "OID_CONNECT_PLUGIN")] is not None:
        backchannel_logout_func = get_idm_backchannel_logout_functions()[getattr(settings, "OID_CONNECT_PLUGIN", "")]
        try:
            if asyncio.iscoroutinefunction(backchannel_logout_func):
                # If the function is a coroutine, we need to await it
                await backchannel_logout_func(refresh_token=user.idm_data[getattr(settings, "OID_CONNECT_PLUGIN")]["idm_token"])
            else:
                # If the function is a regular function, we can call it directly
                backchannel_logout_func(refresh_token=user.idm_data[getattr(settings, "OID_CONNECT_PLUGIN")]["idm_token"])
        except Exception as e:
            pass

    response = get_redirect_response(request)

    # Remove cookies
    response.set_cookie(key="token", value="", httponly=True, secure=getattr(settings, "WIRECLOUD_HTTPS", False), samesite="strict", expires=0)
    response.set_cookie(key="csrf_token", value="", httponly=False, secure=getattr(settings, "WIRECLOUD_HTTPS", False), samesite="strict", expires=0)
    response.set_cookie(key="token_expiration", value="", httponly=False, secure=getattr(settings, "WIRECLOUD_HTTPS", False), samesite="lax", expires=0)

    return response


@router.get(
    "/refresh",
    summary=docs.token_refresh_summary,
    description=docs.token_refresh_description,
    response_model=UserToken,
    response_description=docs.token_refresh_response_model_description,
    responses={
        200: {"content": {"application/json": {"example": docs.token_refresh_response_model_example}}},
        401: root_docs.generate_error_response_openapi_description(
            docs.token_refresh_unauthorized_response_description,
            "You are not logged in"),
        500: root_docs.generate_error_response_openapi_description(
            docs.token_refresh_configuration_error_response_description,
            "OIDC provider is not configured correctly! Contact your administrator."),
        502: root_docs.generate_error_response_openapi_description(
            docs.token_refresh_provider_error_response_description, "Identity provider request failed"),
    }
)
async def token_refresh(request: Request, db: DBDep, session: SessionDep, user: UserDep):
    if not session or not session.oidc_token:
        return build_error_response(request, 401, _("You are not logged in"))

    if getattr(settings, "OID_CONNECT_ENABLED", False):
        if not getattr(settings, "OID_CONNECT_PLUGIN", "") in get_idm_get_token_functions():
            return build_error_response(request, 500, _("OIDC provider is not configured correctly! Contact your administrator."))

        token_data = None
        if user.idm_data[getattr(settings, "OID_CONNECT_PLUGIN")] is not None:
            try:
                token_data_get_func = get_idm_get_token_functions()[getattr(settings, "OID_CONNECT_PLUGIN", "")]
                if asyncio.iscoroutinefunction(token_data_get_func):
                    # If the function is a coroutine, we need to await it
                    token_data = await token_data_get_func(code=None, refresh_token=user.idm_data[getattr(settings, "OID_CONNECT_PLUGIN")]["idm_token"])
                else:
                    # If the function is a regular function, we can call it directly
                    token_data = token_data_get_func(code=None, refresh_token=user.idm_data[getattr(settings, "OID_CONNECT_PLUGIN")]["idm_token"])
            except Exception as e:
                return build_error_response(request, 502, str(e))

        user.idm_data[getattr(settings, "OID_CONNECT_PLUGIN")]["idm_token"] = token_data["refresh_token"] if "refresh_token" in token_data else None
        await update_user(db, user)

    duration = (hasattr(settings, 'SESSION_AGE') and settings.SESSION_AGE) or 14 * 24 * 60 * 60  # 2 weeks
    expiration = datetime.fromtimestamp(int(datetime.now(timezone.utc).timestamp() + duration), tz=timezone.utc)

    await set_token_expiration(db, session.id, expiration)
    await commit(db)

    token_contents = {
        "sub": str(user.id),
        "iss": "Wirecloud",
        "jti": str(session.id),
        "exp": int(expiration.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "csrf_required": session.requires_csrf
    }

    if "real_user" in session.token_data:
        token_contents["real_user"] = session.token_data["real_user"]

    token = jwt.encode(token_contents, settings.JWT_KEY, algorithm="HS256")

    response = Response(status_code=200, content=UserToken(access_token=token, token_type=UserTokenType.bearer).model_dump_json())
    response.set_cookie(key="token", value=token, httponly=True, secure=getattr(settings, "WIRECLOUD_HTTPS", False),
                        samesite="strict", expires=expiration)
    response.set_cookie(key="token_expiration", value=str(int(expiration.timestamp())), httponly=False,
                        secure=getattr(settings, "WIRECLOUD_HTTPS", False), samesite="lax", expires=expiration)

    if session.requires_csrf:
        # If CSRF is required, we need to create a CSRF token
        csrf_token_contents = {
            "sub": "csrf",
            "iss": "Wirecloud",
            "jti": str(session.id),
            "exp": int(expiration.timestamp()),
            "iat": int(datetime.now(timezone.utc).timestamp())
        }
        csrf_token = jwt.encode(csrf_token_contents, settings.JWT_KEY, algorithm="HS256")

        response.set_cookie(key="csrf_token", value=csrf_token, httponly=False,
                            secure=getattr(settings, "WIRECLOUD_HTTPS", False), samesite="strict", expires=expiration)

    return response


@admin_router.post(
    "/switchuser",
    summary=docs.switch_user_summary,
    description=docs.switch_user_description,
    response_class=Response,
    status_code=204,
    responses={
        204: {"description": docs.switch_user_no_content_response_description},
        401: root_docs.generate_error_response_openapi_description(
            docs.switch_user_unauthorized_response_description,
            "You are not logged in"),
        403: root_docs.generate_error_response_openapi_description(
            docs.switch_user_forbidden_response_description,
            "You do not have permission to switch users"),
        404: root_docs.generate_error_response_openapi_description(
            docs.switch_user_not_found_response_description,
            "Target user not found")
    }
)
async def switch_user(request: Request, db: DBDep, real_user: RealUserDep, actual_user: UserDep, switch_data: SwitchUserRequest, session: SessionDep):
    if real_user is None or actual_user is None:
        return build_error_response(request, 401, _("You are not logged in"))

    if not real_user.has_perm("SWITCH_USER") and not real_user.is_superuser:
        return build_error_response(request, 403, _("You do not have permission to switch users"))

    target_user = await get_user_with_all_info_by_username(db, switch_data.username)

    if not target_user or not target_user.is_active:
        return build_error_response(request, 404, _("Target user not found"))

    if target_user.id == actual_user.id:
        return Response(status_code=204)

    location = None
    referer = request.headers.get("Referer")
    if referer is not None:
        parsed_referrer = urlparse(referer)
        if request.url.hostname == '' or parsed_referrer.hostname == request.url.hostname:
            location = parsed_referrer.path

            referer_view_info = resolve_url_name(parsed_referrer.path)
            if referer_view_info is not None and referer_view_info[0] == "wirecloud.workspace_view":
                workspace_info = await get_workspace_by_username_and_name(db, referer_view_info[1]['owner'], referer_view_info[1]['name'])
                if workspace_info is not None and not await workspace_info.is_accessible_by(db, target_user):
                    location = None

    response = Response(status_code=204)
    if location is not None:
        response.headers["Location"] = location

    duration = (hasattr(settings, 'SESSION_AGE') and settings.SESSION_AGE) or 14 * 24 * 60 * 60  # 2 weeks
    expiration = datetime.fromtimestamp(int(datetime.now(timezone.utc).timestamp() + duration), tz=timezone.utc)

    token_id = str(await create_token(db, expiration, real_user.id, await get_token_idm_session(db, session.id)))
    await commit(db)

    token_contents = {
        "sub": str(target_user.id),
        "iss": "Wirecloud",
        "jti": token_id,
        "exp": int(expiration.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "csrf_required": session.requires_csrf,
        "real_user": {
            "id": str(real_user.id),
            "username": real_user.username,
            "fullname": real_user.get_full_name()
        }
    }

    if target_user.id == real_user.id:
        del token_contents["real_user"]

    token = jwt.encode(token_contents, settings.JWT_KEY, algorithm="HS256")

    response.set_cookie(key="token", value=token, httponly=True, secure=getattr(settings, "WIRECLOUD_HTTPS", False),
                        samesite="strict", expires=expiration)
    response.set_cookie(key="token_expiration", value=str(int(expiration.timestamp())), httponly=False,
                        secure=getattr(settings, "WIRECLOUD_HTTPS", False), samesite="lax", expires=expiration)

    if session.requires_csrf:
        # If CSRF is required, we need to create a CSRF token
        csrf_token_contents = {
            "sub": "csrf",
            "iss": "Wirecloud",
            "jti": token_id,
            "exp": int(expiration.timestamp()),
            "iat": int(datetime.now(timezone.utc).timestamp())
        }
        csrf_token = jwt.encode(csrf_token_contents, settings.JWT_KEY, algorithm="HS256")

        response.set_cookie(key="csrf_token", value=csrf_token, httponly=False,
                            secure=getattr(settings, "WIRECLOUD_HTTPS", False), samesite="strict", expires=expiration)

    return response


@admin_router.post(
    "/users",
    summary=docs.create_user_collection_summary,
    description=docs.create_user_collection_description,
    status_code=201,
    response_class=Response,
    response_description=docs.create_user_collection_response_description,
    responses={
        400: root_docs.generate_error_response_openapi_description(
            docs.create_user_collection_bad_request_response_description,
            "Malformed JSON data"
        ),
        401: root_docs.generate_auth_required_response_openapi_description(
            docs.create_user_collection_auth_required_response_description
        ),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.create_user_collection_permission_denied_response_description,
            "You don't have permissions to create users"
        ),
        406: root_docs.generate_not_acceptable_response_openapi_description(
            docs.create_user_collection_not_acceptable_response_description, ["application/json"]
        ),
        409: root_docs.generate_error_response_openapi_description(
            docs.create_user_collection_conflict_response_description,
            "A user with the given username already exists"
        )
    }
)
@authentication_required()
@consumes(["application/json"])
async def create_user(db: DBDep, request: Request, user: UserDep,
                      user_data: UserCreate = Body(description=docs.create_user_collection_user_data_description,
                                                   examples=docs.create_user_collection_user_data_example)):
    if not user.is_superuser and not user.has_perm("USER.CREATE"):
        return build_error_response(request, 403, _("You don't have permissions to create users"))

    if user_data.username == "" or user_data.username is None:
        return build_error_response(request, 400, _("Username cannot be empty"))

    if await get_user_by_username(db, user_data.username) is not None:
        return build_error_response(request, 409, _("A user with that username already exists"))

    user_data.password = hash_password(user_data.password)
    user = await create_user_db(db, user_data)
    await add_user_to_index(User(**user.model_dump(by_alias=False)))

    return Response(status_code=201)


@admin_router.get(
    "/users/{username}",
    summary=docs.get_user_entry_summary,
    description=docs.get_user_entry_description,
    response_model=UserUpdate,
    response_description=docs.get_user_entry_response_description,
    responses={
        200: {"content": {"application/json": {"example": docs.get_user_entry_response_example}}},
        401: root_docs.generate_auth_required_response_openapi_description(
            docs.get_user_entry_auth_required_response_description
        ),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.get_user_entry_permission_denied_response_description,
            "You don't have permissions to view users"
        ),
        404: root_docs.generate_not_found_response_openapi_description(
            docs.get_user_entry_not_found_response_description
        )
    }
)
@authentication_required()
async def get_user_entry(db: DBDep, request: Request, user: UserDep,
                         username: str = Path(description=docs.get_user_entry_username_description)):
    if not user.is_superuser and not user.has_perm("USER.VIEW"):
        return build_error_response(request, 403, _("You don't have permissions to view users"))

    user_db = await get_user_with_all_info_by_username(db, username, only_user_permissions=True)
    if user_db is None:
        return build_error_response(request, 404, _("User not found"))

    return UserUpdate(
        username=user_db.username,
        email=user_db.email,
        first_name=user_db.first_name,
        last_name=user_db.last_name,
        is_staff=user_db.is_staff,
        is_active=user_db.is_active,
        is_superuser=user_db.is_superuser,
        permissions=[perm.codename for perm in user_db.permissions]
    )


@admin_router.put(
    "/users/{username}",
    summary=docs.update_user_entry_summary,
    description=docs.update_user_entry_description,
    status_code=204,
    response_class=Response,
    response_description=docs.update_user_entry_response_description,
    responses={
        400: root_docs.generate_error_response_openapi_description(
            docs.update_user_entry_bad_request_response_description,
            "Malformed JSON data"
        ),
        401: root_docs.generate_auth_required_response_openapi_description(
            docs.update_user_entry_auth_required_response_description
        ),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.update_user_entry_permission_denied_response_description,
            "You don't have permissions to edit users"
        ),
        404: root_docs.generate_not_found_response_openapi_description(
            docs.update_user_entry_not_found_response_description
        ),
        406: root_docs.generate_not_acceptable_response_openapi_description(
            docs.update_user_entry_not_acceptable_response_description, ["application/json"]
        ),
        409: root_docs.generate_error_response_openapi_description(
            docs.update_user_entry_conflict_response_description,
            "A user with the given username already exists"
        )
    }
)
@authentication_required()
@consumes(["application/json"])
async def update_user_entry(db: DBDep, request: Request, user: UserDep,
                            username: str = Path(description=docs.update_user_entry_username_description),
                            user_data: UserUpdate = Body(description=docs.update_user_entry_user_data_description,
                                                         examples=docs.update_user_entry_user_data_example)):
    if not user.is_superuser and not user.has_perm("USER.EDIT"):
        return build_error_response(request, 403, _("You don't have permissions to edit users"))

    user_db = await get_user_with_all_info_by_username(db, username, only_user_permissions=True)
    if user_db is None:
        return build_error_response(request, 404, _("User not found"))

    if user_data.username == "" or user_data.username is None:
        return build_error_response(request, 400, _("Username cannot be empty"))

    if user_data.username != user_db.username:
        if await get_user_by_username(db, user_data.username) is not None:
            return build_error_response(request, 409, _("A user with that username already exists"))
        user_db.username = user_data.username

    if user_data.permissions is not None:
        user_db.permissions = [Permission(codename=perm) for perm in user_data.permissions]

    user_db.email = user_data.email
    user_db.first_name = user_data.first_name
    user_db.last_name = user_data.last_name
    user_db.is_staff = user_data.is_staff
    user_db.is_active = user_data.is_active
    user_db.is_superuser = user_data.is_superuser

    await update_user_with_all_info(db, user_db)

    return Response(status_code=204)


@admin_router.delete(
    "/users/{username}",
    summary=docs.delete_user_entry_summary,
    description=docs.delete_user_entry_description,
    status_code=204,
    response_class=Response,
    response_description=docs.delete_user_entry_response_description,
    responses={
        401: root_docs.generate_auth_required_response_openapi_description(
            docs.delete_user_entry_auth_required_response_description
        ),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.delete_user_entry_permission_denied_response_description,
            "You don't have permissions to delete users"
        ),
        404: root_docs.generate_not_found_response_openapi_description(
            docs.delete_user_entry_not_found_response_description
        )
    }
)
@authentication_required()
async def delete_user_entry(db: DBDep, request: Request, user: UserDep,
                            username: str = Path(description=docs.delete_user_entry_username_description)):
    if not user.is_superuser and not user.has_perm("USER.DELETE"):
        return build_error_response(request, 403, _("You don't have permissions to delete users"))

    user_db = await get_user_by_username(db, username)
    if user_db is None:
        return build_error_response(request, 404, _("User not found"))

    await delete_user(db, user_db)

    return Response(status_code=204)


@admin_router.post(
    "/groups",
    summary=docs.create_group_collection_summary,
    description=docs.create_group_collection_description,
    status_code=201,
    response_class=Response,
    response_description=docs.create_group_collection_response_description,
    responses={
        400: root_docs.generate_error_response_openapi_description(
            docs.create_group_collection_bad_request_response_description,
            "Malformed JSON data"
        ),
        401: root_docs.generate_auth_required_response_openapi_description(
            docs.create_group_collection_auth_required_response_description
        ),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.create_group_collection_permission_denied_response_description,
            "You don't have permissions to create groups"
        ),
        406: root_docs.generate_not_acceptable_response_openapi_description(
            docs.create_group_collection_not_acceptable_response_description, ["application/json"]
        ),
        409: root_docs.generate_error_response_openapi_description(
            docs.create_group_collection_conflict_response_description,
            "A group with the given name already exists"
        )
     }
)
@authentication_required()
@consumes(["application/json"])
async def create_group(db: DBDep, request: Request, user: UserDep,
                       group_data: GroupCreate = Body(description=docs.create_group_collection_group_data_description,
                                                      examples=docs.create_group_collection_group_data_example)):
    if not user.is_superuser and not user.has_perm("GROUP.CREATE"):
        return build_error_response(request, 403, _("You don't have permissions to create groups"))

    if group_data.name == "" or group_data.codename == "":
        return build_error_response(request, 400, _("Group name and codename cannot be empty"))

    if await get_group_by_name(db, group_data.name) is not None:
        return build_error_response(request, 409, _("A group with that name already exists"))

    for user_id in group_data.users:
        if await get_user_by_id(db, user_id) is None:
            return build_error_response(request, 404, _(f"User with id {user_id} does not exist"))

    group = await create_group_db(db, group_data)

    if len(group_data.users) > 0:
        await add_group_to_users(db, group.id, group_data.users)

    await add_group_to_index(group)

    return Response(status_code=201)


@admin_router.get(
    "/groups/{name}",
    summary=docs.get_group_entry_summary,
    description=docs.get_group_entry_description,
    response_model=GroupUpdate,
    response_description=docs.get_group_entry_response_description,
    responses={
        200: {"content": {"application/json": {"example": docs.get_group_entry_response_example}}},
        401: root_docs.generate_auth_required_response_openapi_description(
            docs.get_group_entry_auth_required_response_description
        ),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.get_group_entry_permission_denied_response_description,
            "You don't have permissions to view groups"
        ),
        404: root_docs.generate_not_found_response_openapi_description(
            docs.get_group_entry_not_found_response_description
        )
     }
)
@authentication_required()
async def get_group_entry(db: DBDep, request: Request, user: UserDep,
                          name: str = Path(description=docs.get_group_entry_name_description)):
    if not user.is_superuser and not user.has_perm("GROUP.VIEW"):
        return build_error_response(request, 403, _("You don't have permissions to view groups"))

    group_db = await get_group_by_name(db, name)
    if group_db is None:
        return build_error_response(request, 404, _("Group not found"))

    data = GroupUpdate(
        name=group_db.name,
        codename=group_db.codename,
        permissions=[perm.codename for perm in group_db.group_permissions],
        users=group_db.users,
    )

    return data


@admin_router.put(
    "/groups/{name}",
    summary=docs.update_group_entry_summary,
    description=docs.update_group_entry_description,
    status_code=204,
    response_class=Response,
    response_description=docs.update_group_entry_response_description,
    responses={
        400: root_docs.generate_error_response_openapi_description(
            docs.update_group_entry_bad_request_response_description,
            "Malformed JSON data"
        ),
        401: root_docs.generate_auth_required_response_openapi_description(
            docs.update_group_entry_auth_required_response_description
        ),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.update_group_entry_permission_denied_response_description,
            "You don't have permissions to edit groups"
        ),
        404: root_docs.generate_not_found_response_openapi_description(
            docs.update_group_entry_not_found_response_description
        ),
        406: root_docs.generate_not_acceptable_response_openapi_description(
            docs.update_group_entry_not_acceptable_response_description, ["application/json"]
        ),
        409: root_docs.generate_error_response_openapi_description(
            docs.update_group_entry_conflict_response_description,
            "A group with the given name already exists"
        )
     }
)
@authentication_required()
@consumes(["application/json"])
async def update_group_entry(db: DBDep, request: Request, user: UserDep,
                             name: str = Path(description=docs.update_group_entry_name_description),
                             group_data: GroupUpdate = Body(description=docs.update_group_entry_group_data_description,
                                                            examples=docs.update_group_entry_group_data_example)):
    if not user.is_superuser and not user.has_perm("GROUP.EDIT"):
        return build_error_response(request, 403, _("You don't have permissions to edit groups"))

    if group_data.name == "" or group_data.codename == "":
        return build_error_response(request, 400, _("Group name and codename cannot be empty"))

    group_db = await get_group_by_name(db, name)
    if group_db is None:
        return build_error_response(request, 404, _("Group not found"))

    if group_db.name != group_data.name:
        if await get_group_by_name(db, group_data.name) is not None:
            return build_error_response(request, 409, _("A group with that name already exists"))
        group_db.name = group_data.name

    if group_data.permissions is not None:
        group_db.group_permissions = [Permission(codename=perm) for perm in group_data.permissions]

    users_to_add = set(group_data.users) - set(group_db.users)
    users_to_remove = set(group_db.users) - set(group_data.users)

    if len(users_to_add) > 0:
        await add_group_to_users(db, group_db.id, list(users_to_add))
    if len(users_to_remove) > 0:
        await remove_group_to_users(db, group_db.id, list(users_to_remove))

    group_db.users = group_data.users
    group_db.codename = group_data.codename

    await update_group(db, group_db)
    return Response(status_code=204)


@admin_router.delete(
    "/groups/{name}",
    summary=docs.delete_group_entry_summary,
    description=docs.delete_group_entry_description,
    status_code=204,
    response_class=Response,
    response_description=docs.delete_group_entry_response_description,
    responses={
        401: root_docs.generate_auth_required_response_openapi_description(
            docs.delete_group_entry_auth_required_response_description
        ),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.delete_group_entry_permission_denied_response_description,
            "You don't have permissions to delete groups"
        ),
        404: root_docs.generate_not_found_response_openapi_description(
            docs.delete_group_entry_not_found_response_description
        )
    }
)
@authentication_required()
async def delete_group_entry(db: DBDep, request: Request, user: UserDep,
                             name: str = Path(description=docs.delete_group_entry_name_description)):
    if not user.is_superuser and not user.has_perm("GROUP.DELETE"):
        return build_error_response(request, 403, _("You don't have permissions to delete groups"))

    group_db = await get_group_by_name(db, name)
    if group_db is None:
        return build_error_response(request, 404, _("Group not found"))

    if group_db.is_organization and group_db.parent is None:
        return build_error_response(request, 400, _("You cannot delete the root group of an organization"))

    await delete_group(db, group_db)

    return Response(status_code=204)


@admin_router.post(
    "/organizations",
    summary=docs.create_organization_collection_summary,
    description=docs.create_organization_collection_description,
    status_code=201,
    response_class=Response,
    response_description=docs.create_organization_collection_response_description,
    responses={
        400: root_docs.generate_error_response_openapi_description(
            docs.create_organization_collection_bad_request_response_description,
            "Malformed JSON data"
        ),
        401: root_docs.generate_auth_required_response_openapi_description(
            docs.create_organization_collection_auth_required_response_description
        ),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.create_organization_collection_permission_denied_response_description,
            "You don't have permissions to create organizations"
        ),
        406: root_docs.generate_not_acceptable_response_openapi_description(
            docs.create_organization_collection_not_acceptable_response_description, ["application/json"]
        ),
        409: root_docs.generate_error_response_openapi_description(
            docs.create_organization_collection_conflict_response_description,
            "A group with the given name already exists"
        )
    }
)
@authentication_required()
@consumes(["application/json"])
async def create_organization(db: DBDep, request: Request, user: UserDep,
                              org_data: OrganizationCreate = Body(description=docs.create_organization_collection_organization_data_description,
                                                                  examples=docs.create_organization_collection_organization_data_example)):
    if not user.is_superuser and not user.has_perm("ORGANIZATION.CREATE"):
        return build_error_response(request, 403, _("You don't have permissions to create organizations"))

    if org_data.name == "" or org_data.codename == "":
        return build_error_response(request, 400, _("Organization name and codename cannot be empty"))

    if await get_group_by_name(db, org_data.name) is not None:
        return build_error_response(request, 409, _("A group with that name already exists"))

    org = await create_organization_db(db, org_data)

    if len(org_data.users) > 0:
        await add_group_to_users(db, org.id, org_data.users)
    await add_group_to_index(org)

    return Response(status_code=201)


@admin_router.get(
    "/organizations/{name}",
    summary=docs.get_organization_entry_summary,
    description=docs.get_organization_entry_description,
    response_model=list[OrganizationGroupData],
    response_description=docs.get_organization_entry_response_description,
    responses={
        200: {"content": {"application/json": {"example": docs.get_organization_entry_response_example}}},
        401: root_docs.generate_auth_required_response_openapi_description(
            docs.get_organization_entry_auth_required_response_description
        ),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.get_organization_entry_permission_denied_response_description,
            "You don't have permissions to view organizations"
        ),
        404: root_docs.generate_not_found_response_openapi_description(
            docs.get_organization_entry_not_found_response_description
        )
     }
)
@authentication_required()
async def get_organization_entry(db: DBDep, request: Request, user: UserDep,
                                 name: str = Path(description=docs.get_organization_entry_name_description)):
    if not user.is_superuser and not user.has_perm("ORGANIZATION.VIEW"):
        return build_error_response(request, 403, _("You don't have permissions to view organizations"))

    org_db = await get_group_by_name(db, name)
    if org_db is None or not org_db.is_organization or org_db.parent is not None:
        return build_error_response(request, 404, _("Organization not found"))

    groups = await get_all_organization_groups(db, org_db)
    data = [OrganizationGroupData(name=group.name,
                        codename=group.codename,
                        users=group.users,
                        path=group.path) for group in groups]

    return data


@admin_router.put(
    "/organizations/groups/{name}",
    summary=docs.update_organization_group_entry_summary,
    description=docs.update_organization_group_entry_description,
    status_code=204,
    response_class=Response,
    response_description=docs.update_organization_group_entry_response_description,
    responses={
        400: root_docs.generate_error_response_openapi_description(
            docs.update_organization_group_entry_bad_request_response_description,
            "Malformed JSON data"
        ),
        401: root_docs.generate_auth_required_response_openapi_description(
            docs.update_organization_group_entry_auth_required_response_description
        ),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.update_organization_group_entry_permission_denied_response_description,
            "You don't have permissions to edit organizations"
        ),
        404: root_docs.generate_not_found_response_openapi_description(
            docs.update_organization_group_entry_not_found_response_description
        ),
        406: root_docs.generate_not_acceptable_response_openapi_description(
            docs.update_organization_group_entry_not_acceptable_response_description, ["application/json"]
        )
    }
)
@authentication_required()
@consumes(["application/json"])
async def update_organization_group_entry(db: DBDep, request: Request, user: UserDep,
                                          name: str = Path(description=docs.update_organization_group_entry_name_description),
                                          new_parent: OrganizationGroupUpdate = Body(description=docs.update_organization_group_entry_new_parent_description,
                                                                                     examples=docs.update_organization_group_entry_new_parent_example)):
    if not user.is_superuser and not user.has_perm("ORGANIZATION.EDIT"):
        return build_error_response(request, 403, _("You don't have permissions to update organizations"))

    child_group = await get_group_by_name(db, name)
    if child_group is None:
        return build_error_response(request, 404, _("Group not found"))

    if new_parent.parent_name == "":
        await update_path_for_descendants(db, child_group)
        child_group.path = [child_group.id]
        child_group.is_organization = False
    else:
        parent_group = await get_group_by_name(db, new_parent.parent_name)
        if parent_group is None:
            return build_error_response(request, 404, _("Parent group not found"))

        if not parent_group.is_organization:
            return build_error_response(request, 400, _("The specified parent group is not an organization"))

        # Check there is not a cycle in the group hierarchy
        if child_group.id in parent_group.path:
            return build_error_response(request, 400, _("Cannot set this parent: it would create a circular reference"))

        child_group.path = parent_group.path + [child_group.id]
        child_group.is_organization = True

    await update_group(db, child_group)
    return Response(status_code=204)


@admin_router.delete(
    "/organizations/{name}",
    summary=docs.delete_organization_entry_summary,
    description=docs.delete_organization_entry_description,
    status_code=204,
    response_class=Response,
    response_description=docs.delete_organization_entry_response_description,
    responses={
        401: root_docs.generate_auth_required_response_openapi_description(
            docs.delete_organization_entry_auth_required_response_description
        ),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.delete_organization_entry_permission_denied_response_description,
            "You don't have permissions to delete organizations"
        ),
        404: root_docs.generate_not_found_response_openapi_description(
            docs.delete_organization_entry_not_found_response_description
        )
    }
)
@authentication_required()
async def delete_organization_entry(db: DBDep, request: Request, user: UserDep,
                                    name: str = Path(description=docs.delete_organization_entry_name_description)):
    if not user.is_superuser and not user.has_perm("ORGANIZATION.DELETE"):
        return build_error_response(request, 403, _("You don't have permissions to delete organizations"))

    org_db = await get_group_by_name(db, name)
    if org_db is None:
        return build_error_response(request, 404, _("Organization not found"))
    if org_db.parent is not None or not org_db.is_organization:
        return build_error_response(request, 400, _("The specified group is not the root group of an organization"))

    await delete_organization(db, org_db)

    return Response(status_code=204)
