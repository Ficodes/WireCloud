const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScript,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');

// ---------------------------------------------------------------------------
// Shared setup
// ---------------------------------------------------------------------------

const setup = () => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();

    global.Wirecloud = {
        Utils: StyledElements.Utils,
        ui: {},
        UserInterfaceManager: {
            views: {
                marketplace: {
                    waitMarketListReady: (opts) => {
                        if (opts && opts.onComplete) opts.onComplete();
                    },
                },
            },
        },
    };

    StyledElements.DynamicMenuItems = class DynamicMenuItems {};
    StyledElements.MenuItem = class MenuItem {
        constructor(label, handlerOrOptions, context) {
            this.label = label;
            this.disabled = false;
            this.icons = [];
            if (typeof handlerOrOptions === 'function') {
                this.handler = handlerOrOptions;
            } else if (handlerOrOptions != null) {
                this.handler = handlerOrOptions.handler;
                this.disabled = handlerOrOptions.enabled === false;
                if (handlerOrOptions.iconClass) {
                    this.icons.push(handlerOrOptions.iconClass);
                }
            }
            this.context = context;
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
            if (this.handler) {
                this.handler.call(this, this.context);
            }
        }
    };
    StyledElements.SubMenuItem = class SubMenuItem {
        constructor(label, options = {}) {
            this.label = label;
            this.options = options;
            this.icons = options.iconClass ? [options.iconClass] : [];
            this.items = [];
        }
        append(item) {
            this.items.push(item);
            return this;
        }
    };
};

// ==========================================================================
// WorkspaceTabViewMenuItems
// ==========================================================================

test.beforeEach(() => {
    setup();

    Wirecloud.ui.RenameWindowMenu = class {
        constructor(model, title) {
            this.model = model;
            this.title = title;
            this.shown = false;
        }
        show() { this.shown = true; return this; }
    };

    Wirecloud.ui.AlertWindowMenu = class {
        constructor(message) {
            this.message = message;
            this.shown = false;
        }
        setHandler(fn) { this._handler = fn; return this; }
        show() { this.shown = true; return this; }
    };
});

const makeTab = (overrides = {}) => {
    return {
        model: {
            initial: false,
            title: 'Tab 1',
            isAllowed: () => true,
            setInitial: () => {},
            remove: () => {},
            ...(overrides.model || {}),
        },
        widgets: overrides.widgets !== undefined ? overrides.widgets : [],
        showSettings: overrides.showSettings || (() => {}),
        dragboard: overrides.dragboard || {hiddenWidgets: []},
    };
};

test('WorkspaceTabViewMenuItems build returns correct number of items', () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    const tab = makeTab();
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    const menuItems = items.build();

    assert.equal(menuItems.length, 4);
});

test('WorkspaceTabViewMenuItems item labels are correct', () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    const tab = makeTab();
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    const menuItems = items.build();

    assert.equal(menuItems[0].label, 'Rename');
    assert.equal(menuItems[1].label, 'Set as initial');
    assert.equal(menuItems[2].label, 'Settings');
    assert.equal(menuItems[3].label, 'Remove');
});

test('WorkspaceTabViewMenuItems item icons are correct', () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    const tab = makeTab();
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    const menuItems = items.build();

    assert.ok(menuItems[0].icons.includes('fas fa-pencil-alt'));
    assert.ok(menuItems[1].icons.includes('fas fa-home'));
    assert.ok(menuItems[2].icons.includes('fas fa-cog'));
    assert.ok(menuItems[3].icons.includes('fas fa-trash'));
});

test('WorkspaceTabViewMenuItems "Set as initial" disabled when tab is already initial', () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    const tab = makeTab({ model: { initial: true } });
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    const menuItems = items.build();

    assert.equal(menuItems[1].disabled, true);
});

test('WorkspaceTabViewMenuItems "Set as initial" enabled when tab is not initial', () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    const tab = makeTab({ model: { initial: false } });
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    const menuItems = items.build();

    assert.equal(menuItems[1].disabled, false);
});

test('WorkspaceTabViewMenuItems "Set as initial" click handler calls setInitial', () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    let setInitialCalled = false;
    const tab = makeTab({ model: { initial: false, setInitial: () => { setInitialCalled = true; } } });
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    const menuItems = items.build();

    menuItems[1].tab = tab;
    menuItems[1].run();

    assert.equal(setInitialCalled, true);
});

test('WorkspaceTabViewMenuItems "Remove" disabled when not allowed', () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    const tab = makeTab({ model: { isAllowed: (perm) => perm !== 'remove' } });
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    const menuItems = items.build();

    assert.equal(menuItems[3].disabled, true);
});

