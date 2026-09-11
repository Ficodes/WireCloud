# -*- coding: utf-8 -*-

from types import SimpleNamespace

import pytest

from wirecloud import main as main_module
from wirecloud.main import app
from wirecloud.commons.auth.utils import get_user_csrf, get_user_no_csrf
from wirecloud.platform.iwidget import routes
from wirecloud.platform.iwidget.models import WidgetPermissions
from wirecloud.platform.iwidget.schemas import WidgetInstanceData


async def _noop_close():
    return None


main_module.close = _noop_close


@pytest.fixture(autouse=True)
def _patch_gettext(monkeypatch):
    monkeypatch.setattr(routes, "_", lambda text: text)


@pytest.fixture()
def auth_state():
    user = SimpleNamespace(
        id="507f1f77bcf86cd799439011",
        username="alice",
        is_superuser=False,
        has_perm=lambda _perm: False,
    )
    return {"user": user}


@pytest.fixture(autouse=True)
def _override_auth(auth_state):
    async def _dep():
        return auth_state["user"]

    app.dependency_overrides[get_user_no_csrf] = _dep
    app.dependency_overrides[get_user_csrf] = _dep
    yield
    app.dependency_overrides.pop(get_user_no_csrf, None)
    app.dependency_overrides.pop(get_user_csrf, None)


def _widget_data(widget_id="ws-0-0"):
    return WidgetInstanceData(
        id=widget_id,
        title="Widget",
        widget="acme/widget/1.0.0",
        layouts={"0": {"w": 1, "h": 1}},
        read_only=False,
        permissions=WidgetPermissions(),
        variable_values=None,
        preferences={},
        properties={},
    )


def _iwidget(widget_id="ws-0-0", resource="rid", read_only=False):
    calls = {"set": []}

    async def _set_variable_value(_db, name, value, _user):
        calls["set"].append((name, value))

    item = SimpleNamespace(
        id=widget_id,
        resource=resource,
        read_only=read_only,
        permissions=WidgetPermissions(),
        set_variable_value=_set_variable_value,
        calls=calls,
    )
    return item


def _workspace(tab_id="tab-0", widgets=None, accessible=True, editable=True):
    ws = SimpleNamespace(
        id="507f1f77bcf86cd799439012",
        tabs={tab_id: SimpleNamespace(id=tab_id, widgets=widgets or {})},
    )

    async def _is_accessible_by(_db, _user):
        return accessible

    async def _is_editable_by(_db, _user):
        return editable

    ws.is_accessible_by = _is_accessible_by
    ws.is_editable_by = _is_editable_by
    return ws


