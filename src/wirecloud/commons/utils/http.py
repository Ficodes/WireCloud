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

import socket
from email.utils import formatdate
from inspect import Signature
import re
import mimetypes

import orjson as json
import inspect
import posixpath
import os
import random
import string
from functools import wraps
from lxml import etree
from fastapi import Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Union, Any
from collections.abc import Callable
from urllib.parse import urljoin, unquote, urlparse, quote

from wirecloud.commons.auth.utils import UserDepNoCSRF
from wirecloud.commons.utils import mimeparser
from wirecloud.translation import gettext as _


class HTTPError(BaseModel):
    description: str
    details: Union[str, dict[str, Any], None] = None


class XHTMLResponse(Response):
    media_type = 'application/xhtml+xml'


class PermissionDenied(Exception):
    pass


class NotFound(Exception):
    pass


def get_html_basic_error_response(request: Optional[Request], mimetype: str, status_code: int, context: dict) -> str:
    from wirecloud.platform.routes import render_wirecloud

    try:
        return render_wirecloud(request, page=f"{status_code}", title="Error").body.decode("utf-8")
    except NotFound:
        return render_wirecloud(request, page=f"500", title="Error").body.decode("utf-8")


def get_xml_error_response(request: Optional[Request], mimetype: str, status_code: int, context: dict) -> str:
    doc = etree.Element('error')

    description = etree.Element('description')
    description.text = str(context['error_msg'])

    doc.append(description)

    if context.get('details') is not None:
        details_element = etree.Element('details')
        if isinstance(context['details'], str):
            details_element.text = context['details']
        else:
            for key in context['details']:
                element = etree.Element(key)

                if isinstance(context['details'][key], str):
                    element.text = context['details'][key]
                elif hasattr(context['details'][key], '__iter__'):
                    for value in context['details'][key]:
                        list_element = etree.Element('element')
                        list_element.text = value
                        element.append(list_element)
                else:
                    for key2 in context['details'][key]:
                        list_element = etree.Element(key2)
                        list_element.text = context['details'][key][key2]
                        element.append(list_element)

                details_element.append(element)

        doc.append(details_element)

    return etree.tostring(doc, pretty_print=False, method='xml')


def get_json_error_response(request: Optional[Request], mimetype: str, status_code: int, context: dict) -> str:
    body = {
        'description': str(context['error_msg'])
    }
    if context.get('details') is not None:
        body['details'] = context['details']

    return json.dumps(body).decode("utf-8")


def get_plain_text_error_response(request: Optional[Request], mimetype: str, status_code: int, context: dict) -> str:
    return "%s" % context['error_msg']


ERROR_FORMATTERS = {
    'application/json; charset=utf-8': get_json_error_response,
    'application/xml; charset=utf-8': get_xml_error_response,
    'text/html; charset=utf-8': get_html_basic_error_response,
    'application/xhtml+xml; charset=utf-8': get_html_basic_error_response,
    'text/plain; charset=utf-8': get_plain_text_error_response,
    '': get_plain_text_error_response,  # Fallback
}


def build_response(request: Request, status_code: int, context: Union[dict[str, Any]], formatters: dict[str, Callable],
                   headers: dict[str, str] = None) -> Response:
    if request.headers.get('X-Requested-With', '') == 'XMLHttpRequest':
        content_type = 'application/json; charset=utf-8'
    else:
        formatter_keys = list(formatters.keys())
        formatter_keys.remove('')
        content_type = mimeparser.best_match(formatter_keys, request.headers.get('Accept', '*/*'))

    if content_type in formatters:
        formatter = formatters[content_type]
    else:
        raise Exception('No suitable formatter found')

    body = formatter(request, content_type, status_code, context)
    response = Response(content=body, status_code=status_code, media_type=content_type)
    if headers is None:
        headers = {}

    for header_name in headers:
        response.headers[header_name] = headers[header_name]

    return response


