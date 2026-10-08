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

from typing import Optional, Union
from bson import ObjectId
from fastapi import Request

from wirecloud.catalogue.crud import get_catalogue_resource
from wirecloud.commons.auth.crud import get_user_by_id, get_user_with_all_info
from wirecloud.commons.auth.schemas import UserAll, User
from wirecloud.commons.utils.db import save_alternative
from wirecloud.commons.utils.template import TemplateParser
from wirecloud.commons.utils.template.parsers import TemplateValueProcessor
from wirecloud.commons.utils.template.schemas.macdschemas import MACType
from wirecloud.commons.utils.urlify import URLify
from wirecloud.database import DBSession
from wirecloud.platform.context.utils import get_context_values
from wirecloud.platform.iwidget.models import WidgetLayout
from wirecloud.platform.iwidget.schemas import WidgetInstanceData
from wirecloud.platform.iwidget.utils import save_widget_instance, set_initial_values
from wirecloud.platform.preferences.crud import update_workspace_preferences, update_tab_preferences
from wirecloud.platform.preferences.schemas import WorkspacePreference, TabPreference
from wirecloud.platform.wiring.schemas import WiringConnectionEndpoint, WiringType, WiringConnection, \
    WiringComponents, WiringVisualDescription, WiringVisualDescriptionConnection, WiringBehaviour
from wirecloud.platform.wiring.utils import get_endpoint_name, is_empty_wiring
from wirecloud.platform.workspace.crud import change_workspace, \
    is_a_workspace_with_that_name, insert_workspace
from wirecloud.platform.workspace.models import Workspace, WorkspaceExtraPreference, WorkspaceForcedValue, \
    WorkspaceWiringOperator, WorkspaceAccessPermissions
from wirecloud.platform.workspace.schemas import IdMapping, WorkspaceForcedValues, IdMappingOperator, \
    IdMappingWidget
from wirecloud.platform.workspace.utils import create_tab
from wirecloud.translation import gettext as _


class MissingDependencies(Exception):

    def __init__(self, missing_dependencies):
        self.missing_dependencies = missing_dependencies

    def __str__(self):
        return _('Missing dependencies')


async def check_mashup_dependencies(db: DBSession, template: TemplateParser, user: UserAll) -> None:
    missing_dependencies = set()
    dependencies = template.get_resource_dependencies()
    for dependency in dependencies:
        (vendor, name, version) = dependency.split('/')

        catalogue_resource = await get_catalogue_resource(db, vendor, name, version)
        if catalogue_resource is None:
            missing_dependencies.add(dependency)
        elif not catalogue_resource.is_available_for(user):
            raise ValueError('User does not have access to the resource')

    if len(missing_dependencies) > 0:
        raise MissingDependencies(list(missing_dependencies))


def map_id(endpoint_view: WiringConnectionEndpoint, id_mapping: IdMapping) -> str:
    if endpoint_view.type == WiringType.widget:
        return id_mapping.widget[endpoint_view.id].id
    else:
        return id_mapping.operator[endpoint_view.id].id


def is_valid_connection(connection: WiringConnection, id_mapping: IdMapping) -> bool:
    def is_valid_endpoint(endpoint: WiringConnectionEndpoint) -> bool:
        if endpoint.type == WiringType.widget:
            return endpoint.id in id_mapping.widget
        else:
            return endpoint.id in id_mapping.operator

    return is_valid_endpoint(connection.source) and is_valid_endpoint(connection.target)


def _remap_component_ids(id_mapping: IdMapping, components_description: WiringComponents,
                         isGlobal: bool = False) -> None:
    operators = {}
    for key, operator in components_description.operator.items():
        if key in id_mapping.operator:
            operators[id_mapping.operator[key].id] = operator
    components_description.operator = operators

    widgets = {}
    for key, widget in components_description.widget.items():
        if key in id_mapping.widget:
            if isGlobal:
                widget.name = id_mapping.widget[key].name
            widgets[id_mapping.widget[key].id] = widget
    components_description.widget = widgets


def _create_new_behaviour(mashup_description: WiringVisualDescription, title: str, description: str) -> None:
    operators = {}
    for key, operator in mashup_description.components.operator.items():
        operators[key] = {}

    widgets = {}
    for key, widget in mashup_description.components.widget.items():
        widgets[key] = {}

    connections = []
    for connection in mashup_description.connections:
        connections.append(WiringVisualDescriptionConnection(
            sourcename=connection.sourcename,
            targetname=connection.targetname
        ))

    mashup_description.behaviours.append(WiringBehaviour(
        title=title,
        description=description,
        components=WiringComponents(
            operator=operators,
            widget=widgets
        ),
        connections=connections
    ))


