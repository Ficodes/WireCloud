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

from urllib.parse import urlparse, urlencode
from http.cookies import SimpleCookie
from fastapi import APIRouter, Depends, Path, Response, Request, WebSocket, WebSocketException, status
from fastapi.responses import StreamingResponse
from typing import Annotated, Optional, Union
import asyncio
import aiohttp
import base64
import hashlib
import logging
import inspect

from wirecloud.commons.auth.utils import UserDepNoCSRF, get_token_contents, get_user
from wirecloud.database import DBDep, DBSession, Id
from wirecloud.platform.workspace.crud import get_workspace_by_username_and_name, get_workspace_by_id
from wirecloud.proxy import docs
from wirecloud.proxy.schemas import ProxyRequestData
from wirecloud.proxy.utils import is_valid_response_header
from wirecloud.commons.utils.http import (build_error_response, resolve_url_name, iri_to_uri, get_current_domain,
                                              get_relative_reverse_url)
from wirecloud.commons.auth.schemas import UserAll
from wirecloud.platform.plugins import get_request_proxy_processors, get_response_proxy_processors
from wirecloud import settings
from wirecloud import docs as root_docs
from wirecloud.translation import gettext as _

router = APIRouter()
logger = logging.getLogger(__name__)

BLACKLISTED_HTTP_HEADERS = [
    'host', 'forwarded', 'x-forwarded-by',
    'x-forwarded-host', 'x-forwarded-port',
    'x-forwarded-proto', 'x-forwarded-server'
]


async def parse_request_headers(request: Union[Request, WebSocket], request_data: ProxyRequestData) -> None:
    if 'Transfer-Encoding' in request.headers and request.headers['Transfer-Encoding'] != 'identity' and not request_data.is_ws:
        raise ValueError("WireCloud doesn't support requests using the Transfer-Encoding header")

    for header in request.headers.items():
        header_name = header[0].lower()

        if header_name == 'content-length' and header[1] and not request_data.is_ws:
            # Only take into account request body if the request has a
            # Content-Length header (we don't support chunked requests)
            request_data.data = request.stream()
            request_data.headers["Content-Length"] = "%s" % header[1]
        elif header_name == 'cookie':
            cookie_parser = SimpleCookie(str(header[1]))
            if request_data.is_ws:
                for name in list(cookie_parser):
                    if name in ('token', 'csrf_token', 'wc_login_browser'):
                        del cookie_parser[name]
            request_data.cookies.update(cookie_parser)
        elif header_name not in BLACKLISTED_HTTP_HEADERS:
            request_data.headers[header_name] = header[1]

    if request_data.data is None and 'Content-Type' in request_data.headers:
        del request_data.headers['Content-Type']


async def parse_context_from_referer(db: DBSession, user: Optional[UserAll], request: Union[Request, WebSocket],
                                     request_method: str = "GET") -> ProxyRequestData:
    referrer = request.headers.get('Referer')
    if referrer is None:
        raise Exception()

    parsed_referrer = urlparse(referrer)
    if request.url.netloc != parsed_referrer[1]:
        raise Exception()

    referer_view = resolve_url_name(parsed_referrer.path)
    if referer_view is not None and referer_view[0] == 'wirecloud.workspace_view':
        workspace = await get_workspace_by_username_and_name(db, referer_view[1]['owner'], referer_view[1]['name'])
        if workspace is None or not await workspace.is_accessible_by(db, user):
            raise Exception()
    elif referer_view is not None and (referer_view[0] == 'wirecloud.showcase_media' or referer_view[0] == 'wirecloud|proxy'):
        if request_method not in ('GET', 'POST', 'WS'):
            raise Exception()

        workspace = None
    else:
        raise Exception()

    component_type = request.headers.get("Wirecloud-Component-Type", None)
    component_id = request.headers.get("Wirecloud-Component-Id", None)

    return ProxyRequestData(
        workspace=workspace,
        component_type=component_type,
        component_id=component_id
    )


