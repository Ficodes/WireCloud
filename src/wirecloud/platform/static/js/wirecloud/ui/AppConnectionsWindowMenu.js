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

/* globals Wirecloud, StyledElements */

(function (ns, se, utils) {

    "use strict";

    ns.AppConnectionsWindowMenu = class AppConnectionsWindowMenu extends ns.WindowMenu {

        constructor() {
            super(utils.gettext('App connections'), 'wc-app-connections');
            this.buttons = [];
            this.permissionInputs = [];
            this.content = new se.Container();
            this.content.wrapperElement.setAttribute('aria-live', 'polite');
            this.content.insertInto(this.windowContent);
            this.retry = new se.Button({text: utils.gettext('Retry'), class: 'btn-default'});
            this.retry.addEventListener('click', () => this.load());
            this.retry.insertInto(this.windowBottom);
            const close = new se.Button({text: utils.gettext('Close'), class: 'btn-default'});
            close.addEventListener('click', () => this.hide());
            close.insertInto(this.windowBottom);
            this.load();
        }

        showError(response, fallback) {
            let message = fallback || utils.gettext('Unable to load app connections. Please try again.');
            if (response && response.status === 401) {
                message = utils.gettext('Your session has expired. Sign in again to manage app connections.');
            } else if (response && response.status === 403) {
                message = utils.gettext('Access denied. Reopen App connections and try again.');
            }
            this.content.clear().appendChild(new se.Alert({state: 'danger', title: message}));
            this.retry.show();
            this.repaint();
        }

        load(notice) {
            this.retry.hide();
            this.buttons = [];
            this.permissionInputs = [];
            this.content.clear().appendChild(utils.gettext('Loading app connections…'));
            Wirecloud.io.makeRequest(Wirecloud.URLs.OAUTH2_CONNECTIONS, {
                method: 'GET',
                requestHeaders: {'Accept': 'application/json'},
                onSuccess: (response) => {
                    let data;
                    try {
                        data = JSON.parse(response.responseText);
                        if (!Array.isArray(data.connections) || typeof data.csrf !== 'string') {
                            throw new TypeError('Invalid connections response');
                        }
                    } catch (error) {
                        this.showError();
                        return;
                    }
                    this.csrf = data.csrf;
                    this.render(data.connections, notice);
                },
                onFailure: (response) => this.showError(response)
            });
        }

        render(connections, notice) {
            this.content.clear();
            if (notice) {
                this.content.appendChild(new se.Alert({state: 'success', title: notice}));
            }
            if (connections.length === 0) {
                const empty = new se.Alert({state: 'info', title: utils.gettext('No connected applications')});
                empty.body.appendChild(utils.gettext('Applications you authorize will appear here. You can change their permissions or revoke their access at any time.'));
                this.content.appendChild(empty);
            }
            connections.forEach((connection) => {
                const revoke = new se.Button({text: utils.gettext('Revoke'), class: 'btn-danger'});
                revoke.wrapperElement.setAttribute('aria-label', utils.gettext('Revoke access for') + ' ' + connection.client_name);
                revoke.addEventListener('click', () => this.revoke(connection.id));
                this.buttons.push(revoke);
                const panel = new se.Panel({title: connection.client_name, subtitle: connection.resource_name});
                const permissions = new se.Container({tagname: 'ul', class: 'app-connection-permissions'});
                let save;
                if (connection.scope_options && connection.scope_options.length) {
                    const controls = [];
                    save = new se.Button({text: utils.gettext('Save permissions'), class: 'btn-primary'});
                    save.wrapperElement.setAttribute('aria-label', utils.gettext('Save permissions for') + ' ' + connection.client_name);
                    save.disable();
                    permissions.wrapperElement.setAttribute('role', 'group');
                    permissions.wrapperElement.setAttribute('aria-label', utils.gettext('Permissions for') + ' ' + connection.client_name);
                    connection.scope_options.forEach((option) => {
                        const checkbox = new se.CheckBox({initialValue: option.selected});
                        const label = new se.Container({tagname: 'label', class: 'app-connection-permission'});
                        label.appendChild(checkbox).appendChild(utils.gettext(option.description));
                        permissions.appendChild(new se.Container({tagname: 'li'}).appendChild(label));
                        controls.push({scope: option.scope, selected: option.selected, input: checkbox});
                        this.permissionInputs.push(checkbox);
                        checkbox.addEventListener('change', () => {
                            const changed = controls.some((control) => control.input.getValue() !== control.selected);
                            const selected = controls.some((control) => control.input.getValue());
                            save.setDisabled(!changed || !selected);
                        });
                    });
                    save.addEventListener('click', () => this.updatePermissions(connection.id,
                        controls.filter((control) => control.input.getValue()).map((control) => control.scope)));
                    this.buttons.push(save);
                } else {
                    connection.permissions.forEach((permission) => {
                        permissions.appendChild(new se.Container({tagname: 'li'}).appendChild(utils.gettext(permission)));
                    });
                }
                panel.body.appendChild(permissions);
                if (save) {
                    panel.body.appendChild(new se.Container({tagname: 'p', class: 'app-connection-help'})
                        .appendChild(utils.gettext('Changes apply immediately to this connection. Select at least one permission, or revoke access.')));
                }
                const footer = new se.Container({class: 'panel-footer app-connection-footer'});
                const details = new se.Container({tagname: 'details', class: 'app-connection-details'});
                details.appendChild(new se.Container({tagname: 'summary'}).appendChild(utils.gettext('Application ID')));
                details.appendChild(new se.Container({tagname: 'p'}).appendChild(connection.client_id));
                footer.appendChild(details);
                if (save) {
                    footer.appendChild(save);
                }
                footer.appendChild(revoke);
                footer.insertInto(panel.wrapperElement);
                this.content.appendChild(panel);
            });
            this.repaint();
        }

        revoke(grantId) {
            this.changeConnection({grant_id: grantId});
        }

        updatePermissions(grantId, scopes) {
            this.changeConnection({grant_id: grantId, action: 'update_permissions', scope: scopes.join(' ')});
        }

        changeConnection(parameters) {
            this.buttons.forEach((button) => button.disable());
            this.permissionInputs.forEach((input) => input.disable());
            Wirecloud.io.makeRequest(Wirecloud.URLs.OAUTH2_CONNECTIONS, {
                method: 'POST',
                requestHeaders: {'Accept': 'application/json'},
                parameters: {csrf: this.csrf, ...parameters},
                onSuccess: () => this.load(parameters.action === 'update_permissions'
                    ? utils.gettext('Permissions updated.') : utils.gettext('Access revoked.')),
                onFailure: (response) => this.showError(response, utils.gettext('Unable to update app connections. Please try again.'))
            });
        }

    };

})(Wirecloud.ui, StyledElements, Wirecloud.Utils);
