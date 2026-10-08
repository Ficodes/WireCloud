# Component development

Widgets and operators use the same package format as earlier WireCloud releases. A component is a ZIP archive conventionally named with the `.wgt` extension, with `config.xml` at the archive root.

## Widget and operator roles

A widget has a visual HTML entry point and runs in the browser. An operator has no visual entry point and is normally used for service access, data transformation, or data delivery. Both can declare preferences, persistent variables, requirements, and wiring endpoints.

Keep components focused and reusable. Put service-specific or transformation logic in an operator when that lets the visual widget remain independent of its data source.

## Package layout

A typical widget contains:

```text
my-widget/
├── config.xml
├── index.html
├── css/
│   └── styles.css
├── js/
│   └── main.js
├── images/
│   └── catalogue.png
└── docs/
    └── user-guide.md
```

Paths referenced by `config.xml` are relative to the package root. Do not wrap these files in an extra top-level directory when creating the archive.

## Understanding `config.xml`

`config.xml` is the package manifest and the Mashable Application Component
Description Language (MACDL) document. WireCloud validates it against its XML
schema and then performs additional semantic checks. It controls:

- the resource identity and catalogue metadata;
- which optional platform features must be present;
- the settings and persistent state owned by each component instance;
- the wiring contract exposed to other components;
- the widget HTML or operator scripts to load; and
- for mashup templates, the tabs, component instances, layout, and connections
  used to create a workspace.

