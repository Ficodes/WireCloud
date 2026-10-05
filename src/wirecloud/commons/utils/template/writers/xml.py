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

from lxml import etree
from typing import Union, Optional

from wirecloud.commons.utils.template.base import stringify_contact_info
from wirecloud.commons.utils.template.schemas.macdschemas import MACD, MACDMashup, MACType, \
    MACDMashupResourcePreference
from wirecloud.platform.wiring.schemas import WiringOperatorPreference, WiringVisualDescription, WiringBehaviour, \
    WiringVisualDescriptionConnection, WiringConnectionHandlePositionType, WiringComponents

from wirecloud.translation import gettext as _


def process_option(options, field: str, required: bool = False, type: str = 'string') -> Optional[str]:
    if getattr(options, field) is None:
        if required:
            raise Exception(_('Missing %s option') % field)
        else:
            return None
    else:
        if type == 'string':
            return str(getattr(options, field))
        elif type == 'boolean':
            return 'true' if getattr(options, field) else 'false'
        elif type == 'people':
            return stringify_contact_info(getattr(options, field))


def add_attribute(options, element: etree.Element, field: str, attr_name: Optional[str] = None,
                  default: Optional[str] = '', ignore_default: bool = True, **other_options) -> None:
    if attr_name is None:
        attr_name = field

    value = process_option(options, field, **other_options)
    if ignore_default and value == default:
        return
    elif value is not None:
        element.set(attr_name, value)


def add_attributes(options, element: etree.Element, attrs: tuple[str, ...], **other_options) -> None:
    for attr in attrs:
        add_attribute(options, element, attr, **other_options)


def add_element(options, element: etree.Element, field: str, attr_name: Optional[str] = None,
                default: Optional[str] = '', ignore_default: bool = True, **other_options) -> None:
    if attr_name is None:
        attr_name = field

    value = process_option(options, field, **other_options)
    if ignore_default and value == default:
        return
    elif value is not None:
        new_element = etree.SubElement(element, attr_name)
        new_element.text = value


def add_elements(options, element: etree.Element, attrs: tuple[str, ...], **other_options) -> None:
    for attr in attrs:
        add_element(options, element, attr, **other_options)


def add_preference_values(resource: etree.Element,
                          preferences: Union[dict[str, MACDMashupResourcePreference], dict[str, WiringOperatorPreference]]) -> None:
    for pref_name, pref in preferences.items():
        element = etree.SubElement(resource, 'preferencevalue', name=pref_name)
        add_attribute(pref, element, 'value', type='string', default=None, required=False)
        add_attributes(pref, element, ('readonly', 'hidden'), default='false', type='boolean')


def write_mashup_tree(doc: etree.Element, resources: etree.Element, options: MACDMashup) -> None:
    # Params
    if len(options.params) > 0:
        preferences = etree.SubElement(doc, 'preferences')
        for pref in options.params:
            pref_element = etree.SubElement(preferences, 'preference', name=pref.name)
            add_attributes(pref, pref_element, ('type', 'label', 'description', 'default'))
            add_attribute(pref, pref_element, 'readonly', default='false', type='boolean')
            add_attribute(pref, pref_element, 'required', default='true', type='boolean')

            if pref.value is not None:
                pref_element.set('value', pref.value)

    # Embedded resources
    if len(options.embedded) > 0:
        embedded_element = etree.SubElement(doc, 'embedded')
        for resource in options.embedded:
            etree.SubElement(
                embedded_element, 'resource',
                vendor=resource.vendor,
                name=resource.name,
                version=resource.version,
                src=resource.src
            )

    # Tabs & resources
    for tab_index, tab in enumerate(options.tabs):
        tab_element = etree.SubElement(resources, 'tab', name=tab.name, id=str(tab_index))

        if tab.title.strip() != "":
            tab_element.set('title', tab.title.strip())

        for preference_name, preference_value in tab.preferences.items():
            etree.SubElement(tab_element, 'preferencevalue', name=preference_name, value=preference_value)

        for iwidget in tab.resources:
            resource = etree.SubElement(tab_element, 'resource', id=iwidget.id, vendor=iwidget.vendor,
                                        name=iwidget.name, version=iwidget.version, title=iwidget.title)

            if iwidget.readonly:
                resource.set('readonly', 'true')

            layouts_elem = etree.SubElement(resource, 'layouts')
            for screen_size_id, layout in iwidget.layouts.items():
                layout_elem = etree.SubElement(layouts_elem, 'layout', screensize=str(screen_size_id),
                                               w=str(layout.w), h=str(layout.h))
                if layout.x is not None:
                    layout_elem.set('x', str(layout.x))
                if layout.y is not None:
                    layout_elem.set('y', str(layout.y))
                add_attributes(layout, layout_elem, ('minimized', 'fulldragboard'), default='false',
                               type='boolean')
                add_attributes(layout, layout_elem, ('titlevisible', 'visible'), default='true',
                               type='boolean')
                if layout.dock is not None:
                    layout_elem.set('dock', layout.dock)
                    layout_elem.set('dockmode', layout.dock_mode or 'overlay')
                    layout_elem.set('dockopen', str(layout.dock_open).lower())

            add_preference_values(resource, iwidget.preferences)

            for prop_name, prop in iwidget.properties.items():
                element = etree.SubElement(resource, 'variablevalue', name=prop_name)

                if prop.value is not None:
                    element.set('value', str(prop.value))

                if prop.readonly:
                    element.set('readonly', 'true')


