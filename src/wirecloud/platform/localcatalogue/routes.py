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

import zipfile
import logging
from typing import Union, Optional

import orjson
from fastapi import APIRouter, Request, Response, Query, UploadFile, Path
from fastapi.responses import StreamingResponse

import errno
import os

from wirecloud.catalogue import utils as catalogue_utils
from wirecloud.catalogue.schemas import CatalogueResourceDeleteResults, CatalogueResourceType
from wirecloud.catalogue.search import add_resource_to_index, delete_resource_from_index
from wirecloud.commons.auth.crud import get_user_by_username, get_group_by_name, \
    get_top_group_organization
from wirecloud.commons.auth.schemas import UserAll
from wirecloud.commons.utils.template import TemplateParseException, UnsupportedFeature
from wirecloud.commons.utils.template.schemas.macdschemas import MACD, Vendor, Name, Version
from wirecloud.commons.auth.utils import UserDepNoCSRF, UserDep
from wirecloud.commons.utils.http import produces, NotFound, build_error_response, authentication_required, \
    consumes, build_downloadfile_response
from wirecloud.catalogue.crud import get_catalogue_resource_versions_for_user, get_catalogue_resource_by_id, \
    get_catalogue_resource, get_user_catalogue_resource, get_user_catalogue_resources, \
    delete_catalogue_resources, uninstall_resource_to_user, delete_resource_if_not_used
from wirecloud.commons.utils.wgt import WgtFile, InvalidContents
from wirecloud.platform.localcatalogue import docs
from wirecloud.database import DBDep, Id, DBSession
from wirecloud.platform.localcatalogue.schemas import MultipleResourcesInstalledResponse, ResourceCreateData, \
    MassiveUpdateResponse
from wirecloud.platform.localcatalogue.utils import fix_dev_version, install_component
from wirecloud.platform.workspace.crud import get_workspace_by_id, update_all_workspaces_with_resources
from wirecloud.platform.workspace.models import Workspace
from wirecloud.proxy.routes import parse_context_from_referer, WIRECLOUD_PROXY
from wirecloud.proxy.schemas import ProxyRequestData
from wirecloud.translation import gettext as _
from wirecloud import docs as root_docs

logger = logging.getLogger(__name__)

router = APIRouter()
resources_router = APIRouter()
workspace_router = APIRouter()


@resources_router.get(
    "/",
    response_model=dict[str, MACD],
    summary=docs.get_resource_collection_summary,
    description=docs.get_resource_collection_description,
    response_description=docs.get_resource_collection_response_description,
    responses={
        200: {"content": {"application/json": {"example": docs.get_resource_collection_response_example}}},
        406: root_docs.generate_not_acceptable_response_openapi_description(
                    docs.get_resource_collection_not_acceptable_response_description, ["application/json"]),
        422: root_docs.generate_validation_error_response_openapi_description(
            docs.get_resource_entry_group_validation_error_response_description)
    }
)
@produces(["application/json"])
async def get_resource_collection(db: DBDep, user: UserDepNoCSRF, request: Request,
                                  process_urls: bool = Query(True, description=docs.get_resource_collection_process_urls_description)):
    resources = {}
    results = await get_catalogue_resource_versions_for_user(db, user=user)
    for resource in results:
        options = resource.get_processed_info(request, process_urls=process_urls,
                                              url_pattern_name="wirecloud.showcase_media")
        resources[resource.local_uri_part] = options

    return resources

