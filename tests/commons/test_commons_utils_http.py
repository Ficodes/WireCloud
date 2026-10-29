# -*- coding: utf-8 -*-

import inspect
from types import SimpleNamespace

import pytest
from fastapi import Request
from fastapi.responses import Response

from wirecloud.commons.utils import http
from wirecloud.platform.plugins import URLTemplate


def _request(path="/", query="", headers=None, root_path=""):
    raw_headers = []
    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode("latin-1"), value.encode("latin-1")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": path,
            "query_string": query.encode("latin-1"),
            "headers": raw_headers,
            "root_path": root_path,
            "scheme": "http",
            "server": ("example.org", 80),
            "client": ("127.0.0.1", 12345),
        }
    )


def test_error_response_builders_and_response_selection(monkeypatch):
    monkeypatch.setattr(http, "_", lambda text: text)
    req = _request(headers={"accept": "application/json"})

    # HTML renderer fallback path
    import wirecloud.platform.routes as platform_routes

    calls = {"n": 0}

    def _render(_request, page, title):
        calls["n"] += 1
        if calls["n"] == 1:
            raise http.NotFound("x")
        return Response(content=f"{page}:{title}".encode("utf-8"))

    monkeypatch.setattr(platform_routes, "render_wirecloud", _render)
    assert http.get_html_basic_error_response(req, "text/html", 404, {"error_msg": "x"}) == "500:Error"

    xml = http.get_xml_error_response(
        req,
        "application/xml",
        400,
        {"error_msg": "bad", "details": {"a": "x", "b": ["1", "2"]}},
    ).decode("utf-8")
    assert "<description>bad</description>" in xml
    assert "<a>x</a>" in xml
    assert "<element>1</element>" in xml

    xml_str = http.get_xml_error_response(req, "application/xml", 400, {"error_msg": "bad", "details": "msg"}).decode("utf-8")
    assert "<details>msg</details>" in xml_str

    class _SeqLike:
        def __len__(self):
            return 2

        def __getitem__(self, index):
            if index == 0:
                return "x"
            if index == 1:
                return "y"
            if index == "x":
                return "vx"
            if index == "y":
                return "vy"
            raise IndexError

    xml_seq = http.get_xml_error_response(
        req,
        "application/xml",
        400,
        {"error_msg": "bad", "details": {"c": _SeqLike()}},
    ).decode("utf-8")
    assert "<c><x>vx</x><y>vy</y></c>" in xml_seq

    json_body = http.get_json_error_response(req, "application/json", 400, {"error_msg": "bad", "details": {"x": 1}})
    assert '"description":"bad"' in json_body
    assert '"details":{"x":1}' in json_body
    assert http.get_plain_text_error_response(req, "text/plain", 400, {"error_msg": "bad"}) == "bad"

    formatters = {
        "application/json; charset=utf-8": lambda *_a: '{"ok":true}',
        "": lambda *_a: "fallback",
    }
    xhr_req = _request(headers={"x-requested-with": "XMLHttpRequest"})
    response = http.build_response(xhr_req, 200, {"x": 1}, formatters, headers={"X-Test": "1"})
    assert response.status_code == 200
    assert response.headers["x-test"] == "1"

    monkeypatch.setattr(http.mimeparser, "best_match", lambda *_a, **_k: "image/png")
    with pytest.raises(Exception, match="No suitable formatter found"):
        http.build_response(
            _request(headers={"accept": "image/png"}),
            200,
            {},
            {"application/json; charset=utf-8": lambda *_a: "{}", "": lambda *_a: "fallback"},
        )
    monkeypatch.setattr(http.mimeparser, "best_match", lambda supported, _accept: supported[0])

    built_error = http.build_error_response(req, 400, "bad", extra_formats={"text/custom": lambda *_a: "x"})
    assert built_error.status_code == 400
    assert built_error.body
    built_error2 = http.build_error_response(req, 400, "bad", context={"existing": "1"})
    assert built_error2.status_code == 400


