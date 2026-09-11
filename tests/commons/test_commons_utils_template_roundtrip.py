# -*- coding: utf-8 -*-

from types import SimpleNamespace

import pytest

from wirecloud.commons.utils.template.parsers.json import JSONTemplateParser
from wirecloud.commons.utils.template.parsers.xml import ApplicationMashupTemplateParser
from wirecloud.commons.utils.template.parsers.rdf import RDFTemplateParser
from wirecloud.commons.utils.template.parsers import TemplateParser
from wirecloud.commons.utils.template.writers import xml as xml_writer
from wirecloud.commons.utils.template.writers import rdf as rdf_writer
from wirecloud.commons.utils.template.schemas.macdschemas import MACType


def _widget_payload():
    return {
        "type": "widget",
        "macversion": 2,
        "name": "widget",
        "vendor": "acme",
        "version": "1.0.0",
        "title": "__MSG_TITLE__",
        "description": "__MSG_DESC__",
        "longdescription": "https://example.com/long",
        "authors": [{"name": "Alice", "email": "alice@example.com", "url": "https://alice"}],
        "contributors": [{"name": "Bob", "email": "bob@example.com", "url": "https://bob"}],
        "email": "support@example.com",
        "image": "https://example.com/image.png",
        "smartphoneimage": "https://example.com/smartphone.png",
        "homepage": "https://example.com",
        "doc": "https://example.com/docs",
        "license": "MIT",
        "licenseurl": "https://example.com/license",
        "changelog": "https://example.com/changelog",
        "issuetracker": "https://example.com/issues",
        "requirements": [{"type": "feature", "name": "wc/feature"}],
        "contents": {
            "src": "index.html",
            "contenttype": "text/html",
            "charset": "utf-8",
            "cacheable": False,
            "useplatformstyle": True,
        },
        "altcontents": [
            {
                "scope": "mobile",
                "src": "mobile.html",
                "contenttype": "text/html",
                "charset": "utf-8",
            }
        ],
        "widget_width": "4",
        "widget_height": "3",
        "preferences": [
            {
                "name": "pref",
                "type": "text",
                "label": "__MSG_PREF_LABEL__",
                "description": "__MSG_PREF_DESC__",
                "readonly": True,
                "secure": True,
                "required": True,
                "language": "en",
                "default": "a",
                "value": "a",
            }
        ],
        "properties": [
            {
                "name": "prop",
                "type": "text",
                "label": "__MSG_PROP_LABEL__",
                "description": "__MSG_PROP_DESC__",
                "default": "x",
                "secure": True,
                "multiuser": True,
            }
        ],
        "wiring": {
            "inputs": [
                {
                    "name": "in",
                    "type": "text",
                    "label": "__MSG_IN_LABEL__",
                    "description": "__MSG_IN_DESC__",
                    "actionlabel": "__MSG_IN_ACTION__",
                    "friendcode": "",
                }
            ],
            "outputs": [
                {
                    "name": "out",
                    "type": "text",
                    "label": "__MSG_OUT_LABEL__",
                    "description": "__MSG_OUT_DESC__",
                    "friendcode": "",
                }
            ],
        },
        "translations": {
            "en": {
                "TITLE": "Widget",
                "DESC": "Description",
                "PREF_LABEL": "Preference",
                "PREF_DESC": "Preference description",
                "PROP_LABEL": "Property",
                "PROP_DESC": "Property description",
                "IN_LABEL": "Input",
                "IN_DESC": "Input description",
                "IN_ACTION": "Send",
                "OUT_LABEL": "Output",
                "OUT_DESC": "Output description",
            }
        },
        "default_lang": "en",
        "js_files": ["js/app.js", "js/extra.js"],
        "entrypoint": "Wirecloud",
    }


def _operator_payload():
    payload = _widget_payload()
    payload["type"] = "operator"
    payload.pop("contents")
    payload.pop("altcontents")
    payload.pop("widget_width")
    payload.pop("widget_height")
    return payload


