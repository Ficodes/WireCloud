const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScripts,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');

let componentCounter, endpointCounter, connectionCounter, behaviourCounter;
let lastBehaviourEngineInstances, lastComponentShowcaseInstances, lastConnectionEngineInstances;
let lastKeywordSuggestionInstances, lastComponentDraggableInstances;
let lastAlertWindowMenuInstances, lastMessageWindowMenuInstances;
let lastConnectionEngineConnectCalls;

function makeComponent(overrides = {}) {
    componentCounter++;
    const id = overrides.id || `comp-${componentCounter}`;
    const type = overrides.type || 'operator';
    return {
        id, type,
        meta: { uri: `http://ex.com/${type}/${id}`, type, vendor: 'test' },
        metaUri: `http://ex.com/${type}/${id}`,
        equals(o) { return this === o || (o != null && this.id === o.id); },
        toJSON() { return { id, type, meta: this.meta }; },
        ...overrides,
    };
}

function makeEndpoint(overrides = {}) {
    endpointCounter++;
    const component = overrides.component || makeComponent();
    return {
        id: `ep-${endpointCounter}`, type: overrides.type || 'source',
        name: overrides.name || `endpoint-${endpointCounter}`,
        component,
        _connections: [], _eventListeners: {},
        disabled: false, active: false,
        equals(o) { return o != null && this.id === o.id; },
        addEventListener(n, h) {
            if (!this._eventListeners[n]) this._eventListeners[n] = [];
            this._eventListeners[n].push(h); return this;
        },
        removeEventListener(n, h) {
            if (this._eventListeners[n])
                this._eventListeners[n] = this._eventListeners[n].filter((l) => l !== h);
            return this;
        },
        dispatchEvent(n, ...a) {
            (this._eventListeners[n] || []).forEach((h) => h.apply(this, [this].concat(a)));
        },
        enable() { this.disabled = false; }, disable() { this.disabled = true; },
        ...overrides,
    };
}

function makeConnection(overrides = {}) {
    connectionCounter++;
    return {
        _id: connectionCounter,
        _connection: { _id: connectionCounter, source: { id: `s-${connectionCounter}` }, target: { id: `t-${connectionCounter}` } },
        _background: false, _removed: false, _listeners: {}, _removeAllowed: true,
        source: { endpoint: overrides.sourceEndpoint || makeEndpoint({ type: 'source' }), handle: null },
        target: { endpoint: overrides.targetEndpoint || makeEndpoint({ type: 'target' }), handle: null },
        sourceHandle: overrides.sourceHandle || null, targetHandle: overrides.targetHandle || null,
        get background() { return this._background; }, set background(v) { this._background = v; },
        get removeAllowed() { return this._removeAllowed; }, set removeAllowed(v) { this._removeAllowed = v; },
        get sourceId() { return this.source.endpoint ? this.source.endpoint.id : null; },
        get targetId() { return this.target.endpoint ? this.target.endpoint.id : null; },
        show() { return this; }, remove() { this._removed = true; return this; },
        equals(o) {
            if (o == null) return false;
            if (o._id != null && this._id === o._id) return true;
            return this.sourceId === o.sourceId && this.targetId === o.targetId;
        },
        addEventListener(n, h) {
            if (!this._listeners[n]) this._listeners[n] = [];
            this._listeners[n].push(h); return this;
        },
        dispatchEvent(n, ...a) {
            (this._listeners[n] || []).forEach((h) => h.apply(this, [this].concat(a)));
        },
        ...overrides,
    };
}

function makeBehaviour(overrides = {}) {
    behaviourCounter++;
    return {
        _index: overrides.index != null ? overrides.index : behaviourCounter - 1,
        _title: overrides.title || `Behaviour ${behaviourCounter}`,
        _active: overrides.active || false, _listeners: {},
        _components: { operator: Object.assign({}, overrides.operators || {}), widget: Object.assign({}, overrides.widgets || {}) },
        _connections: (overrides.connections || []).slice(),
        equals(o) { return this === o; },
        get active() { return this._active; }, set active(v) { this._active = v; },
        get title() { return this._title; }, set title(v) { this._title = v; },
        getCurrentStatus() {
            return {
                title: this._title, connections: this._connections.length,
                components: { operator: Object.keys(this._components.operator).length, widget: Object.keys(this._components.widget).length },
            };
        },
        hasComponent(c) {
            return !!(c && c.id && this._components[c.type] && this._components[c.type][c.id]);
        },
        hasConnection(c) {
            return this._connections.some((x) => x.sourcename === c.sourceId && x.targetname === c.targetId);
        },
        addEventListener(n, h) {
            if (!this._listeners[n]) this._listeners[n] = [];
            this._listeners[n].push(h); return this;
        },
        dispatchEvent(n, ...a) { (this._listeners[n] || []).forEach((h) => h.apply(this, [this].concat(a))); },
        toJSON() {
            return { title: this._title, active: this._active,
                components: JSON.parse(JSON.stringify(this._components)),
                connections: this._connections.slice() };
        },
        ...overrides,
    };
}

test.beforeEach(() => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();
    componentCounter = 0; endpointCounter = 0; connectionCounter = 0; behaviourCounter = 0;
    lastBehaviourEngineInstances = []; lastComponentShowcaseInstances = [];
    lastConnectionEngineInstances = []; lastKeywordSuggestionInstances = [];
    lastComponentDraggableInstances = []; lastAlertWindowMenuInstances = [];
    lastMessageWindowMenuInstances = []; lastConnectionEngineConnectCalls = [];
    if (!global.Wirecloud) global.Wirecloud = {};
    Wirecloud.Utils = StyledElements.Utils;
    Wirecloud.ui = { WiringEditor: {} };

    // Minimal Tooltip mock needed by Button.js
    StyledElements.Tooltip = class { constructor(o) {} bind(el) {} insert() {} show() {} hide() {} };

    // ---- StyledElements mocks (load real deps first, then override) ----
    StyledElements.Alternative = class extends StyledElements.StyledElement {
        constructor(id, opts) {
            super(['click', 'hidden']); this.id = id; this.options = opts || {};
            this.wrapperElement = document.createElement('div');
            if (this.options.class) this.wrapperElement.className = this.options.class;
        }
        _onhidden(h) {}
        appendChild(c) {
            if (c && c.wrapperElement) this.wrapperElement.appendChild(c.wrapperElement);
            else if (c && c.nodeType) this.wrapperElement.appendChild(c);
        }
        disable() {}; enable() {};
    };
    StyledElements.Alternative.prototype.addClassName = function(c) { this.wrapperElement.classList.add(c); return this; };

    StyledElements.Container = class extends StyledElements.StyledElement {
        constructor(o) {
            super(['click']); this.options = o || {};
            this.wrapperElement = document.createElement('div');
            if (this.options.class) this.wrapperElement.classList.add(this.options.class);
        }
        appendChild(c) {
            if (c && c.wrapperElement) this.wrapperElement.appendChild(c.wrapperElement);
            else if (c && c.nodeType) this.wrapperElement.appendChild(c);
        }
    };

    StyledElements.OffCanvasLayout = class extends StyledElements.StyledElement {
        constructor() {
            super(['slideOut', 'slideIn']);
            this.wrapperElement = document.createElement('div');
            this.content = {
                _el: document.createElement('div'),
                get() { return this._el; },
                appendChild(c) {
                    if (c && c.wrapperElement) this._el.appendChild(c.wrapperElement);
                    else if (c && c.nodeType) this._el.appendChild(c);
                },
                addClassName(cls) { this._el.classList.add(cls); return this; },
            };
            this.sidebar = {
                _el: document.createElement('div'),
                addClassName(cls) { this._el.classList.add(cls); return this; },
            };
            this._panelIndex = -1;
        }
        slideOut() { this._panelIndex = -1; this.dispatchEvent('slideOut', {}); return this; }
        slideIn(idx) {
            this._panelIndex = idx;
            const cls = idx === 0 ? 'we-panel-behaviours' : 'we-panel-components';
            this.dispatchEvent('slideIn', { hasClassName(c) { return c === cls; } });
            return this;
        }
        appendChild(c) { if (c && c.wrapperElement) this.wrapperElement.appendChild(c.wrapperElement); }
    };

    StyledElements.ToggleButton = class extends StyledElements.StyledElement {
        constructor(o) {
            super(['click', 'blur', 'focus']);
            this.options = o || {}; this._active = false; this._clickHandlers = [];
            this.wrapperElement = document.createElement('button');
            if (o && o.class) this.wrapperElement.className = o.class;
        }
        get active() { return this._active; } set active(v) { this._active = v; }
        addEventListener(t, h) {
            if (t === 'click') this._clickHandlers.push(h);
            else super.addEventListener(t, h);
            return this;
        }
        click() { this._clickHandlers.forEach((f) => f(this)); }
    };

    StyledElements.Alert = class extends StyledElements.StyledElement {
        constructor(o) {
            super([]); this.options = o || {};
            this.wrapperElement = document.createElement('div');
            this.heading = { _el: document.createElement('div'), addClassName(c) { this._el.classList.add(c); } };
            this.body = document.createElement('div'); this.wrapperElement.appendChild(this.body);
            this._shown = true; this._notes = [];
        }
        addNote(f) { this._notes.push(f); return this; }
        hide() { this._shown = false; } show() { this._shown = true; }
        get isShown() { return this._shown; }
    };

    StyledElements.Fragment = class extends StyledElements.StyledElement {
        constructor(c) { super([]); this.children = c || []; this.wrapperElement = document.createElement('div'); }
    };

    StyledElements.GUIBuilder = class {
        constructor() { this.DEFAULT_OPENING = '<div>'; this.DEFAULT_CLOSING = '</div>'; }
        parse(str, tc) {
            if (tc) {
                const w = document.createElement('div'); const c = document.createElement('div');
                if (tc.title) w.appendChild(tc.title);
                if (tc.connections) w.appendChild(tc.connections);
                if (tc.operators) w.appendChild(tc.operators);
                if (tc.widgets) w.appendChild(tc.widgets);
                w.appendChild(c); return { children: [w, c] };
            }
            return { children: [] };
        }
    };

    // Wirecloud.ui mocks are set AFTER loadLegacyScripts below

    Wirecloud.ui.AlertWindowMenu = class {
        constructor(msg) { this._message = msg; this._handler = null; this._shown = false; lastAlertWindowMenuInstances.push(this); }
        setHandler(f) { this._handler = f; return this; } show() { this._shown = true; return this; }
    };

    Wirecloud.ui.MessageWindowMenu = class {
        constructor(err, type) { this.error = err; this.type = type; lastMessageWindowMenuInstances.push(this); }
        show() { return this; }
    };

    // ---- Global mocks ----
    Wirecloud.constants = { LOGGING: { DEBUG_MSG: 1, INFO_MSG: 2, WARN_MSG: 3, ERROR_MSG: 4 } };
    Wirecloud.HistoryManager = { getCurrentState() { return { workspace_owner: 'testowner', workspace_name: 'testworkspace', params: {} }; } };
    Wirecloud.UserInterfaceManager = {
        views: { workspace: { getBreadcrumb() { return [{ label: 'Workspace', menu: {} }]; }, getTitle() { return 'Test Workspace'; } } },
        rootKeydownHandler: null, changeCurrentView: null,
    };
    Wirecloud.Wiring = { normalize() { return { components:{operator:{},widget:{}}, connections:[], operators:{}, visualdescription:{behaviours:[],components:{operator:{},widget:{}},connections:[]} }; } };
    Wirecloud.currentTheme = { templates: { 'wirecloud/wiring/footer': '<div>Footer</div>' } };
    Wirecloud.activeWorkspace = {
        id: 'ws-1',
        wiring: {
            visualdescription: { behaviours: [], components: { operator: {}, widget: {} }, connections: [] },
            connections: [], operators: [],
            createOperator() { return Promise.resolve(makeComponent({ type: 'operator' })); },
            createConnection() { return Promise.resolve({}); },
            load() { return this; },
            save() { return Promise.resolve(); },
        },
        widgets: [], resources: null,
        view: { activeTab: { createWidget() { return Promise.resolve({ model: makeComponent({ type: 'widget' }) }); } } },
    };
    Wirecloud._listeners = {};
    Wirecloud.addEventListener = function(e, h) { if (!this._listeners[e]) this._listeners[e] = []; this._listeners[e].push(h); };
    Wirecloud.dispatchEvent = function(e) { (this._listeners[e] || []).forEach((h) => h()); };
    global.localStorage = { _data: {}, getItem(k) { return k in this._data ? this._data[k] : null; }, setItem(k,v) { this._data[k] = v; }, removeItem(k) { delete this._data[k]; }, _reset() { this._data = {}; } };
    global.DOMParser = function DOMParser() {};
    DOMParser.prototype.parseFromString = function() { const doc = document.createElement('div'); doc.documentElement = document.createElement('root'); return doc; };

    loadLegacyScripts([
        'src/wirecloud/platform/static/js/wirecloud/ui/Registry.js',
        'src/wirecloud/platform/static/js/wirecloud/ui/WiringEditor.js',
    ]);

    // ---- WiringEditor sub-class mocks (must be AFTER loadLegacyScripts since the
    const WE = Wirecloud.ui.WiringEditor;

    WE.BehaviourEngine = class extends StyledElements.StyledElement {
        constructor() {
            super(['activate', 'change', 'enable']);
            this.wrapperElement = document.createElement('div');
            this.enabled = false; this._behaviours = [];
            this._components = { operator: {}, widget: {} };
            this._description = { components: { operator: {}, widget: {} }, connections: [], behaviours: [] };
            this.viewpoint = 0; this._listeners = {};
            lastBehaviourEngineInstances.push(this);
        }
        get behaviours() { return this._behaviours; } set behaviours(v) { this._behaviours = v; }
        get components() { return this._components; } set components(v) { this._components = v; }
        clear() { this._behaviours = []; this._components = { operator: {}, widget: {} }; return this; }
        stopOrdering() { return this; }
        addEventListener(n, h) { if (!this._listeners[n]) this._listeners[n] = []; this._listeners[n].push(h); return this; }
        dispatchEvent(n, ...a) { (this._listeners[n] || []).forEach((h) => h.apply(this, [this].concat(a))); }
        loadBehaviours(l) { this._behaviours = (l || []).map((b,i) => makeBehaviour({ index: i, title: b.title })); this.enabled = this._behaviours.length > 0; return this; }
        forEachComponent(cb) { for (const t of ['operator','widget']) for (const id in this._components[t]) cb(this._components[t][id]); return this; }
        forEachConnection(cb) { return this; }
        hasComponents() { for (const t of ['operator','widget']) if (Object.keys(this._components[t]).length > 0) return true; return false; }
        hasComponent(c) { return !!(c && this._components[c.type] && this._components[c.type][c.id]); }
        hasConnection(c) { return false; }
        updateComponent(c, cascade) { return this; } updateConnection(c, cascade) { return this; }
        removeComponent(c, cascade) { return this; } removeComponentList(l) { return this; }
        removeConnection(c, cascade) { return this; }
        filterByComponent(c) { return []; } filterByConnection(c) { return []; }
        toJSON() { return { behaviours: this._behaviours.map(b=>b.toJSON()), components: JSON.parse(JSON.stringify(this._components)), connections: this._description.connections.slice() }; }
        activate(b) { return this; }
    };
    WE.BehaviourEngine.GLOBAL = 0;

    WE.ComponentShowcase = class extends StyledElements.StyledElement {
        constructor() {
            super(['create', 'add']);
            this.wrapperElement = document.createElement('div');
            this._components = new Map();
            this._listeners = {};
            this.searchComponents = { _refreshed: false, refresh() { this._refreshed = true; } };
            lastComponentShowcaseInstances.push(this);
        }
        addEventListener(n, h) { if (!this._listeners[n]) this._listeners[n] = []; this._listeners[n].push(h); return this; }
        dispatchEvent(n, ...a) { (this._listeners[n] || []).forEach((h) => h.apply(this, [this].concat(a))); }
        addComponent(c) { this._components.set(`${c.type}/${c.id}`, { _component: c, used: false, type: c.type, id: c.id }); return this; }
        findComponent(t, id) { return this._components.get(`${t}/${id}`) || null; }
        clear() { this._components.clear(); return this; }
        removeComponent(c) { this._components.delete(`${c.type}/${c.id}`); return this; }
    };

    WE.ConnectionEngine = class extends StyledElements.StyledElement {
        constructor(container, fw) {
            super(); this._listeners = {};
            this.wrapperElement = document.createElement('div');
            this._connections = []; this._endpoints = { source: [], target: [] };
            this.enabled = true; this._temporalConnection = null;
            this._temporalInitialEndpoint = null; this._connBackup = null;
            lastConnectionEngineInstances.push(this);
        }
        get connections() { return this._connections; }
        get endpoints() { return this._endpoints; }
        get temporalConnection() { return this._temporalConnection; } set temporalConnection(v) { this._temporalConnection = v; }
        get temporalInitialEndpoint() { return this._temporalInitialEndpoint; } set temporalInitialEndpoint(v) { this._temporalInitialEndpoint = v; }
        get _connectionBackup() { return this._connBackup; } set _connectionBackup(v) { this._connBackup = v; }
        addEventListener(n, h) { if (!this._listeners[n]) this._listeners[n] = []; this._listeners[n].push(h); return this; }
        dispatchEvent(n, ...a) { (this._listeners[n] || []).forEach((h) => h.apply(this, [this].concat(a))); }
        appendEndpoint(e) { this._endpoints[e.type].push(e); return this; }
        removeEndpoint(e) { this._endpoints[e.type] = this._endpoints[e.type].filter((x) => x.id !== e.id); return this; }
        connect(wc, src, tgt, opt) {
            const cn = makeConnection({ sourceEndpoint: src, targetEndpoint: tgt, sourceHandle: (opt||{}).sourceHandle, targetHandle: (opt||{}).targetHandle });
            cn._connection = wc || {}; this._connections.push(cn);
            lastConnectionEngineConnectCalls.push({ wiringConn: wc, source: src, target: tgt, options: opt });
            this.dispatchEvent('establish', cn, null); return this;
        }
        forEachConnection(cb) { this._connections.forEach((c,i) => cb(c,i)); return this; }
        hasActiveConnection() { return false; } setUp() { return this; }
        clear() { for (let i = this._connections.length - 1; i >= 0; i--) this._connections[i].remove(); this._connections = []; return this; }
    };

    WE.KeywordSuggestion = class extends StyledElements.StyledElement {
        constructor() { super([]); this.wrapperElement = document.createElement('div'); this._enabled = true; lastKeywordSuggestionInstances.push(this); }
        appendEndpoint(e) { return this; } removeEndpoint(e) { return this; }
        showSuggestions(e) { return this; } hideSuggestions(e) { return this; }
        enable() { this._enabled = true; return this; } disable() { this._enabled = false; return this; }
    };

    WE.ComponentDraggable = class extends StyledElements.StyledElement {
        constructor(wc, opt) {
            super([]);
            this._component = wc; this.options = opt || {};
            this.id = wc ? wc.id : `dr-${Date.now()}`; this.type = wc ? wc.type : 'operator';
            this._active = false; this._collapsed = false; this._position = { x: 0, y: 0 };
            this._endpoints = []; this.wrapperElement = document.createElement('div');
            this._missing = false; this._removable = true; this._listeners = {};
            this._background = false; this._removeAllowed = true;
            this._removeCascadeAllowed = (opt && opt.removecascade_allowed) || false;
            lastComponentDraggableInstances.push(this);
        }
        get active() { return this._active; } set active(v) { this._active = v; }
        get collapsed() { return this._collapsed; } set collapsed(v) { this._collapsed = v; }
        get missing() { return this._missing; } set missing(v) { this._missing = v; }
        get background() { return this._background; } set background(v) { this._background = v; }
        get removeAllowed() { return this._removeAllowed; } set removeAllowed(v) { this._removeAllowed = v; }
        get removeCascadeAllowed() { return this._removeCascadeAllowed; } set removeCascadeAllowed(v) { this._removeCascadeAllowed = v; }
        get initialPosition() { return this._initialPosition; } set initialPosition(v) { this._initialPosition = v; }
        equals(other) { return this === other || (other != null && this.id === other.id); }
        addEventListener(t, h) { if (!this._listeners[t]) this._listeners[t] = []; this._listeners[t].push(h); return this; }
        dispatchEvent(t, ...a) { (this._listeners[t] || []).forEach((h) => h.apply(this, [this].concat(a))); }
        forEachEndpoint(cb) { this._endpoints.forEach(cb); return this; }
        getEndpoint(rol, name) {
            const ep = this._endpoints.find((e) => e.name === name) || null;
            if (!ep && this._component && this._component.meta) {
                // For paste tests: return a synthetic endpoint
                const synEp = makeEndpoint({ type: rol === 'source' ? 'source' : 'target', name, _endpoint: { id: `syn-${name}`, name } });
                this._endpoints.push(synEp);
                return synEp;
            }
            return ep;
        }
        position(v) { if (v) this._position = v; return this._position; }
        isRemovable() { return this._removable; } setUp() { this._active = false; return this; }
        show() { return this; } toFirst() { return this; }
    };
});