@resources_router.post(
    "/",
    response_model=Union[MACD, MultipleResourcesInstalledResponse],
    summary=docs.create_resource_summary,
    description=docs.create_resource_description,
    responses={
        200: {
            "content": {"application/json":{"example": docs.create_resource_response_example}},
            "description": docs.create_resource_ok_response_description
        },
        201: {
            "content": {"application/json": {"example": docs.create_resource_response_example}},
            "description": docs.create_resource_created_response_description
        },
        400: root_docs.generate_error_response_openapi_description(
            docs.create_resource_bad_request_response_description, 'Invalid request data'
        ),
        401: root_docs.generate_auth_required_response_openapi_description(
            docs.create_resource_auth_required_response_description),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.create_resource_permission_denied_response_description,
            docs.create_resource_permission_denied_response_example_msg),
        404: root_docs.generate_not_found_response_openapi_description(
            docs.create_resource_entry_not_found_response_description),
        406: root_docs.generate_not_acceptable_response_openapi_description(
            docs.create_resource_entry_not_acceptable_response_description, ["application/json"]),
        409: root_docs.generate_error_response_openapi_description(
            docs.create_resource_conflict_response_description, 'Resource already exists'),
        415: root_docs.generate_unsupported_media_type_response_openapi_description("Unsupported request content type")
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ResourceCreateData"}
                },
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                },
                "multipart/form-data": {
                    "schema": {"$ref": "#/components/schemas/ResourceCreateFormData"}
                }
            }
        }
    }
)
@authentication_required()
@consumes(['application/json', 'multipart/form-data', 'application/octet-stream'])
@produces(["application/json"])
async def create_resource(db: DBDep, user: UserDep, request: Request,
                          force_create: bool = Query(False, description=docs.create_resource_force_create_parameter_description),
                          public: bool = Query(False, description=docs.create_resource_public_parameter_description),
                          users: Union[list[str], None] = Query(None, description=docs.create_resource_users_parameter_description),
                          groups: Union[list[str], None] = Query(None, description=docs.create_resource_groups_parameter_description),
                          install_embedded_resources: bool = Query(False, description=docs.create_resource_install_embedded_resources_parameter_description)):
    if not user.has_perm("COMPONENT.INSTALL") and not user.is_superuser:
        return build_error_response(request, 403, _('You do not have permission to install components'))
    status_code = 201
    file_contents = None
    user_list = set([user.strip() for user in users if user != ""]) if users else set()
    group_list = set([group.strip() for group in groups if group != ""]) if groups else set()
    if request.state.mimetype == "multipart/form-data":
        # Instead of using the request query parameters, we will use the form data
        form_data = await request.form(max_part_size=100 * 1024 * 1024)  # 100 MB
        force_create = form_data.get("force_create", "false").lower() == "true"
        public = form_data.get("public", "false").lower() == "true"
        user_list = set(user.strip() for user in request.POST.get('users', '').split(',') if user != "")
        group_list = set(group.strip() for group in request.POST.get('groups', '').split(',') if group != "")
        install_embedded_resources = form_data.get("install_embedded_resources", "false").lower() == "true"

        if not "file" in form_data or not isinstance(form_data["file"], UploadFile):
            return build_error_response(request, 400, _("Missing component file in the request"))

        downloaded_file = await form_data["file"].read()
        try:
            file_contents = WgtFile(downloaded_file)
        except zipfile.BadZipfile:
            return build_error_response(request, 400, _("The provided file is not a valid zip file"))
    elif request.state.mimetype == "application/octet-stream":
        # The request body is the file contents
        downloaded_file = await request.body()
        try:
            file_contents = WgtFile(downloaded_file)
        except zipfile.BadZipfile:
            return build_error_response(request, 400, _("The provided file is not a valid zip file"))
    else: # application/json
        data = ResourceCreateData.model_validate_json(await request.body())

        install_embedded_resources = data.install_embedded_resources
        force_create = data.force_create
        template_url = data.url
        headers = data.headers
        headers['Accept-Encoding'] = 'identity'

        try:
            context = parse_context_from_referer(request)
        except Exception:
            context = ProxyRequestData()

        try:
            context.headers = headers
            response = await WIRECLOUD_PROXY.do_request(request, template_url, "GET", context, db)
            if response.status_code >= 300 or response.status_code < 200:
                raise Exception()

            if isinstance(response, StreamingResponse):
                downloaded_file = b""
                async for chunk in response.body_iterator:  # pragma: no branch
                    downloaded_file += chunk
            else:
                downloaded_file = response.render(None)
        except Exception as e:
            logger.error(f"Failed to download content from marketplace: {e}")
            return build_error_response(request, 409, _('Content cannot be downloaded from the specified url'))

        try:
            file_contents = WgtFile(downloaded_file)
        except zipfile.BadZipfile:
            return build_error_response(request, 400, _('The file downloaded from the marketplace is not a zip file'))

    if public is False and len(user_list) == 0 and len(group_list) == 0:
        user_objs = [user]
    else:
        user_objs = [await get_user_by_username(db, username) for username in user_list]
        if None in user_objs:
            return build_error_response(request, 404, _("Some users do not exist"))
    group_objs = [await get_group_by_name(db, group_name) for group_name in group_list]
    if None in group_objs:
        return build_error_response(request, 404, _("Some groups do not exist"))

    # TODO Check more permissions
    if not user.is_superuser:
        if public:
            return build_error_response(request, 403, _('You are not allowed to make resources publicly available to all users'))
        elif len(user_objs) > 0 and (len(user_objs) != 1 or user_objs[0].id != user.id):
            return build_error_response(request, 403, _('You are not allowed allow to install components to other users'))
        elif len(group_objs) > 0:
            for group in group_objs:
                if group.is_organization:
                    organization = await get_top_group_organization(db, group)
                    owners = organization.users
                    if user.id not in owners:
                        return build_error_response(request, 403, _('You are not allowed to install components to non-owned organizations'))

    try:
        fix_dev_version(file_contents, user)
        added, resource = await install_component(db, file_contents, executor_user=user, public=public,
                                                  users=user_objs, groups=group_objs)
        if not added and force_create:
            return build_error_response(request, 409, _('Resource already exists'))
        elif not added:
            status_code = 200
    except zipfile.BadZipfile as e:
        return build_error_response(request, 400, _('The uploaded file is not a valid zip file'), details="{}".format(e))
    except OSError as e:
        if e.errno == errno.EACCES:
            return build_error_response(request, 500, _('Error writing the resource into the filesystem. Please, contact the server administrator.'))
        else:
            raise
    except TemplateParseException as e:
        msg = "Error parsing config.xml descriptor file: %s" % e

        details = "%s" % e
        return build_error_response(request, 400, msg, details=details)
    except (InvalidContents, UnsupportedFeature) as e:
        details = e.details if hasattr(e, 'details') else None
        return build_error_response(request, 400, e, details=str(details))

    if install_embedded_resources:
        info = MultipleResourcesInstalledResponse(
            resource_details=resource.get_processed_info(request, url_pattern_name="wirecloud.showcase_media"),
            extra_resources=[]
        )

        if resource.resource_type() == 'mashup':
            resource_info = resource.get_processed_info(process_urls=False)
            for embedded_resource in resource_info.embedded:
                resource_file = file_contents.read(embedded_resource.src)

                extra_resource_contents = WgtFile(resource_file)
                extra_resource_added, extra_resource = await install_component(db, extra_resource_contents,
                                                                         executor_user=user, public=public,
                                                                         users=user_objs, groups=group_objs)
                if extra_resource_added:
                    info.extra_resources.append(extra_resource.get_processed_info(request, url_pattern_name="wirecloud.showcase_media"))

        response = Response(orjson.dumps(info.model_dump()), media_type="application/json; charset=UTF-8", status_code=status_code)
    else:
        response = Response(orjson.dumps(resource.get_processed_info(request, url_pattern_name="wirecloud.showcase_media").model_dump()),
                            media_type="application/json; charset=UTF-8", status_code=status_code)

    await add_resource_to_index(db, resource)
    response.headers["Location"] = resource.get_template_url()
    return response