def _remap_connection_endpoints(source_mapping: dict, target_mapping: dict,
                                description: Union[WiringVisualDescription, WiringBehaviour]) -> None:
    connections = []

    for connection in description.connections:
        if connection.sourcename in source_mapping and connection.targetname in target_mapping:
            new_connection = connection
            new_connection.sourcename = source_mapping[connection.sourcename]
            new_connection.targetname = target_mapping[connection.targetname]
            connections.append(new_connection)

    description.connections = connections


async def fill_workspace_using_template(db: DBSession, request: Request, user_func: User, workspace: Workspace,
                                        template: TemplateParser, resource_owner: Optional[UserAll] = None) -> None:
    from wirecloud.platform.widget.utils import get_or_add_widget_from_catalogue
    user = workspace.creator

    if template.get_resource_type() != MACType.mashup:
        raise TypeError(_('Unsupported resource type %(type)s') % {"type": template.get_resource_type()})

    context_values = await get_context_values(db, workspace, request,
                                              await get_user_with_all_info(db, workspace.creator))
    processor = TemplateValueProcessor(context={'user': str(user), 'context': context_values})

    mashup_description = template.get_resource_info()  # MACDMashup

    new_values = {}
    id_mapping = IdMapping(
        widget={},
        operator={}
    )

    for preference_name in mashup_description.preferences:
        if preference_name in ('public', 'sharelist'):
            continue
        new_values[preference_name] = WorkspacePreference(
            inherit=False,
            value=mashup_description.preferences[preference_name]
        )

    if len(new_values) > 0:
        await update_workspace_preferences(db, user_func, workspace, new_values)

    new_forced_values = WorkspaceForcedValues(
        extra_prefs=[],
        ioperator={},
        iwidget={}
    )
    for param in mashup_description.params:
        extra_pref = WorkspaceExtraPreference(
            name=param.name,
            inheritable=False,
            label=param.label,
            type=param.type,
            description=param.description,
            required=param.required
        )
        new_forced_values.extra_prefs.append(extra_pref)

    for tab_entry in mashup_description.tabs:
        tab = await create_tab(db, user_func, tab_entry.title, workspace, name=tab_entry.name, allow_renaming=True)

        new_values = {}
        for preference_name in tab_entry.preferences:
            new_values[preference_name] = TabPreference(
                inherit=False,
                value=tab_entry.preferences[preference_name]
            )
        if len(new_values) > 0:
            await update_tab_preferences(db, user_func, workspace, tab, new_values)

        for resource in tab_entry.resources:
            user_all = await get_user_with_all_info(db, user)
            result = await get_or_add_widget_from_catalogue(db, resource.vendor, resource.name, resource.version,
                                                            resource_owner if resource_owner is not None else user_all)

            widget = result[0]
            widget_resource = result[1]

            iwidget_data = WidgetInstanceData(
                widget=widget_resource.local_uri_part,
                title=resource.title,
                layouts={
                    screen_size_id: WidgetLayout(**layout.model_dump())
                    for screen_size_id, layout in resource.layouts.items()
                }
            )

            iwidget = await save_widget_instance(db, workspace, iwidget_data, user_all,
                                                 tab, commit=False, resource_owner=resource_owner)
            if resource.readonly:
                iwidget.readonly = True

            initial_variable_values = {}
            iwidget_forced_values = {}
            iwidget_info = widget_resource.get_processed_info(process_variables=True)
            for prop_name in resource.properties:
                prop = resource.properties[prop_name]
                read_only = prop.readonly
                if prop.value is not None:
                    value = prop.value
                else:
                    value = iwidget_info.variables.properties[prop_name].default
                if read_only:
                    iwidget_forced_values[prop_name] = WorkspaceForcedValue(value=value)
                else:
                    initial_variable_values[prop_name] = processor.process(value)

            for pref_name in resource.preferences:
                pref = resource.preferences[pref_name]
                read_only = pref.readonly
                if pref.value is not None:
                    value = pref.value
                else:
                    value = iwidget_info.variables.preferences[pref_name].default

                if read_only:
                    iwidget_forced_values[pref_name] = WorkspaceForcedValue(value=value, hidden=pref.hidden)
                else:
                    initial_variable_values[pref_name] = processor.process(value)

            await set_initial_values(db, iwidget, initial_variable_values, iwidget_info,
                                     await get_user_by_id(db, workspace.creator))
            workspace.tabs[tab.id].widgets[iwidget.id] = iwidget

            if len(iwidget_forced_values) > 0:
                new_forced_values.iwidget[str(iwidget.id)] = iwidget_forced_values
            id_mapping.widget[resource.id] = IdMappingWidget(
                id=iwidget.id,
                name=resource.vendor + '/' + resource.name + '/' + resource.version
            )

    # wiring
    max_id = 0

    for id_ in workspace.wiring_status.operators.keys():
        if int(id_) > max_id:
            max_id = int(id_)

    # Process operators info
    for operator_id, operator in mashup_description.wiring.operators.items():
        max_id += 1
        new_id = str(max_id)
        id_mapping.operator[operator_id] = IdMappingOperator(
            id=new_id
        )

        workspace.wiring_status.operators[new_id] = WorkspaceWiringOperator(
            id=new_id,
            name=operator.name,
            preferences=operator.preferences,
            properties={}
        )
        ioperator_forced_values = {}
        for pref_id, pref in operator.preferences.items():
            if pref.readonly:
                ioperator_forced_values[pref_id] = WorkspaceForcedValue(value=pref.value, hidden=pref.hidden)

            workspace.wiring_status.operators[new_id].preferences[pref_id].value = {
                'users': {str(workspace.creator): pref.value}}

        if len(ioperator_forced_values) > 0:
            new_forced_values.ioperator[new_id] = ioperator_forced_values

    # Remap connection id
    source_mapping = {}
    target_mapping = {}
    for connection in mashup_description.wiring.connections:
        if not is_valid_connection(connection, id_mapping):
            continue

        old_source_name = get_endpoint_name(connection.source)
        old_target_name = get_endpoint_name(connection.target)

        connection.source.id = map_id(connection.source, id_mapping)
        connection.target.id = map_id(connection.target, id_mapping)

        source_mapping[old_source_name] = get_endpoint_name(connection.source)
        target_mapping[old_target_name] = get_endpoint_name(connection.target)

        # Add new connection
        workspace.wiring_status.connections.append(connection)

    # Merging visual description
    _remap_component_ids(id_mapping, mashup_description.wiring.visualdescription.components, isGlobal=True)
    _remap_connection_endpoints(source_mapping, target_mapping, mashup_description.wiring.visualdescription)

    # Remap mashup description behaviours ids
    if len(mashup_description.wiring.visualdescription.behaviours) != 0:
        for behaviour in mashup_description.wiring.visualdescription.behaviours:
            _remap_component_ids(id_mapping, behaviour.components)
            _remap_connection_endpoints(source_mapping, target_mapping, behaviour)

    if len(workspace.wiring_status.visualdescription.behaviours) != 0 or len(
            mashup_description.wiring.visualdescription.behaviours) != 0:
        if len(workspace.wiring_status.visualdescription.behaviours) == 0 and not is_empty_wiring(
                workspace.wiring_status.visualdescription):
            # Preserve both global descriptions by naming the original one explicitly.
            _create_new_behaviour(workspace.wiring_status.visualdescription, _("Original wiring"),
                                  _("This is the wiring description of the original workspace"))
        if len(mashup_description.wiring.visualdescription.behaviours) == 0:
            _create_new_behaviour(mashup_description.wiring.visualdescription, _("Merged wiring"),
                                  _("This is the wiring description of the merged mashup"))

        workspace.wiring_status.visualdescription.behaviours += mashup_description.wiring.visualdescription.behaviours

    # Merge global behaviour components and connections
    workspace.wiring_status.visualdescription.components.operator.update(
        mashup_description.wiring.visualdescription.components.operator)
    workspace.wiring_status.visualdescription.components.widget.update(
        mashup_description.wiring.visualdescription.components.widget)
    workspace.wiring_status.visualdescription.connections += mashup_description.wiring.visualdescription.connections

    # Forced Values
    workspace.forced_values.extra_prefs += new_forced_values.extra_prefs
    workspace.forced_values.widget.update(new_forced_values.iwidget)
    workspace.forced_values.operator.update(new_forced_values.ioperator)

    await change_workspace(db, workspace, user_func)


