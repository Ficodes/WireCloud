const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScript,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');
const {installGridStackMock} = require('../../support/gridstack-mock.cjs');

const DEFAULT_SCREEN_SIZES = [
    {id: 0, name: 'Phone', moreOrEqual: 0, lessOrEqual: 767, columns: 1},
    {id: 1, name: 'Tablet', moreOrEqual: 768, lessOrEqual: 1199, columns: 6},
    {id: 2, name: 'Desktop', moreOrEqual: 1200, lessOrEqual: -1, columns: 12},
];

const createPreferencesMock = () => {
    const listeners = {};
    const values = {
        cellheight: 40,
        margin: 5,
        screenSizes: DEFAULT_SCREEN_SIZES,
    };
    return {
        _values: values,
        get(key) { return this._values[key]; },
        addEventListener(type, handler) { (listeners[type] = listeners[type] || []).push(handler); },
        _trigger(type, payload) { (listeners[type] || []).forEach((h) => h(this, payload)); }
    };
};

const createWorkspaceMock = (editing = true) => {
    const listeners = {};
    return {
        editing,
        model: { id: 'workspace-1', restricted: false },
        tabs: [{ id: 'tab-1', title: 'Tab 1' }],
        addEventListener(type, handler) { (listeners[type] = listeners[type] || []).push(handler); },
        _trigger(type, ...args) { (listeners[type] || []).forEach((h) => h(this, ...args)); }
    };
};

const createTabMock = (editing = true) => {
    const wrapperElement = document.createElement('div');
    wrapperElement.offsetWidth = 1200;
    wrapperElement.offsetHeight = 800;
    const preferences = createPreferencesMock();
    const workspace = createWorkspaceMock(editing);
    return {
        wrapperElement,
        model: { id: 'tab-1', preferences },
        workspace
    };
};

const createWidgetViewMock = (id, layoutOverrides = {}, isAllowedMove = true, isAllowedResize = true) => {
    const wrapperElement = document.createElement('div');
    const layout = Object.assign({
        x: null, y: null, w: 4, h: 4,
        minimized: false, titlevisible: true, fulldragboard: false, visible: true,
        dock: null, dock_mode: 'overlay', dock_open: true
    }, layoutOverrides);

    const model = {
        id: id,
        volatile: false,
        missing: false,
        meta: { doc: 'doc', version: '1.0.0' },
        hasPreferences: () => true,
        getLayout: () => Object.assign({}, layout),
        setLayout: (screenSizeId, changes, persist) => {
            Object.assign(layout, changes);
            return Promise.resolve(model);
        },
        isAllowed: (action) => {
            if (action === 'move') return isAllowedMove;
            if (action === 'resize') return isAllowedResize;
            return true;
        }
    };

    return {
        id,
        model,
        layout,
        wrapperElement,
        tab: null,
        repaint() {},
        applyLayout(l) { this.layout = Object.assign({}, l); },
        syncLayoutFromNode() {
            if (this.wrapperElement.gridstackNode) {
                this.layout.x = this.wrapperElement.gridstackNode.x;
                this.layout.y = this.wrapperElement.gridstackNode.y;
                this.layout.w = this.wrapperElement.gridstackNode.w;
                this.layout.h = this.wrapperElement.gridstackNode.h;
            }
        },
        updateGridPermissions() {},
        isDocked() { return !!this.layout.dock; },
        dockTo(pos, mode = 'overlay', persist = true) {
            return this.tab.dragboard.dockWidget(this, pos, mode, persist);
        },
        undock(persist = true) {
            return this.tab.dragboard.undockWidget(this, persist);
        },
        setDockMode(mode, persist = true) {
            return this.tab.dragboard.setWidgetDockMode(this, mode, persist);
        },
        toggleDockOpen(persist = true) {
            return this.tab.dragboard.toggleWidgetDockOpen(this, persist);
        }
    };
};