The current schema is available in the repository as
[`xml_schema.xsd`](https://github.com/Wirecloud/wirecloud/blob/main/src/wirecloud/commons/utils/template/schemas/xml_schema.xsd).
The older [MACDL XML reference](https://wirecloud.readthedocs.io/en/stable/development/macdl_xml/)
is useful background, but the rules below follow the current parser.

### Root element, namespace, and identity

The root element identifies the package type: `widget`, `operator`, or `mashup`.
It must use the exact MACDL namespace:

```xml
<widget xmlns="http://wirecloud.conwet.fi.upm.es/ns/macdescription/1"
        vendor="Example"
        name="hello-world"
        version="1.0.0">
    <!-- descriptor sections -->
</widget>
```

The three required attributes form the stable resource identifier
`vendor/name/version`:

| Attribute | Rule |
| --- | --- |
| `vendor` | Publisher or distribution namespace. It cannot contain `/`. |
| `name` | Stable component name. It cannot contain `/`. |
| `version` | Dot-separated numeric release with an optional `aN`, `bN`, or `rcN` prerelease and optional `-dev...` suffix. |

Valid versions include `1`, `1.0.0`, `2.4rc1`, and `3.0-dev5`. Values such as
`v1.0`, `01.2`, and `1.0-rc1` do not match the current version grammar.

Changing the title does not create a new resource. Changing behavior that an
existing workspace may depend upon should use a new `version`. Changing
`vendor` or `name` creates a different component family and prevents normal
upgrade/downgrade handling.

### MAC version 1 and 2

`macversion` selects the component execution model and accepts only `1` or `2`.
It defaults to `1` when omitted.

```xml
<macversion>1</macversion>
```

MAC version 1 is the compatibility model used by existing components:

- widgets run their `contents` document in an iframe;
- widget scripts are referenced from that HTML document, so a `<scripts>` block
  in a version 1 widget is rejected;
- operators list their JavaScript files in `<scripts>`; and
- the FIWARE Application Mashup - Widget API is exposed as the global
  `MashupPlatform` object.

MAC version 2 uses a registered component class:

- widgets still require a `contents` HTML document, but WireCloud renders it in
  a Shadow DOM and loads the JavaScript files declared by `<scripts>`;
- operators also load the declared scripts without a visual document; and
- the component script registers the class that WireCloud instantiates with
  `Wirecloud.registerWidgetClass` or `Wirecloud.registerOperatorClass`.

A version 2 widget descriptor includes:

```xml
<macversion>2</macversion>
<contents src="index.html" useplatformstyle="true"/>
<scripts>
    <script src="js/widget.js"/>
</scripts>
<rendering width="400px" height="300px"/>
```

`js/widget.js` defines the class and registers it immediately:

```javascript
(() => {
    class ExampleWidget {
        constructor(MashupPlatform, shadowRoot, container) {
            this.api = MashupPlatform;
            this.root = shadowRoot;
            this.root.querySelector("#send").addEventListener("click", () => {
                this.api.wiring.pushEvent("clicked", "hello");
            });
        }
    }

    Wirecloud.registerWidgetClass(document.currentScript, ExampleWidget);
})();
```

`document.currentScript` is important. WireCloud adds a `data-id` containing the
component's full `vendor/name/version` URI to each descriptor-loaded script. The
registration function reads that value and associates the class with the right
component. Do not pass a script selected with `querySelector`, construct a fake
script element, or pass the component URI as a string.

Call the registration function synchronously while the descriptor-loaded script
is executing. After a timer, promise callback, dynamic import, or other deferred
operation, `document.currentScript` is normally `null` and registration cannot
identify the component. Class methods can still perform asynchronous work, but
the registration call itself must run during the initial synchronous execution
of the loaded script.

#### Registering a version 2 widget

Use this signature:

```javascript
Wirecloud.registerWidgetClass(document.currentScript, WidgetClass);
```

WireCloud creates a separate `WidgetClass` instance for each widget instance and
calls its constructor as:

```javascript
new WidgetClass(MashupPlatform, shadowRoot, container);
```

- `MashupPlatform` is the FIWARE Application Mashup - Widget API object tailored
  to that widget instance.
- `shadowRoot` is the widget's Shadow DOM root. Query and update widget content
  through this root rather than the platform document.
- `container` holds `MashupPlatform` and any extra objects installed by declared
  requirements, such as `container.StyledElements`. It is mainly useful when a
  feature exposes an additional top-level API object.

Keep mutable state on `this`. Descriptor scripts are shared when several
instances use the same component version, whereas the class is instantiated
once per widget instance. Top-level mutable variables would therefore leak state
between instances.

#### Registering a version 2 operator

An operator uses the equivalent registration function:

```javascript
(() => {
    class NormalizerOperator {
        constructor(MashupPlatform, container) {
            this.api = MashupPlatform;

            this.api.wiring.registerCallback("source", (value) => {
                const normalized = String(value).trim();
                this.api.wiring.pushEvent("result", normalized);
            });
        }
    }

    Wirecloud.registerOperatorClass(
        document.currentScript,
        NormalizerOperator
    );
})();
```

WireCloud calls the constructor as
`new OperatorClass(MashupPlatform, container)`. Operators have no `shadowRoot`
because they have no visual document. As with widgets, put instance state on
`this` and use the supplied `MashupPlatform` object rather than a global one.

The registration call is the one supported use of the global `Wirecloud` object
inside a version 2 component. Do not retain it, inspect its internals, or use it
as a substitute for `MashupPlatform`.

When a component has several scripts, list dependencies before the class script
and register from only one of them:

```xml
<scripts>
    <script src="js/normalization-rules.js"/>
    <script src="js/normalizer.js"/>
</scripts>
```

Every listed script receives the same component identifier. If several scripts
register classes, the last registration replaces the earlier one and makes the
package needlessly dependent on load ordering.

#### Deprecated `entrypoint` compatibility

The descriptor form below is deprecated for version 2 components:

```xml
<!-- Deprecated compatibility fallback; omit from new packages. -->
<entrypoint name="ExampleWidget"/>
```

It requires the named constructor to exist on the platform's global `window`,
for example as `window.ExampleWidget`. The runtime first looks for a class
registered for the component URI and only falls back to the global name from
`entrypoint` when no registration exists. This fallback remains for existing
packages, but new and migrated packages should omit the element and call the
appropriate registration function.

If WireCloud reports `Widget entrypoint class not found!` or
`Operator entrypoint class not found!`, check that:

1. the file containing the class is listed in `<scripts>` and loads without a
   syntax or network error;
2. it calls the widget or operator registration function before the script
   finishes executing; and
3. it passes that call's `document.currentScript`, not a value captured later.

Prefer version 1 when maintaining an established iframe component. Use version
2 deliberately when its per-instance class and, for widgets, Shadow DOM model
suit the component. Test widget styles and third-party libraries for Shadow DOM
compatibility.

### Catalogue metadata with `details`

Every descriptor requires a `details` element, although its children are
optional. Good metadata makes a package understandable before a user runs its
code:

```xml
<details>
    <title>Hello world</title>
    <authors>Example Team &lt;team@example.com&gt; (https://example.com)</authors>
    <contributors>Alice Example, Bob Example</contributors>
    <email>support@example.com</email>
    <description>Shows a message received through wiring.</description>
    <longdescription>docs/description.md</longdescription>
    <homepage>https://example.com/hello-world</homepage>
    <doc>docs/user-guide.md</doc>
    <image>images/catalogue.png</image>
    <smartphoneimage>images/smartphone.png</smartphoneimage>
    <license>Apache-2.0</license>
    <licenseurl>LICENSE</licenseurl>
    <changelog>CHANGELOG.md</changelog>
    <issuetracker>https://example.com/hello-world/issues</issuetracker>
</details>
```

| Element | Purpose |
| --- | --- |
| `title` | Translatable display name and default widget-instance title. Falls back to `name`. |
| `authors`, `contributors` | Comma-separated contacts. Each can use `Name <email> (URL)`. Escape `<` and `>` as XML entities. |
| `email` | Support address. |
| `description` | Short, plain-text, translatable catalogue summary. |
| `longdescription` | Normally a package-relative Markdown description. |
| `homepage` | Absolute project URL. |
| `doc` | Package-relative Markdown documentation or an absolute documentation URL. |
| `image`, `smartphoneimage` | Package-relative or absolute catalogue artwork. |
| `license`, `licenseurl` | License identifier/name and optional full license document. |
| `changelog` | Package-relative Markdown change history. |
| `issuetracker` | Issue-reporting URL. |

Keep every relative path inside the package, preserve its case, and include the
referenced file in the archive. Linux deployments use case-sensitive paths even
if the package was created on a case-insensitive workstation.

### Feature requirements

Requirements make optional APIs explicit and allow WireCloud to reject a
package early when the deployment cannot run it:

```xml
<requirements>
    <feature name="StyledElements"/>
    <feature name="DashboardManagement"/>
    <feature name="NGSI"/>
</requirements>
```

Common core features include `StyledElements`, `FullscreenWidget`,
`DashboardManagement`, and `ComponentManagement`. Plugins can add features such
as `NGSI` or `ObjectStorage`. Check `/api/features` on the target WireCloud
instance for the authoritative set and versions. Declare a feature whenever the
component needs it; do not rely on it merely happening to be installed in a
development instance.

### Preferences

Preferences are configuration values shown in the component settings dialog and
accessed through `MashupPlatform.prefs`:

```xml
<preferences>
    <preference name="service_url"
                type="text"
                label="Service URL"
                description="Base URL of the data service"
                default="https://api.example.com"
                required="true"/>

    <preference name="page_size"
                type="number"
                label="Page size"
                default="25"/>

    <preference name="show_archived"
                type="boolean"
                label="Show archived records"
                default="false"/>

    <preference name="format"
                type="list"
                label="Result format"
                default="compact">
        <option value="compact" label="Compact"/>
        <option value="detailed" label="Detailed"/>
    </preference>

    <preference name="query_template"
                type="code"
                language="javascript"
                label="Query template"/>
</preferences>
```

Supported types are:

| Type | JavaScript value/use |
| --- | --- |
| `text` | Single-line string. |
| `longtext` | Multi-line string. |
| `code` | Multi-line code editor; `language` provides the syntax hint. |
| `number` | Number. |
| `boolean` | Boolean. |
| `password` | Masked string input. It is not secure storage by itself. |
| `list` | String selected from nested `option` elements. A list must contain options. |

Each preference supports:

| Attribute | Meaning |
| --- | --- |
| `name` | Stable programmatic name; cannot contain `/`. |
| `type` | One of the types above. |
| `label`, `description` | Translatable user-interface text. |
| `default` | Default value used for a new instance. XML stores it as text and WireCloud converts it according to `type`. |
| `value` | Explicit initial value overriding `default`. Usually mashup templates should override instance values instead. |
| `readonly` | Prevent changes through the normal settings UI. |
| `required` | Whether the user may leave it blank. Set this explicitly; the current XML parser treats an omitted value as `false`, while older schema documentation described a `true` default. |
| `secure` | Keep the real value out of component JavaScript and use WireCloud proxy substitution for outbound requests. |
| `language` | Syntax/editor hint for `code` preferences. |

For a secure service credential:

```xml
<preference name="api_password"
            type="password"
            label="API password"
            required="true"
            secure="true"/>
```

`secure="true"` is materially different from `type="password"`: the password
type only changes the input control, whereas the secure flag causes WireCloud to
censor the value exposed to the component and makes it available to the
server-side proxy substitution mechanism. Never place a real secret in
`default`, `value`, JavaScript, or another packaged file.

### Persistent variables

Persistent variables store component-managed state across reloads. They are not
shown as ordinary user preferences:

```xml
<persistentvariables>
    <variable name="selected_items"
              type="text"
              label="Selected items"
              default="[]"/>
    <variable name="draft"
              type="text"
              multiuser="true"/>
</persistentvariables>
```

Only `type="text"` is currently accepted. Serialize objects and arrays as JSON.
Attributes include `name`, `label`, `description`, `default`, `secure`, and
`multiuser`. A multi-user variable stores a separate value for each user who
opens the workspace; without it, collaborators share the same instance value.
Use `secure="true"` only with proxy substitution, since direct API access is
censored.

Read and write variables with
`MashupPlatform.widget.getVariable(name)` or
`MashupPlatform.operator.getVariable(name)`. Preferences describe deployment
configuration; persistent variables describe runtime state. Do not use either
as an unbounded database.

### Wiring endpoints

The root `wiring` element declares the component's public event contract:

```xml
<wiring>
    <inputendpoint name="selection"
                   type="text"
                   label="Selection"
                   actionlabel="Show this selection"
                   description="A JSON object containing an id and label"
                   friendcode="selection entity"/>
    <outputendpoint name="record"
                    type="text"
                    label="Selected record"
                    description="A JSON object containing the selected record"
                    friendcode="selection entity"/>
</wiring>
```

Both endpoint types require `name` and `type`. The current schema accepts only
`type="text"`; that historical type name does not prevent JavaScript from
sending objects, but components should document and validate a stable data
shape. Prefer JSON-compatible values when independently developed components
must interoperate.

`label` and `description` are translatable UI text. Space-separated
`friendcode` keywords help the wiring editor suggest compatible endpoints. An
input's `actionlabel` is a short user-facing command such as “Show on map”; it
is also returned by the current API's reachable-endpoint support.

Endpoint names are the strings passed to
`MashupPlatform.wiring.registerCallback()` and `pushEvent()`. Renaming one is a
breaking change for existing mashups.

### Widget contents and rendering

Widgets require `contents` and `rendering`:

```xml
<contents src="index.html"
          contenttype="text/html"
          charset="utf-8"
          cacheable="true"
          useplatformstyle="true"/>
<rendering width="400px" height="300px"/>
```

| Setting | Meaning |
| --- | --- |
| `src` | Required package-relative or absolute widget document. |
| `contenttype` | Defaults to `text/html`. HTML is the portable choice. |
| `charset` | Defaults to `utf-8`. The file must actually decode using this charset. |
| `cacheable` | Defaults to `true`; set false only when the document genuinely must be re-read. |
| `useplatformstyle` | Defaults to `false`; when true, WireCloud injects the active theme's widget styles. |
| `width`, `height` | Required initial size. Accepts a non-negative number, pixels, or a percentage, such as `20`, `320px`, or `50%`. |

`contents` can contain `altcontents` entries with `scope`, `src`, `contenttype`,
and `charset`. They are retained for compatibility and plugin-defined rendering
scopes; use the main `contents` entry for the normal core runtime unless the
target deployment defines a particular alternative scope.

### Operator scripts

Operators have no `contents` or `rendering`. They require a `scripts` block:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<operator xmlns="http://wirecloud.conwet.fi.upm.es/ns/macdescription/1"
          vendor="Example"
          name="normalizer"
          version="1.0.0">
    <details>
        <title>Record normalizer</title>
        <description>Converts service records to a stable shape.</description>
    </details>
    <wiring>
        <inputendpoint name="source" type="text" label="Source record"/>
        <outputendpoint name="result" type="text" label="Normalized record"/>
    </wiring>
    <scripts>
        <script src="js/normalizer.js"/>
    </scripts>
</operator>
```

Scripts are loaded in document order. In MAC version 1 they use the global
`MashupPlatform` object. In MAC version 2 one script must call
`Wirecloud.registerOperatorClass(document.currentScript, OperatorClass)`, as
described above. Keep operator code free of DOM assumptions.

### Mashup template descriptors

A `mashup` package describes a workspace template rather than executable code.
It can declare parameters, embedded component packages, tabs, widget instances,
operators, and connections. Mashup descriptors are usually generated by
publishing an existing workspace, which avoids hand-maintaining internal IDs
and layout geometry.

A compact example is:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<mashup xmlns="http://wirecloud.conwet.fi.upm.es/ns/macdescription/1"
        vendor="Example"
        name="records-dashboard"
        version="1.0.0">
    <details>
        <title>Records dashboard</title>
        <description>Displays records from a configurable service.</description>
    </details>

    <preferences>
        <preference name="service_url" type="text"
                    label="Service URL" required="true"/>
    </preferences>

    <structure>
        <tab id="0" name="Records" title="Records">
            <preferencevalue name="screenSizes"
                              value="[{&quot;id&quot;: 0, &quot;name&quot;: &quot;Phone&quot;, &quot;moreOrEqual&quot;: 0, &quot;lessOrEqual&quot;: 767, &quot;columns&quot;: 1}, {&quot;id&quot;: 1, &quot;name&quot;: &quot;Tablet&quot;, &quot;moreOrEqual&quot;: 768, &quot;lessOrEqual&quot;: 1199, &quot;columns&quot;: 6}, {&quot;id&quot;: 2, &quot;name&quot;: &quot;Desktop&quot;, &quot;moreOrEqual&quot;: 1200, &quot;lessOrEqual&quot;: -1, &quot;columns&quot;: 12}]"/>
            <preferencevalue name="cellheight" value="40"/>
            <preferencevalue name="margin" value="5"/>
            <resource id="1" vendor="Example" name="record-list"
                      version="1.0.0" title="Records">
                <layouts>
                    <layout screensize="0" x="0" y="0" w="1" h="8"/>
                    <layout screensize="2" x="0" y="0" w="6" h="8"/>
                </layouts>
                <preferencevalue name="service_url"
                                 value="%(params.service_url)"
                                 readonly="true"/>
            </resource>
        </tab>
        <wiring version="2.0">
            <visualdescription/>
        </wiring>
    </structure>
</mashup>
```

Important mashup elements are:

- Root `preferences` declare template parameters. Instance values can reference
  them with `%(params.parameter_name)`.
- `preferencevalue` overrides preferences at the level it appears in: inside
  `structure` it overrides workspace preferences, inside a `tab` it overrides
  tab preferences (such as `screenSizes`, `cellheight`, and `margin`, shown
  above), and inside a `resource` it overrides that widget's own preferences.
- Each `tab` requires internal `id` and `name`; `title` is optional.
- Each tab `resource` is a widget instance identified by its own internal `id`
  and a component `vendor/name/version`. It can override `preferencevalue` and
  `variablevalue`; `readonly` prevents normal removal. The old `layout`
  attribute on `resource` (the layout engine selector) has been removed.
- A `layouts` block lists the resource's layout for one or more screen sizes.
  Each `layout` entry needs a `screensize` attribute matching the `id` of an
  entry declared in the tab's (or workspace's) `screenSizes` preference (see
  the example above). `x` and `y` may be omitted for automatic placement; `w`
  and `h`, in grid columns/rows, size the widget and default to `1`. The boolean attributes
  `minimized`, `titlevisible`, `fulldragboard`, and `visible` default to
  `false`, `true`, `false`, and `true` respectively. A resource without a
  `layouts` block, or without an entry for a given screen size, is placed
  automatically the first time it is displayed at that size. The older
  `screensizes` block and the direct `position` plus `rendering` form are
  still parsed and converted best-effort from the old grid (20 columns × 12px
  rows) to the new default grid (12 columns × 40px rows).
- `structure/wiring` must use `version="2.0"`. It contains operator instances,
  connections, and optional visual layout/behaviour information. Wiring version
  1.0 is rejected by the current parser.
- `source` and `target` inside a connection use `type`, internal component `id`,
  and declared endpoint `name`. A `readonly` connection cannot be removed in the
  normal editor.
- Root `embedded/resource` entries can package referenced `.wgt` files under the
  mashup archive, making the template self-contained when embedded-resource
  installation is enabled.
- A root-level `wiring` element declares endpoints exposed by the mashup itself;
  it is different from `structure/wiring`, which connects the instances inside
  the generated workspace.

When editing a generated mashup descriptor, keep every resource/operator ID
consistent across `resource`, `operator`, `connection`, and
`visualdescription` entries.

### Translations

Use `__MSG_key__` placeholders in translatable fields and define every used key
in the default language:

```xml
<details>
    <title>__MSG_title__</title>
    <description>__MSG_description__</description>
</details>

<translations default="en">
    <translation lang="en">
        <msg name="title">Record viewer</msg>
        <msg name="description">Displays the selected record.</msg>
    </translation>
    <translation lang="es">
        <msg name="title">Visor de registros</msg>
        <msg name="description">Muestra el registro seleccionado.</msg>
    </translation>
</translations>
```

The current XML parser tracks placeholders used by the resource title and
description, preference labels/descriptions and list options, and endpoint
labels/descriptions/action labels. A translation catalogue is rejected when the
default language is missing, a used key lacks a default value, or the catalogue
contains keys not used by the descriptor.

### Complete minimal widget descriptor

```xml
<?xml version="1.0" encoding="UTF-8"?>
<widget xmlns="http://wirecloud.conwet.fi.upm.es/ns/macdescription/1"
        vendor="Example"
        name="hello-world"
        version="1.0.0">
    <details>
        <title>Hello world</title>
        <authors>Example team</authors>
        <description>A small example widget</description>
        <license>Apache-2.0</license>
    </details>
    <wiring>
        <inputendpoint name="message" type="text" label="Message"/>
        <outputendpoint name="clicked" type="text" label="Clicked"/>
    </wiring>
    <contents src="index.html" useplatformstyle="true"/>
    <rendering height="300px" width="400px"/>
</widget>
```

This version 1 descriptor deliberately keeps the widget's JavaScript references
inside `index.html`. Add only the sections the component uses, but retain
`details`, `contents`, and `rendering`, which are required for widgets.

### XML and packaging pitfalls

- Put `config.xml` at the archive root, not inside a wrapping directory.
- Use the exact namespace on the root element. A missing, misspelled, or old
  namespace is rejected.
- XML-escape `&`, `<`, `>`, and quote characters where required. JSON stored in
  an attribute must escape its quotes as `&quot;`.
- Keep programmatic names stable and do not use `/` in `vendor`, component
  `name`, or preference/endpoint names.
- Match every referenced path exactly and use forward slashes inside the ZIP.
- Do not create ZIP entries with absolute paths or `../`; WireCloud rejects
  those archive paths. Keep descriptor references package-relative as well.
- Ensure every required feature is available on the target instance.
- For mashups, use wiring version 2.0 and keep internal IDs consistent.
- Prefer exporting a working workspace for complex mashup templates, then make
  small, reviewed descriptor edits.

## Wiring API

Component JavaScript receives the `MashupPlatform` API. Register an input callback and emit an output value using the endpoint names declared in `config.xml`:

```javascript
MashupPlatform.wiring.registerCallback("message", (value) => {
    document.querySelector("#message").textContent = String(value);
});

document.querySelector("#send").addEventListener("click", () => {
    MashupPlatform.wiring.pushEvent("clicked", "hello");
});
```

Do not assume an endpoint is connected. The API also provides `hasInputConnections` and `hasOutputConnections` when a component needs to adapt to its wiring state.

See the
[FIWARE Application Mashup - Widget API Specification](mashup-platform-api.md)
for the complete current reference, including HTTP requests, contexts,
preferences, persistent variables, selective wiring delivery, logging, dynamic
dashboards, and component management.

## Build and upload

From inside the component directory:

```bash
zip -r ../Example_hello-world_1.0.0.wgt .
```

Inspect the archive before upload:

```bash
unzip -l ../Example_hello-world_1.0.0.wgt
unzip -p ../Example_hello-world_1.0.0.wgt config.xml | xmllint --noout -
unzip -t ../Example_hello-world_1.0.0.wgt
```

The `xmllint` command checks that the XML is well formed. WireCloud upload is the
definitive validation because it also applies the MACDL schema, semantic checks,
and feature-availability checks. Open **My Resources**, choose **Upload**, and
select the `.wgt` file. Test the component in a disposable workspace, including
preferences, persistent state, reload, endpoint connections, resize behavior,
translations, logs, and browser console errors.

## Security guidance

- Treat endpoint values and remote responses as untrusted input.
- Avoid inserting strings into `innerHTML`; prefer DOM text APIs or a reviewed sanitizer.
- Do not package secrets in JavaScript, ordinary preferences, defaults, or the
  descriptor. Use `secure="true"` plus server-side proxy substitution for
  credentials that WireCloud must retain.
- Use the WireCloud proxy only for intended remote services and let administrators restrict its destinations.
- Use HTTPS for service calls and avoid disabling certificate verification.
- Document every external service, permission, and data format required by the component.
