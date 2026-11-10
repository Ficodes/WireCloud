const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScript,
    loadLegacyScripts,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');

const setup = () => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();
    global.Wirecloud = {
        ui: {},
        Utils: StyledElements.Utils,
        constants: {},
    };
};

const loadMenuItem = () => {
    loadLegacyScripts([
        'src/wirecloud/commons/static/js/StyledElements/Event.js',
        'src/wirecloud/commons/static/js/StyledElements/MenuItem.js',
        'src/wirecloud/commons/static/js/StyledElements/DynamicMenuItems.js',
    ]);
};

const keyEvent = (key, options = {}) => ({
    key,
    altKey: false,
    ctrlKey: false,
    metaKey: false,
    shiftKey: false,
    defaultPrevented: false,
    target: document.body,
    ...options,
});

// =============================================================================
// Wirecloud.ui.registry
// =============================================================================

test('registry falls back to the platform classes', () => {
    setup();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/Registry.js');

    class Header {}
    class Component {}
    Wirecloud.ui.WirecloudHeader = Header;
    Wirecloud.ui.WiringEditor = {Component};

    assert.equal(Wirecloud.ui.registry.get('WirecloudHeader'), Header);
    assert.equal(Wirecloud.ui.registry.get('WiringEditor.Component'), Component);
    assert.equal(Wirecloud.ui.registry.get('Missing'), undefined);
    assert.equal(Wirecloud.ui.registry.get('Missing', Header), Header);
    assert.equal(Wirecloud.ui.registry.has('WirecloudHeader'), false);
});

test('registry returns registered replacements and can create instances', () => {
    setup();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/Registry.js');

    class Header {}
    class ThemeHeader extends Header {
        constructor(arg) {
            super();
            this.arg = arg;
        }
    }
    Wirecloud.ui.WirecloudHeader = Header;

    Wirecloud.ui.registry.register('WirecloudHeader', ThemeHeader);
    assert.equal(Wirecloud.ui.registry.has('WirecloudHeader'), true);
    assert.equal(Wirecloud.ui.registry.get('WirecloudHeader', Header), ThemeHeader);

    const instance = Wirecloud.ui.registry.create('WirecloudHeader', 5);
    assert.ok(instance instanceof ThemeHeader);
    assert.equal(instance.arg, 5);

    Wirecloud.ui.registry.unregister('WirecloudHeader');
    assert.equal(Wirecloud.ui.registry.get('WirecloudHeader'), Header);
});

test('registry validates its arguments', () => {
    setup();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/Registry.js');

    assert.throws(() => Wirecloud.ui.registry.register('', class {}), TypeError);
    assert.throws(() => Wirecloud.ui.registry.register('Name', null), TypeError);
    assert.throws(() => Wirecloud.ui.registry.create('Unknown'), TypeError);
});

// =============================================================================
// Wirecloud.commands
// =============================================================================

const loadCommands = () => {
    loadMenuItem();
    loadLegacyScripts([
        'src/wirecloud/platform/static/js/wirecloud/ui/Registry.js',
        'src/wirecloud/platform/static/js/wirecloud/Commands.js',
    ]);
};

