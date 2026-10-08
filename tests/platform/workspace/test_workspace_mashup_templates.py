# -*- coding: utf-8 -*-

from types import SimpleNamespace

import pytest
from bson import ObjectId

from wirecloud.commons.utils.template.schemas.macdschemas import (
    MACDMashupResource,
    MACDMashupResourceLayout,
    MACDMashupWithParametrization,
    MACDParametrizationOptions,
    MACDParametrizationOptionsSource,
    MACDParametrizationOptionsStatus,
    MACType,
)
from wirecloud.platform.iwidget.models import WidgetInstance, WidgetLayout
from wirecloud.platform.wiring.schemas import (
    WiringBehaviour,
    WiringComponent,
    WiringComponents,
    WiringConnection,
    WiringConnectionEndpoint,
    WiringOperatorPreference,
    WiringType,
    WiringVisualDescription,
    WiringVisualDescriptionConnection,
)
from wirecloud.platform.workspace import mashupTemplateGenerator as generator
from wirecloud.platform.workspace import mashupTemplateParser as parser
from wirecloud.platform.workspace.models import DBWorkspacePreference, Tab, Workspace, WorkspaceAccessPermissions
from wirecloud.platform.workspace.schemas import IdMapping, IdMappingOperator, IdMappingWidget


def _workspace():
    owner = ObjectId()
    return Workspace(
        _id=ObjectId(),
        name="ws",
        title="Workspace",
        creator=owner,
        users=[WorkspaceAccessPermissions(id=owner, accesslevel=2)],
    )


async def test_parser_dependency_and_mapping_helpers(monkeypatch):
    monkeypatch.setattr(parser, "_", lambda text: text)
    assert str(parser.MissingDependencies(["a/b/1.0.0"])) == "Missing dependencies"

    template = SimpleNamespace(get_resource_dependencies=lambda: ["acme/widget/1.0.0"])
    monkeypatch.setattr(parser, "get_catalogue_resource", lambda *_args, **_kwargs: _none())

    async def _none():
        return None

    with pytest.raises(parser.MissingDependencies):
        await parser.check_mashup_dependencies(None, template, SimpleNamespace(id="u1"))

    async def _unavailable(*_args, **_kwargs):
        return SimpleNamespace(is_available_for=lambda _user: False)

    monkeypatch.setattr(parser, "get_catalogue_resource", _unavailable)
    with pytest.raises(ValueError):
        await parser.check_mashup_dependencies(None, template, SimpleNamespace(id="u1"))

    async def _ok_resource(*_args, **_kwargs):
        return SimpleNamespace(is_available_for=lambda _user: True)

    monkeypatch.setattr(parser, "get_catalogue_resource", _ok_resource)
    await parser.check_mashup_dependencies(None, template, SimpleNamespace(id="u1"))

    id_mapping = IdMapping(
        widget={"w1": IdMappingWidget(id="nw1", name="acme/widget/1.0.0")},
        operator={"1": IdMappingOperator(id="2")},
    )
    widget_ep = WiringConnectionEndpoint(type=WiringType.widget, id="w1", endpoint="out")
    op_ep = WiringConnectionEndpoint(type=WiringType.operator, id="1", endpoint="in")
    assert parser.map_id(widget_ep, id_mapping) == "nw1"
    assert parser.map_id(op_ep, id_mapping) == "2"

    valid = WiringConnection(source=widget_ep, target=op_ep)
    invalid = WiringConnection(
        source=WiringConnectionEndpoint(type=WiringType.widget, id="missing", endpoint="out"),
        target=op_ep,
    )
    assert parser.is_valid_connection(valid, id_mapping) is True
    assert parser.is_valid_connection(invalid, id_mapping) is False

    components = WiringComponents(
        operator={"1": WiringComponent(), "9": WiringComponent()},
        widget={"w1": WiringComponent(name="acme/widget/1.0.0"), "w9": WiringComponent(name="acme/other/1.0.0")},
    )
    parser._remap_component_ids(id_mapping, components, isGlobal=True)
    assert set(components.operator.keys()) == {"2"}
    assert set(components.widget.keys()) == {"nw1"}
    assert components.widget["nw1"].name == "acme/widget/1.0.0"

    visual = WiringVisualDescription(
        components=WiringComponents(operator={"2": WiringComponent()}, widget={"nw1": WiringComponent()}),
        connections=[WiringVisualDescriptionConnection(sourcename="A", targetname="B")],
    )
    parser._create_new_behaviour(visual, "Title", "Desc")
    assert len(visual.behaviours) == 1
    assert visual.behaviours[0].title == "Title"

    parser._remap_connection_endpoints({"A": "A2"}, {"B": "B2"}, visual)
    assert visual.connections[0].sourcename == "A2"
    assert visual.connections[0].targetname == "B2"