async def test_http_wrappers_and_content_type(monkeypatch):
    original_get_content_type = http.get_content_type
    monkeypatch.setattr(http, "build_error_response", lambda _r, status, msg, **_k: SimpleNamespace(status_code=status, msg=msg))
    monkeypatch.setattr(http.mimeparser, "best_match", lambda supported, accept: supported[0] if accept != "image/png" else "")
    monkeypatch.setattr(http, "_", lambda text: text)

    @http.authentication_required(csrf=True)
    async def _auth_async():
        return {"ok": True}

    req = _request(headers={"accept": "application/json"})
    denied = await _auth_async(request=req, user=None)
    assert denied.status_code == 401
    ok = await _auth_async(request=req, user="u1")
    assert ok["ok"] is True

    @http.authentication_required(csrf=False)
    def _auth_sync():
        return {"sync": True}

    ok_sync = await _auth_sync(request=req, user="u2")
    assert ok_sync["sync"] is True

    @http.produces(["application/json; charset=utf-8"])
    async def _produces_async(request: Request):
        return {"mimetype": request.state.best_response_mimetype}

    produced = await _produces_async(request=req)
    assert produced["mimetype"] == "application/json; charset=utf-8"
    not_acceptable = await _produces_async(request=_request(headers={"accept": "image/png"}))
    assert not_acceptable.status_code == 406

    @http.produces(["application/json; charset=utf-8"])
    def _produces_sync(request: Request):
        return request.state.best_response_mimetype

    assert await _produces_sync(request=req) == "application/json; charset=utf-8"

    @http.consumes(["application/json"])
    async def _consumes_async(request: Request):
        return request.state.mimetype

    monkeypatch.setattr(http, "get_content_type", lambda _r: ("application/json", {}))
    assert await _consumes_async(request=req) == "application/json"
    monkeypatch.setattr(http, "get_content_type", lambda _r: ("text/plain", {}))
    unsupported = await _consumes_async(request=req)
    assert unsupported.status_code == 415

    @http.consumes(["application/json"])
    def _consumes_sync(request: Request):
        return request.state.mimetype

    monkeypatch.setattr(http, "get_content_type", lambda _r: ("application/json", {}))
    assert await _consumes_sync(request=req) == "application/json"

    monkeypatch.setattr(http, "get_content_type", original_get_content_type)
    assert http.get_content_type(_request(headers={"content-type": "application/json; charset=utf-8"}))[0] == "application/json"
    monkeypatch.setattr(http.mimeparser, "parse_mime_type", lambda *_a, **_k: (_ for _ in ()).throw(http.mimeparser.InvalidMimeType("x")))
    assert http.get_content_type(_request(headers={"content-type": "invalid"})) == ("", {})
    assert http.get_content_type(_request()) == ("", {})


