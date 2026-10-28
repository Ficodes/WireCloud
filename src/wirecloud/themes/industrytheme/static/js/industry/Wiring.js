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


(function (Industry, utils) {

    "use strict";

    const endpoint_label = function endpoint_label(endpoint) {
        if (endpoint == null) {
            return '';
        }
        return endpoint.title || endpoint.name || '';
    };

    /**
     * Wiring editor: shows a hint bar while a connection is being created and
     * keeps the header in sync with the sidebars.
     */
    Industry.WiringEditor = class WiringEditor extends Wirecloud.ui.WiringEditor {

        constructor(id, options) {
            super(id, options);

            this.hintElement = Industry.element('div', 'we-draft-hint hidden');
            this.hintElement.setAttribute('role', 'status');
            this.hintElement.setAttribute('aria-live', 'polite');
            this.wrapperElement.appendChild(this.hintElement);

            const show_hint = (engine, connection, initialEndpoint) => {
                const name = Industry.element('strong', null, [endpoint_label(initialEndpoint)]);
                const draft = engine._draft === true;
                const target = initialEndpoint != null && initialEndpoint.type === 'target';

                this.hintElement.innerHTML = '';
                this.hintElement.appendChild(document.createTextNode(target ?
                    utils.gettext("Choose an output to connect ") :
                    utils.gettext("Choose an input to connect ")));
                this.hintElement.appendChild(name);
                this.hintElement.appendChild(document.createTextNode(draft ?
                    utils.gettext(" · Esc to cancel") :
                    utils.gettext(" · release on an endpoint")));
                this.hintElement.classList.remove('hidden');
            };

            this.connectionEngine.addEventListener('dragstart', show_hint);
            this.connectionEngine.addEventListener('draftstart', show_hint);
            this.connectionEngine.addEventListener('dragend', () => {
                this.hintElement.classList.add('hidden');
                Industry.statusBar.refresh();
            });

            // The header shows the state of the sidebars (e.g. behaviours)
            [this.btnFindComponents, this.btnListBehaviours].forEach((button) => {
                button.addEventListener('active', () => {
                    if (button === this.btnFindComponents && this.componentManager != null) {
                        Industry.addDrawerCloseButton(this.componentManager.wrapperElement, () => {
                            if (this.btnFindComponents.active) {
                                this.btnFindComponents.click();
                            }
                        });
                    }
                    if (Wirecloud.UserInterfaceManager.header != null) {
                        Wirecloud.UserInterfaceManager.header.refresh();
                    }
                });
            });
        }

    };

    const TYPE_LABELS = {
        widget: () => utils.gettext("widget"),
        operator: () => utils.gettext("operator")
    };

    /**
     * Wiring components: translated type tag in the heading
     */
    Industry.ComponentDraggable = class ComponentDraggable extends Wirecloud.ui.WiringEditor.ComponentDraggable {

        constructor(wiringComponent, options) {
            super(wiringComponent, options);

            const heading = this.wrapperElement.querySelector('.panel-heading');
            if (heading != null && this.type in TYPE_LABELS) {
                heading.insertBefore(Industry.element('span', 'we-component-type', [TYPE_LABELS[this.type]()]), heading.firstChild);
            }
        }

    };

    Wirecloud.ui.registry.register('WiringEditor', Industry.WiringEditor);
    Wirecloud.ui.registry.register('WiringEditor.ComponentDraggable', Industry.ComponentDraggable);

})(Wirecloud.ui.Industry, Wirecloud.Utils);
