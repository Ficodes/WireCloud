const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScript,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');

// ============================================================================
// HELPERS
// ============================================================================

// Builds the DOM tree that the mocked GUIBuilder returns, matching the new
// theme template: an outer wrapper div (the GridStack item) whose first
// child is the content div (`.grid-stack-item-content`) holding
// `.wc-widget-heading` and `.wc-widget-body`.
const fakeParseResult = () => {
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

    // The real GUIBuilder returns a Fragment whose second child (index 1)
    // is the parsed template root; WidgetView.js does `.children[1]`.
    const fragment = {
        children: [
            document.createElement('div'), // dummy first child
            wrapper,
        ],
    };
    return { fragment, wrapper, content, heading, body };
};

const makeModel = (overrides = {}) => {
    const wrapperElement = document.createElement('div');
    wrapperElement.contentDocument = { defaultView: { addEventListener() {} } };

    const model = Object.assign({
        id: 'widget-1',
        volatile: false,
        missing: false,
        loaded: false,
        title: 'Test Widget',
        meta: { macversion: 1, doc: 'manual', version: '1.0' },

        permissions: {
            editor: { close: true, configure: true, move: true, rename: true, resize: true, minimize: true, upgrade: true },
            viewer: { close: false, configure: false, move: false, rename: false, resize: false, minimize: false, upgrade: false },
        },

        wrapperElement,

        isAllowed(name, role) {
            role = role || 'viewer';
            if (this.volatile) {
                return true;
            }
            return !!this.permissions[role][name];
        },

        contextManager: {
            _lastModify: null,
            _allModifies: [],
            modify(data) {
                this._lastModify = data;
                this._allModifies.push(data);
            },
        },

        logManager: {
            errorCount: 0,
            _listeners: {},
            addEventListener(event, handler) {
                (this._listeners[event] = this._listeners[event] || []).push(handler);
            },
            _dispatch(event) {
                (this._listeners[event] || []).forEach((h) => h());
            },
        },

        _eventListeners: {},
        addEventListener(event, handler) {
            (this._eventListeners[event] = this._eventListeners[event] || []).push(handler);
        },
        removeEventListener() {},
        _dispatchEvent(event, ...args) {
            // Real dispatchEvent always passes the model itself as the first
            // argument to every listener.
            (this._eventListeners[event] || []).forEach((h) => h(model, ...args));
        },

        _layoutCalls: [],
        setLayout(id, changes, persist) {
            this._layoutCalls.push({ id: String(id), changes, persist });
            return Promise.resolve(this);
        },

        _permissionCalls: [],
        setPermissions(changes, persist) {
            this._permissionCalls.push({ changes, persist });
            Object.assign(this.permissions.viewer, changes);
            return Promise.resolve(this);
        },

        load() { this._loaded = true; },
        reload() { this._reloaded = true; },
        remove() { this._removed = true; },
        rename(title) { this._renamed = title; },
        showLogs() { this._logsShown = true; },
        showSettings() { this._settingsShown = true; },
    }, overrides);

    return model;
};

const makeGrid = (overrides = {}) => Object.assign({
    calls: [],
    update(el, opts) {
        this.calls.push({ el, opts });
        el.gridstackNode = Object.assign({}, el.gridstackNode, opts);
    },
    getCellHeight() { return 40; },
}, overrides);

const makeWorkspace = (overrides = {}) => Object.assign({
    editing: true,
    hidden: false,
    _listeners: {},
    addEventListener(event, handler) {
        (this._listeners[event] = this._listeners[event] || []).push(handler);
    },
    _dispatch(event, ...args) {
        (this._listeners[event] || []).forEach((h) => h(...args));
    },
}, overrides);

const makeDragboard = (overrides = {}) => Object.assign({
    activeScreenSize: { id: 0, name: 'Phone', moreOrEqual: 0, lessOrEqual: 767, columns: 12 },
    grid: null,
    views: [],
    cellheight: 40,
    margin: 5,
    applying: false,
    withApplying(fn) {
        const was = this.applying;
        this.applying = true;
        try {
            fn();
        } finally {
            this.applying = was;
        }
    },
    addWidget(view) {
        if (this.views.indexOf(view) === -1) {
            this.views.push(view);
        }
    },
    _refreshCalls: [],
    refreshWidget(view) {
        this._refreshCalls.push(view);
    },
    _removeCalls: [],
    removeWidget(view) {
        this._removeCalls.push(view);
        const index = this.views.indexOf(view);
        if (index !== -1) {
            this.views.splice(index, 1);
        }
    },
    _moveCalls: [],
    moveWidgetToTab(view, tabView) {
        this._moveCalls.push({ view, tabView });
        return Promise.resolve(view.model);
    },
    resolveLayout(model) {
        return null;
    },
    hiddenWidgets: [],
}, overrides);

const makeTab = (overrides = {}) => {
    const workspace = overrides.workspace || makeWorkspace();
    const dragboard = overrides.dragboard || makeDragboard();
    const tab = Object.assign({
        id: 'tab-1',
        hidden: false,
        wrapperElement: document.createElement('div'),
        _listeners: {},
        addEventListener(event, handler) {
            (this._listeners[event] = this._listeners[event] || []).push(handler);
        },
        _dispatch(event, ...args) {
            (this._listeners[event] || []).forEach((h) => h(...args));
        },
    }, overrides);
    tab.workspace = workspace;
    tab.dragboard = dragboard;
    dragboard.tab = tab;
    return tab;
};

// ============================================================================
// SETUP
// ============================================================================

let _guibuilderParseResult;

