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

from copy import deepcopy
from typing import Union, Callable, TYPE_CHECKING
from fastapi import Request, Response

from wirecloud import settings
from wirecloud.settings import cache
from wirecloud.commons.auth.schemas import User, UserAll
from wirecloud.commons.utils.http import build_error_response, get_absolute_static_url, get_current_domain
from wirecloud.commons.utils.template.schemas.macdschemas import MACDRequirement
from wirecloud.database import DBSession
from wirecloud.platform.wiring.schemas import Wiring, WiringConnection, WiringConnectionEndpoint, WiringType, \
    WiringVisualDescriptionConnection, WiringVisualDescription, WiringBehaviour, WiringComponents, \
    WiringOperatorPreference
from wirecloud.translation import gettext as _

if TYPE_CHECKING:
    from wirecloud.platform.workspace.models import WorkspaceWiring, Workspace
    from wirecloud.catalogue.schemas import CatalogueResource


def remove_widget_from_wiring_status(id: str, status: Wiring) -> Wiring:
    def has_model_widget(connection: WiringConnection) -> bool:
        def check_endpoint(endpoint: WiringConnectionEndpoint) -> bool:
            return endpoint.type == WiringType.widget and ("%s" % endpoint.id) == id

        return check_endpoint(connection.source) or check_endpoint(connection.target)

    def has_view_widget(connection: WiringVisualDescriptionConnection) -> bool:
        def check_endpoint(endpoint: str) -> bool:
            c_type, c_id, e_name = tuple(endpoint.split('/'))
            return c_type == 'widget' and c_id == id

        return check_endpoint(connection.sourcename) or check_endpoint(connection.targetname)

    def remove_references(description: Union[Wiring, WiringVisualDescription, WiringBehaviour],
                          has_widget: Union[Callable[[WiringConnection], bool],
                          Callable[[WiringVisualDescriptionConnection], bool]]) -> None:
        if hasattr(description, 'components') and id in description.components.widget:
            del description.components.widget[id]

        for connection in [c for c in description.connections if has_widget(c)]:
            description.connections.remove(connection)

    remove_references(status, has_model_widget)

    remove_references(status.visualdescription, has_view_widget)

    for behaviour in status.visualdescription.behaviours:
        remove_references(behaviour, has_view_widget)

    return status


def get_endpoint_name(endpoint: WiringConnectionEndpoint):
    return "%s/%s/%s" % (endpoint.type, endpoint.id, endpoint.endpoint)


def rename_component_type(component_type: str) -> WiringType:
    if component_type in ['widget', 'operator']:
        return WiringType(component_type)
    else:
        raise ValueError("Invalid component type")


def get_behaviour_skeleton() -> WiringBehaviour:
    return WiringBehaviour(
        title="",
        description="",
        components=WiringComponents(widget={}, operator={}),
        connections=[]
    )


def get_wiring_skeleton() -> Wiring:
    return Wiring(
        version="2.0",
        connections=[],
        operators={},
        visualdescription=WiringVisualDescription(
            behaviours=[],
            components=WiringComponents(widget={}, operator={}),
            connections=[]
        )
    )


def is_empty_wiring(visual_info: WiringVisualDescription) -> bool:
    return len(visual_info.connections) == 0 and len(visual_info.components.operator) == 0 and len(
        visual_info.components.widget) == 0


def get_operator_cache_key(operator: 'CatalogueResource', domain: str, mode: str) -> str:
    return f'_operator_xhtml/1/{domain}/{operator.id}?mode={mode}'


async def get_operator_api_files(request: Request, theme: str) -> list[str]:
    from wirecloud.platform.core.plugins import get_version_hash
    key = f'operator_api_files/{get_current_domain(request)}?v={get_version_hash()}'
    operator_api_files = await cache.get(key)

    if operator_api_files is None or settings.DEBUG:
        operator_api_files = tuple([get_absolute_static_url(f"static/js/main-{theme}-operator.js", request=request, versioned=True)])
        await cache.set(key, operator_api_files)

    return list(operator_api_files)


