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

import json
import re
from typing import Any, Union, Optional
from pydantic import BaseModel, Field

from wirecloud.commons.utils.template import docs


class Contact(BaseModel):
    name: str = Field(description=docs.contact_name_description)
    email: Optional[str] = Field(description=docs.contact_email_description, default=None)
    url: Optional[str] = Field(description=docs.contact_url_description, default=None)


__all__ = ('is_valid_name', 'is_valid_vendor', 'is_valid_version')

SEPARATOR_RE = re.compile(r'\s*,\s*')
NAME_RE = re.compile(r'^[^/]+$')
VENDOR_RE = re.compile(r'^[^/]+$')
VERSION_RE = re.compile(r'^(?:[1-9]\d*\.|0\.)*(?:[1-9]\d*|0)(?:(?:a|b|rc)[1-9]\d*)?(-dev.*)?$')
CONTACT_RE = re.compile(r'([^<(\s]+(?:\s+[^<()\s]+)*)(?:\s*<([^>]*)>)?(?:\s*\(([^)]*)\))?')


class TemplateParseException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return str(self.msg)


class TemplateFormatError(TemplateParseException):
    pass


class ObsoleteFormatError(TemplateFormatError):
    def __init__(self):
        super(ObsoleteFormatError, self).__init__('Component description uses a no longer supported format')


