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

from typing import Any, Optional, Union
from fastapi import Request, Response

from wirecloud.catalogue.crud import get_catalogue_resource, get_catalogue_resource_by_id
from wirecloud.catalogue.schemas import CatalogueResource
from wirecloud.commons.auth.schemas import User, UserAll
from wirecloud.commons.utils.http import NotFound, build_error_response
from wirecloud.commons.utils.template.schemas.macdschemas import MACDWidget, MACDProperty, MACDPreference
from wirecloud.database import DBSession
from wirecloud.platform.iwidget.models import WidgetVariables, WidgetInstance, WidgetLayout, WidgetPermissionsConfig
from wirecloud.platform.iwidget.schemas import WidgetInstanceDataUpdate, WidgetInstanceDataCreate, WidgetLayoutUpdate
from wirecloud.platform.workspace.models import Workspace, Tab
from wirecloud.translation import gettext as _

def parse_value_from_text(info: dict, value) -> Any:
    if info['type'] == 'boolean':
        return value.strip().lower() in ('true', '1', 'on')
    elif info['type'] == 'number':
        try:
            return float(value)
        except ValueError:
            try:
                return float(info['default'])
            except (KeyError, ValueError):
                return 0
    else:
        return str(value)


def process_initial_value(vardef: Union[MACDProperty, MACDPreference],
                          initial_value: Union[str, WidgetVariables, None] = None) -> Any:
    if (isinstance(vardef, MACDProperty) or not vardef.readonly) and initial_value is not None:
        value = initial_value
    elif vardef.value is not None:
        value = vardef.value
    elif vardef.default:
        value = parse_value_from_text(vardef.model_dump(), vardef.default)
    else:
        value = ''

    return value


async def update_widget_value(db: DBSession, iwidget: WidgetInstance, data: Union[WidgetInstanceDataCreate, WidgetInstanceDataUpdate], user: UserAll,
                              required: bool = False) -> Optional[CatalogueResource]:
    if data.widget != '' and data.widget is not None:
        (widget_vendor, widget_name, widget_version) = data.widget.split('/')
        resource = await get_catalogue_resource(db, widget_vendor, widget_name, widget_version)
        if resource is None:
            raise ValueError(_('Widget not found'))

        if not resource.is_available_for(user):
            raise NotFound(_('Widget not available'))

        if resource.resource_type() != 'widget':
            raise ValueError(_('%(uri)s is not a widget') % {"uri": data.widget})

        iwidget.resource = resource.id
        iwidget.widget_uri = f"{widget_vendor}/{widget_name}/{widget_version}"
        return resource

    elif required:
        raise ValueError('Missing widget info')

    return None


async def update_title_value(db: DBSession, iwidget: WidgetInstance, data: Union[WidgetInstanceDataCreate, WidgetInstanceDataUpdate]) -> None:
    if data.title is not None:
        if data.title.strip() == '':
            resource = await get_catalogue_resource_by_id(db, iwidget.resource)
            iwidget_info = resource.get_processed_info()
            iwidget.title = iwidget_info.title
        else:
            iwidget.title = data.title


def update_boolean_value(model: WidgetPermissionsConfig, data: WidgetInstanceDataUpdate, field: str) -> None:
    value = getattr(data, field)

    if value is None:
        return

    if not isinstance(value, bool):
        raise TypeError(_(f'Field %(field)s must contain a boolean value') % {"field": field})

    setattr(model, field, value)


def update_permissions(iwidget: WidgetInstance, data: WidgetInstanceDataUpdate) -> None:
    permissions = iwidget.permissions.viewer
    if data.move is not None:
        update_boolean_value(permissions, data, 'move')

async def set_initial_values(db: DBSession, iwidget: WidgetInstance,
                             initial_values: dict[str, Union[str, WidgetVariables]], iwidget_info: MACDWidget,
                             user: User) -> None:
    for vardef in (iwidget_info.preferences + iwidget_info.properties):
        if vardef.name in initial_values:
            initial_value = initial_values[vardef.name]
        else:
            initial_value = None
        await iwidget.set_variable_value(db, vardef.name, process_initial_value(vardef, initial_value), user)