def write_mashup_wiring_tree(mashup: etree.Element, options: MACDMashup) -> None:
    wiring = etree.SubElement(mashup, 'wiring')

    wiring.set('version', options.wiring.version)

    for op_id, operator in options.wiring.operators.items():
        (vendor, name, version) = operator.name.split('/')
        operator_element = etree.SubElement(wiring, 'operator', id=op_id, vendor=vendor, name=name,
                                            version=version)
        add_preference_values(operator_element, operator.preferences)

    for connection in options.wiring.connections:
        element = etree.SubElement(wiring, 'connection')
        if connection.readonly:
            element.set('readonly', 'true')

        etree.SubElement(element, 'source', type=connection.source.type.value, id=connection.source.id,
                         endpoint=connection.source.endpoint)
        etree.SubElement(element, 'target', type=connection.target.type.value, id=connection.target.id,
                         endpoint=connection.target.endpoint)

    visual_description = etree.SubElement(wiring, 'visualdescription')
    write_mashup_wiring_visualdescription_tree(visual_description, options.wiring.visualdescription)


def write_mashup_wiring_visualdescription_tree(target: etree.Element, visualdescription: WiringVisualDescription) -> None:
    write_mashup_wiring_components_tree(target, 'operator', visualdescription.components)
    write_mashup_wiring_components_tree(target, 'widget', visualdescription.components)
    write_mashup_wiring_connections_tree(target, visualdescription.connections)
    write_mashup_wiring_behaviours_tree(target, visualdescription.behaviours)


def write_mashup_wiring_behaviours_tree(target: etree.Element, behaviours: list[WiringBehaviour]) -> None:
    for behaviour in behaviours:
        behaviour_element = etree.SubElement(target, 'behaviour', title=behaviour.title,
                                             description=behaviour.description)

        write_mashup_wiring_components_tree(behaviour_element, 'operator', behaviour.components)
        write_mashup_wiring_components_tree(behaviour_element, 'widget', behaviour.components)
        write_mashup_wiring_connections_tree(behaviour_element, behaviour.connections)


def write_mashup_wiring_connections_tree(target: etree.Element, connections: list[WiringVisualDescriptionConnection]) -> None:
    for connection in connections:
        connectionview = etree.SubElement(target, 'connection', sourcename=connection.sourcename,
                                          targetname=connection.targetname)

        if connection.sourcehandle != WiringConnectionHandlePositionType.auto:
            etree.SubElement(connectionview, 'sourcehandle', x=str(connection.sourcehandle.x),
                             y=str(connection.sourcehandle.y))

        if connection.targethandle != WiringConnectionHandlePositionType.auto:
            etree.SubElement(connectionview, 'targethandle', x=str(connection.targethandle.x),
                             y=str(connection.targethandle.y))


def write_mashup_wiring_components_tree(target: etree.Element, type: str, components: WiringComponents) -> None:
    for c_id, component in getattr(components, type).items():
        componentview = etree.SubElement(target, 'component', id=c_id, type=type)

        if component.collapsed:
            componentview.set('collapsed', 'true')

        if component.position is not None:
            etree.SubElement(componentview, 'position', x=str(component.position.x), y=str(component.position.y))

        if component.endpoints is not None:
            sources = etree.SubElement(componentview, 'sources')

            for endpointname in component.endpoints.source:
                endpoint = etree.SubElement(sources, 'endpoint')
                endpoint.text = endpointname

            targets = etree.SubElement(componentview, 'targets')

            for endpointname in component.endpoints.target:
                endpoint = etree.SubElement(targets, 'endpoint')
                endpoint.text = endpointname


