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

# WARNING: RDF is deprecated and Wirecloud will stop supporting it in the future. Use JSON (preferred) or XML instead.

import rdflib
from lxml import etree
from pydantic import ValidationError

from wirecloud.commons.utils.mimeparser import InvalidMimeType, parse_mime_type
from wirecloud.commons.utils.template.base import is_valid_name, is_valid_vendor, is_valid_version, \
    convert_legacy_layout, default_desktop_screen_size_id, resolve_legacy_screen_sizes
from wirecloud.commons.utils.template.schemas.macdschemas import *
from wirecloud.platform.wiring.schemas import *
from wirecloud.platform.wiring.utils import get_wiring_skeleton

from wirecloud.translation import gettext as _

# Namespaces used by rdflib
WIRE = rdflib.Namespace("http://wirecloud.conwet.fi.upm.es/ns/widget#")
WIRE_M = rdflib.Namespace("http://wirecloud.conwet.fi.upm.es/ns/mashup#")
FOAF = rdflib.Namespace("http://xmlns.com/foaf/0.1/")
USDL = rdflib.Namespace("http://www.linked-usdl.org/ns/usdl-core#")
DCTERMS = rdflib.Namespace("http://purl.org/dc/terms/")
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDF = rdflib.Namespace(RDF_NS)
RDFS = rdflib.Namespace("http://www.w3.org/2000/01/rdf-schema#")
VCARD = rdflib.Namespace("http://www.w3.org/2006/vcard/ns#")
BLUEPRINT = rdflib.Namespace("http://bizweb.sap.com/TR/blueprint#")
DOAP = rdflib.Namespace('http://usefulinc.com/ns/doap#')


def possible_int(value):
    try:
        return int(value)
    except ValueError:
        return value


