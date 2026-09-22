const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScript,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');
const {installGridStackMock} = require('../../support/gridstack-mock.cjs');

// ===========================================================================
// MOCK HELPERS
// ===========================================================================

const DEFAULT_SCREEN_SIZES = [
    {id: 0, name: 'Phone', moreOrEqual: 0, lessOrEqual: 767, columns: 1},
    {id: 1, name: 'Tablet', moreOrEqual: 768, lessOrEqual: 1199, columns: 6},
    {id: 2, name: 'Desktop', moreOrEqual: 1200, lessOrEqual: -1, columns: 12},
];

const cloneScreenSizes = (list) => list.map((entry) => Object.assign({}, entry));

const defaultLayout = () => ({
    x: null,
    y: null,
    w: 1,
    h: 1,
    minimized: false,
    titlevisible: true,
    fulldragboard: false,
    visible: true,
});

const createPreferencesMock = (overrides = {}) => {
    const listeners = {};
    const values = Object.assign({
        cellheight: 40,
        margin: 5,
        screenSizes: cloneScreenSizes(DEFAULT_SCREEN_SIZES),
    }, overrides);

    return {
        _values: values,
        get(key) {
            return this._values[key];
        },
        addEventListener(type, handler) {
            (listeners[type] = listeners[type] || []).push(handler);
        },
        // Simulates Preferences#dispatchEvent('post-commit', modifiedValues):
        // the source (this preferences instance) is prepended as the first arg.
        _trigger(type, payload) {
            (listeners[type] || []).slice().forEach((handler) => handler(this, payload));
        },
    };
};

const createWorkspaceMock = (overrides = {}) => {
    const listeners = {};
    return {
        model: Object.assign({id: 'workspace-1', restricted: false}, overrides.model),
        editing: overrides.editing !== undefined ? overrides.editing : true,
        addEventListener(type, handler) {
            (listeners[type] = listeners[type] || []).push(handler);
        },
        _trigger(type, ...args) {
            (listeners[type] || []).slice().forEach((handler) => handler(this, ...args));
        },
    };
};

const createTabMock = (overrides = {}) => {
    const wrapperElement = document.createElement('div');
    wrapperElement.offsetWidth = overrides.offsetWidth !== undefined ? overrides.offsetWidth : 1200;
    if (overrides.offsetHeight !== undefined) {
        wrapperElement.offsetHeight = overrides.offsetHeight;
    }

    const preferences = overrides.preferences || createPreferencesMock(overrides.preferenceValues);
    const workspace = overrides.workspace || createWorkspaceMock(overrides.workspaceOptions);

    return {
        wrapperElement,
        model: Object.assign({id: 'tab-1', preferences}, overrides.model),
        workspace,
    };
};

const createWidgetModel = (overrides = {}) => {
    const layouts = {};
    Object.keys(overrides.layouts || {}).forEach((key) => {
        layouts[key] = Object.assign(defaultLayout(), overrides.layouts[key]);
    });

    const permissions = Object.assign({move: true, resize: true}, overrides.permissions);

    return {
        id: overrides.id !== undefined ? overrides.id : ('widget-' + Math.random().toString(36).slice(2, 8)),
        volatile: !!overrides.volatile,
        _layouts: layouts,
        setLayoutCalls: [],
        removeLayoutCalls: [],
        get layouts() {
            const copy = {};
            Object.keys(this._layouts).forEach((key) => {
                copy[key] = Object.assign({}, this._layouts[key]);
            });
            return copy;
        },
        getLayout(screenSizeId) {
            const id = String(screenSizeId);
            return (id in this._layouts) ? Object.assign({}, this._layouts[id]) : null;
        },
        setLayout(screenSizeId, changes, persist = false) {
            const id = String(screenSizeId);
            const current = this._layouts[id] || defaultLayout();
            this._layouts[id] = Object.assign({}, current, changes);
            this.setLayoutCalls.push({id, changes, persist});
            return Promise.resolve(this);
        },
        removeLayout(screenSizeId, persist = false) {
            const id = String(screenSizeId);
            delete this._layouts[id];
            this.removeLayoutCalls.push({id, persist});
            return Promise.resolve(this);
        },
        isAllowed(permission, role) {
            if (typeof overrides.isAllowed === 'function') {
                return overrides.isAllowed(permission, role);
            }
            return permissions[permission] !== false;
        },
        changeTab: overrides.changeTab || (() => Promise.resolve()),
    };
};

const createWidgetView = (model, overrides = {}) => {
    const wrapperElement = document.createElement('div');

    const view = {
        id: model.id,
        model,
        wrapperElement,
        layout: null,
        applyLayoutCalls: [],
        syncCalls: 0,
        updateGridPermissionsCalls: 0,
        applyLayout(layout) {
            this.layout = layout;
            this.applyLayoutCalls.push(layout);
            return this;
        },
        syncLayoutFromNode() {
            this.syncCalls++;
            const node = this.wrapperElement.gridstackNode;
            if (node != null && this.layout != null) {
                this.layout.x = node.x;
                this.layout.y = node.y;
                this.layout.w = node.w;
                if (!this.layout.minimized) {
                    this.layout.h = node.h;
                }
            }
            return this;
        },
        updateGridPermissions() {
            this.updateGridPermissionsCalls++;
        },
        get currentLayout() {
            const node = this.wrapperElement.gridstackNode || {};
            const layout = this.layout || {};
            return {
                x: node.x != null ? node.x : layout.x,
                y: node.y != null ? node.y : layout.y,
                w: node.w != null ? node.w : layout.w,
                h: node.h != null ? node.h : layout.h,
                minimized: !!layout.minimized,
                titlevisible: !!layout.titlevisible,
                fulldragboard: !!layout.fulldragboard,
                visible: layout.visible !== false,
            };
        },
        toJSON() {
            const activeId = String(this.tab.dragboard.activeScreenSize.id);
            return {
                id: this.id,
                layouts: {[activeId]: this.currentLayout},
            };
        },
    };

    return Object.assign(view, overrides);
};

// ===========================================================================
// SETUP
// ===========================================================================

let windowListeners;

const setup = () => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();
    const GridStack = installGridStackMock();

    if (global.Wirecloud == null) {
        global.Wirecloud = {};
    }
    Wirecloud.Utils = StyledElements.Utils;
    Wirecloud.ui = Wirecloud.ui || {};

    Wirecloud.URLs = {
        IWIDGET_COLLECTION: {
            evaluate: (params) => `/api/workspaces/${params.workspace_id}/tabs/${params.tab_id}/iwidgets/`,
        },
    };

    Wirecloud.GlobalLogManager = {
        parseErrorResponse: (response) => new Error('server-error-' + response.status),
    };

    Wirecloud.io = {
        makeRequest: () => Promise.resolve({status: 204}),
    };

    global.window.innerWidth = 1200;

    // The DOM shim does not implement window.addEventListener; provide a
    // minimal one so the "window resize fallback" path can be exercised.
    windowListeners = {};
    global.window.addEventListener = (type, handler) => {
        (windowListeners[type] = windowListeners[type] || []).push(handler);
    };
    global.window.removeEventListener = (type, handler) => {
        if (windowListeners[type]) {
            windowListeners[type] = windowListeners[type].filter((h) => h !== handler);
        }
    };
    global.window.dispatchEvent = (event) => {
        (windowListeners[event.type] || []).forEach((handler) => handler(event));
    };

    delete global.ResizeObserver;

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/SidebarLayout.js');
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewDragboard.js');

    return {GridStack};
};

/**
 * Builds a dragboard from a fresh tab mock.
 */
const createDragboard = (tabOverrides = {}) => {
    const tab = createTabMock(tabOverrides);
    const dragboard = new Wirecloud.ui.WorkspaceTabViewDragboard(tab);
    tab.dragboard = dragboard;
    return {dragboard, tab};
};

const paintedDragboard = (tabOverrides = {}) => {
    const result = createDragboard(tabOverrides);
    result.dragboard.paint();
    result.grid = result.dragboard.grid;
    return result;
};

const wait = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));

test.beforeEach(() => {
    setup();
});

// ===========================================================================
// CONSTRUCTION
// ===========================================================================

test('constructor creates and appends the grid element to the tab wrapper', () => {
    const {dragboard, tab} = createDragboard();

    assert.ok(dragboard.gridElement != null);
    assert.equal(dragboard.gridElement.className, 'grid-stack wc-dragboard');
    assert.equal(dragboard.gridElement.parentNode, tab.wrapperElement);
    assert.ok(tab.wrapperElement.childNodes.includes(dragboard.gridElement));
});

test('constructor reads cellheight and margin from tab preferences', () => {
    const {dragboard} = createDragboard({preferenceValues: {cellheight: 77, margin: 13}});

    assert.equal(dragboard.cellheight, 77);
    assert.equal(dragboard.margin, 13);
});

test('constructor initializes grid/painted/applying/views state', () => {
    const {dragboard} = createDragboard();

    assert.equal(dragboard.grid, null);
    assert.equal(dragboard.painted, false);
    assert.equal(dragboard.applying, false);
    assert.deepEqual(dragboard.views, []);
    assert.equal(dragboard.forcedScreenSizeId, null);
});

test('constructor uses ResizeObserver on the tab wrapper when available', () => {
    const observeCalls = [];
    let capturedCallback = null;
    global.ResizeObserver = class {
        constructor(callback) {
            capturedCallback = callback;
        }
        observe(el) {
            observeCalls.push(el);
        }
        disconnect() {}
    };

    const {dragboard, tab} = createDragboard();

    assert.equal(observeCalls.length, 1);
    assert.equal(observeCalls[0], tab.wrapperElement);
    assert.equal(typeof capturedCallback, 'function');

    delete global.ResizeObserver;
});