const setup = (overrides = {}) => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();

    // Augment Element prototype with the DOM helpers WidgetView relies on
    // and that the hand-written browser shim does not provide.
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
            get() {
                return (this.childNodes || []).filter((n) => n.nodeType === 1);
            },
        });
    }

    _guibuilderParseResult = overrides.parseResult || null;

    StyledElements.GUIBuilder = class GUIBuilder {
        constructor() {}
        parse(doc, tcomponents, context) {
            if (tcomponents && typeof tcomponents === 'object') {
                Object.keys(tcomponents).forEach((key) => {
                    const fn = tcomponents[key];
                    if (typeof fn === 'function') {
                        fn({}, tcomponents, context);
                    }
                });
            }
            // A fresh DOM fragment per call, so widget views constructed in
            // the same test never share a wrapper element.
            return _guibuilderParseResult || fakeParseResult().fragment;
        }
    };

    StyledElements.Button = class Button extends StyledElements.StyledElement {
        constructor(options = {}) {
            super(['blur', 'click', 'dblclick', 'focus', 'mouseenter', 'mouseleave']);
            this.wrapperElement = document.createElement('div');
            this.wrapperElement.setAttribute('role', 'button');
            this.wrapperElement.className = 'se-btn';
            this.icon = null;
            this._title = '';
            if (options.class) this.addClassName(options.class);
            if (options.iconClass) this.addIconClassName(options.iconClass);
            if (options.title) this.setTitle(options.title);
            if (options.plain) this.addClassName('plain');
        }
        addIconClassName(classList) {
            if (!this.icon) {
                this.icon = document.createElement('i');
                this.icon.className = 'se-icon';
                this.wrapperElement.appendChild(this.icon);
            }
            (Array.isArray(classList) ? classList : String(classList || '').split(/\s+/)).forEach((c) => {
                if (c) this.icon.classList.add(c);
            });
            return this;
        }
        removeIconClassName(classList) {
            if (this.icon) {
                (Array.isArray(classList) ? classList : String(classList || '').split(/\s+/)).forEach((c) => {
                    if (c) this.icon.classList.remove(c);
                });
            }
            return this;
        }
        replaceIconClassName(oldC, newC) {
            return this.removeIconClassName(oldC).addIconClassName(newC);
        }
        setTitle(title) {
            this._title = title;
            this.wrapperElement.setAttribute('title', String(title || ''));
            return this;
        }
        getTitle() { return this._title; }
        addClassName(name) { this.wrapperElement.classList.add(name); return this; }
    };

    StyledElements.PopupMenu = class PopupMenu extends StyledElements.StyledElement {
        constructor() {
            super(['visibilityChange']);
            this.wrapperElement = document.createElement('ul');
            this._items = [];
        }
        append(item) { this._items.push(item); return this; }
    };

    StyledElements.PopupButton = class PopupButton extends StyledElements.Button {
        constructor(options = {}) {
            super(options);
            this.wrapperElement.setAttribute('aria-haspopup', 'true');
            this.popup_menu = options.menu || new StyledElements.PopupMenu();
        }
    };

    StyledElements.EditableElement = class EditableElement extends StyledElements.StyledElement {
        constructor(options = {}) {
            super(['change']);
            this.wrapperElement = document.createElement('span');
            this.wrapperElement.setAttribute('role', 'textbox');
            this.setTextContent(options.initialContent || '');
        }
        setTextContent(text) {
            this.wrapperElement.textContent = text;
            return this;
        }
        enableEdition() { this._editionEnabled = true; }
    };

    global.Wirecloud = {
        Utils: Object.assign({}, StyledElements.Utils),
        ui: {},
    };

    Wirecloud.currentTheme = {
        templates: {
            'wirecloud/workspace/widget': '<s:dummy></s:dummy>',
        },
    };

    Wirecloud.UserInterfaceManager = {
        _escapeCalls: [],
        handleEscapeEvent(...args) { this._escapeCalls.push(args); },
    };

    Wirecloud.ui.LogWindowMenu = class LogWindowMenu {
        constructor(manager) { this.manager = manager; Wirecloud.ui._lastLogWindow = this; }
        show() { this._shown = true; }
    };

    // Stub: menu building itself is tested separately against the real
    // WidgetViewMenuItems implementation.
    Wirecloud.ui.WidgetViewMenuItems = class WidgetViewMenuItems {
        constructor(view) { this.view = view; }
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WidgetView.js');
};

const createWidgetView = (options = {}) => {
    const model = options.model || makeModel();
    const tab = options.tab || makeTab(options);
    return new Wirecloud.ui.WidgetView(tab, model, {});
};

// ============================================================================
// CONSTRUCTION
// ============================================================================

test('constructor: sets up base classes, attribute and DOM references', () => {
    setup();
    const view = createWidgetView();

    assert.ok(view instanceof Wirecloud.ui.WidgetView);
    assert.equal(view.wrapperElement.classList.contains('wc-widget'), true);
    assert.equal(view.wrapperElement.classList.contains('grid-stack-item'), true);
    assert.equal(view.wrapperElement.getAttribute('data-id'), 'widget-1');
    assert.equal(view.id, 'widget-1');
    assert.equal(view.model.id, 'widget-1');
    assert.equal(view.contentElement, view.wrapperElement.children[0]);
    assert.ok(view.heading);
    assert.equal(view.heading.classList.contains('wc-widget-heading'), true);
    assert.equal(view.title, 'Test Widget');
});

test('constructor: builds every button/component declared by the template', () => {
    setup();
    const view = createWidgetView();

    assert.ok(view.closebutton);
    assert.ok(view.errorbutton);
    assert.ok(view.grip);
    assert.ok(view.menubutton);
    assert.ok(view.minimizebutton);
    assert.ok(view.titleelement);
    assert.ok(view.titlevisibilitybutton);
    assert.equal(view.errorbutton.hidden, true, 'errorbutton starts hidden');
});

test('constructor: registers the view with the tab dragboard', () => {
    setup();
    const dragboard = makeDragboard();
    const tab = makeTab({ dragboard });
    const view = createWidgetView({ tab });

    assert.equal(dragboard.views.includes(view), true);
});

test('constructor: layout starts null and title delegates to the model', () => {
    setup();
    const model = makeModel({ title: 'Initial' });
    const view = createWidgetView({ model });

    assert.equal(view.layout, null);
    assert.equal(view.title, 'Initial');
    model.title = 'Renamed';
    assert.equal(view.title, 'Renamed');
});

test('constructor: closebutton click removes the widget', () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });

    view.closebutton.dispatchEvent('click');
    assert.equal(model._removed, true);
});

test('constructor: grip click toggles the viewer move permission', () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });

    view.grip.dispatchEvent('click');
    assert.equal(model._permissionCalls.length, 1);
    assert.deepEqual(model._permissionCalls[0].changes, { move: true });
    assert.equal(model._permissionCalls[0].persist, true);
});

test('constructor: minimizebutton click toggles minimize status with persistence', () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });

    // change_layout_flag() persists the *whole* currentLayout (not just the
    // changed flag) so a screen size with no stored layout yet keeps its
    // derived position/size; starting from a null view.layout, x/y/w/h stay
    // undefined.
    view.minimizebutton.dispatchEvent('click');
    assert.equal(model._layoutCalls.length, 1);
    assert.deepEqual(model._layoutCalls[0].changes, {
        x: undefined, y: undefined, w: undefined, h: undefined,
        minimized: true, titlevisible: false, fulldragboard: false, visible: true,
    });
    assert.equal(model._layoutCalls[0].persist, true);
});

