# -*- coding: utf-8 -*-

import sys
import types
import errno
import inspect
import io
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Response
from httpx import ASGITransport, AsyncClient
from starlette.datastructures import FormData, UploadFile
from starlette.requests import Request

if "elasticsearch._async.helpers" not in sys.modules:
    _helpers = types.ModuleType("elasticsearch._async.helpers")

    async def _async_bulk(*_args, **_kwargs):
        return (0, [])

    _helpers.async_bulk = _async_bulk
    _helpers.async_reindex = _async_bulk
    _helpers.async_scan = _async_bulk
    _helpers.async_streaming_bulk = _async_bulk
    sys.modules["elasticsearch._async.helpers"] = _helpers

from wirecloud.catalogue import routes
from wirecloud.commons.utils.template import TemplateParseException
from wirecloud.commons.utils.wgt import InvalidContents
from wirecloud.commons.auth.schemas import Permission
from wirecloud.commons.auth.utils import get_user_csrf
from wirecloud.main import app


@pytest.fixture(autouse=True)
def _patch_gettext(monkeypatch):
    monkeypatch.setattr(routes, "_", lambda text: text)


@pytest.fixture()
async def app_http_client(db_session):
    from wirecloud.database import get_session

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def test_catalogue_auth_required_endpoints(app_http_client):
    r1 = await app_http_client.post("/catalogue/resources", content=b"x", headers={"content-type": "application/octet-stream"})
    assert r1.status_code == 401

    r2 = await app_http_client.delete("/catalogue/resource/acme/widget")
    assert r2.status_code == 401

    r3 = await app_http_client.delete("/catalogue/resource/acme/widget/1.0.0")
    assert r3.status_code == 401


async def test_get_resources_scope_and_search_paths(app_http_client, monkeypatch):
    bad_scope = await app_http_client.get("/catalogue/resources", params={"scope": "bad"})
    assert bad_scope.status_code == 400

    async def _search_none(_request, _user, _q, _pagenum, _maxresults, _scope, _orderby):
        return None

    monkeypatch.setattr(routes, "get_search_engine", lambda _name: _search_none)
    bad_order = await app_http_client.get("/catalogue/resources")
    assert bad_order.status_code == 422

    async def _search_ok(_request, _user, _q, _pagenum, _maxresults, _scope, _orderby):
        return {
            "offset": 0,
            "pagecount": 1,
            "pagelen": 0,
            "pagenum": 1,
            "results": [],
            "total": 0,
        }

    monkeypatch.setattr(routes, "get_search_engine", lambda _name: _search_ok)
    ok = await app_http_client.get("/catalogue/resources", params={"scope": "widget", "orderby": "-creation_date"})
    assert ok.status_code == 200
    assert ok.json()["total"] == 0


async def test_resource_version_get_notfound_forbidden_and_success(app_http_client, monkeypatch):
    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(routes, "get_catalogue_resource", _none)
    not_found = await app_http_client.get("/catalogue/resource/acme/widget/1.0.0")
    assert not_found.status_code == 404

    class _Res:
        vendor = "acme"
        short_name = "widget"
        version = "1.0.0"

        def is_available_for(self, user):
            return False

    async def _res(*_args, **_kwargs):
        return _Res()

    monkeypatch.setattr(routes, "get_catalogue_resource", _res)
    forbidden = await app_http_client.get("/catalogue/resource/acme/widget/1.0.0")
    assert forbidden.status_code == 403

    class _ResOk(_Res):
        def is_available_for(self, user):
            return True

    async def _res_ok(*_args, **_kwargs):
        return _ResOk()

    async def _get_resource_data(*_args, **_kwargs):
        return {
            "vendor": "acme",
            "name": "widget",
            "type": "widget",
            "version": "1.0.0",
            "date": 1,
            "permissions": {"delete": False, "uninstall": False},
            "authors": [],
            "contributors": [],
            "title": "t",
            "description": "d",
            "longdescription": "ld",
            "email": "",
            "image": "",
            "homepage": "",
            "doc": "",
            "changelog": "",
            "size": 0,
            "uriTemplate": "",
            "license": "",
            "licenseurl": "",
            "issuetracker": "",
        }

    monkeypatch.setattr(routes, "get_catalogue_resource", _res_ok)
    monkeypatch.setattr(routes, "get_resource_data", _get_resource_data)

    ok = await app_http_client.get("/catalogue/resource/acme/widget/1.0.0")
    assert ok.status_code == 200
    assert ok.json()["vendor"] == "acme"