test('WorkspaceTabViewMenuItems "Remove" enabled when allowed', () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    const tab = makeTab({ model: { isAllowed: () => true } });
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    const menuItems = items.build();

    assert.equal(menuItems[3].disabled, false);
});

test('WorkspaceTabViewMenuItems "Rename" handler opens RenameWindowMenu', () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    const tab = makeTab();
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    const menuItems = items.build();

    const lastConstructed = [];
    Wirecloud.ui.RenameWindowMenu = class {
        constructor(model, title) {
            lastConstructed.push({ model, title });
        }
        show() { return this; }
    };

    menuItems[0].run();
    assert.equal(lastConstructed.length, 1);
    assert.equal(lastConstructed[0].model, tab.model);
    assert.equal(lastConstructed[0].title, 'Rename Workspace Tab');
});

test('WorkspaceTabViewMenuItems "Settings" handler calls tab.showSettings', () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    let called = false;
    const tab = makeTab({ showSettings: () => { called = true; } });
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    const menuItems = items.build();

    menuItems[2].run();
    assert.equal(called, true);
});

test('WorkspaceTabViewMenuItems "Remove" directly removes when no widgets', () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    let removed = false;
    const tab = makeTab({
        widgets: [],
        model: { remove: () => { removed = true; } },
    });
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    const menuItems = items.build();

    menuItems[3].run();
    assert.equal(removed, true);
});

test('WorkspaceTabViewMenuItems "Remove" shows confirmation when tab has widgets', () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    let alertShown = false;
    let alertMessage = '';
    let handlerCalled = false;
    let removed = false;

    Wirecloud.ui.AlertWindowMenu = class {
        constructor(message) {
            alertShown = true;
            alertMessage = message;
        }
        setHandler(fn) {
            handlerCalled = true;
            this._handler = fn;
            return this;
        }
        show() {
            this._handler();
            return this;
        }
    };

    const tab = makeTab({
        widgets: [{ id: 'w1' }],
        model: { remove: () => { removed = true; } },
    });
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    const menuItems = items.build();

    menuItems[3].run();

    assert.equal(alertShown, true);
    assert.ok(alertMessage.includes("tab's widgets"));
    assert.equal(removed, true); // handler executed by mock show()
});

test('WorkspaceTabViewMenuItems inherits from DynamicMenuItems', () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    const tab = makeTab();
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    assert.ok(items instanceof StyledElements.DynamicMenuItems);
});

// -- "Hidden widgets" submenu -----------------------------------------------

test('WorkspaceTabViewMenuItems does not add a "Hidden widgets" submenu when nothing is hidden', () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    const tab = makeTab({dragboard: {hiddenWidgets: []}});
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    const menuItems = items.build();

    assert.equal(menuItems.length, 4);
});

test('WorkspaceTabViewMenuItems adds a "Hidden widgets" submenu when the dragboard reports hidden widgets', () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    const hiddenView = {title: 'My Hidden Widget', showInCurrentScreenSize: () => {}};
    const tab = makeTab({dragboard: {hiddenWidgets: [hiddenView]}});
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    const menuItems = items.build();

    assert.equal(menuItems.length, 5);
    const submenu = menuItems[4];
    assert.equal(submenu.label, 'Hidden widgets');
    assert.ok(submenu.icons.includes('fas fa-eye-slash'));
});

test('WorkspaceTabViewMenuItems "Hidden widgets" submenu has one entry per hidden widget, named after its title', () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    const widgetA = {title: 'Widget A', showInCurrentScreenSize: () => {}};
    const widgetB = {title: 'Widget B', showInCurrentScreenSize: () => {}};
    const tab = makeTab({dragboard: {hiddenWidgets: [widgetA, widgetB]}});
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    const menuItems = items.build();

    const submenu = menuItems[4];
    assert.equal(submenu.items.length, 2);
    assert.equal(submenu.items[0].label, 'Widget A');
    assert.equal(submenu.items[1].label, 'Widget B');
});

test('WorkspaceTabViewMenuItems "Hidden widgets" entry click calls showInCurrentScreenSize on that widget', () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    let shownCalled = false;
    const widgetA = {title: 'Widget A', showInCurrentScreenSize: () => { shownCalled = true; }};
    const tab = makeTab({dragboard: {hiddenWidgets: [widgetA]}});
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    const menuItems = items.build();

    menuItems[4].items[0].run();

    assert.equal(shownCalled, true);
});

// ==========================================================================
// WorkspaceViewMenuItems
// ==========================================================================

