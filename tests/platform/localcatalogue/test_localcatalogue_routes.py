# -*- coding: utf-8 -*-

import errno
import io
import zipfile
import copy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import Response
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter
from starlette.requests import Request

from wirecloud.main import app
from wirecloud import main as main_module
from wirecloud.commons.auth.utils import get_user_csrf, get_user_no_csrf
from wirecloud.commons.utils.template import TemplateParseException, UnsupportedFeature
from wirecloud.commons.utils.template.schemas.macdschemas import MACD
from wirecloud.commons.utils.wgt import InvalidContents
from wirecloud.platform.localcatalogue import routes
from wirecloud.platform.localcatalogue import docs as local_docs


async def _noop_close():
    return None


main_module.close = _noop_close


def _request(path="/api/resource/acme/widget/1.0.0", query=""):
    req = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "server": ("wirecloud.example.org", 443),
            "path": path,
            "query_string": query.encode("utf-8"),
            "headers": [(b"host", b"wirecloud.example.org")],
        }
    )
    req.state.lang = "en"
    return req


def _macd_example():
    return TypeAdapter(MACD).validate_python(copy.deepcopy(local_docs.create_resource_response_example))


@pytest.fixture(autouse=True)
def _patch_gettext(monkeypatch):
    monkeypatch.setattr(routes, "_", lambda text: text)


@pytest.fixture()
def auth_state():
    user = SimpleNamespace(
        id="507f1f77bcf86cd799439011",
        username="alice",
        is_superuser=False,
        has_perm=lambda _perm: False,
    )
    return {"user": user}


@pytest.fixture(autouse=True)
def _override_auth(auth_state):
    async def _dep():
        return auth_state["user"]

    app.dependency_overrides[get_user_no_csrf] = _dep
    app.dependency_overrides[get_user_csrf] = _dep
    yield
    app.dependency_overrides.pop(get_user_no_csrf, None)
    app.dependency_overrides.pop(get_user_csrf, None)


async def test_get_resource_collection_route(app_client, monkeypatch):
    base = copy.deepcopy(local_docs.get_resource_collection_response_example["example/widget/1.0.0"])
    resource = SimpleNamespace(
        local_uri_part="acme/widget/1.0.0",
        get_processed_info=lambda *_args, **_kwargs: base,
    )

    async def _versions(*_args, **_kwargs):
        return [resource]

    monkeypatch.setattr(routes, "get_catalogue_resource_versions_for_user", _versions)
    response = await app_client.get("/api/resources/", headers={"accept": "application/json"})
    assert response.status_code == 200
    assert response.json()["acme/widget/1.0.0"]["name"] == "widget"


async def test_create_resource_permission_denied(app_client):
    response = await app_client.post(
        "/api/resources/",
        content=b"zip",
        headers={"content-type": "application/octet-stream", "accept": "application/json"},
    )
    assert response.status_code == 403


async def test_create_resource_octet_and_json_branches(app_client, monkeypatch, auth_state):
    auth_state["user"] = SimpleNamespace(
        id="507f1f77bcf86cd799439011",
        username="alice",
        is_superuser=True,
        has_perm=lambda perm: perm == "COMPONENT.INSTALL",
    )
    monkeypatch.setattr(routes, "build_error_response", lambda _request, status, _msg, details=None: Response(status_code=status))

    monkeypatch.setattr(routes, "WgtFile", lambda *_args, **_kwargs: (_ for _ in ()).throw(zipfile.BadZipfile()))
    bad_zip = await app_client.post(
        "/api/resources/",
        content=b"not-zip",
        headers={"content-type": "application/octet-stream", "accept": "application/json"},
    )
    assert bad_zip.status_code == 400

    monkeypatch.setattr(routes.ResourceCreateData, "model_validate_json", staticmethod(lambda _body: SimpleNamespace(
        install_embedded_resources=False,
        force_create=False,
        url="https://marketplace.example.org/widget.wgt",
        headers={},
    )))
    monkeypatch.setattr(routes, "parse_context_from_referer", lambda *_args, **_kwargs: SimpleNamespace(headers={}))

    class _BadProxy:
        async def do_request(self, *_args, **_kwargs):
            return Response(status_code=503)

    monkeypatch.setattr(routes, "WIRECLOUD_PROXY", _BadProxy())
    cannot_download = await app_client.post(
        "/api/resources/",
        content=b'{"url":"https://marketplace.example.org/widget.wgt"}',
        headers={"content-type": "application/json", "accept": "application/json"},
    )
    assert cannot_download.status_code == 409

    class _StreamingProxy:
        async def do_request(self, *_args, **_kwargs):
            async def _iter():
                yield b"zip-stream"

            return StreamingResponse(_iter())

    monkeypatch.setattr(routes, "WIRECLOUD_PROXY", _StreamingProxy())
    monkeypatch.setattr(routes, "WgtFile", lambda *_args, **_kwargs: SimpleNamespace(read=lambda _path: b"embedded"))
    monkeypatch.setattr(routes, "fix_dev_version", lambda *_args, **_kwargs: None)

    installed = {"n": 0}

    async def _install_component(*_args, **_kwargs):
        installed["n"] += 1
        if installed["n"] == 1:
            resource = SimpleNamespace(
                id="r1",
                template_uri="main.wgt",
                get_template_url=lambda: "/api/resource/acme/widget/1.0.0",
                get_processed_info=lambda *args, **kwargs: SimpleNamespace(model_dump=lambda: {"type": "mashup", "embedded": [SimpleNamespace(src="embedded.wgt")]} if kwargs.get("process_urls", True) is False else {"type": "mashup"}),
                resource_type=lambda: "mashup",
            )
            return True, resource
        extra = SimpleNamespace(
            id="r2",
            get_processed_info=lambda *args, **kwargs: {"type": "widget"},
        )
        return True, extra

    monkeypatch.setattr(routes, "install_component", _install_component)
    monkeypatch.setattr(routes, "get_user_by_username", lambda *_args, **_kwargs: _user("alice"))
    monkeypatch.setattr(routes, "get_group_by_name", lambda *_args, **_kwargs: _group("devs"))
    monkeypatch.setattr(routes, "add_resource_to_index", lambda *_args, **_kwargs: _none())

    async def _none():
        return None

    async def _user(username):
        return SimpleNamespace(id="u1", username=username)

    async def _group(name):
        return SimpleNamespace(id="g1", name=name, is_organization=False)

    created = await app_client.post(
        "/api/resources/?install_embedded_resources=true&public=true&users=alice&groups=devs",
        content=b'{"url":"https://marketplace.example.org/widget.wgt"}',
        headers={"content-type": "application/json", "accept": "application/json"},
    )
    assert created.status_code == 201
    assert created.headers["location"].endswith("/api/resource/acme/widget/1.0.0")