async def test_parser_build_workspace_from_template_branches(monkeypatch):
    monkeypatch.setattr(parser, "_", lambda text: text)
    db = SimpleNamespace()
    user = SimpleNamespace(id=ObjectId())
    template = SimpleNamespace(get_resource_processed_info=lambda **_kwargs: SimpleNamespace(name="base-name", title="Base Title"))
    called = {"alt": 0, "insert": 0, "fill": 0}

    async def _save_alternative(*_args, **_kwargs):
        called["alt"] += 1

    async def _insert_workspace(*_args, **_kwargs):
        called["insert"] += 1

    async def _fill(*_args, **_kwargs):
        called["fill"] += 1

    monkeypatch.setattr(parser, "save_alternative", _save_alternative)
    monkeypatch.setattr(parser, "insert_workspace", _insert_workspace)
    monkeypatch.setattr(parser, "fill_workspace_using_template", _fill)
    monkeypatch.setattr(parser, "is_a_workspace_with_that_name", lambda *_args, **_kwargs: _false())

    async def _false():
        return False

    built = await parser.build_workspace_from_template(
        db,
        None,
        template,
        user,
        allow_renaming=True,
        new_name="",
        new_title="",
    )
    assert built is not None
    assert called["alt"] == 1
    assert called["fill"] == 1

    built2 = await parser.build_workspace_from_template(
        db,
        None,
        template,
        user,
        allow_renaming=False,
        new_name="name-x",
        new_title="",
    )
    assert built2 is not None
    assert called["insert"] == 1

    monkeypatch.setattr(parser, "is_a_workspace_with_that_name", lambda *_args, **_kwargs: _true())

    async def _true():
        return True

    conflict = await parser.build_workspace_from_template(
        db,
        None,
        template,
        user,
        allow_renaming=False,
        new_name="taken",
        new_title="Taken",
    )
    assert conflict is None

    from_title = await parser.build_workspace_from_template(
        db,
        None,
        template,
        user,
        allow_renaming=True,
        new_name="",
        new_title="Only Title",
    )
    assert from_title.name == "only-title"


async def test_parser_fill_workspace_unsupported_type(monkeypatch):
    monkeypatch.setattr(parser, "_", lambda text: text)
    ws = _workspace()
    template = SimpleNamespace(get_resource_type=lambda: MACType.widget)
    with pytest.raises(TypeError):
        await parser.fill_workspace_using_template(None, None, SimpleNamespace(id=ObjectId()), ws, template)


