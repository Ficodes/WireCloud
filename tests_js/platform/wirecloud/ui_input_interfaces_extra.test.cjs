const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScript,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');

const setup = (options = {}) => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();

    global.Option = class Option {
        constructor(label, value) {
            this.label = label;
            this.text = label;
            this.value = value;
        }
    };

    const originalCreateElement = document.createElement.bind(document);
    document.createElement = (tagName) => {
        const element = originalCreateElement(tagName);
        if (String(tagName).toLowerCase() === 'select') {
            element.options = [];
            element.selectedIndex = 0;
            element.add = function (option, before) {
                if (options.throwSelectAddWithSecondArg && arguments.length > 1) {
                    throw new Error('legacy add signature');
                }
                this.options.push(option);
                if (this.value == null) {
                    this.value = option.value;
                }
            };
        }
        return element;
    };

    global.Wirecloud = {
        Utils: StyledElements.Utils,
        ui: {},
        activeWorkspace: {
            contextManager: {
                _concepts: {
                    'weather-temp': {
                        _label: 'Temperature',
                        _description: 'Weather temperature',
                    },
                    location: {
                        _label: 'Location',
                        _description: 'Current location',
                    },
                },
            },
            view: {
                activeTab: {
                    quitEditingInterval() {},
                    setEditingInterval() {},
                },
            },
        },
        UserInterfaceManager: {
            currentWindowMenu: null,
        },
    };

    StyledElements.InputValidationError = {
        NO_ERROR: { code: 'ok' },
        SCREEN_SIZES_ERROR: { code: 'screen-sizes' },
    };

    StyledElements.InputInterface = class InputInterface {
        constructor(fieldId, options = {}) {
            this.fieldId = fieldId;
            this.options = options;
            this.listeners = {};
        }
        addEventListener(type, listener) {
            this.listeners[type] = listener;
        }
        _callEvent(type, callback) {
            if (callback) {
                callback();
            }
            if (this.listeners[type]) {
                this.listeners[type](this);
            }
        }
        setValue(value) {
            this._setValue(value);
            return this;
        }
    };

    class Button {
        constructor(options = {}) {
            this.options = options;
            this.disabled = false;
            this.listeners = {};
            this.wrapperElement = document.createElement('button');
        }
        addEventListener(type, listener) {
            this.listeners[type] = listener;
        }
        setDisabled(disabled) {
            this.disabled = !!disabled;
            return this;
        }
        setLabel(label) {
            this.label = label;
            return this;
        }
        insertInto(parent) {
            parent.appendChild(this.wrapperElement);
            return this;
        }
        click() {
            this.listeners.click(this);
        }
    }

    class Addon extends Button {
        setTitle(title) {
            this.title = title;
            return this;
        }
    }

    class Container {
        constructor(options = {}) {
            this.children = [];
            this.wrapperElement = document.createElement('div');
            this.wrapperElement.className = options.class || '';
        }
        appendChild(child) {
            this.children.push(child);
            return this;
        }
        prependChild(child) {
            this.children.unshift(child);
            return this;
        }
        removeChild(child) {
            this.children = this.children.filter((entry) => entry !== child);
            return this;
        }
        insertInto(parent) {
            parent.appendChild(this.wrapperElement);
            return this;
        }
        repaint() {
            return this;
        }
    }

    class TextField {
        constructor(options = {}) {
            this.value = options.initialValue || '';
            this.listeners = {};
            this.inputElement = document.createElement('input');
            this.inputElement.value = this.value;
        }
        addEventListener(type, listener) {
            this.listeners[type] = listener;
        }
        getValue() {
            return this.value;
        }
        setValue(value) {
            this.value = value;
            this.inputElement.value = value;
            return this;
        }
        setDisabled(disabled) {
            this.disabled = !!disabled;
            return this;
        }
        disable() {
            this.disabled = true;
            return this;
        }
        insertInto(parent) {
            parent.appendChild(this.inputElement);
            return this;
        }
    }

    class NumericField extends TextField {}

    class TextArea extends TextField {
        constructor() {
            super();
            this.inputElement.value = '';
            this.inputElement.selectionStart = 0;
            this.inputElement.selectionEnd = 0;
        }
    }

    class Select {
        constructor(options = {}) {
            this.value = options.initialEntries?.[0]?.value || '';
            this.listeners = {};
        }
        addEventListener(type, listener) {
            this.listeners[type] = listener;
        }
        getValue() {
            return this.value;
        }
        setValue(value) {
            this.value = value;
            if (this.listeners.change) {
                this.listeners.change(this);
            }
            return this;
        }
        setDisabled(disabled) {
            this.disabled = !!disabled;
            return this;
        }
    }

    StyledElements.Button = Button;
    StyledElements.Addon = Addon;
    StyledElements.Container = Container;
    StyledElements.TextField = TextField;
    StyledElements.TextArea = TextArea;
    StyledElements.Select = Select;
    StyledElements.NumericField = NumericField;

    Wirecloud.ui.FormWindowMenu = class FormWindowMenu {
        constructor(fields) {
            this.fields = fields;
            this.values = null;
            Wirecloud.ui.lastFormWindowMenu = this;
        }
        show(parentWindow) {
            this.parentWindow = parentWindow;
            return this;
        }
        setValue(value) {
            this.values = value;
            return this;
        }
    };
    Wirecloud.ui.ParametrizeWindowMenu = class ParametrizeWindowMenu {
        constructor(inputInterface) {
            this.inputInterface = inputInterface;
        }
        show(parentWindow) {
            this.parentWindow = parentWindow;
            return this;
        }
        setValue(value) {
            this.value = value;
            return this;
        }
    };
};