test('commands are grouped, filtered and ranked', () => {
    setup();
    loadCommands();

    const commands = Wirecloud.commands;
    commands.register({id: 'a', label: 'Open wiring', group: 'navigation', run: () => 'a'});
    commands.register({id: 'b', label: 'New workspace', group: 'commands', run: () => 'b'});
    commands.register({id: 'c', label: 'Hidden', when: () => false, run: () => 'c'});
    commands.register({id: 'd', label: 'Throws', when: () => { throw new Error(); }, run: () => 'd'});
    commands.registerProvider('ws', () => [
        {id: 'ws.1', group: 'workspaces', label: 'admin / Lab', description: 'Sensores de Laboratorio', run: () => 'ws'},
    ]);
    commands.registerProvider('broken', () => { throw new Error('boom'); });
    commands.registerProvider('resources', () => [
        {id: 'r.1', group: 'resources', label: 'Map viewer', requiresQuery: true, run: () => 'r'},
    ]);

    assert.deepEqual(commands.list('').map((command) => command.id), ['ws.1', 'b', 'a']);
    assert.deepEqual(commands.list('laboratorio').map((command) => command.id), ['ws.1']);
    assert.deepEqual(commands.list('map').map((command) => command.id), ['r.1']);
    assert.deepEqual(commands.list('', {groups: ['navigation']}).map((command) => command.id), ['a']);

    // Better matches are listed first inside each group
    commands.register({id: 'e', label: 'Remove workspace', group: 'commands', run: () => 'e'});
    assert.deepEqual(commands.list('workspace').map((command) => command.id), ['b', 'e']);
    commands.register({id: 'f', label: 'Workspace settings', group: 'commands', run: () => 'f'});
    assert.deepEqual(commands.list('workspace').map((command) => command.id), ['f', 'b', 'e']);

    commands.unregister('f');
    commands.unregisterProvider('resources');
    assert.equal(commands.get('f'), null);
    assert.equal(commands.list('map').length, 0);
});

test('commands run only when available and enabled', () => {
    setup();
    loadCommands();

    const commands = Wirecloud.commands;
    let enabled = false;
    commands.register({id: 'x', label: 'X', enabled: () => enabled, run: () => 'ran'});
    commands.register({id: 'y', label: 'Y', when: () => false, run: () => 'ran'});

    assert.equal(commands.get('x').enabled, false);
    assert.equal(commands.run('x'), undefined);
    enabled = true;
    assert.equal(commands.run('x'), 'ran');
    assert.equal(commands.run('y'), undefined);
    assert.equal(commands.run('missing'), undefined);

    assert.throws(() => commands.register({label: 'No id', run: () => {}}), TypeError);
    assert.throws(() => commands.register({id: 'z', label: 'No run'}), TypeError);
    assert.throws(() => commands.registerProvider('p', null), TypeError);
});

test('commands can be built from menu item builders', () => {
    setup();
    loadCommands();

    const calls = [];
    const builder = new StyledElements.DynamicMenuItems(function () {
        const rename = new StyledElements.MenuItem('Rename', function (menuContext, itemContext) {
            calls.push(['rename', itemContext]);
        }, 'ctx');
        rename.addIconClass('fas fa-pencil-alt');
        rename.commandId = 'rename';
        rename.commandLabel = 'Rename workspace';

        const remove = new StyledElements.MenuItem('Remove', () => calls.push(['remove']));
        remove.danger = true;
        remove.disable();

        return [rename, remove, new StyledElements.DynamicMenuItems()];
    });

    const result = Wirecloud.commands.fromMenuItems(builder, {group: 'commands', idPrefix: 'workspace.'});
    assert.equal(result.length, 2);
    assert.equal(result[0].id, 'workspace.rename');
    assert.equal(result[0].label, 'Rename workspace');
    assert.equal(result[0].icon, 'fas fa-pencil-alt');
    assert.equal(result[0].enabled, true);
    assert.equal(result[1].id, 'workspace.remove');
    assert.equal(result[1].danger, true);
    assert.equal(result[1].enabled, false);

    result[0].run();
    assert.deepEqual(calls, [['rename', 'ctx']]);
});

test('commands open the palette registered by the theme', () => {
    setup();
    loadCommands();

    assert.equal(Wirecloud.commands.openPalette(), false);
    assert.equal(Wirecloud.commands.isPaletteOpen(), false);

    const shown = [];
    class Palette {
        constructor(registry) {
            this.registry = registry;
            this.visible = false;
        }
        show(options) {
            this.visible = true;
            shown.push(options);
        }
        hide() {
            this.visible = false;
        }
        isVisible() {
            return this.visible;
        }
    }
    Wirecloud.ui.registry.register('CommandPalette', Palette);

    assert.equal(Wirecloud.commands.openPalette({groups: ['workspaces']}), true);
    assert.deepEqual(shown, [{groups: ['workspaces']}]);
    assert.equal(Wirecloud.commands.isPaletteOpen(), true);
    Wirecloud.commands.closePalette();
    assert.equal(Wirecloud.commands.isPaletteOpen(), false);
});