async def generate_xhtml_operator_code(js_files: list[str], base_url: str, request: Request, requirements: list[str],
                                       mode: str) -> str:
    from wirecloud.platform.plugins import get_operator_api_extensions
    extra_api_js_files = [get_absolute_static_url(url, request=request, versioned=True) for url in
                          get_operator_api_extensions(mode, requirements)]
    from wirecloud.platform.routes import get_current_theme
    api_js = await get_operator_api_files(request, get_current_theme(request)) + extra_api_js_files

    context = {'request': request, 'base_url': base_url, 'js_files': api_js + js_files}

    from wirecloud.commons.templates.tags import templates
    return templates.TemplateResponse('operator_xhtml.html', context).body.decode('utf-8')


def handle_multiuser(user: User, secure: bool, new_variable: WiringOperatorPreference,
                     old_variable: WiringOperatorPreference):
    if secure:
        from wirecloud.platform.workspace.utils import encrypt_value
        new_value = encrypt_value(new_variable.value)
    else:
        new_value = new_variable.value

    new_variable = deepcopy(old_variable)
    from wirecloud.platform.workspace.models import WiringOperatorPreferenceValue
    if not isinstance(new_variable.value, WiringOperatorPreferenceValue):
        new_variable.value = WiringOperatorPreferenceValue(users={})
    new_variable.value.users[str(user.id)] = new_value
    return new_variable


def check_same_wiring(object1, object2) -> bool:
    if len(object1.keys()) != len(object2.keys()):
        return False
    for key in set(object1.keys()):
        if key == 'value':
            pass
        elif isinstance(object1[key], dict):
            if not check_same_wiring(object1[key], object2[key]):
                return False
        else:
            if not object1[key] == object2[key]:
                return False

    return True


async def check_multiuser_wiring(db: DBSession, request: Request, user: UserAll, new_wiring_status: 'WorkspaceWiring',
                                 old_wiring_status: 'WorkspaceWiring', workspace: 'Workspace', adding: bool, can_update_secure: bool = False) -> Union[Response, bool]:
    if not check_same_wiring(new_wiring_status, old_wiring_status):
        return build_error_response(request, 403, _('You are not allowed to update this workspace'))

    for operator_id, operator in new_wiring_status.operators.items():
        old_operator = old_wiring_status.operators[operator_id]

        vendor, name, version = operator.name.split("/")
        from wirecloud.catalogue.crud import get_catalogue_resource
        db_resource = await get_catalogue_resource(db, vendor, name, version)
        if db_resource is not None:
            resource = db_resource.get_processed_info(process_variables=True)
            operator_preferences = resource.variables.preferences
            operator_properties = resource.variables.properties
        else:
            # Missing operator variables can't be updated
            operator.properties = old_operator.properties
            operator.preferences = old_operator.preferences
            continue

        # Check preferences
        from wirecloud.platform.workspace.utils import is_owner_or_has_permission
        if (operator.preferences
                and not adding
                and not is_owner_or_has_permission(user, workspace, "WORKSPACE.OPERATOR.PREFERENCES.EDIT")
                and not user.is_superuser):
            return build_error_response(request, 403, _('You do not have permission to edit operator preferences'))

        for preference_name in operator.preferences:
            old_preference = old_operator.preferences[preference_name]
            new_preference = operator.preferences[preference_name]

            if preference_name in operator_preferences:
                pref = operator_preferences[preference_name]
                preference_secure = pref.secure
            else:
                preference_secure = False

            # Only multiuser variables can be updated
            if not preference_secure or can_update_secure:
                if old_preference != new_preference and old_preference.value.users[str(workspace.creator)] != new_preference.value:
                    return build_error_response(request, 403, _('You are not allowed to update this workspace'))

            operator.preferences[preference_name] = old_preference

        # Check properties
        if (operator.properties
                and not adding
                and not is_owner_or_has_permission(user, workspace, "WORKSPACE.OPERATOR.PROPERTIES.EDIT")
                and not user.is_superuser):
            return build_error_response(request, 403, _('You do not have permission to edit operator properties'))
        for property_name in operator.properties:
            old_property = old_operator.properties[property_name]
            new_property = operator.properties[property_name]

            # Check if its multiuser
            if property_name in operator_properties:
                prop = operator_properties[property_name]
                property_secure = prop.secure
                property_multiuser = prop.multiuser
            else:
                property_secure = False
                property_multiuser = False

            # Update variable value
            if property_secure and not can_update_secure:
                new_property.value = old_property.value
            else:
                if new_property.readonly and new_property.value != old_property.value:
                    return build_error_response(request, 403, _('Read only properties cannot be updated'))
                # Variables can only be updated if multiuser
                if not property_multiuser:
                    if old_property != new_property and old_property.value.users[str(workspace.creator)] != new_property.value:
                        return build_error_response(request, 403, _('You are not allowed to update this workspace'))
                    else:
                        new_property.value = old_property.value
                else:
                    # Handle multiuser
                    try:
                        if new_property.value.users is not None:
                            value = new_property.value.users.get(str(user.id), None)
                            if value is not None:
                                new_property.value = value
                            else:
                                new_property = old_property
                                continue
                    except (AttributeError, ValueError):
                        pass
                    new_property = handle_multiuser(user, property_secure, new_property, old_property)

            operator.properties[property_name] = new_property
    return True