def test_url_helpers_and_download_response(monkeypatch, tmp_path):
    original_build_error_response = http.build_error_response
    from wirecloud import settings
    req = _request(path="/x", root_path="/mount/")
    monkeypatch.setattr(settings, "FORCE_PROTO", None, raising=False)
    monkeypatch.setattr(settings, "FORCE_DOMAIN", None, raising=False)
    monkeypatch.setattr(settings, "FORCE_PORT", None, raising=False)
    assert http.get_current_scheme(req) == "http"

    secure_req = _request(path="/x")
    secure_req.scope["scheme"] = "https"
    assert http.get_current_scheme(secure_req) == "https"

    monkeypatch.setattr(settings, "FORCE_PROTO", "https", raising=False)
    assert http.get_current_scheme(req) == "https"
    monkeypatch.setattr(settings, "FORCE_PROTO", None, raising=False)

    assert http.force_trailing_slash("/a") == "/a/"
    assert http.force_trailing_slash("/a/") == "/a/"
    assert http.get_current_domain(req) == "example.org"
    monkeypatch.setattr(settings, "FORCE_PORT", 8080, raising=False)
    assert http.get_current_domain(req).endswith(":8080")
    monkeypatch.setattr(settings, "FORCE_PORT", None, raising=False)
    monkeypatch.setattr(settings, "FORCE_DOMAIN", "forced.example", raising=False)
    assert http.get_current_domain(req).startswith("forced.example")
    monkeypatch.setattr(settings, "FORCE_DOMAIN", None, raising=False)
    monkeypatch.setattr(http, "_servername", None)
    monkeypatch.setattr(http.socket, "getfqdn", lambda: "fqdn.example")
    assert http.get_current_domain(None) == "fqdn.example"
    assert http.get_current_domain(None) == "fqdn.example"

    import wirecloud.platform.plugins as platform_plugins

    monkeypatch.setattr(
        platform_plugins,
        "get_plugin_urls",
        lambda: {
            "wirecloud.root": URLTemplate(urlpattern="/", defaults={}),
            "wirecloud.item": URLTemplate(urlpattern="/items/{id}/{path:path}", defaults={}),
        },
    )

    rel = http.get_relative_reverse_url("wirecloud.item", req, id="1", path="a/b")
    assert rel == "/mount/items/1/a/b"
    req2 = _request(path="/x", root_path="/mount")
    rel2 = http.get_relative_reverse_url("wirecloud.item", req2, id="1", path="a/b")
    assert rel2 == "/mount/items/1/a/b"
    abs_url = http.get_absolute_reverse_url("wirecloud.item", req, id="1", path="a/b")
    assert abs_url.startswith("http://")

    resolved = http.resolve_url_name("/items/1/a/b")
    assert resolved[0] == "wirecloud.item"
    assert http.resolve_url_name("/unknown") is None

    with pytest.raises(ValueError):
        http.get_relative_reverse_url("unknown", req)

    assert http.iri_to_uri("/á b") == "/%C3%A1%20b"
    http.validate_url_param("u", "https://example.com", force_absolute=True, required=True)
    with pytest.raises(ValueError):
        http.validate_url_param("u", "", required=True)
    with pytest.raises(ValueError):
        http.validate_url_param("u", "/relative", force_absolute=True)
    with pytest.raises(ValueError):
        http.validate_url_param("u", "javascript:alert(1)", force_absolute=False)

    monkeypatch.setattr(http, "build_error_response", lambda _r, status, msg, **_k: SimpleNamespace(status_code=status, msg=msg))
    assert http.build_not_found_response(req).status_code == 404
    assert http.build_validation_error_response(req).status_code == 422
    assert http.build_auth_error_response(req).status_code == 401
    assert http.build_permission_denied_response(req, "no").status_code == 403
    monkeypatch.setattr(http, "build_error_response", original_build_error_response)

    monkeypatch.setattr(http, "get_absolute_reverse_url", lambda _name, _request: "http://root/")
    no_state = http.get_redirect_response(_request())
    assert no_state.headers["location"] == "http://root/"
    with_state = http.get_redirect_response(_request(query="state=/next"))
    assert with_state.headers["location"] == "http://root/next"
    abs_state = http.get_redirect_response(_request(query="state=https://dest/"))
    assert abs_state.headers["location"] == "http://root/"

    # Download response branches
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    file_path = base_dir / "f.txt"
    file_path.write_text("hello")

    redirect = http.build_downloadfile_response(req, "a/../b.txt", str(base_dir))
    assert redirect.status_code == 404
    redirected = http.build_downloadfile_response(req, "foo/../../f.txt", str(base_dir))
    assert redirected.status_code == 302

    not_found = http.build_downloadfile_response(req, "missing.txt", str(base_dir))
    assert not_found.status_code == 404

    monkeypatch.setattr(settings, "USE_XSENDFILE", False, raising=False)
    monkeypatch.setattr(http.mimetypes, "guess_type", lambda _p: (None, None))
    file_resp = http.build_downloadfile_response(req, "f.txt", str(base_dir))
    assert file_resp.status_code == 200
    monkeypatch.setattr(http.mimetypes, "guess_type", lambda _p: ("text/plain", None))
    file_resp2 = http.build_downloadfile_response(req, "f.txt", str(base_dir))
    assert file_resp2.status_code == 200

    monkeypatch.setattr(settings, "USE_XSENDFILE", True, raising=False)
    xsend = http.build_downloadfile_response(req, "f.txt", str(base_dir))
    assert xsend.headers["x-sendfile"].endswith("f.txt")

    assert isinstance(http.http_date(0), str)

    monkeypatch.setattr(http, "get_current_scheme", lambda _r=None: "https")
    monkeypatch.setattr(http, "get_current_domain", lambda _r=None: "example.org")
    static_plain = http.get_absolute_static_url("js/app.js", req, versioned=False)
    assert static_plain == "https://example.org/js/app.js"
    import wirecloud.platform.core.plugins as core_plugins
    monkeypatch.setattr(core_plugins, "get_version_hash", lambda: "v1")
    static_versioned = http.get_absolute_static_url("js/app.js", req, versioned=True)
    assert static_versioned.endswith("js/app.js?v=v1")


def test_generate_new_param_signature_cases():
    def handler_with_req(request: Request):
        return request

    sig = inspect.signature(handler_with_req)
    new_sig, name, existed = http.generate_new_param_signature(sig, "request", Request)
    assert existed is True
    assert name == "request"
    assert new_sig == sig

    def handler_with_name(request: str):
        return request

    sig2 = inspect.signature(handler_with_name)
    new_sig2, name2, existed2 = http.generate_new_param_signature(sig2, "request", Request)
    assert existed2 is False
    assert name2.startswith("_request_")
    assert any(p.annotation == Request for p in new_sig2.parameters.values())