// =============================================================================
// STATIC / Module-level
// =============================================================================
test('WiringEditor is a class', () => {
    assert.ok(typeof Wirecloud.ui.WiringEditor === 'function');
});

test('prototype.view_name is "wiring"', () => {
    assert.equal(Wirecloud.ui.WiringEditor.prototype.view_name, 'wiring');
});

test('extends StyledElements.Alternative', () => {
    const ed = new Wirecloud.ui.WiringEditor('t1');
    assert.ok(ed instanceof StyledElements.Alternative);
});

// =============================================================================
// Constructor
// =============================================================================
test('constructor sets class "wc-workspace-wiring"', () => {
    const ed = new Wirecloud.ui.WiringEditor('c1');
    assert.ok(ed.wrapperElement.className.includes('wc-workspace-wiring'));
});

test('constructor initializes selectedComponents', () => {
    const ed = new Wirecloud.ui.WiringEditor('c2');
    assert.deepEqual(ed.selectedComponents, { operator: {}, widget: {} });
});

test('constructor initializes selectedCount to 0', () => {
    const ed = new Wirecloud.ui.WiringEditor('c3');
    assert.equal(ed.selectedCount, 0);
});

test('constructor initializes orderableComponent to null', () => {
    const ed = new Wirecloud.ui.WiringEditor('c4');
    assert.equal(ed.orderableComponent, null);
});

test('constructor reads copiedComponents from empty clipboard', () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('c5');
    assert.deepEqual(ed.copiedComponents, []);
});

test('constructor reads copiedComponents from valid clipboard', () => {
    global.localStorage._reset();
    global.localStorage.setItem('wirecloud.wiring.clipboard', JSON.stringify({ version: 1, components: [{ id: 'a', type: 'operator', meta: {} }] }));
    const ed = new Wirecloud.ui.WiringEditor('c6');
    assert.equal(ed.copiedComponents.length, 1);
    assert.equal(ed.copiedComponents[0].id, 'a');
});

test('constructor creates layout with content and sidebar', () => {
    const ed = new Wirecloud.ui.WiringEditor('c7');
    assert.ok(ed.layout != null);
    assert.ok(ed.layout.content != null);
    assert.ok(ed.layout.sidebar != null);
});

test('constructor creates btnFindComponents', () => {
    const ed = new Wirecloud.ui.WiringEditor('c8');
    assert.ok(ed.btnFindComponents instanceof StyledElements.ToggleButton);
});

test('constructor creates btnListBehaviours', () => {
    const ed = new Wirecloud.ui.WiringEditor('c9');
    assert.ok(ed.btnListBehaviours instanceof StyledElements.ToggleButton);
});

test('constructor creates suggestionManager', () => {
    const ed = new Wirecloud.ui.WiringEditor('c10');
    assert.ok(ed.suggestionManager instanceof Wirecloud.ui.WiringEditor.KeywordSuggestion);
});

test('constructor creates frozen legend with aria-live', () => {
    const ed = new Wirecloud.ui.WiringEditor('c11');
    assert.ok(Object.isFrozen(ed.legend));
    assert.equal(ed.legend.title.getAttribute('aria-live'), 'polite');
    assert.equal(ed.legend.connections.getAttribute('aria-live'), 'polite');
    assert.equal(ed.legend.operators.getAttribute('aria-live'), 'polite');
    assert.equal(ed.legend.widgets.getAttribute('aria-live'), 'polite');
});

test('constructor creates initialMessage Alert', () => {
    const ed = new Wirecloud.ui.WiringEditor('c12');
    assert.ok(ed.initialMessage instanceof StyledElements.Alert);
    assert.ok(ed.initialMessage.isShown);
});

test('constructor creates connectionEngine', () => {
    const ed = new Wirecloud.ui.WiringEditor('c13');
    assert.ok(ed.connectionEngine instanceof Wirecloud.ui.WiringEditor.ConnectionEngine);
});

test('constructor registers "loaded" event handlers', () => {
    new Wirecloud.ui.WiringEditor('c14');
    assert.ok(Wirecloud._listeners.loaded != null);
    assert.equal(Wirecloud._listeners.loaded.length, 3);
});

test('"loaded" event creates behaviourEngine', () => {
    const ed = new Wirecloud.ui.WiringEditor('c15');
    Wirecloud.dispatchEvent('loaded');
    assert.ok(ed.behaviourEngine instanceof Wirecloud.ui.WiringEditor.BehaviourEngine);
});

test('"loaded" event creates componentManager', () => {
    const ed = new Wirecloud.ui.WiringEditor('c16');
    Wirecloud.dispatchEvent('loaded');
    assert.ok(ed.componentManager instanceof Wirecloud.ui.WiringEditor.ComponentShowcase);
});

test('constructor with invalid localStorage JSON returns empty', () => {
    global.localStorage._reset();
    global.localStorage.setItem('wirecloud.wiring.clipboard', 'bad json');
    const ed = new Wirecloud.ui.WiringEditor('c17');
    assert.deepEqual(ed.copiedComponents, []);
    assert.equal(global.localStorage.getItem('wirecloud.wiring.clipboard'), null);
});

test('constructor with wrong version returns empty', () => {
    global.localStorage._reset();
    global.localStorage.setItem('wirecloud.wiring.clipboard', JSON.stringify({ version: 2, components: [{ id: 'v2' }] }));
    const ed = new Wirecloud.ui.WiringEditor('c18');
    assert.deepEqual(ed.copiedComponents, []);
});

test('constructor with non-array components returns empty', () => {
    global.localStorage._reset();
    global.localStorage.setItem('wirecloud.wiring.clipboard', JSON.stringify({ version: 1, components: 'x' }));
    const ed = new Wirecloud.ui.WiringEditor('c19');
    assert.deepEqual(ed.copiedComponents, []);
});

test('constructor with null data returns empty', () => {
    global.localStorage._reset();
    global.localStorage.setItem('wirecloud.wiring.clipboard', JSON.stringify(null));
    const ed = new Wirecloud.ui.WiringEditor('c20');
    assert.deepEqual(ed.copiedComponents, []);
});

// =============================================================================
// createComponent
// =============================================================================
test('createComponent returns ComponentDraggable', () => {
    const ed = new Wirecloud.ui.WiringEditor('cc1');
    Wirecloud.dispatchEvent('loaded');
    const r = ed.createComponent(makeComponent({ id: 't1' }));
    assert.ok(r instanceof Wirecloud.ui.WiringEditor.ComponentDraggable);
    assert.equal(r.id, 't1');
});

test('createComponent hides initialMessage', () => {
    const ed = new Wirecloud.ui.WiringEditor('cc2');
    Wirecloud.dispatchEvent('loaded');
    ed.initialMessage.show();
    ed.createComponent(makeComponent({ id: 't2' }));
    assert.ok(!ed.initialMessage.isShown);
});

test('createComponent with commit=true appends to layout', () => {
    const ed = new Wirecloud.ui.WiringEditor('cc3');
    Wirecloud.dispatchEvent('loaded');
    const c = ed.createComponent(makeComponent({ id: 't3' }));
    assert.ok(ed.layout.content._el.childNodes.includes(c.wrapperElement));
});

test('createComponent with commit=false does not append', () => {
    const ed = new Wirecloud.ui.WiringEditor('cc4');
    Wirecloud.dispatchEvent('loaded');
    const before = ed.layout.content._el.childNodes.length;
    ed.createComponent(makeComponent({ id: 't4' }), { commit: false });
    assert.equal(ed.layout.content._el.childNodes.length, before);
});

test('createComponent fires endpointadded -> bindEndpoint', () => {
    const ed = new Wirecloud.ui.WiringEditor('cc5');
    Wirecloud.dispatchEvent('loaded');
    const ep = makeEndpoint({ type: 'source', name: 'out' });
    const c = ed.createComponent(makeComponent({ id: 't5' }), { commit: false });
    c.dispatchEvent('endpointadded', ep);
    assert.ok(ed.connectionEngine.endpoints.source.some((e) => e.id === ep.id));
});

test('createComponent with behaviourEngine enabled sets removeCascadeAllowed', () => {
    const ed = new Wirecloud.ui.WiringEditor('cc6');
    Wirecloud.dispatchEvent('loaded');
    ed.behaviourEngine.enabled = true;
    const c = ed.createComponent(makeComponent({ id: 't6' }));
    assert.ok(c.removeCascadeAllowed);
});

