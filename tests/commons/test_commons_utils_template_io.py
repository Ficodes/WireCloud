# -*- coding: utf-8 -*-

from lxml import etree
import pytest
import rdflib
from types import SimpleNamespace

from wirecloud.commons.utils.template.base import ObsoleteFormatError, TemplateParseException
from wirecloud.commons.utils.template.parsers.xml import ApplicationMashupTemplateParser, WIRECLOUD_TEMPLATE_NS
from wirecloud.commons.utils.template.parsers import rdf as rdf_parser
from wirecloud.commons.utils.template.parsers import xml as xml_parser
from wirecloud.commons.utils.template.writers import xml as xml_writer
from wirecloud.commons.utils.template.schemas.macdschemas import MACDMashup, MACDWidget
from wirecloud.platform.wiring.schemas import WiringOperatorPreference


def _widget_info_dict():
    return {
        "type": "widget",
        "macversion": 2,
        "name": "widget",
        "vendor": "acme",
        "version": "1.0.0",
        "title": "Widget",
        "description": "Desc",
        "contents": {"src": "index.html", "charset": "utf-8"},
        "widget_width": "4",
        "widget_height": "3",
        "preferences": [],
        "properties": [],
        "wiring": {"inputs": [], "outputs": []},
        "js_files": ["js/app.js"],
    }


def _mashup_info_dict():
    return {
        "type": "mashup",
        "macversion": 1,
        "name": "mashup",
        "vendor": "acme",
        "version": "1.0.0",
        "tabs": [
            {
                "name": "main",
                "resources": [
                    {
                        "id": "r1",
                        "name": "widget",
                        "vendor": "acme",
                        "version": "1.0.0",
                        "layouts": {"0": {"x": 0, "y": 0, "w": 1, "h": 1}},
                    }
                ],
            }
        ],
    }


def test_xml_writer_helpers():
    xml_writer._ = lambda text: text
    opts = type("O", (), {"name": "x", "enabled": True, "people": [], "missing": None})()

    assert xml_writer.process_option(opts, "name") == "x"
    assert xml_writer.process_option(opts, "enabled", type="boolean") == "true"
    assert xml_writer.process_option(opts, "people", type="people") == ""
    assert xml_writer.process_option(opts, "missing") is None
    with pytest.raises(Exception):
        xml_writer.process_option(opts, "missing", required=True)

    root = etree.Element("root")
    xml_writer.add_attribute(opts, root, "name")
    xml_writer.add_attribute(opts, root, "enabled", type="boolean")
    xml_writer.add_attribute(opts, root, "name", default="x", ignore_default=True)
    xml_writer.add_attributes(opts, root, ("name",))
    assert root.get("name") == "x"
    assert root.get("enabled") == "true"

    xml_writer.add_element(opts, root, "name", attr_name="label")
    xml_writer.add_elements(opts, root, ("name",))
    assert root.find("label") is not None
    assert root.find("name") is not None

    resource = etree.Element("resource")
    xml_writer.add_preference_values(
        resource,
        {
            "a": WiringOperatorPreference(readonly=True, hidden=True, value="x"),
        },
    )
    pref_node = resource.find("preferencevalue")
    assert pref_node is not None
    assert pref_node.get("readonly") == "true"


def test_xml_writer_document_generation():
    widget = MACDWidget.model_validate(_widget_info_dict())
    widget_doc = xml_writer.build_xml_document(widget)
    assert widget_doc.tag.endswith("widget")
    assert widget_doc.find("details") is not None
    widget_xml = xml_writer.write_xml_description(widget)
    assert widget_xml.startswith("<?xml")

    mashup = MACDMashup.model_validate(_mashup_info_dict())
    mashup_doc = xml_writer.build_xml_document(mashup)
    assert mashup_doc.tag.endswith("mashup")
    assert mashup_doc.find("structure") is not None
    raw = xml_writer.write_xml_description(mashup, raw=True)
    assert isinstance(raw, etree._Element)


