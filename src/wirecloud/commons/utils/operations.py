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

import inspect
import json
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.params import Param, Body

from wirecloud.commons.auth.schemas import UserAll
from wirecloud.database import DBSession


async def invoke_operation(
    operation: Callable[..., Awaitable[Any]], db: DBSession, user: UserAll, request: Request, **arguments: Any
) -> Any:
    parameters = inspect.signature(operation).parameters
    values = {"db": db, "user": user, "request": request, **arguments}
    for name, parameter in parameters.items():
        if name not in values and isinstance(parameter.default, (Param, Body)):
            values[name] = parameter.default.default
    result = await operation(**{name: value for name, value in values.items() if name in parameters})
    if isinstance(result, Response):
        body = getattr(result, "body", b"")
        if result.status_code >= 400:
            try:
                details = json.loads(body)
            except (ValueError, TypeError):
                details = {"description": "WireCloud operation failed"}
            raise HTTPException(result.status_code, details)
        if not body:
            return {"ok": True}
        try:
            return json.loads(body)
        except (ValueError, TypeError) as exc:
            raise HTTPException(500, "Unexpected operation response") from exc
    return jsonable_encoder(result) if result is not None else {"ok": True}
