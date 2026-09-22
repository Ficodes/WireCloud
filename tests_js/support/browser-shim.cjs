const escapeHtml = (text) => String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

class FakeNode {}

class FakeTextNode extends FakeNode {

    constructor(text, ownerDocument) {
        super();
        this.nodeType = 3;
        this.ownerDocument = ownerDocument;
        this.parentElement = null;
        this.textContent = String(text);
    }

}

class FakeClassList {

    constructor(owner) {
        this.owner = owner;
        this.values = [];
    }

    add(...classNames) {
        classNames.flatMap((entry) => String(entry).split(/\s+/)).forEach((className) => {
            if (className && !this.values.includes(className)) {
                this.values.push(className);
            }
        });
        this._sync();
    }

    remove(...classNames) {
        const toRemove = new Set(classNames.flatMap((entry) => String(entry).split(/\s+/)).filter(Boolean));
        this.values = this.values.filter((className) => !toRemove.has(className));
        this._sync();
    }

    contains(className) {
        return this.values.includes(className);
    }

    toggle(className, force) {
        const shouldAdd = force == null ? !this.contains(className) : !!force;
        if (shouldAdd) {
            this.add(className);
        } else {
            this.remove(className);
        }
        return shouldAdd;
    }

    set(value) {
        this.values = String(value).trim() === '' ? [] : String(value).trim().split(/\s+/);
        this._sync();
    }

    toString() {
        return this.values.join(' ');
    }

    _sync() {
        this.owner._className = this.toString();
        this.owner.attributes.class = this.owner._className;
    }

}

class FakeElement extends FakeNode {

    constructor(tagName, ownerDocument) {
        super();
        this.nodeType = 1;
        this.tagName = String(tagName).toUpperCase();
        this.ownerDocument = ownerDocument;
        this.parentElement = null;
        this.childNodes = [];
        this.attributes = {};
        this.style = {
            setProperty(name, value) {
                this[name] = String(value);
            },
            getPropertyValue(name) {
                return this[name] || '';
            },
            removeProperty(name) {
                const previous = this[name] || '';
                delete this[name];
                return previous;
            }
        };
        this.dataset = {};
        this.listeners = {};
        this.scrollLeft = 0;
        this.scrollTop = 0;
        this.offsetHeight = 0;
        this.offsetWidth = 0;
        this.classList = new FakeClassList(this);
        this._className = '';
        this._textContent = '';
        this._innerHTML = '';
    }

    get className() {
        return this._className;
    }

    set className(value) {
        this.classList.set(value);
    }

    get textContent() {
        if (this.childNodes.length > 0) {
            return this.childNodes.map((child) => child.textContent).join('');
        }
        return this._textContent;
    }

    set textContent(value) {
        this.childNodes = [];
        this._textContent = value == null ? '' : String(value);
        this._innerHTML = '';
    }

    get innerHTML() {
        if (this.childNodes.length > 0) {
            return this.childNodes.map((child) => {
                return child.nodeType === 3 ? escapeHtml(child.textContent) : child.innerHTML;
            }).join('');
        }
        if (this._innerHTML !== '') {
            return this._innerHTML;
        }
        return escapeHtml(this._textContent);
    }

    set innerHTML(value) {
        this.childNodes = [];
        this._textContent = '';
        this._innerHTML = value == null ? '' : String(value);
    }

    appendChild(child) {
        child.parentElement = this;
        this.childNodes.push(child);
        return child;
    }

    insertBefore(child, referenceNode) {
        child.parentElement = this;
        if (referenceNode == null) {
            this.childNodes.push(child);
            return child;
        }

        const index = this.childNodes.indexOf(referenceNode);
        if (index === -1) {
            this.childNodes.push(child);
        } else {
            this.childNodes.splice(index, 0, child);
        }

        return child;
    }

    removeChild(child) {
        const index = this.childNodes.indexOf(child);
        if (index !== -1) {
            this.childNodes.splice(index, 1);
            child.parentElement = null;
        }
        return child;
    }