const setup = () => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();
    const GridStack = installGridStackMock();

    if (global.Wirecloud == null) {
        global.Wirecloud = {};
    }
    Wirecloud.Utils = StyledElements.Utils;
    Wirecloud.ui = Wirecloud.ui || {};
    Wirecloud.LocalCatalogue = { hasAlternativeVersion: () => false };

    Wirecloud.URLs = {
        IWIDGET_COLLECTION: { evaluate: () => '/api/collection' },
        IWIDGET_ENTRY: { evaluate: () => '/api/entry' },
    };
    Wirecloud.io = {
        makeRequest: () => Promise.resolve({status: 204}),
    };
    global.window.innerWidth = 1200;
    StyledElements.DynamicMenuItems = class DynamicMenuItems {
        constructor(widget) {
            this.widget = widget;
        }
    };
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
    StyledElements.Separator = class Separator {};

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/SidebarLayout.js');
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewDragboard.js');
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WidgetViewMenuItems.js');

    return {GridStack};
};

test.beforeEach(() => {
    setup();
});

test('SidebarLayout constructor validates position and sets vertical flag', () => {
    const tab = createTabMock();
    const dragboard = new Wirecloud.ui.WorkspaceTabViewDragboard(tab);

    const leftDock = new Wirecloud.ui.SidebarLayout(dragboard, {position: 'left'});
    assert.equal(leftDock.position, 'left');
    assert.equal(leftDock.vertical, true);
    assert.equal(leftDock.container.getAttribute('data-dock'), 'left');

    const topDock = new Wirecloud.ui.SidebarLayout(dragboard, {position: 'top'});
    assert.equal(topDock.position, 'top');
    assert.equal(topDock.vertical, false);

    assert.throws(() => {
        new Wirecloud.ui.SidebarLayout(dragboard, {position: 'diagonal'});
    }, TypeError);
});

test('SidebarLayout addWidget attaches widget and toggle handle with caret icon', () => {
    const tab = createTabMock();
    const dragboard = new Wirecloud.ui.WorkspaceTabViewDragboard(tab);
    dragboard.paint();

    const view = createWidgetViewMock('w1', {dock: 'left', dock_open: true});
    dragboard.leftDock.addWidget(view, view.layout, 'editor');

    assert.ok(dragboard.leftDock.views.includes(view));
    assert.equal(dragboard.leftDock.container.classList.contains('hidden'), false);
    assert.equal(view.wrapperElement.classList.contains('wc-docked-widget'), true);
    assert.equal(view.wrapperElement.classList.contains('wc-docked-left'), true);
    assert.equal(view.wrapperElement.classList.contains('wc-dock-widget-open'), true);

    const handle = dragboard.leftDock.getHandle(view);
    assert.ok(handle != null);
    assert.ok(view.wrapperElement.childNodes.includes(handle));
    const icon = handle._icon;
    assert.ok(icon != null);
    // When left sidebar is open, caret points left (to collapse)
    assert.equal(icon.className, 'fas fa-caret-left');
});

test('SidebarLayout toggling widget flips open/closed state and caret icon', () => {
    const tab = createTabMock();
    const dragboard = new Wirecloud.ui.WorkspaceTabViewDragboard(tab);
    dragboard.paint();

    const view = createWidgetViewMock('w1', {dock: 'left', dock_open: true});
    dragboard.leftDock.addWidget(view, view.layout, 'editor');

    // Close widget
    dragboard.leftDock.toggleWidget(view, false);
    assert.equal(view.layout.dock_open, false);
    assert.equal(view.wrapperElement.classList.contains('wc-dock-widget-closed'), true);
    assert.equal(view.wrapperElement.classList.contains('wc-dock-widget-open'), false);

    const handle = dragboard.leftDock.getHandle(view);
    const icon = handle._icon;
    // When left sidebar is closed, caret points right (to expand)
    assert.equal(icon.className, 'fas fa-caret-right');

    // Open widget
    dragboard.leftDock.toggleWidget(view, false);
    assert.equal(view.layout.dock_open, true);
    assert.equal(view.wrapperElement.classList.contains('wc-dock-widget-open'), true);
    assert.equal(icon.className, 'fas fa-caret-left');
});