async def check_wiring(db: DBSession, request: Request, user: UserAll, new_wiring_status: 'WorkspaceWiring',
                       old_wiring_status: 'WorkspaceWiring', workspace: 'Workspace', adding: bool = False, can_update_secure: bool = False) -> Union[Response, bool]:
    from wirecloud.platform.workspace.models import WiringOperatorPreferenceValue

    # Check read only connections
    old_read_only_connections = [connection for connection in old_wiring_status.connections if connection.readonly]
    new_read_only_connections = [connection for connection in new_wiring_status.connections if connection.readonly]

    if len(old_read_only_connections) > len(new_read_only_connections):
        return build_error_response(request, 403, _('You are not allowed to remove or update read only connections'))

    for connection in old_read_only_connections:
        if connection not in new_read_only_connections:
            return build_error_response(request, 403,
                                        _('You are not allowed to remove or update read only connections'))

    # Check operator preferences and properties
    for operator_id, operator in new_wiring_status.operators.items():
        old_operator = None
        if operator_id in old_wiring_status.operators:
            old_operator = old_wiring_status.operators[operator_id]
            added_preferences = set(operator.preferences.keys()) - set(old_operator.preferences.keys())
            removed_preferences = set(old_operator.preferences.keys()) - set(operator.preferences.keys())
            updated_preferences = {key for key in set(operator.preferences).intersection(old_operator.preferences)
                                   if operator.preferences[key] != old_operator.preferences[key]}

            added_properties = set(operator.properties.keys()) - set(old_operator.properties.keys())
            removed_properties = set(old_operator.properties.keys()) - set(operator.properties.keys())
            updated_properties = {key for key in set(operator.properties).intersection(old_operator.properties)
                                 if operator.properties[key] != old_operator.properties[key]}
        else:
            # New operator
            added_preferences = operator.preferences.keys()
            removed_preferences = ()
            updated_preferences = ()

            added_properties = operator.properties.keys()
            removed_properties = ()
            updated_properties = ()

        vendor, name, version = operator.name.split("/")
        from wirecloud.catalogue.crud import get_catalogue_resource
        db_resource = await get_catalogue_resource(db, vendor, name, version)
        if db_resource is not None:
            resource = db_resource.get_processed_info(process_variables=True)
            operator_preferences = resource.variables.preferences
            operator_properties = resource.variables.properties
        else:
            # Missing operator variables can't be updated
            operator.properties = old_operator.properties
            operator.preferences = old_operator.preferences
            continue

        # Handle preferences
        from wirecloud.platform.workspace.utils import is_owner_or_has_permission
        if ((added_preferences or removed_preferences or updated_preferences)
                and not adding
                and not is_owner_or_has_permission(user, workspace, "WORKSPACE.OPERATOR.PREFERENCES.EDIT")
                and not user.is_superuser):
            return build_error_response(request, 403, _('You do not have permission to edit operator preferences'))

        for preference_name in added_preferences:
            if operator.preferences[preference_name].readonly or operator.preferences[preference_name].hidden:
                return build_error_response(request, 403,
                                            _('Read only and hidden preferences cannot be created using this API'))

            # Handle multiuser
            new_preference = operator.preferences[preference_name]
            try:
                preference_secure = getattr(operator_preferences[preference_name], 'secure', False)
            except KeyError:
                preference_secure = False

            if preference_secure:
                from wirecloud.platform.workspace.utils import encrypt_value
                new_value = encrypt_value(new_preference.value)
            else:
                new_value = new_preference.value
            new_preference.value = WiringOperatorPreferenceValue(users={str(user.id): new_value})
            operator.preferences[preference_name] = new_preference

        for preference_name in removed_preferences:
            if old_operator.preferences[preference_name].readonly or old_operator.preferences[preference_name].hidden:
                return build_error_response(request, 403, _('Read only and hidden preferences cannot be removed'))

        for preference_name in updated_preferences:
            old_preference = old_operator.preferences[preference_name]
            new_preference = operator.preferences[preference_name]
            # Using patch means no change at all on non-modified preferences
            if old_preference == new_preference:
                continue

            # Check if its multiuser
            try:
                preference_secure = getattr(operator_preferences[preference_name], 'secure', False)
            except KeyError:
                preference_secure = False

            if old_preference.readonly != new_preference.readonly or old_preference.hidden != new_preference.hidden:
                return build_error_response(request, 403,
                                            _('Read only and hidden status cannot be changed using this API'))

            if new_preference.readonly and new_preference.value != old_preference.value:
                return build_error_response(request, 403, _('Read only preferences cannot be updated'))

            if preference_secure and not can_update_secure:
                new_preference.value = old_preference.value
            else:
                # Handle multiuser
                new_preference = handle_multiuser(user, preference_secure, new_preference, old_preference)
            operator.preferences[preference_name] = new_preference

        # Handle properties
        if ((added_properties or removed_properties or updated_properties)
                and not adding
                and not is_owner_or_has_permission(user, workspace, "WORKSPACE.OPERATOR.PROPERTIES.EDIT")
                and not user.is_superuser):
            return build_error_response(request, 403, _('You do not have permission to edit operator properties'))

        for property_name in added_properties:
            if operator.properties[property_name].readonly or operator.properties[property_name].hidden:
                return build_error_response(request, 403,
                                            _('Read only and hidden properties cannot be created using this API'))

            # Handle multiuser
            new_property = operator.properties[property_name]
            new_property.value = WiringOperatorPreferenceValue(users={str(user.id): new_property.value})
            operator.properties[property_name] = new_property

        for property_name in removed_properties:
            if old_operator.properties[property_name].readonly or old_operator.properties[property_name].hidden:
                return build_error_response(request, 403, _('Read only and hidden properties cannot be removed'))

        for property_name in updated_properties:
            old_property = old_operator.properties[property_name]
            new_property = operator.properties[property_name]
            # Using patch means no change at all on non-modified properties
            if old_property == new_property:
                continue

            # Check if its multiuser
            if property_name in operator_properties:
                prop = operator_properties[property_name]
                property_secure = prop.secure
            else:
                property_secure = False

            if old_property.readonly != new_property.readonly or old_property.hidden != new_property.hidden:
                return build_error_response(request, 403,
                                            _('Read only and hidden status cannot be changed using this API'))

            if new_property.readonly and new_property.value != old_property.value:
                return build_error_response(request, 403, _('Read only properties cannot be updated'))

            if property_secure and not can_update_secure:
                new_property.value = old_property.value
            else:
                # Handle multiuser
                new_property = handle_multiuser(user, property_secure, new_property, old_property)
            operator.properties[property_name] = new_property

    return True


def process_requirements(requirements: list[MACDRequirement]) -> list[str]:
    return [requirement.name for requirement in requirements]