async def parse_context_from_query(db: DBSession, user: Optional[UserAll], request: Union[Request, WebSocket],
                                   request_method: str = "GET") -> ProxyRequestData:
    query_params = request.query_params
    workspace_id = query_params.get('__wirecloud_workspace_id', None)
    if workspace_id is not None:
        workspace = await get_workspace_by_id(db, Id(workspace_id))
        if workspace is None or not await workspace.is_accessible_by(db, user):
            raise Exception()
    elif query_params.get('__wirecloud_workspace_owner') is not None and query_params.get('__wirecloud_workspace_name') is not None:
        workspace = await get_workspace_by_username_and_name(
            db, query_params['__wirecloud_workspace_owner'], query_params['__wirecloud_workspace_name'])
        if workspace is None or not await workspace.is_accessible_by(db, user):
            raise ValueError('Inaccessible workspace')
    else:
        if request_method not in ('GET', 'POST', 'WS'):
            raise Exception()

        workspace = None

    component_type = query_params.get('__wirecloud_component_type', None)
    component_id = query_params.get('__wirecloud_component_id', None)

    # Keep the ASGI connection URL immutable; filter the upstream query below.
    return ProxyRequestData(
        workspace=workspace,
        component_type=component_type,
        component_id=component_id,
        is_ws=request_method == "WS",
    )


def generate_ws_accept_header_from_key(key: str) -> str:
    # Generate the accept key using SHA-1 and base64 encoding
    accept_key = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
    return accept_key

