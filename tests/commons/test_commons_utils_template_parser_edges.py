# -*- coding: utf-8 -*-

import json

import rdflib
import pytest
from lxml import etree
from pydantic import ValidationError

from wirecloud.commons.utils.template.base import TemplateParseException
from wirecloud.commons.utils.template.parsers import rdf as rdf_parser
from wirecloud.commons.utils.template.parsers import xml as xml_parser
from wirecloud.commons.utils.template.parsers.rdf import RDFTemplateParser
from wirecloud.commons.utils.template.parsers.xml import ApplicationMashupTemplateParser, WIRECLOUD_TEMPLATE_NS
from wirecloud.commons.utils.template.schemas.macdschemas import (
    MACDMashup,
    MACDOperator,
    MACDWidget,
    MACDWidgetContents,
    MACType,
)
from wirecloud.platform.wiring.schemas import WiringComponents, WiringVisualDescription
from wirecloud.platform.wiring.utils import get_wiring_skeleton


def _base_rdf_graph(type_uri):
    g = rdflib.Graph()
    root = rdflib.URIRef("http://example.com/root")
    provider = rdflib.BNode()
    g.add((root, rdf_parser.RDF["type"], type_uri))
    g.add((root, rdf_parser.WIRE["macVersion"], rdflib.Literal("2")))
    g.add((root, rdf_parser.USDL["hasProvider"], provider))
    g.add((provider, rdf_parser.FOAF["name"], rdflib.Literal("acme")))
    g.add((root, rdf_parser.DCTERMS["title"], rdflib.Literal("widget")))
    g.add((root, rdf_parser.USDL["versionInfo"], rdflib.Literal("1.0.0")))
    return g, root


def _mk_widget_info():
    return MACDWidget(
        type=MACType.widget,
        vendor="acme",
        name="w",
        version="1.0.0",
        contents=MACDWidgetContents(src="index.html"),
        widget_width="1",
        widget_height="1",
    )


def _mk_operator_info():
    return MACDOperator(type=MACType.operator, vendor="acme", name="o", version="1.0.0")


def _mk_mashup_info():
    m = MACDMashup(type=MACType.mashup, vendor="acme", name="m", version="1.0.0")
    m.wiring = get_wiring_skeleton()
    return m


def test_rdf_parser_field_helpers_and_people():
    rdf_parser._ = lambda text: text
    parser = RDFTemplateParser(rdflib.Graph())
    parser._translations = {}
    parser._translation_indexes = {}

    subject = rdflib.BNode()
    parser._graph.add((subject, rdf_parser.RDFS["label"], rdflib.URIRef("http://example.com/x")))
    with pytest.raises(TemplateParseException, match="Invalid content for field"):
        parser._get_translation_field(rdf_parser.RDFS, "label", subject, "L")

    subject2 = rdflib.BNode()
    parser._graph.add((subject2, rdf_parser.RDFS["label"], rdflib.Literal("Base")))
    parser._graph.add((subject2, rdf_parser.RDFS["label"], rdflib.Literal("Etiqueta", lang="es")))
    value = parser._get_translation_field(rdf_parser.RDFS, "label", subject2, "LBL", type="resource", field="title")
    assert value == "__MSG_LBL__"
    assert parser._translations["en"]["LBL"] == "Base"
    assert parser._translations["es"]["LBL"] == "Etiqueta"
    # cover branch where english catalogue already exists
    parser._translations = {"en": {"X": "Y"}}
    parser._get_translation_field(rdf_parser.RDFS, "label", subject2, "LBL2", type="resource", field="title")

    with pytest.raises(TemplateParseException, match="Missing required field"):
        parser._get_translation_field(rdf_parser.RDFS, "comment", subject2, "MUST_FAIL", required=True)

    assert parser._get_translation_field(rdf_parser.RDFS, "comment", subject2, "MISSING", required=False) == ""

    with pytest.raises(TemplateParseException, match="Missing required field"):
        parser._get_field(rdf_parser.RDFS, "comment", subject2, required=True)

    owner = rdflib.BNode()
    p1 = rdflib.BNode()
    p2 = rdflib.BNode()
    parser._graph.add((owner, rdf_parser.DCTERMS["creator"], p1))
    parser._graph.add((owner, rdf_parser.DCTERMS["creator"], p2))
    parser._graph.add((p1, rdf_parser.WIRE["index"], rdflib.Literal("0")))
    parser._graph.add((p1, rdf_parser.FOAF["name"], rdflib.Literal("")))
    parser._graph.add((p2, rdf_parser.WIRE["index"], rdflib.Literal("1")))
    parser._graph.add((p2, rdf_parser.FOAF["name"], rdflib.Literal("Alice")))
    parser._graph.add((p2, rdf_parser.FOAF["mbox"], rdflib.Literal("a@example.com")))
    parser._graph.add((p2, rdf_parser.FOAF["homepage"], rdflib.Literal("https://a")))
    people = parser._parse_people_field(rdf_parser.DCTERMS, "creator", owner)
    assert len(people) == 1
    assert people[0].name == "Alice"

    p3 = rdflib.BNode()
    parser._graph.add((owner, rdf_parser.DCTERMS["creator"], p3))
    parser._graph.add((p3, rdf_parser.WIRE["index"], rdflib.Literal("2")))
    parser._graph.add((p3, rdf_parser.FOAF["name"], rdflib.Literal("NoContact")))
    people2 = parser._parse_people_field(rdf_parser.DCTERMS, "creator", owner)
    assert any(p.name == "NoContact" for p in people2)