async def test_resource_versions_group_routes(app_http_client, monkeypatch):
    async def _empty(*_args, **_kwargs):
        return []

    monkeypatch.setattr(routes, "get_catalogue_resource_versions_for_user", _empty)
    not_found = await app_http_client.get("/catalogue/resource/acme/widget")
    assert not_found.status_code == 404

    async def _versions(*_args, **_kwargs):
        return [SimpleNamespace()]

    async def _group_data(*_args, **_kwargs):
        return {
            "vendor": "acme",
            "name": "widget",
            "type": "widget",
            "versions": [
                {
                    "version": "1.0.0",
                    "date": 1,
                    "permissions": {"delete": False, "uninstall": False},
                    "authors": [],
                    "contributors": [],
                    "title": "t",
                    "description": "d",
                    "longdescription": "ld",
                    "email": "",
                    "image": "",
                    "homepage": "",
                    "doc": "",
                    "changelog": "",
                    "size": 0,
                    "uriTemplate": "",
                    "license": "",
                    "licenseurl": "",
                    "issuetracker": "",
                }
            ],
        }

    monkeypatch.setattr(routes, "get_catalogue_resource_versions_for_user", _versions)
    monkeypatch.setattr(routes, "get_resource_group_data", _group_data)

    ok = await app_http_client.get("/catalogue/resource/acme/widget")
    assert ok.status_code == 200
    assert ok.json()["vendor"] == "acme"


async def test_changelog_userguide_and_media_paths(app_http_client, monkeypatch):
    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(routes, "get_catalogue_resource", _none)
    assert (await app_http_client.get("/catalogue/resource/acme/widget/1.0.0/changelog")).status_code == 404
    assert (await app_http_client.get("/catalogue/resource/acme/widget/1.0.0/userguide")).status_code == 404
    assert (await app_http_client.get("/catalogue/media/acme/widget/1.0.0/a.js")).status_code == 404

    class _Info:
        changelog = ""
        doc = ""

    class _ResForbidden:
        vendor = "acme"
        short_name = "widget"
        version = "1.0.0"

        def is_available_for(self, _user):
            return False

    class _ResOk(_ResForbidden):
        def is_available_for(self, _user):
            return True

        def get_processed_info(self, process_urls=False):
            return _Info()

        def get_template_url(self, **_kwargs):
            return "http://testserver/catalogue/media/acme/widget/1.0.0/"

    async def _res_forbidden(*_args, **_kwargs):
        return _ResForbidden()

    monkeypatch.setattr(routes, "get_catalogue_resource", _res_forbidden)
    assert (await app_http_client.get("/catalogue/resource/acme/widget/1.0.0/changelog")).status_code == 403
    assert (await app_http_client.get("/catalogue/resource/acme/widget/1.0.0/userguide")).status_code == 403
    assert (await app_http_client.get("/catalogue/media/acme/widget/1.0.0/a.js")).status_code == 403

    async def _res_ok(*_args, **_kwargs):
        return _ResOk()

    monkeypatch.setattr(routes, "get_catalogue_resource", _res_ok)
    assert (await app_http_client.get("/catalogue/resource/acme/widget/1.0.0/changelog")).status_code == 404
    assert (await app_http_client.get("/catalogue/resource/acme/widget/1.0.0/userguide")).status_code == 404

    monkeypatch.setattr(routes, "build_downloadfile_response", lambda *_args, **_kwargs: Response(status_code=302, headers={"Location": "a.js"}))
    monkeypatch.setattr(routes, "get_absolute_reverse_url", lambda *_args, **_kwargs: "http://testserver/catalogue/media/acme/widget/1.0.0/a.js")
    media = await app_http_client.get("/catalogue/media/acme/widget/1.0.0/a.js")
    assert media.status_code == 302
    assert "catalogue/media" in media.headers["location"]


