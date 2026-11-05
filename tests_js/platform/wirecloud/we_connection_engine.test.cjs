const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScripts,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');

let connectionCounter = 0;
let wiringComponentCounter = 0;

function makeComponent(overrides = {}) {
    wiringComponentCounter++;
    return {
        id: `comp-${wiringComponentCounter}`,
        equals(other) { return this === other || (other != null && this.id === other.id); },
        ...overrides,
    };
}

function makeEndpoint(overrides = {}) {
    const component = overrides.component || makeComponent();
    const defaults = {
        id: `ep-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        type: 'source',
        component,
        _connections: [],
        _eventListeners: {},
        disabled: false,
        active: false,
        anchorPosition: { x: 100, y: 200 },
        equals(other) { return other != null && this.id === other.id; },
        addEventListener(name, handler) {
            if (this._eventListeners[name] == null) { this._eventListeners[name] = []; }
            this._eventListeners[name].push(handler);
            return this;
        },
        removeEventListener(name, handler) {
            if (this._eventListeners[name]) {
                this._eventListeners[name] = this._eventListeners[name].filter((l) => l !== handler);
            }
            return this;
        },
        dispatchEvent(name) {
            const list = this._eventListeners[name] || [];
            list.forEach((h) => h.call(this, this));
        },
        disable() { this.disabled = true; },
        enable() { this.disabled = false; },
        activate() { this.active = true; },
        deactivate() { this.disabled = false; this.active = false; },
        hasConnection(connection) {
            if (connection == null) return false;
            return this._connections.some((c) => c.equals(connection));
        },
        hasConnectionTo(otherEndpoint) {
            if (otherEndpoint == null) return false;
            return this._connections.some((c) => {
                const other = otherEndpoint.type === 'target' ? c.target : c.source;
                return other && other.endpoint && other.endpoint.equals(otherEndpoint);
            });
        },
        getConnectionTo(otherEndpoint) {
            return this._connections.find((c) => {
                const other = otherEndpoint.type === 'target' ? c.target : c.source;
                return other && other.endpoint && other.endpoint.equals(otherEndpoint);
            });
        },
        appendConnection(connection) { this._connections.push(connection); },
        removeConnection(connection) {
            this._connections = this._connections.filter((c) => !c.equals(connection));
        },
        toggleActive() {},
        hasEndpoints() { return true; },
        ...overrides,
    };
    return defaults;
}

function makeConnection(overrides = {}) {
    connectionCounter++;
    const sourceEndpoint = overrides.sourceEndpoint || makeEndpoint({ type: 'source' });
    const targetEndpoint = overrides.targetEndpoint || makeEndpoint({ type: 'target' });

    const conn = {
        _id: connectionCounter,
        _classSet: new Set(),
        _enabled: true,
        _editable: false,
        _active: false,
        _background: false,
        _listeners: {},
        _sourceEndpoint: sourceEndpoint,
        _targetEndpoint: targetEndpoint,
        source: { endpoint: sourceEndpoint, handle: null },
        target: { endpoint: targetEndpoint, handle: null },
        options: {
            _parent: null,
            _element: null,
            appendTo(el) {
                this._parent = el;
                if (!this._element) {
                    this._element = document.createElement('div');
                }
                if (el && el.appendChild) {
                    el.appendChild(this._element);
                }
                return this;
            },
            get() {
                if (!this._element) {
                    this._element = document.createElement('div');
                }
                return this._element;
            },
            show() {},
            hide() {},
        },
        wrapperElement: document.createElement('div'),

        get created() {
            return this.source.endpoint != null && this.target.endpoint != null;
        },
        get editable() { return this._editable; },
        set editable(v) { this._editable = v; },
        get active() { return this._active; },
        set active(v) { this._active = v; },
        get background() { return this._background; },
        set background(v) { this._background = v; },
        get enabled() { return this._enabled; },
        set enabled(v) { this._enabled = v; },
        get sourceId() { return this.source.endpoint ? this.source.endpoint.id : null; },
        get targetId() { return this.target.endpoint ? this.target.endpoint.id : null; },

        addEventListener(name, handler) {
            if (this._listeners[name] == null) { this._listeners[name] = []; }
            this._listeners[name].push(handler);
            return this;
        },
        removeEventListener(name, handler) {
            if (this._listeners[name]) {
                this._listeners[name] = this._listeners[name].filter((l) => l !== handler);
            }
            return this;
        },
        dispatchEvent(name, ...args) {
            const list = this._listeners[name] || [];
            list.forEach((h) => h.apply(this, [this].concat(args)));
        },
        equals(other) {
            if (other == null) return false;
            if (other._id != null && this._id === other._id) return true;
            return this.sourceId === other.sourceId && this.targetId === other.targetId;
        },
        click() {
            if (this.enabled && !this.editable) {
                this.active = !this.active;
                this.dispatchEvent('click');
            }
            return this;
        },
        remove() {
            this.dispatchEvent('remove');
            return this;
        },
        addClassName(cls) {
            this._classSet.add(cls);
            return this;
        },
        removeClassName(cls) {
            this._classSet.delete(cls);
            return this;
        },
        hasClassName(cls) {
            return this._classSet.has(cls);
        },
        toggleClassName(cls, force) {
            if (force === true || (force === undefined && !this._classSet.has(cls))) {
                this._classSet.add(cls);
            } else {
                this._classSet.delete(cls);
            }
            return this;
        },
        stickEndpoint(endpoint, options) {
            const opts = options || {};
            const etype = endpoint.type;
            this[etype] = {
                endpoint,
                handle: {
                    position() { return { x: 0, y: 0 }; },
                    toJSON() { return 'auto'; },
                    auto: true,
                    appendTo() { return this; },
                    remove() {},
                    updateDistance() { return this; },
                },
            };
            return this;
        },
        unstickEndpoint(endpoint) {
            this[endpoint.type] = {};
            return this;
        },
        appendTo(element) {
            if (element && element.appendChild) {
                element.appendChild(this.wrapperElement);
            }
            return this;
        },
        updateCursorPosition(pos) { return this; },
        createAndBind(readonly, wiringEngine) {
            const self = this;
            return Promise.resolve().then(() => self);
        },
        get() { return this.wrapperElement; },
        ...overrides,
    };
    return conn;
}

function makeContainer(overrides = {}) {
    const el = document.createElement('div');
    el.getBoundingClientRect = () => ({ left: 0, top: 0, width: 800, height: 600 });
    el.scrollLeft = 0;
    el.scrollTop = 0;
    el._listeners = {};
    el.addEventListener = function (name, handler) {
        if (this._listeners[name] == null) { this._listeners[name] = []; }
        this._listeners[name].push(handler);
    };
    el.removeEventListener = function () {};
    Object.assign(el, overrides);
    return {
        appendChild(child) { el.appendChild(child); },
        get() { return el; },
        ...overrides,
    };
}

function makeWiringEngine() {
    return {
        createConnection() {
            return Promise.resolve({
                logManager: { addEventListener() {}, errorCount: 0 },
                readonly: false,
                showLogs() {},
            });
        },
    };
}

function patchDocumentForSVG() {
    if (typeof document.createElementNS !== 'function') {
        const origCreateElement = document.createElement.bind(document);
        document.createElementNS = function (ns, tagName) {
            const el = origCreateElement(tagName);
            el.namespaceURI = ns;
            el.setAttributeNS = function () {};
            return el;
        };
    }
}

function ensureDocListeners() {
    if (document.listeners == null) {
        document.listeners = {};
    }
}

function createEngine(container) {
    const containerObj = container || makeContainer();
    let findCalls = 0;
    const wiring = makeWiringEngine();
    const findWiring = function () {
        findCalls++;
        return wiring;
    };
    const engine = new Wirecloud.ui.WiringEditor.ConnectionEngine(containerObj, findWiring);
    engine.enabled = true;
    return { engine, containerObj, findWiring, wiring, findCalls };
}

test.beforeEach(() => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();
    patchDocumentForSVG();

    if (global.Wirecloud == null) {
        global.Wirecloud = {};
    }
    Wirecloud.Utils = StyledElements.Utils;
    Wirecloud.ui = { WiringEditor: {} };

    connectionCounter = 0;
    wiringComponentCounter = 0;

    Wirecloud.ui.WiringEditor.Connection = makeConnection;

    loadLegacyScripts([
        'src/wirecloud/platform/static/js/wirecloud/ui/WiringEditor/ConnectionEngine.js',
    ]);
});

// =========================================================================
// STATIC CONSTANTS
// =========================================================================

test('SVG_NS is correct', () => {
    assert.equal(
        Wirecloud.ui.WiringEditor.ConnectionEngine.SVG_NS,
        "http://www.w3.org/2000/svg"
    );
});

test('CONNECTION_INVALID is -1', () => {
    assert.equal(Wirecloud.ui.WiringEditor.ConnectionEngine.CONNECTION_INVALID, -1);
});

test('CONNECTION_ESTABLISHED is 0', () => {
    assert.equal(Wirecloud.ui.WiringEditor.ConnectionEngine.CONNECTION_ESTABLISHED, 0);
});

test('CONNECTION_DUPLICATE is 1', () => {
    assert.equal(Wirecloud.ui.WiringEditor.ConnectionEngine.CONNECTION_DUPLICATE, 1);
});

// =========================================================================
// CONSTRUCTOR
// =========================================================================

test('constructor creates SVG wrapperElement with correct namespace', () => {
    const { engine } = createEngine();

    assert.equal(engine.wrapperElement.namespaceURI, Wirecloud.ui.WiringEditor.ConnectionEngine.SVG_NS);
    assert.equal(engine.wrapperElement.tagName, 'SVG');
});

test('constructor sets we-connections-layer class', () => {
    const { engine } = createEngine();

    assert.equal(engine.wrapperElement.getAttribute('class'), 'we-connections-layer');
});

test('constructor creates SVG g connectionsElement', () => {
    const { engine } = createEngine();

    assert.equal(engine.connectionsElement.tagName, 'G');
    assert.equal(engine.connectionsElement.namespaceURI, Wirecloud.ui.WiringEditor.ConnectionEngine.SVG_NS);
    assert.ok(engine.wrapperElement.childNodes.includes(engine.connectionsElement));
});

test('constructor creates div optionsElement', () => {
    const { engine } = createEngine();

    assert.equal(engine.optionsElement.tagName, 'DIV');
});

test('constructor initializes connections as empty array', () => {
    const { engine } = createEngine();

    assert.deepEqual(engine.connections, []);
});

test('constructor initializes endpoints with source and target arrays', () => {
    const { engine } = createEngine();

    assert.deepEqual(engine.endpoints, { source: [], target: [] });
});

test('constructor appends wrapperElement and optionsElement to container', () => {
    const container = makeContainer();
    const { engine } = createEngine(container);

    const children = container.get().childNodes;
    assert.ok(children.some((c) => c === engine.wrapperElement));
    assert.ok(children.some((c) => c === engine.optionsElement));
});

test('constructor adds scroll listener to container', () => {
    const container = makeContainer();
    createEngine(container);

    assert.ok(container.get()._listeners.scroll != null);
    assert.equal(container.get()._listeners.scroll.length, 1);
});

test('constructor binds _ondrag handler', () => {
    const { engine } = createEngine();

    assert.equal(typeof engine._ondrag, 'function');
});

test('constructor binds _ondragend handler', () => {
    const { engine } = createEngine();

    assert.equal(typeof engine._ondragend, 'function');
});

test('constructor sets up wiringEngine getter', () => {
    const container = makeContainer();
    const wiring = makeWiringEngine();
    const findWiring = () => wiring;
    const engine = new Wirecloud.ui.WiringEditor.ConnectionEngine(container, findWiring);

    assert.equal(engine.wiringEngine, wiring);
});

test('constructor binds endpoint event handlers', () => {
    const { engine } = createEngine();

    assert.equal(typeof engine.endpoint_ondragstart, 'function');
    assert.equal(typeof engine.endpoint_onmouseenter, 'function');
    assert.equal(typeof engine.endpoint_onmouseleave, 'function');
    assert.equal(typeof engine.endpoint_ondragend, 'function');
});

// =========================================================================
// appendEndpoint
// =========================================================================

test('appendEndpoint adds source endpoint to source array', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });

    engine.appendEndpoint(endpoint);

    assert.equal(engine.endpoints.source.length, 1);
    assert.equal(engine.endpoints.source[0], endpoint);
});

test('appendEndpoint adds target endpoint to target array', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'target' });

    engine.appendEndpoint(endpoint);

    assert.equal(engine.endpoints.target.length, 1);
    assert.equal(engine.endpoints.target[0], endpoint);
});

test('appendEndpoint adds mousedown listener', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });

    engine.appendEndpoint(endpoint);

    assert.ok(endpoint._eventListeners.mousedown != null);
    assert.ok(endpoint._eventListeners.mousedown.includes(engine.endpoint_ondragstart));
});

test('appendEndpoint adds mouseenter listener', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });

    engine.appendEndpoint(endpoint);

    assert.ok(endpoint._eventListeners.mouseenter != null);
    assert.ok(endpoint._eventListeners.mouseenter.includes(engine.endpoint_onmouseenter));
});

test('appendEndpoint adds mouseleave listener', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });

    engine.appendEndpoint(endpoint);

    assert.ok(endpoint._eventListeners.mouseleave != null);
    assert.ok(endpoint._eventListeners.mouseleave.includes(engine.endpoint_onmouseleave));
});

test('appendEndpoint adds mouseup listener', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });

    engine.appendEndpoint(endpoint);

    assert.ok(endpoint._eventListeners.mouseup != null);
    assert.ok(endpoint._eventListeners.mouseup.includes(engine.endpoint_ondragend));
});

test('appendEndpoint returns this', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });

    assert.equal(engine.appendEndpoint(endpoint), engine);
});

test('appendEndpoint adds multiple endpoints of same type', () => {
    const { engine } = createEngine();
    const ep1 = makeEndpoint({ type: 'source' });
    const ep2 = makeEndpoint({ type: 'source' });

    engine.appendEndpoint(ep1).appendEndpoint(ep2);

    assert.equal(engine.endpoints.source.length, 2);
    assert.equal(engine.endpoints.source[0], ep1);
    assert.equal(engine.endpoints.source[1], ep2);
});

// =========================================================================
// connect
// =========================================================================

test('connect returns engine', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConnection = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    const result = engine.connect(wiringConnection, source, target);

    assert.equal(result, engine);
});

test('connect creates connection in connections array', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConnection = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    engine.connect(wiringConnection, source, target);

    assert.equal(engine.connections.length, 1);
});

test('connect with null options defaults to empty object', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConnection = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    assert.doesNotThrow(() => {
        engine.connect(wiringConnection, source, target, null);
    });
});

test('connect with explicit options', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConnection = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    assert.doesNotThrow(() => {
        engine.connect(wiringConnection, source, target, {
            sourceHandle: { x: 50, y: 0 },
            targetHandle: { x: 0, y: 0 },
        });
    });
});

test('connect dispatches establish event', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConnection = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    let establishFired = false;
    engine.addEventListener('establish', () => { establishFired = true; });

    engine.connect(wiringConnection, source, target);

    assert.ok(establishFired);
});

// =========================================================================
// deactivateAll
// =========================================================================

test('deactivateAll when no active connection returns this', () => {
    const { engine } = createEngine();

    const result = engine.deactivateAll();

    assert.equal(result, engine);
    assert.equal(engine.hasActiveConnection(), false);
});

test('deactivateAll when has active connection clicks it', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConnection = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };
    engine.connect(wiringConnection, source, target);

    const conn = engine.connections[0];
    conn.active = true;
    engine.activeConnection = conn;

    let clicked = false;
    conn.click = function () {
        clicked = true;
        this.active = false;
        return this;
    };

    engine.deactivateAll();

    assert.ok(clicked);
});

test('deactivateAll returns this', () => {
    const { engine } = createEngine();

    assert.equal(engine.deactivateAll(), engine);
});

// =========================================================================
// clear
// =========================================================================

test('clear when no connections works', () => {
    const { engine } = createEngine();

    const result = engine.clear();

    assert.equal(result, engine);
    assert.deepEqual(engine.connections, []);
});

test('clear with connections removes them in reverse order', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConnection = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    engine.connect(wiringConnection, source, target);
    engine.connect(wiringConnection, source, target);

    assert.equal(engine.connections.length, 2);

    const removeOrder = [];
    engine.connections[0].remove = function () { removeOrder.push(0); return this; };
    engine.connections[1].remove = function () { removeOrder.push(1); return this; };

    engine.clear();

    assert.deepEqual(removeOrder, [1, 0]);
    assert.equal(engine.connections.length, 0);
});

test('clear returns this', () => {
    const { engine } = createEngine();

    assert.equal(engine.clear(), engine);
});

// =========================================================================
// forEachConnection
// =========================================================================

test('forEachConnection iterates all connections with index', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConnection = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    engine.connect(wiringConnection, source, target);
    engine.connect(wiringConnection, source, target);

    const results = [];
    engine.forEachConnection(function (conn, index) {
        results.push({ index, id: conn._id });
    });

    assert.equal(results.length, 2);
    assert.equal(results[0].index, 0);
    assert.equal(results[1].index, 1);
});

test('forEachConnection with empty array works', () => {
    const { engine } = createEngine();

    const results = [];
    engine.forEachConnection(function (conn, index) {
        results.push(index);
    });

    assert.deepEqual(results, []);
});

test('forEachConnection returns this', () => {
    const { engine } = createEngine();

    assert.equal(engine.forEachConnection(function () {}), engine);
});

// =========================================================================
// getConnection
// =========================================================================

test('getConnection finds connection by sourceId and targetId', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConnection = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };
    engine.connect(wiringConnection, source, target);

    const result = engine.getConnection(source.id, target.id);

    assert.ok(result != null);
    assert.equal(result.sourceId, source.id);
    assert.equal(result.targetId, target.id);
});

test('getConnection returns undefined for no match', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConnection = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };
    engine.connect(wiringConnection, source, target);

    const result = engine.getConnection('nonexistent', 'also-nonexistent');

    assert.equal(result, undefined);
});

test('getConnection returns first match when multiple exist', () => {
    const { engine } = createEngine();
    const source1 = makeEndpoint({ type: 'source' });
    const target1 = makeEndpoint({ type: 'target' });
    const source2 = makeEndpoint({ type: 'source' });
    const target2 = makeEndpoint({ type: 'target' });
    const wiringConnection = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    engine.connect(wiringConnection, source1, target1);
    engine.connect(wiringConnection, source2, target2);

    const result = engine.getConnection(source1.id, target1.id);

    assert.equal(result.sourceId, source1.id);
});

// =========================================================================
// hasActiveConnection
// =========================================================================

test('hasActiveConnection returns false initially', () => {
    const { engine } = createEngine();

    assert.equal(engine.hasActiveConnection(), false);
});

test('hasActiveConnection returns true after setting activeConnection', () => {
    const { engine } = createEngine();
    engine.activeConnection = {};

    assert.equal(engine.hasActiveConnection(), true);
});

test('hasActiveConnection returns false when null', () => {
    const { engine } = createEngine();
    engine.activeConnection = null;

    assert.equal(engine.hasActiveConnection(), false);
});

test('hasActiveConnection returns false when undefined', () => {
    const { engine } = createEngine();
    engine.activeConnection = undefined;

    assert.equal(engine.hasActiveConnection(), false);
});

// =========================================================================
// removeEndpoint
// =========================================================================

test('removeEndpoint removes source endpoint from array', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });
    engine.endpoints.source.push(endpoint);

    engine.removeEndpoint(endpoint);

    assert.equal(engine.endpoints.source.length, 0);
});

test('removeEndpoint removes target endpoint from array', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'target' });
    engine.endpoints.target.push(endpoint);

    engine.removeEndpoint(endpoint);

    assert.equal(engine.endpoints.target.length, 0);
});

test('removeEndpoint removes event listeners', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });
    engine.endpoints.source.push(endpoint);
    engine.appendEndpoint(endpoint);

    engine.removeEndpoint(endpoint);

    assert.equal(endpoint._eventListeners.mousedown.length, 0);
    assert.equal(endpoint._eventListeners.mouseenter.length, 0);
    assert.equal(endpoint._eventListeners.mouseleave.length, 0);
    assert.equal(endpoint._eventListeners.mouseup.length, 0);
});

test('removeEndpoint with non-existent endpoint does nothing', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });

    assert.doesNotThrow(() => {
        engine.removeEndpoint(endpoint);
    });
});

test('removeEndpoint returns this', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });

    assert.equal(engine.removeEndpoint(endpoint), engine);
});

test('removeEndpoint only removes matching endpoint', () => {
    const { engine } = createEngine();
    const ep1 = makeEndpoint({ type: 'source' });
    const ep2 = makeEndpoint({ type: 'source' });
    engine.endpoints.source.push(ep1, ep2);

    engine.removeEndpoint(ep1);

    assert.equal(engine.endpoints.source.length, 1);
    assert.equal(engine.endpoints.source[0], ep2);
});

// =========================================================================
// setUp
// =========================================================================

test('setUp calls deactivateAll', () => {
    const { engine } = createEngine();
    let deactivCalled = false;
    engine.deactivateAll = function () {
        deactivCalled = true;
        return this;
    };

    engine.setUp();

    assert.ok(deactivCalled);
});

test('setUp stops customizing when editableConnection exists', () => {
    const { engine } = createEngine();
    const conn = makeConnection();
    engine.editableConnection = conn;
    conn.editable = true;

    engine.setUp();

    assert.equal(conn.editable, false);
    assert.equal(engine.editableConnection, undefined);
});

test('setUp with no editableConnection is a no-op', () => {
    const { engine } = createEngine();

    assert.doesNotThrow(() => {
        engine.setUp();
    });
});

test('setUp returns this', () => {
    const { engine } = createEngine();

    assert.equal(engine.setUp(), engine);
});

// =========================================================================
// endpoint_ondragstart
// =========================================================================

test('endpoint_ondragstart returns early when engine not enabled', () => {
    const { engine } = createEngine();
    engine.enabled = false;
    const endpoint = makeEndpoint({ type: 'source' });

    engine.endpoint_ondragstart(endpoint);

    assert.equal(engine.temporalConnection, undefined);
    assert.equal(engine.temporalInitialEndpoint, undefined);
});

test('endpoint_ondragstart creates temporal connection', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });

    engine.endpoint_ondragstart(endpoint);

    assert.ok(engine.temporalConnection != null);
    assert.equal(engine.temporalInitialEndpoint, endpoint);
});

test('endpoint_ondragstart calls setUp', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });
    let setUpCalled = false;
    engine.setUp = function () { setUpCalled = true; return this; };

    engine.endpoint_ondragstart(endpoint);

    assert.ok(setUpCalled);
});

test('endpoint_ondragstart disables same-type endpoints', () => {
    const { engine } = createEngine();
    const sourceEp = makeEndpoint({ type: 'source' });
    const targetEp = makeEndpoint({ type: 'target' });

    engine.endpoints.source.push(sourceEp);
    engine.endpoints.target.push(targetEp);
    engine.appendEndpoint(sourceEp);

    engine.endpoint_ondragstart(sourceEp);

    // initialEndpoint.type is 'source', so source endpoints get disabled
    // and target endpoints remain enabled (allowing source->target connections)
    assert.equal(sourceEp.disabled, true);
    assert.equal(targetEp.disabled, false);
});

test('endpoint_ondragstart adds dragging class', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });

    engine.endpoint_ondragstart(endpoint);

    assert.ok(engine.wrapperElement.classList.contains('dragging'));
});

test('endpoint_ondragstart adds document mousemove and mouseup listeners', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });
    ensureDocListeners();
    document.listeners = {};

    engine.endpoint_ondragstart(endpoint);

    assert.ok(document.listeners.mousemove != null);
    assert.ok(document.listeners.mousemove.includes(engine._ondrag));
    assert.ok(document.listeners.mouseup != null);
    assert.ok(document.listeners.mouseup.includes(engine._ondragend));
});

test('endpoint_ondragstart dispatches dragstart event', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });

    let fired = false;
    let firedConnection = null;
    let firedInitialEndpoint = null;
    let firedEndpoint = null;
    // DispatchEvent sends [context, connection, initialEndpoint, endpoint]
    engine.addEventListener('dragstart', (engineCtx, connection, initialEndpoint, epArg) => {
        fired = true;
        firedConnection = connection;
        firedInitialEndpoint = initialEndpoint;
        firedEndpoint = epArg;
    });

    engine.endpoint_ondragstart(endpoint);

    assert.ok(fired);
    assert.ok(firedConnection != null);
    assert.equal(firedInitialEndpoint, endpoint);
    assert.equal(firedEndpoint, endpoint);
});

test('endpoint_ondragstart with background active connection clicks it', () => {
    const { engine } = createEngine();
    const component1 = makeComponent({ id: 'comp-bg-1' });
    const component2 = makeComponent({ id: 'comp-bg-2' });
    const endpoint = makeEndpoint({ type: 'source', component: component1 });
    const targetEp = makeEndpoint({ type: 'target', component: component2 });

    engine.endpoints.source.push(endpoint);
    engine.endpoints.target.push(targetEp);

    const conn = makeConnection({ sourceEndpoint: endpoint, targetEndpoint: targetEp });
    conn.background = true;
    conn.active = true;

    let clickCalled = false;
    conn.click = function () { clickCalled = true; delete this.active; return this; };

    endpoint._connections = [conn];
    endpoint.hasConnection = function (c) { return c != null && c._id === conn._id; };

    engine.activeConnection = conn;

    engine.endpoint_ondragstart(endpoint);

    assert.ok(clickCalled);
    assert.equal(engine.temporalInitialEndpoint, endpoint);
});

test('endpoint_ondragstart with non-background active connection sets backup', () => {
    const { engine } = createEngine();
    const component1 = makeComponent({ id: 'comp-nb-1' });
    const component2 = makeComponent({ id: 'comp-nb-2' });
    const sourceEp = makeEndpoint({ type: 'source', component: component1 });
    const targetEp = makeEndpoint({ type: 'target', component: component2 });

    engine.endpoints.source.push(sourceEp);
    engine.endpoints.target.push(targetEp);

    const conn = makeConnection({ sourceEndpoint: sourceEp, targetEndpoint: targetEp });
    conn.background = false;
    conn.active = true;

    let addClassCalled = false;
    conn.addClassName = function (cls) {
        if (cls === 'temporal') addClassCalled = true;
        return this;
    };

    sourceEp._connections = [conn];
    targetEp._connections = [conn];
    sourceEp.hasConnection = function (c) { return c != null && c._id === conn._id; };

    engine.activeConnection = conn;

    engine.endpoint_ondragstart(sourceEp);

    assert.ok(addClassCalled);
    assert.equal(engine._connectionBackup, conn);
    assert.equal(engine.temporalInitialEndpoint, targetEp);
});

test('endpoint_ondragstart with no existing connection uses endpoint as initial', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });

    engine.endpoint_ondragstart(endpoint);

    assert.equal(engine.temporalInitialEndpoint, endpoint);
    assert.equal(engine._connectionBackup, undefined);
});

// =========================================================================
// connection_ondrag
// =========================================================================

test('connection_ondrag updates cursor position on temporal connection', () => {
    const { engine, containerObj } = createEngine();
    const containerEl = containerObj.get();
    containerEl.getBoundingClientRect = () => ({ left: 50, top: 100, width: 800, height: 600 });
    containerEl.scrollLeft = 10;
    containerEl.scrollTop = 20;

    const endpoint = makeEndpoint({ type: 'source' });
    engine.endpoint_ondragstart(endpoint);

    let cursorPos = null;
    engine.temporalConnection.updateCursorPosition = function (pos) {
        cursorPos = pos;
        return this;
    };

    engine._ondrag({ clientX: 300, clientY: 400 });

    assert.equal(cursorPos.x, 300 + 10 - 50);
    assert.equal(cursorPos.y, 400 + 20 - 100);
});

// =========================================================================
// connection_ondragend
// =========================================================================

test('connection_ondragend calls preventDefault and stopPropagation', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });
    engine.endpoint_ondragstart(endpoint);

    let prevented = false;
    let stopped = false;

    engine._ondragend({
        preventDefault() { prevented = true; },
        stopPropagation() { stopped = true; },
    });

    assert.ok(prevented);
    assert.ok(stopped);
});

// =========================================================================
// endpoint_ondragend
// =========================================================================

test('endpoint_ondragend returns early if engine not enabled', () => {
    const { engine } = createEngine();
    engine.enabled = false;
    engine.temporalConnection = {};
    engine.temporalInitialEndpoint = makeEndpoint({ type: 'source' });

    const result = engine.endpoint_ondragend(makeEndpoint({ type: 'target' }));

    assert.equal(result, undefined);
});

test('endpoint_ondragend returns early if no temporalConnection', () => {
    const { engine } = createEngine();
    engine.enabled = true;
    engine.temporalConnection = null;
    engine.temporalInitialEndpoint = null;

    const result = engine.endpoint_ondragend(makeEndpoint({ type: 'target' }));

    assert.equal(result, undefined);
});

test('endpoint_ondragend removes dragging class', () => {
    const { engine } = createEngine();
    const sourceEp = makeEndpoint({ type: 'source' });
    const targetEp = makeEndpoint({ type: 'target' });

    engine.endpoints.source.push(sourceEp);
    engine.endpoints.target.push(targetEp);
    engine.appendEndpoint(sourceEp);
    engine.appendEndpoint(targetEp);

    engine.endpoint_ondragstart(sourceEp);
    engine.endpoint_ondragend(targetEp);

    assert.ok(!engine.wrapperElement.classList.contains('dragging'));
});

test('endpoint_ondragend re-enables endpoints', () => {
    const { engine } = createEngine();
    const sourceEp = makeEndpoint({ type: 'source' });
    const targetEp = makeEndpoint({ type: 'target' });

    engine.endpoints.source.push(sourceEp);
    engine.endpoints.target.push(targetEp);

    // Simulate a disabled source endpoint (same type as temporalInitialEndpoint)
    sourceEp.disable();
    assert.equal(sourceEp.disabled, true);

    engine.temporalConnection = makeConnection();
    engine.temporalInitialEndpoint = sourceEp;
    engine.enabled = true;

    engine.endpoint_ondragend(targetEp);

    // enableEndpoints is called with temporalInitialEndpoint.type ('source'),
    // so source endpoints get re-enabled
    assert.equal(sourceEp.disabled, false);
});

test('endpoint_ondragend with connection backup removes temporal class', () => {
    const { engine } = createEngine();
    const component1 = makeComponent({ id: 'comp-be-1' });
    const component2 = makeComponent({ id: 'comp-be-2' });
    const sourceEp = makeEndpoint({ type: 'source', component: component1 });
    const targetEp = makeEndpoint({ type: 'target', component: component2 });

    engine.endpoints.source.push(sourceEp);
    engine.endpoints.target.push(targetEp);

    const backupConn = makeConnection();
    let classRemoved = false;
    backupConn.removeClassName = function (cls) {
        if (cls === 'temporal') classRemoved = true;
        return this;
    };

    engine._connectionBackup = backupConn;
    engine.temporalConnection = makeConnection();
    engine.temporalInitialEndpoint = sourceEp;
    engine.enabled = true;

    engine.endpoint_ondragend(targetEp);

    assert.ok(classRemoved);
});

test('endpoint_ondragend ESTABLISHED dispatches establish event', () => {
    const { engine } = createEngine();
    const component1 = makeComponent({ id: 'comp-e1' });
    const component2 = makeComponent({ id: 'comp-e2' });
    const sourceEp = makeEndpoint({ type: 'source', component: component1 });
    const targetEp = makeEndpoint({ type: 'target', component: component2 });

    engine.endpoints.source.push(sourceEp);
    engine.endpoints.target.push(targetEp);

    let establishFired = false;
    engine.addEventListener('establish', () => { establishFired = true; });

    const tempConn = makeConnection();
    tempConn.createAndBind = function () { return Promise.resolve(this); };

    engine.temporalConnection = tempConn;
    engine.temporalInitialEndpoint = sourceEp;
    engine.enabled = true;

    engine.endpoint_ondragend(targetEp);

    assert.ok(establishFired);
});

test('endpoint_ondragend ESTABLISHED clicks temporal when backup exists', () => {
    const { engine } = createEngine();
    const component1 = makeComponent({ id: 'comp-ecb1' });
    const component2 = makeComponent({ id: 'comp-ecb2' });
    const sourceEp = makeEndpoint({ type: 'source', component: component1 });
    const targetEp = makeEndpoint({ type: 'target', component: component2 });

    engine.endpoints.source.push(sourceEp);
    engine.endpoints.target.push(targetEp);

    engine._connectionBackup = makeConnection();

    const tempConn = makeConnection();
    let clickCalled = false;
    tempConn.click = function () { clickCalled = true; return this; };
    tempConn.createAndBind = function () { return Promise.resolve(this); };

    engine.temporalConnection = tempConn;
    engine.temporalInitialEndpoint = sourceEp;
    engine.enabled = true;

    engine.endpoint_ondragend(targetEp);

    assert.ok(clickCalled);
});

test('endpoint_ondragend catches createAndBind rejection', async () => {
    const { engine } = createEngine();
    const component1 = makeComponent({ id: 'comp-cb1' });
    const component2 = makeComponent({ id: 'comp-cb2' });
    const sourceEp = makeEndpoint({ type: 'source', component: component1 });
    const targetEp = makeEndpoint({ type: 'target', component: component2 });

    engine.endpoints.source.push(sourceEp);
    engine.endpoints.target.push(targetEp);

    const tempConn = makeConnection();
    const error = new Error('create failed');
    tempConn.createAndBind = function () { return Promise.reject(error); };

    engine.temporalConnection = tempConn;
    engine.temporalInitialEndpoint = sourceEp;
    engine.enabled = true;

    assert.doesNotThrow(() => {
        engine.endpoint_ondragend(targetEp);
    });

    await new Promise((resolve) => setTimeout(resolve, 10));
});

test('endpoint_ondragend DUPLICATE dispatches duplicate event and clicks existing', () => {
    const { engine } = createEngine();
    const component1 = makeComponent({ id: 'comp-d1' });
    const component2 = makeComponent({ id: 'comp-d2' });
    const sourceEp = makeEndpoint({ type: 'source', component: component1 });
    const targetEp = makeEndpoint({ type: 'target', component: component2 });

    const existingConn = makeConnection({ sourceEndpoint: sourceEp, targetEndpoint: targetEp });
    let existingClicked = false;
    existingConn.click = function () { existingClicked = true; return this; };

    sourceEp._connections.push(existingConn);
    targetEp._connections.push(existingConn);

    engine.endpoints.source.push(sourceEp);
    engine.endpoints.target.push(targetEp);

    let duplicateFired = false;
    engine.addEventListener('duplicate', () => { duplicateFired = true; });

    const tempConn = makeConnection();
    let removeCalled = false;
    tempConn.remove = function () { removeCalled = true; return this; };

    engine.temporalConnection = tempConn;
    engine.temporalInitialEndpoint = sourceEp;
    engine.enabled = true;

    engine.endpoint_ondragend(targetEp);

    assert.ok(duplicateFired);
    assert.ok(removeCalled);
    assert.ok(existingClicked);
});

test('endpoint_ondragend INVALID (null finalEndpoint) dispatches cancel', () => {
    const { engine } = createEngine();
    const sourceEp = makeEndpoint({ type: 'source' });

    engine.endpoints.source.push(sourceEp);

    let cancelFired = false;
    engine.addEventListener('cancel', () => { cancelFired = true; });

    const tempConn = makeConnection();
    let removeCalled = false;
    tempConn.remove = function () { removeCalled = true; return this; };

    engine.temporalConnection = tempConn;
    engine.temporalInitialEndpoint = sourceEp;
    engine.enabled = true;

    engine.endpoint_ondragend(null);

    assert.ok(cancelFired);
    assert.ok(removeCalled);
});

test('endpoint_ondragend INVALID with backup clicks backup', () => {
    const { engine } = createEngine();
    const sourceEp = makeEndpoint({ type: 'source' });

    engine.endpoints.source.push(sourceEp);

    const backupConn = makeConnection();
    let backupClicked = false;
    backupConn.click = function () { backupClicked = true; return this; };
    engine._connectionBackup = backupConn;

    const tempConn = makeConnection();
    tempConn.remove = function () { return this; };

    engine.temporalConnection = tempConn;
    engine.temporalInitialEndpoint = sourceEp;
    engine.enabled = true;

    engine.endpoint_ondragend(null);

    assert.ok(backupClicked);
});

test('endpoint_ondragend removes document listeners', () => {
    const { engine } = createEngine();
    const sourceEp = makeEndpoint({ type: 'source' });
    engine.endpoints.source.push(sourceEp);

    ensureDocListeners();
    document.listeners.mousemove = [engine._ondrag];
    document.listeners.mouseup = [engine._ondragend];

    const tempConn = makeConnection();
    engine.temporalConnection = tempConn;
    engine.temporalInitialEndpoint = sourceEp;
    engine.enabled = true;

    engine.endpoint_ondragend(null);

    assert.ok(!(document.listeners.mousemove || []).includes(engine._ondrag));
    assert.ok(!(document.listeners.mouseup || []).includes(engine._ondragend));
});

test('endpoint_ondragend dispatches dragend event', () => {
    const { engine } = createEngine();
    const sourceEp = makeEndpoint({ type: 'source' });

    engine.endpoints.source.push(sourceEp);

    let dragendFired = false;
    let dragendConn = null;
    let dragendEp = null;
    // DispatchEvent sends [context, temporalConnection, temporalInitialEndpoint]
    engine.addEventListener('dragend', (engineCtx, connection, initialEndpoint) => {
        dragendFired = true;
        dragendConn = connection;
        dragendEp = initialEndpoint;
    });

    const tempConn = makeConnection();
    engine.temporalConnection = tempConn;
    engine.temporalInitialEndpoint = sourceEp;
    engine.enabled = true;

    engine.endpoint_ondragend(null);

    assert.ok(dragendFired);
    assert.equal(dragendConn, tempConn);
    assert.equal(dragendEp, sourceEp);
});

test('endpoint_ondragend cleans up temporal properties', () => {
    const { engine } = createEngine();
    const sourceEp = makeEndpoint({ type: 'source' });

    engine.endpoints.source.push(sourceEp);

    const tempConn = makeConnection();
    engine.temporalConnection = tempConn;
    engine.temporalInitialEndpoint = sourceEp;
    engine._connectionBackup = makeConnection();
    engine.enabled = true;

    engine.endpoint_ondragend(null);

    assert.equal(engine.temporalInitialEndpoint, undefined);
    assert.equal(engine._connectionBackup, undefined);
    assert.equal(engine.temporalConnection, undefined);
});

// =========================================================================
// endpoint_onmouseenter
// =========================================================================

test('endpoint_onmouseenter does nothing without temporalConnection', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });
    engine.temporalConnection = null;

    assert.doesNotThrow(() => {
        engine.endpoint_onmouseenter(endpoint);
    });
});

test('endpoint_onmouseenter activates and sticks endpoint', () => {
    const { engine } = createEngine();
    const targetEp = makeEndpoint({ type: 'target' });

    const tempConn = makeConnection();
    let stickCalled = false;
    let stickOptions = null;
    tempConn.stickEndpoint = function (ep, options) {
        stickCalled = true;
        stickOptions = options;
        return this;
    };

    engine.temporalConnection = tempConn;

    engine.endpoint_onmouseenter(targetEp);

    assert.equal(targetEp.active, true);
    assert.ok(stickCalled);
    assert.deepEqual(stickOptions, { establish: false });
});

test('endpoint_onmouseenter removes document mousemove listener', () => {
    const { engine } = createEngine();
    const targetEp = makeEndpoint({ type: 'target' });

    ensureDocListeners();
    document.listeners.mousemove = [engine._ondrag];
    assert.ok(document.listeners.mousemove.includes(engine._ondrag));

    const tempConn = makeConnection();
    engine.temporalConnection = tempConn;

    engine.endpoint_onmouseenter(targetEp);

    assert.ok(!(document.listeners.mousemove || []).includes(engine._ondrag));
});

// =========================================================================
// endpoint_onmouseleave
// =========================================================================

test('endpoint_onmouseleave does nothing without temporalConnection', () => {
    const { engine } = createEngine();
    const endpoint = makeEndpoint({ type: 'source' });
    engine.temporalConnection = null;

    assert.doesNotThrow(() => {
        engine.endpoint_onmouseleave(endpoint);
    });
});

test('endpoint_onmouseleave deactivates and unsticks endpoint', () => {
    const { engine } = createEngine();
    const targetEp = makeEndpoint({ type: 'target' });

    let unstickCalled = false;
    let unstickEndpoint = null;
    const tempConn = makeConnection();
    tempConn.unstickEndpoint = function (ep) {
        unstickCalled = true;
        unstickEndpoint = ep;
        return this;
    };

    engine.temporalConnection = tempConn;

    engine.endpoint_onmouseleave(targetEp);

    assert.equal(targetEp.disabled, false);
    assert.ok(unstickCalled);
    assert.equal(unstickEndpoint, targetEp);
});

test('endpoint_onmouseleave adds document mousemove and touchmove listeners', () => {
    const { engine } = createEngine();
    const targetEp = makeEndpoint({ type: 'target' });

    ensureDocListeners();
    document.listeners = {};

    const tempConn = makeConnection();
    engine.temporalConnection = tempConn;

    engine.endpoint_onmouseleave(targetEp);

    assert.ok(document.listeners.mousemove != null);
    assert.ok(document.listeners.mousemove.includes(engine._ondrag));
    assert.ok(document.listeners.touchmove != null);
    assert.ok(document.listeners.touchmove.includes(engine._ondrag));
});

// =========================================================================
// container_onscroll
// =========================================================================

test('container_onscroll sets transform on connectionsElement', () => {
    const container = makeContainer();
    const { engine } = createEngine(container);
    const containerEl = container.get();
    containerEl.scrollLeft = 50;
    containerEl.scrollTop = 30;

    containerEl._listeners.scroll[0].call(engine);

    assert.equal(engine.connectionsElement.getAttribute('transform'), 'translate(-50 -30)');
});

test('container_onscroll sets wrapperElement style', () => {
    const container = makeContainer();
    const { engine } = createEngine(container);
    const containerEl = container.get();
    containerEl.scrollLeft = 100;
    containerEl.scrollTop = 75;

    containerEl._listeners.scroll[0].call(engine);

    assert.equal(engine.wrapperElement.style.top, '75px');
    assert.equal(engine.wrapperElement.style.left, '100px');
});

test('container_onscroll with zero scroll produces translate(0 0)', () => {
    const container = makeContainer();
    const { engine } = createEngine(container);
    const containerEl = container.get();
    containerEl.scrollLeft = 0;
    containerEl.scrollTop = 0;

    containerEl._listeners.scroll[0].call(engine);

    assert.equal(engine.connectionsElement.getAttribute('transform'), 'translate(0 0)');
    assert.equal(engine.wrapperElement.style.top, '0px');
    assert.equal(engine.wrapperElement.style.left, '0px');
});

// =========================================================================
// validateConnection (tested via endpoint_ondragend)
// =========================================================================

test('validateConnection: null finalEndpoint returns INVALID', () => {
    // When finalEndpoint is null, validateConnection returns INVALID.
    // This triggers the default case and dispatches 'cancel'.
    const { engine } = createEngine();
    const sourceEp = makeEndpoint({ type: 'source' });

    engine.endpoints.source.push(sourceEp);

    let cancelFired = false;
    engine.addEventListener('cancel', () => { cancelFired = true; });

    engine.temporalConnection = makeConnection();
    engine.temporalInitialEndpoint = sourceEp;
    engine.enabled = true;

    engine.endpoint_ondragend(null);

    assert.ok(cancelFired);
});

test('validateConnection: same type (source-source) returns INVALID', () => {
    const { engine } = createEngine();
    const component1 = makeComponent({ id: 'c-ss-1' });
    const component2 = makeComponent({ id: 'c-ss-2' });
    const sourceEp1 = makeEndpoint({ type: 'source', component: component1 });
    const sourceEp2 = makeEndpoint({ type: 'source', component: component2 });

    engine.endpoints.source.push(sourceEp1, sourceEp2);

    let cancelFired = false;
    engine.addEventListener('cancel', () => { cancelFired = true; });

    engine.temporalConnection = makeConnection();
    engine.temporalInitialEndpoint = sourceEp1;
    engine.enabled = true;

    engine.endpoint_ondragend(sourceEp2);

    assert.ok(cancelFired);
});

test('validateConnection: same type (target-target) returns INVALID', () => {
    const { engine } = createEngine();
    const component1 = makeComponent({ id: 'c-tt-1' });
    const component2 = makeComponent({ id: 'c-tt-2' });
    const targetEp1 = makeEndpoint({ type: 'target', component: component1 });
    const targetEp2 = makeEndpoint({ type: 'target', component: component2 });

    engine.endpoints.target.push(targetEp1, targetEp2);

    let cancelFired = false;
    engine.addEventListener('cancel', () => { cancelFired = true; });

    engine.temporalConnection = makeConnection();
    engine.temporalInitialEndpoint = targetEp1;
    engine.enabled = true;

    engine.endpoint_ondragend(targetEp2);

    assert.ok(cancelFired);
});

test('validateConnection: same component returns INVALID', () => {
    const { engine } = createEngine();
    const component = makeComponent({ id: 'same-comp' });
    const sourceEp = makeEndpoint({ type: 'source', component });
    const targetEp = makeEndpoint({ type: 'target', component });

    engine.endpoints.source.push(sourceEp);
    engine.endpoints.target.push(targetEp);

    let cancelFired = false;
    engine.addEventListener('cancel', () => { cancelFired = true; });

    engine.temporalConnection = makeConnection();
    engine.temporalInitialEndpoint = sourceEp;
    engine.enabled = true;

    engine.endpoint_ondragend(targetEp);

    assert.ok(cancelFired);
});

test('validateConnection: existing connection returns DUPLICATE', () => {
    const { engine } = createEngine();
    const component1 = makeComponent({ id: 'c-dup-1' });
    const component2 = makeComponent({ id: 'c-dup-2' });
    const sourceEp = makeEndpoint({ type: 'source', component: component1 });
    const targetEp = makeEndpoint({ type: 'target', component: component2 });

    const existingConn = makeConnection({ sourceEndpoint: sourceEp, targetEndpoint: targetEp });
    existingConn.click = function () { return this; };

    sourceEp._connections.push(existingConn);
    targetEp._connections.push(existingConn);

    engine.endpoints.source.push(sourceEp);
    engine.endpoints.target.push(targetEp);

    let duplicateFired = false;
    engine.addEventListener('duplicate', () => { duplicateFired = true; });

    engine.temporalConnection = makeConnection();
    engine.temporalInitialEndpoint = sourceEp;
    engine.enabled = true;

    engine.endpoint_ondragend(targetEp);

    assert.ok(duplicateFired);
});

test('validateConnection: valid pair returns ESTABLISHED', () => {
    const { engine } = createEngine();
    const component1 = makeComponent({ id: 'c-ok-1' });
    const component2 = makeComponent({ id: 'c-ok-2' });
    const sourceEp = makeEndpoint({ type: 'source', component: component1 });
    const targetEp = makeEndpoint({ type: 'target', component: component2 });

    engine.endpoints.source.push(sourceEp);
    engine.endpoints.target.push(targetEp);

    let establishFired = false;
    engine.addEventListener('establish', () => { establishFired = true; });

    const tempConn = makeConnection();
    tempConn.createAndBind = function () { return Promise.resolve(this); };

    engine.temporalConnection = tempConn;
    engine.temporalInitialEndpoint = sourceEp;
    engine.enabled = true;

    engine.endpoint_ondragend(targetEp);

    assert.ok(establishFired);
});

// =========================================================================
// connection_onclick
// =========================================================================

test('connection_onclick: clicking non-editable active connection sets activeConnection', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConn = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    let clickFired = false;
    engine.addEventListener('click', () => { clickFired = true; });

    engine.connect(wiringConn, source, target);

    const conn = engine.connections[0];
    conn.editable = false;
    conn.active = true;

    conn._listeners.click[0].call(engine, conn);

    assert.ok(clickFired);
    assert.equal(engine.activeConnection, conn);
});

test('connection_onclick: clicking second active connection deactivates first', () => {
    const { engine } = createEngine();
    const source1 = makeEndpoint({ type: 'source' });
    const target1 = makeEndpoint({ type: 'target' });
    const wiringConn = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    engine.connect(wiringConn, source1, target1);
    const conn1 = engine.connections[0];

    const source2 = makeEndpoint({ type: 'source' });
    const target2 = makeEndpoint({ type: 'target' });
    engine.connect(wiringConn, source2, target2);
    const conn2 = engine.connections[1];

    conn1.active = true;
    conn1.editable = false;
    conn2.active = true;
    conn2.editable = false;

    engine.activeConnection = conn1;

    let conn1Clicked = false;
    conn1.click = function () { conn1Clicked = true; delete this.active; return this; };

    conn2._listeners.click[0].call(engine, conn2);

    assert.ok(conn1Clicked);
    assert.equal(engine.activeConnection, conn2);
});

test('connection_onclick: clicking inactive connection deletes activeConnection', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConn = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    engine.connect(wiringConn, source, target);
    const conn = engine.connections[0];
    conn.active = false;
    conn.editable = false;
    engine.activeConnection = conn;

    conn._listeners.click[0].call(engine, conn);

    assert.equal(engine.activeConnection, undefined);
});

test('connection_onclick: clicking editable connection does nothing', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConn = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    let clickFired = false;
    engine.addEventListener('click', () => { clickFired = true; });

    engine.connect(wiringConn, source, target);
    const conn = engine.connections[0];
    conn.editable = true;
    conn.active = false;

    conn._listeners.click[0].call(engine, conn);

    assert.equal(clickFired, false);
});

test('connection_onclick: non-editable connection not equal to editable stops customizing', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConn = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    engine.connect(wiringConn, source, target);
    const conn = engine.connections[0];
    conn.editable = false;
    conn.active = false;

    const otherConn = makeConnection();
    otherConn.editable = true;
    engine.editableConnection = otherConn;

    conn._listeners.click[0].call(engine, conn);

    assert.equal(otherConn.editable, false);
    assert.equal(engine.editableConnection, undefined);
});

test('connection_onclick: connection equals editableConnection skips stopCustomizing', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConn = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    engine.connect(wiringConn, source, target);
    const conn = engine.connections[0];

    // Set up: connection is NOT editable, but equals the engine's editableConnection
    conn._editable = false;  // connection itself is not in editing mode
    conn.active = true;

    // Mark the connection as the one currently being customized
    engine.editableConnection = conn;
    conn.editable = true;  // engine's editableConnection is conn and conn IS editable

    // Now that conn IS editable, the click handler should see !connection.editable = false
    // and skip the entire block (including stopCustomizing)
    let stopCustomizingCalled = false;
    const origSetUp = engine.setUp;
    engine.setUp = function () {
        stopCustomizingCalled = true;
        return this;
    };

    conn._listeners.click[0].call(engine, conn);

    // stopCustomizing should NOT have been called because conn is editable
    assert.equal(stopCustomizingCalled, false);
});

// =========================================================================
// connection_onremove
// =========================================================================

test('connection_onremove removes connection from array', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConn = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    engine.connect(wiringConn, source, target);
    const conn = engine.connections[0];

    conn._listeners.remove[0].call(engine, conn);

    assert.equal(engine.connections.length, 0);
});

test('connection_onremove removes options child', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConn = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    engine.connect(wiringConn, source, target);
    const conn = engine.connections[0];
    const optionsEl = conn.options.get();
    assert.ok(engine.optionsElement.childNodes.includes(optionsEl));

    conn._listeners.remove[0].call(engine, conn);

    assert.ok(!engine.optionsElement.childNodes.includes(optionsEl));
});

test('connection_onremove deactivates active connection', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConn = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    engine.connect(wiringConn, source, target);
    const conn = engine.connections[0];

    // Set the connection as active (this is what makes deactivateAll->click work correctly)
    conn.active = true;
    engine.activeConnection = conn;

    // Override deactivateAll to avoid side effects from cleanup
    let deactivated = false;
    engine.deactivateAll = function () { deactivated = true; delete this.activeConnection; return this; };

    conn._listeners.remove[0].call(engine, conn);

    assert.ok(deactivated);
});

test('connection_onremove with non-matching connection (indexOf returns -1) does nothing', () => {
    const { engine } = createEngine();
    const conn = makeConnection();

    // The remove listener was never added to engine for this connection,
    // but if we simulate calling it with a connection not in the array:
    engine.connections.length = 0;
    engine.activeConnection = conn;

    // No-op: connection not in array so indexOf returns -1
    assert.doesNotThrow(() => {
        // simulate the body of connection_onremove for a connection not in the array
        const index = engine.connections.indexOf(conn);
        assert.equal(index, -1);
    });
});

// =========================================================================
// connection_oncustomizestart
// =========================================================================

test('connection_oncustomizestart calls setUp and sets editableConnection', () => {
    const { engine } = createEngine();
    const source = makeEndpoint({ type: 'source' });
    const target = makeEndpoint({ type: 'target' });
    const wiringConn = { readonly: false, logManager: { errorCount: 0, addEventListener() {} } };

    engine.connect(wiringConn, source, target);
    const conn = engine.connections[0];

    let setUpCalled = false;
    engine.setUp = function () { setUpCalled = true; return this; };

    conn._listeners.customizestart[0].call(engine, conn);

    assert.ok(setUpCalled);
    assert.equal(engine.editableConnection, conn);
});

// =========================================================================
// stopCustomizing (via setUp and connection_oncustomizestart)
// =========================================================================

test('stopCustomizing with editableConnection sets editable to false and clears', () => {
    const { engine } = createEngine();
    const conn = makeConnection();
    conn.editable = true;
    engine.editableConnection = conn;

    engine.setUp();

    assert.equal(conn.editable, false);
    assert.equal(engine.editableConnection, undefined);
});

test('stopCustomizing with null editableConnection is no-op', () => {
    const { engine } = createEngine();

    assert.doesNotThrow(() => {
        engine.setUp();
    });
});

// =========================================================================
// Full integration-style lifecycle tests
// =========================================================================

test('full lifecycle: drag start -> end -> establish connection', () => {
    const { engine } = createEngine();
    const component1 = makeComponent({ id: 'comp-full-1' });
    const component2 = makeComponent({ id: 'comp-full-2' });
    const sourceEp = makeEndpoint({ type: 'source', component: component1 });
    const targetEp = makeEndpoint({ type: 'target', component: component2 });

    engine.endpoints.source.push(sourceEp);
    engine.endpoints.target.push(targetEp);
    engine.appendEndpoint(sourceEp);
    engine.appendEndpoint(targetEp);

    const events = [];
    engine.addEventListener('dragstart', () => events.push('dragstart'));
    engine.addEventListener('establish', () => events.push('establish'));
    engine.addEventListener('dragend', () => events.push('dragend'));

    engine.endpoint_ondragstart(sourceEp);

    assert.ok(events.includes('dragstart'));
    assert.ok(engine.wrapperElement.classList.contains('dragging'));

    engine.endpoint_ondragend(targetEp);

    assert.ok(events.includes('establish'));
    assert.ok(events.includes('dragend'));
    assert.ok(!engine.wrapperElement.classList.contains('dragging'));
    assert.equal(engine.temporalConnection, undefined);
    assert.equal(engine.temporalInitialEndpoint, undefined);
    assert.equal(engine._connectionBackup, undefined);
});

test('full lifecycle: mouseenter/mouseleave during drag toggles document listeners', () => {
    const { engine } = createEngine();
    const component1 = makeComponent({ id: 'comp-me-1' });
    const component2 = makeComponent({ id: 'comp-me-2' });
    const sourceEp = makeEndpoint({ type: 'source', component: component1 });
    const targetEp = makeEndpoint({ type: 'target', component: component2 });

    engine.endpoints.source.push(sourceEp);
    engine.endpoints.target.push(targetEp);
    engine.appendEndpoint(sourceEp);
    engine.appendEndpoint(targetEp);

    ensureDocListeners();
    document.listeners = {};

    engine.endpoint_ondragstart(sourceEp);
    assert.ok(document.listeners.mousemove.includes(engine._ondrag));

    engine.endpoint_onmouseenter(targetEp);
    assert.ok(!(document.listeners.mousemove || []).includes(engine._ondrag));

    engine.endpoint_onmouseleave(targetEp);
    assert.ok(document.listeners.mousemove.includes(engine._ondrag));
});

test('full lifecycle: duplicate connection dispatches duplicate', () => {
    const { engine } = createEngine();
    const component1 = makeComponent({ id: 'comp-fd-1' });
    const component2 = makeComponent({ id: 'comp-fd-2' });
    const sourceEp = makeEndpoint({ type: 'source', component: component1 });
    const targetEp = makeEndpoint({ type: 'target', component: component2 });

    const existingConn = makeConnection({ sourceEndpoint: sourceEp, targetEndpoint: targetEp });
    let existingClicked = false;
    existingConn.click = function () { existingClicked = true; return this; };
    sourceEp._connections.push(existingConn);
    targetEp._connections.push(existingConn);

    engine.endpoints.source.push(sourceEp);
    engine.endpoints.target.push(targetEp);
    engine.appendEndpoint(sourceEp);
    engine.appendEndpoint(targetEp);

    let duplicateFired = false;
    engine.addEventListener('duplicate', () => { duplicateFired = true; });

    engine.endpoint_ondragstart(sourceEp);
    engine.endpoint_ondragend(targetEp);

    assert.ok(duplicateFired);
    assert.ok(existingClicked);
});

test('full lifecycle: same component returns INVALID and dispatches cancel', () => {
    const { engine } = createEngine();
    const component = makeComponent({ id: 'same-comp-lc' });
    const sourceEp = makeEndpoint({ type: 'source', component });
    const targetEp = makeEndpoint({ type: 'target', component });

    engine.endpoints.source.push(sourceEp);
    engine.endpoints.target.push(targetEp);
    engine.appendEndpoint(sourceEp);
    engine.appendEndpoint(targetEp);

    let cancelFired = false;
    engine.addEventListener('cancel', () => { cancelFired = true; });

    engine.endpoint_ondragstart(sourceEp);
    engine.endpoint_ondragend(targetEp);

    assert.ok(cancelFired);
});

// =========================================================================
// click to connect (opt-in)
// =========================================================================

const startClickDraft = () => {
    const { engine } = createEngine();
    const component1 = makeComponent({ id: 'comp-click-1' });
    const component2 = makeComponent({ id: 'comp-click-2' });
    const sourceEp = makeEndpoint({ type: 'source', component: component1 });
    const targetEp = makeEndpoint({ type: 'target', component: component2 });
    // Endpoint elements (the click is detected through the document mouseup)
    const anchor = { id: 'anchor' };
    sourceEp.get = () => ({ contains: (node) => node === anchor });
    engine.endpoints.source.push(sourceEp);
    engine.endpoints.target.push(targetEp);
    ensureDocListeners();
    document.listeners = {};
    engine.enabled = true;
    engine.clickToConnect = true;

    engine.endpoint_ondragstart(sourceEp);
    engine.temporalConnection.createAndBind = function () { return Promise.resolve(this); };
    const release = (target) => engine._ondragend({ preventDefault() {}, stopPropagation() {}, target });
    return { engine, sourceEp, targetEp, anchor, release };
};

test('click on an endpoint is a normal (cancelled) drag when clickToConnect is disabled', () => {
    const { engine, anchor, release } = startClickDraft();
    engine.clickToConnect = false;
    let cancelled = false;
    engine.addEventListener('cancel', () => { cancelled = true; });

    release(anchor);

    assert.ok(cancelled);
    assert.equal(engine.temporalConnection, undefined);
});

test('click on an endpoint starts a draft connection when clickToConnect is enabled', () => {
    const { engine, targetEp, anchor, release } = startClickDraft();
    let drafts = 0;
    let established = false;
    engine.addEventListener('draftstart', () => { drafts += 1; });
    engine.addEventListener('establish', () => { established = true; });

    release(anchor);
    assert.equal(drafts, 1);
    assert.ok(engine.temporalConnection != null, 'the draft connection is kept');
    assert.ok(!document.listeners.mouseup.includes(engine._ondragend));
    assert.ok(document.listeners.mousedown.includes(engine._ondraftmousedown));

    // Releasing the pointer elsewhere keeps the draft
    release({ id: 'canvas' });
    assert.ok(engine.temporalConnection != null);

    // Clicking an input completes the connection
    engine.endpoint_ondragstart(targetEp);
    assert.ok(established);
    assert.equal(engine.temporalConnection, undefined);
    assert.ok(!document.listeners.mousedown.includes(engine._ondraftmousedown));
});

test('dragging from an endpoint and releasing elsewhere cancels the connection', () => {
    const { engine, release } = startClickDraft();
    let cancelled = false;
    engine.addEventListener('cancel', () => { cancelled = true; });

    release({ id: 'canvas' });

    assert.ok(cancelled);
    assert.equal(engine.temporalConnection, undefined);
});

test('draft connections are cancelled by clicking outside the endpoints or programmatically', () => {
    let { engine, anchor, release } = startClickDraft();
    let cancelled = 0;
    engine.addEventListener('cancel', () => { cancelled += 1; });

    release(anchor);
    engine._ondraftmousedown({ target: { closest: () => ({}) } });
    assert.ok(engine.temporalConnection != null, 'mousedown on an endpoint is handled by the endpoint');
    engine._ondraftmousedown({ target: { closest: () => null } });
    assert.equal(cancelled, 1);
    assert.equal(engine.temporalConnection, undefined);

    ({ engine, anchor, release } = startClickDraft());
    release(anchor);
    assert.equal(engine.cancelTemporalConnection(), true);
    assert.equal(engine.temporalConnection, undefined);
    assert.equal(engine.cancelTemporalConnection(), false);
});
