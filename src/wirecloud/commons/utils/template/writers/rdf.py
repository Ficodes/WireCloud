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

import rdflib
from urllib.parse import quote as urlquote
from typing import Union

from wirecloud.commons.utils.translation import replace_trans_index
from wirecloud.commons.utils.template.schemas.macdschemas import (MACD, MACDMashup, MACType,
                                                                      MACDTranslationIndexUsage, MACDWidgetContents,
                                                                      MACDWidgetContentsAlternative)
from wirecloud.platform.wiring.schemas import (WiringComponents, WiringConnectionHandlePositionType, WiringPosition,
                                                   WiringVisualDescriptionConnection)


WIRE = rdflib.Namespace("http://wirecloud.conwet.fi.upm.es/ns/widget#")
WIRE_M = rdflib.Namespace("http://wirecloud.conwet.fi.upm.es/ns/mashup#")
FOAF = rdflib.Namespace('http://xmlns.com/foaf/0.1/')
RDF = rdflib.Namespace('http://www.w3.org/1999/02/22-rdf-syntax-ns#')
RDFS = rdflib.Namespace('http://www.w3.org/2000/01/rdf-schema#')
DCTERMS = rdflib.Namespace('http://purl.org/dc/terms/')
USDL = rdflib.Namespace('http://www.linked-usdl.org/ns/usdl-core#')
VCARD = rdflib.Namespace('http://www.w3.org/2006/vcard/ns#')
XSD = rdflib.Namespace('http://www.w3.org/2001/XMLSchema#')
CTAG = rdflib.Namespace('http://commontag.org/ns#')
ORG = rdflib.Namespace('http://www.w3.org/ns/org#')
SKOS = rdflib.Namespace('http://www.w3.org/2004/02/skos/core#')
TIME = rdflib.Namespace('http://www.w3.org/2006/time#')
GR = rdflib.Namespace('http://purl.org/goodrelations/v1#')
DOAP = rdflib.Namespace('http://usefulinc.com/ns/doap#')


def add_translated_nodes(graph: rdflib.Graph, parent_node: Union[rdflib.BNode, rdflib.URIRef],
                         namespace: rdflib.Namespace, element_name: str, value: str, usage: MACDTranslationIndexUsage,
                         template_info: MACD) -> None:
    used_translation_vars = []
    for translation_var_name, translation_var_usage in template_info.translation_index_usage.items():
        for usage_info in translation_var_usage:
            if usage_info == usage:
                used_translation_vars.append(translation_var_name)
                break

    if len(used_translation_vars) > 0:
        for lang, catalogue in template_info.translations.items():
            msg = value
            for translation_var_name in used_translation_vars:
                msg = replace_trans_index(translation_var_name, catalogue[translation_var_name], msg)

            graph.add((parent_node, namespace[element_name], rdflib.Literal(msg, lang=lang)))
    else:
        graph.add((parent_node, namespace[element_name], rdflib.Literal(value)))


def write_wiring_components_graph(graph: rdflib.Graph, behaviour: rdflib.BNode, components: WiringComponents, type: str) -> None:
    for key, component in getattr(components, type).items():
        component_view = rdflib.BNode()
        graph.add((component_view, rdflib.RDF.type, WIRE_M['ComponentView']))
        graph.add((component_view, WIRE['type'], rdflib.Literal(type)))
        graph.add((component_view, WIRE['id'], rdflib.Literal(key)))

        if component.collapsed:
            graph.add((component_view, WIRE_M['collapsed'], rdflib.Literal('true')))

        if component.position is not None:
            write_position_graph(graph, component_view, component.position)

        if component.endpoints is not None:
            for index, source in enumerate(component.endpoints.source):
                source_element = rdflib.BNode()
                graph.add((source_element, rdflib.RDF.type, WIRE_M['Source']))
                graph.add((component_view, WIRE_M['hasSource'], source_element))
                graph.add((source_element, RDFS['label'], rdflib.Literal(source)))
                graph.add((source_element, WIRE['index'], rdflib.Literal(str(index))))

            for index, target in enumerate(component.endpoints.target):
                target_element = rdflib.BNode()
                graph.add((target_element, rdflib.RDF.type, WIRE_M['Target']))
                graph.add((component_view, WIRE_M['hasTarget'], target_element))
                graph.add((target_element, RDFS['label'], rdflib.Literal(target)))
                graph.add((target_element, WIRE['index'], rdflib.Literal(str(index))))

        graph.add((behaviour, WIRE_M['hasComponentView'], component_view))