async def test_create_resource_restrictions_and_errors(app_client, monkeypatch, auth_state):
    auth_state["user"] = SimpleNamespace(
        id="u-owner",
        username="alice",
        is_superuser=False,
        has_perm=lambda perm: perm == "COMPONENT.INSTALL",
    )
    monkeypatch.setattr(routes, "build_error_response", lambda _request, status, _msg, details=None: Response(status_code=status))
    monkeypatch.setattr(routes, "WgtFile", lambda *_args, **_kwargs: SimpleNamespace(read=lambda _path: b"embedded"))
    monkeypatch.setattr(routes, "fix_dev_version", lambda *_args, **_kwargs: None)

    async def _user_by_username(_db, username):
        if username == "missing":
            return None
        return SimpleNamespace(id="u-other", username=username)

    async def _group_by_name(_db, name):
        if name == "missing":
            return None
        return SimpleNamespace(id="g1", name=name, is_organization=name == "org")

    async def _top_org(*_args, **_kwargs):
        return SimpleNamespace(users=["someone-else"])

    monkeypatch.setattr(routes, "get_user_by_username", _user_by_username)
    monkeypatch.setattr(routes, "get_group_by_name", _group_by_name)
    monkeypatch.setattr(routes, "get_top_group_organization", _top_org)

    missing_users = await app_client.post(
        "/api/resources/?users=missing",
        content=b"zip-content",
        headers={"content-type": "application/octet-stream", "accept": "application/json"},
    )
    assert missing_users.status_code == 404

    missing_groups = await app_client.post(
        "/api/resources/?groups=missing",
        content=b"zip-content",
        headers={"content-type": "application/octet-stream", "accept": "application/json"},
    )
    assert missing_groups.status_code == 404

    forbidden_public = await app_client.post(
        "/api/resources/?public=true",
        content=b"zip-content",
        headers={"content-type": "application/octet-stream", "accept": "application/json"},
    )
    assert forbidden_public.status_code == 403

    forbidden_other_user = await app_client.post(
        "/api/resources/?users=bob",
        content=b"zip-content",
        headers={"content-type": "application/octet-stream", "accept": "application/json"},
    )
    assert forbidden_other_user.status_code == 403

    forbidden_org = await app_client.post(
        "/api/resources/?groups=org",
        content=b"zip-content",
        headers={"content-type": "application/octet-stream", "accept": "application/json"},
    )
    assert forbidden_org.status_code == 403

    monkeypatch.setattr(routes, "get_group_by_name", lambda *_args, **_kwargs: _group_ok())

    async def _group_ok():
        return SimpleNamespace(id="g1", name="devs", is_organization=False)

    async def _install_conflict(*_args, **_kwargs):
        resource = SimpleNamespace(
            id="r1",
            get_template_url=lambda: "/api/resource/acme/widget/1.0.0",
            get_processed_info=lambda *args, **kwargs: SimpleNamespace(model_dump=lambda: {"type": "widget"}),
            resource_type=lambda: "widget",
        )
        return False, resource

    monkeypatch.setattr(routes, "install_component", _install_conflict)
    monkeypatch.setattr(routes, "add_resource_to_index", lambda *_args, **_kwargs: _none())

    async def _none():
        return None

    force_conflict = await app_client.post(
        "/api/resources/?force_create=true",
        content=b"zip-content",
        headers={"content-type": "application/octet-stream", "accept": "application/json"},
    )
    assert force_conflict.status_code == 409

    exists = await app_client.post(
        "/api/resources/",
        content=b"zip-content",
        headers={"content-type": "application/octet-stream", "accept": "application/json"},
    )
    assert exists.status_code == 200

    async def _raise_badzip(*_args, **_kwargs):
        raise zipfile.BadZipfile()

    monkeypatch.setattr(routes, "install_component", _raise_badzip)
    bad_zip_install = await app_client.post(
        "/api/resources/",
        content=b"zip-content",
        headers={"content-type": "application/octet-stream", "accept": "application/json"},
    )
    assert bad_zip_install.status_code == 400

    async def _raise_eacces(*_args, **_kwargs):
        err = OSError("denied")
        err.errno = errno.EACCES
        raise err

    monkeypatch.setattr(routes, "install_component", _raise_eacces)
    eacces = await app_client.post(
        "/api/resources/",
        content=b"zip-content",
        headers={"content-type": "application/octet-stream", "accept": "application/json"},
    )
    assert eacces.status_code == 500

    async def _raise_parse(*_args, **_kwargs):
        raise TemplateParseException("broken")

    monkeypatch.setattr(routes, "install_component", _raise_parse)
    parse_error = await app_client.post(
        "/api/resources/",
        content=b"zip-content",
        headers={"content-type": "application/octet-stream", "accept": "application/json"},
    )
    assert parse_error.status_code == 400

    async def _raise_invalid(*_args, **_kwargs):
        raise InvalidContents("invalid")

    monkeypatch.setattr(routes, "install_component", _raise_invalid)
    invalid = await app_client.post(
        "/api/resources/",
        content=b"zip-content",
        headers={"content-type": "application/octet-stream", "accept": "application/json"},
    )
    assert invalid.status_code == 400

    async def _raise_feature(*_args, **_kwargs):
        raise UnsupportedFeature("unsupported")

    monkeypatch.setattr(routes, "install_component", _raise_feature)
    unsupported = await app_client.post(
        "/api/resources/",
        content=b"zip-content",
        headers={"content-type": "application/octet-stream", "accept": "application/json"},
    )
    assert unsupported.status_code == 400