async def test_parser_fill_workspace_using_template_minimal(monkeypatch):
    monkeypatch.setattr(parser, "_", lambda text: text)
    ws = _workspace()
    user_func = SimpleNamespace(id=ObjectId())

    endpoint_source = WiringConnectionEndpoint(type=WiringType.widget, id="oldw", endpoint="out")
    endpoint_target = WiringConnectionEndpoint(type=WiringType.operator, id="oldop", endpoint="in")
    endpoint_source_name = parser.get_endpoint_name(endpoint_source)
    endpoint_target_name = parser.get_endpoint_name(endpoint_target)

    mashup_description = SimpleNamespace(
        preferences={"custom": "x", "public": "true"},
        params=[SimpleNamespace(name="param", label="Param", type="text", description="", required=False)],
        tabs=[
            SimpleNamespace(
                title="Tab 1",
                name="tab-1",
                preferences={"tp": "tv"},
                resources=[
                    SimpleNamespace(
                        id="oldw",
                        vendor="acme",
                        name="widget",
                        version="1.0.0",
                        title="Widget",
                        readonly=False,
                        properties={"prop1": SimpleNamespace(readonly=False, value="pval")},
                        preferences={"pref1": SimpleNamespace(readonly=True, hidden=True, value="qval")},
                        layouts={"0": MACDMashupResourceLayout(x=1, y=2, w=4, h=5)},
                    )
                ],
            )
        ],
        wiring=SimpleNamespace(
                operators={
                    "oldop": SimpleNamespace(
                        name="acme/op/1.0.0",
                        preferences={"opref": WiringOperatorPreference(readonly=True, hidden=False, value="oval")},
                    )
                },
                connections=[WiringConnection(source=endpoint_source, target=endpoint_target, readonly=False)],
                visualdescription=WiringVisualDescription(
                    components=WiringComponents(
                        widget={"oldw": WiringComponent(name="acme/widget/1.0.0")},
                        operator={"1": WiringComponent(name="acme/op/1.0.0")},
                    ),
                    connections=[WiringVisualDescriptionConnection(sourcename=endpoint_source_name, targetname=endpoint_target_name)],
                    behaviours=[],
                ),
        ),
    )
    template = SimpleNamespace(get_resource_type=lambda: MACType.mashup, get_resource_info=lambda: mashup_description)

    class _Processor:
        def __init__(self, context):
            self.context = context

        def process(self, value):
            return f"proc:{value}"

    monkeypatch.setattr(parser, "TemplateValueProcessor", _Processor)
    monkeypatch.setattr(parser, "get_context_values", lambda *_args, **_kwargs: _ctx())
    monkeypatch.setattr(parser, "get_user_with_all_info", lambda *_args, **_kwargs: _user())
    monkeypatch.setattr(parser, "update_workspace_preferences", lambda *_args, **_kwargs: _none())
    monkeypatch.setattr(parser, "update_tab_preferences", lambda *_args, **_kwargs: _none())
    monkeypatch.setattr(parser, "get_user_by_id", lambda *_args, **_kwargs: _user())
    monkeypatch.setattr(parser, "set_initial_values", lambda *_args, **_kwargs: _none())
    monkeypatch.setattr(parser, "is_empty_wiring", lambda *_args, **_kwargs: False)

    async def _ctx():
        return {}

    async def _user():
        return SimpleNamespace(id=ws.creator)

    async def _none():
        return None

    async def _create_tab(_db, _user_func, title, workspace, name=None, allow_renaming=False):
        tab = Tab(id=f"{workspace.id}-0", name=name or "tab", title=title, visible=True)
        workspace.tabs[tab.id] = tab
        return tab

    monkeypatch.setattr(parser, "create_tab", _create_tab)

    async def _save_widget(_db, workspace, _iwidget_data, _user, tab, commit=False, resource_owner=None):
        widget = WidgetInstance(
            id=f"{tab.id}-0",
            title="Widget",
            resource=ObjectId(),
            layouts={"0": WidgetLayout()},
        )
        workspace.tabs[tab.id].widgets[widget.id] = widget
        return widget

    monkeypatch.setattr(parser, "save_widget_instance", _save_widget)

    widget_resource = SimpleNamespace(
        local_uri_part="acme/widget/1.0.0",
        get_processed_info=lambda **_kwargs: SimpleNamespace(
            variables=SimpleNamespace(
                preferences={"pref1": SimpleNamespace(default="pref-default")},
                properties={"prop1": SimpleNamespace(default="prop-default")},
            )
        ),
    )

    async def _widget_lookup(*_args, **_kwargs):
        return (SimpleNamespace(), widget_resource)

    monkeypatch.setattr("wirecloud.platform.widget.utils.get_or_add_widget_from_catalogue", _widget_lookup)

    changed = {"n": 0}

    async def _change_workspace(*_args, **_kwargs):
        changed["n"] += 1

    monkeypatch.setattr(parser, "change_workspace", _change_workspace)

    await parser.fill_workspace_using_template(None, None, user_func, ws, template)
    assert changed["n"] == 1
    assert len(ws.tabs) == 1
    tab = next(iter(ws.tabs.values()))
    assert len(tab.widgets) == 1
    assert "1" in ws.wiring_status.operators
    assert len(ws.wiring_status.connections) == 1
    assert len(ws.forced_values.extra_prefs) == 1