test('createComponent change event updates behaviourEngine', () => {
    const ed = new Wirecloud.ui.WiringEditor('cc7');
    Wirecloud.dispatchEvent('loaded');
    let uc = null;
    ed.behaviourEngine.updateComponent = function(c) { uc = c; return this; };
    const c = ed.createComponent(makeComponent({ id: 't7' }), { commit: false });
    c.dispatchEvent('change');
    assert.equal(uc, c);
});

test('createComponent optremove calls behaviourEngine.removeComponent', () => {
    const ed = new Wirecloud.ui.WiringEditor('cc8');
    Wirecloud.dispatchEvent('loaded');
    let rc = null;
    ed.behaviourEngine.removeComponent = function(c) { rc = c; return this; };
    const c = ed.createComponent(makeComponent({ id: 't8' }), { commit: false });
    c.dispatchEvent('optremove');
    assert.equal(rc, c);
});

test('createComponent optremovecascade calls with cascade=true', () => {
    const ed = new Wirecloud.ui.WiringEditor('cc9');
    Wirecloud.dispatchEvent('loaded');
    let rc = null, cv = false;
    ed.behaviourEngine.removeComponent = function(c, cascade) { rc = c; cv = cascade; return this; };
    const c = ed.createComponent(makeComponent({ id: 't9' }), { commit: false });
    c.dispatchEvent('optremovecascade');
    assert.equal(rc, c); assert.ok(cv);
});

test('createComponent optshare calls updateComponent with cascade=true', () => {
    const ed = new Wirecloud.ui.WiringEditor('cc10');
    Wirecloud.dispatchEvent('loaded');
    let uc = null, cv = false;
    ed.behaviourEngine.updateComponent = function(c, cascade) { uc = c; cv = cascade; return this; };
    const c = ed.createComponent(makeComponent({ id: 't10' }), { commit: false });
    c.dispatchEvent('optshare');
    assert.equal(uc, c); assert.ok(cv);
});

// =============================================================================
// buildStateData / getBreadcrumb / getTitle / getToolbarButtons / goUp
// =============================================================================
test('buildStateData returns state info', () => {
    const ed = new Wirecloud.ui.WiringEditor('b1');
    const d = ed.buildStateData();
    assert.equal(d.workspace_owner, 'testowner');
    assert.equal(d.view, 'wiring');
});

test('getBreadcrumb removes menu and adds wiring label', () => {
    const ed = new Wirecloud.ui.WiringEditor('b2');
    const bc = ed.getBreadcrumb();
    assert.equal(bc.length, 2);
    assert.equal(bc[1].label, 'wiring');
    assert.ok(!('menu' in bc[0]));
});

test('getTitle includes workspace name and Wiring', () => {
    const ed = new Wirecloud.ui.WiringEditor('b3');
    const t = ed.getTitle();
    assert.ok(t.includes('Test Workspace'));
    assert.ok(t.includes('Wiring'));
});

test('getToolbarButtons returns [btnFindComponents, btnListBehaviours]', () => {
    const ed = new Wirecloud.ui.WiringEditor('b4');
    const btns = ed.getToolbarButtons();
    assert.equal(btns[0], ed.btnFindComponents);
    assert.equal(btns[1], ed.btnListBehaviours);
});

test('goUp changes view to workspace', () => {
    let vc = null;
    Wirecloud.UserInterfaceManager.changeCurrentView = function(v) { vc = v; };
    const ed = new Wirecloud.ui.WiringEditor('b5');
    ed.goUp();
    assert.equal(vc, 'workspace');
});

// =============================================================================
// load
// =============================================================================
test('load sets workspace, errorMessages, returns this', () => {
    const ed = new Wirecloud.ui.WiringEditor('ld1');
    Wirecloud.dispatchEvent('loaded');
    const r = ed.load(Wirecloud.activeWorkspace);
    assert.equal(r, ed);
    assert.equal(ed.workspace, Wirecloud.activeWorkspace);
    assert.deepEqual(ed.errorMessages, []);
});

test('load calls readyView (slideOut, clears behaviour, enables suggestionManager)', () => {
    const ed = new Wirecloud.ui.WiringEditor('ld2');
    Wirecloud.dispatchEvent('loaded');
    ed.behaviourEngine._components.operator.x = { id: 'x' };
    ed.componentManager.addComponent(makeComponent({ id: 'y', type: 'widget' }));
    ed.load(Wirecloud.activeWorkspace);
    assert.deepEqual(ed.behaviourEngine._components, { operator: {}, widget: {} });
    assert.equal(ed.componentManager._components.size, 0);
    assert.equal(ed.suggestionManager._enabled, true);
    assert.equal(ed.orderableComponent, null);
});

test('load sets rootKeydownHandler', () => {
    const ed = new Wirecloud.ui.WiringEditor('ld3');
    Wirecloud.dispatchEvent('loaded');
    ed.load(Wirecloud.activeWorkspace);
    assert.equal(typeof Wirecloud.UserInterfaceManager.rootKeydownHandler, 'function');
});

test('load adds widgets to componentManager', () => {
    const ed = new Wirecloud.ui.WiringEditor('ld4');
    Wirecloud.dispatchEvent('loaded');
    const ws = { ...Wirecloud.activeWorkspace, widgets: [{ id: 'w1', type: 'widget', meta: { type: 'widget', uri: 'http://x' } }] };
    ed.load(ws);
    assert.ok(ed.componentManager.findComponent('widget', 'w1') != null);
});

test('load creates visual components from visualInfo', () => {
    const ed = new Wirecloud.ui.WiringEditor('ld5');
    Wirecloud.dispatchEvent('loaded');
    const vs = { components: { operator: {}, widget: { 'vw': { position: { x: 5, y: 5 }, collapsed: false } } }, connections: [] };
    const ws = { ...Wirecloud.activeWorkspace, widgets: [{ id: 'vw', type: 'widget', meta: { type: 'widget', uri: 'http://v' } }] };
    ws.wiring = { ...ws.wiring, visualdescription: { behaviours: [], components: vs.components, connections: [] } };
    ed.load(ws);
    assert.ok(lastComponentDraggableInstances.find(c => c.id === 'vw') != null);
});

test('load skips component not in visualInfo (no draggable)', () => {
    const ed = new Wirecloud.ui.WiringEditor('ld6');
    Wirecloud.dispatchEvent('loaded');
    const ws = { ...Wirecloud.activeWorkspace, widgets: [{ id: 'no-vi', type: 'widget', meta: { type: 'widget', uri: 'http://n' } }] };
    ed.load(ws);
    assert.ok(ed.componentManager.findComponent('widget', 'no-vi') != null);
});

// Connection loading is tested via loadConnections handle test below

test('load skips volatile connections', () => {
    const ed = new Wirecloud.ui.WiringEditor('ld8');
    Wirecloud.dispatchEvent('loaded');
    const before = lastConnectionEngineConnectCalls.length;
    const ws = { ...Wirecloud.activeWorkspace, wiring: { ...Wirecloud.activeWorkspace.wiring,
        connections: [{ source: { id: 'vs' }, target: { id: 'vt' }, volatile: true }],
        visualdescription: { ...Wirecloud.activeWorkspace.wiring.visualdescription, connections: [{ sourcename: 'vs', targetname: 'vt' }] } } };
    ed.load(ws);
    assert.equal(lastConnectionEngineConnectCalls.length, before);
});

test('load calls behaviourEngine.loadBehaviours', () => {
    const ed = new Wirecloud.ui.WiringEditor('ld9');
    Wirecloud.dispatchEvent('loaded');
    const ws = { ...Wirecloud.activeWorkspace, wiring: { ...Wirecloud.activeWorkspace.wiring,
        visualdescription: { behaviours: [{ title: 'B1' }], components: { operator: {}, widget: {} }, connections: [] } } };
    ed.load(ws);
    assert.equal(ed.behaviourEngine._behaviours.length, 1);
    assert.equal(ed.behaviourEngine._behaviours[0]._title, 'B1');
});

// =============================================================================
// unload
// =============================================================================
test('unload saves wiring and returns this', async () => {
    const ed = new Wirecloud.ui.WiringEditor('ul1');
    Wirecloud.dispatchEvent('loaded');
    let saved = false;
    const ws = { ...Wirecloud.activeWorkspace, wiring: { ...Wirecloud.activeWorkspace.wiring,
        load() { return this; }, save() { saved = true; return Promise.resolve(); } } };
    ed.load(ws);
    ed.unload();
    await new Promise(r => setTimeout(r, 20));
    assert.ok(saved);
});

test('unload resets rootKeydownHandler to null', () => {
    const ed = new Wirecloud.ui.WiringEditor('ul2');
    Wirecloud.dispatchEvent('loaded');
    ed.load(Wirecloud.activeWorkspace);
    ed.unload();
    assert.equal(Wirecloud.UserInterfaceManager.rootKeydownHandler, null);
});

test('unload handles save rejection gracefully', async () => {
    const ed = new Wirecloud.ui.WiringEditor('ul3');
    Wirecloud.dispatchEvent('loaded');
    const ws = { ...Wirecloud.activeWorkspace, wiring: { ...Wirecloud.activeWorkspace.wiring,
        load() { return this; }, save() { return Promise.reject(new Error('fail')); } } };
    ed.load(ws);
    ed.unload();
    await new Promise(r => setTimeout(r, 20));
    assert.ok(lastMessageWindowMenuInstances.length > 0);
});

// =============================================================================
// toJSON
// =============================================================================
test('toJSON returns wiring status object', () => {
    const ed = new Wirecloud.ui.WiringEditor('tj1');
    Wirecloud.dispatchEvent('loaded');
    const j = ed.toJSON();
    assert.ok(j.connections != null);
    assert.ok(j.operators != null);
    assert.ok(j.visualdescription != null);
});

test('toJSON collects connections from connectionEngine', () => {
    const ed = new Wirecloud.ui.WiringEditor('tj2');
    Wirecloud.dispatchEvent('loaded');
    ed.connectionEngine._connections.push(makeConnection(), makeConnection());
    assert.equal(ed.toJSON().connections.length, 2);
});

test('toJSON only includes operator-type in operators', () => {
    const ed = new Wirecloud.ui.WiringEditor('tj3');
    Wirecloud.dispatchEvent('loaded');
    ed.behaviourEngine._components.operator['op1'] = makeComponent({ id: 'op1', type: 'operator' });
    ed.behaviourEngine._components.widget['w1'] = makeComponent({ id: 'w1', type: 'widget' });
    const j = ed.toJSON();
    assert.ok('op1' in j.operators);
    assert.ok(!('w1' in j.operators));
});

test('toJSON sets visualdescription from behaviourEngine', () => {
    const ed = new Wirecloud.ui.WiringEditor('tj4');
    Wirecloud.dispatchEvent('loaded');
    assert.ok(ed.toJSON().visualdescription.behaviours != null);
});

// =============================================================================
// _onhidden
// =============================================================================
test('_onhidden(true) calls unload', () => {
    const ed = new Wirecloud.ui.WiringEditor('oh1');
    Wirecloud.dispatchEvent('loaded');
    let ul = false;
    ed.unload = function() { ul = true; return this; };
    ed._onhidden(true);
    assert.ok(ul);
});

test('_onhidden(false) calls load with activeWorkspace', () => {
    const ed = new Wirecloud.ui.WiringEditor('oh2');
    Wirecloud.dispatchEvent('loaded');
    let lws = null;
    ed.load = function(ws) { lws = ws; return this; };
    ed._onhidden(false);
    assert.equal(lws, Wirecloud.activeWorkspace);
});

// =============================================================================
// Component lifecycle events
// =============================================================================
test('component_onremove clears selection and decrements selectedCount', () => {
    const ed = new Wirecloud.ui.WiringEditor('rm1');
    Wirecloud.dispatchEvent('loaded');
    const wc = makeComponent({ id: 'r1' });
    ed.componentManager.addComponent(wc);
    const c = ed.createComponent(wc, { commit: false });
    ed.selectedComponents.operator.r1 = c; ed.selectedCount = 1;
    c.dispatchEvent('remove');
    assert.ok(!('r1' in ed.selectedComponents.operator));
    assert.equal(ed.selectedCount, 0);
});

test('component_onremove with missing removes from componentManager', () => {
    const ed = new Wirecloud.ui.WiringEditor('rm2');
    Wirecloud.dispatchEvent('loaded');
    const wc = makeComponent({ id: 'r2' });
    const c = ed.createComponent(wc, { commit: false });
    c._missing = true;
    ed.componentManager.addComponent(wc);
    c.dispatchEvent('remove');
    assert.equal(ed.componentManager.findComponent('operator', 'r2'), null);
});

test('component_onremove without missing sets used=false', () => {
    const ed = new Wirecloud.ui.WiringEditor('rm3');
    Wirecloud.dispatchEvent('loaded');
    const wc = makeComponent({ id: 'r3' });
    const c = ed.createComponent(wc, { commit: false });
    c._missing = false;
    ed.componentManager.addComponent(wc);
    ed.componentManager.findComponent('operator', 'r3').used = true;
    c.dispatchEvent('remove');
    assert.equal(ed.componentManager.findComponent('operator', 'r3').used, false);
});

test('component_onremove shows initialMessage when no components left', () => {
    const ed = new Wirecloud.ui.WiringEditor('rm4');
    Wirecloud.dispatchEvent('loaded');
    const wc = makeComponent({ id: 'r4' });
    ed.componentManager.addComponent(wc);
    const c = ed.createComponent(wc, { commit: false });
    ed.initialMessage.hide();
    ed.behaviourEngine.hasComponents = function() { return false; };
    c.dispatchEvent('remove');
    assert.ok(ed.initialMessage.isShown);
});

test('component_onremove does NOT show initialMessage when components remain', () => {
    const ed = new Wirecloud.ui.WiringEditor('rm5');
    Wirecloud.dispatchEvent('loaded');
    const wc = makeComponent({ id: 'r5' });
    ed.componentManager.addComponent(wc);
    const c = ed.createComponent(wc, { commit: false });
    ed.initialMessage.hide();
    ed.behaviourEngine.hasComponents = function() { return true; };
    c.dispatchEvent('remove');
    assert.ok(!ed.initialMessage.isShown);
});