test('constructor falls back to a window resize listener when ResizeObserver is unavailable', () => {
    delete global.ResizeObserver;

    createDragboard();

    assert.ok(windowListeners.resize != null && windowListeners.resize.length === 1);
});

test('ResizeObserver callback re-applies the screen size after paint when width changed', () => {
    let observedCallback = null;
    global.ResizeObserver = class {
        constructor(callback) {
            observedCallback = callback;
        }
        observe() {}
        disconnect() {}
    };

    const {dragboard, tab} = paintedDragboard({offsetWidth: 1200});
    assert.equal(dragboard.activeScreenSize.id, 2);

    tab.wrapperElement.offsetWidth = 100; // now matches "Phone" (id 0)
    let applyScreenSizeCalls = 0;
    const original = dragboard.applyScreenSize.bind(dragboard);
    dragboard.applyScreenSize = () => {
        applyScreenSizeCalls++;
        return original();
    };

    observedCallback();

    assert.equal(applyScreenSizeCalls, 1);
    assert.equal(dragboard.activeScreenSize.id, 0);

    delete global.ResizeObserver;
});

test('window resize fallback re-applies the screen size after paint when width changed', () => {
    delete global.ResizeObserver;

    const {dragboard, tab} = paintedDragboard({offsetWidth: 1200});
    assert.equal(dragboard.activeScreenSize.id, 2);

    tab.wrapperElement.offsetWidth = 100;
    let applyScreenSizeCalls = 0;
    const original = dragboard.applyScreenSize.bind(dragboard);
    dragboard.applyScreenSize = () => {
        applyScreenSizeCalls++;
        return original();
    };

    windowListeners.resize.forEach((handler) => handler({type: 'resize'}));

    assert.equal(applyScreenSizeCalls, 1);
});

test('resize handler is a no-op before paint() (grid is still null)', () => {
    delete global.ResizeObserver;
    const {dragboard, tab} = createDragboard({offsetWidth: 1200});

    tab.wrapperElement.offsetWidth = 100;
    // Should not throw even though the grid has not been created yet.
    windowListeners.resize.forEach((handler) => handler({type: 'resize'}));

    assert.equal(dragboard.grid, null);
});

test('resize handler does nothing while the tab is hidden (offsetWidth === 0)', () => {
    delete global.ResizeObserver;
    const {dragboard, tab} = paintedDragboard({offsetWidth: 1200});
    const initialScreenSizeId = dragboard._lastAppliedScreenSizeId;

    tab.wrapperElement.offsetWidth = 0;
    let applyScreenSizeCalls = 0;
    dragboard.applyScreenSize = () => { applyScreenSizeCalls++; };

    windowListeners.resize.forEach((handler) => handler({type: 'resize'}));

    assert.equal(applyScreenSizeCalls, 0);
    assert.equal(dragboard._lastAppliedScreenSizeId, initialScreenSizeId);
});

// ===========================================================================
// screenSizes GETTER
// ===========================================================================

test('screenSizes normalizes missing columns to 12', () => {
    const {dragboard} = createDragboard({
        preferenceValues: {
            screenSizes: [
                {id: 0, name: 'A', moreOrEqual: 0, lessOrEqual: -1},
            ],
        },
    });

    assert.equal(dragboard.screenSizes[0].columns, 12);
});

test('screenSizes preserves an explicit columns value', () => {
    const {dragboard} = createDragboard({
        preferenceValues: {
            screenSizes: [
                {id: 0, name: 'A', moreOrEqual: 0, lessOrEqual: -1, columns: 4},
            ],
        },
    });

    assert.equal(dragboard.screenSizes[0].columns, 4);
});

test('screenSizes normalizes missing rows to the unbounded vertical mode', () => {
    const {dragboard} = createDragboard({
        preferenceValues: {
            screenSizes: [
                {id: 0, name: 'A', moreOrEqual: 0, lessOrEqual: -1, columns: 4},
            ],
        },
    });

    assert.equal(dragboard.screenSizes[0].rows, 0);
});

test('screenSizes preserves a positive fixed row count', () => {
    const {dragboard} = createDragboard({
        preferenceValues: {
            screenSizes: [
                {id: 0, name: 'A', moreOrEqual: 0, lessOrEqual: -1, columns: 4, rows: 6},
            ],
        },
    });

    assert.equal(dragboard.screenSizes[0].rows, 6);
});

test('screenSizes sorts entries by moreOrEqual ascending regardless of input order', () => {
    const {dragboard} = createDragboard({
        preferenceValues: {
            screenSizes: [
                {id: 2, name: 'Desktop', moreOrEqual: 1200, lessOrEqual: -1, columns: 12},
                {id: 0, name: 'Phone', moreOrEqual: 0, lessOrEqual: 767, columns: 1},
                {id: 1, name: 'Tablet', moreOrEqual: 768, lessOrEqual: 1199, columns: 6},
            ],
        },
    });

    assert.deepEqual(dragboard.screenSizes.map((s) => s.id), [0, 1, 2]);
});

test('screenSizes returns an empty array when the preference is empty', () => {
    const {dragboard} = createDragboard({preferenceValues: {screenSizes: []}});

    assert.deepEqual(dragboard.screenSizes, []);
});

// ===========================================================================
// activeScreenSize GETTER
// ===========================================================================

test('activeScreenSize matches tab.wrapperElement.offsetWidth', () => {
    const {dragboard} = createDragboard({offsetWidth: 900});
    assert.equal(dragboard.activeScreenSize.id, 1); // Tablet: 768-1199
});

test('activeScreenSize matches the phone range at small widths', () => {
    const {dragboard} = createDragboard({offsetWidth: 320});
    assert.equal(dragboard.activeScreenSize.id, 0);
});

test('activeScreenSize treats lessOrEqual === -1 as unbounded', () => {
    const {dragboard} = createDragboard({offsetWidth: 5000});
    assert.equal(dragboard.activeScreenSize.id, 2);
});

test('activeScreenSize falls back to window.innerWidth when offsetWidth is 0', () => {
    global.window.innerWidth = 900;
    const {dragboard} = createDragboard({offsetWidth: 0});
    assert.equal(dragboard.activeScreenSize.id, 1);
});

test('activeScreenSize returns the last entry when width matches none (gap in ranges)', () => {
    const {dragboard} = createDragboard({
        offsetWidth: 250,
        preferenceValues: {
            screenSizes: [
                {id: 0, name: 'A', moreOrEqual: 0, lessOrEqual: 100, columns: 2},
                {id: 1, name: 'B', moreOrEqual: 300, lessOrEqual: 400, columns: 8},
            ],
        },
    });

    assert.equal(dragboard.activeScreenSize.id, 1);
});

test('activeScreenSize returns a synthetic default entry when screenSizes is empty', () => {
    const {dragboard} = createDragboard({preferenceValues: {screenSizes: []}});

    assert.deepEqual(dragboard.activeScreenSize, {id: 0, name: '', moreOrEqual: 0, lessOrEqual: -1, columns: 12, rows: 0});
});

test('activeScreenSize honours a forced screen size regardless of width', () => {
    const {dragboard} = createDragboard({offsetWidth: 320});
    dragboard.forcedScreenSizeId = 2;

    assert.equal(dragboard.activeScreenSize.id, 2);
});

test('activeScreenSize ignores a forced id that no longer exists and detects normally', () => {
    const {dragboard} = createDragboard({offsetWidth: 320});
    dragboard.forcedScreenSizeId = 999;

    assert.equal(dragboard.activeScreenSize.id, 0);
});

// ===========================================================================
// setForcedScreenSize / withApplying
// ===========================================================================

test('setForcedScreenSize sets forcedScreenSizeId, resets _lastAppliedScreenSizeId and re-applies', () => {
    const {dragboard} = paintedDragboard({offsetWidth: 1200});
    let applyCalls = 0;
    const original = dragboard.applyScreenSize.bind(dragboard);
    dragboard.applyScreenSize = () => { applyCalls++; return original(); };

    dragboard.setForcedScreenSize(0);

    assert.equal(dragboard.forcedScreenSizeId, 0);
    assert.equal(applyCalls, 1);
    assert.equal(dragboard.activeScreenSize.id, 0);
});

test('setForcedScreenSize(null) returns to automatic detection', () => {
    const {dragboard} = paintedDragboard({offsetWidth: 1200});
    dragboard.setForcedScreenSize(0);
    assert.equal(dragboard.activeScreenSize.id, 0);

    dragboard.setForcedScreenSize(null);
    assert.equal(dragboard.activeScreenSize.id, 2);
});

test('withApplying restores the previous applying flag value even when fn throws', () => {
    const {dragboard} = createDragboard();

    assert.throws(() => {
        dragboard.withApplying(() => {
            assert.equal(dragboard.applying, true);
            throw new Error('boom');
        });
    }, /boom/);

    assert.equal(dragboard.applying, false);
});

test('withApplying nests correctly (inner call does not clear outer applying)', () => {
    const {dragboard} = createDragboard();

    dragboard.withApplying(() => {
        dragboard.withApplying(() => {});
        assert.equal(dragboard.applying, true);
    });
    assert.equal(dragboard.applying, false);
});

// ===========================================================================
// resolveLayout
// ===========================================================================

test('resolveLayout returns the stored layout for the requested screen size unchanged', () => {
    const {dragboard} = createDragboard();
    const model = createWidgetModel({layouts: {2: {x: 1, y: 2, w: 3, h: 4}}});

    const resolved = dragboard.resolveLayout(model, dragboard.screenSizes[2]);

    assert.deepEqual(resolved, {x: 1, y: 2, w: 3, h: 4, minimized: false, titlevisible: true, fulldragboard: false, visible: true});
});

