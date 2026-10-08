# -*- coding: utf-8 -*-

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from bson import ObjectId
from Crypto.Cipher import AES
from starlette.requests import Request

from wirecloud.commons.utils.template.schemas.macdschemas import MACDPreference, MACDProperty
from wirecloud.platform.iwidget.models import (
    WidgetInstance,
    WidgetLayout,
    WidgetPermissions,
    WidgetVariables,
)
from wirecloud.platform.preferences.schemas import WorkspacePreference
from wirecloud.platform.workspace import utils
from wirecloud.platform.workspace.models import (
    DBWorkspaceForcedValues,
    Tab,
    Workspace,
    WorkspaceAccessPermissions,
    WorkspaceExtraPreference,
    WorkspaceForcedValue,
    WorkspaceWiring,
)
from wirecloud.platform.workspace.schemas import CacheEntry, TabData


def _request():
    req = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "server": ("wirecloud.example.org", 443),
            "path": "/api/workspace",
            "query_string": b"",
            "headers": [(b"host", b"wirecloud.example.org")],
        }
    )
    req.state.lang = "en"
    return req


def _workspace():
    creator = ObjectId()
    return Workspace(
        _id=ObjectId(),
        name="workspace",
        title="Workspace",
        creator=creator,
        users=[WorkspaceAccessPermissions(id=creator, accesslevel=2)],
    )


@pytest.fixture(autouse=True)
def _patch_gettext(monkeypatch):
    monkeypatch.setattr(utils, "_", lambda text: text)


def test_cache_keys_and_encrypt_decrypt():
    ws = _workspace()
    user = SimpleNamespace(id="u1")
    assert "_variables_values_cache/" in utils._variable_values_cache_key(ws, user)
    assert utils._workspace_cache_key(ws, None).endswith("/anonymous")

    utils.SECRET_KEY = "x" * 32
    encrypted = utils.encrypt_value({"k": "v"})
    assert isinstance(encrypted, str)
    assert utils.decrypt_value("invalid") == ""

    key = utils.SECRET_KEY[:32].encode("utf-8")
    payload = b'{"a":1}         '
    cipher = AES.new(key, AES.MODE_ECB)
    encrypted_valid = utils.base64.b64encode(cipher.encrypt(payload)).decode("utf-8")
    assert utils.decrypt_value(encrypted_valid) == {"a": 1}


