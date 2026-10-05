# -*- coding: utf-8 -*-

from datetime import datetime, timezone
from types import SimpleNamespace
import json

import pytest
from bson import ObjectId

from wirecloud.platform.workspace import docs, models, schemas


def test_workspace_model_lazily_migrates_legacy_widget_layouts():
    raw_workspace = {
        "_id": ObjectId(),
        "name": "legacy",
        "title": "Legacy",
        "creator": ObjectId(),
        "preferences": [
            {"name": "baselayout", "value": "{}", "inherit": False},
            {"name": "screenSizes", "value": json.dumps([
                {"id": 0, "moreOrEqual": 0, "lessOrEqual": -1}
            ]), "inherit": False},
        ],
        "tabs": {
            "tab-0": {
                "id": "tab-0",
                "name": "main",
                "title": "Main",
                "widgets": {
                    "tab-0-0": {
                        "id": "tab-0-0",
                        "layout": 5,
                        "positions": {"configurations": [{
                            "id": 0,
                            "widget": {
                                "top": 10, "left": 5, "width": 10, "height": 20,
                                "relx": True, "rely": True,
                                "relwidth": True, "relheight": True,
                            },
                        }]},
                    },
                    "tab-0-1": {
                        "id": "tab-0-1",
                        "layout": 4,
                        "layouts": {"2": {"x": 3, "w": 2, "h": 2}},
                    },
                },
            },
        },
    }

    workspace = models.Workspace.model_validate(raw_workspace)
    tab = workspace.tabs["tab-0"]
    widget = tab.widgets["tab-0-0"]

    # The old all-width screen size maps to the new desktop entry (id 2), while the old top
    # sidebar index becomes a retracted overlay dock instead of silently becoming a grid item.
    assert set(widget.layouts) == {"2"}
    assert widget.layouts["2"].dock == "top"
    assert widget.layouts["2"].dock_mode == "overlay"
    assert widget.layouts["2"].dock_open is False
    mixed_widget = tab.widgets["tab-0-1"].layouts["2"]
    assert mixed_widget.x == 3
    assert mixed_widget.y is None
    assert mixed_widget.dock == "bottom"
    assert {preference.name for preference in workspace.preferences} == set()

    dumped_widget = workspace.model_dump()["tabs"]["tab-0"]["widgets"]["tab-0-0"]
    assert "positions" not in dumped_widget
    assert "layout" not in dumped_widget


def test_workspace_model_preserves_modern_single_screen_size():
    screen_sizes = [{
        "id": 9, "name": "All", "moreOrEqual": 0, "lessOrEqual": -1,
        "columns": 8, "rows": 6,
    }]
    workspace = models.Workspace.model_validate({
        "_id": ObjectId(),
        "name": "modern",
        "title": "Modern",
        "creator": ObjectId(),
        "preferences": [{
            "name": "screenSizes", "value": json.dumps(screen_sizes), "inherit": False,
        }],
        "tabs": {"tab-0": {
            "id": "tab-0", "name": "main", "title": "Main",
            "widgets": {"tab-0-0": {
                "id": "tab-0-0", "layout": 0,
                "positions": {"configurations": [{
                    "id": 9,
                    "widget": {"top": 0, "left": 0, "width": 4, "height": 4},
                }]},
            }},
        }},
    })

    assert len(workspace.preferences) == 1
    assert json.loads(workspace.preferences[0].value) == screen_sizes
    assert set(workspace.tabs["tab-0"].widgets["tab-0-0"].layouts) == {"9"}


def test_workspace_docs_constants_present():
    assert isinstance(docs.get_workspace_collection_summary, str)
    assert isinstance(docs.create_workspace_collection_workspace_example, list)
    assert isinstance(docs.workspace_data, dict)
    assert isinstance(docs.tab_data, dict)