def _mashup_payload():
    return {
        "type": "mashup",
        "macversion": 2,
        "name": "mashup",
        "vendor": "acme",
        "version": "1.0.0",
        "title": "Mashup",
        "description": "Mashup description",
        "preferences": {"theme": "light"},
        "params": [
            {
                "name": "param1",
                "type": "text",
                "label": "Param 1",
                "description": "Param 1 description",
                "readonly": True,
                "required": False,
                "default": "d",
                "value": "v",
            }
        ],
        "embedded": [
            {
                "vendor": "acme",
                "name": "embedded",
                "version": "1.0.0",
                "src": "https://example.com/embedded.wgt",
            }
        ],
        "tabs": [
            {
                "name": "main",
                "title": "Main",
                "preferences": {"tabpref": "x"},
                "resources": [
                    {
                        "id": "r1",
                        "name": "widget",
                        "vendor": "acme",
                        "version": "1.0.0",
                        "title": "Widget instance",
                        "readonly": True,
                        "layouts": {
                            "0": {
                                "x": 10,
                                "y": 20,
                                "w": 2,
                                "h": 3,
                                "minimized": True,
                                "fulldragboard": True,
                                "titlevisible": False,
                                "visible": True,
                            },
                            "2": {
                                "w": 12,
                                "h": 8,
                                "visible": False,
                            },
                        },
                        "properties": {"p1": {"readonly": True, "value": "pv"}},
                        "preferences": {"k1": {"readonly": True, "hidden": True, "value": "vv"}},
                    }
                ],
            }
        ],
        "wiring": {
            "version": "2.0",
            "connections": [
                {
                    "readonly": True,
                    "source": {"type": "widget", "id": "r1", "endpoint": "out"},
                    "target": {"type": "operator", "id": "1", "endpoint": "in"},
                }
            ],
            "operators": {
                "1": {
                    "id": "1",
                    "name": "acme/op/1.0.0",
                    "preferences": {"mode": {"readonly": True, "hidden": True, "value": "safe"}},
                }
            },
            "visualdescription": {
                "components": {
                    "widget": {
                        "r1": {
                            "collapsed": True,
                            "position": {"x": 1, "y": 2},
                            "endpoints": {"source": ["out"], "target": ["in"]},
                        }
                    },
                    "operator": {
                        "1": {
                            "collapsed": False,
                            "position": {"x": 3, "y": 4},
                            "endpoints": {"source": ["s"], "target": ["t"]},
                        }
                    },
                },
                "connections": [
                    {
                        "sourcename": "widget/r1/out",
                        "targetname": "operator/1/in",
                        "sourcehandle": {"x": 9, "y": 8},
                        "targethandle": {"x": 7, "y": 6},
                    }
                ],
                "behaviours": [
                    {
                        "title": "Behaviour",
                        "description": "Behaviour description",
                        "components": {
                            "widget": {},
                            "operator": {
                                "1": {
                                    "collapsed": True,
                                    "position": {"x": 5, "y": 6},
                                    "endpoints": {"source": ["bs"], "target": ["bt"]},
                                }
                            },
                        },
                        "connections": [
                            {
                                "sourcename": "operator/1/bs",
                                "targetname": "operator/1/bt",
                                "sourcehandle": "auto",
                                "targethandle": "auto",
                            }
                        ],
                    }
                ],
            },
            "inputs": [
                {"name": "in", "type": "text", "label": "Input", "description": "", "actionlabel": "", "friendcode": ""}
            ],
            "outputs": [
                {"name": "out", "type": "text", "label": "Output", "description": "", "friendcode": ""}
            ],
        },
        "translations": {},
        "default_lang": "en",
    }


def _json_info(payload):
    parser = JSONTemplateParser(payload)
    parser._init()
    return parser.get_resource_info()


