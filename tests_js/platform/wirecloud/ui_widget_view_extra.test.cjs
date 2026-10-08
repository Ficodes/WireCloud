const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScript,
    loadLegacyScripts,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');
const { installGridStackMock } = require('../../support/gridstack-mock.cjs');

// ============================================================================
// PART 1: Wirecloud.ui.WidgetViewMenuItems
// ============================================================================
//
// WidgetViewMenuItems.build() only constructs StyledElements.MenuItem /
// SubMenuItem / Separator instances and returns them as a plain array; it
// never renders a popup. So instead of loading the (heavier) real
// PopupMenuBase-based classes we use small self-contained mocks that record
// label/icon/disabled state and let tests invoke the stored handler
// directly, the same approach already used elsewhere in this suite for
// menu-building logic.

const setupMenuItems = () => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();

    global.Wirecloud = {
        Utils: StyledElements.Utils,
        ui: {},
        LocalCatalogue: {
            hasAlternativeVersion: () => true,
        },
        UserInterfaceManager: {
            views: {
                myresources: {
                    _calls: [],
                    createUserCommand(...args) {
                        this._calls.push(args);
                        return () => { this._commandInvoked = true; };
                    },
                },
            },
        },
    };

    StyledElements.DynamicMenuItems = class DynamicMenuItems {};
    StyledElements.Separator = class Separator {};
    StyledElements.MenuItem = class MenuItem {
        constructor(label, handler) {
            this.label = label;
            this.handler = handler;
            this.disabled = false;
            this.icons = [];
        }
        addIconClass(iconClass) {
            this.icons.push(iconClass);
            return this;
        }
        setDisabled(disabled) {
            this.disabled = !!disabled;
            return this;
        }
        run() {
            if (!this.disabled && typeof this.handler === 'function') {
                this.handler();
            }
        }
    };
    StyledElements.SubMenuItem = class SubMenuItem {
        constructor(label, options = {}) {
            this.label = label;
            this.iconClass = options.iconClass;
            this.disabled = false;
            this.children = [];
        }
        setDisabled(disabled) {
            this.disabled = !!disabled;
            return this;
        }
        append(item) {
            this.children.push(item);
            return this;
        }
    };

    Wirecloud.ui.UpgradeWindowMenu = class UpgradeWindowMenu {
        constructor(model) { this.model = model; }
        show() { Wirecloud.ui._lastUpgradeDialog = this; }
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WidgetViewMenuItems.js');
};

const makeMenuWidget = (overrides = {}) => {
    const tab = overrides.tab || {
        id: 'tab-1',
        workspace: {
            tabs: [
                { id: 'tab-1', title: 'Tab 1' },
                { id: 'tab-2', title: 'Tab 2' },
                { id: 'tab-3', title: 'Tab 3' },
            ],
        },
    };

    return Object.assign({
        layout: null,
        tab,
        titleelement: {
            enableEdition() { this._editionEnabled = true; },
        },
        model: {
            volatile: false,
            missing: false,
            meta: { doc: 'Some documentation', version: '1.0.0' },
            isAllowed: () => true,
            hasPreferences: () => true,
        },
        reload() { this._reloaded = true; },
        showLogs() { this._logsShown = true; },
        showSettings() { this._settingsShown = true; },
        setFullDragboardMode(enable, persist) { this._fullDragboardCall = { enable, persist }; },
        hideInCurrentScreenSize() { this._hideCalled = true; },
        moveToTab(target) { this._movedTo = target; },
    }, overrides);
};

const buildItems = (widget) => new Wirecloud.ui.WidgetViewMenuItems(widget).build();

test('WidgetViewMenuItems: builds the full item list for a normal (non-fulldragboard) widget with sibling tabs', () => {
    setupMenuItems();
    const widget = makeMenuWidget();
    const items = buildItems(widget);

    // Rename, Reload, Upgrade/Downgrade, Logs, Settings, User's Manual,
    // Separator, Full Dragboard, Hide for this screen size, Move to tab
    assert.equal(items.length, 10);
    assert.equal(items[0].label, 'Rename');
    assert.equal(items[1].label, 'Reload');
    assert.equal(items[2].label, 'Upgrade/Downgrade');
    assert.equal(items[3].label, 'Logs');
    assert.equal(items[4].label, 'Settings');
    assert.equal(items[5].label, "User's Manual");
    assert.ok(items[6] instanceof StyledElements.Separator);
    assert.equal(items[7].label, 'Full Dragboard');
    assert.equal(items[8].label, 'Hide for this screen size');
    assert.equal(items[9].label, 'Move to tab');
});

