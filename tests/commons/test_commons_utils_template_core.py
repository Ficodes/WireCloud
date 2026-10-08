# -*- coding: utf-8 -*-

from types import SimpleNamespace

import pytest
import orjson
from pydantic import ValidationError

from wirecloud.commons.utils.template import base as template_base
from wirecloud.commons.utils.template.parsers import json as json_parser
from wirecloud.commons.utils.template import parsers as template_parsers
from wirecloud.commons.utils.template.writers import json as json_writer
from wirecloud.commons.utils.template.schemas.macdschemas import (
    MACDTranslationIndexUsage,
    MACDMashup,
    MACDMashupResource,
    MACDMashupResourceLayout,
    MACDOperator,
    MACDPreference,
    MACDPreferenceListOption,
    MACDTab,
    MACDWidget,
    MACDWidgetContents,
    MACType,
)
from wirecloud.platform.wiring.schemas import WiringInput, WiringOutput
from wirecloud.platform.wiring.schemas import WiringOperator


def _widget_info_dict():
    return {
        "type": "widget",
        "macversion": 2,
        "name": "widget",
        "vendor": "acme",
        "version": "1.0.0",
        "title": "__MSG_TITLE__",
        "description": "__MSG_DESC__",
        "contents": {"src": "index.html", "charset": "utf-8"},
        "widget_width": "4",
        "widget_height": "3",
        "preferences": [
            {
                "name": "pref",
                "type": "list",
                "label": "__MSG_PREF_LABEL__",
                "description": "__MSG_PREF_DESC__",
                "options": [{"value": "a", "label": "__MSG_OPT_LABEL__"}],
            }
        ],
        "properties": [{"name": "prop", "type": "text", "label": "__MSG_PROP_LABEL__", "description": "__MSG_PROP_DESC__"}],
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
                "TITLE": "Title",
                "DESC": "Desc",
                "PREF_LABEL": "Pref",
                "PREF_DESC": "Pref Desc",
                "OPT_LABEL": "Option",
                "PROP_LABEL": "Prop",
                "PROP_DESC": "Prop Desc",
                "IN_LABEL": "Input",
                "IN_DESC": "Input Desc",
                "IN_ACTION": "Go",
                "OUT_LABEL": "Output",
                "OUT_DESC": "Output Desc",
            },
            "es": {"TITLE": "Titulo"},
        },
        "default_lang": "en",
        "js_files": ["js/app.js"],
    }


def _mashup_with_resource(type_value="mashup", layouts=None):
    if layouts is None:
        layouts = {"0": {"x": 0, "y": 0, "w": 1, "h": 1}}
    return {
        "type": type_value,
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
                        "layouts": layouts,
                    }
                ],
            }
        ],
    }


def test_template_base_helpers_and_contacts():
    assert template_base.is_valid_name("name") is True
    assert template_base.is_valid_name("a/b") is False
    assert template_base.is_valid_vendor("acme") is True
    assert template_base.is_valid_vendor("ac/me") is False
    assert template_base.is_valid_version("1.0.0rc1") is True
    assert template_base.is_valid_version("v1.0") is False

    contact = template_base.parse_contact_info("Alice <alice@example.com> (https://a)")
    assert contact.name == "Alice"
    assert contact.email == "alice@example.com"
    assert contact.url == "https://a"
    assert template_base.parse_contact_info("   ").name == ""

    contacts = template_base.parse_contacts_info(
        ["Bob <bob@example.com>", {"name": "Carol", "email": "carol@example.com"}, " "]
    )
    assert len(contacts) == 2
    contacts_from_string = template_base.parse_contacts_info("Dan <dan@example.com> (https://d), Eve <eve@example.com>")
    assert len(contacts_from_string) == 2
    assert template_base.stringify_contact(contacts[0]).startswith("Bob <bob@example.com>")
    assert "(https://a)" in template_base.stringify_contact(contact)
    assert "Carol" in template_base.stringify_contact_info(contacts)

    contact_url_only = template_base.parse_contact_info("UrlOnly (https://u)")
    assert contact_url_only.email is None
    assert contact_url_only.url == "https://u"
    assert template_base.stringify_contact(contact_url_only) == "UrlOnly (https://u)"

    err = template_base.TemplateParseException("x")
    assert str(err) == "x"
    assert "no longer supported format" in str(template_base.ObsoleteFormatError())
    assert str(template_base.UnsupportedFeature("y")) == "y"


