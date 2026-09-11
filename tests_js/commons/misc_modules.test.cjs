const test = require('node:test');
const assert = require('node:assert/strict');
const {
    loadLegacyScript,
    resetLegacyRuntime,
} = require('../support/legacy-runtime.cjs');

test('StyledElements.DynamicMenuItems supports default and injected builders', () => {
    resetLegacyRuntime();
    global.StyledElements = {};

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/DynamicMenuItems.js');

    const DynamicMenuItems = StyledElements.DynamicMenuItems;
    const customBuild = () => ['x'];
    const custom = new DynamicMenuItems(customBuild);
    const defaults = new DynamicMenuItems();

    assert.equal(custom.build, customBuild);
    assert.deepEqual(defaults.build(), []);
});

test('StyledElements.DefaultInputInterfaceFactory instantiates InputInterfaceFactory', () => {
    resetLegacyRuntime();
    class FakeFactory {}
    global.StyledElements = {
        InputInterfaceFactory: FakeFactory
    };

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/DefaultInputInterfaceFactory.js');

    assert.equal(StyledElements.DefaultInputInterfaceFactory instanceof FakeFactory, true);
});

test('Wirecloud.ui.InputInterfaceFactory registers expected field types', () => {
    resetLegacyRuntime();

    class FakeFactory {
        constructor() {
            this.fieldTypes = {};
        }

        addFieldType(name, value) {
            this.fieldTypes[name] = value;
        }
    }

    class ScreenSizesInputInterface {}
    class ParametrizableValueInputInterface {}
    class ParametrizedTextInputInterface {}
    class MACInputInterface {}

    global.StyledElements = {
        InputInterfaceFactory: FakeFactory
    };
    global.Wirecloud = {
        ui: {
            ScreenSizesInputInterface,
            ParametrizableValueInputInterface,
            ParametrizedTextInputInterface,
            MACInputInterface,
        }
    };

    loadLegacyScript('src/wirecloud/commons/static/js/wirecloud/ui/InputInterfaceFactory.js');

    const factory = Wirecloud.ui.InputInterfaceFactory;
    assert.equal(factory instanceof FakeFactory, true);
    assert.deepEqual(Object.keys(factory.fieldTypes).sort(), [
        'mac',
        'parametrizableValue',
        'parametrizedText',
        'screenSizes',
    ]);
    assert.equal(factory.fieldTypes.screenSizes, ScreenSizesInputInterface);
    assert.equal(factory.fieldTypes.parametrizableValue, ParametrizableValueInputInterface);
    assert.equal(factory.fieldTypes.parametrizedText, ParametrizedTextInputInterface);
    assert.equal(factory.fieldTypes.mac, MACInputInterface);
});

test('Wirecloud.ui.Theme defines readonly fields from descriptor', () => {
    resetLegacyRuntime();
    global.Wirecloud = { ui: {} };

    loadLegacyScript('src/wirecloud/commons/static/js/wirecloud/ui/Theme.js');

    const theme = new Wirecloud.ui.Theme({
        name: 'default',
        label: 'Default Theme',
        templates: { dashboard: 'dashboard.html' },
    });

    assert.equal(theme.name, 'default');
    assert.equal(theme.label, 'Default Theme');
    assert.deepEqual(theme.templates, { dashboard: 'dashboard.html' });
    assert.equal(Object.getOwnPropertyDescriptor(theme, 'name').writable, false);
});

test('Wirecloud.ui.TutorialSubMenu builds menu entries from TutorialCatalogue', () => {
    resetLegacyRuntime();

    class FakeSubMenuItem {
        constructor(label) {
            this.label = label;
            this.appended = [];
            this.menuitem = {
                addIconClass: (value) => {
                    this.iconClass = value;
                }
            };
        }

        append(entry) {
            this.appended.push(entry);
        }
    }

    class FakeMenuItem {
        constructor(label, callback) {
            this.label = label;
            this.callback = callback;
        }
    }

    const firstTutorial = {
        label: 'First',
        start() {
            return 'first';
        }
    };
    const secondTutorial = {
        label: 'Second',
        start() {
            return 'second';
        }
    };

    global.StyledElements = {
        SubMenuItem: FakeSubMenuItem,
        MenuItem: FakeMenuItem,
    };
    global.Wirecloud = {
        Utils: {
            gettext(text) {
                return `tx:${text}`;
            }
        },
        ui: {},
        TutorialCatalogue: {
            tutorials: [firstTutorial, secondTutorial]
        }
    };

    loadLegacyScript('src/wirecloud/commons/static/js/wirecloud/ui/TutorialSubMenu.js');

    const submenu = new Wirecloud.ui.TutorialSubMenu();
    assert.equal(submenu.label, 'tx:Tutorials');
    assert.equal(submenu.iconClass, 'far fa-map');
    assert.deepEqual(submenu.appended.map((entry) => entry.label), ['First', 'Second']);
    assert.equal(submenu.appended[0].callback(), 'first');
    assert.equal(submenu.appended[1].callback(), 'second');
});

test('StyledElements.Separator sets an hr wrapper with separator role', () => {
    resetLegacyRuntime();

    class StyledElement {
        constructor(events) {
            this.events = events;
        }
    }

    global.StyledElements = {
        StyledElement,
        Utils: {}
    };

    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Separator.js');

    const separator = new StyledElements.Separator();
    assert.deepEqual(separator.events, []);
    assert.equal(separator.wrapperElement.tagName, 'HR');
    assert.equal(separator.wrapperElement.getAttribute('role'), 'separator');
});