test('constructor: titlevisibilitybutton click toggles title visibility with persistence', () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });

    // Starting from a null layout, "not titlevisible" is truthy, so the
    // first click makes the title visible.
    view.titlevisibilitybutton.dispatchEvent('click');
    assert.equal(model._layoutCalls.length, 1);
    assert.deepEqual(model._layoutCalls[0].changes, {
        x: undefined, y: undefined, w: undefined, h: undefined,
        minimized: false, titlevisible: true, fulldragboard: false, visible: true,
    });
    assert.equal(model._layoutCalls[0].persist, true);
});

test('constructor: title element change renames the model', () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });

    view.titleelement.dispatchEvent('change', 'New Title');
    assert.equal(model._renamed, 'New Title');
});

test('constructor: errorbutton click opens a LogWindowMenu bound to the widget logManager', () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });

    view.errorbutton.dispatchEvent('click', view.errorbutton);
    assert.equal(Wirecloud.ui._lastLogWindow.manager, model.logManager);
    assert.equal(Wirecloud.ui._lastLogWindow._shown, true);
});

test('constructor: menubutton popup menu holds a WidgetViewMenuItems instance for this view', () => {
    setup();
    const view = createWidgetView();

    assert.equal(view.menubutton.popup_menu._items.length, 1);
    assert.ok(view.menubutton.popup_menu._items[0] instanceof Wirecloud.ui.WidgetViewMenuItems);
    assert.equal(view.menubutton.popup_menu._items[0].view, view);
});

// ============================================================================
// currentLayout
// ============================================================================

test('currentLayout: reads x/y/w from the gridstack node and h from the node when not minimized', () => {
    setup();
    const view = createWidgetView();
    view.applyLayout({ x: 1, y: 2, w: 3, h: 4, minimized: false, titlevisible: true, fulldragboard: false, visible: true });
    view.wrapperElement.gridstackNode = { x: 5, y: 6, w: 7, h: 8 };

    const current = view.currentLayout;
    assert.deepEqual(current, { x: 5, y: 6, w: 7, h: 8, minimized: false, titlevisible: true, fulldragboard: false, visible: true });
});

test('currentLayout: uses the remembered un-minimized height while minimized', () => {
    setup();
    const view = createWidgetView();
    view.applyLayout({ x: 0, y: 0, w: 4, h: 6, minimized: false, titlevisible: true, fulldragboard: false, visible: true });
    // Minimize afterwards: the node height collapses to the header row count,
    // but currentLayout must still report the remembered height (6).
    view.applyLayout({ x: 0, y: 0, w: 4, h: 6, minimized: true, titlevisible: true, fulldragboard: false, visible: true });
    view.wrapperElement.gridstackNode = { x: 0, y: 0, w: 4, h: 1 };

    assert.equal(view.currentLayout.h, 6);
});

test('currentLayout: falls back to the applied layout fields when there is no gridstack node', () => {
    setup();
    const view = createWidgetView();
    view.applyLayout({ x: 2, y: 3, w: 4, h: 5, minimized: false, titlevisible: false, fulldragboard: true, visible: false });
    delete view.wrapperElement.gridstackNode;

    assert.deepEqual(view.currentLayout, { x: 2, y: 3, w: 4, h: 5, minimized: false, titlevisible: false, fulldragboard: true, visible: false });
});

test('currentLayout: booleans are coerced even when the layout stores falsy/undefined flags', () => {
    setup();
    const view = createWidgetView();
    view.layout = { x: 0, y: 0, w: 1, h: 1 };
    view.wrapperElement.gridstackNode = { x: 0, y: 0, w: 1, h: 1 };

    const current = view.currentLayout;
    assert.equal(current.minimized, false);
    assert.equal(current.titlevisible, false);
    assert.equal(current.fulldragboard, false);
    assert.equal(current.visible, true); // visible !== false -> true
});

// ============================================================================
// canMove / canResize
// ============================================================================

test('canMove: false whenever the layout is in full dragboard mode', () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });
    view.layout = { fulldragboard: true };
    assert.equal(view.canMove, false);
});

test('canMove: uses the editor role while editing and the viewer role otherwise', () => {
    setup();
    const model = makeModel();
    model.permissions.editor.move = true;
    model.permissions.viewer.move = false;
    const workspace = makeWorkspace({ editing: true });
    const view = createWidgetView({ model, tab: makeTab({ workspace }) });
    view.layout = { fulldragboard: false };

    assert.equal(view.canMove, true);
    workspace.editing = false;
    assert.equal(view.canMove, false);
});

test('canResize: false when full dragboard or minimized', () => {
    setup();
    const model = makeModel();
    model.permissions.editor.resize = true;
    const view = createWidgetView({ model });

    view.layout = { fulldragboard: true, minimized: false };
    assert.equal(view.canResize, false);

    view.layout = { fulldragboard: false, minimized: true };
    assert.equal(view.canResize, false);

    view.layout = { fulldragboard: false, minimized: false };
    assert.equal(view.canResize, true);
});

test('canResize: delegates to model.isAllowed("resize", role)', () => {
    setup();
    const model = makeModel();
    model.permissions.editor.resize = false;
    const view = createWidgetView({ model, tab: makeTab({ workspace: makeWorkspace({ editing: true }) }) });
    view.layout = { fulldragboard: false, minimized: false };
    assert.equal(view.canResize, false);
});

// ============================================================================
// applyLayout
// ============================================================================

test('applyLayout: stores the layout and toggles CSS classes accordingly', () => {
    setup();
    const model = makeModel({ missing: true });
    model.permissions.editor.move = true;
    const view = createWidgetView({ model });

    view.applyLayout({ x: 0, y: 0, w: 4, h: 3, minimized: true, titlevisible: true, fulldragboard: true, visible: true });

    assert.equal(view.layout.minimized, true);
    assert.equal(view.wrapperElement.classList.contains('wc-missing-widget'), true);
    assert.equal(view.wrapperElement.classList.contains('wc-titled-widget'), true);
    assert.equal(view.wrapperElement.classList.contains('wc-minimized-widget'), true);
    assert.equal(view.wrapperElement.classList.contains('wc-widget-fulldragboard'), true);
});

test('applyLayout: wc-moveable-widget class reflects canMove', () => {
    setup();
    const model = makeModel();
    model.permissions.editor.move = true;
    const view = createWidgetView({ model });

    view.applyLayout({ x: 0, y: 0, w: 1, h: 1, minimized: false, titlevisible: true, fulldragboard: false, visible: true });
    assert.equal(view.wrapperElement.classList.contains('wc-moveable-widget'), true);
});

test('applyLayout: sets _unminimizedHeight from a non-minimized layout and keeps it while minimized', () => {
    setup();
    const view = createWidgetView();

    view.applyLayout({ x: 0, y: 0, w: 4, h: 9, minimized: false, titlevisible: true, fulldragboard: false, visible: true });
    assert.equal(view._unminimizedHeight, 9);

    view.applyLayout({ x: 0, y: 0, w: 4, h: 1, minimized: true, titlevisible: true, fulldragboard: false, visible: true });
    assert.equal(view._unminimizedHeight, 9, 'must remember the height from before minimizing');
});