// =============================================================================
// Wirecloud.ui.shortcuts
// =============================================================================

test('shortcuts are ignored until enabled', () => {
    setup();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/ShortcutManager.js');

    let calls = 0;
    const shortcuts = new Wirecloud.ui.ShortcutManager();
    shortcuts.register({id: 'edit', keys: 'e', run: () => { calls += 1; }});

    assert.equal(shortcuts.handle(keyEvent('e')), false);
    shortcuts.enabled = true;
    assert.equal(shortcuts.handle(keyEvent('e')), true);
    assert.equal(calls, 1);
    assert.equal(shortcuts.handle(keyEvent('E', {shiftKey: true})), true);
    assert.equal(calls, 2);
});

test('shortcuts match modifiers, inputs and modals', () => {
    setup();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/ShortcutManager.js');

    const calls = [];
    const shortcuts = new Wirecloud.ui.ShortcutManager();
    shortcuts.enabled = true;
    shortcuts.register({id: 'palette', keys: 'mod+k', allowInInputs: true, run: () => calls.push('palette')});
    shortcuts.register({id: 'edit', keys: 'e', run: () => calls.push('edit')});
    shortcuts.register({id: 'delete', keys: ['Delete', 'Backspace'], run: () => false});
    shortcuts.register({id: 'cond', keys: 'w', when: () => false, run: () => calls.push('cond')});
    shortcuts.register({id: 'modal', keys: 'Escape', allowInModals: true, run: () => calls.push('modal')});

    const input = document.createElement('input');

    assert.equal(shortcuts.handle(keyEvent('k', {metaKey: true})), true);
    assert.equal(shortcuts.handle(keyEvent('k', {ctrlKey: true, target: input})), true);
    assert.equal(shortcuts.handle(keyEvent('k')), false);
    assert.equal(shortcuts.handle(keyEvent('e', {ctrlKey: true})), false);
    assert.equal(shortcuts.handle(keyEvent('e', {target: input})), false);
    assert.equal(shortcuts.handle(keyEvent('e'), {modal: true}), false);
    assert.equal(shortcuts.handle(keyEvent('Escape'), {modal: true}), true);
    assert.equal(shortcuts.handle(keyEvent('Delete')), false);
    assert.equal(shortcuts.handle(keyEvent('w')), false);
    assert.equal(shortcuts.handle(keyEvent('e', {defaultPrevented: true})), false);
    assert.deepEqual(calls, ['palette', 'palette', 'modal']);

    assert.equal(shortcuts.list().length, 5);
    shortcuts.unregister('edit');
    assert.equal(shortcuts.get('edit'), null);

    assert.throws(() => shortcuts.register({id: 'x', keys: [], run: () => {}}), TypeError);
    assert.throws(() => shortcuts.register({keys: 'x', run: () => {}}), TypeError);
});

// =============================================================================
// Wirecloud.ui.ColorScheme
// =============================================================================

const loadColorScheme = ({preference = 'system', schemes = ['light', 'dark'], systemDark = false, anonymous = false} = {}) => {
    setup();
    const listeners = [];
    global.window.matchMedia = () => ({
        matches: systemDark,
        addEventListener: (type, listener) => listeners.push(listener),
    });
    const storage = {};
    global.window.localStorage = {
        getItem: (key) => (key in storage ? storage[key] : null),
        setItem: (key, value) => { storage[key] = String(value); },
    };
    const saved = [];
    Wirecloud.currentTheme = {config: {color_schemes: schemes}};
    Wirecloud.contextManager = {get: (key) => (key === 'isanonymous' ? anonymous : null)};
    Wirecloud.preferences = new StyledElements.ObjectWithEvents(['post-commit']);
    Wirecloud.preferences.get = () => preference;
    Wirecloud.preferences.set = (values) => {
        saved.push(values);
        return Promise.resolve();
    };
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/ColorScheme.js');
    return {listeners, storage, saved, setSystem: (dark) => { systemDark = dark; }};
};

