const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const webpack = require('webpack');
const {resetLegacyRuntime, loadLegacyScripts} = require('../support/legacy-runtime.cjs');

const repoRoot = path.resolve(__dirname, '../..');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'wirecloud-oauth-bundle-'));
const settingsPath = path.join(temporary, 'settings.json');
const installedApps = ['commons', 'platform', 'catalogue', 'fiware', 'keycloak', 'oauth2provider'].map((name) => ({
    name, module: `wirecloud.${name}`, path: path.join(repoRoot, 'src/wirecloud', name)
}));
fs.writeFileSync(settingsPath, JSON.stringify({installedApps}));
process.env.WEBPACK_SETTINGS_JSON = settingsPath;
require('ts-node').register({project: path.join(repoRoot, 'src/wirecloud/webpack/webpack-tsconfig.json')});
const {getOrderedScriptsEntries} = require('../../src/wirecloud/webpack/entries.ts');
const configuration = require('../../src/wirecloud/webpack/webpack.js.ts').default;
const oauthPlugin = require('../../src/wirecloud/oauth2provider/plugin.ts').default;

test.after(() => fs.rmSync(temporary, {recursive: true, force: true}));

test('OAuth enhancer is contributed only to the dedicated OAuth view', () => {
    for (const view of ['classic', 'smartphone', 'embedded', 'widget', 'operator', 'bootstrap']) {
        assert.deepEqual(oauthPlugin.get_scripts(view), []);
    }
    const entries = getOrderedScriptsEntries();
    for (const theme of ['defaulttheme', 'fiwaretheme']) {
        const files = entries[`main-${theme}-oauth2`].import;
        assert.equal(files.length, 12);
        assert.match(files[0], /StyledElements[/\\]Utils\.js$/);
        assert.match(files.at(-1), /oauth2provider[/\\]pages\.js$/);
        assert.ok(files.slice(0, -1).every((file) => file.includes('StyledElements')));
    }
});

test('Built OAuth bundles run StyledElements without eval, inline scripts, or platform bootstrap', async () => {
    assert.equal(configuration.devtool, process.env.NODE_ENV === 'production' ? false : 'source-map');
    const entries = getOrderedScriptsEntries();
    const compiler = webpack({
        ...configuration,
        entry: Object.fromEntries(Object.entries(entries).filter(([name]) => name.endsWith('-oauth2'))),
        output: {...configuration.output, path: path.join(temporary, 'dist')},
        // These entries contain no Monaco, CSS, or other plugin-managed assets.
        plugins: [],
    });
    try {
        const stats = await new Promise((resolve, reject) => compiler.run((error, result) => error ? reject(error) : resolve(result)));
        assert.equal(stats.hasErrors(), false, stats.toString({all: false, errors: true}));
        for (const theme of ['defaulttheme', 'fiwaretheme']) {
            resetLegacyRuntime();
            document.readyState = 'loading';
            const bundle = path.join(temporary, 'dist/js', `main-${theme}-oauth2.js`);
            assert.doesNotMatch(fs.readFileSync(bundle, 'utf8'), /\beval\s*\(|new Function\s*\(/);
            loadLegacyScripts([bundle]);
            assert.equal(typeof StyledElements.OAuthPages.enhance, 'function');
            assert.equal(global.Wirecloud, undefined);

            const root = document.createElement('main');
            const message = document.createElement('p');
            message.setAttribute('data-se-alert', 'info');
            message.appendChild(document.createTextNode('Signed in as test user'));
            root.appendChild(message);
            root.querySelectorAll = (selector) => selector === '[data-se-alert]' ? [message] : [];
            StyledElements.OAuthPages.enhance(root);
            assert.ok(root.firstChild.classList.contains('alert-info'));
            assert.equal(root.firstChild.textContent, 'Signed in as test user');
        }
    } finally {
        await new Promise((resolve, reject) => compiler.close((error) => error ? reject(error) : resolve()));
    }
});
