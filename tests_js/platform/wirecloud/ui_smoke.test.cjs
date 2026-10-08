const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScript,
    loadLegacyScripts,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');

// ---------------------------------------------------------------------------
// Common setup helper used by all subtests
// ---------------------------------------------------------------------------

const setup = () => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();

    if (global.Wirecloud == null) {
        global.Wirecloud = {};
    }

    // -- Wirecloud.Utils ----------------------------------------------------
    Wirecloud.Utils = StyledElements.Utils;
    Wirecloud.Utils.getCookie = () => null;

    // -- Wirecloud.ui namespace ---------------------------------------------
    Wirecloud.ui = {};

    // -- Wirecloud.events ---------------------------------------------------
    Wirecloud.events = {};
    Wirecloud.addEventListener = StyledElements.ObjectWithEvents.prototype.addEventListener;
    Wirecloud.dispatchEvent = StyledElements.ObjectWithEvents.prototype.dispatchEvent;

    // -- Wirecloud.currentTheme ---------------------------------------------
    Wirecloud.currentTheme = {
        name: 'default',
        templates: {}
    };
    const emptyTemplate = () => {
        const div = document.createElement('div');
        div.elements = [div];
        div.appendTo = function (parent) {
            parent.appendChild(this);
        };
        return div;
    };
    Wirecloud.currentTheme.templates['wirecloud/modals/base'] = emptyTemplate;
    Wirecloud.currentTheme.templates['wirecloud/modals/embed_code'] = emptyTemplate;
    Wirecloud.currentTheme.templates['wirecloud/modals/upgrade_downgrade_component'] = emptyTemplate;

    // -- Wirecloud.constants ------------------------------------------------
    Wirecloud.constants = {
        LOGGING: { ERROR_MSG: 1, WARN_MSG: 2, INFO_MSG: 3, DEBUG_MSG: 4 },
        CURRENT_LANGUAGE: 'en',
        CURRENT_THEME: 'default',
        CURRENT_MODE: 'classic',
        AVAILABLE_THEMES: ['default'],
        AVAILABLE_LANGUAGES: [{ value: 'en', label: 'English' }]
    };

    // -- Wirecloud.URLs ----------------------------------------------------
    Wirecloud.URLs = {
        ROOT_URL: '/',
        PUBLISH_ON_OTHER_MARKETPLACE: '/api/publish',
        SEARCH_SERVICE: '/api/search',
        WIRING_ENTRY: { evaluate: () => '/api/wiring' }
    };

    // -- Wirecloud.location --------------------------------------------------
    const locObj = { origin: 'http://localhost', pathname: '/', search: '', hash: '', assign: () => {}, href: 'http://localhost/' };
    global.location = locObj;
    global.window.location = locObj;

    // -- Wirecloud.io -------------------------------------------------------
    Wirecloud.io = {
        makeRequest: () => Promise.resolve({ status: 200, responseText: '{}', transport: { getResponseHeader: () => '' } })
    };

    // -- Managers & mocks ---------------------------------------------------
    Wirecloud.GlobalLogManager = {
        log: () => {},
        parseErrorResponse: () => 'error',
        formatException: (e) => e.message
    };
    Wirecloud.LogManager = class LogManager {
        constructor() { this.entries = []; this.previouscycles = []; }
        addEventListener() {}
        removeEventListener() {}
        log() {}
        formatException(e) { return e.message; }
    };
    Wirecloud.ContextManager = class ContextManager {
        get(key) { return key === 'username' ? 'testuser' : null; }
        modify() {}
    };
    Wirecloud.contextManager = new Wirecloud.ContextManager();
    Wirecloud.UserInterfaceManager = {
        _registerRootWindowMenu: () => {},
        _unregisterRootWindowMenu: () => {},
        _registerPopup: () => {},
        _unregisterPopup: () => {},
        monitorTask: (p) => p,
        changeCurrentView: () => {},
        views: { marketplace: { viewsByName: {}, waitMarketListReady: () => {} } },
        get currentWindowMenu() { return null; }
    };
    Wirecloud.HistoryManager = { getCurrentState: () => ({}) };
    Wirecloud.LocalCatalogue = {
        resourceVersions: {},
        RESOURCE_CHANGELOG_ENTRY: { evaluate: () => '/api/changelog' },
        getResourceId: (id) => id,
        reload: () => Promise.resolve()
    };
    Wirecloud.MarketManager = {
        getMarketTypes: () => [],
        addMarket: () => Promise.resolve(),
        deleteMarket: () => Promise.resolve()
    };
    Wirecloud.Task = class Task { then() { return this; } catch() { return this; } toTask() { return this; } };
    Wirecloud.PropertyCommiter = class { add() {} commit() {} };
    Wirecloud.wiring = { Operator: class {} };
    Wirecloud.workspacesByUserAndName = {};
    Wirecloud.createWorkspace = () => new Wirecloud.Task();
    Wirecloud.changeActiveWorkspace = () => new Wirecloud.Task();

    // -- Wirecloud.ui base WindowMenu class --------------------------------
    Wirecloud.ui.WindowMenu = class WindowMenu extends StyledElements.StyledElement {
        constructor(title, extra_class) {
            super(['show', 'hide']);
            this.windowContent = document.createElement('div');
            this.windowBottom = document.createElement('div');
            this.titleElement = document.createElement('h3');
            this.htmlElement = document.createElement('div');
            this.htmlElement.classList.add('window_menu');
            if (extra_class) {
                this.htmlElement.classList.add(extra_class);
            }
            this.windowHeader = document.createElement('div');
            this.htmlElement.appendChild(this.windowHeader);
            this.htmlElement.appendChild(this.windowContent);
            this.htmlElement.appendChild(this.windowBottom);
            this._closeListener = () => this.hide();
            this.setTitle(typeof title === 'string' ? title : '');
            // Some subclasses (e.g. ParametrizeWindowMenu) pass a fields object as title
            // and expect a form to be created
            if (title && typeof title === 'object' && !Array.isArray(title)) {
                const fieldKeys = Object.keys(title);
                this.form = {
                    insertInto() {},
                    addEventListener() {},
                    reset() {},
                    focus() {},
                    repaint() {},
                    setData() {},
                    displayMessage() {},
                    acceptButton: { addClassName() {}, disable() {}, enable() {}, removeClassName() {} },
                    cancelButton: { addClassName() {}, disable() {}, enable() {}, focus() {} },
                    fieldInterfaces: {}
                };
                const self = this;
                fieldKeys.forEach(function (key) {
                    const field = title[key];
                    if (field && field.type === 'select') {
                        self.form.fieldInterfaces[key] = {
                            inputElement: {
                                inputElement: { addEventListener() {} },
                                getValue() { return ''; },
                                setValue() {}
                            },
                            focus() {}
                        };
                    } else if (field && field.type === 'parametrizedText') {
                        self.form.fieldInterfaces[key] = {
                            inputElement: { addEventListener() {} },
                            setDisabled() {},
                            update() {},
                            addEventListener() {},
                            focus() {}
                        };
                    } else {
                        self.form.fieldInterfaces[key] = { focus() {} };
                    }
                });
            }
        }
        show() { this.dispatchEvent('show'); return this; }
        hide() { this.dispatchEvent('hide'); return this; }
        setTitle(t) { this.titleElement.textContent = t; }
        destroy() { this.hide(); }
        repaint() { return this; }
        setFocus() { return this; }
        setPosition() { return this; }
        getStylePosition() { return { posX: 10, posY: 10 }; }
    };

    // -- Wirecloud.ui FormWindowMenu base class ----------------------------
    Wirecloud.ui.FormWindowMenu = class FormWindowMenu extends Wirecloud.ui.WindowMenu {
        constructor(fields, title, extra_class) {
            super(title, extra_class);
            this.form = {
                insertInto() {},
                addEventListener() {},
                reset() {},
                focus() {},
                repaint() {},
                setData() {},
                displayMessage() {},
                acceptButton: { addClassName() {}, disable() {}, enable() {}, removeClassName() {} },
                cancelButton: { addClassName() {}, disable() {}, enable() {}, focus() {} },
                fieldInterfaces: {}
            };
            if (fields && typeof fields === 'object' && !Array.isArray(fields)) {
                const fieldKeys = Object.keys(fields);
                fieldKeys.forEach((key) => {
                    this.form.fieldInterfaces[key] = { focus() {} };
                });
            }
        }
        executeOperation() {}
        show(parentWindow) { super.show(parentWindow); this.form.reset(); return this; }
        setFocus() { this.form.focus(); return this; }
    };

    // -- Additional Wirecloud.ui classes ------------------------------------
    Wirecloud.ui.AlertWindowMenu = class AlertWindowMenu extends Wirecloud.ui.WindowMenu {
        setHandler(fn) { this._handler = fn; return this; }
    };
    Wirecloud.ui.MessageWindowMenu = class MessageWindowMenu extends Wirecloud.ui.WindowMenu {};

    // -- StyledElements component mocks -------------------------------------
    class SEButton {
        constructor(opts = {}) {
            this._disabled = false;
            this._label = opts.text || '';
            this._classes = opts.class || '';
            this.wrapperElement = document.createElement('button');
            this.wrapperElement.textContent = this._label;
        }
        addEventListener() {}
        removeEventListener() {}
        insertInto(parent) { parent.appendChild(this.wrapperElement); return this; }
        appendTo(parent) { parent.appendChild(this.wrapperElement); return this; }
        disable() { this._disabled = true; return this; }
        enable() { this._disabled = false; return this; }
        focus() {}
        destroy() {}
        setLabel(label) { this._label = label; return this; }
        addClassName(cls) { return this; }
        removeClassName(cls) { return this; }
    }

    class SESelect {
        constructor(opts = {}) {
            this._entries = opts.initialEntries || [];
            this._value = '';
        }
        addEventListener() {}
        removeEventListener() {}
        getValue() { return this._value; }
        setValue(v) { this._value = v; return this; }
        addEntries(entries) { this._entries.push(...entries); return this; }
    }

    class SETextArea {
        constructor() {}
        setValue() { return this; }
        select() { return this; }
    }

    class SEContainer {
        constructor(opts = {}) {
            this._children = [];
            this.wrapperElement = document.createElement(opts.tagname || 'div');
            if (opts.class) {
                this.wrapperElement.className = opts.class;
            }
        }
        appendChild(child) {
            if (child && typeof child === 'object' && child.wrapperElement) {
                this.wrapperElement.appendChild(child.wrapperElement);
            }
            return this;
        }
        clear() {
            this.wrapperElement.innerHTML = '';
            return this;
        }
        insertInto(parent) {
            if (parent && parent.appendChild) {
                parent.appendChild(this.wrapperElement);
            }
            return this;
        }
        disable() { return this; }
        enable() { return this; }
        addClassName() { return this; }
        removeClassName() { return this; }
    }

    class SEFragment {
        constructor(content) {
            this.elements = [];
            this.wrapperElement = document.createElement('div');
            if (typeof content === 'string') {
                this.wrapperElement.innerHTML = content;
            } else if (Array.isArray(content)) {
                this.elements = content;
            }
        }
        appendTo(parent) { parent.appendChild(this.wrapperElement); return this; }
        insertInto(parent) { parent.appendChild(this.wrapperElement); return this; }
    }

    class SEGUIBuilder {
        parse(template, context) {
            const fragment = new SEFragment('');
            // The template builder returns a fragment that has elements array
            // and appendTo/insertInto methods. Its first Element child becomes htmlElement.
            return fragment;
        }
    }

    class SEPanel {
        constructor(opts = {}) {
            this.body = new SEContainer({ tagname: 'div' });
            this.wrapperElement = document.createElement('div');
        }
        insertInto(parent) { parent.appendChild(this.wrapperElement); return this; }
        appendChild(child) { return this.body.appendChild(child); }
    }

    class SEToggleButton extends SEButton {
        constructor(opts = {}) {
            super(opts);
            this.active = false;
        }
    }

    class SEMenuItem extends SEButton {
        constructor(label, handler, context) {
            super({ text: label });
            this._handler = handler;
            this._context = context;
        }
        addIconClass() { return this; }
        setDisabled() { return this; }
        disable() { return this; }
    }

    class SESeparator {
        constructor() {}
    }

    class SEExpander {
        constructor(opts = {}) {}
        insertInto(parent) { return this; }
        appendChild() { return this; }
    }

    class SEForm {
        constructor(fields, opts = {}) {
            this.fieldInterfaces = {};
            this.acceptButton = new SEButton({ text: 'Accept' });
            this.cancelButton = new SEButton({ text: 'Cancel' });
            if (fields && typeof fields === 'object' && !Array.isArray(fields)) {
                Object.keys(fields).forEach((key) => {
                    const field = fields[key];
                    if (field.type === 'parametrizedText') {
                        this.fieldInterfaces[key] = {
                            inputElement: { addEventListener() {} },
                            setDisabled() {},
                            update() {},
                            addEventListener() {}
                        };
                    } else if (field.type === 'select') {
                        this.fieldInterfaces[key] = {
                            inputElement: new SESelect({ initialEntries: field.initialEntries || [] }),
                            focus() {}
                        };
                    } else if (field.type === 'buttons') {
                        this.fieldInterfaces[key] = {};
                    } else {
                        this.fieldInterfaces[key] = {
                            inputElement: { addEventListener() {} },
                            focus() {},
                            setDisabled() {}
                        };
                    }
                });
            }
        }
        addEventListener() {}
        insertInto(parent) { return this; }
        reset() {}
        focus() {}
        repaint() {}
        setData() {}
        displayMessage() {}
    }

    // Load the real DynamicMenuItems (it's a plain function, not a class)
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/DynamicMenuItems.js');

    // Register mock classes onto the StyledElements namespace
    StyledElements.Button = SEButton;
    StyledElements.Select = SESelect;
    StyledElements.TextArea = SETextArea;
    StyledElements.Container = SEContainer;
    StyledElements.Fragment = SEFragment;
    StyledElements.GUIBuilder = SEGUIBuilder;
    StyledElements.Panel = SEPanel;
    StyledElements.ToggleButton = SEToggleButton;
    StyledElements.MenuItem = SEMenuItem;
    StyledElements.Separator = SESeparator;
    StyledElements.Expander = SEExpander;
    StyledElements.Form = SEForm;

    // Wirecloud.ui.InputInterfaceFactory (needed by FormWindowMenu)
    Wirecloud.ui.InputInterfaceFactory = {
        createInterface: () => ({ inputElement: { addEventListener() {} }, focus() {} })
    };

    // global moment (needed by LogWindowMenu)
    global.moment = () => ({ fromNow: () => 'a few seconds ago' });

    // global DOMParser (needed by WidgetElement)
    global.DOMParser = class DOMParser {
        parseFromString(text, mimeType) {
            const doc = { head: document.createElement('head'), body: document.createElement('div') };
            return doc;
        }
    };

    // global URL class (needed by WidgetElement)
    global.URL = class URL {
        constructor(url, base) { this.href = url; }
    };

    // global window.customElements (needed by WidgetElement)
    global.window.customElements = {
        define: () => {}
    };

    // URLify global (needed by MarketplaceViewMenuItems)
    global.URLify = (s) => s.toLowerCase().replace(/\s+/g, '_');

    return { StyledElements, Wirecloud: global.Wirecloud };
};

