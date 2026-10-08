const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScript,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');

// ===========================================================================
// SETUP
// ===========================================================================

const setup = () => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();

    global.window.innerWidth = 1200;

    if (global.Wirecloud == null) {
        global.Wirecloud = {};
    }
    Wirecloud.Utils = StyledElements.Utils;
    Wirecloud.ui = Wirecloud.ui || {};

    // -- Wirecloud.addEventListener / dispatchEvent ---------------------------
    const wirecloudEvents = {};
    Wirecloud.addEventListener = (type, handler) => {
        if (!wirecloudEvents[type]) wirecloudEvents[type] = [];
        wirecloudEvents[type].push(handler);
    };
    Wirecloud.dispatchEvent = (type, ...args) => {
        (wirecloudEvents[type] || []).forEach((h) => h(...args));
    };

    // -- StyledElements mocks -------------------------------------------------

    // Use a simple self-contained mock hierarchy with events support
    class SEMockSEEvent {
        constructor(owner) {
            this._handlers = [];
        }
        addEventListener(handler) { this._handlers.push(handler); }
        removeEventListener(handler) {
            this._handlers = this._handlers.filter((h) => h !== handler);
        }
        dispatch(...args) {
            this._handlers.forEach((h) => h(...args));
        }
    }

    class SEMockBase {
        constructor(events) {
            this.events = {};
            this._listeners = {};
            this._hidden = false;
            this.wrapperElement = document.createElement('div');

            Object.defineProperties(this, {
                hidden: {
                    get: () => this._hidden,
                    set: (v) => { this._hidden = v; this._onhidden(v); },
                },
                enabled: {
                    get: () => !this.wrapperElement.classList.contains('disabled'),
                    set: (v) => {
                        this.wrapperElement.classList.toggle('disabled', !v);
                    },
                },
            });

            (Array.isArray(events) ? events : []).concat(['hide', 'show']).forEach((name) => {
                if (!this.events[name]) {
                    this.events[name] = new SEMockSEEvent(this);
                }
            });
        }
        addEventListener(type, handler) {
            if (!this._listeners[type]) this._listeners[type] = [];
            this._listeners[type].push(handler);
        }
        removeEventListener(type, handler) {
            if (this._listeners[type]) {
                this._listeners[type] = this._listeners[type].filter((h) => h !== handler);
            }
        }
        _dispatch(type, ...args) {
            (this._listeners[type] || []).forEach((h) => h(...args));
        }
        dispatchEvent(type, ...args) {
            // Also fire through the events system (like the real ObjectWithEvents)
            if (this.events[type]) {
                this.events[type].dispatch(...args);
            }
            return this;
        }
        hide() { this._hidden = true; this.wrapperElement.classList.add('hidden'); return this.dispatchEvent('hide'); }
        show() { this._hidden = false; this.wrapperElement.classList.remove('hidden'); return this.dispatchEvent('show'); }
        appendChild(child) {
            if (child && child.wrapperElement) {
                this.wrapperElement.appendChild(child.wrapperElement);
            } else if (child instanceof Element || (child && child.nodeType)) {
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
        appendTo(parent) {
            if (parent && parent.appendChild) {
                parent.appendChild(this.wrapperElement);
            }
            return this;
        }
        destroy() { return this; }
        clear() {
            while (this.wrapperElement.childNodes.length > 0) {
                this.wrapperElement.removeChild(this.wrapperElement.childNodes[0]);
            }
            return this;
        }
        repaint() { return this; }
        hasClassName(name) { return this.wrapperElement.classList.contains(name); }
        addClassName(name) { this.wrapperElement.classList.add(name); return this; }
        removeClassName(name) { this.wrapperElement.classList.remove(name); return this; }
        toggleClassName(name, force) {
            if (force === undefined) {
                force = !this.hasClassName(name);
            }
            if (force) {
                this.addClassName(name);
            } else {
                this.removeClassName(name);
            }
            return this;
        }
        _onhidden(hidden) {}
        _onenabled(enabled) {}
        disable() { this.enabled = false; return this; }
        enable() { this.enabled = true; return this; }
        get() { return this.wrapperElement; }
        remove() { this.wrapperElement.remove(); return this; }
    }

    class SEMockContainer extends SEMockBase {
        constructor(options, events) {
            super(events);
            if (options && options.class) {
                this.wrapperElement.className = options.class;
            }
        }
        removeChild(child) {
            const el = child && child.wrapperElement ? child.wrapperElement : child;
            if (el && this.wrapperElement.childNodes.includes(el)) {
                this.wrapperElement.removeChild(el);
            }
            return this;
        }
    }

    class SEMockAlternative extends SEMockContainer {
        constructor(id, options) {
            super(options, ['hide', 'show']);
            this.addClassName('hidden');
            Object.defineProperty(this, 'altId', { value: id });
        }
        setVisible(visible) { return visible ? this.show() : this.hide(); }
        isVisible() { return !this.hidden; }
    }
    StyledElements.Alternative = SEMockAlternative;
    StyledElements.Container = SEMockContainer;

    // Button
    class SEMockButton extends SEMockBase {
        constructor(opts = {}) {
            super();
            this._disabled = false;
            this.enabled = true;
            this.active = false;
            this.opts = opts;
            this.wrapperElement = document.createElement('button');
            if (opts.class) this.wrapperElement.className = opts.class;
            if (opts.iconClass) {
                const icon = document.createElement('i');
                icon.className = opts.iconClass;
                this.wrapperElement.appendChild(icon);
            }
            if (opts.title) this.wrapperElement.setAttribute('title', opts.title);
        }
        disable() { this._disabled = true; this.enabled = false; return this; }
        enable() { this._disabled = false; this.enabled = true; return this; }
        addIconClass() { return this; }
        addIconClassName() { return this; }
        removeIconClassName() { return this; }
        setTitle(title) { this.wrapperElement.setAttribute('title', title); return this; }
        removeIconClass() { return this; }
    }

    class SEMockToggleButton extends SEMockButton {
        constructor(opts = {}) {
            super(opts);
            this.active = false;
        }
    }
    StyledElements.ToggleButton = SEMockToggleButton;
    StyledElements.Button = SEMockButton;

    // PopupMenu
    class SEMockPopupMenu extends SEMockBase {
        constructor() {
            super();
            this._items = [];
            this.wrapperElement = document.createElement('ul');
        }
        append(item) { this._items.push(item); return this; }
        appendSeparator() { this._items.push({ separator: true }); return this; }
    }
    StyledElements.PopupMenu = SEMockPopupMenu;

    // OffCanvasLayout
    class SEMockOffCanvasLayout extends SEMockBase {
        constructor() {
            super(['slideIn', 'slideOut']);
            this.wrapperElement = document.createElement('div');
            this.wrapperElement.className = 'se-offcanvas left-sideway';
            this.sidebar = new SEMockContainer({ class: 'se-offcanvas-sidebar' });
            this.content = new SEMockContainer({ class: 'se-offcanvas-content' });
            this.sidebar.appendTo(this.wrapperElement);
            this.content.appendTo(this.wrapperElement);
            this.index = -1;
        }
        appendChild(element) {
            this.sidebar.appendChild(element);
            if (this.index < 0) this.index = 0;
            return this;
        }
        slideIn(index) {
            if (index != null) this.index = index;
            this.toggleClassName('slipped', true);
            return this.dispatchEvent('slideIn');
        }
        slideOut(index) {
            if (index != null) this.index = index;
            this.toggleClassName('slipped', false);
            return this.dispatchEvent('slideOut');
        }
        get slipped() { return this.hasClassName('slipped'); }
    }
    StyledElements.OffCanvasLayout = SEMockOffCanvasLayout;

    // Notebook
    class SEMockNotebook extends SEMockBase {
        constructor(opts = {}) {
            super(['changed']);
            this.tabs = [];
            this._nextTabId = 0;
            this.tabWrapper = new SEMockContainer({ class: 'se-notebook-tab-wrapper' });
            this._visibleTab = null;
            this._fullscreen = false;
        }
        get visibleTab() { return this._visibleTab; }
        get fullscreen() { return this._fullscreen; }
        set fullscreen(v) { this._fullscreen = v; }
        createTab(opts) {
            let tab;
            if (opts && opts.tab_constructor) {
                const id = 'tab-' + (++this._nextTabId);
                const model = opts.model || { id: 'model-' + this._nextTabId, name: 'tab' + this._nextTabId, title: 'Tab ' + this._nextTabId };
                tab = new opts.tab_constructor(model.id, this, {
                    model,
                    workspace: opts.workspace,
                    name: model.name,
                });
            } else {
                tab = {
                    id: 'loading-tab-' + (++this._nextTabId),
                    wrapperElement: document.createElement('div'),
                    disable: () => {},
                    addClassName: () => {},
                };
                this.tabs.push(tab);
                return tab;
            }
            this.tabs.push(tab);
            this._visibleTab = tab;
            return tab;
        }
        removeTab(tab) {
            const idx = this.tabs.indexOf(tab);
            if (idx !== -1) this.tabs.splice(idx, 1);
            return this;
        }
        goToTab(tab) {
            this._visibleTab = tab;
            return this;
        }
        appendTo(parent) {
            if (parent && parent.appendChild) parent.appendChild(this.wrapperElement);
            return this;
        }
        addToEastSection(element) { return this; }
        requestFullscreen() { this._fullscreen = true; return this; }
        exitFullscreen() { this._fullscreen = false; return this; }
    }
    StyledElements.Notebook = SEMockNotebook;

    // Addon
    class SEMockAddon extends SEMockBase {}
    StyledElements.Addon = SEMockAddon;

    // Event (for new StyledElements.Event(this))
    StyledElements.Event = SEMockSEEvent;

    // ObjectWithEvents - keep compatible
    StyledElements.ObjectWithEvents = class ObjectWithEvents {
        constructor(events) {
            this.events = {};
            (Array.isArray(events) ? events : []).forEach((name) => {
                this.events[name] = new SEMockSEEvent(this);
            });
        }
        addEventListener(name, handler) {
            if (this.events[name]) this.events[name].addEventListener(handler);
        }
        removeEventListener(name, handler) {
            if (this.events[name]) this.events[name].removeEventListener(handler);
        }
        dispatchEvent(name, ...args) {
            if (this.events[name]) this.events[name].dispatch(...args);
            return this;
        }
    };

    // -- Wirecloud globals ---------------------------------------------------

    Wirecloud.HistoryManager = {
        _state: { tab: 'default' },
        getCurrentState() { return Object.assign({}, this._state); },
        replaceState(state) { Object.assign(this._state, state); },
        pushState(state) { Object.assign(this._state, state); },
    };

    Wirecloud.UserInterfaceManager = {
        _tasks: [],
        monitorTask(task) { this._tasks.push(task); return task; },
        changeCurrentView(view) { this._lastView = view; },
        _lastView: null,
        header: {
            refresh: () => {},
            currentView: null,
        },
    };

    Wirecloud.activeWorkspace = { owner: 'wirecloud', name: 'home', id: 'home-id' };

    Wirecloud.changeActiveWorkspace = (workspace, opts) => {
        if (workspace.owner === 'wirecloud' && workspace.name === 'home') {
            Wirecloud.activeWorkspace = { owner: 'wirecloud', name: 'home', id: 'home-id' };
        } else {
            Wirecloud.activeWorkspace = workspace;
        }
        return Promise.resolve(workspace);
    };

    Wirecloud.mergeWorkspace = () => Promise.resolve({ id: 'merged-ws', owner: 'test', name: 'merged' });

    Wirecloud.contextManager = {
        _data: { mode: { value: 'normal' }, username: { value: 'testuser' } },
        get(key) { return (this._data[key] && this._data[key].value) || this._data[key] || null; },
    };

    Wirecloud.constants = { LOGGING: { ERROR_MSG: 1 } };

    Wirecloud.URLs = {
        WORKSPACE_VIEW: { evaluate: (opts) => '/workspace/' + opts.owner + '/' + opts.name },
    };

    Wirecloud.Utils.isFullscreenSupported = () => false;
    Wirecloud.Utils.onFullscreenChange = () => {};
    Wirecloud.workspacesByUserAndName = {};

    // -- Wirecloud.ui mocks ---------------------------------------------------

    Wirecloud.ui.WorkspaceListItems = class {
        constructor(handler) { this._handler = handler; }
    };

    Wirecloud.ui.WorkspaceViewMenuItems = class {
        constructor(workspace) { this.workspace = workspace; }
    };

    Wirecloud.ui.PreferencesWindowMenu = class {
        constructor(type, prefs) { this.type = type; this.prefs = prefs; this.shown = false; }
        show() { this.shown = true; return this; }
    };

    Wirecloud.ui.MessageWindowMenu = class {
        constructor(error, level) { this.error = error; this.level = level; this.shown = false; }
        show() { this.shown = true; return this; }
    };

    Wirecloud.ui.MissingDependenciesWindowMenu = class {
        constructor(_, error) { this.error = error; this.shown = false; }
        show() { this.shown = true; return this; }
    };

    Wirecloud.ui.ComponentSidebar = class {
        constructor() {
            this._listeners = {};
            this.searchComponents = { refresh: () => {} };
            this.wrapperElement = document.createElement('div');
        }
        addEventListener(type, handler) {
            if (!this._listeners[type]) this._listeners[type] = [];
            this._listeners[type].push(handler);
        }
        _dispatch(type, ...args) {
            (this._listeners[type] || []).forEach((h) => h(...args));
        }
    };

    Wirecloud.ui.WorkspaceTabView = class {
        constructor(id, notebook, options) {
            this.id = id;
            this.notebook = notebook;
            this.model = options.model;
            this.workspace = options.workspace;
            this.name = options.model ? options.model.name : (options.name || id);
            this.dragboard = {
                paint: () => {},
            };
            this.widgets = [];
            this.wrapperElement = document.createElement('div');
            this.wrapperElement.className = 'wc-workspace-tab-content';
            this._hidden = false;
            this.hidden = false;
        }
        hide() { this._hidden = true; this.hidden = true; return this; }
        show() { this._hidden = false; this.hidden = false; return this; }
        highlight() { return this; }
        quitEditingScreenSize() {}
        getEditingScreenSizeElement() {
            const el = document.createElement('span');
            el.textContent = 'desktop';
            el.setAttribute('role', 'status');
            el.setAttribute('aria-live', 'polite');
            return el;
        }
        updateEditingScreenSizeName() {}
        findWidget() { return null; }
        createWidget() { return Promise.resolve({ id: 'new-widget' }); }
    };

    // -- Load the source file -------------------------------------------------
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceView.js');

    return {
        StyledElements,
        Wirecloud,
        wirecloudEvents,
    };
};

// ===========================================================================
// Helper: create a model mock
// ===========================================================================

const createModelMock = (overrides = {}) => {
    const listeners = {};
    return {
        id: overrides.id || 'ws-1',
        name: overrides.name || 'test-ws',
        title: overrides.title || 'Test Workspace',
        owner: overrides.owner || 'test-owner',
        operators: overrides.operators || [],
        tabs: overrides.tabs || [],
        preferences: overrides.preferences || { get: () => ({}), addEventListener: () => {} },
        isAllowed: overrides.isAllowed || (() => true),
        contextManager: overrides.contextManager || { modify: () => {} },
        addEventListener(type, handler) {
            if (!listeners[type]) listeners[type] = [];
            listeners[type].push(handler);
        },
        removeEventListener(type, handler) {
            if (!listeners[type]) return;
            listeners[type] = listeners[type].filter((h) => h !== handler);
        },
        _dispatch(type, ...args) {
            (listeners[type] || []).forEach((h) => h(...args));
        },
        createTab: overrides.createTab || (() => Promise.resolve({ id: 'new-tab', name: 'newtab', widgets: [], initial: false })),
        ...overrides,
    };
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

test('constructor creates an instance of WorkspaceView', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.ok(view instanceof Wirecloud.ui.WorkspaceView);
    assert.ok(view instanceof StyledElements.Alternative);
});

test('constructor sets altId', () => {
    const view = new Wirecloud.ui.WorkspaceView(5, {});
    assert.equal(view.altId, 5);
});

test('constructor sets view_name on prototype', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.equal(view.view_name, 'workspace');
});

