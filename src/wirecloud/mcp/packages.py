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

from __future__ import annotations

import base64
import io
import posixpath
import stat
import zipfile
from datetime import timedelta
from typing import Any, Optional

from fastapi import HTTPException

from wirecloud.commons.auth.tokens import digest, now, random_token
from wirecloud.commons.utils.wgt import WgtFile, InvalidContents
from wirecloud.commons.utils.template import TemplateParser, TemplateParseException
from wirecloud.commons.utils.template.schemas.macdschemas import MACD
from wirecloud.database import DBSession
from wirecloud.oauth2provider import OAuthPrincipal

INLINE_LIMIT = 2 * 1024 * 1024
PACKAGE_LIMIT = 100 * 1024 * 1024
EXTRACTED_LIMIT = 500 * 1024 * 1024


def validate_package(
    content: bytes, _depth: int = 0, _budget: Optional[list[int]] = None
) -> tuple[WgtFile, MACD]:
    if not content or len(content) > PACKAGE_LIMIT:
        raise HTTPException(413, "Package must contain at most 100 MiB")
    if _depth > 4:
        raise HTTPException(422, "Embedded package nesting limit exceeded")
    _budget = [EXTRACTED_LIMIT] if _budget is None else _budget
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(e.file_size for e in entries) > EXTRACTED_LIMIT:
                raise ValueError("Package extraction limit exceeded")
            _budget[0] -= sum(e.file_size for e in entries)
            if _budget[0] < 0:
                raise ValueError("Embedded package extraction limit exceeded")
            names = set()
            for entry in entries:
                path = entry.filename.replace("\\", "/")
                if path.startswith("/") or ".." in path.split("/") or ":" in path.split("/")[0] or "\x00" in path:
                    raise ValueError("Unsafe archive path")
                normalized = posixpath.normpath(path)
                if normalized in names or stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                    raise ValueError("Duplicate, linked, or encrypted archive entry")
                names.add(normalized)
            bad = archive.testzip()
            if bad:
                raise ValueError("Corrupt archive entry")
        package = WgtFile(content)
        info = TemplateParser(package.get_template()).get_resource_info()
        for embedded in getattr(info, "embedded", []):
            validate_package(package.read(embedded.src), _depth + 1, _budget)
        from wirecloud.catalogue.utils import check_packaged_resource

        check_packaged_resource(package, info)
        return package, info
    except (
        ValueError,
        KeyError,
        OSError,
        zipfile.BadZipFile,
        RuntimeError,
        InvalidContents,
        TemplateParseException,
    ) as exc:
        raise HTTPException(422, "Invalid WGT package: " + str(exc)) from exc


def decode_package(encoded: str) -> bytes:
    if len(encoded) > 4 * ((INLINE_LIMIT + 2) // 3):
        raise HTTPException(413, "Inline packages are limited to 2 MiB; use a URL or binary upload")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(422, "Invalid base64 WGT package") from exc
    if len(content) > INLINE_LIMIT:
        raise HTTPException(413, "Inline package exceeds 2 MiB")
    return content


async def ensure_upload_indexes(db: DBSession) -> None:
    """Expire unused chunks and make shared-worker chunk ordering unambiguous."""
    for collection in ("mcp_uploads", "mcp_upload_chunks"):
        await db.client[collection].create_index("expires_at", expireAfterSeconds=0)
    await db.client.mcp_upload_chunks.create_index([("upload_id", 1), ("index", 1)], unique=True)


async def store_upload(db: DBSession, principal: OAuthPrincipal, content: bytes) -> dict[str, Any]:
    validate_package(content)
    handle = random_token()
    # Mongo documents are bounded at 16 MiB. GridFS-style chunks keep uploads
    # shared across workers without a shared local filesystem.
    key = digest(handle)
    expiry = now() + timedelta(minutes=15)
    for index, start in enumerate(range(0, len(content), 1024 * 1024)):
        await db.client.mcp_upload_chunks.insert_one(
            {"upload_id": key, "index": index, "data": content[start : start + 1024 * 1024], "expires_at": expiry}
        )
    await db.client.mcp_uploads.insert_one(
        {
            "_id": key,
            "user_id": str(principal.user.id),
            "grant_id": principal.grant_id,
            "expires_at": expiry,
            "size": len(content),
        }
    )
    return {"upload_id": handle, "size": len(content), "expires_in": 900}


async def consume_upload(db: DBSession, principal: OAuthPrincipal, handle: str) -> bytes:
    record = await db.client.mcp_uploads.find_one_and_delete(
        {
            "_id": digest(handle),
            "user_id": str(principal.user.id),
            "grant_id": principal.grant_id,
            "expires_at": {"$gt": now()},
        }
    )
    if record is None:
        raise HTTPException(404, "Upload not found or expired")
    chunks = await db.client.mcp_upload_chunks.find({"upload_id": record["_id"]}).sort("index", 1).to_list()
    await db.client.mcp_upload_chunks.delete_many({"upload_id": record["_id"]})
    content = b"".join(chunk["data"] for chunk in chunks)
    if len(content) != record["size"]:
        raise HTTPException(422, "Incomplete package upload")
    return content