const setupView = () => {
    setup();

    Wirecloud.ui.NewWorkspaceWindowMenu = class {
        constructor(opts) {
            this.opts = opts;
            this.shown = false;
        }
        show() { this.shown = true; return this; }
    };

    Wirecloud.ui.RenameWindowMenu = class {
        constructor(model, title) {
            this.model = model;
            this.title = title;
            this.shown = false;
        }
        show() { this.shown = true; return this; }
    };

    Wirecloud.ui.SharingWindowMenu = class {
        constructor(workspace) {
            this.workspace = workspace;
            this.shown = false;
        }
        show() { this.shown = true; return this; }
    };

    Wirecloud.ui.PublishWorkspaceWindowMenu = class {
        constructor(model) {
            this.model = model;
            this.shown = false;
        }
        show() { this.shown = true; return this; }
    };

    Wirecloud.ui.EmbedCodeWindowMenu = class {
        constructor(title, workspace) {
            this.title = title;
            this.workspace = workspace;
            this.shown = false;
        }
        show() { this.shown = true; return this; }
    };

    Wirecloud.ui.AlertWindowMenu = class {
        constructor(message) {
            this.message = message;
            this.shown = false;
        }
        setHandler(fn) { this._handler = fn; return this; }
        show() { this.shown = true; return this; }
    };
};

const makeWorkspace = (overrides = {}) => {
    return {
        model: {
            title: 'Test WS',
            id: 1,
            isAllowed: () => true,
            rename: () => Promise.resolve(),
            remove: () => Promise.resolve(),
            ...(overrides.model || {}),
        },
        editing: overrides.editing !== undefined ? overrides.editing : true,
        title: overrides.title || 'Test WS',
        showSettings: overrides.showSettings || (() => {}),
    };
};

test('WorkspaceViewMenuItems build returns correct number of items', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    const workspace = makeWorkspace();
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    const menuItems = items.build();

    assert.equal(menuItems.length, 8);
});

test('WorkspaceViewMenuItems item labels are correct', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    const workspace = makeWorkspace();
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    const menuItems = items.build();

    assert.equal(menuItems[0].label, 'New workspace');
    assert.equal(menuItems[1].label, 'Rename');
    assert.equal(menuItems[2].label, 'Share');
    assert.equal(menuItems[3].label, 'Upload to my resources');
    assert.equal(menuItems[4].label, 'Embed');
    assert.equal(menuItems[5].label, 'Settings');
    assert.equal(menuItems[6].label, 'Duplicate');
    assert.equal(menuItems[7].label, 'Remove');
});

test('WorkspaceViewMenuItems item icons are correct', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    const workspace = makeWorkspace();
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    const menuItems = items.build();

    assert.ok(menuItems[0].icons.includes('fas fa-plus'));
    assert.ok(menuItems[1].icons.includes('fas fa-pencil-alt'));
    assert.ok(menuItems[2].icons.includes('fas fa-share'));
    assert.ok(menuItems[3].icons.includes('fas fa-archive'));
    assert.ok(menuItems[4].icons.includes('fas fa-code'));
    assert.ok(menuItems[5].icons.includes('fas fa-cog'));
    assert.ok(menuItems[6].icons.includes('fas fa-clone'));
    assert.ok(menuItems[7].icons.includes('fas fa-trash'));
});

test('WorkspaceViewMenuItems "Rename" disabled when not editing', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    const workspace = makeWorkspace({ editing: false });
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    const menuItems = items.build();

    assert.equal(menuItems[1].disabled, true);
});

test('WorkspaceViewMenuItems "Rename" disabled when not allowed', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    const workspace = makeWorkspace({
        model: { isAllowed: (perm) => perm !== 'rename' },
    });
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    const menuItems = items.build();

    assert.equal(menuItems[1].disabled, true);
});

test('WorkspaceViewMenuItems "Rename" enabled when editing and allowed', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    const workspace = makeWorkspace({ editing: true });
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    const menuItems = items.build();

    assert.equal(menuItems[1].disabled, false);
});

test('WorkspaceViewMenuItems "Settings" disabled when not editing', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    const workspace = makeWorkspace({ editing: false });
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    const menuItems = items.build();

    assert.equal(menuItems[5].disabled, true);
});

test('WorkspaceViewMenuItems "Settings" disabled when update_preferences not allowed', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    const workspace = makeWorkspace({
        model: { isAllowed: (perm) => perm !== 'update_preferences' },
    });
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    const menuItems = items.build();

    assert.equal(menuItems[5].disabled, true);
});