test('constructor adds wc-workspace class to wrapperElement', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.ok(view.wrapperElement.classList.contains('wc-workspace'));
});

test('constructor creates wsMenu as PopupMenu', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.ok(view.wsMenu instanceof StyledElements.PopupMenu);
});

test('constructor creates editButton as ToggleButton', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.ok(view.editButton instanceof StyledElements.ToggleButton);
});

test('constructor creates walletButton', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.ok(view.walletButton instanceof StyledElements.ToggleButton);
});

test('constructor creates wiringButton as Button', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.ok(view.wiringButton instanceof StyledElements.Button);
});

test('constructor creates myresourcesButton as Button', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.ok(view.myresourcesButton instanceof StyledElements.Button);
});

test('constructor creates marketButton as Button', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.ok(view.marketButton instanceof StyledElements.Button);
});

test('constructor creates layout as OffCanvasLayout and appends it', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.ok(view.layout instanceof StyledElements.OffCanvasLayout);
});

test('constructor creates events.editmode as Event', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.ok(view.events.editmode instanceof StyledElements.Event);
});

test('constructor binds event handlers', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.equal(typeof view.on_workspace_change_bound, 'function');
    assert.equal(typeof view.on_workspace_remove_bound, 'function');
    assert.equal(typeof view.on_workspace_unload_bound, 'function');
    assert.equal(typeof view.on_workspace_createoperator_bound, 'function');
    assert.equal(typeof view.on_workspace_removeoperator_bound, 'function');
});