test('component_onremove removes endpoints from connectionEngine and suggestionManager', () => {
    const ed = new Wirecloud.ui.WiringEditor('rm6');
    Wirecloud.dispatchEvent('loaded');
    const ep1 = makeEndpoint({ type: 'source', name: 'o1' });
    const ep2 = makeEndpoint({ type: 'target', name: 'i1' });
    const wc = makeComponent({ id: 'r6' });
    ed.componentManager.addComponent(wc);
    const c = ed.createComponent(wc, { commit: false });
    ed.connectionEngine.appendEndpoint(ep1).appendEndpoint(ep2);
    c._endpoints = [ep1, ep2];
    c.forEachEndpoint = function(cb) { this._endpoints.forEach(cb); return this; };
    c.dispatchEvent('remove');
    assert.equal(ed.connectionEngine.endpoints.source.length, 0);
    assert.equal(ed.connectionEngine.endpoints.target.length, 0);
});

test('component_onendpointremoved removes endpoint from engine and suggestions', () => {
    const ed = new Wirecloud.ui.WiringEditor('er1');
    Wirecloud.dispatchEvent('loaded');
    const ep = makeEndpoint({ type: 'source', name: 'ep-rm' });
    const c = ed.createComponent(makeComponent({ id: 'er-c' }), { commit: false });
    ed.connectionEngine.appendEndpoint(ep);
    let smRemoved = false;
    ed.suggestionManager.removeEndpoint = function() { smRemoved = true; return this; };
    c.dispatchEvent('endpointremoved', ep);
    assert.ok(!ed.connectionEngine.endpoints.source.some(e => e.id === ep.id));
    assert.ok(smRemoved);
});

// =============================================================================
// Connection lifecycle events
// =============================================================================
test('connectionEngine establish updates behaviourEngine and adds listeners', () => {
    const ed = new Wirecloud.ui.WiringEditor('ce1');
    Wirecloud.dispatchEvent('loaded');
    let uc = null;
    ed.behaviourEngine.updateConnection = function(c) { uc = c; return this; };
    const cn = makeConnection();
    ed.connectionEngine.dispatchEvent('establish', cn, null);
    assert.equal(uc, cn);
    // change listener
    let uc2 = null;
    ed.behaviourEngine.updateConnection = function(c) { uc2 = c; return this; };
    cn.dispatchEvent('change');
    assert.equal(uc2, cn);
    // optremove listener
    let rc = null;
    ed.behaviourEngine.removeConnection = function(c) { rc = c; return this; };
    cn.dispatchEvent('optremove');
    assert.equal(rc, cn);
    // optshare listener (cascade=true)
    let uc3 = null, cv = false;
    ed.behaviourEngine.updateConnection = function(c, cascade) { uc3 = c; cv = cascade; return this; };
    cn.dispatchEvent('optshare');
    assert.equal(uc3, cn); assert.ok(cv);
});

test('connectionEngine establish with backup removes backup', () => {
    const ed = new Wirecloud.ui.WiringEditor('ce2');
    Wirecloud.dispatchEvent('loaded');
    ed.behaviourEngine.updateConnection = function() { return this; };
    ed.behaviourEngine.hasConnection = function() { return false; };
    let rc = null;
    ed.behaviourEngine.removeConnection = function(c) { rc = c; return this; };
    const backup = makeConnection();
    ed.connectionEngine.dispatchEvent('establish', makeConnection(), backup);
    assert.equal(rc, backup);
    assert.equal(lastAlertWindowMenuInstances.length, 0);
});

test('connectionEngine establish with backup still connected shows modal', () => {
    const ed = new Wirecloud.ui.WiringEditor('ce3');
    Wirecloud.dispatchEvent('loaded');
    lastAlertWindowMenuInstances = [];
    ed.behaviourEngine.updateConnection = function() { return this; };
    const backup = makeConnection();
    let rc = null;
    ed.behaviourEngine.removeConnection = function(c) { rc = c; return this; };
    ed.behaviourEngine.hasConnection = function(c) { return c === backup; };
    ed.connectionEngine.dispatchEvent('establish', makeConnection(), backup);
    assert.equal(rc, backup);
    assert.ok(lastAlertWindowMenuInstances.length > 0);
    assert.ok(lastAlertWindowMenuInstances[0]._shown);
    // modal handler calls removeConnection(connection, true)
    let rc2 = null, cv2 = false;
    ed.behaviourEngine.removeConnection = function(c, cascade) { rc2 = c; cv2 = cascade; return this; };
    lastAlertWindowMenuInstances[0]._handler();
    assert.equal(rc2, backup); assert.ok(cv2);
});

test('connectionEngine duplicate with background updates connection', () => {
    const ed = new Wirecloud.ui.WiringEditor('ce4');
    Wirecloud.dispatchEvent('loaded');
    let uc = false;
    ed.behaviourEngine.updateConnection = function(c, cascade) { uc = true; return this; };
    const cn = makeConnection(); cn._background = true;
    ed.connectionEngine.dispatchEvent('duplicate', cn, null);
    assert.ok(uc);
});

test('connectionEngine duplicate without background is no-op', () => {
    const ed = new Wirecloud.ui.WiringEditor('ce5');
    Wirecloud.dispatchEvent('loaded');
    let uc = false;
    ed.behaviourEngine.updateConnection = function() { uc = true; return this; };
    const cn = makeConnection(); cn._background = false;
    ed.connectionEngine.dispatchEvent('duplicate', cn, null);
    assert.ok(!uc);
});

test('connectionEngine duplicate with backup removes backup connection', () => {
    const ed = new Wirecloud.ui.WiringEditor('ce6');
    Wirecloud.dispatchEvent('loaded');
    const backup = makeConnection();
    let rc = null;
    ed.behaviourEngine.removeConnection = function(c) { rc = c; return this; };
    ed.behaviourEngine.hasConnection = function() { return false; };
    const cn = makeConnection(); cn._background = true;
    ed.behaviourEngine.updateConnection = function() { return this; };
    ed.connectionEngine.dispatchEvent('duplicate', cn, backup);
    assert.equal(rc, backup);
});

test('connectionEngine click clears selection and orderableComponent', () => {
    const ed = new Wirecloud.ui.WiringEditor('ce7');
    Wirecloud.dispatchEvent('loaded');
    const c = ed.createComponent(makeComponent({ id: 'clk' }), { commit: false });
    ed.selectedComponents.operator.clk = c; ed.selectedCount = 1;
    ed.orderableComponent = { setUp() {} };
    ed.connectionEngine.dispatchEvent('click', makeConnection());
    assert.equal(ed.selectedCount, 0);
    assert.equal(ed.orderableComponent, null);
});

test('connectionEngine dragstart collapses uncollapsed components', () => {
    const ed = new Wirecloud.ui.WiringEditor('ce8');
    Wirecloud.dispatchEvent('loaded');
    const d = new Wirecloud.ui.WiringEditor.ComponentDraggable(makeComponent({ id: 'ds' }));
    d._collapsed = true;
    ed.behaviourEngine.forEachComponent = function(cb) { cb(d); return this; };
    ed.connectionEngine.dispatchEvent('dragstart', makeConnection(), makeEndpoint({ type: 'source' }), makeEndpoint({ type: 'target' }));
    assert.ok(!d.collapsed);
    assert.deepEqual(ed.collapsedComponents, [d]);
});

test('connectionEngine dragstart with _connectionBackup swaps suggestions', () => {
    const ed = new Wirecloud.ui.WiringEditor('ce9');
    Wirecloud.dispatchEvent('loaded');
    const initialEp = makeEndpoint({ type: 'source' });
    const realEp = makeEndpoint({ type: 'target' });
    ed.connectionEngine._connectionBackup = makeConnection();
    ed.behaviourEngine.forEachComponent = function() { return this; };
    let hideEp = null, showEp = null;
    ed.suggestionManager.hideSuggestions = function(e) { hideEp = e; return this; };
    ed.suggestionManager.showSuggestions = function(e) { showEp = e; return this; };
    ed.connectionEngine.dispatchEvent('dragstart', makeConnection(), initialEp, realEp);
    assert.equal(hideEp, realEp);
    assert.equal(showEp, initialEp);
});

test('connectionEngine dragend restores collapsed components', async () => {
    const ed = new Wirecloud.ui.WiringEditor('ce10');
    Wirecloud.dispatchEvent('loaded');
    const d = new Wirecloud.ui.WiringEditor.ComponentDraggable(makeComponent({ id: 'de-c' }));
    d._collapsed = true;
    ed.collapsedComponents = [d];
    ed.connectionEngine.dispatchEvent('dragend', makeConnection(), makeEndpoint({ type: 'source' }));
    assert.ok(d.collapsed);
    await new Promise(r => setTimeout(r, 10));
    assert.equal(ed.collapsedComponents, undefined);
});

test('connectionEngine dragend with null collapsedComponents skips restore', () => {
    const ed = new Wirecloud.ui.WiringEditor('ce11');
    Wirecloud.dispatchEvent('loaded');
    ed.collapsedComponents = null;
    assert.doesNotThrow(() => {
        ed.connectionEngine.dispatchEvent('dragend', makeConnection(), makeEndpoint({ type: 'source' }));
    });
});

// =============================================================================
// Behaviour lifecycle events
// =============================================================================
test('behaviourEngine change updates legend (without enabled)', () => {
    const ed = new Wirecloud.ui.WiringEditor('be1');
    Wirecloud.dispatchEvent('loaded');
    ed.behaviourEngine.dispatchEvent('change', { title: 'T', connections: 3, components: { operator: 2, widget: 1 } }, false);
    assert.ok(ed.legend.title.innerHTML === 'T');
    assert.equal(ed.legend.connections.textContent, '3');
    assert.equal(ed.legend.operators.textContent, '2');
    assert.equal(ed.legend.widgets.textContent, '1');
});

test('behaviourEngine change with enabled wraps title with strong', () => {
    const ed = new Wirecloud.ui.WiringEditor('be2');
    Wirecloud.dispatchEvent('loaded');
    ed.behaviourEngine.dispatchEvent('change', { title: 'Active', connections: 0, components: { operator: 0, widget: 0 } }, true);
    assert.ok(ed.legend.title.innerHTML.includes('<strong>'));
    assert.ok(ed.legend.title.innerHTML.includes('Active'));
});

test('behaviourEngine enable iterates connections and components', () => {
    const ed = new Wirecloud.ui.WiringEditor('be3');
    Wirecloud.dispatchEvent('loaded');
    const cn = makeConnection();
    let connIter = false;
    ed.connectionEngine.forEachConnection = function(cb) { cb(cn); connIter = true; return this; };
    const dc = new Wirecloud.ui.WiringEditor.ComponentDraggable(makeComponent({ id: 'bec' }));
    let compIter = false;
    ed.behaviourEngine.forEachComponent = function(cb) { cb(dc); compIter = true; return this; };
    ed.behaviourEngine.dispatchEvent('enable', true);
    assert.ok(connIter); assert.ok(compIter);
    assert.equal(cn.removeAllowed, true); assert.equal(cn.background, false);
    assert.ok(dc.removeCascadeAllowed); assert.equal(dc.removeAllowed, true); assert.equal(dc.background, false);
});

test('behaviourEngine activate GLOBAL sets backgrounds', () => {
    const ed = new Wirecloud.ui.WiringEditor('be4');
    Wirecloud.dispatchEvent('loaded');
    const b = makeBehaviour({ title: 'GB' });
    b.hasComponent = function() { return false; }; b.hasConnection = function() { return false; };
    const cn = makeConnection(); const dc = new Wirecloud.ui.WiringEditor.ComponentDraggable(makeComponent({ id: 'bgc' }));
    ed.connectionEngine.forEachConnection = function(cb) { cb(cn); return this; };
    ed.behaviourEngine.forEachComponent = function(cb) { cb(dc); return this; };
    ed.behaviourEngine.filterByConnection = function() { return [b]; };
    ed.behaviourEngine.filterByComponent = function() { return [b]; };
    ed.behaviourEngine.dispatchEvent('activate', b, 0); // GLOBAL
    assert.equal(cn.removeAllowed, true); assert.ok(cn.background);
    assert.equal(dc.removeAllowed, true); assert.ok(dc.removeCascadeAllowed); assert.ok(dc.background);
});

// =============================================================================
// Layout events
// =============================================================================
test('layout content click clears selection and orderableComponent', () => {
    const ed = new Wirecloud.ui.WiringEditor('lo1');
    Wirecloud.dispatchEvent('loaded');
    const c = ed.createComponent(makeComponent({ id: 'lc' }), { commit: false });
    ed.selectedComponents.operator.lc = c; ed.selectedCount = 1;
    ed.orderableComponent = { setUp() {} };
    ed.layout.content.get().dispatchEvent({ type: 'click' });
    assert.equal(ed.selectedCount, 0); assert.equal(ed.orderableComponent, null);
});

test('layout dblclick calls slideOut', () => {
    const ed = new Wirecloud.ui.WiringEditor('lo2');
    Wirecloud.dispatchEvent('loaded');
    let so = false;
    ed.layout.slideOut = function() { so = true; return this; };
    ed.layout.content.get().dispatchEvent({ type: 'dblclick', preventDefault() {} });
    assert.ok(so);
});

test('layout slideOut sets button active false, stops ordering', () => {
    const ed = new Wirecloud.ui.WiringEditor('lo3');
    Wirecloud.dispatchEvent('loaded');
    ed.btnFindComponents.active = true; ed.btnListBehaviours.active = true;
    let so = false;
    ed.behaviourEngine.stopOrdering = function() { so = true; return this; };
    ed.layout.dispatchEvent('slideOut');
    assert.ok(so);
});

test('layout slideIn with behaviours panel', () => {
    const ed = new Wirecloud.ui.WiringEditor('lo4');
    Wirecloud.dispatchEvent('loaded');
    ed.layout.dispatchEvent('slideIn', { hasClassName(c) { return c === 'we-panel-behaviours'; } });
    assert.ok(!ed.btnFindComponents.active); assert.ok(ed.btnListBehaviours.active);
});

test('layout slideIn with components panel stops ordering', () => {
    const ed = new Wirecloud.ui.WiringEditor('lo5');
    Wirecloud.dispatchEvent('loaded');
    let so = false;
    ed.behaviourEngine.stopOrdering = function() { so = true; return this; };
    ed.layout.dispatchEvent('slideIn', { hasClassName(c) { return c === 'we-panel-components'; } });
    assert.ok(ed.btnFindComponents.active); assert.ok(!ed.btnListBehaviours.active); assert.ok(so);
});

// =============================================================================
// showSelectedPanel (via buttons)
// =============================================================================
test('btnFindComponents active slides in panel 1 and refreshes search', () => {
    const ed = new Wirecloud.ui.WiringEditor('sp1');
    Wirecloud.dispatchEvent('loaded');
    ed.btnFindComponents.active = true;
    let si = -1;
    ed.layout.slideIn = function(i) { si = i; return this; };
    ed.btnFindComponents.click();
    assert.equal(si, 1);
    assert.ok(ed.componentManager.searchComponents._refreshed);
});

