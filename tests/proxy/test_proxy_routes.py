# -*- coding: utf-8 -*-

import asyncio
from http.cookies import SimpleCookie
from types import SimpleNamespace
from urllib.parse import urlparse

import aiohttp
import pytest
from fastapi import Response, WebSocketException, status
from httpx import ASGITransport, AsyncClient

from wirecloud.proxy import routes
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


class _FakeURL:
    def __init__(self, raw):
        parsed = urlparse(raw)
        self.raw = raw
        self.netloc = parsed.netloc
        self.fragment = parsed.fragment

    def __str__(self):
        return self.raw


class _FakeRequest:
    def __init__(self, method="GET", url="https://wirecloud.example.org/path", headers=None, query_params=None):
        self.method = method
        self.url = _FakeURL(url)
        self.headers = headers or {}
        self.query_params = query_params or {}
        self.scope = {"http_version": "1.1"}
        self.client = SimpleNamespace(host="127.0.0.1")

    async def stream(self):
        if False:
            yield b""


class _FakeWebSocket:
    def __init__(self, url="wss://wirecloud.example.org/path", headers=None, query_params=None):
        self.url = _FakeURL(url)
        self.headers = headers or {}
        self.query_params = query_params or {}
        self.scope = {"http_version": "1.1"}
        self.client = SimpleNamespace(host="127.0.0.1")


async def test_parse_request_headers_transfer_encoding_and_cookie_cleanup():
    req = _FakeRequest(headers={"Transfer-Encoding": "chunked"})
    request_data = SimpleNamespace(is_ws=False, headers={}, cookies={}, data=None)

    with pytest.raises(ValueError, match="Transfer-Encoding"):
        await routes.parse_request_headers(req, request_data)

    async def _stream():
        yield b"body"

    req2 = _FakeRequest(headers={
        "content-length": "4",
        "cookie": "a=1; b=2",
        "host": "bad",
        "x-custom": "ok",
        "content-type": "text/plain",
    })
    req2.stream = _stream

    request_data2 = SimpleNamespace(is_ws=False, headers={}, cookies={}, data=None)
    await routes.parse_request_headers(req2, request_data2)

    assert request_data2.data is not None
    assert request_data2.headers["Content-Length"] == "4"
    assert request_data2.headers["x-custom"] == "ok"
    assert "host" not in request_data2.headers

    req3 = _FakeRequest(headers={"x-custom": "ok"})
    request_data3 = SimpleNamespace(is_ws=False, headers={"Content-Type": "text/plain"}, cookies={}, data=None)
    await routes.parse_request_headers(req3, request_data3)
    assert "Content-Type" not in request_data3.headers


async def test_parse_context_from_referer_paths(monkeypatch, db_session):
    monkeypatch.setattr(routes, "ProxyRequestData", lambda **kwargs: SimpleNamespace(**kwargs))

    async def _workspace(_db, _owner, _name):
        return SimpleNamespace(is_accessible_by=lambda db, user: _async_true())

    async def _async_true():
        return True

    monkeypatch.setattr(routes, "get_workspace_by_username_and_name", _workspace)

    req = _FakeRequest(
        method="GET",
        url="https://wirecloud.example.org/x",
        headers={
            "Referer": "https://wirecloud.example.org/workspace/alice/main",
            "Wirecloud-Component-Type": "widget",
            "Wirecloud-Component-Id": "w1",
        },
    )

    monkeypatch.setattr(routes, "resolve_url_name", lambda _path: ("wirecloud.workspace_view", {"owner": "alice", "name": "main"}))
    ctx = await routes.parse_context_from_referer(db_session, None, req, "GET")
    assert ctx.component_type == "widget"
    assert ctx.component_id == "w1"

    monkeypatch.setattr(routes, "resolve_url_name", lambda _path: ("wirecloud.showcase_media", {}))
    ctx2 = await routes.parse_context_from_referer(db_session, None, req, "POST")
    assert ctx2.workspace is None

    monkeypatch.setattr(routes, "resolve_url_name", lambda _path: ("wirecloud|proxy", {}))
    await routes.parse_context_from_referer(db_session, None, req, "GET")

    bad_req = _FakeRequest(url="https://wirecloud.example.org/x", headers={"Referer": "https://other.example.org/x"})
    with pytest.raises(Exception):
        await routes.parse_context_from_referer(db_session, None, bad_req, "GET")