test('editing getter returns editButton.active', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.equal(view.editing, false);
    view.editButton.active = true;
    assert.equal(view.editing, true);
});

test('wirecloud loaded event handler creates ComponentSidebar', () => {
    const { Wirecloud } = setup();
    const view = new Wirecloud.ui.WorkspaceView(0, {});

    assert.equal(view.showcase, undefined);

    // Trigger loaded
    Wirecloud.dispatchEvent('loaded');
    assert.ok(view.showcase instanceof Wirecloud.ui.ComponentSidebar);
});

// ===========================================================================
// PROPERTY GETTERS (after loadWorkspace)
// ===========================================================================

test('activeTab getter returns notebook.visibleTab', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    assert.equal(view.activeTab, view.notebook.visibleTab);
});

test('tabs getter returns notebook.tabs', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    assert.ok(Array.isArray(view.tabs));
    assert.equal(view.tabs.length, 1);
});

test('name getter returns model.name', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        name: 'my-workspace',
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});
    assert.equal(view.name, 'my-workspace');
});

test('title getter returns model.title', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        title: 'My Workspace Title',
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});
    assert.equal(view.title, 'My Workspace Title');
});

test('widgets getter collects widgets from all tabs', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        tabs: [
            { id: 'tab-1', name: 'tab1', title: 'Tab1', initial: true, widgets: [] },
            { id: 'tab-2', name: 'tab2', title: 'Tab2', initial: false, widgets: [] },
        ],
    });
    view.loadWorkspace(model, {});
    view.notebook.tabs[0].widgets = [{ id: 'w1' }, { id: 'w2' }];
    view.notebook.tabs[1].widgets = [{ id: 'w3' }];

    const widgets = view.widgets;
    assert.equal(widgets.length, 3);
});

// ===========================================================================
// SHOW / HIDE TAB BAR via edit button click handler
// ===========================================================================

test('showHideTabBar enables wallet/wiring buttons when editing and allowed', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        isAllowed: () => true,
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});
    // After loadWorkspace, showHideTabBar(false) was called, so buttons are disabled
    // Now simulate clicking edit button to enter edit mode
    view.editButton.active = true;
    view.editButton._dispatch('click', view.editButton);

    assert.equal(view.walletButton.enabled, true);
    assert.equal(view.wiringButton.enabled, true);
});

