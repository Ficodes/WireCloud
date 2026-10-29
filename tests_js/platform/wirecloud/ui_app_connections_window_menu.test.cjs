const test = require('node:test');
const assert = require('node:assert/strict');
const {resetLegacyRuntime, loadLegacyScripts} = require('../../support/legacy-runtime.cjs');

const descendants = (node) => (node.childNodes || []).flatMap((child) => [child, ...descendants(child)]);
const click = (node) => node.dispatchEvent({type: 'click', target: node, preventDefault() {}, stopPropagation() {}});
let requests;

test.beforeEach(() => {
    resetLegacyRuntime();
    loadLegacyScripts(['Utils', 'Event', 'ObjectWithEvents', 'StyledElements', 'Container', 'Fragment',
        'GUIBuilder', 'Tooltip', 'Panel', 'Button', 'Alert', 'InputElement', 'ButtonsGroup', 'CheckBox']
        .map((name) => `src/wirecloud/commons/static/js/StyledElements/${name}.js`));
    requests = [];
    global.Wirecloud = {
        Utils: StyledElements.Utils,
        URLs: {OAUTH2_CONNECTIONS: '/wirecloud/oauth2/connections'},
        io: {makeRequest: (url, options) => requests.push({url, ...options})},
        ui: {WindowMenu: class {
            constructor(title, className) {
                this.title = title;
                this.className = className;
                this.windowContent = document.createElement('div');
                this.windowBottom = document.createElement('div');
            }
            repaint() {}
            hide() { this.hidden = true; }
        }}
    };
    loadLegacyScripts(['src/wirecloud/platform/static/js/wirecloud/ui/AppConnectionsWindowMenu.js']);
});

const respond = (request, connections = [], csrf = 'csrf-token') => request.onSuccess({responseText: JSON.stringify({connections, csrf})});
const connection = {
    id: 'grant-1', client_name: '<img src=x onerror=alert(1)>', client_id: 'https://client.example/id',
    resource_name: 'Workspace access', permissions: ['Read accessible data', 'Edit workspaces']
};

test('connection modal renders real StyledElements, safe client details, and revokes without navigation', () => {
    const menu = new Wirecloud.ui.AppConnectionsWindowMenu();
    assert.equal(menu.title, 'App connections');
    assert.match(menu.windowContent.textContent, /Loading/);
    assert.equal(requests[0].url, '/wirecloud/oauth2/connections');
    assert.equal(requests[0].requestHeaders.Accept, 'application/json');
    respond(requests[0], [connection]);
    assert.match(menu.windowContent.textContent, /Edit workspaces/);
    assert.match(menu.windowContent.textContent, /https:\/\/client.example\/id/);
    assert.match(menu.windowContent.textContent, /<img src=x/);
    assert.equal(descendants(menu.windowContent).filter((node) => node.tagName === 'IMG').length, 0);
    assert.equal(descendants(menu.windowContent).filter((node) => node.tagName === 'DETAILS').length, 1);
    const revoke = menu.buttons[0].wrapperElement;
    assert.ok(descendants(menu.windowContent).includes(revoke));
    assert.ok(revoke.parentNode.classList.contains('app-connection-footer'));
    assert.equal(descendants(menu.windowContent).filter((node) => node.classList?.contains('panel-options')).length, 0);
    assert.equal(revoke.getAttribute('aria-label'), 'Revoke access for ' + connection.client_name);
    click(revoke);
    assert.equal(requests[1].method, 'POST');
    assert.deepEqual(requests[1].parameters, {csrf: 'csrf-token', grant_id: 'grant-1'});
    assert.equal(menu.buttons[0].enabled, false);
    requests[1].onSuccess({});
    respond(requests[2], [], 'new-csrf-token');
    assert.match(menu.windowContent.textContent, /No connected applications/);
    assert.equal(menu.csrf, 'new-csrf-token');
    click(descendants(menu.windowBottom).find((node) => node.getAttribute?.('role') === 'button' && node.textContent === 'Close'));
    assert.equal(menu.hidden, true);
});

