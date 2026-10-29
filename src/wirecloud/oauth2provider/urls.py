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

from wirecloud.platform.plugins import URLTemplate

patterns = {
    "oauth2provider.authorize": URLTemplate(urlpattern="/oauth2/authorize", defaults={}),
    "oauth2provider.token": URLTemplate(urlpattern="/oauth2/token", defaults={}),
    "oauth2provider.register": URLTemplate(urlpattern="/oauth2/register", defaults={}),
    "oauth2provider.revoke": URLTemplate(urlpattern="/oauth2/revoke", defaults={}),
    "oauth2provider.connections": URLTemplate(urlpattern="/oauth2/connections", defaults={}),
}
