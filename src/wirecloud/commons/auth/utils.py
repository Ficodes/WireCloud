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

import aiohttp
import jwt
import secrets
import inspect
from urllib.parse import urlencode
from bson import ObjectId
from typing import Any, Callable, Union, Optional
from secrets import compare_digest
from hashlib import pbkdf2_hmac
from base64 import b64decode, b64encode
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from typing import Annotated
from wirecloud import settings
from wirecloud.database import DBDep, DBSession, Id, commit
from wirecloud.commons.auth import crud, tokens
from wirecloud.commons.auth.schemas import Session, UserAll
from wirecloud.commons.auth.crud import is_token_valid, get_user_with_all_info
from wirecloud.translation import gettext as _

SUPPORTED_HASHES = ['pbkdf2_sha256']


def accepts_context(function: Callable[..., Any]) -> bool:
    parameters = inspect.signature(function).parameters
    return "login_context" in parameters or any(p.kind == p.VAR_KEYWORD for p in parameters.values())


def validate_login_return_to(target: str) -> str:
    if not target.startswith("/") or target.startswith("//") or "\\" in target or any(ord(c) < 32 for c in target):
        raise HTTPException(400, "Invalid login return destination")
    return target


async def consume_login_attempt(request: Request, db: DBSession) -> dict[str, Any]:
    attempt = await crud.consume_login_attempt(
        db, tokens.digest(request.query_params.get("state", "")),
        tokens.digest(request.cookies.get("wc_login_browser", "")), tokens.now(),
    )
    if attempt is None:
        raise HTTPException(400, "Invalid or expired login state")
    await commit(db)
    request.state.login_return_to = validate_login_return_to(attempt.return_to)
    return attempt.model_dump(exclude={"id"})


login_scheme = OAuth2PasswordBearer(scheme_name="User authentication", tokenUrl="api/auth/login/", auto_error=False)

Token = Union[dict[str, Union[str, int, bool, dict[str, Union[str, int, bool, None]], None]], None]

async def get_token_contents(token: Annotated[str, Depends(login_scheme)], request: Request, db: DBDep, csrf: bool) -> Token:
    if token is None:
        token = request.query_params.get('token')
    if token is None:
        token = request.cookies.get('token')
    if token is None:
        return None

    try:
        token_contents = jwt.decode(
            token,
            settings.JWT_KEY,
            algorithms=["HS256"],
            issuer="Wirecloud",
            options={
                "require": ["exp", "sub", "iat", "iss"],
                "verify_exp": True,
                "verify_iss": True
            }
        )
    except Exception:
        return None

    if 'jti' not in token_contents:
        return None

    token_valid = await is_token_valid(db, ObjectId(token_contents['jti']))
    if not token_valid:
        return None

    if token_contents["csrf_required"] and csrf:
        csrf_token = request.headers["X-CSRF-Token"] if "X-CSRF-Token" in request.headers else None
        if csrf_token is None:
            csrf_token = request.query_params.get('csrf_token')
        if csrf_token is None:
            return None

        try:
            csrf_token_contents = jwt.decode(
                csrf_token,
                settings.JWT_KEY,
                algorithms=["HS256"],
                issuer="Wirecloud",
                options={
                    "require": ["exp", "sub", "iat", "iss"],
                    "verify_exp": True,
                    "verify_iss": True
                }
            )
            if csrf_token_contents.get("sub") != "csrf":
                return None

            if csrf_token_contents.get('jti') != token_contents.get('jti'):
                return None
        except Exception:
            return None

    return token_contents


async def get_token_contents_csrf(token: Annotated[str, Depends(login_scheme)], request: Request, db: DBDep) -> Token:
    return await get_token_contents(token, request, db, csrf=True)


async def get_token_contents_no_csrf(token: Annotated[str, Depends(login_scheme)], request: Request, db: DBDep) -> Token:
    return await get_token_contents(token, request, db, csrf=False)


async def get_user(db: DBDep, token: Token, real_user: bool) -> Union[UserAll, None]:
    if token is None:
        return None

    sub: str = token.get('sub')
    if real_user and 'real_user' in token:
        sub = token['real_user'].get('id')

    user = await get_user_with_all_info(db, Id(sub))
    if user is None or not user.is_active:
        return None

    return user