@router.get(
    "/{vendor}/{name}/{version}",
    response_class=Response,
    summary=docs.get_resource_entry_summary,
    description=docs.get_resource_entry_description,
    response_description=docs.get_resource_entry_response_description,
    responses={
        401: root_docs.generate_auth_required_response_openapi_description(
            docs.get_resource_entry_auth_required_response_description),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.get_resource_entry_permission_denied_response_description,
            "You are not allowed to retrieve info about this resource"),
        404: root_docs.generate_not_found_response_openapi_description(
            docs.get_resource_entry_not_found_response_description)
    }
)
@authentication_required()
async def get_resource_entry(db: DBDep, user: UserDepNoCSRF, request: Request,
                             vendor: str = Path(..., description=docs.get_resource_entry_parameter_vendor_description),
                             name: str = Path(..., description=docs.get_resource_entry_parameter_name_description),
                             version: str = Path(..., description=docs.get_resource_entry_parameter_version_description)):
    resource = await get_catalogue_resource(db, vendor, name, version)
    if not resource:
        raise NotFound("Resource not found")

    if not resource.is_available_for(user):
        return build_error_response(request, 403, _("You are not allowed to retrieve info about this resource"))

    file_name = '_'.join((vendor, name, version)) + '.wgt'
    base_dir = catalogue_utils.wgt_deployer.get_base_dir(vendor, name, version)
    response = build_downloadfile_response(request, file_name, base_dir)
    response.headers['Content-Type'] = resource.mimetype
    return response


async def delete_resources(db: DBSession, user: UserAll, request: Request, vendor: str, name: str, version: Optional[str],
                           allusers: bool, affected: bool) -> Response:
    if allusers and not user.is_superuser and not user.has_perm("COMPONENT.DELETE"):
        return build_error_response(request, 403, _('You are not allowed to delete resources'))

    if version is not None:
        resource = await get_user_catalogue_resource(db, user=user, vendor=vendor, short_name=name, version=version)
        if not resource:
            raise NotFound("Resource not found")

        resources = [resource]
    else:
        resources = await get_user_catalogue_resources(db, user=user, vendor=vendor, short_name=name)
        if len(resources) == 0:
            raise NotFound("Resource not found")

    result = CatalogueResourceDeleteResults(
        affectedVersions=[]
    ) if affected else None

    if allusers:
        await delete_catalogue_resources(db, [resource.id for resource in resources])

    for resource in resources:
        if not allusers:
            await uninstall_resource_to_user(db, resource, user)
            await delete_resource_if_not_used(db, resource)

        if affected:
            result.affectedVersions.append(resource.version)

        remaining = None if allusers else await get_catalogue_resource_by_id(db, resource.id)
        if remaining is None:
            await delete_resource_from_index(resource)
        else:
            await add_resource_to_index(db, remaining)

    if affected:
        return Response(orjson.dumps(result.model_dump()), media_type="application/json; charset=UTF-8", status_code=200)
    else:
        return Response(status_code=204)


