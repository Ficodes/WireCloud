"""Internal operation calls preserve defaults and surface response failures."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Body, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from wirecloud.commons.utils.operations import invoke_operation
from wirecloud.database import rollback


async def test_operation_defaults_and_explicit_arguments():
    async def operation(db, user, request, limit=Query(10), options=Body(None)):
        assert (db, user, request) == ("db", "user", "request")
        return {"limit": limit, "options": options}

    assert await invoke_operation(operation, "db", "user", "request", ignored=True) == {"limit": 10, "options": None}
    assert await invoke_operation(operation, "db", "user", "request", limit=3, options={"enabled": True}) == {
        "limit": 3, "options": {"enabled": True},
    }


@pytest.mark.parametrize("result, expected", [
    (None, {"ok": True}),
    (Response(status_code=204), {"ok": True}),
    (JSONResponse({"created": "resource"}, status_code=201), {"created": "resource"}),
    ({"values": (1, 2)}, {"values": [1, 2]}),
])
async def test_operation_success_responses(result, expected):
    async def operation():
        return result

    assert await invoke_operation(operation, None, None, None) == expected


@pytest.mark.parametrize("response, status, detail", [
    (JSONResponse({"description": "Already installed"}, status_code=409), 409, {"description": "Already installed"}),
    (Response("<html>Bad gateway</html>", status_code=502), 502, {"description": "WireCloud operation failed"}),
    (Response("unexpected text"), 500, "Unexpected operation response"),
])
async def test_operation_response_errors_remain_errors(response, status, detail):
    async def operation():
        return response

    with pytest.raises(HTTPException) as error:
        await invoke_operation(operation, None, None, None)
    assert error.value.status_code == status
    assert error.value.detail == detail


@pytest.mark.parametrize("in_transaction", [False, True])
async def test_rollback_aborts_and_restarts_only_an_active_transaction(in_transaction):
    calls = []
    session = SimpleNamespace(
        in_transaction=in_transaction,
        _session=SimpleNamespace(abort_transaction=AsyncMock(side_effect=lambda: calls.append("abort"))),
        start_transaction=AsyncMock(side_effect=lambda: calls.append("start")),
    )
    await rollback(session)
    assert calls == (["abort", "start"] if in_transaction else [])
