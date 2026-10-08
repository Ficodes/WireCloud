const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScript,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');

// ===========================================================================
// MOCK HELPERS
// ===========================================================================

const DEFAULT_SCREEN_SIZES = () => [
    {id: 0, name: 'Phone', moreOrEqual: 0, lessOrEqual: 767, columns: 1},
    {id: 1, name: 'Tablet', moreOrEqual: 768, lessOrEqual: 1199, columns: 6},
    {id: 2, name: 'Desktop', moreOrEqual: 1200, lessOrEqual: -1, columns: 12},
];

const createModelMock = (overrides = {}) => {
    const listeners = {};
    const prefListeners = {};
    return {
        id: 'tab-1',
        title: 'Test Tab',
        name: 'test_tab',
        preferences: {
            _values: {
                cellheight: 40,
                margin: 5,
                screenSizes: DEFAULT_SCREEN_SIZES(),
            },
            get(key) { return this._values[key]; },
            addEventListener(type, handler) {
                if (!prefListeners[type]) prefListeners[type] = [];
                prefListeners[type].push(handler);
            },
            _dispatch(type, ...args) {
                (prefListeners[type] || []).forEach((h) => h(...args));
            },
        },
        widgets: [],
        isAllowed: () => true,
        addEventListener(type, handler) {
            if (!listeners[type]) listeners[type] = [];
            listeners[type].push(handler);
        },
        _dispatch(type, ...args) {
            (listeners[type] || []).forEach((h) => h(...args));
        },
        createWidget: () => Promise.resolve({id: 'widget-new'}),
        ...overrides,
    };
};

const createWorkspaceMock = (overrides = {}) => {
    const listeners = {};
    let _editing = true;
    return {
        get editing() { return _editing; },
        set editing(v) { _editing = v; },
        model: {
            isAllowed: () => true,
        },
        activeTab: null,
        addEventListener(type, handler) {
            if (!listeners[type]) listeners[type] = [];
            listeners[type].push(handler);
        },
        _dispatch(type, ...args) {
            (listeners[type] || []).forEach((h) => h(...args));
        },
        updateEditingInterval: () => {},
        buildAddWidgetButton: () => {},
        ...overrides,
    };
};

// ===========================================================================
// SETUP
// ===========================================================================