@router.delete(
    "/{vendor}/{name}/{version}",
    summary=docs.delete_resource_entry_version_summary,
    description=docs.delete_resource_entry_version_description,
    responses={
        200: {
            "content": {"application/json": {
                "schema": {"$ref": "#/components/schemas/CatalogueResourceDeleteResults"},
                "example": docs.delete_resource_entry_version_response_example}
            },
            "description": docs.delete_resource_entry_version_ok_response_description
        },
        204: {
            "description": docs.delete_resource_entry_version_no_content_response_description
        },
        401: root_docs.generate_auth_required_response_openapi_description(
            docs.delete_resource_entry_version_auth_required_response_description),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.delete_resource_entry_version_permission_denied_response_description,
            "You are not allowed to delete this resource"),
        404: root_docs.generate_not_found_response_openapi_description(
            docs.delete_resource_entry_version_not_found_response_description)
    }
)
@authentication_required()
async def delete_resource_entry_version(db: DBDep, user: UserDep, request: Request,
                                        vendor: str = Path(..., description=docs.delete_resource_entry_version_parameter_vendor_description),
                                        name: str = Path(..., description=docs.delete_resource_entry_version_parameter_name_description),
                                        version: str = Path(..., description=docs.delete_resource_entry_version_parameter_version_description),
                                        allusers: bool = Query(False, description=docs.delete_resource_entry_version_allusers_parameter_description),
                                        affected: bool = Query(False, description=docs.delete_resource_entry_version_affected_parameter_description)):
    return await delete_resources(db, user, request, vendor, name, version, allusers, affected)


@router.delete(
    "/{vendor}/{name}",
    summary=docs.delete_resource_entry_summary,
    description=docs.delete_resource_entry_description,
    responses={
        200: {
            "content": {"application/json": {
                "schema": {"$ref": "#/components/schemas/CatalogueResourceDeleteResults"},
                "example": docs.delete_resource_entry_version_response_example}
            },
            "description": docs.delete_resource_entry_version_ok_response_description
        },
        204: {
            "description": docs.delete_resource_entry_version_no_content_response_description
        },
        401: root_docs.generate_auth_required_response_openapi_description(
            docs.delete_resource_entry_version_auth_required_response_description),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.delete_resource_entry_version_permission_denied_response_description,
            "You are not allowed to delete this resource"),
        404: root_docs.generate_not_found_response_openapi_description(
            docs.delete_resource_entry_version_not_found_response_description)
    }
)
@authentication_required()
async def delete_resource_entry(db: DBDep, user: UserDep, request: Request,
                                vendor: str = Path(..., description=docs.delete_resource_entry_version_parameter_vendor_description),
                                name: str = Path(..., description=docs.delete_resource_entry_version_parameter_name_description),
                                allusers: bool = Query(False, description=docs.delete_resource_entry_version_allusers_parameter_description),
                                affected: bool = Query(False, description=docs.delete_resource_entry_version_affected_parameter_description)):
    return await delete_resources(db, user, request, vendor, name, None, allusers, affected)


@router.get(
    "/{vendor}/{name}/{version}/description",
    summary=docs.get_resource_description_summary,
    description=docs.get_resource_description_description,
    response_description=docs.get_resource_description_response_description,
    response_model=MACD,
    responses={
        200: {"content": {"application/json": {"example": docs.get_resource_description_response_example}}},
        404: root_docs.generate_not_found_response_openapi_description(
            docs.get_resource_description_not_found_response_description)
    }
)
async def get_resource_description(db: DBDep, request: Request, user: UserDepNoCSRF,
                                   vendor: str = Path(..., description=docs.get_resource_description_parameter_vendor_description),
                                   name: str = Path(..., description=docs.get_resource_description_parameter_name_description),
                                   version: str = Path(..., description=docs.get_resource_description_parameter_version_description),
                                   process_urls: bool = Query(True, description=docs.get_resource_description_parameter_process_urls_description),
                                   include_wgt_files: bool = Query(False, description=docs.get_resource_description_parameter_include_wgt_files_description)):
    resource = await get_catalogue_resource(db, vendor, name, version)
    if not resource:
        raise NotFound("Resource not found")

    if not resource.is_available_for(user):
        return build_error_response(request, 403, _("You are not allowed to retrieve info about this resource"))

    resource_info = resource.get_processed_info(request, process_urls=process_urls)
    if include_wgt_files:
        base_dir = catalogue_utils.wgt_deployer.get_base_dir(resource.vendor, resource.short_name, resource.version)
        wgt_file = zipfile.ZipFile(os.path.join(base_dir, resource.template_uri))
        resource_info.wgt_files = [filename for filename in wgt_file.namelist() if filename[-1] != '/']
        wgt_file.close()

    return resource_info