async def test_get_widget_instance_collection_route(app_client, db_session, monkeypatch):
    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(routes, "get_workspace_by_id", _none)
    missing_ws = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/")
    assert missing_ws.status_code == 404

    ws = _workspace()
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))

    async def _value(v):
        return v

    ws.tabs = {}
    missing_tab = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/")
    assert missing_tab.status_code == 404

    ws = _workspace(widgets={"a": _iwidget("a")}, accessible=False, editable=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "is_owner_or_has_permission", lambda *_args, **_kwargs: True)
    forbidden = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/")
    assert forbidden.status_code == 403

    ws = _workspace(widgets={"a": _iwidget("a"), "b": _iwidget("b")}, accessible=True, editable=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "is_owner_or_has_permission", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(routes, "VariableValueCacheManager", lambda *_args, **_kwargs: SimpleNamespace())

    async def _widget_instance_data(*_args, **_kwargs):
        return _widget_data("a")

    monkeypatch.setattr(routes, "get_widget_instance_data", _widget_instance_data)
    ok = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/")
    assert ok.status_code == 200
    assert len(ok.json()) == 2


async def test_create_widget_instance_collection_route(app_client, db_session, monkeypatch):
    payload = {"title": "Widget", "widget": "acme/widget/1.0.0", "layouts": {"0": {"w": 1, "h": 1}}, "permissions": {}, "variable_values": {}}

    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(routes, "get_workspace_by_id", _none)
    missing_ws = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/", json=payload)
    assert missing_ws.status_code == 404

    ws = _workspace()
    ws.tabs = {}
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))

    async def _value(v):
        return v

    missing_tab = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/", json=payload)
    assert missing_tab.status_code == 404

    ws = _workspace(editable=False)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "is_owner_or_has_permission", lambda *_args, **_kwargs: True)
    forbidden = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/", json=payload)
    assert forbidden.status_code == 403

    ws = _workspace(editable=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "is_owner_or_has_permission", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(routes, "save_widget_instance", lambda *_args, **_kwargs: _raise_notfound())

    async def _raise_notfound():
        raise routes.NotFound()

    notfound = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/", json=payload)
    assert notfound.status_code == 422

    monkeypatch.setattr(routes, "save_widget_instance", lambda *_args, **_kwargs: _raise_type())

    async def _raise_type():
        raise TypeError("bad")

    bad = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/", json=payload)
    assert bad.status_code == 400

    monkeypatch.setattr(routes, "save_widget_instance", lambda *_args, **_kwargs: _raise_value())

    async def _raise_value():
        raise ValueError("bad")

    invalid = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/", json=payload)
    assert invalid.status_code == 422

    async def _saved(*_args, **_kwargs):
        return _iwidget("ok")

    monkeypatch.setattr(routes, "save_widget_instance", _saved)

    async def _widget_instance_data(*_args, **_kwargs):
        return _widget_data("ok")

    monkeypatch.setattr(routes, "get_widget_instance_data", _widget_instance_data)
    created = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/", json=payload)
    assert created.status_code == 201
    assert created.json()["id"] == "ok"


async def test_create_widget_instance_invalid_layout_key_returns_422(app_client, db_session, monkeypatch):
    ws = _workspace(editable=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "is_owner_or_has_permission", lambda *_args, **_kwargs: True)

    async def _value(v):
        return v

    payload = {"title": "Widget", "widget": "acme/widget/1.0.0", "layouts": {"not-a-number": {"w": 1, "h": 1}}}
    response = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/", json=payload)
    assert response.status_code == 422


async def test_update_widget_instance_collection_route(app_client, db_session, monkeypatch):
    payload = [{"id": "w1"}]

    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(routes, "get_workspace_by_id", _none)
    missing_ws = await app_client.put("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/", json=payload)
    assert missing_ws.status_code == 404

    ws = _workspace()
    ws.tabs = {}
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))

    async def _value(v):
        return v

    missing_tab = await app_client.put("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/", json=payload)
    assert missing_tab.status_code == 404

    ws = _workspace(editable=False)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "is_owner_or_has_permission", lambda *_args, **_kwargs: True)
    forbidden = await app_client.put("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/", json=payload)
    assert forbidden.status_code == 403

    ws = _workspace(editable=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "is_owner_or_has_permission", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(routes, "update_widget_instance", lambda *_args, **_kwargs: _response())

    async def _response():
        return routes.Response(status_code=409)

    early = await app_client.put("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/", json=payload)
    assert early.status_code == 409

    monkeypatch.setattr(routes, "update_widget_instance", lambda *_args, **_kwargs: _raise_type())

    async def _raise_type():
        raise TypeError("bad")

    type_err = await app_client.put("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/", json=payload)
    assert type_err.status_code == 400

    monkeypatch.setattr(routes, "update_widget_instance", lambda *_args, **_kwargs: _raise_value())

    async def _raise_value():
        raise ValueError("bad")

    value_err = await app_client.put("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/", json=payload)
    assert value_err.status_code == 422

    called = {"n": 0}

    async def _change_workspace(*_args, **_kwargs):
        called["n"] += 1

    monkeypatch.setattr(routes, "update_widget_instance", lambda *_args, **_kwargs: _none())
    monkeypatch.setattr(routes, "change_workspace", _change_workspace)
    ok = await app_client.put("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/", json=payload)
    assert ok.status_code == 204
    assert called["n"] == 1

    called["n"] = 0
    empty = await app_client.put("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/", json=[])
    assert empty.status_code == 204
    assert called["n"] == 0


async def test_widget_instance_entry_routes(app_client, db_session, monkeypatch):
    iwidget = _iwidget("w1")

    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(routes, "get_workspace_by_id", _none)
    missing_ws = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1")
    assert missing_ws.status_code == 404

    ws = _workspace(widgets={"w1": iwidget}, accessible=False)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))

    async def _value(v):
        return v

    monkeypatch.setattr(routes, "is_owner_or_has_permission", lambda *_args, **_kwargs: True)
    forbidden = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1")
    assert forbidden.status_code == 403

    ws = _workspace(widgets={"w1": iwidget}, accessible=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    ws.tabs = {}
    missing_tab = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1")
    assert missing_tab.status_code == 404

    ws = _workspace(widgets={}, accessible=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    missing_iwidget = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1")
    assert missing_iwidget.status_code == 404

    ws = _workspace(widgets={"w1": iwidget}, accessible=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    async def _widget_instance_data(*_args, **_kwargs):
        return _widget_data("w1")

    monkeypatch.setattr(routes, "get_widget_instance_data", _widget_instance_data)
    ok = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1")
    assert ok.status_code == 200
    assert ok.json()["id"] == "w1"

    payload = {"id": "w1"}
    monkeypatch.setattr(routes, "get_workspace_by_id", _none)
    post_missing_ws = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1", json=payload)
    assert post_missing_ws.status_code == 404

    ws = _workspace(widgets={"w1": iwidget}, editable=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    ws.tabs = {}
    post_missing_tab = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1", json=payload)
    assert post_missing_tab.status_code == 404

    ws = _workspace(widgets={"w1": iwidget}, editable=False)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "is_owner_or_has_permission", lambda *_args, **_kwargs: True)
    post_forbidden = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1", json=payload)
    assert post_forbidden.status_code == 403

    ws = _workspace(widgets={"w1": iwidget}, editable=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "is_owner_or_has_permission", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(routes, "update_widget_instance", lambda *_args, **_kwargs: _response())

    async def _response():
        return routes.Response(status_code=409)

    post_early = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1", json=payload)
    assert post_early.status_code == 409

    monkeypatch.setattr(routes, "update_widget_instance", lambda *_args, **_kwargs: _raise_type())

    async def _raise_type():
        raise TypeError("bad")

    post_type = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1", json=payload)
    assert post_type.status_code == 400

    monkeypatch.setattr(routes, "update_widget_instance", lambda *_args, **_kwargs: _raise_value())

    async def _raise_value():
        raise ValueError("bad")

    post_value = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1", json=payload)
    assert post_value.status_code == 422

    monkeypatch.setattr(routes, "update_widget_instance", lambda *_args, **_kwargs: _none())
    post_ok = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1", json=payload)
    assert post_ok.status_code == 204


async def test_delete_widget_instance_entry_route(app_client, db_session, monkeypatch):
    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(routes, "get_workspace_by_id", _none)
    missing_ws = await app_client.delete("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1")
    assert missing_ws.status_code == 404

    ws = _workspace(widgets={"w1": _iwidget("w1")})
    ws.tabs = {}

    async def _value(v):
        return v

    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    missing_tab = await app_client.delete("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1")
    assert missing_tab.status_code == 404

    ws = _workspace(widgets={})
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    missing_iwidget = await app_client.delete("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1")
    assert missing_iwidget.status_code == 404

    ws = _workspace(widgets={"w1": _iwidget("w1")}, editable=False)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "is_owner_or_has_permission", lambda *_args, **_kwargs: True)
    forbidden = await app_client.delete("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1")
    assert forbidden.status_code == 403

    ws = _workspace(widgets={"w1": _iwidget("w1", read_only=True)}, editable=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "is_owner_or_has_permission", lambda *_args, **_kwargs: True)
    readonly = await app_client.delete("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1")
    assert readonly.status_code == 403

    called = {"n": 0}

    async def _change_workspace(*_args, **_kwargs):
        called["n"] += 1

    ws = _workspace(widgets={"w1": _iwidget("w1", read_only=False)}, editable=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "is_owner_or_has_permission", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(routes, "change_workspace", _change_workspace)
    ok = await app_client.delete("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1")
    assert ok.status_code == 204
    assert called["n"] == 1


async def test_widget_preferences_and_properties_routes(app_client, db_session, monkeypatch):
    iwidget = _iwidget("w1", resource="rid")

    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(routes, "get_workspace_by_id", _none)
    missing_ws = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/preferences", json={"p1": "v"})
    assert missing_ws.status_code == 404

    ws = _workspace(widgets={"w1": iwidget}, accessible=True, editable=True)
    ws.tabs = {}

    async def _value(v):
        return v

    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    missing_tab = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/preferences", json={"p1": "v"})
    assert missing_tab.status_code == 404

    ws = _workspace(widgets={}, accessible=True, editable=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    missing_iwidget = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/preferences", json={"p1": "v"})
    assert missing_iwidget.status_code == 404

    ws = _workspace(widgets={"w1": iwidget}, accessible=True, editable=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "get_catalogue_resource_by_id", _none)
    missing_resource = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/preferences", json={"p1": "v"})
    assert missing_resource.status_code == 404

    pref_info = SimpleNamespace(
        variables=SimpleNamespace(
            preferences={
                "p_ro": SimpleNamespace(readonly=True, multiuser=False),
                "p_mu": SimpleNamespace(readonly=False, multiuser=True),
                "p_single": SimpleNamespace(readonly=False, multiuser=False),
            },
            properties={
                "prop_mu": SimpleNamespace(multiuser=True),
                "prop_single": SimpleNamespace(multiuser=False),
            },
        )
    )
    resource = SimpleNamespace(get_processed_info=lambda **_kwargs: pref_info)
    monkeypatch.setattr(routes, "get_catalogue_resource_by_id", lambda *_args, **_kwargs: _value(resource))

    invalid_pref = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/preferences", json={"missing": "v"})
    assert invalid_pref.status_code == 422

    readonly_pref = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/preferences", json={"p_ro": "v"})
    assert readonly_pref.status_code == 403

    monkeypatch.setattr(routes, "is_owner_or_has_permission", lambda *_args, **_kwargs: False)
    ws = _workspace(widgets={"w1": iwidget}, accessible=False, editable=False)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    forbidden_pref_mu = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/preferences", json={"p_mu": "v"})
    assert forbidden_pref_mu.status_code == 403

    ws = _workspace(widgets={"w1": iwidget}, accessible=True, editable=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "is_owner_or_has_permission", lambda *_args, **_kwargs: True)
    called = {"n": 0}

    async def _change_workspace(*_args, **_kwargs):
        called["n"] += 1

    monkeypatch.setattr(routes, "change_workspace", _change_workspace)
    ok_pref = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/preferences", json={"p_single": "v"})
    assert ok_pref.status_code == 204
    assert called["n"] == 1
    assert iwidget.calls["set"] == [("p_single", "v")]

    monkeypatch.setattr(routes, "get_workspace_by_id", _none)
    get_missing_ws = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/preferences")
    assert get_missing_ws.status_code == 404

    ws = _workspace(widgets={"w1": iwidget}, accessible=True)
    ws.tabs = {}
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    get_missing_tab = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/preferences")
    assert get_missing_tab.status_code == 404

    ws = _workspace(widgets={}, accessible=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    get_missing_iwidget = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/preferences")
    assert get_missing_iwidget.status_code == 404

    ws = _workspace(widgets={"w1": _iwidget("w1", resource=None)}, accessible=False)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    get_forbidden = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/preferences")
    assert get_forbidden.status_code == 403

    ws = _workspace(widgets={"w1": _iwidget("w1", resource=None)}, accessible=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    get_empty = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/preferences")
    assert get_empty.status_code == 200
    assert get_empty.json() == {}

    ws = _workspace(widgets={"w1": _iwidget("w1", resource="rid")}, accessible=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "get_catalogue_resource_by_id", _none)
    get_missing_resource = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/preferences")
    assert get_missing_resource.status_code == 404

    cache_manager = SimpleNamespace(get_variable_data=lambda *_args, **_kwargs: _val())

    async def _val():
        return {"value": "x"}

    monkeypatch.setattr(routes, "get_catalogue_resource_by_id", lambda *_args, **_kwargs: _value(resource))
    monkeypatch.setattr(routes, "VariableValueCacheManager", lambda *_args, **_kwargs: cache_manager)
    get_ok = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/preferences")
    assert get_ok.status_code == 200
    assert "p_ro" in get_ok.json()

    monkeypatch.setattr(routes, "get_workspace_by_id", _none)
    prop_missing_ws = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/properties", json={"prop_mu": 1})
    assert prop_missing_ws.status_code == 404

    ws = _workspace(widgets={"w1": iwidget}, accessible=True, editable=True)
    ws.tabs = {}
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    prop_missing_tab = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/properties", json={"prop_mu": 1})
    assert prop_missing_tab.status_code == 404

    ws = _workspace(widgets={}, accessible=True, editable=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    prop_missing_iwidget = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/properties", json={"prop_mu": 1})
    assert prop_missing_iwidget.status_code == 404

    ws = _workspace(widgets={"w1": iwidget}, accessible=True, editable=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "get_catalogue_resource_by_id", _none)
    prop_missing_resource = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/properties", json={"prop_mu": 1})
    assert prop_missing_resource.status_code == 404

    monkeypatch.setattr(routes, "get_catalogue_resource_by_id", lambda *_args, **_kwargs: _value(resource))
    invalid_prop = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/properties", json={"missing": 1})
    assert invalid_prop.status_code == 422

    ws = _workspace(widgets={"w1": iwidget}, accessible=False, editable=False)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "is_owner_or_has_permission", lambda *_args, **_kwargs: False)
    forbidden_prop = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/properties", json={"prop_mu": 1})
    assert forbidden_prop.status_code == 403

    ws = _workspace(widgets={"w1": iwidget}, accessible=True, editable=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "is_owner_or_has_permission", lambda *_args, **_kwargs: True)
    called["n"] = 0
    prop_ok = await app_client.post("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/properties", json={"prop_single": 2})
    assert prop_ok.status_code == 204
    assert called["n"] == 1

    monkeypatch.setattr(routes, "get_workspace_by_id", _none)
    get_prop_missing_ws = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/properties")
    assert get_prop_missing_ws.status_code == 404

    ws = _workspace(widgets={"w1": _iwidget("w1", resource="rid")}, accessible=False)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    get_prop_forbidden = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/properties")
    assert get_prop_forbidden.status_code == 403

    ws = _workspace(widgets={"w1": _iwidget("w1", resource="rid")}, accessible=True)
    ws.tabs = {}
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    get_prop_missing_tab = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/properties")
    assert get_prop_missing_tab.status_code == 404

    ws = _workspace(widgets={}, accessible=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    get_prop_missing_iwidget = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/properties")
    assert get_prop_missing_iwidget.status_code == 404

    ws = _workspace(widgets={"w1": _iwidget("w1", resource=None)}, accessible=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    get_prop_empty = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/properties")
    assert get_prop_empty.status_code == 200
    assert get_prop_empty.json() == {}

    ws = _workspace(widgets={"w1": _iwidget("w1", resource="rid")}, accessible=True)
    monkeypatch.setattr(routes, "get_workspace_by_id", lambda *_args, **_kwargs: _value(ws))
    monkeypatch.setattr(routes, "get_catalogue_resource_by_id", _none)
    get_prop_missing_resource = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/properties")
    assert get_prop_missing_resource.status_code == 404

    monkeypatch.setattr(routes, "get_catalogue_resource_by_id", lambda *_args, **_kwargs: _value(resource))
    monkeypatch.setattr(routes, "VariableValueCacheManager", lambda *_args, **_kwargs: cache_manager)
    get_prop_ok = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/tab/tab-0/widget_instances/w1/properties")
    assert get_prop_ok.status_code == 200
    assert "prop_mu" in get_prop_ok.json()