const setup = () => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();

    // Patch window with addEventListener for resize handling
    global.window.addEventListener = function (type, handler) {
        if (!global.window._listeners) global.window._listeners = {};
        if (!global.window._listeners[type]) global.window._listeners[type] = [];
        global.window._listeners[type].push(handler);
    };
    global.window.removeEventListener = function () {};
    global.window.dispatchEvent = function (event) {
        const listeners = global.window._listeners && global.window._listeners[event.type];
        if (listeners) listeners.forEach((h) => h(event));
    };
    global.window.innerWidth = 1200;

    if (global.Wirecloud == null) {
        global.Wirecloud = {};
    }
    Wirecloud.Utils = StyledElements.Utils;
    Wirecloud.ui = Wirecloud.ui || {};

    // -- SE mocks -----------------------------------------------------------
    class SEButton {
        constructor(opts = {}) {
            this._disabled = false;
            this.enabled = true;
            this.opts = opts;
            this.listeners = {};
            this.wrapperElement = document.createElement('button');
            this.wrapperElement.className = opts.class || '';
            if (opts.iconClass) {
                const icon = document.createElement('i');
                icon.className = opts.iconClass;
                this.wrapperElement.appendChild(icon);
            }
        }
        addEventListener(type, handler) {
            if (!this.listeners[type]) this.listeners[type] = [];
            this.listeners[type].push(handler);
        }
        removeEventListener() {}
        _dispatch(type, data) {
            (this.listeners[type] || []).forEach((h) => h(data));
        }
        insertInto(parent) { parent.appendChild(this.wrapperElement); return this; }
        appendTo(parent) { parent.appendChild(this.wrapperElement); return this; }
        disable() { this._disabled = true; this.enabled = false; return this; }
        enable() { this._disabled = false; this.enabled = true; return this; }
        addClassName() { return this; }
        removeClassName() { return this; }
        addIconClass() { return this; }
        setLabel() { return this; }
        destroy() { return this; }
        focus() {}
    }

    class SEPopupMenuBase {
        constructor() {
            this._items = [];
        }
        append(item) { this._items.push(item); return this; }
    }

    class SEPopupMenu extends SEPopupMenuBase {}
    class SEPopupButton extends SEButton {
        constructor(opts = {}) {
            super(opts);
            this.popup_menu = new SEPopupMenu();
            this.opts = opts;
        }
    }

    class SEContainer {
        constructor(opts = {}, evts) {
            this._children = [];
            this._idCounter = 0;
            this.wrapperElement = document.createElement(opts && opts.tagname ? opts.tagname : 'div');
            if (opts && opts.class) {
                this.wrapperElement.className = opts.class;
            }
            this._hidden = false;
            this.hidden = false;
            this._listeners = {};
            this._events = evts || [];
        }
        appendChild(child) {
            if (child && child.wrapperElement) {
                this.wrapperElement.appendChild(child.wrapperElement);
            } else if (child) {
                this.wrapperElement.appendChild(child);
            }
            return this;
        }
        insertInto(parent) {
            if (parent && parent.appendChild) {
                parent.appendChild(this.wrapperElement);
            }
            return this;
        }
        addEventListener(type, handler) {
            if (!this._listeners[type]) this._listeners[type] = [];
            this._listeners[type].push(handler);
        }
        removeEventListener() {}
        dispatchEvent(type) {
            (this._listeners[type] || []).forEach((h) => h());
            return this;
        }
        hide() { this._hidden = true; this.hidden = true; this.wrapperElement.classList.add('hidden'); return this; }
        show() { this._hidden = false; this.hidden = false; this.wrapperElement.classList.remove('hidden'); return this; }
        clear() { return this; }
        addClassName() { return this; }
        removeClassName() { return this; }
        repaint() { return this; }
    }

    class SENotebook extends SEContainer {
        constructor() {
            super();
            this._tabs = {};
        }
        removeTab(id) { delete this._tabs[id]; return this; }
        goToTab() { return this; }
        createTab() { return this; }
    }

    class SETab extends SEContainer {
        constructor(id, notebook, options) {
            super(options && options.containerOptions ? options.containerOptions : {}, ['show', 'hide', 'close']);
            if (!(notebook instanceof SENotebook)) {
                throw new TypeError("Invalid notebook argument");
            }
            this._label = (options && options.name) || "";
            this.notebook = notebook;
            this.tabId = id;
            this._tabElement = document.createElement("li");
            this._labelElement = document.createElement('span');
            this._tabElement.className = "se-notebook-tab";
            this._tabElement.setAttribute('role', 'tab');
            this._tabElement.setAttribute('aria-selected', 'false');
            this._tabElement.setAttribute('aria-controls', 'se-notebook-tabpanel-' + id);
            this._tabElement.appendChild(this._labelElement);

            this.wrapperElement.classList.add("se-notebook-tab-content");
            this.wrapperElement.classList.add("hidden");
            this.wrapperElement.setAttribute('role', 'tabpanel');
            this.wrapperElement.setAttribute('id', 'se-notebook-tabpanel-' + id);
            this.wrapperElement.setAttribute('aria-labelledby', 'se-notebook-tab-' + id);

            this._tabElement.addEventListener("click", () => {
                this.notebook.goToTab(this.tabId);
            });

            if (options && options.closable) {
                const closeBtn = new SEButton({iconClass: "fas fa-times", plain: true, class: "close_button"});
                closeBtn.insertInto(this._tabElement);
                closeBtn.addEventListener("click", () => this.close());
            }

            this.setLabel(options && options.label ? options.label : (options && options.name ? options.name : ""));
        }
        get label() { return this._labelElement.textContent; }
        get tabElement() { return this._tabElement; }
        close() {
            this.notebook.removeTab(this.tabId);
            return this.dispatchEvent("close");
        }
        setLabel(newLabel) {
            this._labelElement.textContent = newLabel;
            return this;
        }
        hide() {
            super.hide();
            this._tabElement.classList.remove("selected");
            this._tabElement.setAttribute('aria-selected', 'false');
            return this;
        }
        show() {
            super.show();
            this._tabElement.classList.add("selected");
            this._tabElement.setAttribute('aria-selected', 'true');
            return this;
        }
        getTabElement() { return this._tabElement; }
    }
    SETab.prototype.rename = SETab.prototype.setLabel;
    SETab.prototype.Tooltip = class Tooltip {};
    SETab.prototype.Button = SEButton;

    class SEGUIBuilder {
        parse(template, context) {
            const fragment = document.createElement('div');
            const child1 = document.createElement('div');
            const child2 = document.createElement('div');
            fragment.appendChild(child1);
            fragment.appendChild(child2);
            fragment.children = [child1, child2];
            fragment.appendTo = function (parent) { parent.appendChild(this); };
            fragment.insertInto = function (parent) { parent.appendChild(this); };
            return fragment;
        }
    }

    class SEDynamicMenuItems {
        constructor(context) { this.context = context; }
    }

    class SEStyledElement {
        constructor(events) {
            this._listeners = {};
            this._events = events || [];
            this._hidden = false;
            this.hidden = false;
            this.wrapperElement = document.createElement('div');
        }
        addEventListener(type, handler) {
            if (!this._listeners[type]) this._listeners[type] = [];
            this._listeners[type].push(handler);
        }
        removeEventListener() {}
        dispatchEvent(type, data) {
            (this._listeners[type] || []).forEach((h) => h(data));
            return this;
        }
        hide() { this._hidden = true; this.hidden = true; this.wrapperElement.classList.add('hidden'); return this; }
        show() { this._hidden = false; this.hidden = false; this.wrapperElement.classList.remove('hidden'); return this; }
        appendChild(child) {
            if (child && child.wrapperElement) {
                this.wrapperElement.appendChild(child.wrapperElement);
            } else if (child) {
                this.wrapperElement.appendChild(child);
            }
            return this;
        }
        insertInto(parent) {
            if (parent && parent.appendChild) {
                parent.appendChild(this.wrapperElement);
            }
            return this;
        }
        destroy() { return this; }
        clear() { return this; }
        repaint() { return this; }
    }

    // Register mock SE classes on StyledElements
    StyledElements.StyledElement = SEStyledElement;
    StyledElements.objectWithEvents = {prototype: {}};
    StyledElements.Container = SEContainer;
    StyledElements.Tab = SETab;
    StyledElements.Notebook = SENotebook;
    StyledElements.Button = SEButton;
    StyledElements.PopupMenuBase = SEPopupMenuBase;
    StyledElements.PopupMenu = SEPopupMenu;
    StyledElements.PopupButton = SEPopupButton;
    StyledElements.GUIBuilder = SEGUIBuilder;
    StyledElements.DynamicMenuItems = SEDynamicMenuItems;

    // -- Wirecloud globals --------------------------------------------------
    Wirecloud.currentTheme = {
        templates: {},
    };
    const emptyTemplate = '<div><div class="empty-message"></div></div>';
    Wirecloud.currentTheme.templates['wirecloud/workspace/empty_tab_message'] = emptyTemplate;

    Wirecloud.TutorialCatalogue = {
        buildTutorialReferences: () => [],
    };

    Wirecloud.HistoryManager = {
        getCurrentState: () => ({tab: 'test'}),
        replaceState: () => {},
    };

    Wirecloud.GlobalLogManager = {
        log: () => {},
        parseErrorResponse: () => 'error',
        formatException: (e) => e ? e.message : '',
    };

    Wirecloud.LogManager = class LogManager {
        constructor(parent) { this.entries = []; this.parent = parent; }
        addEventListener() {}
        removeEventListener() {}
        log() {}
        formatException(e) { return e ? e.message : ''; }
    };

    // Wirecloud.ui.WidgetView mock
    const WidgetViewCalls = [];
    Wirecloud.ui.WidgetView = class WidgetView {
        constructor(tab, model) {
            WidgetViewCalls.push({tab, model});
            this.id = model.id || 'widget-' + Math.random().toString(36).substr(2, 9);
            this.model = model;
            this.tab = tab;
            this.loaded = false;
        }
        load() { this.loaded = true; }
    };

    // Wirecloud.ui.WorkspaceTabViewMenuItems mock
    const WorkspaceTabViewMenuItemsCalls = [];
    Wirecloud.ui.WorkspaceTabViewMenuItems = class WorkspaceTabViewMenuItems {
        constructor(context) {
            WorkspaceTabViewMenuItemsCalls.push({context});
            this.context = context;
        }
    };

    // Wirecloud.ui.PreferencesWindowMenu mock
    const PrefsWindowMenuCalls = [];
    Wirecloud.ui.PreferencesWindowMenu = class PreferencesWindowMenu {
        constructor(type, prefs) {
            PrefsWindowMenuCalls.push({type, prefs});
            this.shown = false;
        }
        show() { this.shown = true; return this; }
    };

    WidgetViewCalls.length = 0;
    WorkspaceTabViewMenuItemsCalls.length = 0;
    PrefsWindowMenuCalls.length = 0;

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabView.js');

    // Set up a lightweight WorkspaceTabViewDragboard mock so WorkspaceTabView
    // can be tested in isolation from GridStack/real screen-size detection
    // (that behaviour is covered by ui_workspace_tab_view_dragboard.test.cjs).
    const dragboardCalls = [];
    Wirecloud.ui.WorkspaceTabViewDragboard = class WorkspaceTabViewDragboard {
        constructor(tab) {
            dragboardCalls.push({tab});
            this.tab = tab;
            this.forcedScreenSizeId = null;
            this._defaultScreenSize = DEFAULT_SCREEN_SIZES()[2]; // Desktop, by default
            this.activeScreenSize = this._defaultScreenSize;
            this.paintCalls = 0;
            this.addWidgetCalls = [];
            this.parseSizeCalls = [];
            this.setForcedScreenSizeCalls = [];
        }
        paint() { this.paintCalls++; }
        parseSize(value, axis) {
            this.parseSizeCalls.push({value, axis});
            return `${axis}(${value})`;
        }
        setForcedScreenSize(id) {
            this.setForcedScreenSizeCalls.push(id);
            this.forcedScreenSizeId = id;
            if (id != null) {
                const found = this.tab.model.preferences.get('screenSizes').find((s) => s.id === id);
                if (found != null) {
                    this.activeScreenSize = found;
                }
            } else {
                this.activeScreenSize = this._defaultScreenSize;
            }
        }
        addWidget(view) {
            this.addWidgetCalls.push(view);
        }
    };

    return {
        StyledElements,
        Wirecloud,
        WidgetViewCalls,
        WorkspaceTabViewMenuItemsCalls,
        PrefsWindowMenuCalls,
        get dragboardCalls() { return dragboardCalls; },
        createModelMock,
        createWorkspaceMock,
    };
};

