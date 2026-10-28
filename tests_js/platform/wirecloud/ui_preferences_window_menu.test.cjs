const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScript,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');

const installTableHelpers = () => {
    const originalCreateElement = document.createElement.bind(document);
    document.createElement = (tagName) => {
        const element = originalCreateElement(tagName);
        const normalized = String(tagName).toLowerCase();
        if (normalized === 'tbody') {
            element.insertRow = function insertRow() {
                const row = document.createElement('tr');
                this.appendChild(row);
                return row;
            };
        }
        if (normalized === 'tr') {
            element.insertCell = function insertCell() {
                const cell = document.createElement('td');
                this.appendChild(cell);
                return cell;
            };
        }
        return element;
    };
};

const setup = () => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();
    installTableHelpers();

    class Button {
        constructor(options = {}) {
            this.options = options;
            this.wrapperElement = document.createElement('button');
            this.listeners = {};
            this.disabled = false;
            this.destroyed = false;
        }
        addEventListener(type, listener) {
            this.listeners[type] = listener;
        }
        insertInto(parent) {
            parent.appendChild(this.wrapperElement);
            return this;
        }
        setDisabled(disabled) {
            this.disabled = !!disabled;
            return this;
        }
        click(argument) {
            return this.listeners.click?.(argument);
        }
        destroy() {
            this.destroyed = true;
        }
    }

    class Alert {
        constructor(options) {
            this.options = options;
            this.visible = true;
            this.messages = [];
            this.wrapperElement = document.createElement('div');
        }
        insertInto(parent) {
            parent.appendChild(this.wrapperElement);
        }
        hide() {
            this.visible = false;
        }
        show() {
            this.visible = true;
        }
        setMessage(message) {
            this.messages.push(message);
        }
    }

    class Tooltip {
        constructor(options) {
            this.options = options;
            Tooltip.instances.push(this);
        }
        bind(element) {
            element.tooltip = this;
        }
    }
    Tooltip.instances = [];

    class InputInterface {
        constructor(name, options) {
            this.name = name;
            this.options = options;
            this.value = undefined;
            this.disabled = false;
            this.repainted = false;
            this.inputElement = document.createElement('input');
            this.listeners = {};
            InputInterface.instances[name] = this;
        }
        insertInto(parent) {
            parent.appendChild(this.inputElement);
        }
        setValue(value) {
            this.value = value;
        }
        getValue() {
            return this.value;
        }
        setDisabled(disabled) {
            this.disabled = !!disabled;
        }
        addEventListener(type, listener) {
            this.listeners[type] = listener;
        }
        dispatch(type, argument) {
            return this.listeners[type]?.(argument);
        }
        repaint() {
            this.repainted = true;
        }
    }
    InputInterface.instances = {};

    class ValidationErrorManager {
        validate(inputInterface) {
            ValidationErrorManager.validated.push(inputInterface.name);
        }
        toHTML() {
            return ValidationErrorManager.errors;
        }
    }
    ValidationErrorManager.validated = [];
    ValidationErrorManager.errors = [];

    StyledElements.Button = Button;
    StyledElements.Alert = Alert;
    StyledElements.Tooltip = Tooltip;
    StyledElements.ValidationErrorManager = ValidationErrorManager;

    global.Wirecloud = {
        Utils: StyledElements.Utils,
        constants: { LOGGING: { ERROR_MSG: 'error' } },
        ui: {
            WindowMenu: class WindowMenu {
                constructor(title, className) {
                    this.title = title;
                    this.className = className;
                    this.windowContent = document.createElement('div');
                    this.windowBottom = document.createElement('footer');
                    this.msgElement = document.createElement('p');
                    this.windowContent.appendChild(this.msgElement);
                    this.hidden = true;
                    this.destroyed = false;
                    this._closeListener = () => {
                        this.closed = true;
                    };
                }
                setTitle(title) {
                    this.title = title;
                }
                show(parentWindow) {
                    this.parentWindow = parentWindow;
                    this.hidden = false;
                }
                hide() {
                    this.hidden = true;
                }
                destroy() {
                    this.destroyed = true;
                }
            },
            InputInterfaceFactory: {
                createInterface(name, options) {
                    return new InputInterface(name, options);
                },
            },
            MessageWindowMenu: class MessageWindowMenu {
                constructor(error, level) {
                    this.error = error;
                    this.level = level;
                }
                show() {
                    Wirecloud.lastMessage = this;
                }
            },
        },
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/PreferencesWindowMenu.js');
    return { InputInterface, Tooltip, ValidationErrorManager };
};

const makeManager = () => {
    const meta = {
        preferences: {
            color: {
                name: 'color',
                label: 'Color',
                description: 'Theme color',
                options: { type: 'text' },
                hidden: false,
                inheritable: false,
                default: 'blue',
            },
            size: {
                name: 'size',
                label: 'Size',
                description: '   ',
                options: { type: 'number' },
                hidden: false,
                inheritable: true,
                inheritByDefault: true,
                default: 10,
            },
            hidden: {
                name: 'hidden',
                label: 'Hidden',
                options: { type: 'text' },
                hidden: true,
            },
        },
    };
    return {
        meta,
        preferences: {
            color: { value: 'red', inherit: false, meta: meta.preferences.color },
            size: { value: 4, inherit: true, meta: meta.preferences.size },
            hidden: { value: 'secret', inherit: false, meta: meta.preferences.hidden },
        },
        buildTitle() {
            return 'Preferences';
        },
        set(values) {
            this.lastSet = values;
            return this.setResult ?? Promise.resolve();
        },
    };
};