async def test_parser_fill_workspace_additional_branches(monkeypatch):
    monkeypatch.setattr(parser, "_", lambda text: text)
    ws = _workspace()
    ws.wiring_status.visualdescription = WiringVisualDescription(
        components=WiringComponents(
            widget={"origw": WiringComponent(name="acme/widget/1.0.0")},
            operator={"0": WiringComponent(name="acme/op/1.0.0")},
        ),
        connections=[WiringVisualDescriptionConnection(sourcename="w/origw/out", targetname="o/0/in")],
        behaviours=[],
    )
    user_func = SimpleNamespace(id=ObjectId())

    endpoint_source = WiringConnectionEndpoint(type=WiringType.widget, id="oldw", endpoint="out")
    endpoint_target = WiringConnectionEndpoint(type=WiringType.operator, id="oldop", endpoint="in")
    invalid_source = WiringConnectionEndpoint(type=WiringType.widget, id="missing", endpoint="out")

    mashup_description = SimpleNamespace(
        preferences={},
        params=[],
        tabs=[
            SimpleNamespace(
                title="Tab 1",
                name="tab-1",
                preferences={},
                resources=[
                    SimpleNamespace(
                        id="oldw",
                        vendor="acme",
                        name="widget",
                        version="1.0.0",
                        title="Widget",
                        readonly=True,
                        properties={
                            "prop1": SimpleNamespace(readonly=False, value=None),
                            "prop2": SimpleNamespace(readonly=True, value=None),
                        },
                        preferences={"pref1": SimpleNamespace(readonly=False, hidden=False, value=None)},
                        layouts={"0": MACDMashupResourceLayout(x=1, y=2, w=4, h=5)},
                    )
                ],
            )
        ],
        wiring=SimpleNamespace(
            operators={},
            connections=[
                WiringConnection(source=invalid_source, target=endpoint_target, readonly=False),
                WiringConnection(source=endpoint_source, target=endpoint_target, readonly=False),
            ],
            visualdescription=WiringVisualDescription(
                components=WiringComponents(
                    widget={"oldw": WiringComponent(name="acme/widget/1.0.0")},
                    operator={},
                ),
                connections=[WiringVisualDescriptionConnection(sourcename="w/oldw/out", targetname="o/oldop/in")],
                behaviours=[WiringBehaviour(title="b", description="", components=WiringComponents(operator={}, widget={"oldw": WiringComponent()}), connections=[])],
            ),
        ),
    )
    template = SimpleNamespace(get_resource_type=lambda: MACType.mashup, get_resource_info=lambda: mashup_description)

    class _Processor:
        def __init__(self, context):
            self.context = context

        def process(self, value):
            return f"proc:{value}"

    async def _none(*_args, **_kwargs):
        return None

    async def _ctx():
        return {}

    async def _user():
        return SimpleNamespace(id=ws.creator)

    async def _create_tab(_db, _user_func, title, workspace, name=None, allow_renaming=False):
        tab = Tab(id=f"{workspace.id}-0", name=name or "tab", title=title, visible=True)
        workspace.tabs[tab.id] = tab
        return tab

    async def _save_widget(_db, workspace, _iwidget_data, _user, tab, commit=False, resource_owner=None):
        widget = SimpleNamespace(id=f"{tab.id}-0", readonly=False)
        workspace.tabs[tab.id].widgets[widget.id] = widget
        return widget

    widget_resource = SimpleNamespace(
        local_uri_part="acme/widget/1.0.0",
        get_processed_info=lambda **_kwargs: SimpleNamespace(
            variables=SimpleNamespace(
                preferences={"pref1": SimpleNamespace(default="pref-default")},
                properties={
                    "prop1": SimpleNamespace(default="prop-default"),
                    "prop2": SimpleNamespace(default="prop2-default"),
                },
            )
        ),
    )

    async def _widget_lookup(*_args, **_kwargs):
        return (SimpleNamespace(), widget_resource)

    changed = {"n": 0}

    async def _change_workspace(*_args, **_kwargs):
        changed["n"] += 1

    monkeypatch.setattr(parser, "TemplateValueProcessor", _Processor)
    monkeypatch.setattr(parser, "get_context_values", lambda *_args, **_kwargs: _ctx())
    monkeypatch.setattr(parser, "get_user_with_all_info", lambda *_args, **_kwargs: _user())
    monkeypatch.setattr(parser, "get_user_by_id", lambda *_args, **_kwargs: _user())
    monkeypatch.setattr(parser, "update_workspace_preferences", lambda *_args, **_kwargs: _none())
    monkeypatch.setattr(parser, "update_tab_preferences", lambda *_args, **_kwargs: _none())
    monkeypatch.setattr(parser, "set_initial_values", lambda *_args, **_kwargs: _none())
    monkeypatch.setattr(parser, "create_tab", _create_tab)
    monkeypatch.setattr(parser, "save_widget_instance", _save_widget)
    monkeypatch.setattr("wirecloud.platform.widget.utils.get_or_add_widget_from_catalogue", _widget_lookup)
    monkeypatch.setattr(parser, "change_workspace", _change_workspace)

    await parser.fill_workspace_using_template(None, None, user_func, ws, template)
    assert changed["n"] == 1
    tab = next(iter(ws.tabs.values()))
    assert list(tab.widgets.values())[0].readonly is True
    assert len(ws.wiring_status.visualdescription.behaviours) >= 1


async def test_parser_fill_workspace_wiring_behaviour_branches(monkeypatch):
    monkeypatch.setattr(parser, "_", lambda text: text)
    ws = _workspace()
    ws.wiring_status.operators = {"0": SimpleNamespace(), "5": SimpleNamespace()}
    ws.wiring_status.visualdescription = WiringVisualDescription(
        components=WiringComponents(widget={}, operator={}),
        connections=[],
        behaviours=[WiringBehaviour(title="existing", description="", components=WiringComponents(widget={}, operator={}), connections=[])],
    )
    user_func = SimpleNamespace(id=ObjectId())

    mashup_description = SimpleNamespace(
        preferences={},
        params=[],
        tabs=[],
        wiring=SimpleNamespace(
            operators={"1": SimpleNamespace(name="acme/op/1.0.0", preferences={"pref": WiringOperatorPreference(readonly=False, hidden=False, value="x")})},
            connections=[],
            visualdescription=WiringVisualDescription(
                components=WiringComponents(widget={}, operator={"1": WiringComponent()}),
                connections=[],
                behaviours=[],
            ),
        ),
    )
    template = SimpleNamespace(get_resource_type=lambda: MACType.mashup, get_resource_info=lambda: mashup_description)

    async def _none(*_args, **_kwargs):
        return None

    async def _ctx():
        return {}

    async def _user():
        return SimpleNamespace(id=ws.creator)

    class _Processor:
        def __init__(self, context):
            self.context = context

        def process(self, value):
            return value

    monkeypatch.setattr(parser, "TemplateValueProcessor", _Processor)
    monkeypatch.setattr(parser, "get_context_values", lambda *_args, **_kwargs: _ctx())
    monkeypatch.setattr(parser, "get_user_with_all_info", lambda *_args, **_kwargs: _user())
    monkeypatch.setattr(parser, "update_workspace_preferences", lambda *_args, **_kwargs: _none())
    monkeypatch.setattr(parser, "change_workspace", lambda *_args, **_kwargs: _none())

    await parser.fill_workspace_using_template(None, None, user_func, ws, template)
    assert "6" in ws.wiring_status.operators
    assert len(ws.wiring_status.visualdescription.behaviours) >= 2