test('resolveLayout scales w/x by the column ratio from a larger screen size, leaving y/h untouched', () => {
    const {dragboard} = createDragboard();
    const model = createWidgetModel({
        layouts: {2: {x: 6, y: 3, w: 4, h: 2}}, // desktop: 12 columns
    });

    const resolved = dragboard.resolveLayout(model, dragboard.screenSizes[1]); // tablet: 6 columns

    // ratio = 6/12 = 0.5; w = round(4*0.5) = 2; x = round(6*0.5) = 3
    assert.deepEqual(resolved, {x: 3, y: 3, w: 2, h: 2, minimized: false, titlevisible: true, fulldragboard: false, visible: true, derived: true});
});

test('resolveLayout marks a layout scaled from another screen size as derived (an ordering hint, not a placement)', () => {
    const {dragboard} = createDragboard();
    const model = createWidgetModel({layouts: {2: {x: 6, y: 3, w: 4, h: 2}}});

    const resolved = dragboard.resolveLayout(model, dragboard.screenSizes[1]);

    assert.equal(resolved.derived, true);
});

test('resolveLayout does NOT mark a stored (non-scaled) layout as derived', () => {
    const {dragboard} = createDragboard();
    const model = createWidgetModel({layouts: {2: {x: 1, y: 2, w: 3, h: 4}}});

    const resolved = dragboard.resolveLayout(model, dragboard.screenSizes[2]);

    assert.equal(resolved.derived, undefined);
});

test('resolveLayout does NOT mark a default (no stored layout anywhere) layout as derived', () => {
    const {dragboard} = createDragboard();
    const model = createWidgetModel({});

    const resolved = dragboard.resolveLayout(model, dragboard.screenSizes[2]);

    assert.equal(resolved.derived, undefined);
});

test('resolveLayout clamps the scaled x so the widget still fits within the target columns', () => {
    const {dragboard} = createDragboard();
    const model = createWidgetModel({
        layouts: {1: {x: 5, y: 2, w: 4, h: 3}}, // tablet: 6 columns
    });

    const resolved = dragboard.resolveLayout(model, dragboard.screenSizes[0]); // phone: 1 column

    // ratio = 1/6; w = clamp(round(4/6)=1, 1, 1) = 1
    // x = clamp(round(5/6)=1, 0, max(0, 1-1)) = clamp(1, 0, 0) = 0
    assert.equal(resolved.w, 1);
    assert.equal(resolved.x, 0);
    assert.equal(resolved.y, 2);
    assert.equal(resolved.h, 3);
    assert.equal(resolved.derived, true);
});

test('resolveLayout keeps x null when the source layout has no x, but still scales w', () => {
    const {dragboard} = createDragboard();
    const model = createWidgetModel({
        layouts: {2: {x: null, y: null, w: 6, h: 4, minimized: true, titlevisible: false}},
    });

    const resolved = dragboard.resolveLayout(model, dragboard.screenSizes[1]);

    assert.equal(resolved.x, null);
    assert.equal(resolved.y, null);
    assert.equal(resolved.w, 3); // round(6 * 6/12)
    assert.equal(resolved.h, 4);
    assert.equal(resolved.minimized, true);
    assert.equal(resolved.titlevisible, false);
});

test('resolveLayout prefers the nearest LARGER screen size with a stored layout', () => {
    const {dragboard} = createDragboard();
    const model = createWidgetModel({
        layouts: {
            0: {x: null, y: 0, w: 1, h: 5},
            2: {x: 8, y: 1, w: 2, h: 2},
        },
    });

    const resolved = dragboard.resolveLayout(model, dragboard.screenSizes[1]); // tablet, missing

    // Should come from desktop (id 2), scaled: ratio 6/12=0.5, w=1, x=round(8*0.5)=4
    assert.equal(resolved.w, 1);
    assert.equal(resolved.x, 4);
    assert.equal(resolved.y, 1);
    assert.equal(resolved.h, 2);
});

test('resolveLayout falls back to the nearest SMALLER screen size when no larger one is stored', () => {
    const {dragboard} = createDragboard();
    const model = createWidgetModel({
        layouts: {0: {x: null, y: 2, w: 1, h: 3}},
    });

    const resolved = dragboard.resolveLayout(model, dragboard.screenSizes[2]); // desktop, missing

    // ratio 12/1 = 12; w = clamp(round(1*12), 1, 12) = 12
    assert.equal(resolved.w, 12);
    assert.equal(resolved.x, null);
    assert.equal(resolved.y, 2);
    assert.equal(resolved.h, 3);
});

test('resolveLayout scales and clamps y/h between fixed-row screen sizes', () => {
    const screenSizes = [
        {id: 0, name: 'Small', moreOrEqual: 0, lessOrEqual: 799, columns: 4, rows: 4},
        {id: 1, name: 'Large', moreOrEqual: 800, lessOrEqual: -1, columns: 8, rows: 8},
    ];
    const {dragboard} = createDragboard({offsetWidth: 400, preferenceValues: {screenSizes}});
    const model = createWidgetModel({layouts: {1: {x: 4, y: 4, w: 4, h: 4}}});

    const resolved = dragboard.resolveLayout(model, dragboard.screenSizes[0]);

    assert.equal(resolved.y, 2);
    assert.equal(resolved.h, 2);
});

test('resolveLayout uses default_layout_for when the widget has no stored layout at all', () => {
    const {dragboard} = createDragboard({preferenceValues: {cellheight: 40}});
    const model = createWidgetModel({});

    const resolved = dragboard.resolveLayout(model, dragboard.screenSizes[2]); // desktop, 12 columns

    assert.deepEqual(resolved, {
        x: null,
        y: null,
        w: 4,  // min(12, max(1, round(12/3))) = 4
        h: 8,  // max(1, round(300/40)) = 8
        minimized: false,
        titlevisible: true,
        fulldragboard: false,
        visible: true,
    });
});

test('default_layout_for width never exceeds the target columns for narrow screen sizes', () => {
    const {dragboard} = createDragboard();
    const model = createWidgetModel({});

    const resolved = dragboard.resolveLayout(model, dragboard.screenSizes[0]); // phone, 1 column

    assert.equal(resolved.w, 1);
});

// ===========================================================================
// hiddenWidgets
// ===========================================================================

test('hiddenWidgets returns only views whose resolved layout is not visible', () => {
    const {dragboard} = createDragboard({offsetWidth: 1200});
    const visibleModel = createWidgetModel({id: 'v', layouts: {2: {visible: true}}});
    const hiddenModel = createWidgetModel({id: 'h', layouts: {2: {visible: false}}});
    const visibleView = createWidgetView(visibleModel);
    const hiddenView = createWidgetView(hiddenModel);

    dragboard.views.push(visibleView, hiddenView);

    assert.deepEqual(dragboard.hiddenWidgets, [hiddenView]);
});

test('hiddenWidgets is empty when no widget is hidden', () => {
    const {dragboard} = createDragboard();
    const model = createWidgetModel({layouts: {2: {visible: true}}});
    dragboard.views.push(createWidgetView(model));

    assert.deepEqual(dragboard.hiddenWidgets, []);
});

// ===========================================================================
// paint()
// ===========================================================================

test('paint() initializes GridStack with the expected options and target element', () => {
    const built = createDragboard({offsetWidth: 1200, preferenceValues: {cellheight: 50, margin: 8}});
    const dragboard = built.dragboard;
    dragboard.paint();

    assert.equal(global.GridStack.instances.length, 1);
    const instance = global.GridStack.instances[0];
    assert.equal(instance.el, dragboard.gridElement);
    assert.deepEqual(instance.opts, {
        column: 12,
        cellHeight: 50,
        margin: 8,
        float: false,
        animate: true,
        handle: '.wc-widget-heading',
        resizable: {handles: 'e, se, s, sw, w'},
        alwaysShowResizeHandle: 'mobile',
        staticGrid: false,
        row: 0,
        minRow: 0,
        maxRow: 0,
    });
});

test('paint() creates a fixed grid whose rows fill the available height', () => {
    const screenSizes = [
        {id: 0, name: 'Fixed', moreOrEqual: 0, lessOrEqual: -1, columns: 4, rows: 6},
    ];
    const {dragboard} = createDragboard({
        offsetWidth: 800,
        offsetHeight: 600,
        preferenceValues: {cellheight: 40, screenSizes},
    });

    dragboard.paint();

    assert.equal(dragboard.grid.opts.row, 6);
    assert.equal(dragboard.grid.opts.minRow, 6);
    assert.equal(dragboard.grid.opts.maxRow, 6);
    assert.equal(dragboard.grid.getCellHeight(true), 100);
    assert.equal(dragboard.grid.opts.float, true);
    assert.equal(dragboard.grid.engine.float, true);
    assert.equal(dragboard.gridElement.classList.contains('wc-dragboard-fixed-rows'), true);
});

test('a height-only resize recalculates fixed-row cell height', () => {
    let observedCallback = null;
    global.ResizeObserver = class {
        constructor(callback) { observedCallback = callback; }
        observe() {}
        disconnect() {}
    };
    const screenSizes = [
        {id: 0, name: 'Fixed', moreOrEqual: 0, lessOrEqual: -1, columns: 4, rows: 5},
    ];
    const {dragboard, tab} = paintedDragboard({
        offsetWidth: 800,
        offsetHeight: 500,
        preferenceValues: {screenSizes},
    });

    tab.wrapperElement.offsetHeight = 750;
    observedCallback();

    assert.equal(dragboard.grid.getCellHeight(true), 150);
    delete global.ResizeObserver;
});

