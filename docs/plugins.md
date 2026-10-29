# Creating plugins

Plugins extend WireCloud's behavior. They are appropriate for capabilities such as new HTTP endpoints, integration with an identity provider or marketplace, platform context values, component API extensions, proxy processing, initial data, or management commands. They are more invasive and less commonly needed than [themes](themes.md).

The plugin interface is currently a Python extension API rather than a separately versioned compatibility boundary. Pin the WireCloud version used to build a plugin, keep overrides small, and test the plugin again when upgrading WireCloud.

## How discovery works

For each module in `INSTALLED_APPS`, WireCloud tries to import `<module>.plugins` and discovers classes in that module that subclass `WirecloudPlugin`. `wirecloud.platform` is handled specially and installs the core plugin directly.

The same installed-app list is used during frontend generation to find an optional `plugin.ts`. Therefore:

- a backend-only plugin must be importable at application startup;
- a plugin with frontend code must also be importable and listed when `npm run build` generates its settings; and
- changing the installed plugin set requires an application restart and, when frontend assets change, a new frontend build.

## Minimal in-tree plugin

An in-tree plugin can use this layout:

```text
src/wirecloud/acme/
├── __init__.py
├── plugins.py
├── routes.py
├── plugin.ts
└── static/
    └── js/
        └── acme.js
```

`routes.py` defines an ordinary FastAPI router:

```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
async def status():
    return {"status": "ok"}
```

`plugins.py` connects it to WireCloud:

```python
from typing import Optional

from fastapi import FastAPI

from wirecloud.platform.plugins import WirecloudPlugin
from wirecloud.acme.routes import router


class AcmePlugin(WirecloudPlugin):
    features = {"Acme": "1.0.0"}

    def __init__(self, app: Optional[FastAPI]):
        super().__init__(app)
        if app is not None:
            app.include_router(router, prefix="/api/acme", tags=["Acme"])
```

WireCloud also constructs plugins without a FastAPI application while loading management commands and build settings. Always accept `Optional[FastAPI]` and guard route registration with `if app is not None`.

The feature name must be unique across all enabled plugins. Features are exposed to the platform and can satisfy requirements declared by widget and operator packages.

## Enable the plugin

Add the module to `INSTALLED_APPS` while retaining the required core apps. In the Docker environment format:

```text
WIRECLOUD_INSTALLED_APPS=wirecloud.commons,wirecloud.platform,wirecloud.catalogue,wirecloud.proxy,wirecloud.fiware,wirecloud.keycloak,wirecloud.acme
```

For source development, append `wirecloud.acme` to `INSTALLED_APPS` in the settings module used by both Python and the frontend generator. Run:

```bash
npm run build
PYTHONPATH=src python -m manage --help
PYTHONPATH=src python -m manage runserver --reload
```

Check `/openapi.json` or `/docs` for `/api/acme/status`, then call it directly.

!!! warning
    The current `generate_webpack_settings.py` normally reads the repository's `src/settings.py` during a source build. Setting only the runtime `WIRECLOUD_INSTALLED_APPS` variable is not enough to add a plugin's JavaScript to an already-built bundle. Ensure the plugin is in the build-time installed-app list before running `npm run build`.

## Optional frontend code

Backend-only plugins do not need `plugin.ts`. To add a script to selected bundles, create:

```typescript
const getScripts = (view: string): string[] => {
    if (view === "classic") {
        return ["js/acme.js"];
    }
    return [];
};

export default {
    get_scripts: getScripts,
    scripts_location: "js"
};
```

Paths returned by `get_scripts` are relative to the plugin's `static` directory. Use a plugin-specific subdirectory for assets to avoid collisions. The build combines scripts from installed plugins in installed-app order, so do not depend on another plugin's global variables unless that dependency and ordering are explicit.

Frontend code runs in every selected platform page and carries the same security risk as core code. Prefer API-driven UI or a widget when the feature does not need to alter WireCloud itself.

## Configuration validation

A plugin can validate and normalize its settings during application and management-command startup:

```python
def get_config_validators(self):
    def validate(settings, offline: bool) -> None:
        endpoint = getattr(settings, "ACME_ENDPOINT", "")
        if not endpoint:
            raise ValueError("ACME_ENDPOINT is required")

        if not offline:
            # Runtime-only checks may be performed here.
            pass

    return (validate,)
```

A validator may be synchronous or asynchronous. The `offline` flag is true for frontend settings generation; skip network calls and checks requiring running services in that mode. Do not put secrets into the frontend manifest or values returned to browser constants.

## Management commands