test('showHideTabBar hides addTabButton when not editing', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        isAllowed: () => true,
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});
    // After loadWorkspace showHideTabBar(false) was called
    assert.ok(view.addTabButton);
    assert.ok(view.addTabButton.wrapperElement.classList.contains('hidden'));
});

test('edit button click with active=false slides out and quits editing intervals', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        tabs: [
            { id: 'tab-1', name: 'tab1', title: 'Tab1', initial: true, widgets: [] },
            { id: 'tab-2', name: 'tab2', title: 'Tab2', initial: false, widgets: [] },
        ],
    });
    view.loadWorkspace(model, {});

    let slideOutCalled = false;
    view.layout.slideOut = () => { slideOutCalled = true; return view.layout; };

    let quitCalls = 0;
    view.notebook.tabs.forEach((tab) => { tab.quitEditingScreenSize = () => { quitCalls++; }; });

    view.editButton.active = false;
    view.editButton._dispatch('click', view.editButton);

    assert.equal(slideOutCalled, true);
    assert.equal(quitCalls, 2);
});

test('edit button active event dispatches editmode event', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});

    let editmodeVal = null;
    view.events.editmode.addEventListener((val) => { editmodeVal = val; });

    view.editButton.active = true;
    view.editButton._dispatch('active', view.editButton);

    assert.equal(editmodeVal, true);
});

test('edit button active event modifies model contextManager when model is not null', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    let modifyArgs = null;
    const model = createModelMock({
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
        contextManager: { modify: (data) => { modifyArgs = data; } },
    });
    view.loadWorkspace(model, {});

    view.editButton.active = true;
    view.editButton._dispatch('active', view.editButton);

    assert.deepEqual(modifyArgs, { editing: true });
});

test('edit button active event skips contextManager.modify when model is null', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    // model is null and editing is false - active event should not throw
    view.editButton.active = false;
    view.editButton._dispatch('active', view.editButton);
    assert.ok(true);
});

test('wiringButton click changes current view to wiring', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    view.wiringButton._dispatch('click');
    assert.equal(Wirecloud.UserInterfaceManager._lastView, 'wiring');
});

test('myresourcesButton click changes current view to myresources', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    view.myresourcesButton._dispatch('click');
    assert.equal(Wirecloud.UserInterfaceManager._lastView, 'myresources');
});

test('marketButton click changes current view to marketplace', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    view.marketButton._dispatch('click');
    assert.equal(Wirecloud.UserInterfaceManager._lastView, 'marketplace');
});

// ===========================================================================
// on_workspace_createoperator
// ===========================================================================

test('on_workspace_createoperator appends operator wrapperElement when present', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});

    const opWrapper = document.createElement('div');
    model._dispatch('createoperator', model, { wrapperElement: opWrapper });

    assert.ok(view.layout.content.wrapperElement.childNodes.includes(opWrapper));
});

test('on_workspace_createoperator does nothing when operator has no wrapperElement', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    const childCount = view.layout.content.wrapperElement.childNodes.length;
    model._dispatch('createoperator', model, { wrapperElement: null });
    assert.equal(view.layout.content.wrapperElement.childNodes.length, childCount);
});

// ===========================================================================
// on_workspace_removeoperator
// ===========================================================================

test('on_workspace_removeoperator removes operator wrapperElement when present', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});

    const opWrapper = document.createElement('div');
    view.layout.content.wrapperElement.appendChild(opWrapper);
    model._dispatch('removeoperator', model, { wrapperElement: opWrapper });

    assert.ok(!view.layout.content.wrapperElement.childNodes.includes(opWrapper));
});

test('on_workspace_removeoperator does nothing when no wrapperElement', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    model._dispatch('removeoperator', model, { wrapperElement: null });
    assert.ok(true);
});

// ===========================================================================
// on_workspace_change
// ===========================================================================

test('on_workspace_change replaces history state and refreshes header', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        owner: 'owner1', name: 'ws1', title: 'Title1',
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});

    let replaceState = null;
    Wirecloud.HistoryManager.replaceState = (state) => { replaceState = state; };
    let headerRefreshed = false;
    Wirecloud.UserInterfaceManager.header.refresh = () => { headerRefreshed = true; };

    model._dispatch('change', model);

    assert.equal(replaceState.workspace_owner, 'owner1');
    assert.equal(replaceState.workspace_name, 'ws1');
    assert.equal(replaceState.workspace_title, 'Title1');
    assert.equal(replaceState.view, 'workspace');
    assert.equal(headerRefreshed, true);
});

// ===========================================================================
// on_workspace_remove
// ===========================================================================

test('on_workspace_remove navigates to home workspace', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});

    let changeActiveArgs = null;
    Wirecloud.changeActiveWorkspace = (ws) => { changeActiveArgs = ws; return Promise.resolve(); };
    Wirecloud.UserInterfaceManager.monitorTask = (t) => t;

    model._dispatch('remove', model);

    assert.deepEqual(changeActiveArgs, { owner: 'wirecloud', name: 'home' });
});

// ===========================================================================
// on_workspace_unload
// ===========================================================================

test('on_workspace_unload unloads all operators and cleans up', () => {
    let unloadCalls = [];
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        operators: [
            { unload: (force) => { unloadCalls.push(force); } },
            { unload: (force) => { unloadCalls.push(force); } },
        ],
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});

    model._dispatch('unload', model);

    assert.deepEqual(unloadCalls, [true, true]);
    assert.equal(view.editButton.enabled, false);
    assert.equal(view.editButton.active, false);
    assert.equal(view.walletButton.enabled, false);
    assert.equal(view.wiringButton.enabled, false);
});

test('on_workspace_unload handles operators with undefined wrapperElement', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        operators: [{ unload: () => {} }],
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});
    model._dispatch('unload', model);
    assert.ok(true);
});

// ===========================================================================
// on_click_createtab
// ===========================================================================

test('on_click_createtab creates new tab on success', async () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        isAllowed: () => true,
        createTab: () => Promise.resolve({ id: 'new-tab', name: 'newtab', title: 'New', widgets: [], initial: false }),
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});

    const tabCountBefore = view.notebook.tabs.length;
    view.addTabButton._dispatch('click', view.addTabButton);
    await new Promise((r) => setTimeout(r, 10));

    assert.equal(view.notebook.tabs.length, tabCountBefore + 1);
});

test('on_click_createtab re-enables button on failure', async () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        isAllowed: () => true,
        createTab: () => Promise.reject(new Error('fail')),
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});
    view.addTabButton._dispatch('click', view.addTabButton);
    await new Promise((r) => setTimeout(r, 10));

    assert.equal(view.addTabButton._disabled, false);
});