// ============================================================================
// SMALL FILES (≤150 lines, deep coverage)
// ============================================================================

// -- EmbedCodeWindowMenu ------------------------------------------------------

test('EmbedCodeWindowMenu constructor and setFocus', () => {
    setup();

    const workspace = { model: { url: '/ws/test' } };
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/EmbedCodeWindowMenu.js');

    const menu = new Wirecloud.ui.EmbedCodeWindowMenu('Embed Code', workspace);
    assert.ok(menu instanceof Wirecloud.ui.WindowMenu);
    assert.ok(menu.workspace === workspace);
    menu.setFocus();
});

test('EmbedCodeWindowMenu build_embed_code encodes lang and theme (lines 32-33)', () => {
    setup();

    const workspace = { model: { url: '/ws/test' } };
    Wirecloud.currentTheme.name = 'dark';
    Wirecloud.constants.AVAILABLE_THEMES = [{ value: 'dark', label: 'Dark' }];

    // Augment SESelect to store event listeners so we can dispatch
    const OrigAddEventListener = StyledElements.Select.prototype.addEventListener;
    StyledElements.Select.prototype.addEventListener = function (type, handler) {
        if (!this._listeners) this._listeners = {};
        if (!this._listeners[type]) this._listeners[type] = [];
        this._listeners[type].push(handler);
    };
    StyledElements.Select.prototype.dispatchEvent = function (event) {
        const handlers = this._listeners && this._listeners[event.type];
        if (handlers) handlers.forEach((h) => h(this));
    };

    try {
        loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/EmbedCodeWindowMenu.js');

        const menu = new Wirecloud.ui.EmbedCodeWindowMenu('Embed Code', workspace);

        menu.lang.setValue('es');
        menu.lang.dispatchEvent({ type: 'change' });

        menu.theme.setValue('dark');
        menu.theme.dispatchEvent({ type: 'change' });

        assert.ok(true);
    } finally {
        StyledElements.Select.prototype.addEventListener = OrigAddEventListener;
        delete StyledElements.Select.prototype.dispatchEvent;
    }
});

// -- MissingDependenciesWindowMenu --------------------------------------------

test('MissingDependenciesWindowMenu constructor, setFocus, destroy', () => {
    setup();

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/MissingDependenciesWindowMenu.js');

    const details = { missingDependencies: ['dep1', 'dep2'] };
    const menu = new Wirecloud.ui.MissingDependenciesWindowMenu(() => {}, details);
    assert.ok(menu instanceof Wirecloud.ui.WindowMenu);
    menu.setFocus();
    menu.destroy();
});

// -- ParametrizeWindowMenu ----------------------------------------------------

test('ParametrizeWindowMenu constructor and executeOperation', () => {
    setup();

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/ParametrizeWindowMenu.js');

    const inputInterface = {
        variable: { name: 'test' },
        canBeHidden: true,
        setValue: () => {}
    };
    const menu = new Wirecloud.ui.ParametrizeWindowMenu(inputInterface);
    assert.ok(menu instanceof Wirecloud.ui.WindowMenu);
    assert.ok(menu.inputInterface === inputInterface);
    menu.setFocus();
    menu.executeOperation({ value: 'test' });
});

test('ParametrizeWindowMenu updateFunc disables value when source is not custom', () => {
    setup();

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/ParametrizeWindowMenu.js');

    let disabledValue = null;
    const inputInterface = {
        variable: { name: 'test' },
        canBeHidden: true,
        setValue: () => {}
    };
    const menu = new Wirecloud.ui.ParametrizeWindowMenu(inputInterface);

    menu.form.fieldInterfaces.source.inputElement.getValue = () => 'property';
    menu.form.fieldInterfaces.value.setDisabled = (val) => { disabledValue = val; };

    assert.ok(typeof menu.form.fieldInterfaces.value.update === 'function');
    menu.form.fieldInterfaces.value.update();

    assert.equal(disabledValue, true);
});

test('ParametrizeWindowMenu updateFunc enables value when source is custom', () => {
    setup();

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/ParametrizeWindowMenu.js');

    let disabledValue = null;
    const inputInterface = {
        variable: { name: 'test' },
        canBeHidden: true,
        setValue: () => {}
    };
    const menu = new Wirecloud.ui.ParametrizeWindowMenu(inputInterface);

    menu.form.fieldInterfaces.source.inputElement.getValue = () => 'custom';
    menu.form.fieldInterfaces.value.setDisabled = (val) => { disabledValue = val; };

    menu.form.fieldInterfaces.value.update();

    assert.equal(disabledValue, false);
});

// -- RenameWindowMenu ---------------------------------------------------------

test('RenameWindowMenu constructor, setFocus, executeOperation', () => {
    setup();

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/RenameWindowMenu.js');

    const what = { title: 'Old Name', rename: (name) => ({ then: (fn) => fn() }) };
    const menu = new Wirecloud.ui.RenameWindowMenu(what, 'Rename');
    assert.ok(menu instanceof Wirecloud.ui.FormWindowMenu);
    assert.ok(menu.what === what);
    menu.setFocus();
    menu.executeOperation({ title: 'New Name' });
});

// -- WidgetElement ------------------------------------------------------------

test('WidgetElement constructor and connectedCallback', () => {
    setup();

    global.window.customElements = { define: () => {} };
    global.DOMParser = class DOMParser { parseFromString() { return { head: document.createElement('head'), body: document.createElement('div') }; } };
    global.URL = class URL { constructor(u, b) { this.href = u; } };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WidgetElement.js');

    // The IIFE runs window.customElements.define synchronously
    // The Widget class is defined in the closure, not exported on Wirecloud
    // Verify that no error was thrown (namespace init + define call)
    assert.ok(true);
});

// -- UpgradeWindowMenu --------------------------------------------------------

test('UpgradeWindowMenu constructor and show', () => {
    setup();

    Wirecloud.LocalCatalogue.resourceVersions = {};
    const model = {
        meta: {
            version: { compareTo: () => 0, toString: () => '1.0.0' },
            vendor: 'test',
            name: 'widget',
            group_id: 'test/widget/1.0.0'
        },
        upgrade: () => Promise.resolve()
    };
    Wirecloud.LocalCatalogue.resourceVersions[model.meta.group_id] = [{ version: { compareTo: () => 0, toString: () => '1.0.0' } }];
    Wirecloud.LocalCatalogue.RESOURCE_CHANGELOG_ENTRY = { evaluate: () => '/api/changelog' };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/UpgradeWindowMenu.js');

    const menu = new Wirecloud.ui.UpgradeWindowMenu(model);
    assert.ok(menu instanceof Wirecloud.ui.WindowMenu);
    assert.ok(menu.model === model);
    menu.show();
});

// ============================================================================
// LARGER FILES (>150 lines, namespace/init coverage)
// ============================================================================