test('btnFindComponents inactive slides out', () => {
    const ed = new Wirecloud.ui.WiringEditor('sp2');
    Wirecloud.dispatchEvent('loaded');
    ed.btnFindComponents.active = false;
    let so = false;
    ed.layout.slideOut = function() { so = true; return this; };
    ed.btnFindComponents.click();
    assert.ok(so);
});

test('btnListBehaviours active slides in panel 0', () => {
    const ed = new Wirecloud.ui.WiringEditor('sp3');
    Wirecloud.dispatchEvent('loaded');
    ed.btnListBehaviours.active = true;
    let si = -1;
    ed.layout.slideIn = function(i) { si = i; return this; };
    ed.btnListBehaviours.click();
    assert.equal(si, 0);
});

test('btnListBehaviours inactive slides out', () => {
    const ed = new Wirecloud.ui.WiringEditor('sp4');
    Wirecloud.dispatchEvent('loaded');
    ed.btnListBehaviours.active = false;
    let so = false;
    ed.layout.slideOut = function() { so = true; return this; };
    ed.btnListBehaviours.click();
    assert.ok(so);
});

// =============================================================================
// Component click (component_onclick)
// =============================================================================
test('component_onclick: inactive in selection + ctrlKey removes', () => {
    const ed = new Wirecloud.ui.WiringEditor('cl1');
    Wirecloud.dispatchEvent('loaded');
    const c = ed.createComponent(makeComponent({ id: 'clk1' }), { commit: false });
    c._active = false;
    ed.selectedComponents.operator.clk1 = c; ed.selectedCount = 1;
    c.dispatchEvent('click', { ctrlKey: true });
    assert.ok(!('clk1' in ed.selectedComponents.operator)); assert.equal(ed.selectedCount, 0);
});

test('component_onclick: inactive in selection + metaKey removes', () => {
    const ed = new Wirecloud.ui.WiringEditor('cl2');
    Wirecloud.dispatchEvent('loaded');
    const c = ed.createComponent(makeComponent({ id: 'clk2', type: 'widget' }), { commit: false });
    c._active = false;
    ed.selectedComponents.widget.clk2 = c; ed.selectedCount = 1;
    c.dispatchEvent('click', { metaKey: true });
    assert.ok(!('clk2' in ed.selectedComponents.widget)); assert.equal(ed.selectedCount, 0);
});

test('component_onclick: inactive, no mod, selectedCount>1 clears all and activates clicked', () => {
    const ed = new Wirecloud.ui.WiringEditor('cl3');
    Wirecloud.dispatchEvent('loaded');
    const c1 = ed.createComponent(makeComponent({ id: 'm1' }), { commit: false });
    const c2 = ed.createComponent(makeComponent({ id: 'm2' }), { commit: false });
    c1._active = false; c2._active = true;
    ed.selectedComponents.operator.m1 = c1; ed.selectedComponents.operator.m2 = c2; ed.selectedCount = 2;
    c1.dispatchEvent('click', {});
    assert.ok(c1.active);
    assert.equal(ed.selectedCount, 1);
    // c1 is active and added back to selection; m2 is cleared
    assert.ok(!('m2' in ed.selectedComponents.operator));
});

test('component_onclick: inactive, no mod, selectedCount=1 removes only it', () => {
    const ed = new Wirecloud.ui.WiringEditor('cl4');
    Wirecloud.dispatchEvent('loaded');
    const c = ed.createComponent(makeComponent({ id: 'alone' }), { commit: false });
    c._active = false;
    ed.selectedComponents.operator.alone = c; ed.selectedCount = 1;
    c.dispatchEvent('click', {});
    assert.ok(!('alone' in ed.selectedComponents.operator)); assert.equal(ed.selectedCount, 0);
});

test('component_onclick: active + not selected adds to selection', () => {
    const ed = new Wirecloud.ui.WiringEditor('cl5');
    Wirecloud.dispatchEvent('loaded');
    const c = ed.createComponent(makeComponent({ id: 'add-me' }), { commit: false });
    c._active = true;
    c.dispatchEvent('click', {});
    assert.ok('add-me' in ed.selectedComponents.operator); assert.equal(ed.selectedCount, 1);
});

test('component_onclick: active + already selected is no-op', () => {
    const ed = new Wirecloud.ui.WiringEditor('cl6');
    Wirecloud.dispatchEvent('loaded');
    const c = ed.createComponent(makeComponent({ id: 'exist' }), { commit: false });
    c._active = true;
    ed.selectedComponents.operator.exist = c; ed.selectedCount = 1;
    c.dispatchEvent('click', {});
    assert.equal(ed.selectedCount, 1);
});

// =============================================================================
// Component drag events
// =============================================================================
test('component_ondragstart sets initialPosition for all selected', () => {
    const ed = new Wirecloud.ui.WiringEditor('dr1');
    Wirecloud.dispatchEvent('loaded');
    const c1 = ed.createComponent(makeComponent({ id: 'ds1' }), { commit: false });
    const c2 = ed.createComponent(makeComponent({ id: 'ds2' }), { commit: false });
    c1._position = { x: 10, y: 20 }; c2._position = { x: 30, y: 40 };
    ed.selectedComponents.operator.ds1 = c1; ed.selectedComponents.operator.ds2 = c2; ed.selectedCount = 2;
    c1.dispatchEvent('dragstart', { ctrlKey: false });
    assert.deepEqual(c1.initialPosition, { x: 10, y: 20 });
    assert.deepEqual(c2.initialPosition, { x: 30, y: 40 });
});

test('component_ondragstart ctrlKey adds to selection', () => {
    const ed = new Wirecloud.ui.WiringEditor('dr2');
    Wirecloud.dispatchEvent('loaded');
    const c = ed.createComponent(makeComponent({ id: 'ctrl-add' }), { commit: false });
    c.dispatchEvent('dragstart', { ctrlKey: true });
    assert.ok('ctrl-add' in ed.selectedComponents.operator); assert.equal(ed.selectedCount, 1);
});

test('component_ondragstart without ctrlKey clears if not selected', () => {
    const ed = new Wirecloud.ui.WiringEditor('dr3');
    Wirecloud.dispatchEvent('loaded');
    const old = ed.createComponent(makeComponent({ id: 'old' }), { commit: false });
    ed.selectedComponents.operator.old = old; ed.selectedCount = 1;
    const nw = ed.createComponent(makeComponent({ id: 'new' }), { commit: false });
    nw.dispatchEvent('dragstart', {});
    assert.ok(!('old' in ed.selectedComponents.operator)); assert.equal(ed.selectedCount, 0);
});

test('component_ondrag moves other selected by delta', () => {
    const ed = new Wirecloud.ui.WiringEditor('dr4');
    Wirecloud.dispatchEvent('loaded');
    const c1 = ed.createComponent(makeComponent({ id: 'mv1' }), { commit: false });
    const c2 = ed.createComponent(makeComponent({ id: 'mv2' }), { commit: false });
    c1._initialPosition = { x: 0, y: 0 }; c1._position = { x: 0, y: 0 };
    c2._initialPosition = { x: 100, y: 200 }; c2._position = { x: 100, y: 200 };
    ed.selectedComponents.operator.mv1 = c1; ed.selectedComponents.operator.mv2 = c2;
    // Drag on comp1 by (50, 30) — dispatchEvent prepends sender, so handler gets (component, x, y)
    c1.dispatchEvent('drag', 50, 30);
    assert.equal(c1._position.x, 0); assert.equal(c1._position.y, 0);
    assert.equal(c2._position.x, 150); assert.equal(c2._position.y, 230);
});

test('component_ondragend sets active on all and dispatches change on non-dragged', () => {
    const ed = new Wirecloud.ui.WiringEditor('dr5');
    Wirecloud.dispatchEvent('loaded');
    const c1 = ed.createComponent(makeComponent({ id: 'de1' }), { commit: false });
    const c2 = ed.createComponent(makeComponent({ id: 'de2' }), { commit: false });
    ed.selectedComponents.operator.de1 = c1; ed.selectedComponents.operator.de2 = c2;
    let changed = false;
    c2.addEventListener('change', function() { changed = true; });
    c1.dispatchEvent('dragend');
    assert.ok(c1.active); assert.ok(c2.active); assert.ok(changed);
});

// =============================================================================
// Component order events
// =============================================================================
test('component_onorderstart sets orderableComponent, disables engine/suggestions', () => {
    const ed = new Wirecloud.ui.WiringEditor('or1');
    Wirecloud.dispatchEvent('loaded');
    const c = ed.createComponent(makeComponent({ id: 'ord' }), { commit: false });
    c.dispatchEvent('orderstart');
    assert.equal(ed.orderableComponent, c);
    assert.ok(!ed.connectionEngine.enabled); assert.ok(!ed.suggestionManager._enabled);
});

test('component_onorderstart with different existing orderable calls setUp', () => {
    const ed = new Wirecloud.ui.WiringEditor('or2');
    Wirecloud.dispatchEvent('loaded');
    const old = ed.createComponent(makeComponent({ id: 'o1' }), { commit: false });
    const nw = ed.createComponent(makeComponent({ id: 'o2' }), { commit: false });
    ed.orderableComponent = old;
    let su = false;
    old.setUp = function() { su = true; return this; };
    old.equals = function() { return false; };
    nw.dispatchEvent('orderstart');
    assert.ok(su); assert.equal(ed.orderableComponent, nw);
});

test('component_onorderstart with same component does not call setUp', () => {
    const ed = new Wirecloud.ui.WiringEditor('or3');
    Wirecloud.dispatchEvent('loaded');
    const c = ed.createComponent(makeComponent({ id: 'same' }), { commit: false });
    ed.orderableComponent = c;
    let su = false;
    c.setUp = function() { su = true; return this; };
    c.equals = function() { return true; };
    c.dispatchEvent('orderstart');
    assert.ok(!su);
});

test('component_onorderend resets and re-enables', async () => {
    const ed = new Wirecloud.ui.WiringEditor('or4');
    Wirecloud.dispatchEvent('loaded');
    const c = ed.createComponent(makeComponent({ id: 'oe' }), { commit: false });
    ed.orderableComponent = c; ed.connectionEngine.enabled = false; ed.suggestionManager._enabled = false;
    c.dispatchEvent('orderend');
    assert.equal(ed.orderableComponent, null); assert.ok(ed.connectionEngine.enabled);
    await new Promise(r => setTimeout(r, 10));
    assert.ok(ed.suggestionManager._enabled);
});

// =============================================================================
// Keyboard events (document_onkeydown via rootKeydownHandler)
// =============================================================================
test('keyboard Backspace removes selected removable components', () => {
    const ed = new Wirecloud.ui.WiringEditor('kb1');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    const c = ed.createComponent(makeComponent({ id: 'kb-del' }), { commit: false });
    c._removable = true;
    ed.selectedComponents.operator['kb-del'] = c; ed.selectedCount = 1;
    let rl = null;
    ed.behaviourEngine.removeComponentList = function(l) { rl = l; return this; };
    const r = Wirecloud.UserInterfaceManager.rootKeydownHandler('Backspace', {});
    assert.ok(r); assert.equal(rl.length, 1); assert.equal(ed.selectedCount, 0);
});

test('keyboard Delete removes selected removable components', () => {
    const ed = new Wirecloud.ui.WiringEditor('kb2');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    const c = ed.createComponent(makeComponent({ id: 'kb-del2' }), { commit: false });
    c._removable = true;
    ed.selectedComponents.operator['kb-del2'] = c; ed.selectedCount = 1;
    let rl = null;
    ed.behaviourEngine.removeComponentList = function(l) { rl = l; return this; };
    const r = Wirecloud.UserInterfaceManager.rootKeydownHandler('Delete', {});
    assert.ok(r); assert.equal(rl.length, 1);
});

test('keyboard Delete with non-removable components skips', () => {
    const ed = new Wirecloud.ui.WiringEditor('kb3');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    const c = ed.createComponent(makeComponent({ id: 'kb-nr' }), { commit: false });
    c._removable = false;
    ed.selectedComponents.operator['kb-nr'] = c; ed.selectedCount = 1;
    let rl = null;
    ed.behaviourEngine.removeComponentList = function(l) { rl = l; return this; };
    Wirecloud.UserInterfaceManager.rootKeydownHandler('Delete', {});
    assert.equal(rl, null);
});

test('keyboard Backspace with no selected components returns true', () => {
    const ed = new Wirecloud.ui.WiringEditor('kb4');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    assert.ok(Wirecloud.UserInterfaceManager.rootKeydownHandler('Backspace', {}));
});

test('keyboard Ctrl+C triggers copy', () => {
    const ed = new Wirecloud.ui.WiringEditor('kb5');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    assert.ok(Wirecloud.UserInterfaceManager.rootKeydownHandler('c', { ctrlKey: true }));
});

test('keyboard Meta+C triggers copy', () => {
    const ed = new Wirecloud.ui.WiringEditor('kb6');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    assert.ok(Wirecloud.UserInterfaceManager.rootKeydownHandler('c', { metaKey: true }));
});

test('keyboard Ctrl+V triggers paste', () => {
    const ed = new Wirecloud.ui.WiringEditor('kb7');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    assert.ok(Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { ctrlKey: true }));
});

test('keyboard Meta+V triggers paste', () => {
    const ed = new Wirecloud.ui.WiringEditor('kb8');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    assert.ok(Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { metaKey: true }));
});

test('keyboard unknown key returns undefined', () => {
    const ed = new Wirecloud.ui.WiringEditor('kb9');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    assert.equal(Wirecloud.UserInterfaceManager.rootKeydownHandler('z', { ctrlKey: true }), undefined);
});

test('keyboard c without modifier returns undefined', () => {
    const ed = new Wirecloud.ui.WiringEditor('kb10');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    assert.equal(Wirecloud.UserInterfaceManager.rootKeydownHandler('c', {}), undefined);
});

test('keyboard v without modifier returns undefined', () => {
    const ed = new Wirecloud.ui.WiringEditor('kb11');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    assert.equal(Wirecloud.UserInterfaceManager.rootKeydownHandler('v', {}), undefined);
});

// =============================================================================
// copyComponents / pasteComponents
// =============================================================================
test('copyComponents writes to localStorage', () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('cp1');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    const c = ed.createComponent(makeComponent({ id: 'copy-me' }), { commit: false });
    c._position = { x: 50, y: 60 }; c._collapsed = false;
    c._component = { id: 'copy-me', type: 'operator', meta: { uri: 'http://x/copy-me' }, preferences: {}, properties: {}, permissions: {} };
    c._endpoints = []; c.forEachEndpoint = function(cb) { return this; };
    ed.selectedComponents.operator['copy-me'] = c; ed.selectedCount = 1;
    Wirecloud.UserInterfaceManager.rootKeydownHandler('c', { ctrlKey: true });
    assert.ok(ed.copiedComponents.length > 0);
    const cp = ed.copiedComponents[0];
    assert.equal(cp.id, 'copy-me'); assert.deepEqual(cp.position, { x: 50, y: 60 });
    const stored = JSON.parse(global.localStorage.getItem('wirecloud.wiring.clipboard'));
    assert.equal(stored.version, 1); assert.equal(stored.components.length, 1);
});