async def test_get_resource_entry_and_description_routes(app_client, monkeypatch):
    monkeypatch.setattr(routes, "build_error_response", lambda _request, status, _msg, details=None: Response(status_code=status))

    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(routes, "get_catalogue_resource", _none)
    not_found_entry = await app_client.get("/api/resource/acme/widget/1.0.0")
    assert not_found_entry.status_code == 404

    base_description = copy.deepcopy(local_docs.get_resource_description_response_example)
    resource = SimpleNamespace(
        vendor="acme",
        short_name="widget",
        version="1.0.0",
        template_uri="widget.wgt",
        mimetype="application/x-widget",
        local_uri_part="acme/widget/1.0.0",
        is_available_for=lambda _user: False,
        get_processed_info=lambda *_args, **_kwargs: SimpleNamespace(**base_description, wgt_files=None),
    )
    monkeypatch.setattr(routes, "get_catalogue_resource", lambda *_args, **_kwargs: _resource(resource))

    async def _resource(value):
        return value

    forbidden_entry = await app_client.get("/api/resource/acme/widget/1.0.0")
    assert forbidden_entry.status_code == 403

    resource.is_available_for = lambda _user: True
    monkeypatch.setattr(routes.catalogue_utils.wgt_deployer, "get_base_dir", lambda *_args, **_kwargs: "/tmp")
    monkeypatch.setattr(routes, "build_downloadfile_response", lambda *_args, **_kwargs: Response(status_code=200))
    ok_entry = await app_client.get("/api/resource/acme/widget/1.0.0")
    assert ok_entry.status_code == 200
    assert ok_entry.headers["content-type"].startswith("application/x-widget")

    monkeypatch.setattr(routes, "get_catalogue_resource", _none)
    not_found_desc = await app_client.get("/api/resource/acme/none/1.0.0/description")
    assert not_found_desc.status_code == 404

    monkeypatch.setattr(routes, "get_catalogue_resource", lambda *_args, **_kwargs: _resource(resource))
    resource.is_available_for = lambda _user: False
    forbidden_desc = await app_client.get("/api/resource/acme/widget/1.0.0/description")
    assert forbidden_desc.status_code == 403

    resource.is_available_for = lambda _user: True
    resource.get_processed_info = lambda *_args, **_kwargs: SimpleNamespace(**base_description)
    monkeypatch.setattr(routes.catalogue_utils.wgt_deployer, "get_base_dir", lambda *_args, **_kwargs: "/tmp")
    monkeypatch.setattr(routes, "zipfile", SimpleNamespace(ZipFile=lambda *_args, **_kwargs: _zip()))

    class _zip:
        def namelist(self):
            return ["config.xml", "images/", "index.html"]

        def close(self):
            return None

    ok_desc = await routes.get_resource_description(
        db=SimpleNamespace(),
        request=_request(path="/api/resource/acme/widget/1.0.0/description"),
        user=SimpleNamespace(),
        vendor="acme",
        name="widget",
        version="1.0.0",
        process_urls=True,
        include_wgt_files=True,
    )
    assert ok_desc.wgt_files == ["config.xml", "index.html"]