async def test_parser_fill_workspace_without_forced_values(monkeypatch):
    monkeypatch.setattr(parser, "_", lambda text: text)
    ws = _workspace()
    user_func = SimpleNamespace(id=ObjectId())
    mashup_description = SimpleNamespace(
        preferences={},
        params=[],
        tabs=[
            SimpleNamespace(
                title="Tab 1",
                name="tab-1",
                preferences={},
                resources=[
                    SimpleNamespace(
                        id="r1",
                        vendor="acme",
                        name="widget",
                        version="1.0.0",
                        title="Widget",
                        readonly=False,
                        properties={"prop1": SimpleNamespace(readonly=False, value="v")},
                        preferences={"pref1": SimpleNamespace(readonly=False, hidden=False, value="v")},
                        layouts={},
                    )
                ],
            )
        ],
        wiring=SimpleNamespace(operators={}, connections=[], visualdescription=WiringVisualDescription(components=WiringComponents(widget={}, operator={}), connections=[], behaviours=[])),
    )
    template = SimpleNamespace(get_resource_type=lambda: MACType.mashup, get_resource_info=lambda: mashup_description)

    async def _none(*_args, **_kwargs):
        return None

    async def _ctx():
        return {}

    async def _user():
        return SimpleNamespace(id=ws.creator)

    class _Processor:
        def __init__(self, context):
            self.context = context

        def process(self, value):
            return value

    async def _create_tab(_db, _user_func, title, workspace, name=None, allow_renaming=False):
        tab = Tab(id=f"{workspace.id}-0", name=name or "tab", title=title, visible=True)
        workspace.tabs[tab.id] = tab
        return tab

    async def _save_widget(_db, workspace, _iwidget_data, _user, tab, commit=False, resource_owner=None):
        widget = SimpleNamespace(id=f"{tab.id}-0", readonly=False)
        workspace.tabs[tab.id].widgets[widget.id] = widget
        return widget

    widget_resource = SimpleNamespace(
        local_uri_part="acme/widget/1.0.0",
        get_processed_info=lambda **_kwargs: SimpleNamespace(
            variables=SimpleNamespace(
                preferences={"pref1": SimpleNamespace(default="pref-default")},
                properties={"prop1": SimpleNamespace(default="prop-default")},
            )
        ),
    )

    async def _widget_lookup(*_args, **_kwargs):
        return (SimpleNamespace(), widget_resource)

    monkeypatch.setattr(parser, "TemplateValueProcessor", _Processor)
    monkeypatch.setattr(parser, "get_context_values", lambda *_args, **_kwargs: _ctx())
    monkeypatch.setattr(parser, "get_user_with_all_info", lambda *_args, **_kwargs: _user())
    monkeypatch.setattr(parser, "get_user_by_id", lambda *_args, **_kwargs: _user())
    monkeypatch.setattr(parser, "update_workspace_preferences", lambda *_args, **_kwargs: _none())
    monkeypatch.setattr(parser, "update_tab_preferences", lambda *_args, **_kwargs: _none())
    monkeypatch.setattr(parser, "set_initial_values", lambda *_args, **_kwargs: _none())
    monkeypatch.setattr(parser, "create_tab", _create_tab)
    monkeypatch.setattr(parser, "save_widget_instance", _save_widget)
    monkeypatch.setattr("wirecloud.platform.widget.utils.get_or_add_widget_from_catalogue", _widget_lookup)
    monkeypatch.setattr(parser, "change_workspace", lambda *_args, **_kwargs: _none())

    await parser.fill_workspace_using_template(None, None, user_func, ws, template)
    assert ws.forced_values.widget == {}


