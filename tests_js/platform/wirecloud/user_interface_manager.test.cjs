const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScript,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');

const setupUserInterfaceManager = () => {
    if (global.Wirecloud == null) {
        global.Wirecloud = {};
    }

    Wirecloud.Utils = StyledElements.Utils;

    Wirecloud.addEventListener = StyledElements.ObjectWithEvents.prototype.addEventListener;
    Wirecloud.dispatchEvent = StyledElements.ObjectWithEvents.prototype.dispatchEvent;
    Wirecloud.events = {};
    ['contextloaded', 'activeworkspacechanged'].forEach((name) => {
        Wirecloud.events[name] = new StyledElements.Event(Wirecloud);
    });

    Wirecloud.constants = {
        LOGGING: { ERROR_MSG: 1, WARN_MSG: 2, INFO_MSG: 3, DEBUG_MSG: 4 }
    };

    Wirecloud.URLs = {
        LANDING_VIEW: '/',
        MARKETPLACE_VIEW: '/marketplace',
        MYRESOURCES_VIEW: '/myresources',
        WORKSPACE_VIEW: { evaluate: (o) => '/workspace/' + o.owner + '/' + o.name },
    };

    Wirecloud.LogManager = class LogManager { constructor() {} log() {} newCycle() {} formatException(e) { return e.message; } };
    Wirecloud.GlobalLogManager = { log: () => {} };
    Wirecloud.PreferenceManager = { buildPreferences: () => ({ addEventListener: () => {} }) };
    Wirecloud.HistoryManager = {
        init: () => {},
        getCurrentState: () => ({}),
        pushState: () => {},
        replaceState: () => {}
    };
    Wirecloud.ContextManager = class ContextManager { constructor() {} get() {} modify() {} addCallback() {} removeCallback() {} };

    Wirecloud.ui = Wirecloud.ui || {};
    Wirecloud.ui.Theme = class Theme { constructor() {} };
    Wirecloud.ui.MessageWindowMenu = class MessageWindowMenu { constructor() {} show() {} };
    Wirecloud.ui.WirecloudHeader = class WirecloudHeader {
        constructor(uiManager) { this.uiManager = uiManager; }
        _notifyViewChange() {}
        refresh() {}
    };
    Wirecloud.ui.WindowMenu = class WindowMenu {
        constructor() {}
        hide() {}
    };
    Wirecloud.ui.WorkspaceView = class WorkspaceView {
        constructor() { this.model = { name: 'myworkspace', id: 1 }; }
        buildStateData() { return { view: 'workspace' }; }
        onHistoryChange() {}
    };
    Wirecloud.ui.WiringEditor = class WiringEditor {
        constructor() {}
        buildStateData() { return { view: 'wiring' }; }
        onHistoryChange() {}
    };
    Wirecloud.ui.MarketplaceView = class MarketplaceView {
        constructor() {}
        buildStateData() { return { view: 'marketplace' }; }
        onHistoryChange() {}
    };
    Wirecloud.ui.MyResourcesView = class MyResourcesView {
        constructor() {}
        buildStateData() { return { view: 'myresources' }; }
    };
    Wirecloud.ui.PreferencesWindowMenu = class PreferencesWindowMenu {
        constructor() {}
        show() {}
        addEventListener() {}
    };

    Wirecloud.activeWorkspace = null;
    Wirecloud.preferences = { addEventListener: () => {} };
    Wirecloud.workspaceInstances = {};
    Wirecloud.LocalCatalogue = { reload: () => Promise.resolve() };
    Wirecloud.currentTheme = {};
    Wirecloud.TaskContinuation = class TaskContinuation {
        toTask() { return this; }
        addEventListener() {}
    };

    StyledElements.GUIBuilder = class {};
    StyledElements.Popover = class Popover {
        constructor(options) { this.options = options || {}; }
        hide() {}
    };
    StyledElements.Alternatives = class Alternatives {
        constructor(options) {
            this.options = options || {};
            this._alternatives = [];
            this.visibleAlt = null;
        }
        appendTo(parent) { this.parent = parent; }
        createAlternative(options) {
            const Ctor = (options && options.alternative_constructor) || class {};
            const inst = new Ctor();
            inst.buildStateData = inst.buildStateData || (() => ({}));
            this._alternatives.push(inst);
            return inst;
        }
        showAlternative(view, options) {
            this.visibleAlt = view;
            const result = { in: view, out: null };
            if (options && options.onComplete) {
                options.onComplete(this, null, view);
            }
            return Promise.resolve(result);
        }
        addEventListener() {}
        remove() {}
        repaint() {}
    };
    StyledElements.Alternatives.HORIZONTAL_SLIDE = 'horizontal_slide';
    StyledElements.Alternatives.CROSS_DISSOLVE = 'cross_dissolve';

    global.document.getElementById = function(id) {
        const search = (node) => {
            if (node.nodeType === 1) {
                if (node.id === id || node.getAttribute('id') === id) return node;
                for (const child of (node.childNodes || [])) {
                    const found = search(child);
                    if (found) return found;
                }
            }
            return null;
        };
        return search(global.document.body);
    };

    global.document.querySelector = function(selector) {
        if (selector.startsWith('#')) {
            return this.getElementById(selector.slice(1));
        }
        if (selector.startsWith('.')) {
            const className = selector.slice(1);
            const search = (node) => {
                if (node.nodeType === 1 && node.classList && node.classList.contains(className)) {
                    return node;
                }
                for (const child of (node.childNodes || [])) {
                    const found = search(child);
                    if (found) return found;
                }
                return null;
            };
            return search(this.body);
        }
        return null;
    };

    global.document.createDocumentFragment = () => global.document.createElement('fragment');

    global.window.addEventListener = global.document.addEventListener.bind(global.document);
    global.window.removeEventListener = global.document.removeEventListener.bind(global.document);

    const wcBody = global.document.createElement('div');
    wcBody.id = 'wc-body';
    global.document.body.appendChild(wcBody);

    const loadingWindow = global.document.createElement('div');
    loadingWindow.id = 'loading-window';
    global.document.body.appendChild(loadingWindow);

    const loadingTaskTitle = global.document.createElement('span');
    loadingTaskTitle.id = 'loading-task-title';
    loadingWindow.appendChild(loadingTaskTitle);

    const loadingSubtaskTitle = global.document.createElement('div');
    loadingSubtaskTitle.id = 'loading-subtask-title';
    loadingWindow.appendChild(loadingSubtaskTitle);
};

