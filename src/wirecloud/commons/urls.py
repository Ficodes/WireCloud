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

from wirecloud import settings
from wirecloud.platform.plugins import URLTemplate

patterns: dict[str, URLTemplate] = {
    # Auth
    'login': URLTemplate(urlpattern='/login', defaults={}),
    'wirecloud.login_form': URLTemplate(urlpattern='/login', defaults={}),
    'wirecloud.begin_login': URLTemplate(urlpattern='/auth/login', defaults={}),
    'oidc_login_callback': URLTemplate(urlpattern='/oidc/callback', defaults={}),
    'logout': URLTemplate(urlpattern='/logout', defaults={}),
    'wirecloud.token_refresh': URLTemplate(urlpattern='/api/auth/refresh', defaults={}),
    'wirecloud.login': URLTemplate(urlpattern='/api/auth/login', defaults={}),

    # i18n
    'wirecloud.javascript_translation_catalogue': URLTemplate(urlpattern='/api/i18n/js_catalogue', defaults={}),

    # OAuth2
    'oauth.default_redirect_uri': URLTemplate(urlpattern='/oauth2/default_redirect_uri', defaults={}),
}

def get_urlpatterns() -> dict[str, URLTemplate]:
    login = patterns['wirecloud.begin_login'] if settings.OID_CONNECT_ENABLED else patterns['login']
    return {**patterns, 'login': login}