async def test_parse_context_from_query_paths(monkeypatch, db_session):
    monkeypatch.setattr(routes, "ProxyRequestData", lambda **kwargs: SimpleNamespace(**kwargs))

    class _WS:
        async def is_accessible_by(self, _db, _user):
            return True

    monkeypatch.setattr(routes, "get_workspace_by_id", lambda _db, _id: _async_ws())

    async def _async_ws():
        return _WS()

    req = _FakeRequest(
        url="https://wirecloud.example.org/p?__wirecloud_workspace_id=507f1f77bcf86cd799439011&__wirecloud_component_type=widget&__wirecloud_component_id=w1&x=1",
        query_params={
            "__wirecloud_workspace_id": "507f1f77bcf86cd799439011",
            "__wirecloud_component_type": "widget",
            "__wirecloud_component_id": "w1",
            "x": "1",
        },
    )

    ctx = await routes.parse_context_from_query(db_session, None, req, "GET")
    assert ctx.component_type == "widget"
    assert ctx.component_id == "w1"
    # Context parsing must not assign to Starlette's read-only URL property.
    assert "__wirecloud_workspace_id" in str(req.url)
    assert ctx.is_ws is False

    req2 = _FakeRequest(url="https://wirecloud.example.org/p?x=1", query_params={"x": "1"})
    ctx2 = await routes.parse_context_from_query(db_session, None, req2, "POST")
    assert ctx2.workspace is None

    req3 = _FakeRequest(url="https://wirecloud.example.org/p?x=1", query_params={"x": "1"})
    with pytest.raises(Exception):
        await routes.parse_context_from_query(db_session, None, req3, "PUT")


async def test_generate_ws_accept_and_proxy_read_helpers():
    key = "dGhlIHNhbXBsZSBub25jZQ=="
    assert routes.generate_ws_accept_header_from_key(key) == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="

    proxy = routes.Proxy()

    class _WSClient:
        def __init__(self, items):
            self.items = list(items)

        async def receive(self):
            if not self.items:
                raise RuntimeError("boom")
            return self.items.pop(0)

    ws = _WSClient([
        {"type": "websocket.connect"},
        {"type": "websocket.receive", "text": "hi"},
    ])
    src, data, is_binary, close = await proxy.read_ws_from_client(ws)
    assert (src, data, is_binary, close) == ("client", "hi", False, None)

    ws2 = _WSClient([{"type": "websocket.receive", "bytes": b"x"}])
    assert await proxy.read_ws_from_client(ws2) == ("client", b"x", True, None)

    ws3 = _WSClient([{"type": "websocket.disconnect", "code": 1000, "reason": "bye"}])
    assert await proxy.read_ws_from_client(ws3) == ("client", None, None, (1000, "bye"))

    class _Msg:
        def __init__(self, typ, data=None, extra=""):
            self.type = typ
            self.data = data
            self.extra = extra

    class _WSServer:
        def __init__(self, msg):
            self.msg = msg

        async def receive(self):
            return self.msg

    class _BrokenWSServer:
        async def receive(self):
            raise RuntimeError("boom")

    assert (await proxy.read_ws_from_server(_WSServer(_Msg(aiohttp.WSMsgType.CLOSE, 1001, "bye")))) == ("server", None, None, (1001, "bye"))
    assert (await proxy.read_ws_from_server(_WSServer(_Msg(aiohttp.WSMsgType.ERROR)))) == ("server", None, None, (1014, "Connection Error"))
    assert (await proxy.read_ws_from_server(_WSServer(_Msg(aiohttp.WSMsgType.CLOSED)))) == ("server", None, None, (1000, "Gateway Disconnected"))
    assert (await proxy.read_ws_from_server(_WSServer(_Msg(aiohttp.WSMsgType.TEXT, "t")))) == ("server", "t", False, None)
    assert (await proxy.read_ws_from_server(_WSServer(_Msg(aiohttp.WSMsgType.PING)))) == ("server", None, None, (1014, "Connection Error"))
    assert (await proxy.read_ws_from_server(_BrokenWSServer())) == ("server", None, None, (1014, "Gateway Error"))

    ws4 = _WSClient([{"type": "unknown"}])
    assert await proxy.read_ws_from_client(ws4) == ("client", None, None, (1014, "Gateway Error"))

    ws5 = _WSClient([])
    assert await proxy.read_ws_from_client(ws5) == ("client", None, None, (1014, "Gateway Error"))


async def test_parse_context_from_referer_extra_errors(monkeypatch, db_session):
    monkeypatch.setattr(routes, "ProxyRequestData", lambda **kwargs: SimpleNamespace(**kwargs))

    req = _FakeRequest(url="https://wirecloud.example.org/x", headers={})
    with pytest.raises(Exception):
        await routes.parse_context_from_referer(db_session, None, req, "GET")

    monkeypatch.setattr(routes, "resolve_url_name", lambda _path: ("wirecloud.showcase_media", {}))
    req2 = _FakeRequest(url="https://wirecloud.example.org/x", headers={"Referer": "https://wirecloud.example.org/p"})
    with pytest.raises(Exception):
        await routes.parse_context_from_referer(db_session, None, req2, "PUT")

    monkeypatch.setattr(routes, "resolve_url_name", lambda _path: None)
    with pytest.raises(Exception):
        await routes.parse_context_from_referer(db_session, None, req2, "GET")

    monkeypatch.setattr(routes, "resolve_url_name", lambda _path: ("wirecloud.unknown", {}))
    with pytest.raises(Exception):
        await routes.parse_context_from_referer(db_session, None, req2, "GET")

    async def _none_workspace(*_args, **_kwargs):
        return None

    monkeypatch.setattr(routes, "resolve_url_name", lambda _path: ("wirecloud.workspace_view", {"owner": "alice", "name": "main"}))
    monkeypatch.setattr(routes, "get_workspace_by_username_and_name", _none_workspace)
    with pytest.raises(Exception):
        await routes.parse_context_from_referer(db_session, None, req2, "GET")