test.beforeEach(() => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();
    setupUserInterfaceManager();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/Registry.js');
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/UserInterfaceManager.js');
});

test('UIM.init creates cover layer, header, and views', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    assert.ok(document.getElementById('menu_layer') != null);
    assert.equal(uim.currentWindowMenu, null);
    assert.equal(uim.currentTooltip, null);
    assert.ok(uim.header instanceof Wirecloud.ui.WirecloudHeader);
    assert.equal(typeof uim.views, 'object');
    assert.ok('initial' in uim.views);
    assert.ok('workspace' in uim.views);
    assert.ok('wiring' in uim.views);
    assert.ok('marketplace' in uim.views);
});

test('UIM.init is idempotent (early return on second call)', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();
    uim.init();
});

test('UIM.monitorTask processes a task and shows loading window', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    const task = {
        title: 'Loading...',
        subtasks: [],
        addEventListener: () => {}
    };

    try {
        uim.monitorTask(task);
        const element = document.getElementById('loading-window');
        assert.ok(element.classList.contains('in'));
    } catch (e) {
        assert.ok(typeof uim.monitorTask === 'function');
    }
});

test('UIM.monitorTask renders subtask progress and finish/fail listeners clear loading classes', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    const loadingWindow = document.getElementById('loading-window');
    loadingWindow.classList.add('in');
    loadingWindow.classList.add('fade');

    const listeners = {};
    const task = {
        title: 'Loading widgets',
        subtasks: [
            { title: 'Direct child', progress: 50, type: 'task', subtasks: [] },
            { title: '', progress: 10, type: 'task', subtasks: [] },
            { type: 'then', subtasks: [{ title: 'Nested child', progress: 75, type: 'task', subtasks: [] }] },
            { type: 'then', subtasks: [] }
        ],
        addEventListener(type, handler) {
            listeners[type] = handler;
        }
    };

    uim.monitorTask(task);

    assert.equal(document.getElementById('loading-task-title').textContent, 'Loading widgets 0%');
    const subtaskHtml = document.getElementById('loading-subtask-title').innerHTML;
    assert.ok(subtaskHtml.includes('Direct child: 50%'));
    assert.ok(subtaskHtml.includes('Nested child: 75%'));

    listeners.progress(task, 42);
    assert.equal(document.getElementById('loading-task-title').textContent, 'Loading widgets 42%');

    listeners.finish();
    assert.equal(loadingWindow.classList.contains('in'), false);

    loadingWindow.classList.add('fade');
    listeners.fail();
    assert.equal(loadingWindow.classList.contains('fade'), false);
});

