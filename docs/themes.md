# Creating themes

Themes change WireCloud's presentation without changing its application behavior. They can provide colors and typography, images, compiled CSS and JavaScript, translated labels, and selected Jinja templates. Theme inheritance makes a small branding theme possible without copying the whole default interface.

Creating a theme currently requires a custom WireCloud build. The Python loader imports themes from `wirecloud.themes`, and the frontend build scans `src/wirecloud/themes` for `theme.ts` files. Add the theme to the source tree before running Webpack.

## Start with an inherited theme

Create this structure:

```text
src/wirecloud/themes/acmetheme/
├── __init__.py
├── theme.ts
├── static/
│   ├── css/
│   │   └── acme.scss
│   └── images/
│       └── logos/
│           └── header.png
└── templates/
    └── wirecloud/
        └── views/
            └── header.html
```

Only add files that the child theme changes. All other templates and static files are resolved through its parent.

### Python metadata

`__init__.py` must define `parent` and `label`:

```python
from wirecloud.translation import gettext_lazy as _

parent = "defaulttheme"
label = _("Acme")
```

Set `parent = None` only for a complete root theme that supplies everything WireCloud needs. An inherited theme is safer because new parent templates and assets remain available after an upgrade.

The module name, directory name, and configured theme name must match exactly. A missing `parent` attribute is a configuration error. A parent that cannot be imported ends the inheritance chain, usually causing missing templates or assets later, so validate the name carefully.

### Frontend manifest

`theme.ts` tells Webpack which extra CSS and scripts belong to each view:

```typescript
const parent: string | null = "defaulttheme";

const getCSS = (view: string): string[] => {
    if (view === "classic" || view === "smartphone") {
        return ["css/acme.scss"];
    }
    return [];
};

const getScripts = (view: string): string[] => {
    return [];
};

export default {
    parent,
    get_css: getCSS,
    get_scripts: getScripts
};
```

The recognized bundle views include `classic`, `smartphone`, `embedded`, `widget`, `operator`, and `bootstrap`. CSS bundles are produced for platform views and widget rendering. Return files only for views that need them.

Paths are relative to the theme's `static` directory. A child can replace a parent asset by supplying the same relative path. For example, `static/images/logos/header.png` replaces the parent logo wherever that path is requested.

When overriding a parent stylesheet, placing a child file at the same relative path causes the build to use the child file for that entry. Prefer a small additional stylesheet for ordinary branding, and replace a parent stylesheet only when its rules or Sass structure genuinely need to change. Check the resulting cascade because parent and child entries can both contribute rules.

## Templates

Template lookup starts in the active theme and continues through its parents. To customize the header, copy the parent's relative template path:

```text
templates/wirecloud/views/header.html
```

Templates use Jinja syntax. Common helpers include:

- `trans("Text")` for theme-aware translation;
- `static("images/example.png")` for an asset URL; and
- `url("symbolic.route.name", argument=value)` for a URL contributed by the platform or a plugin.

Keep overrides narrow. Copying a large parent template freezes its structure in the child and makes later parent changes harder to adopt.

Plugins may declare additional template fragments through their `get_templates` hook. Every enabled theme must supply or inherit those paths; otherwise `/api/theme/{theme}` reports the missing template. This is one reason presentation-only changes belong in themes while new behavior belongs in [plugins](plugins.md).

## Theme configuration and extension points

Themes can go beyond restyling. The following hooks are available to any theme; when a theme does not use them, the platform behaves as before.

### Client configuration