test('ParametrizedTextInputInterface covers parameter selection, escaping, insertion and disabled state', () => {
    setup();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/ParametrizedTextInputInterface.js');

    const input = new Wirecloud.ui.ParametrizedTextInputInterface('field', {
        variable: { value: 'hello %(user.username)' },
    });

    assert.ok(input.parameters.length >= 2);
    assert.equal(input.escapeValue(null), '');
    assert.equal(input.escapeValue(3), '3');
    assert.equal(input.escapeValue(true), 'true');
    assert.equal(input.escapeValue('%(user.username)'), '%%(user.username)');

    input.inputElement.inputElement.value = 'abc';
    input.inputElement.inputElement.selectionStart = 1;
    input.inputElement.inputElement.selectionEnd = 2;
    input.mainSelect.selectedIndex = 0;
    input.mainSelect.value = 'user';
    input.secondSelect.selectedIndex = 0;
    input.secondSelect.value = 'username';
    input.addButton.click();
    assert.equal(input.inputElement.value, 'a%(user.username)c');

    input.resetButton.click();
    assert.equal(input.inputElement.value, 'hello %%(user.username)');

    input.setValue('custom');
    let updated = false;
    input.update = () => {
        updated = true;
    };
    input.setValue('custom-updated');
    assert.equal(updated, true);
    input._setError();
    input.setDisabled(true);
    assert.equal(input.mainSelect.disabled, true);

    const target = document.createElement('div');
    input.insertInto(target);
});

test('ParametrizedTextInputInterface covers legacy select.add fallback', () => {
    setup({ throwSelectAddWithSecondArg: true });
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/ParametrizedTextInputInterface.js');

    const input = new Wirecloud.ui.ParametrizedTextInputInterface('field', {
        variable: { value: 'value' },
    });

    input.mainSelect.selectedIndex = 0;
    input._updateSecondSelect();
    assert.ok(input.secondSelect.options.length > 0);
});

test('ParametrizableValueInputInterface covers sources, statuses and dialog launching', () => {
    setup();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/ParametrizedTextInputInterface.js');
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/ParametrizableValueInputInterface.js');

    const input = new Wirecloud.ui.ParametrizableValueInputInterface('param', {
        parentWindow: { id: 'parent' },
        variable: { value: 'current' },
        canBeHidden: false,
    });

    input.setValue(null);
    assert.deepEqual(input.getValue(), { source: 'current', status: 'normal', value: 'current' });

    input.setValue({ source: 'default', status: 'hidden' });
    assert.deepEqual(input.getValue(), { source: 'default', status: 'readonly' });

    input.setValue({ source: 'custom', status: 'hidden', value: 'manual' });
    assert.deepEqual(input.getValue(), { source: 'custom', status: 'readonly', value: 'manual' });
    assert.equal(input._checkValue({}), StyledElements.InputValidationError.NO_ERROR);

    input.buttonElement.click();
    const target = document.createElement('div');
    input.insertInto(target);

    const hideable = new Wirecloud.ui.ParametrizableValueInputInterface('param2', {
        parentWindow: { id: 'parent' },
        variable: { value: 'current' },
        canBeHidden: true,
    });
    hideable.setValue({ source: 'custom', status: 'hidden', value: 'secret' });
    assert.equal(hideable.visibilityIcon.classList.contains('visible'), false);
});