test('WorkspaceViewMenuItems "Remove" disabled when not allowed', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    const workspace = makeWorkspace({
        model: { isAllowed: (perm) => perm !== 'remove' },
    });
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    const menuItems = items.build();

    assert.equal(menuItems[7].disabled, true);
});

test('WorkspaceViewMenuItems "New workspace" handler opens NewWorkspaceWindowMenu', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    const createdInstances = [];
    Wirecloud.ui.NewWorkspaceWindowMenu = class {
        constructor() {
            createdInstances.push(true);
        }
        show() { return this; }
    };

    const workspace = makeWorkspace();
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    const menuItems = items.build();

    menuItems[0].run();
    assert.equal(createdInstances.length, 1);
});

test('WorkspaceViewMenuItems "Rename" handler opens RenameWindowMenu with model', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    const createdInstances = [];
    Wirecloud.ui.RenameWindowMenu = class {
        constructor(model, title) {
            createdInstances.push({ model, title });
        }
        show() { return this; }
    };

    const workspace = makeWorkspace({ model: { isAllowed: () => true } });
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    const menuItems = items.build();

    menuItems[1].run();
    assert.equal(createdInstances.length, 1);
    assert.equal(createdInstances[0].model, workspace.model);
    assert.equal(createdInstances[0].title, 'Rename Workspace');
});

test('WorkspaceViewMenuItems "Share" handler opens SharingWindowMenu with workspace', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    const createdInstances = [];
    Wirecloud.ui.SharingWindowMenu = class {
        constructor(ws) {
            createdInstances.push(ws);
        }
        show() { return this; }
    };

    const workspace = makeWorkspace();
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    const menuItems = items.build();

    menuItems[2].run();
    assert.equal(createdInstances.length, 1);
    assert.equal(createdInstances[0], workspace);
});

test('WorkspaceViewMenuItems "Upload to my resources" handler opens PublishWorkspaceWindowMenu', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    const createdInstances = [];
    Wirecloud.ui.PublishWorkspaceWindowMenu = class {
        constructor(model) {
            createdInstances.push(model);
        }
        show() { return this; }
    };

    const workspace = makeWorkspace();
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    const menuItems = items.build();

    menuItems[3].run();
    assert.equal(createdInstances.length, 1);
    assert.equal(createdInstances[0], workspace.model);
});

test('WorkspaceViewMenuItems "Embed" handler opens EmbedCodeWindowMenu', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    const createdInstances = [];
    Wirecloud.ui.EmbedCodeWindowMenu = class {
        constructor(title, ws) {
            createdInstances.push({ title, ws });
        }
        show() { return this; }
    };

    const workspace = makeWorkspace();
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    const menuItems = items.build();

    menuItems[4].run();
    assert.equal(createdInstances.length, 1);
    assert.equal(createdInstances[0].title, 'Embed Code');
    assert.equal(createdInstances[0].ws, workspace);
});

test('WorkspaceViewMenuItems "Settings" handler calls showSettings', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    let called = false;
    const workspace = makeWorkspace({ showSettings: () => { called = true; } });
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    const menuItems = items.build();

    menuItems[5].run();
    assert.equal(called, true);
});

test('WorkspaceViewMenuItems "Duplicate" handler opens NewWorkspaceWindowMenu with workspace copy options', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    const createdInstances = [];
    Wirecloud.ui.NewWorkspaceWindowMenu = class {
        constructor(opts) {
            createdInstances.push(opts);
        }
        show() { return this; }
    };

    const workspace = makeWorkspace({ model: { id: 42 } });
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    const menuItems = items.build();

    menuItems[6].run();
    assert.equal(createdInstances.length, 1);
    assert.equal(createdInstances[0].workspace, 42);
    assert.ok(createdInstances[0].title.includes('Copy of'));
});

test('WorkspaceViewMenuItems "Remove" handler shows confirmation dialog and removes on confirm', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    let alertMessage = '';
    let removed = false;

    Wirecloud.ui.AlertWindowMenu = class {
        constructor(message) {
            alertMessage = message;
        }
        setHandler(fn) {
            this.handler = fn;
            return this;
        }
        show() {
            this.handler();
            return this;
        }
    };

    const workspace = makeWorkspace({
        title: 'My Workspace',
        model: { remove: () => { removed = true; return Promise.resolve(); } },
    });
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    const menuItems = items.build();

    menuItems[7].run();

    assert.ok(alertMessage.includes('My Workspace'));
    assert.ok(alertMessage.includes('remove'));
    assert.equal(removed, true);
});

test('WorkspaceViewMenuItems inherits from DynamicMenuItems', () => {
    setupView();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    const workspace = makeWorkspace();
    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    assert.ok(items instanceof StyledElements.DynamicMenuItems);
});