test('PreferencesWindowMenu builds, shows and resets preference interfaces', () => {
    const { InputInterface, Tooltip } = setup();
    const manager = makeManager();
    const menu = new Wirecloud.ui.PreferencesWindowMenu('platform', manager);

    menu.show('parent');
    assert.equal(menu.title, 'Preferences');
    assert.equal(menu.parentWindow, 'parent');
    assert.equal('hidden' in menu.interfaces, false);
    assert.equal(menu.interfaces.color.base.getValue(), 'red');
    assert.equal(menu.interfaces.size.base.getValue(), 4);
    assert.equal(menu.interfaces.size.inherit.getValue(), true);
    assert.equal(menu.interfaces.size.base.disabled, true);
    assert.equal(menu.interfaces.color.base.repainted, true);
    assert.equal(Tooltip.instances[0].options.content, 'Theme color');
    assert.equal(Tooltip.instances.length, 1);

    menu.resetButton.click();
    assert.equal(menu.interfaces.color.base.getValue(), 'blue');
    assert.equal(menu.interfaces.size.base.getValue(), 10);
    assert.equal(menu.interfaces.size.inherit.getValue(), true);
    assert.equal(menu.interfaces.size.base.disabled, true);

    InputInterface.instances['inherit-size'].setValue(false);
    InputInterface.instances['inherit-size'].inputElement.dispatchEvent({ type: 'change' });
    assert.equal(menu.interfaces.size.base.disabled, false);

    menu.setCancelable(false);
    assert.equal(menu.cancelButton.disabled, true);
});

test('PreferencesWindowMenu validates, saves changed preferences and destroys buttons', async () => {
    const { ValidationErrorManager } = setup();
    const manager = makeManager();
    const menu = new Wirecloud.ui.PreferencesWindowMenu('workspace', manager);
    menu.show();

    menu.interfaces.color.base.setValue('green');
    menu.interfaces.size.inherit.setValue(false);
    menu.interfaces.size.base.setValue(8);
    let callbackCalled = false;
    menu.acceptButton.click(() => {
        callbackCalled = true;
    });
    await Promise.resolve();

    assert.deepEqual(ValidationErrorManager.validated, ['color', 'size']);
    assert.deepEqual(manager.lastSet, {
        color: { value: 'green' },
        size: { inherit: false, value: 8 },
    });
    assert.equal(callbackCalled, true);
    assert.equal(menu.hidden, true);
    assert.equal(menu.alertMsg.visible, false);

    menu.cancelButton.click();
    assert.equal(menu.closed, true);
    menu.destroy();
    assert.equal(menu.acceptButton.destroyed, true);
    assert.equal(menu.cancelButton.destroyed, true);
    assert.equal(menu.destroyed, true);
});

test('PreferencesWindowMenu shows validation and persistence errors', async () => {
    const { ValidationErrorManager } = setup();
    const manager = makeManager();
    const menu = new Wirecloud.ui.PreferencesWindowMenu('tab', manager);
    menu.show();

    ValidationErrorManager.errors = ['Invalid value'];
    menu.acceptButton.click();
    assert.equal(menu.alertMsg.visible, true);
    assert.deepEqual(menu.alertMsg.messages, ['Invalid value']);
    assert.equal(manager.lastSet, undefined);

    ValidationErrorManager.errors = [];
    manager.setResult = Promise.reject(new Error('server failed'));
    menu.interfaces.color.base.setValue('purple');
    menu.interfaces.color.base.dispatch('requestSave');
    await Promise.resolve();
    await Promise.resolve();
    assert.equal(Wirecloud.lastMessage.error.message, 'server failed');
    assert.equal(Wirecloud.lastMessage.level, 'error');
});

test('PreferencesWindowMenu only shows preferences supported by the active theme', () => {
    setup();
    const manager = makeManager();
    const scheme = {
        name: 'color-scheme',
        label: 'Color scheme',
        options: { type: 'select', requiredThemeConfig: 'color_schemes' },
        hidden: false,
        inheritable: false,
        default: 'system',
    };
    manager.meta.preferences['color-scheme'] = scheme;
    manager.preferences['color-scheme'] = { value: 'dark', inherit: false, meta: scheme };

    Wirecloud.currentTheme = { config: { color_schemes: ['light'] } };
    let menu = new Wirecloud.ui.PreferencesWindowMenu('platform', manager);
    menu.show('parent');
    assert.equal('color-scheme' in menu.interfaces, false);

    Wirecloud.currentTheme = { config: { color_schemes: ['light', 'dark'] } };
    menu = new Wirecloud.ui.PreferencesWindowMenu('platform', manager);
    menu.show('parent');
    assert.equal(menu.interfaces['color-scheme'].base.getValue(), 'dark');
});