def build_xml_document(options: MACD) -> etree.Element:
    template = etree.Element(str(options.type.value), xmlns="http://wirecloud.conwet.fi.upm.es/ns/macdescription/1")
    template.set('vendor', options.vendor)
    template.set('name', options.name)
    template.set('version', options.version)

    add_element(options, template, 'macversion', default='1', type='string', ignore_default=False)

    desc = etree.SubElement(template, 'details')
    add_elements(options, desc, ('title', 'email', 'image', 'smartphoneimage', 'description', 'longdescription',
                                 'homepage', 'doc', 'license', 'licenseurl', 'changelog', 'issuetracker'))
    add_elements(options, desc, ('authors', 'contributors'), type='people')

    if len(options.requirements) > 0:
        requirements = etree.SubElement(template, 'requirements')
        for requirement in options.requirements:
            etree.SubElement(requirements, 'feature', name=requirement.name)

    if options.type == MACType.mashup:
        resources = etree.SubElement(template, 'structure')
        for pref_name, pref_value in options.preferences.items():
            etree.SubElement(resources, 'preferencevalue', name=pref_name, value=pref_value)

        write_mashup_tree(template, resources, options)
        write_mashup_wiring_tree(resources, options)
    else:
        if len(options.preferences) > 0:
            preferences_element = etree.SubElement(template, 'preferences')
            for pref in options.preferences:
                pref_element = etree.SubElement(preferences_element, 'preference', name=pref.name)
                add_attributes(pref, pref_element, ('type', 'label', 'description', 'default', 'language'))
                add_attributes(pref, pref_element, ('readonly', 'secure'), default='false', type='boolean')

                if pref.type == 'list':
                    for option in pref.options:
                        etree.SubElement(pref_element, 'option', label=option.label, value=option.value)

                if pref.value is not None:
                    pref_element.set('value', pref.value)

        if len(options.properties) > 0:
            properties_element = etree.SubElement(template, 'persistentvariables')
            for prop in options.properties:
                prop_element = etree.SubElement(properties_element, 'variable', name=prop.name)
                add_attributes(prop, prop_element, ('type', 'label', 'description', 'description', 'default'))
                add_attributes(prop, prop_element, ('secure', 'multiuser'), default='false', type='boolean')

    # Wiring info
    wiring = etree.SubElement(template, 'wiring')

    for output_endpoint in options.wiring.outputs:
        endpoint = etree.SubElement(wiring, 'outputendpoint', name=output_endpoint.name)
        add_attributes(output_endpoint, endpoint, ('type', 'label', 'description', 'friendcode'))

    for input_endpoint in options.wiring.inputs:
        endpoint = etree.SubElement(wiring, 'inputendpoint', name=input_endpoint.name)
        add_attributes(input_endpoint, endpoint, ('type', 'label', 'description', 'actionlabel', 'friendcode'))

    if options.type == MACType.widget:
        # Widget code
        xhtml = etree.SubElement(template, 'contents', src=options.contents.src)
        add_attribute(options.contents, xhtml, 'contenttype', default='text/html')
        add_attribute(options.contents, xhtml, 'charset', default='utf-8')
        add_attribute(options.contents, xhtml, 'cacheable', default='true', type='boolean')
        add_attribute(options.contents, xhtml, 'useplatformstyle', default='false', type='boolean')

        for altcontents in options.altcontents:
            altcontents_element = etree.SubElement(xhtml, 'altcontents', scope=altcontents.scope,
                                                   src=altcontents.src)
            add_attribute(altcontents, altcontents_element, 'contenttype', default='text/html')
            add_attribute(altcontents, altcontents_element, 'charset', default='utf-8')

        # Widget rendering
        etree.SubElement(template, 'rendering', width=options.widget_width, height=options.widget_height)

    if options.type == MACType.operator or (options.type == MACType.widget and options.macversion > 1):
        scripts = etree.SubElement(template, 'scripts')
        for script in options.js_files:
            etree.SubElement(scripts, 'script', src=script)

    if ((options.type == MACType.operator or options.type == MACType.widget) and options.macversion > 1 and
            options.entrypoint is not None):
        # Add entrypoint
        etree.SubElement(template, 'entrypoint', name=options.entrypoint)

    # Translations
    if len(options.translations) > 0:
        translations_element = etree.SubElement(template, 'translations', default=options.default_lang)

        for lang, catalogue in options.translations.items():
            catalogue_element = etree.SubElement(translations_element, 'translation', lang=lang)

            for msg_name, msg in catalogue.items():
                msg_element = etree.SubElement(catalogue_element, 'msg', name=msg_name)
                msg_element.text = msg

    return template


def write_xml_description(options: MACD, raw: bool = False) -> Union[str, etree.Element]:
    doc = build_xml_document(options)
    return doc if raw is True else etree.tostring(doc, method='xml', xml_declaration=True, encoding="UTF-8",
                                                  pretty_print=True).decode('utf-8')