test('color scheme follows the preference and the system setting', () => {
    const env = loadColorScheme({systemDark: true});
    const colorScheme = Wirecloud.ui.ColorScheme;

    colorScheme.init();
    assert.equal(document.documentElement.getAttribute('data-wc-color-scheme'), 'dark');
    assert.equal(env.storage['wirecloud.color-scheme'], 'system');

    env.setSystem(false);
    global.window.matchMedia = () => ({matches: false, addEventListener: () => {}});
    env.listeners.forEach((listener) => listener());
    assert.equal(document.documentElement.getAttribute('data-wc-color-scheme'), 'light');
});

test('color scheme falls back to the schemes supported by the theme', () => {
    loadColorScheme({preference: 'dark', schemes: ['light']});
    assert.equal(Wirecloud.ui.ColorScheme.resolve(), 'light');

    Wirecloud.currentTheme = {config: {}};
    assert.deepEqual(Wirecloud.ui.ColorScheme.supported, ['light']);
    Wirecloud.preferences.get = () => 'invalid';
    assert.equal(Wirecloud.ui.ColorScheme.preference, 'system');
});

test('color scheme toggle stores the preference and propagates to widgets', async () => {
    const env = loadColorScheme({preference: 'light'});
    const colorScheme = Wirecloud.ui.ColorScheme;
    colorScheme.init();

    const changes = [];
    colorScheme.addEventListener('change', (manager, scheme) => changes.push(scheme));

    const iframeRoot = document.createElement('html');
    const iframe = document.createElement('iframe');
    iframe.contentDocument = {documentElement: iframeRoot};
    const shadowWidget = document.createElement('wirecloud-widget');
    colorScheme.applyTo(iframe);
    colorScheme.applyTo(shadowWidget);
    assert.equal(iframeRoot.getAttribute('data-wc-color-scheme'), 'light');
    assert.equal(shadowWidget.getAttribute('data-wc-color-scheme'), 'light');

    await colorScheme.toggle();
    assert.equal(document.documentElement.getAttribute('data-wc-color-scheme'), 'dark');
    assert.equal(env.storage['wirecloud.color-scheme'], 'dark');
    assert.deepEqual(env.saved, [{'color-scheme': {value: 'dark'}}]);
    assert.deepEqual(changes, ['dark']);

    // Once the preference is stored, the stored value is used again
    Wirecloud.preferences.get = () => 'dark';
    Wirecloud.preferences.dispatchEvent('post-commit', {'color-scheme': 'dark'});
    assert.equal(colorScheme.preference, 'dark');

    await assert.rejects(colorScheme.setPreference('blue'), TypeError);
});

test('color scheme keeps anonymous preferences in the browser', async () => {
    const env = loadColorScheme({anonymous: true});
    const colorScheme = Wirecloud.ui.ColorScheme;
    colorScheme.init();

    await colorScheme.setPreference('dark');
    assert.equal(env.saved.length, 0);
    assert.equal(env.storage['wirecloud.color-scheme-preference'], 'dark');
    colorScheme._override = null;
    assert.equal(colorScheme.preference, 'dark');
});

// =============================================================================
// Root state attributes (Wirecloud.UserInterfaceManager)
// =============================================================================

test('UserInterfaceManager exposes the platform state on the root element', () => {
    setup();
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/UserInterfaceManager.js');
    const uim = Wirecloud.UserInterfaceManager;

    uim.setRootState('theme', 'industrytheme');
    assert.equal(document.documentElement.getAttribute('data-wc-theme'), 'industrytheme');
    assert.equal(uim.getRootState('theme'), 'industrytheme');
    uim.setRootState('theme', null);
    assert.equal(document.documentElement.getAttribute('data-wc-theme'), null);

    uim.updateModeState({view_name: 'workspace', editing: false});
    assert.equal(uim.getRootState('mode'), 'view');
    uim.updateModeState({view_name: 'workspace', editing: true});
    assert.equal(uim.getRootState('mode'), 'edit');
    uim.updateModeState({view_name: 'wiring'});
    assert.equal(uim.getRootState('mode'), 'wiring');
    uim.updateModeState({view_name: 'myresources'});
    assert.equal(uim.getRootState('mode'), 'catalogue');
    uim.updateModeState({view_name: 'marketplace'});
    assert.equal(uim.getRootState('mode'), 'marketplace');
    assert.equal(uim.hasPopups(), false);
});

