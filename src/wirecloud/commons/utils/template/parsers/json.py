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

import orjson as json

from pydantic import ValidationError
from typing import Union
from wirecloud.commons.utils.template.schemas.macdschemas import MACD, MACDWidget, MACDOperator, MACDMashup, MACDTranslationIndexUsage, MACType, Name, Vendor, Version
from wirecloud.commons.utils.template.base import TemplateParseException
from wirecloud.commons.utils.translation import get_trans_index
from wirecloud.translation import gettext as _


class JSONTemplateParser(object):
    _info: MACD

    def __init__(self, template: Union[str, bytes, dict]):
        info: dict
        if isinstance(template, str) or isinstance(template, bytes):
            info = json.loads(template)
        elif isinstance(template, dict):
            info = template
        else:
            raise ValueError(_('Invalid input data'))

        if 'type' not in info:
            raise ValueError(_('Missing component type.'))

        if info['type'] not in ('widget', 'operator', 'mashup'):
            raise ValueError(_('Invalid component type: %s') % info['type'])

        try:
            if info['type'] == 'widget':
                self._info = MACDWidget.model_validate(info)
            elif info['type'] == 'operator':
                self._info = MACDOperator.model_validate(info)
            elif info['type'] == 'mashup':
                self._info = MACDMashup.model_validate(info)
        except ValidationError as e:
            raise TemplateParseException(str(e))

    def _add_translation_index(self, value: str, **kwargs) -> None:
        index = get_trans_index(str(value))
        if not index:
            return

        if index not in self._info.translation_index_usage:
            self._info.translation_index_usage[index] = []

        self._info.translation_index_usage[index].append(MACDTranslationIndexUsage(**kwargs))

    def _init(self) -> None:
        self._info.translation_index_usage = {}

        self._add_translation_index(self._info.title, type='resource', field='title')
        self._add_translation_index(self._info.description, type='resource', field='description')

        if not isinstance(self._info, MACDMashup):
            for preference in self._info.preferences:
                self._add_translation_index(preference.label, type='vdef', variable=preference.name, field='label')
                self._add_translation_index(preference.description, type='vdef', variable=preference.name, field='description')

                if preference.type == 'list':
                    for option_index, option in enumerate(preference.options):
                        self._add_translation_index(option.label, type='upo', variable=preference.name, option=option_index)

            for prop in self._info.properties:
                self._add_translation_index(prop.label, type='vdef', variable=prop.name, field='label')
                self._add_translation_index(prop.description, type='vdef', variable=prop.name, field='description')

            for input_endpoint in self._info.wiring.inputs:
                self._add_translation_index(input_endpoint.label, type='inputendpoint', variable=input_endpoint.name, field='label')
                self._add_translation_index(input_endpoint.description, type='inputendpoint', variable=input_endpoint.name, field='description')
                self._add_translation_index(input_endpoint.actionlabel, type='inputendpoint', variable=input_endpoint.name, field='actionlabel')

            for output_endpoint in self._info.wiring.outputs:
                self._add_translation_index(output_endpoint.label, type='outputendpoint', variable=output_endpoint.name, field='label')
                self._add_translation_index(output_endpoint.description, type='outputendpoint', variable=output_endpoint.name, field='description')
        else:
            for preference in self._info.params:
                self._add_translation_index(preference.label, type='vdef', variable=preference.name, field='label')
                self._add_translation_index(preference.description, type='vdef', variable=preference.name, field='description')

                if preference.type == 'list':
                    for option_index, option in enumerate(preference.options):
                        self._add_translation_index(option.label, type='upo', variable=preference.name, option=option_index)

        self._info.check_translations()

    def get_resource_type(self) -> MACType:
        return self._info.type

    def get_resource_name(self) -> Name:
        return self._info.name

    def get_resource_vendor(self) -> Vendor:
        return self._info.vendor

    def get_resource_version(self) -> Version:
        return self._info.version

    def get_resource_info(self) -> MACD:
        return self._info
