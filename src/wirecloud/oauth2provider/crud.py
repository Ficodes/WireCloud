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

from datetime import datetime
from typing import Any, Optional

from wirecloud.database import DBSession


async def ensure_indexes(db: DBSession) -> None:
    for collection in ("oauth_attempts", "oauth_codes", "oauth_tokens"):
        await db.client[collection].create_index("expires_at", expireAfterSeconds=0)
    await db.client.oauth_clients.create_index("client_id", unique=True)
    await db.client.oauth_grants.create_index("user_id")
    await db.client.oauth_grants.create_index("session_id")


async def increment_registration_attempts(db: DBSession, bucket: str, expires_at: datetime) -> int:
    previous = await db.client.oauth_attempts.find_one_and_update(
        {"_id": bucket},
        {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": expires_at}},
        upsert=True,
    )
    return previous["count"] if previous else 0


async def create_client(db: DBSession, client: dict[str, Any]) -> None:
    await db.client.oauth_clients.insert_one(client)


async def get_client_by_id(db: DBSession, client_id: str) -> Optional[dict[str, Any]]:
    return await db.client.oauth_clients.find_one({"client_id": client_id})


async def create_attempt(db: DBSession, attempt: dict[str, Any]) -> None:
    await db.client.oauth_attempts.insert_one(attempt)


async def get_authorization_attempt(db: DBSession, attempt_id: str, current_time: datetime) -> Optional[dict[str, Any]]:
    return await db.client.oauth_attempts.find_one({"_id": attempt_id, "expires_at": {"$gt": current_time}})


async def bind_authorization_attempt(db: DBSession, attempt_id: str, user_id: str, session_id: str) -> bool:
    binding = {"user_id": user_id, "session_id": session_id}
    result = await db.client.oauth_attempts.update_one(
        {"_id": attempt_id, "$or": [{"session_id": {"$exists": False}}, binding]}, {"$set": binding}
    )
    return bool(result.matched_count)


async def consume_authorization_attempt(
    db: DBSession, attempt_id: str, user_id: str, session_id: str
) -> Optional[dict[str, Any]]:
    return await db.client.oauth_attempts.find_one_and_delete(
        {"_id": attempt_id, "user_id": user_id, "session_id": session_id}
    )


async def consume_connection_attempt(
    db: DBSession, attempt_id: str, browser: str, session_id: str, current_time: datetime
) -> Optional[dict[str, Any]]:
    return await db.client.oauth_attempts.find_one_and_delete(
        {
            "_id": attempt_id,
            "browser": browser,
            "session_id": session_id,
            "purpose": "connections",
            "expires_at": {"$gt": current_time},
        }
    )


async def create_grant(db: DBSession, grant: dict[str, Any]) -> None:
    await db.client.oauth_grants.insert_one(grant)


async def get_unrevoked_grant(db: DBSession, grant_id: str) -> Optional[dict[str, Any]]:
    return await db.client.oauth_grants.find_one({"_id": grant_id, "revoked": False})


async def get_grants_for_user(db: DBSession, user_id: str, current_time: datetime) -> list[dict[str, Any]]:
    return await db.client.oauth_grants.find(
        {"user_id": user_id, "revoked": False, "expires_at": {"$gt": current_time}}
    ).to_list()


async def update_grant_scopes(
    db: DBSession, grant_id: str, user_id: str, scopes: list[str], current_time: datetime
) -> bool:
    result = await db.client.oauth_grants.update_one(
        {"_id": grant_id, "user_id": user_id, "revoked": False, "expires_at": {"$gt": current_time}},
        {"$set": {"scopes": scopes}, "$inc": {"scope_version": 1}},
    )
    return bool(result.matched_count)


async def revoke_grant(
    db: DBSession, grant_id: str, *, client_id: Optional[str] = None, user_id: Optional[str] = None
) -> None:
    query = {"_id": grant_id}
    if client_id is not None:
        query["client_id"] = client_id
    if user_id is not None:
        query["user_id"] = user_id
    await db.client.oauth_grants.update_one(query, {"$set": {"revoked": True}})


async def create_code(db: DBSession, code: dict[str, Any]) -> None:
    await db.client.oauth_codes.insert_one(code)


async def consume_code(
    db: DBSession,
    code_id: str,
    client_id: str,
    redirect_uri: str,
    audience: str,
    challenge: str,
    current_time: datetime,
) -> Optional[dict[str, Any]]:
    return await db.client.oauth_codes.find_one_and_delete(
        {
            "_id": code_id,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "audience": audience,
            "challenge": challenge,
            "expires_at": {"$gt": current_time},
        }
    )


async def create_token(db: DBSession, token: dict[str, Any]) -> None:
    await db.client.oauth_tokens.insert_one(token)


async def get_token_by_id(db: DBSession, token_id: str, kind: Optional[str] = None) -> Optional[dict[str, Any]]:
    query = {"_id": token_id}
    if kind is not None:
        query["kind"] = kind
    return await db.client.oauth_tokens.find_one(query)


async def consume_refresh_token(db: DBSession, token_id: str, current_time: datetime) -> bool:
    record = await db.client.oauth_tokens.find_one_and_update(
        {"_id": token_id, "used": False, "expires_at": {"$gt": current_time}}, {"$set": {"used": True}}
    )
    return record is not None
