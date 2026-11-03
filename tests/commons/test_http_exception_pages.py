"""HTTP exceptions use themed pages for navigation and preserve API responses."""

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from wirecloud.commons.middleware import LocaleMiddleware
from wirecloud.commons.plugins import WirecloudCommonsPlugin


@pytest.fixture
async def error_client():
    app = FastAPI()
    WirecloudCommonsPlugin(app)
    app.add_middleware(LocaleMiddleware)

    @app.get("/http-error/{status}")
    async def raise_http_error(status: int):
        raise HTTPException(status, '<img src=x onerror="alert(1)">', headers={"X-Error": "preserved"})

    @app.get("/structured-error")
    async def raise_structured_error():
        raise HTTPException(401, {"error": "invalid_token"}, headers={"WWW-Authenticate": "Bearer"})

    @app.get("/bodyless-error")
    async def raise_bodyless_error():
        raise HTTPException(304, headers={"ETag": '"example"'})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        yield client


@pytest.mark.parametrize("status", [400, 401, 403, 404, 500])
async def test_http_exceptions_render_themed_browser_pages(error_client, status):
    response = await error_client.get(f"/http-error/{status}", headers={
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    assert response.status_code == status
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["x-error"] == "preserved"
    assert '<header id="wirecloud_header"' in response.text
    assert f"Error {status} -" in response.text
    assert '<img src=x' not in response.text
    if status == 400:
        assert "&lt;img src=x" in response.text


async def test_missing_route_uses_themed_404_and_escapes_requested_path(error_client):
    response = await error_client.get('/missing/<img src=x onerror="alert(1)">', headers={"Accept": "text/html"})
    assert response.status_code == 404
    assert "Error 404 - Not Found" in response.text
    assert '<img src=x' not in response.text
    assert "&lt;img" in response.text


async def test_http_exceptions_support_xhtml_navigation(error_client):
    response = await error_client.get("/http-error/403", headers={"Accept": "application/xhtml+xml"})
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/xhtml+xml")
    assert "Error 403 - Forbidden" in response.text


@pytest.mark.parametrize("headers", [
    {},
    {"Accept": "*/*"},
    {"Accept": "application/json"},
    {"Accept": "text/html;q=0.5,application/json"},
    {"Accept": "text/html", "X-Requested-With": "XMLHttpRequest"},
    {"Accept": "text/html;q=invalid"},
])
async def test_http_exceptions_preserve_json_details_and_headers(error_client, headers):
    response = await error_client.get("/structured-error", headers=headers)
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": {"error": "invalid_token"}}


async def test_router_errors_preserve_json_and_allow_header(error_client):
    missing = await error_client.get("/missing")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Not Found"}

    wrong_method = await error_client.post("/structured-error")
    assert wrong_method.status_code == 405
    assert wrong_method.headers["allow"] == "GET"
    assert wrong_method.json() == {"detail": "Method Not Allowed"}


async def test_bodyless_http_exception_remains_bodyless_for_browser_requests(error_client):
    response = await error_client.get("/bodyless-error", headers={"Accept": "text/html"})
    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["etag"] == '"example"'
