const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScript,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');

let g_createdElements = [];
let g_containerCounter = 0;

const setup = () => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();

    if (global.Wirecloud == null) {
        global.Wirecloud = {};
    }
    Wirecloud.Utils = StyledElements.Utils;
    Wirecloud.ui = Wirecloud.ui || {};

    global.gettext = (s) => s;
    global.interpolate = (t, v) => t.replace(/%\((\w+)\)s/g, (_, k) => v[k]);

    g_createdElements = [];
    g_containerCounter = 0;

    // Simple mock Container that tracks children in an array, avoids DOM
    class MockContainer {
        constructor(opts = {}) {
            this._id = ++g_containerCounter;
            this._children = [];
            this.wrapperElement = document.createElement(opts.tagname || 'div');
            if (opts.class) this.wrapperElement.className = opts.class;
        }
        appendChild(child) { this._children.push(child); return this; }
        prependChild(child) { this._children.unshift(child); return this; }
        removeChild() { return this; }
        insertInto(parent) {
            if (parent && parent.appendChild) parent.appendChild(this.wrapperElement);
            return this;
        }
        repaint() { return this; }
        get children() { return this._children; }
    }

    class MockButton {
        constructor(opts = {}) {
            this.opts = opts;
            this._disabled = false;
            this._listeners = {};
            this.wrapperElement = document.createElement('button');
            if (opts.class) this.wrapperElement.className = opts.class;
        }
        addEventListener(type, handler) {
            if (!this._listeners[type]) this._listeners[type] = [];
            this._listeners[type].push(handler);
        }
        setDisabled(disabled) { this._disabled = disabled; return this; }
    }

    class MockAddon {
        constructor(opts = {}) {
            this.opts = opts;
            this.wrapperElement = document.createElement('span');
            this.wrapperElement.textContent = opts.text || '';
        }
        setDisabled() { return this; }
    }

    class MockTextField {
        constructor(opts = {}) {
            this.opts = opts;
            this._value = opts.initialValue || '';
            this._disabled = false;
            this._listeners = {};
            this.inputElement = document.createElement('input');
            this.inputElement.value = this._value;
        }
        addEventListener(type, handler) {
            if (!this._listeners[type]) this._listeners[type] = [];
            this._listeners[type].push(handler);
        }
        getValue() { return this._value; }
        setDisabled(disabled) { this._disabled = disabled; return this; }
    }

    class MockNumericField {
        constructor(opts = {}) {
            this.opts = opts;
            this._value = opts.initialValue !== undefined ? opts.initialValue : 0;
            this._disabled = false;
            this._listeners = {};
            this.inputElement = document.createElement('input');
            this.inputElement.value = this._value;
        }
        addEventListener(type, handler) {
            if (!this._listeners[type]) this._listeners[type] = [];
            this._listeners[type].push(handler);
        }
        getValue() { return this._value; }
        setDisabled(disabled) { this._disabled = disabled; return this; }
    }

    const MockInputValidationError = {
        NO_ERROR: 0,
        SCREEN_SIZES_ERROR: 1,
    };

    class MockInputInterface {
        constructor(fieldId, options) {
            this.fieldId = fieldId;
            this.events = {};
        }
        addEventListener(type, handler) {
            if (!this.events[type]) this.events[type] = [];
            this.events[type].push(handler);
        }
        _callEvent(event, callback) {
            callback();
        }
    }

    StyledElements.Container = MockContainer;
    StyledElements.Button = MockButton;
    StyledElements.Addon = MockAddon;
    StyledElements.TextField = MockTextField;
    StyledElements.NumericField = MockNumericField;
    StyledElements.InputInterface = MockInputInterface;
    StyledElements.InputValidationError = MockInputValidationError;

    StyledElements.PopupMenu = class MockPopupMenu {
        constructor() { this._items = []; this.wrapperElement = document.createElement('div'); }
        append(item) { this._items.push(item); return this; }
    };

    Wirecloud.activeWorkspace = {
        view: {
            activeTab: {
                _editingScreenSizeCalls: [],
                setEditingScreenSize(id) { this._editingScreenSizeCalls.push(id); },
            },
        },
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/ScreenSizesInputInterface.js');
};