def write_endpoint_graph(graph: rdflib.Graph, node: rdflib.BNode, endpoint_view: str,
                         relation_name: str = 'hasEndpoint') -> None:
    component_type, component_id, endpoint_name = endpoint_view.split("/")
    endpoint = rdflib.BNode()

    graph.add((endpoint, rdflib.RDF.type, WIRE_M['Endpoint']))
    graph.add((endpoint, WIRE['type'], rdflib.Literal(component_type)))
    graph.add((endpoint, WIRE_M['id'], rdflib.Literal(str(component_id))))
    graph.add((endpoint, WIRE_M['endpoint'], rdflib.Literal(endpoint_name)))

    graph.add((node, WIRE_M[relation_name], endpoint))


def write_position_graph(graph: rdflib.Graph, node: rdflib.BNode, position_view: WiringPosition,
                         relation_name: str = 'hasPosition') -> None:
    position = rdflib.BNode()

    graph.add((position, rdflib.RDF.type, WIRE_M['Position']))
    graph.add((position, WIRE_M['x'], rdflib.Literal(str(position_view.x))))
    graph.add((position, WIRE_M['y'], rdflib.Literal(str(position_view.y))))

    graph.add((node, WIRE_M[relation_name], position))


def write_wiring_connections_graph(graph: rdflib.Graph, behaviour: rdflib.BNode,
                                   connections: list[WiringVisualDescriptionConnection]) -> None:
    for connection in connections:
        connection_view = rdflib.BNode()
        graph.add((connection_view, rdflib.RDF.type, WIRE_M['ConnectionView']))

        # write source endpoint
        write_endpoint_graph(graph, connection_view, connection.sourcename, relation_name="hasSourceEndpoint")

        if connection.sourcehandle != WiringConnectionHandlePositionType.auto:
            write_position_graph(graph, connection_view, connection.sourcehandle,
                                 relation_name="hasSourceHandlePosition")

        # write target endpoint
        write_endpoint_graph(graph, connection_view, connection.targetname, relation_name="hasTargetEndpoint")

        if connection.targethandle != WiringConnectionHandlePositionType.auto:
            write_position_graph(graph, connection_view, connection.targethandle,
                                 relation_name="hasTargetHandlePosition")

        graph.add((behaviour, WIRE_M['hasConnectionView'], connection_view))


def write_wiring_visualdescription_graph(graph: rdflib.Graph, wiring: rdflib.BNode, template_info: MACDMashup) -> None:
    write_wiring_components_graph(graph, wiring, template_info.wiring.visualdescription.components, 'widget')
    write_wiring_components_graph(graph, wiring, template_info.wiring.visualdescription.components, 'operator')
    write_wiring_connections_graph(graph, wiring, template_info.wiring.visualdescription.connections)

    for index, behaviour in enumerate(template_info.wiring.visualdescription.behaviours):
        wiring_view = rdflib.BNode()
        graph.add((wiring_view, rdflib.RDF.type, WIRE_M['Behaviour']))
        graph.add((wiring_view, WIRE['index'], rdflib.Literal(str(index))))
        graph.add((wiring_view, RDFS['label'], rdflib.Literal(behaviour.title)))
        graph.add((wiring_view, DCTERMS['description'], rdflib.Literal(behaviour.description)))

        write_wiring_components_graph(graph, wiring_view, behaviour.components, 'widget')
        write_wiring_components_graph(graph, wiring_view, behaviour.components, 'operator')
        write_wiring_connections_graph(graph, wiring_view, behaviour.connections)

        graph.add((wiring, WIRE_M['hasBehaviour'], wiring_view))