def test_rdf_parser_basic_info_validation_and_getters():
    rdf_parser._ = lambda text: text

    g, _root = _base_rdf_graph(rdf_parser.WIRE["Widget"])
    parser = RDFTemplateParser(g)
    parser._type = MACType.widget
    parser._parse_basic_info()
    assert parser.get_resource_type() == MACType.widget
    assert parser.get_resource_name() == "widget"
    assert parser.get_resource_vendor() == "acme"
    assert parser.get_resource_version() == "1.0.0"

    g_old, root_old = _base_rdf_graph(rdf_parser.WIRE["Widget"])
    g_old.add((root_old, rdf_parser.DCTERMS["description"], rdflib.Literal("old desc")))
    parser_old = RDFTemplateParser(g_old)
    parser_old._type = MACType.widget
    parser_old._parse_basic_info()
    assert parser_old._info.description in ("old desc", "__MSG_description__")

    g_bad_mac, root = _base_rdf_graph(rdf_parser.WIRE["Widget"])
    g_bad_mac.remove((root, rdf_parser.WIRE["macVersion"], rdflib.Literal("2")))
    g_bad_mac.add((root, rdf_parser.WIRE["macVersion"], rdflib.Literal("x")))
    parser_bad_mac = RDFTemplateParser(g_bad_mac)
    parser_bad_mac._type = MACType.widget
    with pytest.raises(TemplateParseException, match="macversion"):
        parser_bad_mac._parse_basic_info()

    g_bad_mac2, root = _base_rdf_graph(rdf_parser.WIRE["Widget"])
    g_bad_mac2.remove((root, rdf_parser.WIRE["macVersion"], rdflib.Literal("2")))
    g_bad_mac2.add((root, rdf_parser.WIRE["macVersion"], rdflib.Literal("3")))
    parser_bad_mac2 = RDFTemplateParser(g_bad_mac2)
    parser_bad_mac2._type = MACType.widget
    with pytest.raises(TemplateParseException, match="macversion is invalid"):
        parser_bad_mac2._parse_basic_info()

    g_bad_vendor, root = _base_rdf_graph(rdf_parser.WIRE["Widget"])
    provider = next(g_bad_vendor.objects(root, rdf_parser.USDL["hasProvider"]))
    g_bad_vendor.remove((provider, rdf_parser.FOAF["name"], rdflib.Literal("acme")))
    g_bad_vendor.add((provider, rdf_parser.FOAF["name"], rdflib.Literal("ac/me")))
    parser_bad_vendor = RDFTemplateParser(g_bad_vendor)
    parser_bad_vendor._type = MACType.widget
    with pytest.raises(TemplateParseException, match="vendor is invalid"):
        parser_bad_vendor._parse_basic_info()

    g_bad_name, root = _base_rdf_graph(rdf_parser.WIRE["Widget"])
    g_bad_name.remove((root, rdf_parser.DCTERMS["title"], rdflib.Literal("widget")))
    g_bad_name.add((root, rdf_parser.DCTERMS["title"], rdflib.Literal("a/b")))
    parser_bad_name = RDFTemplateParser(g_bad_name)
    parser_bad_name._type = MACType.widget
    with pytest.raises(TemplateParseException, match="name is invalid"):
        parser_bad_name._parse_basic_info()

    g_bad_version, root = _base_rdf_graph(rdf_parser.WIRE["Widget"])
    g_bad_version.remove((root, rdf_parser.USDL["versionInfo"], rdflib.Literal("1.0.0")))
    g_bad_version.add((root, rdf_parser.USDL["versionInfo"], rdflib.Literal("bad")))
    parser_bad_version = RDFTemplateParser(g_bad_version)
    parser_bad_version._type = MACType.widget
    with pytest.raises(TemplateParseException, match="version number is invalid"):
        parser_bad_version._parse_basic_info()

    g_operator, _ = _base_rdf_graph(rdf_parser.WIRE["Operator"])
    parser_operator = RDFTemplateParser(g_operator)
    parser_operator._type = MACType.operator
    parser_operator._parse_basic_info()
    assert parser_operator.get_resource_type() == MACType.operator

    g_mashup, _ = _base_rdf_graph(rdf_parser.WIRE_M["Mashup"])
    parser_mashup = RDFTemplateParser(g_mashup)
    parser_mashup._type = MACType.mashup
    parser_mashup._parse_basic_info()
    assert parser_mashup.get_resource_type() == MACType.mashup