test('WidgetViewMenuItems: Rename item icon, enablement and action', () => {
    setupMenuItems();
    const widget = makeMenuWidget();
    widget.model.isAllowed = (perm, role) => !(perm === 'rename' && role === 'editor');
    let items = buildItems(widget);
    assert.equal(items[0].disabled, true, 'disabled when rename is not allowed');

    widget.model.isAllowed = () => true;
    items = buildItems(widget);
    assert.deepEqual(items[0].icons, ['fas fa-pencil-alt']);
    assert.equal(items[0].disabled, false);

    items[0].run();
    assert.equal(widget.titleelement._editionEnabled, true);
});

test('WidgetViewMenuItems: Reload item is disabled for missing widgets and reloads on click', () => {
    setupMenuItems();
    const widget = makeMenuWidget({ model: Object.assign(makeMenuWidget().model, { missing: true }) });
    let items = buildItems(widget);
    assert.equal(items[1].disabled, true);
    assert.deepEqual(items[1].icons, ['fas fa-sync']);

    widget.model.missing = false;
    items = buildItems(widget);
    assert.equal(items[1].disabled, false);
    items[1].run();
    assert.equal(widget._reloaded, true);
});

test('WidgetViewMenuItems: Upgrade/Downgrade is disabled without the editor permission or an alternative version', () => {
    setupMenuItems();
    const widget = makeMenuWidget();

    widget.model.isAllowed = () => false;
    Wirecloud.LocalCatalogue.hasAlternativeVersion = () => true;
    assert.equal(buildItems(widget)[2].disabled, true, 'no upgrade permission');

    widget.model.isAllowed = () => true;
    Wirecloud.LocalCatalogue.hasAlternativeVersion = () => false;
    assert.equal(buildItems(widget)[2].disabled, true, 'no alternative version available');

    Wirecloud.LocalCatalogue.hasAlternativeVersion = () => true;
    const items = buildItems(widget);
    assert.equal(items[2].disabled, false);
    items[2].run();
    assert.equal(Wirecloud.ui._lastUpgradeDialog.model, widget.model);
});

test('WidgetViewMenuItems: Logs item is always enabled and shows the widget logs', () => {
    setupMenuItems();
    const widget = makeMenuWidget();
    const items = buildItems(widget);
    assert.equal(items[3].disabled, false);
    items[3].run();
    assert.equal(widget._logsShown, true);
});

test('WidgetViewMenuItems: Settings item is disabled without preferences or the configure permission', () => {
    setupMenuItems();
    const widget = makeMenuWidget();

    widget.model.hasPreferences = () => false;
    assert.equal(buildItems(widget)[4].disabled, true, 'no preferences at all');

    widget.model.hasPreferences = () => true;
    widget.model.isAllowed = (perm) => perm !== 'configure';
    assert.equal(buildItems(widget)[4].disabled, true, 'configure not allowed');

    widget.model.isAllowed = () => true;
    const items = buildItems(widget);
    assert.equal(items[4].disabled, false);
    items[4].run();
    assert.equal(widget._settingsShown, true);
});

test("WidgetViewMenuItems: User's Manual is disabled when the widget has no documentation and opens the docs tab otherwise", () => {
    setupMenuItems();
    const widget = makeMenuWidget();
    widget.model.meta.doc = '';
    assert.equal(buildItems(widget)[5].disabled, true);

    widget.model.meta.doc = 'Docs here';
    widget.model.meta.version = '3.2.1';
    const items = buildItems(widget);
    assert.equal(items[5].disabled, false);
    items[5].run();

    const myresources = Wirecloud.UserInterfaceManager.views.myresources;
    assert.equal(myresources._calls.length, 1);
    assert.equal(myresources._calls[0][0], 'showDetails');
    assert.equal(myresources._calls[0][1], widget.model.meta);
    assert.deepEqual(myresources._calls[0][2], { version: '3.2.1', tab: 'Documentation' });
    assert.equal(myresources._commandInvoked, true, 'the command returned by createUserCommand is invoked');
});