def _user_with_perms(*perms):
    class _User:
        username = "tester"
        is_superuser = False
        id = "507f1f77bcf86cd799439011"
        groups = []
        permissions = [Permission(codename=p) for p in perms]

        def has_perm(self, codename):
            return any(p.codename == codename for p in self.permissions)

    return _User()


def _package_upload_request(mimetype, public="true", contents=None, with_file=True):
    if contents is None:
        package = io.BytesIO()
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("config.xml", "<widget/>")
        contents = package.getvalue()

    async def receive():
        return {"type": "http.request", "body": contents}

    request = Request({"type": "http", "method": "POST", "path": "/catalogue/resources",
        "query_string": f"public={public}".encode(), "headers": [(b"accept", b"application/json")]}, receive)
    request.state.mimetype = mimetype
    form = {"public": public}
    if with_file:
        form["file"] = UploadFile(io.BytesIO(contents), filename="widget.wgt")
    request.form = AsyncMock(return_value=FormData(form))
    return request


@pytest.mark.parametrize("mimetype", ["multipart/form-data", "application/octet-stream"])
@pytest.mark.parametrize("public", ["true", "false"])
async def test_catalogue_upload_forwards_package_visibility_and_owner(monkeypatch, mimetype, public):
    user = _user_with_perms("COMPONENT.INSTALL")
    resource = SimpleNamespace(get_template_url=lambda: "/catalogue/media/acme/widget/1.0.0/widget.wgt")
    installer = AsyncMock(return_value=(True, resource))
    indexer = AsyncMock()
    monkeypatch.setattr(routes, "install_component", installer)
    monkeypatch.setattr(routes, "add_resource_to_index", indexer)

    result = await inspect.unwrap(routes.create_resource)("database", _package_upload_request(mimetype, public), user)
    assert result.status_code == 201
    assert result.headers["location"] == resource.get_template_url()
    args, kwargs = installer.await_args
    assert args[0] == "database"
    assert args[1].read("config.xml") == b"<widget/>"
    assert kwargs == {"executor_user": user, "public": public == "true", "users": [user], "restricted": True}
    indexer.assert_awaited_once_with("database", resource)


@pytest.mark.parametrize("make_request, expected", [
    (lambda: _package_upload_request("multipart/form-data", with_file=False), "Missing component file"),
    (lambda: _package_upload_request("application/octet-stream", contents=b"not a zip"), "not a zip file"),
])
async def test_catalogue_rejects_invalid_uploads_before_installing(monkeypatch, make_request, expected):
    installer = AsyncMock()
    monkeypatch.setattr(routes, "install_component", installer)
    response = await inspect.unwrap(routes.create_resource)("database", make_request(), _user_with_perms("COMPONENT.INSTALL"))
    assert response.status_code == 400
    assert expected in response.body.decode()
    installer.assert_not_awaited()


@pytest.mark.parametrize("error, status, message", [
    (OSError(errno.EACCES, "denied"), 500, "Error writing the resource"),
    (TemplateParseException("broken manifest"), 400, "broken manifest"),
    (InvalidContents("missing entry point"), 400, "missing entry point"),
])
async def test_catalogue_installer_errors_keep_diagnostics_and_skip_indexing(monkeypatch, error, status, message):
    indexer = AsyncMock()
    monkeypatch.setattr(routes, "install_component", AsyncMock(side_effect=error))
    monkeypatch.setattr(routes, "add_resource_to_index", indexer)
    response = await inspect.unwrap(routes.create_resource)(
        "database", _package_upload_request("application/octet-stream"), _user_with_perms("COMPONENT.INSTALL"),
    )
    assert response.status_code == status
    assert message in response.body.decode()
    indexer.assert_not_awaited()