def test_rdf_parser_wiring_and_component_error_paths(monkeypatch):
    rdf_parser._ = lambda text: text

    parser = RDFTemplateParser(rdflib.Graph())
    parser._type = MACType.mashup
    parser._info = _mk_mashup_info()
    parser._rootURI = rdflib.URIRef("http://example.com/m")

    wiring = rdflib.BNode()
    parser._graph.add((parser._rootURI, rdf_parser.WIRE_M["hasMashupWiring"], wiring))
    parser._graph.add((wiring, rdf_parser.USDL["versionInfo"], rdflib.Literal("1.0")))
    with pytest.raises(TemplateParseException, match="Only wiring version 2.0"):
        parser._parse_wiring_info(wiring_property="hasMashupWiring")

    parser2 = RDFTemplateParser(rdflib.Graph())
    parser2._type = MACType.mashup
    parser2._info = _mk_mashup_info()
    wiring2 = rdflib.BNode()
    connection = rdflib.BNode()
    parser2._graph.add((wiring2, rdf_parser.WIRE_M["hasConnection"], connection))
    with pytest.raises(TemplateParseException, match="source"):
        parser2._parse_wiring_connection_info(wiring2)

    source = rdflib.BNode()
    parser2._graph.add((connection, rdf_parser.WIRE_M["hasSource"], source))
    parser2._graph.add((source, rdf_parser.WIRE_M["sourceId"], rdflib.Literal("r1")))
    parser2._graph.add((source, rdf_parser.WIRE_M["endpoint"], rdflib.Literal("out")))
    parser2._graph.add((source, rdf_parser.WIRE["type"], rdflib.Literal("widget")))
    with pytest.raises(TemplateParseException, match="target"):
        parser2._parse_wiring_connection_info(wiring2)

    parser3 = RDFTemplateParser(rdflib.Graph())
    entity = rdflib.BNode()
    parent = rdflib.BNode()
    parser3._graph.add((parent, rdf_parser.WIRE_M["hasComponentView"], entity))
    parser3._graph.add((entity, rdf_parser.WIRE["type"], rdflib.Literal("bad")))
    parser3._graph.add((entity, rdf_parser.WIRE["id"], rdflib.Literal("1")))
    with pytest.raises(TemplateParseException, match="Invalid component type"):
        parser3._parse_wiring_components(parent, WiringVisualDescription())

    parser4 = RDFTemplateParser(rdflib.Graph())
    connection_view = rdflib.BNode()
    parser4._graph.add((parent, rdf_parser.WIRE_M["hasConnectionView"], connection_view))
    with pytest.raises(TemplateParseException, match="hasSourceEndpoint"):
        parser4._parse_wiring_connections(parent, WiringVisualDescription())

    source_endpoint = rdflib.BNode()
    parser4._graph.add((connection_view, rdf_parser.WIRE_M["hasSourceEndpoint"], source_endpoint))
    parser4._graph.add((source_endpoint, rdf_parser.WIRE_M["id"], rdflib.Literal("1")))
    parser4._graph.add((source_endpoint, rdf_parser.WIRE_M["endpoint"], rdflib.Literal("out")))
    parser4._graph.add((source_endpoint, rdf_parser.WIRE["type"], rdflib.Literal("widget")))
    with pytest.raises(TemplateParseException, match="hasTargetEndpoint"):
        parser4._parse_wiring_connections(parent, WiringVisualDescription())

    parser5 = RDFTemplateParser(rdflib.Graph())
    entity2 = rdflib.BNode()
    parent2 = rdflib.BNode()
    parser5._graph.add((parent2, rdf_parser.WIRE_M["hasComponentView"], entity2))
    parser5._graph.add((entity2, rdf_parser.WIRE["type"], rdflib.Literal("widget")))
    parser5._graph.add((entity2, rdf_parser.WIRE["id"], rdflib.Literal("w1")))
    parser5._parse_wiring_components(parent2, WiringVisualDescription())

    parser6 = RDFTemplateParser(rdflib.Graph())
    parser6._type = MACType.operator
    parser6._info = _mk_operator_info()
    called = {"component": 0, "workspace": 0, "translations": 0}
    monkeypatch.setattr(parser6, "_parse_component_info", lambda: called.__setitem__("component", called["component"] + 1))
    monkeypatch.setattr(parser6, "_parse_workspace_info", lambda: called.__setitem__("workspace", called["workspace"] + 1))
    monkeypatch.setattr(parser6, "_parse_translation_catalogue", lambda: called.__setitem__("translations", called["translations"] + 1))
    parser6._parse_extra_info()
    assert called == {"component": 1, "workspace": 0, "translations": 1}

    parser7 = RDFTemplateParser(rdflib.Graph())
    parser7._type = MACType.mashup
    parser7._info = _mk_mashup_info()
    monkeypatch.setattr(parser7, "_parse_component_info", lambda: called.__setitem__("component", called["component"] + 1))
    monkeypatch.setattr(parser7, "_parse_workspace_info", lambda: called.__setitem__("workspace", called["workspace"] + 1))
    monkeypatch.setattr(parser7, "_parse_translation_catalogue", lambda: called.__setitem__("translations", called["translations"] + 1))
    parser7._parse_extra_info()
    assert called["workspace"] >= 1