def test_process_forced_values_and_process_variable(monkeypatch):
    utils.SECRET_KEY = "x" * 32
    ws = _workspace()
    ws.forced_values = DBWorkspaceForcedValues(
        extra_prefs=[WorkspaceExtraPreference(name="ep1", inheritable=False, label="L", type="text", description="", required=True)],
        widget={"w1": {"p1": WorkspaceForcedValue(value="{{params.ep1}}", hidden=True)}},
        operator={"1": {"o1": WorkspaceForcedValue(value="{{params.ep1}}", hidden=False)}},
    )
    prefs = {"ep1": WorkspacePreference(value="hello", inherit=False)}

    class _Processor:
        def __init__(self, context):
            self.context = context

        def process(self, _value):
            return self.context["params"]["ep1"] + "-processed"

    monkeypatch.setattr(utils, "TemplateValueProcessor", _Processor)
    forced = utils.process_forced_values(ws, SimpleNamespace(id="u1"), {"ctx": {}}, prefs)
    assert forced.iwidget["w1"]["p1"].value == "hello-processed"
    assert forced.ioperator["1"]["o1"].value == "hello-processed"
    assert forced.empty_params == []

    ws.forced_values = DBWorkspaceForcedValues()
    empty_forced = utils.process_forced_values(ws, None, {}, {})
    assert empty_forced.iwidget == {}
    assert empty_forced.ioperator == {}

    ws.forced_values = DBWorkspaceForcedValues(
        extra_prefs=[WorkspaceExtraPreference(name="missing", inheritable=False, label="M", type="text", description="", required=True)],
        widget={"w1": {"p1": WorkspaceForcedValue(value="{{params.missing}}")}},
    )
    monkeypatch.setattr(utils, "TemplateValueProcessor", lambda **_kwargs: SimpleNamespace(process=lambda value: value))
    missing_param = utils.process_forced_values(ws, None, {}, {})
    assert missing_param.empty_params == ["missing"]

    values = {"iwidget": {"w1": {}}, "ioperator": {"1": {}}}
    vardef = MACDPreference(
        name="p1",
        type="text",
        label="P1",
        description="",
        default="d",
        readonly=False,
        required=False,
        secure=True,
        multiuser=False,
    )
    forced_values = utils.WorkspaceForcedValues(iwidget={"w1": {"p1": WorkspaceForcedValue(value="x", hidden=True)}})
    utils._process_variable("iwidget", "w1", vardef, None, forced_values, values, SimpleNamespace(id="u1"), SimpleNamespace(id="owner"))
    assert values["iwidget"]["w1"]["p1"].readonly is True
    assert values["iwidget"]["w1"]["p1"].hidden is True

    vardef.secure = False
    values = {"iwidget": {"w1": {}}}
    forced_non_secure = utils.WorkspaceForcedValues(iwidget={"w1": {"p1": WorkspaceForcedValue(value="12", hidden=False)}})
    utils._process_variable("iwidget", "w1", vardef, None, forced_non_secure, values, SimpleNamespace(id="u1"), SimpleNamespace(id="owner"))
    assert values["iwidget"]["w1"]["p1"].value == "12"

    values = {"iwidget": {"w2": {}}}
    utils._process_variable(
        "iwidget",
        "w2",
        vardef,
        WidgetVariables(users={}),
        utils.WorkspaceForcedValues(),
        values,
        SimpleNamespace(id="u1"),
        SimpleNamespace(id="owner"),
    )
    assert values["iwidget"]["w2"]["p1"].readonly is False
    assert values["iwidget"]["w2"]["p1"].value == "d"