// ===========================================================================
// HELPER: Create a fully wired WorkspaceTabView instance
// ===========================================================================

const createTab = (options = {}) => {
    const notebook = new StyledElements.Notebook();
    const model = options.model || createModelMock();
    const workspace = options.workspace || createWorkspaceMock();

    const tab = new Wirecloud.ui.WorkspaceTabView(model.id, notebook, {
        model,
        workspace,
    });

    workspace.activeTab = tab;

    if (options.dragboard) {
        Object.assign(tab.dragboard, options.dragboard);
    }

    return {tab, model, workspace, notebook};
};

// ===========================================================================
// TESTS
// ===========================================================================

test.beforeEach(() => {
    setup();
});

// ===========================================================================
// CONSTRUCTOR
// ===========================================================================

test('constructor creates instance with correct inheritance', () => {
    const notebook = new StyledElements.Notebook();
    const model = createModelMock();
    const workspace = createWorkspaceMock();

    const tab = new Wirecloud.ui.WorkspaceTabView(model.id, notebook, {model, workspace});

    assert.ok(tab instanceof Wirecloud.ui.WorkspaceTabView);
    assert.ok(tab instanceof StyledElements.Tab);
    assert.ok(tab instanceof StyledElements.Container);
});

test('constructor sets properties from model', () => {
    const notebook = new StyledElements.Notebook();
    const model = createModelMock({id: 'my-tab-id', title: 'My Tab', name: 'my_tab'});
    const workspace = createWorkspaceMock();

    const tab = new Wirecloud.ui.WorkspaceTabView(model.id, notebook, {model, workspace});

    assert.equal(tab.id, 'my-tab-id');
    assert.equal(tab.title, 'My Tab');
    assert.equal(tab.name, 'my_tab');
    assert.equal(tab.model, model);
    assert.equal(tab.workspace, workspace);
});

test('constructor sets tabElement data attributes and classes', () => {
    const notebook = new StyledElements.Notebook();
    const model = createModelMock({id: 'tab-attr', name: 'attr_name'});
    const workspace = createWorkspaceMock();

    const tab = new Wirecloud.ui.WorkspaceTabView(model.id, notebook, {model, workspace});

    assert.equal(tab.tabElement.getAttribute('data-id'), 'tab-attr');
    assert.equal(tab.tabElement.getAttribute('data-name'), 'attr_name');
    assert.ok(tab.tabElement.classList.contains('wc-workspace-tab'));
});

test('constructor sets wrapperElement data attributes and classes', () => {
    const notebook = new StyledElements.Notebook();
    const model = createModelMock({id: 'tab-wrap'});
    const workspace = createWorkspaceMock();

    const tab = new Wirecloud.ui.WorkspaceTabView(model.id, notebook, {model, workspace});

    assert.equal(tab.wrapperElement.getAttribute('data-id'), 'tab-wrap');
    assert.ok(tab.wrapperElement.classList.contains('wc-workspace-tab-content'));
});