def write_mashup_params(graph: rdflib.Graph, resource_uri: rdflib.URIRef, template_info: MACDMashup) -> None:
    if len(template_info.params) > 0:
        for param_index, param in enumerate(template_info.params):
            param_node = rdflib.BNode()
            graph.add((param_node, DCTERMS['title'], rdflib.Literal(param.name)))
            graph.add((param_node, WIRE['index'], rdflib.Literal(str(param_index))))
            graph.add((param_node, RDFS['label'], rdflib.Literal(param.label)))
            graph.add((param_node, WIRE['type'], rdflib.Literal(param.type)))
            graph.add((param_node, DCTERMS['description'], rdflib.Literal(param.description)))

            if param.readonly:
                graph.add((param_node, WIRE['readonly'], rdflib.Literal('true')))

            if param.default != "":
                graph.add((param_node, WIRE['default'], rdflib.Literal(param.default)))

            if param.value is not None:
                graph.add((param_node, WIRE['value'], rdflib.Literal(param.value)))

            if not param.required:
                graph.add((param_node, WIRE['required'], rdflib.Literal('false')))

            graph.add((resource_uri, WIRE_M['hasMashupParam'], param_node))


def write_mashup_embedded_resources(graph: rdflib.Graph, resource_uri: rdflib.URIRef, template_info: MACDMashup) -> None:
    if len(template_info.embedded) > 0:
        for resource in template_info.embedded:
            resource_node = rdflib.URIRef(resource.src)
            graph.add((resource_uri, WIRE_M['hasEmbeddedResource'], resource_node))

            provider_node = rdflib.BNode()
            graph.add((provider_node, rdflib.RDF.type, GR['BussisnessEntity']))
            graph.add((provider_node, FOAF['name'], rdflib.Literal(resource.vendor)))
            graph.add((resource_node, USDL['hasProvider'], provider_node))
            graph.add((resource_node, RDFS['label'], rdflib.Literal(resource.name)))
            graph.add((resource_node, USDL['versionInfo'], rdflib.Literal(resource.version)))