test('applyLayout: toggles wc-fulldragboard-active on the tab when any view is in full dragboard mode', () => {
    setup();
    const dragboard = makeDragboard();
    const tab = makeTab({ dragboard });
    const viewA = createWidgetView({ tab, model: makeModel({ id: 'a' }) });
    const viewB = createWidgetView({ tab, model: makeModel({ id: 'b' }) });

    viewA.applyLayout({ x: 0, y: 0, w: 1, h: 1, minimized: false, titlevisible: true, fulldragboard: false, visible: true });
    assert.equal(tab.wrapperElement.classList.contains('wc-fulldragboard-active'), false);

    viewB.applyLayout({ x: 0, y: 0, w: 1, h: 1, minimized: false, titlevisible: true, fulldragboard: true, visible: true });
    assert.equal(tab.wrapperElement.classList.contains('wc-fulldragboard-active'), true);

    viewB.applyLayout({ x: 0, y: 0, w: 1, h: 1, minimized: false, titlevisible: true, fulldragboard: false, visible: true });
    assert.equal(tab.wrapperElement.classList.contains('wc-fulldragboard-active'), false);
});

test('applyLayout: when minimized, updates the grid with the computed collapsed row count and noResize', () => {
    setup();
    const grid = makeGrid();
    const dragboard = makeDragboard({ grid });
    const view = createWidgetView({ tab: makeTab({ dragboard }) });
    view.wrapperElement.gridstackNode = { x: 0, y: 0, w: 4, h: 5 };
    view.heading.offsetHeight = 40;

    view.applyLayout({ x: 0, y: 0, w: 4, h: 5, minimized: true, titlevisible: true, fulldragboard: false, visible: true });

    const call = grid.calls.find((c) => c.el === view.wrapperElement);
    assert.ok(call);
    assert.equal(call.opts.noResize, true);
    assert.equal(call.opts.h, 1); // 40px heading / 40px cell height, no margins in the shim
});

test('applyLayout: when not minimized, updates the grid height to layout.h', () => {
    setup();
    const grid = makeGrid();
    const dragboard = makeDragboard({ grid });
    const view = createWidgetView({ tab: makeTab({ dragboard }) });
    view.wrapperElement.gridstackNode = { x: 0, y: 0, w: 4, h: 1 };

    view.applyLayout({ x: 0, y: 0, w: 4, h: 7, minimized: false, titlevisible: true, fulldragboard: false, visible: true });

    const call = grid.calls.find((c) => c.el === view.wrapperElement);
    assert.deepEqual(call.opts, { h: 7 });
});

test('applyLayout: updates the node.grid if different from dragboard.grid (docked widget)', () => {
    setup();
    const mainGrid = makeGrid();
    const dockGrid = makeGrid();
    const dragboard = makeDragboard({ grid: mainGrid });
    const view = createWidgetView({ tab: makeTab({ dragboard }) });
    view.wrapperElement.gridstackNode = { x: 0, y: 0, w: 4, h: 1, grid: dockGrid };

    view.applyLayout({ x: 0, y: 0, w: 4, h: 8, minimized: false, titlevisible: true, fulldragboard: false, visible: true });

    // dockGrid must receive the updates, not mainGrid
    assert.equal(mainGrid.calls.length, 0);
    assert.ok(dockGrid.calls.some((c) => c.el === view.wrapperElement && c.opts.h === 8));
    assert.ok(dockGrid.calls.some((c) => c.el === view.wrapperElement && 'noMove' in c.opts));
});

test('applyLayout: does not touch the grid when there is no gridstack node yet', () => {
    setup();
    const grid = makeGrid();
    const dragboard = makeDragboard({ grid });
    const view = createWidgetView({ tab: makeTab({ dragboard }) });
    // No gridstackNode assigned.

    view.applyLayout({ x: 0, y: 0, w: 1, h: 1, minimized: false, titlevisible: true, fulldragboard: false, visible: true });

    assert.equal(grid.calls.length, 0);
});

test('applyLayout: does not touch the grid when the dragboard has no grid yet', () => {
    setup();
    const dragboard = makeDragboard({ grid: null });
    const view = createWidgetView({ tab: makeTab({ dragboard }) });
    view.wrapperElement.gridstackNode = { x: 0, y: 0, w: 1, h: 1 };

    assert.doesNotThrow(() => {
        view.applyLayout({ x: 0, y: 0, w: 1, h: 1, minimized: false, titlevisible: true, fulldragboard: false, visible: true });
    });
});

test('applyLayout: refreshes grid move/resize permissions', () => {
    setup();
    const grid = makeGrid();
    const dragboard = makeDragboard({ grid });
    const model = makeModel();
    model.permissions.editor.move = false;
    model.permissions.editor.resize = false;
    const view = createWidgetView({ model, tab: makeTab({ dragboard }) });
    view.wrapperElement.gridstackNode = { x: 0, y: 0, w: 1, h: 1 };

    view.applyLayout({ x: 0, y: 0, w: 1, h: 1, minimized: false, titlevisible: true, fulldragboard: false, visible: true });

    const permissionCall = grid.calls.find((c) => 'noMove' in c.opts);
    assert.ok(permissionCall);
    assert.equal(permissionCall.opts.noMove, true);
    assert.equal(permissionCall.opts.noResize, true);
});

test('applyLayout: re-notifies the widget context', () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });
    view.wrapperElement.gridstackNode = { x: 3, y: 4, w: 5, h: 6 };
    model.contextManager._lastModify = null;

    view.applyLayout({ x: 3, y: 4, w: 5, h: 6, minimized: false, titlevisible: true, fulldragboard: false, visible: true });

    assert.ok(model.contextManager._lastModify);
    assert.equal(model.contextManager._lastModify.xPosition, 3);
    assert.equal(model.contextManager._lastModify.yPosition, 4);
    assert.equal(model.contextManager._lastModify.width, 5);
    assert.equal(model.contextManager._lastModify.height, 6);
});