async def test_workspace_resource_collection_route(app_client, monkeypatch):
    monkeypatch.setattr(routes, "build_error_response", lambda _request, status, _msg, details=None: Response(status_code=status))

    async def _none_workspace(*_args, **_kwargs):
        return None

    monkeypatch.setattr(routes, "get_workspace_by_id", _none_workspace)
    missing = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/resources")
    assert missing.status_code == 404

    workspace = SimpleNamespace(
        tabs={},
        wiring_status=SimpleNamespace(operators={}),
    )

    async def _inaccessible(*_args, **_kwargs):
        return False

    workspace.is_accessible_by = _inaccessible

    async def _workspace(*_args, **_kwargs):
        return workspace

    monkeypatch.setattr(routes, "get_workspace_by_id", _workspace)
    denied = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/resources")
    assert denied.status_code == 403

    async def _accessible(*_args, **_kwargs):
        return True

    workspace.is_accessible_by = _accessible
    workspace.tabs = {
        "tab1": SimpleNamespace(
            widgets={
                "w1": SimpleNamespace(id="w1", resource="r-widget-1"),
                "w2": SimpleNamespace(id="w1", resource="r-widget-1"),
            }
        )
    }
    workspace.wiring_status = SimpleNamespace(operators={"op1": SimpleNamespace(name="acme/op/1.0.0")})

    widget_payload = copy.deepcopy(local_docs.get_workspace_resource_collection_response_example["example/widget/1.0.0"])
    op_payload = copy.deepcopy(local_docs.get_workspace_resource_collection_response_example["example/widget/1.0.0"])
    widget_resource = SimpleNamespace(
        local_uri_part="acme/widget/1.0.0",
        is_available_for=lambda _user: True,
        get_processed_info=lambda *_args, **_kwargs: widget_payload,
    )
    op_resource = SimpleNamespace(
        local_uri_part="acme/op/1.0.0",
        is_available_for=lambda _user: True,
        get_processed_info=lambda *_args, **_kwargs: op_payload,
    )

    monkeypatch.setattr(routes, "get_catalogue_resource_by_id", lambda *_args, **_kwargs: _resource(widget_resource))
    monkeypatch.setattr(routes, "get_catalogue_resource", lambda *_args, **_kwargs: _resource(op_resource))

    async def _resource(value):
        return value

    ok = await app_client.get("/api/workspace/507f1f77bcf86cd799439011/resources")
    assert ok.status_code == 200
    body = ok.json()
    assert body["acme/widget/1.0.0"]["name"] == "widget"
    assert body["acme/op/1.0.0"]["name"] == "widget"