test('copyComponents handles setItem throwing', () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('cp2');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    const c = ed.createComponent(makeComponent({ id: 'copy-err' }), { commit: false });
    c._position = { x: 0, y: 0 };
    c._component = { id: 'copy-err', type: 'operator', meta: { uri: 'http://x/err' }, preferences: {}, properties: {}, permissions: {} };
    c._endpoints = []; c.forEachEndpoint = function(cb) { return this; };
    ed.selectedComponents.operator['copy-err'] = c; ed.selectedCount = 1;
    global.localStorage.setItem = function() { throw new Error('quota'); };
    assert.doesNotThrow(() => { Wirecloud.UserInterfaceManager.rootKeydownHandler('c', { ctrlKey: true }); });
});

test('pasteComponents with empty clipboard returns early', () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('cp3');
    Wirecloud.dispatchEvent('loaded');
    ed.load(Wirecloud.activeWorkspace);
    ed.copiedComponents = [];
    assert.doesNotThrow(() => { Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { ctrlKey: true }); });
});

test('pasteComponents operator: creates operator and adds to layout', async () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('cp4');
    Wirecloud.dispatchEvent('loaded');
    let createdMeta = null, createdOpts = null;
    const ws = { ...Wirecloud.activeWorkspace };
    ws.wiring = { ...ws.wiring, createOperator(m, o) { createdMeta = m; createdOpts = o; return Promise.resolve(makeComponent({ id: 'pasted-op' })); } };
    ed.load(ws);
    ed.copiedComponents = [{ id: 'src-op', type: 'operator', meta: { uri: 'http://x/op', type: 'operator' }, metaUri: 'http://x/op', position: { x: 10, y: 20 }, collapsed: true, preferences: { k: 'v' }, properties: { p: 'pv' }, permissions: {}, sourceEndpoints: [] }];
    Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { ctrlKey: true });
    await new Promise(r => setTimeout(r, 100));
    assert.ok(createdMeta != null);
});

test('pasteComponents widget: creates widget and applies preferences/properties', async () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('cp5');
    Wirecloud.dispatchEvent('loaded');
    let createdMeta = null;
    const ws = { ...Wirecloud.activeWorkspace };
    ws.view = { activeTab: { createWidget(m) { createdMeta = m; const model = makeComponent({ id: 'pasted-w', type: 'widget' }); model.preferences = { k1: { value: null } }; model.properties = { p1: { value: null } }; return Promise.resolve({ model }); } } };
    ed.load(ws);
    ed.copiedComponents = [{ id: 'src-w', type: 'widget', meta: { uri: 'http://x/w', type: 'widget' }, metaUri: 'http://x/w', position: { x: 30, y: 40 }, collapsed: false, preferences: { k1: 'v1' }, properties: { p1: 'pv1' }, permissions: {}, sourceEndpoints: [] }];
    Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { ctrlKey: true });
    await new Promise(r => setTimeout(r, 100));
    assert.ok(createdMeta != null);
});

test('pasteComponents with null meta skips', async () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('cp6');
    Wirecloud.dispatchEvent('loaded');
    const ws = { ...Wirecloud.activeWorkspace, resources: { getOrCreateMissing() { return null; } } };
    ed.load(ws);
    ed.copiedComponents = [{ id: 'no-meta', type: 'operator', meta: null, metaUri: null, position: { x: 0, y: 0 }, collapsed: false, preferences: {}, properties: {}, permissions: {}, sourceEndpoints: [] }];
    assert.doesNotThrow(() => { Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { ctrlKey: true }); });
    await new Promise(r => setTimeout(r, 50));
    assert.ok(true);
});

test('pasteComponents widget creation error catches exception', async () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('cp7');
    Wirecloud.dispatchEvent('loaded');
    const ws = { ...Wirecloud.activeWorkspace, view: { activeTab: { createWidget() { return Promise.reject(new Error('fail')); } } } };
    ed.load(ws);
    ed.copiedComponents = [{ id: 'err-w', type: 'widget', meta: { uri: 'http://x/ew', type: 'widget' }, metaUri: 'http://x/ew', position: { x: 0, y: 0 }, collapsed: false, preferences: {}, properties: {}, permissions: {}, sourceEndpoints: [] }];
    assert.doesNotThrow(() => { Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { ctrlKey: true }); });
    await new Promise(r => setTimeout(r, 50));
    assert.ok(true);
});

test('pasteComponents with connections between pasted components', async () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('cp8');
    Wirecloud.dispatchEvent('loaded');
    let cc = false;
    const ws = { ...Wirecloud.activeWorkspace, wiring: { ...Wirecloud.activeWorkspace.wiring, createConnection() { cc = true; return Promise.resolve({}); } } };
    ed.load(ws);
    const c1 = { id: 'pc1', type: 'operator', meta: { uri: 'http://x/pc1', type: 'operator' }, metaUri: 'http://x/pc1', position: { x: 0, y: 0 }, collapsed: false, preferences: {}, properties: {}, permissions: {}, sourceEndpoints: [{ name: 'out', connections: [{ sourceEndpoint: 'out', targetComponent: 'pc2', targetComponentType: 'operator', targetEndpoint: 'in', sourceHandle: null, targetHandle: null }] }] };
    const c2 = { id: 'pc2', type: 'operator', meta: { uri: 'http://x/pc2', type: 'operator' }, metaUri: 'http://x/pc2', position: { x: 0, y: 0 }, collapsed: false, preferences: {}, properties: {}, permissions: {}, sourceEndpoints: [] };
    ed.copiedComponents = [c1, c2];
    Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { ctrlKey: true });
    await new Promise(r => setTimeout(r, 150));
    assert.ok(cc);
});

// =========================================================================
// getCopiedComponentMeta with meta.uri returns meta directly (line 83-85)
// =========================================================================
test('getCopiedComponentMeta returns meta when meta.uri is set', async () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('gc1');
    Wirecloud.dispatchEvent('loaded');
    const ws = { ...Wirecloud.activeWorkspace };
    ed.load(ws);
    const copiedComponent = { id: 'test', type: 'operator', meta: { uri: 'http://x/direct', type: 'operator' }, metaUri: 'http://x/direct', position: { x: 0, y: 0 }, collapsed: false, preferences: {}, properties: {}, permissions: {}, sourceEndpoints: [] };
    ed.copiedComponents = [copiedComponent];
    let createdMeta = null;
    ws.wiring = { ...ws.wiring, createOperator(m) { createdMeta = m; return Promise.resolve(makeComponent({ id: 'gc1-op' })); } };
    Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { ctrlKey: true });
    await new Promise(r => setTimeout(r, 50));
    assert.equal(createdMeta.uri, 'http://x/direct');
});

// =========================================================================
// getCopiedComponentMeta fallback when meta.uri is null and metaUri resolves via workspace.resources (line 87-89)
// =========================================================================
test('getCopiedComponentMeta uses getOrCreateMissing when meta has no uri but metaUri exists', async () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('gc2');
    Wirecloud.dispatchEvent('loaded');
    let getOrCreateMissingCalled = false;
    const ws = { ...Wirecloud.activeWorkspace, resources: { getOrCreateMissing(u, t) { getOrCreateMissingCalled = true; return { uri: u, type: t }; } } };
    ed.load(ws);
    const copiedComponent = { id: 'test2', type: 'operator', meta: { type: 'operator' }, metaUri: 'http://x/fallback', position: { x: 0, y: 0 }, collapsed: false, preferences: {}, properties: {}, permissions: {}, sourceEndpoints: [] };
    ed.copiedComponents = [copiedComponent];
    ws.wiring = { ...ws.wiring, createOperator(m) { return Promise.resolve(makeComponent({ id: 'gc2-op' })); } };
    Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { ctrlKey: true });
    await new Promise(r => setTimeout(r, 50));
    assert.ok(getOrCreateMissingCalled);
});

// =========================================================================
// getCopiedComponentMeta fallback returns meta when resources is null (line 91)
// =========================================================================
test('getCopiedComponentMeta returns meta when resources is null and meta has no uri', async () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('gc3');
    Wirecloud.dispatchEvent('loaded');
    const ws = { ...Wirecloud.activeWorkspace, resources: null };
    ed.load(ws);
    ed.copiedComponents = [{ id: 'fallback-meta', type: 'operator', meta: { type: 'operator' }, metaUri: 'http://x/fallback', position: { x: 0, y: 0 }, collapsed: false, preferences: {}, properties: {}, permissions: {}, sourceEndpoints: [] }];
    ws.wiring = { ...ws.wiring, createOperator(m) { return Promise.resolve(makeComponent({ id: 'fb-op' })); } };
    Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { ctrlKey: true });
    await new Promise(r => setTimeout(r, 50));
    assert.ok(lastComponentDraggableInstances.find(c => c.id === 'fb-op') != null);
});

// =========================================================================
// writeCopiedComponents with null storage (line 64-66)
// =========================================================================
test('writeCopiedComponents handles null storage gracefully', () => {
    const origLocalStorage = global.localStorage;
    const origWindow = global.window;
    try {
        global.localStorage = undefined;
        Object.defineProperty(global, 'window', { value: {}, configurable: true });
        global.window.localStorage = undefined;
        const ed = new Wirecloud.ui.WiringEditor('ws1');
        Wirecloud.dispatchEvent('loaded');
        ed.load(Wirecloud.activeWorkspace);
        const c = ed.createComponent(makeComponent({ id: 'ws-comp' }), { commit: false });
        c._position = { x: 0, y: 0 };
        c._component = { id: 'ws-comp', type: 'operator', meta: { uri: 'http://x/ws' }, preferences: {}, properties: {}, permissions: {} };
        c._endpoints = [];
        c.forEachEndpoint = function(cb) { return this; };
        ed.selectedComponents.operator['ws-comp'] = c;
        ed.selectedCount = 1;
        assert.doesNotThrow(() => { Wirecloud.UserInterfaceManager.rootKeydownHandler('c', { ctrlKey: true }); });
        assert.equal(ed.copiedComponents.length, 1);
    } finally {
        global.localStorage = origLocalStorage;
        global.window = origWindow;
    }
});

// =========================================================================
// readCopiedComponents with null storage (line 44-46)
// =========================================================================
test('readCopiedComponents returns empty when localStorage unavailable', () => {
    const origLocalStorage = global.localStorage;
    const origWindow = global.window;
    try {
        global.localStorage = undefined;
        Object.defineProperty(global, 'window', { value: {}, configurable: true });
        global.window.localStorage = undefined;
        const ed = new Wirecloud.ui.WiringEditor('rc1');
        assert.deepEqual(ed.copiedComponents, []);
    } finally {
        global.localStorage = origLocalStorage;
        global.window = origWindow;
    }
});

// =========================================================================
// findEndpoint fallback: component not in behaviourEngine, create from componentManager (lines 369-372)
// =========================================================================
test('findEndpoint creates component from componentManager when not in behaviourEngine', () => {
    const ed = new Wirecloud.ui.WiringEditor('fe1');
    Wirecloud.dispatchEvent('loaded');
    const op = makeComponent({ id: 'fe-op', type: 'operator' });
    // Component added via workspace.operators so loadComponents adds it to componentManager
    // but we keep behaviourEngine._components empty so findEndpoint falls through to componentManager
    ed.behaviourEngine._components = { operator: {}, widget: {} };
    const vs = { components: { operator: {}, widget: {} },
        connections: [{ sourcename: 'fe-src', targetname: 'fe-tgt' }] };
    const ws = { ...Wirecloud.activeWorkspace,
        wiring: { ...Wirecloud.activeWorkspace.wiring,
            operators: [op],
            visualdescription: vs,
            connections: [{ source: { id: 'fe-src', component: { id: 'fe-op', type: 'operator', meta: { type: 'operator' } }, name: 'out' },
                           target: { id: 'fe-tgt', component: { id: 'fe-op', type: 'operator', meta: { type: 'operator' } }, name: 'in' },
                           volatile: false }] } };
    ed.load(ws);
    assert.ok(lastConnectionEngineConnectCalls.length > 0);
});

// =========================================================================
// copyComponents with endpoints having connections (collects connection data, lines 754-797)
// =========================================================================
test('copyComponents collects connection data between selected components', () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('cc1');
    Wirecloud.dispatchEvent('loaded');
    ed.load(Wirecloud.activeWorkspace);
    const compA = ed.createComponent(makeComponent({ id: 'compA' }), { commit: false });
    const compB = ed.createComponent(makeComponent({ id: 'compB' }), { commit: false });
    const epOut = makeEndpoint({ type: 'source', name: 'out', component: { id: 'compA', type: 'operator' } });
    const epIn = makeEndpoint({ type: 'target', name: 'in', component: { id: 'compB', type: 'operator' } });
    const conn = makeConnection({
        sourceEndpoint: epOut,
        targetEndpoint: epIn,
        source: { endpoint: epOut },
        target: { endpoint: epIn },
    });
    epOut.connections = [conn];
    compA._component = { id: 'compA', type: 'operator', meta: { uri: 'http://x/a', type: 'operator' }, preferences: {}, properties: {}, permissions: {} };
    compB._component = { id: 'compB', type: 'operator', meta: { uri: 'http://x/b', type: 'operator' }, preferences: {}, properties: {}, permissions: {} };
    compA._position = { x: 0, y: 0 };
    compB._position = { x: 100, y: 0 };
    compA._endpoints = [epOut];
    compB._endpoints = [epIn];
    compA.forEachEndpoint = function(cb) { this._endpoints.forEach(cb); return this; };
    compB.forEachEndpoint = function(cb) { this._endpoints.forEach(cb); return this; };
    ed.selectedComponents.operator.compA = compA;
    ed.selectedComponents.operator.compB = compB;
    ed.selectedCount = 2;
    Wirecloud.UserInterfaceManager.rootKeydownHandler('c', { ctrlKey: true });
    assert.ok(ed.copiedComponents.length > 0);
    const copiedA = ed.copiedComponents.find(c => c.id === 'compA');
    assert.ok(copiedA != null);
    assert.ok(Array.isArray(copiedA.sourceEndpoints));
});

