const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScripts,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');

const setupComponentSidebar = () => {
    if (global.Wirecloud == null) {
        global.Wirecloud = {};
    }
    Wirecloud.Utils = StyledElements.Utils;
    Wirecloud.ui = {};

    Wirecloud.ui.MACSearch = function MACSearch(opts) {
        this.opts = opts;
        this.search_scope = opts.scope;
        this._events = {};
        this._wrapper = document.createElement('div');
        this._wrapper.classList = { add() {} };
    };
    Wirecloud.ui.MACSearch.prototype.addEventListener = function (type, handler) {
        if (!this._events[type]) this._events[type] = [];
        this._events[type].push(handler);
    };
    Wirecloud.ui.MACSearch.prototype.get = function () { return this._wrapper; };
    Wirecloud.ui.MACSearch.prototype.clear = function () {};
    Wirecloud.ui.MACSearch.prototype.refresh = function () {
        if (this._events.search) {
            this._events.search.forEach(function (h) { h(); });
        }
    };

    Wirecloud.ui.WiringEditor = {
        ComponentGroup: function ComponentGroup(group, actionLabel) {
            this.id = group;
            this.actionLabel = actionLabel;
            this._events = {};
            this._components = [];
        },
        Component: function Component(wiringComponent) {
            this.wiringComponent = wiringComponent;
            this.meta = wiringComponent.meta;
            this.id = '' + wiringComponent.id;
            this._events = {};
        },
    };
    Wirecloud.ui.WiringEditor.ComponentGroup.prototype.addEventListener = function (type, handler) {
        if (!this._events[type]) this._events[type] = [];
        this._events[type].push(handler);
    };
    Wirecloud.ui.WiringEditor.ComponentGroup.prototype.addComponent = function (comp) {
        this._components.push(comp);
    };
    Wirecloud.ui.WiringEditor.Component.prototype.addEventListener = function (type, handler) {
        if (!this._events[type]) this._events[type] = [];
        this._events[type].push(handler);
    };
    Wirecloud.ui.WiringEditor.Component.prototype.remove = function () {};

    StyledElements.Fragment = function Fragment(content) { this.content = content; };
    StyledElements.Container = function Container(opts) {
        opts = opts || {};
        this._children = [];
        this.wrapperElement = document.createElement('div');
        this.wrapperElement.classList = { add() {} };
    };
    StyledElements.Container.prototype.appendChild = function (child) {
        this._children.push(child); return this;
    };
    StyledElements.Container.prototype.prependChild = function (child) {
        this._children.unshift(child); return this;
    };
    StyledElements.Container.prototype.removeChild = function () { return this; };
    StyledElements.Container.prototype.repaint = function () { return this; };
    StyledElements.Container.prototype.insertInto = function () { return this; };

    StyledElements.ToggleButton = function ToggleButton(opts) {
        this.opts = opts;
        this.active = false;
        this._disabled = false;
        this._events = {};
    };
    StyledElements.ToggleButton.prototype.addEventListener = function (type, handler) {
        if (!this._events[type]) this._events[type] = [];
        this._events[type].push(handler);
        return this;
    };
    StyledElements.ToggleButton.prototype.setDisabled = function (d) { this._disabled = d; };

    loadLegacyScripts([
        'src/wirecloud/commons/static/js/StyledElements/Container.js',
    ]);

    loadLegacyScripts([
        'src/wirecloud/platform/static/js/wirecloud/ui/Registry.js',
        'src/wirecloud/platform/static/js/wirecloud/ui/ComponentSidebar.js',
    ]);
};

test.beforeEach(() => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();
    setupComponentSidebar();
});

test('ComponentSidebar constructor initializes with default state', () => {
    const sidebar = new Wirecloud.ui.ComponentSidebar();
    assert.ok(sidebar.components.mashup);
    assert.ok(sidebar.components.widget);
    assert.ok(sidebar.wrapperElement);
    assert.equal(sidebar.widgetButton.active, true);
    assert.equal(sidebar.mashupButton.active, false);
});

test('mashupButton click toggles filter type to mashup (lines 40-46)', () => {
    const sidebar = new Wirecloud.ui.ComponentSidebar();
    sidebar.mashupButton._events.click[0]();
    assert.equal(sidebar.mashupButton.active, true);
    assert.equal(sidebar.widgetButton.active, false);
    assert.equal(sidebar.searchComponents.search_scope, 'mashup');
});

test('widgetButton click toggles filter type to widget (lines 53-58)', () => {
    const sidebar = new Wirecloud.ui.ComponentSidebar();
    sidebar.mashupButton.active = true;
    sidebar.widgetButton.active = false;
    sidebar.widgetButton._events.click[0]();
    assert.equal(sidebar.mashupButton.active, false);
    assert.equal(sidebar.widgetButton.active, true);
    assert.equal(sidebar.searchComponents.search_scope, 'widget');
});

