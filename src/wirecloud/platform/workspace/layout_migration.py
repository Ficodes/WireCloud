# -*- coding: utf-8 -*-
# Copyright (c) 2026 Future Internet Consulting and Development Solutions S.L.

# This file is part of Wirecloud.

# Wirecloud is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Wirecloud is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with Wirecloud.  If not, see <http://www.gnu.org/licenses/>.

"""Compatibility helpers for the pre-GridStack workspace layout format."""

import json
from typing import Any

from wirecloud.commons.utils.template.base import convert_legacy_layout, default_desktop_screen_size_id, \
    is_legacy_default_screen_sizes, parse_screen_sizes_value


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _is_pre_gridstack_default_screen_sizes(value: Any) -> bool:
    screen_sizes = parse_screen_sizes_value(value)
    return screen_sizes is not None and any(
        isinstance(screen_size, dict) and 'columns' not in screen_size
        for screen_size in screen_sizes
    ) and is_legacy_default_screen_sizes(value)


def migrate_screensizes_value(value: Any) -> Any:
    """Add the GridStack column count to old custom screen-size entries."""
    try:
        screen_sizes = value if isinstance(value, list) else json.loads(value)
    except (TypeError, ValueError):
        return value

    if not isinstance(screen_sizes, list):
        return value

    screen_sizes = [dict(entry) if isinstance(entry, dict) else entry for entry in screen_sizes]
    changed = False
    for screen_size in screen_sizes:
        if isinstance(screen_size, dict) and 'columns' not in screen_size:
            screen_size['columns'] = 12
            changed = True

    if not changed:
        return value
    return screen_sizes if isinstance(value, list) else json.dumps(screen_sizes)


def convert_legacy_preferences(rows: list[dict]) -> tuple[list[dict], bool]:
    """Remove obsolete layout preferences and update custom screen sizes."""
    changed = False
    result = []
    for preference in rows:
        if not isinstance(preference, dict):
            result.append(preference)
            continue
        name = preference.get('name')
        if name in ('baselayout', 'initiallayout'):
            changed = True
            continue

        if name == 'screenSizes':
            if _is_pre_gridstack_default_screen_sizes(preference.get('value')):
                changed = True
                continue

            new_value = migrate_screensizes_value(preference.get('value') or "")
            if new_value != preference.get('value'):
                preference = {**preference, 'value': new_value}
                changed = True

        result.append(preference)

    return result, changed


def tab_uses_legacy_default_screen_sizes(tab_preferences: list, workspace_preferences: list) -> bool:
    """Return whether a tab used the old single all-width screen-size definition."""
    tab_preference = next((p for p in tab_preferences
                           if isinstance(p, dict) and p.get('name') == 'screenSizes'), None)
    if tab_preference is not None and not _as_bool(tab_preference.get('inherit', False)):
        return _is_pre_gridstack_default_screen_sizes(tab_preference.get('value'))

    workspace_preference = next(
        (p for p in workspace_preferences
         if isinstance(p, dict) and p.get('name') == 'screenSizes'), None
    )
    if workspace_preference is not None:
        return _is_pre_gridstack_default_screen_sizes(workspace_preference.get('value'))

    return True


def migrate_widget_positions_to_layouts(positions: dict, legacy_default_screen_sizes: bool,
                                        legacy_layout: int = 0) -> dict[str, dict]:
    """Convert legacy position configurations into per-screen-size GridStack layouts."""
    layouts = {}
    desktop_key = str(default_desktop_screen_size_id()) if legacy_default_screen_sizes else None
    for configuration in positions.get('configurations', []):
        widget = configuration.get('widget', {}) or {}
        key = desktop_key if legacy_default_screen_sizes else str(configuration.get('id', 0))
        layouts[key] = convert_legacy_layout(
            top=float(widget.get('top', 0) or 0),
            left=float(widget.get('left', 0) or 0),
            width=float(widget.get('width', 10) or 10),
            height=float(widget.get('height', 10) or 10),
            relx=bool(widget.get('relx', True)),
            rely=bool(widget.get('rely', False)),
            relwidth=bool(widget.get('relwidth', True)),
            relheight=bool(widget.get('relheight', False)),
            minimized=bool(widget.get('minimized', False)),
            titlevisible=bool(widget.get('titlevisible', True)),
            fulldragboard=bool(widget.get('fulldragboard', False)),
            layout=legacy_layout,
        )

    return layouts


def merge_existing_layouts(converted: dict[str, dict], existing: dict, legacy_layout: int) -> dict[str, dict]:
    """Prefer already-new fields while retaining legacy-only layout semantics such as docking."""
    result = converted
    legacy_metadata = convert_legacy_layout(
        top=0, left=0, width=1, height=1,
        relx=True, rely=True, relwidth=True, relheight=True,
        layout=legacy_layout,
    )
    legacy_metadata = {
        key: legacy_metadata[key]
        for key in ('dock', 'dock_mode', 'dock_open')
        if key in legacy_metadata
    }
    for screen_size, current_layout in existing.items():
        key = str(screen_size)
        merged = dict(legacy_metadata)
        merged.update(result.get(key, {}))
        merged.update(current_layout.model_dump() if hasattr(current_layout, 'model_dump') else current_layout)
        result[key] = merged
    return result


def migrate_workspace_document(data: Any) -> Any:
    """Lazily normalize a raw Mongo workspace before Pydantic discards legacy fields.

    This does not write to MongoDB by itself. Any subsequent normal workspace write persists the
    normalized representation, while read-only requests still receive a correct layout.
    """
    if not isinstance(data, dict):
        return data

    workspace = dict(data)
    original_workspace_preferences = workspace.get('preferences') or []
    workspace_preferences, workspace_preferences_changed = convert_legacy_preferences(
        original_workspace_preferences
    )
    if workspace_preferences_changed:
        workspace['preferences'] = workspace_preferences

    tabs = workspace.get('tabs') or {}
    migrated_tabs = dict(tabs)
    tabs_changed = False
    for tab_id, raw_tab in tabs.items():
        if not isinstance(raw_tab, dict):
            continue

        original_tab_preferences = raw_tab.get('preferences') or []
        tab_preferences, tab_preferences_changed = convert_legacy_preferences(original_tab_preferences)
        legacy_default = tab_uses_legacy_default_screen_sizes(
            original_tab_preferences, original_workspace_preferences
        )

        tab = dict(raw_tab)
        if tab_preferences_changed:
            tab['preferences'] = tab_preferences

        widgets = raw_tab.get('widgets') or {}
        migrated_widgets = dict(widgets)
        widgets_changed = False
        for widget_id, raw_widget in widgets.items():
            if not isinstance(raw_widget, dict) or (
                    'positions' not in raw_widget and 'layout' not in raw_widget):
                continue

            try:
                legacy_layout = int(raw_widget.get('layout', 0) or 0)
            except (TypeError, ValueError):
                legacy_layout = 0

            layouts = migrate_widget_positions_to_layouts(
                raw_widget.get('positions') or {}, legacy_default, legacy_layout
            )
            layouts = merge_existing_layouts(layouts, raw_widget.get('layouts') or {}, legacy_layout)

            widget = dict(raw_widget)
            widget['layouts'] = layouts
            widget.pop('positions', None)
            widget.pop('layout', None)
            migrated_widgets[widget_id] = widget
            widgets_changed = True

        if widgets_changed:
            tab['widgets'] = migrated_widgets
        if tab_preferences_changed or widgets_changed:
            migrated_tabs[tab_id] = tab
            tabs_changed = True

    if tabs_changed:
        workspace['tabs'] = migrated_tabs
    return workspace