def test_xml_parser_init_branches(monkeypatch):
    xml_parser._ = lambda text: text
    with pytest.raises(ValueError, match="Missing document namespace"):
        ApplicationMashupTemplateParser("<widget></widget>")

    with pytest.raises(ObsoleteFormatError):
        ApplicationMashupTemplateParser('<widget xmlns="http://wirecloud.conwet.fi.upm.es/ns/template#"></widget>')

    with pytest.raises(ValueError, match="Invalid namespace"):
        ApplicationMashupTemplateParser('<widget xmlns="http://invalid/ns"></widget>')

    with pytest.raises(TemplateParseException, match="Invalid root element"):
        ApplicationMashupTemplateParser(f'<invalid xmlns="{WIRECLOUD_TEMPLATE_NS}"></invalid>')

    parser = ApplicationMashupTemplateParser(f'<widget xmlns="{WIRECLOUD_TEMPLATE_NS}"></widget>')
    monkeypatch.setattr(xml_parser, "XMLSCHEMA", SimpleNamespace(assertValid=lambda _doc: None))
    monkeypatch.setattr(parser, "_xpath", lambda *_a, **_k: [etree.Element("details")])
    monkeypatch.setattr(parser, "_parse_basic_info", lambda: None)
    parser._init()

    parser_bytes = ApplicationMashupTemplateParser(f'<widget xmlns="{WIRECLOUD_TEMPLATE_NS}"></widget>'.encode("utf-8"))
    assert parser_bytes is not None

    parser_element = ApplicationMashupTemplateParser(etree.fromstring(f'<widget xmlns="{WIRECLOUD_TEMPLATE_NS}"></widget>'))
    assert parser_element is not None

    parser_schema_error = ApplicationMashupTemplateParser(f'<widget xmlns="{WIRECLOUD_TEMPLATE_NS}"></widget>')
    monkeypatch.setattr(xml_parser, "XMLSCHEMA", SimpleNamespace(assertValid=lambda _doc: (_ for _ in ()).throw(ValueError("bad schema"))))
    with pytest.raises(TemplateParseException, match="bad schema"):
        parser_schema_error._init()


def test_xml_parser_widget_macversion_1_rejects_scripts(monkeypatch):
    xml_parser._ = lambda text: text
    parser = ApplicationMashupTemplateParser(
        f'''<widget xmlns="{WIRECLOUD_TEMPLATE_NS}" vendor="acme" name="w" version="1.0.0">\n'''
        "<macversion>1</macversion>"
        "<details/>"
        "<wiring/>"
        '<contents src="index.html"/>'
        '<rendering width="1" height="1"/>'
        '<scripts><script src=\"app.js\"/></scripts>'
        "</widget>"
    )
    monkeypatch.setattr(xml_parser, "XMLSCHEMA", SimpleNamespace(assertValid=lambda _doc: None))
    parser._init()
    with pytest.raises(TemplateParseException, match="script element"):
        parser.get_resource_info()


def test_rdf_parser_init_branches(monkeypatch):
    rdf_parser._ = lambda text: text

    with pytest.raises(ValueError, match="Invalid template type"):
        rdf_parser.RDFTemplateParser(123)

    with pytest.raises(ValueError, match="XML document does not contain"):
        rdf_parser.RDFTemplateParser(b"<widget/>")

    with pytest.raises(ValueError, match="Invalid namespace"):
        rdf_parser.RDFTemplateParser(b'<RDF xmlns="http://invalid/ns"></RDF>')

    with pytest.raises(ValueError, match="Invalid root element"):
        rdf_parser.RDFTemplateParser(b'<widget xmlns="http://www.w3.org/1999/02/22-rdf-syntax-ns#"></widget>')

    g = rdflib.Graph()
    parser = rdf_parser.RDFTemplateParser(g)
    with pytest.raises(UnboundLocalError):
        parser._init()