test('compute_minimized_rows: factors in the heading CSS margins when window.getComputedStyle is available', () => {
    setup();
    const grid = makeGrid();
    const dragboard = makeDragboard({ grid });
    const view = createWidgetView({ tab: makeTab({ dragboard }) });
    view.wrapperElement.gridstackNode = { x: 0, y: 0, w: 4, h: 3 };
    view.heading.offsetHeight = 40;

    const original = global.getComputedStyle;
    global.getComputedStyle = () => ({ marginTop: '10px', marginBottom: '10px' });
    try {
        view.applyLayout({ x: 0, y: 0, w: 4, h: 3, minimized: true, titlevisible: true, fulldragboard: false, visible: true });
    } finally {
        if (original === undefined) {
            delete global.getComputedStyle;
        } else {
            global.getComputedStyle = original;
        }
    }

    const call = grid.calls.find((c) => c.el === view.wrapperElement);
    assert.equal(call.opts.h, 2); // (40 + 10 + 10) / 40 = 1.5 -> ceil -> 2
});

// ============================================================================
// syncLayoutFromNode
// ============================================================================

test('syncLayoutFromNode: no-op when there is no gridstack node or no applied layout', () => {
    setup();
    const view = createWidgetView();
    assert.equal(view.syncLayoutFromNode(), view);

    view.applyLayout({ x: 0, y: 0, w: 1, h: 1, minimized: false, titlevisible: true, fulldragboard: false, visible: true });
    delete view.wrapperElement.gridstackNode;
    const before = Object.assign({}, view.layout);
    view.syncLayoutFromNode();
    assert.deepEqual(view.layout, before);
});

test('syncLayoutFromNode: copies x/y/w/h from the node when not minimized and remembers the height', () => {
    setup();
    const view = createWidgetView();
    view.applyLayout({ x: 0, y: 0, w: 1, h: 1, minimized: false, titlevisible: true, fulldragboard: false, visible: true });
    view.wrapperElement.gridstackNode = { x: 2, y: 3, w: 4, h: 5 };

    view.syncLayoutFromNode();

    assert.equal(view.layout.x, 2);
    assert.equal(view.layout.y, 3);
    assert.equal(view.layout.w, 4);
    assert.equal(view.layout.h, 5);
    assert.equal(view._unminimizedHeight, 5);
});

test('syncLayoutFromNode: leaves h untouched while minimized (node height is the collapsed one)', () => {
    setup();
    const view = createWidgetView();
    view.applyLayout({ x: 0, y: 0, w: 4, h: 8, minimized: true, titlevisible: true, fulldragboard: false, visible: true });
    view.wrapperElement.gridstackNode = { x: 1, y: 1, w: 4, h: 1 };

    view.syncLayoutFromNode();

    assert.equal(view.layout.h, 8, 'height must stay at the remembered value while minimized');
    assert.equal(view.layout.x, 1);
    assert.equal(view.layout.y, 1);
});

// ============================================================================
// updateGridPermissions
// ============================================================================

test('updateGridPermissions: no-op when there is no grid', () => {
    setup();
    const dragboard = makeDragboard({ grid: null });
    const view = createWidgetView({ tab: makeTab({ dragboard }) });
    view.wrapperElement.gridstackNode = { x: 0, y: 0, w: 1, h: 1 };
    assert.doesNotThrow(() => view.updateGridPermissions());
});

test('updateGridPermissions: no-op when there is no gridstack node', () => {
    setup();
    const grid = makeGrid();
    const dragboard = makeDragboard({ grid });
    const view = createWidgetView({ tab: makeTab({ dragboard }) });
    view.updateGridPermissions();
    assert.equal(grid.calls.length, 0);
});

test('updateGridPermissions: writes noMove/noResize matching canMove/canResize', () => {
    setup();
    const grid = makeGrid();
    const dragboard = makeDragboard({ grid });
    const model = makeModel();
    model.permissions.editor.move = true;
    model.permissions.editor.resize = false;
    const view = createWidgetView({ model, tab: makeTab({ dragboard }) });
    view.layout = { fulldragboard: false, minimized: false };
    view.wrapperElement.gridstackNode = { x: 0, y: 0, w: 1, h: 1 };

    view.updateGridPermissions();

    assert.equal(grid.calls.length, 1);
    assert.deepEqual(grid.calls[0].opts, { noMove: false, noResize: true });
});

// ============================================================================
// setMinimizeStatus / toggleMinimizeStatus
// ============================================================================

test('setMinimizeStatus: resolves without side effects when the status is unchanged', async () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });
    view.layout = { minimized: true };

    const result = await view.setMinimizeStatus(true);
    assert.equal(result, view);
    assert.equal(model._layoutCalls.length, 0);
});

test('setMinimizeStatus: applies the new layout and persists through the model', async () => {
    setup();
    const model = makeModel();
    const dragboard = makeDragboard({ activeScreenSize: { id: 2, columns: 12 } });
    const view = createWidgetView({ model, tab: makeTab({ dragboard }) });
    view.layout = { minimized: false, titlevisible: true, fulldragboard: false, visible: true, x: 0, y: 0, w: 1, h: 1 };

    const result = await view.setMinimizeStatus(true, true);

    assert.equal(view.layout.minimized, true);
    assert.equal(result, view);
    assert.equal(model._layoutCalls.length, 1);
    assert.equal(model._layoutCalls[0].id, '2');
    assert.deepEqual(model._layoutCalls[0].changes, {
        x: 0, y: 0, w: 1, h: 1, minimized: true, titlevisible: true, fulldragboard: false, visible: true,
    });
    assert.equal(model._layoutCalls[0].persist, true);
});

test('toggleMinimizeStatus: flips the current minimized flag', async () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });
    view.layout = { minimized: false, x: 0, y: 0, w: 1, h: 1, titlevisible: true, fulldragboard: false, visible: true };

    await view.toggleMinimizeStatus(false);
    assert.equal(view.layout.minimized, true);

    await view.toggleMinimizeStatus(false);
    assert.equal(view.layout.minimized, false);
});

// ============================================================================
// toggleTitleVisibility
// ============================================================================

test('toggleTitleVisibility: flips titlevisible, manages busy state on the button and persists', async () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });
    view.layout = { titlevisible: true, x: 0, y: 0, w: 1, h: 1, minimized: false, fulldragboard: false, visible: true };

    const promise = view.toggleTitleVisibility(true);
    // The button is marked busy immediately; applyLayout() (called
    // synchronously as part of change_layout_flag) then recomputes
    // `.enabled` from the model/layout state through update_buttons(), so
    // only the "busy" class survives as a synchronous visual cue.
    assert.equal(view.titlevisibilitybutton.hasClassName('busy'), true);

    const result = await promise;

    assert.equal(result, view);
    assert.equal(view.layout.titlevisible, false);
    assert.equal(view.titlevisibilitybutton.enabled, true);
    assert.equal(view.titlevisibilitybutton.hasClassName('busy'), false);
    assert.equal(model._layoutCalls.length, 1);
    assert.deepEqual(model._layoutCalls[0].changes, {
        x: 0, y: 0, w: 1, h: 1, minimized: false, titlevisible: false, fulldragboard: false, visible: true,
    });
    assert.equal(model._layoutCalls[0].persist, true);
});

