// Minimal in-memory stand-in for the GridStack library used by
// Wirecloud.ui.WorkspaceTabViewDragboard. It records every call and emulates
// the parts of the real API the platform relies on:
//
//   GridStack.init(options, el)      -> grid instance (also stored in GridStack.instances)
//   grid.makeWidget(el, opts)        -> creates el.gridstackNode {id, x, y, w, h, autoPosition, noMove, noResize, el}
//   grid.removeWidget(el, removeDOM, triggerEvent) -> deletes el.gridstackNode (and el from DOM when removeDOM)
//   grid.update(el, opts)            -> merges x/y/w/h/noMove/noResize into el.gridstackNode
//   grid.column(n, layout)           -> stores the column count
//   grid.cellHeight(px) / grid.getCellHeight(true) / grid.margin(px) / grid.getColumn()
//   grid.batchUpdate(flag)           -> when flag === false, fires a 'change' event with the nodes
//                                      touched since batchUpdate(true) (like the real library)
//   grid.on(name, cb) / grid.off(name) / grid.trigger(name, ...args)
//   grid.getGridItems() / grid.engine.nodes / grid.destroy()
//
// Auto placement: nodes created without x/y get x = 0 and y = (max bottom of
// existing nodes), i.e. they are appended below everything else.

const installGridStackMock = () => {
    class FakeGridStack {

        constructor(options, el) {
            this.opts = Object.assign({}, options);
            this.el = el;
            this.column_ = options.column || 12;
            this.cellHeight_ = typeof options.cellHeight === 'number' ? options.cellHeight : 40;
            this.margin_ = typeof options.margin === 'number' ? options.margin : 5;
            this.engine = {
                nodes: [],
                maxRow: options.row || options.maxRow || 0,
                float: !!options.float,
                nodeBoundFix: (node, resizing) => this.engine,
                moveNode: (node, o) => true,
                moveNodeCheck: (node, o) => true,
                removeNode: (node) => {
                    this.engine.nodes = this.engine.nodes.filter((candidate) => candidate !== node);
                    return this.engine;
                },
            };
            this.listeners = {};
            this.calls = [];
            this.batching = false;
            this.dirty = [];
        }

        _record(name, args) {
            this.calls.push({name, args});
        }

        _autoPosition(node) {
            node.x = 0;
            node.y = this.engine.nodes.reduce((max, other) => {
                return other === node ? max : Math.max(max, (other.y || 0) + (other.h || 1));
            }, 0);
        }

        makeWidget(el, opts) {
            this._record('makeWidget', [el, opts]);
            if (el.gridstackNode != null) {
                return el;
            }
            const node = Object.assign({id: el.getAttribute && el.getAttribute('gs-id'), w: 1, h: 1, noMove: false, noResize: false}, opts || {});
            node.el = el;
            node.grid = this;
            if (node.x == null || node.y == null || node.autoPosition) {
                node.autoPosition = true;
                this._autoPosition(node);
            }
            el.gridstackNode = node;
            if (el.setAttribute && node.id != null) {
                el.setAttribute('gs-id', node.id);
            }
            this.engine.nodes.push(node);
            this.dirty.push(node);
            return el;
        }

        removeWidget(el, removeDOM = true, triggerEvent = true) {
            this._record('removeWidget', [el, removeDOM, triggerEvent]);
            const node = el.gridstackNode;
            if (node == null) {
                return this;
            }
            delete el.gridstackNode;
            this.engine.nodes = this.engine.nodes.filter((n) => n !== node);
            this.dirty = this.dirty.filter((n) => n !== node);
            if (removeDOM && el.parentNode) {
                el.parentNode.removeChild(el);
            }
            if (triggerEvent) {
                this.trigger('removed', [node]);
            }
            return this;
        }

        update(el, opts) {
            this._record('update', [el, opts]);
            const node = el.gridstackNode;
            if (node == null) {
                return this;
            }
            ['x', 'y', 'w', 'h', 'noMove', 'noResize', 'locked'].forEach((key) => {
                if (opts[key] !== undefined) {
                    node[key] = opts[key];
                }
            });
            if (!this.dirty.includes(node)) {
                this.dirty.push(node);
            }
            return this;
        }

        column(n, layout) {
            this._record('column', [n, layout]);
            this.column_ = n;
            return this;
        }

        getColumn() {
            return this.column_;
        }

        cellHeight(px) {
            this._record('cellHeight', [px]);
            if (px != null) {
                this.cellHeight_ = px;
            }
            return this;
        }

        getCellHeight() {
            return this.cellHeight_;
        }

        margin(px) {
            this._record('margin', [px]);
            this.margin_ = px;
            return this;
        }

        updateOptions(options) {
            this._record('updateOptions', [options]);
            if (options.cellHeight != null) {
                this.cellHeight(options.cellHeight);
            }
            if (options.row !== undefined) {
                this.opts.row = options.row;
                this.opts.minRow = options.row;
                this.opts.maxRow = options.row;
                this.engine.maxRow = options.row;
            }
            if (options.float !== undefined) {
                this.opts.float = options.float;
                this.engine.float = options.float;
            }
            Object.assign(this.opts, options);
            return this;
        }

        getMargin() {
            return this.margin_;
        }

        batchUpdate(flag = true) {
            this._record('batchUpdate', [flag]);
            if (flag) {
                this.batching = true;
                this.dirty = [];
                this.engine._prevFloat = this.engine.float;
                this.engine.float = true;
            } else {
                this.batching = false;
                this.engine.float = this.engine._prevFloat;
                delete this.engine._prevFloat;
                const nodes = this.dirty;
                this.dirty = [];
                if (nodes.length > 0) {
                    this.trigger('change', nodes);
                }
            }
            return this;
        }

        on(name, callback) {
            (this.listeners[name] = this.listeners[name] || []).push(callback);
            return this;
        }

        off(name) {
            delete this.listeners[name];
            return this;
        }

        trigger(name, ...args) {
            (this.listeners[name] || []).forEach((callback) => callback({type: name}, ...args));
            return this;
        }

        getGridItems() {
            return this.engine.nodes.map((node) => node.el);
        }

        _onStartMoving(...args) {
            this._record('_onStartMoving', args);
            this.lastStartMovingArgs = args;
            return this;
        }

        _dragOrResize(...args) {
            this._record('_dragOrResize', args);
            this.lastDragOrResizeArgs = args;
            return this;
        }

        setStatic(value) {
            this._record('setStatic', [value]);
            this.opts.staticGrid = value;
            return this;
        }

        destroy(removeDOM) {
            this._record('destroy', [removeDOM]);
            return this;
        }

    }

    const GridStack = {
        instances: [],
        init(options, el) {
            const grid = new FakeGridStack(options || {}, el);
            GridStack.instances.push(grid);
            return grid;
        },
        FakeGridStack
    };

    global.GridStack = GridStack;
    if (global.window != null) {
        global.window.GridStack = GridStack;
    }

    return GridStack;
};

module.exports = {installGridStackMock};