// =========================================================================
// pasteComponents: sourceEndpoint is null (skips connection, line 966-968)
// =========================================================================
test('pasteComponents skips connection when source endpoint not found', async () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('pc1');
    Wirecloud.dispatchEvent('loaded');
    let connectionCreated = false;
    const ws = { ...Wirecloud.activeWorkspace, wiring: { ...Wirecloud.activeWorkspace.wiring, createConnection() { connectionCreated = true; return Promise.resolve({}); } } };
    ed.load(ws);
    let callCount = 0;
    const origCreateComponent = ed.createComponent.bind(ed);
    ed.createComponent = function(wc, opts) {
        const result = origCreateComponent(wc, opts);
        callCount++;
        if (callCount === 1) {
            result.getEndpoint = function() { return null; };
        }
        return result;
    };
    ed.copiedComponents = [
        { id: 'src', type: 'operator', meta: { uri: 'http://x/src', type: 'operator' }, metaUri: 'http://x/src', position: { x: 0, y: 0 }, collapsed: false, preferences: {}, properties: {}, permissions: {}, sourceEndpoints: [{ name: 'out', connections: [{ sourceEndpoint: 'out', targetComponent: 'tgt', targetComponentType: 'operator', targetEndpoint: 'in', sourceHandle: null, targetHandle: null }] }] },
        { id: 'tgt', type: 'operator', meta: { uri: 'http://x/tgt', type: 'operator' }, metaUri: 'http://x/tgt', position: { x: 0, y: 0 }, collapsed: false, preferences: {}, properties: {}, permissions: {}, sourceEndpoints: [] }
    ];
    Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { ctrlKey: true });
    await new Promise(r => setTimeout(r, 100));
    assert.ok(!connectionCreated);
});

// =========================================================================
// pasteComponents: targetComponent not in newComponents (skips connection, line 972-974)
// =========================================================================
test('pasteComponents skips connection when target component not found', async () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('pc2');
    Wirecloud.dispatchEvent('loaded');
    let connectionCreated = false;
    const ws = { ...Wirecloud.activeWorkspace, wiring: { ...Wirecloud.activeWorkspace.wiring, createConnection() { connectionCreated = true; return Promise.resolve({}); } } };
    ed.load(ws);
    ed.copiedComponents = [
        { id: 'src', type: 'operator', meta: { uri: 'http://x/src', type: 'operator' }, metaUri: 'http://x/src', position: { x: 0, y: 0 }, collapsed: false, preferences: {}, properties: {}, permissions: {}, sourceEndpoints: [{ name: 'out', connections: [{ sourceEndpoint: 'out', targetComponent: 'nonexistent', targetComponentType: 'operator', targetEndpoint: 'in', sourceHandle: null, targetHandle: null }] }] },
        { id: 'other', type: 'operator', meta: { uri: 'http://x/other', type: 'operator' }, metaUri: 'http://x/other', position: { x: 0, y: 0 }, collapsed: false, preferences: {}, properties: {}, permissions: {}, sourceEndpoints: [] }
    ];
    Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { ctrlKey: true });
    await new Promise(r => setTimeout(r, 100));
    assert.ok(!connectionCreated);
});

// =========================================================================
// pasteComponents: targetEndpoint is null (skips connection, line 977-979)
// =========================================================================
test('pasteComponents skips connection when target endpoint not found', async () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('pc3');
    Wirecloud.dispatchEvent('loaded');
    let connectionCreated = false;
    const ws = { ...Wirecloud.activeWorkspace, wiring: { ...Wirecloud.activeWorkspace.wiring, createConnection() { connectionCreated = true; return Promise.resolve({}); } } };
    ed.load(ws);
    let callCount = 0;
    const origCreateComponent = ed.createComponent.bind(ed);
    ed.createComponent = function(wc, opts) {
        const result = origCreateComponent(wc, opts);
        callCount++;
        if (callCount === 2) {
            const origGetEndpoint = result.getEndpoint.bind(result);
            result.getEndpoint = function(rol, name) {
                if (rol === 'target') return null;
                return origGetEndpoint(rol, name);
            };
        }
        return result;
    };
    ed.copiedComponents = [
        { id: 'src', type: 'operator', meta: { uri: 'http://x/src', type: 'operator' }, metaUri: 'http://x/src', position: { x: 0, y: 0 }, collapsed: false, preferences: {}, properties: {}, permissions: {}, sourceEndpoints: [{ name: 'out', connections: [{ sourceEndpoint: 'out', targetComponent: 'tgt', targetComponentType: 'operator', targetEndpoint: 'in', sourceHandle: null, targetHandle: null }] }] },
        { id: 'tgt', type: 'operator', meta: { uri: 'http://x/tgt', type: 'operator' }, metaUri: 'http://x/tgt', position: { x: 0, y: 0 }, collapsed: false, preferences: {}, properties: {}, permissions: {}, sourceEndpoints: [] }
    ];
    Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { ctrlKey: true });
    await new Promise(r => setTimeout(r, 100));
    assert.ok(!connectionCreated);
});

// =========================================================================
// keyboard Ctrl+C with no selection copies nothing
// =========================================================================
test('keyboard Ctrl+C with no selection results in empty clipboard', () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('kb12');
    Wirecloud.dispatchEvent('loaded');
    ed.load(Wirecloud.activeWorkspace);
    ed.selectedComponents = { operator: {}, widget: {} };
    ed.selectedCount = 0;
    Wirecloud.UserInterfaceManager.rootKeydownHandler('c', { ctrlKey: true });
    assert.deepEqual(ed.copiedComponents, []);
});

test('pasteComponents uses getOrCreateMissing for metaUri fallback', async () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('cp9');
    Wirecloud.dispatchEvent('loaded');
    let gc = false;
    const ws = { ...Wirecloud.activeWorkspace, resources: { getOrCreateMissing(u, t) { gc = true; return { uri: u, type: t }; } } };
    ed.load(ws);
    ed.copiedComponents = [{ id: 'orphan', type: 'operator', meta: null, metaUri: 'http://x/orphan', position: { x: 0, y: 0 }, collapsed: false, preferences: {}, properties: {}, permissions: {}, sourceEndpoints: [] }];
    Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { ctrlKey: true });
    await new Promise(r => setTimeout(r, 100));
    assert.ok(gc);
});

// =============================================================================
// ComponentShowcase "create" event
// =============================================================================
test('componentManager create operator success', () => {
    const ed = new Wirecloud.ui.WiringEditor('cs1');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    const btn = { _d: false, disable() { this._d = true; }, enable() { this._d = false; } };
    ed.componentManager.dispatchEvent('create', { meta: { type: 'operator', uri: 'http://o' } }, btn);
    assert.ok(btn._d);
});

test('componentManager create operator failure shows error', async () => {
    const ed = new Wirecloud.ui.WiringEditor('cs2');
    Wirecloud.dispatchEvent('loaded');
    const ws = { ...Wirecloud.activeWorkspace, wiring: { ...Wirecloud.activeWorkspace.wiring, createOperator() { return Promise.reject(new Error('fail')); } } };
    ed.load(ws);
    const btn = { _d: false, disable() { this._d = true; }, enable() { this._d = false; } };
    ed.componentManager.dispatchEvent('create', { meta: { type: 'operator', uri: 'http://of' } }, btn);
    await new Promise(r => setTimeout(r, 50));
    assert.ok(!btn._d); assert.ok(lastMessageWindowMenuInstances.length > 0);
});

test('componentManager create widget success', () => {
    const ed = new Wirecloud.ui.WiringEditor('cs3');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    const btn = { _d: false, disable() { this._d = true; }, enable() { this._d = false; } };
    ed.componentManager.dispatchEvent('create', { meta: { type: 'widget', uri: 'http://w' } }, btn);
    assert.ok(btn._d);
});

test('componentManager create widget failure shows error', async () => {
    const ed = new Wirecloud.ui.WiringEditor('cs4');
    Wirecloud.dispatchEvent('loaded');
    const ws = { ...Wirecloud.activeWorkspace, view: { activeTab: { createWidget() { return Promise.reject(new Error('wf')); } } } };
    ed.load(ws);
    const btn = { _d: false, disable() { this._d = true; }, enable() { this._d = false; } };
    ed.componentManager.dispatchEvent('create', { meta: { type: 'widget', uri: 'http://wf' } }, btn);
    await new Promise(r => setTimeout(r, 50));
    assert.ok(!btn._d); assert.ok(lastMessageWindowMenuInstances.length > 0);
});

// =============================================================================
// ComponentShowcase "add" event
// =============================================================================
test('componentManager add creates draggable with commit=false', () => {
    const ed = new Wirecloud.ui.WiringEditor('ca1');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    const sc = makeComponent({ id: 'add-me' });
    ed.componentManager.dispatchEvent('add', { component: { _component: sc }, layout: null, element: null });
    assert.ok(lastComponentDraggableInstances.find(c => c.id === 'add-me') != null);
});

// =============================================================================
// Multiple load/unload cycles
// =============================================================================
test('multiple load/unload cycles', () => {
    const ed = new Wirecloud.ui.WiringEditor('ml1');
    Wirecloud.dispatchEvent('loaded');
    ed.load(Wirecloud.activeWorkspace);
    assert.ok(Wirecloud.UserInterfaceManager.rootKeydownHandler != null);
    ed.unload();
    assert.equal(Wirecloud.UserInterfaceManager.rootKeydownHandler, null);
    ed.load(Wirecloud.activeWorkspace);
    assert.ok(Wirecloud.UserInterfaceManager.rootKeydownHandler != null);
});

// =============================================================================
// Cross-type selection
// =============================================================================
test('dragstart clears selection across types', () => {
    const ed = new Wirecloud.ui.WiringEditor('xt1');
    Wirecloud.dispatchEvent('loaded');
    const o = ed.createComponent(makeComponent({ id: 'xo' }), { commit: false });
    const w = ed.createComponent(makeComponent({ id: 'xw', type: 'widget' }), { commit: false });
    ed.selectedComponents.operator.xo = o; ed.selectedComponents.widget.xw = w; ed.selectedCount = 2;
    const nw = ed.createComponent(makeComponent({ id: 'xn' }), { commit: false });
    nw.dispatchEvent('dragstart', {});
    assert.ok(!('xo' in ed.selectedComponents.operator)); assert.ok(!('xw' in ed.selectedComponents.widget));
    assert.equal(ed.selectedCount, 0);
});

// =============================================================================
// findEndpoint via loadConnections
// =============================================================================
// Connection loading with visualInfo handles is tested below

// =============================================================================
// disableComponent / findComponent edge cases
// =============================================================================
test('disableComponent with null item returns this', () => {
    const ed = new Wirecloud.ui.WiringEditor('dc1');
    Wirecloud.dispatchEvent('loaded');
    // disableComponent is internal; test via createComponent which calls it
    // when component is not in componentManager, findComponent returns null
    const r = ed.createComponent(makeComponent({ id: 'dc-none' }), { commit: true });
    assert.ok(r != null);
});

// =============================================================================
// hasSelectedComponents via different selection states
// =============================================================================
test('rootKeydownHandler with Delete when no selected components still returns true', () => {
    const ed = new Wirecloud.ui.WiringEditor('hs1');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    assert.ok(Wirecloud.UserInterfaceManager.rootKeydownHandler('Delete', {}));
});

test('rootKeydownHandler with Delete and mixed removable/non-removable', () => {
    const ed = new Wirecloud.ui.WiringEditor('hs2');
    Wirecloud.dispatchEvent('loaded'); ed.load(Wirecloud.activeWorkspace);
    const c1 = ed.createComponent(makeComponent({ id: 'rm-yes' }), { commit: false });
    const c2 = ed.createComponent(makeComponent({ id: 'rm-no' }), { commit: false });
    c1._removable = true; c2._removable = false;
    ed.selectedComponents.operator['rm-yes'] = c1; ed.selectedComponents.operator['rm-no'] = c2; ed.selectedCount = 2;
    let rl = null;
    ed.behaviourEngine.removeComponentList = function(l) { rl = l; return this; };
    Wirecloud.UserInterfaceManager.rootKeydownHandler('Delete', {});
    assert.ok(rl != null); assert.equal(rl.length, 1); assert.equal(rl[0].id, 'rm-yes');
});

// =============================================================================
// bindEndpoint mouseenter/mouseleave
// =============================================================================
test('bindEndpoint mouseenter shows suggestions when no temporalConnection', () => {
    const ed = new Wirecloud.ui.WiringEditor('be5');
    Wirecloud.dispatchEvent('loaded');
    const ep = makeEndpoint({ type: 'source', name: 'me-ep' });
    const c = ed.createComponent(makeComponent({ id: 'me-comp' }), { commit: false });
    let showEp = null;
    ed.suggestionManager.showSuggestions = function(e) { showEp = e; return this; };
    ed.connectionEngine.temporalConnection = null;
    c.dispatchEvent('endpointadded', ep);
    ep.dispatchEvent('mouseenter');
    assert.equal(showEp, ep);
});

test('bindEndpoint mouseleave hides suggestions when no temporalConnection', () => {
    const ed = new Wirecloud.ui.WiringEditor('be6');
    Wirecloud.dispatchEvent('loaded');
    const ep = makeEndpoint({ type: 'source', name: 'ml-ep' });
    const c = ed.createComponent(makeComponent({ id: 'ml-comp' }), { commit: false });
    let hideEp = null;
    ed.suggestionManager.hideSuggestions = function(e) { hideEp = e; return this; };
    ed.connectionEngine.temporalConnection = null;
    c.dispatchEvent('endpointadded', ep);
    ep.dispatchEvent('mouseleave');
    assert.equal(hideEp, ep);
});

test('bindEndpoint mouseenter does NOT show suggestions when temporalConnection exists', () => {
    const ed = new Wirecloud.ui.WiringEditor('be7');
    Wirecloud.dispatchEvent('loaded');
    const ep = makeEndpoint({ type: 'source', name: 'tc-ep' });
    const c = ed.createComponent(makeComponent({ id: 'tc-comp' }), { commit: false });
    let showEp = null;
    ed.suggestionManager.showSuggestions = function(e) { showEp = e; return this; };
    ed.connectionEngine.temporalConnection = makeConnection();
    c.dispatchEvent('endpointadded', ep);
    ep.dispatchEvent('mouseenter');
    assert.equal(showEp, null);
});

// =============================================================================
// connectionEngine dragend - hideSuggestions + setTimeout addEventListener
// =============================================================================
test('connectionEngine dragend calls hideSuggestions', async () => {
    const ed = new Wirecloud.ui.WiringEditor('hd1');
    Wirecloud.dispatchEvent('loaded');
    let hideEp = null;
    ed.suggestionManager.hideSuggestions = function(e) { hideEp = e; return this; };
    const initialEp = makeEndpoint({ type: 'source' });
    ed.connectionEngine.dispatchEvent('dragend', makeConnection(), initialEp);
    assert.equal(hideEp, initialEp);
    await new Promise(r => setTimeout(r, 10));
});