test('ScreenSizesInputInterface validates, updates ranges and dispatches edit requests', () => {
    setup();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/ScreenSizesInputInterface.js');

    const initial = [
        { id: 1, name: 'Small', moreOrEqual: 0, lessOrEqual: 399 },
        { id: 2, name: 'Large', moreOrEqual: 400, lessOrEqual: -1 },
    ];
    const input = new Wirecloud.ui.ScreenSizesInputInterface('screens', { defaultValue: initial });

    assert.equal(Wirecloud.ui.ScreenSizesInputInterface.stringify(initial), JSON.stringify(initial));
    assert.equal(Wirecloud.ui.ScreenSizesInputInterface.parse(JSON.stringify(initial))[0].name, 'Small');
    assert.equal(input._checkValue(initial), StyledElements.InputValidationError.NO_ERROR);
    assert.equal(input._checkValue([]), StyledElements.InputValidationError.SCREEN_SIZES_ERROR);
    assert.equal(input._checkValue([{ id: 1, moreOrEqual: 2, lessOrEqual: -1 }]), StyledElements.InputValidationError.SCREEN_SIZES_ERROR);
    assert.equal(input._checkValue([{ id: 1, moreOrEqual: 0, lessOrEqual: 20 }]), StyledElements.InputValidationError.SCREEN_SIZES_ERROR);
    assert.deepEqual(input._normalize(initial), initial);

    input.on_valueChange(2, 'moreOrEqual', 500);
    assert.equal(input.getValue()[0].lessOrEqual, 499);
    input.on_valueChange(1, 'lessOrEqual', 300);
    assert.equal(input.getValue()[1].moreOrEqual, 301);

    input.on_addScreenSize();
    assert.equal(input.getValue().length, 3);
    input.on_deleteScreenSize(3);
    assert.equal(input.getValue().length, 2);

    let saved = false;
    let edited = false;
    let editedId = null;
    Wirecloud.activeWorkspace.view.activeTab.setEditingScreenSize = (id) => {
        edited = true;
        editedId = id;
    };
    input.setValue([
        { id: 1, name: 'Small', moreOrEqual: 0, lessOrEqual: 399 },
        { id: 9, name: 'Large', moreOrEqual: 400, lessOrEqual: -1 },
    ]);
    assert.equal(input.highestIdUsed, 9);
    input.addEventListener('requestSave', () => {
        saved = true;
    });
    // Row layout: name, from, to, columns, rows, buttons
    input.screenSizesInputs[1].children[5].children[0].click();
    assert.equal(saved, true);
    assert.equal(edited, true);
    assert.equal(editedId, 1);

    // The columns field defaults to 12 and feeds back into the value
    assert.equal(input.getValue()[0].columns, 12);
    input.screenSizesInputs[1].children[3].children[1].setValue(4);
    input.screenSizesInputs[1].children[3].children[1].listeners.change();
    assert.equal(input.getValue()[0].columns, 4);

    // The optional rows field defaults to the unbounded mode (0)
    assert.equal(input.getValue()[0].rows, 0);
    input.screenSizesInputs[1].children[4].children[1].setValue(6);
    input.screenSizesInputs[1].children[4].children[1].listeners.change();
    assert.equal(input.getValue()[0].rows, 6);

    input.screenSizesInputs[1].children[0].children[1].setValue('Tiny');
    input.screenSizesInputs[1].children[0].children[1].listeners.change();
    assert.equal(input.getValue()[0].name, 'Tiny');
    input.screenSizesInputs[9].children[1].children[1].setValue(450);
    input.screenSizesInputs[9].children[1].children[1].listeners.change();
    assert.equal(input.getValue()[0].lessOrEqual, 449);
    input.screenSizesInputs[1].children[2].children[1].setValue(200);
    input.screenSizesInputs[1].children[2].children[1].listeners.change();
    assert.equal(input.getValue()[1].moreOrEqual, 201);

    input.setValue([
        { id: 1, name: 'Broken', moreOrEqual: 5, lessOrEqual: 20 },
        { id: 2, name: 'Broken 2', moreOrEqual: 21, lessOrEqual: 30 },
    ]);
    assert.equal(input.getValue()[0].moreOrEqual, 0);
    assert.equal(input.getValue()[1].lessOrEqual, -1);

    input.setDisabled(true);
    input.repaint();
    input.setValue(initial);
    input._setError();
    input.insertInto(document.createElement('div'));
});
