# -*- coding: utf-8 -*-

from contextlib import asynccontextmanager

import pytest
from fastapi import APIRouter, FastAPI

from wirecloud import main


async def test_wirecloud_main_lifespan_calls_validate_and_close(monkeypatch):
    calls = {"validate": 0, "close": 0}

    async def _validate():
        calls["validate"] += 1

    async def _close():
        calls["close"] += 1

    monkeypatch.setattr(main, "validate_settings", _validate)
    monkeypatch.setattr(main, "close", _close)
    events = []
    @asynccontextmanager
    async def plugin_lifespan(app):
        events.append("start")
        try:
            yield
        finally:
            events.append("stop")
    application = FastAPI(lifespan=main.lifespan)
    application.include_router(APIRouter(lifespan=plugin_lifespan))

    async with application.router.lifespan_context(application):
        assert calls["validate"] == 1
        assert calls["close"] == 0
        assert events == ["start"]

    assert calls["close"] == 1
    assert events == ["start", "stop"]


@pytest.mark.parametrize("failure", [None, "startup", "shutdown"])
async def test_native_router_lifespans_unwind_before_database_close(monkeypatch, failure):
    events = []

    async def validate():
        events.append("validate")

    async def close():
        events.append("database-close")

    @asynccontextmanager
    async def first_router(app):
        events.append("first-start")
        try:
            yield
        finally:
            events.append("first-stop")

    @asynccontextmanager
    async def second_router(app):
        events.append("second-start")
        if failure == "startup":
            raise RuntimeError("startup")
        try:
            yield
        finally:
            events.append("second-stop")
            if failure == "shutdown":
                raise RuntimeError("shutdown")

    monkeypatch.setattr(main, "validate_settings", validate)
    monkeypatch.setattr(main, "close", close)
    application = FastAPI(lifespan=main.lifespan)
    application.include_router(APIRouter(lifespan=first_router))
    application.include_router(APIRouter(lifespan=second_router))

    async def serve():
        async with application.router.lifespan_context(application):
            events.append("serve")

    if failure:
        with pytest.raises(RuntimeError, match=failure):
            await serve()
    else:
        await serve()

    expected = ["validate", "first-start", "second-start"]
    if failure != "startup":
        expected.extend(["serve", "second-stop"])
    expected.extend(["first-stop", "database-close"])
    assert events == expected


def test_wirecloud_main_custom_openapi(monkeypatch):
    calls = {"openapi": 0}
    main.app.openapi_schema = None

    def _get_openapi(**_kwargs):
        calls["openapi"] += 1
        return {"info": {}, "components": {"schemas": {}}}

    monkeypatch.setattr(main, "get_openapi", _get_openapi)
    monkeypatch.setattr(main, "get_extra_openapi_schemas", lambda: {"Extra": {"type": "object"}})

    schema = main.custom_openapi()
    assert "x-logo" in schema["info"]
    assert "Extra" in schema["components"]["schemas"]
    assert calls["openapi"] == 1

    schema_cached = main.custom_openapi()
    assert schema_cached is schema
    assert calls["openapi"] == 1

    assert main.app.openapi == main.custom_openapi


def test_wirecloud_main_bootstrap_guards(monkeypatch):
    source_path = main.__file__
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    start = source.index("import sys")
    end = source.index("from contextlib import asynccontextmanager")
    padding = "\n" * source[:start].count("\n")
    bootstrap = padding + source[start:end]

    import builtins
    import types

    original_import = builtins.__import__
    fake_sys_low = types.SimpleNamespace(version_info=(3, 8), path=[])

    def _import_low(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "sys":
            return fake_sys_low
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import_low)
    g = {"__file__": source_path}
    with pytest.raises(Exception, match="Python 3.9"):
        exec(compile(bootstrap, source_path, "exec"), g, g)

    fake_sys = types.SimpleNamespace(version_info=(3, 9), path=[])

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "sys":
            return fake_sys
        if name == "wirecloud":
            raise ImportError("no wirecloud")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import)
    g2 = {"__file__": source_path}
    exec(compile(bootstrap, source_path, "exec"), g2, g2)
    assert len(fake_sys.path) == 1
