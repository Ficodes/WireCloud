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

import sys

# Wirecloud is only compatible with Python 3.9 or higher
if sys.version_info < (3, 9):
    raise Exception("Wirecloud is only compatible with Python 3.9 or higher")

# Make sure the wirecloud directory is identified as a module
try:
    from wirecloud import __init__
except ImportError:
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from wirecloud.settings_validator import validate_settings
from wirecloud.database import close
from wirecloud.platform.plugins import get_plugins, get_extra_openapi_schemas
from wirecloud.commons.middleware import install_all_middlewares
from wirecloud import docs


@asynccontextmanager
async def lifespan(application: FastAPI):
    await validate_settings()
    try:
        yield
    finally:
        await close()


app = FastAPI(lifespan=lifespan)

install_all_middlewares(app)
get_plugins(app)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=docs.title,
        version=docs.version,
        summary=docs.summary,
        description=docs.description,
        license_info=docs.license_info,
        contact=docs.contact,
        routes=app.routes
    )

    openapi_schema["info"]["x-logo"] = {
        "url": docs.logo_url
    }

    openapi_schema["components"]["schemas"].update(get_extra_openapi_schemas())

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
