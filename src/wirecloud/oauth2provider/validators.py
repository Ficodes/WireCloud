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

from urllib.parse import urlsplit

from wirecloud.oauth2provider.service import valid_redirect, validate_client
from wirecloud.platform.plugins import ImproperlyConfigured


def validate_oauth_settings(settings: object, offline: bool = False) -> None:
    public_url = getattr(settings, "OAUTH2_PUBLIC_URL", "")
    if public_url and (not valid_redirect(public_url) or urlsplit(public_url).query):
        raise ImproperlyConfigured("OAUTH2_PUBLIC_URL must be an HTTPS or loopback public base URL")

    if not isinstance(getattr(settings, "OAUTH2_DYNAMIC_REGISTRATION", True), bool):
        raise ImproperlyConfigured("OAUTH2_DYNAMIC_REGISTRATION must be a boolean")

    for client in getattr(settings, "OAUTH2_CLIENTS", []):
        validate_client(client)