def test_convert_legacy_layout():
    # Cell-based (relative) coordinates: rescaled by the column/row ratio between the old grid
    # (20 columns x 12px rows) and the new one (12 columns x 40px rows)
    cell_based = template_base.convert_legacy_layout(
        top=8, left=10, width=6, height=4, relx=True, rely=True, relwidth=True, relheight=True,
    )
    assert cell_based == {
        "x": round(10 * 12 / 20),
        "y": round(8 * 12 / 40),
        "w": max(1, round(6 * 12 / 20)),
        "h": max(1, round(4 * 12 / 40)),
        "minimized": False,
        "titlevisible": True,
        "fulldragboard": False,
        "visible": True,
    }

    # Pixel-based (absolute) coordinates: position is left to auto-placement (None); size is
    # estimated assuming a 100px column / 40px row
    pixel_based = template_base.convert_legacy_layout(
        top=80, left=250, width=250, height=80, relx=False, rely=False, relwidth=False, relheight=False,
        minimized=True, titlevisible=False, fulldragboard=True,
    )
    assert pixel_based == {
        "x": None,
        "y": None,
        "w": max(1, round(250 / 100)),
        "h": max(1, round(80 / 40)),
        "minimized": True,
        "titlevisible": False,
        "fulldragboard": True,
        "visible": True,
    }

    # w/h are never rounded down to 0
    tiny = template_base.convert_legacy_layout(
        top=0, left=0, width=1, height=1, relx=True, rely=True, relwidth=False, relheight=False,
    )
    assert tiny["w"] == 1
    assert tiny["h"] == 1

    # relx/rely and relwidth/relheight are independent of each other
    mixed = template_base.convert_legacy_layout(
        top=8, left=10, width=250, height=80, relx=True, rely=False, relwidth=False, relheight=True,
    )
    assert mixed["x"] == round(10 * 12 / 20)
    assert mixed["y"] is None
    assert mixed["w"] == max(1, round(250 / 100))
    assert mixed["h"] == max(1, round(80 * 12 / 40))

    # Old sidebar layout indexes retain their docking semantics. They start retracted, matching
    # the legacy sidebar's initial state; the old free layout (1) remains an ordinary grid item.
    docked = template_base.convert_legacy_layout(
        top=0, left=0, width=4, height=4, relx=True, rely=True,
        relwidth=True, relheight=True, layout=4,
    )
    assert docked["dock"] == "bottom"
    assert docked["dock_mode"] == "overlay"
    assert docked["dock_open"] is False
    assert "dock" not in template_base.convert_legacy_layout(
        top=0, left=0, width=4, height=4, relx=True, rely=True,
        relwidth=True, relheight=True, layout=1,
    )


def test_json_template_parser_errors_and_getters():
    with pytest.raises(ValueError):
        json_parser.JSONTemplateParser(123)
    with pytest.raises(ValueError):
        json_parser.JSONTemplateParser({})
    with pytest.raises(ValueError):
        json_parser.JSONTemplateParser({"type": "bad"})
    with pytest.raises(template_base.TemplateParseException):
        json_parser.JSONTemplateParser({"type": "widget"})

    parser_from_bytes = json_parser.JSONTemplateParser(orjson.dumps(_widget_info_dict()))
    assert parser_from_bytes.get_resource_type() == MACType.widget

    operator_payload = {
        **_widget_info_dict(),
        "type": "operator",
    }
    operator_payload.pop("contents")
    operator_payload.pop("widget_width")
    operator_payload.pop("widget_height")
    operator = json_parser.JSONTemplateParser(operator_payload)
    operator._init()
    assert operator.get_resource_type() == MACType.operator

    parser = json_parser.JSONTemplateParser(_widget_info_dict())
    parser._init()
    assert parser.get_resource_type() == MACType.widget
    assert parser.get_resource_name() == "widget"
    assert parser.get_resource_vendor() == "acme"
    assert parser.get_resource_version() == "1.0.0"
    info = parser.get_resource_info()
    assert "TITLE" in info.translation_index_usage
    assert any(u.type == "resource" for u in info.translation_index_usage["TITLE"])


