"""Legacy preference conversion handles malformed and partially migrated data."""

import copy
import json

import pytest

from wirecloud.commons.utils.template import base
from wirecloud.platform.workspace import layout_migration as migration


@pytest.mark.parametrize("value", [None, "", "not json", "{}", "[]", [], 1])
def test_invalid_screen_sizes_use_defaults(value):
    assert base.parse_screen_sizes_value(value) is None
    assert base.is_legacy_default_screen_sizes(value) is True


@pytest.mark.parametrize("value", [[None], [{"moreOrEqual": 0}, {"moreOrEqual": 100}], [{"moreOrEqual": 100}]])
def test_custom_or_malformed_entries_are_not_the_old_default(value):
    assert base.is_legacy_default_screen_sizes(value) is False


def test_empty_desktop_definitions_fall_back_to_screen_zero(monkeypatch):
    from wirecloud.platform.core import plugins

    monkeypatch.setattr(plugins, "DEFAULT_SCREEN_SIZES", [])
    assert base.default_desktop_screen_size_id() == 0


def test_invalid_legacy_layout_mode_does_not_enable_docking():
    result = base.convert_legacy_layout(0, 0, 20, 40, True, True, True, False, layout="invalid")
    assert result["w"] == 12
    assert result["h"] == 1
    assert "dock" not in result


@pytest.mark.parametrize("tab, workspace, expected_tab, expected_workspace, legacy", [
    ({"screenSizes": "invalid"}, {"screenSizes": "keep"}, {}, {"screenSizes": "keep"}, True),
    ({"screenSizes": [{"moreOrEqual": 100}]}, {}, {"screenSizes": [{"moreOrEqual": 100}]}, {}, False),
    ({}, {"screenSizes": [{"moreOrEqual": 0, "lessOrEqual": -1}]}, {}, {}, True),
    ({}, {"screenSizes": [{"moreOrEqual": 100}]}, {}, {"screenSizes": [{"moreOrEqual": 100}]}, False),
    ({}, {}, {}, {}, True),
])
def test_template_screen_size_precedence(tab, workspace, expected_tab, expected_workspace, legacy):
    assert base.resolve_legacy_screen_sizes(tab, workspace) is legacy
    assert tab == expected_tab
    assert workspace == expected_workspace


@pytest.mark.parametrize("value", [None, "invalid", "{}", [], [{"columns": 6}], [None]])
def test_screen_size_migration_preserves_values_without_legacy_columns(value):
    assert migration.migrate_screensizes_value(value) == value


@pytest.mark.parametrize("encoded", [False, True])
def test_custom_screen_sizes_gain_columns_without_mutating_input(encoded):
    original = [{"id": 7, "moreOrEqual": 700}, {"id": 8, "columns": 4}, None]
    value = json.dumps(original) if encoded else copy.deepcopy(original)
    result = migration.migrate_screensizes_value(value)
    assert (json.loads(result) if encoded else result) == [
        {"id": 7, "moreOrEqual": 700, "columns": 12}, {"id": 8, "columns": 4}, None,
    ]
    assert value == (json.dumps(original) if encoded else original)


def test_preference_migration_removes_obsolete_layout_and_updates_custom_sizes():
    original = [None, {"name": "baselayout", "value": "free"}, {"name": "initiallayout", "value": "0"},
        {"name": "screenSizes", "value": [{"id": 1, "moreOrEqual": 600}]}]
    rows, changed = migration.convert_legacy_preferences(original)
    assert changed is True
    assert rows == [None, {"name": "screenSizes", "value": [{"id": 1, "moreOrEqual": 600, "columns": 12}]}]
    assert "columns" not in original[-1]["value"][0]


@pytest.mark.parametrize("inherit", [True, "yes", "on", "1"])
def test_inherited_tab_screen_sizes_use_the_workspace(inherit):
    tab = [{"name": "screenSizes", "inherit": inherit, "value": [{"id": 1, "columns": 4}]}]
    workspace = [{"name": "screenSizes", "value": [{"id": 0, "moreOrEqual": 0, "lessOrEqual": -1}]}]
    assert migration.tab_uses_legacy_default_screen_sizes(tab, workspace) is True


def test_partial_workspace_migration_preserves_unknown_entries_and_uses_grid_for_invalid_layout():
    original = {"tabs": {"unknown": None, "tab": {"widgets": {"widget": {"layout": "invalid", "positions": {
        "configurations": [{"id": 0, "widget": {"top": 40, "left": 1, "width": 3, "height": 80}}],
    }}}}}}
    saved = copy.deepcopy(original)
    result = migration.migrate_workspace_document(original)
    assert original == saved
    assert result["tabs"]["unknown"] is None
    widget = result["tabs"]["tab"]["widgets"]["widget"]
    assert "positions" not in widget and "layout" not in widget
    layout = widget["layouts"][str(base.default_desktop_screen_size_id())]
    assert {key: layout[key] for key in ("x", "y", "w", "h")} == {"x": 1, "y": None, "w": 2, "h": 2}


def test_non_document_workspace_is_preserved():
    assert migration.migrate_workspace_document(None) is None