def test_workspace_schema_serializers_and_validators(monkeypatch):
    monkeypatch.setattr(schemas, "_", lambda text: text)

    now = datetime(2026, 3, 12, tzinfo=timezone.utc)
    tab_data = schemas.TabData(id="w-0", name="tab", title="Tab", last_modified=now)
    assert tab_data.model_dump()["last_modified"] == int(now.timestamp() * 1000)
    assert tab_data.serialize_last_modified(now, None) == int(now.timestamp() * 1000)

    workspace_data = schemas.WorkspaceData(
        id="wid",
        name="w",
        title="W",
        public=False,
        shared=False,
        requireauth=False,
        owner="alice",
        removable=True,
        lastmodified=now,
        description="d",
        longdescription="ld",
    )
    assert workspace_data.model_dump()["lastmodified"] == int(now.timestamp() * 1000)
    assert workspace_data.serialize_lastmodified(now, None) == int(now.timestamp() * 1000)

    with pytest.raises(ValueError, match="Missing name or title parameter"):
        schemas.WorkspaceCreate()

    with pytest.raises(ValueError, match="cannot be used at the same time"):
        schemas.WorkspaceCreate(name="x", title="", workspace="1", mashup="m/v/1.0.0")

    valid = schemas.WorkspaceCreate(name="x", title="", workspace="", mashup="")
    assert valid.name == "x"


async def test_workspace_model_access_and_editability(monkeypatch):
    user_id = ObjectId()
    creator_id = ObjectId()
    group_id = ObjectId()
    workspace = models.Workspace(
        _id=ObjectId(),
        name="w",
        title="W",
        creator=creator_id,
        users=[models.WorkspaceAccessPermissions(id=user_id, accesslevel=1)],
        groups=[models.WorkspaceAccessPermissions(id=group_id, accesslevel=1)],
    )

    async def _groups(_db, _user):
        return [SimpleNamespace(id=group_id)]

    monkeypatch.setattr(models, "get_all_user_groups", _groups)

    anonymous_access = await workspace.is_accessible_by(None, None)
    assert anonymous_access is False

    workspace.public = True
    workspace.requireauth = False
    assert await workspace.is_accessible_by(None, None) is True

    view_user = SimpleNamespace(id=ObjectId(), has_perm=lambda perm: perm == "WORKSPACE.VIEW", is_superuser=False)
    assert await workspace.is_accessible_by(None, view_user) is True

    workspace.public = False
    workspace.requireauth = True
    owner_user = SimpleNamespace(id=creator_id, has_perm=lambda _perm: False, is_superuser=False)
    assert await workspace.is_accessible_by(None, owner_user) is True

    listed_user = SimpleNamespace(id=user_id, has_perm=lambda _perm: False, is_superuser=False)
    assert await workspace.is_accessible_by(None, listed_user) is True

    workspace.users = []
    grouped_user = SimpleNamespace(id=ObjectId(), has_perm=lambda _perm: False, is_superuser=False)
    assert await workspace.is_accessible_by(None, grouped_user) is True

    workspace.groups = []
    workspace.public = False
    assert await workspace.is_accessible_by(None, grouped_user) is False

    workspace.users = [models.WorkspaceAccessPermissions(id=ObjectId(), accesslevel=2)]
    superuser = SimpleNamespace(id=ObjectId(), has_perm=lambda _perm: False, is_superuser=True)
    assert await workspace.is_editable_by(None, superuser) is True
    assert await workspace.is_editable_by(None, owner_user) is True

    direct_editor = SimpleNamespace(id=workspace.users[0].id, has_perm=lambda _perm: False, is_superuser=False)
    assert await workspace.is_editable_by(None, direct_editor) is True

    workspace.users = [models.WorkspaceAccessPermissions(id=direct_editor.id, accesslevel=1)]
    fallback_editor = SimpleNamespace(
        id=direct_editor.id,
        has_perm=lambda perm: perm == "WORKSPACE.EDIT",
        is_superuser=False,
    )
    workspace.public = True
    workspace.requireauth = False
    assert await workspace.is_editable_by(None, fallback_editor) is True

    workspace.users = []
    workspace.groups = [models.WorkspaceAccessPermissions(id=group_id, accesslevel=2)]
    assert await workspace.is_editable_by(None, grouped_user) is True

    workspace.groups = [models.WorkspaceAccessPermissions(id=group_id, accesslevel=1)]
    assert await workspace.is_editable_by(None, grouped_user) is False

    workspace.groups = []
    workspace.public = True
    workspace.requireauth = False
    perm_editor = SimpleNamespace(
        id=ObjectId(),
        has_perm=lambda perm: perm == "WORKSPACE.EDIT",
        is_superuser=False,
    )
    assert await workspace.is_editable_by(None, perm_editor) is True

    workspace.public = False
    assert workspace.is_shared() is False
    workspace.public = True
    assert workspace.is_shared() is True