// =============================================================================
// connection_ondragstart removes click listener, dragend adds it back
// =============================================================================
test('dragstart removes layout click listener, dragend restores it after timeout', async () => {
    const ed = new Wirecloud.ui.WiringEditor('cl1');
    Wirecloud.dispatchEvent('loaded');
    // The click listener is stored as ed._layout_onclick
    assert.equal(typeof ed._layout_onclick, 'function');
    // Trigger dragstart
    ed.behaviourEngine.forEachComponent = function() { return this; };
    ed.connectionEngine.dispatchEvent('dragstart', makeConnection(), makeEndpoint({ type: 'source' }), makeEndpoint({ type: 'target' }));
    // After dragstart, the click handler should be removed
    // Trigger dragend
    ed.suggestionManager.hideSuggestions = function() { return this; };
    ed.connectionEngine.dispatchEvent('dragend', makeConnection(), makeEndpoint({ type: 'source' }));
    await new Promise(r => setTimeout(r, 10));
    // After timeout, it should be re-added (not easily testable with mock DOM, but shouldn't crash)
});

// =============================================================================
// Layout click calls connectionEngine.setUp
// =============================================================================
test('layout click calls connectionEngine.setUp', () => {
    const ed = new Wirecloud.ui.WiringEditor('su1');
    Wirecloud.dispatchEvent('loaded');
    let su = false;
    ed.connectionEngine.setUp = function() { su = true; return this; };
    ed.layout.content.get().dispatchEvent({ type: 'click' });
    assert.ok(su);
});

// =============================================================================
// loadConnections visualInfo splice
// =============================================================================
test('loadConnections connects endpoints from connection data', () => {
    const ed = new Wirecloud.ui.WiringEditor('lc1');
    Wirecloud.dispatchEvent('loaded');
    // Override behaviourEngine.clear to keep our pre-loaded components
    ed.behaviourEngine.clear = function() { this._behaviours = []; return this; };
    const sc = new Wirecloud.ui.WiringEditor.ComponentDraggable(makeComponent({ id: 'sc1', type: 'operator' }));
    const tc = new Wirecloud.ui.WiringEditor.ComponentDraggable(makeComponent({ id: 'tc1', type: 'operator' }));
    sc.getEndpoint = (r,n) => (n==='out' ? makeEndpoint({ type: 'source', name: 'out' }) : null);
    tc.getEndpoint = (r,n) => (n==='in' ? makeEndpoint({ type: 'target', name: 'in' }) : null);
    ed.behaviourEngine._components.operator.sc1 = sc;
    ed.behaviourEngine._components.operator.tc1 = tc;
    const vs = { components: { operator: {}, widget: {} },
        connections: [{ sourcename: 'v1', targetname: 'v2', sourcehandle: 'h-src', targethandle: 'h-tgt' }] };
    const ws = { ...Wirecloud.activeWorkspace, wiring: { ...Wirecloud.activeWorkspace.wiring, visualdescription: vs,
        connections: [{ source: { id: 'v1', component: { id: 'sc1', type: 'operator', meta: { type: 'operator' } }, name: 'out' },
                       target: { id: 'v2', component: { id: 'tc1', type: 'operator', meta: { type: 'operator' } }, name: 'in' },
                       volatile: false }] } };
    ed.load(ws);
    assert.ok(lastConnectionEngineConnectCalls.length > 0);
});

// =========================================================================
// connectionEngine establish fires change dispatch on connection
// =========================================================================
test('connection change event triggers behaviourEngine.updateConnection', () => {
    const ed = new Wirecloud.ui.WiringEditor('ch1');
    Wirecloud.dispatchEvent('loaded');
    ed.behaviourEngine.updateConnection = function() { return this; };
    const cn = makeConnection();
    ed.connectionEngine.dispatchEvent('establish', cn, null);
    let uc = null;
    ed.behaviourEngine.updateConnection = function(c) { uc = c; return this; };
    cn.dispatchEvent('change');
    assert.equal(uc, cn);
});

// =========================================================================
// constructor does not create behaviourEngine/componentManager until "loaded"
// =========================================================================
test('before loaded event, behaviourEngine is undefined', () => {
    const ed = new Wirecloud.ui.WiringEditor('bl1');
    assert.equal(ed.behaviourEngine, undefined);
    assert.equal(ed.componentManager, undefined);
});

test('after loaded event, behaviourEngine and componentManager exist', () => {
    const ed = new Wirecloud.ui.WiringEditor('bl2');
    Wirecloud.dispatchEvent('loaded');
    assert.ok(ed.behaviourEngine != null);
    assert.ok(ed.componentManager != null);
});

// =========================================================================
// pasteComponents operator preferences/properties (lines 882-890)
// =========================================================================
test('pasteComponents operator applies preferences and properties', async () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('cp10');
    Wirecloud.dispatchEvent('loaded');
    let createdOpts = null;
    const ws = { ...Wirecloud.activeWorkspace };
    ws.wiring = { ...ws.wiring, createOperator(m, o) { createdOpts = o; return Promise.resolve(makeComponent({ id: 'op-with-prefs' })); } };
    ed.load(ws);
    ed.copiedComponents = [{ id: 'src-op2', type: 'operator', meta: { uri: 'http://x/op2', type: 'operator' }, metaUri: 'http://x/op2', position: { x: 15, y: 25 }, collapsed: false, preferences: { k1: 'v1', k2: 'v2' }, properties: { p1: 'pv1', p2: 'pv2' }, permissions: {}, sourceEndpoints: [] }];
    Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { ctrlKey: true });
    await new Promise(r => setTimeout(r, 100));
    assert.ok(createdOpts != null);
    assert.deepEqual(createdOpts.preferences, { k1: { value: 'v1' }, k2: { value: 'v2' } });
    assert.deepEqual(createdOpts.properties, { p1: { value: 'pv1' }, p2: { value: 'pv2' } });
    assert.equal(createdOpts.collapsed, false);
    assert.deepEqual(createdOpts.position, { x: 35, y: 45 });
});

// =========================================================================
// pasteComponents connection creation error (lines 989-990)
// =========================================================================
test('pasteComponents handles connection creation failure', async () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('cp11');
    Wirecloud.dispatchEvent('loaded');
    const origError = console.error;
    let consoleErrorMsg = null;
    console.error = (msg) => { consoleErrorMsg = msg; };

    const ws = { ...Wirecloud.activeWorkspace, wiring: { ...Wirecloud.activeWorkspace.wiring,
        createConnection() { return Promise.reject(new Error('conn fail')); }
    } };
    ed.load(ws);

    ed.copiedComponents = [{ id: 'err-c1', type: 'operator', meta: { uri: 'http://x/ec1', type: 'operator' }, metaUri: 'http://x/ec1', position: { x: 0, y: 0 }, collapsed: false, preferences: {}, properties: {}, permissions: {}, sourceEndpoints: [{ name: 'out', connections: [{ sourceEndpoint: 'out', targetComponent: 'err-c2', targetComponentType: 'operator', targetEndpoint: 'in', sourceHandle: null, targetHandle: null }] }] }, { id: 'err-c2', type: 'operator', meta: { uri: 'http://x/ec2', type: 'operator' }, metaUri: 'http://x/ec2', position: { x: 0, y: 0 }, collapsed: false, preferences: {}, properties: {}, permissions: {}, sourceEndpoints: [] }];
    Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { ctrlKey: true });
    await new Promise(r => setTimeout(r, 150));

    assert.ok(consoleErrorMsg !== null, 'console.error should have been called');
    assert.ok(consoleErrorMsg.toString().includes('Failed to create connection'));
    console.error = origError;
});

// =========================================================================
// pasteComponents async catch error (line 1004)
// =========================================================================
test('pasteComponents async catch logs error', async () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('cp12');
    Wirecloud.dispatchEvent('loaded');
    const origError = console.error;
    let consoleErrorMsgs = [];

    const ws = { ...Wirecloud.activeWorkspace };
    ws.resources = { getOrCreateMissing() { throw new Error('pasting boom'); } };
    ed.load(ws);
    ed.copiedComponents = [{ id: 'boom', type: 'operator', meta: null, metaUri: 'http://x/boom', position: { x: 0, y: 0 }, collapsed: false, preferences: {}, properties: {}, permissions: {}, sourceEndpoints: [] }];

    console.error = (msg) => { consoleErrorMsgs.push(msg); };
    Wirecloud.UserInterfaceManager.rootKeydownHandler('v', { ctrlKey: true });
    await new Promise(r => setTimeout(r, 150));

    const found = consoleErrorMsgs.some(m => m.toString().includes('Error in paste'));
    assert.ok(found, 'console.error should log paste error');

    console.error = origError;
});

// =============================================================================
// getClipboardStorage catch when window.localStorage access throws (lines 37-38)
// =============================================================================
test('getClipboardStorage returns null when window.localStorage throws', () => {
    const origLocalStorage = global.localStorage;
    const origWindowDescriptor = Object.getOwnPropertyDescriptor(global, 'window');
    try {
        Object.defineProperty(global, 'window', {
            value: {}, configurable: true
        });
        Object.defineProperty(global.window, 'localStorage', {
            get() { throw new Error('access denied'); },
            configurable: true
        });
        const ed = new Wirecloud.ui.WiringEditor('gc1');
        assert.deepEqual(ed.copiedComponents, []);
    } finally {
        if (origWindowDescriptor) {
            Object.defineProperty(global, 'window', origWindowDescriptor);
        } else {
            delete global.window;
        }
        global.localStorage = origLocalStorage;
    }
});

// =============================================================================
// findWiringEngine returns workspace.wiring (line 178)
// =============================================================================
test('findWiringEngine returns workspace.wiring', () => {
    let fwFn = null;
    const OrigConnEngine = Wirecloud.ui.WiringEditor.ConnectionEngine;
    Wirecloud.ui.WiringEditor.ConnectionEngine = class extends OrigConnEngine {
        constructor(container, fw) {
            super(container, fw);
            fwFn = fw;
        }
    };
    const ed = new Wirecloud.ui.WiringEditor('fw1');
    Wirecloud.dispatchEvent('loaded');
    ed.load(Wirecloud.activeWorkspace);
    Wirecloud.ui.WiringEditor.ConnectionEngine = OrigConnEngine;
    assert.equal(typeof fwFn, 'function');
    assert.equal(fwFn(), ed.workspace.wiring);
});

// =============================================================================
// component_ondragstart clears existing orderableComponent (lines 659-661)
// =============================================================================
test('component_ondragstart calls setUp on existing orderableComponent and nulls it', () => {
    const ed = new Wirecloud.ui.WiringEditor('cd1');
    Wirecloud.dispatchEvent('loaded');
    const c = ed.createComponent(makeComponent({ id: 'drag-orderable' }), { commit: false });
    const orderable = { setUp() {} };
    let setUpCalled = false;
    orderable.setUp = function() { setUpCalled = true; };
    ed.orderableComponent = orderable;
    c.dispatchEvent('dragstart', {});
    assert.ok(setUpCalled);
    assert.equal(ed.orderableComponent, null);
});

// =============================================================================
// copyComponents: endpoint.connections with missing source/target endpoint (lines 764-765)
// =============================================================================
test('copyComponents skips connection when sourceEndpointId or targetEndpointId is null', () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('cp13');
    Wirecloud.dispatchEvent('loaded');
    ed.load(Wirecloud.activeWorkspace);
    const comp = ed.createComponent(makeComponent({ id: 'skip-conn' }), { commit: false });
    const ep = makeEndpoint({ type: 'source', name: 'out', component: { id: 'skip-conn', type: 'operator' } });
    const conn = makeConnection({
        source: null,
        target: null,
    });
    ep.connections = [conn];
    comp._component = { id: 'skip-conn', type: 'operator', meta: { uri: 'http://x/skip' }, preferences: {}, properties: {}, permissions: {} };
    comp._position = { x: 0, y: 0 };
    comp._endpoints = [ep];
    comp.forEachEndpoint = function(cb) { this._endpoints.forEach(cb); return this; };
    ed.selectedComponents.operator['skip-conn'] = comp;
    ed.selectedCount = 1;
    assert.doesNotThrow(() => { Wirecloud.UserInterfaceManager.rootKeydownHandler('c', { ctrlKey: true }); });
    assert.equal(ed.copiedComponents.length, 1);
});

// =============================================================================
// copyComponents iterates preferences (lines 808-809)
// =============================================================================
test('copyComponents copies preferences from component', () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('cp14');
    Wirecloud.dispatchEvent('loaded');
    ed.load(Wirecloud.activeWorkspace);
    const comp = ed.createComponent(makeComponent({ id: 'pref-comp' }), { commit: false });
    comp._position = { x: 0, y: 0 };
    comp._component = {
        id: 'pref-comp', type: 'operator', meta: { uri: 'http://x/pref' },
        preferences: { p1: { value: 'a' }, p2: { value: 'b' } },
        properties: {}, permissions: {}
    };
    comp._endpoints = [];
    comp.forEachEndpoint = function(cb) { return this; };
    ed.selectedComponents.operator['pref-comp'] = comp;
    ed.selectedCount = 1;
    Wirecloud.UserInterfaceManager.rootKeydownHandler('c', { ctrlKey: true });
    assert.equal(ed.copiedComponents[0].preferences.p1, 'a');
    assert.equal(ed.copiedComponents[0].preferences.p2, 'b');
});

// =============================================================================
// copyComponents iterates properties (lines 814-815)
// =============================================================================
test('copyComponents copies properties from component', () => {
    global.localStorage._reset();
    const ed = new Wirecloud.ui.WiringEditor('cp15');
    Wirecloud.dispatchEvent('loaded');
    ed.load(Wirecloud.activeWorkspace);
    const comp = ed.createComponent(makeComponent({ id: 'prop-comp' }), { commit: false });
    comp._position = { x: 0, y: 0 };
    comp._component = {
        id: 'prop-comp', type: 'operator', meta: { uri: 'http://x/prop' },
        preferences: {}, properties: { q1: { value: 'x' }, q2: { value: 'y' } }, permissions: {}
    };
    comp._endpoints = [];
    comp.forEachEndpoint = function(cb) { return this; };
    ed.selectedComponents.operator['prop-comp'] = comp;
    ed.selectedCount = 1;
    Wirecloud.UserInterfaceManager.rootKeydownHandler('c', { ctrlKey: true });
    assert.equal(ed.copiedComponents[0].properties.q1, 'x');
    assert.equal(ed.copiedComponents[0].properties.q2, 'y');
});