@workspace_router.get(
    "/{workspace_id}/resources",
    summary=docs.get_workspace_resource_collection_summary,
    description=docs.get_workspace_resource_collection_description,
    response_description=docs.get_workspace_resource_collection_response_description,
    response_model=dict[str, MACD],
    responses={
        200: {"content": {"application/json": {"example": docs.get_workspace_resource_collection_response_example}}},
        404: root_docs.generate_not_found_response_openapi_description(
            docs.get_workspace_resource_collection_not_found_response_description),
        406: root_docs.generate_not_acceptable_response_openapi_description(
            docs.get_workspace_resource_collection_not_acceptable_response_description, ["application/json"]),
    }
)
@produces(["application/json"])
async def get_workspace_resource_collection(db: DBDep, user: UserDepNoCSRF, request: Request,
                                            workspace_id: str = Path(..., description=docs.get_workspace_resource_collection_parameter_workspace_id_description),
                                            process_urls: bool = Query(True, description=docs.get_workspace_resource_collection_parameter_process_urls_description)):
    workspace: Workspace = await get_workspace_by_id(db, Id(workspace_id))
    if not workspace:
        raise NotFound("Workspace not found")

    if not await workspace.is_accessible_by(db, user):
        return build_error_response(request, 403, _("You don't have access to this workspace"))

    widgets = set()
    result = {}
    for tab in workspace.tabs.values():
        for widget in tab.widgets.values():
            if not widget.id in widgets:
                resource = await get_catalogue_resource_by_id(db, widget.resource)
                if resource:
                    options = resource.get_processed_info(request, process_urls=process_urls,
                                                          url_pattern_name="wirecloud.showcase_media")
                    result[resource.local_uri_part] = options

                widgets.add(widget.id)

    for operator_id, operator in workspace.wiring_status.operators.items():
        vendor, name, version = operator.name.split('/')
        resource = await get_catalogue_resource(db, vendor, name, version)
        if resource and resource.is_available_for(user):
            options = resource.get_processed_info(request, process_urls=process_urls,
                                                  url_pattern_name="wirecloud.showcase_media")
            result[resource.local_uri_part] = options

    return result


@router.post(
    "/{vendor}/{name}/{version}/mass-update",
    summary=docs.mass_update_resource_summary,
    description=docs.mass_update_resource_description,
    response_description=docs.mass_update_resource_response_description,
    response_model=MassiveUpdateResponse,
    responses={
        200: {"content": {"application/json": {"example": docs.mass_update_resource_response_example}}},
        401: root_docs.generate_auth_required_response_openapi_description(
            docs.mass_update_resource_auth_required_response_description
        ),
        403: root_docs.generate_permission_denied_response_openapi_description(
            docs.mass_update_resource_permission_denied_response_description,
            "You do not have permission to perform massive updates on components"
        ),
        404: root_docs.generate_not_found_response_openapi_description(
            docs.mass_update_resource_not_found_response_description
        ),
        422: root_docs.generate_validation_error_response_openapi_description(
            docs.mass_update_resource_validation_error_response_description
        )
    }
)
@authentication_required()
async def massive_resource_update(db: DBDep, request: Request, user: UserDep, vendor: Vendor = Path(), name: Name = Path(), version: Version = Path()):
    if not user.has_perm("COMPONENT.MASSIVE_UPDATE") and not user.is_superuser:
        return build_error_response(request, 403, _('You do not have permission to perform massive updates on components'))

    resource = await get_catalogue_resource(db, vendor, name, version)
    if resource is None:
        return build_error_response(request, 404, _('Resource not found'))

    if resource.type != CatalogueResourceType.widget and resource.type != CatalogueResourceType.operator:
        return build_error_response(request, 422, _('The resource type is not supported for massive updates'))

    return await update_all_workspaces_with_resources(db, user, request, resource)