async def build_workspace_from_template(db: DBSession, request: Request, template: TemplateParser, user: UserAll,
                                        allow_renaming: bool = False, new_name: Optional[str] = None,
                                        new_title: Optional[str] = None, searchable: bool = True,
                                        public: bool = False, resource_owner: Optional[UserAll] = None) -> Optional[Workspace]:
    if (new_name is None or new_name.strip() == '') and (new_title is None or new_title.strip() == ''):
        processed_info = template.get_resource_processed_info(process_urls=False)
        new_name = processed_info.name
        new_title = processed_info.title
    elif new_title is None or new_title.strip() == '':
        new_title = new_name
    elif new_name is None or new_name.strip() == '':
        new_name = URLify(new_title)

    workspace = Workspace(
        id=ObjectId(),
        name=new_name,
        title=new_title,
        creator=user.id,
        public=public,
        searchable=searchable,
        users=[WorkspaceAccessPermissions(id=user.id)]
    )
    if allow_renaming:
        await save_alternative(db, 'workspaces', 'name', workspace)
    else:
        if await is_a_workspace_with_that_name(db, workspace.name, user.id):
            return None
        await insert_workspace(db, workspace)

    await fill_workspace_using_template(db, request, user, workspace, template, resource_owner=resource_owner)

    return workspace