test('toggleTitleVisibility: re-enables the button even when persistence rejects', async () => {
    setup();
    const model = makeModel();
    model.setLayout = () => Promise.reject(new Error('boom'));
    const view = createWidgetView({ model });
    view.layout = { titlevisible: true, x: 0, y: 0, w: 1, h: 1, minimized: false, fulldragboard: false, visible: true };

    await assert.rejects(view.toggleTitleVisibility(true), /boom/);
    assert.equal(view.titlevisibilitybutton.enabled, true);
    assert.equal(view.titlevisibilitybutton.hasClassName('busy'), false);
});

// ============================================================================
// setFullDragboardMode
// ============================================================================

test('setFullDragboardMode: resolves without side effects when unchanged', async () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });
    view.layout = { fulldragboard: true };

    const result = await view.setFullDragboardMode(true);
    assert.equal(result, view);
    assert.equal(model._layoutCalls.length, 0);
});

test('setFullDragboardMode: applies the layout and persists through the model', async () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });
    view.layout = { fulldragboard: false, x: 0, y: 0, w: 1, h: 1, minimized: false, titlevisible: true, visible: true };

    const result = await view.setFullDragboardMode(true, true);

    assert.equal(view.layout.fulldragboard, true);
    assert.equal(result, view);
    assert.deepEqual(model._layoutCalls[0].changes, {
        x: 0, y: 0, w: 1, h: 1, minimized: false, titlevisible: true, fulldragboard: true, visible: true,
    });
    assert.equal(model._layoutCalls[0].persist, true);
    assert.equal(view.wrapperElement.classList.contains('wc-widget-fulldragboard'), true);
    assert.equal(view.tab.wrapperElement.scrollTop, 0);
});

// ============================================================================
// hideInCurrentScreenSize / showInCurrentScreenSize
// ============================================================================

test('hideInCurrentScreenSize: persists the whole layout with visible:false, then refreshes the widget', async () => {
    setup();
    const model = makeModel();
    const dragboard = makeDragboard({ activeScreenSize: { id: 1, columns: 6 } });
    const view = createWidgetView({ model, tab: makeTab({ dragboard }) });
    view.applyLayout({ x: 2, y: 3, w: 4, h: 5, minimized: false, titlevisible: true, fulldragboard: false, visible: true });

    const result = await view.hideInCurrentScreenSize();

    assert.equal(result, view);
    assert.equal(model._layoutCalls.length, 1);
    assert.equal(model._layoutCalls[0].id, '1');
    // The geometry travels with the flag: the widget must come back to the same
    // place when shown again, and the screen sizes that derive their layout from
    // this one must keep a full layout to derive from.
    assert.deepEqual(model._layoutCalls[0].changes, {
        x: 2, y: 3, w: 4, h: 5,
        minimized: false, titlevisible: true, fulldragboard: false, visible: false,
    });
    assert.equal(model._layoutCalls[0].persist, true);
    assert.deepEqual(dragboard._refreshCalls, [view]);
});

test('hideInCurrentScreenSize: never persists a "derived" marker', async () => {
    setup();
    const model = makeModel();
    const dragboard = makeDragboard({ activeScreenSize: { id: 1, columns: 6 } });
    const view = createWidgetView({ model, tab: makeTab({ dragboard }) });
    view.applyLayout({ x: 0, y: 0, w: 2, h: 2, minimized: false, titlevisible: true, fulldragboard: false, visible: true, derived: true });

    await view.hideInCurrentScreenSize();

    assert.equal('derived' in model._layoutCalls[0].changes, false);
});

test('showInCurrentScreenSize: persists the whole layout with visible:true, then refreshes the widget', async () => {
    setup();
    const model = makeModel();
    const dragboard = makeDragboard({ activeScreenSize: { id: 0, columns: 12 } });
    const view = createWidgetView({ model, tab: makeTab({ dragboard }) });
    view.applyLayout({ x: 1, y: 6, w: 3, h: 7, minimized: false, titlevisible: true, fulldragboard: false, visible: false });

    const result = await view.showInCurrentScreenSize();

    assert.equal(result, view);
    assert.deepEqual(model._layoutCalls[0].changes, {
        x: 1, y: 6, w: 3, h: 7,
        minimized: false, titlevisible: true, fulldragboard: false, visible: true,
    });
    assert.equal(model._layoutCalls[0].persist, true);
    assert.deepEqual(dragboard._refreshCalls, [view]);
});

// ============================================================================
// moveToTab
// ============================================================================

test('moveToTab: delegates to dragboard.moveWidgetToTab', () => {
    setup();
    const dragboard = makeDragboard();
    const view = createWidgetView({ tab: makeTab({ dragboard }) });
    const targetTab = { id: 'other-tab' };

    view.moveToTab(targetTab);

    assert.equal(dragboard._moveCalls.length, 1);
    assert.equal(dragboard._moveCalls[0].view, view);
    assert.equal(dragboard._moveCalls[0].tabView, targetTab);
});

// ============================================================================
// togglePermission
// ============================================================================

test('togglePermission: negates the current viewer permission and delegates to the model', () => {
    setup();
    const model = makeModel();
    model.permissions.viewer.move = false;
    const view = createWidgetView({ model });

    view.togglePermission('move', true);

    assert.equal(model._permissionCalls.length, 1);
    assert.deepEqual(model._permissionCalls[0].changes, { move: true });
    assert.equal(model._permissionCalls[0].persist, true);
});

// ============================================================================
// load / repaint / reload / showLogs / showSettings
// ============================================================================

test('load: loads the model and adds the "in" class when not already loaded', () => {
    setup();
    const model = makeModel({ loaded: false });
    const view = createWidgetView({ model });

    const result = view.load();

    assert.equal(model._loaded, true);
    assert.equal(view.contentElement.classList.contains('in'), true);
    assert.equal(result, view);
});

test('load: does not reload an already-loaded model but still repaints', () => {
    setup();
    const model = makeModel({ loaded: true });
    const view = createWidgetView({ model });
    model.contextManager._lastModify = null;

    view.load();

    assert.equal(model._loaded, undefined);
    assert.ok(model.contextManager._lastModify);
});

test('repaint: re-notifies context and returns the view', () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });
    model.contextManager._lastModify = null;

    const result = view.repaint();

    assert.equal(result, view);
    assert.ok(model.contextManager._lastModify);
});

test('reload: delegates to the model and returns the view', () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });
    assert.equal(view.reload(), view);
    assert.equal(model._reloaded, true);
});