test('switching from fixed rows to columns-only removes the row limit', () => {
    const screenSizes = [
        {id: 0, name: 'Fluid', moreOrEqual: 0, lessOrEqual: 499, columns: 2, rows: 0},
        {id: 1, name: 'Fixed', moreOrEqual: 500, lessOrEqual: -1, columns: 4, rows: 5},
    ];
    const {dragboard, tab} = paintedDragboard({
        offsetWidth: 800,
        offsetHeight: 500,
        preferenceValues: {cellheight: 40, screenSizes},
    });
    assert.equal(dragboard.grid.engine.maxRow, 5);

    tab.wrapperElement.offsetWidth = 400;
    dragboard.applyScreenSize();

    assert.equal(dragboard.grid.engine.maxRow, 0);
    assert.equal(dragboard.grid.getCellHeight(true), 40);
    assert.equal(dragboard.grid.opts.float, false);
    assert.equal(dragboard.grid.engine.float, false);
    assert.equal(dragboard.gridElement.classList.contains('wc-dragboard-fixed-rows'), false);
});

test('paint() passes tab.workspace.model.restricted as staticGrid', () => {
    const {dragboard} = createDragboard({workspaceOptions: {model: {id: 'w', restricted: true}}});
    dragboard.paint();

    assert.equal(dragboard.grid.opts.staticGrid, true);
});

test('paint() is idempotent: calling it twice only creates one GridStack instance', () => {
    const {dragboard} = createDragboard();

    dragboard.paint();
    dragboard.paint();

    assert.equal(dragboard.painted, true);
    assert.equal(global.GridStack.instances.length, 1);
});

test('paint() registers change/dragstop/resizestop handlers exactly once', () => {
    const {dragboard} = paintedDragboard();

    assert.equal(dragboard.grid.listeners.change.length, 1);
    assert.equal(dragboard.grid.listeners.dragstop.length, 1);
    assert.equal(dragboard.grid.listeners.resizestop.length, 1);
});

test('paint() disables GridStack internal DOM re-sorting via _sortDom', () => {
    const {dragboard} = paintedDragboard();

    assert.equal(typeof dragboard.grid._sortDom, 'function');
    assert.equal(dragboard.grid._sortDom(), dragboard.grid);
});

test('paint() applies the current screen size immediately (grid.column is called)', () => {
    const {dragboard} = paintedDragboard({offsetWidth: 1200});

    assert.ok(dragboard.grid.calls.some((c) => c.name === 'column' && c.args[0] === 12));
    assert.equal(dragboard._lastAppliedScreenSizeId, 2);
});

// ===========================================================================
// addWidget / refreshWidget / removeWidget / moveWidgetToTab
// ===========================================================================

test('addWidget appends the wrapper element to the grid container and registers the view', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({layouts: {2: {x: 0, y: 0, w: 2, h: 2}}});
    const view = createWidgetView(model);

    dragboard.addWidget(view);

    assert.ok(dragboard.gridElement.childNodes.includes(view.wrapperElement));
    assert.ok(dragboard.views.includes(view));
    assert.equal(view.tab, dragboard.tab);
});

test('addWidget does not re-append the element if it is already a child', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({layouts: {2: {x: 0, y: 0, w: 2, h: 2}}});
    const view = createWidgetView(model);

    dragboard.addWidget(view);
    const childCountBefore = dragboard.gridElement.childNodes.length;
    dragboard.addWidget(view);

    assert.equal(dragboard.gridElement.childNodes.length, childCountBefore);
    assert.equal(dragboard.views.filter((v) => v === view).length, 1);
});

test('addWidget before paint() just registers the view; placement happens once painted', () => {
    const {dragboard} = createDragboard();
    const model = createWidgetModel({layouts: {2: {x: 0, y: 0, w: 2, h: 2}}});
    const view = createWidgetView(model);

    dragboard.addWidget(view);

    assert.ok(dragboard.views.includes(view));
    assert.equal(view.wrapperElement.gridstackNode, undefined);

    dragboard.paint();

    assert.ok(view.wrapperElement.gridstackNode != null);
});

test('refreshWidget places a single widget using its resolved layout', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({layouts: {2: {x: 3, y: 1, w: 2, h: 2}}});
    const view = createWidgetView(model);
    dragboard.views.push(view);
    dragboard.gridElement.appendChild(view.wrapperElement);

    dragboard.refreshWidget(view);

    assert.equal(view.wrapperElement.gridstackNode.x, 3);
    assert.equal(view.wrapperElement.gridstackNode.y, 1);
});

test('refreshWidget is a no-op when the grid has not been painted', () => {
    const {dragboard} = createDragboard();
    const model = createWidgetModel({layouts: {2: {x: 3, y: 1, w: 2, h: 2}}});
    const view = createWidgetView(model);
    dragboard.views.push(view);

    dragboard.refreshWidget(view); // should not throw

    assert.equal(view.wrapperElement.gridstackNode, undefined);
});

test('refreshWidget is a no-op when the view is not registered', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({layouts: {2: {x: 3, y: 1, w: 2, h: 2}}});
    const view = createWidgetView(model);

    dragboard.refreshWidget(view); // never pushed to dragboard.views

    assert.equal(view.wrapperElement.gridstackNode, undefined);
});

test('removeWidget removes the view from the list and the grid', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({layouts: {2: {x: 0, y: 0, w: 2, h: 2}}});
    const view = createWidgetView(model);
    dragboard.addWidget(view);

    dragboard.removeWidget(view);

    assert.ok(!dragboard.views.includes(view));
    const lastRemoveCall = dragboard.grid.calls.filter((c) => c.name === 'removeWidget').pop();
    assert.deepEqual(lastRemoveCall.args, [view.wrapperElement, true, false]);
});

test('removeWidget is safe to call for a view that was never added', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({});
    const view = createWidgetView(model);

    dragboard.removeWidget(view); // should not throw

    assert.ok(!dragboard.views.includes(view));
});

test('moveWidgetToTab removes the view from this grid (keeping the DOM element) and calls model.changeTab', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({layouts: {2: {x: 0, y: 0, w: 2, h: 2}}});
    let changeTabArg = null;
    model.changeTab = (targetModel) => {
        changeTabArg = targetModel;
        return Promise.resolve('moved');
    };
    const view = createWidgetView(model);
    dragboard.addWidget(view);

    const targetTabModel = {id: 'target-tab'};
    const targetTabView = {model: targetTabModel};

    const result = dragboard.moveWidgetToTab(view, targetTabView);

    assert.ok(!dragboard.views.includes(view));
    assert.ok(dragboard.gridElement.childNodes.includes(view.wrapperElement)); // DOM element kept
    assert.equal(changeTabArg, targetTabModel);

    return result.then((value) => {
        assert.equal(value, 'moved');
    });
});

test('moveWidgetToTab removes the DOM element from the grid without destroying it (removeDOM=false)', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({layouts: {2: {x: 0, y: 0, w: 2, h: 2}}});
    const view = createWidgetView(model);
    dragboard.addWidget(view);

    dragboard.moveWidgetToTab(view, {model: {id: 'target'}});

    const lastRemoveCall = dragboard.grid.calls.filter((c) => c.name === 'removeWidget').pop();
    assert.deepEqual(lastRemoveCall.args, [view.wrapperElement, false, false]);
});

// ===========================================================================
// applyScreenSize() / place_view (via applyScreenSize / addWidget)
// ===========================================================================

test('applyScreenSize is a no-op before paint()', () => {
    const {dragboard} = createDragboard();
    dragboard.applyScreenSize(); // should not throw
    assert.equal(dragboard.grid, null);
});

test('applyScreenSize sets the grid column count to the active screen size columns', () => {
    const {dragboard} = paintedDragboard({offsetWidth: 900}); // tablet: 6 columns
    dragboard.grid.calls.length = 0;

    dragboard.applyScreenSize();

    const columnCall = dragboard.grid.calls.find((c) => c.name === 'column');
    assert.deepEqual(columnCall.args, [6, 'none']);
});

test('applyScreenSize places a brand-new widget with explicit coordinates via makeWidget', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({id: 'w1', layouts: {2: {x: 2, y: 1, w: 3, h: 2}}});
    const view = createWidgetView(model);
    dragboard.views.push(view);
    dragboard.gridElement.appendChild(view.wrapperElement);

    dragboard.applyScreenSize();

    const makeCall = dragboard.grid.calls.find((c) => c.name === 'makeWidget');
    assert.ok(makeCall != null);
    assert.equal(makeCall.args[0], view.wrapperElement);
    assert.deepEqual(makeCall.args[1], {id: 'w1', autoPosition: false, w: 3, h: 2, noMove: false, noResize: false, x: 2, y: 1});
    assert.equal(view.wrapperElement.hidden, false);
    assert.deepEqual(view.applyLayoutCalls[view.applyLayoutCalls.length - 1], {x: 2, y: 1, w: 3, h: 2, minimized: false, titlevisible: true, fulldragboard: false, visible: true});
});

test('applyScreenSize auto-positions a brand-new widget with null coordinates', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({id: 'w1', layouts: {2: {x: null, y: null, w: 2, h: 2}}});
    const view = createWidgetView(model);
    dragboard.views.push(view);
    dragboard.gridElement.appendChild(view.wrapperElement);

    dragboard.applyScreenSize();

    const makeCall = dragboard.grid.calls.find((c) => c.name === 'makeWidget');
    assert.deepEqual(makeCall.args[1], {id: 'w1', autoPosition: true, w: 2, h: 2, noMove: false, noResize: false});
    assert.ok(view.wrapperElement.gridstackNode.x != null);
    assert.ok(view.wrapperElement.gridstackNode.y != null);
});