class UnsupportedFeature(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return str(self.msg)


def is_valid_name(name: str) -> bool:
    return bool(re.match(NAME_RE, name))


def is_valid_vendor(vendor: str) -> bool:
    return bool(re.match(VENDOR_RE, vendor))


def is_valid_version(version: str) -> bool:
    return bool(re.match(VERSION_RE, version))


def parse_contact_info(text: str) -> Contact:
    result = re.match(CONTACT_RE, text)
    if result is None:
        return Contact(name='')

    contact = Contact(name=result[1])

    if result[2] is not None:
        contact.email = result[2]

    if result[3] is not None:
        contact.url = result[3]

    return contact


def parse_contacts_info(info: Union[str, list[str], tuple[str, ...], list[dict]]) -> list[Contact]:
    contacts = []

    if isinstance(info, str):
        info = re.split(SEPARATOR_RE, info)

    for contact in info:
        if isinstance(contact, str):
            contact = parse_contact_info(contact)

        if isinstance(contact, dict):
            contact = Contact.model_validate(contact)

        if contact.name != '':
            contacts.append(contact)

    return contacts


def stringify_contact(contact: Contact) -> str:
    contact_string = contact.name

    if contact.email:
        contact_string += ' <' + contact.email + '>'

    if contact.url:
        contact_string += ' (' + contact.url + ')'

    return contact_string


def stringify_contact_info(contacts: list[Contact]) -> str:
    return ', '.join([stringify_contact(contact) for contact in contacts])


def convert_legacy_layout(top: float, left: float, width: float, height: float, relx: bool, rely: bool,
                          relwidth: bool, relheight: bool, minimized: bool = False, titlevisible: bool = True,
                          fulldragboard: bool = False) -> dict:
    """Convert a legacy widget position/rendering (old grid: 20 columns x 12 px rows) into the new
    GridStack-based layout format (new grid: 12 columns x 40 px rows), using a best-effort rule: cell-based
    (relative) coordinates are rescaled by the column/row ratio between grids; absolute (pixel-based)
    coordinates cannot be mapped to a specific column/row, so the position is left to auto-placement and the
    size is estimated assuming a 100px-wide column / a 40px-tall row."""

    if relx:
        x = round(left * 12 / 20)
    else:
        x = None

    if relwidth:
        w = max(1, round(width * 12 / 20))
    else:
        w = max(1, round(width / 100))

    if rely:
        y = round(top * 12 / 40)
    else:
        y = None

    if relheight:
        h = max(1, round(height * 12 / 40))
    else:
        h = max(1, round(height / 40))

    return {
        'x': x,
        'y': y,
        'w': w,
        'h': h,
        'minimized': bool(minimized),
        'titlevisible': bool(titlevisible),
        'fulldragboard': bool(fulldragboard),
        'visible': True,
    }


def default_desktop_screen_size_id() -> int:
    """Id of the platform's default 'desktop' screen size: the entry with the most columns in
    DEFAULT_SCREEN_SIZES (ties broken by the largest 'moreOrEqual') -- the same constant backing
    the 'screenSizes' workspace preference's defaultValue (WirecloudCorePlugin.get_workspace_
    preferences()). Legacy data converted from the old single-screen-size system targets a
    12-column grid, so it must be keyed to whichever screen size has the most columns rather
    than reusing the old (now meaningless) screen size id.

    Imports wirecloud.platform.core.plugins lazily to avoid a circular import (that module
    imports commons.utils.template modules), and reads the plain DEFAULT_SCREEN_SIZES constant
    rather than calling get_workspace_preferences() itself: that method builds translated
    PreferenceKey labels/descriptions via gettext, which requires an HTTP request context and
    would fail when this helper is called from CLI management commands or template parsing run
    outside a request (e.g. the 'migrate'/'convert_layouts' commands)."""
    from wirecloud.platform.core.plugins import DEFAULT_SCREEN_SIZES

    if not DEFAULT_SCREEN_SIZES:
        return 0

    best = max(DEFAULT_SCREEN_SIZES, key=lambda entry: (entry.get('columns', 1), entry.get('moreOrEqual', 0)))
    return best.get('id', 0)


def parse_screen_sizes_value(value: Any) -> Optional[list]:
    """Best-effort decode of a 'screenSizes' preference value (a JSON-encoded list, or already a
    list) into a list of dicts. Returns None when the value is missing/empty or cannot be
    interpreted as a non-empty list."""
    if not value:
        return None

    if isinstance(value, list):
        parsed = value
    else:
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return None

    if not isinstance(parsed, list) or len(parsed) == 0:
        return None

    return parsed


def is_legacy_default_screen_sizes(value: Any) -> bool:
    """A 'screenSizes' preference value is 'legacy default' when it is missing/unparseable, or
    when it describes a single interval covering the whole [0, +inf) range (regardless of its
    name/id) — i.e. the old system's single "Default" screen size. Such values must not be kept
    as-is: they should be dropped so the platform's new responsive defaults apply, and any
    layout that was converted assuming that single screen size must be remapped to the id of the
    new default desktop screen size (see default_desktop_screen_size_id)."""
    screen_sizes = parse_screen_sizes_value(value)
    if screen_sizes is None:
        return True

    if len(screen_sizes) != 1:
        return False

    entry = screen_sizes[0]
    if not isinstance(entry, dict):
        return False

    return entry.get('moreOrEqual') == 0 and entry.get('lessOrEqual') == -1


def resolve_legacy_screen_sizes(tab_preferences: dict, workspace_preferences: dict) -> bool:
    """For a mashup template tab: determine whether the effective 'screenSizes' preference (the
    tab's own value if present, else the workspace's, else none) is 'legacy default', dropping it
    from wherever it was found so the platform's new responsive defaults apply. Mutates
    tab_preferences/workspace_preferences in place. Returns True when legacy-default, meaning
    widget layouts converted for this tab from the legacy position/rendering format must be
    remapped to the id returned by default_desktop_screen_size_id()."""
    if 'screenSizes' in tab_preferences:
        legacy = is_legacy_default_screen_sizes(tab_preferences['screenSizes'])
        if legacy:
            del tab_preferences['screenSizes']
        return legacy

    if 'screenSizes' in workspace_preferences:
        legacy = is_legacy_default_screen_sizes(workspace_preferences['screenSizes'])
        if legacy:
            workspace_preferences.pop('screenSizes', None)
        return legacy

    return True
