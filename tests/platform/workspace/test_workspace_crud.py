# -*- coding: utf-8 -*-

from types import SimpleNamespace

import pytest
from bson import ObjectId
from fastapi import Response

from wirecloud.platform.iwidget.models import WidgetInstance, WidgetLayout
from wirecloud.platform.workspace import crud
from wirecloud.platform.workspace.models import Workspace, WorkspaceAccessPermissions, Tab


def _workspace_model(name="workspace", creator=None):
    creator = creator or ObjectId()
    return Workspace(
        _id=ObjectId(),
        name=name,
        title=name.title(),
        creator=creator,
        tabs={},
        users=[WorkspaceAccessPermissions(id=creator, accesslevel=2)],
    )


async def test_workspace_crud_db_operations_and_lookup(db_session, monkeypatch):
    creator = ObjectId()
    group_id = ObjectId()
    user_id = ObjectId()
    public_ws = _workspace_model(name="public", creator=creator)
    public_ws.public = True
    public_ws.searchable = True
    private_ws = _workspace_model(name="private", creator=creator)
    private_ws.public = False
    private_ws.groups = [WorkspaceAccessPermissions(id=group_id, accesslevel=1)]
    private_ws.users = [WorkspaceAccessPermissions(id=user_id, accesslevel=1)]

    await crud.insert_workspace(db_session, public_ws)
    await crud.insert_workspace(db_session, private_ws)

    anon = await crud.get_workspace_list(db_session, None)
    assert {w.name for w in anon} == {"public"}

    admin_user = SimpleNamespace(id=user_id, has_perm=lambda perm: perm == "WORKSPACE.VIEW")
    all_visible = await crud.get_workspace_list(db_session, admin_user)
    assert {w.name for w in all_visible} == {"public", "private"}

    async def _groups(_db, _user):
        return [SimpleNamespace(id=group_id)]

    monkeypatch.setattr(crud, "get_all_user_groups", _groups)
    normal_user = SimpleNamespace(id=user_id, has_perm=lambda _perm: False)
    visible = await crud.get_workspace_list(db_session, normal_user)
    assert {w.name for w in visible} == {"public", "private"}

    found = await crud.get_workspace_by_id(db_session, public_ws.id)
    assert found is not None and found.name == "public"
    assert await crud.get_workspace_by_id(db_session, ObjectId()) is None

    all_workspaces = await crud.get_all_workspaces(db_session)
    assert len(all_workspaces) >= 2


async def test_create_empty_workspace_paths(monkeypatch):
    db = SimpleNamespace()
    user = SimpleNamespace(id=ObjectId())
    calls = {"tab": 0, "alt": 0, "insert": 0}
    monkeypatch.setattr(crud, "_", lambda text: text)

    async def _create_tab(_db, _user, _title, workspace):
        calls["tab"] += 1
        workspace.tabs["x-0"] = Tab(id="x-0", name="tab", title="Tab", visible=True)

    async def _save_alt(_db, _collection, _field, _workspace):
        calls["alt"] += 1

    async def _insert(_db, _workspace):
        calls["insert"] += 1

    monkeypatch.setattr(crud, "create_tab", _create_tab)
    monkeypatch.setattr(crud, "save_alternative", _save_alt)
    monkeypatch.setattr(crud, "insert_workspace", _insert)
    monkeypatch.setattr(crud, "is_a_workspace_with_that_name", lambda *_args, **_kwargs: _false())

    async def _false():
        return False

    created = await crud.create_empty_workspace(db, "My Workspace", user, allow_renaming=True, name="")
    assert created is not None
    assert calls["tab"] == 1
    assert calls["alt"] == 1

    calls["insert"] = 0
    created = await crud.create_empty_workspace(db, "My Workspace", user, allow_renaming=False, name="named")
    assert created is not None
    assert calls["insert"] == 1

    monkeypatch.setattr(crud, "is_a_workspace_with_that_name", lambda *_args, **_kwargs: _true())

    async def _true():
        return True

    conflict = await crud.create_empty_workspace(db, "My Workspace", user, allow_renaming=False, name="named")
    assert conflict is None