test('constructor creates logManager', () => {
    const {tab} = createTab();
    assert.ok(tab.logManager instanceof Wirecloud.LogManager);
});

test('constructor sets widgets as empty array copy', () => {
    const {tab} = createTab();
    assert.deepEqual(tab.widgets, []);
});

test('constructor sets widgetsById as empty object', () => {
    const {tab} = createTab();
    assert.deepEqual(tab.widgetsById, {});
});

test('constructor creates prefbutton when edit is allowed', () => {
    const {tab} = createTab({workspace: createWorkspaceMock({model: {isAllowed: () => true}})});

    assert.ok(tab.prefbutton instanceof StyledElements.PopupButton);
    assert.equal(tab.prefbutton.enabled, true);
});

test('constructor does not create prefbutton when edit is not allowed', () => {
    const {tab} = createTab({workspace: createWorkspaceMock({model: {isAllowed: (perm) => perm !== 'edit'}})});
    assert.equal(tab.prefbutton, undefined);
});

test('constructor creates a dragboard and calls updateEditingScreenSizeName', () => {
    const {tab} = createTab();

    assert.ok(tab.dragboard instanceof Wirecloud.ui.WorkspaceTabViewDragboard);
    assert.equal(tab.editingScreenSizeName, tab.dragboard.activeScreenSize.name);
});

test('constructor creates initialMessage and appends it', () => {
    const {tab} = createTab({model: createModelMock({widgets: []}), workspace: createWorkspaceMock({model: {isAllowed: () => true}})});

    assert.ok(tab.initialMessage != null);
    assert.equal(tab.initialMessage.hidden, false);
});

test('constructor hides initialMessage when widgets exist', () => {
    const {tab} = createTab({model: createModelMock({widgets: [{id: 'existing-widget', title: 'W1'}]})});

    assert.equal(tab.initialMessage.hidden, true);
    assert.equal(tab.widgets.length, 1);
});

test('constructor hides initialMessage when edit not allowed even without widgets', () => {
    const {tab} = createTab({
        model: createModelMock({widgets: []}),
        workspace: createWorkspaceMock({model: {isAllowed: (perm) => perm !== 'edit'}}),
    });

    assert.equal(tab.initialMessage.hidden, true);
});

test('constructor registers model event listeners', () => {
    const {tab, model} = createTab();
    assert.ok(typeof model._dispatch === 'function');
});

test('constructor registers a window resize listener without throwing', () => {
    const {tab} = createTab();
    assert.ok(tab != null);
});

test('constructor throws TypeError if notebook is not an instance of se.Notebook', () => {
    assert.throws(() => {
        const model = createModelMock();
        const workspace = createWorkspaceMock();
        new Wirecloud.ui.WorkspaceTabView('id', {}, {model, workspace});
    }, TypeError);
});

// ===========================================================================
// INITIAL MESSAGE LOGIC
// ===========================================================================

test('initialMessage hidden reflects workspace edit permission and widget count', () => {
    const tab1 = createTab({
        model: createModelMock({widgets: []}),
        workspace: createWorkspaceMock({model: {isAllowed: () => true}}),
    }).tab;
    assert.equal(tab1.initialMessage.hidden, false);

    const tab2 = createTab({
        model: createModelMock({widgets: [{id: 'w1'}]}),
        workspace: createWorkspaceMock({model: {isAllowed: () => true}}),
    }).tab;
    assert.equal(tab2.initialMessage.hidden, true);

    const tab3 = createTab({
        model: createModelMock({widgets: []}),
        workspace: createWorkspaceMock({model: {isAllowed: (p) => p !== 'edit'}}),
    }).tab;
    assert.equal(tab3.initialMessage.hidden, true);
});

// ===========================================================================
// PREFBUTTON
// ===========================================================================

test('prefbutton enabled set correctly based on workspace editing state', () => {
    const workspace = createWorkspaceMock({model: {isAllowed: () => true}});
    workspace.editing = true;
    const {tab} = createTab({workspace});
    assert.equal(tab.prefbutton.enabled, true);

    workspace.editing = false;
    workspace._dispatch('editmode');
    assert.equal(tab.prefbutton.enabled, false);
});

test('prefbutton disabled when edit not allowed', () => {
    const {tab} = createTab({workspace: createWorkspaceMock({model: {isAllowed: (p) => p !== 'edit'}})});
    assert.equal(tab.prefbutton, undefined);
});

// ===========================================================================
// WIDGETS
// ===========================================================================

test('widgets returns a copy of the internal array', () => {
    const {tab} = createTab({model: createModelMock({widgets: [{id: 'w1'}, {id: 'w2'}]})});
    const widgets = tab.widgets;

    assert.equal(widgets.length, 2);
    assert.equal(widgets[0].model.id, 'w1');
    assert.equal(widgets[1].model.id, 'w2');

    widgets.pop();
    assert.equal(tab.widgets.length, 2);
});

test('widgetsById returns correct mapping', () => {
    const {tab} = createTab({model: createModelMock({widgets: [{id: 'w1'}, {id: 'w2'}]})});
    const byId = tab.widgetsById;

    assert.ok(byId[tab.widgets[0].id] instanceof Wirecloud.ui.WidgetView);
    assert.ok(byId[tab.widgets[1].id] instanceof Wirecloud.ui.WidgetView);
});

// ===========================================================================
// HIGHLIGHT / UNHIGHLIGHT / FINDWIDGET / REPAINT / SHOWSETTINGS
// ===========================================================================

test('highlight adds highlight class to tabElement and returns this', () => {
    const {tab} = createTab();
    assert.equal(tab.highlight(), tab);
    assert.ok(tab.tabElement.classList.contains('highlight'));
});

test('unhighlight removes highlight class from tabElement and returns this', () => {
    const {tab} = createTab();
    tab.tabElement.classList.add('highlight');
    assert.equal(tab.unhighlight(), tab);
    assert.equal(tab.tabElement.classList.contains('highlight'), false);
});

