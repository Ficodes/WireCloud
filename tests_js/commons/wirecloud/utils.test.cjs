const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScript,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');

const loadWirecloudUtils = () => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();
    global.gettext = (text) => `tr:${text}`;
    global.ngettext = (singular, plural, count) => count === 1 ? `sg:${singular}` : `pl:${plural}`;
    global.Wirecloud = {
        ui: {}
    };
    global.document.cookie = 'session=abc123; theme=dark';
    loadLegacyScript('src/wirecloud/commons/static/js/wirecloud/Utils.js');
};

test('Wirecloud.Utils reuses StyledElements helpers and translation globals', () => {
    loadWirecloudUtils();

    assert.equal(Wirecloud.Utils, StyledElements.Utils);
    assert.equal(Wirecloud.Utils.gettext('hello'), 'tr:hello');
    assert.equal(Wirecloud.Utils.ngettext('file', 'files', 2), 'pl:files');
});

test('Wirecloud.Utils.getCookie returns values or null', () => {
    loadWirecloudUtils();

    assert.equal(Wirecloud.Utils.getCookie('theme'), 'dark');
    assert.equal(Wirecloud.Utils.getCookie('missing'), null);
});