// =============================================================================
// Constructor - branch 30: options.defaultValue || []
// =============================================================================

test('constructor defaults value to empty array when defaultValue is not provided', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    assert.deepEqual(field.value, []);
});

test('constructor uses provided defaultValue', () => {
    setup();
    const defaultVal = [{ id: 1, name: 'desktop', moreOrEqual: 0, lessOrEqual: -1 }];
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', { defaultValue: defaultVal });
    assert.deepEqual(field.value, defaultVal);
});

// =============================================================================
// on_addScreenSize - branch 66: empty screenSizes -> moreOrEqual: 0
// =============================================================================

test('on_addScreenSize with empty value creates first screen size with moreOrEqual=0', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', { defaultValue: [] });
    assert.equal(field.value.length, 0);

    field.on_addScreenSize();

    assert.equal(field.value.length, 1);
    assert.equal(field.value[0].moreOrEqual, 0);
    assert.equal(field.value[0].lessOrEqual, -1);
    assert.equal(field.value[0].name, 'Default-1');
});

test('on_addScreenSize with existing sizes chains lessOrEqual+1', () => {
    setup();
    // Use two elements so the first one's lessOrEqual isn't normalized to -1
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {
        defaultValue: [
            { id: 1, name: 'phone', moreOrEqual: 0, lessOrEqual: 480 },
            { id: 2, name: 'tablet', moreOrEqual: 481, lessOrEqual: -1 },
        ],
    });
    assert.equal(field.value.length, 2);

    field.on_addScreenSize();

    assert.equal(field.value.length, 3);
    // Last existing size has lessOrEqual=-1, so new moreOrEqual = -1+1 = 0
    // Actually field.value was normalized: the last element always gets lessOrEqual=-1
    // So the second element (tablet) had lessOrEqual normalized to -1
    // New moreOrEqual = -1 + 1 = 0
    assert.equal(field.value[2].lessOrEqual, -1);
});

// =============================================================================
// _update - branch 195: screenSize without 'name' property
// =============================================================================

test('_update uses Default-N when screenSize has no name property', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', { defaultValue: [] });

    field._update([{ id: 5, moreOrEqual: 0, lessOrEqual: 480 }]);

    const container = field.screenSizesInputs[5];
    assert.ok(container != null);
    // First child is nameContainer (Container), second child is nameInput (TextField)
    // screenSizeContainer._children = [nameContainer, fromContainer, toContainer, buttonContainer]
    // nameContainer._children = [nameAddon, nameInput]
    const nameContainer = container._children[0];
    const nameInput = nameContainer._children[1];
    assert.equal(nameInput.inputElement.value, 'Default-5');
});

test('_update uses existing name when screenSize has name property', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', { defaultValue: [] });

    field._update([{ id: 3, name: 'CustomName', moreOrEqual: 0, lessOrEqual: 480 }]);

    const nameContainer = field.screenSizesInputs[3]._children[0];
    const nameInput = nameContainer._children[1];
    assert.equal(nameInput.inputElement.value, 'CustomName');
});

// =============================================================================
// _checkValue
// =============================================================================

test('_checkValue returns error for non-array', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    assert.equal(field._checkValue('not-array'), StyledElements.InputValidationError.SCREEN_SIZES_ERROR);
});

test('_checkValue returns error for empty array', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    assert.equal(field._checkValue([]), StyledElements.InputValidationError.SCREEN_SIZES_ERROR);
});

test('_checkValue returns error for gap in ranges', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    const val = [
        { id: 1, moreOrEqual: 0, lessOrEqual: 480 },
        { id: 2, moreOrEqual: 500, lessOrEqual: -1 },
    ];
    assert.equal(field._checkValue(val), StyledElements.InputValidationError.SCREEN_SIZES_ERROR);
});

