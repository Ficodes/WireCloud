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


(function (ns, utils) {

    "use strict";

    const DEFAULT_COLUMNS = 12;

    const clamp = function clamp(value, min, max) {
        return Math.min(Math.max(value, min), max);
    };

    const normalize_screen_size = function normalize_screen_size(screenSize) {
        return {
            id: screenSize.id,
            name: screenSize.name,
            moreOrEqual: screenSize.moreOrEqual,
            lessOrEqual: screenSize.lessOrEqual,
            columns: (screenSize.columns != null) ? screenSize.columns : DEFAULT_COLUMNS
        };
    };

    /**
     * Derives the layout for a screen size from the layout stored for another
     * one: sizes are scaled by the column ratio, while `x`/`y` are only kept
     * as ordering hints (`derived: true` makes the widget auto-placed in
     * reading order, so the widgets reflow left to right instead of piling up
     * where the scaled positions collide).
     *
     * Visibility is never inherited: hiding a widget is a decision taken for
     * one specific screen size, so a screen size that has no layout of its own
     * always shows the widget.
     *
     * @private
     */
    const scale_layout = function scale_layout(layout, sourceScreenSize, targetScreenSize) {
        const ratio = targetScreenSize.columns / sourceScreenSize.columns;
        const w = clamp(Math.round(layout.w * ratio), 1, targetScreenSize.columns);
        const x = (layout.x == null) ? null : clamp(Math.round(layout.x * ratio), 0, Math.max(0, targetScreenSize.columns - w));

        const res = {
            x: x,
            y: layout.y,
            w: w,
            h: layout.h,
            minimized: layout.minimized,
            titlevisible: layout.titlevisible,
            fulldragboard: layout.fulldragboard,
            visible: true,
            derived: true
        };

        if (layout.dock != null) {
            res.dock = layout.dock;
            res.dock_mode = layout.dock_mode || 'overlay';
            res.dock_open = layout.dock_open === true;
        }

        return res;
    };

    const default_layout_for = function default_layout_for(screenSize, cellheight) {
        return {
            x: null,
            y: null,
            w: Math.min(screenSize.columns, Math.max(1, Math.round(screenSize.columns / 3))),
            h: Math.max(1, Math.round(300 / cellheight)),
            minimized: false,
            titlevisible: true,
            fulldragboard: false,
            visible: true
        };
    };

    // =========================================================================
    // EVENT HANDLERS
    // =========================================================================

    const on_grid_event = function on_grid_event() {
        if (this.applying) {
            return;
        }

        // Keep every view's layout in sync with what the user did on the grid
        this.views.forEach((view) => view.syncLayoutFromNode());

        if (!this.tab.workspace.editing) {
            return;
        }
        schedule_persist.call(this);
    };

    /**
     * While a widget is being dragged or resized the mouse events must keep
     * reaching the document: any widget iframe passing under the cursor would
     * otherwise swallow them, leaving the operation stuck half way. The class
     * added here makes the widget contents transparent to the pointer for as
     * long as the interaction lasts.
     *
     * @private
     */
    const on_interaction_start = function on_interaction_start() {
        this.gridElement.classList.add('wc-dragboard-interacting');
        if (this.tab && this.tab.wrapperElement) {
            this.tab.wrapperElement.classList.add('wc-dragboard-interacting');
        }
    };

    const on_interaction_end = function on_interaction_end() {
        this.gridElement.classList.remove('wc-dragboard-interacting');
        if (this.tab && this.tab.wrapperElement) {
            this.tab.wrapperElement.classList.remove('wc-dragboard-interacting');
        }
        on_grid_event.call(this);
    };

    /**
     * Places (or hides) a single widget view on the grid according to a
     * resolved layout. Must be called inside `withApplying` and a GridStack
     * batch.
     *
     * @private
     */
    const place_view = function place_view(view, layout, role) {
        const el = view.wrapperElement;

        if (layout.dock && this.docks && this.docks[layout.dock]) {
            if (el.gridstackNode != null && el.parentNode === this.gridElement) {
                this.grid.removeWidget(el, false, false);
            }
            Object.keys(this.docks).forEach((pos) => {
                if (pos !== layout.dock && this.docks[pos].views.includes(view)) {
                    this.docks[pos].removeWidget(view);
                }
            });
            this.docks[layout.dock].addWidget(view, layout, role);
            return;
        }

        if (this.docks) {
            Object.keys(this.docks).forEach((pos) => {
                if (this.docks[pos].views.includes(view)) {
                    this.docks[pos].removeWidget(view);
                }
            });
        }

        if (el.parentNode !== this.gridElement) {
            this.gridElement.appendChild(el);
        }

        if (!layout.visible) {
            if (el.gridstackNode != null) {
                this.grid.removeWidget(el, false, false);
            }
            el.hidden = true;
            view.applyLayout(layout);
            return;
        }

        el.hidden = false;

        const canMove = !layout.fulldragboard && view.model.isAllowed('move', role);
        const canResize = !layout.fulldragboard && !layout.minimized && view.model.isAllowed('resize', role);
        const autoPosition = layout.derived === true || layout.x == null || layout.y == null;

        const nodeOpts = {
            w: layout.w,
            h: layout.h,
            noMove: !canMove,
            noResize: !canResize
        };
        if (!autoPosition) {
            nodeOpts.x = layout.x;
            nodeOpts.y = layout.y;
        }

        if (el.gridstackNode != null && autoPosition) {
            // GridStack's update() cannot auto-place an existing node, re-add it instead
            this.grid.removeWidget(el, false, false);
        }

        if (el.gridstackNode == null) {
            this.grid.makeWidget(el, Object.assign({id: view.id, autoPosition: autoPosition}, nodeOpts));
        } else {
            this.grid.update(el, nodeOpts);
        }

        view.applyLayout(layout);
    };

    const schedule_persist = function schedule_persist() {
        if (this._persistTimeout != null) {
            return;
        }
        this._persistTimeout = setTimeout(() => {
            this._persistTimeout = null;
            this.persist();
        }, 0);
    };

    const on_resize = function on_resize() {
        if (this.grid == null || this.tab.wrapperElement.offsetWidth === 0) {
            return;
        }

        if (this.activeScreenSize.id !== this._lastAppliedScreenSizeId) {
            this.applyScreenSize();
        }
    };

    const on_preferences_commit = function on_preferences_commit(preferences, modifiedValues) {
        if ('cellheight' in modifiedValues) {
            this.cellheight = modifiedValues.cellheight;
            if (this.grid != null) {
                this.grid.cellHeight(this.cellheight);
            }
        }

        if ('margin' in modifiedValues) {
            this.margin = modifiedValues.margin;
            if (this.grid != null) {
                this.grid.margin(this.margin);
            }
        }

        if ('screenSizes' in modifiedValues) {
            on_screensizes_change.call(this);
        }
    };

    const on_screensizes_change = function on_screensizes_change() {
        const validIds = this.screenSizes.map((screenSize) => String(screenSize.id));
        const content = [];

        this.views.forEach((view) => {
            if (view.model.volatile) {
                return;
            }

            const layouts = view.model.layouts;
            const removedLayouts = {};
            let hasRemovals = false;

            Object.keys(layouts).forEach((id) => {
                if (validIds.indexOf(id) === -1) {
                    removedLayouts[id] = null;
                    hasRemovals = true;
                    view.model.removeLayout(id, false);
                }
            });

            if (hasRemovals) {
                content.push({id: view.id, layouts: removedLayouts});
            }
        });

        const finish = () => {
            this.applyScreenSize();
        };

        if (content.length === 0) {
            finish();
            return;
        }

        const url = Wirecloud.URLs.IWIDGET_COLLECTION.evaluate({
            workspace_id: this.tab.workspace.model.id,
            tab_id: this.tab.model.id
        });

        Wirecloud.io.makeRequest(url, {
            method: 'PUT',
            requestHeaders: {'Accept': 'application/json'},
            contentType: 'application/json',
            postBody: JSON.stringify(content)
        }).then(finish, finish);
    };

    const on_editmode = function on_editmode(workspace, editing) {
        this.setEditing(editing);
    };

    ns.WorkspaceTabViewDragboard = class WorkspaceTabViewDragboard {

        /**
         * @name Wirecloud.ui.WorkspaceTabViewDragboard
         *
         * @constructor
         * @param {Wirecloud.ui.WorkspaceTabView} tab
         */
        constructor(tab) {
            this.tab = tab;
            this.grid = null;
            this.painted = false;
            this.applying = false;
            this.views = [];
            this.forcedScreenSizeId = null;
            this._lastAppliedScreenSizeId = null;
            this._persistTimeout = null;

            this.cellheight = this.tab.model.preferences.get('cellheight');
            this.margin = this.tab.model.preferences.get('margin');

            this.gridElement = document.createElement('div');
            this.gridElement.className = 'grid-stack wc-dragboard';
            this.tab.wrapperElement.appendChild(this.gridElement);

            if (Wirecloud.ui.SidebarLayout) {
                this.topDock = new Wirecloud.ui.SidebarLayout(this, {position: 'top'});
                this.bottomDock = new Wirecloud.ui.SidebarLayout(this, {position: 'bottom'});
                this.leftDock = new Wirecloud.ui.SidebarLayout(this, {position: 'left'});
                this.rightDock = new Wirecloud.ui.SidebarLayout(this, {position: 'right'});

                this.docks = {
                    top: this.topDock,
                    bottom: this.bottomDock,
                    left: this.leftDock,
                    right: this.rightDock
                };

                this.tab.wrapperElement.appendChild(this.topDock.container);
                this.tab.wrapperElement.appendChild(this.bottomDock.container);
                this.tab.wrapperElement.appendChild(this.leftDock.container);
                this.tab.wrapperElement.appendChild(this.rightDock.container);
            } else {
                this.docks = null;
            }

            this._on_resize = on_resize.bind(this);
            if (typeof ResizeObserver !== 'undefined') {
                this._resizeObserver = new ResizeObserver(this._on_resize);
                this._resizeObserver.observe(this.tab.wrapperElement);
            } else if (typeof window !== 'undefined' && window.addEventListener) {
                window.addEventListener('resize', this._on_resize);
            }

            this.tab.model.preferences.addEventListener('post-commit', on_preferences_commit.bind(this));
            this.tab.workspace.addEventListener('editmode', on_editmode.bind(this));
        }

        /**
         * Normalized, sorted (by `moreOrEqual`) list of screen sizes for this tab.
         *
         * @type {Array}
         */
        get screenSizes() {
            const raw = this.tab.model.preferences.get('screenSizes') || [];

            return raw.map(normalize_screen_size).sort((a, b) => a.moreOrEqual - b.moreOrEqual);
        }

        /**
         * The screen size entry that applies to the current tab width (or the
         * forced screen size, see {@link #setForcedScreenSize}).
         *
         * @type {Object}
         */
        get activeScreenSize() {
            const screenSizes = this.screenSizes;

            if (screenSizes.length === 0) {
                return {id: 0, name: '', moreOrEqual: 0, lessOrEqual: -1, columns: DEFAULT_COLUMNS};
            }

            if (this.forcedScreenSizeId != null) {
                const forced = screenSizes.find((screenSize) => screenSize.id === this.forcedScreenSizeId);
                if (forced != null) {
                    return forced;
                }
            }

            const width = this._currentWidth();
            for (const screenSize of screenSizes) {
                if (width >= screenSize.moreOrEqual && (screenSize.lessOrEqual === -1 || width <= screenSize.lessOrEqual)) {
                    return screenSize;
                }
            }

            return screenSizes[screenSizes.length - 1];
        }

        /**
         * List of widget views that are not visible at the current screen size.
         *
         * @type {Array.<Wirecloud.ui.WidgetView>}
         */
        get hiddenWidgets() {
            const screenSize = this.activeScreenSize;

            return this.views.filter((view) => {
                return this.resolveLayout(view.model, screenSize).visible === false;
            });
        }

        _currentWidth() {
            const width = this.tab.wrapperElement.offsetWidth;
            return (width > 0) ? width : window.innerWidth;
        }

        /**
         * Overrides screen size detection so the tab is edited/rendered as if it
         * had the given screen size, regardless of the current tab width.
         *
         * @param {Number|null} id `null` to go back to automatic detection.
         */
        setForcedScreenSize(id) {
            this.forcedScreenSizeId = id;
            this._lastAppliedScreenSizeId = null;
            this.applyScreenSize();
        }

        /**
         * Runs `fn` while suppressing dragboard persistence triggered by
         * GridStack `change`/`dragstop`/`resizestop` events.
         *
         * @param {Function} fn
         */
        withApplying(fn) {
            const was = this.applying;
            this.applying = true;
            try {
                fn();
            } finally {
                this.applying = was;
            }
        }

        /**
         * Registers a widget view with this dragboard. The view's wrapper
         * element is appended to the grid container (if not already) and is
         * never re-parented afterwards, except when the widget is moved to
         * another tab.
         *
         * @param {Wirecloud.ui.WidgetView} view
         */
        addWidget(view) {
            if (this.views.indexOf(view) === -1) {
                this.views.push(view);
            }

            view.tab = this.tab;

            const layout = this.resolveLayout(view.model, this.activeScreenSize);
            if (!layout.dock && view.wrapperElement.parentNode !== this.gridElement) {
                this.gridElement.appendChild(view.wrapperElement);
            }

            this.refreshWidget(view);
        }

        /**
         * Re-places a single widget view on the grid using its resolved
         * layout for the active screen size (other widgets are left alone,
         * apart from the collisions GridStack resolves). Does nothing until
         * the grid has been painted.
         *
         * @param {Wirecloud.ui.WidgetView} view
         */
        refreshWidget(view) {
            if (this.grid == null || this.views.indexOf(view) === -1) {
                return;
            }

            const screenSize = this.activeScreenSize;
            const role = this.tab.workspace.editing ? 'editor' : 'viewer';

            this.withApplying(() => {
                this.grid.batchUpdate();
                try {
                    place_view.call(this, view, this.resolveLayout(view.model, screenSize), role);
                } finally {
                    this.grid.batchUpdate(false);
                }
            });
        }

        /**
         * Fully removes a widget view from this dragboard (and from the DOM).
         *
         * @param {Wirecloud.ui.WidgetView} view
         */
        removeWidget(view) {
            const index = this.views.indexOf(view);
            if (index !== -1) {
                this.views.splice(index, 1);
            }

            if (this.docks) {
                Object.values(this.docks).forEach((dock) => {
                    if (dock.views.includes(view)) {
                        dock.removeWidget(view);
                    }
                });
            }

            if (this.grid != null && view.wrapperElement.gridstackNode != null) {
                this.grid.removeWidget(view.wrapperElement, true, false);
            }
        }

        /**
         * Removes a widget view from this dragboard's grid (keeping its DOM
         * element around) and moves the underlying model to another tab; the
         * target tab's dragboard is responsible for re-attaching the view.
         *
         * @param {Wirecloud.ui.WidgetView} view
         * @param {Wirecloud.ui.WorkspaceTabView} targetTabView
         *
         * @returns {Promise}
         */
        moveWidgetToTab(view, targetTabView) {
            const index = this.views.indexOf(view);
            if (index !== -1) {
                this.views.splice(index, 1);
            }

            if (this.docks) {
                Object.values(this.docks).forEach((dock) => {
                    if (dock.views.includes(view)) {
                        dock.removeWidget(view);
                    }
                });
            }

            if (this.grid != null && view.wrapperElement.gridstackNode != null) {
                this.grid.removeWidget(view.wrapperElement, false, false);
            }

            return view.model.changeTab(targetTabView.model);
        }

        /**
         * Resolves the effective layout a widget model should use for the
         * given screen size: its own stored layout if present, otherwise a
         * scaled copy of the nearest screen size (by column count) that has
         * one, otherwise a sensible default.
         *
         * @param {Wirecloud.Widget} model
         * @param {Object} screenSize
         *
         * @returns {Object}
         */
        resolveLayout(model, screenSize) {
            const stored = model.getLayout(screenSize.id);
            if (stored != null) {
                return stored;
            }

            const screenSizes = this.screenSizes;
            const index = screenSizes.findIndex((entry) => entry.id === screenSize.id);

            for (let i = index + 1; i < screenSizes.length; i++) {
                const candidate = model.getLayout(screenSizes[i].id);
                if (candidate != null) {
                    return scale_layout(candidate, screenSizes[i], screenSize);
                }
            }

            for (let i = index - 1; i >= 0; i--) {
                const candidate = model.getLayout(screenSizes[i].id);
                if (candidate != null) {
                    return scale_layout(candidate, screenSizes[i], screenSize);
                }
            }

            return default_layout_for(screenSize, this.cellheight);
        }

        /**
         * Re-applies the layout of every registered widget view for the
         * current (or forced) screen size: sets the grid column count, hides
         * widgets whose resolved layout is not visible, and (re)positions the
         * remaining ones.
         */
        applyScreenSize() {
            if (this.grid == null) {
                return;
            }

            const screenSize = this.activeScreenSize;
            const role = this.tab.workspace.editing ? 'editor' : 'viewer';

            this.withApplying(() => {
                this.grid.batchUpdate();

                if (this.docks) {
                    Object.values(this.docks).forEach((dock) => {
                        dock.updateScreenSize(screenSize);
                    });
                }

                try {
                    this.grid.column(screenSize.columns, 'none');

                    // Detach every widget from the grid before placing them
                    // again. Otherwise the widgets that have not been processed
                    // yet still sit at the coordinates of the previously active
                    // screen size, and auto placement flows around them, so the
                    // result would depend on which screen size was active
                    // before (making a window narrower and then wider again did
                    // not give back the original layout).
                    this.views.forEach((view) => {
                        if (view.wrapperElement.gridstackNode != null && view.wrapperElement.parentNode === this.gridElement) {
                            this.grid.removeWidget(view.wrapperElement, false, false);
                        }
                    });

                    const resolved = this.views.map((view) => ({
                        view: view,
                        layout: this.resolveLayout(view.model, screenSize)
                    }));

                    resolved.sort((a, b) => {
                        const ay = (a.layout.y == null) ? Infinity : a.layout.y;
                        const by = (b.layout.y == null) ? Infinity : b.layout.y;
                        if (ay !== by) {
                            return ay - by;
                        }

                        const ax = (a.layout.x == null) ? Infinity : a.layout.x;
                        const bx = (b.layout.x == null) ? Infinity : b.layout.x;
                        if (ax !== bx) {
                            return ax - bx;
                        }

                        return String(a.view.id).localeCompare(String(b.view.id));
                    });

                    resolved.forEach(({view, layout}) => {
                        place_view.call(this, view, layout, role);
                    });
                } finally {
                    this.grid.batchUpdate(false);
                }
            });

            this._lastAppliedScreenSizeId = screenSize.id;
        }

        /**
         * Creates the underlying GridStack instance (only once) and applies
         * the current screen size.
         */
        paint() {
            if (this.painted) {
                return;
            }
            this.painted = true;

            this.grid = window.GridStack.init({
                column: this.activeScreenSize.columns,
                cellHeight: this.cellheight,
                margin: this.margin,
                float: false,
                animate: true,
                handle: '.wc-widget-heading',
                resizable: {handles: 'e, se, s, sw, w'},
                alwaysShowResizeHandle: 'mobile',
                staticGrid: this.tab.workspace.model.restricted
            }, this.gridElement);

            // GridStack re-orders the item elements in the DOM after every
            // change (its internal _sortDom, meant to keep keyboard tab order in
            // sync with the visual layout). Re-inserting a widget element
            // reloads its <iframe>, so that behaviour must be disabled here.
            this.grid._sortDom = () => this.grid;

            // GridStack keeps one handler per event name (a second `on()` call
            // for the same name replaces the first one), so the interaction
            // handlers below also take care of the layout bookkeeping.
            this.grid.on('change', on_grid_event.bind(this));
            this.grid.on('dragstart', on_interaction_start.bind(this));
            this.grid.on('resizestart', on_interaction_start.bind(this));
            this.grid.on('dragstop', on_interaction_end.bind(this));
            this.grid.on('resizestop', on_interaction_end.bind(this));

            if (this.docks) {
                Object.values(this.docks).forEach((dock) => {
                    dock.paint();
                });
            }

            this.applyScreenSize();
        }

        /**
         * Refreshes every widget view's move/resize permissions. Called on
         * `editmode` changes.
         *
         * @param {Boolean} editing
         */
        setEditing(editing) {
            this.views.forEach((view) => view.updateGridPermissions());
            if (this.docks) {
                Object.values(this.docks).forEach((dock) => {
                    dock.updatePermissions();
                    if (editing) {
                        dock.openAll(false);
                    }
                });
            }
        }

        setDockPushMargin(position, px) {
            if (!this._dockMargins) {
                this._dockMargins = { top: 0, bottom: 0, left: 0, right: 0 };
            }
            this._dockMargins[position] = px;
            if (position === 'left') {
                this.gridElement.style.marginLeft = px > 0 ? px + 'px' : '';
            } else if (position === 'right') {
                this.gridElement.style.marginRight = px > 0 ? px + 'px' : '';
            } else if (position === 'top') {
                this.gridElement.style.marginTop = px > 0 ? px + 'px' : '';
            } else if (position === 'bottom') {
                this.gridElement.style.marginBottom = px > 0 ? px + 'px' : '';
            }
        }

        columnsToPixels(cols) {
            return cols * this.getColumnWidth();
        }

        _on_dock_change(dock) {
            if (this.applying) {
                return;
            }
            dock.views.forEach((view) => view.syncLayoutFromNode());
            if (!this.tab.workspace.editing) {
                return;
            }
            schedule_persist.call(this);
        }

        _on_interaction_start() {
            on_interaction_start.call(this);
        }

        _on_interaction_end() {
            on_interaction_end.call(this);
        }

        dockWidget(view, position, mode = 'overlay', persist = true) {
            const activeId = String(this.activeScreenSize.id);
            const current = this.resolveLayout(view.model, this.activeScreenSize);
            const updated = Object.assign({}, current, {
                dock: position,
                dock_mode: mode,
                dock_open: true
            });
            const role = this.tab.workspace.editing ? 'editor' : 'viewer';

            this.withApplying(() => {
                place_view.call(this, view, updated, role);
            });

            if (persist && !view.model.volatile) {
                return view.model.setLayout(activeId, view.currentLayout, true);
            }
            return Promise.resolve(view);
        }

        undockWidget(view, persist = true) {
            const activeId = String(this.activeScreenSize.id);
            const current = this.resolveLayout(view.model, this.activeScreenSize);
            const updated = Object.assign({}, current, {
                dock: null
            });
            const role = this.tab.workspace.editing ? 'editor' : 'viewer';

            this.withApplying(() => {
                place_view.call(this, view, updated, role);
            });

            if (persist && !view.model.volatile) {
                return view.model.setLayout(activeId, view.currentLayout, true);
            }
            return Promise.resolve(view);
        }

        setWidgetDockMode(view, mode, persist = true) {
            if (this.docks && view.layout && view.layout.dock && this.docks[view.layout.dock]) {
                return this.docks[view.layout.dock].setWidgetMode(view, mode, persist);
            }
            return Promise.resolve(view);
        }

        toggleWidgetDockOpen(view, persist = true) {
            if (this.docks && view.layout && view.layout.dock && this.docks[view.layout.dock]) {
                return this.docks[view.layout.dock].toggleWidget(view, persist);
            }
            return Promise.resolve(view);
        }

        /**
         * @returns {Number} the width, in pixels, of one grid column.
         */
        getColumnWidth() {
            return this.gridElement.offsetWidth / this.activeScreenSize.columns;
        }

        /**
         * @param {Number} px
         *
         * @returns {Number} `px` converted to grid columns (rounded, minimum 1).
         */
        pixelsToColumns(px) {
            const columnWidth = this.getColumnWidth();
            if (!columnWidth) {
                return 1;
            }
            return Math.max(1, Math.round(px / columnWidth));
        }

        /**
         * @param {Number} px
         *
         * @returns {Number} `px` converted to grid rows (ceiled, minimum 1).
         */
        pixelsToRows(px) {
            return Math.max(1, Math.ceil(px / this.cellheight));
        }

        /**
         * Parses a widget size value into grid units.
         *
         * @param {Number|String} value a number (old-grid cell units), a
         * string with a `px` suffix, a string with a `%` suffix (percent of
         * the grid width/height), or a unitless numeric string (old-grid cell
         * units).
         * @param {String} axis `"w"` or `"h"`
         *
         * @returns {Number} the value converted to grid columns (`axis ===
         * "w"`) or grid rows (`axis === "h"`).
         */
        parseSize(value, axis) {
            const screenSize = this.activeScreenSize;

            if (typeof value === 'string') {
                const trimmed = value.trim();

                if (/px$/i.test(trimmed)) {
                    const px = parseFloat(trimmed);
                    return (axis === 'w') ? this.pixelsToColumns(px) : this.pixelsToRows(px);
                }

                if (/%$/.test(trimmed)) {
                    const percent = parseFloat(trimmed) / 100;
                    if (axis === 'w') {
                        return Math.max(1, Math.round(percent * screenSize.columns));
                    }

                    const gridHeight = this.gridElement.offsetHeight || this.tab.wrapperElement.offsetHeight;
                    return this.pixelsToRows(percent * gridHeight);
                }

                value = parseFloat(trimmed);
            }

            // Unitless number: old layout cells (20 columns x 12px rows)
            const n = Number(value) || 0;
            if (axis === 'w') {
                return Math.max(1, Math.round(n * screenSize.columns / 20));
            }

            return Math.max(1, Math.round(n * 12 / this.cellheight));
        }

        /**
         * Persists the layout (for the active screen size) of every
         * non-volatile, non-hidden widget currently tracked by the grid, in a
         * single request.
         *
         * @returns {Promise}
         */
        persist() {
            const targets = this.views.filter((view) => {
                return !view.model.volatile && view.wrapperElement.gridstackNode != null && !view.wrapperElement.hidden;
            });

            if (targets.length === 0) {
                return Promise.resolve(this);
            }

            const activeId = String(this.activeScreenSize.id);
            const content = targets.map((view) => view.toJSON());

            const url = Wirecloud.URLs.IWIDGET_COLLECTION.evaluate({
                workspace_id: this.tab.workspace.model.id,
                tab_id: this.tab.model.id
            });

            return Wirecloud.io.makeRequest(url, {
                method: 'PUT',
                requestHeaders: {'Accept': 'application/json'},
                contentType: 'application/json',
                postBody: JSON.stringify(content)
            }).then((response) => {
                if ([204, 401, 403, 404, 500].indexOf(response.status) === -1) {
                    return Promise.reject(new Error(utils.gettext("Unexpected response from server")));
                } else if ([401, 403, 404, 500].indexOf(response.status) !== -1) {
                    return Promise.reject(Wirecloud.GlobalLogManager.parseErrorResponse(response));
                }

                targets.forEach((view) => {
                    view.model.setLayout(activeId, view.currentLayout);
                });

                return this;
            });
        }

    }

})(Wirecloud.ui, Wirecloud.Utils);