def update_layouts(iwidget: WidgetInstance, layouts: dict[str, Optional[WidgetLayoutUpdate]]) -> None:
    # For each key -> value: value is None deletes iwidget.layouts[key] (ignore if missing); otherwise merge
    # the non-None fields of the update into the existing WidgetLayout (or into a fresh WidgetLayout() when
    # the key is new). Invalid (non-decimal) keys are rejected by the schema itself (422).
    for key, value in layouts.items():
        if value is None:
            iwidget.layouts.pop(key, None)
            continue

        current = iwidget.layouts.get(key, WidgetLayout())
        changes = value.model_dump(exclude_none=True)
        iwidget.layouts[key] = current.model_copy(update=changes)


def first_id_widget_instance(widgets: dict[str, WidgetInstance]) -> int:
    used = {int(widget.id.split("-")[2]) for widget in widgets.values()}
    i = 0
    while i in used:
        i += 1
    return i

async def save_widget_instance(db: DBSession, workspace: Workspace, iwidget: WidgetInstanceDataCreate, user: UserAll, tab: Tab,
                       initial_variable_values: dict[str, WidgetVariables] = None,
                       commit: bool = True, resource_owner: Optional[UserAll] = None) -> WidgetInstance:

    new_iwidget = WidgetInstance(
        id=tab.id + '-' + str(first_id_widget_instance(tab.widgets)),
        permissions=iwidget.permissions,
        widget_uri=iwidget.widget
    )
    resource = await update_widget_value(db, new_iwidget, iwidget, resource_owner if resource_owner is not None else user, required=True)
    iwidget_info = resource.get_processed_info()
    new_iwidget.title = iwidget_info.title

    new_iwidget.layouts = dict(iwidget.layouts)

    if initial_variable_values is not None:
        await set_initial_values(db, new_iwidget, initial_variable_values, iwidget_info, user)

    await update_title_value(db, new_iwidget, iwidget)

    if commit:
        tab.widgets[new_iwidget.id] = new_iwidget
        from wirecloud.platform.workspace.crud import change_tab
        await change_tab(db, user, workspace, tab)

    return new_iwidget


def get_widget_instances_from_workspace(workspace: Workspace) -> list[WidgetInstance]:
    return [widget for tab in workspace.tabs.values() for widget in tab.widgets.values()]


async def update_widget_instance(db: DBSession, request: Request,  data: WidgetInstanceDataUpdate, user: UserAll, workspace: Workspace, tab: Tab, update_cache: bool = True) -> Optional[Response]:
    if data.id is None:
        raise ValueError('Missing id field')

    try:
        iwidget = tab.widgets[data.id]
    except KeyError:
        return build_error_response(request, 404, _("Widget Instance not found"))

    await update_widget_value(db, iwidget, data, user)
    await update_title_value(db, iwidget, data)

    update_permissions(iwidget, data)

    if data.layouts is not None:
        update_layouts(iwidget, data.layouts)

    if data.tab is not None:
        if data.tab not in workspace.tabs:
            return build_error_response(request, 404, _("Tab not found"))
        if data.tab != tab.id:
            del workspace.tabs[tab.id].widgets[iwidget.id]
            iwidget.id = str(data.tab) + '-' + str(first_id_widget_instance(workspace.tabs[data.tab].widgets))
            workspace.tabs[data.tab].widgets[iwidget.id] = iwidget

        else:
            workspace.tabs[tab.id].widgets[iwidget.id] = iwidget
    else:
        workspace.tabs[tab.id].widgets[iwidget.id] = iwidget

    if update_cache:
        from wirecloud.platform.workspace.crud import change_workspace
        await change_workspace(db, workspace, user)