// ===========================================================================
// buildAddWidgetButton
// ===========================================================================

test('buildAddWidgetButton creates ToggleButton', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const button = view.buildAddWidgetButton();
    assert.ok(button instanceof StyledElements.ToggleButton);
});

test('buildAddWidgetButton click with active=true slides in and refreshes', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    view.showcase = { searchComponents: { refresh: () => {} } };
    view.layout = new StyledElements.OffCanvasLayout();

    let slideInCalled = false;
    let refreshCalled = false;
    view.layout.slideIn = () => { slideInCalled = true; return view.layout; };
    view.showcase.searchComponents.refresh = () => { refreshCalled = true; };

    const button = view.buildAddWidgetButton();
    button.active = true;
    button._dispatch('click', button);

    assert.equal(slideInCalled, true);
    assert.equal(refreshCalled, true);
});

test('buildAddWidgetButton click with active=false slides out', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    view.showcase = { searchComponents: { refresh: () => {} } };
    view.layout = new StyledElements.OffCanvasLayout();

    let slideOutCalled = false;
    view.layout.slideOut = () => { slideOutCalled = true; return view.layout; };

    const button = view.buildAddWidgetButton();
    button.active = false;
    button._dispatch('click', button);

    assert.equal(slideOutCalled, true);
});

// ===========================================================================
// findTab
// ===========================================================================

test('findTab returns tab by id', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    const tab = view.notebook.tabs[0];
    assert.equal(view.findTab(tab.id), tab);
});

test('findTab returns null when tab not found', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    assert.equal(view.findTab('non-existent'), null);
});

// ===========================================================================
// findWidget
// ===========================================================================

test('findWidget finds widget across tabs', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    const tab = view.notebook.tabs[0];
    const widget = { id: 'w1', _found: true };
    tab.findWidget = (id) => id === 'w1' ? widget : null;

    assert.equal(view.findWidget('w1'), widget);
});

test('findWidget returns null when widget not found', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    assert.equal(view.findWidget('missing'), null);
});

test('findWidget skips non-WorkspaceTabView tabs', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    const brokenTab = { id: 'loading', findWidget: () => { throw new Error('nope'); } };
    view.notebook.tabs.push(brokenTab);
    assert.equal(view.findWidget('w1'), null);
});

// ===========================================================================
// showSettings
// ===========================================================================

test('showSettings opens PreferencesWindowMenu and returns this', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    let lastMenu = null;
    Wirecloud.ui.PreferencesWindowMenu = class {
        constructor(type, prefs) { lastMenu = { type, prefs, shown: false }; }
        show() { lastMenu.shown = true; return this; }
    };

    const result = view.showSettings();
    assert.equal(lastMenu.type, 'workspace');
    assert.equal(lastMenu.prefs, model.preferences);
    assert.equal(lastMenu.shown, true);
    assert.equal(result, view);
});

// ===========================================================================
// loadWorkspace
// ===========================================================================

test('loadWorkspace creates notebook and sets model.view', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});

    assert.ok(view.notebook instanceof StyledElements.Notebook);
    assert.equal(view.model, model);
    assert.equal(view.model.view, view);
});

test('loadWorkspace slides out and clears content', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    let slideOutCalled = false;
    view.layout.slideOut = () => { slideOutCalled = true; return view.layout; };

    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});

    assert.equal(slideOutCalled, true);
});

test('loadWorkspace creates and removes loading tab', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    // Should have exactly 1 tab (real), loading tab was removed
    assert.equal(view.notebook.tabs.length, 1);
});

test('loadWorkspace registers all model event listeners', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});

    // Dispatch all events to ensure they don't throw
    model._dispatch('change', model);
    model._dispatch('remove', model);
    model._dispatch('unload', model);
    model._dispatch('createoperator', model, { wrapperElement: null });
    model._dispatch('removeoperator', model, { wrapperElement: null });
    assert.ok(true);
});

test('loadWorkspace appends existing operator wrapperElements', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const opWrapper = document.createElement('div');
    const model = createModelMock({
        operators: [{ wrapperElement: opWrapper }],
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});
    assert.ok(view.layout.content.wrapperElement.childNodes.includes(opWrapper));
});

test('loadWorkspace skips operators without wrapperElement', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        operators: [{ wrapperElement: null }],
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});
    assert.ok(true);
});

test('loadWorkspace goes to initial tab', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const tab1Model = { id: 'tab-1', name: 'tab1', title: 'Tab1', initial: false, widgets: [] };
    const tab2Model = { id: 'tab-2', name: 'tab2', title: 'Tab2', initial: true, widgets: [] };
    const model = createModelMock({ tabs: [tab1Model, tab2Model] });
    view.loadWorkspace(model, {});
    assert.equal(view.notebook.visibleTab.model, tab2Model);
});

test('loadWorkspace goes to requestedTab when options.initialtab matches', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const tab1Model = { id: 'tab-1', name: 'tab1', title: 'Tab1', initial: false, widgets: [] };
    const tab2Model = { id: 'tab-2', name: 'tab2', title: 'Tab2', initial: true, widgets: [] };
    const model = createModelMock({ tabs: [tab1Model, tab2Model] });
    view.loadWorkspace(model, { initialtab: 'tab1' });
    assert.equal(view.notebook.visibleTab.model, tab1Model);
});

test('loadWorkspace enables editButton when isAllowed("edit")', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        isAllowed: (perm) => perm === 'edit',
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});
    assert.equal(view.editButton.enabled, true);
});

test('loadWorkspace disables editButton when edit not allowed', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        isAllowed: (perm) => perm !== 'edit',
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});
    assert.equal(view.editButton.enabled, false);
});

test('loadWorkspace creates editingIntervalAddon and addTabButton when edit allowed', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        isAllowed: () => true,
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});
    assert.ok(view.editingIntervalAddon instanceof StyledElements.Addon);
    assert.ok(view.addTabButton instanceof StyledElements.Button);
});

test('loadWorkspace sets addTabButton=null when edit not allowed', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        isAllowed: (perm) => perm !== 'edit',
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});
    assert.equal(view.addTabButton, null);
});

test('loadWorkspace notebook changed event updates editing interval', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        isAllowed: () => true,
        tabs: [
            { id: 'tab-1', name: 'tab1', title: 'Tab1', initial: true, widgets: [] },
            { id: 'tab-2', name: 'tab2', title: 'Tab2', initial: false, widgets: [] },
        ],
    });
    let updateCalled = false;
    view.updateEditingInterval = () => { updateCalled = true; };
    view.loadWorkspace(model, {});
    const newTab = view.notebook.tabs[1];
    view.notebook.dispatchEvent('changed', view.notebook, view.notebook.tabs[0], newTab);
    assert.equal(updateCalled, true);
});