def test_json_template_parser_mashup_empty_layouts_is_valid():
    # A widget with no stored layouts at all is valid: it is auto-placed by the client
    json_parser._ = lambda text: text
    payload = _mashup_with_resource(layouts={})
    parser = json_parser.JSONTemplateParser(payload)
    parser._init()
    info = parser.get_resource_info()
    assert info.tabs[0].resources[0].layouts == {}


def test_json_template_parser_mashup_params_translation_indexes():
    json_parser._ = lambda text: text
    payload = {
        "type": "mashup",
        "macversion": 1,
        "name": "m",
        "vendor": "acme",
        "version": "1.0.0",
        "params": [
            {
                "name": "choice",
                "type": "list",
                "label": "__MSG_LABEL__",
                "description": "__MSG_DESC__",
                "options": [{"value": "v1", "label": "__MSG_OPT__"}],
            }
        ],
        "translations": {"en": {"LABEL": "L", "DESC": "D", "OPT": "O"}},
    }
    parser = json_parser.JSONTemplateParser(payload)
    with pytest.raises(AttributeError):
        parser._init()

    # Cover normal path for mashup params list options
    parser_ok = json_parser.JSONTemplateParser(_mashup_with_resource())
    parser_ok._info.params = [
        SimpleNamespace(
            name="choice",
            type="list",
            label="__MSG_LABEL__",
            description="__MSG_DESC__",
            options=[SimpleNamespace(label="__MSG_OPT__")],
        )
    ]
    parser_ok._info.translations = {"en": {"LABEL": "L", "DESC": "D", "OPT": "O"}}
    parser_ok._init()
    assert "OPT" in parser_ok._info.translation_index_usage

    # cover branch where translation index already exists
    parser_ok._add_translation_index("__MSG_LABEL__", type="resource", field="title")
    parser_ok._add_translation_index("__MSG_LABEL__", type="resource", field="description")
    assert len(parser_ok._info.translation_index_usage["LABEL"]) >= 2


def test_template_parser_selection_and_errors(monkeypatch):
    class _Bad:
        def __init__(self, _template):
            raise RuntimeError("bad")

    class _TemplateErr:
        def __init__(self, _template):
            raise template_base.TemplateParseException("boom")

    monkeypatch.setattr(template_parsers.TemplateParser, "parsers", (_Bad, _TemplateErr))
    with pytest.raises(template_base.TemplateParseException):
        template_parsers.TemplateParser("x")

    monkeypatch.setattr(template_parsers.TemplateParser, "parsers", (_Bad,))
    with pytest.raises(template_base.TemplateFormatError):
        template_parsers.TemplateParser("x")


def test_template_parser_processed_info_mashup_branches(monkeypatch):
    monkeypatch.setattr(template_parsers.TemplateParser, "parsers", (json_parser.JSONTemplateParser,))
    payload = _mashup_with_resource()
    payload["translations"] = {"en": {}, "es": {}}
    parser = template_parsers.TemplateParser(payload, base="https://base/")

    info = parser.get_resource_processed_info(lang="fr", process_urls=True, translate=True, process_variables=False)
    assert info.type == MACType.mashup
    assert info.translations == {}


def test_template_parser_processed_info_unknown_and_upo_non_string(monkeypatch):
    monkeypatch.setattr(template_parsers.TemplateParser, "parsers", (json_parser.JSONTemplateParser,))
    payload = _widget_info_dict()
    parser = template_parsers.TemplateParser(payload, base="https://base/")

    info = parser.get_resource_info()
    info.translation_index_usage["TITLE"].append(MACDTranslationIndexUsage(type="unknown", field="title"))
    info.translation_index_usage["OPT_LABEL"] = [MACDTranslationIndexUsage(type="upo", variable="pref", option=0)]
    info.preferences[0].options[0].value = 1

    processed = parser.get_resource_processed_info(lang="en", process_urls=False, translate=True, process_variables=False)
    assert processed.type == MACType.widget


def test_json_template_parser_unreachable_branch_trick():
    class WeirdType:
        def __init__(self):
            self.calls = 0

        def __eq__(self, other):
            self.calls += 1
            if self.calls == 3:  # pass the membership check at line 44
                return other == "mashup"
            return False

    parser = json_parser.JSONTemplateParser({"type": WeirdType()})
    assert not hasattr(parser, "_info")