    remove() {
        if (this.parentElement != null) {
            this.parentElement.removeChild(this);
        }
    }

    setAttribute(name, value) {
        this.attributes[name] = String(value);
        if (name === 'class') {
            this.classList.set(value);
        }
    }

    getAttribute(name) {
        return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null;
    }

    hasAttribute(name) {
        return Object.prototype.hasOwnProperty.call(this.attributes, name);
    }

    removeAttribute(name) {
        delete this.attributes[name];
        if (name === 'class') {
            this.classList.set('');
        }
    }

    addEventListener(type, handler) {
        if (this.listeners[type] == null) {
            this.listeners[type] = [];
        }
        this.listeners[type].push(handler);
    }

    removeEventListener(type, handler) {
        if (this.listeners[type] == null) {
            return;
        }
        this.listeners[type] = this.listeners[type].filter((listener) => listener !== handler);
    }

    dispatchEvent(event) {
        const listeners = this.listeners[event.type] || [];
        listeners.forEach((listener) => listener.call(this, event));
        return true;
    }

    querySelector() {
        return null;
    }

    focus() {
        this.ownerDocument.activeElement = this;
    }

    blur() {
        if (this.ownerDocument.activeElement === this) {
            this.ownerDocument.activeElement = this.ownerDocument.body;
        }
    }

    getBoundingClientRect() {
        return {
            top: 0,
            left: 0,
            width: this.offsetWidth,
            height: this.offsetHeight,
        };
    }

    get parentNode() {
        return this.parentElement;
    }

    get firstChild() {
        return this.childNodes[0] ?? null;
    }

    get nextSibling() {
        if (this.parentElement == null) {
            return null;
        }
        const siblings = this.parentElement.childNodes;
        const index = siblings.indexOf(this);
        return index >= 0 ? siblings[index + 1] ?? null : null;
    }

}

const createDocument = () => {
    const document = {
        listeners: {},
        activeElement: null,
        fullscreenElement: null,
        fullscreenEnabled: false,
        createElement(tagName) {
            return new FakeElement(tagName, document);
        },
        createTextNode(text) {
            return new FakeTextNode(text, document);
        },
        createRange() {
            return {
                selectNodeContents() {}
            };
        },
        addEventListener(type, handler) {
            if (this.listeners[type] == null) {
                this.listeners[type] = [];
            }
            this.listeners[type].push(handler);
        },
        removeEventListener(type, handler) {
            if (this.listeners[type] == null) {
                return;
            }
            this.listeners[type] = this.listeners[type].filter((listener) => listener !== handler);
        },
    };

    document.documentElement = document.createElement('html');
    document.head = document.createElement('head');
    document.body = document.createElement('body');
    document.documentElement.appendChild(document.head);
    document.documentElement.appendChild(document.body);
    document.defaultView = {
        HTMLElement: FakeElement,
        getComputedStyle(target) {
            return {
                getPropertyValue(name) {
                    return target?.style?.[name] || '';
                },
                getPropertyCSSValue() {
                    return {
                        getFloatValue() {
                            return 0;
                        }
                    };
                }
            };
        }
    };
    document.activeElement = document.body;

    return document;
};

const installBrowserShim = () => {
    const document = createDocument();
    const selection = {
        removeAllRanges() {},
        addRange() {}
    };

    global.window = global;
    global.self = global;
    global.document = document;
    global.Element = FakeElement;
    global.Node = FakeNode;
    global.HTMLElement = FakeElement;
    global.CSSPrimitiveValue = { CSS_PX: 0 };
    global.requestAnimationFrame = (callback) => setTimeout(callback, 0);
    global.cancelAnimationFrame = (handle) => clearTimeout(handle);
    global.getSelection = () => selection;
    global.window.document = document;
    global.window.console = console;
    global.window.getSelection = global.getSelection;
    global.window.requestAnimationFrame = global.requestAnimationFrame;
    global.window.cancelAnimationFrame = global.cancelAnimationFrame;

    return { document };
};

module.exports = {
    installBrowserShim,
};
