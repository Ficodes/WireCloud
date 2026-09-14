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

/* globals Wirecloud */


(function (ns, se, utils) {

    "use strict";

    const privates = new WeakMap();

    const compute_minimized_rows = function compute_minimized_rows() {
        const dragboard = this.tab.dragboard;
        const heading = this.heading;

        let marginTop = 0, marginBottom = 0;
        if (heading != null && typeof window !== 'undefined' && window.getComputedStyle) {
            const style = window.getComputedStyle(heading);
            marginTop = parseFloat(style.marginTop) || 0;
            marginBottom = parseFloat(style.marginBottom) || 0;
        }

        const grid = (this.wrapperElement && this.wrapperElement.gridstackNode && this.wrapperElement.gridstackNode.grid) || dragboard.grid;
        const cellHeightPx = (grid != null && grid.getCellHeight(true)) || dragboard.cellheight || 1;
        const headingHeight = (heading != null) ? heading.offsetHeight : 0;

        return Math.max(1, Math.ceil((headingHeight + marginTop + marginBottom) / cellHeightPx));
    };

    const update_classes = function update_classes() {
        const layout = this.layout || {};

        this.wrapperElement.classList.toggle('wc-missing-widget', this.model.missing);
        this.wrapperElement.classList.toggle('wc-moveable-widget', this.canMove);
        this.wrapperElement.classList.toggle('wc-titled-widget', !!layout.titlevisible);
        this.wrapperElement.classList.toggle('wc-minimized-widget', !!layout.minimized);
        this.wrapperElement.classList.toggle('wc-widget-fulldragboard', !!layout.fulldragboard);
    };

    const update_tab_fulldragboard_class = function update_tab_fulldragboard_class(view) {
        const anyFulldragboard = view.tab.dragboard.views.some((v) => v.layout != null && v.layout.fulldragboard);
        view.tab.wrapperElement.classList.toggle('wc-fulldragboard-active', anyFulldragboard);
    };

    const update_buttons = function update_buttons() {
        const editing = this.tab.workspace.editing;
        const role = editing ? "editor" : "viewer";
        const layout = this.layout || {};

        if (this.grip) {
            const visible = editing && !this.model.volatile;
            this.grip.hidden = !visible;
            if (visible) {
                const moveable = this.model.isAllowed('move', 'viewer');
                this.grip.icon.classList.toggle("fa-anchor", !moveable);
                this.grip.icon.classList.toggle("fa-grip-vertical", moveable);
                this.grip.setTitle(moveable ? utils.gettext("Disallow to move this widget") : utils.gettext("Allow to move this widget"));
            }
        }

        if (this.titlevisibilitybutton) {
            this.titlevisibilitybutton.hidden = !editing;
            this.titlevisibilitybutton.enabled = (!this.model.volatile && !layout.minimized && editing);
            this.titlevisibilitybutton.setTitle(layout.titlevisible ? utils.gettext("Hide title") : utils.gettext("Show title"));
            if (layout.titlevisible) {
                this.titlevisibilitybutton.replaceIconClassName("fa-eye-slash", "fa-eye");
            } else {
                this.titlevisibilitybutton.replaceIconClassName("fa-eye", "fa-eye-slash");
            }
        }

        if (this.minimizebutton) {
            this.minimizebutton.enabled = this.model.isAllowed('minimize', role);
        }

        this.closebutton.hidden = !(this.model.volatile || editing) || !this.model.isAllowed('close', role);
        this.menubutton.hidden = !editing;
    };

    const notify_context = function notify_context() {
        const node = this.wrapperElement.gridstackNode || {};
        const layout = this.layout || {};

        this.model.contextManager.modify({
            xPosition: (node.x != null) ? node.x : 0,
            yPosition: (node.y != null) ? node.y : 0,
            zPosition: 0,
            width: (node.w != null) ? node.w : 0,
            height: (node.h != null) ? node.h : 0,
            widthInPixels: this.wrapperElement.offsetWidth,
            heightInPixels: this.wrapperElement.offsetHeight,
            visible: layout.visible !== false && !layout.minimized && !this.tab.hidden && !this.tab.workspace.hidden
        });
    };

    // =========================================================================
    // EVENT HANDLERS
    // =========================================================================

    /**
     * Applies a change of one of the layout flags (minimized, titlevisible,
     * fulldragboard) and stores the resulting layout in the model. The whole
     * current layout is stored (not only the changed flag) so that a screen
     * size that had no stored layout yet keeps the derived position and size.
     *
     * @private
     */
    const change_layout_flag = function change_layout_flag(changes, persist) {
        const activeId = String(this.tab.dragboard.activeScreenSize.id);
        const newLayout = utils.merge(utils.clone(this.layout || {}, true), changes);

        this.applyLayout(newLayout);

        return this.model.setLayout(activeId, this.currentLayout, persist).then(() => this);
    };

    const on_add_log = function on_add_log() {
        const errorCount = this.model.logManager.errorCount;
        this.errorbutton.hidden = errorCount === 0;

        const label = utils.interpolate(
            utils.ngettext("%(errorCount)s error", "%(errorCount)s errors", errorCount),
            {errorCount: errorCount},
            true
        );
        this.errorbutton.setTitle(label);
    };

    ns.WidgetView = class WidgetView extends se.StyledElement {

        /**
         * @name Wirecloud.UI.WidgetView
         *
         * @extends {StyledElements.StyledElement}
         * @constructor
         *
         * @param {Wirecloud.UI.WorkspaceTabView} tab
         * @param {Wirecloud.Widget} model
         * @param {Object} [options]
         */
        constructor(tab, model, options) {
            super([
                'highlight',
                'remove',
                'unhighlight'
            ]);

            options = utils.merge({
                template: Wirecloud.currentTheme.templates['wirecloud/workspace/widget']
            }, options);

            privates.set(this, {
                tab: tab,
                layout: null
            });

            Object.defineProperties(this, {
                id: {
                    value: model.id
                },
                /**
                 * The layout currently applied to this widget view:
                 * `{x, y, w, h, minimized, titlevisible, fulldragboard, visible}`.
                 *
                 * @memberOf Wirecloud.ui.WidgetView#
                 * @type {Object}
                 */
                layout: {
                    get: function () {
                        return privates.get(this).layout;
                    },
                    set: function (value) {
                        privates.get(this).layout = value;
                    }
                },
                model: {
                    value: model
                },
                tab: {
                    get: function () {
                        return privates.get(this).tab;
                    },
                    set: function (value) {
                        privates.get(this).tab = value;
                    }
                },
                title: {
                    get: () => {
                        return this.model.title;
                    }
                }
            });

            this.wrapperElement = (new se.GUIBuilder()).parse(options.template, {
                'closebutton': function (options, tcomponents, view) {
                    const button = new se.Button({
                        plain: true,
                        class: 'wc-remove',
                        iconClass: 'fas fa-times',
                        title: utils.gettext("Remove")
                    });

                    view.closebutton = button;
                    button.addEventListener('click', function () {
                        view.remove();
                    });
                    return button;
                },
                'errorbutton': function (options, tcomponents, view) {
                    const button = new StyledElements.Button({
                        plain: true,
                        class: 'errorbutton',
                        iconClass: 'fas fa-exclamation-triangle'
                    });

                    button.hide().addEventListener('click', function (button) {
                        const dialog = new Wirecloud.ui.LogWindowMenu(view.model.logManager);
                        dialog.show();
                    });
                    view.errorbutton = button;
                    return button;
                },
                'grip': (options, tcomponents, view) => {
                    view.grip = new StyledElements.Button({
                        plain: true,
                        class: 'wc-grip-button',
                        iconClass: 'fa-fw fas fa-grip-vertical'
                    });
                    view.grip.addEventListener('click', (button) => {
                        button.disable().addClassName('busy');
                        view.togglePermission('move', true).finally(() => {
                            button.enable().removeClassName('busy');
                        });
                    });
                    return view.grip;
                },
                'menubutton': function (options, tcomponents, view) {
                    const button = new StyledElements.PopupButton({
                        class: 'wc-menu-button',
                        iconClass: 'fas fa-cogs',
                        plain: true,
                        title: utils.gettext("Menu")
                    });

                    view.menubutton = button;
                    button.popup_menu.append(new ns.WidgetViewMenuItems(view));
                    return button;
                },
                'minimizebutton': function (options, tcomponents, view) {
                    const button = new StyledElements.Button({
                        iconClass: 'fas fa-minus',
                        plain: true,
                        title: utils.gettext("Minimize")
                    });

                    button.enable = view.model.isAllowed('minimize');
                    button.addEventListener('click', function (button) {
                        view.toggleMinimizeStatus(true);
                    });
                    view.minimizebutton = button;
                    return button;
                },
                'title': function (options, tcomponents, view) {
                    const element = new StyledElements.EditableElement({initialContent: view.model.title});

                    element.addEventListener('change', function (element, new_title) {
                        view.model.rename(new_title);
                    });
                    view.titleelement = element;
                    return element;
                },
                'titlevisibilitybutton': (options, tcomponents, view) => {
                    const button = new StyledElements.Button({
                        plain: true,
                        class: 'wc-titlevisibility-button',
                        iconClass: 'fa-fw fas fa-eye-slash'
                    });

                    button.addEventListener('click', (button) => {
                        view.toggleTitleVisibility(true);
                    });
                    view.titlevisibilitybutton = button;
                    return button;
                },
                'iframe': function (options, tcomponents, view) {
                    return view.model.wrapperElement;
                }
            }, this).children[1];

            this.wrapperElement.classList.add("wc-widget", "grid-stack-item");
            this.wrapperElement.setAttribute('data-id', model.id);

            this.contentElement = this.wrapperElement.children[0];
            this.heading = this.wrapperElement.getElementsByClassName('wc-widget-heading')[0];

            model.addEventListener('change', (widget, changes) => {
                if (changes.indexOf('title') !== -1) {
                    this.titleelement.setTextContent(widget.title);
                }

                if (changes.indexOf('meta') !== -1) {
                    update_classes.call(this);
                    update_buttons.call(this);
                }

                if (changes.indexOf('permissions') !== -1) {
                    update_classes.call(this);
                    update_buttons.call(this);
                    this.updateGridPermissions();
                }
            });

            model.addEventListener('unload', () => {
                this.unhighlight();
            });

            model.addEventListener('load', () => {
                this.contentElement.classList.add('in');

                const containerToListen = (model.meta.macversion > 1) ? model.wrapperElement : model.wrapperElement.contentDocument.defaultView;

                containerToListen.addEventListener('keydown', (event) => {
                    if (event.keyCode === 27) { // escape
                        Wirecloud.UserInterfaceManager.handleEscapeEvent();
                    }
                }, true);

                containerToListen.addEventListener('click', () => {
                    Wirecloud.UserInterfaceManager.handleEscapeEvent(true);
                    this.unhighlight();
                }, true);

                this.repaint();
            });

            model.addEventListener('remove', () => {
                this.tab.dragboard.removeWidget(this);
                this.dispatchEvent('remove');
            });

            this.model.logManager.addEventListener('newentry', on_add_log.bind(this));

            this.tab.workspace.addEventListener('editmode', () => {
                update_classes.call(this);
                update_buttons.call(this);
                this.updateGridPermissions();
            });

            this.tab.workspace.addEventListener('show', () => notify_context.call(this));
            this.tab.workspace.addEventListener('hide', () => notify_context.call(this));
            this.tab.addEventListener('show', () => notify_context.call(this));
            this.tab.addEventListener('hide', () => notify_context.call(this));

            this.tab.dragboard.addWidget(this);

            update_classes.call(this);
            update_buttons.call(this);
        }

        /**
         * The `{x, y, w, h, minimized, titlevisible, fulldragboard, visible}`
         * object that should be persisted for the active screen size: `x`/`y`/`w`/`h`
         * are read from the underlying GridStack node (when minimized, `h` is
         * the remembered un-minimized height, not the collapsed one).
         *
         * @type {Object}
         */
        get currentLayout() {
            const node = this.wrapperElement.gridstackNode || {};
            const layout = this.layout || {};

            const result = {
                x: (node.x != null) ? node.x : layout.x,
                y: (node.y != null) ? node.y : layout.y,
                w: (node.w != null) ? node.w : layout.w,
                h: layout.minimized ? (this._unminimizedHeight != null ? this._unminimizedHeight : layout.h) : ((node.h != null) ? node.h : layout.h),
                minimized: !!layout.minimized,
                titlevisible: !!layout.titlevisible,
                fulldragboard: !!layout.fulldragboard,
                visible: layout.visible !== false
            };

            if (layout.dock != null) {
                result.dock = layout.dock;
                result.dock_mode = layout.dock_mode || 'overlay';
                result.dock_open = layout.dock_open !== false;
            } else if (layout.dock === null && ('dock' in layout)) {
                result.dock = null;
            }

            return result;
        }

        get canMove() {
            const layout = this.layout || {};
            if (layout.fulldragboard) {
                return false;
            }
            const role = this.tab.workspace.editing ? 'editor' : 'viewer';
            return this.model.isAllowed('move', role);
        }

        get canResize() {
            const layout = this.layout || {};
            if (layout.fulldragboard || layout.minimized) {
                return false;
            }
            const role = this.tab.workspace.editing ? 'editor' : 'viewer';
            return this.model.isAllowed('resize', role);
        }

        /**
         * Applies a resolved layout (as produced by
         * `Wirecloud.ui.WorkspaceTabViewDragboard#resolveLayout`) to this view:
         * updates its CSS classes/buttons, collapses/restores it if
         * minimized, refreshes its move/resize permissions and re-notifies
         * the widget context.
         *
         * @param {Object} layout
         *
         * @returns {Wirecloud.ui.WidgetView}
         */
        applyLayout(layout) {
            this.layout = layout;

            if (!layout.minimized || this._unminimizedHeight == null) {
                this._unminimizedHeight = layout.h;
            }

            update_classes.call(this);
            update_buttons.call(this);
            update_tab_fulldragboard_class(this);

            const grid = (this.wrapperElement.gridstackNode && this.wrapperElement.gridstackNode.grid) || this.tab.dragboard.grid;
            if (this.wrapperElement.gridstackNode != null && grid != null) {
                this.tab.dragboard.withApplying(() => {
                    if (layout.minimized) {
                        const rows = compute_minimized_rows.call(this);
                        grid.update(this.wrapperElement, {h: rows, noResize: true});
                    } else {
                        grid.update(this.wrapperElement, {h: layout.h});
                    }
                });
            }

            this.updateGridPermissions();
            notify_context.call(this);

            return this;
        }

        /**
         * Refreshes `layout.x/y/w/h` from the underlying GridStack node after
         * the user moved or resized the widget (when minimized, the height is
         * left untouched as the node holds the collapsed height).
         *
         * @returns {Wirecloud.ui.WidgetView}
         */
        syncLayoutFromNode() {
            const node = this.wrapperElement.gridstackNode;
            const layout = this.layout;

            if (node == null || layout == null) {
                return this;
            }

            layout.x = node.x;
            layout.y = node.y;
            layout.w = node.w;
            if (!layout.minimized) {
                layout.h = node.h;
                this._unminimizedHeight = node.h;
            }

            return this;
        }

        /**
         * Refreshes this widget's `noMove`/`noResize` GridStack node options
         * from its current permissions.
         */
        updateGridPermissions() {
            const dragboard = this.tab.dragboard;
            const grid = (this.wrapperElement.gridstackNode && this.wrapperElement.gridstackNode.grid) || dragboard.grid;

            if (grid == null || this.wrapperElement.gridstackNode == null) {
                return;
            }

            dragboard.withApplying(() => {
                grid.update(this.wrapperElement, {
                    noMove: !this.canMove,
                    noResize: !this.canResize
                });
            });
        }

        /**
         * @param {Boolean} [persist]
         *
         * @returns {Promise}
         */
        toggleMinimizeStatus(persist) {
            return this.setMinimizeStatus(!(this.layout && this.layout.minimized), persist);
        }

        /**
         * @param {Boolean} status
         * @param {Boolean} [persist]
         *
         * @returns {Promise}
         */
        setMinimizeStatus(status, persist) {
            status = !!status;

            if (this.layout != null && status === !!this.layout.minimized) {
                return Promise.resolve(this);
            }

            return change_layout_flag.call(this, {minimized: status}, persist);
        }

        /**
         * @param {Boolean} persistence save change on server
         *
         * @returns {Promise}
         */
        toggleTitleVisibility(persistence) {
            const newValue = !(this.layout && this.layout.titlevisible);

            this.titlevisibilitybutton.disable().addClassName('busy');

            return change_layout_flag.call(this, {titlevisible: newValue}, persistence).finally(() => {
                this.titlevisibilitybutton.enable().removeClassName('busy');
            });
        }

        /**
         * Enables/disables "full dragboard" mode (the widget covers the whole
         * tab).
         *
         * @param {Boolean} enable
         * @param {Boolean} [persist]
         *
         * @returns {Promise}
         */
        setFullDragboardMode(enable, persist) {
            enable = !!enable;

            if (this.layout != null && enable === !!this.layout.fulldragboard) {
                return Promise.resolve(this);
            }

            if (enable) {
                // The widget covers the visible area of the tab, starting at its top
                this.tab.wrapperElement.scrollTop = 0;
            }

            return change_layout_flag.call(this, {fulldragboard: enable}, persist);
        }

        /**
         * Hides this widget for the current screen size.
         *
         * @returns {Promise}
         */
        hideInCurrentScreenSize() {
            // The whole layout is stored (not just the flag) so that the
            // widget comes back to the same place when shown again, and so
            // that the other screen sizes, which may derive their layout from
            // this one, keep showing the widget.
            return change_layout_flag.call(this, {visible: false}, true).then(() => {
                this.tab.dragboard.refreshWidget(this);
                return this;
            });
        }

        /**
         * Shows this widget again for the current screen size.
         *
         * @returns {Promise}
         */
        showInCurrentScreenSize() {
            return change_layout_flag.call(this, {visible: true}, true).then(() => {
                this.tab.dragboard.refreshWidget(this);
                return this;
            });
        }

        /**
         * Moves this widget to another tab.
         *
         * @param {Wirecloud.ui.WorkspaceTabView} tabView
         *
         * @returns {Promise}
         */
        moveToTab(tabView) {
            return this.tab.dragboard.moveWidgetToTab(this, tabView);
        }

        /**
         * @returns {Boolean} whether this widget view is currently docked onto a side
         */
        isDocked() {
            return !!(this.layout && this.layout.dock);
        }

        /**
         * Docks this widget onto one of the sides ('left', 'right', 'top', 'bottom').
         *
         * @param {String} position
         * @param {String} [mode='overlay'] 'overlay' or 'push'
         * @param {Boolean} [persist=true]
         *
         * @returns {Promise}
         */
        dockTo(position, mode = 'overlay', persist = true) {
            return this.tab.dragboard.dockWidget(this, position, mode, persist);
        }

        /**
         * Undocks this widget, returning it to the main grid.
         *
         * @param {Boolean} [persist=true]
         *
         * @returns {Promise}
         */
        undock(persist = true) {
            return this.tab.dragboard.undockWidget(this, persist);
        }

        /**
         * Sets the display mode ('overlay' or 'push') for this docked widget.
         *
         * @param {String} mode
         * @param {Boolean} [persist=true]
         *
         * @returns {Promise}
         */
        setDockMode(mode, persist = true) {
            return this.tab.dragboard.setWidgetDockMode(this, mode, persist);
        }

        /**
         * Toggles the open/closed state of this docked widget.
         *
         * @param {Boolean} [persist=true]
         *
         * @returns {Promise}
         */
        toggleDockOpen(persist = true) {
            return this.tab.dragboard.toggleWidgetDockOpen(this, persist);
        }

        /**
         * Toggles a widget permission
         *
         * @param {String} permission permission to toggle
         * @param {Boolean} persistence save change on server
         *
         * @return {Wirecloud.Task} task instance controlling the progress
         */
        togglePermission(permission, persistence) {
            const changes = {
                [permission]: !this.model.permissions.viewer[permission]
            };
            return this.model.setPermissions(changes, persistence);
        }

        load() {
            if (!this.model.loaded) {
                this.contentElement.classList.add('in');
                this.model.load();
            }

            return this.repaint();
        }

        /**
         * Re-notifies the widget context (position/size/visibility).
         */
        repaint() {
            notify_context.call(this);
            return this;
        }

        reload() {
            this.model.reload();
            return this;
        }

        showLogs() {
            this.model.showLogs();
            return this;
        }

        showSettings() {
            this.model.showSettings();
            return this;
        }

        highlight() {
            this.contentElement.classList.add('panel-success');
            this.contentElement.classList.remove('panel-default');
            if (!this.wrapperElement.classList.contains('wc-widget-highlight')) {
                this.wrapperElement.classList.add('wc-widget-highlight');
                this.dispatchEvent('highlight');
            } else {
                // Reset highlighting animation
                this.wrapperElement.classList.remove('wc-widget-highlight');
                setTimeout(() => {
                    this.wrapperElement.classList.add('wc-widget-highlight');
                });
            }

            return this;
        }

        unhighlight() {
            this.contentElement.classList.remove('panel-success');
            this.contentElement.classList.add('panel-default');
            if (this.wrapperElement.classList.contains('wc-widget-highlight')) {
                this.wrapperElement.classList.remove('wc-widget-highlight');
                this.dispatchEvent('unhighlight');
            }

            return this;
        }

        toJSON() {
            const activeId = String(this.tab.dragboard.activeScreenSize.id);
            return {
                id: this.id,
                layouts: {
                    [activeId]: this.currentLayout
                }
            };
        }

        remove() {
            this.model.remove();
            return this;
        }

    }

})(Wirecloud.ui, StyledElements, StyledElements.Utils);