class Proxy:
    async def read_ws_from_client(self, ws: WebSocket) -> tuple[str, Union[bytes, None], Union[bool, None], Union[tuple[int, str], None]]:
        try:
            # Receive data in text or binary mode
            data = await ws.receive()

            if data["type"] == "websocket.connect":
                return await self.read_ws_from_client(ws)
            elif data["type"] == "websocket.receive":
                if "bytes" in data and data["bytes"] is not None:
                    return 'client', data["bytes"], True, None
                else:
                    return 'client', data["text"], False, None
            elif data["type"] == "websocket.disconnect":
                return 'client', None, None, (data["code"], data.get("reason", ''))
        except Exception as e:
            return 'client', None, None, (1014, 'Gateway Error')

        return 'client', None, None, (1014, 'Gateway Error')


    async def read_ws_from_server(self, response: aiohttp.ClientWebSocketResponse) -> tuple[str, Union[bytes, None], Union[bool, None], Union[tuple[int, str], None]]:
        try:
            data = await response.receive()

            if data.type == aiohttp.WSMsgType.CLOSE:
                return 'server', None, None, (data.data, data.extra)
            elif data.type == aiohttp.WSMsgType.ERROR:
                return 'server', None, None, (1014, 'Connection Error')
            elif data.type == aiohttp.WSMsgType.CLOSED:
                return 'server', None, None, (1000, 'Gateway Disconnected')
            elif data.type == aiohttp.WSMsgType.BINARY or data.type == aiohttp.WSMsgType.TEXT:
                return 'server', data.data, data.type == aiohttp.WSMsgType.BINARY, None
            else:
                return 'server', None, None, (1014, 'Connection Error')
        except Exception:
            return 'server', None, None, (1014, 'Gateway Error')


    async def relay_websocket(self, request, session, request_data, db):
        # aiohttp and the ASGI server own their respective WebSocket handshakes.
        handshake = {'connection', 'upgrade', 'sec-websocket-key', 'sec-websocket-version',
                     'sec-websocket-accept', 'sec-websocket-protocol', 'sec-websocket-extensions'}
        headers = {key: value for key, value in request_data.headers.items() if key.lower() not in handshake}
        protocols = [value.strip() for value in request.headers.get('sec-websocket-protocol', '').split(',') if value.strip()]
        pending = set()
        async with session.ws_connect(
            url=request_data.url, headers=headers, protocols=protocols, timeout=60,
            ssl=getattr(settings, 'WIRECLOUD_HTTPS_VERIFY', True),
            max_msg_size=getattr(settings, 'PROXY_WS_MAX_MSG_SIZE', 4 * 1024 * 1024),
        ) as upstream:
            response_headers = {key.lower(): value for key, value in upstream._response.headers.items()}
            for processor in get_response_proxy_processors():
                if inspect.iscoroutinefunction(processor.process_response):
                    response_headers = await processor.process_response(db, request_data, response_headers)
                else:
                    response_headers = processor.process_response(db, request_data, response_headers)
            response_headers = [(key.encode(), value.encode()) for key, value in response_headers.items()
                                if key.lower() not in handshake | {'date', 'content-length', 'transfer-encoding'}]
            try:
                try:
                    await request.accept(subprotocol=upstream.protocol, headers=response_headers)
                except RuntimeError:
                    await upstream.close(code=1014, message=b'Client disconnected')
                    try:
                        await request.close(code=1014, reason='Client disconnected')
                    except RuntimeError:
                        pass
                    return
                pending = {asyncio.create_task(self.read_ws_from_client(request)),
                           asyncio.create_task(self.read_ws_from_server(upstream))}
                while pending:
                    done, pending = await asyncio.wait(list(pending), return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        source, data, binary, close = await task
                        if data is None:
                            code, reason = close or (1014, 'Gateway Error')
                            if code in (1005, 1006, 1015) or not isinstance(code, int):
                                code = 1000
                            if source == 'client':
                                await upstream.close(code=code, message=reason.encode())
                            else:
                                await request.close(code=code, reason=reason)
                            return
                        if source == 'client':
                            await (upstream.send_bytes(data) if binary else upstream.send_str(data))
                            pending.add(asyncio.create_task(self.read_ws_from_client(request)))
                        else:
                            await (request.send_bytes(data) if binary else request.send_text(data))
                            pending.add(asyncio.create_task(self.read_ws_from_server(upstream)))
            except RuntimeError:
                # A browser can disconnect between a receive and its paired send.
                await upstream.close(code=1014, message=b'Client disconnected')
            finally:
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)


    async def do_request(self, request: Union[Request, WebSocket], url: str, method: str, request_data: ProxyRequestData,
                         db: DBSession, user: Optional[UserAll] = None) -> Optional[Response]:
        url = iri_to_uri(url)

        request_data.method = method
        request_data.url = url
        request_data.original_request = request
        request_data.user = user

        # Build the Via header
        protocol_version = request.scope.get('http_version', '1.1')
        via_header = "%s %s (Wirecloud-python-Proxy/2.0)" % (protocol_version, get_current_domain(request))
        if 'via' in request_data.headers:
            request_data.headers['via'] += ', ' + via_header
        else:
            request_data.headers['via'] = via_header

        # XFF headers
        if 'x-forwarded-for' in request.headers:
            request_data.headers['x-forwarded-for'] += ', ' + request.client.host
        else:
            request_data.headers['x-forwarded-for'] = request.client.host

        # Pass proxy processors to the new request
        try:
            for processor in get_request_proxy_processors():
                if inspect.iscoroutinefunction(processor.process_request):
                    await processor.process_request(db, request_data)
                else:
                    processor.process_request(db, request_data)
        except Exception as e:
            if not request_data.is_ws:
                return build_error_response(request, 422, str(e))
            else:
                raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason=str(e))

        # Cookies
        cookie_header_content = ', '.join([request_data.cookies[key].OutputString() for key in request_data.cookies])
        if cookie_header_content != '':
            request_data.headers['Cookie'] = cookie_header_content

        session = None
        try:
            session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
            if not request_data.is_ws:
                res = await session.request(
                    method=request_data.method,
                    url=request_data.url,
                    headers=request_data.headers,
                    data=request_data.data,
                    timeout=60,
                    auto_decompress=False,
                    ssl=getattr(settings, 'WIRECLOUD_HTTPS_VERIFY', True)
                )
            else:
                await self.relay_websocket(request, session, request_data, db)
        except aiohttp.ServerTimeoutError as e:
            await session.close()
            if not request_data.is_ws:
                return build_error_response(request, 504, _('Gateway Timeout'), details=str(e))
            else:
                raise WebSocketException(code=status.WS_1014_BAD_GATEWAY, reason=_('Gateway Timeout'))
        except aiohttp.ClientSSLError as e:
            await session.close()
            if not request_data.is_ws:
                return build_error_response(request, 502, _('SSL error'), details=str(e))
            else:
                raise WebSocketException(code=status.WS_1014_BAD_GATEWAY, reason=_('SSL error'))
        except aiohttp.ClientError as e:
            await session.close()
            if not request_data.is_ws:
                return build_error_response(request, 502, _('Connection Error'), details=str(e))
            else:
                raise WebSocketException(code=status.WS_1014_BAD_GATEWAY, reason=_('Connection Error'))

        except BaseException:
            if session is not None:
                await session.close()
            raise

        if request_data.is_ws:
            await session.close()
            return None

        async def stream_response(s: aiohttp.ClientSession, r: aiohttp.ClientResponse):
            async for chunk in r.content.iter_any():
                yield chunk

            await s.close()

        response = StreamingResponse(stream_response(session, res), status_code=res.status)
        # Split URL into protocol, domain and path
        parsed_url = urlparse(url)
        protocol = parsed_url.scheme
        domain = parsed_url.netloc
        path = parsed_url.path

        for header in res.headers:
            header_lower = header.lower()
            if header_lower == 'set-cookie':
                for cookie in session.cookie_jar:
                    response.set_cookie(
                        key=cookie.key,
                        value=cookie.value,
                        path=cookie['path'] if cookie['path'] != '' else
                            get_relative_reverse_url('wirecloud|proxy', request=request, protocol=protocol,
                                                     domain=domain, path=path),
                        expires=cookie['expires']
                    )
            elif header_lower == 'via':
                via_header = via_header + ', ' + res.headers[header]
            elif is_valid_response_header(header_lower):
                response.headers[header] = res.headers[header]

        # Pass proxy processors to the response
        for processor in get_response_proxy_processors():
            if inspect.iscoroutinefunction(processor.process_response):
                response = await processor.process_response(db, request_data, response)
            else:
                response = processor.process_response(db, request_data, response)

        response.headers['Via'] = via_header

        return response