def test_rdf_parser_component_info_error_paths(monkeypatch):
    rdf_parser._ = lambda text: text

    parser = RDFTemplateParser(rdflib.Graph())
    parser._type = MACType.widget
    parser._rootURI = rdflib.URIRef("http://example.com/w")
    parser._info = _mk_widget_info()
    monkeypatch.setattr(parser, "_parse_wiring_info", lambda *args, **kwargs: None)

    content = rdflib.URIRef("index.html")
    parser._graph.add((parser._rootURI, rdf_parser.USDL["utilizedResource"], content))
    parser._graph.add((content, rdf_parser.DCTERMS["format"], rdflib.Literal("bad")))
    monkeypatch.setattr(rdf_parser, "parse_mime_type", lambda _fmt: (_ for _ in ()).throw(rdf_parser.InvalidMimeType("x")))
    with pytest.raises(TemplateParseException, match="Invalid code content type"):
        parser._parse_component_info()

    parser2 = RDFTemplateParser(rdflib.Graph())
    parser2._type = MACType.widget
    parser2._rootURI = rdflib.URIRef("http://example.com/w2")
    parser2._info = _mk_widget_info()
    monkeypatch.setattr(parser2, "_parse_wiring_info", lambda *args, **kwargs: None)
    content2 = rdflib.URIRef("index2.html")
    parser2._graph.add((parser2._rootURI, rdf_parser.USDL["utilizedResource"], content2))
    parser2._graph.add((content2, rdf_parser.DCTERMS["format"], rdflib.Literal("text/html; charset=utf-8; foo=bar")))
    monkeypatch.setattr(rdf_parser, "parse_mime_type", lambda _fmt: ("text/html", {"charset": "utf-8", "foo": "bar"}))
    with pytest.raises(TemplateParseException, match="Invalid code content type"):
        parser2._parse_component_info()

    parser3 = RDFTemplateParser(rdflib.Graph())
    parser3._type = MACType.widget
    parser3._rootURI = rdflib.URIRef("http://example.com/w3")
    parser3._info = _mk_widget_info()
    monkeypatch.setattr(parser3, "_parse_wiring_info", lambda *args, **kwargs: None)
    alt = rdflib.URIRef("alt.html")
    parser3._graph.add((parser3._rootURI, rdf_parser.USDL["utilizedResource"], alt))
    parser3._graph.add((alt, rdf_parser.WIRE["contentsScope"], rdflib.Literal("mobile")))
    with pytest.raises(TemplateParseException, match="Main content"):
        parser3._parse_component_info()

    parser4 = RDFTemplateParser(rdflib.Graph())
    parser4._type = MACType.operator
    parser4._rootURI = rdflib.URIRef("http://example.com/o")
    parser4._info = _mk_operator_info()
    monkeypatch.setattr(parser4, "_parse_wiring_info", lambda *args, **kwargs: None)
    with pytest.raises(TemplateParseException, match="Javascript files"):
        parser4._parse_component_info()

    parser5 = RDFTemplateParser(rdflib.Graph())
    parser5._type = MACType.widget
    parser5._rootURI = rdflib.URIRef("http://example.com/w5")
    parser5._info = _mk_widget_info()
    parser5._info.macversion = 1
    monkeypatch.setattr(parser5, "_parse_wiring_info", lambda *args, **kwargs: None)
    main = rdflib.URIRef("index5.html")
    rendering = rdflib.BNode()
    parser5._graph.add((parser5._rootURI, rdf_parser.USDL["utilizedResource"], main))
    parser5._graph.add((parser5._rootURI, rdf_parser.WIRE["hasPlatformRendering"], rendering))
    parser5._graph.add((rendering, rdf_parser.WIRE["renderingWidth"], rdflib.Literal("1")))
    parser5._graph.add((rendering, rdf_parser.WIRE["renderingHeight"], rdflib.Literal("1")))
    parser5._parse_component_info()

    parser6 = RDFTemplateParser(rdflib.Graph())
    parser6._type = MACType.widget
    parser6._rootURI = rdflib.URIRef("http://example.com/w6")
    parser6._info = _mk_widget_info()
    monkeypatch.setattr(parser6, "_parse_wiring_info", lambda *args, **kwargs: None)
    main2 = rdflib.URIRef("index6.html")
    rendering2 = rdflib.BNode()
    parser6._graph.add((parser6._rootURI, rdf_parser.USDL["utilizedResource"], main2))
    parser6._graph.add((main2, rdf_parser.DCTERMS["format"], rdflib.Literal("text/plain")))
    parser6._graph.add((parser6._rootURI, rdf_parser.WIRE["hasPlatformRendering"], rendering2))
    parser6._graph.add((rendering2, rdf_parser.WIRE["renderingWidth"], rdflib.Literal("1")))
    parser6._graph.add((rendering2, rdf_parser.WIRE["renderingHeight"], rdflib.Literal("1")))
    monkeypatch.setattr(rdf_parser, "parse_mime_type", lambda _fmt: ("text/plain", {}))
    parser6._parse_component_info()


def test_xml_parser_helper_error_paths(monkeypatch):
    xml_parser._ = lambda text: text
    parser = ApplicationMashupTemplateParser(f'<widget xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="w" version="1.0.0"><details/></widget>')

    with pytest.raises(TemplateParseException, match="Missing details element"):
        parser.get_xpath("t:details", etree.Element("root"), required=True)

    with pytest.raises(TemplateParseException, match="Missing required field"):
        parser._get_field("t:title", etree.Element("root"), required=True)


def test_xml_parser_mashup_wiring_error_paths(monkeypatch):
    xml_parser._ = lambda text: text
    parser = ApplicationMashupTemplateParser(
        f'<mashup xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="m" version="1.0.0"><details/><structure/></mashup>'
    )
    parser._component_description = etree.Element("details")
    parser._parse_basic_info()
    parser._parse_workspace_info()
    assert parser._info.wiring.version == "2.0"

    # A resource with no layouts/screensizes/position/rendering at all simply has no stored
    # layouts (it is auto-placed by the client) instead of raising
    parser2 = ApplicationMashupTemplateParser(
        f'<mashup xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="m" version="1.0.0">'
        '<details/><structure><tab name="t"><resource id="r" vendor="acme" name="w" version="1.0.0"/></tab></structure>'
        '</mashup>'
    )
    parser2._component_description = etree.Element("details")
    parser2._parse_basic_info()
    parser2._parse_workspace_info()
    assert parser2._info.tabs[0].resources[0].layouts == {}