class RDFTemplateParser(object):
    _type: MACType
    _info: MACD
    _graph: Optional[rdflib.Graph] = None
    _parsed: bool = False
    _rootURI: Optional[rdflib.term.Node] = None
    _translation_indexes: dict[str, list[MACDTranslationIndexUsage]] = {}
    _translations: dict[str, dict[str, str]] = {}

    def __init__(self, template: Union[bytes, str, rdflib.Graph]):
        if isinstance(template, rdflib.Graph):
            self._graph = template
        else:
            try:
                self._graph = rdflib.Graph()
                self._graph.parse(data=template, format='n3')
            except Exception:
                if isinstance(template, bytes):
                    doc = etree.fromstring(template)
                elif isinstance(template, str):
                    # Work around: ValueError: Unicode strings with encoding
                    # declaration are not supported.
                    doc = etree.fromstring(template.encode('utf-8'))
                else:
                    raise ValueError(_("Invalid template type"))

                root_element_qname = etree.QName(doc)

                if root_element_qname.namespace is None:
                    raise ValueError(_("XML document does not contain a valid rdf namespace"))

                if root_element_qname.namespace != RDF_NS:
                    raise ValueError(_("Invalid namespace: ") + root_element_qname.namespace)

                if root_element_qname.localname != 'RDF':
                    raise ValueError(_("Invalid root element: ") + root_element_qname.localname)

                self._graph = rdflib.Graph()
                self._graph.parse(data=template, format='xml')

    def _init(self) -> None:
        # check if is a mashup, a widget or an operator
        for _ in self._graph.subjects(RDF['type'], WIRE['Widget']):
            self._type = MACType.widget
            break
        else:
            for _ in self._graph.subjects(RDF['type'], WIRE['Operator']):
                self._type = MACType.operator
                break
            else:
                for _ in self._graph.subjects(RDF['type'], WIRE_M['Mashup']):
                    self._type = MACType.mashup
                    break
                else:
                    raise TemplateParseException(_('RDF document does not describe a widget, operator or mashup component'))

        self._parse_basic_info()

    def _add_translation_index(self, value: str, **kwargs) -> None:
        if value not in self._translation_indexes:
            self._translation_indexes[str(value)] = []
            self._translation_indexes[str(value)].append(MACDTranslationIndexUsage(**kwargs))

    def _get_translation_field(self, namespace: rdflib.Namespace, element: str, subject: rdflib.term.Node,
                               translation_name: str, required: bool = True, **kwargs) -> str:
        translated = False
        base_value = None

        for field_element in self._graph.objects(subject, namespace[element]):
            if not isinstance(field_element, rdflib.Literal):
                msg = _('Invalid content for field: %(field)s')
                raise TemplateParseException(msg % {'field': element})

            if field_element.language:
                translated = True

                if field_element.language not in self._translations:
                    self._translations[str(field_element.language)] = {}

                self._translations[str(field_element.language)][translation_name] = str(field_element)
            else:
                base_value = str(field_element)

        if base_value is not None and translated is True:
            if 'en' not in self._translations:
                self._translations['en'] = {}

            self._translations['en'][translation_name] = base_value

        if translated is True:
            self._add_translation_index(translation_name, **kwargs)
            return '__MSG_' + translation_name + '__'
        elif base_value is None and required:
            msg = _('Missing required field: %(field)s')
            raise TemplateParseException(msg % {'field': element})
        elif base_value is not None:
            return base_value
        else:
            return ''

    def _get_field(self, namespace: rdflib.Namespace, element: str, subject: Union[rdflib.term.Node, str],
                   required: bool = True, id_: bool = False, default: Optional[str] = '') -> Union[str, rdflib.term.Node]:
        fields = self._graph.objects(subject, namespace[element])
        for field_element in fields:
            result = str(field_element) if not id_ else field_element
            break
        else:
            if required:
                msg = _('Missing required field: %(field)s')
                raise TemplateParseException(msg % {'field': element})
            else:
                result = default
        return result

    def _parse_people_field(self, namespace: rdflib.Namespace, element: str, subject: rdflib.term.Node) -> list[Contact]:
        people = []
        sorted_people = sorted(self._graph.objects(subject, namespace[element]),
                               key=lambda person: possible_int(self._get_field(WIRE, 'index', person, required=False)))
        for person in sorted_people:
            name = self._get_field(FOAF, 'name', person, required=True)
            if name == '':
                continue

            person_info = Contact(name=name)

            email = self._get_field(FOAF, 'mbox', person, required=False)
            if email != '':
                person_info.email = email

            homepage = self._get_field(FOAF, 'homepage', person, required=False)
            if homepage != '':
                person_info.url = homepage

            people.append(person_info)

        return people

    def _parse_extra_info(self) -> None:
        if self._type == MACType.widget or self._type == MACType.operator:
            self._parse_component_info()
        elif self._type == MACType.mashup:
            self._parse_workspace_info()

        self._parse_translation_catalogue()
        self._parsed = True
        # self._graph = None

        # Force validation of the model
        self._info = type(self._info)(**self._info.model_dump())

    def _parse_basic_info(self) -> None:
        if self._type == MACType.widget:
            self._rootURI = next(self._graph.subjects(RDF['type'], WIRE['Widget']))
        elif self._type == MACType.mashup:
            self._rootURI = next(self._graph.subjects(RDF['type'], WIRE_M['Mashup']))
        elif self._type == MACType.operator:
            self._rootURI = next(self._graph.subjects(RDF['type'], WIRE['Operator']))

        macversion = self._get_field(WIRE, 'macVersion', self._rootURI, required=False, default='1')
        try:
            macversion = int(macversion)
        except ValueError:
            raise TemplateParseException(_('The format of the macversion is invalid. It must be an integer.'))
        if macversion != 1 and macversion != 2:
            raise TemplateParseException(_('The macversion is invalid. Currently only macversion 1 or 2 are supported.'))

        vendor_node = self._get_field(USDL, 'hasProvider', self._rootURI, id_=True)
        vendor = self._get_field(FOAF, 'name', vendor_node)
        if not is_valid_vendor(vendor):
            raise TemplateParseException(_('The format of the vendor is invalid.'))

        name = self._get_field(DCTERMS, 'title', self._rootURI)
        if not is_valid_name(name):
            raise TemplateParseException(_('The format of the name is invalid.'))

        version = self._get_field(USDL, 'versionInfo', self._rootURI)
        if not is_valid_version(version):
            raise TemplateParseException(_('The format of the version number is invalid. Format: X.X.X where X is an integer. Ex. "0.1", "1.11" NOTE: "1.01" should be changed to "1.0.1" or "1.1"'))

        if self._type == MACType.widget:
            self._info = MACDWidget(type=MACType.widget, macversion=MACVersion(macversion), name=Name(name),
                                    vendor=Vendor(vendor), version=version, contents=MACDWidgetContents(src=""),
                                    widget_width="0", widget_height="0")
        elif self._type == MACType.operator:
            self._info = MACDOperator(type=MACType.operator, macversion=MACVersion(macversion), name=Name(name),
                                      vendor=Vendor(vendor), version=version)
        elif self._type == MACType.mashup:
            self._info = MACDMashup(type=MACType.mashup, macversion=MACVersion(macversion), name=Name(name),
                                    vendor=Vendor(vendor), version=version)

        license = self._get_field(DCTERMS, 'license', self._rootURI, required=False, default=None, id_=True)
        if license is not None:
            self._info.licenseurl = str(license)
            self._info.license = self._get_field(RDFS, 'label', license, required=False)

        longdescription = self._get_field(DCTERMS, 'description', self._rootURI, id_=True, required=False)
        if longdescription != '' and isinstance(longdescription, rdflib.Literal):
            # Old and deprecated behaviour
            self._info.description = self._get_translation_field(DCTERMS, 'description', self._rootURI, 'description', required=False, type='resource', field='description')
        else:
            self._info.longdescription = '%s' % longdescription
            self._info.description = self._get_translation_field(DCTERMS, 'abstract', self._rootURI, 'description', required=False, type='resource', field='description')

        self._info.authors = self._parse_people_field(DCTERMS, 'creator', self._rootURI)
        self._info.contributors = self._parse_people_field(DCTERMS, 'contributor', self._rootURI)

        self._info.image = self._get_field(WIRE, 'hasImageUri', self._rootURI, required=False)
        self._info.smartphoneimage = self._get_field(WIRE, 'hasiPhoneImageUri', self._rootURI, required=False)

        self._info.changelog = self._get_field(WIRE, 'hasChangeLog', self._rootURI, required=False)
        self._info.homepage = self._get_field(FOAF, 'homepage', self._rootURI, required=False)
        self._info.issuetracker = self._get_field(DOAP, 'bug-database', self._rootURI, required=False)
        self._info.doc = self._get_field(FOAF, 'page', self._rootURI, required=False)

        self._info.title = self._get_translation_field(WIRE, 'displayName', self._rootURI, 'title', required=False, type='resource', field='title')

        addr_element = self._get_field(VCARD, 'addr', self._rootURI, id_=True, default=None, required=False)
        if addr_element is not None:
            self._info.email = self._get_field(VCARD, 'email', addr_element, required=False)

        self._parse_requirements()

        # Force validation of the model
        self._info = type(self._info)(**self._info.model_dump())

    def _parse_requirements(self) -> None:
        for wrequirement in self._graph.objects(self._rootURI, WIRE['hasRequirement']):
            if next(self._graph.objects(wrequirement, RDF['type'])) == WIRE['Feature']:
                self._info.requirements.append(MACDRequirement(
                    type='feature',
                    name=self._get_field(RDFS, 'label', wrequirement, required=True),
                ))

    def _parse_wiring_info(self, wiring_property: str = 'hasPlatformWiring') -> None:
        if self._type == MACType.mashup:
            self._info.wiring = MACDMashupWiring(**get_wiring_skeleton().model_dump())

        # method self._graph.objects always returns an iterable object not subscriptable,
        # althought only exits one instance
        wiring_type = WIRE_M if self._type == MACType.mashup else WIRE
        wiring_element = self._get_field(wiring_type, wiring_property, self._rootURI, id_=True, required=False)

        if self._type == MACType.mashup:
            self._info.wiring.version = self._get_field(USDL, 'versionInfo', wiring_element, default="1.0", required=False)

        sorted_inputs = sorted(self._graph.objects(wiring_element, WIRE['hasInputEndpoint']), key=lambda source: possible_int(self._get_field(WIRE, 'index', source, required=False)))

        for input_endpoint in sorted_inputs:
            var_name = self._get_field(DCTERMS, 'title', input_endpoint, required=True)
            self._info.wiring.inputs.append(WiringInput(
                name=var_name,
                type=self._get_field(WIRE, 'type', input_endpoint, required=True),
                label=self._get_translation_field(RDFS, 'label', input_endpoint, var_name + '_label', required=False, type='inputendpoint', variable=var_name, field='label'),
                description=self._get_translation_field(DCTERMS, 'description', input_endpoint, var_name + '_description', required=False, type='inputendpoint', variable=var_name, field='description'),
                actionlabel=self._get_translation_field(WIRE, 'inputActionLabel', input_endpoint, var_name + '_actionlabel', required=False, type='inputendpoint', variable=var_name, field='actionlabel'),
                friendcode=self._get_field(WIRE, 'friendcode', input_endpoint, required=False)
            ))

        sorted_outputs = sorted(self._graph.objects(wiring_element, WIRE['hasOutputEndpoint']), key=lambda output: possible_int(self._get_field(WIRE, 'index', output, required=False)))

        for output_endpoint in sorted_outputs:
            var_name = self._get_field(DCTERMS, 'title', output_endpoint, required=True)
            self._info.wiring.outputs.append(WiringOutput(
                name=var_name,
                type=self._get_field(WIRE, 'type', output_endpoint, required=True),
                label=self._get_translation_field(RDFS, 'label', output_endpoint, var_name + '_label', required=False, type='outputendpoint', variable=var_name, field='label'),
                description=self._get_translation_field(DCTERMS, 'description', output_endpoint, var_name + '_description', required=False, type='outputendpoint', variable=var_name, field='description'),
                friendcode=self._get_field(WIRE, 'friendcode', output_endpoint, required=False)
            ))

        if self._type == MACType.mashup:
            self._parse_wiring_connection_info(wiring_element)
            self._parse_wiring_operator_info(wiring_element)

            if self._info.wiring.version == '1.0':
                raise TemplateParseException(_("Only wiring version 2.0 is supported. The old 1.0 version is no longer supported."))
            else:
                self._parse_wiring_behaviours(wiring_element)

    def _parse_wiring_connection_info(self, wiring_element: rdflib.term.Node) -> None:
        connections = []

        for connection in self._graph.objects(wiring_element, WIRE_M['hasConnection']):
            for source in self._graph.objects(connection, WIRE_M['hasSource']):
                connection_source = WiringConnectionEndpoint(
                    id=self._get_field(WIRE_M, 'sourceId', source),
                    endpoint=self._get_field(WIRE_M, 'endpoint', source),
                    type=self._get_field(WIRE, 'type', source)
                )
                break
            else:
                raise TemplateParseException('Missing required field: source')

            for target in self._graph.objects(connection, WIRE_M['hasTarget']):
                connection_target = WiringConnectionEndpoint(
                    id=self._get_field(WIRE_M, 'targetId', target),
                    endpoint=self._get_field(WIRE_M, 'endpoint', target),
                    type=self._get_field(WIRE, 'type', target)
                )
                break
            else:
                raise TemplateParseException(_('Missing required field: target'))

            connection_info = WiringConnection(
                readonly=self._get_field(WIRE_M, 'readonly', connection, required=False).lower() == 'true',
                source=connection_source,
                target=connection_target
            )

            connections.append(connection_info)

        self._info.wiring.connections = connections

    def _parse_wiring_operator_info(self, wiring_element: rdflib.term.Node) -> None:
        for operator in self._graph.objects(wiring_element, WIRE_M['hasiOperator']):
            operator_info = WiringOperator(
                id=self._get_field(WIRE_M, 'iOperatorId', operator),
                name=self._get_field(DCTERMS, 'title', operator),
                preferences={}
            )

            for pref in self._graph.objects(operator, WIRE_M['hasiOperatorPreference']):
                operator_info.preferences[self._get_field(DCTERMS, 'title', pref)] = WiringOperatorPreference(
                    readonly=self._get_field(WIRE_M, 'readonly', pref, required=False).lower() == 'true',
                    hidden=self._get_field(WIRE_M, 'hidden', pref, required=False).lower() == 'true',
                    value=self._get_field(WIRE, 'value', pref, default=None, required=False)
                )

            self._info.wiring.operators[operator_info.id] = operator_info

    def _parse_wiring_components(self, element: rdflib.term.Node, behaviour: Union[WiringVisualDescription, WiringBehaviour]) -> None:
        for entity_view in self._graph.objects(element, WIRE_M['hasComponentView']):
            type_ = self._get_field(WIRE, 'type', entity_view)
            id_ = self._get_field(WIRE, 'id', entity_view)

            if type_ == 'widget':
                component_view_description = behaviour.components.widget[id_] = WiringComponent()
            elif type_ == 'operator':
                component_view_description = behaviour.components.operator[id_] = WiringComponent()
            else:
                raise TemplateParseException(_('Invalid component type in wiring: %s') % type_)

            component_view_description.collapsed = self._get_field(WIRE_M, 'collapsed', entity_view, required=False).lower() == 'true'

            sorted_sources = sorted(self._graph.objects(entity_view, WIRE_M['hasSource']), key=lambda source: possible_int(self._get_field(WIRE, 'index', source, required=False)))
            sorted_targets = sorted(self._graph.objects(entity_view, WIRE_M['hasTarget']), key=lambda target: possible_int(self._get_field(WIRE, 'index', target, required=False)))

            component_view_description.endpoints = WiringComponentEndpoints(
                source=[self._get_field(RDFS, 'label', sourc) for sourc in sorted_sources],
                target=[self._get_field(RDFS, 'label', targ) for targ in sorted_targets]
            )

            position = self._parse_position(entity_view)
            if position is not None:
                component_view_description.position = position

    def _parse_position(self, node: rdflib.term.Node, relation_name: str = 'hasPosition',
                        default: Union[WiringConnectionHandlePositionType, WiringPosition, None] = None) -> Optional[WiringPosition]:
        position_node = self._get_field(WIRE_M, relation_name, node, id_=True, default=None, required=False)
        if position_node is not None:
            return WiringPosition(
                x=int(self._get_field(WIRE_M, 'x', position_node)),
                y=int(self._get_field(WIRE_M, 'y', position_node))
            )

        return default

    def _join_endpoint_name(self, endpoint_view: rdflib.term.Node) -> str:
        endpoint = WiringConnectionEndpoint(
            id=self._get_field(WIRE_M, 'id', endpoint_view),
            endpoint=self._get_field(WIRE_M, 'endpoint', endpoint_view),
            type=self._get_field(WIRE, 'type', endpoint_view)
        )

        return "%s/%s/%s" % (endpoint.type, endpoint.id, endpoint.endpoint)

    def _parse_wiring_connections(self, element: rdflib.term.Node,
                                  behaviour: Union[WiringVisualDescription, WiringBehaviour]) -> None:
        for connection in self._graph.objects(element, WIRE_M['hasConnectionView']):
            for source in self._graph.objects(connection, WIRE_M['hasSourceEndpoint']):
                sourcename = self._join_endpoint_name(source)
                break
            else:
                raise TemplateParseException(_('missing required field: hasSourceEndpoint'))

            sourcehandle = self._parse_position(connection, relation_name='hasSourceHandlePosition',
                                                default=WiringConnectionHandlePositionType.auto)

            for target in self._graph.objects(connection, WIRE_M['hasTargetEndpoint']):
                targetname = self._join_endpoint_name(target)
                break
            else:
                raise TemplateParseException(_('missing required field: hasTargetEndpoint'))

            targethandle = self._parse_position(connection, relation_name='hasTargetHandlePosition',
                                                default=WiringConnectionHandlePositionType.auto)

            behaviour.connections.append(WiringVisualDescriptionConnection(
                sourcename=sourcename,
                targetname=targetname,
                sourcehandle=sourcehandle,
                targethandle=targethandle
            ))

    def _parse_wiring_behaviours(self, wiring_element: rdflib.term.Node) -> None:
        visualdescription = WiringVisualDescription()

        self._parse_wiring_components(wiring_element, visualdescription)
        self._parse_wiring_connections(wiring_element, visualdescription)

        sorted_behaviours = sorted(self._graph.objects(wiring_element, WIRE_M['hasBehaviour']), key=lambda behaviour: possible_int(self._get_field(WIRE, 'index', behaviour, required=False)))
        for view in sorted_behaviours:
            behaviour = WiringBehaviour(
                title=self._get_field(RDFS, 'label', view),
                description=self._get_field(DCTERMS, 'description', view),
                components=WiringComponents(),
                connections=[]
            )

            self._parse_wiring_components(view, behaviour)
            self._parse_wiring_connections(view, behaviour)

            visualdescription.behaviours.append(behaviour)

        self._info.wiring.visualdescription = visualdescription

    def _parse_component_info(self) -> None:
        # Platform preferences must be sorted
        sorted_preferences = sorted(self._graph.objects(self._rootURI, WIRE['hasPlatformPreference']), key=lambda pref: possible_int(self._get_field(WIRE, 'index', pref, required=False)))

        for preference in sorted_preferences:
            var_name = self._get_field(DCTERMS, 'title', preference, required=True)
            preference_info = MACDPreference(
                name=var_name,
                type=self._get_field(WIRE, 'type', preference, required=True),
                label=self._get_translation_field(RDFS, 'label', preference, var_name + '_label', required=False, type='vdef', variable=var_name, field='label'),
                description=self._get_translation_field(DCTERMS, 'description', preference, var_name + '_description', required=False, type='vdef', variable=var_name, field='description'),
                readonly=self._get_field(WIRE, 'readonly', preference, required=False).lower() == 'true',
                default=self._get_field(WIRE, 'default', preference, required=False),
                value=self._get_field(WIRE, 'value', preference, required=False, default=None),
                secure=self._get_field(WIRE, 'secure', preference, required=False).lower() == 'true',
                multiuser=False,
                required=self._get_field(WIRE, 'required', preference, required=False).lower() == 'true',
                language=self._get_field(WIRE, 'language', preference, required=False, default=None),
                options=[] if self._get_field(WIRE, 'type', preference, required=True) == 'list' else None
            )

            if preference_info.type == 'list':
                sorted_options = sorted(self._graph.objects(preference, WIRE['hasOption']), key=lambda option: possible_int(self._get_field(WIRE, 'index', option, required=False)))
                for option_index, option in enumerate(sorted_options):
                    preference_info.options.append(MACDPreferenceListOption(
                        label=self._get_translation_field(RDFS, 'label', option, var_name + '_option' + str(option_index) + '_label', required=True, type='upo', variable=var_name, option=option_index),
                        value=self._get_field(WIRE, 'value', option, required=True),
                    ))

            self._info.preferences.append(preference_info)

        # State properties info
        sorted_properties = sorted(self._graph.objects(self._rootURI, WIRE['hasPlatformStateProperty']), key=lambda prop: possible_int(self._get_field(WIRE, 'index', prop, required=False)))
        for prop in sorted_properties:
            var_name = self._get_field(DCTERMS, 'title', prop, required=True)
            self._info.properties.append(MACDProperty(
                name=var_name,
                type=self._get_field(WIRE, 'type', prop, required=True),
                label=self._get_translation_field(RDFS, 'label', prop, var_name + '_label', required=False, type='vdef', variable=var_name, field='label'),
                description=self._get_translation_field(DCTERMS, 'description', prop, var_name + '_description', required=False, type='vdef', variable=var_name, field='description'),
                default=self._get_field(WIRE, 'default', prop, required=False),
                secure=self._get_field(WIRE, 'secure', prop, required=False).lower() == 'true',
                multiuser=self._get_field(WIRE, 'multiuser', prop, required=False).lower() == 'true',
            ))

        self._parse_wiring_info()

        if self._type == MACType.widget:
            # It contains the widget code
            filtered_contents = [file for file in self._graph.objects(self._rootURI, USDL['utilizedResource']) if not str(file).endswith('.js')]
            sorted_contents = sorted(filtered_contents, key=lambda contents: possible_int(self._get_field(WIRE, 'index', contents, required=False)))

            has_main_content = False
            for contents_node in sorted_contents:
                contents_info = MACDWidgetContentsAlternative(
                    src=str(contents_node),
                    scope=self._get_field(WIRE, 'contentsScope', contents_node, required=False),
                    contenttype='text/html',
                    charset='utf-8'
                )
                contents_format = self._get_field(DCTERMS, 'format', contents_node, required=False)

                if contents_format.strip() != '':
                    try:
                        contenttype, parameters = parse_mime_type(contents_format)
                    except InvalidMimeType:
                        raise TemplateParseException(_('Invalid code content type: %s') % contents_format)

                    contents_info.contenttype = contenttype
                    if 'charset' in parameters:
                        contents_info.charset = parameters['charset'].lower()
                        del parameters['charset']

                    if len(parameters) > 0:
                        raise TemplateParseException(_('Invalid code content type: %s') % contents_format)

                if contents_info.scope == '':
                    self._info.contents = MACDWidgetContents(
                        src=contents_info.src,
                        contenttype=contents_info.contenttype,
                        charset=contents_info.charset,
                        useplatformstyle=self._get_field(WIRE, 'usePlatformStyle', contents_node, required=False).lower() == 'true',
                        cacheable=self._get_field(WIRE, 'codeCacheable', contents_node, required=False, default='true').lower() == 'true'
                    )
                    has_main_content = True
                else:
                    self._info.altcontents.append(contents_info)

            if not has_main_content:
                raise TemplateParseException(_('Missing required field: Main content'))

            rendering_element = self._get_field(WIRE, 'hasPlatformRendering', self._rootURI, id_=True, required=True)

            self._info.widget_width = self._get_field(WIRE, 'renderingWidth', rendering_element, required=True)
            self._info.widget_height = self._get_field(WIRE, 'renderingHeight', rendering_element, required=True)

        if (self._type == MACType.widget and self._info.macversion > 1) or self._info.type == MACType.operator:
            # The tamplate has 1-n javascript elements

            # Javascript files must be sorted
            filtered_files = [file for file in self._graph.objects(self._rootURI, USDL['utilizedResource']) if str(file).endswith('.js')]
            sorted_js_files = sorted(filtered_files, key=lambda js_file: possible_int(self._get_field(WIRE, 'index', js_file, required=True)))

            for js_element in sorted_js_files:
                self._info.js_files.append(str(js_element))

            # JS files are optional on v1 widgets
            if (self._type == MACType.operator or (self._type == MACType.widget and self._info.macversion > 1)) and not len(self._info.js_files) > 0:
                raise TemplateParseException(_('Missing required field: Javascript files'))

            if self._info.macversion > 1:
                self._info.entrypoint = self._get_field(WIRE, 'entryPoint', self._rootURI, required=False, default=None)

    def _parse_translation_catalogue(self) -> None:
        self._info.translations = self._translations
        self._info.translation_index_usage = self._translation_indexes

        self._info.check_translations()

    def _parse_workspace_info(self) -> None:
        preferences = {}

        for preference in self._graph.objects(self._rootURI, WIRE_M['hasMashupPreference']):
            preferences[self._get_field(DCTERMS, 'title', preference)] = self._get_field(WIRE, 'value', preference)

        self._info.preferences = preferences

        ordered_params = sorted(self._graph.objects(self._rootURI, WIRE_M['hasMashupParam']), key=lambda raw_param: possible_int(self._get_field(WIRE, 'index', raw_param, required=False)))
        for param in ordered_params:
            var_name = self._get_field(DCTERMS, 'title', param, required=True)
            self._info.params.append(MACDMashupPreference(
                name=var_name,
                type=self._get_field(WIRE, 'type', param),
                label=self._get_translation_field(RDFS, 'label', param, var_name + '_label', required=False, type='vdef', variable=var_name, field='label'),
                description=self._get_translation_field(DCTERMS, 'description', param, var_name + '_description', required=False, type='vdef', variable=var_name, field='description'),
                readonly=self._get_field(WIRE, 'readonly', param, required=False).lower() == 'true',
                default=self._get_field(WIRE, 'default', param, required=False),
                value=self._get_field(WIRE, 'value', param, required=False, default=None),
                required=self._get_field(WIRE, 'required', param, required=False).lower() == 'true'
            ))

        for component in self._graph.objects(self._rootURI, WIRE_M['hasEmbeddedResource']):
            vendor = self._get_field(USDL, 'hasProvider', component, id_=True, required=True)

            self._info.embedded.append(MACDMashupEmbedded(
                vendor=self._get_field(FOAF, 'name', vendor),
                name=self._get_field(RDFS, 'label', component),
                version=self._get_field(USDL, 'versionInfo', component),
                src=str(component)
            ))

        ordered_tabs = sorted(self._graph.objects(self._rootURI, WIRE_M['hasTab']), key=lambda raw_tab: possible_int(self._get_field(WIRE, 'index', raw_tab, required=False)))

        tabs = []
        for tab in ordered_tabs:
            tab_info = MACDTab(
                name=self._get_field(DCTERMS, 'title', tab),
                title=self._get_field(WIRE, 'displayName', tab, required=False),
            )

            for preference in self._graph.objects(tab, WIRE_M['hasTabPreference']):
                tab_info.preferences[self._get_field(DCTERMS, 'title', preference)] = self._get_field(WIRE, 'value', preference)

            # Resolve (and, if 'legacy default', drop) the effective 'screenSizes' preference for
            # this tab; legacy hasPosition/hasiWidgetRendering widget layouts must then be
            # remapped to the new default desktop screen size instead of the old (now
            # meaningless) screen size id.
            tab_legacy_default_screen_sizes = resolve_legacy_screen_sizes(tab_info.preferences, self._info.preferences)

            for widget in self._graph.objects(tab, WIRE_M['hasiWidget']):
                vendor = self._get_field(USDL, 'hasProvider', widget, id_=True, required=True)

                widget_info = MACDMashupResource(
                    id=self._get_field(WIRE_M, 'iWidgetId', widget),
                    vendor=self._get_field(FOAF, 'name', vendor),
                    name=self._get_field(RDFS, 'label', widget),
                    version=self._get_field(USDL, 'versionInfo', widget),
                    title=self._get_field(DCTERMS, 'title', widget),
                    readonly=self._get_field(WIRE_M, 'readonly', widget, required=False).lower() == 'true',
                )

                layout_nodes = list(self._graph.objects(widget, WIRE_M['hasLayout']))
                if len(layout_nodes) > 0:
                    for layout_node in layout_nodes:
                        screen_size_id = self._get_field(WIRE_M, 'screenSizeId', layout_node)
                        x = self._get_field(WIRE_M, 'x', layout_node, required=False, default=None)
                        y = self._get_field(WIRE_M, 'y', layout_node, required=False, default=None)
                        widget_info.layouts[str(screen_size_id)] = MACDMashupResourceLayout(
                            x=int(x) if x is not None else None,
                            y=int(y) if y is not None else None,
                            w=int(self._get_field(WIRE_M, 'w', layout_node, required=False, default='1')),
                            h=int(self._get_field(WIRE_M, 'h', layout_node, required=False, default='1')),
                            minimized=self._get_field(WIRE_M, 'minimized', layout_node, required=False).lower() == 'true',
                            titlevisible=self._get_field(WIRE_M, 'titlevisible', layout_node, default='true', required=False).lower() == 'true',
                            fulldragboard=self._get_field(WIRE_M, 'fullDragboard', layout_node, required=False).lower() == 'true',
                            visible=self._get_field(WIRE_M, 'visible', layout_node, default='true', required=False).lower() == 'true',
                            dock=self._get_field(WIRE_M, 'dock', layout_node, default=None, required=False),
                            dock_mode=self._get_field(WIRE_M, 'dockMode', layout_node, default='overlay', required=False),
                            dock_open=self._get_field(WIRE_M, 'dockOpen', layout_node, default='false', required=False).lower() == 'true',
                        )
                else:
                    # Legacy formats, converted best-effort:
                    #  - one or more hasScreenSize nodes, each with its own hasPosition/hasiWidgetRendering
                    #  - a single hasPosition + hasiWidgetRendering pair directly on the widget
                    screen_sizes = list(self._graph.objects(widget, WIRE_M['hasScreenSize']))
                    if len(screen_sizes) > 0:
                        for screenSize in screen_sizes:
                            legacy_position = self._get_field(WIRE_M, 'hasPosition', screenSize, id_=True, required=False, default=None)
                            legacy_rendering = self._get_field(WIRE_M, 'hasiWidgetRendering', screenSize, id_=True, required=False, default=None)
                            if legacy_position is None or legacy_rendering is None:
                                continue
                            key = str(default_desktop_screen_size_id()) if tab_legacy_default_screen_sizes \
                                else str(self._get_field(WIRE_M, 'screenSizeId', screenSize))
                            widget_info.layouts[key] = MACDMashupResourceLayout(**convert_legacy_layout(
                                top=float(self._get_field(WIRE_M, 'y', legacy_position)),
                                left=float(self._get_field(WIRE_M, 'x', legacy_position)),
                                width=float(self._get_field(WIRE, 'renderingWidth', legacy_rendering)),
                                height=float(self._get_field(WIRE, 'renderingHeight', legacy_rendering)),
                                relx=self._get_field(WIRE_M, 'relx', legacy_position, required=False, default='true').lower() == 'true',
                                rely=self._get_field(WIRE_M, 'rely', legacy_position, required=False, default='true').lower() == 'true',
                                relwidth=self._get_field(WIRE_M, 'relwidth', legacy_rendering, required=False, default='true').lower() == 'true',
                                relheight=self._get_field(WIRE_M, 'relheight', legacy_rendering, required=False, default='true').lower() == 'true',
                                minimized=self._get_field(WIRE_M, 'minimized', legacy_rendering, required=False).lower() == 'true',
                                titlevisible=self._get_field(WIRE_M, 'titlevisible', legacy_rendering, default='true', required=False).lower() == 'true',
                                fulldragboard=self._get_field(WIRE_M, 'fullDragboard', legacy_rendering, required=False).lower() == 'true',
                                layout=int(self._get_field(WIRE_M, 'layout', widget, required=False, default='0')),
                            ))
                    else:
                        legacy_position = self._get_field(WIRE_M, 'hasPosition', widget, id_=True, required=False, default=None)
                        legacy_rendering = self._get_field(WIRE_M, 'hasiWidgetRendering', widget, id_=True, required=False, default=None)
                        if legacy_position is not None and legacy_rendering is not None:
                            key = str(default_desktop_screen_size_id()) if tab_legacy_default_screen_sizes else '0'
                            widget_info.layouts[key] = MACDMashupResourceLayout(**convert_legacy_layout(
                                top=float(self._get_field(WIRE_M, 'y', legacy_position)),
                                left=float(self._get_field(WIRE_M, 'x', legacy_position)),
                                width=float(self._get_field(WIRE, 'renderingWidth', legacy_rendering)),
                                height=float(self._get_field(WIRE, 'renderingHeight', legacy_rendering)),
                                relx=self._get_field(WIRE_M, 'relx', legacy_position, required=False, default='true').lower() == 'true',
                                rely=self._get_field(WIRE_M, 'rely', legacy_position, required=False, default='true').lower() == 'true',
                                relwidth=self._get_field(WIRE_M, 'relwidth', legacy_rendering, required=False, default='true').lower() == 'true',
                                relheight=self._get_field(WIRE_M, 'relheight', legacy_rendering, required=False, default='true').lower() == 'true',
                                minimized=self._get_field(WIRE_M, 'minimized', legacy_rendering, required=False).lower() == 'true',
                                titlevisible=self._get_field(WIRE_M, 'titlevisible', legacy_rendering, default='true', required=False).lower() == 'true',
                                fulldragboard=self._get_field(WIRE_M, 'fullDragboard', legacy_rendering, required=False).lower() == 'true',
                                layout=int(self._get_field(WIRE_M, 'layout', legacy_rendering, required=False, default='0')),
                            ))

                for prop in self._graph.objects(widget, WIRE_M['hasiWidgetProperty']):
                    widget_info.properties[self._get_field(DCTERMS, 'title', prop)] = MACDMashupResourceProperty(
                        readonly=self._get_field(WIRE_M, 'readonly', prop, required=False).lower() == 'true',
                        value=self._get_field(WIRE, 'value', prop, default=None, required=False),
                    )

                for pref in self._graph.objects(widget, WIRE_M['hasiWidgetPreference']):
                    widget_info.preferences[self._get_field(DCTERMS, 'title', pref)] = MACDMashupResourcePreference(
                        readonly=self._get_field(WIRE_M, 'readonly', pref, required=False).lower() == 'true',
                        hidden=self._get_field(WIRE_M, 'hidden', pref, required=False).lower() == 'true',
                        value=self._get_field(WIRE, 'value', pref, default=None, required=False),
                    )

                tab_info.resources.append(widget_info)

            tabs.append(tab_info)

        self._info.tabs = tabs

        self._parse_wiring_info(wiring_property='hasMashupWiring')

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