async def test_create_workspace_validation_and_dry_run(monkeypatch):
    db = SimpleNamespace()
    owner = SimpleNamespace(id=ObjectId())

    monkeypatch.setattr(crud, "_", lambda text: text)
    with pytest.raises(ValueError, match="Invalid mashup id"):
        await crud.create_workspace(db, None, owner, "invalid-id")

    async def _missing_resource(*_args, **_kwargs):
        return None

    monkeypatch.setattr(crud, "get_catalogue_resource", _missing_resource)
    with pytest.raises(ValueError, match="Mashup not found"):
        await crud.create_workspace(db, None, owner, "acme/mashup/1.0.0")

    class _TemplateParser:
        def __init__(self, _payload):
            self.payload = _payload

        def get_resource_processed_info(self, process_urls=False):
            return SimpleNamespace(name="template-name", title="Template Title")

    async def _build_json(*_args, **_kwargs):
        return SimpleNamespace(model_dump=lambda: {"k": "v"})

    async def _check_dependencies(*_args, **_kwargs):
        return None

    async def _build_workspace(*_args, **_kwargs):
        return _workspace_model()

    from wirecloud.platform.workspace import mashupTemplateGenerator as gen
    from wirecloud.platform.workspace import mashupTemplateParser as parser

    monkeypatch.setattr(gen, "build_json_template_from_workspace", _build_json)
    monkeypatch.setattr(parser, "check_mashup_dependencies", _check_dependencies)
    monkeypatch.setattr(parser, "build_workspace_from_template", _build_workspace)
    monkeypatch.setattr(crud, "TemplateParser", _TemplateParser)
    monkeypatch.setattr(crud, "is_a_workspace_with_that_name", lambda *_args, **_kwargs: _false())

    async def _false():
        return False

    source_workspace = _workspace_model(name="source")
    dry_run = await crud.create_workspace(
        db, None, owner, source_workspace, new_name="copy", dry_run=True
    )
    assert dry_run is not None
    assert dry_run.name == "copy"

    template_named = await crud.create_workspace(
        db, None, owner, source_workspace, dry_run=True
    )
    assert template_named.name == "template-name"
    assert template_named.title == "Template Title"

    title_named = await crud.create_workspace(
        db, None, owner, source_workspace, new_name="", new_title="My Copy", dry_run=True
    )
    assert title_named.name == "my-copy"
    assert title_named.title == "My Copy"

    explicitly_named = await crud.create_workspace(
        db, None, owner, source_workspace, new_name="copy-2", new_title="Copy 2", dry_run=True
    )
    assert explicitly_named.name == "copy-2"
    assert explicitly_named.title == "Copy 2"

    monkeypatch.setattr(crud, "is_a_workspace_with_that_name", lambda *_args, **_kwargs: _true())

    async def _true():
        return True

    conflict = await crud.create_workspace(
        db, None, owner, source_workspace, new_name="copy", dry_run=True
    )
    assert conflict is None


async def test_workspace_change_delete_and_tab_helpers(db_session, monkeypatch):
    creator = ObjectId()
    workspace = _workspace_model(name="ops", creator=creator)
    tab0 = Tab(id=f"{workspace.id}-0", name="tab0", title="Tab 0", visible=True)
    tab1 = Tab(id=f"{workspace.id}-1", name="tab1", title="Tab 1", visible=False)
    workspace.tabs = {tab0.id: tab0, tab1.id: tab1}
    await crud.insert_workspace(db_session, workspace)

    called = {"delete": [], "index": 0}

    async def _cache_delete(key):
        called["delete"].append(key)

    async def _update_index(_db, _workspace):
        called["index"] += 1

    monkeypatch.setattr(crud.cache, "delete", _cache_delete)
    monkeypatch.setattr(crud, "update_workspace_in_index", _update_index)
    await crud.change_workspace(db_session, workspace, SimpleNamespace(id=str(creator)))
    assert called["index"] == 1
    assert len(called["delete"]) == 2

    changed = {"n": 0}

    async def _change_workspace(_db, _workspace, _user):
        changed["n"] += 1

    monkeypatch.setattr(crud, "change_workspace", _change_workspace)
    await crud.change_tab(db_session, SimpleNamespace(id=str(creator)), workspace, tab1, save_workspace=True)
    assert changed["n"] == 1

    saved_tabs = []

    async def _change_tab(_db, _user, _workspace, tab, save_workspace=True):
        saved_tabs.append((tab.id, tab.visible, save_workspace))

    monkeypatch.setattr(crud, "change_tab", _change_tab)
    await crud.set_visible_tab(db_session, SimpleNamespace(id=str(creator)), workspace, tab1)
    assert any(tab_id == tab1.id and visible for tab_id, visible, _ in saved_tabs)

    async def _delete_index(_workspace):
        changed["n"] += 1

    monkeypatch.setattr(crud, "delete_workspace_from_index", _delete_index)
    await crud.delete_workspace(db_session, workspace)
    assert changed["n"] >= 2