def build_error_response(request: Request, status_code: int, error_msg: str, extra_formats: dict = None,
                         headers: dict[str, str] = None, details: Union[str, dict[str, Any]] = None,
                         context: dict = None) -> Response:
    if extra_formats is not None:
        formatters = extra_formats.copy()
        formatters.update(ERROR_FORMATTERS)
    else:
        formatters = ERROR_FORMATTERS

    if context is None:
        context = {}

    context.update({'error_msg': error_msg, 'details': details})

    return build_response(request, status_code, context, formatters, headers)


def get_redirect_response(request: Request) -> Response:
    continuation = getattr(request.state, "login_return_to", None)
    if continuation is not None:
        return Response(status_code=302, headers={"Location": continuation})
    # Get query state
    query_state = request.query_params.get("state", None)
    if query_state is not None:
        if not query_state.startswith('/') or query_state.startswith('//') or '\\' in query_state or any(ord(c) < 32 for c in query_state):
            query_state = '/'
        # Redirect to the state URL, converting it to an absolute URL if necessary
        if query_state.startswith('/'):
            query_state = get_absolute_reverse_url('wirecloud.root', request) + query_state[1:]
        response = Response(status_code=302, headers={"Location": query_state})
    else:
        # Redirect to the main page
        response = Response(status_code=302, headers={"Location": get_absolute_reverse_url('wirecloud.root', request)})

    return response


def get_content_type(request: Request) -> tuple[str, dict[str, str]]:
    content_type_header = request.headers.get('Content-Type', None)
    if content_type_header is not None:
        try:
            return mimeparser.parse_mime_type(content_type_header)
        except mimeparser.InvalidMimeType:
            pass

    return '', {}


def build_not_found_response(request: Request) -> Response:
    return build_error_response(request, 404, 'Page Not Found')


def build_validation_error_response(request: Request) -> Response:
    return build_error_response(request, 422, 'Invalid Payload')


def build_auth_error_response(request: Request) -> Response:
    return build_error_response(request, 401, 'Authentication Required')


def build_permission_denied_response(request: Request, error_msg: str) -> Response:
    return build_error_response(request, 403, error_msg)


def generate_new_param_signature(sig: Signature, new_param_name: str, new_param_type: type,
                                 default_value: Any = inspect.Parameter.empty) -> tuple[Signature, str, bool]:
    params = list(sig.parameters.values())
    new_sig = sig

    # Check if a parameter with type new_param_type already exists
    new_param_exists = any(param.annotation == new_param_type for param in params)
    new_param_name_exists = any(param.name == f'{new_param_name}' and param.annotation != new_param_type for param in params)

    if new_param_name_exists and not new_param_exists:
        new_param_name = f"_{new_param_name}_"
        # Add extra text to the parameter name to avoid conflicts
        new_param_name += ''.join(random.choice(string.ascii_lowercase) for _ in range(10))

    if not new_param_exists:
        # Add a new parameter to the handler
        request_param = inspect.Parameter(new_param_name, inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                          annotation=new_param_type, default=default_value)
        params.insert(0, request_param)

        new_sig = sig.replace(parameters=params)
    else:
        # Find the parameter with the new_param_type
        new_param_name = [param.name for param in params if param.annotation == new_param_type][0]

    return new_sig, new_param_name, new_param_exists