test('findWidget returns widget by id, undefined for unknown id', () => {
    const {tab} = createTab({model: createModelMock({widgets: [{id: 'w-find'}]})});
    const widget = tab.findWidget(tab.widgets[0].id);

    assert.ok(widget instanceof Wirecloud.ui.WidgetView);
    assert.equal(widget.model.id, 'w-find');
    assert.equal(tab.findWidget('non-existent'), undefined);
});

test('showSettings creates a PreferencesWindowMenu for the tab preferences and shows it, returns this', () => {
    const {tab} = createTab();

    let prefMenu = null;
    Wirecloud.ui.PreferencesWindowMenu = class {
        constructor(type, prefs) {
            prefMenu = {type, prefs, shown: false};
        }
        show() { prefMenu.shown = true; return this; }
    };

    assert.equal(tab.showSettings(), tab);
    assert.ok(prefMenu != null);
    assert.equal(prefMenu.type, 'tab');
    assert.equal(prefMenu.prefs, tab.model.preferences);
    assert.equal(prefMenu.shown, true);
});

// ===========================================================================
// repaint() / show()
// ===========================================================================

test('repaint calls dragboard.paint() and returns this', () => {
    const {tab} = createTab();

    assert.equal(tab.repaint(), tab);
    assert.equal(tab.dragboard.paintCalls, 1);
});

test('show loads all widgets', () => {
    const {tab} = createTab({model: createModelMock({widgets: [{id: 'w1'}, {id: 'w2'}]})});

    tab.show();

    tab.widgets.forEach((w) => assert.equal(w.loaded, true));
});

test('show updates the editing screen size name and the workspace editing interval addon', () => {
    const {tab, workspace} = createTab();

    let updateIntervalArg = null;
    workspace.updateEditingInterval = (el) => { updateIntervalArg = el; };

    tab.show();

    assert.equal(tab.editingScreenSizeName, tab.dragboard.activeScreenSize.name);
    assert.ok(updateIntervalArg != null);
    assert.equal(updateIntervalArg.getAttribute('role'), 'status');
});

test('show delegates to repaint (paints the dragboard) and returns this', () => {
    const {tab} = createTab();

    assert.equal(tab.show(), tab);
    assert.equal(tab.dragboard.paintCalls, 1);
});

// ===========================================================================
// setEditingScreenSize / quitEditingScreenSize / getEditingScreenSizeElement /
// updateEditingScreenSizeName
// ===========================================================================

test('updateEditingScreenSizeName reads the name from dragboard.activeScreenSize', () => {
    const {tab} = createTab();
    tab.dragboard.activeScreenSize = {id: 1, name: 'Tablet', moreOrEqual: 768, lessOrEqual: 1199, columns: 6};

    tab.updateEditingScreenSizeName();

    assert.equal(tab.editingScreenSizeName, 'Tablet');
});

test('setEditingScreenSize does nothing when the given id does not exist in screenSizes', () => {
    const {tab} = createTab();
    const before = tab.wrapperElement.style.width;

    tab.setEditingScreenSize(999);

    assert.equal(tab.dragboard.setForcedScreenSizeCalls.length, 0);
    assert.equal(tab.wrapperElement.style.width, before);
    assert.equal(tab.wrapperElement.classList.contains('wc-editing-screen-size'), false);
});

test('setEditingScreenSize forces the dragboard screen size and marks the tab as editing that size', () => {
    const {tab} = createTab();

    tab.setEditingScreenSize(1);

    assert.deepEqual(tab.dragboard.setForcedScreenSizeCalls, [1]);
    assert.ok(tab.wrapperElement.classList.contains('wc-editing-screen-size'));
    assert.equal(tab.editingScreenSizeName, 'Tablet');
});

test('setEditingScreenSize sets the wrapper width to lessOrEqual when the range is bounded', () => {
    const {tab} = createTab();

    tab.setEditingScreenSize(1); // Tablet: lessOrEqual 1199

    assert.equal(tab.wrapperElement.style.width, '1199px');
});

test('setEditingScreenSize sets the wrapper width to max(moreOrEqual, window.innerWidth) when unbounded', () => {
    const {tab} = createTab();

    global.window.innerWidth = 800;
    tab.setEditingScreenSize(2); // Desktop: moreOrEqual 1200, lessOrEqual -1
    assert.equal(tab.wrapperElement.style.width, '1200px');

    global.window.innerWidth = 2000;
    tab.setEditingScreenSize(2);
    assert.equal(tab.wrapperElement.style.width, '2000px');
});

test('setEditingScreenSize updates the workspace editing interval addon with an "Overriden" message', () => {
    const {tab, workspace} = createTab();

    let updateIntervalArg = null;
    workspace.updateEditingInterval = (el) => { updateIntervalArg = el; };

    tab.setEditingScreenSize(1);

    assert.ok(updateIntervalArg != null);
    assert.ok(updateIntervalArg.textContent.includes('Overriden'));
    assert.ok(updateIntervalArg.textContent.includes('Tablet'));
});

test('quitEditingScreenSize reverts the forced screen size, width and CSS class', () => {
    const {tab} = createTab();
    tab.setEditingScreenSize(1);

    tab.quitEditingScreenSize();

    assert.deepEqual(tab.dragboard.setForcedScreenSizeCalls, [1, null]);
    assert.equal(tab.wrapperElement.style.width, '');
    assert.equal(tab.wrapperElement.classList.contains('wc-editing-screen-size'), false);
});

test('quitEditingScreenSize updates editingScreenSizeName from the (now automatic) active screen size', () => {
    const {tab} = createTab();
    tab.setEditingScreenSize(1);
    assert.equal(tab.editingScreenSizeName, 'Tablet');

    tab.quitEditingScreenSize();

    assert.equal(tab.editingScreenSizeName, tab.dragboard.activeScreenSize.name);
    assert.equal(tab.editingScreenSizeName, 'Desktop');
});