test('SidebarLayout supports multiple widgets per side with independent dimensions', () => {
    const tab = createTabMock();
    const dragboard = new Wirecloud.ui.WorkspaceTabViewDragboard(tab);
    dragboard.paint();

    // Widget 1: width 3, height 4
    const view1 = createWidgetViewMock('w1', {dock: 'left', w: 3, h: 4, x: 0, y: 0});
    // Widget 2: width 6, height 5 (different width than widget 1)
    const view2 = createWidgetViewMock('w2', {dock: 'left', w: 6, h: 5, x: 0, y: 4});

    dragboard.leftDock.addWidget(view1, view1.layout, 'editor');
    dragboard.leftDock.addWidget(view2, view2.layout, 'editor');

    assert.equal(dragboard.leftDock.views.length, 2);

    // Both widgets are locked to x: 0 (1 column stacked vertically)
    assert.equal(view1.wrapperElement.gridstackNode.x, 0);
    assert.equal(view2.wrapperElement.gridstackNode.x, 0);

    // Each widget preserves its own independent width and height!
    assert.equal(view1.wrapperElement.gridstackNode.w, 3);
    assert.equal(view1.wrapperElement.gridstackNode.h, 4);
    assert.equal(view2.wrapperElement.gridstackNode.w, 6);
    assert.equal(view2.wrapperElement.gridstackNode.h, 5);
});

test('Top sidebar locks widgets to y: 0 (single row) while preserving independent dimensions', () => {
    const tab = createTabMock();
    const dragboard = new Wirecloud.ui.WorkspaceTabViewDragboard(tab);
    dragboard.paint();

    // Widget 1: width 3, height 2
    const view1 = createWidgetViewMock('w1', {dock: 'top', w: 3, h: 2, x: 0, y: 0});
    // Widget 2: width 5, height 4 (different height than widget 1)
    const view2 = createWidgetViewMock('w2', {dock: 'top', w: 5, h: 4, x: 3, y: 0});

    dragboard.topDock.addWidget(view1, view1.layout, 'editor');
    dragboard.topDock.addWidget(view2, view2.layout, 'editor');

    assert.equal(dragboard.topDock.views.length, 2);

    // Both widgets are locked to y: 0 (1 row side-by-side)
    assert.equal(view1.wrapperElement.gridstackNode.y, 0);
    assert.equal(view2.wrapperElement.gridstackNode.y, 0);

    // Independent heights and widths
    assert.equal(view1.wrapperElement.gridstackNode.h, 2);
    assert.equal(view1.wrapperElement.gridstackNode.w, 3);
    assert.equal(view2.wrapperElement.gridstackNode.h, 4);
    assert.equal(view2.wrapperElement.gridstackNode.w, 5);
});

test('Sidebar display mode: push mode applies margin to dragboard, overlay mode does not', () => {
    const tab = createTabMock();
    const dragboard = new Wirecloud.ui.WorkspaceTabViewDragboard(tab);
    dragboard.paint();
    dragboard.gridElement.offsetWidth = 1200; // columnWidth = 100

    const view = createWidgetViewMock('w1', {dock: 'left', dock_mode: 'overlay', dock_open: true, w: 3});
    dragboard.leftDock.addWidget(view, view.layout, 'editor');

    // In overlay mode, marginLeft is empty
    assert.equal(dragboard.gridElement.style.marginLeft, '');

    // Switch to push mode: 3 cols * 100px/col = 300px margin
    dragboard.leftDock.setWidgetMode(view, 'push', false);
    assert.equal(dragboard.gridElement.style.marginLeft, '300px');

    // Closing the widget removes the push margin
    dragboard.leftDock.setWidgetOpen(view, false, false);
    assert.equal(dragboard.gridElement.style.marginLeft, '');

    // Reopening restores push margin
    dragboard.leftDock.setWidgetOpen(view, true, false);
    assert.equal(dragboard.gridElement.style.marginLeft, '300px');
});

test('Multiple push widgets on the same side use the maximum width for margin', () => {
    const tab = createTabMock();
    const dragboard = new Wirecloud.ui.WorkspaceTabViewDragboard(tab);
    dragboard.paint();
    dragboard.gridElement.offsetWidth = 1200; // columnWidth = 100

    const view1 = createWidgetViewMock('w1', {dock: 'left', dock_mode: 'push', dock_open: true, w: 3});
    const view2 = createWidgetViewMock('w2', {dock: 'left', dock_mode: 'push', dock_open: true, w: 5});

    dragboard.leftDock.addWidget(view1, view1.layout, 'editor');
    dragboard.leftDock.addWidget(view2, view2.layout, 'editor');

    // Max of (300px, 500px) is 500px
    assert.equal(dragboard.gridElement.style.marginLeft, '500px');

    // Closing the wider widget drops the margin to 300px
    dragboard.leftDock.setWidgetOpen(view2, false, false);
    assert.equal(dragboard.gridElement.style.marginLeft, '300px');
});