test('WidgetViewMenuItems: Full Dragboard toggle shows "Full Dragboard" when off and toggles it on', () => {
    setupMenuItems();
    const widget = makeMenuWidget();
    widget.layout = { fulldragboard: false };
    const items = buildItems(widget);

    const toggle = items[7];
    assert.equal(toggle.label, 'Full Dragboard');
    assert.deepEqual(toggle.icons, ['fas fa-expand']);
    toggle.run();
    assert.deepEqual(widget._fullDragboardCall, { enable: true, persist: true });
});

test('WidgetViewMenuItems: Full Dragboard toggle shows "Exit Full Dragboard" when on, toggles it off and stops other options', () => {
    setupMenuItems();
    const widget = makeMenuWidget();
    widget.layout = { fulldragboard: true };
    const items = buildItems(widget);

    // Everything after the toggle (Hide for this screen size, Move to tab)
    // is skipped while in full dragboard mode.
    assert.equal(items.length, 8);
    const toggle = items[7];
    assert.equal(toggle.label, 'Exit Full Dragboard');
    assert.deepEqual(toggle.icons, ['fas fa-compress']);

    toggle.run();
    assert.deepEqual(widget._fullDragboardCall, { enable: false, persist: true });
});

test('WidgetViewMenuItems: Full Dragboard toggle is disabled without the editor move permission', () => {
    setupMenuItems();
    const widget = makeMenuWidget();
    widget.model.isAllowed = (perm, role) => !(perm === 'move' && role === 'editor');
    const items = buildItems(widget);
    assert.equal(items[7].disabled, true);
});

test('WidgetViewMenuItems: "Hide for this screen size" hides the widget on click', () => {
    setupMenuItems();
    const widget = makeMenuWidget();
    const items = buildItems(widget);
    const hideItem = items[8];
    assert.deepEqual(hideItem.icons, ['fas fa-eye-slash']);
    hideItem.run();
    assert.equal(widget._hideCalled, true);
});

test('WidgetViewMenuItems: "Move to tab" lists every other tab and moves the widget on click', () => {
    setupMenuItems();
    const widget = makeMenuWidget();
    const items = buildItems(widget);
    const submenu = items[9];

    assert.equal(submenu.disabled, false);
    assert.equal(submenu.children.length, 2);
    assert.equal(submenu.children[0].label, 'Tab 2');
    assert.equal(submenu.children[1].label, 'Tab 3');

    submenu.children[1].run();
    assert.equal(widget._movedTo, widget.tab.workspace.tabs[2]);
});

test('WidgetViewMenuItems: "Move to tab" is disabled when this is the only tab', () => {
    setupMenuItems();
    const widget = makeMenuWidget({
        tab: { id: 'only-tab', workspace: { tabs: [{ id: 'only-tab', title: 'Only tab' }] } },
    });
    const items = buildItems(widget);
    const submenu = items[9];
    assert.equal(submenu.disabled, true);
    assert.equal(submenu.children.length, 0);
});

test('WidgetViewMenuItems: "Move to tab" is disabled when the widget may not be moved, even with sibling tabs', () => {
    setupMenuItems();
    const widget = makeMenuWidget();
    widget.model.isAllowed = (perm, role) => !(perm === 'move' && role === 'editor');
    const items = buildItems(widget);
    const submenu = items[9];
    assert.equal(submenu.disabled, true);
    // The submenu is still populated with entries even though it is disabled.
    assert.equal(submenu.children.length, 2);
});

// ============================================================================
// PART 2: WidgetView integration on top of a real WorkspaceTabViewDragboard
// and the fake GridStack, exercising the addWidget/refreshWidget/
// resolveLayout/applyScreenSize machinery end to end.
// ============================================================================