async def test_workspace_description_and_user_lookup(db_session, monkeypatch):
    creator = ObjectId()
    workspace = _workspace_model(name="desc", creator=creator)
    widget = WidgetInstance(
        id="w1",
        title="Weather",
        layouts={"0": WidgetLayout()},
    )
    workspace.tabs = {f"{workspace.id}-0": Tab(id=f"{workspace.id}-0", name="t0", title="T0", widgets={"w1": widget})}
    await crud.insert_workspace(db_session, workspace)

    description = await crud.get_workspace_description(db_session, workspace)
    assert "Weather" in description

    async def _user_by_username(_db, username):
        if username == "alice":
            return SimpleNamespace(id=creator)
        return None

    monkeypatch.setattr(crud, "get_user_by_username", _user_by_username)
    found = await crud.get_workspace_by_username_and_name(db_session, "alice", "desc")
    assert found is not None and found.name == "desc"
    assert await crud.get_workspace_by_username_and_name(db_session, "missing", "desc") is None


async def test_clear_and_add_workspace_access_and_create_workspace_wgt_paths(db_session, monkeypatch):
    monkeypatch.setattr(crud, "_", lambda text: text)
    workspace = _workspace_model(name="access")
    await crud.insert_workspace(db_session, workspace)

    await crud.clear_workspace_users(db_session, workspace)
    await crud.clear_workspace_groups(db_session, workspace)
    await crud.add_user_to_workspace(db_session, workspace, SimpleNamespace(id=ObjectId()))
    await crud.add_group_to_workspace(db_session, workspace, SimpleNamespace(id=ObjectId()))
    raw = await db_session.client.workspaces.find_one({"_id": ObjectId(workspace.id)})
    assert isinstance(raw["users"], list)
    assert isinstance(raw["groups"], list)

    owner = SimpleNamespace(id=ObjectId())

    class _WgtFile:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_template(self):
            return {"k": "v"}

        def read(self, _path):
            return b"bin"

    class _TemplateNonMashup:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_resource_processed_info(self, process_urls=False):
            return SimpleNamespace(type="widget", embedded=[])

    monkeypatch.setattr(crud, "WgtFile", _WgtFile)
    monkeypatch.setattr(crud, "TemplateParser", _TemplateNonMashup)
    with pytest.raises(ValueError, match="not a mashup"):
        await crud.create_workspace(db_session, None, owner, _WgtFile("dummy.wgt"))

    class _TemplateMashup:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_resource_processed_info(self, process_urls=False):
            return SimpleNamespace(
                type=crud.MACType.mashup,
                embedded=[SimpleNamespace(src="https://example.org/a.wgt"), SimpleNamespace(src="b.wgt")],
            )

    called = {"install": 0}

    monkeypatch.setattr(crud, "TemplateParser", _TemplateMashup)
    async def _download(*_args, **_kwargs):
        return b"data"

    monkeypatch.setattr(crud, "download_http_content", _download)

    async def _install(*_args, **_kwargs):
        called["install"] += 1

    async def _deps(*_args, **_kwargs):
        return None

    async def _build(*_args, **_kwargs):
        return _workspace_model(name="built")

    monkeypatch.setattr(crud, "install_component", _install)
    from wirecloud.platform.workspace import mashupTemplateParser as parser
    monkeypatch.setattr(parser, "check_mashup_dependencies", _deps)
    monkeypatch.setattr(parser, "build_workspace_from_template", _build)
    built = await crud.create_workspace(db_session, None, owner, _WgtFile("dummy.wgt"))
    assert built is not None
    assert called["install"] == 2


