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

from typing import Optional
from urllib.parse import quote, urlsplit


def page_headers(form_redirect_uri: Optional[str] = None) -> dict[str, str]:
    form_actions = "'self'"
    if form_redirect_uri is not None:
        callback = urlsplit(form_redirect_uri)
        form_actions += " " + quote(f"{callback.scheme}://{callback.netloc}", safe=":/[]")
    return {
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'none'; script-src 'self'; script-src-attr 'none'; "
        "style-src 'self'; img-src 'self'; font-src 'self'; "
        f"form-action {form_actions}; frame-ancestors 'none'; base-uri 'none'",
    }