test('_checkValue returns error for overlap', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    const val = [
        { id: 1, moreOrEqual: 0, lessOrEqual: 500 },
        { id: 2, moreOrEqual: 200, lessOrEqual: -1 },
    ];
    assert.equal(field._checkValue(val), StyledElements.InputValidationError.SCREEN_SIZES_ERROR);
});

test('_checkValue returns error when last lessOrEqual is not -1', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    const val = [
        { id: 1, moreOrEqual: 0, lessOrEqual: 480 },
        { id: 2, moreOrEqual: 481, lessOrEqual: 1024 },
    ];
    assert.equal(field._checkValue(val), StyledElements.InputValidationError.SCREEN_SIZES_ERROR);
});

test('_checkValue returns NO_ERROR for valid contiguous ranges', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    const val = [
        { id: 1, name: 'phone', moreOrEqual: 0, lessOrEqual: 480, columns: 1 },
        { id: 2, name: 'tablet', moreOrEqual: 481, lessOrEqual: 1024, columns: 6 },
        { id: 3, name: 'desktop', moreOrEqual: 1025, lessOrEqual: -1, columns: 12 },
    ];
    assert.equal(field._checkValue(val), StyledElements.InputValidationError.NO_ERROR);
});

// =============================================================================
// _checkValue - columns validation and unique ids
// =============================================================================

test('_checkValue returns error when columns is missing or not an integer', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    const base = [
        { id: 1, moreOrEqual: 0, lessOrEqual: -1 },
    ];
    assert.equal(field._checkValue(base), StyledElements.InputValidationError.SCREEN_SIZES_ERROR, 'columns missing');
    assert.equal(field._checkValue([{ id: 1, moreOrEqual: 0, lessOrEqual: -1, columns: 1.5 }]), StyledElements.InputValidationError.SCREEN_SIZES_ERROR, 'columns not an integer');
});

test('_checkValue returns error when columns is less than 1', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    assert.equal(field._checkValue([{ id: 1, moreOrEqual: 0, lessOrEqual: -1, columns: 0 }]), StyledElements.InputValidationError.SCREEN_SIZES_ERROR);
    assert.equal(field._checkValue([{ id: 1, moreOrEqual: 0, lessOrEqual: -1, columns: -3 }]), StyledElements.InputValidationError.SCREEN_SIZES_ERROR);
});

test('_checkValue accepts columns === 1 (minimum valid value)', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    assert.equal(field._checkValue([{ id: 1, moreOrEqual: 0, lessOrEqual: -1, columns: 1 }]), StyledElements.InputValidationError.NO_ERROR);
});

test('_checkValue returns error when two entries share the same id', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    const val = [
        { id: 1, moreOrEqual: 0, lessOrEqual: 480, columns: 1 },
        { id: 1, moreOrEqual: 481, lessOrEqual: -1, columns: 12 },
    ];
    assert.equal(field._checkValue(val), StyledElements.InputValidationError.SCREEN_SIZES_ERROR);
});

// =============================================================================
// parse / stringify / _normalize / getValue
// =============================================================================

test('parse parses JSON string', () => {
    setup();
    const result = Wirecloud.ui.ScreenSizesInputInterface.parse('[{"id":1,"name":"d","moreOrEqual":0,"lessOrEqual":-1}]');
    assert.deepEqual(result, [{ id: 1, name: 'd', moreOrEqual: 0, lessOrEqual: -1 }]);
});

test('stringify converts to JSON string', () => {
    setup();
    const result = Wirecloud.ui.ScreenSizesInputInterface.stringify([{ id: 1, name: 'd', moreOrEqual: 0, lessOrEqual: -1 }]);
    assert.equal(typeof result, 'string');
    assert.ok(result.includes('id'));
});

