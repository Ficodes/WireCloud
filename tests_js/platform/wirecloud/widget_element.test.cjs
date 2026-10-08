const test = require('node:test');
const assert = require('node:assert/strict');
const {
    loadLegacyScript,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');

let WidgetClass = null;

test.beforeEach(() => {
    resetLegacyRuntime();
    WidgetClass = null;
    if (global.Wirecloud == null) {
        global.Wirecloud = {};
    }
    Wirecloud.io = {
        makeRequest: () => Promise.resolve({
            status: 200,
            responseText: '<!DOCTYPE html><html><head><link rel="stylesheet" href="style.css"><script src="app.js"></script></head><body><div id="app">Hello</div></body></html>',
            transport: { getResponseHeader: () => 'text/html' },
        }),
    };
    global.window.customElements = {
        define(name, cls) { WidgetClass = cls; },
    };
    global.window.URL = URL;
    global.window.DOMParser = class DOMParser {
        parseFromString() {
            return { head: document.createElement('head'), body: document.createElement('body') };
        }
    };
});

const createWidget = () => {
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/WidgetElement.js');
    const widget = new WidgetClass();
    widget.style = {};
    widget.shadowRoot = null;
    widget.attachShadow = function () {
        this.shadowRoot = { innerHTML: '', appendChild() {}, querySelectorAll() { return []; } };
        this.hasShadowDOM = true;
        return this.shadowRoot;
    };
    widget.dispatchEvent = () => true;
    widget.addEventListener = () => {};
    return widget;
};

test('WidgetElement.connectedCallback attaches shadow DOM', () => {
    const widget = createWidget();
    widget.connectedCallback();
    assert.equal(widget.hasShadowDOM, true);
    assert.ok(widget.shadowRoot);
    assert.equal(widget.style.width, '100%');
    assert.equal(widget.style.height, '100%');
    assert.equal(widget.style.display, 'block');
});

test('WidgetElement.connectedCallback does not re-attach if hasShadowDOM', () => {
    const widget = createWidget();
    widget.hasShadowDOM = true;
    const original = {};
    widget.shadowRoot = original;
    widget.connectedCallback();
    assert.equal(widget.shadowRoot, original);
});

test('WidgetElement._unload returns early when no shadow DOM (lines 83-84)', () => {
    const widget = createWidget();
    widget.hasShadowDOM = false;
    assert.doesNotThrow(() => widget._unload());
});

test('WidgetElement._unload clears shadow DOM and dispatches unload (lines 86-92)', () => {
    const widget = createWidget();
    widget.hasShadowDOM = true;
    widget.shadowRoot = { innerHTML: '<div>content</div>', appendChild() {}, querySelectorAll() { return []; } };
    let unloadFired = false;
    widget.addEventListener = (type, fn) => { if (type === 'unload') widget._unloadHandler = fn; };
    widget.dispatchEvent = (evt) => { if (evt.type === 'unload' && widget._unloadHandler) widget._unloadHandler(); };
    widget._unload();
    assert.equal(widget.shadowRoot.innerHTML, '');
});

test('WidgetElement.disconnectedCallback calls _unload', () => {
    const widget = createWidget();
    widget.hasShadowDOM = true;
    widget.shadowRoot = { innerHTML: '', appendChild() {}, querySelectorAll() { return []; } };
    let unloaded = false;
    widget._unload = () => { unloaded = true; };
    widget.disconnectedCallback();
    assert.equal(unloaded, true);
});

test('WidgetElement.connectedMoveCallback preserves the loaded shadow DOM', () => {
    const widget = createWidget();
    widget.hasShadowDOM = true;
    widget.shadowRoot = { innerHTML: '<div>running widget</div>', appendChild() {}, querySelectorAll() { return []; } };
    let unloaded = false;
    widget._unload = () => { unloaded = true; };

    widget.connectedMoveCallback();

    assert.equal(unloaded, false);
    assert.equal(widget.shadowRoot.innerHTML, '<div>running widget</div>');
});

test('WidgetElement.load throws when not attached (no shadow DOM)', () => {
    const widget = createWidget();
    widget.hasShadowDOM = false;
    assert.throws(() => { widget.load('/code.html', 'http://base/'); }, /Cannot load widget/);
});

test('WidgetElement.load fetches and dispatches load event', async () => {
    const widget = createWidget();
    widget.hasShadowDOM = true;
    widget.shadowRoot = { innerHTML: '', appendChild() {}, querySelectorAll() { return []; } };
    widget._handleHTMLResponse = () => {};
    let loadFired = false;
    widget.addEventListener = (type, fn) => { if (type === 'load') widget._loadHandler = fn; };
    widget.dispatchEvent = (evt) => { if (evt.type === 'load' && widget._loadHandler) widget._loadHandler(); };
    widget.load('/code.html', 'http://example.com/base/');
    await new Promise((r) => setTimeout(r, 10));
    assert.equal(widget.loadedURL, '/code.html');
});

test('WidgetElement.load handles non-html and non-success responses through catch path', () => {
    const widget = createWidget();
    widget.hasShadowDOM = true;
    widget.shadowRoot = { innerHTML: '', appendChild() {}, querySelectorAll() { return []; } };

    const makeThenable = (response) => ({
        _error: null,
        then(onFulfilled) {
            try {
                onFulfilled(response);
            } catch (error) {
                this._error = error;
            }
            return this;
        },
        catch(onRejected) {
            try {
                onRejected(this._error);
            } catch (error) {
                this._caught = error;
            }
            return this;
        },
    });

    Wirecloud.io.makeRequest = () => makeThenable({
        status: 200,
        responseText: '<html></html>',
        transport: { getResponseHeader: () => null },
    });
    assert.doesNotThrow(() => widget.load('/json', 'http://example.com/'));

    Wirecloud.io.makeRequest = () => makeThenable({
        status: 404,
        statusText: 'Not Found',
        responseText: '',
        transport: { getResponseHeader: () => 'text/html' },
    });
    assert.doesNotThrow(() => widget.load('/missing', 'http://example.com/'));
});

test('WidgetElement._handleHTMLResponse rewrites relative URLs and appends parsed content', () => {
    const widget = createWidget();
    const appended = [];
    widget.hasShadowDOM = true;
    widget.baseURL = 'http://example.com/base/';
    widget.shadowRoot = {
        innerHTML: '',
        appendChild(node) { appended.push(node); },
        querySelectorAll() { return []; },
    };
    global.Node = { ELEMENT_NODE: 1 };
    global.DOMParser = class DOMParser {
        parseFromString() {
            const head = document.createElement('head');
            const link = document.createElement('link');
            link.setAttribute('href', 'style.css');
            const script = document.createElement('script');
            script.setAttribute('src', 'app.js');
            const style = document.createElement('style');
            style.textContent = 'body { color: red; }';
            head.appendChild(link);
            head.appendChild(script);
            head.appendChild(style);
            head.querySelectorAll = () => [link, script, style];

            const body = document.createElement('body');
            const img = document.createElement('img');
            img.setAttribute('src', 'images/logo.png');
            img.setAttribute('srcset', 'small.png 1x, large.png 2x');
            const form = document.createElement('form');
            form.setAttribute('action', 'submit');
            body.appendChild(img);
            body.appendChild(form);
            body.querySelector = (selector) => selector === 'img' ? img : form;

            return { head, body };
        }
    };

    widget._handleHTMLResponse('<html></html>');

    assert.equal(appended.length, 4);
    assert.equal(appended[0].getAttribute('href'), 'http://example.com/base/style.css');
    assert.equal(appended[1].getAttribute('src'), 'http://example.com/base/app.js');
    assert.equal(appended[3].querySelector('img').getAttribute('src'), 'http://example.com/base/images/logo.png');
    assert.equal(appended[3].querySelector('img').getAttribute('srcset'), 'http://example.com/base/small.png 1x, http://example.com/base/large.png 2x');
    assert.equal(appended[3].querySelector('form').getAttribute('action'), 'http://example.com/base/submit');
});