def test_xml_roundtrip_widget_operator_mashup(monkeypatch):
    from wirecloud.commons.utils.template.parsers import xml as xml_parser

    xml_parser._ = lambda text: text

    widget_info = _json_info(_widget_payload())
    operator_info = _json_info(_operator_payload())
    mashup_info = _json_info(_mashup_payload())

    mashup_parsed = None
    for info in (widget_info, operator_info, mashup_info):
        xml_text = xml_writer.write_xml_description(info)
        parser = ApplicationMashupTemplateParser(xml_text)
        parser._init()
        parsed = parser.get_resource_info()

        assert parsed.type == info.type
        assert parsed.vendor == info.vendor
        assert parsed.name == info.name
        assert parsed.version == info.version

        if info is mashup_info:
            mashup_parsed = parsed

    assert mashup_info.wiring.operators["1"].preferences["mode"].hidden is True

    # 'layouts' round-trip through XML: omitted x/y stay None, non-default booleans survive
    layouts = mashup_parsed.tabs[0].resources[0].layouts
    assert layouts["0"].model_dump() == {
        "x": 10, "y": 20, "w": 2, "h": 3,
        "minimized": True, "titlevisible": False, "fulldragboard": True, "visible": True,
    }
    assert layouts["2"].model_dump() == {
        "x": None, "y": None, "w": 12, "h": 8,
        "minimized": False, "titlevisible": True, "fulldragboard": False, "visible": False,
    }


def test_rdf_roundtrip_widget_operator_mashup(monkeypatch):
    from wirecloud.commons.utils.template.parsers import rdf as rdf_parser

    rdf_parser._ = lambda text: text
    RDFTemplateParser._translations = {}
    RDFTemplateParser._translation_indexes = {}

    widget_info = _json_info(_widget_payload())
    operator_info = _json_info(_operator_payload())
    mashup_info = _json_info(_mashup_payload())

    mashup_parsed = None
    for info in (widget_info, operator_info, mashup_info):
        rdf_text = rdf_writer.write_rdf_description(info)
        parser = RDFTemplateParser(rdf_text)
        parser._init()
        parsed = parser.get_resource_info()

        assert parsed.type == info.type
        assert parsed.vendor == info.vendor
        assert parsed.name == info.name
        assert parsed.version == info.version

        if info is mashup_info:
            mashup_parsed = parsed

    assert len(mashup_info.wiring.visualdescription.behaviours) == 1

    # 'layouts' round-trip through RDF: omitted x/y stay None, non-default booleans survive
    layouts = mashup_parsed.tabs[0].resources[0].layouts
    assert layouts["0"].model_dump() == {
        "x": 10, "y": 20, "w": 2, "h": 3,
        "minimized": True, "titlevisible": False, "fulldragboard": True, "visible": True,
    }
    assert layouts["2"].model_dump() == {
        "x": None, "y": None, "w": 12, "h": 8,
        "minimized": False, "titlevisible": True, "fulldragboard": False, "visible": False,
    }


def test_rdf_writer_unsupported_resource_type():
    dummy = SimpleNamespace(type=SimpleNamespace(value="unknown"), vendor="acme", name="x", version="1.0.0")
    with pytest.raises(Exception, match="Unsupported resource type"):
        rdf_writer.build_rdf_graph(dummy)


def test_template_value_processor_even_percent_escape():
    from wirecloud.commons.utils.template.parsers import TemplateValueProcessor

    processor = TemplateValueProcessor(context={"user": {"name": "Alice"}})
    assert processor.process("%%(user.name)") == "%(user.name)"


def test_template_parser_get_resource_type_and_xml_list_options():
    parser = TemplateParser(_widget_payload())
    assert parser.get_resource_type() == MACType.widget

    info = _json_info(_widget_payload())
    info.preferences[0].type = "list"
    info.preferences[0].options = [SimpleNamespace(label="Option A", value="a")]
    xml_text = xml_writer.write_xml_description(info)
    assert "<option" in xml_text


def test_rdf_writer_options_and_nondefault_contenttype():
    info = _json_info(_widget_payload())
    info.contents.contenttype = "text/plain"
    info.contents.charset = "iso-8859-1"
    info.preferences[0].type = "list"
    info.preferences[0].options = [SimpleNamespace(label="Option A", value="a")]

    rdf_text = rdf_writer.write_rdf_description(info)
    assert "hasOption" in rdf_text
    assert "charset=ISO-8859-1" in rdf_text
