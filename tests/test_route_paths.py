"""Route assertions must include nested prefixes and hidden endpoints."""
from fastapi import APIRouter, FastAPI


def test_registered_route_paths_preserve_prefixes_and_hidden_routes(registered_route_paths):
    async def endpoint():
        return {}

    child = APIRouter()
    child.add_api_route("/hidden/", endpoint, include_in_schema=False)
    parent = APIRouter()
    parent.include_router(child, prefix="/nested")
    app = FastAPI()
    app.include_router(parent, prefix="/first")
    app.include_router(parent, prefix="/second")
    app.add_api_route("/direct/", endpoint)
    app.mount("/static", FastAPI())

    paths = registered_route_paths(app)
    assert {"/first/nested/hidden/", "/second/nested/hidden/", "/direct/", "/static"} <= paths
    assert "/hidden/" not in paths
    assert "/nested/hidden/" not in paths