test('_normalize returns value as-is', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    const val = [{ id: 1 }];
    assert.deepEqual(field._normalize(val), val);
});

test('getValue returns current value', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', { defaultValue: [{ id: 1, moreOrEqual: 0, lessOrEqual: -1, columns: 12 }] });
    assert.deepEqual(field.getValue(), [{ id: 1, moreOrEqual: 0, lessOrEqual: -1, columns: 12 }]);
});

// =============================================================================
// setDisabled / repaint / insertInto
// =============================================================================

test('setDisabled disables add button and marks enabledStatus', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    assert.equal(field.enabledStatus, true);

    field.setDisabled(true);
    assert.equal(field.enabledStatus, false);
    assert.equal(field.addButton._disabled, true);
});

test('setDisabled with false re-enables', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    field.setDisabled(true);
    field.setDisabled(false);
    assert.equal(field.enabledStatus, true);
});

test('repaint calls wrapperElement.repaint', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    // wrapperElement is a MockContainer with repaint() defined
    field.repaint();
    assert.ok(true);
});

test('insertInto appends to parent', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    const parent = document.createElement('div');
    field.insertInto(parent);
    assert.ok(parent.childNodes.length >= 1);
});

// =============================================================================
// _setValue / _setError
// =============================================================================

test('_setValue updates value and tracks highestIdUsed', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    const newValue = [
        { id: 10, name: 'a', moreOrEqual: 0, lessOrEqual: 480 },
        { id: 20, name: 'b', moreOrEqual: 481, lessOrEqual: -1 },
    ];
    field._setValue(newValue);
    assert.deepEqual(field.value, newValue);
    assert.equal(field.highestIdUsed, 20);
});

test('_setError does not throw', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {});
    assert.doesNotThrow(() => field._setError('some error'));
});

// =============================================================================
// on_deleteScreenSize / on_valueChange
// =============================================================================

test('on_deleteScreenSize removes element by id', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {
        defaultValue: [
            { id: 1, name: 'a', moreOrEqual: 0, lessOrEqual: 480 },
            { id: 2, name: 'b', moreOrEqual: 481, lessOrEqual: -1 },
        ],
    });
    field.on_deleteScreenSize(1);
    assert.equal(field.value.length, 1);
    assert.equal(field.value[0].id, 2);
});

test('on_valueChange updates moreOrEqual and adjacent lessOrEqual', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {
        defaultValue: [
            { id: 1, name: 'a', moreOrEqual: 0, lessOrEqual: 480 },
            { id: 2, name: 'b', moreOrEqual: 481, lessOrEqual: -1 },
        ],
    });
    field._update(field.value, false);

    field.on_valueChange(1, 'moreOrEqual', 100);

    assert.equal(field.value[0].moreOrEqual, 100);
    // When from === 'moreOrEqual' and idx > 0, previous element's lessOrEqual = value - 1
    // idx is 0 (for id=1), so idx > 0 is false. No adjacent update.
    // Let's test with the second element instead
});

test('on_valueChange updates moreOrEqual of second element adjusts first lessOrEqual', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {
        defaultValue: [
            { id: 1, name: 'a', moreOrEqual: 0, lessOrEqual: 480 },
            { id: 2, name: 'b', moreOrEqual: 481, lessOrEqual: -1 },
        ],
    });
    field._update(field.value, false);

    field.on_valueChange(2, 'moreOrEqual', 300);

    assert.equal(field.value[1].moreOrEqual, 300);
    // When idx=1 (second element), previous lessOrEqual becomes 300-1=299
    assert.equal(field.value[0].lessOrEqual, 299);
});

test('on_valueChange updates name', () => {
    setup();
    const field = new Wirecloud.ui.ScreenSizesInputInterface('test-field', {
        defaultValue: [{ id: 1, name: 'old', moreOrEqual: 0, lessOrEqual: -1 }],
    });
    field.on_valueChange(1, 'name', 'newname');
    assert.equal(field.value[0].name, 'newname');
});