Plugins can add commands to `python -m manage`:

```python
async def acme_sync(_args):
    print("Synchronizing Acme data")


def get_management_commands(self, subparsers):
    subparsers.add_parser("acme-sync", help="Synchronize Acme data")
    return {"acme-sync": acme_sync}
```

Command names share one global namespace. Use a plugin-specific prefix and return the exact parser name as the dictionary key. Command handlers may be synchronous or asynchronous.

## Initial data

Override `populate` when the plugin needs idempotent initial data:

```python
async def populate(self, db, wirecloud_user) -> bool:
    # Create only records that do not already exist.
    # Return True when something changed.
    return False
```

This hook runs when an administrator executes `python -m manage populate`, not automatically at every startup. It receives a database session and WireCloud's internal `wirecloud` user. Make it safe to repeat and commit database work consistently with the existing CRUD helpers.

## Runtime resources

Use FastAPI's native router lifespan for background services, database indexes,
and other runtime resources. Attaching it to the router keeps startup and
shutdown beside the endpoints that need them:

```python
from contextlib import asynccontextmanager
from fastapi import APIRouter


@asynccontextmanager
async def lifespan(app):
    async with AcmeClient() as client:
        app.state.acme_client = client
        yield


router = APIRouter(lifespan=lifespan)
```

Register this router using `app.include_router(router)` in the plugin constructor,
as in the minimal example. FastAPI composes the router lifespans with WireCloud's
application lifespan: settings are validated first, resources start in router
registration order, and they close in reverse order before the database closes.
The same cleanup occurs if a later router fails to start. Runtime resources are
not opened during build or offline plugin discovery. A separate WireCloud
plugin lifecycle hook is unnecessary.

## Other extension hooks

Keep identity-provider handling in WireCloud's auth hooks;
resource plugins can register their audiences and scopes with
[`wirecloud.oauth2provider`](oauth2.md). That module provides authorization,
themeable consent and connection management, and scoped bearer verification.
The [MCP plugin](mcp.md) uses this public API; other plugins need no MCP dependency.

Override only the hooks the plugin needs:

| Hook | Contribution |
| --- | --- |
| `get_features` / `features` | Named platform capabilities and versions. |
| `get_platform_context_definitions` and current values | Values exposed through WireCloud context. |
| `get_platform_preferences`, `get_workspace_preferences`, `get_tab_preferences` | New preference definitions. |
| `get_constants` | JSON-serialized constants added to frontend bootstrap data. |
| `get_ajax_endpoints` | Symbolic endpoint templates added to frontend bootstrap data. |
| `get_urls` | Symbolic URL patterns used by URL generation; this does not mount a FastAPI route. |
| `get_templates` | Theme fragment paths required by a view. Each enabled theme must provide them. |
| `get_template_context_processors` | Extra values for server-rendered template context. |
| `get_widget_api_extensions`, `get_operator_api_extensions` | Scripts injected into components according to view and feature requirements. |
| `get_market_classes` | New marketplace manager types. |
| `get_proxy_processors` | Request/response processors around the WireCloud proxy. |
| `get_openapi_extra_schemas` | Additional schemas merged into OpenAPI components. |
| OIDC provider hooks | Authorization URL, token, user-info, and back-channel logout behavior. |

The base class in `wirecloud.platform.plugins` is the authoritative list for the installed version. Several hooks operate on internal models and serialization formats, so use bundled plugins such as `wirecloud.catalogue`, `wirecloud.fiware`, `wirecloud.keycloak`, and `wirecloud.proxy` as focused implementation examples.

## External Python packages

A backend plugin may live in a separately installed Python distribution if its application module and `plugins.py` are importable and its static/templates are included as package data. A frontend plugin additionally has to be installed in the Node build environment and present in the build-time installed-app list so Webpack can resolve `plugin.ts` and its assets.

For Docker, this usually means producing a derived multi-stage image that installs the plugin before the frontend and WireCloud wheel build, rather than installing it into a running container. Treat the application wheel, plugin package, frontend bundle, and settings as one versioned release unit.

## Test checklist

- Start WireCloud with and without the plugin enabled.
- Run settings validation in normal and offline/build modes.
- Verify new operations in `/openapi.json` and exercise authorization failures.
- Run every management command twice when it is intended to be idempotent.
- Run `populate` twice and confirm it does not duplicate data.
- Build every enabled theme and frontend view.
- Test component API extensions in both widgets and operators.
- Check proxy and identity hooks with failure, timeout, and logout paths.
- Confirm that disabling the plugin leaves no required templates, scripts, settings, or database assumptions behind.
