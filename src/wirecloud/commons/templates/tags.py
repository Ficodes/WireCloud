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

import orjson
import os
from gettext import GNUTranslations
from typing import Optional
import gettext as gt
from importlib import import_module
from fastapi import Request
from fastapi.templating import Jinja2Templates
from urllib.parse import urlparse, parse_qs

from wirecloud.commons.utils.http import get_absolute_reverse_url
from wirecloud.commons.utils.theme import get_theme_translation
from wirecloud.platform.plugins import get_constants, get_wirecloud_ajax_endpoints
from wirecloud.translation import gettext as _trans
from wirecloud import settings

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), './templatefiles'))

def get_translation(theme: str, lang: str, text: str, **kwargs) -> str:
    theme_translation = get_theme_translation(theme, lang)

    translation = _trans(text, lang=lang, translation=theme_translation)
    for k, v in kwargs.items():
        translation = translation.replace(f"%({k})s", v)

    return translation

def get_static_path(theme: str, view: str, request: Request, path: str) -> str:
    # Get query from the path and add themeactive and view to it
    parsed_url = urlparse(path)
    query_dict = parse_qs(parsed_url.query)
    query_dict["themeactive"] = [theme]
    if "view" not in query_dict:
        query_dict["view"] = [view]

    root = request.scope.get("root_path", "").rstrip("/")
    return root + "/static/" + parsed_url.path + "?" + "&".join(
        [f"{k}={v[0]}" for k, v in query_dict.items()])

def get_url_from_view(request: Request, view: str, **kwargs) -> str:
    return get_absolute_reverse_url(view, request, **kwargs)

def get_wirecloud_bootstrap(context: dict, available_themes: list[dict[str, str]], view: Optional[str] = None, plain: bool = False) -> str:
    if view is None:
        view = context["VIEW_MODE"]

    def get_wirecloud_constants() -> list[dict[str, str]]:
        constants_def = get_constants()
        constants = []
        for constant in constants_def:
            constants.append({'key': constant['key'], 'value': constant['value']})
        constants.append({'key': 'CURRENT_LANGUAGE', 'value': '"' + str(context["request"].state.lang) + '"'})
        constants.append({'key': 'CURRENT_MODE', 'value': '"' + view + '"'})
        constants.append({'key': 'CURRENT_THEME', 'value': '"' + context["THEME"] + '"'})
        constants.append({'key': 'AVAILABLE_THEMES', 'value': orjson.dumps(available_themes).decode('utf-8')})

        return constants

    def get_wirecloud_bootstrap_script() -> str:
        endpoints = get_wirecloud_ajax_endpoints(view, context["request"])
        script = 'Wirecloud.URLs = {\n'
        for endpoint in endpoints:
            script += '    "' + endpoint.id + '": '
            if '%(' in endpoint.url:
                script += "new Wirecloud.Utils.Template('" + endpoint.url + "'),\n"
            else:
                script += "'" + endpoint.url + "',\n"

        script += '};\n'

        return script

    template_context = {
        'request': context['request'],
        'static': context['static'],
        'url': context['url'],
        'wirecloud_constants': get_wirecloud_constants(),
        'wirecloud_bootstrap_script': get_wirecloud_bootstrap_script(),
        'plain': plain,

        'LANGUAGE_CODE': context['LANGUAGE_CODE'],
        'WIRECLOUD_VERSION_HASH': context['WIRECLOUD_VERSION_HASH'],
        'THEME': context['THEME']
    }

    # Render directly to avoid Starlette TemplateResponse signature differences across versions
    return templates.get_template('bootstrap.html').render(template_context)

def get_javascript_catalogue(lang: str, theme: str) -> str:
    template_context = {
        'request': None
    }

    translations: list[GNUTranslations] = []
    try:
        theme_module = import_module(f"wirecloud.themes.{theme}")
    except ModuleNotFoundError:
        theme_module = None

    try:
        while theme_module is not None:
            if not os.path.exists(os.path.join(os.path.dirname(theme_module.__file__), 'locale', lang, 'LC_MESSAGES', f'{theme}.js.mo')):
                if theme_module.parent is None:
                    theme_module = None
                else:
                    theme_module = import_module(f"wirecloud.themes.{theme_module.parent}")
                continue

            translations.append(gt.translation(f'{theme}.js', os.path.join(os.path.dirname(theme_module.__file__), 'locale'), languages=[lang]))
            if theme_module.parent is None:
                theme_module = None
            else:
                theme_module = import_module(f"wirecloud.themes.{theme_module.parent}")
    except ModuleNotFoundError:
        pass

    # Now, get the translations from the plugins
    for plugin_name in settings.INSTALLED_APPS:
        src_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "../..")
        locale_path = os.path.join(src_path, plugin_name.replace(".", "/"), "locale")
        if not os.path.exists(locale_path) or not os.path.isdir(locale_path):
            continue

        try:
            translations.append(gt.translation(f"{plugin_name}.js", locale_path, languages=[lang]))
        except FileNotFoundError:
            pass

    # Now, we have all GNUTranslations objects in the translations list, in order of priority (if the same
    # string is translated in multiple places, the first one in the list has priority)
    translations_dict = {}

    for translation in translations:
        for key in translation._catalog.keys():
            if len(key) == 0:
                continue

            if type(key) == str:
                if key not in translations_dict:
                    translations_dict[key] = translation._catalog[key]
            else:
                # If the key is a tuple, it is a plural form
                if key[0] not in translations_dict:
                    translations_dict[key[0]] = [None, None]
                    translations_dict[key[0]][key[1]] = translation._catalog[key]
                elif translations_dict[key[0]][key[1]] is None:
                    translations_dict[key[0]][key[1]] = translation._catalog[key]

    if len(translations_dict) > 0:
        template_context['js_catalogue'] = f"catalog = {orjson.dumps(translations_dict).decode('utf-8')};"

    # Render directly to avoid Starlette TemplateResponse signature differences across versions
    return templates.get_template('js_catalogue.js').render(template_context)
