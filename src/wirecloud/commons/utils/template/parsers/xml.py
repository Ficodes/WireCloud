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

import codecs
import os

from lxml import etree
from pydantic import ValidationError

from wirecloud.commons.utils.template.base import ObsoleteFormatError, convert_legacy_layout, \
    default_desktop_screen_size_id, resolve_legacy_screen_sizes
from wirecloud.commons.utils.template.schemas.macdschemas import *
from wirecloud.commons.utils.translation import get_trans_index
from wirecloud.platform.wiring.schemas import *
from wirecloud.platform.wiring.utils import get_behaviour_skeleton, get_wiring_skeleton

from wirecloud.translation import gettext as _

XMLSCHEMA_FILE = codecs.open(os.path.join(os.path.dirname(__file__), '../schemas/xml_schema.xsd'), 'rb')
XMLSCHEMA_DOC = etree.parse(XMLSCHEMA_FILE)
XMLSCHEMA_FILE.close()
XMLSCHEMA = etree.XMLSchema(XMLSCHEMA_DOC)

WIRECLOUD_TEMPLATE_NS = 'http://wirecloud.conwet.fi.upm.es/ns/macdescription/1'
OLD_TEMPLATE_NAMESPACES = ('http://wirecloud.conwet.fi.upm.es/ns/template#', 'http://morfeo-project.org/2007/Template')

MAC_VERSION_XPATH = 't:macversion'
RESOURCE_DESCRIPTION_XPATH = 't:details'
DISPLAY_NAME_XPATH = 't:title'
DESCRIPTION_XPATH = 't:description'
LONG_DESCRIPTION_XPATH = 't:longdescription'
AUTHORS_XPATH = 't:authors'
CONTRIBUTORS_XPATH = 't:contributors'
IMAGE_URI_XPATH = 't:image'
IPHONE_IMAGE_URI_XPATH = 't:smartphoneimage'
MAIL_XPATH = 't:email'
HOMEPAGE_XPATH = 't:homepage'
DOC_URI_XPATH = 't:doc'
LICENCE_XPATH = 't:license'
LICENCE_URL_XPATH = 't:licenseurl'
CHANGELOG_XPATH = 't:changelog'
REQUIREMENTS_XPATH = 't:requirements'
ISSUETRACKER_XPATH = 't:issuetracker'

FEATURE_XPATH = 't:feature'
CODE_XPATH = 't:contents'
ALTCONTENT_XPATH = 't:altcontents'
PREFERENCE_XPATH = 't:preference'
PREFERENCE_VALUE_XPATH = 't:preferencevalue'
PREFERENCES_XPATH = 't:preferences/t:preference'
OPTION_XPATH = 't:option'
PROPERTY_XPATH = 't:persistentvariables/t:variable'
WIRING_XPATH = 't:wiring'
MASHUP_WIRING_XPATH = 't:structure/t:wiring'
INPUT_ENDPOINT_XPATH = 't:inputendpoint'
OUTPUT_ENDPOINT_XPATH = 't:outputendpoint'
SCRIPT_XPATH = 't:scripts/t:script'
PLATFORM_RENDERING_XPATH = 't:rendering'
ENTRYPOINT_XPATH = 't:entrypoint'

INCLUDED_RESOURCES_XPATH = 't:structure'
TAB_XPATH = 't:tab'
RESOURCE_XPATH = 't:resource'
LAYOUTS_XPATH = 't:layouts'
LAYOUT_XPATH = 't:layout'
POSITION_XPATH = 't:position'
SCREEN_SIZES_XPATH = 't:screensizes'
RENDERING_XPATH = 't:rendering'
PARAM_XPATH = 't:preferences/t:preference'
EMBEDDEDRESOURCE_XPATH = 't:embedded/t:resource'
PROPERTIES_XPATH = 't:variablevalue'
CONNECTION_XPATH = 't:connection'
IOPERATOR_XPATH = 't:operator'
SOURCE_XPATH = 't:source'
TARGET_XPATH = 't:target'

VISUALDESCRIPTION_XPATH = 't:visualdescription'
BEHAVIOUR_XPATH = 't:behaviour'

COMPONENT_XPATH = 't:component'
COMPONENTSOURCES_XPATH = 't:sources/t:endpoint'
COMPONENTTARGETS_XPATH = 't:targets/t:endpoint'
SOURCEHANDLE_XPATH = 't:sourcehandle'
TARGETHANDLE_XPATH = 't:targethandle'