async def test_parse_context_from_query_inaccessible_workspace(monkeypatch, db_session):
    monkeypatch.setattr(routes, "ProxyRequestData", lambda **kwargs: SimpleNamespace(**kwargs))

    class _WS:
        async def is_accessible_by(self, _db, _user):
            return False

    async def _workspace(*_args, **_kwargs):
        return _WS()

    monkeypatch.setattr(routes, "get_workspace_by_id", _workspace)

    req = _FakeRequest(
        url="https://wirecloud.example.org/p?__wirecloud_workspace_id=507f1f77bcf86cd799439011",
        query_params={"__wirecloud_workspace_id": "507f1f77bcf86cd799439011"},
    )
    with pytest.raises(Exception):
        await routes.parse_context_from_query(db_session, None, req, "GET")


async def test_do_request_processor_failure_paths(monkeypatch, db_session):
    proxy = routes.Proxy()

    def _iri(url):
        return url

    monkeypatch.setattr(routes, "iri_to_uri", _iri)
    monkeypatch.setattr(routes, "get_current_domain", lambda _req: "wirecloud.example.org")

    class _Processor:
        async def process_request(self, _db, _request_data):
            raise RuntimeError("blocked")

    monkeypatch.setattr(routes, "get_request_proxy_processors", lambda: [_Processor()])

    req = _FakeRequest(headers={})
    request_data = SimpleNamespace(is_ws=False, headers={}, cookies={}, data=None)

    monkeypatch.setattr(routes, "build_error_response", lambda _request, code, msg: {"code": code, "msg": msg})
    res = await proxy.do_request(req, "https://api.example.org", "GET", request_data, db_session, None)
    assert res["code"] == 422

    ws = _FakeWebSocket(headers={})
    request_data_ws = SimpleNamespace(is_ws=True, headers={}, cookies={}, data=None)
    with pytest.raises(WebSocketException) as exc:
        await proxy.do_request(ws, "wss://api.example.org", "WS", request_data_ws, db_session, None)
    assert exc.value.code == status.WS_1008_POLICY_VIOLATION


async def test_do_request_http_success_and_error_handlers(monkeypatch, db_session):
    proxy = routes.Proxy()
    monkeypatch.setattr(routes, "iri_to_uri", lambda url: url)
    monkeypatch.setattr(routes, "get_current_domain", lambda _req: "wirecloud.example.org")
    class _ReqProcSync:
        def process_request(self, _db, _request_data):
            _request_data.headers["x-sync-proc"] = "1"

    monkeypatch.setattr(routes, "get_request_proxy_processors", lambda: [_ReqProcSync()])

    class _Cookie:
        key = "sid"
        value = "abc"

        def __getitem__(self, item):
            return {"path": "", "expires": "soon"}[item]

    class _Content:
        async def iter_any(self):
            yield b"x"

    class _Res:
        status = 201
        headers = {"Set-Cookie": "a=b", "Via": "upstream", "X-Test": "1", "Transfer-Encoding": "chunked"}
        content = _Content()

    class _Session:
        def __init__(self):
            self.cookie_jar = [_Cookie()]
            self.closed = False

        async def request(self, **kwargs):
            return _Res()

        async def close(self):
            self.closed = True

    monkeypatch.setattr(routes.aiohttp, "ClientSession", lambda **_kwargs: _Session())
    monkeypatch.setattr(routes, "get_relative_reverse_url", lambda *_args, **_kwargs: "/cdp/http/api/path")
    monkeypatch.setattr(routes, "is_valid_response_header", lambda h: h not in ("transfer-encoding",))

    class _RespProcSync:
        def process_response(self, _db, _request_data, response):
            response.headers["X-Processed"] = "sync"
            return response

    monkeypatch.setattr(routes, "get_response_proxy_processors", lambda: [_RespProcSync()])

    req = _FakeRequest(headers={"x-forwarded-for": "10.0.0.1"})
    cookies = SimpleCookie()
    cookies["sid"] = "abc"
    request_data = SimpleNamespace(is_ws=False, headers={"x-forwarded-for": "10.0.0.1"}, cookies=cookies, data=None)
    response = await proxy.do_request(req, "https://api.example.org/path", "GET", request_data, db_session, None)
    assert response.status_code == 201
    assert response.headers["X-Test"] == "1"
    assert response.headers["X-Processed"] == "sync"
    assert "upstream" in response.headers["Via"]
    assert request_data.headers["Cookie"].startswith("sid=abc")

    class _RespProcAsync:
        async def process_response(self, _db, _request_data, response):
            response.headers["X-Processed-Async"] = "1"
            return response

    monkeypatch.setattr(routes, "get_response_proxy_processors", lambda: [_RespProcAsync()])
    response2 = await proxy.do_request(req, "https://api.example.org/path", "GET", request_data, db_session, None)
    assert response2.headers["X-Processed-Async"] == "1"

    errors = []
    monkeypatch.setattr(routes, "build_error_response", lambda _req, code, msg, details=None: errors.append((code, msg, details)) or {"code": code})

    class _SessionTimeout:
        async def request(self, **kwargs):
            raise aiohttp.ServerTimeoutError("t")

        async def close(self):
            return None

    monkeypatch.setattr(routes.aiohttp, "ClientSession", lambda **_kwargs: _SessionTimeout())
    out = await proxy.do_request(req, "https://api.example.org/path", "GET", request_data, db_session, None)
    assert out["code"] == 504

    class _SessionSSL:
        async def request(self, **kwargs):
            conn_key = SimpleNamespace(ssl=True, host="api.example.org", port=443)
            raise aiohttp.ClientSSLError(conn_key, OSError("ssl"))

        async def close(self):
            return None

    monkeypatch.setattr(routes.aiohttp, "ClientSession", lambda **_kwargs: _SessionSSL())
    out2 = await proxy.do_request(req, "https://api.example.org/path", "GET", request_data, db_session, None)
    assert out2["code"] == 502

    class _SessionClientErr:
        async def request(self, **kwargs):
            raise aiohttp.ClientError("boom")

        async def close(self):
            return None

    monkeypatch.setattr(routes.aiohttp, "ClientSession", lambda **_kwargs: _SessionClientErr())
    out3 = await proxy.do_request(req, "https://api.example.org/path", "GET", request_data, db_session, None)
    assert out3["code"] == 502