const DEFAULT_SCREEN_SIZES = [
    { id: 0, name: 'Phone', moreOrEqual: 0, lessOrEqual: 767, columns: 1 },
    { id: 1, name: 'Tablet', moreOrEqual: 768, lessOrEqual: 1199, columns: 6 },
    { id: 2, name: 'Desktop', moreOrEqual: 1200, lessOrEqual: -1, columns: 12 },
];

const makePreferences = (overrides = {}) => {
    const values = Object.assign({ cellheight: 40, margin: 5, screenSizes: DEFAULT_SCREEN_SIZES.map((s) => Object.assign({}, s)) }, overrides);
    const listeners = {};
    return {
        _values: values,
        get(key) { return this._values[key]; },
        addEventListener(type, handler) { (listeners[type] = listeners[type] || []).push(handler); },
        _trigger(type, payload) { (listeners[type] || []).slice().forEach((h) => h(this, payload)); },
    };
};

const makeStorageModel = (overrides = {}) => {
    const layouts = {};
    Object.keys(overrides.layouts || {}).forEach((key) => {
        layouts[key] = Object.assign({ x: null, y: null, w: 1, h: 1, minimized: false, titlevisible: true, fulldragboard: false, visible: true }, overrides.layouts[key]);
    });

    const wrapperElement = document.createElement('div');
    wrapperElement.contentDocument = { defaultView: { addEventListener() {} } };

    const model = Object.assign({
        id: overrides.id || 'widget-1',
        volatile: false,
        missing: false,
        loaded: false,
        title: 'Integration Widget',
        meta: { macversion: 1 },
        wrapperElement,
        permissions: {
            editor: { close: true, configure: true, move: true, rename: true, resize: true, minimize: true, upgrade: true },
            viewer: { close: false, configure: false, move: false, rename: false, resize: false, minimize: false, upgrade: false },
        },
        isAllowed(name, role) {
            role = role || 'viewer';
            return this.volatile || !!this.permissions[role][name];
        },
        contextManager: { modify() {} },
        logManager: { errorCount: 0, addEventListener() {} },
        _eventListeners: {},
        addEventListener(event, handler) { (this._eventListeners[event] = this._eventListeners[event] || []).push(handler); },
        removeEventListener() {},
        load() {},
        reload() {},
        remove() {},
        rename() {},
        showLogs() {},
        showSettings() {},
        setPermissions(changes) { Object.assign(this.permissions.viewer, changes); return Promise.resolve(this); },
        getLayout(id) {
            id = String(id);
            return (id in layouts) ? Object.assign({}, layouts[id]) : null;
        },
        setLayout(id, changes) {
            id = String(id);
            const current = layouts[id] || { x: null, y: null, w: 1, h: 1, minimized: false, titlevisible: true, fulldragboard: false, visible: true };
            layouts[id] = Object.assign({}, current, changes);
            return Promise.resolve(model);
        },
        removeLayout(id) {
            delete layouts[String(id)];
            return Promise.resolve(model);
        },
    }, overrides);

    return model;
};