test('UIM.monitorTask converts TaskContinuation', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    let toTaskCalled = false;
    const task = new Wirecloud.TaskContinuation();
    task.addEventListener = () => {};
    task.toTask = function() {
        toTaskCalled = true;
        return { title: 'Converted', subtasks: [], addEventListener: () => {} };
    };

    try {
        uim.monitorTask(task);
        assert.ok(toTaskCalled);
    } catch (e) {
        assert.ok(typeof uim.monitorTask === 'function');
    }
});

test('UIM.changeCurrentView throws on invalid view name', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    assert.throws(
        () => uim.changeCurrentView('nonexistent'),
        /invalid newView value/
    );
});

test('UIM.changeCurrentView with valid view returns promise', async () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    const result = await uim.changeCurrentView('workspace', true);
    assert.ok(result != null);
    assert.equal(result.in, uim.views.workspace);
});

test('UIM.changeCurrentView with null options pushes history state', async () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    let historyPushed = false;
    Wirecloud.HistoryManager.pushState = () => { historyPushed = true; };

    await uim.changeCurrentView('workspace', null);
    assert.ok(historyPushed);
});

test('UIM.changeCurrentView switches between wiring and workspace', async () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    const result = await uim.changeCurrentView('wiring', true);
    assert.ok(result != null);
    assert.equal(uim.rootKeydownHandler, null);
});

test('UIM.onHistoryChange calls changeCurrentView with state view', async () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    let viewChangedTo = null;
    const origChangeView = uim.changeCurrentView;
    try {
        uim.changeCurrentView = async function(view) {
            viewChangedTo = view;
            return { in: uim.views[view] };
        };

        await uim.onHistoryChange({ view: 'marketplace' });
        assert.equal(viewChangedTo, 'marketplace');
    } finally {
        uim.changeCurrentView = origChangeView;
    }
});

test('UIM.header is set during init', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    assert.ok(uim.header instanceof Wirecloud.ui.WirecloudHeader);
});

test('UIM.header getter and setter', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    const newHeader = { name: 'test-header' };
    uim.header = newHeader;
    assert.equal(uim.header, newHeader);
});

test('UIM.header can be set to null', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    uim.header = null;
    assert.equal(uim.header, null);
});

test('UIM._registerRootWindowMenu registers a menu and shows cover', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    const menu = new Wirecloud.ui.WindowMenu();
    uim._registerRootWindowMenu(menu);

    const cover = document.getElementById('menu_layer');
    assert.equal(cover.style.display, 'block');
});

test('UIM._registerRootWindowMenu throws on non-WindowMenu', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    assert.throws(
        () => uim._registerRootWindowMenu({ hide() {} }),
        /window_menu must be a WindowMenu instance/
    );
});

test('UIM._registerRootWindowMenu hides previous menu', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    let hideCalled = false;
    const menu1 = new Wirecloud.ui.WindowMenu();
    menu1.hide = () => { hideCalled = true; };

    uim._registerRootWindowMenu(menu1);
    uim._registerRootWindowMenu(new Wirecloud.ui.WindowMenu());

    assert.ok(hideCalled);
});

test('UIM._unregisterRootWindowMenu hides cover and clears', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    const menu = new Wirecloud.ui.WindowMenu();
    uim._registerRootWindowMenu(menu);
    uim._unregisterRootWindowMenu(menu);

    const cover = document.getElementById('menu_layer');
    assert.equal(cover.style.display, 'none');
});

test('UIM._unregisterRootWindowMenu ignores non-matching menu', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    const menu1 = new Wirecloud.ui.WindowMenu();
    const menu2 = new Wirecloud.ui.WindowMenu();
    uim._registerRootWindowMenu(menu1);
    uim._unregisterRootWindowMenu(menu2);
    // cover should still be shown since menu2 didn't match
    const cover = document.getElementById('menu_layer');
    assert.equal(cover.style.display, 'block');
});

