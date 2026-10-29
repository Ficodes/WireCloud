// -*- coding: utf-8 -*-
// Copyright (c) 2026 Future Internet Consulting and Development Solutions S.L.

// This file is part of Wirecloud.

// Wirecloud is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

// Wirecloud is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.

// You should have received a copy of the GNU Affero General Public License
// along with Wirecloud.  If not, see <http://www.gnu.org/licenses/>.

/* globals StyledElements, Wirecloud */


(function (Industry, se, utils) {

    "use strict";

    const builder = new se.GUIBuilder();

    const get_initial = function get_initial() {
        const name = Wirecloud.contextManager.get('fullname') || Wirecloud.contextManager.get('username') || '?';
        return name.trim().charAt(0).toUpperCase();
    };

    const get_current_mode = function get_current_mode(view) {
        if (view == null) {
            return null;
        }
        return Wirecloud.UserInterfaceManager.getRootState('mode');
    };

    // =========================================================================
    // Navigation rail
    // =========================================================================

    const Rail = class Rail {

        constructor(header) {
            this.header = header;
            this.wrapperElement = document.getElementById('wc-rail');
            this.itemsElement = this.wrapperElement.querySelector('.wc-rail-items');
            this.toolsElement = this.wrapperElement.querySelector('.wc-rail-tools');

            const item = (view, icon, label) => {
                const button = Industry.button({
                    className: 'wc-rail-item',
                    icon: icon,
                    iconSize: 19,
                    title: label,
                    onclick: () => {
                        Wirecloud.UserInterfaceManager.changeCurrentView(view);
                    }
                });
                button.setAttribute('role', 'listitem');
                button.dataset.view = view;
                this.itemsElement.appendChild(button);
                return button;
            };

            this.items = {
                workspace: item('workspace', 'layout-dashboard', utils.gettext("Workspaces")),
                myresources: item('myresources', 'boxes', utils.gettext("My resources")),
                marketplace: item('marketplace', 'store', utils.gettext("Marketplace"))
            };
            this.items.myresources.hidden = true;
            this.items.marketplace.hidden = true;

            this.schemeButton = Industry.button({
                className: 'wc-rail-item wc-color-scheme-toggle',
                icon: 'moon',
                iconSize: 18,
                title: utils.gettext("Toggle color scheme"),
                onclick: () => {
                    Wirecloud.ui.ColorScheme.toggle();
                }
            });
            this.schemeButton.hidden = true;
            this.toolsElement.appendChild(this.schemeButton);

            Wirecloud.ui.ColorScheme.addEventListener('change', this.refreshColorScheme.bind(this));

            Wirecloud.addEventListener('contextloaded', () => {
                const anonymous = Industry.isAnonymous();
                this.items.myresources.hidden = anonymous;
                this.refreshColorScheme();
            });

            Wirecloud.addEventListener('loaded', () => {
                if (Industry.isAnonymous()) {
                    return;
                }
                // The marketplace is only offered when markets are configured
                Wirecloud.MarketManager.getMarkets().then((markets) => {
                    this.items.marketplace.hidden = Object.keys(markets || {}).length === 0;
                }, () => {});
            });
        }

        refresh(view) {
            const mode = get_current_mode(view);
            const active = mode === 'catalogue' ? 'myresources' : (mode === 'marketplace' ? 'marketplace' : 'workspace');
            Object.keys(this.items).forEach((key) => {
                const selected = key === active;
                this.items[key].classList.toggle('active', selected);
                if (selected) {
                    this.items[key].setAttribute('aria-current', 'page');
                } else {
                    this.items[key].removeAttribute('aria-current');
                }
            });
        }

        refreshColorScheme() {
            const colorScheme = Wirecloud.ui.ColorScheme;
            const supported = colorScheme.supported;
            this.schemeButton.hidden = supported.indexOf('dark') === -1 || supported.indexOf('light') === -1;

            const dark = colorScheme.resolve() === 'dark';
            const icon = this.schemeButton.querySelector('.lc-icon');
            icon.className = 'lc-icon ' + (dark ? 'lc-sun' : 'lc-moon');
            const label = dark ? utils.gettext("Switch to light color scheme") : utils.gettext("Switch to dark color scheme");
            this.schemeButton.title = label;
            this.schemeButton.setAttribute('aria-label', label);
        }

    };

    // =========================================================================
    // Header
    // =========================================================================

    const build_workspace_header = function build_workspace_header() {
        const bar = this.appBar;

        // Workspace switcher (breadcrumb)
        this.ownerElement = Industry.element('span', 'wc-header-owner');
        this.titleElement = Industry.element('span', 'wc-header-title');
        this.switcher = Industry.element('button', 'wc-header-switcher', [
            this.ownerElement,
            this.titleElement,
            Industry.icon('chevron-down')
        ]);
        this.switcher.type = 'button';
        this.switcher.title = utils.gettext("Switch workspace");
        this.switcher.addEventListener('click', () => {
            Wirecloud.commands.openPalette({groups: ['workspaces']});
        });
        this.breadcrum.appendChild(this.switcher);

        this.visibilityTag = Industry.element('span', 'tag tag-neutral wc-visibility-tag', [
            Industry.icon('lock'),
            Industry.element('span', 'wc-visibility-label', [""])
        ]);
        bar.appendChild(this.visibilityTag);

        bar.appendChild(Industry.element('div', 'wc-header-spacer'));

        // Search / command palette trigger
        this.searchTrigger = Industry.element('button', 'wc-search-trigger', [
            Industry.icon('search'),
            Industry.element('span', 'wc-search-label', [utils.gettext("Search or run…")]),
            Industry.element('kbd', 'wc-search-kbd', [Industry.modKey() + 'K'])
        ]);
        this.searchTrigger.type = 'button';
        this.searchTrigger.setAttribute('aria-label', utils.gettext("Search or run a command"));
        this.searchTrigger.addEventListener('click', () => {
            Wirecloud.commands.openPalette();
        });
        bar.appendChild(this.searchTrigger);

        // Toolbar (the class is used by the tutorials)
        this.toolbar = Industry.element('div', 'wc-toolbar');
        this.toolbar.setAttribute('role', 'toolbar');
        this.toolbar.setAttribute('aria-label', utils.gettext("Wirecloud toolbar"));
        bar.appendChild(this.toolbar);

        this.modeSwitch = Industry.element('div', 'seg wc-mode-switch');
        this.modeSwitch.setAttribute('role', 'radiogroup');
        this.modeSwitch.setAttribute('aria-label', utils.gettext("Mode"));
        this.toolbar.appendChild(this.modeSwitch);

        this.toolbarDivider = Industry.element('div', 'wc-header-divider');
        this.toolbarDivider.setAttribute('aria-hidden', 'true');
        this.toolbar.appendChild(this.toolbarDivider);

        this.secondaryActions = Industry.element('div', 'wc-header-secondary');
        this.toolbar.appendChild(this.secondaryActions);

        this.menuButton = new se.PopupButton({
            class: 'btn-icon wc-workspace-menu-button',
            iconClass: 'lc-icon lc-ellipsis',
            title: utils.gettext("Workspace menu"),
            menuOptions: {placement: ['bottom-right', 'top-right']}
        });
        this.menuButton.insertInto(this.toolbar);

        this.primaryButton = new se.Button({
            class: 'btn-primary wc-primary-action',
            iconClass: 'lc-icon lc-plus',
            text: utils.gettext("Add widget")
        });
        this.primaryButton.addEventListener('click', () => {
            if (this.primaryAction != null) {
                this.primaryAction.run();
            }
        });
        this.primaryButton.insertInto(this.toolbar);

        // Generic views: back button + toolbar buttons
        this.backButton = new se.Button({
            class: 'btn-icon wc-back-button',
            iconClass: 'lc-icon lc-chevron-left',
            title: utils.gettext("Back")
        });
        this.backButton.addEventListener('click', () => {
            if (this.currentView != null && typeof this.currentView.goUp === 'function') {
                this.currentView.goUp();
            }
        });
        this.backButton.insertInto(this.breadcrum.parentNode, this.breadcrum);

        this.genericBreadcrumb = Industry.element('span', 'wc-header-crumbs');
        this.breadcrum.appendChild(this.genericBreadcrumb);

        this.viewToolbar = Industry.element('div', 'wc-view-toolbar');
        this.toolbar.insertBefore(this.viewToolbar, this.modeSwitch);
    };

    const paint_modes = function paint_modes(view) {
        this.modeSwitch.innerHTML = '';
        const modes = typeof view.getModes === 'function' ? view.getModes() : [];
        const modeClasses = {view: 'wc-view-mode-button', edit: 'wc-edit-mode-button', wiring: 'wc-show-wiring-button'};
        const modeIcons = {view: 'eye', edit: 'pencil', wiring: 'workflow'};

        modes.forEach((mode) => {
            const button = Industry.button({
                className: 'seg-opt ' + (modeClasses[mode.id] || ''),
                icon: modeIcons[mode.id] || null,
                label: mode.label,
                title: mode.shortcut ? utils.interpolate(utils.gettext("%(mode)s (shortcut: %(key)s)"), {mode: mode.label, key: mode.shortcut.toUpperCase()}) : mode.label,
                onclick: () => {
                    if (!mode.active) {
                        mode.activate();
                    }
                }
            });
            if (!modeIcons[mode.id] && mode.icon) {
                button.insertBefore(Industry.iconFromClass(mode.icon), button.firstChild);
            }
            button.setAttribute('role', 'radio');
            button.setAttribute('aria-checked', mode.active ? 'true' : 'false');
            button.classList.toggle('active', !!mode.active);
            button.disabled = !mode.enabled;
            this.modeSwitch.appendChild(button);
        });

        this.modeSwitch.hidden = modes.length === 0;
    };

    const paint_actions = function paint_actions(view) {
        this.secondaryActions.innerHTML = '';
        const actions = typeof view.getSecondaryActions === 'function' ? view.getSecondaryActions() : [];
        const icons = {share: 'share-2', behaviours: 'workflow'};

        actions.forEach((action) => {
            const button = new se.Button({
                class: 'wc-secondary-action wc-action-' + action.id,
                iconClass: icons[action.id] ? 'lc-icon lc-' + icons[action.id] : action.icon,
                text: action.label,
                title: action.label
            });
            button.enabled = action.enabled !== false;
            button.toggleClassName('active', !!action.active);
            button.addEventListener('click', () => action.run());
            button.insertInto(this.secondaryActions);
        });

        this.primaryAction = typeof view.getPrimaryAction === 'function' ? view.getPrimaryAction() : null;
        this.primaryButton.toggleClassName('hidden', this.primaryAction == null);
        if (this.primaryAction != null) {
            this.primaryButton.setLabel(this.primaryAction.label);
            this.primaryButton.enabled = this.primaryAction.enabled !== false;
            // Classes expected by the tutorials
            this.primaryButton.toggleClassName('wc-show-component-sidebar-button', this.primaryAction.id === 'add-widget');
            this.primaryButton.toggleClassName('we-show-component-sidebar-button', this.primaryAction.id === 'add-operator');
        }

        const menu = new se.PopupMenu({placement: ['bottom-right', 'top-right']});
        let hasMenu = false;
        if (view.view_name === 'workspace' && view.model != null && !Industry.isAnonymous()) {
            menu.append(new Wirecloud.ui.WorkspaceViewMenuItems(view));
            hasMenu = true;
        } else if (view.view_name === 'wiring') {
            const workspaceView = Wirecloud.UserInterfaceManager.views.workspace;
            if (workspaceView.model != null) {
                menu.append(new Wirecloud.ui.WorkspaceViewMenuItems(workspaceView));
                hasMenu = true;
            }
        }
        this.menuButton.replacePopupMenu(hasMenu ? menu : null);
        this.menuButton.toggleClassName('hidden', !hasMenu);

        this.toolbarDivider.hidden = actions.length === 0 && !hasMenu && this.primaryAction == null;
    };

    const paint_workspace_info = function paint_workspace_info(view) {
        const workspace = Wirecloud.activeWorkspace;
        const state = Wirecloud.HistoryManager.getCurrentState();
        const owner = workspace != null ? workspace.owner : state.workspace_owner;
        const title = workspace != null ? workspace.title : (state.workspace_title || utils.gettext("loading..."));

        this.ownerElement.textContent = owner != null ? owner + ' /' : '';
        this.titleElement.textContent = title;
        this.switcher.title = utils.interpolate(utils.gettext("%(workspace)s · Switch workspace"), {workspace: title});

        const isPublic = workspace != null && workspace.preferences != null && workspace.preferences.get('public');
        this.visibilityTag.hidden = workspace == null;
        this.visibilityTag.querySelector('.lc-icon').className = 'lc-icon ' + (isPublic ? 'lc-globe' : 'lc-lock');
        this.visibilityTag.querySelector('.wc-visibility-label').textContent = isPublic ? utils.gettext("Public") : utils.gettext("Private");
    };

    const paint_generic = function paint_generic(view) {
        this.genericBreadcrumb.innerHTML = '';
        const entries = typeof view.getBreadcrumb === 'function' ? view.getBreadcrumb() : [];
        entries.forEach((entry, index) => {
            if (typeof entry === 'string') {
                entry = {label: entry};
            }
            if (index > 0) {
                this.genericBreadcrumb.appendChild(Industry.element('span', 'wc-header-crumb-separator', ['/']));
            }
            const crumb = Industry.element('span', index === entries.length - 1 ? 'wc-header-title' : 'wc-header-owner', [entry.label]);
            crumb.setAttribute('aria-level', String(index + 1));
            this.genericBreadcrumb.appendChild(crumb);
        });

        this.viewToolbar.innerHTML = '';
        const buttons = typeof view.getToolbarButtons === 'function' ? view.getToolbarButtons() : [];
        buttons.forEach((button) => {
            button.addClassName('btn-icon');
            button.insertInto(this.viewToolbar);
        });

        const menu = typeof view.getToolbarMenu === 'function' ? view.getToolbarMenu() : null;
        this.menuButton.replacePopupMenu(menu);
        this.menuButton.toggleClassName('hidden', menu == null);

        let canGoUp = typeof view.goUp === 'function';
        if (canGoUp && typeof view.canGoUp === 'function') {
            canGoUp = view.canGoUp();
        }
        this.backButton.toggleClassName('hidden', !canGoUp);
    };

    Industry.Header = class Header {

        constructor() {
            this.wrapperElement = document.getElementById('wirecloud_header');
            this.plain = document.querySelector('.plain_content') != null;
            this.currentView = null;
            this.primaryAction = null;

            this.breadcrum = document.getElementById('wirecloud_breadcrum');
            this.appBar = this.wrapperElement.querySelector('.wirecloud_app_bar');

            if (!this.plain) {
                build_workspace_header.call(this);
                if (document.getElementById('wc-rail') != null) {
                    this.rail = new Rail(this);
                }

                Wirecloud.addEventListener('viewcontextchanged', this.refresh.bind(this));
                Wirecloud.addEventListener('activeworkspacechanged', (wirecloud, workspace) => {
                    if (workspace != null && workspace.preferences != null) {
                        workspace.preferences.addEventListener('post-commit', () => this.refresh());
                    }
                });
            }

            Wirecloud.addEventListener('contextloaded', this._initUserMenu.bind(this));
        }

        get defaults() {
            return Wirecloud.ui.WirecloudHeader != null ? Wirecloud.ui.WirecloudHeader.defaults : {userMenuIconClasses: {}};
        }

        _initUserMenu() {
            const wrapper = document.querySelector('#wc-user-menu');
            if (wrapper == null) {
                return;
            }

            if (Wirecloud.contextManager.get('isanonymous')) {
                builder.parse(Wirecloud.currentTheme.templates['wirecloud/signin']).appendTo(wrapper);
                wrapper.querySelectorAll(".wc-signin-button").forEach((button) => {
                    button.addEventListener('click', (event) => {
                        event.preventDefault();
                        Wirecloud.login();
                    });
                });
                return;
            }

            const username = Wirecloud.contextManager.get('username');
            const avatar = Industry.element('span', 'wc-avatar', [get_initial()]);
            avatar.setAttribute('aria-hidden', 'true');

            builder.parse(Wirecloud.currentTheme.templates['wirecloud/user_menu'], {
                username: username,
                avatar: avatar,
                usermenu: (options) => {
                    options.menuOptions = {placement: ['right-bottom', 'top-left', 'bottom-right']};
                    this.user_button = new se.PopupButton(options);
                    this.user_button.setTitle(utils.interpolate(utils.gettext("User menu of %(username)s"), {username: username}));
                    return this.user_button;
                }
            }).appendTo(wrapper);

            const menu = this.user_button.getPopupMenu();
            this.buildUserMenu(menu);
        }

        buildUserMenu(menu) {
            Wirecloud.ui.WirecloudHeader.prototype.buildUserMenu.call(this, menu);
        }

        _notifyViewChange(newView) {
            if (newView != null) {
                this.currentView = newView;
                this.refresh();
            }
        }

        refresh() {
            const view = this.currentView;
            if (this.plain || view == null) {
                return;
            }

            if (this.rail != null) {
                this.rail.refresh(view);
            }
            if (Industry.statusBar != null) {
                Industry.statusBar.refresh();
            }

            const workspaceMode = typeof view.getModes === 'function';
            if (view.view_name === 'workspace' && !this._editmodeListener) {
                // Repaint the mode switch and actions when entering/leaving edit mode
                this._editmodeListener = () => this.refresh();
                view.addEventListener('editmode', this._editmodeListener);
            }
            this.wrapperElement.classList.toggle('wc-header-workspace', workspaceMode);
            this.wrapperElement.classList.toggle('wc-header-generic', !workspaceMode);

            // The catalogue search view provides its own header
            const ownHeader = view.view_name === 'myresources' && view.alternatives != null &&
                view.alternatives.getCurrentAlternative() === view.viewsByName.search &&
                Wirecloud.ui.registry.has('MyResourcesSearchView');
            this.wrapperElement.classList.toggle('hidden', ownHeader);

            if (workspaceMode) {
                paint_workspace_info.call(this, view);
                paint_modes.call(this, view);
                paint_actions.call(this, view);
                this.viewToolbar.innerHTML = '';
                this.backButton.addClassName('hidden');
            } else {
                this.modeSwitch.hidden = true;
                this.secondaryActions.innerHTML = '';
                this.primaryButton.addClassName('hidden');
                this.visibilityTag.hidden = true;
                this.toolbarDivider.hidden = true;
                paint_generic.call(this, view);
            }
        }

    };

    Industry.Rail = Rail;

    if (Wirecloud.constants.CURRENT_MODE !== 'embedded') {
        Wirecloud.ui.registry.register('WirecloudHeader', Industry.Header);
    }

})(Wirecloud.ui.Industry, StyledElements, Wirecloud.Utils);
