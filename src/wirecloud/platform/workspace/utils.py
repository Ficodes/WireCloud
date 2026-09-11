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

import base64
import json
import os
from copy import deepcopy
from typing import Any, Union, Optional
from fastapi import Request, Response

import markdown
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from wirecloud.catalogue.crud import get_catalogue_resource_by_id, get_catalogue_resource
from wirecloud.catalogue.schemas import CatalogueResource
from wirecloud.commons.auth.crud import get_username_by_id, get_user_by_id, get_group_by_id, get_user_with_all_info
from wirecloud.commons.utils.cache import CacheableData, check_if_modified_since, patch_cache_headers
from wirecloud.commons.utils.html import clean_html
from wirecloud.commons.utils.http import build_error_response
from wirecloud.commons.utils.template.parsers import TemplateValueProcessor
from wirecloud.commons.utils.template.schemas.macdschemas import MACDPreference, MACDProperty
from wirecloud.commons.utils.urlify import URLify
from wirecloud.database import DBSession, Id
from wirecloud.platform.context.utils import get_context_values
from wirecloud.platform.iwidget.models import WidgetVariables, WidgetInstance
from wirecloud.platform.iwidget.schemas import WidgetInstanceData
from wirecloud.platform.iwidget.utils import parse_value_from_text, get_widget_instances_from_workspace
from wirecloud.platform.preferences.schemas import WorkspacePreference
from wirecloud.platform.preferences.utils import get_workspace_preference_values, get_tab_preference_values
from wirecloud.commons.auth.schemas import User, UserAll
from wirecloud.settings import cache, SECRET_KEY
from wirecloud.platform.workspace.models import Workspace, Tab, WiringOperatorPreferenceValue
from wirecloud.platform.workspace.schemas import WorkspaceForcedValues, CacheEntry, CacheVariableData, \
    WorkspaceData, TabData, WorkspaceGlobalData, UserWorkspaceData, GroupWorkspaceData
from wirecloud.translation import gettext as _


def _variable_values_cache_key(workspace: Workspace, user: Optional[User]) -> str:
    return f'_variables_values_cache/{workspace.id}/{workspace.last_modified}/{user.id if user is not None else "anonymous"}'


def _workspace_cache_key(workspace: Workspace, user: Optional[User]) -> str:
    return f'_workspace_global_data/{workspace.id}/{workspace.last_modified}/{user.id if user is not None else "anonymous"}'