async def test_do_request_ws_success_and_close_paths(monkeypatch, db_session):
    proxy = routes.Proxy()
    monkeypatch.setattr(routes, "iri_to_uri", lambda url: url)
    monkeypatch.setattr(routes, "get_current_domain", lambda _req: "wirecloud.example.org")
    monkeypatch.setattr(routes, "get_request_proxy_processors", lambda: [])
    monkeypatch.setattr(routes, "get_response_proxy_processors", lambda: [])
    monkeypatch.setattr(routes, "build_error_response", lambda *_args, **_kwargs: {"code": 422})

    class _ResponseHeaders:
        headers = {"Date": "now", "Sec-WebSocket-Accept": "server-accept", "X-Test": "1"}

    class _WSConn:
        protocol = "proto1"
        _response = _ResponseHeaders()

        async def close(self, **kwargs):
            return None

        async def send_bytes(self, _data):
            return None

        async def send_str(self, _data):
            return None

    class _WSCtx:
        def __init__(self):
            self.ws = _WSConn()

        async def __aenter__(self):
            return self.ws

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Session:
        def __init__(self):
            self.cookie_jar = []
            self.closed = False

        def ws_connect(self, **kwargs):
            return _WSCtx()

        async def close(self):
            self.closed = True

    monkeypatch.setattr(routes.aiohttp, "ClientSession", lambda **_kwargs: _Session())
    monkeypatch.setattr(proxy, "read_ws_from_server", lambda _ws: _done_tuple("server", None, None, (1000, "bye")))
    monkeypatch.setattr(proxy, "read_ws_from_client", lambda _request: _done_tuple("client", "hello", False, None))

    async def _wait(tasks, return_when=None):
        done = set()
        for t in tasks:
            done.add(routes.asyncio.ensure_future(t))
        return done, set()

    monkeypatch.setattr(routes.asyncio, "wait", _wait)

    class _WSReq(_FakeWebSocket):
        def __init__(self):
            super().__init__(headers={"Sec-WebSocket-Key": "key", "Sec-WebSocket-Protocol": "a, b"})
            self.accepted = False
            self.closed = False

        async def accept(self, subprotocol=None, headers=None):
            self.accepted = True

        async def close(self, code=None, reason=None):
            self.closed = True

        async def send_bytes(self, _data):
            return None

        async def send_text(self, _data):
            return None

    ws_request = _WSReq()
    request_data = SimpleNamespace(is_ws=True, headers={}, cookies={}, data=None)
    out = await proxy.do_request(ws_request, "wss://api.example.org/ws", "WS", request_data, db_session, None)
    assert out is None
    assert ws_request.accepted is True
    assert ws_request.closed is True