def test_rdf_parser_workspace_legacy_position_rendering(monkeypatch):
    # Legacy RDF format: a single hasPosition + hasiWidgetRendering pair directly on the widget
    # (no hasLayout, no hasScreenSize). With no screenSizes preference anywhere (tab or
    # workspace), the effective screenSizes is 'legacy default', so the converted layout is
    # remapped to the id of the platform's new default desktop screen size (not the old,
    # now-meaningless, screen size id).
    rdf_parser._ = lambda text: text

    parser = RDFTemplateParser(rdflib.Graph())
    parser._type = MACType.mashup
    parser._rootURI = rdflib.URIRef("http://example.com/m")
    parser._info = _mk_mashup_info()
    monkeypatch.setattr(parser, "_parse_wiring_info", lambda *args, **kwargs: None)

    tab = rdflib.BNode()
    parser._graph.add((parser._rootURI, rdf_parser.WIRE_M["hasTab"], tab))
    parser._graph.add((tab, rdf_parser.DCTERMS["title"], rdflib.Literal("main")))
    parser._graph.add((tab, rdf_parser.WIRE["index"], rdflib.Literal("0")))

    widget = rdflib.BNode()
    provider = rdflib.BNode()
    position = rdflib.BNode()
    rendering = rdflib.BNode()
    parser._graph.add((tab, rdf_parser.WIRE_M["hasiWidget"], widget))
    parser._graph.add((widget, rdf_parser.WIRE_M["iWidgetId"], rdflib.Literal("r1")))
    parser._graph.add((widget, rdf_parser.USDL["hasProvider"], provider))
    parser._graph.add((provider, rdf_parser.FOAF["name"], rdflib.Literal("acme")))
    parser._graph.add((widget, rdf_parser.RDFS["label"], rdflib.Literal("widget")))
    parser._graph.add((widget, rdf_parser.USDL["versionInfo"], rdflib.Literal("1.0.0")))
    parser._graph.add((widget, rdf_parser.DCTERMS["title"], rdflib.Literal("Widget")))
    parser._graph.add((widget, rdf_parser.WIRE_M["hasPosition"], position))
    parser._graph.add((widget, rdf_parser.WIRE_M["hasiWidgetRendering"], rendering))
    parser._graph.add((position, rdf_parser.WIRE_M["x"], rdflib.Literal("10")))
    parser._graph.add((position, rdf_parser.WIRE_M["y"], rdflib.Literal("8")))
    parser._graph.add((position, rdf_parser.WIRE_M["z"], rdflib.Literal("1")))
    parser._graph.add((rendering, rdf_parser.WIRE["renderingWidth"], rdflib.Literal("6")))
    parser._graph.add((rendering, rdf_parser.WIRE["renderingHeight"], rdflib.Literal("4")))

    parser._parse_workspace_info()

    from wirecloud.commons.utils.template.base import convert_legacy_layout, default_desktop_screen_size_id

    expected = convert_legacy_layout(top=8, left=10, width=6, height=4, relx=True, rely=True,
                                     relwidth=True, relheight=True)
    desktop_id = str(default_desktop_screen_size_id())
    layouts = parser._info.tabs[0].resources[0].layouts
    assert set(layouts) == {desktop_id}
    assert layouts[desktop_id].model_dump() == expected

    req = rdflib.BNode()
    parser._graph.add((parser._rootURI, rdf_parser.WIRE["hasRequirement"], req))
    parser._graph.add((req, rdf_parser.RDF["type"], rdf_parser.WIRE["Other"]))
    parser._parse_requirements()

    # A widget with neither hasLayout, hasScreenSize, nor hasPosition/hasiWidgetRendering
    # simply gets no stored layouts
    parser_empty = RDFTemplateParser(rdflib.Graph())
    parser_empty._type = MACType.mashup
    parser_empty._rootURI = rdflib.URIRef("http://example.com/m2")
    parser_empty._info = _mk_mashup_info()
    monkeypatch.setattr(parser_empty, "_parse_wiring_info", lambda *args, **kwargs: None)

    tab2 = rdflib.BNode()
    parser_empty._graph.add((parser_empty._rootURI, rdf_parser.WIRE_M["hasTab"], tab2))
    parser_empty._graph.add((tab2, rdf_parser.DCTERMS["title"], rdflib.Literal("main")))
    parser_empty._graph.add((tab2, rdf_parser.WIRE["index"], rdflib.Literal("0")))

    widget2 = rdflib.BNode()
    provider2 = rdflib.BNode()
    parser_empty._graph.add((tab2, rdf_parser.WIRE_M["hasiWidget"], widget2))
    parser_empty._graph.add((widget2, rdf_parser.WIRE_M["iWidgetId"], rdflib.Literal("r2")))
    parser_empty._graph.add((widget2, rdf_parser.USDL["hasProvider"], provider2))
    parser_empty._graph.add((provider2, rdf_parser.FOAF["name"], rdflib.Literal("acme")))
    parser_empty._graph.add((widget2, rdf_parser.RDFS["label"], rdflib.Literal("widget")))
    parser_empty._graph.add((widget2, rdf_parser.USDL["versionInfo"], rdflib.Literal("1.0.0")))
    parser_empty._graph.add((widget2, rdf_parser.DCTERMS["title"], rdflib.Literal("Widget")))

    parser_empty._parse_workspace_info()
    assert parser_empty._info.tabs[0].resources[0].layouts == {}


def test_rdf_parser_workspace_custom_screen_sizes_keeps_ids(monkeypatch):
    # A tab with a real, custom multi-interval screenSizes preference is NOT 'legacy default':
    # legacy hasScreenSize entries keep their own screen size ids instead of being remapped.
    rdf_parser._ = lambda text: text

    parser = RDFTemplateParser(rdflib.Graph())
    parser._type = MACType.mashup
    parser._rootURI = rdflib.URIRef("http://example.com/m3")
    parser._info = _mk_mashup_info()
    monkeypatch.setattr(parser, "_parse_wiring_info", lambda *args, **kwargs: None)

    tab = rdflib.BNode()
    parser._graph.add((parser._rootURI, rdf_parser.WIRE_M["hasTab"], tab))
    parser._graph.add((tab, rdf_parser.DCTERMS["title"], rdflib.Literal("main")))
    parser._graph.add((tab, rdf_parser.WIRE["index"], rdflib.Literal("0")))

    tab_pref = rdflib.BNode()
    parser._graph.add((tab, rdf_parser.WIRE_M["hasTabPreference"], tab_pref))
    parser._graph.add((tab_pref, rdf_parser.DCTERMS["title"], rdflib.Literal("screenSizes")))
    custom_screen_sizes = json.dumps([
        {"id": 4, "moreOrEqual": 0, "lessOrEqual": 767},
        {"id": 8, "moreOrEqual": 768, "lessOrEqual": -1},
    ])
    parser._graph.add((tab_pref, rdf_parser.WIRE["value"], rdflib.Literal(custom_screen_sizes)))

    widget = rdflib.BNode()
    provider = rdflib.BNode()
    parser._graph.add((tab, rdf_parser.WIRE_M["hasiWidget"], widget))
    parser._graph.add((widget, rdf_parser.WIRE_M["iWidgetId"], rdflib.Literal("r1")))
    parser._graph.add((widget, rdf_parser.USDL["hasProvider"], provider))
    parser._graph.add((provider, rdf_parser.FOAF["name"], rdflib.Literal("acme")))
    parser._graph.add((widget, rdf_parser.RDFS["label"], rdflib.Literal("widget")))
    parser._graph.add((widget, rdf_parser.USDL["versionInfo"], rdflib.Literal("1.0.0")))
    parser._graph.add((widget, rdf_parser.DCTERMS["title"], rdflib.Literal("Widget")))

    for size_id in (4, 8):
        screen_size = rdflib.BNode()
        position = rdflib.BNode()
        rendering = rdflib.BNode()
        parser._graph.add((widget, rdf_parser.WIRE_M["hasScreenSize"], screen_size))
        parser._graph.add((screen_size, rdf_parser.WIRE_M["screenSizeId"], rdflib.Literal(str(size_id))))
        parser._graph.add((screen_size, rdf_parser.WIRE_M["hasPosition"], position))
        parser._graph.add((screen_size, rdf_parser.WIRE_M["hasiWidgetRendering"], rendering))
        parser._graph.add((position, rdf_parser.WIRE_M["x"], rdflib.Literal("10")))
        parser._graph.add((position, rdf_parser.WIRE_M["y"], rdflib.Literal("8")))
        parser._graph.add((position, rdf_parser.WIRE_M["z"], rdflib.Literal("1")))
        parser._graph.add((rendering, rdf_parser.WIRE["renderingWidth"], rdflib.Literal("6")))
        parser._graph.add((rendering, rdf_parser.WIRE["renderingHeight"], rdflib.Literal("4")))

    parser._parse_workspace_info()

    layouts = parser._info.tabs[0].resources[0].layouts
    assert set(layouts) == {"4", "8"}

    # The custom preference is preserved on the tab (untouched, per §7's "leave the preference
    # value untouched" rule for templates)
    assert parser._info.tabs[0].preferences["screenSizes"] == custom_screen_sizes