test('Dragboard dockWidget and undockWidget transition widget between main grid and dock', () => {
    const tab = createTabMock();
    const dragboard = new Wirecloud.ui.WorkspaceTabViewDragboard(tab);
    dragboard.paint();

    const view = createWidgetViewMock('w1', {dock: null, w: 4, h: 4});
    dragboard.addWidget(view);

    assert.ok(dragboard.gridElement.childNodes.includes(view.wrapperElement));
    assert.equal(dragboard.leftDock.views.includes(view), false);

    // Dock to left
    dragboard.dockWidget(view, 'left', 'overlay', false);
    assert.ok(dragboard.leftDock.views.includes(view));
    assert.equal(view.wrapperElement.parentNode, dragboard.leftDock.gridElement);

    // Undock back to main grid
    dragboard.undockWidget(view, false);
    assert.equal(dragboard.leftDock.views.includes(view), false);
    assert.ok(dragboard.gridElement.childNodes.includes(view.wrapperElement));
});

test('WidgetViewMenuItems: undocked widget provides Dock to sidebar submenu', () => {
    const tab = createTabMock();
    const dragboard = new Wirecloud.ui.WorkspaceTabViewDragboard(tab);
    dragboard.paint();

    let dockedTo = null;
    const view = createWidgetViewMock('w1', {dock: null});
    view.tab = tab;
    tab.dragboard = dragboard;
    view.dockTo = (pos, mode, persist) => { dockedTo = {pos, mode, persist}; };

    const menu = new Wirecloud.ui.WidgetViewMenuItems(view);
    const items = menu.build();

    const dockSubmenu = items.find((i) => i.label === 'Dock to sidebar');
    assert.ok(dockSubmenu != null);
    assert.equal(dockSubmenu.children.length, 4);
    assert.equal(dockSubmenu.children[0].label, 'Left sidebar');
    assert.equal(dockSubmenu.children[1].label, 'Right sidebar');
    assert.equal(dockSubmenu.children[2].label, 'Top sidebar');
    assert.equal(dockSubmenu.children[3].label, 'Bottom sidebar');

    dockSubmenu.children[0].run();
    assert.deepEqual(dockedTo, {pos: 'left', mode: 'overlay', persist: true});
});

test('WidgetViewMenuItems: docked widget provides Snap to grid, Move to sidebar, and Sidebar display mode', () => {
    const tab = createTabMock();
    const dragboard = new Wirecloud.ui.WorkspaceTabViewDragboard(tab);
    dragboard.paint();

    let undocked = false;
    let newMode = null;
    const view = createWidgetViewMock('w1', {dock: 'left', dock_mode: 'overlay'});
    view.tab = tab;
    tab.dragboard = dragboard;
    view.undock = (persist) => { undocked = persist; };
    view.setDockMode = (mode, persist) => { newMode = {mode, persist}; };

    const menu = new Wirecloud.ui.WidgetViewMenuItems(view);
    const items = menu.build();

    const snapItem = items.find((i) => i.label === 'Snap to grid');
    assert.ok(snapItem != null);
    snapItem.run();
    assert.equal(undocked, true);

    const moveDockSubmenu = items.find((i) => i.label === 'Move to sidebar');
    assert.ok(moveDockSubmenu != null);
    // Should contain Right, Top, Bottom (omitting Left)
    assert.equal(moveDockSubmenu.children.length, 3);
    assert.equal(moveDockSubmenu.children.some((c) => c.label === 'Left sidebar'), false);

    const modeSubmenu = items.find((i) => i.label === 'Sidebar display mode');
    assert.ok(modeSubmenu != null);
    assert.equal(modeSubmenu.children.length, 2);
    assert.equal(modeSubmenu.children[0].label, 'Show on top of content (overlay)');
    assert.equal(modeSubmenu.children[1].label, 'Push main content');

    modeSubmenu.children[1].run();
    assert.deepEqual(newMode, {mode: 'push', persist: true});
});