async def test_create_resource_direct_branches(monkeypatch):
    monkeypatch.setattr(routes, "build_error_response", lambda _request, status, _msg, details=None: Response(status_code=status))

    class _Req:
        def __init__(self, mimetype):
            self.state = SimpleNamespace(mimetype=mimetype)
            self.POST = {"users": "alice,bob", "groups": "devs"}
            self.url = SimpleNamespace(path="/api/resources/", query="", scheme="https", netloc="wirecloud.example.org")

        async def form(self, max_part_size=None):
            return self._form_data

        async def body(self):
            return self._body

    user = SimpleNamespace(id="u1", username="alice", is_superuser=True, has_perm=lambda perm: perm == "COMPONENT.INSTALL")

    create_resource_fn = routes.create_resource
    while hasattr(create_resource_fn, "__wrapped__"):
        create_resource_fn = create_resource_fn.__wrapped__

    req = _Req("multipart/form-data")
    req._form_data = {}
    missing_file = await create_resource_fn(
        SimpleNamespace(), user, req,
        force_create=False, public=False, users=None, groups=None, install_embedded_resources=False
    )
    assert missing_file.status_code == 400

    from fastapi import UploadFile

    req._form_data = {"file": UploadFile(file=io.BytesIO(b"bad"), filename="x.wgt")}
    monkeypatch.setattr(routes, "WgtFile", lambda *_args, **_kwargs: (_ for _ in ()).throw(zipfile.BadZipfile()))
    invalid_zip = await create_resource_fn(
        SimpleNamespace(), user, req,
        force_create=False, public=False, users=None, groups=None, install_embedded_resources=False
    )
    assert invalid_zip.status_code == 400

    req_json = _Req("application/json")
    req_json._body = b'{"url":"https://marketplace.example.org/widget.wgt"}'
    monkeypatch.setattr(routes.ResourceCreateData, "model_validate_json", staticmethod(lambda _body: SimpleNamespace(
        install_embedded_resources=False,
        force_create=False,
        url="https://marketplace.example.org/widget.wgt",
        headers={},
    )))
    monkeypatch.setattr(routes, "parse_context_from_referer", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bad referer")))

    class _ProxyOK:
        async def do_request(self, *_args, **_kwargs):
            class _Resp:
                status_code = 200

                def render(self, _content):
                    return b"zip-bytes"

            return _Resp()

    monkeypatch.setattr(routes, "WIRECLOUD_PROXY", _ProxyOK())
    monkeypatch.setattr(routes, "WgtFile", lambda *_args, **_kwargs: SimpleNamespace(read=lambda _src: b"embedded"))
    monkeypatch.setattr(routes, "get_user_by_username", lambda *_args, **_kwargs: _user_ok())
    monkeypatch.setattr(routes, "get_group_by_name", lambda *_args, **_kwargs: _group_ok())
    monkeypatch.setattr(routes, "fix_dev_version", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(routes, "add_resource_to_index", lambda *_args, **_kwargs: _none())

    async def _none():
        return None

    async def _user_ok():
        return SimpleNamespace(id="u1", username="alice")

    async def _group_ok():
        return SimpleNamespace(id="g1", is_organization=False)

    async def _install_raise(*_args, **_kwargs):
        err = OSError("boom")
        err.errno = errno.EPERM
        raise err

    monkeypatch.setattr(routes, "install_component", _install_raise)
    with pytest.raises(OSError):
        await create_resource_fn(
            SimpleNamespace(), user, req_json,
            force_create=False, public=False, users=None, groups=None, install_embedded_resources=False
        )

    req_json._body = b'{"url":"https://marketplace.example.org/widget.wgt"}'
    monkeypatch.setattr(routes, "WgtFile", lambda *_args, **_kwargs: (_ for _ in ()).throw(zipfile.BadZipfile()))
    bad_downloaded_zip = await create_resource_fn(
        SimpleNamespace(), user, req_json,
        force_create=False, public=False, users=None, groups=None, install_embedded_resources=False
    )
    assert bad_downloaded_zip.status_code == 400

    req_json._body = b'{"url":"https://marketplace.example.org/widget.wgt"}'
    monkeypatch.setattr(routes, "WgtFile", lambda *_args, **_kwargs: SimpleNamespace(read=lambda _src: b"embedded"))
    owner_user = SimpleNamespace(id="owner", username="owner", is_superuser=False, has_perm=lambda perm: perm == "COMPONENT.INSTALL")
    monkeypatch.setattr(routes, "get_group_by_name", lambda *_args, **_kwargs: _org_group())
    monkeypatch.setattr(routes, "get_top_group_organization", lambda *_args, **_kwargs: _top_org())

    async def _org_group():
        return SimpleNamespace(id="g1", is_organization=True)

    async def _top_org():
        return SimpleNamespace(users=["owner"])

    async def _install_ok(*_args, **_kwargs):
        resource = SimpleNamespace(
            get_template_url=lambda: "/api/resource/acme/widget/1.0.0",
            get_processed_info=lambda *args, **kwargs: SimpleNamespace(model_dump=lambda: {"type": "widget"}),
            resource_type=lambda: "widget",
        )
        return True, resource

    monkeypatch.setattr(routes, "install_component", _install_ok)
    ok = await create_resource_fn(
        SimpleNamespace(), owner_user, req_json,
        force_create=False, public=False, users=None, groups=["org"], install_embedded_resources=False
    )
    assert ok.status_code == 201

    async def _regular_group(_db, name):
        return SimpleNamespace(id=name, is_organization=False)

    monkeypatch.setattr(routes, "get_group_by_name", _regular_group)
    regular_groups = await create_resource_fn(
        SimpleNamespace(), owner_user, req_json,
        force_create=False, public=False, users=None, groups=["devs", "ops"], install_embedded_resources=False
    )
    assert regular_groups.status_code == 201


async def test_get_resource_description_and_workspace_direct_extra_branches(monkeypatch):
    monkeypatch.setattr(routes, "build_error_response", lambda _request, status, _msg, details=None: Response(status_code=status))
    base_description = copy.deepcopy(local_docs.get_resource_description_response_example)
    resource = SimpleNamespace(
        vendor="acme",
        short_name="widget",
        version="1.0.0",
        template_uri="widget.wgt",
        is_available_for=lambda _user: True,
        get_processed_info=lambda *_args, **_kwargs: SimpleNamespace(**base_description),
    )

    async def _resource(*_args, **_kwargs):
        return resource

    monkeypatch.setattr(routes, "get_catalogue_resource", _resource)
    monkeypatch.setattr(routes.catalogue_utils.wgt_deployer, "get_base_dir", lambda *_args, **_kwargs: "/tmp")
    monkeypatch.setattr(routes, "zipfile", SimpleNamespace(ZipFile=lambda *_args, **_kwargs: _zip()))

    class _zip:
        def namelist(self):
            return ["a/", "a.txt"]

        def close(self):
            return None

    desc = await routes.get_resource_description(
        db=SimpleNamespace(),
        request=_request(path="/api/resource/acme/widget/1.0.0/description"),
        user=SimpleNamespace(),
        vendor="acme",
        name="widget",
        version="1.0.0",
        process_urls=True,
        include_wgt_files=True,
    )
    assert desc.wgt_files == ["a.txt"]

    desc_no_wgt = await routes.get_resource_description(
        db=SimpleNamespace(),
        request=_request(path="/api/resource/acme/widget/1.0.0/description"),
        user=SimpleNamespace(),
        vendor="acme",
        name="widget",
        version="1.0.0",
        process_urls=True,
        include_wgt_files=False,
    )
    assert hasattr(desc_no_wgt, "version")

    workspace = SimpleNamespace(
        tabs={"tab": SimpleNamespace(widgets={"w": SimpleNamespace(id="w", resource="r1")})},
        wiring_status=SimpleNamespace(operators={"op": SimpleNamespace(name="acme/op/1.0.0")}),
    )

    async def _workspace(*_args, **_kwargs):
        return workspace

    async def _accessible(*_args, **_kwargs):
        return True

    workspace.is_accessible_by = _accessible
    monkeypatch.setattr(routes, "get_workspace_by_id", _workspace)
    monkeypatch.setattr(routes, "get_catalogue_resource_by_id", lambda *_args, **_kwargs: _none_resource())
    monkeypatch.setattr(routes, "get_catalogue_resource", lambda *_args, **_kwargs: _op_resource())

    async def _none_resource():
        return None

    async def _op_resource():
        return SimpleNamespace(is_available_for=lambda _user: False, local_uri_part="acme/op/1.0.0", get_processed_info=lambda *_args, **_kwargs: {})

    result = await routes.get_workspace_resource_collection(
        db=SimpleNamespace(),
        user=SimpleNamespace(),
        request=_request(path="/api/workspace/507f1f77bcf86cd799439011/resources"),
        workspace_id="507f1f77bcf86cd799439011",
        process_urls=True,
    )
    assert result == {}


async def test_create_resource_direct_embedded_and_streaming_branches(monkeypatch):
    monkeypatch.setattr(routes, "build_error_response", lambda _request, status, _msg, details=None: Response(status_code=status))

    create_resource_fn = routes.create_resource
    while hasattr(create_resource_fn, "__wrapped__"):
        create_resource_fn = create_resource_fn.__wrapped__

    class _Req:
        def __init__(self):
            self.state = SimpleNamespace(mimetype="application/json")
            self.POST = {"users": "", "groups": ""}
            self.url = SimpleNamespace(path="/api/resources/", query="", scheme="https", netloc="wirecloud.example.org")
            self._body = b'{"url":"https://marketplace.example.org/widget.wgt"}'

        async def body(self):
            return self._body

    req = _Req()
    user = SimpleNamespace(id="u1", username="alice", is_superuser=False, has_perm=lambda perm: perm == "COMPONENT.INSTALL")

    monkeypatch.setattr(routes.ResourceCreateData, "model_validate_json", staticmethod(lambda _body: SimpleNamespace(
        install_embedded_resources=True,
        force_create=False,
        url="https://marketplace.example.org/widget.wgt",
        headers={},
    )))
    monkeypatch.setattr(routes, "parse_context_from_referer", lambda *_args, **_kwargs: SimpleNamespace(headers={}))

    class _ProxyStreamingEmpty:
        async def do_request(self, *_args, **_kwargs):
            async def _iter():
                if False:
                    yield b""

            return StreamingResponse(_iter())

    monkeypatch.setattr(routes, "WIRECLOUD_PROXY", _ProxyStreamingEmpty())
    monkeypatch.setattr(routes, "WgtFile", lambda *_args, **_kwargs: SimpleNamespace(read=lambda _src: b"embedded"))
    monkeypatch.setattr(routes, "fix_dev_version", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(routes, "get_user_by_username", lambda *_args, **_kwargs: _user_ok())
    monkeypatch.setattr(routes, "get_group_by_name", lambda *_args, **_kwargs: _organization_group())
    monkeypatch.setattr(routes, "get_top_group_organization", lambda *_args, **_kwargs: _owned_organization())
    monkeypatch.setattr(routes, "add_resource_to_index", lambda *_args, **_kwargs: _none())

    async def _none():
        return None

    async def _user_ok():
        return SimpleNamespace(id="u1", username="alice")

    async def _organization_group():
        return SimpleNamespace(id="g1", is_organization=True)

    async def _owned_organization():
        return SimpleNamespace(users=["u1"])

    calls = {"n": 0}

    async def _install_component(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            resource = SimpleNamespace(
                get_template_url=lambda: "/api/resource/acme/widget/1.0.0",
                get_processed_info=lambda *args, **kwargs: SimpleNamespace(embedded=[SimpleNamespace(src="embedded.wgt")]) if kwargs.get("process_urls", True) is False else _macd_example(),
                resource_type=lambda: "mashup",
            )
            return True, resource
        extra_resource = SimpleNamespace(get_processed_info=lambda *_args, **_kwargs: _macd_example())
        return True, extra_resource

    monkeypatch.setattr(routes, "install_component", _install_component)

    response = await create_resource_fn(
        SimpleNamespace(),
        user,
        req,
        force_create=False,
        public=False,
        users=None,
        groups=["devs"],
        install_embedded_resources=True,
    )
    assert response.status_code == 201
    assert calls["n"] == 2


async def test_create_resource_remaining_branch_arcs(monkeypatch):
    monkeypatch.setattr(routes, "build_error_response", lambda _request, status, _msg, details=None: Response(status_code=status))
    create_resource_fn = routes.create_resource
    while hasattr(create_resource_fn, "__wrapped__"):
        create_resource_fn = create_resource_fn.__wrapped__

    class _Req:
        def __init__(self):
            self.state = SimpleNamespace(mimetype="application/json")
            self.POST = {"users": "", "groups": ""}
            self.url = SimpleNamespace(path="/api/resources/", query="", scheme="https", netloc="wirecloud.example.org")
            self._body = b'{"url":"https://marketplace.example.org/widget.wgt"}'

        async def body(self):
            return self._body

    class _EmptyStreamingResponse(StreamingResponse):
        def __init__(self):
            async def _iter():
                if False:
                    yield b"never"
            super().__init__(_iter(), status_code=200)

    req = _Req()
    user = SimpleNamespace(id="u1", username="alice", is_superuser=False, has_perm=lambda perm: perm == "COMPONENT.INSTALL")
    monkeypatch.setattr(routes.ResourceCreateData, "model_validate_json", staticmethod(lambda _body: SimpleNamespace(
        install_embedded_resources=True,
        force_create=False,
        url="https://marketplace.example.org/widget.wgt",
        headers={},
    )))
    monkeypatch.setattr(routes, "parse_context_from_referer", lambda *_args, **_kwargs: SimpleNamespace(headers={}))

    class _ProxyStream:
        async def do_request(self, *_args, **_kwargs):
            return _EmptyStreamingResponse()

    monkeypatch.setattr(routes, "WIRECLOUD_PROXY", _ProxyStream())
    monkeypatch.setattr(routes, "WgtFile", lambda *_args, **_kwargs: SimpleNamespace(read=lambda _src: b"embedded"))
    monkeypatch.setattr(routes, "fix_dev_version", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(routes, "get_group_by_name", lambda *_args, **_kwargs: _organization_group())
    monkeypatch.setattr(routes, "get_top_group_organization", lambda *_args, **_kwargs: _owned_organization())
    monkeypatch.setattr(routes, "add_resource_to_index", lambda *_args, **_kwargs: _none())

    async def _organization_group():
        return SimpleNamespace(id="g1", is_organization=True)

    async def _owned_organization():
        return SimpleNamespace(users=["u1"])

    async def _none():
        return None

    sequence = {"step": 0}

    async def _install_component(*_args, **_kwargs):
        sequence["step"] += 1
        if sequence["step"] == 1:
            resource = SimpleNamespace(
                get_template_url=lambda: "/api/resource/acme/widget/1.0.0",
                get_processed_info=lambda *args, **kwargs: SimpleNamespace(embedded=[SimpleNamespace(src="one.wgt"), SimpleNamespace(src="two.wgt")]) if kwargs.get("process_urls", True) is False else _macd_example(),
                resource_type=lambda: "mashup",
            )
            return True, resource
        if sequence["step"] == 2:
            return False, SimpleNamespace(get_processed_info=lambda *_args, **_kwargs: _macd_example())
        return True, SimpleNamespace(get_processed_info=lambda *_args, **_kwargs: _macd_example())

    monkeypatch.setattr(routes, "install_component", _install_component)
    first = await create_resource_fn(
        SimpleNamespace(),
        user,
        req,
        force_create=False,
        public=False,
        users=None,
        groups=["devs"],
        install_embedded_resources=True,
    )
    assert first.status_code == 201

    async def _install_component_widget(*_args, **_kwargs):
        resource = SimpleNamespace(
            get_template_url=lambda: "/api/resource/acme/widget/1.0.0",
            get_processed_info=lambda *args, **kwargs: _macd_example(),
            resource_type=lambda: "widget",
        )
        return True, resource

    monkeypatch.setattr(routes, "install_component", _install_component_widget)
    second = await create_resource_fn(
        SimpleNamespace(),
        user,
        req,
        force_create=False,
        public=False,
        users=None,
        groups=["devs"],
        install_embedded_resources=True,
    )
    assert second.status_code == 201


async def test_create_resource_empty_stream_iterator_branch(monkeypatch):
    monkeypatch.setattr(routes, "build_error_response", lambda _request, status, _msg, details=None: Response(status_code=status))
    create_resource_fn = routes.create_resource
    while hasattr(create_resource_fn, "__wrapped__"):
        create_resource_fn = create_resource_fn.__wrapped__

    class _Req:
        def __init__(self):
            self.state = SimpleNamespace(mimetype="application/json")
            self.POST = {"users": "", "groups": ""}
            self.url = SimpleNamespace(path="/api/resources/", query="", scheme="https", netloc="wirecloud.example.org")
            self._body = b'{"url":"https://marketplace.example.org/widget.wgt"}'

        async def body(self):
            return self._body

    class _FakeStream:
        status_code = 200

        def __init__(self):
            async def _iter():
                if False:
                    yield b"none"
            self.body_iterator = _iter()

    class _Proxy:
        async def do_request(self, *_args, **_kwargs):
            return _FakeStream()

    req = _Req()
    user = SimpleNamespace(id="u1", username="alice", is_superuser=True, has_perm=lambda perm: perm == "COMPONENT.INSTALL")
    monkeypatch.setattr(routes.ResourceCreateData, "model_validate_json", staticmethod(lambda _body: SimpleNamespace(
        install_embedded_resources=False,
        force_create=False,
        url="https://marketplace.example.org/widget.wgt",
        headers={},
    )))
    monkeypatch.setattr(routes, "parse_context_from_referer", lambda *_args, **_kwargs: SimpleNamespace(headers={}))
    monkeypatch.setattr(routes, "StreamingResponse", _FakeStream)
    monkeypatch.setattr(routes, "WIRECLOUD_PROXY", _Proxy())
    monkeypatch.setattr(routes, "WgtFile", lambda *_args, **_kwargs: (_ for _ in ()).throw(zipfile.BadZipfile()))

    response = await create_resource_fn(
        SimpleNamespace(),
        user,
        req,
        force_create=False,
        public=False,
        users=None,
        groups=None,
        install_embedded_resources=False,
    )
    assert response.status_code == 400


async def test_create_resource_real_streaming_response_empty_iterator(monkeypatch):
    monkeypatch.setattr(routes, "build_error_response", lambda _request, status, _msg, details=None: Response(status_code=status))
    create_resource_fn = routes.create_resource
    while hasattr(create_resource_fn, "__wrapped__"):
        create_resource_fn = create_resource_fn.__wrapped__

    class _Req:
        def __init__(self):
            self.state = SimpleNamespace(mimetype="application/json")
            self.POST = {"users": "", "groups": ""}
            self.url = SimpleNamespace(path="/api/resources/", query="", scheme="https", netloc="wirecloud.example.org")
            self._body = b'{"url":"https://marketplace.example.org/widget.wgt"}'

        async def body(self):
            return self._body

    class _Proxy:
        async def do_request(self, *_args, **_kwargs):
            async def _empty():
                if False:
                    yield b""
            return StreamingResponse(_empty(), status_code=200)

    monkeypatch.setattr(routes.ResourceCreateData, "model_validate_json", staticmethod(lambda _body: SimpleNamespace(
        install_embedded_resources=False,
        force_create=False,
        url="https://marketplace.example.org/widget.wgt",
        headers={},
    )))
    monkeypatch.setattr(routes, "parse_context_from_referer", lambda *_args, **_kwargs: SimpleNamespace(headers={}))
    monkeypatch.setattr(routes, "WIRECLOUD_PROXY", _Proxy())
    monkeypatch.setattr(routes, "WgtFile", lambda *_args, **_kwargs: (_ for _ in ()).throw(zipfile.BadZipfile()))

    response = await create_resource_fn(
        SimpleNamespace(),
        SimpleNamespace(id="u1", username="alice", is_superuser=True, has_perm=lambda perm: perm == "COMPONENT.INSTALL"),
        _Req(),
        force_create=False,
        public=False,
        users=None,
        groups=None,
        install_embedded_resources=False,
    )
    assert response.status_code == 400


async def test_delete_routes_delegate(app_client, monkeypatch):
    monkeypatch.setattr(routes, "delete_resources", lambda *_args, **_kwargs: _ok())

    async def _ok():
        return Response(status_code=204)

    by_version = await app_client.delete("/api/resource/acme/widget/1.0.0")
    assert by_version.status_code == 204

    by_name = await app_client.delete("/api/resource/acme/widget")
    assert by_name.status_code == 204


async def test_delete_resources_helper(db_session, monkeypatch):
    user = SimpleNamespace(id="u1", username="alice", is_superuser=False, has_perm=lambda _perm: False)
    request = _request()
    monkeypatch.setattr(routes, "build_error_response", lambda _request, status, _msg, details=None: Response(status_code=status))

    denied = await routes.delete_resources(db_session, user, request, "acme", "widget", "1.0.0", True, False)
    assert denied.status_code == 403

    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(routes, "get_user_catalogue_resource", _none)
    with pytest.raises(Exception):
        await routes.delete_resources(db_session, user, request, "acme", "widget", "1.0.0", False, False)

    async def _empty(*_args, **_kwargs):
        return []

    monkeypatch.setattr(routes, "get_user_catalogue_resources", _empty)
    with pytest.raises(Exception):
        await routes.delete_resources(db_session, user, request, "acme", "widget", None, False, False)

    resources = [
        SimpleNamespace(id="r1", version="1.0.0"),
        SimpleNamespace(id="r2", version="2.0.0"),
    ]

    async def _resources(*_args, **_kwargs):
        return resources

    called = {"delete": 0, "uninstall": 0, "delete_if_unused": 0, "index_delete": 0}
    monkeypatch.setattr(routes, "get_user_catalogue_resources", _resources)
    monkeypatch.setattr(routes, "delete_catalogue_resources", lambda *_args, **_kwargs: _inc(called, "delete"))
    monkeypatch.setattr(routes, "uninstall_resource_to_user", lambda *_args, **_kwargs: _inc(called, "uninstall"))
    monkeypatch.setattr(routes, "delete_resource_if_not_used", lambda *_args, **_kwargs: _inc(called, "delete_if_unused"))
    monkeypatch.setattr(routes, "delete_resource_from_index", lambda *_args, **_kwargs: _inc(called, "index_delete"))

    async def _inc(store, key):
        store[key] += 1

    allusers = await routes.delete_resources(
        SimpleNamespace(), SimpleNamespace(id="admin", is_superuser=True, has_perm=lambda _perm: True),
        request, "acme", "widget", None, True, True,
    )
    assert allusers.status_code == 200
    assert called["delete"] == 1
    assert called["index_delete"] == 2

    called["uninstall"] = called["delete_if_unused"] = 0
    monkeypatch.setattr(routes, "get_catalogue_resource_by_id", _none)
    monkeypatch.setattr(routes, "get_user_catalogue_resource", lambda *_args, **_kwargs: _resource(resources[0]))

    async def _resource(value):
        return value

    one = await routes.delete_resources(
        SimpleNamespace(), SimpleNamespace(id="u1", is_superuser=False, has_perm=lambda _perm: True),
        request, "acme", "widget", "1.0.0", False, False,
    )
    assert one.status_code == 204
    assert called["uninstall"] == 1
    assert called["delete_if_unused"] == 1


async def test_massive_resource_update_branches(monkeypatch):
    req = _request("/api/resource/acme/widget/1.0.0")
    monkeypatch.setattr(routes, "build_error_response", lambda _request, status, _msg, details=None: Response(status_code=status))
    handler = routes.massive_resource_update.__wrapped__

    user_no_perm = SimpleNamespace(is_superuser=False, has_perm=lambda _perm: False)
    denied = await handler(SimpleNamespace(), req, user_no_perm, "acme", "widget", "1.0")
    assert denied.status_code == 403

    user_perm = SimpleNamespace(is_superuser=False, has_perm=lambda perm: perm == "COMPONENT.MASSIVE_UPDATE")

    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(routes, "get_catalogue_resource", _none)
    missing = await handler(SimpleNamespace(), req, user_perm, "acme", "widget", "1.0")
    assert missing.status_code == 404

    async def _unsupported(*_args, **_kwargs):
        return SimpleNamespace(type="other")

    monkeypatch.setattr(routes, "get_catalogue_resource", _unsupported)
    unsupported = await handler(SimpleNamespace(), req, user_perm, "acme", "widget", "1.0")
    assert unsupported.status_code == 422

    async def _supported(*_args, **_kwargs):
        return SimpleNamespace(type=routes.CatalogueResourceType.widget)

    async def _update(*_args, **_kwargs):
        return routes.MassiveUpdateResponse(
            resource_type="widget",
            total_workspaces_updated=2,
            total_resources_updated=3
        )

    monkeypatch.setattr(routes, "get_catalogue_resource", _supported)
    monkeypatch.setattr(routes, "update_all_workspaces_with_resources", _update)
    ok = await handler(SimpleNamespace(), req, user_perm, "acme", "widget", "1.0")
    assert isinstance(ok, routes.MassiveUpdateResponse)
    assert ok.total_resources_updated == 3