async def test_generator_process_widget_instance_and_invalid_source(monkeypatch):
    iwidget = WidgetInstance(
        id="w1",
        resource=ObjectId(),
        title="Widget title",
        layouts={"0": WidgetLayout(x=2, y=1, w=4, h=5)},
    )

    widget_description = SimpleNamespace(
        wiring=SimpleNamespace(
            outputs=[SimpleNamespace(name="out", type="text", label="", description="", friendcode="")],
            inputs=[SimpleNamespace(name="in", type="text", label="", description="", friendcode="", actionlabel="")],
        ),
        preferences=[SimpleNamespace(name="pref_bool", type="boolean"), SimpleNamespace(name="pref_num", type="number")],
        properties=[],
    )
    resource = SimpleNamespace(
        vendor="acme",
        short_name="widget",
        version="1.0.0",
        get_template=lambda: SimpleNamespace(get_resource_info=lambda: widget_description),
    )

    async def _resource(*_args, **_kwargs):
        return resource

    monkeypatch.setattr(generator, "get_catalogue_resource_by_id", _resource)

    class _Cache:
        async def get_variable_value_from_varname(self, _db, _request, component_type, _component_id, var_name):
            if component_type == "iwidget" and var_name == "pref_bool":
                return True
            if component_type == "iwidget" and var_name == "pref_num":
                return 7
            return "value"

    wiring = generator.MACDMashupWiring()
    parametrization = {"w1": {}}
    data = await generator.process_widget_instance(None, None, iwidget, wiring, parametrization, True, _Cache())
    assert data.id == "w1"
    assert data.preferences["pref_bool"].value == "true"
    assert data.preferences["pref_num"].value == "7"
    assert data.properties == {}
    assert len(wiring.outputs) == 1
    assert len(wiring.inputs) == 1

    no_param_data = await generator.process_widget_instance(None, None, iwidget, generator.MACDMashupWiring(), {}, True, _Cache())
    assert no_param_data.id == "w1"

    bad_param = {"w1": {"pref_bool": SimpleNamespace(source="invalid", status=MACDParametrizationOptionsStatus.normal, value="x")}}
    with pytest.raises(Exception):
        await generator.process_widget_instance(None, None, iwidget, generator.MACDMashupWiring(), bad_param, False, _Cache())

    bad_property_desc = SimpleNamespace(
        wiring=SimpleNamespace(outputs=[], inputs=[]),
        preferences=[],
        properties=[SimpleNamespace(name="prop_bad", type="text")],
    )
    bad_property_resource = SimpleNamespace(
        vendor="acme",
        short_name="widget",
        version="1.0.0",
        get_template=lambda: SimpleNamespace(get_resource_info=lambda: bad_property_desc),
    )

    async def _bad_property_resource(*_args, **_kwargs):
        return bad_property_resource

    monkeypatch.setattr(generator, "get_catalogue_resource_by_id", _bad_property_resource)
    with pytest.raises(Exception):
        await generator.process_widget_instance(
            None,
            None,
            iwidget,
            generator.MACDMashupWiring(),
            {"w1": {"prop_bad": SimpleNamespace(source="invalid", status=MACDParametrizationOptionsStatus.normal, value="x")}},
            False,
            _Cache(),
        )


async def test_generator_process_widget_instance_additional_param_sources(monkeypatch):
    iwidget = WidgetInstance(
        id="w2",
        resource=ObjectId(),
        title="Widget title",
        layouts={"0": WidgetLayout(x=2, y=1, w=4, h=5)},
    )
    widget_description = SimpleNamespace(
        wiring=SimpleNamespace(outputs=[], inputs=[]),
        preferences=[
            SimpleNamespace(name="pref_default", type="text"),
            SimpleNamespace(name="pref_current", type="text"),
            SimpleNamespace(name="pref_custom", type="number"),
        ],
        properties=[SimpleNamespace(name="prop_current", type="text")],
    )
    resource = SimpleNamespace(
        vendor="acme",
        short_name="widget",
        version="1.0.0",
        get_template=lambda: SimpleNamespace(get_resource_info=lambda: widget_description),
    )

    async def _resource(*_args, **_kwargs):
        return resource

    class _Cache:
        async def get_variable_value_from_varname(self, _db, _request, _component_type, _component_id, var_name):
            return {"pref_current": "cv", "prop_current": "pv"}.get(var_name, "")

    monkeypatch.setattr(generator, "get_catalogue_resource_by_id", _resource)
    parametrization = {
        "w2": {
            "pref_default": SimpleNamespace(
                source=MACDParametrizationOptionsSource.default,
                status=MACDParametrizationOptionsStatus.normal,
                value="",
            ),
            "pref_current": SimpleNamespace(
                source=MACDParametrizationOptionsSource.current,
                status=MACDParametrizationOptionsStatus.hidden,
                value="",
            ),
            "pref_custom": SimpleNamespace(
                source=MACDParametrizationOptionsSource.custom,
                status=MACDParametrizationOptionsStatus.readonly,
                value="8",
            ),
            "prop_current": SimpleNamespace(
                source=MACDParametrizationOptionsSource.current,
                status=MACDParametrizationOptionsStatus.normal,
                value="",
            ),
        }
    }
    with pytest.raises(Exception):
        await generator.process_widget_instance(None, None, iwidget, generator.MACDMashupWiring(), parametrization, False, _Cache())


