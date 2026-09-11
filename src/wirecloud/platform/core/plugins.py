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

import os
import logging
from argparse import _SubParsersAction
from urllib.parse import quote_plus
import orjson as json
from bson.errors import InvalidId
from hashlib import sha1, md5
from typing import Any, Optional, Callable
from fastapi import FastAPI, Request

import wirecloud.platform as platform
from wirecloud import settings
from wirecloud.catalogue.crud import get_catalogue_resource
from wirecloud.commons.auth.crud import get_user_groups, get_all_user_permissions, get_group_by_id
from wirecloud.commons.auth.routes import admin_router
from wirecloud.commons.utils.http import get_absolute_reverse_url
from wirecloud.commons.utils.template.schemas.macdschemas import Vendor, Name, Version
from wirecloud.commons.utils.wgt import WgtFile
from wirecloud.database import DBSession
from wirecloud.platform.core.commands import setup_commands
from wirecloud.platform.iwidget.routes import iwidget_router
from wirecloud.platform.localcatalogue.schemas import ResourceCreateData, ResourceCreateFormData
from wirecloud.platform.localcatalogue.utils import install_component
from wirecloud.platform.widget.routes import widget_router, showcase_router
from wirecloud.platform.wiring.routes import wiring_router, operator_router
from wirecloud.platform.workspace.crud import get_workspace_by_username_and_name, create_workspace
from wirecloud.platform.workspace.routes import workspace_router, workspaces_router
from wirecloud.platform.plugins import (get_active_features_info, get_plugin_urls, AjaxEndpoint, build_url_template,
                                            WirecloudPlugin, URLTemplate)
from wirecloud.platform.context.schemas import BaseContextKey, WorkspaceContextKey
from wirecloud.platform.preferences.routes import preferences_router
from wirecloud.platform.preferences.schemas import PreferenceKey, TabPreferenceKey
from wirecloud.platform.urls import patterns
from wirecloud.platform.routes import get_current_theme, get_current_view
from wirecloud.commons.auth.schemas import UserAll, Session

from wirecloud.platform.context.routes import router as context_router
from wirecloud.platform.localcatalogue.routes import (router as localcatalogue_router,
                                                          resources_router as localcatalogue_resources_router,
                                                          workspace_router as localcatalogue_workspace_router)
from wirecloud.platform.markets.routes import router as market_router, markets_router
from wirecloud.platform.routes import router as platform_router
from wirecloud.platform.theme.routes import router as theme_router
from wirecloud.platform.core.catalogue_manager import WirecloudCatalogueManager
from wirecloud.translation import gettext as _

BASE_PATH = os.path.dirname(__file__)
WORKSPACE_BROWSER_FILE = os.path.join(BASE_PATH, 'initial', 'WireCloud_workspace-browser_0.1.4a1.wgt')
INITIAL_HOME_DASHBOARD_FILE = os.path.join(BASE_PATH, 'initial', 'initial_home_dashboard.wgt')
MARKDOWN_VIEWER_FILE = os.path.join(BASE_PATH, 'initial', 'CoNWeT_markdown-viewer_0.1.1.wgt')
MARKDOWN_EDITOR_FILE = os.path.join(BASE_PATH, 'initial', 'CoNWeT_markdown-editor_0.1.0.wgt')
LANDING_DASHBOARD_FILE = os.path.join(BASE_PATH, 'initial', 'WireCloud_landing-dashboard_1.0.wgt')


logger = logging.getLogger(__name__)


def get_version_hash():
    return sha1(json.dumps(get_active_features_info())).hexdigest()


