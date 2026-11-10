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
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

# ---------------------------------------------------------------------------
# 1. Path setup — tests/ must come BEFORE src/ so that the `settings` shim
#    in tests/settings.py is found before the real src/settings.py.
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent
_SRC = str(_ROOT / "src")
_TESTS = str(_ROOT / "tests")

for _p in (_TESTS, _SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# 2. Patch pymongo.AsyncMongoClient with mongomock_motor BEFORE wirecloud.database
#    is imported for the first time.  This prevents any real TCP connection.
# ---------------------------------------------------------------------------
import mongomock_motor

_mock_mongo_client_instance = mongomock_motor.AsyncMongoMockClient()

# Patch in both the pymongo namespace and in wirecloud.database (in case it's
# already been imported by a previous import somewhere in the collection phase).
import pymongo as _pymongo
_pymongo.AsyncMongoClient = lambda *a, **kw: _mock_mongo_client_instance  # type: ignore

# Now it is safe to import wirecloud modules.
import wirecloud.database as wc_db
from wirecloud.database import PyMongoSession

# Override the module-level singletons so all code that does
# `from wirecloud.database import client` also gets the mock.
wc_db.client = _mock_mongo_client_instance
wc_db.database = _mock_mongo_client_instance[wc_db.DATABASE['NAME']]
# Disable transaction support globally for tests
wc_db.USE_TRANSACTIONS = False
wc_db._transactions_supported = False

import pytest


@pytest.fixture
def registered_route_paths():
    """List effective paths with both lazy and flattened FastAPI routers."""
    from fastapi import routing

    def paths(app):
        routes = getattr(routing, "iter_route_contexts", iter)(app.routes)
        return {route.path for route in routes if route.path is not None}

    return paths

# ---------------------------------------------------------------------------
# 3. Helpers
# ---------------------------------------------------------------------------

class _FakeClientSession:
    def __init__(self, mongo_client):
        self._mongo_client = mongo_client
        self._in_transaction = False

    @property
    def client(self):
        # PyMongoSession does: self._session.client[DATABASE['NAME']]
        return self._mongo_client

    @property
    def in_transaction(self):
        return self._in_transaction

    async def start_transaction(self):
        self._in_transaction = True

    async def commit_transaction(self):
        self._in_transaction = False

    async def abort_transaction(self):
        self._in_transaction = False

    async def end_session(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.end_session()


# ---------------------------------------------------------------------------
# 4. Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def mock_mongo_client():
    return _mock_mongo_client_instance


@pytest.fixture()
async def db_session(mock_mongo_client):
    fake_session = _FakeClientSession(mock_mongo_client)
    session = PyMongoSession(fake_session, use_transactions=False)  # type: ignore[arg-type]
    yield session


@pytest.fixture()
async def app_client(mock_mongo_client, db_session):
    from asgi_lifespan import LifespanManager
    from httpx import AsyncClient, ASGITransport
    from wirecloud.main import app
    from wirecloud.database import get_session

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session

    try:
        async with LifespanManager(app) as manager:
            transport = ASGITransport(app=manager.app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                yield client
    finally:
        app.dependency_overrides.clear()