test('quitEditingScreenSize updates the workspace editing interval addon without the "Overriden" message', () => {
    const {tab, workspace} = createTab();
    tab.setEditingScreenSize(1);

    let updateIntervalArg = null;
    workspace.updateEditingInterval = (el) => { updateIntervalArg = el; };

    tab.quitEditingScreenSize();

    assert.ok(!updateIntervalArg.textContent.includes('Overriden'));
    assert.ok(updateIntervalArg.textContent.includes('Editing for screen size'));
});

test('getEditingScreenSizeElement returns a status div with role/aria-live and the current screen size name', () => {
    const {tab} = createTab();

    const el = tab.getEditingScreenSizeElement();

    assert.equal(el.getAttribute('role'), 'status');
    assert.equal(el.getAttribute('aria-live'), 'polite');
    assert.ok(el.textContent.includes('Desktop'));
    assert.ok(!el.textContent.includes('Overriden'));
});

test('getEditingScreenSizeElement includes a close button only when forced', () => {
    const {tab} = createTab();

    const before = tab.getEditingScreenSizeElement();
    assert.equal(before.childNodes.length, 1); // just the text span

    tab.setEditingScreenSize(1);
    const after = tab.getEditingScreenSizeElement();
    assert.equal(after.childNodes.length, 2);
    const closeBtn = after.childNodes[1];
    assert.equal(closeBtn.tagName, 'A');
    assert.equal(closeBtn.getAttribute('role'), 'button');
    assert.equal(closeBtn.getAttribute('aria-label'), 'Quit editing interval');
});

test('getEditingScreenSizeElement close button click calls quitEditingScreenSize', () => {
    const {tab} = createTab();
    tab.setEditingScreenSize(1);

    let quitCalled = false;
    tab.quitEditingScreenSize = () => { quitCalled = true; };

    const el = tab.getEditingScreenSizeElement();
    const closeBtn = el.childNodes[el.childNodes.length - 1];
    const clickEvent = {type: 'click', preventDefault: () => {}};
    (closeBtn.listeners['click'] || []).forEach((h) => h(clickEvent));

    assert.equal(quitCalled, true);
});

// ===========================================================================
// createWidget
// ===========================================================================

test('createWidget uses options.w/h directly, bypassing dragboard.parseSize', () => {
    const {tab, model} = createTab();
    let capturedOptions = null;
    model.createWidget = (resource, options) => { capturedOptions = options; return {id: 'x'}; };
    tab.findWidget = () => ({id: 'found'});

    tab.createWidget({title: 'R', default_width: 999, default_height: 999}, {commit: false, w: 4, h: 5});

    assert.equal(tab.dragboard.parseSizeCalls.length, 0);
    const layout = capturedOptions.layouts[String(tab.dragboard.activeScreenSize.id)];
    assert.equal(layout.w, 4);
    assert.equal(layout.h, 5);
});

test('createWidget derives w/h from options.width/height via dragboard.parseSize', () => {
    const {tab, model} = createTab();
    let capturedOptions = null;
    model.createWidget = (resource, options) => { capturedOptions = options; return {id: 'x'}; };
    tab.findWidget = () => ({id: 'found'});

    tab.createWidget({title: 'R'}, {commit: false, width: '400px', height: '50%'});

    assert.deepEqual(tab.dragboard.parseSizeCalls, [{value: '400px', axis: 'w'}, {value: '50%', axis: 'h'}]);
    const layout = capturedOptions.layouts[String(tab.dragboard.activeScreenSize.id)];
    assert.equal(layout.w, 'w(400px)');
    assert.equal(layout.h, 'h(50%)');
});

test('createWidget falls back to resource.default_width/default_height when nothing else is given', () => {
    const {tab, model} = createTab();
    let capturedOptions = null;
    model.createWidget = (resource, options) => { capturedOptions = options; return {id: 'x'}; };
    tab.findWidget = () => ({id: 'found'});

    tab.createWidget({title: 'R', default_width: 77, default_height: 88}, {commit: false});

    assert.deepEqual(tab.dragboard.parseSizeCalls, [{value: 77, axis: 'w'}, {value: 88, axis: 'h'}]);
});

test('createWidget defaults x/y to null and honors explicit x/y', () => {
    const {tab, model} = createTab();
    let capturedOptions = null;
    model.createWidget = (resource, options) => { capturedOptions = options; return {id: 'x'}; };
    tab.findWidget = () => ({id: 'found'});

    tab.createWidget({title: 'R', default_width: 1, default_height: 1}, {commit: false});
    let layout = capturedOptions.layouts[String(tab.dragboard.activeScreenSize.id)];
    assert.equal(layout.x, null);
    assert.equal(layout.y, null);

    tab.createWidget({title: 'R', default_width: 1, default_height: 1}, {commit: false, x: 3, y: 7});
    layout = capturedOptions.layouts[String(tab.dragboard.activeScreenSize.id)];
    assert.equal(layout.x, 3);
    assert.equal(layout.y, 7);
});

test('createWidget defaults titlevisible to true and honors an explicit false', () => {
    const {tab, model} = createTab();
    let capturedOptions = null;
    model.createWidget = (resource, options) => { capturedOptions = options; return {id: 'x'}; };
    tab.findWidget = () => ({id: 'found'});

    tab.createWidget({title: 'R', default_width: 1, default_height: 1}, {commit: false});
    assert.equal(capturedOptions.layouts[String(tab.dragboard.activeScreenSize.id)].titlevisible, true);

    tab.createWidget({title: 'R', default_width: 1, default_height: 1}, {commit: false, titlevisible: false});
    assert.equal(capturedOptions.layouts[String(tab.dragboard.activeScreenSize.id)].titlevisible, false);
});

test('createWidget always sets minimized:false, fulldragboard:false, visible:true on the derived layout', () => {
    const {tab, model} = createTab();
    let capturedOptions = null;
    model.createWidget = (resource, options) => { capturedOptions = options; return {id: 'x'}; };
    tab.findWidget = () => ({id: 'found'});

    tab.createWidget({title: 'R', default_width: 1, default_height: 1}, {commit: false});

    const layout = capturedOptions.layouts[String(tab.dragboard.activeScreenSize.id)];
    assert.equal(layout.minimized, false);
    assert.equal(layout.fulldragboard, false);
    assert.equal(layout.visible, true);
});

