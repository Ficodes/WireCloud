# -*- coding: utf-8 -*-

import rdflib

from wirecloud.commons.utils.template.writers import rdf as rdf_writer
from wirecloud.commons.utils.template.writers import xml as xml_writer
from wirecloud.commons.utils.template.schemas.macdschemas import (
    MACDMashup,
    MACDMashupResource,
    MACDMashupResourceLayout,
    MACDMashupResourceProperty,
    MACDPreference,
    MACDProperty,
    MACDWidget,
    MACDWidgetContents,
    MACType,
)
from wirecloud.platform.wiring.schemas import WiringComponent, WiringComponents, WiringVisualDescriptionConnection


def _simple_widget():
    w = MACDWidget(
        type=MACType.widget,
        vendor="acme",
        name="w",
        version="1.0.0",
        macversion=2,
        contents=MACDWidgetContents(src="index.html"),
        widget_width="1",
        widget_height="1",
    )
    w.preferences = [
        MACDPreference(
            name="p",
            type="text",
            label="",
            description="",
            readonly=False,
            default="",
            value=None,
            secure=False,
            required=False,
            language=None,
            options=None,
        )
    ]
    w.properties = [
        MACDProperty(
            name="prop",
            type="text",
            label="",
            description="",
            default="",
            secure=False,
            multiuser=False,
        )
    ]
    w.js_files = ["app.js"]
    return w


def _simple_mashup():
    m = MACDMashup(type=MACType.mashup, vendor="acme", name="m", version="1.0.0")
    m.params = []
    m.embedded = []
    m.tabs = []
    return m


def test_rdf_writer_helper_false_branches():
    graph = rdflib.Graph()
    node = rdflib.BNode()

    rdf_writer.add_translated_nodes(
        graph,
        node,
        rdf_writer.DCTERMS,
        "title",
        "plain",
        rdf_writer.MACDTranslationIndexUsage(type="resource", field="title"),
        _simple_widget(),
    )

    components = WiringComponents(widget={"w1": {}}, operator={})
    # replace dict item with simple object shape used by writer
    components.widget["w1"] = type("C", (), {"collapsed": False, "position": None, "endpoints": None})()
    rdf_writer.write_wiring_components_graph(graph, rdflib.BNode(), components, "widget")

    connection = WiringVisualDescriptionConnection.model_validate(
        {
            "sourcename": "widget/w1/out",
            "targetname": "operator/1/in",
            "sourcehandle": "auto",
            "targethandle": "auto",
        }
    )
    rdf_writer.write_wiring_connections_graph(graph, rdflib.BNode(), [connection])

    mashup = _simple_mashup()
    rdf_writer.write_mashup_params(graph, rdflib.BNode(), mashup)
    rdf_writer.write_mashup_embedded_resources(graph, rdflib.BNode(), mashup)


def test_rdf_writer_platform_preference_property_false_paths():
    widget = _simple_widget()
    # ensure optional branches are skipped
    widget.entrypoint = None
    widget.title = ""
    widget.description = ""
    widget.issuetracker = ""
    widget.license = ""
    widget.licenseurl = ""
    widget.doc = ""
    widget.homepage = ""
    widget.email = ""
    widget.changelog = ""
    widget.image = ""
    widget.smartphoneimage = ""

    rdf_text = rdf_writer.write_rdf_description(widget)
    assert "PlatformPreference" in rdf_text
    assert "PlatformStateProperty" in rdf_text


def test_xml_writer_false_paths_for_prefs_and_props():
    widget = _simple_widget()
    xml_text = xml_writer.write_xml_description(widget)
    assert "<preference" in xml_text
    assert "<variable" in xml_text

    mashup = _simple_mashup()
    resource = MACDMashupResource(
        id="r1",
        vendor="acme",
        name="w",
        version="1.0.0",
        title="t",
        readonly=False,
        layouts={
            "0": MACDMashupResourceLayout(
                x=0, y=0, w=1, h=1, dock="left", dock_mode="push", dock_open=True
            ),
            "2": MACDMashupResourceLayout(w=12, h=8, visible=False),
        },
        properties={"p": MACDMashupResourceProperty(value=None, readonly=False)},
        preferences={},
    )
    mashup.tabs = [type("T", (), {"name": "main", "title": "", "preferences": {}, "resources": [resource]})()]
    mashup.wiring.version = "2.0"

    xml_text2 = xml_writer.write_xml_description(mashup)
    assert "<resource" in xml_text2
    assert 'dock="left"' in xml_text2
    assert 'dockmode="push"' in xml_text2
    assert 'dockopen="true"' in xml_text2


def test_xml_writer_remaining_helper_branches():
    opts = type("O", (), {"name": None, "enabled": False, "people": [], "value": None})()
    assert xml_writer.process_option(opts, "enabled", type="unknown") is None

    root = xml_writer.etree.Element("root")
    xml_writer.add_attribute(opts, root, "enabled", attr_name="flag", type="boolean")
    assert root.get("flag") == "false"
    xml_writer.add_element(opts, root, "value")
    assert root.find("value") is None