async def test_do_request_ws_accept_failure_and_ws_exception_handlers(monkeypatch, db_session):
    proxy = routes.Proxy()
    monkeypatch.setattr(routes, "iri_to_uri", lambda url: url)
    monkeypatch.setattr(routes, "get_current_domain", lambda _req: "wirecloud.example.org")
    monkeypatch.setattr(routes, "get_request_proxy_processors", lambda: [])

    class _RespProc:
        sponse = object()

        def process_response(self, _db, _request_data, headers_dict):
            headers_dict["x-processed"] = "1"
            return headers_dict

    monkeypatch.setattr(routes, "get_response_proxy_processors", lambda: [_RespProc()])

    class _ResponseHeaders:
        headers = {"X-Test": "1"}

    class _WSConn:
        protocol = "proto"
        _response = _ResponseHeaders()

        async def close(self, **kwargs):
            return None

        async def send_bytes(self, _data):
            return None

        async def send_str(self, _data):
            return None

    class _WSCtx:
        async def __aenter__(self):
            return _WSConn()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Session:
        def __init__(self):
            self.cookie_jar = []

        def ws_connect(self, **kwargs):
            return _WSCtx()

        async def close(self):
            return None

    monkeypatch.setattr(routes.aiohttp, "ClientSession", lambda **_kwargs: _Session())

    class _WSReq(_FakeWebSocket):
        def __init__(self):
            super().__init__(headers={})
            self.closed = False

        async def accept(self, subprotocol=None, headers=None):
            raise RuntimeError("cannot accept")

        async def close(self, code=None, reason=None):
            self.closed = True

    ws_req = _WSReq()
    request_data = SimpleNamespace(is_ws=True, headers={}, cookies={}, data=None)
    out = await proxy.do_request(ws_req, "wss://api.example.org/ws", "WS", request_data, db_session, None)
    assert out is None
    assert ws_req.closed is True

    class _SessionTimeout:
        def ws_connect(self, **kwargs):
            raise aiohttp.ServerTimeoutError("t")

        async def close(self):
            return None

    monkeypatch.setattr(routes.aiohttp, "ClientSession", lambda **_kwargs: _SessionTimeout())
    with pytest.raises(WebSocketException) as exc1:
        await proxy.do_request(ws_req, "wss://api.example.org/ws", "WS", request_data, db_session, None)
    assert exc1.value.code == status.WS_1014_BAD_GATEWAY

    class _SessionSSL:
        def ws_connect(self, **kwargs):
            conn_key = SimpleNamespace(ssl=True, host="api.example.org", port=443)
            raise aiohttp.ClientSSLError(conn_key, OSError("ssl"))

        async def close(self):
            return None

    monkeypatch.setattr(routes.aiohttp, "ClientSession", lambda **_kwargs: _SessionSSL())
    with pytest.raises(WebSocketException) as exc2:
        await proxy.do_request(ws_req, "wss://api.example.org/ws", "WS", request_data, db_session, None)
    assert exc2.value.code == status.WS_1014_BAD_GATEWAY

    class _SessionErr:
        def ws_connect(self, **kwargs):
            raise aiohttp.ClientError("err")

        async def close(self):
            return None

    monkeypatch.setattr(routes.aiohttp, "ClientSession", lambda **_kwargs: _SessionErr())
    with pytest.raises(WebSocketException) as exc3:
        await proxy.do_request(ws_req, "wss://api.example.org/ws", "WS", request_data, db_session, None)
    assert exc3.value.code == status.WS_1014_BAD_GATEWAY


async def test_do_request_ws_loop_branches_and_streaming_body(monkeypatch, db_session):
    proxy = routes.Proxy()
    monkeypatch.setattr(routes, "iri_to_uri", lambda url: url)
    monkeypatch.setattr(routes, "get_current_domain", lambda _req: "wirecloud.example.org")
    monkeypatch.setattr(routes, "get_request_proxy_processors", lambda: [])
    monkeypatch.setattr(routes, "get_response_proxy_processors", lambda: [])

    class _Content:
        async def iter_any(self):
            yield b"a"
            yield b"b"

    class _Res:
        status = 200
        headers = {"X-Test": "1"}
        content = _Content()

    class _WSConn:
        protocol = "proto"

        def __init__(self, headers):
            self._response = SimpleNamespace(headers=headers)
            self.closed = []
            self.sent = []

        async def close(self, code=None, message=None):
            self.closed.append((code, message))

        async def send_bytes(self, data):
            self.sent.append(("bytes", data))

        async def send_str(self, data):
            self.sent.append(("text", data))

    class _WSCtx:
        def __init__(self, ws):
            self.ws = ws

        async def __aenter__(self):
            return self.ws

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Session:
        def __init__(self, ws_headers):
            self.cookie_jar = []
            self.ws = _WSConn(ws_headers)
            self.closed = False

        async def request(self, **kwargs):
            return _Res()

        def ws_connect(self, **kwargs):
            return _WSCtx(self.ws)

        async def close(self):
            self.closed = True

    session_http = _Session({"X-Test": "1"})
    monkeypatch.setattr(routes.aiohttp, "ClientSession", lambda **_kwargs: session_http)
    req_http = _FakeRequest(headers={})
    request_data_http = SimpleNamespace(is_ws=False, headers={}, cookies=SimpleCookie(), data=None)
    response = await proxy.do_request(req_http, "https://api.example.org/path", "GET", request_data_http, db_session, None)
    body = b""
    async for chunk in response.body_iterator:
        body += chunk
    assert body == b"ab"
    assert session_http.closed is True

    session_ws = _Session({"X-Test": "1", "Sec-WebSocket-Accept": "server-value"})
    monkeypatch.setattr(routes.aiohttp, "ClientSession", lambda **_kwargs: session_ws)

    # hit 273 by sending websocket key when accept is already in headers
    class _WSReq(_FakeWebSocket):
        def __init__(self):
            super().__init__(headers={"sec-websocket-key": "dGhlIHNhbXBsZSBub25jZQ=="})
            self.closed = False

        async def accept(self, subprotocol=None, headers=None):
            return None

        async def close(self, code=None, reason=None):
            self.closed = True

        async def send_bytes(self, data):
            raise RuntimeError("client closed")

        async def send_text(self, data):
            return None

    ws_req = _WSReq()
    request_data_ws = SimpleNamespace(is_ws=True, headers={}, cookies=SimpleCookie(), data=None)

    async def _read_client(_request):
        return "client", None, None, (1000, "bye")

    async def _read_server(_ws):
        return "server", b"y", True, None

    monkeypatch.setattr(proxy, "read_ws_from_client", _read_client)
    monkeypatch.setattr(proxy, "read_ws_from_server", _read_server)

    async def _wait(tasks, return_when=None):
        # Drive both real tasks; the obsolete mock discarded a receive task and
        # could loop forever after the production relay correctly used Tasks.
        futures = {routes.asyncio.ensure_future(task) for task in tasks}
        await asyncio.gather(*futures)
        return futures, set()

    monkeypatch.setattr(routes.asyncio, "wait", _wait)
    out = await proxy.do_request(ws_req, "wss://api.example.org/ws", "WS", request_data_ws, db_session, None)
    assert out is None

    # hit 277 by omitting server accept header but keeping client websocket key
    session_ws2 = _Session({"X-Test": "1"})
    monkeypatch.setattr(routes.aiohttp, "ClientSession", lambda **_kwargs: session_ws2)

    async def _read_server_close(_ws):
        return "server", None, None, (1000, "bye")

    async def _read_client_data(_request):
        return "client", b"x", True, None

    monkeypatch.setattr(proxy, "read_ws_from_server", _read_server_close)
    monkeypatch.setattr(proxy, "read_ws_from_client", _read_client_data)

    out2 = await proxy.do_request(ws_req, "wss://api.example.org/ws", "WS", request_data_ws, db_session, None)
    assert out2 is None

    class _RespProcAsync:
        async def process_response(self, _db, _request_data, headers_dict):
            headers_dict["x-async"] = "1"
            return headers_dict

    session_ws3 = _Session({"X-Test": "1"})
    monkeypatch.setattr(routes.aiohttp, "ClientSession", lambda **_kwargs: session_ws3)
    monkeypatch.setattr(routes, "get_response_proxy_processors", lambda: [_RespProcAsync()])
    out3 = await proxy.do_request(ws_req, "wss://api.example.org/ws", "WS", request_data_ws, db_session, None)
    assert out3 is None


