const test = require('node:test');
const assert = require('node:assert/strict');
const {
    loadLegacyScript,
    resetLegacyRuntime,
} = require('../../../support/legacy-runtime.cjs');

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