def authentication_required(csrf: bool = True):
    from wirecloud.commons.auth.schemas import UserAll
    from wirecloud.commons.auth.utils import UserDep

    def wrap(handler):
        # Check that the handler has a user and request parameter
        new_sig, request_param, request_param_existed = generate_new_param_signature(inspect.signature(handler), 'request', Request)
        if csrf:
            new_sig, user_param, user_param_existed = generate_new_param_signature(new_sig, 'user', UserDep)
        else:
            new_sig, user_param, user_param_existed = generate_new_param_signature(new_sig, 'user', UserDepNoCSRF)

        @wraps(handler)
        async def wrapper(*args, **kwargs):
            user: Optional[UserAll] = kwargs.get(user_param) if user_param_existed else kwargs.pop(user_param)
            request: Request = kwargs.get(request_param) if request_param_existed else kwargs.pop(request_param)

            if user is None:
                return build_error_response(request, 401, 'Authentication Required')
            else:
                is_async = inspect.iscoroutinefunction(handler)

                if is_async:
                    return await handler(*args, **kwargs)
                else:
                    return handler(*args, **kwargs)

        wrapper.__signature__ = new_sig

        return wrapper

    return wrap


def produces(mime_types: list[str]):
    def wrap(handler):
        new_sig, request_param, request_param_existed = generate_new_param_signature(inspect.signature(handler), 'request', Request)

        @wraps(handler)
        async def wrapper(*args, **kwargs):
            request: Request = kwargs.get(request_param) if request_param_existed else kwargs.pop(request_param)

            accept_header = request.headers.get('Accept', '*/*')
            request.state.best_response_mimetype = mimeparser.best_match(mime_types, accept_header)

            if request.state.best_response_mimetype == '':
                msg = _("The requested resource is only capable of generating content not acceptable according to the Accept headers sent in the request")
                details = {'supported_mime_types': mime_types}
                return build_error_response(request, 406, msg, details=details)

            is_async = inspect.iscoroutinefunction(handler)

            if is_async:
                return await handler(*args, **kwargs)
            else:
                return handler(*args, **kwargs)

        wrapper.__signature__ = new_sig

        return wrapper

    return wrap


def consumes(mime_types: list[str]):
    def wrap(handler):
        new_sig, request_param, request_param_existed = generate_new_param_signature(inspect.signature(handler), 'request', Request)

        @wraps(handler)
        async def wrapper(*args, **kwargs):
            request: Request = kwargs.get(request_param) if request_param_existed else kwargs.pop(request_param)
            request.state.mimetype = get_content_type(request)[0]
            if request.state.mimetype not in mime_types:
                msg = _("Unsupported request media type")
                return build_error_response(request, 415, msg)

            is_async = inspect.iscoroutinefunction(handler)

            if is_async:
                return await handler(*args, **kwargs)
            else:
                return handler(*args, **kwargs)

        wrapper.__signature__ = new_sig

        return wrapper

    return wrap


_servername = None


def get_current_scheme(request: Optional[Request] = None) -> str:
    from wirecloud import settings

    if getattr(settings, 'FORCE_PROTO', None) is not None:
        return settings.FORCE_PROTO
    elif request is not None and request.url.is_secure:
        return 'https'
    else:
        return 'http'


def force_trailing_slash(url):
    return url if url[-1] == '/' else url + '/'


def get_current_domain(request: Optional[Request] = None) -> str:
    from wirecloud import settings

    # Server name
    if getattr(settings, 'FORCE_DOMAIN', None) is not None:
        servername = settings.FORCE_DOMAIN
    else:
        try:
            servername = request.url.hostname
        except Exception:
            global _servername
            if _servername is None:
                _servername = socket.getfqdn()
            servername = _servername

    # Port
    scheme = get_current_scheme(request)

    if getattr(settings, 'FORCE_PORT', None) is not None:
        port = int(settings.FORCE_PORT)
    else:
        try:
            port = request.url.port
        except Exception:
            port = 80 if scheme == 'http' else 443

    if port is not None and ((scheme == 'http' and port != 80) or (scheme == 'https' and port != 443)):
        return servername + (':%s' % port)
    else:
        return servername


def get_absolute_reverse_url(viewname: str, request: Optional[Request] = None, **kwargs) -> str:
    url = get_relative_reverse_url(viewname, request, **kwargs)

    return urljoin(get_current_scheme(request) + '://' + get_current_domain(request), url)