test('connection modal handles invalid responses, expired sessions, and retry', () => {
    const menu = new Wirecloud.ui.AppConnectionsWindowMenu();
    requests[0].onSuccess({responseText: '<html>login</html>'});
    assert.match(menu.windowContent.textContent, /Unable to load/);
    click(menu.retry.wrapperElement);
    assert.equal(requests.length, 2);
    requests[1].onFailure({status: 401});
    assert.match(menu.windowContent.textContent, /session has expired/);
    click(menu.retry.wrapperElement);
    respond(requests[2]);
    assert.match(menu.windowContent.textContent, /No connected applications/);
});

test('connection modal recovers from failed revocation by fetching fresh CSRF and connections', () => {
    const menu = new Wirecloud.ui.AppConnectionsWindowMenu();
    respond(requests[0], [connection]);
    click(menu.buttons[0].wrapperElement);
    requests[1].onFailure({status: 403});
    assert.match(menu.windowContent.textContent, /Access denied/);
    click(menu.retry.wrapperElement);
    respond(requests[2], [connection], 'fresh-csrf');
    click(menu.buttons[0].wrapperElement);
    assert.equal(requests[3].parameters.csrf, 'fresh-csrf');
});

test('permission editing saves checked scopes and reloads current state and CSRF', () => {
    const menu = new Wirecloud.ui.AppConnectionsWindowMenu();
    const editable = {...connection, scope_options: [
        {scope: 'read', description: 'Read accessible data', selected: true},
        {scope: 'write', description: 'Edit workspaces', selected: false}
    ]};
    respond(requests[0], [editable]);
    const [read, write] = menu.permissionInputs;
    const save = menu.buttons[1];
    assert.equal(read.getValue(), true);
    assert.equal(write.getValue(), false);
    assert.equal(save.enabled, false);
    write.setValue(true);
    write.inputElement.dispatchEvent({type: 'change'});
    assert.equal(save.enabled, true);
    read.setValue(false);
    read.inputElement.dispatchEvent({type: 'change'});
    click(save.wrapperElement);
    assert.deepEqual(requests[1].parameters, {
        csrf: 'csrf-token', grant_id: 'grant-1', action: 'update_permissions', scope: 'write'
    });
    assert.ok(menu.buttons.every((button) => !button.enabled));
    assert.ok(menu.permissionInputs.every((input) => !input.enabled));
    requests[1].onSuccess({});
    respond(requests[2], [{...editable, scope_options: editable.scope_options.map((option) => ({
        ...option, selected: option.scope === 'write'
    }))}], 'fresh-csrf');
    assert.equal(menu.csrf, 'fresh-csrf');
    assert.equal(menu.permissionInputs[0].getValue(), false);
    assert.equal(menu.permissionInputs[1].getValue(), true);
    assert.equal(menu.buttons[1].enabled, false);
});

test('permission editing disables saving an empty selection and recovers after a failed save', () => {
    const menu = new Wirecloud.ui.AppConnectionsWindowMenu();
    respond(requests[0], [{...connection, scope_options: [
        {scope: 'read', description: 'Read accessible data', selected: true},
        {scope: 'write', description: 'Edit workspaces', selected: false}
    ]}]);
    const [read, write] = menu.permissionInputs;
    const save = menu.buttons[1];
    read.setValue(false);
    read.inputElement.dispatchEvent({type: 'change'});
    assert.equal(save.enabled, false);
    write.setValue(true);
    write.inputElement.dispatchEvent({type: 'change'});
    click(save.wrapperElement);
    requests[1].onFailure({status: 500});
    assert.match(menu.windowContent.textContent, /Unable to update/);
    click(menu.retry.wrapperElement);
    assert.equal(requests[2].method, 'GET');
});