test('showLogs: delegates to the model and returns the view', () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });
    assert.equal(view.showLogs(), view);
    assert.equal(model._logsShown, true);
});

test('showSettings: delegates to the model and returns the view', () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });
    assert.equal(view.showSettings(), view);
    assert.equal(model._settingsShown, true);
});

// ============================================================================
// highlight / unhighlight
// ============================================================================

test('highlight: marks the content panel as success and dispatches highlight once', () => {
    setup();
    const view = createWidgetView();
    let highlighted = 0;
    view.addEventListener('highlight', () => { highlighted += 1; });

    view.highlight();

    assert.equal(view.contentElement.classList.contains('panel-success'), true);
    assert.equal(view.contentElement.classList.contains('panel-default'), false);
    assert.equal(view.wrapperElement.classList.contains('wc-widget-highlight'), true);
    assert.equal(highlighted, 1);
});

test('highlight: calling it again resets the animation without re-dispatching the event', () => {
    setup();
    const view = createWidgetView();
    let highlighted = 0;
    view.addEventListener('highlight', () => { highlighted += 1; });

    view.highlight();
    view.highlight();

    assert.equal(highlighted, 1, 'event only fires the first time the highlight is applied');
    assert.equal(view.wrapperElement.classList.contains('wc-widget-highlight'), false, 'class removed synchronously to restart the CSS animation');
});

test('unhighlight: restores the default panel look and dispatches unhighlight only if it was highlighted', () => {
    setup();
    const view = createWidgetView();
    let unhighlighted = 0;
    view.addEventListener('unhighlight', () => { unhighlighted += 1; });

    view.unhighlight();
    assert.equal(unhighlighted, 0, 'nothing to undo yet');

    view.highlight();
    view.unhighlight();

    assert.equal(view.contentElement.classList.contains('panel-success'), false);
    assert.equal(view.contentElement.classList.contains('panel-default'), true);
    assert.equal(view.wrapperElement.classList.contains('wc-widget-highlight'), false);
    assert.equal(unhighlighted, 1);
});

// ============================================================================
// toJSON
// ============================================================================

test('toJSON: returns the id and the current layout keyed by the active screen size', () => {
    setup();
    const dragboard = makeDragboard({ activeScreenSize: { id: 2, columns: 12 } });
    const view = createWidgetView({ tab: makeTab({ dragboard }) });
    view.applyLayout({ x: 1, y: 2, w: 3, h: 4, minimized: false, titlevisible: true, fulldragboard: false, visible: true });
    view.wrapperElement.gridstackNode = { x: 1, y: 2, w: 3, h: 4 };

    const json = view.toJSON();

    assert.deepEqual(json, {
        id: view.id,
        layouts: {
            '2': { x: 1, y: 2, w: 3, h: 4, minimized: false, titlevisible: true, fulldragboard: false, visible: true },
        },
    });
});

// ============================================================================
// remove
// ============================================================================

test('remove: delegates to the model and returns the view', () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });
    assert.equal(view.remove(), view);
    assert.equal(model._removed, true);
});

// ============================================================================
// MODEL EVENTS
// ============================================================================

test('model "change" with title updates the title element text content', () => {
    setup();
    const model = makeModel({ title: 'Old' });
    const view = createWidgetView({ model });

    model.title = 'New';
    model._dispatchEvent('change', ['title']);

    assert.equal(view.titleelement.wrapperElement.textContent, 'New');
});

test('model "change" with meta refreshes classes and buttons', () => {
    setup();
    const model = makeModel({ missing: false });
    const view = createWidgetView({ model });
    assert.equal(view.wrapperElement.classList.contains('wc-missing-widget'), false);

    model.missing = true;
    model._dispatchEvent('change', ['meta']);

    assert.equal(view.wrapperElement.classList.contains('wc-missing-widget'), true);
});

test('model "change" with permissions refreshes classes, buttons and grid permissions', () => {
    setup();
    const grid = makeGrid();
    const dragboard = makeDragboard({ grid });
    const model = makeModel();
    model.permissions.editor.move = false;
    const view = createWidgetView({ model, tab: makeTab({ dragboard }) });
    view.layout = { fulldragboard: false, minimized: false };
    view.wrapperElement.gridstackNode = { x: 0, y: 0, w: 1, h: 1 };
    grid.calls = [];

    model.permissions.editor.move = true;
    model._dispatchEvent('change', ['permissions']);

    assert.ok(grid.calls.some((c) => 'noMove' in c.opts && c.opts.noMove === false));
});

test('model "unload" un-highlights the widget', () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });
    view.highlight();

    model._dispatchEvent('unload');

    assert.equal(view.wrapperElement.classList.contains('wc-widget-highlight'), false);
});

test('model "load" adds the "in" class, installs keydown/click listeners and repaints', () => {
    setup();
    const model = makeModel({ meta: { macversion: 1 } });
    const view = createWidgetView({ model });
    model.contextManager._lastModify = null;

    let keydownHandler = null;
    let clickHandler = null;
    model.wrapperElement.contentDocument.defaultView.addEventListener = (type, handler, useCapture) => {
        if (type === 'keydown') keydownHandler = handler;
        if (type === 'click') clickHandler = handler;
    };

    model._dispatchEvent('load');

    assert.equal(view.contentElement.classList.contains('in'), true);
    assert.ok(model.contextManager._lastModify, 'repaint() was called');
    assert.equal(typeof keydownHandler, 'function');
    assert.equal(typeof clickHandler, 'function');

    keydownHandler({ keyCode: 27 });
    assert.equal(Wirecloud.UserInterfaceManager._escapeCalls.length, 1);

    view.highlight();
    clickHandler();
    assert.equal(Wirecloud.UserInterfaceManager._escapeCalls.length, 2);
    assert.equal(Wirecloud.UserInterfaceManager._escapeCalls[1][0], true);
    assert.equal(view.wrapperElement.classList.contains('wc-widget-highlight'), false);
});

test('model "load" listens on the wrapperElement itself for macversion > 1 widgets', () => {
    setup();
    const model = makeModel({ meta: { macversion: 2 } });
    let listenedOn = null;
    model.wrapperElement.addEventListener = (type) => { listenedOn = model.wrapperElement; };
    const view = createWidgetView({ model });

    model._dispatchEvent('load');

    assert.equal(listenedOn, model.wrapperElement);
});

test('model "remove" removes the widget from the dragboard and dispatches the view remove event', () => {
    setup();
    const dragboard = makeDragboard();
    const model = makeModel();
    const view = createWidgetView({ model, tab: makeTab({ dragboard }) });

    let removed = false;
    view.addEventListener('remove', () => { removed = true; });

    model._dispatchEvent('remove');

    assert.deepEqual(dragboard._removeCalls, [view]);
    assert.equal(removed, true);
});