async def test_generator_process_widget_instance_property_and_default_paths(monkeypatch):
    iwidget = WidgetInstance(
        id="w3",
        resource=ObjectId(),
        title="Widget title",
        layouts={"0": WidgetLayout(x=2, y=1, w=4, h=5)},
    )
    widget_description = SimpleNamespace(
        wiring=SimpleNamespace(outputs=[], inputs=[]),
        preferences=[SimpleNamespace(name="pref_hidden_default", type="text")],
        properties=[
            SimpleNamespace(name="prop_default_skip", type="text"),
            SimpleNamespace(name="prop_hidden_default", type="text"),
            SimpleNamespace(name="prop_custom", type="text"),
            SimpleNamespace(name="prop_current", type="text"),
            SimpleNamespace(name="prop_plain", type="text"),
        ],
    )
    resource = SimpleNamespace(
        vendor="acme",
        short_name="widget",
        version="1.0.0",
        get_template=lambda: SimpleNamespace(get_resource_info=lambda: widget_description),
    )

    async def _resource(*_args, **_kwargs):
        return resource

    class _Cache:
        async def get_variable_value_from_varname(self, _db, _request, _component_type, _component_id, var_name):
            return f"cached:{var_name}"

    monkeypatch.setattr(generator, "get_catalogue_resource_by_id", _resource)
    parametrization = {
        "w3": {
            "pref_hidden_default": SimpleNamespace(
                source=MACDParametrizationOptionsSource.default,
                status=MACDParametrizationOptionsStatus.hidden,
                value="",
            ),
            "prop_default_skip": SimpleNamespace(
                source=MACDParametrizationOptionsSource.default,
                status=MACDParametrizationOptionsStatus.normal,
                value="",
            ),
            "prop_hidden_default": SimpleNamespace(
                source=MACDParametrizationOptionsSource.default,
                status=MACDParametrizationOptionsStatus.hidden,
                value="",
            ),
            "prop_custom": SimpleNamespace(
                source=MACDParametrizationOptionsSource.custom,
                status=MACDParametrizationOptionsStatus.readonly,
                value="custom",
            ),
            "prop_current": SimpleNamespace(
                source=MACDParametrizationOptionsSource.current,
                status=MACDParametrizationOptionsStatus.normal,
                value="",
            ),
        }
    }
    with pytest.raises(Exception):
        await generator.process_widget_instance(None, None, iwidget, generator.MACDMashupWiring(), parametrization, False, _Cache())


async def test_generator_build_json_and_xml(monkeypatch):
    ws = _workspace()
    ws.preferences = [
        DBWorkspacePreference(name="public", inherit=False, value="false"),
        DBWorkspacePreference(name="custom", inherit=False, value="x"),
    ]
    tab = Tab(
        id=f"{ws.id}-0",
        name="tab0",
        title="Tab 0",
        preferences=[
            DBWorkspacePreference(name="tabpref", inherit=False, value="tv"),
            DBWorkspacePreference(name="tabpref2", inherit=True, value="ignored"),
        ],
        widgets={"w1": WidgetInstance(id="w1", resource=ObjectId())},
    )
    ws.tabs = {tab.id: tab}
    ws.wiring_status.operators = {
        "1": SimpleNamespace(id="1", name="acme/op/1.0.0", preferences={"op_pref": SimpleNamespace(value={"users": {"a": "b"}})})
    }
    ws.wiring_status.connections = [
        WiringConnection(
            source=WiringConnectionEndpoint(type=WiringType.widget, id="w1", endpoint="out"),
            target=WiringConnectionEndpoint(type=WiringType.operator, id="1", endpoint="in"),
        )
    ]

    async def _description(*_args, **_kwargs):
        return "Generated description"

    async def _username(*_args, **_kwargs):
        return "alice"

    async def _user(*_args, **_kwargs):
        return SimpleNamespace(id=ws.creator)

    async def _process_widget(*_args, **_kwargs):
        return MACDMashupResource(id="w1", vendor="acme", name="widget", version="1.0.0")

    async def _catalogue(*_args, **_kwargs):
        return SimpleNamespace(description=SimpleNamespace(preferences=[SimpleNamespace(name="op_pref")]))

    class _Cache:
        async def get_variable_value_from_varname(self, *_args, **_kwargs):
            return "cached"

    monkeypatch.setattr(generator, "get_workspace_description", _description)
    monkeypatch.setattr(generator, "get_username_by_id", _username)
    monkeypatch.setattr(generator, "get_user_with_all_info", _user)
    monkeypatch.setattr(generator, "process_widget_instance", _process_widget)
    monkeypatch.setattr(generator, "get_catalogue_resource", _catalogue)
    monkeypatch.setattr(generator, "VariableValueCacheManager", lambda *_args, **_kwargs: _Cache())

    options = MACDMashupWithParametrization(
        type=MACType.mashup,
        name="mashup",
        vendor="acme",
        version="1.0.0",
        title="Mashup",
        description="",
        email="a@example.com",
        embedmacs=True,
    )
    result = await generator.build_json_template_from_workspace(None, None, options, ws)
    assert result.description == "Generated description"
    assert len(result.authors) == 1
    assert result.preferences["custom"] == "x"
    assert "1" in result.wiring.operators
    assert len(result.embedded) == 1
    assert result.embedmacs is False

    ws.wiring_status.version = "1.0"
    with pytest.raises(ValueError):
        await generator.build_json_template_from_workspace(None, None, options, ws)

    monkeypatch.setattr(generator, "build_json_template_from_workspace", lambda *_args, **_kwargs: _built())
    monkeypatch.setattr(generator.xml, "write_xml_description", lambda *_args, **_kwargs: "<xml/>")

    async def _built():
        return options

    xml_out = await generator.build_xml_template_from_workspace(None, None, options, _workspace())
    assert xml_out == "<xml/>"


