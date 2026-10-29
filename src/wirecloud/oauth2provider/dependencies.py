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

from typing import Collection

from fastapi import HTTPException, Request

from wirecloud.database import DBSession
from wirecloud.oauth2provider.service import OAuthPrincipal, bearer_token, get_resource, resource_metadata_url, verify_access_token


async def require_access(
    request: Request, db: DBSession, audience: str, scopes: Collection[str] = ()
) -> OAuthPrincipal:
    resource = get_resource(request, audience)
    if not set(scopes).issubset(resource.scopes):
        raise ValueError("Endpoint requires scopes not declared by its OAuth resource")
    principal = await verify_access_token(db, bearer_token(request), audience)
    challenge = f'Bearer resource_metadata="{resource_metadata_url(audience)}"'
    if scopes:
        challenge += ', scope="' + " ".join(scopes) + '"'
    if principal is None:
        raise HTTPException(
            401, {"error": "invalid_token"}, headers={"WWW-Authenticate": challenge, "Cache-Control": "no-store"}
        )
    if not set(scopes).issubset(principal.scopes):
        raise HTTPException(
            403,
            {"error": "insufficient_scope"},
            headers={"WWW-Authenticate": challenge + ', error="insufficient_scope"', "Cache-Control": "no-store"},
        )
    return principal