WIRECLOUD_PROXY = Proxy()


async def proxy_request(request: Request,
                        db: DBDep,
                        user: UserDepNoCSRF,
                        protocol: str = Path(description=docs.proxy_request_protocol_description, pattern='http|https'),
                        domain: str = Path(description=docs.proxy_request_domain_description, pattern='[A-Za-z0-9-.]+'),
                        path: str = Path(description=docs.proxy_request_path_description)) -> Response:
    request_method = request.method.upper()
    if protocol not in ('http', 'https'):
        return build_error_response(request, 422, _("Invalid protocol: %s") % protocol)

    if settings.PROXY_BLACKLIST_ENABLED and domain in settings.PROXY_BLACKLIST:
        return build_error_response(request, 403, _("Invalid request"))

    if settings.PROXY_WHITELIST_ENABLED and domain not in settings.PROXY_WHITELIST:
        return build_error_response(request, 403, _("Invalid request"))

    try:
        context = await parse_context_from_referer(db, user, request, request_method)
    except Exception:
        return build_error_response(request, 403, _("Invalid request"))

    url = protocol + '://' + domain + "/" + (path[1:] if path.startswith('/') else path)
    # Add query and fragment to the url
    for query_param in request.query_params.items():
        url += ('&' if '?' in url else '?') + query_param[0] + '=' + query_param[1]

    if request.url.fragment:
        url += '#' + request.url.fragment

    try:
        # Extract headers from META
        await parse_request_headers(request, context)

        response = await WIRECLOUD_PROXY.do_request(request, url, request_method, context, db, user)
    except ValueError as e:
        return build_error_response(request, 422, str(e))
    except Exception as e:
        msg = _("Error processing proxy request: %s") % e
        return build_error_response(request, 500, msg)

    return response