test('workspace "editmode" refreshes classes, buttons and grid permissions', () => {
    setup();
    const workspace = makeWorkspace({ editing: false });
    const view = createWidgetView({ tab: makeTab({ workspace }) });

    assert.equal(view.menubutton.hidden, true);

    workspace.editing = true;
    workspace._dispatch('editmode');

    assert.equal(view.menubutton.hidden, false);
});

test('workspace/tab "show" and "hide" re-notify the widget context', () => {
    setup();
    const model = makeModel();
    const workspace = makeWorkspace();
    const tab = makeTab({ workspace });
    const view = createWidgetView({ model, tab });

    model.contextManager._lastModify = null;
    workspace._dispatch('show');
    assert.ok(model.contextManager._lastModify);

    model.contextManager._lastModify = null;
    workspace._dispatch('hide');
    assert.ok(model.contextManager._lastModify);

    model.contextManager._lastModify = null;
    tab._dispatch('show');
    assert.ok(model.contextManager._lastModify);

    model.contextManager._lastModify = null;
    tab._dispatch('hide');
    assert.ok(model.contextManager._lastModify);
});

test('logManager "newentry" updates the error button', () => {
    setup();
    const model = makeModel();
    const view = createWidgetView({ model });

    model.logManager.errorCount = 2;
    model.logManager._dispatch('newentry');
    assert.equal(view.errorbutton.hidden, false);
    assert.equal(view.errorbutton.getTitle(), '2 errors');

    model.logManager.errorCount = 1;
    model.logManager._dispatch('newentry');
    assert.equal(view.errorbutton.getTitle(), '1 error');

    model.logManager.errorCount = 0;
    model.logManager._dispatch('newentry');
    assert.equal(view.errorbutton.hidden, true);
});

// ============================================================================
// notify_context: visibility flag
// ============================================================================

test('notify_context: visible is false while minimized, tab hidden or workspace hidden', () => {
    setup();
    const model = makeModel();
    const workspace = makeWorkspace({ hidden: false });
    const tab = makeTab({ workspace });
    const view = createWidgetView({ model, tab });

    view.applyLayout({ x: 0, y: 0, w: 1, h: 1, minimized: false, titlevisible: true, fulldragboard: false, visible: true });
    assert.equal(model.contextManager._lastModify.visible, true);

    view.applyLayout({ x: 0, y: 0, w: 1, h: 1, minimized: true, titlevisible: true, fulldragboard: false, visible: true });
    assert.equal(model.contextManager._lastModify.visible, false);

    view.applyLayout({ x: 0, y: 0, w: 1, h: 1, minimized: false, titlevisible: true, fulldragboard: false, visible: false });
    assert.equal(model.contextManager._lastModify.visible, false);

    tab.hidden = true;
    view.repaint();
    assert.equal(model.contextManager._lastModify.visible, false);
});

// ============================================================================
// update_buttons (constructed at different editing/permission states)
// ============================================================================

test('update_buttons: grip is hidden for volatile widgets even while editing', () => {
    setup();
    const model = makeModel({ volatile: true });
    const view = createWidgetView({ model, tab: makeTab({ workspace: makeWorkspace({ editing: true }) }) });
    assert.equal(view.grip.hidden, true);
});

test('update_buttons: grip icon and title reflect whether viewers may move the widget', () => {
    setup();
    const model = makeModel();
    model.permissions.viewer.move = false;
    const view = createWidgetView({ model, tab: makeTab({ workspace: makeWorkspace({ editing: true }) }) });

    assert.equal(view.grip.hidden, false);
    assert.equal(view.grip.icon.classList.contains('fa-anchor'), true);
    assert.equal(view.grip.getTitle(), 'Allow to move this widget');

    model.permissions.viewer.move = true;
    model._dispatchEvent('change', ['meta']);

    assert.equal(view.grip.icon.classList.contains('fa-grip-vertical'), true);
    assert.equal(view.grip.getTitle(), 'Disallow to move this widget');
});

test('update_buttons: titlevisibilitybutton hidden unless editing, disabled when minimized or volatile', () => {
    setup();
    const model = makeModel();
    const workspace = makeWorkspace({ editing: false });
    const view = createWidgetView({ model, tab: makeTab({ workspace }) });
    assert.equal(view.titlevisibilitybutton.hidden, true);

    workspace.editing = true;
    workspace._dispatch('editmode');
    assert.equal(view.titlevisibilitybutton.hidden, false);
    assert.equal(view.titlevisibilitybutton.enabled, true);

    view.applyLayout({ x: 0, y: 0, w: 1, h: 1, minimized: true, titlevisible: true, fulldragboard: false, visible: true });
    assert.equal(view.titlevisibilitybutton.enabled, false);
});

test('update_buttons: minimizebutton.enabled follows model.isAllowed("minimize", role)', () => {
    setup();
    const model = makeModel();
    model.permissions.editor.minimize = false;
    const workspace = makeWorkspace({ editing: true });
    const view = createWidgetView({ model, tab: makeTab({ workspace }) });
    assert.equal(view.minimizebutton.enabled, false);

    model.permissions.editor.minimize = true;
    model._dispatchEvent('change', ['meta']);
    assert.equal(view.minimizebutton.enabled, true);
});

test('update_buttons: closebutton is hidden unless volatile or editing, and the model allows close', () => {
    setup();
    const model = makeModel({ volatile: false });
    model.permissions.editor.close = true;
    const workspace = makeWorkspace({ editing: false });
    const view = createWidgetView({ model, tab: makeTab({ workspace }) });
    assert.equal(view.closebutton.hidden, true, 'not volatile and not editing');

    workspace.editing = true;
    workspace._dispatch('editmode');
    assert.equal(view.closebutton.hidden, false);

    model.permissions.editor.close = false;
    model._dispatchEvent('change', ['meta']);
    assert.equal(view.closebutton.hidden, true, 'model denies close even while editing');
});

test('update_buttons: closebutton is visible for volatile widgets in viewer mode when close is allowed', () => {
    setup();
    const model = makeModel({ volatile: true });
    const workspace = makeWorkspace({ editing: false });
    const view = createWidgetView({ model, tab: makeTab({ workspace }) });
    assert.equal(view.closebutton.hidden, false);
});

test('update_buttons: menubutton is only shown while editing', () => {
    setup();
    const workspace = makeWorkspace({ editing: false });
    const view = createWidgetView({ tab: makeTab({ workspace }) });
    assert.equal(view.menubutton.hidden, true);

    workspace.editing = true;
    workspace._dispatch('editmode');
    assert.equal(view.menubutton.hidden, false);
});