async def get_user_csrf(db: DBDep, token: Annotated[Token, Depends(get_token_contents_csrf)]) -> Union[UserAll, None]:
    return await get_user(db, token, False)


async def get_user_no_csrf(db: DBDep, token: Annotated[Token, Depends(get_token_contents_no_csrf)]) -> Union[UserAll, None]:
    return await get_user(db, token, False)


async def get_real_user_csrf(db: DBDep, token: Annotated[Token, Depends(get_token_contents_csrf)]) -> Union[UserAll, None]:
    return await get_user(db, token, True)


async def get_real_user_no_csrf(db: DBDep, token: Annotated[Token, Depends(get_token_contents_no_csrf)]) -> Union[UserAll, None]:
    return await get_user(db, token, True)


UserDep = Annotated[UserAll, Depends(get_user_csrf)]
UserDepNoCSRF = Annotated[UserAll, Depends(get_user_no_csrf)]
RealUserDep = Annotated[UserAll, Depends(get_real_user_csrf)]
RealUserDepNoCSRF = Annotated[UserAll, Depends(get_real_user_no_csrf)]

async def get_session(db: DBDep, request: Request, token: Token) -> Union[Session, None]:
    if token is None:
        return None

    real_username = None
    real_fullname = None
    if 'real_user' in token:
        real_username = token['real_user'].get('username')
        real_fullname = token['real_user'].get('fullname')

    return Session(
        id=Id(token.get("jti")),
        real_user=real_username,
        real_fullname=real_fullname,
        requires_csrf=token.get('csrf_required', True),
        token_data=token
    )


async def get_session_csrf(db: DBDep, request: Request, token: Annotated[Token, Depends(get_token_contents_csrf)]) -> Union[Session, None]:
    return await get_session(db, request, token)


async def get_session_no_csrf(db: DBDep, request: Request, token: Annotated[Token, Depends(get_token_contents_no_csrf)]) -> Union[Session, None]:
    return await get_session(db, request, token)


SessionDep = Annotated[Session, Depends(get_session_csrf)]
SessionDepNoCSRF = Annotated[Session, Depends(get_session_no_csrf)]


def check_password(password: str, password_hash: str) -> bool:
    used_hash = None
    for hash_name in SUPPORTED_HASHES:
        if hash_name in password_hash:
            used_hash = hash_name
            break

    if used_hash is None:
        return False

    if used_hash == 'pbkdf2_sha256':
        _, iterations, salt, expected_password_hash = password_hash.split('$')
        hashed_password = pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('ascii'), int(iterations))
        return compare_digest(hashed_password, b64decode(expected_password_hash))

    return False


def hash_password(password: str) -> str:
    algorithm = 'pbkdf2_sha256'
    salt = secrets.token_hex(16)
    iterations = 150000
    hashed_password = pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('ascii'), iterations)
    return f'{algorithm}${iterations}${salt}${b64encode(hashed_password).decode("ascii")}'


async def make_oidc_provider_request(endpoint: str, data: Optional[dict] = None, auth: Optional[str] = None,
                                     auth_type: str = "Bearer", query: Optional[dict] = None) -> dict:
    headers = {
        'Accept': 'application/json'
    }

    if data:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'

    if auth:
        headers['Authorization'] = f'{auth_type} {auth}'

    encoded_data = urlencode(data) if data else None

    session = aiohttp.ClientSession()
    try:
        res = await session.request(
            method='POST' if data else 'GET',
            url=endpoint,
            timeout=5,
            headers=headers,
            allow_redirects=True,
            data=encoded_data,
            params=query,
            ssl=getattr(settings, "WIRECLOUD_HTTPS_VERIFY", True),
        )
    except:
        await session.close()
        raise Exception(_("OIDC provider is not reachable"))

    if res.status != 200 and res.status != 204:
        await session.close()
        raise Exception(_("OIDC provider has not returned a valid response"))

    response_data = None

    if res.status != 204:  # 204 No Content
        try:
            response_data = await res.json()
        except:
            await session.close()
            raise Exception(_("OIDC provider has not returned a valid response"))

    await session.close()
    return response_data