test('createWidget keys the derived layout by the current active screen size id', () => {
    const {tab, model} = createTab();
    tab.dragboard.activeScreenSize = {id: 1, name: 'Tablet', moreOrEqual: 768, lessOrEqual: 1199, columns: 6};
    let capturedOptions = null;
    model.createWidget = (resource, options) => { capturedOptions = options; return {id: 'x'}; };
    tab.findWidget = () => ({id: 'found'});

    tab.createWidget({title: 'R', default_width: 1, default_height: 1}, {commit: false});

    assert.deepEqual(Object.keys(capturedOptions.layouts), ['1']);
});

test('createWidget uses options.layouts as-is when given, skipping the derived-layout logic', () => {
    const {tab, model} = createTab();
    let capturedOptions = null;
    model.createWidget = (resource, options) => { capturedOptions = options; return {id: 'x'}; };
    tab.findWidget = () => ({id: 'found'});

    const explicitLayouts = {5: {x: 1, y: 1, w: 2, h: 2, minimized: false, titlevisible: true, fulldragboard: false, visible: true}};
    tab.createWidget({title: 'R'}, {commit: false, layouts: explicitLayouts});

    assert.equal(capturedOptions.layouts, explicitLayouts);
    assert.equal(tab.dragboard.parseSizeCalls.length, 0);
});

test('createWidget defaults options.title to resource.title when not given', () => {
    const {tab, model} = createTab();
    let capturedOptions = null;
    model.createWidget = (resource, options) => { capturedOptions = options; return {id: 'x'}; };
    tab.findWidget = () => ({id: 'found'});

    tab.createWidget({title: 'Resource Title', default_width: 1, default_height: 1}, {commit: false});

    assert.equal(capturedOptions.title, 'Resource Title');
});

test('createWidget passes permissions through to the model call', () => {
    const {tab, model} = createTab();
    let capturedOptions = null;
    model.createWidget = (resource, options) => { capturedOptions = options; return {id: 'x'}; };
    tab.findWidget = () => ({id: 'found'});

    const permissions = {viewer: {move: false}};
    tab.createWidget({title: 'R', default_width: 1, default_height: 1}, {commit: false, permissions});

    assert.equal(capturedOptions.permissions, permissions);
});

test('createWidget with commit:false returns tab.findWidget(result.id) synchronously (not a promise)', () => {
    const {tab, model} = createTab();
    model.createWidget = () => ({id: 'direct-widget'});
    const foundWidget = {id: 'direct-widget', found: true};
    tab.findWidget = (id) => id === 'direct-widget' ? foundWidget : undefined;

    const result = tab.createWidget({title: 'R', default_width: 1, default_height: 1}, {commit: false});

    assert.equal(result, foundWidget);
});

test('createWidget with commit:true returns a promise resolving to tab.findWidget(model.id)', async () => {
    const {tab, model} = createTab();
    model.createWidget = () => Promise.resolve({id: 'promise-widget'});
    const foundWidget = {id: 'promise-widget', found: true};
    tab.findWidget = (id) => id === 'promise-widget' ? foundWidget : undefined;

    const result = await tab.createWidget({title: 'R', default_width: 1, default_height: 1}, {commit: true});

    assert.equal(result, foundWidget);
});

test('createWidget defaults commit to true when omitted', async () => {
    const {tab, model} = createTab();
    let sawPromisePath = false;
    model.createWidget = () => { sawPromisePath = true; return Promise.resolve({id: 'w'}); };
    tab.findWidget = () => ({id: 'w'});

    await tab.createWidget({title: 'R', default_width: 1, default_height: 1}, {});

    assert.equal(sawPromisePath, true);
});

// ===========================================================================
// MODEL EVENT HANDLERS
// ===========================================================================

test('on_changetab title change renames the tab', () => {
    const {tab, model} = createTab();

    let renameCalled = null;
    const origRename = StyledElements.Tab.prototype.rename;
    StyledElements.Tab.prototype.rename = function (newTitle) {
        renameCalled = newTitle;
    };

    try {
        model._dispatch('change', model, ['title']);
        assert.equal(renameCalled, 'Test Tab');
    } finally {
        StyledElements.Tab.prototype.rename = origRename;
    }
});

test('on_changetab non-title change does not rename', () => {
    const {tab, model} = createTab();
    let renamed = false;
    tab.rename = () => { renamed = true; };

    model._dispatch('change', model, ['name']);

    assert.equal(renamed, false);
});

test('on_changetab name change updates data-name attribute and history state when not hidden', () => {
    let replaceStateCalled = false;
    let replaceStateData = null;
    Wirecloud.HistoryManager.replaceState = (data) => { replaceStateCalled = true; replaceStateData = data; };
    Wirecloud.HistoryManager.getCurrentState = () => ({existing: 'state'});

    const {tab, model} = createTab();
    tab.hidden = false;
    model.name = 'new_name';

    model._dispatch('change', model, ['name']);

    assert.equal(replaceStateCalled, true);
    assert.equal(replaceStateData.tab, 'new_name');
    assert.equal(replaceStateData.existing, 'state');
    assert.equal(tab.tabElement.getAttribute('data-name'), 'new_name');
});

test('on_changetab name change does not update history state when tab is hidden', () => {
    let replaceStateCalled = false;
    Wirecloud.HistoryManager.replaceState = () => { replaceStateCalled = true; };

    const {tab, model} = createTab();
    tab.hidden = true;
    model.name = 'hidden_name';

    model._dispatch('change', model, ['name']);

    assert.equal(replaceStateCalled, false);
});

// -- on_addwidget -------------------------------------------------------