TRANSLATIONS_XPATH = 't:translations'
TRANSLATION_XPATH = 't:translation'
MSG_XPATH = 't:msg'


class ApplicationMashupTemplateParser(object):
    _info: MACD

    _doc: Optional[etree.Element] = None
    _component_description: Optional[etree.Element] = None
    _parsed: bool = False

    _info: MACD
    _translation_indexes: dict[str, list[MACDTranslationIndexUsage]] = {}

    _type: MACType

    def __init__(self, template: Union[bytes, str, etree.Element]):
        if isinstance(template, bytes):
            self._doc = etree.fromstring(template)
        elif isinstance(template, str):
            # Work around: ValueError: Unicode strings with encoding
            # declaration are not supported.
            self._doc = etree.fromstring(template.encode('utf-8'))
        else:
            self._doc = template

        root_element_qname = etree.QName(self._doc)
        xmlns = root_element_qname.namespace

        if xmlns is None:
            raise ValueError(_("Missing document namespace"))
        elif xmlns in OLD_TEMPLATE_NAMESPACES:
            raise ObsoleteFormatError()
        elif xmlns != WIRECLOUD_TEMPLATE_NS:
            raise ValueError(_("Invalid namespace: ") + xmlns)

        if root_element_qname.localname not in ('widget', 'operator', 'mashup'):
            raise TemplateParseException(_("Invalid root element (%s)") % root_element_qname.localname)

        self._type = MACType(root_element_qname.localname)

    def _init(self) -> None:
        try:
            XMLSCHEMA.assertValid(self._doc)
        except Exception as e:
            raise TemplateParseException('%s' % e)

        self._component_description = self._xpath(RESOURCE_DESCRIPTION_XPATH, self._doc)[0]
        self._parse_basic_info()

    def _xpath(self, query: str, element: etree.Element) -> list[etree.Element]:
        return element.xpath(query, namespaces={'t': WIRECLOUD_TEMPLATE_NS})

    def get_xpath(self, query: str, element: etree.Element, required: bool = True) -> Optional[etree.Element]:
        elements = self._xpath(query, element)

        if len(elements) == 0 and required:
            raise TemplateParseException(_('Missing %s element') % query.replace('t:', ''))
        elif len(elements) > 0:
            return elements[0]
        else:
            return None

    def _add_translation_index(self, value: str, **kwargs) -> None:
        index = get_trans_index(str(value))
        if not index:
            return

        if index not in self._translation_indexes:
            self._translation_indexes[index] = []

        self._translation_indexes[index].append(MACDTranslationIndexUsage(**kwargs))

    def _parse_extra_info(self) -> None:
        if self._type == MACType.widget:
            self._parse_widget_info()
        elif self._type == MACType.operator:
            self._parse_operator_info()
        elif self._type == MACType.mashup:
            self._parse_workspace_info()

        self._parse_translation_catalogue()
        self._parsed = True
        self._doc = None
        self._component_description = None

        # Force validation of the model
        self._info = type(self._info)(**self._info.model_dump())

    def _get_field(self, xpath: str, element: etree.Element, required: bool = True) -> str:
        elements = self._xpath(xpath, element)
        if len(elements) == 1 and elements[0].text and len(elements[0].text.strip()) > 0:
            return str(elements[0].text)
        elif not required:
            return ''
        else:
            msg = _('Missing required field: %(field)s')
            raise TemplateParseException(msg % {'field': xpath})

    def _parse_basic_info(self) -> None:
        vendor = str(self._doc.get('vendor', '').strip())
        name = str(self._doc.get('name', '').strip())
        version = str(self._doc.get('version', '').strip())

        if self._type == MACType.widget:
            self._info = MACDWidget(type=self._type, vendor=Vendor(vendor), name=Name(name), version=Version(version),
                                    contents=MACDWidgetContents(src=""), widget_width="0", widget_height="0")
        elif self._type == MACType.operator:
            self._info = MACDOperator(type=self._type, vendor=Vendor(vendor), name=Name(name), version=Version(version))
        elif self._type == MACType.mashup:
            self._info = MACDMashup(type=self._type, vendor=Vendor(vendor), name=Name(name), version=Version(version))

        macversion_elem = self._get_field(MAC_VERSION_XPATH, self._doc, required=False)
        if len(macversion_elem) != 0:
            self._info.macversion = MACVersion(int(macversion_elem))

        self._info.title = self._get_field(DISPLAY_NAME_XPATH, self._component_description, required=False)
        self._add_translation_index(self._info.title, type='resource', field='title')

        self._info.description = self._get_field(DESCRIPTION_XPATH, self._component_description, required=False)
        self._add_translation_index(self._info.description, type='resource', field='description')
        self._info.longdescription = self._get_field(LONG_DESCRIPTION_XPATH, self._component_description, required=False)

        self._info.authors = parse_contacts_info(self._get_field(AUTHORS_XPATH, self._component_description, required=False))
        self._info.contributors = parse_contacts_info(self._get_field(CONTRIBUTORS_XPATH, self._component_description, required=False))
        self._info.email = self._get_field(MAIL_XPATH, self._component_description, required=False)
        self._info.image = self._get_field(IMAGE_URI_XPATH, self._component_description, required=False)
        self._info.smartphoneimage = self._get_field(IPHONE_IMAGE_URI_XPATH, self._component_description, required=False)
        self._info.homepage = self._get_field(HOMEPAGE_XPATH, self._component_description, required=False)
        self._info.doc = self._get_field(DOC_URI_XPATH, self._component_description, required=False)
        self._info.license = self._get_field(LICENCE_XPATH, self._component_description, required=False)
        self._info.licenseurl = self._get_field(LICENCE_URL_XPATH, self._component_description, required=False)
        self._info.issuetracker = self._get_field(ISSUETRACKER_XPATH, self._component_description, required=False)
        self._info.changelog = self._get_field(CHANGELOG_XPATH, self._component_description, required=False)
        self._parse_requirements()

        # Force validation of the model
        self._info = type(self._info)(**self._info.model_dump())

    def _parse_requirements(self) -> None:
        requirements_elements = self._xpath(REQUIREMENTS_XPATH, self._doc)
        if len(requirements_elements) < 1:
            return

        for requirement in self._xpath(FEATURE_XPATH, requirements_elements[0]):
            self._info.requirements.append(MACDRequirement(
                type=u'feature',
                name=str(requirement.get('name').strip())
            ))

    def _parse_visualdescription_info(self, visualdescription_element: etree.Element) -> None:
        self._parse_wiring_component_view_info(self._info.wiring.visualdescription, visualdescription_element)
        self._parse_wiring_connection_view_info(self._info.wiring.visualdescription, visualdescription_element)
        self._parse_wiring_behaviour_view_info(self._info.wiring.visualdescription, visualdescription_element)

    def _parse_wiring_behaviour_view_info(self, target: WiringVisualDescription, behaviours_element: etree.Element) -> None:
        for behaviour in self._xpath(BEHAVIOUR_XPATH, behaviours_element):
            behaviour_info = get_behaviour_skeleton()
            behaviour_info.title = str(behaviour.get('title'))
            behaviour_info.description = str(behaviour.get('description'))

            self._parse_wiring_component_view_info(behaviour_info, behaviour)
            self._parse_wiring_connection_view_info(behaviour_info, behaviour)

            target.behaviours.append(behaviour_info)

    def _parse_wiring_component_view_info(self, target: Union[WiringVisualDescription, WiringBehaviour],
                                          components_element: etree.Element) -> None:
        for component in self._xpath(COMPONENT_XPATH, components_element):
            component_info = WiringComponent(
                collapsed=component.get('collapsed', 'false').strip().lower() == 'true',
                endpoints=WiringComponentEndpoints(
                    source=[endpoint.text for endpoint in self._xpath(COMPONENTSOURCES_XPATH, component)],
                    target=[endpoint.text for endpoint in self._xpath(COMPONENTTARGETS_XPATH, component)]
                )
            )

            position = self.get_xpath(POSITION_XPATH, component, required=False)
            if position is not None:
                component_info.position = WiringPosition(
                    x=int(position.get('x')),
                    y=int(position.get('y'))
                )

            if component.get('type') == 'widget':
                target.components.widget[str(component.get('id'))] = component_info
            elif component.get('type') == 'operator':
                target.components.operator[str(component.get('id'))] = component_info

    def _parse_wiring_connection_view_info(self, target: Union[WiringVisualDescription, WiringBehaviour],
                                           connections_element: etree.Element) -> None:
        for connection in self._xpath(CONNECTION_XPATH, connections_element):
            connection_info = WiringVisualDescriptionConnection(
                sourcename=str(connection.get('sourcename')),
                targetname=str(connection.get('targetname'))
            )

            sourcehandle_element = self.get_xpath(SOURCEHANDLE_XPATH, connection, required=False)
            targethandle_element = self.get_xpath(TARGETHANDLE_XPATH, connection, required=False)

            if sourcehandle_element is not None:
                connection_info.sourcehandle = WiringPosition(
                    x=int(sourcehandle_element.get('x')),
                    y=int(sourcehandle_element.get('y'))
                )

            if targethandle_element is not None:
                connection_info.targethandle = WiringPosition(
                    x=int(targethandle_element.get('x')),
                    y=int(targethandle_element.get('y'))
                )

            target.connections.append(connection_info)

    def _parse_wiring_info(self) -> None:
        if self._type == MACType.mashup:
            self._info.wiring = MACDMashupWiring(**get_wiring_skeleton().model_dump())

        wiring_elements = self._xpath(WIRING_XPATH, self._doc)
        if len(wiring_elements) != 0:
            wiring_element = wiring_elements[0]

            for slot in self._xpath(INPUT_ENDPOINT_XPATH, wiring_element):
                self._add_translation_index(str(slot.get('label')), type='inputendpoint', variable=slot.get('name'))
                self._add_translation_index(str(slot.get('actionlabel', '')), type='inputendpoint', variable=slot.get('name'))
                self._add_translation_index(str(slot.get('description', '')), type='inputendpoint', variable=slot.get('name'))
                self._info.wiring.inputs.append(WiringInput(
                    name=str(slot.get('name')),
                    type=str(slot.get('type')),
                    label=str(slot.get('label', '')),
                    description=str(slot.get('description', '')),
                    actionlabel=str(slot.get('actionlabel', '')),
                    friendcode=str(slot.get('friendcode', ''))
                ))

            for event in self._xpath(OUTPUT_ENDPOINT_XPATH, wiring_element):
                self._add_translation_index(str(event.get('label')), type='outputendpoint', variable=event.get('name'))
                self._add_translation_index(str(event.get('description', '')), type='outputendpoint', variable=event.get('name'))
                self._info.wiring.outputs.append(WiringOutput(
                    name=str(event.get('name')),
                    type=str(event.get('type')),
                    label=str(event.get('label', '')),
                    description=str(event.get('description', '')),
                    friendcode=str(event.get('friendcode', ''))
                ))

        if self._type == MACType.mashup:
            mashup_wiring_element = self.get_xpath(MASHUP_WIRING_XPATH, self._doc, required=False)
            if mashup_wiring_element is None:
                return

            self._info.wiring.version = str(mashup_wiring_element.get('version', "1.0"))

            self._parse_wiring_connection_info(mashup_wiring_element)
            self._parse_wiring_operator_info(mashup_wiring_element)

            if self._info.wiring.version == '1.0':
                raise TemplateParseException(_("Only wiring version 2.0 is supported. The old 1.0 version is no longer supported."))
            elif self._info.wiring.version == '2.0':
                visualdescription_element = self.get_xpath(VISUALDESCRIPTION_XPATH, mashup_wiring_element, required=False)
                if visualdescription_element is not None:
                    self._parse_visualdescription_info(visualdescription_element)
            else:
                raise TemplateParseException(_("Invalid wiring version: %s") % self._info.wiring.version)

    def _parse_wiring_connection_info(self, wiring_element: etree.Element) -> None:
        for connection in self._xpath(CONNECTION_XPATH, wiring_element):
            source_element = self._xpath(SOURCE_XPATH, connection)[0]
            target_element = self._xpath(TARGET_XPATH, connection)[0]

            connection_info = WiringConnection(
                readonly=connection.get('readonly', 'false').lower() == 'true',
                source=WiringConnectionEndpoint(
                    type=str(source_element.get('type')),
                    endpoint=str(source_element.get('endpoint')),
                    id=str(source_element.get('id'))
                ),
                target=WiringConnectionEndpoint(
                    type=str(target_element.get('type')),
                    endpoint=str(target_element.get('endpoint')),
                    id=str(target_element.get('id'))
                )
            )

            self._info.wiring.connections.append(connection_info)

    def _parse_wiring_operator_info(self, wiring_element: etree.Element) -> None:
        for operator in self._xpath(IOPERATOR_XPATH, wiring_element):
            operator_info = WiringOperator(
                id=str(operator.get('id')),
                name=str('/'.join((operator.get('vendor'), operator.get('name'), operator.get('version')))),
                preferences={}
            )

            for pref in self._xpath(PREFERENCE_VALUE_XPATH, operator):
                pref_value = pref.get('value')
                operator_info.preferences[str(pref.get('name'))] = WiringOperatorPreference(
                    readonly=pref.get('readonly', 'false').lower() == 'true',
                    hidden=pref.get('hidden', 'false').lower() == 'true',
                    value=str(pref_value) if pref_value is not None else None
                )

            self._info.wiring.operators[operator_info.id] = operator_info

    def _parse_widget_info(self) -> None:
        self._parse_component_preferences()
        self._parse_component_persistentvariables()
        self._parse_wiring_info()

        xhtml_element = self._xpath(CODE_XPATH, self._doc)[0]
        self._info.contents = MACDWidgetContents(
            src=str(xhtml_element.get('src')),
            contenttype=str(xhtml_element.get('contenttype', 'text/html')),
            charset=str(xhtml_element.get('charset', 'utf-8')),
            useplatformstyle=xhtml_element.get('useplatformstyle', 'false').lower() == 'true',
            cacheable=xhtml_element.get('cacheable', 'true').lower() == 'true'
        )

        for altcontents in self._xpath(ALTCONTENT_XPATH, xhtml_element):
            self._info.altcontents.append(MACDWidgetContentsAlternative(
                scope=str(altcontents.get('scope')),
                src=str(altcontents.get('src')),
                contenttype=str(altcontents.get('contenttype', 'text/html')),
                charset=str(altcontents.get('charset', 'utf-8'))
            ))

        rendering_element = self.get_xpath(PLATFORM_RENDERING_XPATH, self._doc)
        self._info.widget_width = str(rendering_element.get('width'))
        self._info.widget_height = str(rendering_element.get('height'))

        if self._info.macversion > 1:
            js_files = self._xpath(SCRIPT_XPATH, self._doc)

            for script in js_files:
                self._info.js_files.append(str(script.get('src')))

            entrypoint = self.get_xpath(ENTRYPOINT_XPATH, self._doc, required=False)
            if entrypoint is not None:
                self._info.entrypoint = str(entrypoint.get('name'))
        else:
            js_files = self._xpath(SCRIPT_XPATH, self._doc)
            if len(js_files) > 0:
                raise TemplateParseException(_("The use of the script element is not allowed in version 1.0 widgets"))

    def _parse_operator_info(self) -> None:
        self._parse_component_preferences()
        self._parse_component_persistentvariables()
        self._parse_wiring_info()

        for script in self._xpath(SCRIPT_XPATH, self._doc):
            self._info.js_files.append(str(script.get('src')))

        if self._info.macversion > 1:
            entrypoint = self.get_xpath(ENTRYPOINT_XPATH, self._doc, required=False)
            if entrypoint is not None:
                self._info.entrypoint = str(entrypoint.get('name'))

    def _parse_component_preferences(self) -> None:
        for preference in self._xpath(PREFERENCES_XPATH, self._doc):
            self._add_translation_index(preference.get('label'), type='vdef', variable=preference.get('name'), field='label')
            self._add_translation_index(preference.get('description', ''), type='vdef', variable=preference.get('name'), field='description')
            preference_info = MACDPreference(
                name=str(preference.get('name')),
                type=str(preference.get('type')),
                label=str(preference.get('label', '')),
                description=str(preference.get('description', '')),
                readonly=preference.get('readonly', 'false').lower() == 'true',
                default=str(preference.get('default', '')),
                value=preference.get('value'),
                secure=preference.get('secure', 'false').lower() == 'true',
                multiuser=False,
                required=preference.get('required', 'false').lower() == 'true',
                language=preference.get('language', None),
                options=[] if preference.get('type') == 'list' else None
            )

            if preference_info.type == 'list':
                for option_index, option in enumerate(self._xpath(OPTION_XPATH, preference)):
                    option_label = str(option.get('label', option.get('name')))
                    self._add_translation_index(option_label, type='upo', variable=preference.get('name'), option=option_index)
                    preference_info.options.append(MACDPreferenceListOption(
                        label=str(option_label),
                        value=str(option.get('value'))
                    ))

            self._info.preferences.append(preference_info)

    def _parse_component_persistentvariables(self) -> None:
        for prop in self._xpath(PROPERTY_XPATH, self._doc):
            self._add_translation_index(prop.get('label'), type='vdef', variable=prop.get('name'))
            self._add_translation_index(prop.get('description', ''), type='vdef', variable=prop.get('name'))
            self._info.properties.append(MACDProperty(
                name=str(prop.get('name')),
                type=str(prop.get('type')),
                label=str(prop.get('label', '')),
                description=str(prop.get('description', '')),
                default=str(prop.get('default', '')),
                secure=prop.get('secure', 'false').lower() == 'true',
                multiuser=prop.get('multiuser', 'false').lower() == 'true'
            ))

    def _parse_preference_values(self, element: etree.Element) -> dict[str, Optional[str]]:
        values = {}

        for preference in self._xpath(PREFERENCE_VALUE_XPATH, element):
            pref_value = preference.get('value')
            values[str(preference.get('name'))] = str(pref_value) if pref_value is not None else None

        return values

    def _parse_workspace_info(self) -> None:
        workspace_structure = self._xpath(INCLUDED_RESOURCES_XPATH, self._doc)[0]

        self._info.preferences = self._parse_preference_values(workspace_structure)

        for param in self._xpath(PARAM_XPATH, self._doc):
            self._info.params.append(MACDMashupPreference(
                name=str(param.get('name')),
                type=str(param.get('type')),
                label=str(param.get('label', '')),
                description=str(param.get('description', '')),
                readonly=param.get('readonly', 'false').lower() == 'true',
                default=str(param.get('default', '')),
                value=param.get('value'),
                required=param.get('required', 'false').lower() == 'true'
            ))

        for component in self._xpath(EMBEDDEDRESOURCE_XPATH, self._doc):
            self._info.embedded.append(MACDMashupEmbedded(
                vendor=str(component.get('vendor')),
                name=str(component.get('name')),
                version=str(component.get('version')),
                src=str(component.get('src'))
            ))

        tabs = []
        for tab in self._xpath(TAB_XPATH, workspace_structure):
            tab_info = MACDTab(
                name=str(tab.get('name')),
                title=str(tab.get('title', '')),
                preferences=self._parse_preference_values(tab)
            )

            # Resolve (and, if 'legacy default', drop) the effective 'screenSizes' preference for
            # this tab; legacy position/rendering widget layouts must then be remapped to the new
            # default desktop screen size instead of the old (now meaningless) screen size id.
            tab_legacy_default_screen_sizes = resolve_legacy_screen_sizes(tab_info.preferences, self._info.preferences)

            for widget in self._xpath(RESOURCE_XPATH, tab):
                layouts_container = self.get_xpath(LAYOUTS_XPATH, widget, required=False)
                position = self.get_xpath(POSITION_XPATH, widget, required=False)
                screenSizes = self.get_xpath(SCREEN_SIZES_XPATH, widget, required=False)
                rendering = self.get_xpath(RENDERING_XPATH, widget, required=False)

                widget_info = MACDMashupResource(
                    id=str(widget.get('id')),
                    name=str(widget.get('name')),
                    vendor=str(widget.get('vendor')),
                    version=str(widget.get('version')),
                    title=str(widget.get('title')),
                    readonly=widget.get('readonly', '').lower() == 'true',
                )

                if layouts_container is not None:
                    for layout_elem in self._xpath(LAYOUT_XPATH, layouts_container):
                        x = layout_elem.get('x')
                        y = layout_elem.get('y')
                        widget_info.layouts[str(layout_elem.get('screensize'))] = MACDMashupResourceLayout(
                            x=int(x) if x is not None else None,
                            y=int(y) if y is not None else None,
                            w=int(layout_elem.get('w', 1)),
                            h=int(layout_elem.get('h', 1)),
                            minimized=layout_elem.get('minimized', 'false').lower() == 'true',
                            titlevisible=layout_elem.get('titlevisible', 'true').lower() == 'true',
                            fulldragboard=layout_elem.get('fulldragboard', 'false').lower() == 'true',
                            visible=layout_elem.get('visible', 'true').lower() == 'true',
                        )
                elif screenSizes is not None:
                    # Legacy format: <screensizes><screensize moreOrEqual lessOrEqual id><position/><rendering/></screensize></screensizes>
                    for screenSize in screenSizes:
                        legacy_position = self.get_xpath(POSITION_XPATH, screenSize)
                        legacy_rendering = self.get_xpath(RENDERING_XPATH, screenSize)
                        key = str(default_desktop_screen_size_id()) if tab_legacy_default_screen_sizes \
                            else str(screenSize.get('id'))
                        widget_info.layouts[key] = MACDMashupResourceLayout(**convert_legacy_layout(
                            top=float(legacy_position.get('y')),
                            left=float(legacy_position.get('x')),
                            width=float(legacy_rendering.get('width')),
                            height=float(legacy_rendering.get('height')),
                            relx=legacy_position.get('relx', 'true').lower() == 'true',
                            rely=legacy_position.get('rely', 'true').lower() == 'true',
                            relwidth=legacy_rendering.get('relwidth', 'true').lower() == 'true',
                            relheight=legacy_rendering.get('relheight', 'true').lower() == 'true',
                            minimized=legacy_rendering.get('minimized', 'false').lower() == 'true',
                            titlevisible=legacy_rendering.get('titlevisible', 'true').lower() == 'true',
                            fulldragboard=legacy_rendering.get('fulldragboard', 'false').lower() == 'true',
                        ))
                elif position is not None and rendering is not None:
                    # Legacy format: <resource ...><position/><rendering/>...</resource>
                    key = str(default_desktop_screen_size_id()) if tab_legacy_default_screen_sizes else '0'
                    widget_info.layouts[key] = MACDMashupResourceLayout(**convert_legacy_layout(
                        top=float(position.get('y')),
                        left=float(position.get('x')),
                        width=float(rendering.get('width')),
                        height=float(rendering.get('height')),
                        relx=position.get('relx', 'true').lower() == 'true',
                        rely=position.get('rely', 'true').lower() == 'true',
                        relwidth=rendering.get('relwidth', 'true').lower() == 'true',
                        relheight=rendering.get('relheight', 'true').lower() == 'true',
                        minimized=rendering.get('minimized', 'false').lower() == 'true',
                        titlevisible=rendering.get('titlevisible', 'true').lower() == 'true',
                        fulldragboard=rendering.get('fulldragboard', 'false').lower() == 'true',
                    ))

                for prop in self._xpath(PROPERTIES_XPATH, widget):
                    prop_value = prop.get('value')
                    widget_info.properties[str(prop.get('name'))] = MACDMashupResourceProperty(
                        readonly=prop.get('readonly', 'false').lower() == 'true',
                        value=str(prop_value) if prop_value is not None else None
                    )

                for pref in self._xpath(PREFERENCE_VALUE_XPATH, widget):
                    pref_value = pref.get('value')
                    widget_info.preferences[str(pref.get('name'))] = MACDMashupResourcePreference(
                        readonly=pref.get('readonly', 'false').lower() == 'true',
                        hidden=pref.get('hidden', 'false').lower() == 'true',
                        value=str(pref_value) if pref_value is not None else None,
                    )

                tab_info.resources.append(widget_info)

            tabs.append(tab_info)

        self._info.tabs = tabs

        self._parse_wiring_info()

    def _parse_translation_catalogue(self) -> None:
        translations_elements = self._xpath(TRANSLATIONS_XPATH, self._doc)

        if len(translations_elements) == 0:
            return

        translations = translations_elements[0]
        self._info.default_lang = str(translations.get('default'))

        for translation in self._xpath(TRANSLATION_XPATH, translations):
            current_catalogue = {}

            for msg in self._xpath(MSG_XPATH, translation):
                current_catalogue[str(msg.get('name'))] = str(msg.text)

            self._info.translations[translation.get('lang')] = current_catalogue

        self._info.translation_index_usage = self._translation_indexes

        self._info.check_translations()

    def get_resource_type(self) -> MACType:
        return self._info.type

    def get_resource_name(self) -> Name:
        return self._info.name

    def get_resource_vendor(self) -> Vendor:
        return self._info.vendor

    def get_resource_version(self) -> Version:
        return self._info.version

    def get_resource_info(self) -> MACD:
        if not self._parsed:
            try:
                self._parse_extra_info()
            except ValidationError as e:
                raise TemplateParseException(_("Invalid template: %s") % e)

        return self._info