test('loadWorkspace creates fullscreen button when supported', () => {
    Wirecloud.Utils.isFullscreenSupported = () => true;
    Wirecloud.Utils.onFullscreenChange = () => {};

    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    assert.ok(view.fullscreenButton instanceof StyledElements.Button);
});

test('loadWorkspace creates poweredByWirecloudButton when not embedded', () => {
    Wirecloud.contextManager._data.mode = { value: 'normal' };
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    assert.ok(view.poweredByWirecloudButton instanceof StyledElements.Button);
    assert.equal(view.seeOnWirecloudButton, undefined);
});

test('loadWorkspace creates seeOnWirecloudButton when embedded', () => {
    Wirecloud.contextManager._data.mode = { value: 'embedded' };
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    assert.ok(view.seeOnWirecloudButton instanceof StyledElements.Button);
    assert.equal(view.poweredByWirecloudButton, undefined);
});

// ===========================================================================
// buildStateData
// ===========================================================================

test('buildStateData returns state from history manager', () => {
    Wirecloud.HistoryManager._state = {
        workspace_owner: 'ownerX', workspace_name: 'wsX',
        workspace_title: 'TitleX', params: { key: 'val' },
    };
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const data = view.buildStateData();
    assert.equal(data.workspace_owner, 'ownerX');
    assert.equal(data.workspace_name, 'wsX');
    assert.equal(data.workspace_title, 'TitleX');
    assert.equal(data.view, 'workspace');
    assert.deepEqual(data.params, { key: 'val' });
});

// ===========================================================================
// canGoUp
// ===========================================================================

test('canGoUp returns false when activeWorkspace is home', () => {
    Wirecloud.activeWorkspace = { owner: 'wirecloud', name: 'home' };
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.equal(view.canGoUp(), false);
});

test('canGoUp returns true when activeWorkspace is not home', () => {
    Wirecloud.activeWorkspace = { owner: 'other', name: 'other-ws' };
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.equal(view.canGoUp(), true);
});

test('canGoUp returns false when activeWorkspace is null', () => {
    Wirecloud.activeWorkspace = null;
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.equal(view.canGoUp(), false);
});

// ===========================================================================
// goUp
// ===========================================================================

test('goUp navigates to home workspace and returns this', () => {
    let changeArgs = null;
    Wirecloud.changeActiveWorkspace = (ws) => { changeArgs = ws; return Promise.resolve(); };
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const result = view.goUp();
    assert.deepEqual(changeArgs, { owner: 'wirecloud', name: 'home' });
    assert.equal(result, view);
});

// ===========================================================================
// getBreadcrumb
// ===========================================================================

test('getBreadcrumb returns owner and title from model', () => {
    Wirecloud.HistoryManager._state = {};
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        owner: 'testuser', title: 'My WS',
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});
    const entries = view.getBreadcrumb();
    assert.equal(entries.length, 2);
    assert.equal(entries[0].label, 'testuser');
    assert.equal(entries[1].label, 'My WS');
});

test('getBreadcrumb returns from current state when model is null', () => {
    Wirecloud.HistoryManager._state = { workspace_owner: 'sowner', workspace_title: 'STitle' };
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const entries = view.getBreadcrumb();
    assert.equal(entries[0].label, 'sowner');
    assert.equal(entries[1].label, 'STitle');
});

test('getBreadcrumb returns loading when no model and no state workspace', () => {
    Wirecloud.HistoryManager._state = {};
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const entries = view.getBreadcrumb();
    assert.equal(entries.length, 1);
    assert.equal(entries[0].label, 'loading...');
});

// ===========================================================================
// getTitle
// ===========================================================================

test('getTitle returns model owner/title', () => {
    Wirecloud.HistoryManager._state = {};
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        owner: 'user1', title: 'Dashboard',
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});
    assert.equal(view.getTitle(), 'user1/Dashboard');
});

test('getTitle returns from current state when model is null', () => {
    Wirecloud.HistoryManager._state = { workspace_owner: 'suser', workspace_title: 'SDash' };
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.equal(view.getTitle(), 'suser/SDash');
});

test('getTitle returns loading when no model and no state workspace', () => {
    Wirecloud.HistoryManager._state = {};
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.equal(view.getTitle(), 'loading...');
});

// ===========================================================================
// getToolbarMenu
// ===========================================================================

test('getToolbarMenu returns wsMenu when authenticated and has workspace in state', () => {
    Wirecloud.HistoryManager._state = { workspace_owner: 'someone' };
    Wirecloud.contextManager._data.username = { value: 'testuser' };
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.equal(view.getToolbarMenu(), view.wsMenu);
});

test('getToolbarMenu returns null when user is anonymous', () => {
    Wirecloud.HistoryManager._state = { workspace_owner: 'someone' };
    Wirecloud.contextManager._data.username = { value: 'anonymous' };
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.equal(view.getToolbarMenu(), null);
});

test('getToolbarMenu returns null when no workspace in state', () => {
    Wirecloud.HistoryManager._state = {};
    Wirecloud.contextManager._data.username = { value: 'testuser' };
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.equal(view.getToolbarMenu(), null);
});

test('getToolbarMenu returns null when contextManager is null', () => {
    Wirecloud.HistoryManager._state = { workspace_owner: 'someone' };
    Wirecloud.contextManager = null;
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    assert.equal(view.getToolbarMenu(), null);
});

// ===========================================================================
// getToolbarButtons
// ===========================================================================

test('getToolbarButtons returns all buttons when authenticated', () => {
    Wirecloud.contextManager._data.username = { value: 'testuser' };
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const buttons = view.getToolbarButtons();
    assert.equal(buttons.length, 5);
    assert.ok(buttons.includes(view.editButton));
    assert.ok(buttons.includes(view.walletButton));
    assert.ok(buttons.includes(view.wiringButton));
    assert.ok(buttons.includes(view.myresourcesButton));
    assert.ok(buttons.includes(view.marketButton));
});

test('getToolbarButtons returns empty array when user is anonymous', () => {
    Wirecloud.contextManager._data.username = { value: 'anonymous' };
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const buttons = view.getToolbarButtons();
    assert.deepEqual(buttons, []);
});

test('getToolbarButtons returns empty array when contextManager is null', () => {
    Wirecloud.contextManager = null;
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const buttons = view.getToolbarButtons();
    assert.deepEqual(buttons, []);
});

// ===========================================================================
// onHistoryChange
// ===========================================================================

test('onHistoryChange loads workspace when nextWorkspace is different', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    Wirecloud.workspacesByUserAndName = {
        owner1: { ws1: { id: 'ws-new', owner: 'owner1', name: 'ws1' } },
    };
    let changeCalled = false;
    Wirecloud.changeActiveWorkspace = () => { changeCalled = true; return Promise.resolve(); };

    view.onHistoryChange({ workspace_owner: 'owner1', workspace_name: 'ws1', tab: 'default', params: {} });
    assert.equal(changeCalled, true);
});

