const test = require('node:test');
const assert = require('node:assert/strict');
const {resetLegacyRuntime, loadLegacyScripts} = require('../support/legacy-runtime.cjs');

const descendants = (node) => (node.childNodes || []).flatMap((child) => [child, ...descendants(child)]);
const select = (root, selector) => descendants(root).filter((node) => {
    const match = selector.match(/^(button)?\[([^\]]+)\]$/);
    return node.nodeType === 1 && node.hasAttribute(match[2]) && (!match[1] || node.tagName === 'BUTTON');
});
const element = (tag, attributes = {}, text = '') => {
    const node = document.createElement(tag);
    Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, value));
    if (text) node.appendChild(document.createTextNode(text));
    return node;
};

test.beforeEach(() => {
    resetLegacyRuntime();
    document.readyState = 'loading';
    loadLegacyScripts(['Utils', 'Event', 'ObjectWithEvents', 'StyledElements', 'Container', 'Fragment',
        'GUIBuilder', 'Tooltip', 'Panel', 'Button', 'Alert'].map((name) => `src/wirecloud/commons/static/js/StyledElements/${name}.js`));
    loadLegacyScripts(['src/wirecloud/oauth2provider/static/js/oauth2provider/pages.js']);
});

function fixture(actions) {
    const root = element('main');
    root.querySelectorAll = (selector) => select(root, selector);
    const panel = element('section', {'data-se-panel': ''});
    const title = element('h1', {'data-se-panel-title': '', id: 'page-title'}, 'Connect an application');
    title.id = 'page-title';
    const body = element('div', {'data-se-panel-body': ''});
    const message = element('p', {'data-se-alert': 'info'}, '<script>untrusted client name</script>');
    body.appendChild(message);
    const footer = element('div', {'data-se-panel-footer': ''});
    const form = element('form', {method: 'post'});
    const csrf = element('input', {type: 'hidden', name: 'csrf', value: 'browser-csrf-token'});
    const request = element('input', {type: 'hidden', name: 'request_id', value: 'browser-attempt'});
    form.appendChild(csrf);
    form.appendChild(request);
    const submissions = [];
    form.requestSubmit = (submitter) => {
        assert.equal(submitter.tagName, 'BUTTON');
        assert.equal(submitter.getAttribute('type'), 'submit');
        assert.ok(descendants(form).includes(submitter));
        submissions.push({name: submitter.getAttribute('name'), value: submitter.getAttribute('value'),
            csrf: csrf.getAttribute('value'), request_id: request.getAttribute('value')});
    };
    actions.forEach(([name, value, state]) => {
        const button = element('button', {'data-se-button': state, name, value,
            'aria-label': value === 'grant-123' ? 'Revoke access for Example client' : value}, value);
        button.form = form;
        form.appendChild(button);
    });
    footer.appendChild(form);
    panel.appendChild(title);
    panel.appendChild(body);
    panel.appendChild(footer);
    panel.querySelector = (selector) => select(panel, selector)[0] || null;
    root.appendChild(panel);
    return {root, form, title, csrf, request, submissions};
}

test('StyledElements panels and alerts preserve escaped content and native form fields', () => {
    const view = fixture([['decision', 'deny', 'default'], ['decision', 'approve', 'primary']]);
    StyledElements.OAuthPages.enhance(view.root);
    const panel = view.root.firstChild;
    assert.ok(panel.classList.contains('panel-default'));
    assert.equal(panel.getAttribute('aria-labelledby'), 'page-title');
    assert.ok(descendants(panel).includes(view.title));
    assert.ok(descendants(panel).includes(view.form));
    const alert = descendants(panel).find((node) => node.nodeType === 1 && node.classList.contains('alert-info'));
    assert.equal(alert.getAttribute('role'), 'note');
    assert.equal(alert.textContent, '<script>untrusted client name</script>');
    assert.equal(descendants(alert).filter((node) => node.tagName === 'SCRIPT').length, 0);
    assert.ok(descendants(view.form).includes(view.csrf));
    assert.equal(select(view.root, '[data-se-panel]').length, 0);
    // Initialization can safely run again after a partial page update.
    StyledElements.OAuthPages.enhance(view.root);
    assert.equal(view.root.firstChild, panel);
});

for (const [value, state, event] of [['approve', 'primary', 'click'], ['deny', 'default', 'keydown']]) {
    test(`StyledElements ${value} action submits its value and CSRF using ${event}`, () => {
        const view = fixture([['decision', value, state]]);
        StyledElements.OAuthPages.enhance(view.root);
        const button = descendants(view.form).find((node) => node.tagName === 'BUTTON');
        assert.ok(button.classList.contains(`btn-${state}`));
        button.dispatchEvent({type: event, key: 'Enter', altKey: false, ctrlKey: false, metaKey: false, shiftKey: false,
            target: button, preventDefault() {}, stopPropagation() {}});
        assert.deepEqual(view.submissions, [{name: 'decision', value, csrf: 'browser-csrf-token', request_id: 'browser-attempt'}]);
    });
}

test('StyledElements revocation keeps its grant ID and accessible label', () => {
    const view = fixture([['grant_id', 'grant-123', 'danger']]);
    StyledElements.OAuthPages.enhance(view.root);
    const button = descendants(view.form).find((node) => node.tagName === 'BUTTON');
    assert.equal(button.getAttribute('aria-label'), 'Revoke access for Example client');
    button.dispatchEvent({type: 'click', target: button, preventDefault() {}, stopPropagation() {}});
    assert.equal(view.submissions[0].value, 'grant-123');
    assert.equal(view.submissions[0].csrf, 'browser-csrf-token');
});