const setupIntegration = () => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();
    installGridStackMock();

    if (!Element.prototype.getElementsByClassName) {
        Element.prototype.getElementsByClassName = function (className) {
            const results = [];
            const walk = (node) => {
                if (node.nodeType === 1) {
                    if (node.classList && node.classList.contains(className)) {
                        results.push(node);
                    }
                    (node.childNodes || []).forEach(walk);
                }
            };
            walk(this);
            return results;
        };
    }
    if (!Object.getOwnPropertyDescriptor(Element.prototype, 'children')) {
        Object.defineProperty(Element.prototype, 'children', {
            configurable: true,
            get() { return (this.childNodes || []).filter((n) => n.nodeType === 1); },
        });
    }

    const makeFragment = () => {
        const wrapper = document.createElement('div');
        const content = document.createElement('div');
        content.className = 'grid-stack-item-content panel panel-default fade';
        const heading = document.createElement('div');
        heading.className = 'wc-widget-heading panel-heading';
        content.appendChild(heading);
        const body = document.createElement('div');
        body.className = 'wc-widget-body';
        content.appendChild(body);
        wrapper.appendChild(content);
        wrapper.offsetWidth = 300;
        wrapper.offsetHeight = 200;
        return { children: [document.createElement('div'), wrapper] };
    };

    StyledElements.GUIBuilder = class GUIBuilder {
        parse(doc, tcomponents, context) {
            if (tcomponents) {
                Object.keys(tcomponents).forEach((key) => {
                    const fn = tcomponents[key];
                    if (typeof fn === 'function') fn({}, tcomponents, context);
                });
            }
            // A fresh DOM fragment per call, so widget views constructed in
            // the same test never share a wrapper element.
            return makeFragment();
        }
    };

    StyledElements.Button = class Button extends StyledElements.StyledElement {
        constructor(options = {}) {
            super(['blur', 'click', 'dblclick', 'focus', 'mouseenter', 'mouseleave']);
            this.wrapperElement = document.createElement('div');
            this.icon = document.createElement('i');
            if (options.title) this.setTitle(options.title);
        }
        addIconClassName() { return this; }
        removeIconClassName() { return this; }
        replaceIconClassName() { return this; }
        setTitle(title) { this._title = title; return this; }
        getTitle() { return this._title; }
        addClassName(name) { this.wrapperElement.classList.add(name); return this; }
    };
    StyledElements.PopupMenu = class PopupMenu extends StyledElements.StyledElement {
        constructor() { super(['visibilityChange']); this.wrapperElement = document.createElement('ul'); this._items = []; }
        append(item) { this._items.push(item); return this; }
    };
    StyledElements.PopupButton = class PopupButton extends StyledElements.Button {
        constructor(options = {}) { super(options); this.popup_menu = new StyledElements.PopupMenu(); }
    };
    StyledElements.EditableElement = class EditableElement extends StyledElements.StyledElement {
        constructor(options = {}) {
            super(['change']);
            this.wrapperElement = document.createElement('span');
            this.setTextContent(options.initialContent || '');
        }
        setTextContent(text) { this.wrapperElement.textContent = text; return this; }
        enableEdition() {}
    };

    global.Wirecloud = { Utils: StyledElements.Utils, ui: {} };
    Wirecloud.currentTheme = { templates: { 'wirecloud/workspace/widget': '<s:dummy/>' } };
    Wirecloud.UserInterfaceManager = { handleEscapeEvent() {} };
    Wirecloud.ui.LogWindowMenu = class { constructor() {} show() {} };
    Wirecloud.ui.WidgetViewMenuItems = class { constructor(view) { this.view = view; } };
    Wirecloud.URLs = { IWIDGET_COLLECTION: { evaluate: () => '/api/widgets' } };
    Wirecloud.io = { makeRequest: () => Promise.resolve({ status: 204 }) };
    Wirecloud.GlobalLogManager = { parseErrorResponse: () => 'error' };

    loadLegacyScripts([
        'src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewDragboard.js',
        'src/wirecloud/platform/static/js/wirecloud/ui/WidgetView.js',
    ]);
};

const makeIntegrationTab = (overrides = {}) => {
    const wrapperElement = document.createElement('div');
    wrapperElement.offsetWidth = overrides.width != null ? overrides.width : 1200;

    const listeners = {};
    const workspace = Object.assign({
        editing: true,
        hidden: false,
        model: { restricted: false, id: 'ws-1' },
        addEventListener(type, handler) { (listeners[type] = listeners[type] || []).push(handler); },
        _dispatch(type, ...args) { (listeners[type] || []).forEach((h) => h(...args)); },
    }, overrides.workspace);

    const tabListeners = {};
    const tab = {
        id: 'tab-1',
        hidden: false,
        wrapperElement,
        model: { id: 'tab-1', preferences: overrides.preferences || makePreferences() },
        workspace,
        addEventListener(type, handler) { (tabListeners[type] = tabListeners[type] || []).push(handler); },
        _dispatch(type, ...args) { (tabListeners[type] || []).forEach((h) => h(...args)); },
    };

    tab.dragboard = new Wirecloud.ui.WorkspaceTabViewDragboard(tab);
    return tab;
};