# Default responsive breakpoints for the 'screenSizes' workspace/tab preference. Kept as a
# translation-free module-level constant (rather than inline in get_workspace_preferences) so it
# can be imported and used outside of a request context -- e.g. by
# wirecloud.commons.utils.template.base.default_desktop_screen_size_id(), which the legacy
# layout/mashup-template conversion code uses and which must work from CLI management commands.
DEFAULT_SCREEN_SIZES = [
    {"id": 0, "name": "Phone", "moreOrEqual": 0, "lessOrEqual": 767, "columns": 1},
    {"id": 1, "name": "Tablet", "moreOrEqual": 768, "lessOrEqual": 1199, "columns": 6},
    {"id": 2, "name": "Desktop", "moreOrEqual": 1200, "lessOrEqual": -1, "columns": 12},
]


async def populate_component(db: DBSession, wirecloud_user: UserAll, vendor: Vendor, name: Name,
                             version: Version, wgt_path: str) -> bool:
    if await get_catalogue_resource(db, vendor, name, version):
        return False

    print(f"Installing the {name} widget...", end=' ')
    await install_component(db, WgtFile(wgt_path), executor_user=wirecloud_user, users=[wirecloud_user])
    print("DONE")
    return True


class WirecloudCorePlugin(WirecloudPlugin):
    features = {
        'Wirecloud': platform.__version__,
        'ApplicationMashup': platform.__application_mashup_version__,
        'StyledElements': '0.11.0',
        'FullscreenWidget': '0.5',
        'DashboardManagement': '1.0',
        'ComponentManagement': '1.0',
    }

    urls = patterns

    def __init__(self, app: Optional[FastAPI]):
        super().__init__(app)

        if app is None:
            return

        app.include_router(context_router, prefix="/api/context", tags=["Context"])
        app.include_router(localcatalogue_resources_router, prefix="/api/resources", tags=["Local Catalogue"])
        app.include_router(localcatalogue_router, prefix="/api/resource", tags=["Local Catalogue"])
        app.include_router(localcatalogue_workspace_router, prefix="/api/workspace", tags=["Local Catalogue"])
        app.include_router(market_router, prefix="/api/market", tags=["Market"])
        app.include_router(markets_router, prefix="/api/markets", tags=["Market"])
        app.include_router(preferences_router, prefix="/api", tags=["Preferences"])
        app.include_router(workspace_router, prefix="/api/workspace", tags=["Workspace"])
        app.include_router(workspaces_router, prefix="/api/workspaces", tags=["Workspace"])
        app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
        app.include_router(iwidget_router, prefix="/api/workspace", tags=["Widget instances"])
        app.include_router(widget_router, prefix="/api/widget", tags=["Widget"])
        app.include_router(showcase_router, prefix="/showcase/media", tags=["Widget"])
        app.include_router(theme_router, prefix="/api/theme", tags=["Theme"])
        app.include_router(wiring_router, prefix="/api/workspace", tags=["Wiring"])
        app.include_router(operator_router, prefix="/api/operator", tags=["Operator"])
        app.include_router(platform_router, prefix="", tags=["Platform"])

    def get_config_validators(self) -> tuple[Callable, ...]:
        def validate_platform_settings(settings, _offline: bool) -> None:
            from os import path

            # WIDGET_DEPLOYMENT_DIR (default: BASEDIR/deployment/widgets)
            if not hasattr(settings, 'WIDGET_DEPLOYMENT_DIR'):
                setattr(settings, 'WIDGET_DEPLOYMENT_DIR', path.join(settings.BASEDIR, 'deployment', 'widgets'))

            if not isinstance(settings.WIDGET_DEPLOYMENT_DIR, str):
                raise ValueError("WIDGET_DEPLOYMENT_DIR must be a string")

            # Create directory if it doesn't exist
            if not os.path.exists(settings.WIDGET_DEPLOYMENT_DIR):
                try:
                    os.makedirs(settings.WIDGET_DEPLOYMENT_DIR, exist_ok=True)
                    logger.info(f"Created WIDGET_DEPLOYMENT_DIR directory: {settings.WIDGET_DEPLOYMENT_DIR}")
                except Exception as e:
                    raise ValueError(f"Failed to create WIDGET_DEPLOYMENT_DIR directory: {e}")

            # CACHE_DIR validation
            if hasattr(settings, 'CACHE_DIR'):
                if not isinstance(settings.CACHE_DIR, str):
                    raise ValueError("CACHE_DIR must be a string")

                # Create directory if it doesn't exist
                if not os.path.exists(settings.CACHE_DIR):
                    try:
                        os.makedirs(settings.CACHE_DIR, exist_ok=True)
                        logger.info(f"Created CACHE_DIR directory: {settings.CACHE_DIR}")
                    except Exception as e:
                        raise ValueError(f"Failed to create CACHE_DIR directory: {e}")

            # AVAILABLE_THEMES (default: ['defaulttheme'])
            if not hasattr(settings, 'AVAILABLE_THEMES'):
                setattr(settings, 'AVAILABLE_THEMES', ['defaulttheme'])

            if not isinstance(settings.AVAILABLE_THEMES, list):
                raise ValueError("AVAILABLE_THEMES must be a list")

            if len(settings.AVAILABLE_THEMES) == 0:
                raise ValueError("AVAILABLE_THEMES must contain at least one theme")

            # THEME_ACTIVE (default: 'defaulttheme')
            if not hasattr(settings, 'THEME_ACTIVE'):
                setattr(settings, 'THEME_ACTIVE', 'defaulttheme')

            if not isinstance(settings.THEME_ACTIVE, str):
                raise ValueError("THEME_ACTIVE must be a string")

            if settings.THEME_ACTIVE not in settings.AVAILABLE_THEMES:
                raise ValueError(f"THEME_ACTIVE '{settings.THEME_ACTIVE}' is not in AVAILABLE_THEMES")

        return (validate_platform_settings,)

    def get_platform_context_definitions(self) -> dict[str, BaseContextKey]:
        return {
            'language': BaseContextKey(
                label=_('Language'),
                description=_('Current language used in the platform'),
            ),
            'username': BaseContextKey(
                label=_('Username'),
                description=_('User name of the current logged user'),
            ),
            'fullname': BaseContextKey(
                label=_('Full name'),
                description=_('Full name of the logged user'),
            ),
            'avatar': BaseContextKey(
                label=_('Avatar'),
                description=_('URL of the avatar'),
            ),
            'isanonymous': BaseContextKey(
                label=_('Is Anonymous'),
                description=_('Boolean. Designates whether current user is logged in the system.'),
            ),
            'isstaff': BaseContextKey(
                label=_('Is Staff'),
                description=_('Boolean. Designates whether current user can access the admin site.'),
            ),
            'issuperuser': BaseContextKey(
                label=_('Is Superuser'),
                description=_('Boolean. Designates whether current user is a super user.'),
            ),
            'groups': BaseContextKey(
                label=_('Groups'),
                description=_('List of groups the user belongs to'),
            ),
            'permissions': BaseContextKey(
                label=_('Permissions'),
                description=_('List of permissions the user has'),
            ),
            'mode': BaseContextKey(
                label=_('Mode'),
                description=_('Rendering mode used by the platform (available modes: classic, smartphone and embedded)'),
            ),
            'organizations': BaseContextKey(
                label=_('User Organizations'),
                description=_('List of the organizations the user belongs to.'),
            ),
            'orientation': BaseContextKey(
                label=_('Orientation'),
                description=_('Current screen orientation'),
            ),
            'realuser': BaseContextKey(
                label=_('Real User Username'),
                description=_('User name of the real logged user'),
            ),
            'theme': BaseContextKey(
                label=_('Theme'),
                description=_('Name of the theme used by the platform'),
            ),
            'version': BaseContextKey(
                label=_('Version'),
                description=_('Version of the platform'),
            ),
            'version_hash': BaseContextKey(
                label=_('Version Hash'),
                description=_('Hash for the current version of the platform. This hash changes when the platform is updated or when an addon is added or removed'),
            ),
        }

    async def get_platform_context_current_values(self, db: DBSession, request: Optional[Request], user: Optional[UserAll],
                                            session: Optional[Session]):
        if user:
            username = user.username
            fullname = user.get_full_name()
            avatar = 'https://www.gravatar.com/avatar/' + md5(
                user.email.strip().lower().encode('utf8')).hexdigest() + '?s=25'
            user_groups = await get_user_groups(db, user.id)
            groups = tuple(group.name for group in user_groups)
            organizations_by_id = {}
            for group in user_groups:
                if not getattr(group, "is_organization", False) or not getattr(group, "path", None):
                    continue
                root_id = group.path[0]
                if root_id in organizations_by_id:
                    continue
                root = group if group.id == root_id else await get_group_by_id(db, root_id)
                if root is not None:
                    organizations_by_id[root_id] = root.name
            organizations = tuple(organizations_by_id.values())
            try:
                permissions = [p.codename for p in await get_all_user_permissions(db, user.id)]
            except InvalidId:
                permissions = []
        else:
            username = 'anonymous'
            fullname = 'Anonymous'
            avatar = 'https://www.gravatar.com/avatar/00000000000000000000000000000000?s=25'
            groups = ()
            organizations = ()
            permissions = ()

        return {
            'language': request.state.lang if request else None,
            'orientation': 'landscape',
            'username': username,
            'fullname': fullname,
            'avatar': avatar,
            'isanonymous': user is None,
            'isstaff': user.is_staff if user else False,
            'issuperuser': user.is_superuser if user else False,
            'groups': groups,
            'permissions': permissions,
            'organizations': organizations,
            'mode': get_current_view(request) if request else None,
            'realuser': session.real_user if session else None,
            'theme': get_current_theme(request) if request else None,
            'version': platform.__version__,
            'version_hash': get_version_hash(),
        }

    def get_workspace_context_definitions(self) -> dict[str, WorkspaceContextKey]:
        return {
            'description': WorkspaceContextKey(
                label=_('Description'),
                description=_('Short description of the workspace without formating'),
            ),
            'editing': WorkspaceContextKey(
                label=_('Editing mode'),
                description=_('Boolean. Designates whether the workspace is in editing mode.'),
            ),
            'title': WorkspaceContextKey(
                label=_('Title'),
                description=_('Current title of the workspace'),
            ),
            'name': WorkspaceContextKey(
                label=_('Name'),
                description=_('Current name of the workspace'),
            ),
            'owner': WorkspaceContextKey(
                label=_('Owner'),
                description=_('Workspace\'s owner username'),
            ),
            'longdescription': WorkspaceContextKey(
                label=_('Long description'),
                description=_('Detailed workspace\'s description. This description can contain formatting.'),
            ),
            'params': WorkspaceContextKey(
                label=_('Params'),
                description=_('Dictionary with the parameters of the workspace'),
            ),
        }

    def get_platform_preferences(self) -> list[PreferenceKey]:
        return [
            PreferenceKey(
                name='allow_external_token_use',
                label=_('Allow external token use'),
                type='boolean',
                description=_('Allow other users to use your token to authenticate in external services. The token will not be directly exposed to these users. Necessary for features like "Use workspace owner token".'),
                defaultValue=False
            ),
            PreferenceKey(
                name='external_token_domain_whitelist',
                label=_('External token domain whitelist'),
                type='text',
                description=_('List of domains separated by commas that can be used to authenticate in external services. Use * to allow any domain (DANGEROUS, since that could expose it to non-authorised services).'),
                defaultValue='*'
            )
        ]

    def get_workspace_preferences(self) -> list[PreferenceKey]:
        return [
            PreferenceKey(
                name='public',
                label=_('Public'),
                type='boolean',
                hidden=True,
                description=_('Allow any user to open this workspace (in read-only mode). (default: disabled)'),
                defaultValue=False
            ),
            PreferenceKey(
                name='requireauth',
                label=_('Required registered user'),
                type='boolean',
                hidden=True,
                description=_('Require users to be logged in to access the workspace (This option has only effect if the workspace is public). (default: disabled)'),
                defaultValue=False
            ),
            PreferenceKey(
                name='sharelist',
                label=_('Share list'),
                type='text',  # Legacy client field type used by the preference renderer. Hidden and never rendered.
                hidden=True,
                description=_('List of users with access to this workspace. (default: [])'),
                defaultValue=[]
            ),
            PreferenceKey(
                name='screenSizes', label=_('Screen sizes'), type='screenSizes',
                description=_('Responsive breakpoints of the dashboard. Each screen size covers a range of widths in '
                              'pixels and defines the number of grid columns used when the dashboard is displayed at '
                              'that width. Widgets can have a different layout for each screen size.'),
                defaultValue=[dict(screen_size) for screen_size in DEFAULT_SCREEN_SIZES]
            ),
            PreferenceKey(
                name='cellheight', label=_('Cell height'), type='number',
                description=_('Height in pixels of a grid row.'), defaultValue=40
            ),
            PreferenceKey(
                name='margin', label=_('Widget margin'), type='number',
                description=_('Space in pixels between widgets.'), defaultValue=5
            ),
        ]

    def get_tab_preferences(self) -> list[TabPreferenceKey]:
        workspace_preferences = self.get_workspace_preferences()
        tab_preferences = []
        for preference in workspace_preferences:
            if preference.name != 'public':
                tab_preferences.append(TabPreferenceKey(
                    name=preference.name,
                    label=preference.label,
                    type=preference.type,
                    hidden=preference.hidden,
                    description=preference.description,
                    initialEntries=preference.initialEntries,
                    defaultValue=preference.defaultValue,
                    inheritable=True,
                    inheritByDefault=True
                ))

        return tab_preferences

    def get_market_classes(self) -> dict[str, type]:
        return {
            'wirecloud': WirecloudCatalogueManager,
        }

    def get_constants(self) -> dict[str, Any]:
        languages = [{'value': lang[0], 'label': lang[1]} for lang in settings.LANGUAGES]
        return {
            'AVAILABLE_LANGUAGES': languages,
        }

    def get_templates(self, view: str) -> list[str]:
        if view == 'classic' or view == 'smartphone':
            return [
                "wirecloud/component_sidebar",
                "wirecloud/catalogue/main_resource_details",
                "wirecloud/catalogue/modals/upload",
                "wirecloud/catalogue/resource",
                "wirecloud/catalogue/resource_details",
                "wirecloud/catalogue/search_interface",
                "wirecloud/logs/details",
                "wirecloud/modals/base",
                "wirecloud/modals/embed_code",
                "wirecloud/macsearch/base",
                "wirecloud/macsearch/component",
                "wirecloud/wiring/behaviour_sidebar",
                "wirecloud/wiring/component_group",
                "wirecloud/wiring/footer",
                "wirecloud/workspace/empty_tab_message",
                "wirecloud/workspace/sharing_user",
                "wirecloud/workspace/visibility_option",
                "wirecloud/workspace/widget",
                "wirecloud/modals/upgrade_downgrade_component",
                "wirecloud/signin",
                "wirecloud/user_menu",
            ]
        else:
            return []

    # TODO Move each template to its own plugin
    def get_ajax_endpoints(self, view: str, request: Request) -> tuple[AjaxEndpoint, ...]:
        url_patterns = get_plugin_urls()
        prefix = request.scope.get('root_path')

        if not 'wirecloud|proxy' in url_patterns:
            raise ValueError('Missing proxy url pattern. Is the proxy plugin enabled?')

        login_url_pattern = URLTemplate(urlpattern=url_patterns['login'].urlpattern, defaults={})
        if getattr(settings, 'OID_CONNECT_ENABLED', False):
            if '?' in login_url_pattern.urlpattern:
                login_url_pattern.urlpattern += '&'
            else:
                login_url_pattern.urlpattern += '?'
            login_url_pattern.urlpattern += f"redirect_uri={quote_plus(get_absolute_reverse_url('oidc_login_callback', request))}"
            # Add the current URL as the state, in order to redirect to the same page after login
            login_url_pattern.urlpattern += f"&state={quote_plus(request.url.path + (('?' + request.url.query) if request.url.query else ''))}"

        endpoints = (
            AjaxEndpoint(id='IWIDGET_COLLECTION', url=build_url_template(url_patterns['wirecloud.iwidget_collection'],
                                                                         ['workspace_id', 'tab_id'], prefix)),
            AjaxEndpoint(id='IWIDGET_ENTRY', url=build_url_template(url_patterns['wirecloud.iwidget_entry'],
                                                                    ['workspace_id', 'tab_id', 'iwidget_id'], prefix)),
            AjaxEndpoint(id='IWIDGET_PREFERENCES', url=build_url_template(url_patterns['wirecloud.iwidget_preferences'],
                                                                          ['workspace_id', 'tab_id', 'iwidget_id'],
                                                                          prefix)),
            AjaxEndpoint(id='IWIDGET_PROPERTIES', url=build_url_template(url_patterns['wirecloud.iwidget_properties'],
                                                                         ['workspace_id', 'tab_id', 'iwidget_id'],
                                                                         prefix)),
            AjaxEndpoint(id='LOCAL_REPOSITORY', url=build_url_template(url_patterns['wirecloud.root'], [], prefix)),
            AjaxEndpoint(id='LOCAL_RESOURCE_COLLECTION',
                         url=build_url_template(url_patterns['wirecloud.resource_collection'],
                                                ['vendor', 'name', 'version'], prefix)),
            AjaxEndpoint(id='LOCAL_RESOURCE_ENTRY',
                         url=build_url_template(url_patterns['wirecloud.resource_entry'], ['vendor', 'name', 'version'],
                                                prefix)),
            AjaxEndpoint(id='LOCAL_UNVERSIONED_RESOURCE_ENTRY',
                         url=build_url_template(url_patterns['wirecloud.unversioned_resource_entry'],
                                                ['vendor', 'name'], prefix)),
            AjaxEndpoint(id='LOCAL_RESOURCE_MASSIVE_UPDATE_ENTRY',
                         url=build_url_template(url_patterns['wirecloud.massive_resource_update_entry'],
                                                ['vendor', 'name', 'version'], prefix)),
            AjaxEndpoint(id='LOGIN_API', url=build_url_template(url_patterns['wirecloud.login'], [], prefix)),
            AjaxEndpoint(id='LOGIN_VIEW', url=build_url_template(login_url_pattern, [], prefix)),
            AjaxEndpoint(id='LOGOUT_VIEW', url=build_url_template(url_patterns['logout'], [], prefix)),
            AjaxEndpoint(id="REFRESH_TOKEN", url=build_url_template(url_patterns['wirecloud.token_refresh'], [], prefix)),
            AjaxEndpoint(id='MAC_BASE_URL', url=build_url_template(url_patterns['wirecloud.showcase_media'],
                                                                   ['vendor', 'name', 'version', 'file_path'], prefix)),
            AjaxEndpoint(id='MARKET_COLLECTION',
                         url=build_url_template(url_patterns['wirecloud.market_collection'], [], prefix)),
            AjaxEndpoint(id='MARKET_ENTRY',
                         url=build_url_template(url_patterns['wirecloud.market_entry'], ['user', 'market'], prefix)),
            AjaxEndpoint(id='MISSING_WIDGET_CODE_ENTRY',
                         url=build_url_template(url_patterns['wirecloud.missing_widget_code_entry'], [], prefix)),
            AjaxEndpoint(id='WIDGET_CODE_ENTRY',
                         url=build_url_template(url_patterns['wirecloud.widget_html'], ['vendor', 'name', 'version'], prefix)),
            AjaxEndpoint(id='OPERATOR_ENTRY', url=build_url_template(url_patterns['wirecloud.operator_code_entry'],
                                                                     ['vendor', 'name', 'version'], prefix)),
            AjaxEndpoint(id='PLATFORM_CONTEXT_COLLECTION',
                         url=build_url_template(url_patterns['wirecloud.platform_context_collection'], [], prefix)),
            AjaxEndpoint(id='PLATFORM_PREFERENCES',
                         url=build_url_template(url_patterns['wirecloud.platform_preferences'], [], prefix)),
            AjaxEndpoint(id='PROXY',
                         url=build_url_template(url_patterns['wirecloud|proxy'], ['protocol', 'domain', 'path'],
                                                prefix)),
            AjaxEndpoint(id='PUBLISH_ON_OTHER_MARKETPLACE',
                         url=build_url_template(url_patterns['wirecloud.publish_on_other_marketplace'], [], prefix)),
            AjaxEndpoint(id='ROOT_URL', url=build_url_template(url_patterns['wirecloud.root'], [], prefix)),
            AjaxEndpoint(id='SEARCH_SERVICE',
                         url=build_url_template(url_patterns['wirecloud.search_service'], [], prefix)),
            AjaxEndpoint(id='SWITCH_USER_SERVICE',
                         url=build_url_template(url_patterns['wirecloud.switch_user_service'], [], prefix)),
            AjaxEndpoint(id='ADMIN_USER_COLLECTION',
                         url=build_url_template(url_patterns['wirecloud.admin_user_collection'], [], prefix)),
            AjaxEndpoint(id='ADMIN_USER_ENTRY',
                         url=build_url_template(url_patterns['wirecloud.admin_user_entry'], ['user_username'], prefix)),
            AjaxEndpoint(id='ADMIN_GROUP_COLLECTION',
                         url=build_url_template(url_patterns['wirecloud.admin_group_collection'], [], prefix)),
            AjaxEndpoint(id='ADMIN_GROUP_ENTRY',
                         url=build_url_template(url_patterns['wirecloud.admin_group_entry'], ['group_name'], prefix)),
            AjaxEndpoint(id='ADMIN_ORGANIZATION_COLLECTION',
                         url=build_url_template(url_patterns['wirecloud.admin_organization_collection'], [], prefix)),
            AjaxEndpoint(id='ADMIN_ORGANIZATION_ENTRY',
                         url=build_url_template(url_patterns['wirecloud.admin_organization_entry'], ['org_name'], prefix)),
            AjaxEndpoint(id='ADMIN_ORGANIZATION_GROUP_ENTRY',
                         url=build_url_template(url_patterns['wirecloud.admin_organization_group_entry'], ['group_name'], prefix)),
            AjaxEndpoint(id='TAB_COLLECTION',
                         url=build_url_template(url_patterns['wirecloud.tab_collection'], ['workspace_id'], prefix)),
            AjaxEndpoint(id='TAB_ENTRY',
                         url=build_url_template(url_patterns['wirecloud.tab_entry'], ['workspace_id', 'tab_id'],
                                                prefix)),
            AjaxEndpoint(id='TAB_PREFERENCES',
                         url=build_url_template(url_patterns['wirecloud.tab_preferences'], ['workspace_id', 'tab_id'],
                                                prefix)),
            AjaxEndpoint(id='THEME_ENTRY',
                         url=build_url_template(url_patterns['wirecloud.theme_entry'], ['name'], prefix)),
            AjaxEndpoint(id='WIRING_ENTRY',
                         url=build_url_template(url_patterns['wirecloud.workspace_wiring'], ['workspace_id'], prefix)),
            AjaxEndpoint(id='OPERATOR_VARIABLES_ENTRY',
                         url=build_url_template(url_patterns['wirecloud.operator_variables'],
                                                ['workspace_id', 'operator_id'], prefix)),
            AjaxEndpoint(id='WORKSPACE_COLLECTION',
                         url=build_url_template(url_patterns['wirecloud.workspace_collection'], [], prefix)),
            AjaxEndpoint(id='WORKSPACE_ENTRY_OWNER_NAME',
                         url=build_url_template(url_patterns['wirecloud.workspace_entry_owner_name'], ['owner', 'name'],
                                                prefix)),
            AjaxEndpoint(id='WORKSPACE_ENTRY',
                         url=build_url_template(url_patterns['wirecloud.workspace_entry'], ['workspace_id'], prefix)),
            AjaxEndpoint(id='WORKSPACE_MERGE',
                         url=build_url_template(url_patterns['wirecloud.workspace_merge'], ['to_ws_id'], prefix)),
            AjaxEndpoint(id='WORKSPACE_PREFERENCES',
                         url=build_url_template(url_patterns['wirecloud.workspace_preferences'], ['workspace_id'],
                                                prefix)),
            AjaxEndpoint(id='WORKSPACE_PUBLISH',
                         url=build_url_template(url_patterns['wirecloud.workspace_publish'], ['workspace_id'], prefix)),
            AjaxEndpoint(id='WORKSPACE_RESOURCE_COLLECTION',
                         url=build_url_template(url_patterns['wirecloud.workspace_resource_collection'],
                                                ['workspace_id'], prefix)),
            AjaxEndpoint(id='WORKSPACE_VIEW',
                         url=build_url_template(url_patterns['wirecloud.workspace_view'], ['owner', 'name'], prefix)),
        )

        return endpoints

    def get_widget_api_extensions(self, view: str, features: list[str]) -> list[str]:
        extensions = ['js/WirecloudAPI/StyledElements.js']

        if 'DashboardManagement' in features:
            extensions.append('js/WirecloudAPI/DashboardManagementAPI.js')

        if 'ComponentManagement' in features:
            extensions.append('js/WirecloudAPI/ComponentManagementAPI.js')

        return extensions

    def get_operator_api_extensions(self, view: str, features: list[str]) -> list[str]:
        extensions = []

        if 'DashboardManagement' in features:
            extensions.append('js/WirecloudAPI/DashboardManagementAPI.js')

        if 'ComponentManagement' in features:
            extensions.append('js/WirecloudAPI/ComponentManagementAPI.js')

        return extensions

    def get_proxy_processors(self) -> tuple[str, ...]:
        return ('wirecloud.proxy.processors.SecureDataProcessor',)

    def get_openapi_extra_schemas(self) -> dict[str, dict[str, Any]]:
        return {
            "ResourceCreateData": ResourceCreateData.model_json_schema(),
            "ResourceCreateFormData": ResourceCreateFormData.model_json_schema(),
        }

    def get_management_commands(self, subparsers: _SubParsersAction) -> dict[str, Callable]:
        return setup_commands(subparsers)

    async def populate(self, db: DBSession, wirecloud_user: UserAll) -> bool:
        updated = False

        updated |= await populate_component(db, wirecloud_user, "WireCloud", "workspace-browser", "0.1.4a1",
                                           WORKSPACE_BROWSER_FILE)

        if await get_workspace_by_username_and_name(db, "wirecloud", "home") is None:
            updated = True

            logger.info("Creating a initial version of the wirecloud/home workspace...")
            await create_workspace(db, None, wirecloud_user, WgtFile(INITIAL_HOME_DASHBOARD_FILE),
                                   searchable=False, public=True)
            logger.info("DONE")

        updated |= await populate_component(db, wirecloud_user, "CoNWeT", "markdown-viewer", "0.1.1",
                                           MARKDOWN_VIEWER_FILE)
        updated |= await populate_component(db, wirecloud_user, "CoNWeT", "markdown-editor", "0.1.0",
                                           MARKDOWN_EDITOR_FILE)

        if await get_workspace_by_username_and_name(db, "wirecloud", "landing") is None:
            updated = True

            logger.info("Creating a initial version of the wirecloud/landing workspace...")
            await create_workspace(db, None, wirecloud_user, WgtFile(LANDING_DASHBOARD_FILE),
                                   searchable=False, public=True)
            logger.info("DONE")

        return updated
