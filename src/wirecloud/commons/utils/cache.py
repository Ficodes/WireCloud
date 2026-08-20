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

import hashlib
from datetime import datetime, timezone
from typing import Union, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse, HTMLResponse

from pydantic import BaseModel
import time

from email.utils import parsedate_to_datetime

from wirecloud.commons.utils.http import http_date
from wirecloud.platform.workspace.schemas import WorkspaceGlobalData


def patch_cache_headers(response: Response, timestamp: int=None, cache_timeout: int=None, etag=None) -> Response:
    current_timestamp = int(time.time())
    if timestamp is None:
        timestamp = current_timestamp
    else:
        timestamp = int(timestamp / 1000)

    if not 'Last-Modified' in response.headers:
        response.headers['Last-Modified'] = http_date(timestamp)

    if etag is not None:
        response.headers['ETag'] = etag
    elif hasattr(response, 'body') and 'ETag' not in response.headers:
        hash_value = hashlib.sha1(response.body).hexdigest()
        result = f'"{hash_value}"'
        response.headers['ETag'] = result

    if cache_timeout is not None and timestamp + cache_timeout > current_timestamp:
        response.headers['Cache-Control'] = f'private, max-age={timestamp + cache_timeout - current_timestamp}'
        response.headers['Expires'] = http_date(timestamp + cache_timeout)
    else:
        response.headers['Cache-Control'] = 'private, max-age=0'

    return response

def check_if_modified_since(request: Request, time_last_modified: Optional[datetime]) -> bool:
    if_modified_since = request.headers.get("If-Modified-Since")

    if if_modified_since is None or time_last_modified is None:
        return True

    try:
        if_modified_since = parsedate_to_datetime(if_modified_since).replace(tzinfo=timezone.utc)
        time_last_modified = time_last_modified.replace(tzinfo=timezone.utc)
    except Exception:
        return True

    return time_last_modified > if_modified_since

class CacheableData(BaseModel):
    data: Union[WorkspaceGlobalData, str]
    timestamp: Union[datetime, float] = None
    timeout: int = 0
    content_type: str = 'application/json; charset=UTF-8'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.timestamp is None:
            self.timestamp = time.time() * 1000

    def get_response(self, status_code=200, cacheable=True):
        if isinstance(self.data, str):
            response = HTMLResponse(content=self.data, status_code=status_code)
        else:
            response = JSONResponse(content=self.data.model_dump(), status_code=status_code)

        if cacheable:
            aux_timestamp = self.timestamp
            if isinstance(aux_timestamp, datetime):
                aux_timestamp = aux_timestamp.timestamp()
            patch_cache_headers(response, aux_timestamp, self.timeout)

        return response