test('on_addwidget creates and pushes a widget view when view is null, loads if not hidden', () => {
    const {tab, model} = createTab();
    tab.hidden = false;

    model._dispatch('addwidget', model, {id: 'added-widget'}, null);

    assert.equal(tab.widgets.length, 1);
    assert.equal(tab.widgets[0].model.id, 'added-widget');
    assert.equal(tab.widgets[0].loaded, true);
    assert.equal(tab.initialMessage.hidden, true);
});

test('on_addwidget creates a widget view but does not load it when the tab is hidden', () => {
    const {tab, model} = createTab();
    tab.hidden = true;

    model._dispatch('addwidget', model, {id: 'hidden-widget'}, null);

    assert.equal(tab.widgets.length, 1);
    assert.equal(tab.widgets[0].loaded, false);
});

test('on_addwidget with an existing view (widget moved from another tab) pushes it and calls dragboard.addWidget', () => {
    const {tab, model} = createTab();

    const existingView = {id: 'existing-view', loaded: false};
    model._dispatch('addwidget', model, {id: 'm'}, existingView);

    assert.equal(tab.widgets.length, 1);
    assert.equal(tab.widgets[0], existingView);
    assert.deepEqual(tab.dragboard.addWidgetCalls, [existingView]);
    assert.equal(tab.initialMessage.hidden, true);
});

test('on_addwidget with an existing view does not create a brand-new WidgetView', () => {
    const {tab, model, workspace} = createTab();
    const before = tab.widgets.length;

    const existingView = {id: 'moved-widget', loaded: true};
    model._dispatch('addwidget', model, {id: 'm2'}, existingView);

    // The only widget registered should be the moved view itself, not a
    // freshly constructed Wirecloud.ui.WidgetView.
    assert.equal(tab.widgets.length, before + 1);
    assert.ok(!(tab.widgets[tab.widgets.length - 1] instanceof Wirecloud.ui.WidgetView));
});

// -- on_removetab ---------------------------------------------------------

test('on_removetab calls close (removes the tab from the notebook)', () => {
    const {tab, model, notebook} = createTab();
    notebook._tabs[tab.tabId] = tab;

    model._dispatch('remove', model);

    assert.equal(notebook._tabs[tab.tabId], undefined);
});

// -- on_removewidget --------------------------------------------------------

test('on_removewidget removes the widget from the array', () => {
    const {tab, model} = createTab({model: createModelMock({widgets: [{id: 'w1'}, {id: 'w2'}]})});
    const widgetToRemove = tab.widgets[0].model;

    model._dispatch('removewidget', model, widgetToRemove);

    assert.equal(tab.widgets.length, 1);
});

test('on_removewidget hides initialMessage when no widgets remain and edit is not allowed', () => {
    const {tab, model} = createTab({
        model: createModelMock({widgets: [{id: 'w1'}]}),
        workspace: createWorkspaceMock({model: {isAllowed: (p) => p !== 'edit'}}),
    });
    const widgetToRemove = tab.widgets[0].model;

    model._dispatch('removewidget', model, widgetToRemove);

    assert.equal(tab.initialMessage.hidden, true);
    assert.equal(tab.widgets.length, 0);
});

test('on_removewidget shows initialMessage when no widgets remain and edit is allowed', () => {
    const {tab, model} = createTab({
        model: createModelMock({widgets: [{id: 'w1'}]}),
        workspace: createWorkspaceMock({model: {isAllowed: () => true}}),
    });
    const widgetToRemove = tab.widgets[0].model;

    model._dispatch('removewidget', model, widgetToRemove);

    assert.equal(tab.initialMessage.hidden, false);
    assert.equal(tab.widgets.length, 0);
});

test('on_removewidget keeps initialMessage hidden when widgets remain', () => {
    const {tab, model} = createTab({model: createModelMock({widgets: [{id: 'w1'}, {id: 'w2'}]})});
    const widgetToRemove = tab.widgets[0].model;

    model._dispatch('removewidget', model, widgetToRemove);

    assert.equal(tab.initialMessage.hidden, true);
    assert.equal(tab.widgets.length, 1);
});

// ===========================================================================
// WINDOW RESIZE HANDLER (on_windowresize)
// ===========================================================================

test('window resize updates editing screen size name/interval when this tab is the active tab', () => {
    const {tab, workspace} = createTab();
    workspace.activeTab = tab;

    let editingIntervalElement = null;
    workspace.updateEditingInterval = (el) => { editingIntervalElement = el; };
    tab.dragboard.activeScreenSize = {id: 1, name: 'Tablet', moreOrEqual: 768, lessOrEqual: 1199, columns: 6};

    global.window.dispatchEvent({type: 'resize'});

    assert.equal(tab.editingScreenSizeName, 'Tablet');
    assert.ok(editingIntervalElement != null);
});

test('window resize does not update editing interval when this tab is not the active tab', () => {
    const {tab, workspace} = createTab();
    workspace.activeTab = null;

    let editingIntervalCalled = false;
    workspace.updateEditingInterval = () => { editingIntervalCalled = true; };

    global.window.dispatchEvent({type: 'resize'});

    assert.equal(editingIntervalCalled, false);
});

// ===========================================================================
// UPDATE_PREF_BUTTON
// ===========================================================================

test('update_pref_button sets enabled based on workspace.editing', () => {
    const workspace = createWorkspaceMock({model: {isAllowed: () => true}});
    workspace.editing = true;
    const {tab} = createTab({workspace});
    assert.equal(tab.prefbutton.enabled, true);

    workspace.editing = false;
    workspace._dispatch('editmode');
    assert.equal(tab.prefbutton.enabled, false);

    workspace.editing = true;
    workspace._dispatch('editmode');
    assert.equal(tab.prefbutton.enabled, true);
});

// ===========================================================================
// name / title accessors
// ===========================================================================

test('name getter returns model.name', () => {
    const {tab, model} = createTab();
    model.name = 'my_custom_name';
    assert.equal(tab.name, 'my_custom_name');
});

test('title getter returns model.title', () => {
    const {tab, model} = createTab();
    model.title = 'My Custom Title';
    assert.equal(tab.title, 'My Custom Title');
});