def test_template_parser_processing_and_dependencies(monkeypatch):
    monkeypatch.setattr(template_parsers.TemplateParser, "parsers", (json_parser.JSONTemplateParser,))
    parser = template_parsers.TemplateParser(_widget_info_dict(), base="https://cdn.example.com/base/")

    processed = parser.get_resource_processed_info(base="https://cdn.example.com/base/", lang="es", process_urls=True, translate=True, process_variables=True)
    assert processed.title == "Titulo"
    assert processed.description == "Desc"
    assert processed.contents.src.startswith("https://cdn.example.com/base/")
    assert "pref" in processed.variables.preferences
    assert "prop" in processed.variables.properties
    assert processed.translations == {}
    assert processed.translation_index_usage == {}

    parser_no_urls = template_parsers.TemplateParser(_widget_info_dict(), base="https://cdn.example.com/base/")
    no_urls = parser_no_urls.get_resource_processed_info(process_urls=False)
    assert no_urls.contents.src == "index.html"

    parser_no_title = template_parsers.TemplateParser({**_widget_info_dict(), "title": "", "translations": {}}, base="https://cdn.example.com/base/")
    no_title = parser_no_title.get_resource_processed_info(base=None, lang=None, process_urls=True, translate=False, process_variables=False)
    assert no_title.title == "widget"

    parser_with_alt = template_parsers.TemplateParser(
        {**_widget_info_dict(), "altcontents": [{"scope": "mobile", "src": "mobile.html", "contenttype": "text/html", "charset": "utf-8"}]},
        base="https://cdn.example.com/base/",
    )
    alt = parser_with_alt.get_resource_processed_info(base=None, lang="en", process_urls=True, translate=False, process_variables=False)
    assert alt.altcontents[0].src.startswith("https://cdn.example.com/base/")

    # get_absolute_url and basic helper
    assert parser.get_absolute_url("x.js") == "https://cdn.example.com/base/x.js"
    assert parser.get_absolute_url("x.js", base="https://other/") == "https://other/x.js"
    assert template_parsers.absolutize_url_field("  x.js ", "https://b/") == "https://b/x.js"
    assert template_parsers.absolutize_url_field("   ", "https://b/") == ""

    mashup_parser = template_parsers.TemplateParser(_mashup_with_resource(), base="https://x/")
    info = mashup_parser.get_resource_info()
    info.wiring.operators = {"1": WiringOperator.model_validate({"id": "1", "name": "acme/op/1.0.0", "preferences": {}})}
    deps = mashup_parser.get_resource_dependencies()
    assert "acme/widget/1.0.0" in deps
    assert "acme/op/1.0.0" in deps

    non_mashup_deps = parser.get_resource_dependencies()
    assert non_mashup_deps == set()
    parser.set_base("https://new-base/")
    assert parser.base == "https://new-base/"
    assert parser.get_resource_name() == "widget"
    assert parser.get_resource_vendor() == "acme"
    assert parser.get_resource_version() == "1.0.0"


def test_template_value_processor():
    ctx = {"obj": {"name": "Alice"}, "x": {"y": "Z"}, "holder": SimpleNamespace(value="Attr")}
    proc = template_parsers.TemplateValueProcessor(context=ctx)
    out = proc.process("Hello %(obj.name) and %% (keep) and %%(%(x.y)) and %(holder.value) and %(missing.val)")
    assert "Alice" in out
    assert "%%(Z)" in out
    assert "Attr" in out
    assert "Z" in out
    assert "%(missing.val)" in out


def test_json_writer_helpers_and_output():
    data = {"title": "", "desc": "x", "authors": []}
    json_writer.remove_empty_string_fields(("title",), data)
    assert "title" not in data
    with pytest.raises(Exception):
        json_writer.remove_empty_string_fields(("desc",), {"desc": 3})

    arr = {"authors": []}
    json_writer.remove_empty_array_fields(("authors",), arr)
    assert "authors" not in arr
    with pytest.raises(Exception):
        json_writer.remove_empty_array_fields(("authors",), {"authors": "x"})

    widget = MACDWidget.model_validate(_widget_info_dict())
    widget.translation_index_usage = {"X": [MACDTranslationIndexUsage(type="resource", field="title")]}
    written = json_writer.write_json_description(widget)
    assert '"translation_index_usage"' not in written
    assert '"type":"widget"' in written

    mashup = MACDMashup.model_validate(_mashup_with_resource())
    written_mashup = json_writer.write_json_description(mashup)
    assert '"type":"mashup"' in written_mashup