test('integration: constructing a WidgetView and painting the dragboard places it on the real GridStack grid', () => {
    setupIntegration();
    const tab = makeIntegrationTab();
    const model = makeStorageModel();

    const view = new Wirecloud.ui.WidgetView(tab, model, {});
    assert.equal(tab.dragboard.views.includes(view), true);
    assert.equal(view.wrapperElement.gridstackNode, undefined, 'not placed until the dragboard is painted');

    tab.dragboard.paint();

    assert.ok(view.wrapperElement.gridstackNode, 'GridStack placed the widget once painted');
    assert.equal(view.layout.visible, true);
    assert.equal(view.wrapperElement.hidden, false);
});

test('integration: minimizing collapses the real grid node height and un-minimizing restores it', () => {
    setupIntegration();
    const tab = makeIntegrationTab();
    const model = makeStorageModel({ layouts: { 2: { x: 0, y: 0, w: 4, h: 6 } } });
    const view = new Wirecloud.ui.WidgetView(tab, model, {});
    tab.dragboard.paint();

    view.heading.offsetHeight = 40;
    assert.equal(view.wrapperElement.gridstackNode.h, 6);

    return view.toggleMinimizeStatus(true).then(() => {
        assert.equal(view.wrapperElement.gridstackNode.h, 1); // 40px heading / 40px cell height
        assert.equal(view.wrapperElement.gridstackNode.noResize, true);

        return view.toggleMinimizeStatus(true);
    }).then(() => {
        assert.equal(view.wrapperElement.gridstackNode.h, 6, 'restores the remembered height');
    });
});

test('integration: hideInCurrentScreenSize removes the node from the grid and marks it hidden; showInCurrentScreenSize brings it back', async () => {
    setupIntegration();
    const tab = makeIntegrationTab();
    const model = makeStorageModel();
    const view = new Wirecloud.ui.WidgetView(tab, model, {});
    tab.dragboard.paint();

    assert.ok(view.wrapperElement.gridstackNode);

    await view.hideInCurrentScreenSize();

    assert.equal(view.wrapperElement.gridstackNode, undefined);
    assert.equal(view.wrapperElement.hidden, true);
    assert.equal(model.getLayout('2').visible, false);

    await view.showInCurrentScreenSize();

    assert.ok(view.wrapperElement.gridstackNode);
    assert.equal(view.wrapperElement.hidden, false);
    assert.equal(model.getLayout('2').visible, true);
});

test('integration: full-dragboard mode releases and restores the widget grid cells', async () => {
    setupIntegration();
    const tab = makeIntegrationTab();
    const model = makeStorageModel({ layouts: { 2: { x: 2, y: 3, w: 4, h: 5 } } });
    const view = new Wirecloud.ui.WidgetView(tab, model, {});
    tab.dragboard.paint();

    assert.ok(view.wrapperElement.gridstackNode);

    await view.setFullDragboardMode(true, false);

    assert.equal(view.wrapperElement.gridstackNode, undefined);
    assert.equal(view.layout.fulldragboard, true);
    assert.equal(view.wrapperElement.hidden, false);

    await view.setFullDragboardMode(false, false);

    assert.ok(view.wrapperElement.gridstackNode);
    assert.equal(view.wrapperElement.gridstackNode.x, 2);
    assert.equal(view.wrapperElement.gridstackNode.y, 3);
    assert.equal(view.wrapperElement.gridstackNode.w, 4);
    assert.equal(view.wrapperElement.gridstackNode.h, 5);
});

test('integration: updateGridPermissions reflects viewer permissions once the widget is placed', () => {
    setupIntegration();
    const tab = makeIntegrationTab({ workspace: { editing: false } });
    const model = makeStorageModel();
    model.permissions.viewer.move = false;
    model.permissions.viewer.resize = false;
    const view = new Wirecloud.ui.WidgetView(tab, model, {});
    tab.dragboard.paint();

    assert.equal(view.wrapperElement.gridstackNode.noMove, true);
    assert.equal(view.wrapperElement.gridstackNode.noResize, true);

    model.permissions.viewer.move = true;
    model.permissions.viewer.resize = true;
    view.updateGridPermissions();

    assert.equal(view.wrapperElement.gridstackNode.noMove, false);
    assert.equal(view.wrapperElement.gridstackNode.noResize, false);
});