async def test_create_workspace_mashup_string_and_misc_helpers(db_session, monkeypatch):
    monkeypatch.setattr(crud, "_", lambda text: text)
    owner = SimpleNamespace(id=ObjectId())

    class _Template:
        def __init__(self, *_args, **_kwargs):
            pass


async def test_update_all_workspaces_with_widgets(monkeypatch):
    user = SimpleNamespace(id=ObjectId())
    w1 = SimpleNamespace(widget_uri="acme/weather/1.0", resource=ObjectId())
    w2 = SimpleNamespace(widget_uri="acme/weather/2.0", resource=ObjectId())
    w3 = SimpleNamespace(widget_uri="other/component/1.0", resource=ObjectId())
    ws1 = SimpleNamespace(
        tabs={"t": SimpleNamespace(widgets={"a": w1, "b": w2})},
        is_editable_by=lambda _db, _user: _true(),
    )
    ws2 = SimpleNamespace(
        tabs={"t": SimpleNamespace(widgets={"c": w3})},
        is_editable_by=lambda _db, _user: _true(),
    )
    ws3 = SimpleNamespace(
        tabs={"t": SimpleNamespace(widgets={"d": SimpleNamespace(widget_uri="acme/weather/1.5", resource=ObjectId())})},
        is_editable_by=lambda _db, _user: _false(),
    )

    async def _true():
        return True

    async def _false():
        return False

    changed = {"n": 0}

    async def _change_workspace(_db, _workspace, _user):
        changed["n"] += 1

    monkeypatch.setattr(crud, "get_all_workspaces", lambda _db: _workspaces([ws1, ws2, ws3]))
    monkeypatch.setattr(crud, "change_workspace", _change_workspace)

    async def _workspaces(items):
        return items

    result = await crud.update_all_workspaces_with_widgets(SimpleNamespace(), user, "acme", "weather", "3.0", ObjectId())
    assert result.total_resources_updated == 2
    assert result.total_workspaces_updated == 1
    assert changed["n"] == 1
    assert w1.widget_uri == "acme/weather/3.0"
    assert w2.widget_uri == "acme/weather/3.0"