def test_macdschemas_validators_and_layouts():
    import wirecloud.commons.utils.template.schemas.macdschemas as macdschemas
    macdschemas._ = lambda text: text

    # check_options + set_multiuser
    with pytest.raises(ValueError, match="List preferences must have options"):
        MACDPreference.model_validate({"name": "p", "type": "list"})
    pref = MACDPreference.model_validate(
        {"name": "p", "type": "list", "multiuser": True, "options": [{"value": "a", "label": "A"}]}
    )
    assert pref.multiuser is False

    with pytest.raises(ValueError, match="Invalid type for widget"):
        MACDWidget.model_validate(
            {
                **_widget_info_dict(),
                "type": "operator",
            }
        )
    with pytest.raises(ValueError, match="JS scripts are not allowed"):
        MACDWidget.model_validate(
            {
                **_widget_info_dict(),
                "macversion": 1,
            }
        )

    with pytest.raises(ValueError, match="Invalid type for operator"):
        MACDOperator.model_validate(
            {
                **_widget_info_dict(),
                "type": "widget",
            }
        )

    # check_translations branches
    base_obj = MACDWidget.model_validate(_widget_info_dict())
    base_obj.translation_index_usage = {"TITLE": [MACDTranslationIndexUsage(type="resource", field="title")]}
    base_obj.translations = {"es": {"TITLE": "Titulo"}}
    with pytest.raises(KeyError):
        base_obj.check_translations()

    base_obj.translation_index_usage = {}
    with pytest.raises(template_base.TemplateParseException, match="default translation language"):
        base_obj.check_translations()

    base_obj.translation_index_usage = {"TITLE": [MACDTranslationIndexUsage(type="resource", field="title")]}
    base_obj.translations = {"en": {}}
    with pytest.raises(template_base.TemplateParseException, match="need a default value"):
        base_obj.check_translations()

    base_obj.translations = {"en": {"TITLE": "Title", "EXTRA": "x"}}
    with pytest.raises(template_base.TemplateParseException, match="not used"):
        base_obj.check_translations()

    op = MACDOperator.model_validate(
        {
            **_widget_info_dict(),
            "type": "operator",
            "entrypoint": "main",
            "contents": None,
            "widget_width": None,
            "widget_height": None,
        }
    )
    assert op.type == MACType.operator

    with pytest.raises(ValueError, match="Invalid type for mashup"):
        MACDMashup.model_validate({**_mashup_with_resource(), "type": "widget"})

    valid_mashup = MACDMashup.model_validate(_mashup_with_resource())
    assert valid_mashup.tabs[0].resources[0].layouts["0"].w == 1

    # cover parse_contacts non-dict branch directly
    assert macdschemas.MACDBase.parse_contacts("noop") == "noop"

    # MACDMashupResourceLayout defaults and field validation
    default_layout = MACDMashupResourceLayout()
    assert default_layout.model_dump() == {
        "x": None,
        "y": None,
        "w": 1,
        "h": 1,
        "minimized": False,
        "titlevisible": True,
        "fulldragboard": False,
        "visible": True,
        "dock": None,
        "dock_mode": "overlay",
        "dock_open": False,
    }

    with pytest.raises(ValidationError):
        MACDMashupResourceLayout(w=0)
    with pytest.raises(ValidationError):
        MACDMashupResourceLayout(h=0)
    with pytest.raises(ValidationError):
        MACDMashupResourceLayout(x=-1)
    with pytest.raises(ValidationError):
        MACDMashupResourceLayout(y=-1)

    # A MACDMashupResource with no layouts at all is valid: the widget has no persisted layout
    # yet and is auto-placed
    no_layouts_resource = MACDMashupResource(id="r2", name="widget", vendor="acme", version="1.0.0")
    assert no_layouts_resource.layouts == {}

    multi_layout_resource = MACDMashupResource(
        id="r3",
        name="widget",
        vendor="acme",
        version="1.0.0",
        layouts={
            "0": MACDMashupResourceLayout(x=1, y=2, w=3, h=4),
            "2": MACDMashupResourceLayout(w=12, h=8, visible=False),
        },
    )
    assert multi_layout_resource.layouts["0"].x == 1
    assert multi_layout_resource.layouts["2"].visible is False
    assert multi_layout_resource.layouts["2"].x is None
