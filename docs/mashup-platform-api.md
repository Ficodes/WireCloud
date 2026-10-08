# FIWARE Application Mashup - Widget API Specification

The FIWARE Application Mashup - Widget API is the browser-side API available to
WireCloud widgets and operators. WireCloud exposes the specification through the
`MashupPlatform` JavaScript object. It provides access to wiring, preferences,
persistent variables, context, logging, HTTP requests, and selected workspace
operations.

This API is different from WireCloud's [HTTP API](api.md): `MashupPlatform`
runs inside a component and acts on that component's current workspace, while
the HTTP API is used by external clients and integrations.

The earlier
[FIWARE Application Mashup - Widget API Specification](https://wirecloud.readthedocs.io/en/latest/widgetapi/widgetapi/)
describes the original contract. This is the same API specification, updated
here for the current implementation and its additional methods and return
values.

## Availability

For classic components, WireCloud injects the API before the component's own
scripts run. Use the `MashupPlatform` object directly; do not access
`window.parent`, `Wirecloud`, or `MashupPlatform.priv`. Those are implementation
details and are deliberately hidden from component code.

MAC version 2 is the exception during class registration. Its descriptor-loaded
script must synchronously call one of:

```javascript
Wirecloud.registerWidgetClass(document.currentScript, WidgetClass);
Wirecloud.registerOperatorClass(document.currentScript, OperatorClass);
```

WireCloud then supplies the instance-specific `MashupPlatform` object to the
registered class's constructor. Do not use the global `Wirecloud` object for any
other component operation. See
[Registering MAC version 2 classes](components.md#mac-version-1-and-2) for the
complete widget and operator patterns, constructor signatures, timing rules,
and migration from the deprecated descriptor `entrypoint`.

The core surface depends on the component type:

| API | Widget | Operator | Extra requirement |
| --- | --- | --- | --- |
| `location`, `http`, `context`, `log`, `prefs`, `wiring` | Yes | Yes | None |
| `mashup.context` | Yes | Yes | None |
| `widget` | Yes | No | None |
| `operator` | No | Yes | None |
| Dynamic dashboard methods | Yes | Yes | `DashboardManagement` |
| `components` | Yes | Yes | `ComponentManagement` |

Declare optional API features in `config.xml`:

```xml
<requirements>
    <feature name="DashboardManagement"/>
    <feature name="ComponentManagement"/>
</requirements>
```

WireCloud validates requirements when installing a component. Administrators
and developers can inspect `/api/features` on a running instance to see the
available feature names and versions.

## Quick example

This widget reads a preference, accepts JSON through an input endpoint, makes a
request, and sends the result through an output endpoint:

```javascript
const endpoint = MashupPlatform.prefs.get("service_url");

MashupPlatform.wiring.registerCallback("query", async (rawValue) => {
    let query;
    try {
        query = JSON.parse(rawValue);
    } catch (error) {
        throw new MashupPlatform.wiring.EndpointTypeError(
            "query must be JSON"
        );
    }

    try {
        const response = await MashupPlatform.http.makeRequest(endpoint, {
            method: "GET",
            parameters: query,
            responseType: "json",
            supportsAccessControl: true
        });

        if (response.status < 200 || response.status >= 300) {
            throw new Error(`Service returned HTTP ${response.status}`);
        }

        MashupPlatform.wiring.pushEvent("result", response.response);
    } catch (error) {
        MashupPlatform.widget.log(String(error), MashupPlatform.log.ERROR);
    }
});
```

Endpoint and preference names must match those declared in `config.xml`.

## Component location

`MashupPlatform.location` is the component's base URL. Resolve packaged assets
against it instead of assuming a page-relative deployment path:

```javascript
const iconURL = new URL("images/icon.svg", MashupPlatform.location);
```

## HTTP requests

### `MashupPlatform.http.buildProxyURL`

```javascript
MashupPlatform.http.buildProxyURL(url, options)
```

Builds the URL WireCloud would use for a request. Cross-origin URLs use the
WireCloud proxy by default. The original URL is retained for same-origin calls,
`blob:` and `data:` URLs, and cross-origin calls where
`supportsAccessControl: true` allows direct CORS access. Set `forceProxy: true`
to require proxying.

```javascript
const imageURL = MashupPlatform.http.buildProxyURL(remoteURL, {
    method: "GET",
    forceProxy: true
});
```

The server can restrict proxy destinations with an allowlist or denylist. A URL
being syntactically valid does not guarantee that the deployment permits it.

### `MashupPlatform.http.makeRequest`

```javascript
MashupPlatform.http.makeRequest(url, options)
```

Sends an `XMLHttpRequest` directly or through the proxy and returns an abortable,
Promise-compatible request task. Pass an options object, even when no custom
options are needed:

```javascript
const response = await MashupPlatform.http.makeRequest("data.json", {});
```

The main request options are:

| Option | Meaning |
| --- | --- |
| `method` | HTTP method. The implementation defaults to `POST`. |
| `parameters` | Object or query string. Added to the URL for `GET`; used as the body of `PUT` or `POST` when `postBody` is absent. |
| `postBody` | Request body: string, `FormData`, `Blob`, `Document`, or an array-buffer view. |
| `contentType` | Request `Content-Type`. |
| `encoding` | Character encoding appended to `Content-Type`. |
| `requestHeaders` | Object mapping header names to values. |
| `responseType` | `""`, `"arraybuffer"`, `"blob"`, `"document"`, `"json"`, or `"text"`. |
| `supportsAccessControl` | Try a direct CORS request instead of the WireCloud proxy. |
| `withCredentials` | Include credentials on a direct CORS request. Use only with a trusted service. |
| `forceProxy` | Always route the request through WireCloud's proxy. |
| `context` | Value used as `this` for request callbacks. |

Callback-style code can use `onSuccess`, `onFailure`, `onComplete`, `onAbort`,
`onException`, `onUploadProgress`, `onProgress`, or a status-specific callback
such as `on404`:

```javascript
const request = MashupPlatform.http.makeRequest(serviceURL, {
    method: "POST",
    contentType: "application/json",
    postBody: JSON.stringify({enabled: true}),
    onSuccess(response) {
        MashupPlatform.widget.log("Saved", MashupPlatform.log.INFO);
    },
    onFailure(response) {
        MashupPlatform.widget.log(
            `Save failed: HTTP ${response.status}`,
            MashupPlatform.log.ERROR
        );
    }
});
```

When using promises, an HTTP response resolves the task even when its status is
outside the 2xx range. Inspect `response.status` yourself. The rejection path is
used for connection-level failures; aborting follows the WireCloud task abort
path.

The request object exposes `method`, `url`, `transport`, and `abort()`. A response
contains `request`, `transport`, `status`, `statusText`, and `response`.
`responseText` and `responseXML` are also available when `responseType` is empty.
Use `response.getHeader(name)` and `response.getAllResponseHeaders()` to inspect
response headers.

```javascript
const request = MashupPlatform.http.makeRequest(serviceURL, {method: "GET"});

document.querySelector("#cancel").addEventListener("click", () => {
    request.abort();
});
```

WireCloud adds internal component-identification headers and, for same-origin
requests, the current CSRF header. Do not depend on those internal headers from
component code.

## Context

Context managers expose information at three levels:

| Manager | Scope | Examples |
| --- | --- | --- |
| `MashupPlatform.context` | Platform and signed-in user | `username`, `language`, `groups`, `permissions`, `theme`, `mode` |
| `MashupPlatform.mashup.context` | Current workspace | `owner`, `name`, `title`, `editing`, `params` |
| `MashupPlatform.widget.context` | Current widget instance | `title`, `xPosition`, `yPosition`, `zPosition`, `width`, `height`, `widthInPixels`, `heightInPixels`, `visible`, `volatile` |

The widget-level manager exists only in widgets. The current operator API does
not expose `MashupPlatform.operator.context`; operators can still use platform
and mashup context. `width` and `height` are grid columns/rows on the active
screen size (`widthInPixels`/`heightInPixels` give the rendered pixel size);
`zPosition` is always `0` now that layout stacking has been removed.

Every context manager supports:

```javascript
manager.getAvailableContext()
manager.get(name)
manager.registerCallback(callback)
```

`getAvailableContext()` returns metadata keyed by context name, so prefer it to
hard-coding optional keys added by plugins. `get(name)` returns the current
value. The callback receives an object containing only changed values:

```javascript
const context = MashupPlatform.mashup.context;

if ("editing" in context.getAvailableContext()) {
    updateEditingState(context.get("editing"));

    context.registerCallback((changes) => {
        if ("editing" in changes) {
            updateEditingState(changes.editing);
        }
    });
}
```

Treat identity and permission context as display or adaptation information, not
as a client-side authorization boundary. The server must still enforce access.

## Preferences

Preferences are the user-configurable values declared in `config.xml`.

```javascript
MashupPlatform.prefs.get(name)
MashupPlatform.prefs.set(name, value)
MashupPlatform.prefs.set(values)
MashupPlatform.prefs.registerCallback(callback)
```

The current API supports setting one preference or several atomically from the
component's point of view:

```javascript
const pageSize = MashupPlatform.prefs.get("page_size");

MashupPlatform.prefs.set("page_size", 50);
MashupPlatform.prefs.set({
    page_size: 50,
    show_archived: false
});

MashupPlatform.prefs.registerCallback((changes) => {
    if ("page_size" in changes) {
        reloadPage(changes.page_size);
    }
});
```

Values are converted according to the descriptor type: number preferences are
numbers, boolean preferences are booleans, and text, password, and list
preferences are strings. An unknown name raises
`MashupPlatform.prefs.PreferenceDoesNotExistError`; a non-function callback or
invalid bulk value raises `TypeError`.

Do not store secrets in ordinary client-visible preferences. A password-style
control only masks the user interface. When WireCloud must retain a service
credential, declare the preference with `secure="true"` and use the server-side
proxy substitution mechanism instead of reading the credential in JavaScript.

## Persistent variables

Widgets and operators can read persistent variables declared in `config.xml`
through their type-specific module:

```javascript
const state = MashupPlatform.widget.getVariable("state");
// Inside an operator, use MashupPlatform.operator.getVariable("state").

if (state !== undefined) {
    const currentValue = state.get();
    state.set(JSON.stringify({selected: [1, 2, 3]}));
}
```

`getVariable(name)` returns `undefined` for an unknown variable. The returned
object has `get()` and `set(value)` methods. Serialize structured data explicitly
and handle missing or older stored formats during component upgrades.

## Wiring

### Declared endpoints

The core wiring API uses endpoint names declared in `config.xml`:

```javascript
MashupPlatform.wiring.registerCallback(inputName, callback)
MashupPlatform.wiring.pushEvent(outputName, data, options)
MashupPlatform.wiring.hasInputConnections(inputName)
MashupPlatform.wiring.hasOutputConnections(outputName)
MashupPlatform.wiring.getReachableEndpoints(outputName)
MashupPlatform.wiring.registerStatusCallback(callback)
```

Registering another callback for the same input replaces the previous callback.
Use `registerStatusCallback` to re-evaluate connection-dependent UI when the
wiring model is loaded or refreshed:

```javascript
function updateSendButton() {
    document.querySelector("#send").disabled =
        !MashupPlatform.wiring.hasOutputConnections("selection");
}

MashupPlatform.wiring.registerStatusCallback(updateSendButton);
updateSendButton();
```

`getReachableEndpoints(outputName)` is a current extension to the legacy API. It
returns target descriptors containing `type`, `id`, `endpoint`, and an
`actionlabel`. Pass selected descriptors back without modifying them through
`pushEvent`'s `targetEndpoints` option to deliver an event to only those targets:

```javascript
const targets = MashupPlatform.wiring.getReachableEndpoints("selection");

if (targets.length > 0) {
    MashupPlatform.wiring.pushEvent("selection", payload, {
        targetEndpoints: [targets[0]]
    });
}
```

Omitting `targetEndpoints` broadcasts to every connected target. Passing an
empty array sends to none.

Unknown endpoint names raise
`MashupPlatform.wiring.EndpointDoesNotExistError`. Input handlers can raise
`EndpointTypeError` when data has the wrong representation or
`EndpointValueError` when the representation is correct but its value is not:

```javascript
MashupPlatform.wiring.registerCallback("temperature", (value) => {
    const temperature = Number(value);
    if (!Number.isFinite(temperature)) {
        throw new MashupPlatform.wiring.EndpointTypeError(
            "temperature must be numeric"
        );
    }
    if (temperature < -273.15) {
        throw new MashupPlatform.wiring.EndpointValueError(
            "temperature is below absolute zero"
        );
    }
});
```

### Endpoint objects

Widgets expose `MashupPlatform.widget.inputs` and `.outputs`; operators expose
the equivalent `MashupPlatform.operator` dictionaries. Each entry has a
read-only `connected` property and supports programmatic connections:

```javascript
output.connect(input)
input.connect(output)
output.disconnect(input)
input.disconnect(output)
output.pushEvent(data)
```

Calling `disconnect()` without the opposite endpoint removes all removable
dynamic connections for that endpoint. User-created wiring is not intended to
be silently removed by component code.

## Logging and component-specific methods

Use the component log instead of relying only on the browser console:

```javascript
MashupPlatform.widget.log("Loaded", MashupPlatform.log.INFO);
MashupPlatform.operator.log("Retrying", MashupPlatform.log.WARN);
```

Available levels are `MashupPlatform.log.ERROR`, `.WARN`, and `.INFO`. The
`widget` and `operator` modules also expose their instance `id`, `inputs`,
`outputs`, `getVariable()`, and `log()`.

Widgets additionally provide:

- `MashupPlatform.widget.drawAttention()` to notify the user that the widget
  needs attention.
- `MashupPlatform.widget.close()` to remove the widget, but only when it is a
  volatile widget created by the dashboard-management API. Calling it on a
  normal workspace widget raises `TypeError`.

## Dashboard management feature

The following APIs exist only when `DashboardManagement` is declared in the
component requirements.

### Create dynamic endpoints

Widgets and operators can create endpoints not declared in the descriptor:

```javascript
const input = MashupPlatform.widget.createInputEndpoint((value) => {
    console.log(value);
});
const output = MashupPlatform.widget.createOutputEndpoint();
```

Use `MashupPlatform.operator.createInputEndpoint` and
`createOutputEndpoint` inside an operator. The returned endpoint objects support
the methods described above.

### Add temporary components

```javascript
const widget = MashupPlatform.mashup.addWidget(
    "Example/map/1.0.0",
    {
        title: "Result map",
        preferences: {basemap: {value: "light"}},
        properties: {},
        permissions: {close: true, move: true},
        x: 6,
        y: 0,
        w: 6,
        h: 8,
        titlevisible: true
    }
);

const operator = MashupPlatform.mashup.addOperator(
    "Example/normalizer/1.0.0",
    {
        preferences: {},
        properties: {},
        permissions: {close: true}
    }
);
```

References use `vendor/name/version` and must already be installed for the
current user. Added widgets and operators are volatile: they are not committed
to the workspace and are removed when the component that created them unloads.

`addWidget` accepts `x`, `y`, `w`, and `h` to place and size the widget in grid
columns/rows, as well as `width`/`height` as an alternative to `w`/`h` (a
pixel string such as `"400px"`, a percentage of the grid such as `"50%"`, or a
unitless number/string meaning legacy layout cells), and `titlevisible`. `top`
and `left` are no longer supported; a widget added without `x`/`y` is placed
automatically on the active screen size's grid.

The returned facades expose `inputs`, `outputs`, `addEventListener(name,
handler)`, and `remove()`. This allows a component to wire the instances:

```javascript
MashupPlatform.widget.outputs.entities.connect(operator.inputs.source);
operator.outputs.result.connect(widget.inputs.entities);
```

Connections between two endpoints belonging to the same component are rejected.

### Manage workspaces

```javascript
MashupPlatform.mashup.createWorkspace({
    name: "generated-dashboard",
    allowrenaming: true,
    onSuccess(workspace) {
        console.log(workspace.id, workspace.owner, workspace.name, workspace.url);
        workspace.open();
    },
    onFailure(message) {
        console.error(message);
    }
});
```

`createWorkspace(options)` accepts a `name`, a `mashup` reference, or an
`owner/name` workspace reference as a template, plus initial `preferences`.
Creation reports its result through `onSuccess` or `onFailure`.

Workspace facades expose `id`, `owner`, `name`, `url`, `open(options)`, and
`remove(options)`. Equivalent direct methods are:

```javascript
MashupPlatform.mashup.openWorkspace({owner: "alice", name: "operations"})
MashupPlatform.mashup.removeWorkspace({owner: "alice", name: "old-dashboard"})
```

Opening returns a task. Removing asks the user for confirmation before the
operation is performed. Both operations remain subject to server permissions.

## Component management feature

The `ComponentManagement` requirement adds:

```javascript
MashupPlatform.components.install(options)
MashupPlatform.components.uninstall(vendor, name, version)
MashupPlatform.components.isInstalled(vendor, name, version)
```

Install a package from a URL with:

```javascript
await MashupPlatform.components.install({
    url: "https://components.example.com/Example_map_1.0.0.wgt",
    install_embedded_resources: false
});
```

`install()` returns a task. Only use URLs controlled by a trusted component
publisher; installing a package introduces new browser code into WireCloud.

`uninstall(vendor, name, version)` returns a promise and is idempotent for an
already absent exact version. Omit `version` to uninstall every locally
available version. For `isInstalled`, pass a version string to check an exact
version or `null` to check whether any version is installed:

```javascript
if (MashupPlatform.components.isInstalled("Example", "map", "1.0.0")) {
    await MashupPlatform.components.uninstall("Example", "map", "1.0.0");
}

const anyVersion = MashupPlatform.components.isInstalled(
    "Example", "map", null
);
```

These operations act with the current user's permissions and can affect
component instances using the installed resource.

## Optional extension APIs

Requirements can also add APIs outside the `MashupPlatform` namespace:

- `StyledElements` provides WireCloud-themed controls to widgets. Classic
  widgets receive the compatibility surface automatically; declare the feature
  when the component contract depends on it.
- `NGSI` exposes the `NGSI` API when the `wirecloud.fiware` plugin is installed.
- `ObjectStorage` exposes the FIWARE object-storage integration when that plugin
  feature is installed.

Check `/api/features` and declare every feature the component requires. Do not
feature-detect only by catching a late runtime error: an explicit descriptor
requirement gives users a useful installation-time error.

## Error-handling checklist

- Validate and parse values arriving through wiring endpoints.
- Check HTTP status codes in Promise-based request code.
- Catch rejected network tasks and log a useful component-level message.
- Test for optional context keys with `getAvailableContext()`.
- Treat proxy responses, context values, preferences, and persistent variables
  as untrusted input before inserting them into the DOM.
- Do not retain access tokens or secrets in component JavaScript or persistent
  variables.
- Expect workspace, catalogue, and component-management operations to fail when
  the current user lacks permission.