def test_xml_writer_mashup_false_condition_branches():
    mashup = _simple_mashup()
    mashup.params = [
        type(
            "P",
            (),
            {
                "name": "p",
                "type": "text",
                "label": "",
                "description": "",
                "default": "",
                "readonly": False,
                "required": True,
                "value": None,
            },
        )()
    ]
    mashup.tabs = []
    doc = xml_writer.etree.Element("mashup")
    res = xml_writer.etree.Element("structure")
    xml_writer.write_mashup_tree(doc, res, mashup)
    assert doc.find("preferences") is not None

    mashup2 = _simple_mashup()
    mashup2.wiring.connections = [
        type(
            "C",
            (),
            {
                "readonly": False,
                "source": type("E", (), {"type": type("T", (), {"value": "widget"})(), "id": "1", "endpoint": "out"})(),
                "target": type("E", (), {"type": type("T", (), {"value": "operator"})(), "id": "2", "endpoint": "in"})(),
            },
        )()
    ]
    mashup2.wiring.operators = {}
    mashup2.wiring.visualdescription.components = WiringComponents(widget={"w": WiringComponent(collapsed=False, position=None, endpoints=None)}, operator={})
    mashup2.wiring.visualdescription.connections = []
    target = xml_writer.etree.Element("structure")
    xml_writer.write_mashup_wiring_tree(target, mashup2)
    assert target.find("wiring") is not None

    # readonly=true branch and component position/endpoints branches
    mashup2.wiring.connections = [
        type(
            "C2",
            (),
            {
                "readonly": True,
                "source": type("E", (), {"type": type("T", (), {"value": "widget"})(), "id": "1", "endpoint": "out"})(),
                "target": type("E", (), {"type": type("T", (), {"value": "operator"})(), "id": "2", "endpoint": "in"})(),
            },
        )()
    ]
    cmp = WiringComponent.model_validate({"collapsed": False, "position": {"x": 1, "y": 2}, "endpoints": {"source": ["s"], "target": ["t"]}})
    mashup2.wiring.visualdescription.components = WiringComponents(widget={"w": cmp}, operator={})
    target2 = xml_writer.etree.Element("structure")
    xml_writer.write_mashup_wiring_tree(target2, mashup2)
    assert "readonly=\"true\"" in xml_writer.etree.tostring(target2).decode()


def test_rdf_writer_remaining_branch_conditions():
    graph = rdflib.Graph()
    resource_uri = rdflib.URIRef("http://example.com/m")
    mashup = _simple_mashup()
    mashup.params = [
        type("Param", (), {"name": "p1", "label": "", "type": "text", "description": "", "readonly": False, "default": "", "value": None, "required": True})()
    ]
    rdf_writer.write_mashup_params(graph, resource_uri, mashup)

    tab = type("Tab", (), {"name": "t", "title": "", "preferences": {}, "resources": []})()
    mashup.tabs = [tab]
    rdf_writer.write_mashup_resources_graph(graph, resource_uri, mashup)

    mashup.wiring.operators = {
        "1": type("Op", (), {"name": "acme/op/1.0.0", "preferences": {"x": type("Pr", (), {"value": None, "readonly": False, "hidden": False})()}})()
    }
    mashup.wiring.connections = [
        type(
            "Conn",
            (),
            {
                "readonly": False,
                "source": type("E", (), {"type": type("T", (), {"value": "widget"})(), "id": "1", "endpoint": "out"})(),
                "target": type("E", (), {"type": type("T", (), {"value": "operator"})(), "id": "2", "endpoint": "in"})(),
            },
        )()
    ]
    rdf_writer.write_mashup_wiring_graph(graph, rdflib.BNode(), mashup)

    # write_mashup_resources_graph branches
    resource = MACDMashupResource.model_validate(
        {
            "id": "r1",
            "vendor": "acme",
            "name": "w",
            "version": "1.0.0",
            "title": "Widget",
            "readonly": True,
            "layouts": {"0": {"x": 1, "y": 2, "w": 1, "h": 1}},
            "preferences": {"p": {"value": "v", "readonly": True, "hidden": True}},
            "properties": {"k": {"value": "x", "readonly": True}},
        }
    )
    resource2 = MACDMashupResource.model_validate(
        {
            "id": "r2",
            "vendor": "acme",
            "name": "w",
            "version": "1.0.0",
            "title": "Widget2",
            "readonly": False,
            "layouts": {"0": {"x": 1, "y": 2, "w": 1, "h": 1}},
            "preferences": {"p2": {"value": None, "readonly": False, "hidden": False}},
            "properties": {"k2": {"value": None, "readonly": False}},
        }
    )
    mashup.tabs = [type("Tab2", (), {"name": "t2", "title": "", "preferences": {}, "resources": [resource, resource2]})()]
    rdf_writer.write_mashup_resources_graph(graph, resource_uri, mashup)


def test_rdf_writer_author_contributor_and_license_branches():
    widget = _simple_widget()
    widget.authors = [type("C", (), {"name": "A", "email": None, "url": None})(), type("C", (), {"name": "B", "email": "b@example.com", "url": "https://b"})()]
    widget.contributors = [type("C", (), {"name": "C", "email": None, "url": None})(), type("C", (), {"name": "D", "email": "d@example.com", "url": "https://d"})()]
    widget.licenseurl = "https://license.example.com"
    widget.license = ""
    text = rdf_writer.write_rdf_description(widget)
    assert "license" in text