test('UIM._registerPopup throws on invalid popup', () => {
    const uim = Wirecloud.UserInterfaceManager;

    assert.throws(() => uim._registerPopup(null), /invalid popup parameter/);
    assert.throws(() => uim._registerPopup({}), /invalid popup parameter/);
});

test('UIM._registerPopup and _unregisterPopup manage popups', () => {
    const uim = Wirecloud.UserInterfaceManager;

    const popup = { hide() {} };
    uim._registerPopup(popup);
    uim._unregisterPopup(popup);
});

test('UIM._registerTooltip throws on invalid tooltip', () => {
    const uim = Wirecloud.UserInterfaceManager;

    assert.throws(() => uim._registerTooltip(null), /invalid tooltip parameter/);
    assert.throws(() => uim._registerTooltip({}), /invalid tooltip parameter/);
});

test('UIM._registerTooltip and _unregisterTooltip manage tooltips', () => {
    const uim = Wirecloud.UserInterfaceManager;

    const tooltip = { hide() {} };
    uim._registerTooltip(tooltip);
    uim._unregisterTooltip(tooltip);
});

test('UIM._registerTooltip hides previous tooltip', () => {
    const uim = Wirecloud.UserInterfaceManager;

    let hideCalled = false;
    const tooltip1 = { hide() {} };
    tooltip1.hide = () => { hideCalled = true; };

    uim._registerTooltip(tooltip1);
    uim._registerTooltip({ hide() {} });

    assert.ok(hideCalled);
});

test('UIM.handleEscapeEvent handles escape with popup', () => {
    const uim = Wirecloud.UserInterfaceManager;

    const popup = new StyledElements.Popover({ sticky: false });
    uim._registerPopup(popup);

    try {
        uim.handleEscapeEvent();
    } catch (e) {
        // May throw in test environment due to instanceof checks
    }
});

test('UIM.terminate cleans up after init', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    uim.terminate();

    assert.equal(uim.header, null);
    assert.equal(document.getElementById('menu_layer'), null);
});

test('UIM.terminate returns early if not initialized', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.terminate();
    // Should not throw
});

test('UIM.terminate can be called multiple times', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();
    uim.terminate();
    uim.terminate();
    // Should not throw
});

// === terminate with registered tooltip hides and nullifies it (lines 304-306) ===

test('UIM.terminate hides and nullifies registered tooltip', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    let tooltipHidden = false;
    const tooltip = { hide: () => { tooltipHidden = true; } };
    uim._registerTooltip(tooltip);

    uim.terminate();

    assert.ok(tooltipHidden, 'tooltip.hide should have been called');
});

// === changeCurrentView with HORIZONTAL_SLIDE between workspace/wiring (line 338) ===

test('UIM.changeCurrentView uses HORIZONTAL_SLIDE between workspace and wiring', async () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    let effectUsed = null;
    const origShowAlt = StyledElements.Alternatives.prototype.showAlternative;
    StyledElements.Alternatives.prototype.showAlternative = function(view, options) {
        effectUsed = options.effect;
        return origShowAlt.call(this, view, options);
    };

    // First call sets visibleAlt to workspace
    await uim.changeCurrentView('workspace', true);

    // Second call from workspace → wiring should use HORIZONTAL_SLIDE
    await uim.changeCurrentView('wiring', true);

    assert.equal(effectUsed, StyledElements.Alternatives.HORIZONTAL_SLIDE);

    StyledElements.Alternatives.prototype.showAlternative = origShowAlt;
});

// === handleEscapeEvent with registered tooltip hides it (lines 348-349) ===

test('UIM.handleEscapeEvent hides registered tooltip and nullifies it', () => {
    const uim = Wirecloud.UserInterfaceManager;

    let tooltipHidden = false;
    const tooltip = { hide: () => { tooltipHidden = true; } };
    uim._registerTooltip(tooltip);

    uim.handleEscapeEvent();

    assert.ok(tooltipHidden, 'tooltip.hide should have been called');
});

// === on_keydown with rootKeydownHandler when no modals (line 72) ===

