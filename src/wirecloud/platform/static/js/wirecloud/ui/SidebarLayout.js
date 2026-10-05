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

    const ICON = Object.freeze({
        "right": "right",
        "left": "left",
        "top": "up",
        "bottom": "down"
    });
    const OPPOSITE = Object.freeze({
        "right": "left",
        "left": "right",
        "bottom": "up",
        "top": "down"
    });
    const POSITIONS = Object.freeze(["top", "right", "bottom", "left"]);

    ns.SidebarLayout = class SidebarLayout {

        /**
         * @name Wirecloud.ui.SidebarLayout
         *
         * @constructor
         * @param {Wirecloud.ui.WorkspaceTabViewDragboard} dragboard
         * @param {Object} options
         */
        constructor(dragboard, options) {
            options = utils.merge({
                position: "left"
            }, options);

            if (POSITIONS.indexOf(options.position) === -1) {
                throw new TypeError("Invalid position option: " + options.position);
            }

            this.dragboard = dragboard;
            this.position = options.position;
            this.vertical = (options.position === "right" || options.position === "left");
            this.views = [];
            this.handles = new Map();
            this.grid = null;
            this.painted = false;

            this.container = document.createElement("div");
            this.container.className = "wc-dock wc-dock-" + this.position + " hidden";
            this.container.setAttribute("data-dock", this.position);

            this.gridElement = document.createElement("div");
            this.gridElement.className = "grid-stack wc-dock-grid wc-dock-grid-" + this.position;
            this.container.appendChild(this.gridElement);
        }

        isWidgetOpen(view) {
            if (view.layout == null || view.layout.dock_open == null) {
                return false;
            }
            return !!view.layout.dock_open;
        }

        _getOrCreateHandle(view) {
            if (this.handles.has(view)) {
                return this.handles.get(view);
            }

            const handle = document.createElement("div");
            handle.className = "wc-sidebar-" + this.position + "-handle";
            handle.setAttribute("role", "button");
            handle.setAttribute("aria-label", utils.interpolate(
                utils.gettext("Toggle %(position)s sidebar"),
                {position: this.position},
                true
            ));

            const icon = document.createElement("i");
            icon.setAttribute("aria-hidden", "true");
            handle.appendChild(icon);
            handle._icon = icon;

            handle.addEventListener("click", (event) => {
                event.stopPropagation();
                this.toggleWidget(view, true);
            });

            this.handles.set(view, handle);
            this._updateHandleIcon(view);

            return handle;
        }

        _updateHandleIcon(view) {
            const handle = this.handles.get(view);
            if (!handle) {
                return;
            }
            const icon = handle._icon || (handle.querySelector ? handle.querySelector("i") : null);
            if (!icon) {
                return;
            }
            const isOpen = this.isWidgetOpen(view);
            const caret = isOpen ? ICON[this.position] : OPPOSITE[this.position];
            icon.className = "fas fa-caret-" + caret;
        }

        getHandle(view) {
            return this.handles.get(view);
        }

        toggleWidget(view, persist = true) {
            const isOpen = this.isWidgetOpen(view);
            return this.setWidgetOpen(view, !isOpen, persist);
        }

        openWidget(view, persist = true) {
            return this.setWidgetOpen(view, true, persist);
        }

        closeWidget(view, persist = true) {
            return this.setWidgetOpen(view, false, persist);
        }

        setWidgetOpen(view, open, persist = true) {
            open = !!open;

            if (view.layout != null) {
                view.layout.dock_open = open;
            }

            view.wrapperElement.classList.toggle("wc-dock-widget-open", open);
            view.wrapperElement.classList.toggle("wc-dock-widget-closed", !open);
            this._updateHandleIcon(view);

            this.updatePushMargins();
            view.repaint();
            setTimeout(() => {
                view.repaint();
            }, 300);

            if (persist && !view.model.volatile) {
                const activeId = String(this.dragboard.activeScreenSize.id);
                return view.model.setLayout(activeId, view.currentLayout, true);
            }

            return Promise.resolve(view);
        }

        openAll(persist = false) {
            this.views.forEach((view) => this.openWidget(view, persist));
        }

        closeAll(persist = false) {
            this.views.forEach((view) => this.closeWidget(view, persist));
        }

        setWidgetMode(view, mode, persist = true) {
            if (this.position === "bottom" || (mode !== "overlay" && mode !== "push")) {
                mode = "overlay";
            }

            if (view.layout != null) {
                view.layout.dock_mode = mode;
            }

            view.wrapperElement.classList.toggle("wc-dock-widget-push", mode === "push");
            view.wrapperElement.classList.toggle("wc-dock-widget-overlay", mode === "overlay");

            this.updatePushMargins();

            if (persist && !view.model.volatile) {
                const activeId = String(this.dragboard.activeScreenSize.id);
                return view.model.setLayout(activeId, view.currentLayout, true);
            }

            return Promise.resolve(view);
        }

        updatePushMargins() {
            // A bottom dock is fixed to the visible workspace edge. Pushing
            // the main grid from there would both shrink the content and
            // create vertical scroll overflow, so it is always overlay-only.
            if (this.position === "bottom") {
                this.dragboard.setDockPushMargin(this.position, 0);
                return;
            }

            if (this.views.length === 0) {
                this.dragboard.setDockPushMargin(this.position, 0);
                return;
            }

            const openPushViews = this.views.filter((v) => {
                return this.isWidgetOpen(v) && v.layout && v.layout.dock_mode === "push";
            });

            if (openPushViews.length === 0) {
                this.dragboard.setDockPushMargin(this.position, 0);
                return;
            }

            let maxDimension = 0;
            if (this.vertical) {
                openPushViews.forEach((v) => {
                    const px = (v.wrapperElement && v.wrapperElement.offsetWidth > 0)
                        ? v.wrapperElement.offsetWidth
                        : this.dragboard.columnsToPixels(v.layout.w || 4);
                    if (px > maxDimension) {
                        maxDimension = px;
                    }
                });
            } else {
                openPushViews.forEach((v) => {
                    const px = (v.wrapperElement && v.wrapperElement.offsetHeight > 0)
                        ? v.wrapperElement.offsetHeight
                        : (v.layout.h || 4) * (this.dragboard.cellheight || 40);
                    if (px > maxDimension) {
                        maxDimension = px;
                    }
                });
            }

            this.dragboard.setDockPushMargin(this.position, maxDimension);
        }

        _constrainNode(node) {
            if (node == null) {
                return;
            }
            const columns = this.grid ? this.grid.getColumn() : (this.dragboard.activeScreenSize.columns || 12);
            if (this.position === "left") {
                node.x = 0;
            } else if (this.position === "right") {
                node.x = Math.max(0, columns - (node.w || 1));
            } else if (this.position === "top" || this.position === "bottom") {
                node.y = 0;
            }
        }

        _constrainCoord(o, node) {
            if (o == null) {
                return;
            }
            const columns = this.grid ? this.grid.getColumn() : (this.dragboard.activeScreenSize.columns || 12);
            const w = (o.w != null) ? o.w : (node ? node.w : 1);
            if (this.position === "left") {
                o.x = 0;
            } else if (this.position === "right") {
                o.x = Math.max(0, columns - w);
            } else if (this.position === "top" || this.position === "bottom") {
                o.y = 0;
            }
        }

        paint() {
            if (this.painted || this.views.length === 0) {
                return;
            }
            this._initGrid();
        }

        _initGrid() {
            if (this.painted) {
                return;
            }
            this.painted = true;

            const columns = this.dragboard.activeScreenSize.columns || 12;
            const cellHeight = this.dragboard.cellheight || 40;
            const margin = this.dragboard.margin || 5;

            const gridOpts = {
                column: columns,
                cellHeight: cellHeight,
                margin: margin,
                float: true,
                animate: true,
                handle: ".wc-widget-heading",
                alwaysShowResizeHandle: "mobile",
                staticGrid: this.dragboard.tab.workspace.model.restricted
            };

            if (this.vertical) {
                gridOpts.resizable = {
                    handles: (this.position === "left") ? "n, ne, e, se, s" : "n, nw, w, sw, s"
                };
            } else {
                gridOpts.resizable = {
                    handles: (this.position === "top") ? "e, se, s, sw, w" : "e, ne, n, nw, w"
                };
            }

            this.grid = window.GridStack.init(gridOpts, this.gridElement);

            this.grid._sortDom = () => this.grid;

            // Docked widgets remain children of the main grid to keep their
            // live content connected. GridStack's drag/resize adapters report
            // positions relative to that DOM parent, so translate them into
            // this dock grid's coordinate system before its engine uses them.
            if (typeof this.grid._onStartMoving === "function") {
                const originalOnStartMoving = this.grid._onStartMoving.bind(this.grid);
                this.grid._onStartMoving = (element, event, ui, ...args) => {
                    const result = originalOnStartMoving(
                        element,
                        event,
                        this._toDockCoordinates(element, event, ui),
                        ...args
                    );

                    // Bottom widgets are logically kept at row 0, although
                    // they are rendered against the lower workspace edge.
                    // GridStack consequently limits a north resize to the
                    // current height. Replace that limit with the available
                    // workspace height so the visible top edge can move.
                    if (this.position === "bottom" && event?.type === "resizestart") {
                        const node = element.gridstackNode;
                        const cellHeight = args[2] || this.grid.getCellHeight(true);
                        const workspaceHeight = this.dragboard.tab.wrapperElement.clientHeight ||
                            this.dragboard.tab.wrapperElement.offsetHeight || window.innerHeight;
                        const availableRows = Math.max(node?.h || 1, Math.floor(workspaceHeight / cellHeight));
                        const maxRows = node?.maxH ? Math.min(node.maxH, availableRows) : availableRows;
                        element.ddElement?.ddResizable?.updateOption({
                            maxHeightMoveUp: maxRows * cellHeight
                        });
                    }

                    return result;
                };
            }
            if (typeof this.grid._dragOrResize === "function") {
                const originalDragOrResize = this.grid._dragOrResize.bind(this.grid);
                this.grid._dragOrResize = (element, event, ui, ...args) => {
                    return originalDragOrResize(element, event, this._toDockCoordinates(element, event, ui), ...args);
                };
            }

            if (this.grid.engine) {
                const engine = this.grid.engine;
                if (typeof engine.nodeBoundFix === "function") {
                    const origNodeBoundFix = engine.nodeBoundFix.bind(engine);
                    engine.nodeBoundFix = (node, resizing) => {
                        origNodeBoundFix(node, resizing);
                        this._constrainNode(node);
                        return engine;
                    };
                }
                if (typeof engine.moveNode === "function") {
                    const origMoveNode = engine.moveNode.bind(engine);
                    engine.moveNode = (node, o) => {
                        if (o) {
                            this._constrainCoord(o, node);
                        }
                        return origMoveNode(node, o);
                    };
                }
                if (typeof engine.moveNodeCheck === "function") {
                    const origMoveNodeCheck = engine.moveNodeCheck.bind(engine);
                    engine.moveNodeCheck = (node, o) => {
                        if (o) {
                            this._constrainCoord(o, node);
                        }
                        return origMoveNodeCheck(node, o);
                    };
                }
            }

            this.grid.on("change", () => {
                this.syncPositions();
                this.updateWidgetPositions();
                this.dragboard._on_dock_change(this);
                this.updatePushMargins();
            });
            this.grid.on("drag resize", (event, element) => {
                const view = this.views.find((candidate) => candidate.wrapperElement === element);
                if (view != null) {
                    this.updateWidgetPosition(view);
                }
            });
            this.grid.on("dragstart", () => {
                this.container.classList.add("wc-dock-interacting");
                this.dragboard._on_interaction_start(this);
            });
            this.grid.on("resizestart", () => {
                this.container.classList.add("wc-dock-interacting");
                this.dragboard._on_interaction_start(this);
            });
            this.grid.on("dragstop", () => {
                this.container.classList.remove("wc-dock-interacting");
                this.dragboard._on_interaction_end();
                this.syncPositions();
                this.views.forEach((v) => v.syncLayoutFromNode());
                this.updateWidgetPositions();
                this.updatePushMargins();
                if (this.dragboard.tab.workspace.editing) {
                    this.dragboard.persist();
                }
            });
            this.grid.on("resizestop", () => {
                this.container.classList.remove("wc-dock-interacting");
                this.dragboard._on_interaction_end();
                this.syncPositions();
                this.views.forEach((v) => v.syncLayoutFromNode());
                this.updateWidgetPositions();
                this.updatePushMargins();
                if (this.dragboard.tab.workspace.editing) {
                    this.dragboard.persist();
                }
            });
        }

        _toDockCoordinates(element, event, ui) {
            if (ui == null || ui.position == null || element.parentElement == null) {
                return ui;
            }

            const parentRect = element.parentElement.getBoundingClientRect();
            const dockRect = this.gridElement.getBoundingClientRect();
            const resizing = event && event.type && event.type.indexOf("resize") === 0;
            const transform = resizing ? element.ddElement?.ddResizable?.rectScale :
                element.ddElement?.ddDraggable?.dragTransform;
            const xScale = transform?.xScale ?? transform?.x ?? 1;
            const yScale = transform?.yScale ?? transform?.y ?? 1;
            const rtl = this.grid && this.grid.opts.rtl === true;
            const xOffset = rtl ? dockRect.right - parentRect.right : parentRect.left - dockRect.left;

            return Object.assign({}, ui, {
                position: Object.assign({}, ui.position, {
                    left: ui.position.left + xOffset * xScale,
                    top: ui.position.top + (parentRect.top - dockRect.top) * yScale
                })
            });
        }

        syncPositions() {
            if (this.grid == null) {
                return;
            }

            const columns = this.grid.getColumn();
            this.dragboard.withApplying(() => {
                this.views.forEach((view) => {
                    const node = view.wrapperElement.gridstackNode;
                    if (node == null || node._moving || node._resizing) {
                        return;
                    }

                    let needsUpdate = false;
                    const updates = {};

                    if (this.position === "left") {
                        if (node.x !== 0) {
                            updates.x = 0;
                            needsUpdate = true;
                        }
                    } else if (this.position === "right") {
                        const targetX = Math.max(0, columns - node.w);
                        if (node.x !== targetX) {
                            updates.x = targetX;
                            needsUpdate = true;
                        }
                    } else if (this.position === "top" || this.position === "bottom") {
                        if (node.y !== 0) {
                            updates.y = 0;
                            needsUpdate = true;
                        }
                    }

                    if (needsUpdate) {
                        this.grid.update(view.wrapperElement, updates);
                    }
                });
            });
        }

        addWidget(view, layout, role) {
            if (this.views.indexOf(view) === -1) {
                this.views.push(view);
            }

            // The main dragboard is the permanent DOM parent for live widget
            // content. GridStack can manage an element owned by another
            // container, which lets docking change layout ownership without
            // disconnecting iframes or custom elements from the document.
            if (view.wrapperElement.parentNode == null) {
                this.dragboard.gridElement.appendChild(view.wrapperElement);
            }

            if (this.dragboard.painted && !this.painted) {
                this._initGrid();
            }

            this.container.classList.remove("hidden");

            view.wrapperElement.classList.add("wc-docked-widget", "wc-docked-" + this.position);

            const handles = (this.position === "left") ? "n,ne,e,se,s" :
                            (this.position === "right") ? "n,nw,w,sw,s" :
                            (this.position === "top") ? "e,se,s,sw,w" : "e,ne,n,nw,w";
            view.wrapperElement.setAttribute("gs-resize-handles", handles);

            const handle = this._getOrCreateHandle(view);
            if (handle.parentNode !== view.wrapperElement) {
                view.wrapperElement.appendChild(handle);
            }

            view.applyLayout(layout);

            const isOpen = this.isWidgetOpen(view);
            const mode = this.position === "bottom"
                ? "overlay"
                : ((layout && layout.dock_mode) ? layout.dock_mode : "overlay");
            if (view.layout != null) {
                view.layout.dock_mode = mode;
            }
            view.wrapperElement.classList.toggle("wc-dock-widget-open", isOpen);
            view.wrapperElement.classList.toggle("wc-dock-widget-closed", !isOpen);
            view.wrapperElement.classList.toggle("wc-dock-widget-push", mode === "push");
            view.wrapperElement.classList.toggle("wc-dock-widget-overlay", mode === "overlay");

            this._updateHandleIcon(view);

            if (this.grid != null) {
                const columns = this.grid.getColumn();
                const canMove = view.model.isAllowed("move", role);
                const canResize = !layout.minimized && view.model.isAllowed("resize", role);

                let x = layout.x;
                let y = layout.y;
                const w = Math.min(layout.w || (this.vertical ? 4 : 3), columns);
                const h = layout.h || (this.vertical ? 6 : 4);

                if (this.position === "left") {
                    x = 0;
                } else if (this.position === "right") {
                    x = Math.max(0, columns - w);
                } else if (this.position === "top" || this.position === "bottom") {
                    y = 0;
                }

                const nodeOpts = {
                    w: w,
                    h: h,
                    noMove: !canMove,
                    noResize: !canResize
                };
                if (x != null) {
                    nodeOpts.x = x;
                }
                if (y != null) {
                    nodeOpts.y = y;
                }

                if (view.wrapperElement.gridstackNode == null) {
                    this.grid.makeWidget(view.wrapperElement, Object.assign({
                        id: view.id,
                        autoPosition: (x == null || (this.vertical && y == null) || (!this.vertical && x == null))
                    }, nodeOpts));
                } else {
                    this.grid.update(view.wrapperElement, nodeOpts);
                }
            }

            this.syncPositions();
            this.updateWidgetPosition(view);
            this.updatePushMargins();
        }

        updateWidgetPosition(view) {
            const node = view.wrapperElement.gridstackNode;
            if (node == null || node.grid !== this.grid) {
                return;
            }

            const margins = this.dragboard._dockMargins || {top: 0, right: 0, bottom: 0, left: 0};
            const width = this.dragboard.tab.wrapperElement.clientWidth ||
                this.dragboard.tab.wrapperElement.offsetWidth || window.innerWidth;
            const height = this.dragboard.tab.wrapperElement.clientHeight ||
                this.dragboard.tab.wrapperElement.offsetHeight || window.innerHeight;
            const workspaceRect = this.dragboard.tab.wrapperElement.getBoundingClientRect();
            const columnWidth = width / this.grid.getColumn();
            const cellHeight = this.grid.getCellHeight(true);
            const style = view.wrapperElement.style;
            const uniformMargin = this.grid.getMargin();
            const marginUnit = this.grid.opts.marginUnit || "px";
            const cssMargin = (side) => {
                const value = this.grid.opts["margin" + side] ?? uniformMargin ?? 0;
                return (typeof value === "number") ? value + marginUnit : value;
            };

            const fixedPositioned = this.position === "bottom";
            const fixedOffsetLeft = fixedPositioned ? workspaceRect.left : 0;
            // Absolute docks are children of the pushed main grid and must
            // cancel its offset. Bottom docks are fixed to the viewport, so
            // their coordinates must never include that compensation.
            const pushOffsetLeft = fixedPositioned ? 0 : margins.left;
            style.setProperty("--wc-dock-left", (fixedOffsetLeft + node.x * columnWidth - pushOffsetLeft) + "px");
            const top = this.position === "bottom"
                ? workspaceRect.top + height - node.h * cellHeight
                : node.y * cellHeight - margins.top;
            style.setProperty("--wc-dock-top", Math.max(-margins.top, top) + "px");
            if (this.position === "bottom") {
                // Bottom docks use fixed positioning so scrolling the main
                // grid cannot move them. Keep them above the workspace tab
                // bar when it is visible, or at the viewport edge otherwise.
                const visibleBottom = Math.min(window.innerHeight, workspaceRect.bottom);
                style.setProperty("--wc-dock-bottom", (window.innerHeight - visibleBottom) + "px");
            } else {
                style.removeProperty("--wc-dock-bottom");
            }
            style.setProperty("--wc-dock-width", (node.w * columnWidth) + "px");
            style.setProperty("--wc-dock-height", (node.h * cellHeight) + "px");
            // Dock nodes deliberately live under the main grid element to
            // preserve iframe/custom-element state. Copy the owning dock
            // grid's margins onto the node instead of inheriting the main
            // grid's --gs-item-margin-* custom properties.
            style.setProperty("--wc-dock-margin-top", cssMargin("Top"));
            style.setProperty("--wc-dock-margin-right", cssMargin("Right"));
            style.setProperty("--wc-dock-margin-bottom", cssMargin("Bottom"));
            style.setProperty("--wc-dock-margin-left", cssMargin("Left"));
        }

        updateWidgetPositions() {
            this.views.forEach((view) => this.updateWidgetPosition(view));
        }

        removeWidget(view) {
            const idx = this.views.indexOf(view);
            if (idx !== -1) {
                this.views.splice(idx, 1);
            }

            const handle = this.handles.get(view);
            if (handle) {
                handle.remove();
                this.handles.delete(view);
            }

            view.wrapperElement.removeAttribute("gs-resize-handles");
            view.wrapperElement.classList.remove(
                "wc-docked-widget", "wc-docked-left", "wc-docked-right", "wc-docked-top", "wc-docked-bottom",
                "wc-dock-widget-open", "wc-dock-widget-closed", "wc-dock-widget-push", "wc-dock-widget-overlay"
            );

            if (this.grid != null && view.wrapperElement.gridstackNode != null &&
                    view.wrapperElement.gridstackNode.grid === this.grid) {
                const element = view.wrapperElement;
                const node = element.gridstackNode;

                // GridStack's public removeWidget() ignores external items.
                // Docked widgets deliberately remain children of the stable
                // main grid, so remove the node directly from this dock engine.
                if (element.parentNode === this.gridElement) {
                    this.grid.removeWidget(element, false, false);
                } else {
                    if (typeof this.grid._removeDD === "function") {
                        this.grid._removeDD(element);
                    }
                    delete element.gridstackNode;
                    this.grid.engine.removeNode(node, false, false);
                    if (typeof this.grid._updateContainerHeight === "function") {
                        this.grid._updateContainerHeight();
                    }
                }
            }

            view.wrapperElement.style.removeProperty("--wc-dock-left");
            view.wrapperElement.style.removeProperty("--wc-dock-top");
            view.wrapperElement.style.removeProperty("--wc-dock-bottom");
            view.wrapperElement.style.removeProperty("--wc-dock-width");
            view.wrapperElement.style.removeProperty("--wc-dock-height");
            view.wrapperElement.style.removeProperty("--wc-dock-margin-top");
            view.wrapperElement.style.removeProperty("--wc-dock-margin-right");
            view.wrapperElement.style.removeProperty("--wc-dock-margin-bottom");
            view.wrapperElement.style.removeProperty("--wc-dock-margin-left");

            if (this.views.length === 0) {
                this.container.classList.add("hidden");
            }

            this.updatePushMargins();
        }

        updateScreenSize(screenSize) {
            if (this.grid == null) {
                return;
            }

            this.grid.column(screenSize.columns, "none");
            this.syncPositions();
            this.updateWidgetPositions();
            this.updatePushMargins();
        }

        setMargin(margin) {
            if (this.grid == null) {
                return;
            }

            this.grid.margin(margin);
            this.updateWidgetPositions();
        }

        updatePermissions() {
            if (this.grid == null) {
                return;
            }
            this.views.forEach((view) => view.updateGridPermissions());
        }

    };

})(Wirecloud.ui, Wirecloud.Utils);