def write_mashup_resources_graph(graph: rdflib.Graph, resource_uri: rdflib.URIRef, template_info: MACDMashup) -> None:
    # Tabs & resources
    for tab_index, tab in enumerate(template_info.tabs):
        tab_element = rdflib.BNode()
        graph.add((tab_element, rdflib.RDF.type, WIRE_M['Tab']))
        graph.add((resource_uri, WIRE_M['hasTab'], tab_element))
        graph.add((tab_element, DCTERMS['title'], rdflib.Literal(tab.name)))
        if tab.title != "":
            graph.add((tab_element, WIRE['displayName'], rdflib.Literal(tab.title)))
        graph.add((tab_element, WIRE['index'], rdflib.Literal(str(tab_index))))

        for preference_name in tab.preferences:
            pref = rdflib.BNode()
            graph.add((pref, rdflib.RDF.type, WIRE_M['TabPreference']))
            graph.add((tab_element, WIRE_M['hasTabPreference'], pref))
            graph.add((pref, DCTERMS['title'], rdflib.Literal(preference_name)))
            graph.add((pref, WIRE['value'], rdflib.Literal(tab.preferences[preference_name])))

        for iwidget in tab.resources:
            resource = rdflib.BNode()
            graph.add((resource, WIRE_M['iWidgetId'], rdflib.Literal(iwidget.id)))
            graph.add((resource, rdflib.RDF.type, WIRE_M['iWidget']))
            graph.add((tab_element, WIRE_M['hasiWidget'], resource))
            provider = rdflib.BNode()
            graph.add((provider, rdflib.RDF.type, GR['BussisnessEntity']))
            graph.add((provider, FOAF['name'], rdflib.Literal(iwidget.vendor)))
            graph.add((resource, USDL['hasProvider'], provider))
            graph.add((resource, RDFS['label'], rdflib.Literal(iwidget.name)))
            graph.add((resource, USDL['versionInfo'], rdflib.Literal(iwidget.version)))
            graph.add((resource, DCTERMS['title'], rdflib.Literal(iwidget.title)))

            if iwidget.readonly:
                graph.add((resource, WIRE_M['readonly'], rdflib.Literal('true')))

            for screen_size_id, layout in iwidget.layouts.items():
                layout_node = rdflib.BNode()
                graph.add((layout_node, rdflib.RDF.type, WIRE_M['Layout']))
                graph.add((resource, WIRE_M['hasLayout'], layout_node))
                graph.add((layout_node, WIRE_M['screenSizeId'], rdflib.Literal(str(screen_size_id))))
                if layout.x is not None:
                    graph.add((layout_node, WIRE_M['x'], rdflib.Literal(str(layout.x))))
                if layout.y is not None:
                    graph.add((layout_node, WIRE_M['y'], rdflib.Literal(str(layout.y))))
                graph.add((layout_node, WIRE_M['w'], rdflib.Literal(str(layout.w))))
                graph.add((layout_node, WIRE_M['h'], rdflib.Literal(str(layout.h))))
                graph.add((layout_node, WIRE_M['minimized'], rdflib.Literal(str(layout.minimized).lower())))
                graph.add((layout_node, WIRE_M['titlevisible'], rdflib.Literal(str(layout.titlevisible).lower())))
                graph.add((layout_node, WIRE_M['fullDragboard'], rdflib.Literal(str(layout.fulldragboard).lower())))
                graph.add((layout_node, WIRE_M['visible'], rdflib.Literal(str(layout.visible).lower())))

            # iWidget preferences
            for pref_name, pref in iwidget.preferences.items():
                element = rdflib.BNode()
                graph.add((element, rdflib.RDF.type, WIRE_M['iWidgetPreference']))
                graph.add((resource, WIRE_M['hasiWidgetPreference'], element))
                graph.add((element, DCTERMS['title'], rdflib.Literal(pref_name)))
                if pref.value is not None:
                    graph.add((element, WIRE['value'], rdflib.Literal(pref.value)))
                if pref.readonly:
                    graph.add((element, WIRE_M['readonly'], rdflib.Literal('true')))
                if pref.hidden:
                    graph.add((element, WIRE_M['hidden'], rdflib.Literal('true')))

            for prop_name, prop in iwidget.properties.items():
                element = rdflib.BNode()
                graph.add((element, rdflib.RDF.type, WIRE_M['iWidgetProperty']))
                graph.add((resource, WIRE_M['hasiWidgetProperty'], element))
                graph.add((element, DCTERMS['title'], rdflib.Literal(prop_name)))
                if prop.value is not None:
                    graph.add((element, WIRE['value'], rdflib.Literal(prop.value)))
                if prop.readonly:
                    graph.add((element, WIRE_M['readonly'], rdflib.Literal('true')))


def write_mashup_wiring_graph(graph: rdflib.Graph, wiring: rdflib.BNode, template_info: MACDMashup) -> None:
    graph.add((wiring, USDL['versionInfo'], rdflib.Literal(template_info.wiring.version)))

    # Serialize operators
    for id_, operator in template_info.wiring.operators.items():
        op = rdflib.BNode()
        graph.add((op, rdflib.RDF.type, WIRE_M['iOperator']))
        graph.add((wiring, WIRE_M['hasiOperator'], op))
        graph.add((op, DCTERMS['title'], rdflib.Literal(operator.name)))
        graph.add((op, WIRE_M['iOperatorId'], rdflib.Literal(str(id_))))

        for pref_name, pref in operator.preferences.items():
            element = rdflib.BNode()
            graph.add((element, rdflib.RDF.type, WIRE_M['iOperatorPreference']))
            graph.add((op, WIRE_M['hasiOperatorPreference'], element))
            graph.add((element, DCTERMS['title'], rdflib.Literal(pref_name)))
            if pref.value is not None:
                graph.add((element, WIRE['value'], rdflib.Literal(pref.value)))
            if pref.readonly:
                graph.add((element, WIRE_M['readonly'], rdflib.Literal('true')))
            if pref.hidden:
                graph.add((element, WIRE_M['hidden'], rdflib.Literal('true')))

    # Serialize connections
    for connection in template_info.wiring.connections:
        element = rdflib.BNode()
        graph.add((element, rdflib.RDF.type, WIRE_M['Connection']))
        graph.add((wiring, WIRE_M['hasConnection'], element))

        if connection.readonly:
            graph.add((element, WIRE_M['readonly'], rdflib.Literal('true')))

        source = rdflib.BNode()
        graph.add((source, rdflib.RDF.type, WIRE_M['Source']))
        graph.add((element, WIRE_M['hasSource'], source))
        graph.add((source, WIRE['type'], rdflib.Literal(connection.source.type.value)))
        graph.add((source, WIRE_M['sourceId'], rdflib.Literal(connection.source.id)))
        graph.add((source, WIRE_M['endpoint'], rdflib.Literal(connection.source.endpoint)))

        target = rdflib.BNode()
        graph.add((target, rdflib.RDF.type, WIRE_M['Target']))
        graph.add((element, WIRE_M['hasTarget'], target))
        graph.add((target, WIRE['type'], rdflib.Literal(connection.target.type.value)))
        graph.add((target, WIRE_M['targetId'], rdflib.Literal(connection.target.id)))
        graph.add((target, WIRE_M['endpoint'], rdflib.Literal(connection.target.endpoint)))

    write_wiring_visualdescription_graph(graph, wiring, template_info)