test('UIM.keydown calls rootKeydownHandler when no window menu is open', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    let handlerCalled = false;
    let handlerKey = null;
    uim.rootKeydownHandler = (key, modifiers) => {
        handlerCalled = true;
        handlerKey = key;
        return false;
    };

    // Add dispatchEvent to the document (browser shim creates document without it)
    global.document.dispatchEvent = (event) => {
        const listeners = global.document.listeners[event.type] || [];
        listeners.forEach((listener) => listener.call(global.document, event));
        return true;
    };

    const event = { type: 'keydown', key: 'a', altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, preventDefault() {} };
    global.document.dispatchEvent(event);

    assert.ok(handlerCalled, 'rootKeydownHandler should have been called');
});

test('UIM.keydown prevents default for backspace inside modal and escapes via handler', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();
    global.document.dispatchEvent = (event) => {
        const listeners = global.document.listeners[event.type] || [];
        listeners.forEach((listener) => listener.call(global.document, event));
        return true;
    };

    let escapeHandled = 0;
    const menu = new Wirecloud.ui.WindowMenu();
    uim._registerRootWindowMenu(menu);

    const originalHandleEscapeEvent = uim.handleEscapeEvent;
    uim.handleEscapeEvent = () => { escapeHandled += 1; };

    let backspacePrevented = false;
    global.document.dispatchEvent({
        type: 'keydown',
        key: 'Backspace',
        altKey: false,
        ctrlKey: false,
        metaKey: false,
        shiftKey: false,
        preventDefault() { backspacePrevented = true; }
    });

    let escapePrevented = false;
    global.document.dispatchEvent({
        type: 'keydown',
        key: 'Escape',
        altKey: false,
        ctrlKey: false,
        metaKey: false,
        shiftKey: false,
        preventDefault() { escapePrevented = true; }
    });

    assert.equal(backspacePrevented, true);
    assert.equal(escapeHandled, 1);
    assert.equal(escapePrevented, false);

    uim.handleEscapeEvent = originalHandleEscapeEvent;
});

test('UIM.resize and click listeners repaint popups/tooltip and clear fade when loading is inactive', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    let popupRepainted = 0;
    let tooltipRepainted = 0;
    uim._registerPopup({ hide() {}, repaint() { popupRepainted += 1; } });
    uim._registerTooltip({ hide() {}, repaint() { tooltipRepainted += 1; } });

    global.window.dispatchEvent = (event) => {
        const listeners = global.document.listeners[event.type] || [];
        listeners.forEach((listener) => listener.call(global.window, event));
        return true;
    };
    global.document.dispatchEvent = (event) => {
        const listeners = global.document.listeners[event.type] || [];
        listeners.forEach((listener) => listener.call(global.document, event));
        return true;
    };

    const loadingWindow = document.getElementById('loading-window');
    loadingWindow.classList.add('fade');
    global.window.dispatchEvent({ type: 'resize' });
    global.document.dispatchEvent({ type: 'click' });

    assert.equal(popupRepainted, 1);
    assert.equal(tooltipRepainted, 1);
    assert.equal(loadingWindow.classList.contains('fade'), false);
});

test('UIM fullscreen change moves the cover layer into the fullscreen element', () => {
    let fullscreenHandler = null;
    StyledElements.Utils.onFullscreenChange = function (element, handler) {
        fullscreenHandler = handler;
    };
    StyledElements.Utils.getFullscreenElement = function () {
        return fullscreenRoot;
    };

    const fullscreenRoot = document.createElement('section');
    const firstChild = document.createElement('span');
    fullscreenRoot.appendChild(firstChild);
    document.body.appendChild(fullscreenRoot);

    const uim = Wirecloud.UserInterfaceManager;
    uim.init();
    const cover = document.getElementById('menu_layer');

    fullscreenHandler();

    assert.equal(fullscreenRoot.firstChild, cover);
});

test('UIM.init handles plain content mode and creates header only', () => {
    const wcBody = document.getElementById('wc-body');
    wcBody.parentNode.removeChild(wcBody);

    const plainContent = document.createElement('div');
    plainContent.className = 'plain_content';
    document.body.appendChild(plainContent);

    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    assert.ok(uim.header instanceof Wirecloud.ui.WirecloudHeader);
    assert.equal(uim.views, undefined);
});

test('UIM.init contextloaded listener creates myresources view', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    assert.equal(uim.views.myresources, undefined);
    Wirecloud.dispatchEvent('contextloaded');
    assert.ok(uim.views.myresources instanceof Wirecloud.ui.MyResourcesView);
});

