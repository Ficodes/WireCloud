const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScript,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');

const setup = (context = {}) => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();

    const elementsById = {};
    const register = (id, element) => {
        element.setAttribute('id', id);
        elementsById[id] = element;
        return element;
    };

    const wrapper = register('wirecloud_header', document.createElement('header'));
    const appBar = document.createElement('div');
    appBar.className = 'wirecloud_app_bar';
    wrapper.appendChild(appBar);
    const breadcrumParent = document.createElement('nav');
    const breadcrum = register('wirecloud_breadcrum', document.createElement('div'));
    breadcrumParent.appendChild(breadcrum);
    const userMenu = register('wc-user-menu', document.createElement('div'));
    document.body.appendChild(wrapper);
    document.body.appendChild(breadcrumParent);
    document.body.appendChild(userMenu);

    document.getElementById = (id) => elementsById[id] ?? null;
    document.querySelector = (selector) => {
        if (selector === '#wc-user-menu') {
            return elementsById['wc-user-menu'] ?? null;
        }
        if (selector === '.wc-signin-button') {
            return document.querySelectorAll(selector)[0] ?? null;
        }
        return null;
    };
    document.querySelectorAll = (selector) => {
        if (selector === '.wc-signin-button') {
            return userMenu.childNodes.filter((node) => node.classList?.contains('wc-signin-button'));
        }
        return [];
    };
    wrapper.querySelector = (selector) => selector === '.wirecloud_app_bar' ? appBar : null;

    class Button {
        constructor(options = {}) {
            this.options = options;
            this.wrapperElement = document.createElement('button');
            this.enabled = true;
            this.icons = [];
            this.classes = [];
            this.listeners = {};
            if (options.class) {
                this.wrapperElement.className = options.class;
            }
            if (options.iconClass) {
                this.icons.push(options.iconClass);
            }
        }
        addEventListener(type, listener) {
            this.listeners[type] = listener;
        }
        click() {
            this.listeners.click?.();
        }
        disable() {
            this.enabled = false;
            return this;
        }
        setDisabled(disabled) {
            this.enabled = !disabled;
            return this;
        }
        insertInto(parent, reference) {
            parent.insertBefore(this.wrapperElement, reference ?? null);
            return this;
        }
        addClassName(className) {
            this.classes.push(className);
            return this;
        }
        addIconClassName(className) {
            this.icons.push(className);
            return this;
        }
        addIconClass(className) {
            this.icons.push(className);
            return this;
        }
    }

    class PopupMenu {
        constructor() {
            this.items = [];
        }
        append(item) {
            this.items.push(item);
            return this;
        }
    }

    class PopupButton extends Button {
        constructor(options = {}) {
            super(options);
            this.menu = new PopupMenu();
        }
        getPopupMenu() {
            return this.menu;
        }
        replacePopupMenu(menu) {
            this.menu = menu;
        }
    }

    class MenuItem {
        constructor(label, handler) {
            this.label = label;
            this.handler = handler;
            this.icons = [];
        }
        addIconClass(className) {
            this.icons.push(className);
            return this;
        }
        run() {
            this.handler?.();
        }
    }

    StyledElements.Button = Button;
    StyledElements.PopupButton = PopupButton;
    StyledElements.MenuItem = MenuItem;
    StyledElements.Separator = class Separator {};
    StyledElements.GUIBuilder = class GUIBuilder {
        parse(template, data) {
            return {
                appendTo(parent) {
                    if (data.usermenu) {
                        const button = data.usermenu({});
                        parent.appendChild(button.wrapperElement);
                    } else {
                        const button = document.createElement('button');
                        button.className = 'wc-signin-button';
                        parent.appendChild(button);
                    }
                    this.template = template;
                    this.data = data;
                }
            };
        }
    };

    const eventListeners = {};
    global.Wirecloud = {
        Utils: StyledElements.Utils,
        URLs: { DJANGO_ADMIN: '/admin/' },
        currentTheme: {
            templates: {
                'wirecloud/signin': '<signin/>',
                'wirecloud/user_menu': '<user-menu/>',
            },
        },
        contextManager: {
            get(name) {
                return context[name];
            }
        },
        ui: {
            PreferencesWindowMenu: class PreferencesWindowMenu {
                constructor(scope, preferences) {
                    this.scope = scope;
                    this.preferences = preferences;
                }
                show() {
                    Wirecloud.lastPreferencesDialog = this;
                }
            },
            TutorialSubMenu: class TutorialSubMenu {},
            AppConnectionsWindowMenu: class AppConnectionsWindowMenu {
                show() {
                    Wirecloud.appConnectionsShown = true;
                }
            },
            FormWindowMenu: class FormWindowMenu {
                constructor(fields, title, className) {
                    this.fields = fields;
                    this.title = title;
                    this.className = className;
                    this.form = { fieldInterfaces: { username: { inputElement: document.createElement('input') } } };
                }
                show() {
                    Wirecloud.lastFormDialog = this;
                }
            },
            UserTypeahead: class UserTypeahead {
                bind(input) {
                    Wirecloud.lastTypeaheadInput = input;
                }
            },
            AdminPanelWindowMenu: class AdminPanelWindowMenu {
                show() {
                    Wirecloud.adminPanelShown = true;
                }
            },
        },
        preferences: { name: 'prefs' },
        addEventListener(type, listener) {
            eventListeners[type] = listener;
        },
        login() {
            Wirecloud.loggedIn = true;
        },
        logout() {
            Wirecloud.loggedOut = true;
        },
        switchUser(username) {
            Wirecloud.switchedTo = username;
        },
        eventListeners,
    };
    window.open = (url, target) => {
        window.lastOpened = { url, target };
    };

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WirecloudHeader.js');
    return { appBar, breadcrum, userMenu, Button, MenuItem };
};