test('onHistoryChange shows alert when workspace not found and activeWorkspace exists', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    Wirecloud.activeWorkspace = { id: 'existing', unload: () => {} };
    Wirecloud.workspacesByUserAndName = {};
    let dispatchedEvent = null;
    Wirecloud.dispatchEvent = (event) => { dispatchedEvent = event; };

    view.onHistoryChange({ workspace_owner: 'missing', workspace_name: 'gone' });
    assert.equal(dispatchedEvent, 'viewcontextchanged');
    assert.equal(Wirecloud.activeWorkspace, null);
});

test('onHistoryChange shows alert when workspace not found and activeWorkspace is null', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    Wirecloud.activeWorkspace = null;
    Wirecloud.workspacesByUserAndName = {};
    let dispatchedEvent = null;
    Wirecloud.dispatchEvent = (event) => { dispatchedEvent = event; };

    view.onHistoryChange({ workspace_owner: 'missing', workspace_name: 'gone' });
    assert.equal(dispatchedEvent, 'viewcontextchanged');
});

test('onHistoryChange goes to specific tab within same workspace', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        id: 'current-id',
        tabs: [
            { id: 'tab-1', name: 'tab1', title: 'Tab1', initial: true, widgets: [] },
            { id: 'tab-2', name: 'tab2', title: 'Tab2', initial: false, widgets: [] },
        ],
    });
    view.loadWorkspace(model, {});

    Wirecloud.activeWorkspace = { id: 'current-id', unload: () => {} };
    Wirecloud.workspacesByUserAndName = {
        'test-owner': { 'test-ws': model },
    };

    let goToTabArg = null;
    view.notebook.goToTab = (tab) => { goToTabArg = tab; };

    view.onHistoryChange({
        workspace_owner: 'test-owner', workspace_name: 'test-ws',
        tab: 'tab2', tab_id: view.notebook.tabs[1].id,
    });
    assert.equal(goToTabArg, view.notebook.tabs[1]);
    assert.equal(document.title, 'test-owner/test-ws');
});

test('onHistoryChange updates document title when no tab change needed', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        id: 'current-id',
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});

    Wirecloud.activeWorkspace = { id: 'current-id', unload: () => {} };
    Wirecloud.workspacesByUserAndName = {
        'test-owner': { 'test-ws': model },
    };

    view.onHistoryChange({ workspace_owner: 'test-owner', workspace_name: 'test-ws' });
    assert.equal(document.title, 'test-owner/test-ws');
});

// ===========================================================================
// drawAttention
// ===========================================================================

test('drawAttention highlights the widget and its tab', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});

    let widgetHighlighted = false;
    let tabHighlighted = false;
    const widget = {
        id: 'w1',
        tab: {
            highlight: () => { tabHighlighted = true; },
        },
        highlight: function () { widgetHighlighted = true; return this; },
    };
    view.findWidget = (id) => id === 'w1' ? widget : null;

    const result = view.drawAttention('w1');
    assert.equal(widgetHighlighted, true);
    assert.equal(tabHighlighted, true);
    assert.equal(result, view);
});

test('drawAttention does nothing when widget not found', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    const result = view.drawAttention('missing');
    assert.equal(result, view);
});

// ===========================================================================
// updateEditingInterval
// ===========================================================================

test('updateEditingInterval replaces addon content with element', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        isAllowed: () => true,
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});
    const el = document.createElement('span');
    el.textContent = 'new interval';

    view.updateEditingInterval(el);
    assert.ok(view.editingIntervalAddon.wrapperElement.childNodes.includes(el));
});

test('updateEditingInterval does nothing when addon is null', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        isAllowed: (perm) => perm !== 'edit',
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});
    view.updateEditingInterval(document.createElement('span'));
    assert.ok(true);
});

// ===========================================================================
// ComponentSidebar create event handlers (loaded callback)
// ===========================================================================

test('loaded handler: create event for widget type disables button', () => {
    const { Wirecloud } = setup();
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    Wirecloud.dispatchEvent('loaded');

    let buttonDisabled = false;
    const button = { disable: () => { buttonDisabled = true; }, enable: () => {} };
    const group = { meta: { type: 'widget' } };
    view.showcase._dispatch('create', view.showcase, group, button);
    assert.equal(buttonDisabled, true);
});

test('loaded handler: create event for non-widget handles success', () => {
    const { Wirecloud } = setup();
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    Wirecloud.dispatchEvent('loaded');

    let mergeCalled = false;
    Wirecloud.mergeWorkspace = () => { mergeCalled = true; return Promise.resolve({ id: 'new', owner: 'x', name: 'y' }); };
    Wirecloud.changeActiveWorkspace = () => Promise.resolve();
    Wirecloud.UserInterfaceManager.monitorTask = (p) => p;

    const button = { disable: () => {}, enable: () => {} };
    const group = { meta: { type: 'operator', uri: 'some-uri' } };
    view.showcase._dispatch('create', view.showcase, group, button);

    return new Promise((resolve) => setTimeout(() => {
        assert.equal(mergeCalled, true);
        resolve();
    }, 10));
});

test('loaded handler: merge error with missingDependencies shows MissingDependenciesWindowMenu', () => {
    const { Wirecloud } = setup();
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    Wirecloud.dispatchEvent('loaded');

    let lastDialog = null;
    Wirecloud.ui.MissingDependenciesWindowMenu = class {
        constructor(_, error) { lastDialog = this; this.shown = false; }
        show() { this.shown = true; return this; }
    };
    Wirecloud.mergeWorkspace = () => Promise.reject({ details: { missingDependencies: ['d1', 'd2'] } });
    Wirecloud.UserInterfaceManager.monitorTask = (p) => p;

    const button = { disable: () => {}, enable: () => {} };
    const group = { meta: { type: 'operator', uri: 'some-uri' } };
    view.showcase._dispatch('create', view.showcase, group, button);

    return new Promise((resolve) => setTimeout(() => {
        assert.ok(lastDialog != null);
        assert.equal(lastDialog.shown, true);
        resolve();
    }, 10));
});

test('loaded handler: merge error without missingDependencies shows MessageWindowMenu', () => {
    const { Wirecloud } = setup();
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    Wirecloud.dispatchEvent('loaded');

    let lastDialog = null;
    Wirecloud.ui.MessageWindowMenu = class {
        constructor(error, level) { lastDialog = this; this.shown = false; }
        show() { this.shown = true; return this; }
    };
    Wirecloud.mergeWorkspace = () => Promise.reject(new Error('General error'));
    Wirecloud.UserInterfaceManager.monitorTask = (p) => p;

    const button = { disable: () => {}, enable: () => {} };
    const group = { meta: { type: 'operator', uri: 'some-uri' } };
    view.showcase._dispatch('create', view.showcase, group, button);

    return new Promise((resolve) => setTimeout(() => {
        assert.ok(lastDialog != null);
        assert.equal(lastDialog.shown, true);
        resolve();
    }, 10));
});

