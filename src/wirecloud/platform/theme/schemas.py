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

from typing import Any

from pydantic import BaseModel, Field

from wirecloud.platform.theme import docs

class ThemeInfo(BaseModel):
    name: str = Field(description=docs.theme_info_name_description)
    label: str = Field(description=docs.theme_info_label_description)
    templates: dict[str, str] = Field(description=docs.theme_info_templates_description)
    config: dict[str, Any] = Field(default_factory=dict, description=docs.theme_info_config_description)