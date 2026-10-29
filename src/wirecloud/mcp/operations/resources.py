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

import hashlib
import os
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from wirecloud.catalogue import utils as catalogue_utils
from wirecloud.catalogue.crud import get_catalogue_resource
from wirecloud.catalogue.search import add_resource_to_index
from wirecloud.commons.utils.template import TemplateParser
from wirecloud.commons.utils.wgt import WgtFile
from wirecloud.mcp import packages, schemas
from wirecloud.mcp.utils import operation_request, paginate
from wirecloud.platform.localcatalogue import routes
from wirecloud.platform.localcatalogue.utils import fix_dev_version, install_component
from wirecloud.proxy.routes import WIRECLOUD_PROXY
from wirecloud.proxy.schemas import ProxyRequestData

if TYPE_CHECKING:
    from wirecloud.catalogue.schemas import CatalogueResource
    from wirecloud.mcp.adapter import WireCloudAdapter

DOCUMENTATION_LIMIT = 65536


async def list_resources(adapter: WireCloudAdapter, args: schemas.Page) -> dict[str, Any]:
    data = await adapter.call(routes.get_resource_collection, process_urls=True)
    return paginate([dict(value, resource=key) for key, value in data.items()], args)


async def get_resource(adapter: WireCloudAdapter, args: schemas.Resource) -> dict[str, Any]:
    resource = await adapter.resource(args.resource)
    return jsonable_encoder(resource.get_processed_info(adapter.request, process_variables=True))


async def get_resource_documentation(adapter: WireCloudAdapter, args: schemas.Resource) -> dict[str, Any]:
    resource = await adapter.resource(args.resource)
    info = jsonable_encoder(resource.get_processed_info(adapter.request, process_variables=True))
    result = {
        key: info.get(key) for key in ("title", "description", "longdescription", "doc", "changelog", "homepage")
    }
    base_dir = catalogue_utils.wgt_deployer.get_base_dir(resource.vendor, resource.short_name, resource.version)
    package = WgtFile(os.path.join(base_dir, resource.template_uri))
    try:
        descriptor = TemplateParser(package.get_template()).get_resource_info()
        doc_path = descriptor.doc
        if doc_path and not urlsplit(doc_path).scheme and not doc_path.startswith("/"):
            candidates = [doc_path, doc_path.rstrip("/") + "/index.md", doc_path.rstrip("/") + "/index.html"]
            for path in candidates:
                if path in package.namelist():
                    content = package.read(path)
                    result["documentation"] = content[:DOCUMENTATION_LIMIT].decode("utf-8", errors="replace")
                    result["truncated"] = len(content) > DOCUMENTATION_LIMIT
                    break
    finally:
        package.close()
    return result


async def validate_resource_package(adapter: WireCloudAdapter, args: schemas.ValidatePackage) -> dict[str, Any]:
    _, info = packages.validate_package(packages.decode_package(args.package_base64))
    return {"valid": True, "descriptor": jsonable_encoder(info)}


async def uninstall_resource(adapter: WireCloudAdapter, args: schemas.Resource) -> dict[str, Any]:
    vendor, name, version = args.resource.split("/")
    if not (adapter.user.has_perm("COMPONENT.UNINSTALL") or adapter.user.is_superuser):
        raise HTTPException(403, "Component uninstall permission is required")
    return await adapter.call(
        routes.delete_resource_entry_version,
        vendor=vendor,
        name=name,
        version=version,
        allusers=False,
        affected=True,
    )


async def install_resource(adapter: WireCloudAdapter, args: schemas.Install) -> dict[str, Any]:
    if not (adapter.user.has_perm("COMPONENT.INSTALL") or adapter.user.is_superuser):
        raise HTTPException(403, "Component install permission is required")

    content = await read_package_source(adapter, args)
    package, info = packages.validate_package(content)
    embedded = list(getattr(info, "embedded", [])) if args.install_embedded_resources else []
    for item in embedded:
        if item.src.startswith(("http:", "https:")):
            raise HTTPException(422, "Install remote embedded dependencies explicitly before installing this mashup")
        packages.validate_package(package.read(item.src))

    # Each embedded component goes through the same private installation path.
    for child_content in [package.read(item.src) for item in embedded] + [content]:
        child, _ = packages.validate_package(child_content)
        fix_dev_version(child, adapter.user)
        effective = TemplateParser(child.get_template()).get_resource_info()
        existing = await get_catalogue_resource(adapter.db, effective.vendor, effective.name, effective.version)
        reused = existing is not None and "-dev" not in effective.version
        if reused:
            check_immutable_contents(existing, child_content)
        added, resource = await install_component(
            adapter.db,
            child,
            executor_user=adapter.user,
            public=False,
            users=[adapter.user],
            groups=[],
        )
        await add_resource_to_index(adapter.db, resource)

    return {
        "installed": added,
        "reused_existing": reused,
        "resource": resource.local_uri_part,
        "descriptor": jsonable_encoder(resource.get_processed_info(adapter.request)),
    }


async def read_package_source(adapter: WireCloudAdapter, args: schemas.Install) -> bytes:
    if args.url:
        return await download_package(adapter, args.url)
    if args.package_base64 is not None:
        return packages.decode_package(args.package_base64)
    return await packages.consume_upload(adapter.db, adapter.principal, args.upload_id)


async def download_package(adapter: WireCloudAdapter, url: str) -> bytes:
    parsed = urlsplit(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(422, "An HTTP(S) package URL without embedded credentials is required")

    response = await WIRECLOUD_PROXY.do_request(
        operation_request(adapter.request),
        url,
        "GET",
        ProxyRequestData(headers={"Accept-Encoding": "identity"}),
        adapter.db,
        user=adapter.user,
    )
    if response is None or not 200 <= response.status_code < 300:
        raise HTTPException(409, "Package cannot be downloaded through the configured proxy")

    content = bytearray()
    try:
        if hasattr(response, "body_iterator"):
            async for chunk in response.body_iterator:
                content.extend(chunk)
                if len(content) > packages.PACKAGE_LIMIT:
                    raise HTTPException(413, "Downloaded package exceeds 100 MiB")
        else:
            content.extend(response.body)
    finally:
        if response.background:
            await response.background()
    return bytes(content)


def check_immutable_contents(resource: CatalogueResource, content: bytes) -> None:
    base_dir = catalogue_utils.wgt_deployer.get_base_dir(resource.vendor, resource.short_name, resource.version)
    stored_hash = hashlib.sha256()
    with open(os.path.join(base_dir, resource.template_uri), "rb") as stored:
        for chunk in iter(lambda: stored.read(1024 * 1024), b""):
            stored_hash.update(chunk)
    if stored_hash.digest() != hashlib.sha256(content).digest():
        raise HTTPException(
            409, "An immutable resource version already exists with different contents; use a new version"
        )