def test_rdf_parser_component_info_list_options_and_validation_error(monkeypatch):
    rdf_parser._ = lambda text: text

    parser = RDFTemplateParser(rdflib.Graph())
    parser._type = MACType.operator
    parser._rootURI = rdflib.URIRef("http://example.com/o")
    parser._info = _mk_operator_info()
    monkeypatch.setattr(parser, "_parse_wiring_info", lambda *args, **kwargs: None)

    pref = rdflib.BNode()
    option = rdflib.BNode()
    parser._graph.add((parser._rootURI, rdf_parser.WIRE["hasPlatformPreference"], pref))
    parser._graph.add((pref, rdf_parser.DCTERMS["title"], rdflib.Literal("p")))
    parser._graph.add((pref, rdf_parser.WIRE["type"], rdflib.Literal("list")))
    parser._graph.add((pref, rdf_parser.WIRE["hasOption"], option))
    parser._graph.add((option, rdf_parser.WIRE["index"], rdflib.Literal("0")))
    parser._graph.add((option, rdf_parser.RDFS["label"], rdflib.Literal("Option")))
    parser._graph.add((option, rdf_parser.WIRE["value"], rdflib.Literal("v")))
    parser._graph.add((parser._rootURI, rdf_parser.USDL["utilizedResource"], rdflib.URIRef("op.js")))
    parser._graph.add((rdflib.URIRef("op.js"), rdf_parser.WIRE["index"], rdflib.Literal("0")))
    parser._parse_component_info()
    assert parser._info.preferences[0].options[0].label == "Option"

    parser_err = RDFTemplateParser(rdflib.Graph())
    parser_err._parsed = False
    parser_err._info = _mk_operator_info()
    monkeypatch.setattr(
        parser_err,
        "_parse_extra_info",
        lambda: (_ for _ in ()).throw(ValidationError.from_exception_data("X", [])),
    )
    with pytest.raises(TemplateParseException, match="Invalid template"):
        parser_err.get_resource_info()


