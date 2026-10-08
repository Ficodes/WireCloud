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


(function (ns, se, utils) {

    "use strict";

    const privates = new WeakMap();

    const _create_widget = function _create_widget(model) {
        const widget = new Wirecloud.ui.WidgetView(this, model);

        privates.get(this).widgets.push(widget);

        return widget;
    };

    const get_widgets_by_id = function get_widgets_by_id() {
        const widgets = {};

        privates.get(this).widgets.forEach(function (widget) {
            widgets[widget.id] = widget;
        });

        return widgets;
    };

    // =========================================================================
    // EVENT HANDLERS
    // =========================================================================

    const on_changetab = function on_changetab(tab, changes) {
        if (changes.indexOf('title') !== -1) {
            se.Tab.prototype.rename.call(this, tab.title);
        }

        if (changes.indexOf('name') !== -1 && !this.hidden) {
            this.tabElement.setAttribute('data-name', this.name);
            const currentState = Wirecloud.HistoryManager.getCurrentState();
            const newState = utils.merge({}, currentState, {
                tab: tab.name
            });
            Wirecloud.HistoryManager.replaceState(newState);
        }
    };

    const on_addwidget = function on_addwidget(tab, model, view) {
        const priv = privates.get(this);

        if (view == null) {
            view = _create_widget.call(this, model);

            if (!this.hidden) {
                view.load();
            }
        } else {
            priv.widgets.push(view);
            this.dragboard.addWidget(view);
        }
        this.initialMessage.hidden = true;
    };

    const on_removetab = function on_removetab(model) {
        se.Tab.prototype.close.call(this);
    };

    const on_removewidget = function on_removewidget(tab, widgetModel) {
        const priv = privates.get(this);
        const view = priv.widgets.find((v) => v.id === widgetModel.id);
        if (view != null) {
            priv.widgets.splice(priv.widgets.indexOf(view), 1);
        }
        this.initialMessage.hidden = !this.workspace.model.isAllowed("edit") || priv.widgets.length > 0;
    };

    const update_pref_button = function update_pref_button() {
        this.prefbutton.enabled = this.workspace.editing;
    };

    const on_windowresize = function on_windowresize() {
        if (this.workspace.activeTab === this) {
            this.updateEditingScreenSizeName();
            this.workspace.updateEditingInterval(this.getEditingScreenSizeElement());
        }
    };

    ns.WorkspaceTabView = class WorkspaceTabView extends se.Tab {

        constructor(id, notebook, options) {
            const model = options.model,
                workspace = options.workspace;

            super(id, notebook, {
                closable: false,
                name: model.title
            });

            const priv = {
                widgets: [],
                on_changetab: on_changetab.bind(this),
                on_addwidget: on_addwidget.bind(this),
                on_removetab: on_removetab.bind(this),
                on_removewidget: on_removewidget.bind(this),
                on_windowresize: on_windowresize.bind(this)
            };
            privates.set(this, priv);

            Object.defineProperties(this, {
                /**
                 * @memberOf Wirecloud.ui.WorkspaceTabView#
                 * @type {String}
                 */
                id: {
                    value: model.id
                },
                /**
                 * @memberOf Wirecloud.ui.WorkspaceTabView#
                 * @type {Wirecloud.LogManager}
                 */
                logManager: {
                    value: new Wirecloud.LogManager(Wirecloud.GlobalLogManager)
                },
                /**
                 * @memberOf Wirecloud.ui.WorkspaceTabView#
                 * @type {Wirecloud.WorkspaceTab}
                 */
                model: {
                    value: model
                },
                /**
                 * @memberOf Wirecloud.ui.WorkspaceTabView#
                 * @type {String}
                 */
                name: {
                    get: function () {
                        return this.model.name;
                    }
                },
                /**
                 * @memberOf Wirecloud.ui.WorkspaceTabView#
                 * @type {String}
                 */
                title: {
                    get: function () {
                        return this.model.title;
                    }
                },
                /**
                 * @memberOf Wirecloud.ui.WorkspaceTabView#
                 * @type {Array.<Wirecloud.ui.WidgetView>}
                 */
                widgets: {
                    get: function () {
                        return priv.widgets.slice(0);
                    }
                },
                /**
                 * @memberOf Wirecloud.ui.WorkspaceTabView#
                 * @type {Object.<String, Wirecloud.ui.WidgetView>}
                 */
                widgetsById: {
                    get: function () {
                        return get_widgets_by_id.call(this);
                    }
                },
                /**
                 * @memberOf Wirecloud.ui.WorkspaceTabView#
                 * @type {Wirecloud.ui.WorkspaceView}
                 */
                workspace: {
                    value: workspace
                }
            });

            this.tabElement.classList.add("wc-workspace-tab");
            this.tabElement.setAttribute('data-id', this.id);
            this.tabElement.setAttribute('data-name', this.name);

            this.wrapperElement.classList.add("wc-workspace-tab-content");
            this.wrapperElement.setAttribute('data-id', this.id);

            if (this.workspace.model.isAllowed("edit")) {
                this.prefbutton = new se.PopupButton({
                    title: utils.gettext("Preferences"),
                    class: 'icon-tab-menu',
                    iconClass: 'fa fa-caret-up',
                    plain: true,
                    menuOptions: {
                        position: ['top-left', 'top-right']
                    }
                });
                this.prefbutton.popup_menu.append(new ns.WorkspaceTabViewMenuItems(this));
                this.prefbutton.insertInto(this.tabElement);
                this.workspace.addEventListener('editmode', update_pref_button.bind(this));
                update_pref_button.call(this);
            }

            this.dragboard = new ns.WorkspaceTabViewDragboard(this);
            this.updateEditingScreenSizeName();

            this.initialMessage = (new se.GUIBuilder()).parse(Wirecloud.currentTheme.templates['wirecloud/workspace/empty_tab_message'], {
                button: this.workspace.buildAddWidgetButton.bind(this.workspace),
                tutorials: Wirecloud.TutorialCatalogue.buildTutorialReferences(['basic-concepts'])
            }).children[1];
            this.appendChild(this.initialMessage);

            this.model.widgets.forEach(_create_widget, this);
            this.initialMessage.hidden = !this.workspace.model.isAllowed("edit") || this.widgets.length > 0;

            this.model.addEventListener('change', priv.on_changetab);
            this.model.addEventListener('addwidget', priv.on_addwidget);
            this.model.addEventListener('remove', priv.on_removetab);
            this.model.addEventListener('removewidget', priv.on_removewidget);
            window.addEventListener('resize', priv.on_windowresize);
        }

        /**
         * @param {Wirecloud.WidgetMeta} resource
         * @param {Object} [options]
         * @param {String} [options.title]
         * @param {Boolean} [options.commit]
         * @param {Number} [options.x]
         * @param {Number} [options.y]
         * @param {Number} [options.w]
         * @param {Number} [options.h]
         * @param {Number|String} [options.width] px/%/old-cells, converted via `dragboard.parseSize`
         * @param {Number|String} [options.height] px/%/old-cells, converted via `dragboard.parseSize`
         * @param {Boolean} [options.titlevisible]
         * @param {Object} [options.permissions]
         * @param {Boolean} [options.volatile]
         * @param {String} [options.id]
         * @param {Object} [options.layouts] explicit `{screenSizeId(string): layout}`, used as is when given
         *
         * @returns {Promise} A promise that returns a {Widget} instance if
         * resolved, or an Error if rejected.
         */
        createWidget(resource, options) {
            options = utils.merge({
                commit: true
            }, options);

            if (options.title == null) {
                options.title = resource.title;
            }

            if (options.layouts == null) {
                const screenSize = this.dragboard.activeScreenSize;
                const activeId = String(screenSize.id);

                let w;
                if (options.w != null) {
                    w = options.w;
                } else {
                    w = this.dragboard.parseSize(options.width != null ? options.width : resource.default_width, 'w');
                }

                let h;
                if (options.h != null) {
                    h = options.h;
                } else {
                    h = this.dragboard.parseSize(options.height != null ? options.height : resource.default_height, 'h');
                }

                options.layouts = {
                    [activeId]: {
                        x: options.x != null ? options.x : null,
                        y: options.y != null ? options.y : null,
                        w: w,
                        h: h,
                        minimized: false,
                        titlevisible: options.titlevisible != null ? options.titlevisible : true,
                        fulldragboard: false,
                        visible: true
                    }
                };
            }

            if (!options.commit) {
                return this.findWidget(this.model.createWidget(resource, options).id);
            }

            return this.model.createWidget(resource, options).then(
                (model) => {
                    return Promise.resolve(this.findWidget(model.id));
                }
            );
        }

        /**
         * Builds the header addon shown while editing a specific screen size.
         *
         * @returns {HTMLElement}
         */
        getEditingScreenSizeElement() {
            let text = "";
            if (this.dragboard.forcedScreenSizeId != null) {
                text = utils.interpolate(utils.gettext("(Overriden) Editing for screen size %(name)s"), {name: this.editingScreenSizeName});
            } else {
                text = utils.interpolate(utils.gettext("Editing for screen size %(name)s"), {name: this.editingScreenSizeName});
            }

            const div = document.createElement('div');
            div.setAttribute('role', 'status');
            div.setAttribute('aria-live', 'polite');
            const span = document.createElement('span');
            span.textContent = text;
            div.appendChild(span);

            if (this.dragboard.forcedScreenSizeId != null) {
                const a = document.createElement('a');
                a.className = 'far fa-times-circle wc-editing-interval-close';
                a.href = '#';
                a.setAttribute('role', 'button');
                a.setAttribute('aria-label', utils.gettext('Quit editing interval'));
                a.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.quitEditingScreenSize();
                });
                div.appendChild(a);
            }

            return div;
        }

        /**
         * Forces this tab to be edited/rendered for a specific screen size,
         * regardless of the current tab width.
         *
         * @param {Number} id
         */
        setEditingScreenSize(id) {
            const screenSize = this.model.preferences.get('screenSizes').find((entry) => entry.id === id);
            if (screenSize == null) {
                return;
            }

            this.dragboard.setForcedScreenSize(id);

            const width = (screenSize.lessOrEqual !== -1) ? screenSize.lessOrEqual : Math.max(screenSize.moreOrEqual, window.innerWidth);
            this.wrapperElement.style.width = width + 'px';
            this.wrapperElement.classList.add('wc-editing-screen-size');

            this.editingScreenSizeName = screenSize.name;
            this.workspace.updateEditingInterval(this.getEditingScreenSizeElement());
        }

        /**
         * Reverts {@link #setEditingScreenSize}.
         */
        quitEditingScreenSize() {
            // Restore the real width before re-detecting the screen size
            this.wrapperElement.style.width = '';
            this.wrapperElement.classList.remove('wc-editing-screen-size');
            this.dragboard.setForcedScreenSize(null);

            this.updateEditingScreenSizeName();
            this.workspace.updateEditingInterval(this.getEditingScreenSizeElement());
        }

        /**
         * Refreshes `this.editingScreenSizeName` from the dragboard's active
         * screen size.
         */
        updateEditingScreenSizeName() {
            this.editingScreenSizeName = this.dragboard.activeScreenSize.name;
        }

        /**
         * Highlights this tab
         */
        highlight() {
            this.tabElement.classList.add("highlight");
            return this;
        }

        /**
         * @param {String} id
         *
         * @returns {*}
         */
        findWidget(id) {
            return this.widgetsById[id];
        }

        repaint() {
            this.dragboard.paint();
            return this;
        }

        show() {
            super.show(this);

            privates.get(this).widgets.forEach(function (widget) {
                widget.load();
            });

            this.updateEditingScreenSizeName();
            this.workspace.updateEditingInterval(this.getEditingScreenSizeElement());

            return this.repaint();
        }

        showSettings() {
            (new Wirecloud.ui.PreferencesWindowMenu('tab', this.model.preferences)).show();
            return this;
        }

        unhighlight() {
            this.tabElement.classList.remove("highlight");
            return this;
        }

    }

})(Wirecloud.ui, StyledElements, StyledElements.Utils);
