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

    const SAVE_DELAY = 400;
    const REMOVE_DELAY = 4500;

    const screen_size_icon = function screen_size_icon(screenSize, index, count) {
        const name = String(screenSize.name || '').toLowerCase();
        if (/phone|mobile|small|móvil|movil/.test(name)) {
            return 'smartphone';
        } else if (/tablet|medium/.test(name)) {
            return 'tablet';
        } else if (/desktop|large|wide|escritorio/.test(name)) {
            return 'monitor';
        }
        if (index === 0 && count > 1) {
            return 'smartphone';
        }
        return index === count - 1 ? 'monitor' : 'tablet';
    };

    const screen_size_range = function screen_size_range(screenSize) {
        if (screenSize.lessOrEqual === -1) {
            return '≥' + screenSize.moreOrEqual + 'px';
        }
        return screenSize.moreOrEqual + '–' + screenSize.lessOrEqual + 'px';
    };

    // =========================================================================
    // Layout settings dialog
    // =========================================================================

    /**
     * Screen sizes, cell height and widget margin of a workspace. Changes are
     * applied live (they are stored in the workspace preferences, inherited by
     * the tabs).
     */
    Industry.LayoutSettingsWindowMenu = class LayoutSettingsWindowMenu extends Wirecloud.ui.WindowMenu {

        constructor(workspaceView) {
            super(utils.gettext("Layout settings"), 'wc-layout-settings');

            this.workspaceView = workspaceView;
            this.preferences = workspaceView.model.preferences;
            this.timeout = null;

            const definitions = this.preferences.meta.preferences;
            const values = {
                screenSizes: this.preferences.get('screenSizes'),
                cellheight: this.preferences.get('cellheight'),
                margin: this.preferences.get('margin')
            };
            this.saved = utils.clone(values, true);

            this.screenSizesInput = Wirecloud.ui.InputInterfaceFactory.createInterface('screenSizes', definitions.screenSizes.options);
            this.screenSizesInput.setValue(values.screenSizes);
            const screenSizesField = Industry.element('div', 'field wc-layout-settings-screen-sizes', [
                Industry.element('label', null, [definitions.screenSizes.label])
            ]);
            this.screenSizesInput.insertInto(screenSizesField);
            this.windowContent.appendChild(screenSizesField);

            const numeric = (name, label, min, max) => {
                const input = new se.NumericField({
                    initialValue: values[name],
                    min: min,
                    max: max,
                    inc: 1
                });
                const field = Industry.element('div', 'field', [Industry.element('label', null, [label])]);
                input.insertInto(field);
                input.addEventListener('change', () => this.scheduleSave());
                return {input: input, field: field};
            };

            this.cellHeightInput = numeric('cellheight', utils.gettext("Cell height (px)"), 10, 400);
            this.marginInput = numeric('margin', utils.gettext("Widget margin (px)"), 0, 60);
            this.windowContent.appendChild(Industry.element('div', 'wc-layout-settings-fields', [
                this.cellHeightInput.field,
                this.marginInput.field
            ]));

            this.windowContent.appendChild(Industry.element('p', 'wc-layout-settings-note', [
                utils.gettext("Changes apply live to the workspace behind this dialog.")
            ]));

            // The screen sizes editor does not dispatch events, so listen to
            // the changes of its fields
            ['change', 'input', 'click'].forEach((type) => {
                screenSizesField.addEventListener(type, () => this.scheduleSave(), true);
            });

            this.doneButton = new se.Button({
                class: 'btn-primary btn-accept',
                text: utils.gettext("Done")
            });
            this.doneButton.addEventListener('click', () => {
                this.save();
                this.hide();
            });
            this.doneButton.insertInto(this.windowBottom);
        }

        scheduleSave() {
            clearTimeout(this.timeout);
            this.timeout = setTimeout(() => this.save(), SAVE_DELAY);
        }

        save() {
            clearTimeout(this.timeout);
            this.timeout = null;

            const changes = {};
            const screenSizes = this.screenSizesInput.getValue();
            if (this.screenSizesInput.checkValue() === se.InputValidationError.NO_ERROR &&
                    JSON.stringify(screenSizes) !== JSON.stringify(this.saved.screenSizes)) {
                changes.screenSizes = {value: screenSizes};
            }

            [['cellheight', this.cellHeightInput.input], ['margin', this.marginInput.input]].forEach(([name, input]) => {
                const value = input.getValue();
                if (typeof value === 'number' && !isNaN(value) && value !== this.saved[name]) {
                    changes[name] = {value: value};
                }
            });

            if (Object.keys(changes).length === 0) {
                return Promise.resolve();
            }

            Object.keys(changes).forEach((name) => {
                this.saved[name] = utils.clone(changes[name].value, true);
            });

            return this.preferences.set(changes).catch((error) => {
                Industry.toast(utils.gettext("The layout settings could not be saved"));
                Wirecloud.GlobalLogManager.log(error);
            });
        }

        hide() {
            if (this.timeout != null) {
                this.save();
            }
            return super.hide();
        }

    };

    // =========================================================================
    // Embed dialog: "Copy code" + "Close"
    // =========================================================================

    Industry.EmbedCodeWindowMenu = class EmbedCodeWindowMenu extends Wirecloud.ui.EmbedCodeWindowMenu {

        constructor(title, workspace) {
            super(utils.gettext("Embed workspace"), workspace);

            this.button.setLabel(utils.gettext("Close"));
            this.button.removeClassName('btn-primary btn-accept');

            this.copyButton = new se.Button({
                class: 'btn-primary btn-accept wc-embed-copy',
                iconClass: 'lc-icon lc-copy',
                text: utils.gettext("Copy code")
            });
            this.copyButton.addEventListener('click', () => {
                const code = this.code.getValue();
                const done = () => {
                    Industry.toast(utils.gettext("Embed code copied"));
                    this.hide();
                };
                if (navigator.clipboard != null && typeof navigator.clipboard.writeText === 'function') {
                    navigator.clipboard.writeText(code).then(done, () => this.code.select());
                } else {
                    this.code.select();
                }
            });
            this.copyButton.insertInto(this.windowBottom);
        }

    };

    // =========================================================================
    // Tab bar
    // =========================================================================

    const build_tabbar = function build_tabbar() {
        const notebook = this.notebook;

        this.tabbarExtras = Industry.element('div', 'wc-tabbar-extras');
        const east = notebook.tabWrapper.east.wrapperElement;
        east.insertBefore(this.tabbarExtras, east.firstChild);

        // "+" ghost button right after the tabs
        if (this.addTabButton != null) {
            this.addTabButton.addClassName('btn-ghost btn-icon wc-tabbar-add');
            notebook.tabArea.wrapperElement.appendChild(this.addTabButton.wrapperElement);
        }

        // Clicking the active tab while editing renames it
        notebook.tabArea.wrapperElement.addEventListener('click', (event) => {
            const tabElement = event.target.closest('.se-notebook-tab.selected');
            if (tabElement == null || !this.editing || event.target.closest('.se-btn') != null) {
                return;
            }
            const tab = this.activeTab;
            if (tab != null && tab.tabElement === tabElement && tab.model.isAllowed('rename')) {
                (new Wirecloud.ui.RenameWindowMenu(tab.model, utils.gettext('Rename Workspace Tab'))).show();
            }
        });

        notebook.addEventListener('changed', () => {
            refresh_tabbar.call(this);
            Industry.statusBar.refresh();
        });

        refresh_tabbar.call(this);
    };

    const build_layout_controls = function build_layout_controls(tab) {
        const dragboard = tab.dragboard;
        const screenSizes = dragboard.screenSizes;
        const active = dragboard.activeScreenSize;
        const detected = (() => {
            const forced = dragboard.forcedScreenSizeId;
            dragboard.forcedScreenSizeId = null;
            const value = dragboard.activeScreenSize;
            dragboard.forcedScreenSizeId = forced;
            return value;
        })();

        const container = Industry.element('div', 'wc-layout-controls');
        container.appendChild(Industry.element('span', 'wc-layout-label', [utils.gettext("Layout for")]));

        const seg = Industry.element('div', 'seg wc-layout-sizes');
        seg.setAttribute('role', 'radiogroup');
        seg.setAttribute('aria-label', utils.gettext("Screen size"));
        screenSizes.forEach((screenSize, index) => {
            const selected = screenSize.id === active.id;
            const button = Industry.button({
                className: 'seg-opt' + (selected ? ' active' : ''),
                icon: screen_size_icon(screenSize, index, screenSizes.length),
                label: selected ? screenSize.name : null,
                title: screenSize.name + ' · ' + screen_size_range(screenSize),
                onclick: () => {
                    if (screenSize.id === detected.id) {
                        tab.quitEditingScreenSize();
                    } else {
                        tab.setEditingScreenSize(screenSize.id);
                    }
                    refresh_tabbar.call(this);
                }
            });
            button.setAttribute('role', 'radio');
            button.setAttribute('aria-checked', selected ? 'true' : 'false');
            seg.appendChild(button);
        });
        container.appendChild(seg);

        const spec = [
            screen_size_range(active),
            utils.interpolate(utils.gettext("%(columns)s col"), {columns: active.columns})
        ];
        if (active.rows > 0) {
            spec.push(utils.interpolate(utils.gettext("%(rows)s rows"), {rows: active.rows}));
        } else {
            spec.push(Math.round(dragboard.getCellHeight(active)) + 'px');
        }
        container.appendChild(Industry.element('span', 'wc-layout-spec mono', [spec.join(' · ')]));

        container.appendChild(Industry.button({
            className: 'se-btn btn-ghost wc-layout-settings-button',
            icon: 'sliders-horizontal',
            label: utils.gettext("Layout"),
            onclick: () => {
                (new Industry.LayoutSettingsWindowMenu(this)).show();
            }
        }));

        return container;
    };

    const build_hints = function build_hints() {
        const hint = (key, label) => [
            Industry.element('kbd', 'wc-key', [key]),
            Industry.element('span', null, [label])
        ];
        const items = [];
        if (this.model.isAllowed('edit') && !Industry.isAnonymous()) {
            items.push(...hint('E', utils.gettext("edit")), ...hint('W', utils.gettext("wiring")));
        }
        items.push(...hint(Industry.modKey() + 'K', utils.gettext("commands")));
        const element = Industry.element('div', 'wc-shortcut-hints', items);
        element.setAttribute('aria-hidden', 'true');
        return element;
    };

    const refresh_tabbar = function refresh_tabbar() {
        if (this.tabbarExtras == null || this.model == null) {
            return;
        }

        this.tabbarExtras.innerHTML = '';
        const tab = this.activeTab;
        if (this.editing && tab != null && tab.dragboard != null) {
            this.tabbarExtras.appendChild(build_layout_controls.call(this, tab));
        } else if (!this.editing) {
            this.tabbarExtras.appendChild(build_hints.call(this));
        }
    };

    // =========================================================================
    // Workspace view
    // =========================================================================

    Industry.WorkspaceView = class WorkspaceView extends Wirecloud.ui.WorkspaceView {

        constructor(id, options) {
            super(id, options);

            this.addEventListener('editmode', () => {
                refresh_tabbar.call(this);
                Industry.statusBar.refresh();
            });

            this.layout.addEventListener('slideIn', () => this.wrapperElement.classList.add('wc-drawer-open'));
            this.layout.addEventListener('slideOut', () => this.wrapperElement.classList.remove('wc-drawer-open'));

            Wirecloud.addEventListener('loaded', () => {
                if (this.showcase == null) {
                    return;
                }
                Industry.addDrawerCloseButton(this.showcase.wrapperElement, () => this.showComponentSidebar(false));
            });
        }

        buildAddWidgetButton() {
            const button = new se.ToggleButton({
                title: utils.gettext("Add widget"),
                text: utils.gettext("Add widget"),
                class: "btn-primary wc-show-component-sidebar-button",
                iconClass: "lc-icon lc-plus"
            });
            button.addEventListener('click', (button) => {
                if (button.active) {
                    this.setEditing(true);
                    this.showcase.searchComponents.refresh();
                    this.layout.slideIn();
                } else {
                    this.layout.slideOut();
                }
            });

            return button;
        }

        loadWorkspace(workspace, options) {
            const result = super.loadWorkspace(workspace, options);

            build_tabbar.call(this);

            ['createwidget', 'removewidget', 'createoperator', 'removeoperator', 'change'].forEach((event) => {
                workspace.addEventListener(event, () => Industry.statusBar.refresh());
            });
            workspace.wiring.addEventListener('load', () => Industry.statusBar.refresh());
            this.tabs.forEach((tab) => {
                tab.model.preferences.addEventListener('post-commit', () => refresh_tabbar.call(this));
            });
            workspace.addEventListener('createtab', (workspace, tabModel) => {
                tabModel.preferences.addEventListener('post-commit', () => refresh_tabbar.call(this));
            });

            Industry.statusBar.refresh();
            return result;
        }

        updateEditingInterval(element) {
            super.updateEditingInterval(element);
            refresh_tabbar.call(this);
        }

    };

    // =========================================================================
    // Widget chrome
    // =========================================================================

    const update_size_badge = function update_size_badge() {
        const badge = this.wrapperElement.querySelector('.wc-widget-size-badge');
        const node = this.wrapperElement.gridstackNode;
        if (badge != null && node != null) {
            badge.textContent = node.w + ' × ' + node.h;
        }
    };

    Industry.WidgetView = class WidgetView extends Wirecloud.ui.WidgetView {

        applyLayout(layout) {
            const result = super.applyLayout(layout);
            update_size_badge.call(this);
            return result;
        }

        syncLayoutFromNode() {
            const result = super.syncLayoutFromNode.apply(this, arguments);
            update_size_badge.call(this);
            return result;
        }

        select() {
            const result = super.select();
            update_size_badge.call(this);
            return result;
        }

        /**
         * Removing a widget while editing can be undone during a few seconds:
         * the widget is hidden and removed when the toast is dismissed.
         */
        remove() {
            if (this._pendingRemoval != null) {
                return this;
            }

            if (!this.tab.workspace.editing) {
                return super.remove();
            }

            const workspace = this.tab.workspace;
            if (workspace.selectedWidget === this) {
                workspace.selectWidget(null);
            }

            this.wrapperElement.classList.add('wc-widget-removing');
            const commit = () => {
                window.removeEventListener('beforeunload', commit);
                if (this._pendingRemoval != null) {
                    this._pendingRemoval = null;
                    Wirecloud.ui.WidgetView.prototype.remove.call(this);
                }
            };
            this._pendingRemoval = commit;
            window.addEventListener('beforeunload', commit);

            Industry.toast(utils.interpolate(utils.gettext("Removed “%(title)s”"), {title: this.title}), {
                actionLabel: utils.gettext("Undo"),
                action: () => {
                    window.removeEventListener('beforeunload', commit);
                    this._pendingRemoval = null;
                    this.wrapperElement.classList.remove('wc-widget-removing');
                },
                onclose: commit,
                duration: REMOVE_DELAY
            });

            return this;
        }

    };

    // =========================================================================
    // Status bar
    // =========================================================================

    const StatusBar = class StatusBar {

        constructor() {
            this.wrapperElement = null;
        }

        init() {
            this.wrapperElement = document.getElementById('wc-statusbar');
            if (this.wrapperElement == null) {
                return;
            }

            this.iconElement = Industry.icon('eye');
            this.messageElement = Industry.element('span', 'wc-statusbar-message');
            this.countsElement = Industry.element('div', 'wc-statusbar-counts');
            this.wrapperElement.appendChild(Industry.element('span', 'wc-statusbar-state', [this.iconElement, this.messageElement]));
            this.wrapperElement.appendChild(Industry.element('div', 'wc-statusbar-spacer'));
            this.wrapperElement.appendChild(this.countsElement);

            Wirecloud.addEventListener('viewcontextchanged', () => this.refresh());
        }

        refresh() {
            if (this.wrapperElement == null) {
                return;
            }

            const uim = Wirecloud.UserInterfaceManager;
            const workspace = Wirecloud.activeWorkspace;
            // Computed from the views: this may run before data-wc-mode is updated
            const view = uim.getCurrentView();
            let mode = null;
            if (view != null && view.view_name === 'wiring') {
                mode = 'wiring';
            } else if (view == null || view.view_name == null || view.view_name === 'workspace') {
                mode = uim.views.workspace != null && uim.views.workspace.editing ? 'edit' : 'view';
            }
            const visible = workspace != null && (mode === 'view' || mode === 'edit' || mode === 'wiring');
            this.wrapperElement.classList.toggle('hidden', !visible);
            if (!visible) {
                return;
            }

            let icon, message;
            if (mode === 'edit') {
                icon = 'check';
                message = utils.gettext("All changes saved");
            } else if (mode === 'wiring') {
                icon = 'workflow';
                message = Wirecloud.currentTheme.config.wiring_click_to_connect ?
                    utils.gettext("Click an output, then an input to connect · click a connection to remove it") :
                    utils.gettext("Drag from an output to an input to connect · click a connection to remove it");
            } else {
                icon = 'eye';
                message = utils.gettext("View mode");
            }
            this.iconElement.className = 'lc-icon lc-' + icon;
            this.messageElement.textContent = message;

            const widgets = workspace.widgets.length;
            const operators = workspace.operators.length;
            const connections = workspace.wiring.connections.length;

            this.countsElement.innerHTML = '';
            this.countsElement.appendChild(Industry.element('span', null, [
                utils.interpolate(utils.ngettext("%(count)s widget", "%(count)s widgets", widgets), {count: widgets})
            ]));
            this.countsElement.appendChild(Industry.element('span', null, [
                utils.interpolate(utils.ngettext("%(count)s operator", "%(count)s operators", operators), {count: operators})
            ]));

            const connectionsLabel = utils.interpolate(utils.ngettext("%(count)s connection", "%(count)s connections", connections), {count: connections});
            if (mode !== 'wiring' && workspace.isAllowed('edit') && !Industry.isAnonymous()) {
                this.countsElement.appendChild(Industry.button({
                    className: 'wc-statusbar-link',
                    label: connectionsLabel + ' →',
                    title: utils.gettext("Open wiring"),
                    onclick: () => uim.changeCurrentView('wiring')
                }));
            } else {
                this.countsElement.appendChild(Industry.element('span', null, [connectionsLabel]));
            }
        }

    };

    Industry.statusBar = new StatusBar();

    Wirecloud.ui.registry.register('WorkspaceView', Industry.WorkspaceView);
    Wirecloud.ui.registry.register('EmbedCodeWindowMenu', Industry.EmbedCodeWindowMenu);
    Wirecloud.ui.registry.register('WidgetView', Industry.WidgetView);

})(Wirecloud.ui.Industry, StyledElements, Wirecloud.Utils);