async def test_generator_build_json_operator_parametrization_branches(monkeypatch):
    ws = _workspace()
    ws.tabs = {f"{ws.id}-0": Tab(id=f"{ws.id}-0", name="tab0", title="", widgets={})}
    ws.wiring_status.operators = {
        "1": SimpleNamespace(id="1", name="acme/op/1.0.0", preferences={"a": SimpleNamespace(value={"users": {"u": "x"}})}),
    }

    async def _description(*_args, **_kwargs):
        return "desc"

    async def _username(*_args, **_kwargs):
        return "alice"

    async def _user(*_args, **_kwargs):
        return SimpleNamespace(id=ws.creator)

    async def _catalogue(*_args, **_kwargs):
        return SimpleNamespace(
            description=SimpleNamespace(preferences=[SimpleNamespace(name="a"), SimpleNamespace(name="b"), SimpleNamespace(name="c"), SimpleNamespace(name="d")])
        )

    class _Cache:
        async def get_variable_value_from_varname(self, *_args, **_kwargs):
            return "cached"

    monkeypatch.setattr(generator, "get_workspace_description", _description)
    monkeypatch.setattr(generator, "get_username_by_id", _username)
    monkeypatch.setattr(generator, "get_user_with_all_info", _user)
    monkeypatch.setattr(generator, "process_widget_instance", lambda *_args, **_kwargs: _resource())
    monkeypatch.setattr(generator, "get_catalogue_resource", _catalogue)
    monkeypatch.setattr(generator, "VariableValueCacheManager", lambda *_args, **_kwargs: _Cache())

    async def _resource():
        return MACDMashupResource(id="w1", vendor="acme", name="widget", version="1.0.0")

    options = MACDMashupWithParametrization(
        type=MACType.mashup,
        name="mashup",
        vendor="acme",
        version="1.0.0",
        title="Mashup",
        description="x",
        email="a@example.com",
        embedmacs=False,
    )
    options.parametrization.ioperators = {
        "1": {
            "a": SimpleNamespace(source=MACDParametrizationOptionsSource.default, status=MACDParametrizationOptionsStatus.normal, value=""),
            "b": SimpleNamespace(source=MACDParametrizationOptionsSource.current, status=MACDParametrizationOptionsStatus.normal, value=""),
            "c": SimpleNamespace(source=MACDParametrizationOptionsSource.custom, status=MACDParametrizationOptionsStatus.readonly, value="custom"),
            "d": SimpleNamespace(source=MACDParametrizationOptionsSource.default, status=MACDParametrizationOptionsStatus.hidden, value=""),
        }
    }
    out = await generator.build_json_template_from_workspace(None, None, options, ws)
    assert "a" not in out.wiring.operators["1"].preferences
    assert out.wiring.operators["1"].preferences["b"].value == "cached"
    assert out.wiring.operators["1"].preferences["c"].value == "custom"
    assert out.wiring.operators["1"].preferences["d"].value is None

    options_bad = MACDMashupWithParametrization(
        type=MACType.mashup,
        name="mashup",
        vendor="acme",
        version="1.0.0",
        title="Mashup",
        description="x",
        email="a@example.com",
    )
    options_bad.parametrization.ioperators = {
        "1": {
            "a": SimpleNamespace(source="invalid", status=MACDParametrizationOptionsStatus.normal, value="x"),
        }
    }
    with pytest.raises(Exception):
        await generator.build_json_template_from_workspace(None, None, options_bad, ws)