// =============================================================================
// Platform commands and shortcuts (PlatformCommands.js)
// =============================================================================

const loadPlatformCommands = ({editing = false, anonymous = false} = {}) => {
    setup();
    loadMenuItem();
    loadLegacyScripts([
        'src/wirecloud/platform/static/js/wirecloud/ui/Registry.js',
        'src/wirecloud/platform/static/js/wirecloud/Commands.js',
        'src/wirecloud/platform/static/js/wirecloud/ui/ShortcutManager.js',
    ]);

    const calls = [];
    const workspace = {id: 'w1', owner: 'admin', name: 'lab', title: 'Lab', public: false, description: 'Sensors'};
    const other = {id: 'w2', owner: 'wirecloud', name: 'home', title: 'home', public: true, description: ''};
    Wirecloud.workspacesByUserAndName = {admin: {lab: workspace}, wirecloud: {home: other}};
    Wirecloud.activeWorkspace = {id: 'w1', wiring: {createOperator: (meta) => { calls.push(['operator', meta.uri]); return Promise.resolve(); }}};
    Wirecloud.contextManager = {get: (key) => ({isanonymous: anonymous, username: anonymous ? 'anonymous' : 'admin'})[key]};
    Wirecloud.changeActiveWorkspace = (target) => { calls.push(['switch', target.id]); return 'task'; };

    const modes = [];
    const workspaceView = {
        view_name: 'workspace',
        model: {isAllowed: () => true},
        editing: editing,
        selectedWidget: null,
        activeTab: {createWidget: (meta) => calls.push(['widget', meta.uri])},
        setEditing: (value) => calls.push(['editing', value]),
        getModes: () => [
            {id: 'view', label: 'View', icon: 'fas fa-eye', shortcut: 'v', active: !editing, enabled: true, activate: () => modes.push('view')},
            {id: 'edit', label: 'Edit', icon: 'fas fa-pencil-alt', shortcut: 'e', active: editing, enabled: true, activate: () => modes.push('edit')},
            {id: 'wiring', label: 'Wiring', icon: 'fas fa-sitemap', shortcut: 'w', active: false, enabled: false, activate: () => modes.push('wiring')},
        ],
        deleteSelection: () => { calls.push(['delete']); return true; },
        cancel: () => { calls.push(['cancel']); return true; },
    };
    let popups = false;
    Wirecloud.UserInterfaceManager = {
        views: {workspace: workspaceView, myresources: {view_name: 'myresources'}, marketplace: {view_name: 'marketplace'}},
        getCurrentView: () => workspaceView,
        changeCurrentView: (name) => calls.push(['view', name]),
        monitorTask: (task) => calls.push(['monitor', task]),
        hasPopups: () => popups,
    };

    class Version {
        constructor(value) { this.value = value; }
        compareTo(other) { return this.value - other.value; }
    }
    Wirecloud.LocalCatalogue = {resourceVersions: {
        'CoNWeT/map': [
            {type: 'widget', uri: 'CoNWeT/map/1', title: 'Map viewer', name: 'map', vendor: 'CoNWeT', description: 'Map', version: new Version(1)},
            {type: 'widget', uri: 'CoNWeT/map/2', title: 'Map viewer', name: 'map', vendor: 'CoNWeT', description: 'Map', version: new Version(2)},
        ],
        'CoNWeT/ngsi': [{type: 'operator', uri: 'CoNWeT/ngsi/1', title: 'NGSI source', name: 'ngsi', vendor: 'CoNWeT', description: 'Orion', version: new Version(1)}],
        'CoNWeT/mashup': [{type: 'mashup', uri: 'CoNWeT/mashup/1', title: 'Map mashup', name: 'mashup', vendor: 'CoNWeT', description: '', version: new Version(1)}],
    }};

    Wirecloud.ui.WorkspaceViewMenuItems = class extends StyledElements.DynamicMenuItems {
        constructor() {
            super();
        }
        build() {
            const item = new StyledElements.MenuItem('Share', () => calls.push(['share']));
            item.commandId = 'share';
            return [item];
        }
    };
    Wirecloud.ui.WorkspaceTabViewMenuItems = class extends StyledElements.DynamicMenuItems {
        constructor() {
            super();
        }
        build() {
            return [new StyledElements.MenuItem('Rename', () => calls.push(['rename-tab']))];
        }
    };
    workspaceView.activeTab.model = {};

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/PlatformCommands.js');
    return {calls, modes, workspaceView, setPopups: (value) => { popups = value; }};
};