test('refreshWidget updates an existing node in-place when coordinates stay explicit', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({id: 'w1', layouts: {2: {x: 1, y: 1, w: 2, h: 2}}});
    const view = createWidgetView(model);
    dragboard.addWidget(view);
    dragboard.grid.calls.length = 0;

    // Unlike applyScreenSize, which re-places every widget from scratch,
    // refreshWidget touches a single one and leaves its node in place.
    dragboard.refreshWidget(view);

    assert.equal(dragboard.grid.calls.filter((c) => c.name === 'makeWidget').length, 0);
    const updateCall = dragboard.grid.calls.find((c) => c.name === 'update');
    assert.ok(updateCall != null);
    assert.deepEqual(updateCall.args[1], {w: 2, h: 2, noMove: false, noResize: false, x: 1, y: 1});
});

test('applyScreenSize re-adds a node (remove + makeWidget) when it becomes auto-positioned', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({id: 'w1', layouts: {2: {x: 1, y: 1, w: 2, h: 2}}});
    const view = createWidgetView(model);
    dragboard.addWidget(view);
    assert.ok(view.wrapperElement.gridstackNode != null);

    model.setLayout('2', {x: null, y: null});
    dragboard.grid.calls.length = 0;

    dragboard.applyScreenSize();

    const names = dragboard.grid.calls.map((c) => c.name);
    const removeIndex = names.indexOf('removeWidget');
    const makeIndex = names.indexOf('makeWidget');
    assert.ok(removeIndex !== -1 && makeIndex !== -1 && removeIndex < makeIndex);
    const removeCall = dragboard.grid.calls[removeIndex];
    assert.deepEqual(removeCall.args, [view.wrapperElement, false, false]);
    const makeCall = dragboard.grid.calls[makeIndex];
    assert.deepEqual(makeCall.args[1], {id: 'w1', autoPosition: true, w: 2, h: 2, noMove: false, noResize: false});
});

test('applyScreenSize auto-positions a brand-new widget whose layout was derived (scaled) from another screen size', () => {
    const {dragboard} = paintedDragboard(); // active screen size: Desktop (id 2)
    // Only the Phone (id 0) layout is stored; the Desktop layout must be derived from it.
    const model = createWidgetModel({id: 'w1', layouts: {0: {x: 0, y: 0, w: 1, h: 2}}});
    const view = createWidgetView(model);
    dragboard.views.push(view);
    dragboard.gridElement.appendChild(view.wrapperElement);

    const resolved = dragboard.resolveLayout(model, dragboard.activeScreenSize);
    assert.equal(resolved.derived, true); // sanity check on the fixture

    dragboard.applyScreenSize();

    const makeCall = dragboard.grid.calls.find((c) => c.name === 'makeWidget');
    assert.ok(makeCall != null);
    // No x/y keys: the derived layout's scaled coordinates are only an
    // ordering hint, GridStack must still auto-place the widget.
    assert.deepEqual(makeCall.args[1], {id: 'w1', autoPosition: true, w: resolved.w, h: resolved.h, noMove: false, noResize: false});
    assert.equal('x' in makeCall.args[1], false);
    assert.equal('y' in makeCall.args[1], false);
});

test('applyScreenSize re-adds (remove + makeWidget) an existing node once its layout becomes derived', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({
        id: 'w1',
        layouts: {
            0: {x: 0, y: 0, w: 1, h: 2}, // Phone layout, used as the derivation source
            2: {x: 1, y: 1, w: 2, h: 2}, // Desktop layout, explicit for now
        },
    });
    const view = createWidgetView(model);
    dragboard.addWidget(view); // placed explicitly (stored id 2 layout)
    assert.ok(view.wrapperElement.gridstackNode != null);
    assert.equal(view.wrapperElement.gridstackNode.x, 1);

    model.removeLayout('2'); // Desktop layout now has to be derived from Phone
    dragboard.grid.calls.length = 0;

    dragboard.applyScreenSize();

    const names = dragboard.grid.calls.map((c) => c.name);
    const removeIndex = names.indexOf('removeWidget');
    const makeIndex = names.indexOf('makeWidget');
    assert.ok(removeIndex !== -1 && makeIndex !== -1 && removeIndex < makeIndex);
    assert.equal(dragboard.grid.calls[makeIndex].args[1].autoPosition, true);
    assert.equal('x' in dragboard.grid.calls[makeIndex].args[1], false);
});

test('applyScreenSize hides a widget whose resolved layout is not visible and removes it from the grid', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({id: 'w1', layouts: {2: {x: 1, y: 1, w: 2, h: 2}}});
    const view = createWidgetView(model);
    dragboard.addWidget(view);
    assert.ok(view.wrapperElement.gridstackNode != null);

    model.setLayout('2', {visible: false});
    dragboard.grid.calls.length = 0;

    dragboard.applyScreenSize();

    assert.equal(view.wrapperElement.hidden, true);
    assert.equal(view.wrapperElement.gridstackNode, undefined);
    const removeCall = dragboard.grid.calls.find((c) => c.name === 'removeWidget');
    assert.deepEqual(removeCall.args, [view.wrapperElement, false, false]);
    assert.equal(dragboard.grid.calls.some((c) => c.name === 'makeWidget' || c.name === 'update'), false);
});

test('applyScreenSize hides a never-added widget without calling removeWidget', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({id: 'w1', layouts: {2: {x: 1, y: 1, w: 2, h: 2, visible: false}}});
    const view = createWidgetView(model);
    dragboard.views.push(view);
    dragboard.gridElement.appendChild(view.wrapperElement);

    dragboard.applyScreenSize();

    assert.equal(view.wrapperElement.hidden, true);
    assert.equal(dragboard.grid.calls.some((c) => c.name === 'removeWidget'), false);
});

test('applyScreenSize orders placement by (y, x, id) with null treated as last', () => {
    const {dragboard} = paintedDragboard();
    const modelC = createWidgetModel({id: 'c', layouts: {2: {x: 0, y: 1, w: 1, h: 1}}});
    const modelB = createWidgetModel({id: 'b', layouts: {2: {x: 5, y: 1, w: 1, h: 1}}});
    const modelA = createWidgetModel({id: 'a', layouts: {2: {x: 0, y: 2, w: 1, h: 1}}});
    const modelD = createWidgetModel({id: 'd', layouts: {2: {x: null, y: null, w: 1, h: 1}}});

    [modelC, modelB, modelA, modelD].forEach((model) => {
        const view = createWidgetView(model);
        dragboard.views.push(view);
        dragboard.gridElement.appendChild(view.wrapperElement);
    });

    dragboard.applyScreenSize();

    const order = dragboard.grid.calls
        .filter((c) => c.name === 'makeWidget')
        .map((c) => c.args[1].id);

    assert.deepEqual(order, ['c', 'b', 'a', 'd']);
});

test('applyScreenSize passes noMove/noResize based on move/resize permissions', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({
        id: 'w1',
        layouts: {2: {x: 0, y: 0, w: 2, h: 2}},
        permissions: {move: false, resize: true},
    });
    const view = createWidgetView(model);
    dragboard.views.push(view);
    dragboard.gridElement.appendChild(view.wrapperElement);

    dragboard.applyScreenSize();

    assert.equal(view.wrapperElement.gridstackNode.noMove, true);
    assert.equal(view.wrapperElement.gridstackNode.noResize, false);
});

test('applyScreenSize forces noMove/noResize for full-dragboard widgets', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({
        id: 'w1',
        layouts: {2: {x: 0, y: 0, w: 2, h: 2, fulldragboard: true}},
    });
    const view = createWidgetView(model);
    dragboard.views.push(view);
    dragboard.gridElement.appendChild(view.wrapperElement);

    dragboard.applyScreenSize();

    assert.equal(view.wrapperElement.gridstackNode.noMove, true);
    assert.equal(view.wrapperElement.gridstackNode.noResize, true);
});

test('applyScreenSize forces noResize (but not noMove) for minimized widgets', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({
        id: 'w1',
        layouts: {2: {x: 0, y: 0, w: 2, h: 2, minimized: true}},
    });
    const view = createWidgetView(model);
    dragboard.views.push(view);
    dragboard.gridElement.appendChild(view.wrapperElement);

    dragboard.applyScreenSize();

    assert.equal(view.wrapperElement.gridstackNode.noMove, false);
    assert.equal(view.wrapperElement.gridstackNode.noResize, true);
});

test('applyScreenSize uses the "viewer" role when the workspace is not editing', () => {
    const {dragboard} = paintedDragboard({workspaceOptions: {editing: false}});
    let requestedRole = null;
    const model = createWidgetModel({
        id: 'w1',
        layouts: {2: {x: 0, y: 0, w: 2, h: 2}},
        isAllowed: (permission, role) => { requestedRole = role; return true; },
    });
    const view = createWidgetView(model);
    dragboard.views.push(view);
    dragboard.gridElement.appendChild(view.wrapperElement);

    dragboard.applyScreenSize();

    assert.equal(requestedRole, 'viewer');
});

test('applyScreenSize uses the "editor" role when the workspace is editing', () => {
    const {dragboard} = paintedDragboard({workspaceOptions: {editing: true}});
    let requestedRole = null;
    const model = createWidgetModel({
        id: 'w1',
        layouts: {2: {x: 0, y: 0, w: 2, h: 2}},
        isAllowed: (permission, role) => { requestedRole = role; return true; },
    });
    const view = createWidgetView(model);
    dragboard.views.push(view);
    dragboard.gridElement.appendChild(view.wrapperElement);

    dragboard.applyScreenSize();

    assert.equal(requestedRole, 'editor');
});

test('applyScreenSize records _lastAppliedScreenSizeId', () => {
    const {dragboard} = paintedDragboard({offsetWidth: 320});

    assert.equal(dragboard._lastAppliedScreenSizeId, 0);
});