async def test_catalogue_conflicts_and_unexpected_filesystem_errors(monkeypatch):
    user = _user_with_perms("COMPONENT.INSTALL")
    monkeypatch.setattr(routes, "install_component", AsyncMock(return_value=(False, None)))
    conflict = await inspect.unwrap(routes.create_resource)("database", _package_upload_request("application/octet-stream"), user)
    assert conflict.status_code == 409
    assert "Resource already exists" in conflict.body.decode()

    monkeypatch.setattr(routes, "install_component", AsyncMock(side_effect=OSError(errno.EIO, "disk error")))
    with pytest.raises(OSError) as error:
        await inspect.unwrap(routes.create_resource)("database", _package_upload_request("application/octet-stream"), user)
    assert error.value.errno == errno.EIO


async def test_create_and_delete_with_authenticated_user_overrides(app_http_client, monkeypatch):
    async def _no_perm():
        return _user_with_perms()

    app.dependency_overrides[get_user_csrf] = _no_perm
    try:
        denied = await app_http_client.post("/catalogue/resources", content=b"x", headers={"content-type": "application/octet-stream"})
        assert denied.status_code == 403
    finally:
        app.dependency_overrides.pop(get_user_csrf, None)

    async def _install_perm():
        return _user_with_perms("COMPONENT.INSTALL")

    class _Wgt:
        def __init__(self, _data):
            pass

    async def _install(*_args, **_kwargs):
        return False, None

    monkeypatch.setattr(routes, "WgtFile", _Wgt)
    monkeypatch.setattr(routes, "install_component", _install)

    app.dependency_overrides[get_user_csrf] = _install_perm
    try:
        conflict = await app_http_client.post("/catalogue/resources", content=b"x", headers={"content-type": "application/octet-stream"})
        assert conflict.status_code == 409
    finally:
        app.dependency_overrides.pop(get_user_csrf, None)

    class _Res:
        version = "1.0.0"

        async def is_removable_by(self, _db, _user, vendor=True):
            return True

    async def _res_list(*_args, **_kwargs):
        return [_Res()]

    async def _res_one(*_args, **_kwargs):
        return _Res()

    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(routes, "get_all_catalogue_resource_versions", _res_list)
    monkeypatch.setattr(routes, "get_catalogue_resource", _res_one)
    monkeypatch.setattr(routes, "mark_resources_as_not_available", _noop)
    monkeypatch.setattr(routes, "delete_resource_from_index", _noop)

    async def _delete_perm():
        return _user_with_perms("COMPONENT.DELETE")

    app.dependency_overrides[get_user_csrf] = _delete_perm
    try:
        ok_group = await app_http_client.delete("/catalogue/resource/acme/widget")
        assert ok_group.status_code == 200
        assert ok_group.json()["affectedVersions"] == ["1.0.0"]
    finally:
        app.dependency_overrides.pop(get_user_csrf, None)

    async def _uninstall_perm():
        return _user_with_perms("COMPONENT.UNINSTALL")

    app.dependency_overrides[get_user_csrf] = _uninstall_perm
    try:
        ok_one = await app_http_client.delete("/catalogue/resource/acme/widget/1.0.0")
        assert ok_one.status_code == 200
        assert ok_one.json()["affectedVersions"] == ["1.0.0"]
    finally:
        app.dependency_overrides.pop(get_user_csrf, None)