test('platform commands list workspaces, menus and navigation', () => {
    const env = loadPlatformCommands();
    const commands = Wirecloud.commands;

    const all = commands.list('');
    const ids = all.map((command) => command.id);
    assert.deepEqual(ids.slice(0, 2), ['workspaces.w1', 'workspaces.w2']);
    assert.ok(ids.includes('workspace.share'));
    assert.ok(!ids.some((id) => id.startsWith('tab.')), 'tab commands are only available while editing');
    assert.ok(ids.includes('mode.edit'));
    assert.ok(!ids.includes('mode.view'), 'the active mode is not listed');
    assert.ok(ids.includes('navigation.myresources'));
    assert.ok(!ids.some((id) => id.startsWith('resources.')), 'resources require a query');

    const current = all[0];
    assert.equal(current.label, 'admin / Lab');
    assert.equal(current.icon, 'fas fa-lock');
    assert.equal(current.hint, 'Current');
    assert.equal(all[1].icon, 'fas fa-globe');

    commands.run('workspaces.w2');
    commands.run('workspace.share');
    commands.run('navigation.myresources');
    assert.deepEqual(env.calls, [['switch', 'w2'], ['monitor', 'task'], ['share'], ['view', 'myresources']]);
});

test('platform commands offer installed resources when searching', async () => {
    const env = loadPlatformCommands({editing: true});
    const commands = Wirecloud.commands;

    const results = commands.list('map');
    assert.deepEqual(results.filter((command) => command.group === 'resources').map((command) => command.id), ['resources.CoNWeT/map/2']);

    // Query-only commands are run from the listed command objects
    assert.equal(commands.run('resources.CoNWeT/map/2'), undefined);
    commands.run(results.find((command) => command.id === 'resources.CoNWeT/map/2'));
    assert.deepEqual(env.calls.slice(-1), [['widget', 'CoNWeT/map/2']]);

    await commands.run(commands.list('orion').find((command) => command.group === 'resources'));
    assert.deepEqual(env.calls.slice(-2), [['operator', 'CoNWeT/ngsi/1'], ['view', 'wiring']]);

    assert.ok(commands.list('').some((command) => command.id.startsWith('tab.')));
});

test('platform shortcuts switch modes, delete and cancel', () => {
    const env = loadPlatformCommands();
    const shortcuts = Wirecloud.ui.shortcuts;
    shortcuts.enabled = true;

    assert.equal(shortcuts.handle(keyEvent('e')), true);
    assert.equal(shortcuts.handle(keyEvent('v')), true, 'the active mode consumes the key');
    assert.equal(shortcuts.handle(keyEvent('w')), false, 'disabled modes are ignored');
    assert.deepEqual(env.modes, ['edit']);

    assert.equal(shortcuts.handle(keyEvent('Delete')), true);
    assert.equal(shortcuts.handle(keyEvent('Escape')), true);
    env.setPopups(true);
    assert.equal(shortcuts.handle(keyEvent('Escape')), false);
    assert.deepEqual(env.calls, [['delete'], ['cancel']]);

    // No palette registered by the theme
    assert.equal(shortcuts.handle(keyEvent('k', {metaKey: true})), false);
});