test('addComponent adds to correct type group (lines 98-119)', () => {
    const sidebar = new Wirecloud.ui.ComponentSidebar();
    const wiringComponent = {
        meta: { group_id: 'V/W', type: 'widget' },
        id: 'w1',
    };
    const component = sidebar.addComponent(wiringComponent);
    assert.ok(sidebar.components.widget['V/W']);
    assert.ok(sidebar.components.widget['V/W'].w1);
});

test('addComponent click dispatches add event with the created component', () => {
    const sidebar = new Wirecloud.ui.ComponentSidebar();
    let addedComponent = null;
    sidebar.addEventListener('add', (source, component) => { addedComponent = component; });

    const component = sidebar.addComponent({
        meta: { group_id: 'V/W', type: 'widget' },
        id: 'w1',
    });
    component._events.click[0]();

    assert.equal(addedComponent, component);
});

test('resource painter builds groups, attaches existing components, and dispatches create', () => {
    const sidebar = new Wirecloud.ui.ComponentSidebar();
    const mashup = sidebar.addComponent({ meta: { group_id: 'V/W', type: 'mashup' }, id: 'm1' });
    const widget = sidebar.addComponent({ meta: { group_id: 'V/W', type: 'widget' }, id: 'w1' });
    let createdGroup = null;
    let createButton = null;
    sidebar.addEventListener('create', (source, group, button) => {
        createdGroup = group;
        createButton = button;
    });

    const group = sidebar.searchComponents.opts.resource_painter.paint('V/W');
    const button = { id: 'button' };
    group._events['btncreate.click'][0](group, button);

    assert.equal(group.actionLabel, 'Add to workspace');
    assert.equal(group._components.includes(mashup), true);
    assert.equal(group._components.includes(widget), true);
    assert.equal(sidebar.groups['V/W'], group);
    assert.equal(createdGroup, group);
    assert.equal(createButton, button);
});

test('resource painter uses merge label for mashup search scope', () => {
    const sidebar = new Wirecloud.ui.ComponentSidebar();
    sidebar.searchComponents.search_scope = 'mashup';

    const group = sidebar.searchComponents.opts.resource_painter.paint('V/M');

    assert.equal(group.actionLabel, 'Merge');
});

test('addComponent adds to existing group when group exists (lines 114-116)', () => {
    const sidebar = new Wirecloud.ui.ComponentSidebar();
    let added = null;
    const group = {
        id: 'V/W',
        addEventListener() {},
        addComponent(c) { added = c; },
    };
    sidebar.groups['V/W'] = group;
    sidebar.addComponent({ meta: { group_id: 'V/W', type: 'widget' }, id: 'w1' });
    assert.ok(added);
});

test('clear resets components and search (lines 121-125)', () => {
    const sidebar = new Wirecloud.ui.ComponentSidebar();
    sidebar.addComponent({ meta: { group_id: 'V/W', type: 'widget' }, id: 'w1' });
    sidebar.clear();
    assert.equal(sidebar.components.widget['V/W'], undefined);
});

test('findComponent returns component by type and id (lines 127-137)', () => {
    const sidebar = new Wirecloud.ui.ComponentSidebar();
    sidebar.addComponent({ meta: { group_id: 'V/W', type: 'widget' }, id: 'w1' });
    assert.ok(sidebar.findComponent('widget', 'w1'));
    assert.equal(sidebar.findComponent('widget', 'nonexistent'), null);
});

test('forEachComponent visits all stored components and is chainable', () => {
    const sidebar = new Wirecloud.ui.ComponentSidebar();
    const mashup = sidebar.addComponent({ meta: { group_id: 'V/M', type: 'mashup' }, id: 'm1' });
    const widget = sidebar.addComponent({ meta: { group_id: 'V/W', type: 'widget' }, id: 'w1' });
    const seen = [];

    const result = sidebar.forEachComponent((component) => { seen.push(component); });

    assert.equal(result, sidebar);
    assert.equal(seen.includes(mashup), true);
    assert.equal(seen.includes(widget), true);
});

test('removeComponent removes from internal state (lines 153-160)', () => {
    const sidebar = new Wirecloud.ui.ComponentSidebar();
    sidebar.addComponent({ meta: { group_id: 'V/W', type: 'widget' }, id: 'w1' });
    sidebar.removeComponent({ meta: { group_id: 'V/W', type: 'widget' }, id: 'w1' });
    assert.ok(!sidebar.components.widget['V/W'].w1);
});

test('search event clears groups (line 92, lines 164-166)', () => {
    const sidebar = new Wirecloud.ui.ComponentSidebar();
    sidebar.groups = { 'V/W': {} };
    sidebar.searchComponents._events.search.forEach((h) => h());
    assert.deepEqual(sidebar.groups, {});
});
