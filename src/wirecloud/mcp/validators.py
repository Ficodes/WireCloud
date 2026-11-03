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

import sys
from urllib.parse import urlsplit

from wirecloud.platform.plugins import ImproperlyConfigured


def validate_mcp_settings(settings: object, offline: bool = False) -> None:
    if sys.version_info < (3, 11):
        raise ImproperlyConfigured("The MCP plugin requires Python 3.11 or newer")

    public_url = getattr(settings, "MCP_PUBLIC_URL", "")
    parsed = urlsplit(public_url)
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.path.endswith("/mcp")
    ):
        raise ImproperlyConfigured("MCP_PUBLIC_URL must be the absolute public URL ending in /mcp")

    local_http = parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme != "https" and not local_http:
        raise ImproperlyConfigured("MCP requires HTTPS (HTTP is allowed only on loopback for development)")
