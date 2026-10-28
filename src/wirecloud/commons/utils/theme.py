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

import os
import inspect
from importlib import import_module
import gettext as gt
from fastapi.templating import Jinja2Templates
from jinja2.loaders import FileSystemLoader
from jinja2 import Environment

from wirecloud.settings import AVAILABLE_THEMES, LANGUAGES
from wirecloud import themes
from wirecloud.commons.utils.http import NotFound
from wirecloud.platform.plugins import get_plugins

DIST_PATH = os.path.join(os.path.dirname(__file__), "../../dist")
JINJA2_TEMPLATES = {}
THEME_TRANSLATIONS = {}

def _generate_jinja2_templates() -> None:
    for theme in AVAILABLE_THEMES:
        try:
            theme_module = import_module(f"wirecloud.themes.{theme}")
        except ModuleNotFoundError:
            continue

        paths = []

        while theme_module is not None:
            if not hasattr(theme_module, "parent"):
                raise ValueError(f"Invalid theme: {theme}: parent not found. If you didn't intend to use a parent theme, set parent to None")

            theme_path = os.path.join(os.path.dirname(theme_module.__file__), 'templates')

            if theme_module.parent is not None:
                try:
                    theme_module = import_module(f"wirecloud.themes.{theme_module.parent}")
                except ModuleNotFoundError:
                    theme_module = None
            else:
                theme_module = None

            if not os.path.exists(theme_path) or not os.path.isdir(theme_path):
                continue

            paths.append(theme_path)

        JINJA2_TEMPLATES[theme] = Jinja2Templates(env=Environment(loader=FileSystemLoader(paths)))

def _generate_theme_translations() -> None:
    for theme in AVAILABLE_THEMES:
        try:
            theme_module = import_module(f"wirecloud.themes.{theme}")
        except ModuleNotFoundError:
            continue

        if not theme in THEME_TRANSLATIONS:
            THEME_TRANSLATIONS[theme] = {}

        for lang, _ in LANGUAGES:
            translation = None

            while theme_module is not None:
                if not hasattr(theme_module, "parent"):
                    raise ValueError(f"Invalid theme: {theme}: parent not found. If you didn't intend to use a parent theme, set parent to None")

                locale_path = os.path.join(os.path.dirname(theme_module.__file__), 'locale')
                if translation is None:
                    translation = gt.translation(theme, locale_path, languages=[lang], fallback=True)
                else:
                    translation.add_fallback(gt.translation(theme, locale_path, languages=[lang], fallback=True))

                if theme_module.parent is not None:
                    try:
                        theme_module = import_module(f"wirecloud.themes.{theme_module.parent}")
                    except ModuleNotFoundError:
                        theme_module = None
                else:
                    theme_module = None

            if translation is None:
                translation = gt.NullTranslations()

            THEME_TRANSLATIONS[theme][lang] = translation

def get_jinja2_templates(theme: str) -> Jinja2Templates:
    if theme not in JINJA2_TEMPLATES:
        raise NotFound("Theme not found")

    return JINJA2_TEMPLATES[theme]

def get_theme_translation(theme: str, lang: str) -> gt.NullTranslations:
    if theme not in THEME_TRANSLATIONS:
        raise NotFound("Theme not found")

    if lang not in THEME_TRANSLATIONS[theme]:
        raise NotFound("Language not found")

    return THEME_TRANSLATIONS[theme][lang]

def get_available_themes(lang: str) -> list[dict[str, str]]:
    result = []
    for theme in AVAILABLE_THEMES:
        # Find the translations for the theme
        try:
            theme_module = import_module(f"wirecloud.themes.{theme}")
        except ModuleNotFoundError:
            continue

        if not hasattr(theme_module, "label"):
            raise ValueError(f"Invalid theme: {theme}: label not found")

        # Get the locale path of the theme
        locale_path = os.path.join(os.path.dirname(theme_module.__file__), 'locale')
        try:
            translation = gt.translation(theme, locale_path, languages=[lang])
        except:
            translation = gt.NullTranslations()

        result.append({
            "value": theme,
            "label": theme_module.label(lang, translation) if type(theme_module.label) != str else theme_module.label
        })

    return result

def get_theme_config(theme: str) -> dict:
    """
    Returns the optional client configuration declared by a theme module (its
    ``config`` attribute), e.g. ``{"color_schemes": ["light", "dark"]}``. Themes
    inherit their parent's configuration, child keys taking precedence.
    """
    chain = []
    try:
        theme_module = import_module(f"wirecloud.themes.{theme}")
    except ModuleNotFoundError:
        raise NotFound(f"Theme not found: {theme}")

    while theme_module is not None:
        chain.append(theme_module)

        parent = getattr(theme_module, "parent", None)
        if parent is None:
            theme_module = None
        else:
            try:
                theme_module = import_module(f"wirecloud.themes.{parent}")
            except ModuleNotFoundError:
                theme_module = None

    config = {}
    for theme_module in reversed(chain):
        module_config = getattr(theme_module, "config", None)
        if module_config is None:
            continue
        if not isinstance(module_config, dict):
            raise ValueError(f"Invalid theme: {theme}: config must be a dict")
        config.update(module_config)

    return config

def get_theme_static_path(theme: str, path: str) -> str:
    from wirecloud.platform.core.plugins import WirecloudCorePlugin

    if theme not in AVAILABLE_THEMES:
        raise NotFound("Theme not found")

    if path.startswith("/"):
        path = path[1:]

    if '..' in path:
        raise ValueError("Path traversal attack attempted!")

    # First, look in the dist directory for the specified file
    dist_path = os.path.join(DIST_PATH, path)
    if os.path.exists(dist_path):
        return dist_path

    themes_path = os.path.dirname(themes.__file__)

    if not os.path.exists(os.path.join(themes_path, theme)):
        raise NotFound("Theme not found")

    try:
        theme_module = import_module(f"wirecloud.themes.{theme}")
    except ModuleNotFoundError:
        raise NotFound(f"Theme not found: {theme}")
    if not hasattr(theme_module, "parent"):
        raise ValueError(f"Invalid theme: {theme}: parent not found. If you didn't intend to use a parent theme, set parent to None")

    found_path = None
    while theme_module is not None:
        static_path = os.path.join(os.path.dirname(theme_module.__file__), 'static')
        if os.path.exists(static_path) and os.path.exists(os.path.join(static_path, path)):
            found_path = os.path.join(static_path, path)
            break

        # Root themes (parent = None) end the chain, even when they have no static directory
        if theme_module.parent is None:
            theme_module = None
        else:
            try:
                theme_module = import_module(f"wirecloud.themes.{theme_module.parent}")
            except ModuleNotFoundError:
                theme_module = None

    if found_path is None:
        # If a static path could not be found in any theme, search in plugin static directories
        plugins = get_plugins()
        for plugin in plugins:
            # Get the file the class "plugin" is defined in
            plugins_file = inspect.getfile(plugin.__class__)
            # Get the parent directory of the file
            plugin_dir = os.path.dirname(plugins_file)

            if isinstance(plugin, WirecloudCorePlugin):
                plugin_dir = os.path.dirname(plugin_dir)

            static_path = os.path.join(plugin_dir, "static", path)
            if os.path.exists(static_path):
                found_path = static_path
                break

    if found_path is None:
        raise NotFound(f"Static file not found: {path}")

    return found_path

_generate_jinja2_templates()
_generate_theme_translations()