def test_xml_parser_extra_branches_and_getters(monkeypatch):
    xml_parser._ = lambda text: text

    parser = ApplicationMashupTemplateParser(
        f'<widget xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="w" version="1.0.0">'
        "<details/>"
        "<preferences><preference name='p' type='list'><option name='a' value='1'/></preference></preferences>"
        "<wiring/>"
        "<contents src='index.html'/>"
        "<rendering width='1' height='1' layout='0'/>"
        "</widget>"
    )
    parser._component_description = etree.Element("details")
    parser._parse_basic_info()
    parser._parse_component_preferences()
    assert parser._info.preferences[0].options[0].label == "a"

    assert parser.get_resource_type() == MACType.widget
    assert parser.get_resource_name() == "w"
    assert parser.get_resource_vendor() == "acme"
    assert parser.get_resource_version() == "1.0.0"

    parser_ver1 = ApplicationMashupTemplateParser(
        f'<mashup xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="m" version="1.0.0">'
        "<details/>"
        "<structure>"
        "<tab name='t'><resource id='r' vendor='acme' name='w' version='1.0.0' title='t' layout='0'>"
        "<screensizes><screensize id='0' moreOrEqual='0' lessOrEqual='-1'><position x='1' y='2' z='1'/>"
        "<rendering width='1' height='1'/></screensize></screensizes>"
        "</resource></tab>"
        "<wiring version='1.0'/>"
        "</structure>"
        "</mashup>"
    )
    parser_ver1._component_description = etree.Element("details")
    parser_ver1._parse_basic_info()
    with pytest.raises(TemplateParseException, match="Only wiring version 2.0"):
        parser_ver1._parse_workspace_info()

    parser_bad_version = ApplicationMashupTemplateParser(
        f'<mashup xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="m" version="1.0.0">'
        "<details/>"
        "<structure>"
        "<tab name='t'><resource id='r' vendor='acme' name='w' version='1.0.0' title='t' layout='0'>"
        "<position x='1' y='2' z='1'/><rendering width='1' height='1' layout='0'/>"
        "</resource></tab>"
        "<wiring version='3.0'/>"
        "</structure>"
        "</mashup>"
    )
    parser_bad_version._component_description = etree.Element("details")
    parser_bad_version._parse_basic_info()
    with pytest.raises(TemplateParseException, match="Invalid wiring version"):
        parser_bad_version._parse_workspace_info()

    # Legacy <screensizes> parses fine without any 'layout' attribute on <resource> (that
    # attribute, and the requirement for it, no longer exist). No screenSizes preference is
    # present anywhere, so the effective value is 'legacy default' and the single old
    # screensize's converted layout is remapped to the new default desktop screen size id.
    parser_legacy_screensizes = ApplicationMashupTemplateParser(
        f'<mashup xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="m" version="1.0.0">'
        "<details/>"
        "<structure><tab name='t'><resource id='r' vendor='acme' name='w' version='1.0.0' title='t'>"
        "<screensizes><screensize id='0' moreOrEqual='0' lessOrEqual='-1'><position x='1' y='2' z='1'/>"
        "<rendering width='1' height='1'/></screensize></screensizes>"
        "</resource></tab></structure>"
        "</mashup>"
    )
    parser_legacy_screensizes._component_description = etree.Element("details")
    parser_legacy_screensizes._parse_basic_info()
    parser_legacy_screensizes._parse_workspace_info()
    from wirecloud.commons.utils.template.base import default_desktop_screen_size_id
    legacy_layouts = parser_legacy_screensizes._info.tabs[0].resources[0].layouts
    assert set(legacy_layouts) == {str(default_desktop_screen_size_id())}

    # A tab with a real, custom multi-interval screenSizes preference keeps the legacy
    # screensize's own id instead of remapping it
    parser_custom_screensizes = ApplicationMashupTemplateParser(
        f'<mashup xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="m" version="1.0.0">'
        "<details/>"
        "<structure><tab name='t'>"
        '<preferencevalue name="screenSizes" '
        'value=\'[{"id": 4, "moreOrEqual": 0, "lessOrEqual": 767}, {"id": 8, "moreOrEqual": 768, "lessOrEqual": -1}]\'/>'
        "<resource id='r' vendor='acme' name='w' version='1.0.0' title='t'>"
        "<screensizes><screensize id='8' moreOrEqual='0' lessOrEqual='-1'><position x='1' y='2' z='1'/>"
        "<rendering width='1' height='1'/></screensize></screensizes>"
        "</resource></tab></structure>"
        "</mashup>"
    )
    parser_custom_screensizes._component_description = etree.Element("details")
    parser_custom_screensizes._parse_basic_info()
    parser_custom_screensizes._parse_workspace_info()
    custom_layouts = parser_custom_screensizes._info.tabs[0].resources[0].layouts
    assert set(custom_layouts) == {"8"}
    assert parser_custom_screensizes._info.tabs[0].preferences["screenSizes"] == (
        '[{"id": 4, "moreOrEqual": 0, "lessOrEqual": 767}, {"id": 8, "moreOrEqual": 768, "lessOrEqual": -1}]'
    )

    # New <layouts> format takes precedence and needs no 'layout' attribute either
    parser_new_layouts = ApplicationMashupTemplateParser(
        f'<mashup xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="m" version="1.0.0">'
        "<details/>"
        "<structure><tab name='t'><resource id='r' vendor='acme' name='w' version='1.0.0' title='t'>"
        "<layouts><layout screensize='0' x='1' y='2' w='3' h='4' visible='false'/></layouts>"
        "</resource></tab></structure>"
        "</mashup>"
    )
    parser_new_layouts._component_description = etree.Element("details")
    parser_new_layouts._parse_basic_info()
    parser_new_layouts._parse_workspace_info()
    new_layout = parser_new_layouts._info.tabs[0].resources[0].layouts["0"]
    assert new_layout.x == 1 and new_layout.y == 2 and new_layout.w == 3 and new_layout.h == 4
    assert new_layout.visible is False

    parser_err = ApplicationMashupTemplateParser(f'<widget xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="w" version="1.0.0"><details/></widget>')
    parser_err._parsed = False
    parser_err._info = _mk_widget_info()
    monkeypatch.setattr(
        parser_err,
        "_parse_extra_info",
        lambda: (_ for _ in ()).throw(ValidationError.from_exception_data("X", [])),
    )
    with pytest.raises(TemplateParseException, match="Invalid template"):
        parser_err.get_resource_info()

    parser_err._parsed = True
    assert parser_err.get_resource_info() == parser_err._info


def test_xml_parser_init_dispatch_and_cached_info(monkeypatch):
    xml_parser._ = lambda text: text

    parser_widget = ApplicationMashupTemplateParser(f'<widget xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="w" version="1.0.0"><details/><wiring/><contents src="i.html"/><rendering width="1" height="1"/></widget>')
    called = {"widget": 0, "operator": 0, "mashup": 0, "translations": 0}
    monkeypatch.setattr(parser_widget, "_parse_widget_info", lambda: called.__setitem__("widget", called["widget"] + 1))
    monkeypatch.setattr(parser_widget, "_parse_operator_info", lambda: called.__setitem__("operator", called["operator"] + 1))
    monkeypatch.setattr(parser_widget, "_parse_workspace_info", lambda: called.__setitem__("mashup", called["mashup"] + 1))
    monkeypatch.setattr(parser_widget, "_parse_translation_catalogue", lambda: called.__setitem__("translations", called["translations"] + 1))
    parser_widget._component_description = etree.Element("details")
    parser_widget._parse_basic_info()
    parser_widget._parse_extra_info()
    assert called["widget"] == 1
    assert called["operator"] == 0
    assert called["mashup"] == 0
    assert called["translations"] == 1
    assert parser_widget.get_resource_info() == parser_widget._info

    parser_op = ApplicationMashupTemplateParser(
        f'<operator xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="o" version="1.0.0"><details/><wiring/></operator>'
    )
    flags = {"w": 0, "o": 0, "m": 0, "t": 0}
    monkeypatch.setattr(parser_op, "_parse_widget_info", lambda: flags.__setitem__("w", flags["w"] + 1))
    monkeypatch.setattr(parser_op, "_parse_operator_info", lambda: flags.__setitem__("o", flags["o"] + 1))
    monkeypatch.setattr(parser_op, "_parse_workspace_info", lambda: flags.__setitem__("m", flags["m"] + 1))
    monkeypatch.setattr(parser_op, "_parse_translation_catalogue", lambda: flags.__setitem__("t", flags["t"] + 1))
    parser_op._component_description = etree.Element("details")
    parser_op._parse_basic_info()
    parser_op._parse_extra_info()
    assert flags == {"w": 0, "o": 1, "m": 0, "t": 1}

    parser_m = ApplicationMashupTemplateParser(
        f'<mashup xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="m" version="1.0.0"><details/><structure/></mashup>'
    )
    monkeypatch.setattr(parser_m, "_parse_widget_info", lambda: flags.__setitem__("w", flags["w"] + 1))
    monkeypatch.setattr(parser_m, "_parse_operator_info", lambda: flags.__setitem__("o", flags["o"] + 1))
    monkeypatch.setattr(parser_m, "_parse_workspace_info", lambda: flags.__setitem__("m", flags["m"] + 1))
    monkeypatch.setattr(parser_m, "_parse_translation_catalogue", lambda: flags.__setitem__("t", flags["t"] + 1))
    parser_m._component_description = etree.Element("details")
    parser_m._parse_basic_info()
    parser_m._parse_extra_info()
    assert flags["m"] >= 1


