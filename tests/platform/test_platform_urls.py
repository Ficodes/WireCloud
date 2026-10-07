# -*- coding: utf-8 -*-

import re

from wirecloud.main import app
from wirecloud.platform import urls
from wirecloud.platform.plugins import get_plugin_urls, URLTemplate


def test_platform_url_patterns_shape():
    assert "wirecloud.root" in urls.patterns
    assert "wirecloud.workspace_view" in urls.patterns
    assert "wirecloud.search_service" in urls.patterns

    root = urls.patterns["wirecloud.root"]
    context = urls.patterns["wirecloud.platform_context_collection"]
    workspace = urls.patterns["wirecloud.workspace_view"]

    assert isinstance(root, URLTemplate)
    assert root.urlpattern == "/"
    assert root.defaults == {}
    assert context.urlpattern == "/api/context/"
    assert workspace.urlpattern == "/workspace/{owner}/{name}"


def test_frontend_urls_use_canonical_trailing_slashes():
    def normalize(path):
        return re.sub(r"\{[^}]+\}", "{}", path).rstrip("/")

    route_paths = {route.path for route in app.routes}

    for name, template in get_plugin_urls().items():
        matching_routes = {path for path in route_paths if normalize(path) == normalize(template.urlpattern)}
        for route_path in matching_routes:
            assert template.urlpattern.endswith("/") == route_path.endswith("/"), name