test('WirecloudHeader paints breadcrumbs, toolbar buttons, menu and back state', () => {
    const { breadcrum, appBar, Button } = setup();
    const header = new Wirecloud.ui.WirecloudHeader();
    const toolbarButton = new Button();
    let wentUp = false;
    const toolbarMenu = { id: 'menu' };
    const view = {
        getBreadcrumb: () => ['Home', { label: 'Workspace', class: 'current' }],
        getToolbarButtons: () => [toolbarButton],
        getToolbarMenu: () => toolbarMenu,
        goUp: () => {
            wentUp = true;
        },
        canGoUp: () => true,
    };

    header._notifyViewChange(view);
    assert.equal(breadcrum.textContent, 'Home/Workspace');
    assert.equal(breadcrum.childNodes[2].classList.contains('current'), true);
    assert.equal(toolbarButton.classes.includes('btn-large'), true);
    assert.equal(toolbarButton.icons.includes('fa-fw'), true);
    assert.equal(header.toolbar.parentElement, appBar);
    assert.equal(header.menuButton.menu, toolbarMenu);
    assert.equal(header.menuButton.enabled, true);
    assert.equal(header.backButton.enabled, true);

    header.backButton.click();
    assert.equal(wentUp, true);

    header._notifyViewChange(null);
    assert.equal(header.backButton.enabled, false);
    assert.equal(header.menuButton.enabled, false);
});

test('WirecloudHeader handles views without optional breadcrumb, toolbar and menu APIs', () => {
    const { breadcrum } = setup();
    const header = new Wirecloud.ui.WirecloudHeader();

    header._paintBreadcrumb(null);
    assert.equal(breadcrum.textContent, '');

    header._paintBreadcrumb({ getBreadcrumb: () => [] });
    assert.equal(breadcrum.textContent, '');

    header._notifyViewChange({ getBreadcrumb: () => ['Only'], goUp() {} });
    assert.equal(breadcrum.textContent, 'Only');
    assert.equal(header.menuButton.menu, undefined);
    assert.equal(header.menuButton.enabled, false);
    assert.equal(header.backButton.enabled, true);

    header._notifyViewChange({ getBreadcrumb: () => ['Only'], goUp() {}, canGoUp: () => false });
    assert.equal(header.backButton.enabled, false);
});

test('WirecloudHeader initializes anonymous sign-in menu', () => {
    const { userMenu } = setup({ isanonymous: true });
    const header = new Wirecloud.ui.WirecloudHeader();

    header._initUserMenu();
    assert.equal(userMenu.childNodes.length, 1);
    userMenu.childNodes[0].dispatchEvent({ type: 'click' });
    assert.equal(Wirecloud.loggedIn, true);
});

test('WirecloudHeader initializes authenticated user menu actions', () => {
    setup({
        isanonymous: false,
        username: 'alice',
        avatar: '/avatar.png',
        isstaff: true,
        issuperuser: true,
        realuser: 'admin',
    });
    const header = new Wirecloud.ui.WirecloudHeader();

    header._initUserMenu();
    const items = header.user_button.getPopupMenu().items;
    assert.equal(items.length, 8);
    items[0].run();
    assert.equal(Wirecloud.lastPreferencesDialog.scope, 'platform');
    items[1].run();
    assert.deepEqual(window.lastOpened, { url: '/admin/', target: '_blank' });
    items[4].run();
    Wirecloud.lastFormDialog.executeOperation({ username: 'bob' });
    assert.equal(Wirecloud.switchedTo, 'bob');
    assert.equal(Wirecloud.lastTypeaheadInput.tagName, 'INPUT');
    items[5].run();
    assert.equal(Wirecloud.adminPanelShown, true);
    items[6].run();
    assert.equal(Wirecloud.switchedTo, 'admin');
    items[7].run();
    assert.equal(Wirecloud.loggedOut, true);
});

test('WirecloudHeader skips missing user menu wrapper and optional staff entries', () => {
    setup({ isanonymous: false, username: 'alice', avatar: '/avatar.png', isstaff: false, issuperuser: false });
    document.querySelector = () => null;
    const header = new Wirecloud.ui.WirecloudHeader();
    assert.doesNotThrow(() => header._initUserMenu());

    document.querySelector = (selector) => selector === '#wc-user-menu' ? document.getElementById('wc-user-menu') : null;
    header._initUserMenu();
    const items = header.user_button.getPopupMenu().items;
    assert.equal(items.length, 4);
});

test('WirecloudHeader opens app connections in a modal', () => {
    setup({ isanonymous: false, username: 'alice', avatar: '/avatar.png', realuser: null });
    Wirecloud.URLs.OAUTH2_CONNECTIONS = '/wirecloud/oauth2/connections';
    const header = new Wirecloud.ui.WirecloudHeader();
    header._initUserMenu();
    const item = header.user_button.getPopupMenu().items.find((item) => item.label === 'App connections');
    assert.ok(item);
    assert.ok(item.icons.includes('fas fa-plug'));
    item.run();
    assert.equal(Wirecloud.appConnectionsShown, true);
});

test('WirecloudHeader omits app connections when OAuth is disabled or the user is impersonated', () => {
    for (const [enabled, realuser] of [[false, null], [true, 'admin']]) {
        setup({ isanonymous: false, username: 'alice', avatar: '/avatar.png', realuser });
        if (enabled) Wirecloud.URLs.OAUTH2_CONNECTIONS = '/oauth2/connections';
        const header = new Wirecloud.ui.WirecloudHeader();
        header._initUserMenu();
        assert.ok(!header.user_button.getPopupMenu().items.some((item) => item.label === 'App connections'));
    }
});