def encrypt_value(value: Any) -> str:
    key = SECRET_KEY[:32].encode("utf-8")
    iv = os.urandom(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    json_value = json.dumps(value, ensure_ascii=False).encode('utf-8')
    padded_value = pad(json_value, AES.block_size)
    encrypted = cipher.encrypt(padded_value)
    return base64.b64encode(iv + encrypted).decode('utf-8')


def decrypt_value(value: str) -> str:
    cipher = AES.new(SECRET_KEY[:32].encode('utf-8'), AES.MODE_ECB)
    try:
        value = cipher.decrypt(base64.b64decode(value))
        return json.loads(value.decode('utf-8'))
    except Exception:
        return ''


def process_forced_values(workspace: Workspace, user: Optional[User], concept_values: dict[str, dict[str, Any]],
                          preferences: dict[str, WorkspacePreference]) -> WorkspaceForcedValues:
    forced_values = deepcopy(workspace.forced_values)

    if len(forced_values.widget) == 0 and len(forced_values.operator) == 0:
        forced_values.empty_params = []
        return WorkspaceForcedValues(
            extra_prefs=forced_values.extra_prefs,
            ioperator=forced_values.operator,
            iwidget=forced_values.widget,
            empty_params=forced_values.empty_params
        )

    param_values = {}
    empty_params = []
    for param in forced_values.extra_prefs:
        if param.name in preferences and (not param.required or preferences[param.name].value.strip() != ''):
            param_values[param.name] = preferences[param.name].value
        else:
            empty_params.append(param.name)
            param_values[param.name] = ''
    forced_values.empty_params = empty_params

    processor = TemplateValueProcessor(context={'user': user, 'context': concept_values, 'params': param_values})

    collection = forced_values.widget
    for key in collection:
        values = collection[key]
        for var_name in values:
            collection[key][var_name].value = processor.process(values[var_name].value)

    collection = forced_values.operator
    for key in collection:
        values = collection[key]
        for var_name in values:
            collection[key][var_name].value = processor.process(values[var_name].value)

    return WorkspaceForcedValues(
        extra_prefs=forced_values.extra_prefs,
        ioperator=forced_values.operator,
        iwidget=forced_values.widget,
        empty_params=forced_values.empty_params
    )


def _process_variable(component_type: str, component_id: str, vardef: Union[MACDPreference, MACDProperty],
                      value: Union[WidgetVariables, dict], forced_values: WorkspaceForcedValues,
                      values_by_varname: dict[str, dict], current_user: Optional[User], workspace_creator: User) -> None:
    if isinstance(value, dict):
        value = WiringOperatorPreferenceValue(**value)

    varname = vardef.name
    entry = CacheEntry(
        type=vardef.type,
        secure=vardef.secure
    )

    if component_id in getattr(forced_values, component_type) and varname in getattr(forced_values, component_type)[component_id]:
        fv_entry = getattr(forced_values, component_type)[component_id][varname]

        entry.value = fv_entry.value
        if vardef.secure:
            entry.value = encrypt_value(entry.value)
        else:
            entry.value = parse_value_from_text(entry.model_dump(), entry.value)

        entry.readonly = True
        entry.hidden = fv_entry.hidden

    else:
        # Handle multiuser variables
        variable_user = current_user if vardef.multiuser else workspace_creator

        if value is None or value.users.get(str(variable_user.id if variable_user else "anonymous"), None) is None:
            value = parse_value_from_text(entry.model_dump(), vardef.default)
        else:
            value = value.users.get(str(variable_user.id if variable_user else "anonymous"), None)

        entry.value = value
        entry.readonly = False
        entry.hidden = False

    values_by_varname[component_type][component_id][varname] = entry


async def _populate_variables_values_cache(db: DBSession, workspace: Workspace, request: Optional[Request], user: Optional[UserAll],
                                           key: Any, forced_values=None):
    values_by_varname = {
        "ioperator": {},
        "iwidget": {}
    }
    if forced_values is None:
        context_values = await get_context_values(db, workspace, request, user)
        preferences = await get_workspace_preference_values(workspace)
        forced_values = process_forced_values(workspace, user, context_values, preferences)

    for iwidget in get_widget_instances_from_workspace(workspace):
        svariwidget = str(iwidget.id)
        values_by_varname["iwidget"][svariwidget] = {}

        if iwidget.resource is None:
            continue

        resource = await get_catalogue_resource_by_id(db, iwidget.resource)
        iwidget_info = resource.get_processed_info()

        for vardef in iwidget_info.preferences:
            value = iwidget.variables.get(vardef.name, None)
            _process_variable("iwidget", svariwidget, vardef, value, forced_values, values_by_varname, user,
                              await get_user_by_id(db, workspace.creator))

        for vardef in iwidget_info.properties:
            value = iwidget.variables.get(vardef.name, None)
            _process_variable("iwidget", svariwidget, vardef, value, forced_values, values_by_varname, user,
                              await get_user_by_id(db, workspace.creator))

    for operator_id, operator in workspace.wiring_status.operators.items():
        values_by_varname["ioperator"][operator_id] = {}
        vendor, name, version = operator.name.split('/')

        resource = await get_catalogue_resource(db, vendor, name, version)
        if resource is None:
            continue
        operator_info = resource.get_processed_info()
        for vardef in operator_info.preferences:
            value = operator.preferences[vardef.name].value
            _process_variable("ioperator", operator_id, vardef, value, forced_values, values_by_varname, user,
                              await get_user_by_id(db, workspace.creator))

        for vardef in operator_info.properties:
            value = operator.properties[vardef.name].value
            _process_variable("ioperator", operator_id, vardef, value, forced_values, values_by_varname, user,
                              await get_user_by_id(db, workspace.creator))

    await cache.set(key, values_by_varname)

    return values_by_varname


class VariableValueCacheManager:
    workspace: Optional[Workspace] = None
    user: Optional[UserAll] = None
    values = None
    forced_values = None

    def __init__(self, workspace: Workspace, user: Optional[UserAll], forced_values=None):
        self.workspace = workspace
        self.user = user
        self.forced_values = forced_values

    def _process_entry(self, entry: CacheEntry):
        if entry.secure:
            value = decrypt_value(entry.value)
            return parse_value_from_text(entry.model_dump(), value)
        else:
            return entry.value

    async def get_variable_values(self, db: DBSession, request: Optional[Request]):
        if self.values is None:
            key = _variable_values_cache_key(self.workspace, self.user)
            self.values = await cache.get(key)
            if self.values is None:
                self.values = await _populate_variables_values_cache(db, self.workspace, request, self.user, key,
                                                                     self.forced_values)

        return self.values

    async def get_variable_value_from_varname(self, db: DBSession, request: Optional[Request], component_type: str,
                                              component_id: str, var_name: str) -> str:
        values = await self.get_variable_values(db, request)
        entry = values[component_type][str(component_id)][var_name]
        return self._process_entry(entry)

    async def get_variable_data(self, db: DBSession, request: Optional[Request], component_type, component_id,
                                var_name) -> CacheVariableData:
        values = await self.get_variable_values(db, request)
        entry = values[component_type][str(component_id)][var_name]
        if entry.secure and entry.value != '':
            value = '********'
        else:
            value = entry.value

        return CacheVariableData(
            name=var_name,
            secure=entry.secure,
            readonly=entry.readonly,
            hidden=entry.hidden,
            value=value
        )


async def get_workspace_data(db: DBSession, workspace: Workspace, user: Optional[UserAll]) -> WorkspaceData:
    longdescription = workspace.longdescription
    if longdescription != '':
        longdescription = clean_html(markdown.markdown(longdescription, output_format='xhtml'))
    else:
        longdescription = workspace.description

    return WorkspaceData(
        id=str(workspace.id),
        name=workspace.name,
        title=workspace.title,
        public=workspace.public,
        shared=workspace.is_shared(),
        requireauth=workspace.requireauth,
        owner=await get_username_by_id(db, workspace.creator),
        removable=await workspace.is_editable_by(db, user) if user is not None else False,
        lastmodified=workspace.last_modified,
        description=workspace.description,
        longdescription=longdescription,
    )


def first_id_tab(tabs: dict[str, Tab]) -> int:
    used = {int(key.split("-")[-1]) for key in tabs.keys()}
    i = 0
    while i in used:
        i += 1
    return i

async def create_tab(db: DBSession, user: Optional[User], title: str, workspace: Workspace, name: str = None,
                     allow_renaming: bool = False) -> Tab:
    if name is None or name.strip() == '':
        name = URLify(title)

    visible = False
    tabs = workspace.tabs.copy()
    if len(tabs) == 0:
        visible = True

    # Creating tab
    id_tab = str(workspace.id) + '-' + str(first_id_tab(tabs))
    tab = Tab(
        id=id_tab,
        name=name,
        title=title,
        visible=visible
    )

    if allow_renaming:
        from wirecloud.commons.utils.db import save_alternative_tab
        tab = await save_alternative_tab(db, tab)

    workspace.tabs[id_tab] = tab
    from wirecloud.platform.workspace.crud import change_workspace
    await change_workspace(db, workspace, user)

    return tab


async def get_widget_instance_data(db: DBSession, request: Request, iwidget: WidgetInstance, workspace: Workspace,
                                   cache_manager: VariableValueCacheManager = None,
                                   user: Optional[UserAll] = None) -> WidgetInstanceData:
    data_ret = WidgetInstanceData(
        id=iwidget.id,
        title=iwidget.title,
        widget=iwidget.widget_uri,
        layouts=iwidget.layouts,
        read_only=iwidget.read_only,
        permissions=iwidget.permissions
    )

    if iwidget.resource is None:
        return data_ret

    resource = await get_catalogue_resource_by_id(db, iwidget.resource)
    if resource is None:
        # The widget used by this iwidget is missing
        return data_ret

    if cache_manager is None:
        cache_manager = VariableValueCacheManager(workspace, user)

    iwidget_info = resource.get_processed_info()
    data_ret.preferences = {
        preference.name: await cache_manager.get_variable_data(db, request, "iwidget", iwidget.id, preference.name) for
        preference in iwidget_info.preferences}
    data_ret.properties = {
        proper.name: await cache_manager.get_variable_data(db, request, "iwidget", iwidget.id, proper.name) for proper
        in iwidget_info.properties}

    return data_ret


async def get_tab_data(db: DBSession, request: Request, tab: Tab, workspace: Workspace = None,
                       cache_manager: VariableValueCacheManager = None, user: Optional[User] = None) -> TabData:
    if workspace is None:
        from wirecloud.platform.workspace.crud import get_workspace_by_id
        workspace = await get_workspace_by_id(db, Id(tab.id.split('-')[0]))

    if cache_manager is None:
        cache_manager = VariableValueCacheManager(workspace, user)

    return TabData(
        id=tab.id,
        name=tab.name,
        title=tab.title,
        visible=tab.visible,
        preferences=await get_tab_preference_values(tab),
        widgets=[
            await get_widget_instance_data(db, request, widget, workspace, cache_manager, user)
            for widget in tab.widgets.values()]
    )


async def _get_global_workspace_data(db: DBSession, request: Request, workspace: Workspace,
                                     user: Optional[UserAll]) -> WorkspaceGlobalData:
    workspace_data = await get_workspace_data(db, workspace, user)
    data_ret = WorkspaceGlobalData(**workspace_data.model_dump())

    # Workspace preferences
    preferences = await get_workspace_preference_values(workspace)
    data_ret.preferences = preferences

    if user and workspace.creator == user.id:
        for u in workspace.users:
            u_all = await get_user_with_all_info(db, u.id)
            if u_all is None:
                continue
            data_ret.users.append(UserWorkspaceData(
                fullname=u_all.get_full_name(),
                username=u_all.username,
                accesslevel="owner" if u.id == workspace.creator else "read"
            ))

        for g in workspace.groups:
            group = await get_group_by_id(db, g.id)
            if group is None:
                continue
            if group.is_organization:
                data_ret.users.append(UserWorkspaceData(
                    fullname=group.name,
                    username=group.name,
                    accesslevel="read",
                    organization=True,
                ))
            else:
                data_ret.groups.append(GroupWorkspaceData(
                    name=group.name,
                    organization=False,
                    accesslevel="read"
                ))

    concept_values = await get_context_values(db, workspace, request, user)
    forced_values = process_forced_values(workspace, user, concept_values, preferences)
    data_ret.empty_params = forced_values.empty_params
    data_ret.extra_prefs = forced_values.extra_prefs
    if len(forced_values.empty_params) > 0:
        return data_ret

    cache_manager = VariableValueCacheManager(workspace, user, forced_values)

    # Tabs processing
    tabs = workspace.tabs
    if len(tabs) == 0:
        tab = await create_tab(db, user, _('Tab'), workspace)
        tabs[tab.id] = tab

    data_ret.tabs = [
        await get_tab_data(db, request, tab, workspace=workspace, cache_manager=cache_manager, user=user) for tab in
        tabs.values()]
    data_ret.wiring = deepcopy(workspace.wiring_status)
    for operator_id, operator in data_ret.wiring.operators.items():
        try:
            (vendor, name, version) = operator.name.split('/')
        except ValueError:
            continue

        try:
            resource = await get_catalogue_resource(db, vendor, name, version)
            operator_info = resource.get_processed_info(process_variables=True)
            if not resource.is_available_for(user):
                raise ValueError()
        except ValueError:
            operator.preferences = {}
            operator.properties = {}
            continue

        operator_forced_values = forced_values.ioperator.get(operator_id, {})
        for preference_name, preference in operator.preferences.items():
            vardef = operator_info.variables.preferences.get(preference_name)
            value = preference.value

            variable_user = user if vardef is not None and vardef.multiuser else await get_user_with_all_info(db, workspace.creator)

            if preference_name in operator_forced_values:
                preference.value = operator_forced_values[preference_name].value
            elif value is None or value['users'].get(str(variable_user.id if variable_user else "anonymous"), None) is None:
                preference.value = parse_value_from_text(vardef.model_dump(), vardef.default)
            else:
                preference.value = value['users'].get(str(variable_user.id if variable_user else "anonymous"))

            if vardef is not None and vardef.secure:
                preference.value = '' if preference.value is None or decrypt_value(
                    preference.value) == '' else '********'

        for property_name, property in operator.properties.items():
            vardef = operator_info.variables.properties.get(property_name)
            value = property.value

            variable_user = user if vardef is not None and vardef.multiuser else workspace.creator

            if property_name in operator_forced_values:
                property.value = operator_forced_values[property_name].value
            elif value is None or value.users.get(str(variable_user.id if variable_user else "anonymous"), None) is None:
                property.value = parse_value_from_text(vardef.model_dump(), vardef.default)
            else:
                property.value = value.users.get(str(variable_user.id if variable_user else "anonymous"))

            if vardef is not None and vardef.secure:
                property.value = '' if property.value is None or decrypt_value(property.value) == '' else '********'

    return data_ret


async def get_global_workspace_data(db: DBSession, request: Request, workspace: Workspace,
                                    user: Optional[UserAll]) -> CacheableData:
    key = _workspace_cache_key(workspace, user)
    data = await cache.get(key)
    if data is None:
        workspace_data = await _get_global_workspace_data(db, request, workspace, user)
        data = CacheableData(data=workspace_data, timestamp=workspace.last_modified)
        key = _workspace_cache_key(workspace, user)
        await cache.set(key, data)

    return data


async def get_workspace_entry(db: DBSession, user: Optional[UserAll], request: Request, workspace: Optional[Workspace]) -> Response:
    if workspace is None:
        return build_error_response(request, 404, _("Workspace not found"))

    if not await workspace.is_accessible_by(db, user):
        return build_error_response(request, 403, _("You don't have permission to access this workspace"))

    last_modified = workspace.last_modified

    if not check_if_modified_since(request, last_modified):
        response = Response(status_code=304)
        patch_cache_headers(response, last_modified)
        return response

    workspace_data = await get_global_workspace_data(db, request, workspace, user)

    return workspace_data.get_response()


def is_there_a_tab_with_that_name(tab_name: str, tabs: dict[str, Tab]) -> bool:
    found = False
    for tab in tabs.values():
        if tab.name == tab_name:
            found = True
            break
    return found


def is_owner_or_has_permission(user: UserAll, workspace: Workspace, permission: str) -> bool:
    return workspace.creator == user.id or user.has_perm(permission)