def write_contents_node(graph: rdflib.Graph, resource_uri: rdflib.URIRef,
                        contents_info: Union[MACDWidgetContents, MACDWidgetContentsAlternative],
                        alternative: bool = True) -> None:
    contents_node = rdflib.URIRef(contents_info.src)
    graph.add((contents_node, rdflib.RDF.type, USDL['Resource']))
    graph.add((resource_uri, USDL['utilizedResource'], contents_node))

    if contents_info.contenttype != 'text/html' or contents_info.charset != 'utf-8':
        contenttype = contents_info.contenttype + '; charset=' + contents_info.charset.upper()
        graph.add((contents_node, DCTERMS['format'], rdflib.Literal(contenttype)))

    if alternative is False:
        if not contents_info.cacheable:
            graph.add((contents_node, WIRE['codeCacheable'], rdflib.Literal('false')))

        if contents_info.useplatformstyle:
            graph.add((contents_node, WIRE['usePlatformStyle'], rdflib.Literal('true')))
    else:
        graph.add((contents_node, WIRE['contentsScope'], rdflib.Literal(contents_info.scope)))


def build_rdf_graph(template_info: MACD) -> rdflib.Graph:
    graph = rdflib.Graph()
    graph.bind('dcterms', DCTERMS)
    graph.bind('foaf', FOAF)
    graph.bind('usdl', USDL)
    graph.bind('vcard', VCARD)
    graph.bind('wire', WIRE)
    graph.bind('wire-m', WIRE_M)
    graph.bind('gr', GR)

    uri = urlquote(template_info.vendor + '/' + template_info.name + '/' + template_info.version)
    if template_info.type == MACType.widget:
        resource_uri = rdflib.URIRef(WIRE[uri])
        graph.add((resource_uri, rdflib.RDF.type, WIRE['Widget']))
    elif template_info.type == MACType.operator:
        resource_uri = rdflib.URIRef(WIRE[uri])
        graph.add((resource_uri, rdflib.RDF.type, WIRE['Operator']))
    elif template_info.type == MACType.mashup:
        resource_uri = rdflib.URIRef(WIRE_M[uri])
        graph.add((resource_uri, rdflib.RDF.type, WIRE_M['Mashup']))
    else:
        raise Exception('Unsupported resource type: %s' % template_info.type.value)

    # Macversion
    graph.add((resource_uri, WIRE['macVersion'], rdflib.Literal(str(template_info.macversion))))

    # Create basic info
    provider = rdflib.BNode()
    graph.add((provider, rdflib.RDF.type, GR['BusinessEntity']))
    graph.add((resource_uri, USDL['hasProvider'], provider))
    graph.add((provider, FOAF['name'], rdflib.Literal(template_info.vendor)))
    graph.add((resource_uri, USDL['versionInfo'], rdflib.Literal(template_info.version)))
    graph.add((resource_uri, DCTERMS['title'], rdflib.Literal(template_info.name)))
    add_translated_nodes(graph, resource_uri, DCTERMS, 'abstract', template_info.description,
                         MACDTranslationIndexUsage(type='resource', field='description'), template_info)

    longdescription = template_info.longdescription
    if longdescription != "":
        graph.add((resource_uri, DCTERMS['description'], rdflib.URIRef(longdescription)))

    for index, author in enumerate(template_info.authors):
        author_node = rdflib.BNode()
        graph.add((resource_uri, DCTERMS['creator'], author_node))
        graph.add((author_node, rdflib.RDF.type, FOAF['Person']))
        graph.add((author_node, WIRE['index'], rdflib.Literal(str(index))))
        graph.add((author_node, FOAF['name'], rdflib.Literal(author.name)))
        if author.email is not None:
            graph.add((author_node, FOAF['mbox'], rdflib.Literal(author.email)))
        if author.url is not None:
            graph.add((author_node, FOAF['homepage'], rdflib.Literal(author.url)))

    for index, contributor in enumerate(template_info.contributors):
        contributor_node = rdflib.BNode()
        graph.add((resource_uri, DCTERMS['contributor'], contributor_node))
        graph.add((contributor_node, rdflib.RDF.type, FOAF['Person']))
        graph.add((contributor_node, WIRE['index'], rdflib.Literal(str(index))))
        graph.add((contributor_node, FOAF['name'], rdflib.Literal(contributor.name)))
        if contributor.email is not None:
            graph.add((contributor_node, FOAF['mbox'], rdflib.Literal(contributor.email)))
        if contributor.url is not None:
            graph.add((contributor_node, FOAF['homepage'], rdflib.Literal(contributor.url)))

    graph.add((resource_uri, WIRE['hasImageUri'], rdflib.URIRef(template_info.image)))

    graph.add((resource_uri, WIRE['hasChangeLog'], rdflib.URIRef(template_info.changelog)))

    homepage = template_info.homepage
    if homepage != "":
        graph.add((resource_uri, FOAF['homepage'], rdflib.URIRef(homepage)))

    if template_info.doc != "":
        graph.add((resource_uri, FOAF['page'], rdflib.URIRef(template_info.doc)))

    display_name = template_info.title
    if display_name != "":
        add_translated_nodes(graph, resource_uri, WIRE, 'displayName', display_name,
                             MACDTranslationIndexUsage(type='resource', field='title'), template_info)

    license_url_text = template_info.licenseurl
    if license_url_text != "":
        license = rdflib.URIRef(license_url_text)
        graph.add((resource_uri, DCTERMS['license'], license))
        license_text = template_info.license
        if license_text != "":
            graph.add((license, rdflib.RDF.type, DCTERMS['LicenseDocument']))
            graph.add((license, RDFS['label'], rdflib.Literal(license_text)))

    issuetracker = template_info.issuetracker
    if issuetracker != "":
        graph.add((resource_uri, DOAP['bug-database'], rdflib.URIRef(issuetracker)))

    contact_email = template_info.email
    if contact_email != "":
        addr = rdflib.BNode()
        graph.add((addr, rdflib.RDF.type, VCARD['Work']))
        graph.add((resource_uri, VCARD['addr'], addr))
        graph.add((addr, VCARD['email'], rdflib.Literal(contact_email)))

    # Requirements
    for requirement in template_info.requirements:
        requirement_node = rdflib.BNode()
        graph.add((requirement_node, rdflib.RDF.type, WIRE['Feature']))
        graph.add((requirement_node, RDFS['label'], rdflib.Literal(requirement.name)))
        graph.add((resource_uri, WIRE['hasRequirement'], requirement_node))

    if template_info.type == MACType.mashup:
        write_mashup_resources_graph(graph, resource_uri, template_info)

        # Params
        write_mashup_params(graph, resource_uri, template_info)
        write_mashup_embedded_resources(graph, resource_uri, template_info)

    # Create wiring
    wiring = rdflib.BNode()
    graph.add((wiring, rdflib.RDF.type, WIRE['PlatformWiring']))
    if template_info.type == MACType.mashup:
        graph.add((resource_uri, WIRE_M['hasMashupWiring'], wiring))
    else:
        graph.add((resource_uri, WIRE['hasPlatformWiring'], wiring))

    # Output endpoints
    for output_index, output_endpoint in enumerate(template_info.wiring.outputs):
        output_node = rdflib.BNode()
        graph.add((output_node, rdflib.RDF.type, WIRE['OutputEndpoint']))
        graph.add((wiring, WIRE['hasOutputEndpoint'], output_node))
        graph.add((output_node, WIRE['index'], rdflib.Literal(str(output_index))))
        graph.add((output_node, DCTERMS['title'], rdflib.Literal(output_endpoint.name)))
        add_translated_nodes(graph, output_node, RDFS, 'label', output_endpoint.label,
                             MACDTranslationIndexUsage(type='outputendpoint', variable=output_endpoint.name, field='label'), template_info)
        add_translated_nodes(graph, output_node, DCTERMS, 'description', output_endpoint.description,
                             MACDTranslationIndexUsage(type='outputendpoint', variable=output_endpoint.name, field='description'), template_info)
        graph.add((output_node, WIRE['type'], rdflib.Literal(output_endpoint.type)))
        graph.add((output_node, WIRE['friendcode'], rdflib.Literal(output_endpoint.friendcode)))

    # Input endpoints
    for input_index, input_endpoint in enumerate(template_info.wiring.inputs):
        input_node = rdflib.BNode()
        graph.add((input_node, rdflib.RDF.type, WIRE['InputEndpoint']))
        graph.add((wiring, WIRE['hasInputEndpoint'], input_node))
        graph.add((input_node, WIRE['index'], rdflib.Literal(str(input_index))))
        graph.add((input_node, DCTERMS['title'], rdflib.Literal(input_endpoint.name)))
        add_translated_nodes(graph, input_node, RDFS, 'label', input_endpoint.label,
                             MACDTranslationIndexUsage(type='inputendpoint', variable=input_endpoint.name, field='label'), template_info)
        add_translated_nodes(graph, input_node, DCTERMS, 'description', input_endpoint.description,
                             MACDTranslationIndexUsage(type='inputendpoint', variable=input_endpoint.name, field='description'), template_info)
        graph.add((input_node, WIRE['type'], rdflib.Literal(input_endpoint.type)))
        graph.add((input_node, WIRE['friendcode'], rdflib.Literal(input_endpoint.friendcode)))
        add_translated_nodes(graph, input_node, WIRE, 'inputActionLabel', input_endpoint.actionlabel,
                             MACDTranslationIndexUsage(type='inputendpoint', variable=input_endpoint.name, field='actionlabel'), template_info)

    if template_info.type == MACType.mashup:
        write_mashup_wiring_graph(graph, wiring, template_info)

    if template_info.smartphoneimage != "":
        graph.add((resource_uri, WIRE['hasiPhoneImageUri'], rdflib.URIRef(template_info.smartphoneimage, '')))

    if template_info.type == MACType.mashup:
        # Mashup preferences
        for pref_name, pref_value in template_info.preferences.items():
            pref = rdflib.BNode()
            graph.add((pref, rdflib.RDF.type, WIRE_M['MashupPreference']))
            graph.add((resource_uri, WIRE_M['hasMashupPreference'], pref))
            graph.add((pref, DCTERMS['title'], rdflib.Literal(pref_name)))
            graph.add((pref, WIRE['value'], rdflib.Literal(pref_value)))
    else:
        # Platform preferences
        for pref_index, pref in enumerate(template_info.preferences):
            pref_node = rdflib.BNode()
            graph.add((pref_node, rdflib.RDF.type, WIRE['PlatformPreference']))
            graph.add((resource_uri, WIRE['hasPlatformPreference'], pref_node))
            graph.add((pref_node, WIRE['index'], rdflib.Literal(str(pref_index))))
            graph.add((pref_node, DCTERMS['title'], rdflib.Literal(pref.name)))
            graph.add((pref_node, WIRE['type'], rdflib.Literal(pref.type)))
            add_translated_nodes(graph, pref_node, RDFS, 'label', pref.label,
                                 MACDTranslationIndexUsage(type='vdef', variable=pref.name, field='label'), template_info)
            add_translated_nodes(graph, pref_node, DCTERMS, 'description', pref.description,
                                 MACDTranslationIndexUsage(type='vdef', variable=pref.name, field='description'), template_info)

            if pref.readonly:
                graph.add((pref_node, WIRE['readonly'], rdflib.Literal('true')))

            if pref.default != "":
                graph.add((pref_node, WIRE['default'], rdflib.Literal(pref.default)))

            if pref.value is not None:
                graph.add((pref_node, WIRE['value'], rdflib.Literal(pref.value)))

            if pref.language is not None:
                graph.add((pref_node, WIRE['language'], rdflib.Literal(pref.language)))

            if pref.secure:
                graph.add((pref_node, WIRE['secure'], rdflib.Literal('true')))

            if pref.required:
                graph.add((pref_node, WIRE['required'], rdflib.Literal('true')))

            if pref.options is not None:
                for option_index, option in enumerate(pref.options):
                    option_node = rdflib.BNode()
                    graph.add((option_node, rdflib.RDF.type, WIRE['Option']))
                    graph.add((pref_node, WIRE['hasOption'], option_node))
                    graph.add((option_node, WIRE['index'], rdflib.Literal(str(option_index))))
                    add_translated_nodes(graph, option_node, DCTERMS, 'title', option.label,
                                         MACDTranslationIndexUsage(type='upo', variable=pref.name, option=option_index), template_info)
                    graph.add((option_node, WIRE['value'], rdflib.Literal(option.value)))

        # Platform state properties
        for prop_index, prop in enumerate(template_info.properties):
            prop_node = rdflib.BNode()
            graph.add((prop_node, rdflib.RDF.type, WIRE['PlatformStateProperty']))
            graph.add((resource_uri, WIRE['hasPlatformStateProperty'], prop_node))
            graph.add((prop_node, WIRE['index'], rdflib.Literal(str(prop_index))))
            graph.add((prop_node, DCTERMS['title'], rdflib.Literal(prop.name)))
            graph.add((prop_node, WIRE['type'], rdflib.Literal(prop.type)))
            add_translated_nodes(graph, prop_node, RDFS, 'label', prop.label,
                                 MACDTranslationIndexUsage(type='vdef', variable=prop.name, field='label'), template_info)
            add_translated_nodes(graph, prop_node, DCTERMS, 'description', prop.description,
                                 MACDTranslationIndexUsage(type='vdef', variable=prop.name, field='description'), template_info)

            if prop.default != "":
                graph.add((prop_node, WIRE['default'], rdflib.Literal(prop.default)))

            if prop.secure:
                graph.add((prop_node, WIRE['secure'], rdflib.Literal('true')))

            if prop.multiuser:
                graph.add((prop_node, WIRE['multiuser'], rdflib.Literal('true')))

    # Code
    if template_info.type == MACType.widget:
        write_contents_node(graph, resource_uri, template_info.contents, alternative=False)

        for altcontents in template_info.altcontents:
            write_contents_node(graph, resource_uri, altcontents)

    if template_info.type == MACType.operator or (template_info.type == MACType.widget and template_info.macversion > 1):
        for index, js_file in enumerate(template_info.js_files):
            js_node = rdflib.URIRef(js_file)
            graph.add((js_node, rdflib.RDF.type, USDL['Resource']))
            graph.add((js_node, WIRE['index'], rdflib.Literal(str(index))))
            graph.add((resource_uri, USDL['utilizedResource'], js_node))

    if ((template_info.type == MACType.operator or template_info.type == MACType.widget) and
            template_info.macversion > 1 and template_info.entrypoint is not None):
        # Add entryPoint
        graph.add((resource_uri, WIRE['entryPoint'], rdflib.Literal(template_info.entrypoint)))

    # Rendering
    if template_info.type == MACType.widget:
        rendering = rdflib.BNode()
        graph.add((rendering, rdflib.RDF.type, WIRE['PlatformRendering']))
        graph.add((resource_uri, WIRE['hasPlatformRendering'], rendering))
        graph.add((rendering, WIRE['renderingWidth'], rdflib.Literal(template_info.widget_width)))
        graph.add((rendering, WIRE['renderingHeight'], rdflib.Literal(template_info.widget_height)))

    return graph


def write_rdf_description(template_info: MACD, format: str = 'pretty-xml') -> str:
    graph = build_rdf_graph(template_info)
    return graph.serialize(format=format, encoding='utf-8').decode('utf-8')