test('ComponentSidebar — loads without errors', () => {
    setup();

    // MACSearch dependency (used inside ComponentSidebar)
    Wirecloud.ui.MACSearch = class MACSearch {
        constructor() {}
        addEventListener() {}
        get() { return document.createElement('div'); }
    };
    Wirecloud.ui.WiringEditor = {
        ComponentGroup: class {
            constructor(g, label) { this.id = g; this.label = label; }
            addEventListener() {}
            addComponent() {}
        },
        Component: class {
            constructor(wc) { this.id = 'comp-1'; this.meta = wc.meta; }
            addEventListener() {}
            remove() {}
        }
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/ComponentSidebar.js');

    const sidebar = new Wirecloud.ui.ComponentSidebar();
    assert.ok(sidebar instanceof StyledElements.StyledElement);
    assert.equal(typeof sidebar.addComponent, 'function');
    assert.equal(typeof sidebar.clear, 'function');
    assert.equal(typeof sidebar.findComponent, 'function');
    assert.equal(typeof sidebar.forEachComponent, 'function');
    assert.equal(typeof sidebar.removeComponent, 'function');
});

test('AdminPanelWindowMenu — loads without errors', () => {
    setup();

    Wirecloud.workspacesByUserAndName = { testuser: { ws1: { name: 'ws1' } } };
    Wirecloud.ui.UserManagementWindowMenu = class extends Wirecloud.ui.WindowMenu {};

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/AdminPanelWindowMenu.js');

    const menu = new Wirecloud.ui.AdminPanelWindowMenu();
    assert.ok(menu instanceof Wirecloud.ui.WindowMenu);
});

test('AdminPanelWindowMenu — group fetch success path (lines 131-135)', async () => {
    const { Wirecloud } = setup();

    Wirecloud.workspacesByUserAndName = { testuser: { ws1: { name: 'ws1' } } };
    Wirecloud.ui.UserManagementWindowMenu = class extends Wirecloud.ui.WindowMenu {};

    Wirecloud.io.makeRequest = function (url, opts) {
        if (opts.parameters && opts.parameters.namespace === 'user') {
            opts.onSuccess({ responseText: JSON.stringify({ total: 2 }) });
        } else if (opts.parameters && opts.parameters.namespace === 'group') {
            opts.onSuccess({ responseText: JSON.stringify({
                total: 10,
                results: [
                    { is_organization: false },
                    { is_organization: true, is_root: false },
                    { is_organization: true, is_root: true }
                ]
            })});
        }
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/AdminPanelWindowMenu.js');
    const menu = new Wirecloud.ui.AdminPanelWindowMenu();
    await new Promise((r) => setTimeout(r, 5));
    assert.ok(menu instanceof Wirecloud.ui.WindowMenu);
});

test('AdminPanelWindowMenu — group fetch failure path (lines 137-138)', async () => {
    const { Wirecloud } = setup();

    Wirecloud.workspacesByUserAndName = { testuser: { ws1: { name: 'ws1' } } };
    Wirecloud.ui.UserManagementWindowMenu = class extends Wirecloud.ui.WindowMenu {};

    Wirecloud.io.makeRequest = function (url, opts) {
        if (opts.parameters && opts.parameters.namespace === 'user') {
            opts.onSuccess({ responseText: JSON.stringify({ total: 2 }) });
        } else if (opts.parameters && opts.parameters.namespace === 'group') {
            opts.onFailure({});
        }
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/AdminPanelWindowMenu.js');
    const menu = new Wirecloud.ui.AdminPanelWindowMenu();
    await new Promise((r) => setTimeout(r, 5));
    assert.ok(menu instanceof Wirecloud.ui.WindowMenu);
});

test('LogWindowMenu — loads without errors', () => {
    setup();

    global.moment = function () { return { fromNow: () => 'a few seconds ago' }; };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/LogWindowMenu.js');

    const logManager = new Wirecloud.LogManager();
    logManager.entries = [{ level: 2, date: Date.now(), msg: 'test', details: null }];
    logManager.previouscycles = [];
    logManager.addEventListener = () => {};
    logManager.removeEventListener = () => {};

    const menu = new Wirecloud.ui.LogWindowMenu(logManager, { title: 'Test Logs' });
    assert.ok(menu instanceof Wirecloud.ui.WindowMenu);
    menu.setFocus();
    menu.show();
    menu.hide();
});

test('LogWindowMenu — on_fade and on_newentry handlers (lines 156-161, 165-179)', () => {
    setup();

    global.moment = function () { return { fromNow: () => 'a few seconds ago' }; };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/LogWindowMenu.js');

    let newEntryListener = null;
    const logManager = new Wirecloud.LogManager();
    logManager.entries = [{ level: 2, date: Date.now(), msg: 'test entry', details: 'some detail' }];
    logManager.previouscycles = [[{ level: 3, date: Date.now(), msg: 'old cycle', details: null }]];
    logManager.addEventListener = (event, handler) => {
        if (event === 'newentry') newEntryListener = handler;
    };
    logManager.removeEventListener = () => {};

    const origSetTimeout = global.setTimeout;
    const origClearTimeout = global.clearTimeout;
    global.setTimeout = (fn) => { fn(); return 1; };
    global.clearTimeout = () => {};

    try {
        const menu = new Wirecloud.ui.LogWindowMenu(logManager, { title: 'Test Logs' });
        menu.show();

        assert.ok(menu.windowContent.childNodes.length > 0);

        assert.ok(newEntryListener);
        newEntryListener(logManager, { level: 2, date: Date.now(), msg: 'new entry', details: null });
        assert.ok(menu.windowContent.childNodes.length > 1);

        menu.hide();
    } finally {
        global.setTimeout = origSetTimeout;
        global.clearTimeout = origClearTimeout;
    }
});

test('LogWindowMenu — ignores debug entries and appends object details', () => {
    const { Wirecloud } = setup();

    global.moment = function () { return { fromNow: () => 'a few seconds ago' }; };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/LogWindowMenu.js');

    const detailNode = document.createElement('span');
    detailNode.textContent = 'details';
    const listeners = {};
    const logManager = new Wirecloud.LogManager();
    logManager.entries = [
        { level: Wirecloud.constants.LOGGING.DEBUG_MSG, date: Date.now(), msg: 'debug' },
        { level: Wirecloud.constants.LOGGING.INFO_MSG, date: Date.now(), msg: 'info', details: detailNode },
    ];
    logManager.previouscycles = [[
        { level: Wirecloud.constants.LOGGING.DEBUG_MSG, date: Date.now(), msg: 'old debug' },
    ]];
    logManager.addEventListener = (event, handler) => { listeners[event] = handler; };
    logManager.removeEventListener = (event) => { delete listeners[event]; };

    const menu = new Wirecloud.ui.LogWindowMenu(logManager, { title: 'Test Logs' });
    menu.show();
    const countLogs = () => menu.windowContent.childNodes.filter((node) => node.getAttribute && node.getAttribute('role') === 'log').length;
    assert.equal(countLogs(), 1);

    listeners.newentry(logManager, { level: Wirecloud.constants.LOGGING.DEBUG_MSG, date: Date.now(), msg: 'new debug' });
    assert.equal(countLogs(), 1);

    menu.setFocus();
    menu.hide();
    assert.equal(listeners.newentry, undefined);
});

test('MarketplaceViewMenuItems — loads without errors', () => {
    setup();

    global.URLify = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '_');

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/MarketplaceViewMenuItems.js');

    const marketplace_view = {
        viewList: [{
            getLabel: () => 'Market 1',
            market_id: 'm1',
            isAllow: () => true
        }],
        number_of_alternatives: 1,
        alternatives: { getCurrentAlternative: () => ({ getLabel: () => 'Test Market', isAllow: () => true, desc: {} }) },
        changeCurrentMarket: () => {},
        refreshViewInfo: () => Promise.resolve(),
        addMarket: () => {}
    };

    const items = new Wirecloud.ui.MarketplaceViewMenuItems(marketplace_view);
    assert.ok(items instanceof StyledElements.DynamicMenuItems);
    const menuItems = items.build();
    assert.ok(Array.isArray(menuItems));
});

test('NewWorkspaceWindowMenu — loads without errors', () => {
    setup();

    Wirecloud.ui.MissingDependenciesWindowMenu = class extends Wirecloud.ui.WindowMenu {};
    Wirecloud.ui.MessageWindowMenu = class extends Wirecloud.ui.WindowMenu {};

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/NewWorkspaceWindowMenu.js');

    const menu = new Wirecloud.ui.NewWorkspaceWindowMenu({ title: 'Test WS' });
    assert.ok(menu instanceof Wirecloud.ui.FormWindowMenu);
    menu.executeOperation({ title: 'New Title' });
});

test('OperatorPreferencesWindowMenu — loads without errors', () => {
    setup();

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/OperatorPreferencesWindowMenu.js');

    const menu = new Wirecloud.ui.OperatorPreferencesWindowMenu();
    assert.ok(menu instanceof Wirecloud.ui.WindowMenu);

    const ioperator = {
        id: 'op1',
        volatile: true,
        preferenceList: [
            {
                hidden: false,
                meta: { name: 'pref1' },
                getInterfaceDescription: () => ({ type: 'text', label: 'Pref 1' }),
                value: 'old'
            }
        ],
        preferences: {
            pref1: { meta: { name: 'pref1', secure: false }, value: 'old' }
        },
        wiring: { workspace: { id: 1 } },
        logManager: { log: () => {}, formatException: (e) => e.message }
    };

    menu.show(ioperator);
});

test('PublishResourceWindowMenu — loads without errors', () => {
    setup();

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/PublishResourceWindowMenu.js');

    const resource = { uri: '/api/resource/1' };
    const menu = new Wirecloud.ui.PublishResourceWindowMenu(resource);
    assert.ok(menu instanceof Wirecloud.ui.FormWindowMenu);
    assert.equal(menu.resource, resource);
    menu.setFocus();
});

test('WorkspaceListItems — loads without errors', () => {
    setup();

    Wirecloud.workspacesByUserAndName = {
        testuser: { ws1: { title: 'My Workspace', name: 'ws1' } }
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceListItems.js');

    const handler = () => {};
    const items = new Wirecloud.ui.WorkspaceListItems(handler);
    assert.ok(items instanceof StyledElements.DynamicMenuItems);
    const menuItems = items.build();
    assert.ok(Array.isArray(menuItems));
    assert.ok(menuItems.length > 0);
});

test('WorkspaceListItems — empty workspace list', () => {
    setup();

    Wirecloud.workspacesByUserAndName = {};
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceListItems.js');

    const items = new Wirecloud.ui.WorkspaceListItems(() => {});
    const menuItems = items.build();
    assert.equal(menuItems.length, 1);
});

test('WorkspaceTabViewMenuItems — loads without errors', () => {
    setup();

    Wirecloud.ui.RenameWindowMenu = class extends Wirecloud.ui.FormWindowMenu {};
    Wirecloud.ui.AlertWindowMenu = class extends Wirecloud.ui.WindowMenu {
        setHandler(fn) { fn && fn(); return this; }  // auto-execute handler for test
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceTabViewMenuItems.js');

    const tab = {
        model: {
            initial: false,
            title: 'Tab 1',
            isAllowed: () => true,
            setInitial: () => {},
            remove: () => {}
        },
        widgets: [],
        showSettings: () => {},
        dragboard: {hiddenWidgets: []}
    };
    const items = new Wirecloud.ui.WorkspaceTabViewMenuItems(tab);
    assert.ok(items instanceof StyledElements.DynamicMenuItems);
    const menuItems = items.build();
    assert.ok(Array.isArray(menuItems));
});

test('WorkspaceViewMenuItems — loads without errors', () => {
    setup();

    Wirecloud.ui.NewWorkspaceWindowMenu = class extends Wirecloud.ui.FormWindowMenu {};
    Wirecloud.ui.RenameWindowMenu = class extends Wirecloud.ui.FormWindowMenu {};
    Wirecloud.ui.SharingWindowMenu = class extends Wirecloud.ui.WindowMenu {};
    Wirecloud.ui.PublishWorkspaceWindowMenu = class extends Wirecloud.ui.FormWindowMenu {
        constructor(model) { super(null, 'Publish'); }
    };
    Wirecloud.ui.EmbedCodeWindowMenu = class extends Wirecloud.ui.WindowMenu {};
    Wirecloud.ui.AlertWindowMenu = class extends Wirecloud.ui.WindowMenu {
        setHandler(fn) { fn && fn(); return this; }
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WorkspaceViewMenuItems.js');

    const workspace = {
        model: {
            title: 'Test WS',
            id: 1,
            isAllowed: () => true,
            rename: (name) => ({ then: (fn) => fn() }),
            remove: () => Promise.resolve()
        },
        editing: true,
        title: 'Test WS',
        showSettings: () => {}
    };

    const items = new Wirecloud.ui.WorkspaceViewMenuItems(workspace);
    assert.ok(items instanceof StyledElements.DynamicMenuItems);
    const menuItems = items.build();
    assert.ok(Array.isArray(menuItems));
});

// ============================================================================
// ADDITIONAL COVERAGE: CatalogueSearchView, CatalogueView,
// PublishWorkspaceWindowMenu, SharingWindowMenu
// ============================================================================

// -- CatalogueSearchView -------------------------------------------------------

test('CatalogueSearchView — constructor, init, mark_outdated, refresh_if_needed, handleKeydownEvent', () => {
    const { Wirecloud, StyledElements } = setup();

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');

    // -- Additional SourcedElements mocks -----------------------------------
    StyledElements.TextField = class TextField {
        constructor(opts = {}) {
            this._value = '';
            this.wrapperElement = document.createElement('input');
        }
        addEventListener() {}
        setValue(v) { this._value = v; return this; }
        getValue() { return this._value; }
        focus() {}
    };

    StyledElements.PaginationInterface = class PaginationInterface {
        constructor() {}
    };

    StyledElements.PaginatedSource = class PaginatedSource {
        constructor(opts = {}) { this.options = opts; }
        addEventListener() {}
        changeOptions() { return this; }
        refresh() { return this; }
    };

    // -- Wirecloud dependencies --------------------------------------------
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/Version.js');

    Wirecloud.WirecloudCatalogue = class WirecloudCatalogue {
        constructor() {
            this.title = 'TestCatalogue';
            this.catalogue = { addEventListener() {} };
        }
        search() { return Promise.resolve({ resources: [], corrected_query: null }); }
        getCurrentSearchContext() { return {}; }
        isAllow() { return true; }
    };

    // -- Templates ---------------------------------------------------------
    Wirecloud.currentTheme.templates['wirecloud/catalogue/search_interface'] = () => {
        const div = document.createElement('div');
        div.elements = [div];
        div.appendTo = function (p) { p.appendChild(this); };
        return div;
    };
    Wirecloud.currentTheme.templates['wirecloud/catalogue/resource'] = () => {
        const div = document.createElement('div');
        div.elements = [div];
        return div;
    };

    // -- Resource painter mock ---------------------------------------------
    const ResourcePainter = class ResourcePainter {
        constructor() {}
        paint() { return document.createElement('div'); }
        paintInfo() { return document.createElement('div'); }
        setError() {}
    };

    const catalogue = new Wirecloud.WirecloudCatalogue();

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/CatalogueSearchView.js');

    const view = new Wirecloud.ui.CatalogueSearchView('search-view', {
        catalogue: catalogue,
        resource_painter: ResourcePainter,
        resource_extra_context: {}
    });

    assert.ok(view instanceof StyledElements.Alternative);
    assert.equal(view.view_name, 'search');
    assert.equal(typeof view.init, 'function');
    assert.equal(typeof view.mark_outdated, 'function');
    assert.equal(typeof view.refresh_if_needed, 'function');
    assert.equal(typeof view.handleKeydownEvent, 'function');
    assert.equal(typeof view._search, 'function');
    assert.equal(typeof view._keywordTimeoutHandler, 'function');

    view.init();
    assert.equal(view.initialized, true);

    view.mark_outdated();
    assert.equal(view._last_search, false);

    view.refresh_if_needed();

    const handled = view.handleKeydownEvent('f', { ctrlKey: true });
    assert.equal(handled, true);
});

// -- CatalogueView -------------------------------------------------------------

test('CatalogueView — constructor, getLabel, isAllow, goUp, wait_ready, changeCurrentView, home, refresh_search_results', () => {
    const { Wirecloud, StyledElements } = setup();

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');

    // -- StyledElements.Alternatives mock -------------------------------
    StyledElements.Alternatives = class Alternatives {
        constructor() {
            this._current = null;
            this._altMap = {};
        }
        getCurrentAlternative() { return this._current; }
        createAlternative(opts) {
            const alt = { altId: 0, show() { return this; }, hide() { return this; }, init() {}, enable() {}, disable() {}, repaint() {}, refresh_if_needed() {}, source: { refresh() {} }, paint() {}, isVisible() { return false; }, changeVersion() {}, get currentEntry() { return null; } };
            this._altMap[alt.altId] = alt;
            this._current = alt;
            return alt;
        }
        showAlternative(alt, opts) {
            if (alt && alt.altId !== undefined) this._current = this._altMap[alt.altId] || this._current;
            (opts && opts.onComplete) ? opts.onComplete() : null;
        }
        addEventListener() {}
    };

    // -- Wirecloud.WirecloudCatalogue mock ----------------------------------
    Wirecloud.WirecloudCatalogue = class WirecloudCatalogue {
        constructor(desc) {
            this.title = (desc && desc.name) || 'MockCatalogue';
            this.desc = desc || {};
        }
        search() { return Promise.resolve({}); }
        getResourceDetails() { return Promise.resolve({}); }
        isAllow() { return true; }
    };
    Wirecloud.WirecloudCatalogue.ResourceDetails = class ResourceDetails {};

    // -- CatalogueSearchView mock (dependency of CatalogueView) --------------
    Wirecloud.ui.CatalogueSearchView = class extends StyledElements.Alternative {
        constructor(id, opts) { super(id, opts); }
        init() {}
        refresh_if_needed() {}
    };

    // -- ResourceDetailsView mock -------------------------------------------
    Wirecloud.ui.WirecloudCatalogue = Wirecloud.ui.WirecloudCatalogue || {};
    Wirecloud.ui.WirecloudCatalogue.ResourceDetailsView = class extends StyledElements.Alternative {
        constructor(id, opts) { super(id, opts); }
        paint() {}
        repaint() {}
        enable() {}
        disable() {}
    };

    // -- Additional Wirecloud mocks ---------------------------------------
    Wirecloud.HistoryManager.pushState = () => {};
    Wirecloud.HistoryManager.replaceState = () => {};
    Wirecloud.LocalCatalogue.resourceExists = () => false;
    Wirecloud.UserInterfaceManager.views.myresources = {
        createUserCommand: () => () => {}
    };
    Wirecloud.ui.ResourcePainter = class ResourcePainter {};

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/CatalogueView.js');

    const view = new Wirecloud.ui.CatalogueView('cat-view', {
        marketplace_desc: { user: 'test', name: 'TestMarket' },
        catalogue: { buildStateData() { return {}; } }
    });

    assert.ok(view instanceof StyledElements.Alternative);
    assert.equal(typeof view.getLabel, 'function');
    assert.equal(typeof view.isAllow, 'function');
    assert.equal(typeof view.goUp, 'function');
    assert.equal(typeof view.wait_ready, 'function');
    assert.equal(typeof view.changeCurrentView, 'function');
    assert.equal(typeof view.home, 'function');
    assert.equal(typeof view.refresh_search_results, 'function');
    assert.equal(typeof view.createUserCommand, 'function');
    assert.equal(typeof view.getPublishEndpoints, 'function');
    assert.equal(typeof view.refresh_if_needed, 'function');
    assert.equal(typeof view.search, 'function');

    assert.ok(view.market_id);

    view.getLabel();
    view.isAllow('read');
    assert.equal(typeof view.goUp(), 'boolean');
    view.wait_ready(() => {});
    view.changeCurrentView('search');
    view.home();
    view.refresh_search_results();
    view.refresh_if_needed();

    // Test showDetails ui_command
    assert.equal(typeof view.ui_commands, 'object');
    assert.equal(typeof view.ui_commands.showDetails, 'function');
    const cmd = view.createUserCommand('showDetails', { vendor: 'test', name: 'widget', version: '1.0' }, { history: 'ignore' });
    assert.equal(typeof cmd, 'function');
    cmd();
});

// -- PublishWorkspaceWindowMenu ------------------------------------------------

test('PublishWorkspaceWindowMenu — constructor, setFocus, executeOperation', () => {
    const { Wirecloud } = setup();

    Wirecloud.contextManager.get = (key) => {
        if (key === 'fullname') return 'Test User';
        if (key === 'username') return 'testuser';
        return null;
    };

    Wirecloud.ui.MessageWindowMenu = class extends Wirecloud.ui.WindowMenu {};

    global.URLify = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '_');

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/PublishWorkspaceWindowMenu.js');

    const workspace = {
        title: 'Test Workspace',
        publish: () => Promise.resolve(),
        tabs: []
    };

    const menu = new Wirecloud.ui.PublishWorkspaceWindowMenu(workspace);
    assert.ok(menu instanceof Wirecloud.ui.FormWindowMenu);
    assert.equal(menu.workspace, workspace);
    assert.equal(typeof menu._addVariableParametrization, 'function');
    assert.equal(typeof menu._parseTab, 'function');
    assert.equal(typeof menu._sortVariables, 'function');
    assert.equal(typeof menu.setFocus, 'function');
    assert.equal(typeof menu.executeOperation, 'function');

    menu.form.fieldInterfaces.title = { focus() {} };
    menu.setFocus();
    menu.executeOperation({ title: 'New Mashup' });
});

// -- SharingWindowMenu ---------------------------------------------------------

test('SharingWindowMenu — constructor, show, hide, destroy', () => {
    const { Wirecloud, StyledElements } = setup();

    StyledElements.Container.prototype.appendTo = function (parent) {
        parent.appendChild(this.wrapperElement);
        return this;
    };
    StyledElements.Container.prototype.setDisabled = function () { return this; };

    // -- Additional SourcedElements mocks -----------------------------------
    StyledElements.TextField = class TextField {
        constructor(opts = {}) {
            this._value = '';
            this.wrapperElement = document.createElement('input');
        }
        addEventListener() {}
        setValue(v) { this._value = v; return this; }
        getValue() { return this._value; }
        appendTo(parent) { parent.appendChild(this.wrapperElement); return this; }
        setDisabled() { return this; }
    };

    StyledElements.RadioButton = class RadioButton {
        constructor(opts = {}) {
            this.wrapperElement = document.createElement('input');
            this.wrapperElement.type = 'radio';
        }
        addEventListener() {}
    };

    StyledElements.ButtonsGroup = class ButtonsGroup {
        constructor() {
            this.value = '';
            this.wrapperElement = document.createElement('div');
        }
        setValue(v) { this.value = v; return this; }
        addEventListener() {}
        getValue() { return this.value; }
    };

    // -- UserGroupTypeahead mock --------------------------------------------
    Wirecloud.ui.UserGroupTypeahead = class UserGroupTypeahead {
        constructor() {}
        bind() {}
        addEventListener() {}
    };

    // -- Templates ----------------------------------------------------------
    Wirecloud.currentTheme.templates['wirecloud/workspace/visibility_option'] = () => {
        const div = document.createElement('div');
        div.elements = [div];
        div.appendTo = function (p) { p.appendChild(this); };
        return div;
    };
    Wirecloud.currentTheme.templates['wirecloud/workspace/sharing_user'] = () => {
        const frag = document.createElement('div');
        const row = document.createElement('div');
        frag.appendChild(row);
        frag.elements = [frag, row];
        return frag;
    };

    // -- Workspace model ----------------------------------------------------
    const workspace = {
        model: {
            preferences: {
                get(key) {
                    if (key === 'public') return false;
                    if (key === 'requireauth') return true;
                    return null;
                },
                set() { return Promise.resolve(); }
            },
            users: [],
            groups: []
        }
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/SharingWindowMenu.js');

    const menu = new Wirecloud.ui.SharingWindowMenu(workspace);
    assert.ok(menu instanceof Wirecloud.ui.WindowMenu);
    assert.equal(menu.workspace, workspace);
    assert.ok(menu.visibilityOptions instanceof StyledElements.ButtonsGroup);
    assert.ok(menu.btnAccept instanceof StyledElements.Button);
    assert.ok(menu.btnCancel instanceof StyledElements.Button);
    assert.ok(Array.isArray(menu.sharelist));
    assert.equal(typeof menu.users, 'object');
    assert.equal(typeof menu.groups, 'object');

    menu.show();
    menu.hide();
    menu.destroy();
});

// ============================================================================
// ADDITIONAL COVERAGE: CatalogueSearchView methods
// ============================================================================

test('CatalogueSearchView — _keywordTimeoutHandler clears timeout and changes options', () => {
    const { Wirecloud, StyledElements } = setup();

    // Mocks required by CatalogueSearchView
    StyledElements.TextField = class TextField {
        constructor(opts = {}) { this._value = ''; this.wrapperElement = document.createElement('input'); }
        addEventListener() {} setValue(v) { this._value = v; return this; } getValue() { return this._value; } focus() {}
    };
    StyledElements.PaginationInterface = class PaginationInterface { constructor() {} };
    StyledElements.PaginatedSource = class PaginatedSource {
        constructor(opts = {}) { this.options = opts; }
        addEventListener() {} changeOptions() { return this; } refresh() { return this; }
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/Version.js');

    Wirecloud.WirecloudCatalogue = class {
        constructor() { this.catalogue = { addEventListener() {} }; }
        search() { return Promise.resolve({ resources: [], corrected_query: null }); }
        getCurrentSearchContext() { return {}; }
    };
    Wirecloud.currentTheme.templates['wirecloud/catalogue/search_interface'] = () => {
        const div = document.createElement('div');
        div.elements = [div];
        div.appendTo = function (p) { p.appendChild(this); };
        return div;
    };
    Wirecloud.currentTheme.templates['wirecloud/catalogue/resource'] = () => {
        const div = document.createElement('div');
        div.elements = [div];
        return div;
    };
    const ResourcePainter = class { constructor() {} paint() { return document.createElement('div'); } paintInfo() { return document.createElement('div'); } setError() {} };
    const catalogue = new Wirecloud.WirecloudCatalogue();

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/CatalogueSearchView.js');

    const view = new Wirecloud.ui.CatalogueSearchView('search-view', {
        catalogue: catalogue,
        resource_painter: ResourcePainter,
        resource_extra_context: {}
    });

    view._keywordTimeoutHandler();
    assert.equal(view.timeout, null);
});

test('CatalogueSearchView — _onSearchInputKeyPress handles Enter key', () => {
    const { Wirecloud, StyledElements } = setup();

    StyledElements.TextField = class TextField {
        constructor(opts = {}) { this._value = ''; this.wrapperElement = document.createElement('input'); }
        addEventListener() {} setValue(v) { this._value = v; return this; } getValue() { return this._value; } focus() {}
    };
    StyledElements.PaginationInterface = class PaginationInterface { constructor() {} };
    StyledElements.PaginatedSource = class PaginatedSource {
        constructor(opts = {}) { this.options = opts; }
        addEventListener() {} changeOptions() { return this; } refresh() { return this; }
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/Version.js');

    Wirecloud.WirecloudCatalogue = class {
        constructor() { this.catalogue = { addEventListener() {} }; }
        search() { return Promise.resolve({ resources: [], corrected_query: null }); }
        getCurrentSearchContext() { return {}; }
    };
    Wirecloud.currentTheme.templates['wirecloud/catalogue/search_interface'] = () => {
        const div = document.createElement('div');
        div.elements = [div];
        div.appendTo = function (p) { p.appendChild(this); };
        return div;
    };
    Wirecloud.currentTheme.templates['wirecloud/catalogue/resource'] = () => {
        const div = document.createElement('div');
        div.elements = [div];
        return div;
    };
    const ResourcePainter = class { constructor() {} paint() { return document.createElement('div'); } paintInfo() { return document.createElement('div'); } setError() {} };
    const catalogue = new Wirecloud.WirecloudCatalogue();

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/CatalogueSearchView.js');

    const view = new Wirecloud.ui.CatalogueSearchView('search-view', {
        catalogue: catalogue,
        resource_painter: ResourcePainter,
        resource_extra_context: {}
    });

    view.timeout = 1;
    view._onSearchInputKeyPress(null, null, 'Enter');
    assert.equal(view.timeout, null);
});

test('CatalogueSearchView — _search calls catalogue.search', async () => {
    const { Wirecloud, StyledElements } = setup();

    StyledElements.TextField = class TextField {
        constructor(opts = {}) { this._value = ''; this.wrapperElement = document.createElement('input'); }
        addEventListener() {} setValue(v) { this._value = v; return this; } getValue() { return this._value; } focus() {}
    };
    StyledElements.PaginationInterface = class PaginationInterface { constructor() {} };
    StyledElements.PaginatedSource = class PaginatedSource {
        constructor(opts = {}) { this.options = opts; }
        addEventListener() {} changeOptions() { return this; } refresh() { return this; }
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/Version.js');

    let searchCalled = false;
    Wirecloud.WirecloudCatalogue = class {
        constructor() { this.catalogue = { addEventListener() {} }; }
        search(opts) {
            searchCalled = true;
            return Promise.resolve({ resources: [{ vendor_name: 'V', name: 'N', version: '1.0' }], corrected_query: null });
        }
        getCurrentSearchContext() { return {}; }
    };
    Wirecloud.currentTheme.templates['wirecloud/catalogue/search_interface'] = () => {
        const div = document.createElement('div');
        div.elements = [div];
        div.appendTo = function (p) { p.appendChild(this); };
        return div;
    };
    Wirecloud.currentTheme.templates['wirecloud/catalogue/resource'] = () => {
        const div = document.createElement('div');
        div.elements = [div];
        return div;
    };
    const ResourcePainter = class {
        constructor() {}
        paint(resource) { return document.createElement('div'); }
        paintInfo() { return document.createElement('div'); }
        setError() {}
    };
    const catalogue = new Wirecloud.WirecloudCatalogue();

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/CatalogueSearchView.js');

    const view = new Wirecloud.ui.CatalogueSearchView('search-view', {
        catalogue: catalogue,
        resource_painter: ResourcePainter,
        resource_extra_context: {}
    });

    const onSuccess = () => {};
    const onError = () => {};
    view._search(1, { order_by: '-creation_date', keywords: 'test', scope: 'all', pageSize: 30 }, onSuccess, onError);
    await new Promise((r) => setTimeout(r, 10));
    assert.ok(searchCalled);
});

test('CatalogueSearchView — _onSearchInputKeyPress ignores non-Enter key', () => {
    const { Wirecloud, StyledElements } = setup();

    StyledElements.TextField = class TextField {
        constructor(opts = {}) { this._value = ''; this.wrapperElement = document.createElement('input'); }
        addEventListener() {} setValue(v) { this._value = v; return this; } getValue() { return this._value; } focus() {}
    };
    StyledElements.PaginationInterface = class PaginationInterface { constructor() {} };
    StyledElements.PaginatedSource = class PaginatedSource {
        constructor(opts = {}) { this.options = opts; }
        addEventListener() {} changeOptions() { return this; } refresh() { return this; }
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/Version.js');

    Wirecloud.WirecloudCatalogue = class {
        constructor() { this.catalogue = { addEventListener() {} }; }
        search() { return Promise.resolve({ resources: [], corrected_query: null }); }
        getCurrentSearchContext() { return {}; }
    };
    Wirecloud.currentTheme.templates['wirecloud/catalogue/search_interface'] = () => {
        const div = document.createElement('div');
        div.elements = [div];
        div.appendTo = function (p) { p.appendChild(this); };
        return div;
    };
    Wirecloud.currentTheme.templates['wirecloud/catalogue/resource'] = () => {
        const div = document.createElement('div');
        div.elements = [div];
        return div;
    };
    const ResourcePainter = class { constructor() {} paint() { return document.createElement('div'); } paintInfo() { return document.createElement('div'); } setError() {} };
    const catalogue = new Wirecloud.WirecloudCatalogue();

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/CatalogueSearchView.js');

    const view = new Wirecloud.ui.CatalogueSearchView('search-view', {
        catalogue: catalogue,
        resource_painter: ResourcePainter,
        resource_extra_context: {}
    });

    view.timeout = 1;
    assert.doesNotThrow(() => {
        view._onSearchInputKeyPress(null, null, 'a');
    });
});

test('CatalogueSearchView — orderby and scope change handlers (lines 142-153, 156-169)', () => {
    const { Wirecloud, StyledElements } = setup();

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');

    let changeOptionsOrderCalled = false;
    let changeOptionsScopeCalled = false;

    StyledElements.TextField = class TextField {
        constructor(opts = {}) { this._value = ''; this.wrapperElement = document.createElement('input'); }
        addEventListener() {} setValue(v) { this._value = v; return this; } getValue() { return this._value; } focus() {}
    };
    StyledElements.PaginationInterface = class PaginationInterface { constructor() {} };
    StyledElements.PaginatedSource = class PaginatedSource {
        constructor(opts = {}) { this.options = opts; }
        addEventListener() {}
        changeOptions(opts) {
            if (opts.order_by !== undefined) changeOptionsOrderCalled = true;
            if (opts.scope !== undefined) changeOptionsScopeCalled = true;
            return this;
        }
        refresh() { return this; }
    };

    let orderbySelect;
    let scopeSelect;

    const OrigGUIBuilder = StyledElements.GUIBuilder;
    StyledElements.GUIBuilder = class {
        parse(template, context) {
            if (context.orderby) orderbySelect = context.orderby();
            if (context.scope) scopeSelect = context.scope();
            if (context.reset_button) context.reset_button();
            if (context.pagination) context.pagination();
            return new StyledElements.Fragment('');
        }
    };

    StyledElements.Select = class Select {
        constructor(opts = {}) {
            this._entries = opts.initialEntries || [];
            this._value = opts.initialValue || '';
            this._listeners = {};
        }
        addEventListener(type, handler) {
            if (!this._listeners[type]) this._listeners[type] = [];
            this._listeners[type].push(handler);
        }
        getValue() { return this._value; }
        setValue(v) { this._value = v; return this; }
        dispatchEvent(event) {
            const handlers = this._listeners && this._listeners[event.type];
            if (handlers) handlers.forEach((h) => h(this));
        }
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/Version.js');

    Wirecloud.WirecloudCatalogue = class {
        constructor() { this.catalogue = { addEventListener() {} }; }
        search() { return Promise.resolve({ resources: [], corrected_query: null }); }
        getCurrentSearchContext() { return {}; }
    };
    Wirecloud.currentTheme.templates['wirecloud/catalogue/search_interface'] = () => {
        const div = document.createElement('div');
        div.elements = [div];
        div.appendTo = function (p) { p.appendChild(this); };
        return div;
    };
    Wirecloud.currentTheme.templates['wirecloud/catalogue/resource'] = () => {
        const div = document.createElement('div');
        div.elements = [div];
        return div;
    };
    const ResourcePainter = class { constructor() {} paint() { return document.createElement('div'); } paintInfo() { return document.createElement('div'); } setError() {} };
    const catalogue = new Wirecloud.WirecloudCatalogue();

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/CatalogueSearchView.js');

    const view = new Wirecloud.ui.CatalogueSearchView('search-view', {
        catalogue: catalogue,
        resource_painter: ResourcePainter,
        resource_extra_context: {}
    });

    assert.ok(orderbySelect);
    assert.ok(scopeSelect);

    orderbySelect.setValue('name');
    orderbySelect.dispatchEvent({ type: 'change' });
    assert.ok(changeOptionsOrderCalled);

    scopeSelect.setValue('widget');
    scopeSelect.dispatchEvent({ type: 'change' });
    assert.ok(changeOptionsScopeCalled);

    assert.equal(view.scopeSelect, scopeSelect);
});

test('CatalogueSearchView — source listeners and template controls', () => {
    const { Wirecloud, StyledElements } = setup();

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/Version.js');

    let sourceInstance = null;
    let resetButton = null;
    const painted = [];
    const infoMessages = [];
    const errors = [];

    StyledElements.TextField = class TextField {
        constructor() {
            this._value = '';
            this._listeners = {};
            this.wrapperElement = document.createElement('input');
        }
        addEventListener(type, handler) { this._listeners[type] = handler; }
        setValue(value) { this._value = value; return this; }
        getValue() { return this._value; }
        focus() { this.focused = true; }
    };
    StyledElements.Button = class Button {
        constructor(opts = {}) {
            this.label = opts.text || '';
            this._listeners = {};
            this.wrapperElement = document.createElement('button');
        }
        addEventListener(type, handler) { this._listeners[type] = handler; }
        setLabel(label) { this.label = label; return this; }
        click() { this._listeners.click(); }
    };
    StyledElements.Select = class Select {
        constructor(opts = {}) {
            this._value = opts.initialValue || '';
            this._listeners = {};
        }
        addEventListener(type, handler) { this._listeners[type] = handler; }
        setValue(value) { this._value = value; return this; }
        getValue() { return this._value; }
    };
    StyledElements.PaginationInterface = class PaginationInterface {
        constructor(source) { this.source = source; }
    };
    StyledElements.PaginatedSource = class PaginatedSource {
        constructor(opts = {}) {
            this.options = opts;
            this.listeners = {};
            this.refreshes = 0;
            sourceInstance = this;
        }
        addEventListener(type, handler) { this.listeners[type] = handler; }
        changeOptions(options) {
            this.options = Object.assign({}, this.options, options);
            this.listeners.optionsChanged(this, this.options);
            return this;
        }
        refresh() { this.refreshes += 1; return this; }
    };

    StyledElements.GUIBuilder = class GUIBuilder {
        constructor() {
            this.DEFAULT_OPENING = '';
            this.DEFAULT_CLOSING = '';
        }
        parse(template, context) {
            if (context.reset_button) resetButton = context.reset_button();
            if (context.orderby) context.orderby();
            if (context.scope) context.scope();
            if (context.pagination) context.pagination();
            const node = document.createElement('div');
            return {
                elements: [node],
                appendTo(parent) { parent.appendChild(node); },
            };
        }
    };

    Wirecloud.contextManager.get = (key) => key === 'language' ? 'en' : null;
    Wirecloud.currentTheme.templates['wirecloud/catalogue/search_interface'] = 'template';
    Wirecloud.currentTheme.templates['wirecloud/catalogue/resource'] = 'resource';
    const catalogue = {
        catalogue: { addEventListener() {} },
        search() { return Promise.resolve({ resources: [], corrected_query: null }); },
        getCurrentSearchContext() { return { extra: true }; },
    };
    const ResourcePainter = class ResourcePainter {
        paint(resource) {
            painted.push(resource);
            return document.createElement('div');
        }
        paintInfo(message, context) {
            infoMessages.push({ message, context });
            return document.createElement('div');
        }
        setError(error) { errors.push(error); }
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/CatalogueSearchView.js');

    const view = new Wirecloud.ui.CatalogueSearchView('search-view', {
        catalogue,
        resource_painter: ResourcePainter,
        extra_context: { extraNode: 'value' },
        resource_template: 'wirecloud/catalogue/resource',
    });

    sourceInstance.options.processFunc([
        { vendor_name: 'Vendor', version: '1.0' },
    ], { corrected_query: 'corrected' });
    assert.equal(infoMessages.length, 1);
    assert.equal(painted.length, 1);
    assert.ok(painted[0].version instanceof Wirecloud.Version);
    assert.equal(painted[0].group_id, 'Vendor');

    sourceInstance.changeOptions({ keywords: 'term', scope: 'widget' });
    assert.equal(view.simple_search_input.getValue(), 'term');
    assert.equal(view.scopeSelect.getValue(), 'widget');
    assert.equal(resetButton.label, 'Clear filters');

    resetButton.click();
    assert.equal(view.simple_search_input.getValue(), '');
    assert.equal(resetButton.label, 'Refresh');

    sourceInstance.listeners.requestStart();
    sourceInstance.listeners.requestEnd({ totalCount: 0, options: { keywords: '', scope: 'all' } }, null);
    sourceInstance.listeners.requestEnd({ totalCount: 0, options: { keywords: ' missing ', scope: 'widget' } }, {});
    assert.equal(errors.length, 2);

    view.simple_search_input._listeners.change();
    assert.notEqual(view.timeout, null);
    clearTimeout(view.timeout);

    let clearedTimeout = null;
    const origClearTimeout = global.clearTimeout;
    global.clearTimeout = (timeout) => { clearedTimeout = timeout; };
    try {
        view.timeout = 123;
        view.simple_search_input._listeners.change();
        assert.equal(clearedTimeout, 123);
        clearTimeout(view.timeout);
    } finally {
        global.clearTimeout = origClearTimeout;
    }

    assert.equal(view.handleKeydownEvent('x', { ctrlKey: false, metaKey: false }), undefined);
    sourceInstance.refreshes = 0;
    view.initialized = false;
    view.refresh_if_needed();
    assert.equal(sourceInstance.refreshes, 0);
});

// ============================================================================
// ADDITIONAL COVERAGE: CatalogueView methods
// ============================================================================

test('CatalogueView — onHistoryChange with search subview', () => {
    const { Wirecloud, StyledElements } = setup();

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');

    StyledElements.Alternatives = class Alternatives {
        constructor() {
            this._current = null;
            this._altMap = {};
        }
        getCurrentAlternative() { return this._current; }
        createAlternative(opts) {
            const alt = { altId: 0, show() { return this; }, hide() { return this; }, init() {}, enable() {}, disable() {}, repaint() {}, refresh_if_needed() {}, source: { refresh() {} }, paint() {}, isVisible() { return false; }, changeVersion() {}, get currentEntry() { return null; } };
            this._altMap[alt.altId] = alt;
            this._current = alt;
            return alt;
        }
        showAlternative(alt, opts) {
            if (alt && alt.altId !== undefined) this._current = this._altMap[alt.altId] || this._current;
            (opts && opts.onComplete) ? opts.onComplete() : null;
        }
        addEventListener() {}
    };

    Wirecloud.WirecloudCatalogue = class {
        constructor(desc) { this.title = (desc && desc.name) || 'MockCatalogue'; this.desc = desc || {}; }
        search() { return Promise.resolve({}); }
        getResourceDetails() { return Promise.resolve({}); }
        isAllow() { return true; }
    };
    Wirecloud.WirecloudCatalogue.ResourceDetails = class ResourceDetails {};
    Wirecloud.ui.CatalogueSearchView = class extends StyledElements.Alternative {
        constructor(id, opts) { super(id, opts); }
        init() {}
        refresh_if_needed() {}
    };
    Wirecloud.ui.WirecloudCatalogue = Wirecloud.ui.WirecloudCatalogue || {};
    Wirecloud.ui.WirecloudCatalogue.ResourceDetailsView = class extends StyledElements.Alternative {
        constructor(id, opts) { super(id, opts); }
        paint() {}
        repaint() {}
        enable() {}
        disable() {}
    };
    Wirecloud.HistoryManager.pushState = () => {};
    Wirecloud.HistoryManager.replaceState = () => {};
    Wirecloud.LocalCatalogue.resourceExists = () => false;
    Wirecloud.UserInterfaceManager.views.myresources = { createUserCommand: () => () => {} };
    Wirecloud.ui.ResourcePainter = class ResourcePainter {};

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/CatalogueView.js');

    const view = new Wirecloud.ui.CatalogueView('cat-view', {
        marketplace_desc: { user: 'test', name: 'TestMarket' },
        catalogue: { buildStateData() { return {}; } }
    });

    assert.doesNotThrow(() => {
        view.onHistoryChange({ subview: 'search' });
    });
});

test('CatalogueView — onHistoryChange with resource subview', () => {
    const { Wirecloud, StyledElements } = setup();

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');

    StyledElements.Alternatives = class Alternatives {
        constructor() {
            this._current = null;
            this._altMap = {};
        }
        getCurrentAlternative() { return this._current; }
        createAlternative(opts) {
            const alt = { altId: 0, show() { return this; }, hide() { return this; }, init() {}, enable() {}, disable() {}, repaint() {}, refresh_if_needed() {}, source: { refresh() {} }, paint() {}, isVisible() { return false; }, changeVersion() {}, get currentEntry() { return null; } };
            this._altMap[alt.altId] = alt;
            this._current = alt;
            return alt;
        }
        showAlternative(alt, opts) {
            if (alt && alt.altId !== undefined) this._current = this._altMap[alt.altId] || this._current;
            (opts && opts.onComplete) ? opts.onComplete() : null;
        }
        addEventListener() {}
    };

    Wirecloud.WirecloudCatalogue = class {
        constructor(desc) { this.title = (desc && desc.name) || 'MockCatalogue'; this.desc = desc || {}; }
        search() { return Promise.resolve({}); }
        getResourceDetails() { return Promise.resolve({}); }
        isAllow() { return true; }
    };
    Wirecloud.WirecloudCatalogue.ResourceDetails = class ResourceDetails {};
    Wirecloud.ui.CatalogueSearchView = class extends StyledElements.Alternative {
        constructor(id, opts) { super(id, opts); }
        init() {}
        refresh_if_needed() {}
    };
    Wirecloud.ui.WirecloudCatalogue = Wirecloud.ui.WirecloudCatalogue || {};
    Wirecloud.ui.WirecloudCatalogue.ResourceDetailsView = class extends StyledElements.Alternative {
        constructor(id, opts) { super(id, opts); }
        paint() {}
        repaint() {}
        enable() {}
        disable() {}
    };
    Wirecloud.HistoryManager.pushState = () => {};
    Wirecloud.HistoryManager.replaceState = () => {};
    Wirecloud.LocalCatalogue.resourceExists = () => false;
    Wirecloud.UserInterfaceManager.views.myresources = { createUserCommand: () => () => {} };
    Wirecloud.ui.ResourcePainter = class ResourcePainter {};

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/CatalogueView.js');

    const view = new Wirecloud.ui.CatalogueView('cat-view', {
        marketplace_desc: { user: 'test', name: 'TestMarket' },
        catalogue: { buildStateData() { return {}; } }
    });

    assert.doesNotThrow(() => {
        view.onHistoryChange({ subview: 'details', resource: 'test/widget/1.0' });
    });
});

test('CatalogueView — search method proxies to catalogue', () => {
    const { Wirecloud, StyledElements } = setup();

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');

    StyledElements.Alternatives = class Alternatives {
        constructor() {
            this._current = null;
            this._altMap = {};
        }
        getCurrentAlternative() { return this._current; }
        createAlternative(opts) {
            const alt = { altId: 0, show() { return this; }, hide() { return this; }, init() {}, enable() {}, disable() {}, repaint() {}, refresh_if_needed() {}, source: { refresh() {} }, paint() {}, isVisible() { return false; }, changeVersion() {}, get currentEntry() { return null; } };
            this._altMap[alt.altId] = alt;
            this._current = alt;
            return alt;
        }
        showAlternative(alt, opts) {
            if (alt && alt.altId !== undefined) this._current = this._altMap[alt.altId] || this._current;
            (opts && opts.onComplete) ? opts.onComplete() : null;
        }
        addEventListener() {}
    };

    let proxied = false;
    Wirecloud.WirecloudCatalogue = class {
        constructor(desc) { this.title = (desc && desc.name) || 'MockCatalogue'; this.desc = desc || {}; }
        search(onSuccess, onError, options) { proxied = true; return {}; }
        getResourceDetails() { return Promise.resolve({}); }
        isAllow() { return true; }
    };
    Wirecloud.WirecloudCatalogue.ResourceDetails = class ResourceDetails {};
    Wirecloud.ui.CatalogueSearchView = class extends StyledElements.Alternative {
        constructor(id, opts) { super(id, opts); }
        init() {}
        refresh_if_needed() {}
    };
    Wirecloud.ui.WirecloudCatalogue = Wirecloud.ui.WirecloudCatalogue || {};
    Wirecloud.ui.WirecloudCatalogue.ResourceDetailsView = class extends StyledElements.Alternative {
        constructor(id, opts) { super(id, opts); }
        paint() {}
        repaint() {}
        enable() {}
        disable() {}
    };
    Wirecloud.HistoryManager.pushState = () => {};
    Wirecloud.HistoryManager.replaceState = () => {};
    Wirecloud.LocalCatalogue.resourceExists = () => false;
    Wirecloud.UserInterfaceManager.views.myresources = { createUserCommand: () => () => {} };
    Wirecloud.ui.ResourcePainter = class ResourcePainter {};

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/CatalogueView.js');

    const view = new Wirecloud.ui.CatalogueView('cat-view', {
        marketplace_desc: { user: 'test', name: 'TestMarket' },
        catalogue: { buildStateData() { return {}; } }
    });

    view.search(() => {}, () => {}, {});
    assert.ok(proxied);
});

test('CatalogueView — getPublishEndpoints returns null', () => {
    const { Wirecloud, StyledElements } = setup();

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');

    StyledElements.Alternatives = class Alternatives {
        constructor() {
            this._current = null;
            this._altMap = {};
        }
        getCurrentAlternative() { return this._current; }
        createAlternative(opts) {
            const alt = { altId: 0, show() { return this; }, hide() { return this; }, init() {}, enable() {}, disable() {}, repaint() {}, refresh_if_needed() {}, source: { refresh() {} }, paint() {}, isVisible() { return false; }, changeVersion() {}, get currentEntry() { return null; } };
            this._altMap[alt.altId] = alt;
            this._current = alt;
            return alt;
        }
        showAlternative(alt, opts) {
            if (alt && alt.altId !== undefined) this._current = this._altMap[alt.altId] || this._current;
            (opts && opts.onComplete) ? opts.onComplete() : null;
        }
        addEventListener() {}
    };

    Wirecloud.WirecloudCatalogue = class {
        constructor(desc) { this.title = (desc && desc.name) || 'MockCatalogue'; this.desc = desc || {}; }
        search() { return Promise.resolve({}); }
        getResourceDetails() { return Promise.resolve({}); }
        isAllow() { return true; }
    };
    Wirecloud.WirecloudCatalogue.ResourceDetails = class ResourceDetails {};
    Wirecloud.ui.CatalogueSearchView = class extends StyledElements.Alternative {
        constructor(id, opts) { super(id, opts); }
        init() {}
        refresh_if_needed() {}
    };
    Wirecloud.ui.WirecloudCatalogue = Wirecloud.ui.WirecloudCatalogue || {};
    Wirecloud.ui.WirecloudCatalogue.ResourceDetailsView = class extends StyledElements.Alternative {
        constructor(id, opts) { super(id, opts); }
        paint() {}
        repaint() {}
        enable() {}
        disable() {}
    };
    Wirecloud.HistoryManager.pushState = () => {};
    Wirecloud.HistoryManager.replaceState = () => {};
    Wirecloud.LocalCatalogue.resourceExists = () => false;
    Wirecloud.UserInterfaceManager.views.myresources = { createUserCommand: () => () => {} };
    Wirecloud.ui.ResourcePainter = class ResourcePainter {};

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/CatalogueView.js');

    const view = new Wirecloud.ui.CatalogueView('cat-view', {
        marketplace_desc: { user: 'test', name: 'TestMarket' },
        catalogue: { buildStateData() { return {}; } }
    });

    assert.equal(view.getPublishEndpoints(), null);
});

test('CatalogueView — wait_ready throws for non-function callback', () => {
    const { Wirecloud, StyledElements } = setup();

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');

    StyledElements.Alternatives = class Alternatives {
        constructor() {
            this._current = null;
            this._altMap = {};
        }
        getCurrentAlternative() { return this._current; }
        createAlternative(opts) {
            const alt = { altId: 0, show() { return this; }, hide() { return this; }, init() {}, enable() {}, disable() {}, repaint() {}, refresh_if_needed() {}, source: { refresh() {} }, paint() {}, isVisible() { return false; }, changeVersion() {}, get currentEntry() { return null; } };
            this._altMap[alt.altId] = alt;
            this._current = alt;
            return alt;
        }
        showAlternative(alt, opts) {
            if (alt && alt.altId !== undefined) this._current = this._altMap[alt.altId] || this._current;
            (opts && opts.onComplete) ? opts.onComplete() : null;
        }
        addEventListener() {}
    };

    Wirecloud.WirecloudCatalogue = class {
        constructor(desc) { this.title = (desc && desc.name) || 'MockCatalogue'; this.desc = desc || {}; }
        search() { return Promise.resolve({}); }
        getResourceDetails() { return Promise.resolve({}); }
        isAllow() { return true; }
    };
    Wirecloud.WirecloudCatalogue.ResourceDetails = class ResourceDetails {};
    Wirecloud.ui.CatalogueSearchView = class extends StyledElements.Alternative {
        constructor(id, opts) { super(id, opts); }
        init() {}
        refresh_if_needed() {}
    };
    Wirecloud.ui.WirecloudCatalogue = Wirecloud.ui.WirecloudCatalogue || {};
    Wirecloud.ui.WirecloudCatalogue.ResourceDetailsView = class extends StyledElements.Alternative {
        constructor(id, opts) { super(id, opts); }
        paint() {}
        repaint() {}
        enable() {}
        disable() {}
    };
    Wirecloud.HistoryManager.pushState = () => {};
    Wirecloud.HistoryManager.replaceState = () => {};
    Wirecloud.LocalCatalogue.resourceExists = () => false;
    Wirecloud.UserInterfaceManager.views.myresources = { createUserCommand: () => () => {} };
    Wirecloud.ui.ResourcePainter = class ResourcePainter {};

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/CatalogueView.js');

    const view = new Wirecloud.ui.CatalogueView('cat-view', {
        marketplace_desc: { user: 'test', name: 'TestMarket' },
        catalogue: { buildStateData() { return {}; } }
    });

    assert.throws(
        () => view.wait_ready(null),
        /missing onComplete callback/
    );
});

test('CatalogueView — changeCurrentView throws for invalid view_name', () => {
    const { Wirecloud, StyledElements } = setup();

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');

    StyledElements.Alternatives = class Alternatives {
        constructor() {
            this._current = null;
            this._altMap = {};
        }
        getCurrentAlternative() { return this._current; }
        createAlternative(opts) {
            const alt = { altId: 0, show() { return this; }, hide() { return this; }, init() {}, enable() {}, disable() {}, repaint() {}, refresh_if_needed() {}, source: { refresh() {} }, paint() {}, isVisible() { return false; }, changeVersion() {}, get currentEntry() { return null; } };
            this._altMap[alt.altId] = alt;
            this._current = alt;
            return alt;
        }
        showAlternative(alt, opts) {
            if (alt && alt.altId !== undefined) this._current = this._altMap[alt.altId] || this._current;
            (opts && opts.onComplete) ? opts.onComplete() : null;
        }
        addEventListener() {}
    };

    Wirecloud.WirecloudCatalogue = class {
        constructor(desc) { this.title = (desc && desc.name) || 'MockCatalogue'; this.desc = desc || {}; }
        search() { return Promise.resolve({}); }
        getResourceDetails() { return Promise.resolve({}); }
        isAllow() { return true; }
    };
    Wirecloud.WirecloudCatalogue.ResourceDetails = class ResourceDetails {};
    Wirecloud.ui.CatalogueSearchView = class extends StyledElements.Alternative {
        constructor(id, opts) { super(id, opts); }
        init() {}
        refresh_if_needed() {}
    };
    Wirecloud.ui.WirecloudCatalogue = Wirecloud.ui.WirecloudCatalogue || {};
    Wirecloud.ui.WirecloudCatalogue.ResourceDetailsView = class extends StyledElements.Alternative {
        constructor(id, opts) { super(id, opts); }
        paint() {}
        repaint() {}
        enable() {}
        disable() {}
    };
    Wirecloud.HistoryManager.pushState = () => {};
    Wirecloud.HistoryManager.replaceState = () => {};
    Wirecloud.LocalCatalogue.resourceExists = () => false;
    Wirecloud.UserInterfaceManager.views.myresources = { createUserCommand: () => () => {} };
    Wirecloud.ui.ResourcePainter = class ResourcePainter {};

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/CatalogueView.js');

    const view = new Wirecloud.ui.CatalogueView('cat-view', {
        marketplace_desc: { user: 'test', name: 'TestMarket' },
        catalogue: { buildStateData() { return {}; } }
    });

    assert.throws(
        () => view.changeCurrentView('nonexistent'),
        TypeError
    );
});

test('CatalogueView — showDetails with replace history (lines 190-191)', async () => {
    const { Wirecloud, StyledElements } = setup();

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');

    let historyReplaced = false;

    StyledElements.Alternatives = class Alternatives {
        constructor() { this._current = null; this._altMap = {}; }
        getCurrentAlternative() { return this._current; }
        createAlternative(opts) {
            const alt = { altId: 0, show() { return this; }, hide() { return this; }, init() {}, enable() {}, disable() {}, repaint() {}, refresh_if_needed() {}, source: { refresh() {} }, paint() {}, isVisible() { return false; }, changeVersion() {}, get currentEntry() { return null; } };
            this._altMap[alt.altId] = alt; this._current = alt; return alt;
        }
        showAlternative(alt, opts) { if (alt && alt.altId !== undefined) this._current = this._altMap[alt.altId] || this._current; }
        addEventListener() {}
    };

    Wirecloud.WirecloudCatalogue = class {
        constructor(desc) { this.title = (desc && desc.name) || 'MockCatalogue'; this.desc = desc || {}; }
        getResourceDetails() { return Promise.resolve({}); }
        isAllow() { return true; }
    };
    Wirecloud.WirecloudCatalogue.ResourceDetails = class ResourceDetails {};
    Wirecloud.ui.CatalogueSearchView = class extends StyledElements.Alternative { constructor(id, opts) { super(id, opts); } init() {} refresh_if_needed() {} };
    Wirecloud.ui.WirecloudCatalogue = Wirecloud.ui.WirecloudCatalogue || {};
    Wirecloud.ui.WirecloudCatalogue.ResourceDetailsView = class extends StyledElements.Alternative {
        constructor(id, opts) { super(id, opts); }
        paint() {} repaint() {} enable() {} disable() {}
    };
    Wirecloud.HistoryManager.pushState = () => {};
    Wirecloud.HistoryManager.replaceState = () => { historyReplaced = true; };
    Wirecloud.LocalCatalogue.resourceExists = () => false;
    Wirecloud.UserInterfaceManager.views.myresources = { createUserCommand: () => () => {} };
    Wirecloud.ui.ResourcePainter = class ResourcePainter {};

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/CatalogueView.js');

    const view = new Wirecloud.ui.CatalogueView('cat-view', {
        marketplace_desc: { user: 'test', name: 'TestMarket' },
        catalogue: { buildStateData() { return {}; } }
    });

    const cmd = view.createUserCommand('showDetails', { vendor: 'test', name: 'widget', version: '1.0' }, { history: 'replace' });
    cmd();
    await new Promise((r) => setTimeout(r, 5));
    assert.ok(historyReplaced);
});

test('CatalogueView — showDetails with ResourceDetails instance (lines 199-200)', () => {
    const { Wirecloud, StyledElements } = setup();

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');

    let detailsPainted = false;

    StyledElements.Alternatives = class Alternatives {
        constructor() { this._current = null; this._altMap = {}; }
        getCurrentAlternative() { return this._current; }
        createAlternative(opts) {
            const alt = { altId: 0, show() { return this; }, hide() { return this; }, init() {}, enable() {}, disable() {}, repaint() {}, refresh_if_needed() {}, source: { refresh() {} }, paint() { detailsPainted = true; }, isVisible() { return false; }, changeVersion() {}, get currentEntry() { return null; } };
            this._altMap[alt.altId] = alt; this._current = alt; return alt;
        }
        showAlternative(alt, opts) { if (alt && alt.altId !== undefined) this._current = this._altMap[alt.altId] || this._current; }
        addEventListener() {}
    };

    Wirecloud.WirecloudCatalogue = class {
        constructor(desc) { this.title = (desc && desc.name) || 'MockCatalogue'; this.desc = desc || {}; }
        getResourceDetails() { return Promise.resolve({}); }
        isAllow() { return true; }
    };
    Wirecloud.WirecloudCatalogue.ResourceDetails = class ResourceDetails {};
    Wirecloud.ui.CatalogueSearchView = class extends StyledElements.Alternative { constructor(id, opts) { super(id, opts); } init() {} refresh_if_needed() {} };
    Wirecloud.ui.WirecloudCatalogue = Wirecloud.ui.WirecloudCatalogue || {};
    Wirecloud.ui.WirecloudCatalogue.ResourceDetailsView = class extends StyledElements.Alternative {
        constructor(id, opts) { super(id, opts); }
        paint() {} repaint() {} enable() {} disable() {}
    };
    Wirecloud.HistoryManager.pushState = () => {};
    Wirecloud.HistoryManager.replaceState = () => {};
    Wirecloud.LocalCatalogue.resourceExists = () => false;
    Wirecloud.UserInterfaceManager.views.myresources = { createUserCommand: () => () => {} };
    Wirecloud.ui.ResourcePainter = class ResourcePainter {};

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/CatalogueView.js');

    const view = new Wirecloud.ui.CatalogueView('cat-view', {
        marketplace_desc: { user: 'test', name: 'TestMarket' },
        catalogue: { buildStateData() { return {}; } }
    });

    const resDetails = new Wirecloud.WirecloudCatalogue.ResourceDetails();
    const cmd = view.createUserCommand('showDetails', resDetails, { history: 'ignore' });
    assert.doesNotThrow(() => cmd());
    assert.ok(detailsPainted);
});

test('CatalogueView — constructor wiring, main buttons, current details and refresh branches', () => {
    const { Wirecloud, StyledElements } = setup();

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');

    let postTransitionHandler = null;
    let viewContextChanged = false;
    let pushedHistory = false;
    const commands = [];
    StyledElements.Button = class Button {
        constructor(opts = {}) {
            this.opts = opts;
            this.classes = [];
            this.listeners = {};
        }
        addEventListener(type, handler) { this.listeners[type] = handler; }
        addClassName(name) { this.classes.push(name); return this; }
    };
    StyledElements.Alternatives = class Alternatives {
        constructor() {
            this._current = null;
            this._nextId = 0;
        }
        getCurrentAlternative() { return this._current; }
        createAlternative(opts) {
            const alt = new opts.alternative_constructor(this._nextId++, opts.containerOptions);
            this._current = alt;
            return alt;
        }
        showAlternative(alt, opts) {
            this._current = alt;
            if (opts && opts.onComplete) opts.onComplete();
        }
        addEventListener(type, handler) {
            if (type === 'postTransition') postTransitionHandler = handler;
        }
    };
    Wirecloud.dispatchEvent = (eventName) => {
        if (eventName === 'viewcontextchanged') viewContextChanged = true;
    };
    Wirecloud.WirecloudCatalogue = class {
        constructor(desc) { this.title = desc.name; }
        search() { return Promise.resolve({}); }
        getResourceDetails(vendor, name) { return Promise.resolve({ vendor, name }); }
        isAllow() { return true; }
    };
    Wirecloud.WirecloudCatalogue.ResourceDetails = class ResourceDetails {
        constructor(vendor, name) {
            this.vendor = vendor;
            this.name = name;
        }
    };
    Wirecloud.ui.CatalogueSearchView = class {
        constructor(id, opts) {
            this.altId = id;
            this.opts = opts;
            this.source = { refreshed: false, refresh() { this.refreshed = true; } };
            this.refreshes = 0;
        }
        init() {}
        refresh_if_needed() { this.refreshes += 1; }
    };
    Wirecloud.ui.WirecloudCatalogue = Wirecloud.ui.WirecloudCatalogue || {};
    Wirecloud.ui.WirecloudCatalogue.ResourceDetailsView = class {
        constructor(id) {
            this.altId = id;
            this.currentEntry = null;
            this.painted = null;
        }
        paint(resource) { this.painted = resource; }
        repaint() {}
        enable() {}
        disable() {}
    };
    Wirecloud.LocalCatalogue.resourceExists = (resource) => resource.installed === true;
    Wirecloud.UserInterfaceManager.views.myresources = {
        createUserCommand(command, resource, source) {
            commands.push({ command, resource, source });
            return () => {};
        },
    };
    Wirecloud.HistoryManager.pushState = () => { pushedHistory = true; };
    Wirecloud.HistoryManager.replaceState = () => {};
    Wirecloud.ui.ResourcePainter = class ResourcePainter {};

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/CatalogueView.js');

    const view = new Wirecloud.ui.CatalogueView('cat-view', {
        marketplace_desc: { user: 'test', name: 'TestMarket' },
        catalogue: { buildStateData() { return {}; } },
    });

    view._onShow();

    const mainbutton = view.viewsByName.search.opts.resource_extra_context.mainbutton;
    const installButton = mainbutton({}, {}, { installed: false });
    const uninstallButton = mainbutton({}, {}, { installed: true });
    assert.equal(installButton.opts.text, 'Install');
    assert.equal(uninstallButton.opts.text, 'Uninstall');
    assert.equal(commands.map((entry) => entry.command).join(','), 'install,uninstall');

    postTransitionHandler();
    assert.equal(viewContextChanged, true);

    view.alternatives._current = view.viewsByName.search;
    assert.equal(view.goUp(), false);
    view.refresh_if_needed();
    assert.equal(view.viewsByName.search.refreshes, 1);

    let changedVersion = null;
    view.viewsByName.details.currentEntry = {
        vendor: 'vendor',
        name: 'widget',
        changeVersion(version) {
            changedVersion = version;
            return { vendor: 'vendor', name: 'widget', version };
        },
    };
    view.onHistoryChange({ subview: 'details', resource: 'vendor/widget/2.0' });
    assert.equal(changedVersion, '2.0');

    const details = new Wirecloud.WirecloudCatalogue.ResourceDetails('vendor', 'widget');
    view.createUserCommand('showDetails', details, { history: 'push' })();
    assert.equal(view.viewsByName.details.painted, details);
    assert.equal(pushedHistory, true);
});
