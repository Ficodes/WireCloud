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

from fastapi import Request
from typing import Optional

from wirecloud.catalogue.crud import get_catalogue_resource, get_catalogue_resource_by_id
from wirecloud.commons.auth.crud import get_username_by_id, get_user_with_all_info
from wirecloud.commons.utils.template.base import Contact
from wirecloud.commons.utils.template.schemas.macdschemas import MACDMashupWithParametrization, MACDTab, \
    MACDMashupEmbedded, MACDMashupWiring, IntegerStr, MACDParametrizationOptions, MACDParametrizationOptionsStatus, \
    MACDParametrizationOptionsSource, MACDMashupResourcePreference, MACDMashupResourcePropertyBase, \
    MACDMashupResourceLayout, MACDMashupResource
from wirecloud.database import DBSession
from wirecloud.platform.iwidget.models import WidgetInstance
from wirecloud.platform.wiring.schemas import WiringOperator, WiringOperatorPreference, WiringConnection, \
    WiringOutput, WiringInput
from wirecloud.platform.workspace.crud import get_workspace_description
from wirecloud.platform.workspace.models import Workspace
from wirecloud.platform.workspace.utils import VariableValueCacheManager
from wirecloud.commons.utils.template.writers import xml


async def process_widget_instance(db: DBSession, request: Optional[Request], iwidget: WidgetInstance, wiring: MACDMashupWiring,
                          parametrization: dict[IntegerStr, dict[str, MACDParametrizationOptions]],
                          read_only_widgets: bool, cache_manager: VariableValueCacheManager) -> MACDMashupResource:

    widget = await get_catalogue_resource_by_id(db, iwidget.resource)
    widget_description = widget.get_template().get_resource_info()
    iwidget_params = {}
    if iwidget.id in parametrization:
        iwidget_params = parametrization[iwidget.id]

    # input and output endpoints
    for output_endpoint in widget_description.wiring.outputs:
        aux_output = WiringOutput(
            name=output_endpoint.name,
            type=output_endpoint.type,
            label=output_endpoint.label,
            description=output_endpoint.description,
            friendcode=output_endpoint.friendcode
        )
        wiring.outputs.append(aux_output)

    for input_endpoint in widget_description.wiring.inputs:
        aux_input = WiringInput(
            name=input_endpoint.name,
            type=input_endpoint.type,
            label=input_endpoint.label,
            description=input_endpoint.description,
            friendcode=input_endpoint.friendcode,
            actionlabel=input_endpoint.actionlabel
        )
        wiring.inputs.append(aux_input)

    # preferences
    preferences = {}
    for pref in widget_description.preferences:
        status = MACDParametrizationOptionsStatus.normal
        if pref.name in iwidget_params:
            iwidget_param_desc = iwidget_params[pref.name]
            status = iwidget_param_desc.status
            source = iwidget_param_desc.source
            if source == MACDParametrizationOptionsSource.default:
                if status == MACDParametrizationOptionsStatus.normal:
                    continue
                value = None
            elif source == MACDParametrizationOptionsSource.current:
                value = await cache_manager.get_variable_value_from_varname(db, request, "iwidget", iwidget.id,
                                                                            pref.name)
            elif source == MACDParametrizationOptionsSource.custom:
                value = iwidget_param_desc.value
            else:
                raise Exception(f'Invalid preference value source: {source}')
        else:
            value = await cache_manager.get_variable_value_from_varname(db, request, "iwidget", iwidget.id, pref.name)

        if value is not None:
            if pref.type == 'boolean':
                value = str(value).lower()
            elif pref.type == 'number':
                value = str(value)
            preferences[pref.name] = MACDMashupResourcePreference(
                readonly=status != MACDParametrizationOptionsStatus.normal,
                hidden=status == MACDParametrizationOptionsStatus.hidden,
                value=value
            )

    # iwidget properties
    widget_properties = widget_description.properties
    properties = {}
    for prop in widget_properties:
        status = MACDParametrizationOptionsStatus.normal
        if prop.name in iwidget_params:
            iwidget_param_desc = iwidget_params[prop.name]
            status = iwidget_param_desc.status
            source = iwidget_param_desc.source
            if source == MACDParametrizationOptionsSource.default:
                if status == MACDParametrizationOptionsStatus.normal:
                    continue
                else:
                    value = None
            elif source == MACDParametrizationOptionsSource.current:
                value = await cache_manager.get_variable_value_from_varname(db, request, "iwidget", iwidget.id,
                                                                            prop.name)
            elif source == MACDParametrizationOptionsSource.custom:
                value = iwidget_param_desc.value
            else:
                raise Exception(f'Invalid preference value source: {source}')
        else:
            value = await cache_manager.get_variable_value_from_varname(db, request, "iwidget", iwidget.id,
                                                                        prop.name)

        properties[prop.name] = MACDMashupResourcePropertyBase(
            readonly=status != MACDParametrizationOptionsStatus.normal,
            value=value
        )

    layouts = {
        screen_size_id: MACDMashupResourceLayout(**layout.model_dump())
        for screen_size_id, layout in iwidget.layouts.items()
    }

    iwidget_data = MACDMashupResource(
        id=iwidget.id,
        vendor=widget.vendor,
        name=widget.short_name,
        version=widget.version,
        title=iwidget.title,
        readonly=read_only_widgets,
        properties=properties,
        preferences=preferences,
        layouts=layouts
    )

    return iwidget_data