def get_relative_reverse_url(viewname: str, request: Optional[Request] = None, **kwargs) -> str:
    from wirecloud.platform.plugins import get_plugin_urls

    patterns = get_plugin_urls()
    if viewname not in patterns:
        raise ValueError('No URL pattern found for view "%s"' % viewname)

    url = patterns[viewname].urlpattern
    for key in kwargs:
        if '{' + f"{key}:path" + '}' in url:
            url = url.replace('{' + f"{key}:path" + '}', kwargs[key])
        else:
            url = url.replace('{' + key + '}', str(kwargs[key]))

    mount_path = request.scope.get("root_path") if request else ""
    if mount_path and mount_path[-1] == '/':
        mount_path = mount_path[:-1]

    return mount_path + url


def resolve_url_name(path: str) -> Optional[tuple[str, dict[str, str]]]:
    from wirecloud.platform.plugins import get_plugin_urls

    for name, url in get_plugin_urls().items():
        # Check if the pattern matches the path, to do so, convert the pattern to a regex
        pattern = re.escape(url.urlpattern).replace('\\{', '{').replace('\\}', '}')
        param_names = re.findall(r'\{([^/]+)}', pattern)
        pattern = re.sub(r'\{[^/]+:path}', r'(.+)', pattern)
        pattern = re.sub(r'\{[^/]+}', r'([^/]+)', pattern)
        pattern = '^' + pattern + '$'

        match = re.match(pattern, path)
        if match:
            param_values = match.groups()
            params = dict(zip(param_names, param_values))
            return name, params

    return None


def iri_to_uri(iri: str) -> str:
    return quote(iri, safe="/#%[]=:;$&()+,!?*@'~")


def validate_url_param(name: str, value: str, force_absolute: bool = True, required: bool = False):
    # FIXME Figure out if we can translate this, as it's not used in the same way the original code does
    if required and value.strip() == '':
        msg = 'Missing required parameter: %(parameter)s' % {"parameter": name}
        raise ValueError(msg)

    parsed_url = urlparse(value)
    if force_absolute and not bool(parsed_url.netloc and parsed_url.scheme):
        msg = "%(parameter)s must be an absolute URL" % {"parameter": name}
        raise ValueError(msg)
    elif parsed_url.scheme not in ('', 'http', 'https', 'ftp'):
        msg = "Invalid schema: %(schema)s" % {"schema": parsed_url.scheme}
        raise ValueError(msg)


def build_downloadfile_response(request: Request, file_path: str, base_dir: str) -> Response:
    from wirecloud import settings

    path = posixpath.normpath(unquote(file_path))
    path = path.lstrip('/')
    newpath = ''
    for part in path.split('/'):
        drive, part = os.path.splitdrive(part)
        head, part = os.path.split(part)
        if part in (os.curdir, os.pardir):
            # Strip '.' and '..' in path.
            continue
        newpath = os.path.join(newpath, part).replace('\\', '/')
    if newpath and path != newpath:
        return Response(status_code=302, headers={'Location': newpath})

    fullpath = os.path.join(base_dir, newpath)

    if not os.path.isfile(fullpath):
        return build_not_found_response(request)

    if not getattr(settings, 'USE_XSENDFILE', False):
        mime_type, _ = mimetypes.guess_type(fullpath)
        if mime_type is None:
            mime_type = 'application/octet-stream'
        return FileResponse(fullpath, media_type=mime_type)
    else:
        return Response(headers={'X-Sendfile': fullpath})


def http_date(timestamp: int) -> str:
    return formatdate(timestamp)


def get_absolute_static_url(url, request: Optional[Request] = None, versioned: bool = False):
    scheme = get_current_scheme(request)
    base = urljoin(scheme + '://' + get_current_domain(request), '/static')

    if versioned:
        from wirecloud.platform.core.plugins import get_version_hash
        url += f"?v={get_version_hash()}"

    return urljoin(base, url)