async def test_create_resource_additional_error_and_success_branches(app_http_client, monkeypatch):
    async def _install_perm():
        return _user_with_perms("COMPONENT.INSTALL")

    app.dependency_overrides[get_user_csrf] = _install_perm
    try:
        class _WgtRead:
            def __init__(self, _data):
                raise routes.zipfile.BadZipfile()

        monkeypatch.setattr(routes, "WgtFile", _WgtRead)
        multipart_with_file = await app_http_client.post(
            "/catalogue/resources",
            files={"file": ("widget.wgt", b"x"), "public": (None, "true")},
        )
        assert multipart_with_file.status_code == 400

        multipart_missing = await app_http_client.post("/catalogue/resources", files={"public": (None, "true")})
        assert multipart_missing.status_code == 400

        class _BadZip:
            def __init__(self, _data):
                raise routes.zipfile.BadZipfile()

        monkeypatch.setattr(routes, "WgtFile", _BadZip)
        bad_zip = await app_http_client.post("/catalogue/resources", content=b"x", headers={"content-type": "application/octet-stream"})
        assert bad_zip.status_code == 400

        class _Wgt:
            def __init__(self, _data):
                pass

        monkeypatch.setattr(routes, "WgtFile", _Wgt)

        async def _template_error(*_args, **_kwargs):
            raise TemplateParseException("bad template")

        monkeypatch.setattr(routes, "install_component", _template_error)
        bad_template = await app_http_client.post("/catalogue/resources", content=b"x", headers={"content-type": "application/octet-stream"})
        assert bad_template.status_code == 400

        async def _invalid_contents(*_args, **_kwargs):
            raise InvalidContents("bad package")

        monkeypatch.setattr(routes, "install_component", _invalid_contents)
        bad_contents = await app_http_client.post("/catalogue/resources", content=b"x", headers={"content-type": "application/octet-stream"})
        assert bad_contents.status_code == 400

        async def _eacces(*_args, **_kwargs):
            raise OSError(errno.EACCES, "denied")

        monkeypatch.setattr(routes, "install_component", _eacces)
        write_error = await app_http_client.post("/catalogue/resources", content=b"x", headers={"content-type": "application/octet-stream"})
        assert write_error.status_code == 500

        async def _other_os(*_args, **_kwargs):
            raise OSError(errno.EPERM, "other")

        monkeypatch.setattr(routes, "install_component", _other_os)
        internal_error = await app_http_client.post("/catalogue/resources", content=b"x", headers={"content-type": "application/octet-stream"})
        assert internal_error.status_code == 500

        class _Res:
            def get_template_url(self):
                return "http://testserver/catalogue/media/acme/widget/1.0.0/widget.wgt"

        async def _ok_install(*_args, **_kwargs):
            return True, _Res()

        async def _noop(*_args, **_kwargs):
            return None

        monkeypatch.setattr(routes, "install_component", _ok_install)
        monkeypatch.setattr(routes, "add_resource_to_index", _noop)
        created = await app_http_client.post("/catalogue/resources?public=false", content=b"x", headers={"content-type": "application/octet-stream"})
        assert created.status_code == 201
        assert "catalogue/media" in created.headers["location"]
    finally:
        app.dependency_overrides.pop(get_user_csrf, None)


async def test_delete_permission_denied_and_notfound_paths(app_http_client, monkeypatch):
    async def _no_perms():
        return _user_with_perms()

    app.dependency_overrides[get_user_csrf] = _no_perms
    try:
        denied_group = await app_http_client.delete("/catalogue/resource/acme/widget")
        denied_one = await app_http_client.delete("/catalogue/resource/acme/widget/1.0.0")
        assert denied_group.status_code == 403
        assert denied_one.status_code == 403
    finally:
        app.dependency_overrides.pop(get_user_csrf, None)

    class _Res:
        version = "1.0.0"

        async def is_removable_by(self, _db, _user, vendor=True):
            return False

    async def _delete_perm():
        return _user_with_perms("COMPONENT.DELETE")

    app.dependency_overrides[get_user_csrf] = _delete_perm
    try:
        monkeypatch.setattr(routes, "get_all_catalogue_resource_versions", lambda *_a, **_k: _async_value([]))
        group_not_found = await app_http_client.delete("/catalogue/resource/acme/widget")
        assert group_not_found.status_code == 404

        monkeypatch.setattr(routes, "get_all_catalogue_resource_versions", lambda *_a, **_k: _async_value([_Res()]))
        group_denied = await app_http_client.delete("/catalogue/resource/acme/widget")
        assert group_denied.status_code == 403
    finally:
        app.dependency_overrides.pop(get_user_csrf, None)

    async def _uninstall_perm():
        return _user_with_perms("COMPONENT.UNINSTALL")

    app.dependency_overrides[get_user_csrf] = _uninstall_perm
    try:
        monkeypatch.setattr(routes, "get_catalogue_resource", lambda *_a, **_k: _async_value(None))
        one_not_found = await app_http_client.delete("/catalogue/resource/acme/widget/1.0.0")
        assert one_not_found.status_code == 404

        monkeypatch.setattr(routes, "get_catalogue_resource", lambda *_a, **_k: _async_value(_Res()))
        one_denied = await app_http_client.delete("/catalogue/resource/acme/widget/1.0.0")
        assert one_denied.status_code == 403
    finally:
        app.dependency_overrides.pop(get_user_csrf, None)


