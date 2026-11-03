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

from fastapi import Depends
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import OperationFailure
from typing import AsyncIterator, Annotated, Any, Optional

import logging

from pydantic_core import core_schema

from wirecloud.settings import DATABASE
from bson import ObjectId


class CollectionWrapper:
    def __init__(self, collection, session):
        self._collection = collection
        self._session = session

    def __getattr__(self, item):
        attr = getattr(self._collection, item)
        if callable(attr):
            def wrapper(*args, **kwargs):
                if 'session' not in kwargs:
                    kwargs['session'] = self._session
                return attr(*args, **kwargs)
            return wrapper
        return attr


class DatabaseWrapper:
    def __init__(self, db, session):
        self._db = db
        self._session = session

    def __getitem__(self, name):
        collection = self._db[name]
        return CollectionWrapper(collection, self._session)

    def __getattr__(self, item):
        collection = getattr(self._db, item)
        return CollectionWrapper(collection, self._session)


class PyMongoSession:
    def __init__(self, session: AsyncClientSession, use_transactions: bool = True):
        self._session = session
        self._transactions_supported = use_transactions

    def __getattr__(self, item: str):
        if item == "client":
            db = self._session.client[DATABASE['NAME']]
            if self._transactions_supported:
                return DatabaseWrapper(db, self._session)
            else:
                return db
        else:
            return getattr(self._session, item)

    @property
    def in_transaction(self) -> bool:
        if not self._transactions_supported:
            return False
        return self._session.in_transaction

    async def start_transaction(self):
        if not self._transactions_supported or self._session.in_transaction:
            return

        try:
            await self._session.start_transaction()
        except OperationFailure as e:
            if e.code == 20:
                logging.warning("Transactions are not supported by the MongoDB deployment. Continuing without transactions.")
                self._transactions_supported = False
            else:
                raise


class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type: Any, _handler: Any) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema([
                core_schema.is_instance_schema(ObjectId),
                core_schema.chain_schema([
                    core_schema.str_schema(),
                    core_schema.no_info_plain_validator_function(cls.validate),
                ])
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: x if isinstance(x, ObjectId) else ObjectId(x)
            ),
        )

    @classmethod
    def validate(cls, value) -> ObjectId:
        if not ObjectId.is_valid(value):
            raise ValueError("Invalid ObjectId")
        return ObjectId(value)


Id = PyObjectId


def get_db_url() -> str:
    driver = "mongodb"
    if DATABASE['USER'] and DATABASE['PASSWORD'] and DATABASE['USER'] != "" and DATABASE["PASSWORD"] != "":
        database_url = f"{driver}://{DATABASE['USER']}:{DATABASE['PASSWORD']}@{DATABASE['HOST']}"
    elif DATABASE['USER'] and DATABASE['USER'] != "":
        database_url = f"{driver}://{DATABASE['USER']}@{DATABASE['HOST']}"
    else:
        database_url = f"{driver}://{DATABASE['HOST']}"

    if DATABASE['PORT']:
        database_url += f":{DATABASE['PORT']}"

    return database_url


USE_TRANSACTIONS = DATABASE.get('USE_TRANSACTIONS', True)
client = AsyncMongoClient(get_db_url())
database = client[DATABASE['NAME']]


async def close() -> None:
    await client.close()


_transactions_supported: Optional[bool] = None

async def check_transactions_supported() -> bool:
    global _transactions_supported

    if _transactions_supported is not None:
        return _transactions_supported

    async with client.start_session() as session:
        try:
            await session.start_transaction()
            db = session.client[DATABASE['NAME']]
            await db.command("find", "test_collection", limit=1, session=session)
            await session.abort_transaction()
            _transactions_supported = True
        except OperationFailure as e:
            if e.code == 20:
                logging.warning(
                    "Transactions are not supported by the MongoDB deployment. Continuing without transactions.")
                _transactions_supported = False
            else:
                raise

    return _transactions_supported


async def get_session() -> AsyncIterator[PyMongoSession]:
    async with client.start_session() as session:
        transactions_enabled = USE_TRANSACTIONS and await check_transactions_supported()
        pymongo_session = PyMongoSession(session, use_transactions=transactions_enabled)

        try:
            await pymongo_session.start_transaction()
            yield pymongo_session
            if pymongo_session.in_transaction:
                await pymongo_session._session.commit_transaction()

        except Exception:
            if pymongo_session.in_transaction:
                await pymongo_session._session.abort_transaction()
            raise


async def commit(session: PyMongoSession) -> None:
    if session.in_transaction:
        await session._session.commit_transaction()
        await session.start_transaction()


async def rollback(session: PyMongoSession) -> None:
    """Abort a failed operation even when its transport turns errors into data."""
    if session.in_transaction:
        await session._session.abort_transaction()
        await session.start_transaction()


DBSession = PyMongoSession
DBDep = Annotated[PyMongoSession, Depends(get_session)]