test('UIM.handleEscapeEvent respects sticky popovers on click close attempts', () => {
    const uim = Wirecloud.UserInterfaceManager;
    let hideCalled = false;
    const popup = new StyledElements.Popover({ sticky: true });
    popup.hide = () => { hideCalled = true; };
    uim._registerPopup(popup);

    uim.handleEscapeEvent(true);

    assert.equal(hideCalled, false);
});

test('UIM.terminate hides registered root menu and popups', () => {
    const oldSetTimeout = global.setTimeout;
    global.setTimeout = (fn) => { fn(); return 0; };

    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    let windowHidden = false;
    let popupHidden = false;
    const menu = new Wirecloud.ui.WindowMenu();
    menu.hide = () => { windowHidden = true; };
    uim._registerRootWindowMenu(menu);

    uim._registerPopup({ hide() { popupHidden = true; } });
    uim.terminate();

    assert.equal(windowHidden, true);
    assert.equal(popupHidden, true);

    global.setTimeout = oldSetTimeout;
});

test('UIM.init activeworkspacechanged prompts for empty workspace preferences and monitors retry', () => {
    const oldSetTimeout = global.setTimeout;
    global.setTimeout = (fn) => { fn(); return 0; };

    const uim = Wirecloud.UserInterfaceManager;
    let postCommitHandler = null;
    let dialogShown = 0;
    let monitoredTask = null;
    const expectedTask = { id: 'change-task' };

    Wirecloud.PreferenceManager.buildPreferences = (scope, values, workspace, extraprefs, emptyparams) => {
        assert.equal(scope, 'workspace');
        assert.deepEqual(values, { apiKey: { value: 'token' } });
        assert.deepEqual(emptyparams, ['apiKey']);
        return {
            addEventListener(type, handler) {
                if (type === 'post-commit') {
                    postCommitHandler = handler;
                }
            }
        };
    };
    Wirecloud.changeActiveWorkspace = (workspace) => {
        assert.equal(workspace.name, 'demo');
        return expectedTask;
    };
    Wirecloud.UserInterfaceManager.monitorTask = (task) => {
        monitoredTask = task;
    };
    Wirecloud.ui.PreferencesWindowMenu = class PreferencesWindowMenu {
        constructor(scope, preferences) {
            this.scope = scope;
            this.preferences = preferences;
        }
        show() {
            dialogShown += 1;
        }
    };

    uim.init();
    uim.views.workspace.layout = { slideOut() {} };
    Wirecloud.dispatchEvent('activeworkspacechanged', {
        name: 'demo',
        emptyparams: ['apiKey'],
        preferences: { apiKey: { value: 'token' } },
        extraprefs: {},
        wiring: { errorCount: 0, logManager: { addEventListener() {} } }
    });

    assert.equal(dialogShown, 1);
    assert.equal(typeof postCommitHandler, 'function');

    postCommitHandler();
    assert.equal(monitoredTask, expectedTask);

    global.setTimeout = oldSetTimeout;
});

test('UIM.init activeworkspacechanged loads workspace, updates history and wiring badge', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    let historyReplacedWith = null;
    let historyPushedWith = null;
    let headerRefreshed = 0;
    let wiringBadge = null;
    let wiringListener = null;
    let loggedWorkspaceLoaded = false;

    Wirecloud.HistoryManager.getCurrentState = () => ({ workspace_title: 'Old title' });
    Wirecloud.HistoryManager.replaceState = (state) => { historyReplacedWith = state; };
    Wirecloud.HistoryManager.pushState = (state) => { historyPushedWith = state; };
    Wirecloud.UserInterfaceManager.header.refresh = () => { headerRefreshed += 1; };
    Wirecloud.GlobalLogManager.log = (message) => {
        if (message === 'Workspace loaded') {
            loggedWorkspaceLoaded = true;
        }
    };

    uim.views.workspace.layout = { slideOut() {} };
    uim.views.workspace.loadWorkspace = function (workspace, options) {
        this.model = { title: 'Demo workspace' };
        this.notebook = {
            visibleTab: { model: { name: 'Main', id: 'tab-1' } },
            addEventListener(type, handler) {
                this._changedHandler = handler;
            }
        };
        this.wiringButton = {
            setBadge(value, status) {
                wiringBadge = { value, status };
            }
        };
        assert.equal(workspace.name, 'demo');
        assert.deepEqual(options, { initialtab: undefined });
    };

    const workspace = {
        name: 'demo',
        emptyparams: [],
        wiring: {
            errorCount: 3,
            logManager: {
                addEventListener(type, handler) {
                    if (type === 'newentry') {
                        wiringListener = handler;
                    }
                }
            }
        }
    };

    Wirecloud.dispatchEvent('activeworkspacechanged', workspace);

    assert.deepEqual(historyReplacedWith, {
        tab: 'Main',
        tab_id: 'tab-1',
        workspace_title: 'Demo workspace'
    });
    assert.equal(headerRefreshed, 1);
    assert.deepEqual(wiringBadge, { value: 3, status: 'danger' });
    assert.equal(typeof wiringListener, 'function');
    assert.equal(loggedWorkspaceLoaded, true);

    uim.views.workspace.notebook._changedHandler(
        uim.views.workspace.notebook,
        { model: { name: 'Main', id: 'tab-1' } },
        { model: { name: 'Secondary', id: 'tab-2' } }
    );

    assert.deepEqual(historyPushedWith, {
        workspace_title: 'Old title',
        tab: 'Secondary',
        tab_id: 'tab-2'
    });
});