async def websocket_proxy_user(ws: WebSocket, db: DBDep) -> Optional[UserAll]:
    # Explicitly use the WebSocket connection, not an HTTP Request dependency.
    authorization = ws.headers.get('authorization', '')
    bearer = authorization[7:] if authorization.lower().startswith('bearer ') else None
    cookie = ws.cookies.get('token')
    if cookie and bearer is None:
        origin = urlparse(ws.headers.get('origin', ''))
        expected_scheme = 'https' if ws.url.scheme == 'wss' else 'http'
        if origin.scheme != expected_scheme or origin.netloc != ws.url.netloc:
            raise WebSocketException(code=1008, reason='Invalid WebSocket origin')
    credential = bearer if bearer is not None else cookie
    if not credential:
        return None
    token = await get_token_contents(credential, ws, db, csrf=False)
    user = await get_user(db, token, False)
    if user is None:
        raise WebSocketException(code=1008, reason='Invalid session')
    return user


async def proxy_ws_request(ws: WebSocket,
                           db: DBDep,
                           user: Annotated[Optional[UserAll], Depends(websocket_proxy_user)],
                           protocol: str = Path(description=docs.proxy_request_protocol_description, pattern='ws|wss'),
                           domain: str = Path(description=docs.proxy_request_domain_description, pattern=r'(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\])(?::[0-9]{1,5})?'),
                           path: str = Path(description=docs.proxy_request_path_description)):
    request_method = "WS"
    if protocol not in ('ws', 'wss'):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason=_("Invalid protocol: %s") % protocol)

    if settings.PROXY_BLACKLIST_ENABLED and domain in settings.PROXY_BLACKLIST:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason=_("Invalid request"))

    if settings.PROXY_WHITELIST_ENABLED and domain not in settings.PROXY_WHITELIST:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason=_("Invalid request"))

    # Browsers do not allow custom headers in websocket requests, so we have to accept the connection
    try:
        context = await parse_context_from_query(db, user, ws, request_method)
    except Exception:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason=_("Invalid request"))

    url = protocol + '://' + domain + "/" + (path[1:] if path.startswith('/') else path)
    internal = {'__wirecloud_workspace_id', '__wirecloud_workspace_owner', '__wirecloud_workspace_name',
                '__wirecloud_component_type', '__wirecloud_component_id'}
    query_items = ws.query_params.multi_items() if hasattr(ws.query_params, 'multi_items') else ws.query_params.items()
    query = urlencode([(key, value) for key, value in query_items if key not in internal])
    if query:
        url += '?' + query
    try:
        port = urlparse(url).port
        if port is not None and not 0 < port < 65536:
            raise ValueError()
    except ValueError:
        raise WebSocketException(code=1008, reason='Invalid upstream port')

    try:
        # Extract headers from META
        await parse_request_headers(ws, context)

        await WIRECLOUD_PROXY.do_request(ws, url, request_method, context, db, user)
    except ValueError as e:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason=str(e))
    except Exception as e:
        msg = _("Error processing proxy request: %s") % e
        raise WebSocketException(code=status.WS_1011_INTERNAL_ERROR, reason=msg)


for method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD']:
    router.add_api_route('/{protocol}/{domain}/{path:path}', proxy_request,
                     response_class=Response,
                     summary=docs.proxy_request_summary,
                     description=docs.proxy_request_description,
                     response_description=docs.proxy_request_response_description,
                     methods=[method],
                     responses={
                        403: root_docs.generate_permission_denied_response_openapi_description(
                             docs.proxy_request_permission_denied_description,
                            "Invalid request"),
                        422: root_docs.generate_validation_error_response_openapi_description(
                             docs.proxy_request_validation_error_description),
                        502: root_docs.generate_error_response_openapi_description(
                             docs.proxy_request_bad_gateway_description,
                             "Bad Gateway"),
                        504: root_docs.generate_error_response_openapi_description(
                             docs.proxy_request_gateway_timeout_description,
                             "Gateway Timeout")
                     })

router.add_api_websocket_route('/{protocol}/{domain}/{path:path}', proxy_ws_request)