async def test_variable_cache_manager_and_workspace_entry(monkeypatch, db_session):
    ws = _workspace()
    user = SimpleNamespace(id="u1")
    req = _request()

    cache_values = {
        "iwidget": {"w1": {"v1": CacheEntry(type="text", secure=False, value="plain", readonly=False, hidden=False)}},
        "ioperator": {"1": {"v2": CacheEntry(type="text", secure=True, value="secret", readonly=True, hidden=True)}},
    }
    manager = utils.VariableValueCacheManager(ws, user)

    async def _cache_get(_key):
        return cache_values

    monkeypatch.setattr(utils.cache, "get", _cache_get)
    val = await manager.get_variable_value_from_varname(db_session, req, "iwidget", "w1", "v1")
    assert val == "plain"

    data_plain = await manager.get_variable_data(db_session, req, "iwidget", "w1", "v1")
    assert data_plain.value == "plain"

    data_secure = await manager.get_variable_data(db_session, req, "ioperator", "1", "v2")
    assert data_secure.value == "********"
    secure_raw = await manager.get_variable_value_from_varname(db_session, req, "ioperator", "1", "v2")
    assert secure_raw == ""

    async def _cache_get_none(_key):
        return None

    async def _populate(*_args, **_kwargs):
        return cache_values

    monkeypatch.setattr(utils.cache, "get", _cache_get_none)
    monkeypatch.setattr(utils, "_populate_variables_values_cache", _populate)
    manager2 = utils.VariableValueCacheManager(ws, user)
    populated = await manager2.get_variable_values(db_session, req)
    assert "iwidget" in populated

    fake_workspace = SimpleNamespace(last_modified=datetime.now(timezone.utc))

    async def _not_accessible(_db, _user):
        return False

    fake_workspace.is_accessible_by = _not_accessible
    denied = await utils.get_workspace_entry(db_session, user, req, fake_workspace)
    assert denied.status_code == 403

    not_found = await utils.get_workspace_entry(db_session, user, req, None)
    assert not_found.status_code == 404

    async def _accessible(_db, _user):
        return True

    fake_workspace.is_accessible_by = _accessible
    monkeypatch.setattr(utils, "check_if_modified_since", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(utils, "patch_cache_headers", lambda response, *_args, **_kwargs: response)
    response_304 = await utils.get_workspace_entry(db_session, user, req, fake_workspace)
    assert response_304.status_code == 304

    class _Cacheable:
        def get_response(self):
            return utils.Response(status_code=200, content="ok")

    monkeypatch.setattr(utils, "check_if_modified_since", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(utils, "get_global_workspace_data", lambda *_args, **_kwargs: _cacheable())

    async def _cacheable():
        return _Cacheable()

    response_200 = await utils.get_workspace_entry(db_session, user, req, fake_workspace)
    assert response_200.status_code == 200


async def test_workspace_data_tab_helpers_and_widget_data(monkeypatch, db_session):
    ws = _workspace()
    ws.description = "plain"
    ws.longdescription = "# Heading"
    user = SimpleNamespace(id=ws.creator, has_perm=lambda _perm: False, is_superuser=False)

    async def _username(_db, _uid):
        return "alice"

    monkeypatch.setattr(utils, "get_username_by_id", _username)
    data = await utils.get_workspace_data(db_session, ws, user)
    assert data.owner == "alice"
    assert "<h1>" in data.longdescription

    ws.longdescription = ""
    data2 = await utils.get_workspace_data(db_session, ws, user)
    assert data2.longdescription == "plain"

    assert utils.first_id_tab({"w-0": Tab(id="w-0", name="a", title="A"), "w-2": Tab(id="w-2", name="b", title="B")}) == 1

    changed = {"n": 0}

    async def _change_workspace(*_args, **_kwargs):
        changed["n"] += 1

    monkeypatch.setattr("wirecloud.platform.workspace.crud.change_workspace", _change_workspace)
    tab = await utils.create_tab(db_session, user, "My Tab", ws, name="")
    assert tab.visible is True
    assert changed["n"] == 1

    async def _save_alternative_tab(_db, tab):
        tab.name = "renamed-tab"
        return tab

    monkeypatch.setattr("wirecloud.commons.utils.db.save_alternative_tab", _save_alternative_tab)
    tab2 = await utils.create_tab(db_session, user, "Another", ws, allow_renaming=True)
    assert tab2.name == "renamed-tab"
    tab3 = await utils.create_tab(db_session, user, "Another", ws, name="explicit-name")
    assert tab3.name == "explicit-name"

    iwidget = WidgetInstance(
        id="w1",
        title="Widget",
        widget_uri="acme/widget/1.0.0",
        layouts={"0": WidgetLayout(x=2, y=1)},
        permissions=WidgetPermissions(),
    )
    req = _request()
    widget_data = await utils.get_widget_instance_data(db_session, req, iwidget, ws, cache_manager=SimpleNamespace(), user=user)
    assert widget_data.id == "w1"
    assert len(widget_data.layouts) == 1
    assert widget_data.layouts["0"].x == 2

    iwidget.resource = ObjectId()
    monkeypatch.setattr(utils, "get_catalogue_resource_by_id", lambda *_args, **_kwargs: _none())

    async def _none():
        return None

    missing_resource = await utils.get_widget_instance_data(db_session, req, iwidget, ws, cache_manager=SimpleNamespace(), user=user)
    assert missing_resource.id == "w1"

    resource_info = SimpleNamespace(
        preferences=[SimpleNamespace(name="p1")],
        properties=[SimpleNamespace(name="k1")],
    )
    resource = SimpleNamespace(get_processed_info=lambda **_kwargs: resource_info)
    monkeypatch.setattr(utils, "get_catalogue_resource_by_id", lambda *_args, **_kwargs: _resource())

    async def _resource():
        return resource

    class _CacheMgr:
        async def get_variable_data(self, *_args, **_kwargs):
            return SimpleNamespace(name="x", secure=False, readonly=False, hidden=False, value="v")

    full_data = await utils.get_widget_instance_data(db_session, req, iwidget, ws, cache_manager=_CacheMgr(), user=user)
    assert "p1" in full_data.preferences
    assert "k1" in full_data.properties

    monkeypatch.setattr(utils, "VariableValueCacheManager", lambda *_args, **_kwargs: _CacheMgr())
    full_data_auto_cache = await utils.get_widget_instance_data(db_session, req, iwidget, ws, cache_manager=None, user=user)
    assert "p1" in full_data_auto_cache.preferences

    tab = Tab(id=f"{ws.id}-7", name="tab", title="Tab", widgets={"w1": iwidget})
    monkeypatch.setattr(utils, "get_tab_preference_values", lambda *_args, **_kwargs: _prefs())

    async def _prefs():
        return {"p": WorkspacePreference(value="v", inherit=False)}

    tab_data = await utils.get_tab_data(db_session, req, tab, workspace=ws, cache_manager=_CacheMgr(), user=user)
    assert tab_data.id.endswith("-7")
    assert len(tab_data.widgets) == 1

    monkeypatch.setattr("wirecloud.platform.workspace.crud.get_workspace_by_id", lambda *_args, **_kwargs: _ws())

    async def _ws():
        return ws

    resolved = await utils.get_tab_data(db_session, req, tab, workspace=None, cache_manager=_CacheMgr(), user=user)
    assert resolved.name == "tab"

    resolved_auto_cache = await utils.get_tab_data(db_session, req, tab, workspace=ws, cache_manager=None, user=user)
    assert resolved_auto_cache.name == "tab"

    assert utils.is_there_a_tab_with_that_name("tab", {tab.id: tab}) is True
    assert utils.is_there_a_tab_with_that_name("missing", {tab.id: tab}) is False
    assert utils.is_owner_or_has_permission(SimpleNamespace(id=ws.creator, has_perm=lambda _perm: False), ws, "X") is True
    assert utils.is_owner_or_has_permission(SimpleNamespace(id=ObjectId(), has_perm=lambda perm: perm == "X"), ws, "X") is True


async def test_populate_variables_values_cache(monkeypatch, db_session):
    ws = _workspace()
    req = _request()
    creator = ws.creator
    iwidget = WidgetInstance(
        id="w1",
        resource=ObjectId(),
        variables={
            "pref1": WidgetVariables(users={str(creator): "abc"}),
            "prop1": WidgetVariables(users={str(creator): "12"}),
        },
        layouts={"0": WidgetLayout()},
    )
    ws.wiring_status = WorkspaceWiring()
    ws.wiring_status.operators = {
        "1": SimpleNamespace(
            name="acme/op/1.0.0",
            preferences={"op_pref": SimpleNamespace(value={"users": {str(creator): "ov"}})},
            properties={"op_prop": SimpleNamespace(value=WidgetVariables(users={str(creator): "9"}))},
        )
    }

    widget_info = SimpleNamespace(
        preferences=[MACDPreference(name="pref1", type="text", default="d", label="", description="", required=False, readonly=False)],
        properties=[MACDProperty(name="prop1", type="number", default="1", label="", description="")],
    )
    operator_info = SimpleNamespace(
        preferences=[MACDPreference(name="op_pref", type="text", default="d", label="", description="", required=False, readonly=False)],
        properties=[MACDProperty(name="op_prop", type="number", default="1", label="", description="")],
    )

    monkeypatch.setattr(utils, "get_widget_instances_from_workspace", lambda _workspace: [iwidget])
    monkeypatch.setattr(utils, "get_catalogue_resource_by_id", lambda *_args, **_kwargs: _widget_resource())
    monkeypatch.setattr(utils, "get_catalogue_resource", lambda *_args, **_kwargs: _operator_resource())
    monkeypatch.setattr(utils, "get_user_by_id", lambda *_args, **_kwargs: _user())

    async def _widget_resource():
        return SimpleNamespace(get_processed_info=lambda **_kwargs: widget_info)

    async def _operator_resource():
        return SimpleNamespace(get_processed_info=lambda **_kwargs: operator_info)

    async def _user():
        return SimpleNamespace(id=creator)

    saved = {"key": None}

    async def _cache_set(key, value):
        saved["key"] = key
        saved["value"] = value

    monkeypatch.setattr(utils.cache, "set", _cache_set)

    values = await utils._populate_variables_values_cache(
        db_session,
        ws,
        req,
        SimpleNamespace(id="u1"),
        "cache-key",
        forced_values=utils.WorkspaceForcedValues(),
    )
    assert "w1" in values["iwidget"]
    assert "1" in values["ioperator"]
    assert saved["key"] == "cache-key"

    iwidget.resource = None
    ws.wiring_status.operators = {"1": SimpleNamespace(name="acme/op/1.0.0", preferences={}, properties={})}
    monkeypatch.setattr(utils, "get_context_values", lambda *_args, **_kwargs: _ctx())
    monkeypatch.setattr(utils, "get_workspace_preference_values", lambda *_args, **_kwargs: _prefs())
    monkeypatch.setattr(utils, "get_catalogue_resource", lambda *_args, **_kwargs: _none())

    async def _ctx():
        return {}

    async def _prefs():
        return {}

    async def _none():
        return None

    values_none = await utils._populate_variables_values_cache(
        db_session,
        ws,
        req,
        SimpleNamespace(id="u1"),
        "cache-key-2",
        forced_values=None,
    )
    assert values_none["iwidget"]["w1"] == {}


async def test_get_global_workspace_data_paths(monkeypatch, db_session):
    ws = _workspace()
    ws.tabs = {"tab-0": Tab(id="tab-0", name="tab", title="Tab", widgets={})}
    ws.wiring_status = WorkspaceWiring()
    ws.wiring_status.operators = {
        "1": SimpleNamespace(name="invalid", preferences={}, properties={}),
        "2": SimpleNamespace(
            name="acme/op/1.0.0",
            preferences={"p2": SimpleNamespace(value={"users": {str(ws.creator): "secret"}})},
            properties={"k2": SimpleNamespace(value=WidgetVariables(users={str(ws.creator): "3"}))},
        ),
    }
    user = SimpleNamespace(id=ws.creator)
    req = _request()

    workspace_data = utils.WorkspaceData(
        id=str(ws.id),
        name=ws.name,
        title=ws.title,
        public=False,
        shared=False,
        requireauth=False,
        owner="alice",
        removable=True,
        lastmodified=ws.last_modified,
        description="",
        longdescription="",
    )

    monkeypatch.setattr(utils, "get_workspace_data", lambda *_args, **_kwargs: _workspace_data())
    monkeypatch.setattr(utils, "get_workspace_preference_values", lambda *_args, **_kwargs: _prefs())
    monkeypatch.setattr(utils, "get_context_values", lambda *_args, **_kwargs: _ctx())
    monkeypatch.setattr(utils, "get_tab_data", lambda *_args, **_kwargs: _tab_data())
    monkeypatch.setattr(utils, "get_group_by_id", lambda *_args, **_kwargs: _group())
    monkeypatch.setattr(utils, "get_user_with_all_info", lambda *_args, **_kwargs: _user())
    monkeypatch.setattr(utils, "decrypt_value", lambda _value: "x")

    async def _workspace_data():
        return workspace_data

    async def _prefs():
        return {"public": WorkspacePreference(value="false", inherit=False)}

    async def _ctx():
        return {}

    async def _tab_data():
        return TabData(id="tab-0", name="tab", title="Tab")

    async def _group():
        return SimpleNamespace(name="g", is_organization=False)

    async def _user():
        return SimpleNamespace(id=ws.creator, username="alice", get_full_name=lambda: "Alice")

    forced = utils.WorkspaceForcedValues(
        ioperator={"2": {"p2": WorkspaceForcedValue(value="forced"), "k2": WorkspaceForcedValue(value="forced")}},
        iwidget={},
        extra_prefs=[],
        empty_params=[],
    )
    monkeypatch.setattr(utils, "process_forced_values", lambda *_args, **_kwargs: forced)

    async def _catalogue(_db, vendor, name, version):
        if name == "op":
            info = SimpleNamespace(
                variables=SimpleNamespace(
                    preferences={"p2": SimpleNamespace(multiuser=False, default="d", secure=True, model_dump=lambda: {"type": "text"})},
                    properties={"k2": SimpleNamespace(multiuser=False, default="1", secure=True, model_dump=lambda: {"type": "number"})},
                )
            )
            return SimpleNamespace(get_processed_info=lambda **_kwargs: info, is_available_for=lambda _user: True)
        raise ValueError()

    monkeypatch.setattr(utils, "get_catalogue_resource", _catalogue)
    result = await utils._get_global_workspace_data(db_session, req, ws, user)
    assert result.id == str(ws.id)
    assert len(result.tabs) == 1
    assert result.wiring.operators["2"].preferences["p2"].value == "********"
    assert result.wiring.operators["2"].properties["k2"].value == "********"

    forced_empty = utils.WorkspaceForcedValues(ioperator={}, iwidget={}, extra_prefs=[], empty_params=["missing"])
    monkeypatch.setattr(utils, "process_forced_values", lambda *_args, **_kwargs: forced_empty)
    early = await utils._get_global_workspace_data(db_session, req, ws, user)
    assert early.empty_params == ["missing"]

    ws.tabs = {}
    ws.users = [SimpleNamespace(id=ws.creator)]
    ws.groups = [SimpleNamespace(id=ObjectId())]
    ws.wiring_status.operators = {
        "3": SimpleNamespace(
            name="acme/op/1.0.0",
            preferences={"p2": SimpleNamespace(value={"users": {str(ws.creator): "visible"}})},
            properties={"k2": SimpleNamespace(value=WidgetVariables(users={str(ws.creator): "7"}))},
        )
    }
    monkeypatch.setattr(utils, "process_forced_values", lambda *_args, **_kwargs: utils.WorkspaceForcedValues())

    async def _catalogue_visible(_db, _vendor, _name, _version):
        info = SimpleNamespace(
            variables=SimpleNamespace(
                preferences={"p2": SimpleNamespace(multiuser=True, default="d", secure=False, model_dump=lambda: {"type": "text"})},
                properties={"k2": SimpleNamespace(multiuser=True, default="1", secure=False, model_dump=lambda: {"type": "number"})},
            )
        )
        return SimpleNamespace(get_processed_info=lambda **_kwargs: info, is_available_for=lambda _user: True)

    monkeypatch.setattr(utils, "get_catalogue_resource", _catalogue_visible)
    tabs_created = {"n": 0}

    async def _create_tab(_db, _user, _title, workspace):
        tabs_created["n"] += 1
        tab = Tab(id="new-tab", name="new-tab", title="Tab", visible=True)
        workspace.tabs[tab.id] = tab
        return tab

    monkeypatch.setattr(utils, "create_tab", _create_tab)
    created_tab_data = await utils._get_global_workspace_data(db_session, req, ws, user)
    assert tabs_created["n"] == 1
    assert created_tab_data.wiring.operators["3"].preferences["p2"].value == "visible"
    assert created_tab_data.wiring.operators["3"].properties["k2"].value == "7"
    assert len(created_tab_data.groups) == 1

    async def _organization():
        return SimpleNamespace(name="Acme", is_organization=True)

    monkeypatch.setattr(utils, "get_group_by_id", lambda *_args, **_kwargs: _organization())
    organization_data = await utils._get_global_workspace_data(db_session, req, ws, user)
    assert organization_data.groups == []
    assert organization_data.users[-1].username == "Acme"
    assert organization_data.users[-1].organization is True

    async def _missing_related_object():
        return None

    monkeypatch.setattr(utils, "get_user_with_all_info", lambda *_args, **_kwargs: _missing_related_object())
    monkeypatch.setattr(utils, "get_group_by_id", lambda *_args, **_kwargs: _missing_related_object())
    missing_related_data = await utils._get_global_workspace_data(db_session, req, ws, user)
    assert missing_related_data.users == []
    assert missing_related_data.groups == []

    async def _catalogue_not_available(_db, _vendor, _name, _version):
        info = SimpleNamespace(
            variables=SimpleNamespace(
                preferences={"p2": SimpleNamespace(multiuser=True, default="d", secure=False, model_dump=lambda: {"type": "text"})},
                properties={"k2": SimpleNamespace(multiuser=True, default="1", secure=False, model_dump=lambda: {"type": "number"})},
            )
        )
        return SimpleNamespace(get_processed_info=lambda **_kwargs: info, is_available_for=lambda _user: False)

    monkeypatch.setattr(utils, "get_catalogue_resource", _catalogue_not_available)
    unavailable = await utils._get_global_workspace_data(db_session, req, ws, user)
    assert unavailable.wiring.operators["3"].preferences == {}
    assert unavailable.wiring.operators["3"].properties == {}

    ws.wiring_status.operators = {
        "4": SimpleNamespace(
            name="acme/op/1.0.0",
            preferences={"p2": SimpleNamespace(value={"users": {}})},
            properties={"k2": SimpleNamespace(value=WidgetVariables(users={}))},
        )
    }
    monkeypatch.setattr(utils, "get_catalogue_resource", _catalogue_visible)
    defaults = await utils._get_global_workspace_data(db_session, req, ws, user)
    assert defaults.wiring.operators["4"].preferences["p2"].value == "d"
    assert defaults.wiring.operators["4"].properties["k2"].value == 1.0

    non_owner = await utils._get_global_workspace_data(db_session, req, ws, SimpleNamespace(id=ObjectId()))
    assert non_owner.users == []
    assert non_owner.groups == []


async def test_get_global_workspace_data_cache_wrapper(monkeypatch, db_session):
    ws = _workspace()
    user = SimpleNamespace(id="u1")
    req = _request()
    payload = utils.CacheableData(
        data=utils.WorkspaceGlobalData(
            id=str(ws.id),
            name=ws.name,
            title=ws.title,
            public=False,
            shared=False,
            requireauth=False,
            owner="alice",
            removable=True,
            lastmodified=ws.last_modified,
            description="",
            longdescription="",
        ),
        timestamp=ws.last_modified,
    )

    async def _cache_get_none(_key):
        return None

    async def _cache_get_hit(_key):
        return payload

    async def _cache_set(*_args, **_kwargs):
        return None

    async def _global(*_args, **_kwargs):
        return payload.data

    monkeypatch.setattr(utils.cache, "get", _cache_get_none)
    monkeypatch.setattr(utils.cache, "set", _cache_set)
    monkeypatch.setattr(utils, "_get_global_workspace_data", _global)
    miss = await utils.get_global_workspace_data(db_session, req, ws, user)
    assert isinstance(miss, utils.CacheableData)

    monkeypatch.setattr(utils.cache, "get", _cache_get_hit)
    hit = await utils.get_global_workspace_data(db_session, req, ws, user)
    assert hit is payload