test('applyScreenSize suppresses persistence via the applying flag even when editing', () => {
    const {dragboard} = paintedDragboard({workspaceOptions: {editing: true}});
    const model = createWidgetModel({id: 'w1', layouts: {2: {x: 0, y: 0, w: 2, h: 2}}});
    const view = createWidgetView(model);
    dragboard.views.push(view);
    dragboard.gridElement.appendChild(view.wrapperElement);

    let persistCalls = 0;
    dragboard.persist = () => { persistCalls++; return Promise.resolve(); };

    dragboard.applyScreenSize();

    assert.equal(persistCalls, 0);
    assert.equal(dragboard._persistTimeout, null);
});

// ===========================================================================
// GridStack change / dragstop / resizestop -> debounced persist
// ===========================================================================

test('grid "change" event syncs every view from its node when not applying', () => {
    const {dragboard} = paintedDragboard({workspaceOptions: {editing: false}});
    const model = createWidgetModel({id: 'w1', layouts: {2: {x: 0, y: 0, w: 2, h: 2}}});
    const view = createWidgetView(model);
    dragboard.addWidget(view);

    dragboard.grid.trigger('change', [view.wrapperElement.gridstackNode]);

    assert.equal(view.syncCalls, 1);
});

test('grid events do nothing while dragboard.applying is true', () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({id: 'w1', layouts: {2: {x: 0, y: 0, w: 2, h: 2}}});
    const view = createWidgetView(model);
    dragboard.addWidget(view);

    dragboard.applying = true;
    dragboard.grid.trigger('change', []);

    assert.equal(view.syncCalls, 0);
    dragboard.applying = false;
});

test('grid "change" event does not schedule a persist in view mode (not editing)', () => {
    const {dragboard} = paintedDragboard({workspaceOptions: {editing: false}});
    const model = createWidgetModel({id: 'w1', layouts: {2: {x: 0, y: 0, w: 2, h: 2}}});
    const view = createWidgetView(model);
    dragboard.addWidget(view);

    dragboard.grid.trigger('change', []);

    assert.equal(dragboard._persistTimeout, null);
});

test('grid "change"/"dragstop"/"resizestop" schedule a single debounced persist while editing', async () => {
    const {dragboard} = paintedDragboard({workspaceOptions: {editing: true}});
    const model = createWidgetModel({id: 'w1', layouts: {2: {x: 0, y: 0, w: 2, h: 2}}});
    const view = createWidgetView(model);
    dragboard.addWidget(view);

    let persistCalls = 0;
    dragboard.persist = () => { persistCalls++; return Promise.resolve(); };

    dragboard.grid.trigger('change', []);
    dragboard.grid.trigger('dragstop', view.wrapperElement);
    dragboard.grid.trigger('resizestop', view.wrapperElement);

    assert.equal(persistCalls, 0); // debounced, not yet flushed

    await wait(10);

    assert.equal(persistCalls, 1);
});

test('on_grid_event syncs the layout coordinates reported by the mocked node', () => {
    const {dragboard} = paintedDragboard({workspaceOptions: {editing: false}});
    const model = createWidgetModel({id: 'w1', layouts: {2: {x: 0, y: 0, w: 2, h: 2}}});
    const view = createWidgetView(model);
    dragboard.addWidget(view);

    view.wrapperElement.gridstackNode.x = 5;
    view.wrapperElement.gridstackNode.y = 6;
    view.wrapperElement.gridstackNode.w = 3;
    view.wrapperElement.gridstackNode.h = 4;

    dragboard.grid.trigger('change', [view.wrapperElement.gridstackNode]);

    assert.equal(view.layout.x, 5);
    assert.equal(view.layout.y, 6);
    assert.equal(view.layout.w, 3);
    assert.equal(view.layout.h, 4);
});

// ===========================================================================
// setEditing
// ===========================================================================

test('setEditing refreshes every registered view\'s grid permissions', () => {
    const {dragboard} = paintedDragboard();
    const view1 = createWidgetView(createWidgetModel({id: 'v1'}));
    const view2 = createWidgetView(createWidgetModel({id: 'v2'}));
    dragboard.views.push(view1, view2);

    dragboard.setEditing(true);

    assert.equal(view1.updateGridPermissionsCalls, 1);
    assert.equal(view2.updateGridPermissionsCalls, 1);
});

test('workspace "editmode" event triggers setEditing automatically', () => {
    const {dragboard, tab} = paintedDragboard();
    let setEditingArg = 'unset';
    dragboard.setEditing = (editing) => { setEditingArg = editing; };

    tab.workspace._trigger('editmode', false);

    assert.equal(setEditingArg, false);
});

// ===========================================================================
// Preferences post-commit
// ===========================================================================

test('post-commit cellheight change updates dragboard.cellheight and calls grid.cellHeight', () => {
    const {dragboard, tab} = paintedDragboard({preferenceValues: {cellheight: 40}});

    tab.model.preferences._values.cellheight = 60;
    tab.model.preferences._trigger('post-commit', {cellheight: 60});

    assert.equal(dragboard.cellheight, 60);
    const call = dragboard.grid.calls.find((c) => c.name === 'cellHeight' && c.args[0] === 60);
    assert.ok(call != null);
});

test('post-commit cellheight change before paint() only updates the local value', () => {
    const {dragboard, tab} = createDragboard({preferenceValues: {cellheight: 40}});

    tab.model.preferences._trigger('post-commit', {cellheight: 60});

    assert.equal(dragboard.cellheight, 60);
    assert.equal(dragboard.grid, null);
});

test('post-commit margin change updates the main grid and painted dock grids', () => {
    const {dragboard, tab} = paintedDragboard({preferenceValues: {margin: 5}});
    const view = createWidgetView(createWidgetModel({
        id: 'docked',
        layouts: {'2': {x: 0, y: 0, w: 4, h: 4, dock: 'left'}}
    }), {tab});
    dragboard.addWidget(view);

    tab.model.preferences._values.margin = 20;
    tab.model.preferences._trigger('post-commit', {margin: 20});

    assert.equal(dragboard.margin, 20);
    const call = dragboard.grid.calls.find((c) => c.name === 'margin' && c.args[0] === 20);
    assert.ok(call != null);
    const dockCall = dragboard.leftDock.grid.calls.find((c) => c.name === 'margin' && c.args[0] === 20);
    assert.ok(dockCall != null);
    assert.equal(view.wrapperElement.style.getPropertyValue('--wc-dock-margin-left'), '20px');
});

test('post-commit with unrelated keys does not touch cellheight/margin/screenSizes handling', () => {
    const {dragboard, tab} = paintedDragboard();
    const originalCellheight = dragboard.cellheight;
    let applyScreenSizeCalls = 0;
    dragboard.applyScreenSize = () => { applyScreenSizeCalls++; };

    tab.model.preferences._trigger('post-commit', {unrelated: true});

    assert.equal(dragboard.cellheight, originalCellheight);
    assert.equal(applyScreenSizeCalls, 0);
});

test('post-commit screenSizes change deletes stale layouts (batched into one PUT) then re-applies', async () => {
    const {dragboard, tab} = paintedDragboard();
    const model = createWidgetModel({
        id: 'w1',
        layouts: {
            0: {x: 0, y: 0, w: 1, h: 1},
            1: {x: 0, y: 0, w: 1, h: 1},
            2: {x: 0, y: 0, w: 1, h: 1},
        },
    });
    const view = createWidgetView(model);
    dragboard.addWidget(view);

    const requests = [];
    Wirecloud.io.makeRequest = (url, options) => {
        requests.push({url, options});
        return Promise.resolve({status: 204});
    };

    let applyScreenSizeCalls = 0;
    const originalApply = dragboard.applyScreenSize.bind(dragboard);
    dragboard.applyScreenSize = () => { applyScreenSizeCalls++; return originalApply(); };

    // Remove "Tablet" (id 1) from the screen sizes list.
    tab.model.preferences._values.screenSizes = [
        {id: 0, name: 'Phone', moreOrEqual: 0, lessOrEqual: 767, columns: 1},
        {id: 2, name: 'Desktop', moreOrEqual: 1200, lessOrEqual: -1, columns: 12},
    ];
    tab.model.preferences._trigger('post-commit', {screenSizes: tab.model.preferences._values.screenSizes});

    assert.deepEqual(model.removeLayoutCalls, [{id: '1', persist: false}]);
    assert.equal(requests.length, 1);
    assert.equal(requests[0].options.method, 'PUT');
    assert.deepEqual(JSON.parse(requests[0].options.postBody), [{id: 'w1', layouts: {'1': null}}]);

    await wait(10);
    assert.equal(applyScreenSizeCalls, 1);
});

test('post-commit screenSizes change with no stale layouts sends no request but still re-applies', () => {
    const {dragboard, tab} = paintedDragboard();
    const model = createWidgetModel({id: 'w1', layouts: {2: {x: 0, y: 0, w: 1, h: 1}}});
    const view = createWidgetView(model);
    dragboard.addWidget(view);

    let requestCount = 0;
    Wirecloud.io.makeRequest = () => { requestCount++; return Promise.resolve({status: 204}); };

    let applyScreenSizeCalls = 0;
    const originalApply = dragboard.applyScreenSize.bind(dragboard);
    dragboard.applyScreenSize = () => { applyScreenSizeCalls++; return originalApply(); };

    tab.model.preferences._trigger('post-commit', {screenSizes: tab.model.preferences._values.screenSizes});

    assert.equal(requestCount, 0);
    assert.equal(applyScreenSizeCalls, 1);
});