A theme module can declare a `config` dictionary. It is returned by `/api/theme/{theme}` and exposed as `Wirecloud.currentTheme.config` (child themes inherit and override their parent's entries):

```python
config = {
    "color_schemes": ["light", "dark"],   # schemes supported by the stylesheets
    "keyboard_shortcuts": True,           # enable Wirecloud.ui.shortcuts
    "wiring_click_to_connect": True,      # click an output, then an input
    "shell": "rail",                      # free-form entries for the theme scripts
    "icon_set": "lucide",
}
```

When `color_schemes` lists more than one scheme, the *Color scheme* platform preference (`system`, `light` or `dark`) is shown in the user settings.

### Root state attributes

The root element exposes the platform state, so themes can style states with CSS only:

| Attribute | Values |
| --- | --- |
| `data-wc-theme` | active theme name |
| `data-wc-view` | `classic`, `smartphone` or `embedded` |
| `data-wc-mode` | `view`, `edit`, `wiring`, `catalogue` or `marketplace` |
| `data-wc-color-scheme` | `light` or `dark` (also set on the widget documents) |
| `data-wc-screen-size` | name of the active screen size of the visible tab |

`Wirecloud.UserInterfaceManager.setRootState(name, value)` updates them. Before the platform code is loaded, `data-wc-color-scheme` is missing; style the system preference with `@media (prefers-color-scheme: dark)` on `:root:not([data-wc-color-scheme])`. The last resolved scheme is stored in `localStorage` (`wirecloud.color-scheme`) so pages can apply it before painting.

### Replaceable UI classes

Theme scripts (returned by `get_scripts` in `theme.ts`) run after the platform ones and can replace UI classes through a registry:

```javascript
class MyHeader extends Wirecloud.ui.WirecloudHeader { /* ... */ }
Wirecloud.ui.registry.register("WirecloudHeader", MyHeader);
```

The platform builds these pieces through the registry: `WirecloudHeader`, `WorkspaceView`, `WorkspaceToolbar` (header buttons of the workspace view), `WidgetView` (override `getTemplateComponents()` to change the widget chrome), `WiringEditor`, `WiringEditor.Component`, `WiringEditor.ComponentDraggable`, `MarketplaceView`, `MyResourcesView`, `MyResourcesSearchView` (search view of My resources), `CatalogueSearchView`, `ResourcePainter` and `CommandPalette`. `Wirecloud.ui.registry.get(name)` falls back to `Wirecloud.ui.<name>`.

`Wirecloud.ui.WirecloudHeader.defaults` holds the presentation defaults of the default header (button classes and icons) and `buildUserMenu(menu)` fills the user menu, so small changes do not require a new header.

### Semantic view API

Besides `getBreadcrumb()`, `getToolbarButtons()` and `getToolbarMenu()`, the workspace view and the wiring editor describe their actions so headers can render them in any form:

- `getModes()` → `[{id: "view"|"edit"|"wiring", label, icon, shortcut, active, enabled, activate()}]`
- `getPrimaryAction()` → `{id, label, icon, enabled, run()}` ("Add widget", "Add operator") or `null`
- `getSecondaryActions()` → e.g. `[{id: "share", ...}]`
- `deleteSelection()` and `cancel()` (used by the keyboard shortcuts)

The workspace view also tracks the selected widget while editing (`selectWidget(widget)`, `selectedWidget`, `selectionchange` event; the widget gets the `wc-widget-selected` class).

### Commands and keyboard shortcuts

`Wirecloud.commands` lists the commands available in the current context: workspaces, workspace/tab/widget/marketplace menus (built from the same menu builders), navigation and installed components. Use `list(query)` and `run(command)`, and `register()`/`registerProvider()` to add commands. `openPalette()` shows the palette registered as `CommandPalette`.

`Wirecloud.ui.shortcuts` handles `⌘/Ctrl+K` (palette), `V`/`E`/`W` (modes), `Delete` (remove the selected widget or connection) and `Esc` (cancel). Shortcuts are only processed when the theme sets `keyboard_shortcuts`; themes can `register()` more.

### The Industry theme

`industrytheme` is a complete root theme built on these hooks: a navigation rail, a header with a mode switch and a command palette, layout controls in the tab bar, a status bar, a faceted My resources view with a detail pane, light and dark color schemes, Barlow fonts and Lucide icons (Font Awesome class names used by the platform and widgets are mapped to Lucide icons in `static/css/base/_icon-map.scss`; run `scripts/update_icons.py` after adding icons). Its stylesheets are written against the CSS custom properties of `static/css/_tokens.scss`.

## Translations

For a translatable theme label or template strings, catalogue files use the theme name as their gettext domain:

```text
locale/es/LC_MESSAGES/acmetheme.po
locale/es/LC_MESSAGES/acmetheme.mo
```

Generate and compile them from the repository root:

```bash
PYTHONPATH=src python -m manage gentranslations --language es
PYTHONPATH=src python -m manage compiletranslations --language es
```

Theme translation lookup follows the same child-to-parent chain as templates.

## Build and enable the theme

Build assets after adding or changing `theme.ts`, Sass, CSS, or JavaScript:

```bash
npm run build
```

Then make the theme available. With the Docker settings format:

```text
WIRECLOUD_AVAILABLE_THEMES=defaulttheme,acmetheme
WIRECLOUD_THEME_ACTIVE=acmetheme
```

`WIRECLOUD_THEME_ACTIVE` must be present in the available list. Restart WireCloud after changing theme settings. In a source settings module, use the equivalent values:

```python
AVAILABLE_THEMES = ["defaulttheme", "acmetheme"]
THEME_ACTIVE = "acmetheme"
```

An available theme can be previewed without making it the default by adding `?themeactive=acmetheme` to a WireCloud workspace URL. The value is accepted only when it is in `AVAILABLE_THEMES`.

## Test checklist

Test every view your users rely on:

- anonymous landing and authenticated login pages;
- classic and mobile workspace views;
- My Resources, resource details, and upload dialogs;
- workspace editing, widget menus, and the wiring editor;
- embedded workspaces and widgets using platform styles;
- error pages; and
- every enabled language.

Also test missing images and fonts in the browser network panel, keyboard focus, contrast, narrow screens, and a production-mode `npm run build`. A successful Webpack build proves that assets compile, but not that inherited templates remain visually compatible.

## Packaging and upgrades

The current build discovers frontend themes from the WireCloud source tree rather than from arbitrary external Python packages. Maintain a small patch layer or derived source/image build containing `src/wirecloud/themes/acmetheme`, and rebuild it for each WireCloud release. Keep theme code under version control and compare overridden parent files during upgrades.