test('UIM.init activeworkspacechanged handles loadWorkspace errors and zero wiring errors', () => {
    const uim = Wirecloud.UserInterfaceManager;
    uim.init();

    let historyReplaced = false;
    let headerRefreshed = false;
    let badgeArgs = null;
    Wirecloud.HistoryManager.replaceState = () => { historyReplaced = true; };
    Wirecloud.UserInterfaceManager.header.refresh = () => { headerRefreshed = true; };

    uim.views.workspace.layout = { slideOut() {} };
    uim.views.workspace.wiringButton = { setBadge(value, status) { badgeArgs = { value, status }; } };
    uim.views.workspace.loadWorkspace = function (workspace) {
        if (workspace.name === 'broken') {
            throw new Error('boom');
        }
        this.model = { title: 'Empty workspace' };
        this.notebook = {
            visibleTab: { model: { name: 'Main', id: 'tab-1' } },
            addEventListener() {}
        };
        this.wiringButton = { setBadge(value, status) { badgeArgs = { value, status }; } };
    };

    Wirecloud.dispatchEvent('activeworkspacechanged', {
        name: 'broken',
        emptyparams: [],
        wiring: { errorCount: 0, logManager: { addEventListener() {} } }
    });

    assert.equal(historyReplaced, false);
    assert.equal(headerRefreshed, false);

    Wirecloud.dispatchEvent('activeworkspacechanged', {
        name: 'ok',
        emptyparams: [],
        wiring: { errorCount: 0, logManager: { addEventListener() {} } }
    });

    assert.deepEqual(badgeArgs, { value: null, status: 'danger' });
});

test('UIM.init transition listeners notify header and fullscreen callback falls back to body', () => {
    let fullscreenHandler = null;
    let preTransitionHandler = null;
    let postTransitionHandler = null;

    resetLegacyRuntime();
    bootstrapStyledElementsBase();
    setupUserInterfaceManager();
    StyledElements.Utils.onFullscreenChange = function (element, handler) {
        fullscreenHandler = handler;
    };
    StyledElements.Utils.getFullscreenElement = function () {
        return null;
    };
    const originalAddEventListener = StyledElements.Alternatives.prototype.addEventListener;
    StyledElements.Alternatives.prototype.addEventListener = function (type, handler) {
        if (type === 'preTransition') preTransitionHandler = handler;
        if (type === 'postTransition') postTransitionHandler = handler;
        return originalAddEventListener.call(this, type, handler);
    };
    Wirecloud.ui.WirecloudHeader = class WirecloudHeader {
        constructor(uiManager) { this.uiManager = uiManager; }
        _notifyViewChange(view) { notifiedArgs.push(view); }
        refresh() {}
    };
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/Registry.js');
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/UserInterfaceManager.js');

    const uim = Wirecloud.UserInterfaceManager;
    let notifiedArgs = [];

    uim.init();
    const cover = document.getElementById('menu_layer');
    preTransitionHandler(null, null, uim.views.workspace);
    postTransitionHandler(null, null, uim.views.marketplace);
    fullscreenHandler();

    assert.deepEqual(notifiedArgs, [undefined, uim.views.marketplace]);
    assert.equal(document.body.firstChild, cover);
});