async def build_json_template_from_workspace(db: DBSession, request: Optional[Request], options: MACDMashupWithParametrization,
                                             workspace: Workspace) -> MACDMashupWithParametrization:
    description = options.description.strip()
    if description == '':
        options.description = await get_workspace_description(db, workspace)

    if len(options.authors) == 0:
        options.authors.append(Contact(name=await get_username_by_id(db, workspace.creator)))

    cache_manager = VariableValueCacheManager(workspace, await get_user_with_all_info(db, workspace.creator))

    # WORKSPACE PREFERENCES
    options.preferences = {}
    for preference in workspace.preferences:
        if not preference.inherit and preference.name not in ("public", "sharelist"):
            options.preferences[preference.name] = preference.value

    # TABS AND THEIR PREFERENCES
    options.wiring.inputs = []
    options.wiring.outputs = []

    sorted_tabs = workspace.tabs

    aux_embedded = []

    for tab in sorted_tabs.values():
        preferences = {}
        for preference in tab.preferences:
            if not preference.inherit:
                preferences[preference.name] = preference.value
        resources = []
        for iwidget in tab.widgets.values():
            resource_info = await process_widget_instance(db, request, iwidget, options.wiring,
                                                  options.parametrization.iwidgets,
                                                  options.readOnlyWidgets, cache_manager)
            resources.append(resource_info)
            if options.embedmacs:
                embedded = '/'.join((resource_info.vendor, resource_info.name, resource_info.version))
                aux_embedded.append(embedded)

        tab_info = MACDTab(
            name=tab.name,
            preferences=preferences,
            resources=resources
        )
        if tab.title.strip() != '':
            tab_info.title = tab.title

        options.tabs.append(tab_info)

    if workspace.wiring_status.version != '2.0':
        raise ValueError("Only wiring version 2.0 is supported")

    wiring_status = workspace.wiring_status
    parametrization = options.parametrization
    for operator_id, operator in wiring_status.operators.items():

        operator_data = WiringOperator(
            id=operator_id,
            name=operator.name,
            preferences={}
        )

        vendor, name, version = operator.name.split('/')
        resource = await get_catalogue_resource(db, vendor, name, version)
        operator_info = resource.description
        operator_params = parametrization.ioperators.get(operator_id, {})
        for pref_index, preference in enumerate(operator_info.preferences):
            status = MACDParametrizationOptionsStatus.normal
            if preference.name in operator_params:
                ioperator_param_desc = operator_params[preference.name]
                status = ioperator_param_desc.status
                source = ioperator_param_desc.source
                if source == MACDParametrizationOptionsSource.default:
                    if status == MACDParametrizationOptionsStatus.normal:
                        continue
                    value = None
                elif source == MACDParametrizationOptionsSource.current:
                    value = await cache_manager.get_variable_value_from_varname(db, request, "ioperator", operator_id,
                                                                                preference.name)
                elif source == MACDParametrizationOptionsSource.custom:
                    value = ioperator_param_desc.value
                else:
                    raise Exception(f'Invalid preference value source: {source}')
            else:
                value = await cache_manager.get_variable_value_from_varname(db, request, "ioperator", operator_id,
                                                                            preference.name)

            operator_data.preferences[preference.name] = WiringOperatorPreference(
                readonly=status != MACDParametrizationOptionsStatus.normal,
                hidden=status == MACDParametrizationOptionsStatus.hidden,
                value=value
            )
            if value is not None:
                operator_data.preferences[preference.name].value = value

        options.wiring.operators[operator_id] = operator_data
        if options.embedmacs:
            options.embedded.append(operator.name)

    options.wiring.connections = []
    for connection in wiring_status.connections:
        conn = WiringConnection(
            source=connection.source,
            target=connection.target,
            readonly=options.readOnlyConnectables
        )
        options.wiring.connections.append(conn)

    options.wiring.visualdescription = wiring_status.visualdescription

    options.embedded = []
    for resource in aux_embedded:
        (vendor, name, version) = resource.split('/')
        embedded = MACDMashupEmbedded(
            vendor=vendor,
            name=name,
            version=version,
            src=f'macs/{vendor}_{name}_{version}.wgt'
        )
        options.embedded.append(embedded)

    options.embedmacs = False

    return options


async def build_xml_template_from_workspace(db: DBSession, request: Request, options: MACDMashupWithParametrization,
                                            workspace: Workspace, raw: bool = False) -> str:
    await build_json_template_from_workspace(db, request, options, workspace)

    return xml.write_xml_description(options, raw=raw)