async def test_update_all_workspaces_with_operators_and_resource(db_session, monkeypatch):
    monkeypatch.setattr(crud, "_", lambda text: text)
    user = SimpleNamespace(id=ObjectId())
    request = SimpleNamespace()
    owner = SimpleNamespace(id=ObjectId())

    class _Template:
        def __init__(self, *_args, **_kwargs):
            pass

    op = SimpleNamespace(name="acme/op/1.0")
    wiring = SimpleNamespace(operators={"1": op})
    ws = SimpleNamespace(
        wiring_status=wiring,
        is_editable_by=lambda _db, _user: _true(),
    )
    ws_no_change = SimpleNamespace(
        wiring_status=SimpleNamespace(operators={"2": SimpleNamespace(name="other/op/1.0")}),
        is_editable_by=lambda _db, _user: _true(),
    )
    ws_not_editable = SimpleNamespace(
        wiring_status=SimpleNamespace(operators={"3": SimpleNamespace(name="acme/op/1.1")}),
        is_editable_by=lambda _db, _user: _false(),
    )

    async def _true():
        return True

    async def _false():
        return False

    async def _workspaces(_db):
        return [ws, ws_no_change, ws_not_editable]

    changed = {"n": 0}

    async def _change_workspace(_db, _workspace, _user):
        changed["n"] += 1

    async def _check_wiring(*_args, **_kwargs):
        return True

    monkeypatch.setattr(crud, "get_all_workspaces", _workspaces)
    monkeypatch.setattr(crud, "change_workspace", _change_workspace)
    monkeypatch.setattr(crud, "check_wiring", _check_wiring)

    result = await crud.update_all_workspaces_with_operators(SimpleNamespace(), user, request, "acme", "op", "2.0")
    assert result.total_resources_updated == 1
    assert result.total_workspaces_updated == 1
    assert changed["n"] == 1
    assert ws.wiring_status.operators["1"].name == "acme/op/2.0"

    async def _check_wiring_response(*_args, **_kwargs):
        return Response(status_code=422)

    monkeypatch.setattr(crud, "check_wiring", _check_wiring_response)
    result2 = await crud.update_all_workspaces_with_operators(SimpleNamespace(), user, request, "acme", "op", "3.0")
    assert isinstance(result2, Response)
    assert result2.status_code == 422

    async def _widgets(*_args, **_kwargs):
        return "widgets-updated"

    async def _operators(*_args, **_kwargs):
        return "operators-updated"

    monkeypatch.setattr(crud, "update_all_workspaces_with_widgets", _widgets)
    monkeypatch.setattr(crud, "update_all_workspaces_with_operators", _operators)

    widget_resource = SimpleNamespace(
        vendor="acme",
        short_name="w",
        version="1.0",
        id=ObjectId(),
        type=crud.CatalogueResourceType.widget,
    )
    operator_resource = SimpleNamespace(
        vendor="acme",
        short_name="o",
        version="1.0",
        id=ObjectId(),
        type=crud.CatalogueResourceType.operator,
    )
    invalid_resource = SimpleNamespace(
        vendor="acme",
        short_name="x",
        version="1.0",
        id=ObjectId(),
        type="other",
    )

    assert await crud.update_all_workspaces_with_resources(SimpleNamespace(), user, request, widget_resource) == "widgets-updated"
    assert await crud.update_all_workspaces_with_resources(SimpleNamespace(), user, request, operator_resource) == "operators-updated"
    with pytest.raises(ValueError, match="not supported"):
        await crud.update_all_workspaces_with_resources(SimpleNamespace(), user, request, invalid_resource)

    async def _resource(*_args, **_kwargs):
        return SimpleNamespace(
            is_available_for=lambda _user: True,
            resource_type=lambda: "mashup",
            template_uri="m.wgt",
        )

    async def _deps(*_args, **_kwargs):
        return None

    async def _build(*_args, **_kwargs):
        return _workspace_model(name="w-built")

    updates = {"n": 0}

    async def _update_prefs(*_args, **_kwargs):
        updates["n"] += 1

    monkeypatch.setattr(crud, "get_catalogue_resource", _resource)
    monkeypatch.setattr(crud.catalogue.wgt_deployer, "get_base_dir", lambda *_args, **_kwargs: "/tmp")
    monkeypatch.setattr(crud, "WgtFile", lambda *_args, **_kwargs: SimpleNamespace(get_template=lambda: {}))
    monkeypatch.setattr(crud, "TemplateParser", _Template)
    from wirecloud.platform.workspace import mashupTemplateParser as parser
    monkeypatch.setattr(parser, "check_mashup_dependencies", _deps)
    monkeypatch.setattr(parser, "build_workspace_from_template", _build)
    monkeypatch.setattr("wirecloud.platform.preferences.crud.update_workspace_preferences", _update_prefs)

    created = await crud.create_workspace(
        db_session,
        None,
        owner,
        "acme/mashup/1.0.0",
        preferences={"p": "v"},
    )
    assert created is not None
    assert updates["n"] == 1

    async def _build_none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(parser, "build_workspace_from_template", _build_none)
    none_workspace = await crud.create_workspace(
        db_session,
        None,
        owner,
        "acme/mashup/1.0.0",
    )
    assert none_workspace is None

    creator = ObjectId()
    ws = _workspace_model(name="lookup", creator=creator)
    await crud.insert_workspace(db_session, ws)
    assert await crud.is_a_workspace_with_that_name(db_session, "lookup", creator) is True
    assert await crud.is_a_workspace_with_that_name(db_session, "missing", creator) is False

    async def _user_by_username(_db, _username):
        return SimpleNamespace(id=creator)

    monkeypatch.setattr(crud, "get_user_by_username", _user_by_username)
    assert await crud.get_workspace_by_username_and_name(db_session, "alice", "missing") is None

    changed = {"n": 0}

    async def _change_workspace(*_args, **_kwargs):
        changed["n"] += 1

    monkeypatch.setattr(crud, "change_workspace", _change_workspace)
    await crud.change_tab(db_session, SimpleNamespace(id=str(creator)), ws, Tab(id="t-1", name="t1", title="T1"), save_workspace=False)
    assert changed["n"] == 0