test('post-commit screenSizes change skips volatile widgets entirely', () => {
    const {dragboard, tab} = paintedDragboard();
    const model = createWidgetModel({id: 'w1', volatile: true, layouts: {1: {x: 0, y: 0, w: 1, h: 1}}});
    const view = createWidgetView(model);
    dragboard.views.push(view);
    dragboard.gridElement.appendChild(view.wrapperElement);

    let requestCount = 0;
    Wirecloud.io.makeRequest = () => { requestCount++; return Promise.resolve({status: 204}); };

    tab.model.preferences._values.screenSizes = [
        {id: 0, name: 'Phone', moreOrEqual: 0, lessOrEqual: 767, columns: 1},
        {id: 2, name: 'Desktop', moreOrEqual: 1200, lessOrEqual: -1, columns: 12},
    ];
    tab.model.preferences._trigger('post-commit', {screenSizes: tab.model.preferences._values.screenSizes});

    assert.deepEqual(model.removeLayoutCalls, []);
    assert.equal(requestCount, 0);
});

test('post-commit screenSizes change still re-applies even if the cleanup request fails', async () => {
    const {dragboard, tab} = paintedDragboard();
    const model = createWidgetModel({
        id: 'w1',
        layouts: {1: {x: 0, y: 0, w: 1, h: 1}, 2: {x: 0, y: 0, w: 1, h: 1}},
    });
    const view = createWidgetView(model);
    dragboard.addWidget(view);

    Wirecloud.io.makeRequest = () => Promise.reject(new Error('network down'));

    let applyScreenSizeCalls = 0;
    const originalApply = dragboard.applyScreenSize.bind(dragboard);
    dragboard.applyScreenSize = () => { applyScreenSizeCalls++; return originalApply(); };

    tab.model.preferences._values.screenSizes = [
        {id: 0, name: 'Phone', moreOrEqual: 0, lessOrEqual: 767, columns: 1},
        {id: 2, name: 'Desktop', moreOrEqual: 1200, lessOrEqual: -1, columns: 12},
    ];
    tab.model.preferences._trigger('post-commit', {screenSizes: tab.model.preferences._values.screenSizes});

    await wait(10);

    assert.equal(applyScreenSizeCalls, 1);
});

// ===========================================================================
// getColumnWidth / pixelsToColumns / pixelsToRows / parseSize
// ===========================================================================

test('getColumnWidth divides the grid element width by the active screen size columns', () => {
    const {dragboard} = createDragboard({offsetWidth: 1200});
    dragboard.gridElement.offsetWidth = 1200;

    assert.equal(dragboard.getColumnWidth(), 100); // 1200 / 12
});

test('pixelsToColumns rounds and enforces a minimum of 1', () => {
    const {dragboard} = createDragboard({offsetWidth: 1200});
    dragboard.gridElement.offsetWidth = 1200; // columnWidth = 100

    assert.equal(dragboard.pixelsToColumns(430), 4); // round(4.3) = 4
    assert.equal(dragboard.pixelsToColumns(1), 1); // rounds to 0, clamped to 1
});

test('pixelsToColumns returns 1 when the grid has zero width (columnWidth is 0)', () => {
    const {dragboard} = createDragboard();
    dragboard.gridElement.offsetWidth = 0;

    assert.equal(dragboard.pixelsToColumns(500), 1);
});

test('pixelsToRows ceils and enforces a minimum of 1', () => {
    const {dragboard} = createDragboard({preferenceValues: {cellheight: 40}});

    assert.equal(dragboard.pixelsToRows(81), 3); // ceil(2.025) = 3
    assert.equal(dragboard.pixelsToRows(1), 1);
});

test('pixelsToRows uses the fitted cell height in fixed-row mode', () => {
    const screenSizes = [
        {id: 0, name: 'Fixed', moreOrEqual: 0, lessOrEqual: -1, columns: 4, rows: 5},
    ];
    const {dragboard} = createDragboard({offsetWidth: 800, offsetHeight: 500, preferenceValues: {screenSizes}});

    assert.equal(dragboard.pixelsToRows(201), 3);
});

test('parseSize("Npx", "w") converts pixels to columns', () => {
    const {dragboard} = createDragboard({offsetWidth: 1200});
    dragboard.gridElement.offsetWidth = 1200; // columnWidth = 100

    assert.equal(dragboard.parseSize('400px', 'w'), 4);
});

test('parseSize("Npx", "h") converts pixels to rows', () => {
    const {dragboard} = createDragboard({preferenceValues: {cellheight: 40}});

    assert.equal(dragboard.parseSize('400px', 'h'), 10);
});

test('parseSize("N%", "w") is a percentage of the active screen size columns', () => {
    const {dragboard} = createDragboard({offsetWidth: 1200}); // desktop: 12 columns

    assert.equal(dragboard.parseSize('50%', 'w'), 6);
});

test('parseSize("N%", "h") is a percentage of the grid element height when available', () => {
    const {dragboard} = createDragboard({preferenceValues: {cellheight: 40}});
    dragboard.gridElement.offsetHeight = 800;

    assert.equal(dragboard.parseSize('50%', 'h'), 10); // 50% of 800 = 400; ceil(400/40) = 10
});

test('parseSize("N%", "h") falls back to the tab wrapper height when the grid has no height yet', () => {
    const {dragboard, tab} = createDragboard({preferenceValues: {cellheight: 40}, offsetHeight: 800});
    dragboard.gridElement.offsetHeight = 0;

    assert.equal(dragboard.parseSize('50%', 'h'), 10);
});

test('parseSize(number, "w") treats a unitless value as old-grid cells (20 columns)', () => {
    const {dragboard} = createDragboard({offsetWidth: 1200}); // 12 columns

    // w = round(n * columns / 20)
    assert.equal(dragboard.parseSize(20, 'w'), 12); // round(20*12/20) = 12
    assert.equal(dragboard.parseSize(1, 'w'), 1); // round(1*12/20)=round(0.6)=1
});

test('parseSize(number, "h") treats a unitless value as old-grid cells (12px rows)', () => {
    const {dragboard} = createDragboard({preferenceValues: {cellheight: 40}});

    // h = round(n * 12 / cellheight)
    assert.equal(dragboard.parseSize(10, 'h'), 3); // round(10*12/40) = round(3) = 3
});

test('parseSize accepts a unitless numeric string using the same old-grid cell formula', () => {
    const {dragboard} = createDragboard({offsetWidth: 1200});

    assert.equal(dragboard.parseSize('20', 'w'), dragboard.parseSize(20, 'w'));
});

test('parseSize enforces a minimum of 1 column/row for tiny values', () => {
    const {dragboard} = createDragboard({offsetWidth: 1200, preferenceValues: {cellheight: 400}});

    assert.equal(dragboard.parseSize(0, 'w'), 1);
    assert.equal(dragboard.parseSize(0, 'h'), 1);
});

// ===========================================================================
// persist()
// ===========================================================================

const setupPersistScenario = (extra = {}) => {
    const built = paintedDragboard(extra.dragboardOverrides);
    const model = createWidgetModel({id: 'w1', layouts: {2: {x: 1, y: 2, w: 3, h: 4}}});
    const view = createWidgetView(model);
    built.dragboard.addWidget(view);
    return Object.assign(built, {model, view});
};

test('persist() sends a single PUT with one entry per eligible widget', async () => {
    const {dragboard, view} = setupPersistScenario();
    view.wrapperElement.gridstackNode.x = 1;
    view.wrapperElement.gridstackNode.y = 2;
    view.wrapperElement.gridstackNode.w = 3;
    view.wrapperElement.gridstackNode.h = 4;

    const requests = [];
    Wirecloud.io.makeRequest = (url, options) => {
        requests.push({url, options});
        return Promise.resolve({status: 204});
    };

    await dragboard.persist();

    assert.equal(requests.length, 1);
    assert.equal(requests[0].options.method, 'PUT');
    const body = JSON.parse(requests[0].options.postBody);
    assert.equal(body.length, 1);
    assert.equal(body[0].id, 'w1');
    assert.deepEqual(body[0].layouts, {
        '2': {x: 1, y: 2, w: 3, h: 4, minimized: false, titlevisible: true, fulldragboard: false, visible: true},
    });
});

test('persist() skips volatile widgets', async () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({id: 'w1', volatile: true, layouts: {2: {x: 0, y: 0, w: 1, h: 1}}});
    const view = createWidgetView(model);
    dragboard.addWidget(view);

    let requestCount = 0;
    Wirecloud.io.makeRequest = () => { requestCount++; return Promise.resolve({status: 204}); };

    const result = await dragboard.persist();

    assert.equal(requestCount, 0);
    assert.equal(result, dragboard);
});

test('persist() skips hidden widgets', async () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({id: 'w1', layouts: {2: {x: 0, y: 0, w: 1, h: 1}}});
    const view = createWidgetView(model);
    dragboard.addWidget(view);
    view.wrapperElement.hidden = true;

    let requestCount = 0;
    Wirecloud.io.makeRequest = () => { requestCount++; return Promise.resolve({status: 204}); };

    await dragboard.persist();

    assert.equal(requestCount, 0);
});

test('persist() skips widgets that are not currently tracked by the grid', async () => {
    const {dragboard} = paintedDragboard();
    const model = createWidgetModel({id: 'w1', layouts: {2: {x: 0, y: 0, w: 1, h: 1, visible: false}}});
    const view = createWidgetView(model);
    dragboard.views.push(view); // never placed on the grid (no gridstackNode)

    let requestCount = 0;
    Wirecloud.io.makeRequest = () => { requestCount++; return Promise.resolve({status: 204}); };

    await dragboard.persist();

    assert.equal(requestCount, 0);
});