test('SidebarLayout sets gs-resize-handles attribute and engine constraints lock coordinates', () => {
    const tab = createTabMock();
    const dragboard = new Wirecloud.ui.WorkspaceTabViewDragboard(tab);
    dragboard.paint();

    const viewLeft = createWidgetViewMock('wLeft', {dock: 'left', w: 4, h: 6});
    dragboard.dockWidget(viewLeft, 'left', 'overlay', false);

    assert.equal(viewLeft.wrapperElement.getAttribute('gs-resize-handles'), 'n,ne,e,se,s');

    // Check engine constraint for left dock
    const leftDock = dragboard.leftDock;
    const testNode = { x: 5, y: 3, w: 4, h: 6 };
    leftDock.grid.engine.nodeBoundFix(testNode, false);
    assert.equal(testNode.x, 0, 'Left dock nodeBoundFix forces x to 0');

    const testCoord = { x: 3, y: 4, w: 4, h: 6 };
    leftDock.grid.engine.moveNode(testNode, testCoord);
    assert.equal(testCoord.x, 0, 'Left dock moveNode forces x to 0');

    // Right dock handles and constraint
    const viewRight = createWidgetViewMock('wRight', {dock: 'right', w: 5, h: 4});
    dragboard.dockWidget(viewRight, 'right', 'overlay', false);
    assert.equal(viewRight.wrapperElement.getAttribute('gs-resize-handles'), 'n,nw,w,sw,s');

    const rightDock = dragboard.rightDock;
    const rightNode = { x: 0, y: 2, w: 5, h: 4 };
    rightDock.grid.engine.nodeBoundFix(rightNode, false);
    assert.equal(rightNode.x, 7, 'Right dock nodeBoundFix forces x to 12 - 5 = 7');

    // Top dock handles and constraint
    const viewTop = createWidgetViewMock('wTop', {dock: 'top', w: 4, h: 4});
    dragboard.dockWidget(viewTop, 'top', 'overlay', false);
    assert.equal(viewTop.wrapperElement.getAttribute('gs-resize-handles'), 'e,se,s,sw,w');

    const topDock = dragboard.topDock;
    const topNode = { x: 2, y: 5, w: 4, h: 4 };
    topDock.grid.engine.nodeBoundFix(topNode, false);
    assert.equal(topNode.y, 0, 'Top dock nodeBoundFix forces y to 0');

    // Bottom dock handles
    const viewBottom = createWidgetViewMock('wBottom', {dock: 'bottom', w: 4, h: 4});
    dragboard.dockWidget(viewBottom, 'bottom', 'overlay', false);
    assert.equal(viewBottom.wrapperElement.getAttribute('gs-resize-handles'), 'e,ne,n,nw,w');

    // Undock removes gs-resize-handles
    dragboard.undockWidget(viewLeft, false);
    assert.equal(viewLeft.wrapperElement.getAttribute('gs-resize-handles'), null);
});

test('SidebarLayout drag and resize events toggle wc-dock-interacting and sync layout', () => {
    const tab = createTabMock();
    const dragboard = new Wirecloud.ui.WorkspaceTabViewDragboard(tab);
    dragboard.paint();

    const view = createWidgetViewMock('w1', {dock: 'left', w: 4, h: 6});
    dragboard.dockWidget(view, 'left', 'overlay', false);

    const dock = dragboard.leftDock;
    assert.equal(dock.container.classList.contains('wc-dock-interacting'), false);

    // Simulate dragstart
    dock.grid.trigger('dragstart');
    assert.equal(dock.container.classList.contains('wc-dock-interacting'), true);

    // Change node position (e.g. user reordered stacked widgets vertically)
    view.wrapperElement.gridstackNode.y = 6;
    let persistCalled = false;
    dragboard.persist = () => { persistCalled = true; return Promise.resolve(dragboard); };

    // Simulate dragstop
    dock.grid.trigger('dragstop');
    assert.equal(dock.container.classList.contains('wc-dock-interacting'), false);
    assert.equal(view.layout.y, 6, 'view layout synced from node y');
    assert.equal(persistCalled, true, 'dragboard.persist was triggered');
});