async def test_changelog_userguide_and_media_additional_content_branches(app_http_client, monkeypatch):
    monkeypatch.setattr(routes, "markdown", SimpleNamespace(markdown=lambda *_a, **_k: "<p>doc</p>"))
    monkeypatch.setattr(routes, "clean_html", lambda html, base_url=None: f"clean:{base_url}:{html}")
    monkeypatch.setattr(routes.catalogue_utils.wgt_deployer, "get_base_dir", lambda *_a: "/tmp")

    class _Resource:
        vendor = "acme"
        short_name = "widget"
        version = "1.0.0"

        def __init__(self, changelog="docs/changelog.md", doc="docs/user.md"):
            self._changelog = changelog
            self._doc = doc

        def is_available_for(self, _user):
            return True

        def get_processed_info(self, process_urls=False):
            return SimpleNamespace(changelog=self._changelog, doc=self._doc)

        def get_template_url(self, **_kwargs):
            return "http://testserver/catalogue/media/acme/widget/1.0.0/"

    current = {"resource": _Resource()}

    async def _get_resource(*_args, **_kwargs):
        return current["resource"]

    monkeypatch.setattr(routes, "get_catalogue_resource", _get_resource)

    def _download(path):
        if path.endswith(".en.md"):
            raise IOError("no localized")
        return b"# Title"

    monkeypatch.setattr(routes, "download_local_file", _download)
    monkeypatch.setattr(routes, "filter_changelog", lambda html, _v: html)

    changelog_ok = await app_http_client.get("/catalogue/resource/acme/widget/1.0.0/changelog")
    assert changelog_ok.status_code == 200

    changelog_from_ok = await app_http_client.get("/catalogue/resource/acme/widget/1.0.0/changelog", params={"from": "0.9.0"})
    assert changelog_from_ok.status_code == 200

    monkeypatch.setattr(routes, "filter_changelog", lambda html, _v: "")
    changelog_empty = await app_http_client.get("/catalogue/resource/acme/widget/1.0.0/changelog", params={"from": "0.9.0"})
    assert changelog_empty.status_code == 404

    monkeypatch.setattr(routes, "download_local_file", lambda _path: (_ for _ in ()).throw(IOError("missing")))
    current["resource"] = _Resource(changelog="docs/changelog.md")
    changelog_missing_file = await app_http_client.get("/catalogue/resource/acme/widget/1.0.0/changelog")
    assert changelog_missing_file.status_code == 200

    current["resource"] = _Resource(doc="http://external/guide")
    userguide_external = await app_http_client.get("/catalogue/resource/acme/widget/1.0.0/userguide")
    assert userguide_external.status_code == 200

    def _download_fail(_path):
        raise IOError("missing")

    current["resource"] = _Resource(doc="docs/user.md")
    monkeypatch.setattr(routes, "download_local_file", _download_fail)
    userguide_fallback = await app_http_client.get("/catalogue/resource/acme/widget/1.0.0/userguide")
    assert userguide_fallback.status_code == 200

    monkeypatch.setattr(routes, "build_downloadfile_response", lambda *_a, **_k: Response(status_code=200))
    media_ok = await app_http_client.get("/catalogue/media/acme/widget/1.0.0/a.js")
    assert media_ok.status_code == 200


async def _async_value(value):
    return value