def test_rdf_and_xml_unknown_type_branches(monkeypatch):
    rdf_parser._ = lambda text: text
    p = RDFTemplateParser(rdflib.Graph())
    p._type = "other"
    p._info = _mk_widget_info()
    monkeypatch.setattr(p, "_parse_component_info", lambda: None)
    monkeypatch.setattr(p, "_parse_workspace_info", lambda: None)
    monkeypatch.setattr(p, "_parse_translation_catalogue", lambda: None)
    p._parse_extra_info()

    g, root = _base_rdf_graph(rdf_parser.WIRE["Widget"])
    p2 = RDFTemplateParser(g)
    p2._type = "other"
    with pytest.raises(AttributeError):
        p2._parse_basic_info()
    p2._parsed = True
    p2._info = _mk_widget_info()
    assert p2.get_resource_info() == p2._info

    xml_parser._ = lambda text: text
    xp = ApplicationMashupTemplateParser(f'<widget xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="w" version="1.0.0"><details/></widget>')
    xp._type = "other"
    xp._component_description = etree.Element("details")
    with pytest.raises(Exception):
        xp._parse_basic_info()
    xp._info = _mk_widget_info()
    monkeypatch.setattr(xp, "_parse_translation_catalogue", lambda: None)
    xp._parse_extra_info()


def test_xml_parser_remaining_branch_paths(monkeypatch):
    xml_parser._ = lambda text: text

    parser_view = ApplicationMashupTemplateParser(f'<mashup xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="m" version="1.0.0"><details/><structure/></mashup>')
    target = WiringVisualDescription()
    visual = etree.fromstring(
        f'<visualdescription xmlns="{WIRECLOUD_TEMPLATE_NS}">'
        '<component id="w1" type="widget"><sources/><targets/></component>'
        '<component id="o1" type="operator"><position x="1" y="2"/><sources/><targets/></component>'
        '<component id="x1" type="other"><sources/><targets/></component>'
        '</visualdescription>'
    )
    parser_view._parse_wiring_component_view_info(target, visual)
    assert "w1" in target.components.widget
    assert "o1" in target.components.operator

    parser_wiring = ApplicationMashupTemplateParser(
        f'<mashup xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="m" version="1.0.0">'
        "<details/><structure><wiring version='2.0'/></structure></mashup>"
    )
    parser_wiring._component_description = etree.Element("details")
    parser_wiring._parse_basic_info()
    parser_wiring._parse_wiring_info()
    assert parser_wiring._info.wiring.version == "2.0"

    parser_widget_v2 = ApplicationMashupTemplateParser(
        f'<widget xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="w" version="1.0.0">'
        "<macversion>2</macversion><details/><wiring/><contents src='index.html'/>"
        "<rendering width='1' height='1'/><scripts><script src='a.js'/></scripts>"
        "</widget>"
    )
    parser_widget_v2._component_description = etree.Element("details")
    parser_widget_v2._parse_basic_info()
    parser_widget_v2._parse_widget_info()
    assert parser_widget_v2._info.js_files == ["a.js"]

    parser_widget_v1 = ApplicationMashupTemplateParser(
        f'<widget xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="w" version="1.0.0">'
        "<macversion>1</macversion><details/><wiring/><contents src='index.html'/>"
        "<rendering width='1' height='1'/>"
        "</widget>"
    )
    parser_widget_v1._component_description = etree.Element("details")
    parser_widget_v1._parse_basic_info()
    parser_widget_v1._parse_widget_info()
    assert parser_widget_v1._info.js_files == []

    parser_op_v1 = ApplicationMashupTemplateParser(
        f'<operator xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="o" version="1.0.0">'
        "<macversion>1</macversion><details/><wiring/><scripts><script src='o.js'/></scripts>"
        "</operator>"
    )
    parser_op_v1._component_description = etree.Element("details")
    parser_op_v1._parse_basic_info()
    parser_op_v1._parse_operator_info()
    assert parser_op_v1._info.entrypoint is None

    parser_op_v2_no_entry = ApplicationMashupTemplateParser(
        f'<operator xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="o" version="1.0.0">'
        "<macversion>2</macversion><details/><wiring/><scripts><script src='o.js'/></scripts>"
        "</operator>"
    )
    parser_op_v2_no_entry._component_description = etree.Element("details")
    parser_op_v2_no_entry._parse_basic_info()
    parser_op_v2_no_entry._parse_operator_info()
    assert parser_op_v2_no_entry._info.entrypoint is None