async def test_do_request_ws_loop_remaining_branches(monkeypatch, db_session):
    proxy = routes.Proxy()
    monkeypatch.setattr(routes, "iri_to_uri", lambda url: url)
    monkeypatch.setattr(routes, "get_current_domain", lambda _req: "wirecloud.example.org")
    monkeypatch.setattr(routes, "get_request_proxy_processors", lambda: [])
    monkeypatch.setattr(routes, "get_response_proxy_processors", lambda: [])

    class _WSConn:
        protocol = "proto"
        _response = SimpleNamespace(headers={"X-Test": "1"})

        async def close(self, **kwargs):
            return None

        async def send_bytes(self, _data):
            return None

        async def send_str(self, _data):
            return None

    class _WSCtx:
        async def __aenter__(self):
            return _WSConn()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Session:
        def __init__(self):
            self.cookie_jar = []

        def ws_connect(self, **kwargs):
            return _WSCtx()

        async def close(self):
            return None

    monkeypatch.setattr(routes.aiohttp, "ClientSession", lambda **_kwargs: _Session())
    monkeypatch.setattr(proxy, "read_ws_from_client", lambda _request: _done_tuple("client", "unused", False, None))
    monkeypatch.setattr(proxy, "read_ws_from_server", lambda _ws: _done_tuple("server", "unused", False, None))

    def _fut(value):
        f = routes.asyncio.get_running_loop().create_future()
        f.set_result(value)
        return f

    wait_calls = {"n": 0}
    pending_client_close = _fut(("client", None, None, (1000, "bye")))
    pending_client_bytes = _fut(("client", b"x", True, None))
    pending_server_text = _fut(("server", "svr", False, None))

    async def _wait(tasks, return_when=None):
        for task in tasks:
            if asyncio.iscoroutine(task):
                task.close() if asyncio.iscoroutine(task) else task.cancel()

        wait_calls["n"] += 1
        if wait_calls["n"] == 1:
            return {_fut(("client", "hello", False, None))}, {pending_server_text}
        if wait_calls["n"] == 2:
            return {pending_server_text}, {pending_client_bytes}
        if wait_calls["n"] == 3:
            return {pending_client_bytes}, {pending_client_close}
        return {pending_client_close}, set()

    monkeypatch.setattr(routes.asyncio, "wait", _wait)

    class _WSReq(_FakeWebSocket):
        def __init__(self):
            super().__init__(headers={})

        async def accept(self, subprotocol=None, headers=None):
            return None

        async def close(self, code=None, reason=None):
            raise RuntimeError("close failed")

        async def send_bytes(self, data):
            return None

        async def send_text(self, data):
            return None

    ws_req = _WSReq()
    request_data_ws = SimpleNamespace(is_ws=True, headers={}, cookies=SimpleCookie(), data=None)
    out = await proxy.do_request(ws_req, "wss://api.example.org/ws", "WS", request_data_ws, db_session, None)
    assert out is None


