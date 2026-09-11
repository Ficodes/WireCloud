# User guide

This guide covers the normal workflow after an administrator has initialized WireCloud and created your account.

## Sign in and open a workspace

Open the instance root URL. If the administrator enabled Keycloak, **Sign in**
redirects you to the organization's Keycloak page. Complete any password,
multi-factor authentication, or identity-provider steps there; you should not
enter the Keycloak password directly into WireCloud. On the first successful
login, WireCloud creates its local account record and subsequently updates the
name and email supplied by Keycloak.

Your administrator may also synchronize Keycloak groups into WireCloud. Group
changes normally take effect at the next login. If Keycloak accepts the login
but WireCloud denies access, reports an inactive account, or assigns the wrong
permissions, contact the WireCloud administrator rather than creating another
account with a different username.

Signing out of WireCloud always ends the WireCloud session. Depending on the
administrator's single-sign-out configuration, it may also end the Keycloak
session; otherwise, Keycloak can sign you straight back in on the next visit.
Local login is available only when the administrator has chosen to expose it.

After authentication, WireCloud redirects you to the built-in home workspace.
Use the workspace selector to open another workspace or choose **New workspace**.

A workspace URL has this form:

```text
/workspace/{owner}/{name}
```

The owner and stable workspace name appear in the URL; the displayed title can be changed independently.

## Create a workspace

1. Open the workspace menu and choose **New workspace**.
2. Enter a name and title.
3. Choose an empty workspace, an existing workspace to clone, or an installed mashup template when those choices are available.
4. Confirm the dialog.

A new empty workspace contains a default tab. Use tabs to separate parts of a dashboard and workspace settings to control its title, description, sharing, and other preferences.

## Install components in My Resources

WireCloud components are distributed as `.wgt` files. A package can contain a widget, an operator, or a mashup template.

1. Open **My Resources**.
2. Choose **Upload**.
3. Select a `.wgt` file and confirm the upload.
4. Check the resource details, version, and declared requirements.

Uploading a new version does not silently replace widget instances already placed in workspaces. Use the instance menu's upgrade/downgrade action when you deliberately want to change an instance version.

Only install packages from sources you trust. Widgets execute browser code and operators participate in workspace data flows.

Component authors can use WireCloud's injected JavaScript interface for wiring,
preferences, context, HTTP requests, and advanced workspace operations. See the
[FIWARE Application Mashup - Widget API Specification](mashup-platform-api.md);
this is separate from the server's external HTTP API. For package construction,
including the required `registerWidgetClass` and `registerOperatorClass` pattern
for MAC version 2, see [Packaging components](components.md#mac-version-1-and-2).
The version 2 descriptor `entrypoint` is a deprecated compatibility fallback.

## Add and configure widgets

1. Return to the workspace editor.
2. Open the component sidebar.
3. Find a widget and choose **Add to workspace**.
4. In edit mode, drag it by its title bar and resize it from its edges or corners to place it on the active tab's grid.
5. Open its menu to edit settings, rename it, reload it, view logs or documentation, or change its version.

Preferences are the user-configurable values declared by a component. Persistent variables are component-managed values retained by WireCloud. They serve different purposes and may be reset or migrated differently when a component changes version.

## Responsive layouts

Each tab lays out its widgets on a grid. In edit mode, drag a widget by its title bar to move it and drag its edges or corners to resize it; the other widgets rearrange to make room.

### Screen sizes

A workspace or tab preference named **Screen sizes** defines one or more breakpoints, each with a name, a width range in pixels, and a number of grid columns. The defaults are:

- **Phone**: 0–767 px, 1 column.
- **Tablet**: 768–1199 px, 6 columns.
- **Desktop**: 1200 px and above, 12 columns.

A widget's layout (position, size, and visibility) is stored separately for each screen size. If a widget has no layout stored for the screen size currently active, WireCloud derives one from the layout of the nearest screen size that does have one, scaled to the new column count; that derived layout is only saved once you edit the widget at that screen size.

To edit the layout for a specific screen size regardless of your current window width, open the workspace's or tab's preferences, find **Screen sizes**, and use the **edit** button next to the screen size you want. The workspace header then shows an indicator naming the screen size you are editing; use its close icon to return to editing at your actual window width.

### Hiding widgets per screen size

Open a widget's menu and choose **Hide for this screen size** to remove it from the layout at the screen size you are currently editing, without affecting its layout at other screen sizes. To bring it back, open the tab menu, expand **Hidden widgets**, and select the widget's title.

### Minimize, title, and full dragboard

The buttons on a widget's title bar minimize it to its title bar or toggle whether the title bar is shown outside edit mode. The widget's menu can switch it to **Full Dragboard**, which expands the widget to cover the visible area of the tab; choose **Exit Full Dragboard** to restore its normal layout. These settings are also stored per screen size.

### Moving a widget to another tab

Open the widget's menu and choose **Move to tab**, then pick the destination tab. The widget keeps its own settings and moves with the layout it would normally get on the target tab.

## Wire components

Open the **Wiring** view. Components expose named input and output endpoints:

1. Add the required widgets and operators to the wiring canvas.
2. Configure operators before connecting them when they need a service URL or credentials.
3. Drag from an output endpoint to a compatible input endpoint.
4. Return to the workspace view and exercise the source component.

An operator is useful when a source's data shape does not match a widget's input, or when network/service logic should remain separate from the visual component. Remove a connection from its connection control in the wiring view.

The behaviour editor can group components and connections by purpose. A component may participate in more than one behaviour. Disabling behaviour-oriented wiring flattens the view, so treat that action carefully.

## Share or embed a workspace

Use **Share** in the workspace menu to configure access for users and groups and to make a workspace public when appropriate. Anonymous visitors can open a public workspace only when the instance administrator also enables anonymous access.

Use **Embed** to obtain markup for including a workspace in another page. The browser visiting the parent page must still satisfy the workspace's authentication and access rules. For cross-site embedding, the reverse proxy and parent site's security headers must also permit framing.

Use **Upload to my resources** to turn the current workspace into a reusable mashup template. You can choose whether to include the widget and operator packages it uses.