// ===========================================================================
// Fullscreen button
// ===========================================================================

test('fullscreen button: click requests fullscreen when not in fullscreen', () => {
    Wirecloud.Utils.isFullscreenSupported = () => true;
    Wirecloud.Utils.onFullscreenChange = () => {};

    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});

    view.notebook.fullscreen = false;
    let requestCalled = false;
    view.notebook.requestFullscreen = () => { requestCalled = true; };

    view.fullscreenButton._dispatch('click');
    assert.equal(requestCalled, true);
});

test('fullscreen button: click exits fullscreen when already in fullscreen', () => {
    Wirecloud.Utils.isFullscreenSupported = () => true;
    Wirecloud.Utils.onFullscreenChange = () => {};

    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});

    view.notebook.fullscreen = true;
    let exitCalled = false;
    view.notebook.exitFullscreen = () => { exitCalled = true; };

    view.fullscreenButton._dispatch('click');
    assert.equal(exitCalled, true);
});

// ===========================================================================
// Embedded mode: seeOnWirecloudButton
// ===========================================================================

test('seeOnWirecloudButton click opens workspace URL in new window', () => {
    Wirecloud.contextManager._data.mode = { value: 'embedded' };
    let openUrl = null;
    let openTarget = null;
    global.window.open = (url, target) => { openUrl = url; openTarget = target; };

    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        owner: 'testowner', name: 'testws',
        tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }],
    });
    view.loadWorkspace(model, {});
    view.seeOnWirecloudButton._dispatch('click');

    assert.ok(openUrl.includes('testowner'));
    assert.ok(openUrl.includes('testws'));
    assert.equal(openTarget, '_blank');
});

// ===========================================================================
// poweredByWirecloudButton
// ===========================================================================

test('poweredByWirecloudButton click opens github URL', () => {
    Wirecloud.contextManager._data.mode = { value: 'normal' };
    let openUrl = null;
    let openTarget = null;
    global.window.open = (url, target) => { openUrl = url; openTarget = target; };

    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    view.poweredByWirecloudButton._dispatch('click');

    assert.equal(openUrl, 'https://github.com/Wirecloud/wirecloud');
    assert.equal(openTarget, '_blank');
});

// ===========================================================================
// Line 138: WorkspaceListItems handler in constructor
// ===========================================================================

test('constructor WorkspaceListItems handler calls changeActiveWorkspace', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const handler = view.wsMenu._items[0]._handler;
    let monitorCalled = false;
    let changeArgs = null;
    Wirecloud.UserInterfaceManager.monitorTask = (p) => { monitorCalled = true; return p; };
    Wirecloud.changeActiveWorkspace = (ws) => { changeArgs = ws; return Promise.resolve(); };
    handler('context', { owner: 'test', name: 'ws-name' });
    assert.deepEqual(changeArgs, { owner: 'test', name: 'ws-name' });
    assert.equal(monitorCalled, true);
});

// ===========================================================================
// Lines 257-258: showcase create widget error path
// ===========================================================================

test('loaded handler: create widget error re-enables button', () => {
    const { Wirecloud } = setup();
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});
    Wirecloud.dispatchEvent('loaded');

    let enabled = false;
    const button = { disable: () => {}, enable: () => { enabled = true; } };
    const group = { meta: { type: 'widget' } };
    view.activeTab.createWidget = () => Promise.reject(new Error('fail'));
    view.showcase._dispatch('create', view.showcase, group, button);

    return new Promise((resolve) => setTimeout(() => {
        assert.equal(enabled, true);
        resolve();
    }, 10));
});

// ===========================================================================
// Lines 389-390: notebook changed event inside edit-allowed branch
// ===========================================================================

test('loadWorkspace notebook changed event calls updateEditingScreenSizeName', () => {
    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({
        isAllowed: () => true,
        tabs: [
            { id: 'tab-1', name: 'tab1', title: 'Tab1', initial: true, widgets: [] },
            { id: 'tab-2', name: 'tab2', title: 'Tab2', initial: false, widgets: [] },
        ],
    });
    view.loadWorkspace(model, {});

    const newTab = view.notebook.tabs[1];
    let nameUpdated = false;
    newTab.updateEditingScreenSizeName = () => { nameUpdated = true; };
    let intervalUpdated = false;
    view.updateEditingInterval = () => { intervalUpdated = true; };

    const handler = view.notebook._listeners['changed'][0];
    handler(view.notebook, view.notebook.tabs[0], newTab);

    assert.equal(nameUpdated, true);
    assert.equal(intervalUpdated, true);
});

// ===========================================================================
// Lines 413-422: fullscreen onFullscreenChange callback
// ===========================================================================

test('fullscreen onFullscreenChange callback updates button and notebook', () => {
    Wirecloud.Utils.isFullscreenSupported = () => true;

    let fsCallback = null;
    Wirecloud.Utils.onFullscreenChange = (el, cb) => { fsCallback = cb; };

    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});

    view.notebook.fullscreen = true;
    fsCallback();
    assert.ok(view.notebook.wrapperElement.classList.contains('fullscreen'));
    assert.equal(view.fullscreenButton.wrapperElement.getAttribute('title'), 'Exit full screen');

    view.notebook.fullscreen = false;
    fsCallback();
    assert.ok(!view.notebook.wrapperElement.classList.contains('fullscreen'));
    assert.equal(view.fullscreenButton.wrapperElement.getAttribute('title'), 'Full screen');
});

test('fullscreen button click toggles fullscreen mode', () => {
    Wirecloud.Utils.isFullscreenSupported = () => true;
    Wirecloud.Utils.onFullscreenChange = () => {};

    const view = new Wirecloud.ui.WorkspaceView(0, {});
    const model = createModelMock({ tabs: [{ id: 'tab-1', name: 'tab1', title: 'Tab', initial: true, widgets: [] }] });
    view.loadWorkspace(model, {});

    view.notebook._fullscreen = false;
    let requestedFullscreen = false;
    view.notebook.requestFullscreen = () => { requestedFullscreen = true; };
    view.fullscreenButton._dispatch('click');
    assert.ok(requestedFullscreen);

    view.notebook._fullscreen = true;
    let exitedFullscreen = false;
    view.notebook.exitFullscreen = () => { exitedFullscreen = true; };
    view.fullscreenButton._dispatch('click');
    assert.ok(exitedFullscreen);
});