async def test_do_request_ws_direct_break_path(monkeypatch, db_session):
    proxy = routes.Proxy()
    monkeypatch.setattr(routes, "iri_to_uri", lambda url: url)
    monkeypatch.setattr(routes, "get_current_domain", lambda _req: "wirecloud.example.org")
    monkeypatch.setattr(routes, "get_request_proxy_processors", lambda: [])
    monkeypatch.setattr(routes, "get_response_proxy_processors", lambda: [])

    class _WSConn:
        protocol = "proto"
        _response = SimpleNamespace(headers={"X-Test": "1"})

        async def close(self, **kwargs):
            return None

        async def send_bytes(self, _data):
            return None

        async def send_str(self, _data):
            return None

    class _WSCtx:
        async def __aenter__(self):
            return _WSConn()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Session:
        def __init__(self):
            self.cookie_jar = []

        def ws_connect(self, **kwargs):
            return _WSCtx()

        async def close(self):
            return None

    monkeypatch.setattr(routes.aiohttp, "ClientSession", lambda **_kwargs: _Session())
    monkeypatch.setattr(proxy, "read_ws_from_client", lambda _request: _done_tuple("client", None, None, (1000, "bye")))
    monkeypatch.setattr(proxy, "read_ws_from_server", lambda _ws: _done_tuple("server", "unused", False, None))

    async def _wait(tasks, return_when=None):
        for task in tasks:
            if asyncio.iscoroutine(task):
                task.close() if asyncio.iscoroutine(task) else task.cancel()
        f = routes.asyncio.get_running_loop().create_future()
        f.set_result(("client", None, None, (1000, "bye")))
        return {f}, set()

    monkeypatch.setattr(routes.asyncio, "wait", _wait)

    class _WSReq(_FakeWebSocket):
        async def accept(self, subprotocol=None, headers=None):
            return None

        async def close(self, code=None, reason=None):
            return None

        async def send_bytes(self, data):
            return None

        async def send_text(self, data):
            return None

    ws_req = _WSReq(headers={})
    request_data_ws = SimpleNamespace(is_ws=True, headers={}, cookies=SimpleCookie(), data=None)
    out = await proxy.do_request(ws_req, "wss://api.example.org/ws", "WS", request_data_ws, db_session, None)
    assert out is None


async def _done_tuple(source, data, is_binary, close):
    return source, data, is_binary, close


async def test_proxy_request_http_validation_and_success_with_asgi_client(app_http_client, monkeypatch):
    routes.settings.PROXY_BLACKLIST_ENABLED = True
    routes.settings.PROXY_BLACKLIST = ["blocked.example.org"]
    routes.settings.PROXY_WHITELIST_ENABLED = False
    routes.settings.PROXY_WHITELIST = []

    bad = await app_http_client.get("/cdp/http/blocked.example.org/x")
    assert bad.status_code == 403

    routes.settings.PROXY_BLACKLIST_ENABLED = False
    routes.settings.PROXY_WHITELIST_ENABLED = True
    routes.settings.PROXY_WHITELIST = ["allowed.example.org"]
    bad2 = await app_http_client.get("/cdp/http/blocked.example.org/x")
    assert bad2.status_code == 403

    routes.settings.PROXY_WHITELIST_ENABLED = False

    async def _context(_db, _user, _request, _method):
        return SimpleNamespace(workspace=None, component_type="widget", component_id="w1", is_ws=False, headers={}, cookies={}, data=None)

    async def _headers(_request, _context):
        return None

    captured = {}

    async def _do_request(_request, _url, _method, _context, _db, _user):
        captured["url"] = _url
        captured["method"] = _method
        return Response(content="ok", status_code=200)

    monkeypatch.setattr(routes, "parse_context_from_referer", _context)
    monkeypatch.setattr(routes, "parse_request_headers", _headers)
    monkeypatch.setattr(routes.WIRECLOUD_PROXY, "do_request", _do_request)

    ok = await app_http_client.post("/cdp/https/api.example.org/v1?a=1")
    assert ok.status_code == 200
    assert ok.text == "ok"
    assert "a=1" in captured["url"]

    monkeypatch.setattr(routes, "parse_context_from_referer", lambda *_args, **_kwargs: (_ for _ in ()).throw(Exception("bad")))
    bad3 = await app_http_client.post("/cdp/https/api.example.org/v1")
    assert bad3.status_code == 403


async def test_proxy_ws_request_validation_and_success(monkeypatch, db_session):
    ws = _FakeWebSocket(url="wss://wirecloud.example.org/p#f", query_params={"a": "1"})

    async def _ws_context(_db, _user, _ws, _method):
        return SimpleNamespace(workspace=None, component_type="operator", component_id="o1", is_ws=True, headers={}, cookies={}, data=None)

    async def _do_request(_request, _url, _method, _context, _db, _user):
        return None

    monkeypatch.setattr(routes, "parse_context_from_query", _ws_context)
    monkeypatch.setattr(routes.WIRECLOUD_PROXY, "do_request", _do_request)

    await routes.proxy_ws_request(ws, db_session, None, protocol="wss", domain="api.example.org", path="ws")

    with pytest.raises(WebSocketException, match="Invalid protocol"):
        await routes.proxy_ws_request(ws, db_session, None, protocol="http", domain="api.example.org", path="ws")