test('persist() resolves without a request when there is nothing to persist', async () => {
    const {dragboard} = paintedDragboard();

    let requestCount = 0;
    Wirecloud.io.makeRequest = () => { requestCount++; return Promise.resolve({status: 204}); };

    const result = await dragboard.persist();

    assert.equal(requestCount, 0);
    assert.equal(result, dragboard);
});

test('persist() applies the new layout locally (without persisting again) on success', async () => {
    const {dragboard, view, model} = setupPersistScenario();

    Wirecloud.io.makeRequest = () => Promise.resolve({status: 204});

    await dragboard.persist();

    assert.equal(model.setLayoutCalls.length, 1);
    assert.equal(model.setLayoutCalls[0].id, '2');
    assert.equal(model.setLayoutCalls[0].persist, false);
});

test('persist() rejects with the parsed error for known error statuses', async () => {
    const {dragboard} = setupPersistScenario();

    for (const status of [401, 403, 404, 500]) {
        Wirecloud.io.makeRequest = () => Promise.resolve({status});
        await assert.rejects(dragboard.persist(), (err) => {
            assert.ok(err instanceof Error);
            assert.equal(err.message, 'server-error-' + status);
            return true;
        });
    }
});

test('persist() rejects with a generic error for an unexpected status code', async () => {
    const {dragboard} = setupPersistScenario();

    Wirecloud.io.makeRequest = () => Promise.resolve({status: 200});

    await assert.rejects(dragboard.persist(), /Unexpected response from server/);
});

test('persist() targets the IWIDGET_COLLECTION URL for the tab\'s workspace and tab id', async () => {
    const {dragboard} = setupPersistScenario({});
    let requestedUrl = null;
    Wirecloud.io.makeRequest = (url) => { requestedUrl = url; return Promise.resolve({status: 204}); };

    await dragboard.persist();

    assert.equal(requestedUrl, `/api/workspaces/${dragboard.tab.workspace.model.id}/tabs/${dragboard.tab.model.id}/iwidgets/`);
});

// ===========================================================================
// REGRESSION TESTS
// ===========================================================================

// --- Placement must not depend on the previously active screen size ---

const setupThreeStoredWidgets = () => {
    const {dragboard, tab} = createDragboard({offsetWidth: 1400});
    ['a', 'b', 'c'].forEach((id, i) => {
        const model = createWidgetModel({id, layouts: {'2': {x: i * 4, y: 0, w: 4, h: 5}}});
        dragboard.addWidget(createWidgetView(model, {tab}));
    });
    dragboard.paint();
    return {dragboard, tab};
};

const snapshot = (dragboard) => dragboard.grid.engine.nodes
    .map((n) => `${n.id}@${n.x},${n.y} ${n.w}x${n.h}`)
    .sort()
    .join(' | ');

test('applyScreenSize detaches every widget before placing them again', () => {
    const {dragboard} = setupThreeStoredWidgets();

    dragboard.grid.calls.length = 0;
    dragboard.tab.wrapperElement.offsetWidth = 900;
    dragboard.applyScreenSize();

    const names = dragboard.grid.calls.map((call) => call.name);
    const lastRemove = names.lastIndexOf('removeWidget');
    const firstMake = names.indexOf('makeWidget');

    assert.ok(firstMake !== -1, 'widgets are re-added to the grid');
    assert.ok(lastRemove < firstMake,
        'every widget is detached before the first one is placed again, so auto placement ' +
        'cannot flow around the coordinates left over from the previous screen size');
});

test('going to a narrower screen size and back restores the original placement', () => {
    const {dragboard} = setupThreeStoredWidgets();
    const desktop = snapshot(dragboard);

    dragboard.tab.wrapperElement.offsetWidth = 900;
    dragboard.applyScreenSize();
    const tabletGoingDown = snapshot(dragboard);

    dragboard.tab.wrapperElement.offsetWidth = 500;
    dragboard.applyScreenSize();

    dragboard.tab.wrapperElement.offsetWidth = 900;
    dragboard.applyScreenSize();
    const tabletComingBack = snapshot(dragboard);

    dragboard.tab.wrapperElement.offsetWidth = 1400;
    dragboard.applyScreenSize();

    assert.equal(tabletComingBack, tabletGoingDown,
        'the same screen size gives the same layout whether it was reached by shrinking or growing');
    assert.equal(snapshot(dragboard), desktop, 'the stored layout is restored untouched');
});

// --- Hiding a widget only affects the screen size it was hidden at ---

test('resolveLayout never inherits visible:false from another screen size', () => {
    const {dragboard} = createDragboard({offsetWidth: 1400});
    const model = createWidgetModel({layouts: {'2': {x: 3, y: 1, w: 6, h: 4, visible: false}}});

    const derived = dragboard.resolveLayout(model, dragboard.screenSizes[1]);

    assert.equal(derived.visible, true, 'hiding is a per-screen-size decision, it is not inherited');
    assert.equal(derived.derived, true);
    assert.equal(derived.w, 3, 'the geometry is still scaled from the source screen size');
});

test('a widget hidden at one screen size stays on the grid at the others', () => {
    const {dragboard, tab} = createDragboard({offsetWidth: 1400});
    const hidden = createWidgetModel({id: 'hidden', layouts: {'2': {x: 0, y: 0, w: 4, h: 4, visible: false}}});
    const other = createWidgetModel({id: 'other', layouts: {'2': {x: 4, y: 0, w: 4, h: 4}}});
    const hiddenView = createWidgetView(hidden, {tab});
    dragboard.addWidget(hiddenView);
    dragboard.addWidget(createWidgetView(other, {tab}));
    dragboard.paint();

    assert.deepEqual(dragboard.hiddenWidgets.map((v) => v.id), ['hidden']);
    assert.equal(hiddenView.wrapperElement.hidden, true);

    tab.wrapperElement.offsetWidth = 900;
    dragboard.applyScreenSize();

    assert.deepEqual(dragboard.hiddenWidgets.map((v) => v.id), [],
        'the screen size that derives its layout shows the widget');
    assert.equal(hiddenView.wrapperElement.hidden, false);
    assert.notEqual(hiddenView.wrapperElement.gridstackNode, null);

    tab.wrapperElement.offsetWidth = 1400;
    dragboard.applyScreenSize();

    assert.deepEqual(dragboard.hiddenWidgets.map((v) => v.id), ['hidden'],
        'and it is still hidden at the screen size it was hidden at');
});

// --- The pointer must keep reaching the document while dragging/resizing ---

test('dragging or resizing marks the dragboard so widget contents stop capturing the pointer', () => {
    const {dragboard, grid} = paintedDragboard();
    const cls = () => dragboard.gridElement.classList.contains('wc-dragboard-interacting');

    assert.equal(cls(), false);

    grid.trigger('dragstart');
    assert.equal(cls(), true, 'the class is set while dragging');
    grid.trigger('dragstop');
    assert.equal(cls(), false, 'and cleared when the drag ends');

    grid.trigger('resizestart');
    assert.equal(cls(), true, 'the class is set while resizing');
    grid.trigger('resizestop');
    assert.equal(cls(), false, 'and cleared when the resize ends');
});

test('the end of a drag or resize still persists the layout', async () => {
    const {dragboard, grid, tab} = paintedDragboard();
    const model = createWidgetModel({id: 'w1', layouts: {'2': {x: 0, y: 0, w: 4, h: 4}}});
    const view = createWidgetView(model, {tab});
    dragboard.addWidget(view);

    const requests = [];
    Wirecloud.io.makeRequest = (url, options) => {
        requests.push(JSON.parse(options.postBody));
        return Promise.resolve({status: 204});
    };

    grid.trigger('resizestart');
    view.wrapperElement.gridstackNode.h = 9;
    grid.trigger('resizestop');
    await wait();

    assert.equal(requests.length, 1, 'the interaction handler still runs the layout bookkeeping');
    assert.equal(requests[0][0].layouts['2'].h, 9);
    assert.equal(view.syncCalls > 0, true);
});

test('at most one handler is registered per GridStack event name', () => {
    const {grid} = paintedDragboard();

    // GridStack keeps a single callback per event name: registering twice for
    // the same name would silently drop the first handler.
    Object.keys(grid.listeners).forEach((name) => {
        assert.equal(grid.listeners[name].length, 1, `${name} must have exactly one handler`);
    });
});

test('setDockPushMargin sets explicit pixel margins and repaints views after transition', async () => {
    const {dragboard, tab} = paintedDragboard();
    let repainted = false;
    const view = {
        repaint: () => {
            repainted = true;
        }
    };
    dragboard.views.push(view);

    dragboard.setDockPushMargin('left', 250);
    assert.equal(dragboard.gridElement.style.marginLeft, '250px');
    assert.equal(dragboard._dockMargins.left, 250);

    dragboard.setDockPushMargin('right', 300);
    assert.equal(dragboard.gridElement.style.marginRight, '300px');
    assert.equal(dragboard._dockMargins.right, 300);

    dragboard.setDockPushMargin('top', 150);
    assert.equal(dragboard.gridElement.style.marginTop, '150px');
    assert.equal(dragboard._dockMargins.top, 150);

    dragboard.setDockPushMargin('bottom', 100);
    assert.equal(dragboard.gridElement.style.marginBottom, '');
    assert.equal(dragboard._dockMargins.bottom, 0, 'bottom docks are overlay-only');

    dragboard.setDockPushMargin('left', 0);
    assert.equal(dragboard.gridElement.style.marginLeft, '');
    assert.equal(dragboard._dockMargins.left, 0);

    assert.equal(repainted, false, 'repaint is debounced to after the 300ms animation');
    await wait(350);
    assert.equal(repainted, true, 'repaint called after animation settles');
});