async def test_proxy_request_http_error_wrappers_with_asgi_client(app_http_client, monkeypatch):
    routes.settings.PROXY_BLACKLIST_ENABLED = False
    routes.settings.PROXY_WHITELIST_ENABLED = False
    routes.settings.PROXY_WHITELIST = []
    routes.settings.PROXY_BLACKLIST = []

    bad_protocol = await app_http_client.get("/cdp/ws/api.example.org/x")
    assert bad_protocol.status_code == 422

    async def _context(*_args, **_kwargs):
        return SimpleNamespace(workspace=None, component_type="widget", component_id="w1", is_ws=False, headers={}, cookies={}, data=None)

    async def _value_error(*_args, **_kwargs):
        raise ValueError("invalid headers")

    monkeypatch.setattr(routes, "parse_context_from_referer", _context)
    monkeypatch.setattr(routes, "parse_request_headers", _value_error)
    bad_422 = await app_http_client.get("/cdp/http/api.example.org/x")
    assert bad_422.status_code == 422

    async def _generic_error(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(routes, "parse_request_headers", _generic_error)
    bad_500 = await app_http_client.get("/cdp/http/api.example.org/x")
    assert bad_500.status_code == 500


async def test_proxy_request_direct_unreachable_branches(monkeypatch, db_session):
    monkeypatch.setattr(routes, "build_error_response", lambda _request, code, msg, details=None: {"code": code, "msg": msg})
    routes.settings.PROXY_BLACKLIST_ENABLED = False
    routes.settings.PROXY_WHITELIST_ENABLED = False
    routes.settings.PROXY_WHITELIST = []
    routes.settings.PROXY_BLACKLIST = []

    req = _FakeRequest(method="GET", url="https://wirecloud.example.org/p", query_params={})
    bad = await routes.proxy_request(req, db_session, None, protocol="ws", domain="api.example.org", path="x")
    assert bad["code"] == 422

    async def _context(_db, _user, _request, _method):
        return SimpleNamespace(workspace=None, component_type="widget", component_id="w1", is_ws=False, headers={}, cookies={}, data=None)

    async def _headers(_request, _context):
        return None

    captured = {}

    async def _do_request(_request, _url, _method, _context, _db, _user):
        captured["url"] = _url
        return {"ok": True}

    monkeypatch.setattr(routes, "parse_context_from_referer", _context)
    monkeypatch.setattr(routes, "parse_request_headers", _headers)
    monkeypatch.setattr(routes.WIRECLOUD_PROXY, "do_request", _do_request)

    req2 = _FakeRequest(method="GET", url="https://wirecloud.example.org/p#frag", query_params={"a": "1"})
    ok = await routes.proxy_request(req2, db_session, None, protocol="https", domain="api.example.org", path="/v1")
    assert ok["ok"] is True
    assert captured["url"].endswith("#frag")


async def test_proxy_ws_request_error_wrappers(monkeypatch, db_session):
    ws = _FakeWebSocket(url="wss://wirecloud.example.org/p", query_params={})
    routes.settings.PROXY_BLACKLIST_ENABLED = True
    routes.settings.PROXY_BLACKLIST = ["api.example.org"]
    with pytest.raises(WebSocketException) as exc1:
        await routes.proxy_ws_request(ws, db_session, None, protocol="wss", domain="api.example.org", path="x")
    assert exc1.value.code == status.WS_1008_POLICY_VIOLATION

    routes.settings.PROXY_BLACKLIST_ENABLED = False
    routes.settings.PROXY_WHITELIST_ENABLED = True
    routes.settings.PROXY_WHITELIST = ["allowed.example.org"]
    with pytest.raises(WebSocketException) as exc2:
        await routes.proxy_ws_request(ws, db_session, None, protocol="wss", domain="api.example.org", path="x")
    assert exc2.value.code == status.WS_1008_POLICY_VIOLATION

    routes.settings.PROXY_WHITELIST_ENABLED = False
    monkeypatch.setattr(routes, "parse_context_from_query", lambda *_args, **_kwargs: (_ for _ in ()).throw(Exception("bad")))
    with pytest.raises(WebSocketException) as exc3:
        await routes.proxy_ws_request(ws, db_session, None, protocol="wss", domain="api.example.org", path="x")
    assert exc3.value.code == status.WS_1008_POLICY_VIOLATION

    async def _ws_context(*_args, **_kwargs):
        return SimpleNamespace(workspace=None, component_type="operator", component_id="o1", is_ws=True, headers={}, cookies={}, data=None)

    async def _value_error(*_args, **_kwargs):
        raise ValueError("invalid headers")

    async def _generic_error(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(routes, "parse_context_from_query", _ws_context)
    monkeypatch.setattr(routes, "parse_request_headers", _value_error)
    with pytest.raises(WebSocketException) as exc4:
        await routes.proxy_ws_request(ws, db_session, None, protocol="wss", domain="api.example.org", path="x")
    assert exc4.value.code == status.WS_1008_POLICY_VIOLATION

    monkeypatch.setattr(routes, "parse_request_headers", _generic_error)
    with pytest.raises(WebSocketException) as exc5:
        await routes.proxy_ws_request(ws, db_session, None, protocol="wss", domain="api.example.org", path="x")
    assert exc5.value.code == status.WS_1011_INTERNAL_ERROR
